#!/usr/bin/env python3
"""Lint deep dives for decision-stack report structure.

Usage:
  python _system/scripts/lint_deep_dive.py              # all tickers, latest dive each
  python _system/scripts/lint_deep_dive.py ICE        # latest ICE dive
  python _system/scripts/lint_deep_dive.py --all ICE    # all ICE dives
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

REQUIRED_SECTIONS = [
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


def latest_dive(ticker_dir: Path) -> Path | None:
    dives = sorted(ticker_dir.glob("deep_dive_*.md"))
    return dives[-1] if dives else None


def lint_file(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    errors: list[str] = []
    rel = path.relative_to(ROOT)
    for pattern, name in REQUIRED_SECTIONS:
        if not re.search(pattern, text, re.IGNORECASE):
            errors.append(f"{rel}: missing section — {name}")
    for pattern, msg in FORBIDDEN:
        if re.search(pattern, text):
            errors.append(f"{rel}: {msg}")
    if "## Classification" in text and "Implied 10yr IRR" not in text:
        errors.append(f"{rel}: Classification table missing Implied 10yr IRR (decision stack)")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Lint deep dive structure")
    parser.add_argument("ticker", nargs="?", help="Ticker to lint")
    parser.add_argument("--all", action="store_true", help="Lint all dives for ticker")
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
    for p in paths:
        all_errors.extend(lint_file(p))

    if all_errors:
        for e in all_errors:
            print(f"LINT: {e}")
        sys.exit(1)

    print(f"OK: {len(paths)} deep dive(s)")


if __name__ == "__main__":
    main()
