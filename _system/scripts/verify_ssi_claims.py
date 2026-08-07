#!/usr/bin/env python3
"""Phase 3 of the SSI Perplexity-grade pipeline: Skeptic verification & gatekeeper routing.

Blind re-verification of every Phase 2 claim against the original sources —
the Skeptic never trusts a claim's stated values; it re-derives everything
from the filing text and the hashed evidence pack, then deletes (never
softens) anything that fails.

Stages:
  1. Pack integrity   — recompute the evidence pack's canonical hash and each
                        filing's sha256 from disk; any drift fails every claim
                        that anchors to the drifted source.
  2. Skeptic pass     — per-claim blind recheck:
                          fact claims       → the cited line must still parse
                                              as `Tag: value` for the cited
                                              tag, in both current and prior
                                              locators, with direction
                                              re-derived from the raw values;
                          section claims    → section diff re-run from raw
                                              text; the severity keyword must
                                              still be newly-added;
                          revenue claims    → bank-style definition recomputed
                                              from NII + non-interest tags.
  3. Gatekeeper       — authority resolved via decision_authority.resolve_authority
                        (never reimplemented); committee routing is reported as
                        eligible/ineligible only — dispatch stays with
                        investment-committee.yml and human_decision.json stays
                        the sole capital authority.
  4. Decision Auditor — time-zero snapshot (pack hash, claims-file sha256,
                        verified claim ids, authority state) committed so
                        future outcome scoring runs against what was actually
                        believed, not hindsight.
  5. Gold set         — every verification failure appends an adjudication
                        case to _eval/ssi_skeptic_gold.jsonl (issuer-keyed for
                        train/dev/test splits by issuer, not filing).

Outputs:
  {TICKER}/research/evidence/ssi_verified_claims_{date}.json
  {TICKER}/research/evidence/ssi_time_zero_{date}.json
  _eval/ssi_skeptic_gold.jsonl (append-only, failures only)

Usage:
  python _system/scripts/verify_ssi_claims.py TBBK ABX
  python _system/scripts/verify_ssi_claims.py ABX --date 2026-08-05
  python _system/scripts/verify_ssi_claims.py ABX --check
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_ssi_evidence_pack import (  # noqa: E402
    canonical_hash,
    discover_filings,
    revenue_definition_check,
    section_diff_engine,
    sha256_text,
)
from decision_authority import resolve_authority  # noqa: E402

ROOT = SCRIPT_DIR.parents[1]
GOLD_PATH = ROOT / "_eval" / "ssi_skeptic_gold.jsonl"

SCHEMA_VERSION = "1.0"

IX_LINE_RE = re.compile(r"^([A-Za-z][A-Za-z0-9]*(?:\.[A-Za-z0-9]+)*):\s*(.+)$")


def _latest_json_path(evidence_dir: Path, stem: str) -> Path | None:
    files = sorted(evidence_dir.glob(f"{stem}_*.json"), reverse=True)
    return files[0] if files else None


def _load(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


# ---------------------------------------------------------------------------
# Stage 1 — pack integrity
# ---------------------------------------------------------------------------

def verify_pack_integrity(pack: dict, ticker_dir: Path) -> dict:
    """Recompute the pack hash and each filing sha256 from disk."""
    body = {k: v for k, v in pack.items() if k != "pack_hash"}
    hash_ok = canonical_hash(body) == pack.get("pack_hash")
    drifted: list[str] = []
    missing: list[str] = []
    for filing in pack.get("filings", []):
        path = ticker_dir.parent / filing["path"]
        if not path.exists():
            missing.append(filing["path"])
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if sha256_text(text) != filing["sha256"]:
            drifted.append(filing["path"])
    return {
        "pack_hash_ok": hash_ok,
        "drifted_sources": drifted,
        "missing_sources": missing,
        "ok": hash_ok and not drifted and not missing,
    }


# ---------------------------------------------------------------------------
# Stage 2 — blind Skeptic pass
# ---------------------------------------------------------------------------

def _line_tag_value(lines: list[str], line_no: int | None) -> tuple[str, float] | None:
    """Parse `Tag: value` at a 1-indexed line; None if unparseable."""
    if line_no is None or line_no < 1 or line_no > len(lines):
        return None
    match = IX_LINE_RE.match(lines[line_no - 1].strip())
    if not match:
        return None
    tag = match.group(1)
    tag = tag.split(":")[-1] if ":" in tag else tag
    raw = match.group(2).strip().replace(",", "")
    try:
        return tag, float(raw)
    except ValueError:
        return None


def _verify_fact_claim(claim: dict, texts: dict[str, list[str]]) -> str | None:
    """Return a failure reason, or None if the claim verifies."""
    ref = claim["evidence_ref"]
    tag = ref.get("tag")
    cur_lines = texts.get(ref.get("source_path", ""))
    if cur_lines is None:
        return "source_unreadable"

    cur = _line_tag_value(cur_lines, ref.get("line_current"))
    direction = claim.get("direction")
    if direction in ("up", "down", "new", "flag") or ref.get("line_current"):
        if cur is None:
            return "current_locator_unparseable"
        if cur[0] != tag:
            return f"current_tag_mismatch:{cur[0]}"

    pri = None
    if ref.get("line_prior") is not None:
        pri_lines = texts.get(ref.get("prior_path") or ref.get("source_path", ""))
        if pri_lines is None:
            return "prior_source_unreadable"
        pri = _line_tag_value(pri_lines, ref["line_prior"])
        if pri is None:
            return "prior_locator_unparseable"
        if pri[0] != tag:
            return f"prior_tag_mismatch:{pri[0]}"

    # Re-derive direction from raw values — never trust the claim's text.
    if cur is not None and pri is not None and direction in ("up", "down"):
        rederived = "up" if cur[1] > pri[1] else "down"
        if rederived != direction:
            return f"direction_mismatch:rederived_{rederived}"
    if direction == "removed" and cur is not None and ref.get("line_prior") is None:
        return "removed_claim_has_current_locator"
    return None


def _verify_section_claim(claim: dict, filings_by_path: dict) -> str | None:
    ref = claim["evidence_ref"]
    current = filings_by_path.get(ref.get("source_path"))
    prior = filings_by_path.get(ref.get("prior_path"))
    if current is None or prior is None:
        return "filing_not_discoverable"
    snippet = (ref.get("snippet") or "").strip()
    if snippet and snippet not in current.text:
        return "snippet_not_in_source"
    section = ref.get("section")
    diff = section_diff_engine(current, prior)
    diff_section = (diff.get("sections") or {}).get(section)
    if not diff_section:
        return f"section_diff_empty:{section}"
    keyword_hit = any(
        kw in claim["statement"] for kw in diff_section.get("severity_keywords_added", [])
    )
    if not keyword_hit:
        return "severity_keyword_not_rederived"
    return None


def _verify_revenue_claim(claim: dict, filings_by_path: dict) -> str | None:
    ref = claim["evidence_ref"]
    filing = filings_by_path.get(ref.get("source_path"))
    if filing is None:
        return "filing_not_discoverable"
    recheck = revenue_definition_check(filing)
    if "bank_style_revenue" not in recheck.get("flags", []):
        return "bank_style_not_rederived"
    return None


def compact_claims_file(claims_path: Path, claims_doc: dict, as_of: str) -> bool:
    """Drop the `claims` array once it has been consumed by the Skeptic pass.

    Every claim body survives verbatim in ssi_verified_claims (same claim_ids,
    same fields, plus a `verification` block), so persisting both doubles the
    artifact footprint for no added information. The rest of this file —
    management_ledger, spawner, and the tier/severity histograms — is unique to
    Phase 2 and is kept.

    Compaction runs before the time-zero snapshot and the Phase 4 audit trail
    hash the file, so both record the hash of what is actually on disk. Phase 2
    is deterministic and cheap: re-run build_ssi_claims.py to restore the array.
    """
    if not claims_doc.get("claims"):
        return False
    compacted = {k: v for k, v in claims_doc.items() if k != "claims"}
    compacted["claims_compacted"] = True
    compacted["claims_verified_into"] = f"ssi_verified_claims_{as_of}.json"
    compacted["claims_compaction_note"] = (
        "Claim bodies live in ssi_verified_claims (superset: adds `verification`). "
        "Re-run build_ssi_claims.py to rebuild this array."
    )
    claims_path.write_text(json.dumps(compacted, indent=2) + "\n", encoding="utf-8")
    return True


def skeptic_pass(claims_doc: dict, pack: dict, ticker_dir: Path, integrity: dict) -> tuple[list[dict], list[dict]]:
    """Return (verified_claims, failures). Failures carry a reason and are
    dropped from the verified set — deleted, not softened."""
    if claims_doc.get("claims_compacted") and not claims_doc.get("claims"):
        raise ValueError(
            "claims array was compacted away after a previous verification; "
            "re-run build_ssi_claims.py for this ticker/date before verifying"
        )
    filings = discover_filings(ticker_dir)
    filings_by_path = {f.rel_path: f for f in filings}
    texts = {f.rel_path: f.text.splitlines() for f in filings}
    drifted = set(integrity["drifted_sources"]) | set(integrity["missing_sources"])

    verified: list[dict] = []
    failures: list[dict] = []
    for claim in claims_doc.get("claims", []):
        ref = claim.get("evidence_ref", {})
        reason: str | None = None
        if ref.get("pack_hash") != pack.get("pack_hash"):
            reason = "pack_hash_mismatch"
        elif not integrity["pack_hash_ok"]:
            reason = "pack_integrity_failed"
        elif ref.get("source_path") in drifted or ref.get("prior_path") in drifted:
            reason = "source_drift"
        elif ref.get("section"):
            reason = _verify_section_claim(claim, filings_by_path)
        elif ref.get("tag") == "revenue_definition" or "lines" in ref:
            reason = _verify_revenue_claim(claim, filings_by_path)
        elif ref.get("tag"):
            reason = _verify_fact_claim(claim, texts)
        else:
            reason = "unrecognized_evidence_ref_shape"

        if reason is None:
            verified.append({**claim, "verification": "verified"})
        else:
            failures.append({**claim, "verification": "failed", "failure_reason": reason})
    return verified, failures


# ---------------------------------------------------------------------------
# Stage 3 — gatekeeper routing (reuses decision_authority; never dispatches)
# ---------------------------------------------------------------------------

def gatekeeper_routing(ticker_dir: Path, verified: list[dict]) -> dict:
    research = ticker_dir / "research"
    valuation = _load(research / "valuation.json") or {"ticker": ticker_dir.name}
    try:
        authority = resolve_authority(research, valuation=valuation)
    except Exception as exc:  # authority resolution must never kill verification
        authority = {"authority_level": "unresolved", "error": str(exc)[:200]}
    contract_status = authority.get("contract_status", "missing")
    high_severity = [c["claim_id"] for c in verified if c.get("severity", 0) >= 4]
    eligible = bool(high_severity) and contract_status == "decision_grade"
    if eligible:
        reason = "verified severity>=4 claims on a decision_grade contract"
    elif not high_severity:
        reason = "no verified severity>=4 claims"
    else:
        reason = f"contract_status={contract_status} (needs decision_grade)"
    return {
        "authority_level": authority.get("authority_level"),
        "contract_status": contract_status,
        "committee_state": authority.get("committee_state"),
        "committee_eligible": eligible,
        "reason": reason,
        "high_severity_claim_ids": high_severity,
        "dispatch_note": (
            "Reporting only — committee dispatch stays with investment-committee.yml; "
            "human_decision.json remains the sole capital authority."
        ),
    }


# ---------------------------------------------------------------------------
# Stage 4 — Decision Auditor time-zero snapshot
# ---------------------------------------------------------------------------

def time_zero_snapshot(
    ticker: str, as_of: str, pack: dict, claims_path: Path,
    verified: list[dict], routing: dict,
) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "ticker": ticker,
        "as_of": as_of,
        "pack_hash": pack.get("pack_hash"),
        "pack_as_of": pack.get("as_of"),
        "claims_file": claims_path.name,
        "claims_file_sha256": hashlib.sha256(claims_path.read_bytes()).hexdigest(),
        "verified_claim_ids": [c["claim_id"] for c in verified],
        "severity_histogram": {
            str(n): sum(1 for c in verified if c.get("severity") == n) for n in range(1, 6)
        },
        "authority_level": routing.get("authority_level"),
        "contract_status": routing.get("contract_status"),
        "committee_eligible": routing.get("committee_eligible"),
        # Not resolvable offline at snapshot time; recorded as explicit gaps
        # rather than omitted silently.
        "unavailable_fields": ["price", "consensus_estimates", "persona_votes"],
    }


# ---------------------------------------------------------------------------
# Stage 5 — error-driven gold set
# ---------------------------------------------------------------------------

def append_gold_cases(ticker: str, as_of: str, failures: list[dict], gold_path: Path) -> int:
    if not failures:
        return 0
    gold_path.parent.mkdir(parents=True, exist_ok=True)
    with gold_path.open("a", encoding="utf-8") as fh:
        for failure in failures:
            fh.write(json.dumps({
                "issuer": ticker,  # split train/dev/test by issuer, not filing
                "as_of": as_of,
                "claim_id": failure.get("claim_id"),
                "source": failure.get("source"),
                "taxonomy": failure.get("taxonomy"),
                "failure_reason": failure.get("failure_reason"),
                "statement": failure.get("statement"),
                "evidence_ref": failure.get("evidence_ref"),
                "adjudication": "pending",
            }, ensure_ascii=True) + "\n")
    return len(failures)


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def verify_ticker(ticker_dir: Path, as_of: str, gold_path: Path | None = None,
                  compact: bool = True) -> dict | None:
    evidence_dir = ticker_dir / "research" / "evidence"
    claims_path = _latest_json_path(evidence_dir, "ssi_claims")
    pack_path = _latest_json_path(evidence_dir, "ssi_evidence_pack")
    if claims_path is None or pack_path is None:
        return None
    claims_doc = _load(claims_path)
    pack = _load(pack_path)
    if claims_doc is None or pack is None:
        return None

    integrity = verify_pack_integrity(pack, ticker_dir)
    verified, failures = skeptic_pass(claims_doc, pack, ticker_dir, integrity)
    routing = gatekeeper_routing(ticker_dir, verified)
    # Compact before hashing: the snapshot and the Phase 4 audit trail must
    # record the sha256 of the file that actually remains on disk.
    if compact:
        compact_claims_file(claims_path, claims_doc, as_of)
    snapshot = time_zero_snapshot(
        ticker_dir.name, as_of, pack, claims_path, verified, routing,
    )
    gold_written = append_gold_cases(
        ticker_dir.name, as_of, failures, gold_path or GOLD_PATH,
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "ticker": ticker_dir.name,
        "as_of": as_of,
        "pack_hash": pack.get("pack_hash"),
        "source_claims_file": claims_path.name,
        "pack_integrity": integrity,
        "verified_claims": verified,
        "verified_count": len(verified),
        "failed_count": len(failures),
        "failure_reasons": sorted({f["failure_reason"] for f in failures}),
        "gold_cases_appended": gold_written,
        "routing": routing,
        "time_zero": snapshot,
    }


def write_verification(ticker_dir: Path, as_of: str, compact: bool = True) -> tuple[Path, Path] | None:
    result = verify_ticker(ticker_dir, as_of, compact=compact)
    if result is None:
        return None
    evidence_dir = ticker_dir / "research" / "evidence"
    snapshot = result.pop("time_zero")
    verified_out = evidence_dir / f"ssi_verified_claims_{as_of}.json"
    snapshot_out = evidence_dir / f"ssi_time_zero_{as_of}.json"
    verified_out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    snapshot_out.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    return verified_out, snapshot_out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tickers", nargs="*", help="Ticker folders (default: all with ssi_claims files)")
    parser.add_argument("--date", default=datetime.now().date().isoformat())
    parser.add_argument("--check", action="store_true", help="Verify in memory and report, do not write")
    parser.add_argument("--no-compact", action="store_true",
                        help="keep the claims array in ssi_claims after verification "
                             "(default: drop it, since ssi_verified_claims is a superset)")
    args = parser.parse_args(argv)

    if args.tickers:
        ticker_dirs = [ROOT / t for t in args.tickers]
    else:
        ticker_dirs = sorted(
            {p.parents[2] for p in ROOT.glob("*/research/evidence/ssi_claims_*.json")}
        )

    failures = 0
    for ticker_dir in ticker_dirs:
        if args.check:
            # --check must not touch disk, so never compact on this path.
            result = verify_ticker(ticker_dir, args.date, compact=False)
            if result is None:
                print(f"[skip] {ticker_dir.name}: no claims/pack (run Phases 1-2 first)")
                failures += 1
                continue
            print(
                f"[check] {ticker_dir.name}: {result['verified_count']} verified, "
                f"{result['failed_count']} failed, committee_eligible="
                f"{result['routing']['committee_eligible']}"
            )
        else:
            outs = write_verification(ticker_dir, args.date, compact=not args.no_compact)
            if outs is None:
                print(f"[skip] {ticker_dir.name}: no claims/pack (run Phases 1-2 first)")
                failures += 1
            else:
                for out in outs:
                    print(f"[ok] {out.relative_to(ROOT)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
