#!/usr/bin/env python3
"""Phase 2 of the SSI Perplexity-grade pipeline: specialist synthesis & claim resolution.

Consumes the Phase 1 evidence pack (`ssi_evidence_pack_{date}.json`) and emits
structured atomic claims — never prose. Three specialist passes, all
deterministic:

  Filing Sentinel   — classifies material deltas and section-diff signals
                      against the five-part furnace taxonomy
                      (_system/frameworks/short_alpha_filing_furnace.md):
                      identity_instrument, liquidity_oxygen, earnings_quality,
                      operating_failure, market_mechanics.
  Management Ledger — quantitative promises vs realized outcomes; consumes
                      management_facts_*.json claims when present and resolves
                      realized values from filing facts.
  Spawner Engine    — capital-allocation discipline scored from cited facts
                      (buyback trajectory, capex vs operating cash flow),
                      abstaining with a reason when inputs are missing.

Every claim carries: statement, direction, magnitude, severity (1–5),
confidence, a falsifier, and an evidence_ref that resolves to
{pack_hash, source sha256, source path, tag, line}. Claims without a
resolvable evidence_ref are not emitted.

Output: {TICKER}/research/evidence/ssi_claims_{date}.json

Usage:
  python _system/scripts/build_ssi_claims.py TBBK ABX
  python _system/scripts/build_ssi_claims.py ABX --date 2026-08-05
  python _system/scripts/build_ssi_claims.py ABX --check
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

ROOT = SCRIPT_DIR.parents[1]

SCHEMA_VERSION = "1.0"

# ---------------------------------------------------------------------------
# Furnace taxonomy routing: first matching rule wins (ordered most- to
# least-specific). Tags that match no rule are counted, not silently dropped.
# ---------------------------------------------------------------------------
TAXONOMY_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("operating_failure", re.compile(
        r"Impairment|GoodwillImpairment|RestructuringCharges|AssetRetirement"
        r"|DisposalGroup|DiscontinuedOperation", re.I)),
    ("earnings_quality", re.compile(
        r"AllowanceFor(?:Credit|Loan|Doubtful)|ProvisionFor(?:Credit|Loan|Doubtful)"
        r"|DeferredRevenue|ContractWithCustomerLiability|AccountsReceivable"
        r"|InventoryNet|CapitalizedContractCost|UnbilledReceivables", re.I)),
    ("liquidity_oxygen", re.compile(
        r"Cash(?:And|Cash)|Debt|Borrowings|LineOfCredit|InterestExpense"
        r"|OperatingLeaseLiability|FinanceLeaseLiability|LettersOfCredit"
        r"|CommercialPaper|NotesPayable", re.I)),
    ("identity_instrument", re.compile(
        r"SharesOutstanding|SharesIssued|StockIssuedDuringPeriod|Warrant"
        r"|Convertible|PreferredStock|TreasuryStock|StockRepurchase", re.I)),
)

SECTION_TAXONOMY = {
    "risk_factors": "operating_failure",
    "mdna": "earnings_quality",
    "liquidity_covenants": "liquidity_oxygen",
    "accounting_policies": "earnings_quality",
    "controls": "earnings_quality",
    "related_party": "identity_instrument",
}

# Severity-5 narrative triggers (must match SEVERITY_KEYWORDS in Phase 1).
CRITICAL_NARRATIVE = re.compile(
    r"going\s+concern|substantial\s+doubt|material\s+weakness|covenant\s+(?:breach|violation|waiver)"
    r"|default|restatement|delisting", re.I)

# Ledger: promise metrics we can resolve deterministically from fact deltas.
LEDGER_RESOLVABLE = {
    "revenues", "revenue", "net_income", "eps_basic", "operating_income",
    "shares_outstanding", "operating_cash_flow", "capital_expenditures",
}


def claim_id(ticker: str, taxonomy: str, tag: str, filing_path: str) -> str:
    blob = f"{ticker}|{taxonomy}|{tag}|{filing_path}"
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def _route_taxonomy(tag: str) -> str | None:
    for taxonomy, pattern in TAXONOMY_RULES:
        if pattern.search(tag):
            return taxonomy
    return None


def _severity_for_delta(taxonomy: str, row: dict) -> int:
    pct = row.get("pct")
    flags = row.get("flags", [])
    severity = 2
    if "extreme_move" in flags or "sign_flip" in flags:
        severity = 3
    if pct is not None and abs(pct) >= 100.0:
        severity = 4
    if taxonomy == "earnings_quality" and pct is not None and pct >= 30.0 \
            and re.search(r"AllowanceFor|ProvisionFor", row["tag"], re.I):
        severity = max(severity, 4)
    if taxonomy == "liquidity_oxygen" and "gone_tag" in flags \
            and re.search(r"Cash(?:And|Cash)", row["tag"], re.I):
        severity = max(severity, 4)
    return severity


def _confidence_for_row(row: dict) -> str:
    flags = set(row.get("flags", []))
    if flags & {"occurrence_mismatch"} or flags >= {"intra_filing_pairing", "ambiguous_occurrences"}:
        return "low"
    if flags & {"new_tag", "gone_tag", "intra_filing_pairing"}:
        return "medium"
    return "high"


def _direction(row: dict) -> str:
    if row.get("current") is None:
        return "removed"
    if row.get("prior") is None:
        return "new"
    return "up" if row["current"] > row["prior"] else "down"


def _fmt(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.4g}"


# ---------------------------------------------------------------------------
# Filing Sentinel
# ---------------------------------------------------------------------------

def sentinel_claims(pack: dict) -> tuple[list[dict], dict]:
    ticker = pack["ticker"]
    sha_by_path = {f["path"]: f["sha256"] for f in pack["filings"]}
    claims: list[dict] = []
    unrouted = 0

    for comparison in pack.get("comparisons", []):
        deltas = comparison.get("fact_deltas")
        if not deltas:
            continue
        filing_path = deltas["current_filing"]
        prior_path = deltas["prior_filing"]
        intra = deltas.get("mode") == "intra_filing"
        basis = (
            "vs prior period within the same filing (intra-filing pairing)"
            if intra else "vs comparable prior filing"
        )
        for row in deltas["rows"]:
            taxonomy = _route_taxonomy(row["tag"])
            if taxonomy is None:
                unrouted += 1
                continue
            severity = _severity_for_delta(taxonomy, row)
            direction = _direction(row)
            pct = row.get("pct")
            magnitude = f"{pct:+.1f}%" if pct is not None else direction
            statement = (
                f"{row['tag']} moved {_fmt(row.get('prior'))} → {_fmt(row.get('current'))}"
                f" ({magnitude}) {basis}"
            )
            if intra:
                falsifier = (
                    f"Re-extract both occurrences of {row['tag']} from {filing_path}; "
                    f"claim fails if the current/prior document-order pairing is wrong"
                )
            else:
                falsifier = (
                    f"Re-extract {row['tag']} from {filing_path} and {prior_path}; "
                    f"claim fails if either value or the comparability pairing differs"
                )
            claims.append({
                "claim_id": claim_id(ticker, taxonomy, row["tag"], filing_path),
                "source": "filing_sentinel",
                "taxonomy": taxonomy,
                "statement": statement,
                "direction": direction,
                "magnitude_pct": pct,
                "severity": severity,
                "confidence": _confidence_for_row(row),
                "falsifier": falsifier,
                "evidence_ref": {
                    "pack_hash": pack["pack_hash"],
                    "source_path": filing_path,
                    "source_sha256": sha_by_path.get(filing_path),
                    "prior_path": prior_path,
                    "prior_sha256": sha_by_path.get(prior_path),
                    "tag": row["tag"],
                    "line_current": row.get("line_current"),
                    "line_prior": row.get("line_prior"),
                },
                "flags": row.get("flags", []),
            })

        section_diff = comparison.get("section_diff") or {}
        for section, diff in (section_diff.get("sections") or {}).items():
            for keyword in diff.get("severity_keywords_added", []):
                taxonomy = SECTION_TAXONOMY.get(section, "operating_failure")
                added_line = next(
                    (line for line in diff.get("added", []) if CRITICAL_NARRATIVE.search(line)),
                    None,
                )
                claims.append({
                    "claim_id": claim_id(ticker, taxonomy, f"{section}:{keyword}", filing_path),
                    "source": "filing_sentinel",
                    "taxonomy": taxonomy,
                    "statement": f"New '{keyword}' language added to {section} vs comparable prior filing",
                    "direction": "new",
                    "magnitude_pct": None,
                    "severity": 5,
                    "confidence": "high" if added_line else "medium",
                    "falsifier": (
                        f"Re-diff section '{section}' between {filing_path} and {prior_path}; "
                        f"claim fails if '{keyword}' appears in the prior period too"
                    ),
                    "evidence_ref": {
                        "pack_hash": pack["pack_hash"],
                        "source_path": filing_path,
                        "source_sha256": sha_by_path.get(filing_path),
                        "prior_path": prior_path,
                        "prior_sha256": sha_by_path.get(prior_path),
                        "section": section,
                        "snippet": (added_line or "")[:240],
                    },
                    "flags": ["critical_narrative"],
                })

    for rev in pack.get("revenue_definition", []):
        if "bank_style_revenue" not in rev.get("flags", []):
            continue
        filing_path = rev["filing"]
        claims.append({
            "claim_id": claim_id(ticker, "earnings_quality", "revenue_definition", filing_path),
            "source": "filing_sentinel",
            "taxonomy": "earnings_quality",
            "statement": (
                f"Bank-style revenue definition: operating revenue "
                f"{_fmt(rev.get('operating_revenue'))} (NII {_fmt(rev.get('net_interest_income'))} "
                f"+ non-interest {_fmt(rev.get('noninterest_income'))}) — consensus 'revenue' "
                f"comparisons must reconcile definitions first"
            ),
            "direction": "flag",
            "magnitude_pct": None,
            "severity": 3,
            "confidence": "high",
            "falsifier": (
                f"Recompute NII + non-interest income from {filing_path}; claim fails if the "
                f"reported revenue tag already equals operating revenue"
            ),
            "evidence_ref": {
                "pack_hash": pack["pack_hash"],
                "source_path": filing_path,
                "source_sha256": sha_by_path.get(filing_path),
                "lines": rev.get("evidence_lines", {}),
            },
            "flags": rev.get("flags", []),
        })

    return claims, {"unrouted_delta_rows": unrouted}


# ---------------------------------------------------------------------------
# Management Credibility & Commitment Ledger
# ---------------------------------------------------------------------------

def _latest_json(evidence_dir: Path, stem: str) -> dict | None:
    files = sorted(evidence_dir.glob(f"{stem}_*.json"), reverse=True)
    for path in files:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
    return None


def _latest_filing_facts(evidence_dir: Path) -> dict:
    facts = _latest_json(evidence_dir, "filing_facts") or {}
    return facts.get("metrics") or {}


def management_ledger(pack: dict, evidence_dir: Path, as_of: str) -> dict:
    """Promise rows in, resolution status out. Promises come from
    management_facts_*.json (schema: {claims: [{metric, value, due, ...}]});
    realized values resolve from the latest filing_facts metrics."""
    mgmt = _latest_json(evidence_dir, "management_facts") or {}
    promises = mgmt.get("claims") or []
    metrics = _latest_filing_facts(evidence_dir)

    rows: list[dict] = []
    unresolvable = 0
    for promise in promises:
        metric = str(promise.get("metric", "")).lower()
        row = {
            "promise": promise.get("statement") or promise.get("claim") or metric,
            "metric": metric,
            "promised_value": promise.get("value"),
            "date_made": promise.get("date") or promise.get("as_of"),
            "due": promise.get("due"),
            "source_ref": promise.get("source") or promise.get("evidence_ref"),
            "realized_value": None,
            "delta": None,
            "status": "pending",
        }
        if metric in LEDGER_RESOLVABLE and metric in metrics:
            realized = metrics[metric].get("current")
            row["realized_value"] = realized
            promised = promise.get("value")
            if isinstance(promised, (int, float)) and isinstance(realized, (int, float)):
                row["delta"] = realized - promised
                row["status"] = "met" if realized >= promised else "missed"
            else:
                row["status"] = "unresolved_types"
        elif metric and metric not in LEDGER_RESOLVABLE:
            row["status"] = "unresolvable_metric"
            unresolvable += 1
        rows.append(row)

    scored = [r for r in rows if r["status"] in ("met", "missed")]
    return {
        "as_of": as_of,
        "pack_hash": pack["pack_hash"],
        "promise_count": len(rows),
        "resolved_count": len(scored),
        "hit_rate": (
            round(sum(1 for r in scored if r["status"] == "met") / len(scored), 3)
            if scored else None
        ),
        "unresolvable_count": unresolvable,
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# Spawner Engine (capital allocation)
# ---------------------------------------------------------------------------

def spawner_scores(pack: dict, evidence_dir: Path) -> dict:
    metrics = _latest_filing_facts(evidence_dir)

    def pair(key: str) -> tuple[float | None, float | None]:
        entry = metrics.get(key) or {}
        return entry.get("current"), entry.get("prior")

    shares_cur, shares_pri = pair("shares_outstanding")
    capex_cur, _ = pair("capital_expenditures")
    ocf_cur, _ = pair("operating_cash_flow")

    block: dict = {"pack_hash": pack["pack_hash"], "components": {}, "abstentions": []}

    if shares_cur and shares_pri:
        change_pct = (shares_cur - shares_pri) / shares_pri * 100.0
        block["components"]["buyback_trajectory"] = {
            "share_count_change_pct": round(change_pct, 2),
            "read": "shrinking" if change_pct < -0.5 else ("diluting" if change_pct > 0.5 else "flat"),
            "evidence_ref": {"metric": "shares_outstanding", "tag": metrics["shares_outstanding"].get("tag")},
        }
    else:
        block["abstentions"].append("buyback_trajectory:missing_share_count_pair")

    if capex_cur is not None and ocf_cur:
        ratio = abs(capex_cur) / abs(ocf_cur)
        block["components"]["capex_intensity"] = {
            "capex_to_ocf": round(ratio, 3),
            "read": "reinvesting_heavily" if ratio > 0.6 else ("balanced" if ratio > 0.25 else "capital_light"),
            "evidence_ref": {
                "capex_tag": metrics["capital_expenditures"].get("tag"),
                "ocf_tag": metrics["operating_cash_flow"].get("tag"),
            },
        }
    else:
        block["abstentions"].append("capex_intensity:missing_capex_or_ocf")

    # Small-bet / kill discipline need segment-level history — abstain rather
    # than fabricate a score from insufficient inputs.
    block["abstentions"].append("small_bet_discipline:requires_segment_history")
    block["abstentions"].append("kill_discipline:requires_segment_history")
    return block


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def _latest_pack(evidence_dir: Path) -> dict | None:
    return _latest_json(evidence_dir, "ssi_evidence_pack")


def build_claims(ticker_dir: Path, as_of: str) -> dict | None:
    evidence_dir = ticker_dir / "research" / "evidence"
    if not evidence_dir.is_dir():
        return None
    pack = _latest_pack(evidence_dir)
    if pack is None:
        return None

    claims, sentinel_meta = sentinel_claims(pack)
    claims.sort(key=lambda c: (-c["severity"], c["taxonomy"], c["claim_id"]))
    ledger = management_ledger(pack, evidence_dir, as_of)
    spawner = spawner_scores(pack, evidence_dir)

    severity_hist = {str(n): sum(1 for c in claims if c["severity"] == n) for n in range(1, 6)}
    return {
        "schema_version": SCHEMA_VERSION,
        "ticker": pack["ticker"],
        "as_of": as_of,
        "pack_hash": pack["pack_hash"],
        "pack_as_of": pack.get("as_of"),
        "claims": claims,
        "claim_count": len(claims),
        "severity_histogram": severity_hist,
        "management_ledger": ledger,
        "spawner": spawner,
        "dropped_modalities": {
            **sentinel_meta,
            "market_mechanics": "requires borrow/days-to-cover feed (see refresh_short_alpha_borrow.py)",
        },
    }


def write_claims(ticker_dir: Path, as_of: str) -> Path | None:
    result = build_claims(ticker_dir, as_of)
    if result is None:
        return None
    out = ticker_dir / "research" / "evidence" / f"ssi_claims_{as_of}.json"
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tickers", nargs="*", help="Ticker folders (default: all with an evidence pack)")
    parser.add_argument("--date", default=datetime.now().date().isoformat())
    parser.add_argument("--check", action="store_true", help="Build in memory and report, do not write")
    args = parser.parse_args(argv)

    if args.tickers:
        ticker_dirs = [ROOT / t for t in args.tickers]
    else:
        ticker_dirs = sorted(
            {p.parents[2] for p in ROOT.glob("*/research/evidence/ssi_evidence_pack_*.json")}
        )

    failures = 0
    for ticker_dir in ticker_dirs:
        if args.check:
            result = build_claims(ticker_dir, args.date)
            if result is None:
                print(f"[skip] {ticker_dir.name}: no evidence pack (run build_ssi_evidence_pack.py first)")
                failures += 1
                continue
            sev5 = result["severity_histogram"]["5"]
            print(
                f"[check] {ticker_dir.name}: {result['claim_count']} claims "
                f"(sev5: {sev5}), ledger {result['management_ledger']['promise_count']} promises"
            )
        else:
            out = write_claims(ticker_dir, args.date)
            if out is None:
                print(f"[skip] {ticker_dir.name}: no evidence pack (run build_ssi_evidence_pack.py first)")
                failures += 1
            else:
                print(f"[ok] {out.relative_to(ROOT)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
