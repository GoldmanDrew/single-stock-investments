#!/usr/bin/env python3
"""Refresh Short Alpha borrow from an authenticated IBKR export.

Input CSV columns: symbol,borrow_rate_pct,as_of. The export can contain any
universe; this writer retains only the live Short Alpha tickers, so new ideas
are automatically picked up on the next refresh without a code change.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "_system" / "research" / "short-alpha" / "ideas.json"
OUTPUT = ROOT / "dashboard" / "data" / "short_alpha_borrow.json"
EXCLUDED = {"ECHX"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="IBKR normalized borrow CSV")
    args = parser.parse_args()
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    tickers = {str(row["ticker"]).upper() for row in ledger["ideas"]} - EXCLUDED
    rates: dict[str, dict] = {}
    with args.input.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            ticker = str(row.get("symbol") or "").upper().strip()
            if ticker not in tickers:
                continue
            try:
                rate = float(row["borrow_rate_pct"])
            except (KeyError, TypeError, ValueError):
                continue
            rates[ticker] = {
                "rate_pct": rate,
                "as_of": row.get("as_of") or None,
                "status": "available",
                "source": "IBKR borrow export",
            }
    OUTPUT.write_text(json.dumps({
        "schema_version": "1.0",
        "provider": "IBKR",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "rates": rates,
        "note": "Missing names are pending a valid IBKR borrow observation, not a zero fee.",
    }, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
