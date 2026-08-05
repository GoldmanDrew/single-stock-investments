#!/usr/bin/env python3
"""Phase 1 of the SSI Perplexity-grade pipeline: deterministic evidence extraction.

Builds a hashed, point-in-time evidence pack per ticker from the cached
full-tier `_text` extracts. No LLM involvement — everything here is
deterministic and locator-addressed so Phase 2 synthesis receives only
small, source-locked facts.

Stages:
  1. Filing discovery       — parse form / file_date / period_end / accession
                              from `_text` filenames, sha256 each source.
  2. Comparability gate     — pair each filing only with its truly comparable
                              prior period (same form class, period_end
                              300–430 days earlier, same fiscal quarter for
                              periodics). Rejections are recorded, not dropped.
  3. Fact delta engine      — cross-filing tag-level deltas (current filing's
                              current-period value vs comparable filing's),
                              flagged for new/gone tags, sign flips, extremes.
                              When no comparable prior filing exists on disk,
                              falls back to intra-filing pairing (current vs
                              prior period inside one filing, document order)
                              with confidence capped at medium.
  4. Revenue definition     — detect bank-style revenue (NII-centric) vs
                              operating revenue so consensus beats/misses are
                              never quoted against the wrong denominator.
  5. Section diff engine    — narrative-line diffs grouped by disclosure
                              section (Risk Factors, MD&A, Liquidity/Covenants,
                              Accounting Policies, Controls, Related-Party),
                              when narrative text exists in the extract.

Output: {TICKER}/research/evidence/ssi_evidence_pack_{date}.json with a
stable `pack_hash` over the canonical payload.

Usage:
  python _system/scripts/build_ssi_evidence_pack.py TBBK ABX
  python _system/scripts/build_ssi_evidence_pack.py ABX --date 2026-08-05
  python _system/scripts/build_ssi_evidence_pack.py ABX --check
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from filing_facts import IX_LINE, parse_ix_fact_lines_indexed  # noqa: E402

ROOT = SCRIPT_DIR.parents[1]

SCHEMA_VERSION = "1.0"

# Comparability gate: a prior filing must sit 300–430 days behind the current
# one (annual-vs-annual or quarter-vs-same-quarter YoY). Sequential-quarter
# pairings are structurally impossible under this window.
COMPARABLE_MIN_DAYS = 300
COMPARABLE_MAX_DAYS = 430

# Materiality floor for emitted delta rows; sub-floor rows are counted, not
# silently dropped.
DELTA_PCT_FLOOR = 10.0
DELTA_ROW_CAP = 200

FILENAME_RE = re.compile(
    r"^(?P<form>10-K|10-Q|20-F|40-F|8-K|S-1|DEF[\s_]14A|Semi-Annual|Annual_Report|Quarterly|Interim)"
    r"_(?P<file_date>\d{8})"
    r"(?:_rpt(?P<period_end>\d{8}))?"
    r"(?:_acc(?P<accession>[0-9_]+))?",
    re.I,
)

ANNUAL_FORMS = {"10-K", "20-F", "40-F", "ANNUAL_REPORT"}
QUARTERLY_FORMS = {"10-Q", "QUARTERLY", "INTERIM", "SEMI-ANNUAL"}

SECTION_HEADINGS = (
    ("risk_factors", re.compile(r"\brisk\s+factors\b", re.I)),
    ("mdna", re.compile(r"management.{0,3}s\s+discussion\s+and\s+analysis", re.I)),
    ("liquidity_covenants", re.compile(r"\bliquidity\b|\bcovenants?\b|\bcredit\s+(?:facility|agreement)\b", re.I)),
    ("accounting_policies", re.compile(r"\b(?:significant|critical)\s+accounting\s+(?:policies|estimates)\b", re.I)),
    ("controls", re.compile(r"\bcontrols\s+and\s+procedures\b|\binternal\s+control\s+over\s+financial\s+reporting\b", re.I)),
    ("related_party", re.compile(r"\brelated[\s-]part(?:y|ies)\b", re.I)),
)

SEVERITY_KEYWORDS = re.compile(
    r"going\s+concern|substantial\s+doubt|material\s+weakness|covenant\s+(?:breach|violation|waiver)"
    r"|default|restatement|delisting|subpoena|informal\s+inquiry|formal\s+investigation",
    re.I,
)


@dataclass
class FilingText:
    path: Path
    rel_path: str
    form: str
    form_class: str  # annual | quarterly | proxy | event | other
    file_date: str | None
    period_end: str | None
    accession: str | None
    sha256: str
    text: str = field(repr=False, default="")


def _iso(raw: str | None) -> str | None:
    if not raw or len(raw) != 8:
        return None
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"


def _form_class(form: str) -> str:
    up = form.upper().replace(" ", "_")
    if up in {f.replace(" ", "_") for f in ANNUAL_FORMS}:
        return "annual"
    if up in {f.replace(" ", "_") for f in QUARTERLY_FORMS}:
        return "quarterly"
    if "14A" in up:
        return "proxy"
    if up == "8-K":
        return "event"
    return "other"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def discover_filings(ticker_dir: Path, unparsed: list[str] | None = None) -> list[FilingText]:
    text_dir = ticker_dir / "research" / "evidence" / "_text"
    filings: list[FilingText] = []
    if not text_dir.is_dir():
        return filings
    for path in sorted(text_dir.glob("*.txt")):
        stem = path.name[:-4]
        match = FILENAME_RE.match(stem.replace(" ", "_"))
        if not match:
            if unparsed is not None:
                unparsed.append(path.name)
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if not text.strip():
            continue
        form = match.group("form").upper().replace("_", " ")
        filings.append(
            FilingText(
                path=path,
                rel_path=str(path.relative_to(ticker_dir.parent)).replace("\\", "/"),
                form=form,
                form_class=_form_class(form),
                file_date=_iso(match.group("file_date")),
                period_end=_iso(match.group("period_end")),
                accession=(match.group("accession") or "").replace("_", "-") or None,
                sha256=sha256_text(text),
                text=text,
            )
        )
    return filings


# ---------------------------------------------------------------------------
# Stage 2 — comparability gate
# ---------------------------------------------------------------------------

def _days_between(later: str, earlier: str) -> int:
    return (date.fromisoformat(later) - date.fromisoformat(earlier)).days


def comparability_gate(current: FilingText, candidates: list[FilingText]) -> dict:
    """Select the single comparable prior filing for `current`.

    Returns {"match": FilingText|None, "rejections": [{path, reason}]}.
    """
    rejections: list[dict] = []
    viable: list[FilingText] = []
    cur_anchor = current.period_end or current.file_date
    for cand in candidates:
        if cand.path == current.path:
            continue
        reason = None
        cand_anchor = cand.period_end or cand.file_date
        if cand.form_class != current.form_class:
            reason = f"form_class_mismatch:{cand.form_class}"
        elif not cur_anchor or not cand_anchor:
            reason = "missing_period_anchor"
        else:
            days = _days_between(cur_anchor, cand_anchor)
            if days < COMPARABLE_MIN_DAYS:
                reason = f"too_recent:{days}d"
            elif days > COMPARABLE_MAX_DAYS:
                reason = f"too_stale:{days}d"
            elif (
                current.form_class == "quarterly"
                and current.period_end
                and cand.period_end
                and abs(int(current.period_end[5:7]) - int(cand.period_end[5:7])) > 1
            ):
                reason = "fiscal_quarter_mismatch"
        if reason:
            rejections.append({"path": cand.rel_path, "reason": reason})
        else:
            viable.append(cand)
    match = None
    if viable:
        # Closest to 365 days wins.
        match = min(
            viable,
            key=lambda c: abs(
                _days_between(cur_anchor, c.period_end or c.file_date) - 365
            ),
        )
    return {"match": match, "rejections": rejections}


# ---------------------------------------------------------------------------
# Stage 3 — cross-filing fact delta engine
# ---------------------------------------------------------------------------

def _current_period_values(text: str) -> dict[str, dict]:
    """First occurrence per tag = current-period value (document order),
    matching the pairing convention in filing_facts.py."""
    lines, indexed = parse_ix_fact_lines_indexed(text)
    out: dict[str, dict] = {}
    for tag, occurrences in indexed.items():
        first = occurrences[0]
        out[tag] = {
            "value": first.value,
            "line": first.line,
            "occurrences": len(occurrences),
        }
    return out


def fact_delta_engine(current: FilingText, prior: FilingText) -> dict:
    cur = _current_period_values(current.text)
    pri = _current_period_values(prior.text)
    rows: list[dict] = []
    sub_floor = 0
    for tag in sorted(set(cur) | set(pri)):
        c, p = cur.get(tag), pri.get(tag)
        row: dict = {"tag": tag}
        flags: list[str] = []
        if c and not p:
            row.update(current=c["value"], prior=None, line_current=c["line"])
            flags.append("new_tag")
            materiality = abs(c["value"])
        elif p and not c:
            row.update(current=None, prior=p["value"], line_prior=p["line"])
            flags.append("gone_tag")
            materiality = abs(p["value"])
        else:
            assert c is not None and p is not None
            delta = c["value"] - p["value"]
            pct = (delta / abs(p["value"]) * 100.0) if p["value"] else None
            row.update(
                current=c["value"],
                prior=p["value"],
                delta=delta,
                pct=round(pct, 2) if pct is not None else None,
                line_current=c["line"],
                line_prior=p["line"],
            )
            if c["occurrences"] != p["occurrences"]:
                flags.append("occurrence_mismatch")
            if c["value"] * p["value"] < 0:
                flags.append("sign_flip")
            if pct is not None and abs(pct) >= 50.0:
                flags.append("extreme_move")
            if pct is not None and abs(pct) < DELTA_PCT_FLOOR and not flags:
                sub_floor += 1
                continue
            materiality = abs(pct) if pct is not None else abs(delta)
        row["flags"] = flags
        row["_materiality"] = materiality
        rows.append(row)

    rows.sort(key=lambda r: r["_materiality"], reverse=True)
    dropped_over_cap = max(0, len(rows) - DELTA_ROW_CAP)
    rows = rows[:DELTA_ROW_CAP]
    for row in rows:
        row.pop("_materiality", None)
    return {
        "mode": "cross_filing",
        "current_filing": current.rel_path,
        "prior_filing": prior.rel_path,
        "rows": rows,
        "dropped_sub_floor": sub_floor,
        "dropped_over_cap": dropped_over_cap,
    }


def intra_filing_delta_engine(filing: FilingText) -> dict:
    """Fallback when no comparable prior filing exists on disk: pair the first
    two occurrences of each tag inside the filing (document order lists the
    current period before the prior, the convention filing_facts.py relies
    on). Every row is flagged `intra_filing_pairing` so Phase 2 caps its
    confidence at medium."""
    _lines, indexed = parse_ix_fact_lines_indexed(filing.text)
    rows: list[dict] = []
    sub_floor = 0
    single_occurrence = 0
    for tag in sorted(indexed):
        occurrences = indexed[tag]
        if len(occurrences) < 2:
            single_occurrence += 1
            continue
        current, prior = occurrences[0], occurrences[1]
        delta = current.value - prior.value
        pct = (delta / abs(prior.value) * 100.0) if prior.value else None
        flags = ["intra_filing_pairing"]
        if len(occurrences) > 2:
            flags.append("ambiguous_occurrences")
        if current.value * prior.value < 0:
            flags.append("sign_flip")
        if pct is not None and abs(pct) >= 50.0:
            flags.append("extreme_move")
        if pct is not None and abs(pct) < DELTA_PCT_FLOOR and len(flags) == 1:
            sub_floor += 1
            continue
        rows.append({
            "tag": tag,
            "current": current.value,
            "prior": prior.value,
            "delta": delta,
            "pct": round(pct, 2) if pct is not None else None,
            "line_current": current.line,
            "line_prior": prior.line,
            "flags": flags,
            "_materiality": abs(pct) if pct is not None else abs(delta),
        })
    rows.sort(key=lambda r: r["_materiality"], reverse=True)
    dropped_over_cap = max(0, len(rows) - DELTA_ROW_CAP)
    rows = rows[:DELTA_ROW_CAP]
    for row in rows:
        row.pop("_materiality", None)
    return {
        "mode": "intra_filing",
        "current_filing": filing.rel_path,
        "prior_filing": filing.rel_path,
        "rows": rows,
        "dropped_sub_floor": sub_floor,
        "dropped_single_occurrence": single_occurrence,
        "dropped_over_cap": dropped_over_cap,
    }


# ---------------------------------------------------------------------------
# Stage 4 — revenue definition check
# ---------------------------------------------------------------------------

REVENUE_TAGS = (
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet",
)
NII_TAGS = ("InterestIncomeExpenseNet", "InterestIncomeExpenseAfterProvisionForLoanLoss")
NONINTEREST_TAGS = ("NoninterestIncome", "NoninterestIncomeOtherOperatingIncome")


def revenue_definition_check(filing: FilingText) -> dict:
    """Detect bank-style (NII-centric) revenue so downstream consensus
    comparisons use operating revenue, not the definitional artifact."""
    facts = _current_period_values(filing.text)

    def first(tags: tuple[str, ...]) -> tuple[str, dict] | None:
        for tag in tags:
            if tag in facts:
                return tag, facts[tag]
        return None

    revenue = first(REVENUE_TAGS)
    nii = first(NII_TAGS)
    nonint = first(NONINTEREST_TAGS)

    result: dict = {
        "filing": filing.rel_path,
        "revenue_tag": revenue[0] if revenue else None,
        "revenue_value": revenue[1]["value"] if revenue else None,
        "definition": "standard",
        "flags": [],
    }
    if nii and nonint:
        operating = nii[1]["value"] + nonint[1]["value"]
        result.update(
            definition="bank_style",
            net_interest_income=nii[1]["value"],
            noninterest_income=nonint[1]["value"],
            operating_revenue=operating,
            evidence_lines={
                nii[0]: nii[1]["line"],
                nonint[0]: nonint[1]["line"],
            },
        )
        result["flags"].append("bank_style_revenue")
        if revenue and operating and abs(revenue[1]["value"]) < 0.75 * abs(operating):
            result["flags"].append("reported_revenue_below_operating_revenue")
        if nonint[1]["value"] > nii[1]["value"]:
            result["flags"].append("noninterest_income_exceeds_nii")
    elif not revenue:
        result["definition"] = "unresolved"
        result["flags"].append("no_revenue_tag")
    return result


# ---------------------------------------------------------------------------
# Stage 5 — section diff engine (narrative lines only)
# ---------------------------------------------------------------------------

def _narrative_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    active: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or IX_LINE.match(line):
            continue
        for key, pattern in SECTION_HEADINGS:
            if pattern.search(line) and len(line) < 160:
                active = key
                sections.setdefault(active, [])
                break
        else:
            if active is not None:
                sections[active].append(line)
    return sections


def section_diff_engine(current: FilingText, prior: FilingText) -> dict:
    cur_sections = _narrative_sections(current.text)
    pri_sections = _narrative_sections(prior.text)
    diffs: dict[str, dict] = {}
    for key in sorted(set(cur_sections) | set(pri_sections)):
        cur_lines = cur_sections.get(key, [])
        pri_lines = pri_sections.get(key, [])
        added, removed = [], []
        for token in difflib.unified_diff(pri_lines, cur_lines, lineterm="", n=0):
            if token.startswith("+") and not token.startswith("+++"):
                added.append(token[1:].strip())
            elif token.startswith("-") and not token.startswith("---"):
                removed.append(token[1:].strip())
        severity_hits = sorted(
            {m.group(0).lower() for line in added for m in SEVERITY_KEYWORDS.finditer(line)}
        )
        if added or removed:
            diffs[key] = {
                "added": added[:40],
                "removed": removed[:40],
                "added_count": len(added),
                "removed_count": len(removed),
                "severity_keywords_added": severity_hits,
            }
    return {
        "current_filing": current.rel_path,
        "prior_filing": prior.rel_path,
        "narrative_available": bool(cur_sections or pri_sections),
        "sections": diffs,
    }


# ---------------------------------------------------------------------------
# Pack assembly
# ---------------------------------------------------------------------------

def canonical_hash(payload: dict) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def build_evidence_pack(ticker_dir: Path, as_of: str) -> dict:
    ticker = ticker_dir.name
    unparsed: list[str] = []
    filings = discover_filings(ticker_dir, unparsed)
    pack: dict = {
        "schema_version": SCHEMA_VERSION,
        "ticker": ticker,
        "as_of": as_of,
        "filings": [
            {
                "path": f.rel_path,
                "form": f.form,
                "form_class": f.form_class,
                "file_date": f.file_date,
                "period_end": f.period_end,
                "accession": f.accession,
                "sha256": f.sha256,
            }
            for f in filings
        ],
        "comparisons": [],
        "revenue_definition": [],
        "coverage_notes": [],
    }
    for name in unparsed:
        pack["coverage_notes"].append(f"unparsed_filename:{name}")
    if not filings:
        if not unparsed:
            pack["coverage_notes"].append("no_text_extracts")
        pack["pack_hash"] = canonical_hash(pack)
        return pack

    periodics = [f for f in filings if f.form_class in ("annual", "quarterly")]
    skipped = [f for f in filings if f.form_class not in ("annual", "quarterly")]
    for f in skipped:
        pack["coverage_notes"].append(f"not_diffed:{f.rel_path}")

    # Newest filing per form_class is the diff target; older ones are candidates.
    by_class: dict[str, list[FilingText]] = {}
    for f in periodics:
        by_class.setdefault(f.form_class, []).append(f)
    for form_class, group in sorted(by_class.items()):
        group.sort(key=lambda f: (f.period_end or f.file_date or ""), reverse=True)
        target = group[0]
        gate = comparability_gate(target, periodics)
        comparison: dict = {
            "form_class": form_class,
            "current_filing": target.rel_path,
            "gate": {
                "matched": gate["match"].rel_path if gate["match"] else None,
                "window_days": [COMPARABLE_MIN_DAYS, COMPARABLE_MAX_DAYS],
                "rejections": gate["rejections"],
            },
        }
        if gate["match"]:
            comparison["fact_deltas"] = fact_delta_engine(target, gate["match"])
            comparison["section_diff"] = section_diff_engine(target, gate["match"])
        else:
            comparison["fact_deltas"] = intra_filing_delta_engine(target)
            pack["coverage_notes"].append(
                f"no_comparable_prior:{target.rel_path}:intra_filing_fallback"
            )
        pack["comparisons"].append(comparison)

    for f in periodics:
        pack["revenue_definition"].append(revenue_definition_check(f))

    pack["pack_hash"] = canonical_hash(pack)
    return pack


def write_evidence_pack(ticker_dir: Path, as_of: str) -> Path | None:
    evidence_dir = ticker_dir / "research" / "evidence"
    if not evidence_dir.is_dir():
        return None
    pack = build_evidence_pack(ticker_dir, as_of)
    out = evidence_dir / f"ssi_evidence_pack_{as_of}.json"
    out.write_text(json.dumps(pack, indent=2) + "\n", encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tickers", nargs="*", help="Ticker folders (default: all with _text extracts)")
    parser.add_argument("--date", default=datetime.now().date().isoformat())
    parser.add_argument("--check", action="store_true", help="Build in memory and report, do not write")
    args = parser.parse_args(argv)

    if args.tickers:
        ticker_dirs = [ROOT / t for t in args.tickers]
    else:
        ticker_dirs = sorted(
            p.parents[2] for p in ROOT.glob("*/research/evidence/_text") if p.is_dir()
        )

    failures = 0
    for ticker_dir in ticker_dirs:
        if not ticker_dir.is_dir():
            print(f"[skip] {ticker_dir.name}: no ticker folder")
            failures += 1
            continue
        if args.check:
            pack = build_evidence_pack(ticker_dir, args.date)
            comps = sum(1 for c in pack["comparisons"] if c["gate"]["matched"])
            print(
                f"[check] {ticker_dir.name}: {len(pack['filings'])} filings, "
                f"{comps} gated comparisons, hash {pack['pack_hash'][:12]}"
            )
        else:
            out = write_evidence_pack(ticker_dir, args.date)
            if out is None:
                print(f"[skip] {ticker_dir.name}: no research/evidence dir")
                failures += 1
            else:
                print(f"[ok] {out.relative_to(ROOT)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
