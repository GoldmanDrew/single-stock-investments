#!/usr/bin/env python3
"""Sync classification across thesis.md, classification.json, and valuation.json.

Usage:
  python _system/scripts/sync_classification.py           # report drift
  python _system/scripts/sync_classification.py --fix   # push valuation → json + thesis
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLASS_PATH = ROOT / "_system" / "portfolio" / "classification.json"

CLASS_FIELDS = [
    "archetype",
    "moat",
    "dhando",
    "stance",
    "cycle",
    "implied_irr",
    "irr_method",
    "lawrence_bucket",
]

LABEL_MAP = {
    "archetype": "Archetype",
    "moat": "Moat",
    "dhando": "Dhando",
    "stance": "Stance",
    "cycle": "Cycle",
    "implied_irr": "Implied 10yr IRR",
    "irr_method": "IRR method",
    "lawrence_bucket": "Lawrence bucket",
}


def parse_thesis_classification(ticker_dir: Path) -> dict:
    thesis = ticker_dir / "research" / "thesis.md"
    if not thesis.exists():
        return {}
    text = thesis.read_text(encoding="utf-8", errors="ignore")
    fields = {}
    for key, label in LABEL_MAP.items():
        m = re.search(rf"\*\*{label}\*\*[^|]*\|\s*([^\|]+)", text)
        if m:
            fields[key] = m.group(1).strip()
    return fields


def load_valuation(ticker: str) -> dict | None:
    path = ROOT / ticker / "research" / "valuation.json"
    legacy = ROOT / ticker / "research" / "irr_model.json"
    target = path if path.exists() else legacy if legacy.exists() else None
    if not target:
        return None
    return json.loads(target.read_text(encoding="utf-8"))


def valuation_classification(val: dict) -> dict:
    out = {}
    if val.get("lawrence_bucket"):
        out["lawrence_bucket"] = val["lawrence_bucket"]
    method = val.get("method", val.get("irr_method"))
    if method:
        out["irr_method"] = method
    implied = val.get("implied_return", {})
    if implied.get("display"):
        out["implied_irr"] = implied["display"]
    elif val.get("results", {}).get("base", {}).get("return_pct") is not None:
        out["implied_irr"] = f"{val['results']['base']['return_pct']}% (base)"
    proposal = val.get("stance_proposal", {})
    if proposal.get("suggested") and proposal["suggested"] != "pending":
        out["stance_proposed"] = proposal["suggested"]
    return out


def classification_table(row: dict) -> str:
    def cell(key: str, label: str, genius: str = "") -> str:
        val = row.get(key, "—")
        suffix = f" ({genius})" if genius else ""
        return f"| **{label}**{suffix} | {val} |"

    lines = [
        "## Classification",
        "",
        "| Field | Value |",
        "|-------|-------|",
        cell("archetype", "Archetype", "Stahl"),
        cell("moat", "Moat", "Munger"),
        cell("dhando", "Dhando", "Pabrai"),
        cell("stance", "Stance"),
        cell("cycle", "Cycle"),
        cell("implied_irr", "Implied 10yr IRR", "Lawrence"),
        cell("irr_method", "IRR method"),
        cell("lawrence_bucket", "Lawrence bucket"),
        "",
    ]
    return "\n".join(lines)


def update_thesis(ticker: str, row: dict) -> bool:
    thesis_path = ROOT / ticker / "research" / "thesis.md"
    if not thesis_path.exists():
        return False
    text = thesis_path.read_text(encoding="utf-8")
    text = re.sub(
        r"\n## Classification\s*\n\s*\n\| Field \| Value \|\s*\n\|[-| ]+\|\s*\n(?:\|[^\n]+\|\s*\n)+",
        "\n",
        text,
    )
    title_m = re.match(r"(# .+?\n\n)", text)
    if not title_m:
        return False
    rest = text[len(title_m.group(1)) :]
    rest = re.sub(r"\*\*Last updated:\*\*[^\n]*\n", "", rest)
    header = f"{title_m.group(1)}**Last updated:** auto-sync\n\n{classification_table(row)}\n"
    thesis_path.write_text(header + rest.lstrip(), encoding="utf-8")
    return True


def check_ticker(ticker: str, portfolio: dict, fix: bool) -> list[str]:
    issues: list[str] = []
    ticker_dir = ROOT / ticker
    from_json = portfolio.get(ticker, {})
    from_thesis = parse_thesis_classification(ticker_dir)
    val = load_valuation(ticker)
    from_val = valuation_classification(val) if val else {}

    merged = {**from_json, **from_thesis}
    for key in CLASS_FIELDS:
        j = from_json.get(key)
        t = from_thesis.get(key)
        if j and t and j != t:
            issues.append(f"{ticker}: thesis vs json mismatch on {key}: thesis={t!r} json={j!r}")

    if from_val.get("implied_irr") and from_json.get("implied_irr"):
        if from_val["implied_irr"] != from_json["implied_irr"]:
            issues.append(
                f"{ticker}: valuation implied_irr {from_val['implied_irr']!r} "
                f"!= json {from_json['implied_irr']!r}"
            )

    if fix and val:
        updated = dict(from_json)
        if from_val.get("implied_irr"):
            updated["implied_irr"] = from_val["implied_irr"]
        if from_val.get("irr_method"):
            updated["irr_method"] = from_val["irr_method"]
        if from_val.get("lawrence_bucket"):
            updated["lawrence_bucket"] = from_val["lawrence_bucket"]
        approved = val.get("approved_stance") or (val.get("stance_proposal") or {}).get("approved_stance")
        if approved:
            updated["stance"] = approved
        portfolio[ticker] = updated
        update_thesis(ticker, portfolio[ticker])

    elif fix and from_json:
        update_thesis(ticker, from_json)

    return issues


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync classification sources")
    parser.add_argument("--fix", action="store_true", help="Update json/thesis from valuation")
    parser.add_argument("--ticker", help="Single ticker only")
    args = parser.parse_args()

    portfolio = json.loads(CLASS_PATH.read_text(encoding="utf-8"))
    tickers = [args.ticker] if args.ticker else sorted(portfolio.keys())

    all_issues: list[str] = []
    for ticker in tickers:
        all_issues.extend(check_ticker(ticker, portfolio, args.fix))

    if args.fix:
        CLASS_PATH.write_text(json.dumps(portfolio, indent=2) + "\n", encoding="utf-8")
        print(f"Updated {CLASS_PATH.relative_to(ROOT)}")

    if all_issues:
        for issue in all_issues:
            print(f"DRIFT: {issue}")
        sys.exit(1)

    print(f"OK: {len(tickers)} ticker(s) in sync")


if __name__ == "__main__":
    main()
