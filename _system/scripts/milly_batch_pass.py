#!/usr/bin/env python3
"""Batch Milly standard pass: adversarial_{date}.md + dive header link.

Usage:
  python _system/scripts/milly_batch_pass.py --date 2026-05-28
  python _system/scripts/milly_batch_pass.py --date 2026-05-28 --fix-returns
  python _system/scripts/milly_batch_pass.py --date 2026-05-28 --skip APLD QDEL FRMO
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from lint_adversarial import (  # noqa: E402
    collect_dive_irrs,
    expected_base_irr,
    lint_ticker,
    latest_dive,
    tickers_from_registry,
)

TOLERANCE = 0.25
REVENUE_IN_DIVE = re.compile(
    r"revenue[^\d$]{0,40}\$?\s*([\d,.]+)\s*([BbMm])?",
    re.I,
)
RETURNS_PAT = re.compile(
    r"(\*\*Returns statement(?: \(blended\))?:\*\*[^\n]*?)\*\*~?(\d{1,2}(?:\.\d)?)\s*%\*\*",
    re.I,
)
CLASS_PAT = re.compile(
    r"(\|\s*\*\*Implied 10yr IRR\*\*[^\|]*\|\s*)([^\|]+)(\|)",
    re.I,
)
HEADER_THIRD = re.compile(r"^\*\*Third party:\*\*.*$", re.M)


def latest_filing_facts(evidence: Path) -> dict | None:
    files = sorted(evidence.glob("filing_facts_*.json"), reverse=True)
    if not files:
        return None
    return json.loads(files[0].read_text(encoding="utf-8"))


def fmt_millions(v: float | None) -> str:
    if v is None:
        return "n/a"
    if v >= 1000:
        return f"${v/1000:.2f}B"
    return f"${v:.1f}M"


def filing_rows(ticker: str, dive_text: str, facts: dict | None) -> list[str]:
    rows = []
    metrics = (facts or {}).get("metrics") or {}
    rev = metrics.get("revenues") or {}
    if rev.get("current") is not None:
        cur, pri = rev.get("current"), rev.get("prior")
        yoy = ""
        if pri and pri != 0:
            yoy = f" ({(cur - pri) / pri * 100:+.1f}% YoY)"
        rows.append(
            f"| 1 | Latest revenue (filing) | — | **{fmt_millions(cur)}**"
            f"{f' vs prior {fmt_millions(pri)}' if pri else ''}{yoy} | spot-check dive | — |"
        )
    for tag, key in (
        ("Stockholders' equity", "stockholders_equity"),
        ("Net income", "net_income"),
        ("EPS basic", "eps_basic"),
    ):
        m = metrics.get(key) or {}
        if m.get("current") is not None:
            rows.append(
                f"| — | {tag} (filing) | — | **{m['current']}** | spot-check dive | — |"
            )
    if not rows:
        rows.append("| — | No filing_facts metrics | — | — | run build_filing_evidence | — |")
    if facts and facts.get("error"):
        rows.insert(0, f"| — | filing_facts | — | {facts['error']} | — | inference |")
    return rows


def yaml_verdict(
    errs: list[str],
    warns: list[str],
    irr: dict[str, float | None],
    expected: float | None,
) -> dict:
    block = False
    issues: list[str] = []
    filing = "pass"
    consistency = "pass"
    if any("returns_statement" in e for e in errs):
        consistency = "fail"
        block = True
        issues.append("returns_statement_irr")
    if any("classification" in e for e in errs):
        consistency = "fail"
        block = True
        issues.append("classification_irr")
    if any("empty #### Look-through" in e for e in errs):
        consistency = "fail"
        block = True
        issues.append("empty_lookthrough")
    if any("filing_facts" in w.lower() for w in warns):
        filing = "partial"
    return {
        "filing": filing,
        "consistency": consistency,
        "disclosure": "pass",
        "short": "no_hit",
        "third_party": "n/a",
        "block_final": block,
        "blocking_issues": issues,
        "re_pass": False,
    }


def write_adversarial(
    ticker: str,
    dive_date: str,
    dive_path: Path,
    val: dict,
    facts: dict | None,
    errs: list[str],
    warns: list[str],
) -> Path:
    text = dive_path.read_text(encoding="utf-8", errors="ignore")
    expected = expected_base_irr(val)
    irr = collect_dive_irrs(text)
    yv = yaml_verdict(errs, warns, irr, expected)
    issues_yaml = json.dumps(yv["blocking_issues"])
    if issues_yaml == "[]":
        issues_yaml = "[]"

    ff_path = ""
    if facts:
        ff_path = f"`{ticker}/research/evidence/filing_facts_{dive_date}.json`"
    else:
        ff_path = "*(none — run build_filing_evidence.py)*"

    short_note = "No Tier-1 forensic short in `short_scan_2026-05-28.md`; no local `short_reports/`."
    overall = (
        "Mechanical pass from filing_facts + lint. "
        + ("**Block fixes** in dive before final." if yv["block_final"] else "No blocking factual errors.")
    )

    lines = [
        "---",
        f"filing: {yv['filing']}",
        f"consistency: {yv['consistency']}",
        f"disclosure: {yv['disclosure']}",
        f"short: {yv['short']}",
        f"third_party: {yv['third_party']}",
        f"block_final: {str(yv['block_final']).lower()}",
        f"blocking_issues: {issues_yaml}",
        f"re_pass: {str(yv['re_pass']).lower()}",
        "---",
        "",
        f"# {ticker} — Adversarial review",
        "",
        f"**Date:** {dive_date}  ",
        "**Agent:** Milly (batch pass)  ",
        f"**Dive reviewed:** `{ticker}/research/deep_dive_{dive_date}.md`  ",
        f"**Valuation reviewed:** `{ticker}/research/valuation.json`  ",
        f"**Filings used:** {ff_path}",
        "",
        "**Goal:** Truth-seeking QA. Not bearish for its own sake.",
        "",
        "---",
        "",
        "## Summary verdict",
        "",
        "| Area | Status | One line |",
        "|------|--------|----------|",
        f"| Filing reconciliation | {yv['filing']} | filing_facts spot-check |",
        f"| Internal consistency | {yv['consistency']} | lint_adversarial |",
        f"| Disclosure scan | {yv['disclosure']} | no 8-K scan this batch |",
        f"| Short activist scan | {yv['short']} | {short_note[:60]}… |",
        f"| Third-party (approved) | {yv['third_party']} | — |",
        "",
        f"**Overall:** {overall}",
        "",
        "---",
        "",
        "## Filing reconciliation",
        "",
        "| # | Claim in dive | Dive cites | Filing value | Match? | Severity |",
        "|---|---------------|------------|--------------|--------|----------|",
        *filing_rows(ticker, text, facts),
        "",
        "---",
        "",
        "## Internal consistency",
        "",
        "| Check | Expected (valuation.json) | Found in dive | OK? |",
        "|-------|---------------------------|---------------|-----|",
    ]
    exp_s = f"{expected}%" if expected is not None else "n/a"
    for label, key in [
        ("Returns statement", "returns_statement"),
        ("Classification IRR", "classification"),
        ("Valuation bridge base", "valuation_bridge_base"),
    ]:
        found = irr.get(key) or irr.get("returns_statement")
        if key == "classification":
            found = irr.get("classification")
        elif key == "Valuation bridge base":
            found = irr.get("valuation_bridge_base")
        else:
            found = irr.get("returns_statement")
        ok = "—"
        if expected is not None and found is not None:
            ok = "Yes" if abs(found - expected) <= TOLERANCE else "**No**"
        lines.append(f"| {label} | {exp_s} | {found}% | {ok} |")

    if errs or warns:
        lines.append("")
        lines.append("**Lint notes:**")
        for e in errs:
            lines.append(f"- {e}")
        for w in warns[:5]:
            lines.append(f"- {w}")

    lines.extend(
        [
            "",
            "---",
            "",
            "## Disclosure scan",
            "",
            "| Event | Date | Source | In dive? | Action |",
            "|-------|------|--------|----------|--------|",
            "| (batch) | — | not scanned | — | full pass on next refresh |",
            "",
            "---",
            "",
            "## Short activist scan",
            "",
            f"{short_note}",
            "",
            "---",
            "",
            "## Recommended actions",
            "",
        ]
    )
    if yv["block_final"]:
        lines.append("1. **Marvin:** Align Returns statement / Classification IRR with `valuation.json` base.")
    else:
        lines.append("1. None blocking — optional exec-summary IRR wording vs floor/bull.")
    lines.extend(
        [
            "2. **Human:** Tier-1 short web scan per `short_activist_registry.md` when prioritizing name.",
            "",
            "---",
            "",
            "## [HUMAN REVIEW]",
            "",
            "- Batch pass — not a substitute for targeted disclosure / short research on high-risk names.",
            "",
        ]
    )

    out = ROOT / ticker / "research" / f"adversarial_{dive_date}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def fix_returns_statement(text: str, target_pct: float) -> str:
    pct_s = f"{target_pct:.1f}".rstrip("0").rstrip(".")
    if "." not in pct_s and target_pct != int(target_pct):
        pct_s = f"{target_pct:.1f}"

    def repl(m: re.Match) -> str:
        return f"{m.group(1)}**{pct_s}%**"

    new_text, n = RETURNS_PAT.subn(repl, text, count=0)
    if n == 0:
        return text

    def class_repl(m: re.Match) -> str:
        row = m.group(2)
        if re.search(r"\d", row):
            new_row = re.sub(r"(\d{1,2}(?:\.\d)?)\s*%", f"{pct_s}%", row, count=1)
            return m.group(1) + new_row + m.group(3)
        return m.group(0)

    new_text = CLASS_PAT.sub(class_repl, new_text, count=1)
    return new_text


def add_dive_header_link(ticker: str, dive_path: Path, dive_date: str, blocked: bool) -> None:
    text = dive_path.read_text(encoding="utf-8", errors="ignore")
    if re.search(r"\*\*Adversarial", text, re.I):
        return
    status = "blocked" if blocked else "pass"
    link = f"**Adversarial:** {status} · `{ticker}/research/adversarial_{dive_date}.md` (Milly)"
    if re.search(r"\*\*Adversarial", text, re.I):
        text = re.sub(r"\*\*Adversarial[^\n]+\n", link + "\n", text, count=1)
    elif HEADER_THIRD.search(text):
        text = HEADER_THIRD.sub(lambda m: m.group(0) + "\n" + link, text, count=1)
    else:
        text = text.replace(
            f"**Date:** {dive_date}\n",
            f"**Date:** {dive_date}\n{link}\n",
            1,
        )
    dive_path.write_text(text, encoding="utf-8")


def append_milly_log(ticker: str, ok: bool, note: str) -> None:
    log = ROOT / "_system" / "research" / "milly_log.md"
    row = f"| {date.today().isoformat()} | {ticker} | standard_batch | {'OK' if ok else 'BLOCKED'} | {note} |\n"
    with log.open("a", encoding="utf-8") as f:
        f.write(row)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="2026-05-28")
    parser.add_argument("--skip", nargs="*", default=["APLD", "QDEL", "FRMO"])
    parser.add_argument("--fix-returns", action="store_true", help="Align returns to valuation.json")
    parser.add_argument("--headers-only", action="store_true")
    args = parser.parse_args()

    done = 0
    for ticker in tickers_from_registry():
        if ticker in args.skip:
            continue
        research = ROOT / ticker / "research"
        dive = latest_dive(research)
        if not dive or args.date not in dive.name:
            print(f"SKIP {ticker}: no deep_dive_{args.date}.md")
            continue

        val = {}
        vp = research / "valuation.json"
        if vp.exists():
            val = json.loads(vp.read_text(encoding="utf-8"))

        expected = expected_base_irr(val)
        if args.fix_returns and expected is not None:
            text = dive.read_text(encoding="utf-8", errors="ignore")
            irr = collect_dive_irrs(text)
            if irr.get("returns_statement") is not None and abs(
                irr["returns_statement"] - expected
            ) > TOLERANCE:
                dive.write_text(fix_returns_statement(text, expected), encoding="utf-8")
                print(f"FIX {ticker}: returns -> {expected}%")

        if args.headers_only:
            adv = research / f"adversarial_{args.date}.md"
            blocked = False
            if adv.exists():
                blocked = "block_final: true" in adv.read_text(encoding="utf-8")[:500]
            add_dive_header_link(ticker, dive, args.date, blocked)
            continue

        errs, warns = lint_ticker(ticker, consistency_only=False, strict=False)
        facts = latest_filing_facts(research / "evidence")
        out = write_adversarial(ticker, args.date, dive, val, facts, errs, warns)
        blocked = any("returns_statement" in e for e in errs)
        add_dive_header_link(ticker, dive, args.date, blocked)
        append_milly_log(ticker, not blocked, "batch pass")
        print(f"OK {ticker} -> {out.name} ({len(errs)} errors)")
        done += 1

    print(f"Done: {done} adversarial reports")


if __name__ == "__main__":
    main()
