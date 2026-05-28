#!/usr/bin/env python3
"""Milly consistency re-pass after Marvin fixes factual errors.

Runs lint_deep_dive + lint_adversarial --consistency-only.
Appends one line to _system/research/milly_log.md.

Usage:
  python _system/scripts/milly_repass.py QDEL
  python _system/scripts/milly_repass.py QDEL --note "fixed returns statement"
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOG = ROOT / "_system" / "research" / "milly_log.md"


def run(cmd: list[str]) -> int:
    r = subprocess.run(cmd, cwd=ROOT)
    return r.returncode


def append_log(ticker: str, ok: bool, note: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    if not LOG.exists():
        LOG.write_text(
            "# Milly pass log\n\n"
            "| Date | Ticker | Pass type | Result | Note |\n"
            "|------|--------|-----------|--------|------|\n",
            encoding="utf-8",
        )
    row = f"| {date.today().isoformat()} | {ticker} | consistency_repass | {'OK' if ok else 'FAIL'} | {note or '—'} |\n"
    with LOG.open("a", encoding="utf-8") as f:
        f.write(row)


def main() -> None:
    parser = argparse.ArgumentParser(description="Milly consistency re-pass")
    parser.add_argument("ticker", help="Ticker symbol")
    parser.add_argument("--note", default="", help="Optional note for milly_log")
    args = parser.parse_args()

    py = sys.executable
    scripts = ROOT / "_system" / "scripts"
    codes = [
        run([py, str(scripts / "lint_deep_dive.py"), args.ticker]),
        run([py, str(scripts / "lint_adversarial.py"), args.ticker, "--consistency-only"]),
    ]
    ok = all(c == 0 for c in codes)
    append_log(args.ticker, ok, args.note)
    if not ok:
        print("FAIL: consistency re-pass — fix errors above, update adversarial YAML block_final: false")
        sys.exit(1)
    print(f"OK: {args.ticker} consistency re-pass")


if __name__ == "__main__":
    main()
