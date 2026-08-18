#!/usr/bin/env python3
"""Build due schedules for frozen committee forecasts and owner decisions."""
from __future__ import annotations

import argparse
import calendar
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def add_months(value: str, months: int) -> str:
    source = date.fromisoformat(value[:10])
    index = source.month - 1 + months
    year, month = source.year + index // 12, index % 12 + 1
    return date(year, month, min(source.day, calendar.monthrange(year, month)[1])).isoformat()


def _jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _outcome_keys(rows: list[dict]) -> set[tuple]:
    return {(str(row.get("forecast_id") or row.get("decision_id") or row.get("ticker")),
             int(row.get("horizon_months") or 0)) for row in rows}


def build(as_of: str, root: Path = ROOT) -> dict:
    rows = []
    committee_outcomes = _outcome_keys(_jsonl(
        root / "_system/research/committee_forecast_outcomes.jsonl"))
    decision_outcomes = _outcome_keys(_jsonl(
        root / "_system/research/committee_outcomes.jsonl"))
    attempt_rows = _jsonl(root / "_system/research/committee_outcome_attempts.jsonl")
    attempts: dict[tuple[str, int], list[dict]] = {}
    for attempt in attempt_rows:
        key = (str(attempt.get("forecast_id") or ""), int(attempt.get("horizon_months") or 0))
        attempts.setdefault(key, []).append(attempt)

    for forecast in _jsonl(root / "_system/research/committee_forecasts.jsonl"):
        forecast_id = str(forecast.get("forecast_id") or "")
        forecast_date = str(forecast.get("forecast_date") or "")[:10]
        if not forecast_id or not forecast_date:
            continue
        for months in forecast.get("outcome_horizons_months") or [1, 3, 6, 12, 24]:
            months = int(months)
            due = add_months(forecast_date, months)
            recorded = (forecast_id, months) in committee_outcomes
            prior_attempts = attempts.get((forecast_id, months), [])
            status = ("recorded" if recorded else
                      "needs_semantic_review" if due <= as_of and len(prior_attempts) >= 3 else
                      "due" if due <= as_of else "scheduled")
            rows.append({
                "item_type": "committee_forecast",
                "forecast_id": forecast_id,
                "ticker": forecast.get("ticker"),
                "forecast_date": forecast_date,
                "horizon_months": months,
                "due_date": due,
                "status": status,
                "attempt_count": len(prior_attempts),
                "last_attempt_reason": (prior_attempts[-1].get("reason_code")
                                        if prior_attempts else None),
                "committee_ref": forecast.get("committee_ref"),
            })

    for decision_path in sorted(root.glob("*/research/human_decision.json")):
        decision = json.loads(decision_path.read_text(encoding="utf-8"))
        if decision.get("status") != "decided" or not decision.get("decision"):
            continue
        ticker = decision_path.parents[1].name.upper()
        decided_at = str(decision.get("decided_at") or "")
        if not decided_at:
            continue
        decision_id = str(decision.get("decision_id") or
                          f"{ticker}|{decided_at}|{decision.get('committee_source') or ''}")
        for months in decision.get("outcome_horizons_months") or [6, 12, 24]:
            months = int(months)
            due = add_months(decided_at, months)
            recorded = (decision_id, months) in decision_outcomes or (ticker, months) in decision_outcomes
            rows.append({
                "item_type": "owner_decision",
                "decision_id": decision_id,
                "ticker": ticker,
                "decision_date": decided_at[:10],
                "horizon_months": months,
                "due_date": due,
                "status": "recorded" if recorded else "due" if due <= as_of else "scheduled",
                "committee_ref": decision.get("committee_source"),
            })
    return {
        "schema_version": "2.0", "as_of": as_of,
        "items": sorted(rows, key=lambda row: (row["due_date"], str(row.get("ticker")), row["item_type"])),
        "counts": {status: sum(row["status"] == status for row in rows)
                   for status in ("scheduled", "due", "needs_semantic_review", "recorded")},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    payload = build(args.date, args.root)
    target = args.out or args.root / "_system/research/committee_monitoring.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
