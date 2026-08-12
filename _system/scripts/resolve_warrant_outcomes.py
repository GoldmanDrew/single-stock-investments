#!/usr/bin/env python3
"""Resolve matured point-in-time warrant cohorts and build calibration.

This is descriptive only.  It never mutates scoring weights, portfolio sizing,
or trade state.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from warrant_common import (
    CALIBRATION_PATH,
    COHORTS_PATH,
    MARKET_HISTORY_PATH,
    OUTCOMES_PATH,
    append_jsonl,
    latest_registry,
    load_jsonl,
    parse_date,
    utc_now,
    write_json,
)


def corporate_action_terminal(record: dict | None, due) -> dict | None:
    """Survivorship-free terminal value when trading disappears before due."""
    if not record:
        return None
    action = record.get("corporate_action") or {}
    action_date = parse_date(action.get("effective_at"))
    if action_date and action_date <= due and action.get("cash_per_warrant") is not None:
        return {
            "quote_date": action_date.isoformat(),
            "close": float(action["cash_per_warrant"]),
            "outcome_kind": str(record.get("lifecycle") or "corporate_action"),
        }
    expiry = parse_date((record.get("terms") or {}).get("expiry"))
    if record.get("lifecycle") == "expired" and expiry and expiry <= due:
        return {"quote_date": expiry.isoformat(), "close": 0.0, "outcome_kind": "expired_zero"}
    return None


def resolve() -> tuple[int, dict]:
    cohorts = load_jsonl(COHORTS_PATH)
    observations = load_jsonl(MARKET_HISTORY_PATH)
    existing = {str(row.get("outcome_id")) for row in load_jsonl(OUTCOMES_PATH)}
    registry = {str(row.get("warrant_id")): row for row in latest_registry()}
    by_warrant: dict[str, list[dict]] = defaultdict(list)
    for row in observations:
        if row.get("role") == "warrant" and parse_date(row.get("quote_date")):
            by_warrant[str(row.get("warrant_id"))].append(row)
    for rows in by_warrant.values():
        rows.sort(key=lambda row: str(row.get("quote_date")))

    new_rows: list[dict] = []
    for cohort in cohorts:
        baseline_date = parse_date(cohort.get("baseline_date"))
        baseline = cohort.get("baseline_warrant_close")
        if not baseline_date or baseline in (None, 0):
            continue
        for horizon in cohort.get("horizons_days") or [90, 365]:
            due = baseline_date + timedelta(days=int(horizon))
            outcome_id = f"{cohort.get('cohort_id')}:{horizon}d"
            if outcome_id in existing:
                continue
            candidates = [
                row for row in by_warrant.get(str(cohort.get("warrant_id")), [])
                if parse_date(row.get("quote_date")) and parse_date(row.get("quote_date")) >= due
            ]
            terminal = candidates[0] if candidates else corporate_action_terminal(
                registry.get(str(cohort.get("warrant_id"))), due
            )
            if terminal is None:
                continue
            terminal_price = float(terminal["close"])
            total_return = terminal_price / float(baseline) - 1
            new_rows.append(
                {
                    "outcome_id": outcome_id,
                    "cohort_id": cohort.get("cohort_id"),
                    "warrant_id": cohort.get("warrant_id"),
                    "lane": cohort.get("lane"),
                    "horizon_days": int(horizon),
                    "baseline_date": cohort.get("baseline_date"),
                    "baseline_price": baseline,
                    "outcome_date": terminal.get("quote_date"),
                    "outcome_price": terminal_price,
                    "total_return_pct": round(total_return * 100, 4),
                    "positive_return": total_return > 0,
                    "outcome_kind": terminal.get("outcome_kind", "market_quote"),
                    "resolved_at": utc_now(),
                    "point_in_time": True,
                }
            )
    added = append_jsonl(OUTCOMES_PATH, new_rows, identity_key="outcome_id")

    all_outcomes = load_jsonl(OUTCOMES_PATH)
    buckets: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for row in all_outcomes:
        buckets[(str(row.get("lane") or "other"), int(row.get("horizon_days") or 0))].append(row)
    calibration_rows = []
    for (lane, horizon), rows in sorted(buckets.items()):
        returns = [float(row["total_return_pct"]) for row in rows]
        calibration_rows.append(
            {
                "lane": lane,
                "horizon_days": horizon,
                "sample_size": len(rows),
                "positive_rate_pct": round(sum(value > 0 for value in returns) / len(returns) * 100, 2),
                "mean_return_pct": round(sum(returns) / len(returns), 2),
                "min_return_pct": round(min(returns), 2),
                "max_return_pct": round(max(returns), 2),
            }
        )
    calibration = {
        "schema_version": "1.0",
        "generated_at": utc_now(),
        "outcome_count": len(all_outcomes),
        "buckets": calibration_rows,
        "policy": "descriptive_only_no_automatic_weight_changes",
    }
    write_json(CALIBRATION_PATH, calibration)
    return added, calibration


def main() -> int:
    added, calibration = resolve()
    print(f"warrant outcomes: added={added}; total={calibration['outcome_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
