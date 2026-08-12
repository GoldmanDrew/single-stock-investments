#!/usr/bin/env python3
"""Refresh only evidence needed by currently observable falsifier specs."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from automate_valuation_readiness import build_fact_ledger, fetch_companyfacts  # noqa: E402
from falsifier_specs import forecast_dates, read_json  # noqa: E402


def due_tickers(root: Path, today: date) -> list[str]:
    tickers = []
    for path in sorted(root.glob("*/research/falsifier_specs.json")):
        doc = read_json(path)
        if any(not spec.get("untestable") and forecast_dates(spec)[1]
               and forecast_dates(spec)[1] <= today
               for spec in doc.get("specs") or []):
            tickers.append(path.parents[1].name.upper())
    return tickers


def registry_cik(root: Path, ticker: str) -> str | None:
    identity = read_json(root / ticker / "research/security_identity.json")
    if identity.get("cik"):
        return str(identity["cik"])
    registry = read_json(root / "_system/portfolio/registry.json")
    rows = registry.get("holdings") or registry.get("tickers") or registry
    row = rows.get(ticker) or {}
    return str(row.get("cik")) if row.get("cik") else None


def refresh(root: Path, today: date, write: bool = True) -> dict:
    results = []
    for ticker in due_tickers(root, today):
        cik = registry_cik(root, ticker)
        fetched = fetch_companyfacts(ticker, cik)
        result = {"ticker": ticker, "cik": cik,
                  "fetch_returncode": fetched.get("returncode")}
        if fetched.get("returncode") == 0 and cik:
            ledger = build_fact_ledger(ticker, today.isoformat())
            if write:
                path = root / ticker / "research/valuation_fact_ledger.json"
                path.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
            result["ledger_facts"] = len(ledger.get("facts") or [])
        results.append(result)
    return {"as_of": today.isoformat(), "tickers": results,
            "failed": sum(row["fetch_returncode"] != 0 for row in results)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()
    result = refresh(ROOT, date.fromisoformat(args.date))
    print(json.dumps(result, indent=2))
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
