#!/usr/bin/env python3
"""Full Marvin refresh for all registry holdings.

Pipeline per ticker:
  build_filing_evidence.py → marvin_valuation.py --write → refresh_deep_dive_v2.py → lint_deep_dive.py

Usage:
  python _system/scripts/batch_portfolio_refresh.py --date 2026-05-29
  python _system/scripts/batch_portfolio_refresh.py --date 2026-05-29 --skip SNOW
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
PY = sys.executable


def tickers_from_registry() -> list[str]:
    reg = ROOT / "_system" / "portfolio" / "registry.json"
    data = json.loads(reg.read_text(encoding="utf-8"))
    return sorted(data.get("holdings", {}).keys())


def run_step(label: str, cmd: list[str]) -> bool:
    print(f"  {label}...", flush=True)
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    out = (r.stdout or "") + (r.stderr or "")
    if out.strip():
        for line in out.strip().splitlines()[-8:]:
            print(f"    {line}")
    if r.returncode != 0:
        print(f"  FAIL {label} exit={r.returncode}")
        return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="Deep dive output date YYYY-MM-DD")
    parser.add_argument("--skip", nargs="*", default=[], help="Tickers to skip")
    parser.add_argument("--only", nargs="*", help="Only these tickers")
    args = parser.parse_args()

    tickers = args.only or tickers_from_registry()
    skip = {t.upper() for t in args.skip}
    ok, fail, skipped = [], [], []

    for ticker in tickers:
        if ticker in skip:
            skipped.append(ticker)
            print(f"SKIP {ticker} (--skip)")
            continue
        print(f"\n=== {ticker} ===")
        research = ROOT / ticker / "research"
        if not research.is_dir():
            print(f"SKIP {ticker}: no research/")
            skipped.append(ticker)
            continue
        if not (research / "valuation.json").exists():
            print(f"SKIP {ticker}: no valuation.json")
            skipped.append(ticker)
            continue

        steps_ok = True
        steps_ok &= run_step(
            "filing evidence",
            [PY, str(SCRIPTS / "build_filing_evidence.py"), ticker],
        )
        steps_ok &= run_step(
            "valuation",
            [PY, str(SCRIPTS / "marvin_valuation.py"), "--ticker", ticker, "--write"],
        )
        steps_ok &= run_step(
            "deep dive refresh",
            [PY, str(SCRIPTS / "refresh_deep_dive_v2.py"), ticker, "--date", args.date],
        )
        lint_ok = run_step(
            "lint",
            [PY, str(SCRIPTS / "lint_deep_dive.py"), ticker],
        )
        if steps_ok and lint_ok:
            ok.append(ticker)
        else:
            fail.append(ticker)

    print(f"\n=== Done {args.date} ===")
    print(f"OK ({len(ok)}): {', '.join(ok) or 'none'}")
    print(f"FAIL ({len(fail)}): {', '.join(fail) or 'none'}")
    print(f"SKIP ({len(skipped)}): {', '.join(skipped) or 'none'}")
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
