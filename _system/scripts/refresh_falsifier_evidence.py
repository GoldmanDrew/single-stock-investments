#!/usr/bin/env python3
"""Refresh only evidence needed by currently observable falsifier specs."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from automate_valuation_readiness import build_fact_ledger, fetch_companyfacts  # noqa: E402
from falsifier_specs import forecast_dates, read_json, spec_payload_hash  # noqa: E402
from resolve_falsifiers import ATTEMPTS_REL, append_unique_jsonl, load_outcomes  # noqa: E402


def due_tickers(root: Path, today: date) -> list[str]:
    tickers = []
    resolved_hashes = {str(row.get("spec_hash")) for row in load_outcomes(
        root / "_system/research/falsifier_outcomes.jsonl") if row.get("spec_hash")}
    for path in sorted(root.glob("*/research/falsifier_specs.json")):
        doc = read_json(path)
        if any(not spec.get("untestable")
               and spec_payload_hash(spec) not in resolved_hashes
               and forecast_dates(spec)[1]
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
    attempts = []
    for ticker in due_tickers(root, today):
        cik = registry_cik(root, ticker)
        try:
            fetched = fetch_companyfacts(ticker, cik)
            returncode = int(fetched.get("returncode") or 0)
            result = {"ticker": ticker, "cik": cik, "fetch_returncode": returncode}
            if returncode == 0 and cik:
                ledger = build_fact_ledger(ticker, today.isoformat())
                if write:
                    path = root / ticker / "research/valuation_fact_ledger.json"
                    path.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
                result["ledger_facts"] = len(ledger.get("facts") or [])
                result["status"] = "success"
            elif not cik:
                result["status"] = "adapter_missing"
                result["reason_code"] = "cik_missing"
            else:
                result["status"] = "transient_failure"
                result["reason_code"] = "companyfacts_fetch_failed"
        except Exception as exc:  # isolate one ticker; preserve the rest of the run
            result = {"ticker": ticker, "cik": cik, "fetch_returncode": 1,
                      "status": "transient_failure", "reason_code": type(exc).__name__,
                      "error": str(exc)[:500]}
        attempt_key = f"refresh|{ticker}|{today.isoformat()}|{result.get('reason_code') or result.get('status')}"
        attempts.append({
            "attempt_id": hashlib.sha256(attempt_key.encode()).hexdigest()[:24],
            "ticker": ticker,
            "attempted_on": today.isoformat(),
            "adapter": "sec_companyfacts_refresh",
            "reason_code": result.get("reason_code"),
            "status": result.get("status"),
            "recorded_at": datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc).isoformat(),
        })
        results.append(result)
    if write:
        append_unique_jsonl(root / ATTEMPTS_REL, attempts,
                            ("ticker", "attempted_on", "adapter", "reason_code"))
    failed = sum(row.get("status") != "success" for row in results)
    return {"as_of": today.isoformat(), "tickers": results, "failed": failed,
            "status": "no_work" if not results else "success" if not failed else
                      "failed" if failed == len(results) else "partial"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()
    result = refresh(ROOT, date.fromisoformat(args.date))
    print(json.dumps(result, indent=2))
    # Per-ticker failures are durable queue state, not grounds to prevent
    # successful tickers from reaching the resolver. Fail only when every
    # attempted ticker failed, which signals a systemic acquisition outage.
    return 1 if result["tickers"] and result["failed"] == len(result["tickers"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
