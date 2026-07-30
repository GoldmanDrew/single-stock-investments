#!/usr/bin/env python3
"""Audit dashboard snapshots for stale data that the UI would mislabel unavailable."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TECHNICAL_SUMMARY = ROOT / "dashboard" / "data" / "technical_summary.json"
CURRENT_TECHNICAL_MODEL = "technical-fear-v2"


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def audit_technicals(payload: dict) -> tuple[list[str], Counter]:
    rows = payload.get("by_ticker") or {}
    failures: list[str] = []
    counts: Counter = Counter()

    for ticker, row in rows.items():
        counts["total"] += 1
        quality = str(row.get("data_quality") or "")
        observations = int(row.get("observation_count") or 0)
        usable_history = quality == "ready" and observations >= 120
        current_model = row.get("model_version") == CURRENT_TECHNICAL_MODEL

        if usable_history:
            counts["usable_history"] += 1
        if not current_model:
            counts["legacy_model"] += 1
        if row.get("market_structure"):
            counts["market_structure"] += 1

        # A ready price history must never render empty setup pillars merely
        # because its stored snapshot predates the current presentation model.
        if usable_history and not current_model:
            failures.append(
                f"{ticker}: {row.get('model_version') or 'missing model'} has "
                f"{observations} usable observations but no current setup"
            )
            continue

        if current_model and usable_history:
            setup = row.get("setup") or {}
            capitulation = row.get("capitulation") or {}
            missing = [
                field
                for field in ("phase", "direction", "pressure", "participation")
                if not setup.get(field)
            ]
            if missing or not (capitulation.get("scores") or {}).get("confidence"):
                failures.append(
                    f"{ticker}: current technical snapshot is missing "
                    f"{', '.join(missing) if missing else 'capitulation confidence'}"
                )

    return failures, counts


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail when usable dashboard data would be presented as unavailable."
    )
    parser.add_argument(
        "--max-details",
        type=int,
        default=20,
        help="Maximum number of failing ticker details to print.",
    )
    args = parser.parse_args()

    failures, counts = audit_technicals(load_json(TECHNICAL_SUMMARY))
    print(
        "Technical availability: "
        f"{counts['total']} snapshots; "
        f"{counts['usable_history']} usable histories; "
        f"{counts['legacy_model']} legacy snapshots; "
        f"{counts['market_structure']} with float/short-interest coverage."
    )

    if failures:
        print(
            f"FAIL: {len(failures)} usable snapshots would render false or "
            "unexplained unavailable states."
        )
        for failure in failures[: max(0, args.max_details)]:
            print(f"  - {failure}")
        if len(failures) > args.max_details:
            print(f"  ... and {len(failures) - args.max_details} more")
        return 1

    print("PASS: no usable technical snapshot is hidden by a stale data contract.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
