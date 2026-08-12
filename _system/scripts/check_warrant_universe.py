#!/usr/bin/env python3
"""Validate warrant registry, event ledger, market state, and dashboard gates."""
from __future__ import annotations

import argparse
from datetime import date

from warrant_common import (
    DASHBOARD_PATH,
    DISCOVERY_STATE_PATH,
    EVENTS_PATH,
    MARKET_PATH,
    load_jsonl,
    parse_date,
    read_json,
    validate_registry,
)


def check(*, strict: bool) -> tuple[list[str], list[str]]:
    errors = validate_registry()
    warnings: list[str] = []
    event_ids: set[str] = set()
    for row in load_jsonl(EVENTS_PATH):
        event_id = str(row.get("event_id") or "")
        if not event_id:
            errors.append("event row missing event_id")
        elif event_id in event_ids:
            errors.append(f"duplicate event_id: {event_id}")
        event_ids.add(event_id)
        if not str(row.get("source_url") or "").startswith("https://www.sec.gov/Archives/"):
            errors.append(f"event {event_id}: source is not accession-locked SEC URL")

    market = read_json(MARKET_PATH, {}) or {}
    market_stamp = parse_date(market.get("last_successful_refresh"))
    if market_stamp is None:
        warnings.append("market has no successful refresh stamp")
    elif (date.today() - market_stamp).days > 5:
        warnings.append(f"market last successful refresh is {(date.today() - market_stamp).days} days old")

    discovery = read_json(DISCOVERY_STATE_PATH, {}) or {}
    if discovery.get("unhealthy"):
        warnings.append(
            f"SEC discovery unhealthy after {discovery.get('consecutive_failures')} consecutive failures"
        )

    dashboard = read_json(DASHBOARD_PATH, {}) or {}
    if not dashboard:
        errors.append("dashboard/data/warrants.json missing or invalid")
    health = dashboard.get("health") or {}
    if health.get("status") == "unhealthy":
        warnings.append("dashboard warrant feed reports unhealthy")
    stale_active_quotes = health.get("stale_active_quotes") or []
    if stale_active_quotes:
        warnings.append(
            "active warrant delayed marks are stale or missing: "
            + ", ".join(map(str, stale_active_quotes))
        )
    for row in dashboard.get("rows") or []:
        score = (row.get("diagnostics") or {}).get("opportunity_score")
        gates = row.get("gates") or {}
        all_pass = all((gates.get(name) or {}).get("pass") for name in ("identity", "survival", "market"))
        if score is not None and not all_pass:
            errors.append(f"{row.get('warrant_ticker')}: opportunity score emitted before all gates passed")
        if row.get("lifecycle") != "active" and row.get("status") == "review_ready":
            errors.append(f"{row.get('warrant_ticker')}: inactive security marked review_ready")
    if health.get("structural_errors"):
        errors.append("dashboard health carries structural registry errors")
    if strict:
        errors.extend(warnings)
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    errors, warnings = check(strict=args.strict)
    for warning in warnings:
        print(f"WARN: {warning}")
    if errors:
        print(f"check_warrant_universe: {len(errors)} issue(s)")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("check_warrant_universe: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
