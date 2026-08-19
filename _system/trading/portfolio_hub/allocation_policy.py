from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

from _system.trading.sleeves.classify_positions import classify_position, norm_sym


POLICY_SOURCE_PREFIX = "policy:owner-custody:v1"


@dataclass(frozen=True)
class PolicyAllocation:
    owner: str
    strategy: str
    reason: str


def _default_universe_path() -> Path:
    return Path(__file__).parents[1] / "sleeves" / "data" / "etf_ls_universe.json"


def load_ls_universe(path: str | Path | None = None) -> set[str]:
    payload = json.loads((Path(path) if path else _default_universe_path()).read_text(encoding="utf-8"))
    return {norm_sym(symbol) for symbol in payload.get("symbols") or [] if norm_sym(symbol)}


def classify_policy_position(row: dict[str, Any], *, ls_symbols: Iterable[str]) -> PolicyAllocation:
    symbol = norm_sym(row.get("symbol") or row.get("local_symbol") or "")
    if not symbol:
        return PolicyAllocation("unallocated", "other", "missing_symbol_quarantine")
    classification = classify_position(
        {
            "symbol": symbol,
            "localSymbol": row.get("local_symbol"),
            "secType": row.get("sec_type"),
            "underlying": row.get("underlying"),
            "orderRef": row.get("order_ref"),
        },
        blacklist_family=set(),
        etf_ls_symbols=set(ls_symbols),
    )
    if classification.bucket == "spx_0dte":
        return PolicyAllocation("unallocated", "spx_0dte", "spx_option_strategy_exclusion")
    if classification.bucket == "etf_ls":
        return PolicyAllocation("unallocated", "letf", "ls_algo_universe_exclusion")
    if classification.bucket == "ignored":
        return PolicyAllocation("unallocated", "other", classification.reason)
    return PolicyAllocation("michael", "single_stock", "michael_residual_book")


def residual_quantity(position_quantity: Any, explicit_quantities: Iterable[Any]) -> Decimal:
    return Decimal(str(position_quantity)) - sum((Decimal(str(value)) for value in explicit_quantities), Decimal("0"))
