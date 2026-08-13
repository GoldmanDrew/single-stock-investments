#!/usr/bin/env python3
"""Discover historical raw 10-Q/K filings and mine comparable section deltas.

Raw disclosure deltas are review proposals, never final conclusions. This fills
the historical 10-Q coverage gap left by the latest-filing structured-fact feed.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

from filing_sentinel_gold import ROOT, _iso, _portfolio_tickers, _sha256, load_taxonomy, write_jsonl
from filing_sentinel_workflow import SECTION_PATTERNS, _normalise_excerpt, lock_split, quota_sample

RAW_FILING_RE = re.compile(
    r"(?P<form>10-K|10-Q)_(?P<filed>\d{8})_rpt(?P<period>\d{8})_acc(?P<accession>[\d_]+)\.html?$",
    re.I,
)
HIGH_RISK_TERMS = (
    ("financial_oxygen", "going_concern", r"going concern", "critical"),
    ("financial_oxygen", "covenant_pressure", r"covenant", "high"),
    ("financial_oxygen", "refinancing", r"debt maturit|refinanc", "high"),
    ("financial_oxygen", "serial_equity_issuance", r"at-the-market|shelf registration|equity issu", "high"),
    ("accounting", "restatement", r"restatement", "critical"),
    ("accounting", "material_weakness", r"material weakness", "critical"),
    ("accounting", "auditor_change", r"dismissed .* auditor|auditor.*resign", "high"),
    ("governance_legal", "related_party", r"related part", "high"),
    ("governance_legal", "investigation", r"investigation|subpoena", "critical"),
    ("governance_legal", "litigation", r"legal proceedings|litigation", "high"),
    ("transaction", "strategic_review", r"strategic review", "high"),
    ("transaction", "wind_down", r"wind down|discontinue operations", "critical"),
)


def html_to_text(raw: str) -> str:
    raw = re.sub(r"<(?:script|style)[^>]*>.*?</(?:script|style)>", " ", raw, flags=re.I | re.S)
    raw = re.sub(r"</(?:p|div|tr|li|h[1-6]|table)\s*>", "\n", raw, flags=re.I)
    raw = re.sub(r"<[^>]+>", " ", raw)
    return html.unescape(re.sub(r"\s+", " ", raw)).strip()


def raw_filings(*, universe: str, tickers: set[str], since: str, per_ticker: int, forms: set[str], max_issuers: int | None, issuer_offset: int) -> list[dict]:
    allowed = tickers or (_portfolio_tickers() if universe == "portfolio" else set())
    rows: list[dict] = []
    issuer_count = 0
    eligible_dirs = [
        ticker_dir for ticker_dir in sorted(ROOT.iterdir())
        if ticker_dir.is_dir() and not ticker_dir.name.startswith((".", "_"))
        and (not allowed or ticker_dir.name.upper() in allowed)
    ]
    for ticker_dir in eligible_dirs[max(0, issuer_offset):]:
        if not ticker_dir.is_dir() or ticker_dir.name.startswith((".", "_")):
            continue
        ticker = ticker_dir.name.upper()
        if max_issuers is not None and issuer_count >= max_issuers:
            break
        base = ticker_dir / "investor-documents"
        if not base.exists():
            continue
        by_form: dict[str, list[dict]] = defaultdict(list)
        index = ticker_dir / "INDEX.csv"
        if index.exists():
            try:
                with index.open(encoding="utf-8") as handle:
                    paths = [ticker_dir / row["path"] for row in csv.DictReader(handle) if row.get("filename", "").lower().endswith((".htm", ".html"))]
            except OSError:
                paths = []
        else:
            sec_edgar = base / "sec-edgar"
            paths = sec_edgar.rglob("*.htm*") if sec_edgar.exists() else base.rglob("*.htm*")
        for path in paths:
            if not path.is_file():
                continue
            match = RAW_FILING_RE.match(path.name)
            if not match:
                continue
            if match.group("form").upper() not in forms:
                continue
            filed_at = _iso(match.group("filed"))
            if filed_at < since:
                continue
            by_form[match.group("form").upper()].append({
                "ticker": ticker, "path": path, "form": match.group("form").upper(),
                "filed_at": filed_at, "period_end": _iso(match.group("period")),
                "accession": match.group("accession").replace("_", "-"),
            })
        for form_rows in by_form.values():
            form_rows.sort(key=lambda row: (row["period_end"], row["filed_at"]), reverse=True)
            # Four quarters plus a prior-year comparable support each selected 10-Q.
            rows.extend(form_rows[: per_ticker * 4 + 1])
        if by_form:
            issuer_count += 1
    return rows


def _read_text(path: Path) -> str:
    try:
        return html_to_text(path.read_text(encoding="utf-8", errors="ignore"))[:500_000]
    except OSError:
        return ""


def _term_evidence(text: str, pattern: str, *, evidence_id: str, source_role: str) -> dict | None:
    match = re.search(pattern, text, re.I)
    if not match:
        return None
    start = max(0, match.start() - 600)
    end = min(len(text), match.end() + 1000)
    excerpt = _normalise_excerpt(text[start:end])
    if not excerpt:
        return None
    return {
        "evidence_id": evidence_id,
        "locator": f"{source_role} normalized text characters {start + 1}-{end}; keyword /{pattern}/i",
        "excerpt": excerpt,
        "content_sha256": _sha256(excerpt),
        "source_role": source_role,
    }


def _section_categories(text: str) -> set[str]:
    return {category for category, patterns in SECTION_PATTERNS.items() if any(re.search(pattern, text, re.I) for pattern in patterns)}


def comparable_prior(current: dict, group: list[dict]) -> dict | None:
    current_period = date.fromisoformat(current["period_end"])
    candidates = [
        row for row in group
        if row["period_end"] < current["period_end"]
        and 300 <= (current_period - date.fromisoformat(row["period_end"])).days <= 430
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda row: abs((current_period - date.fromisoformat(row["period_end"])).days - 365))


def raw_candidates(*, universe: str, tickers: set[str], since: str, per_ticker: int, forms: set[str], max_issuers: int | None, issuer_offset: int, as_of: str) -> list[dict]:
    taxonomy = load_taxonomy()
    filings = raw_filings(universe=universe, tickers=tickers, since=since, per_ticker=per_ticker, forms=forms, max_issuers=max_issuers, issuer_offset=issuer_offset)
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for filing in filings:
        grouped[(filing["ticker"], filing["form"])].append(filing)
    cases: list[dict] = []
    for (ticker, _form), group in grouped.items():
        group.sort(key=lambda row: (row["period_end"], row["filed_at"]))
        for current in group[-per_ticker:]:
            prior = comparable_prior(current, group)
            if not prior:
                continue
            current_text, prior_text = _read_text(current["path"]), _read_text(prior["path"])
            if not current_text:
                continue
            evidence: list[dict] = []
            proposals: list[dict] = []
            current_categories = _section_categories(current_text)
            prior_categories = _section_categories(prior_text)
            for term_index, (category, tag, pattern, severity) in enumerate(HIGH_RISK_TERMS, start=1):
                current_hit = re.search(pattern, current_text, re.I)
                prior_hit = re.search(pattern, prior_text, re.I)
                if not current_hit or prior_hit:
                    continue
                evidence_id = f"ev-new-{tag}-{term_index}"
                item = _term_evidence(current_text, pattern, evidence_id=evidence_id, source_role="current")
                if not item:
                    continue
                evidence.append(item)
                proposals.append({
                    "proposal_type": "semantic_keyword_delta",
                    "category": category,
                    "tags": [tag],
                    "direction": "strengthens",
                    "severity": severity,
                    "confidence": "low",
                    "claim": f"New {tag.replace('_', ' ')} keyword relative to the preceding comparable {current['form']}; requires section review.",
                    "evidence_ids": [evidence_id],
                    "review_required": True,
                    "falsifier": "Comparable full-section review shows the disclosure is not new, not material, or is only a boilerplate variation.",
                })
            # A bounded context pack permits clean/no-alert review and catches deltas outside the high-risk vocabulary.
            for category in sorted(current_categories - {"identity_instrument"})[:4]:
                pattern = SECTION_PATTERNS[category][0]
                item = _term_evidence(current_text, pattern, evidence_id=f"ev-current-{category}", source_role="current")
                if item and not any(existing["content_sha256"] == item["content_sha256"] for existing in evidence):
                    evidence.append(item)
            for category in sorted(prior_categories - {"identity_instrument"})[:2]:
                pattern = SECTION_PATTERNS[category][0]
                item = _term_evidence(prior_text, pattern, evidence_id=f"ev-prior-{category}", source_role="prior")
                if item and not any(existing["content_sha256"] == item["content_sha256"] for existing in evidence):
                    evidence.append(item)
            if not evidence:
                continue
            source_ref = str(current["path"].relative_to(ROOT)).replace("\\", "/")
            prior_ref = str(prior["path"].relative_to(ROOT)).replace("\\", "/")
            raw_id = f"{ticker}|{current['form']}|{current['filed_at']}|{source_ref}"
            reasons = ["raw_section_delta" if proposals else "raw_section_control:no-new-high-risk-keyword"]
            case = {
                "schema_version": 1,
                "case_id": f"fs-{ticker.lower().replace('.', '-')}-{current['filed_at']}-{_sha256(raw_id)[:8]}",
                "label_status": "candidate",
                "split": lock_split(ticker, taxonomy.get("split_policy") or {}),
                "ticker": ticker,
                "filing": {
                    "form": current["form"], "filed_at": current["filed_at"], "period_end": current["period_end"], "accession": current["accession"],
                    "source_ref": source_ref, "source_sha256": _sha256(current["path"].read_bytes()), "extract_ref": None, "extract_sha256": None,
                    "comparison_source_ref": prior_ref, "comparison_period_end": prior["period_end"], "comparison_sha256": _sha256(prior["path"].read_bytes()),
                },
                "evidence": evidence,
                "proposals": proposals,
                "mining_reasons": reasons,
                "section_signals": sorted(current_categories),
                "expected": {"events": [], "no_event_tags": [], "no_material_change": False},
                "provenance": {"origin": "raw_historical_filing", "created_at": as_of, "adjudicated_by": [], "rationale": "Comparable raw filing section delta; candidate only."},
            }
            strata = ["semantic_section"] if proposals else ["clean_control"]
            if proposals and any(p["severity"] in {"high", "critical"} for p in proposals):
                strata.append("high_adverse")
            case["sampling"] = {"strata": strata}
            case["candidate_priority"] = 5 * len(proposals) + len(evidence)
            cases.append(case)
    return cases


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--universe", choices=("portfolio", "all"), default="portfolio")
    parser.add_argument("--ticker", action="append", default=[])
    parser.add_argument("--since", default="2023-01-01")
    parser.add_argument("--per-ticker", type=int, default=4)
    parser.add_argument("--forms", nargs="+", choices=("10-Q", "10-K"), default=["10-Q", "10-K"])
    parser.add_argument("--max-issuers", type=int)
    parser.add_argument("--issuer-offset", type=int, default=0, help="Skip this many sorted eligible issuers for the next historical cohort")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--as-of", default=date.today().isoformat())
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    taxonomy = load_taxonomy()
    all_cases = raw_candidates(universe=args.universe, tickers={ticker.upper() for ticker in args.ticker}, since=args.since, per_ticker=max(1, args.per_ticker), forms=set(args.forms), max_issuers=args.max_issuers, issuer_offset=max(0, args.issuer_offset), as_of=args.as_of)
    selected, summary = quota_sample(all_cases, limit=max(1, args.limit), taxonomy=taxonomy)
    summary["source"] = "raw_historical_filings"
    write_jsonl(args.output, selected)
    args.output.with_suffix(args.output.suffix + ".summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"candidates": len(selected), "available": len(all_cases), "output": str(args.output), "summary": summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
