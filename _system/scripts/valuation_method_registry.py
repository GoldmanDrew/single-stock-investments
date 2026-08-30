#!/usr/bin/env python3
"""Read and enforce the approved, versioned valuation method registry."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "_system" / "reference" / "valuation_method_registry.json"
OUTPUT_BASES = {
    "present_value_today",
    "future_payoff",
    "forward_cashflow_schedule",
}


@lru_cache(maxsize=1)
def registry() -> dict[str, dict]:
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    approved = {}
    for row in data.get("method_cards") or []:
        if row.get("status") != "approved":
            continue
        key = f"{row['method_id']}@{row['version']}"
        if row.get("output_basis") not in OUTPUT_BASES:
            raise ValueError(
                f"{key}: approved method must declare output_basis as one of "
                f"{', '.join(sorted(OUTPUT_BASES))}"
            )
        approved[key] = row
    return approved


def approved_method(method_id: str | None, version: str | None) -> dict | None:
    return registry().get(f"{method_id}@{version}")
