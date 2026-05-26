#!/usr/bin/env python3
"""Lint deep dives for decision-stack report structure and prose rules.

Usage:
  python _system/scripts/lint_deep_dive.py              # all tickers, latest dive each
  python _system/scripts/lint_deep_dive.py ICE        # latest ICE dive
  python _system/scripts/lint_deep_dive.py --all ICE    # all ICE dives
  python _system/scripts/lint_deep_dive.py ICE --legacy # skip 2026 prose sections
  python _system/scripts/lint_deep_dive.py ICE --strict # prose warnings fail too
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

REQUIRED_SECTIONS = [
    (r"## What this business is", "What this business is"),
    (r"## Why the market might be wrong", "Why the market might be wrong"),
    (r"## Executive summary", "Executive summary"),
    (r"## (Business & moat|Business overview)", "Business & moat (or legacy Business overview)"),
    (r"## (Payoff & return|Lawrence IRR)", "Payoff & return (or legacy Lawrence IRR)"),
    (r"## (Risks & inversion|Risks)", "Risks & inversion"),
    (r"## Classification", "Classification"),
    (r"## \[HUMAN REVIEW\]", "[HUMAN REVIEW]"),
]

FORBIDDEN = [
    (r"\*\*Thesis status:\*\*", "Legacy thesis status — use Classification table"),
    (r"## Thesis status", "Legacy Thesis status section"),
]

EXEC_SUMMARY_LABEL_OPEN = re.compile(
    r"^\s*\*\*(Archetype|Stahl|Munger|Pabrai|Lawrence|Dhando|Moat)\b",
    re.IGNORECASE | re.MULTILINE,
)

TIER2_HEADER = re.compile(r"### Tier 2 prompts", re.IGNORECASE)
MENTAL_MODELS = re.compile(r"### Mental models in plain English", re.IGNORECASE)
RETURN_MATH = re.compile(r"#### Return math in plain English", re.IGNORECASE)
UPSIDE_DOWN = re.compile(r"\*\*Upside / downside from price:\*\*", re.IGNORECASE)
PRIMARY_RISK = re.compile(r"\*\*Primary risk:\*\*", re.IGNORECASE)
HOLDING_CO = re.compile(r"\*\*Archetype\*\*.*holding_co", re.IGNORECASE)
LOOKTHROUGH_OR_SOTP = re.compile(
    r"#### (Look-through snapshot|Sum-of-parts or NAV)", re.IGNORECASE
)
CATALYST_PATH = re.compile(r"#### Catalyst path", re.IGNORECASE)

EM_DASH = "\u2014"  # —
EXEC_SUMMARY_MAX_WORDS = 220
EM_DASH_MAX = 1


def latest_dive(ticker_dir: Path) -> Path | None:
    dives = sorted(ticker_dir.glob("deep_dive_*.md"))
    return dives[-1] if dives else None


def body_before_classification(text: str) -> str:
    idx = text.find("## Classification")
    return text[:idx] if idx >= 0 else text


def extract_executive_summary(text: str) -> str | None:
    m = re.search(
        r"## Executive summary\s*\n+(.*?)(?=\n## |\Z)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    return m.group(1).strip() if m else None


def word_count(s: str) -> int:
    return len(re.findall(r"\b[\w']+\b", s))


def lint_file(path: Path, *, legacy: bool, strict: bool) -> tuple[list[str], list[str]]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    errors: list[str] = []
    warnings: list[str] = []
    rel = path.relative_to(ROOT)

    for pattern, name in REQUIRED_SECTIONS:
        if legacy and name in (
            "What this business is",
            "Why the market might be wrong",
        ):
            continue
        if not re.search(pattern, text, re.IGNORECASE):
            errors.append(f"{rel}: missing section — {name}")

    for pattern, msg in FORBIDDEN:
        if re.search(pattern, text):
            errors.append(f"{rel}: {msg}")

    if "## Classification" in text and "Implied 10yr IRR" not in text:
        errors.append(f"{rel}: Classification table missing Implied 10yr IRR (decision stack)")

    if legacy:
        return errors, warnings

    body = body_before_classification(text)

    if TIER2_HEADER.search(text) and not MENTAL_MODELS.search(text):
        msg = f"{rel}: Tier 2 prompts present but missing ### Mental models in plain English"
        errors.append(msg)

    if not RETURN_MATH.search(text):
        errors.append(f"{rel}: missing #### Return math in plain English (Hohn essentials)")
    if not UPSIDE_DOWN.search(text):
        errors.append(f"{rel}: missing **Upside / downside from price:** (Hohn essentials)")
    if not PRIMARY_RISK.search(text):
        errors.append(f"{rel}: missing **Primary risk:** in Risks section (Hohn essentials)")

    if HOLDING_CO.search(text):
        if not LOOKTHROUGH_OR_SOTP.search(text):
            errors.append(
                f"{rel}: holding_co — missing #### Look-through snapshot or #### Sum-of-parts or NAV"
            )
        if not CATALYST_PATH.search(text):
            (errors if strict else warnings).append(
                f"{rel}: holding_co — missing #### Catalyst path (dated events)"
            )

    em_count = body.count(EM_DASH)
    if em_count > EM_DASH_MAX:
        msg = f"{rel}: {em_count} em dashes in body (max {EM_DASH_MAX}); use periods or parentheses"
        (errors if strict else warnings).append(msg)

    exec_sum = extract_executive_summary(text)
    if exec_sum:
        if EXEC_SUMMARY_LABEL_OPEN.search(exec_sum):
            msg = f"{rel}: executive summary opens with framework label — lead with the business"
            (errors if strict else warnings).append(msg)
        wc = word_count(exec_sum)
        if wc > EXEC_SUMMARY_MAX_WORDS:
            msg = f"{rel}: executive summary is {wc} words (target ≤{EXEC_SUMMARY_MAX_WORDS})"
            (errors if strict else warnings).append(msg)

    return errors, warnings


def main() -> None:
    parser = argparse.ArgumentParser(description="Lint deep dive structure and prose")
    parser.add_argument("ticker", nargs="?", help="Ticker to lint")
    parser.add_argument("--all", action="store_true", help="Lint all dives for ticker")
    parser.add_argument(
        "--legacy",
        action="store_true",
        help="Skip What/Why sections and prose checks (pre-refresh dives)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat prose warnings as errors",
    )
    args = parser.parse_args()

    paths: list[Path] = []
    if args.ticker:
        research = ROOT / args.ticker / "research"
        if args.all:
            paths = sorted(research.glob("deep_dive_*.md"))
        else:
            d = latest_dive(research)
            if d:
                paths = [d]
    else:
        for td in sorted(ROOT.iterdir()):
            if td.is_dir() and (td / "research").is_dir():
                d = latest_dive(td / "research")
                if d:
                    paths.append(d)

    if not paths:
        print("No deep dives found.")
        sys.exit(0)

    all_errors: list[str] = []
    all_warnings: list[str] = []
    for p in paths:
        errs, warns = lint_file(p, legacy=args.legacy, strict=args.strict)
        all_errors.extend(errs)
        all_warnings.extend(warns)

    for w in all_warnings:
        print(f"WARN: {w}")
    if all_errors:
        for e in all_errors:
            print(f"LINT: {e}")
        sys.exit(1)

    suffix = ""
    if args.legacy:
        suffix = " (legacy mode)"
    elif all_warnings:
        suffix = f" ({len(all_warnings)} warning(s))"
    print(f"OK: {len(paths)} deep dive(s){suffix}")


if __name__ == "__main__":
    main()
