#!/usr/bin/env python3
"""Record due, non-actionable committee forecast outcomes in isolation."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

from build_committee_monitoring import build as build_monitoring
from build_total_return_panel import compute_period_total_return
from committee_calibration import summarize

ROOT = Path(__file__).resolve().parents[2]


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def record_due(root: Path = ROOT, as_of: str | None = None, write: bool = True) -> dict:
    as_of = as_of or date.today().isoformat()
    forecasts = {row["forecast_id"]: row for row in _rows(
        root / "_system/research/committee_forecasts.jsonl")}
    ledger = root / "_system/research/committee_forecast_outcomes.jsonl"
    existing = _rows(ledger)
    seen = {(row.get("forecast_id"), int(row.get("horizon_months") or 0)) for row in existing}
    fresh, attempts = [], []
    for item in build_monitoring(as_of, root).get("items") or []:
        if item.get("item_type") != "committee_forecast" or item.get("status") != "due":
            continue
        key = (item.get("forecast_id"), int(item.get("horizon_months") or 0))
        if key in seen:
            continue
        forecast = forecasts.get(str(item.get("forecast_id")))
        if not forecast:
            continue
        try:
            outcome = compute_period_total_return(
                str(forecast["ticker"]), str(forecast["forecast_date"]), str(item["due_date"]))
            if outcome.get("return_status") != "complete":
                raise ValueError(
                    f"return_not_complete:{outcome.get('return_status')}:"
                    f"{outcome.get('error') or 'missing verified return evidence'}")
            row = {
                **outcome,
                "outcome_class": "committee_forecast",
                "forecast_id": forecast["forecast_id"],
                "ticker": forecast["ticker"],
                "decision_date": forecast["forecast_date"],
                "measurement_date": item["due_date"],
                "horizon_months": item["horizon_months"],
                "committee_ref": forecast.get("committee_ref"),
                "committee_packet_hash": forecast.get("committee_packet_hash"),
                "power_zone": forecast.get("power_zone"),
                "votes": forecast.get("votes") or [],
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "outcome_id": hashlib.sha256(
                    f"{forecast['forecast_id']}|{item['horizon_months']}".encode()).hexdigest()[:24],
                "revision": 1,
            }
            fresh.append(row)
            seen.add(key)
        except Exception as exc:
            attempts.append({
                "forecast_id": forecast["forecast_id"], "ticker": forecast["ticker"],
                "horizon_months": item["horizon_months"], "attempted_at": datetime.now(timezone.utc).isoformat(),
                "status": "retry_wait", "reason_code": type(exc).__name__, "error": str(exc)[:500],
            })
    if write:
        ledger.parent.mkdir(parents=True, exist_ok=True)
        with ledger.open("a", encoding="utf-8") as handle:
            for row in fresh:
                handle.write(json.dumps(row, sort_keys=True) + "\n")
        attempt_path = root / "_system/research/committee_outcome_attempts.jsonl"
        with attempt_path.open("a", encoding="utf-8") as handle:
            for row in attempts:
                handle.write(json.dumps(row, sort_keys=True) + "\n")
        owner_rows = _rows(root / "_system/research/committee_outcomes.jsonl")
        calibration = summarize(owner_rows + existing + fresh)
        (root / "_system/research/committee_calibration.json").write_text(
            json.dumps(calibration, indent=2) + "\n", encoding="utf-8")
        from build_calibration_brief import build as build_brief
        build_brief(root)
    return {"recorded": len(fresh), "attempts": len(attempts), "rows": fresh}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = record_due(args.root, args.date, not args.dry_run)
    print(json.dumps({key: result[key] for key in ("recorded", "attempts")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
