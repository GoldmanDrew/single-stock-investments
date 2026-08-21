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


def _default_sleeve_tags_path() -> Path:
    # SleeveStore's default store_dir ("data/local"); read directly so the hub
    # stays dependency-light and strictly read-only against the sleeve desk.
    return Path(__file__).parents[1] / "sleeves" / "data" / "local" / "sleeve_tags.json"


def load_ls_universe(path: str | Path | None = None) -> set[str]:
    payload = json.loads((Path(path) if path else _default_universe_path()).read_text(encoding="utf-8"))
    return {norm_sym(symbol) for symbol in payload.get("symbols") or [] if norm_sym(symbol)}


def load_drew_symbols(path: str | Path | None = None) -> set[str]:
    """Tickers held by Drew's sleeve, from the desk's owner-tagged buys.

    Drew's book is defined by DREW_SLEEVE-stamped orders; positions carry no
    orderRef, so the durable record is the sleeve store's tag ledger. Absent or
    empty file means Drew holds nothing yet (the sleeve starts as cash) and the
    residual policy sends everything non-systematic to Michael.
    """
    target = Path(path) if path else _default_sleeve_tags_path()
    if not target.exists():
        return set()
    tags = json.loads(target.read_text(encoding="utf-8")) or []
    return {
        norm_sym(tag.get("ticker") or "")
        for tag in tags
        if str(tag.get("owner") or "").strip().lower() == "drew" and norm_sym(tag.get("ticker") or "")
    }


def classify_policy_position(
    row: dict[str, Any], *, ls_symbols: Iterable[str], drew_symbols: Iterable[str] = (),
) -> PolicyAllocation:
    """Owner custody rule: Michael's book is everything EXCEPT
    SPX option strategies, every ticker in ls-algo's universe (ETFs and
    underlyings alike), and Drew's sleeve holdings."""
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
        drew_symbols=set(drew_symbols),
    )
    if classification.bucket == "spx_0dte":
        return PolicyAllocation("unallocated", "spx_0dte", "spx_option_strategy_exclusion")
    if classification.bucket == "etf_ls":
        return PolicyAllocation("unallocated", "letf", "ls_algo_universe_exclusion")
    if classification.bucket == "drew":
        return PolicyAllocation("drew", "single_stock", "drew_sleeve_holding")
    if classification.bucket == "ignored":
        return PolicyAllocation("unallocated", "other", classification.reason)
    return PolicyAllocation("michael", "single_stock", "michael_residual_book")


def residual_quantity(position_quantity: Any, explicit_quantities: Iterable[Any]) -> Decimal:
    return Decimal(str(position_quantity)) - sum((Decimal(str(value)) for value in explicit_quantities), Decimal("0"))
