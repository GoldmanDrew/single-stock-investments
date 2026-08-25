"""Broker truth from IBKR Flex. No Gateway, no client ID, no polling.

This is the replacement for the collector that was masked on 2026-08-25 for
reconnect-storming the Gateway shared with the live SPX 0DTE executor
(CLAUDE.md rule 9). The difference is structural, not a tuning change:

  * Flex is an HTTPS report service. It cannot contend with SPX for a Gateway
    socket, an API client id, or a market-data line, because it uses none of
    them. There is no failure mode here that reaches the executor.
  * It reads XML that already exists on disk. ls-algo fetches these files once
    a day for its own accounting, so this path adds *zero* IBKR requests --
    not a smaller number of them, zero.
  * It runs once, after the close, and exits. Nothing is held open between runs.

It also removes the FX problem rather than fixing it. Flex states
`fxRateToBase` on every position row, so nothing is inferred; the collector had
to derive a rate from marketValue / (position x price) and got ~1.0 for every
foreign holding, publishing yen at dollar magnitudes.

What Flex does not give us, and must be said out loud: this query carries only
`OpenPosition`. There are no account values in it -- no NetLiquidation, no
margin, no buying power -- so a snapshot built from it is deliberately
`complete: false` and the read model will not serve it as the account book
until an equity-summary section is added to the Flex query in Client Portal.
Publishing it as complete would put a positions-only snapshot behind a cockpit
that shows margin and NAV, which would then be silently stale forever.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .flex import parse_flex_file
from .publisher import publish_payload


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _text(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def file_age_hours(path: Path, now: float | None = None) -> float:
    import time

    return ((now or time.time()) - path.stat().st_mtime) / 3600.0


def build_account_snapshot(
    positions_xml: Path, *, account_alias: str, base_currency: str = "USD",
    source_run_id: str | None = None,
) -> dict[str, Any]:
    """An account_snapshot.v1 envelope sourced entirely from Flex.

    Deliberately reuses the existing schema rather than inventing a Flex-shaped
    one: every consumer -- the read model, the risk endpoint, the allocation
    ledger -- already speaks it, and a parallel schema would mean two code paths
    that can disagree about the same account.
    """
    parsed = parse_flex_file(positions_xml, account_alias=account_alias)
    rows: list[dict[str, Any]] = []
    untranslated = 0

    # Flex reports at LOT level: 5,804 rows for roughly 495 instruments, with
    # the same conId repeated once per tax lot. `portfolio_positions` is keyed
    # (source_run_id, account_alias, conid, model_code), so inserting lots
    # directly would collide on the primary key and fail the whole batch. Lots
    # are summed into one position per contract here -- quantity and value add,
    # and average cost is recomputed from the summed cost so it stays a real
    # weighted average rather than the mean of per-lot averages.
    for row in _fold_lots(parsed["positions"]):
        conid = int(row.get("conid") or 0)
        if conid <= 0:
            # A position with no conId cannot be reconciled or allocated. Count
            # it rather than dropping it silently.
            untranslated += 1
            continue
        currency = str(row.get("currency") or base_currency).upper()
        quantity = _decimal(row.get("quantity")) or Decimal(0)
        native_value = _decimal(row.get("market_value"))
        rate = _decimal(row.get("fx_rate_to_base"))
        sec_type = str(row.get("sec_type") or "STK").upper()

        if currency == base_currency:
            fx_rate, fx_source = Decimal(1), "identity"
        elif rate is not None and rate > 0:
            fx_rate, fx_source = rate, "ibkr_flex_rate"
        else:
            fx_rate, fx_source = None, "fx_unavailable"
            untranslated += 1

        base_value = None if (native_value is None or fx_rate is None) else native_value * fx_rate
        unrealized_native = _decimal(row.get("unrealized_pnl"))
        unrealized_base = None if (unrealized_native is None or fx_rate is None) else unrealized_native * fx_rate
        cost = _decimal(row.get("cost_basis"))

        rows.append({
            "account_alias": account_alias, "conid": conid,
            "model_code": row.get("model_code") or "",
            "symbol": str(row.get("symbol") or ""),
            "local_symbol": row.get("local_symbol") or None,
            "description": row.get("description") or None,
            "sec_type": sec_type, "currency": currency,
            "native_currency": currency, "base_currency": base_currency,
            "quantity_unit": "contracts" if sec_type in {"OPT", "FOP"} else "shares",
            "exchange": row.get("exchange") or None,
            "expiry": row.get("expiry") or None,
            "strike": row.get("strike") or None,
            "right": row.get("right") or None,
            "multiplier": row.get("multiplier") or None,
            "quantity": _text(quantity),
            "average_cost": _text(cost / quantity) if cost is not None and quantity else None,
            "average_cost_native": _text(cost / quantity) if cost is not None and quantity else None,
            "mark": row.get("mark"), "mark_native": row.get("mark"),
            "market_value": _text(native_value), "market_value_native": _text(native_value),
            # The envelope requires a decimal here even when the row cannot be
            # translated; fx_source and quality are what forbid using it as base.
            "market_value_base": _text(base_value if base_value is not None else native_value),
            "fx_rate_to_base": _text(fx_rate), "fx_as_of": parsed["as_of"], "fx_source": fx_source,
            "unrealized_pnl": _text(unrealized_native),
            "unrealized_pnl_base": _text(unrealized_base if unrealized_base is not None else unrealized_native),
            "realized_pnl": None, "daily_pnl": None,
            "source": "ibkr_flex", "as_of": parsed["as_of"],
            "quality": "estimated" if fx_source == "fx_unavailable" and quantity else "settled",
        })

    return {
        "schema_version": "account_snapshot.v1",
        "source_run_id": source_run_id or parsed["source_run_id"],
        "account_alias": account_alias,
        "gateway_session_id": None,
        "as_of": parsed["as_of"], "base_currency": base_currency,
        # Not complete, and not pretending to be. This query has no equity
        # summary, so there is no NetLiquidation, margin or buying power in it.
        # The read model serves only complete runs, which is the correct outcome
        # until the Flex query grows an equity-summary section.
        "complete": False,
        "completeness": {
            "positions": True, "account_summary": False, "open_orders": False, "pnl": False,
            "session_date": parsed["session_date"],
            "note": "Flex positions query carries no equity summary; add one in Client Portal for account values.",
        },
        "account_values": [],
        "positions": rows,
        "open_orders": [],
        "flex": {
            "session_date": parsed["session_date"],
            "position_rows": len(rows),
            "untranslated_rows": untranslated,
        },
    }


def publish_flex_snapshot(
    ledger: Any, *, positions: Path, account_alias: str, url: str = "",
    cash: Path | None = None, trades: Path | None = None,
    stale_hours: int = 30, dry_run: bool = False, token: str | None = None,
) -> dict[str, Any]:
    """Ingest locally, then publish. Refuses a stale file rather than republishing it.

    Freshness is read off the file's mtime, not off this run succeeding. A
    producer that stops writing leaves a well-formed file behind, and
    republishing it forever presents a frozen book as current -- the failure
    that let a podcast catalog sit at 3,561 episodes while the page called it
    live, and the same failure the strategy publisher guards against.
    """
    import os

    if not positions.exists():
        return {"published": False, "reason": f"{positions} does not exist"}
    age = file_age_hours(positions)
    if age > stale_hours:
        return {
            "published": False,
            "reason": f"flex positions file is {age:.1f}h old (> {stale_hours}h); not republishing stale state",
            "session_date": None,
        }

    payload = build_account_snapshot(positions, account_alias=account_alias)
    result: dict[str, Any] = {
        "session_date": payload["completeness"]["session_date"],
        "position_rows": payload["flex"]["position_rows"],
        "untranslated_rows": payload["flex"]["untranslated_rows"],
        "age_hours": round(age, 2),
        "complete": payload["complete"],
        "gateway_contacted": False,
    }
    ledger.ingest_account_snapshot(payload)
    if dry_run or not url:
        result["published"] = False
        result["reason"] = "dry run" if dry_run else "no ingest url configured"
        return result
    response = publish_payload(url, token or os.environ.get("PORTFOLIO_INGEST_TOKEN", ""), payload)
    result["published"] = True
    result["response"] = response
    return result


def _fold_lots(lots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per (conid, model_code), summing the tax lots underneath it."""
    folded: dict[tuple[int, str], dict[str, Any]] = {}
    for lot in lots:
        conid = int(lot.get("conid") or 0)
        key = (conid, str(lot.get("model_code") or ""))
        target = folded.get(key)
        if target is None:
            folded[key] = dict(lot)
            continue
        for field in ("quantity", "market_value", "cost_basis", "unrealized_pnl"):
            left, right = _decimal(target.get(field)), _decimal(lot.get(field))
            if left is None and right is None:
                continue
            target[field] = _text((left or Decimal(0)) + (right or Decimal(0)))
        # mark, fx rate and identity are per-contract, not per-lot, so the first
        # lot's values already describe the position. Taking a "sum" of a price
        # would be meaningless.
    return list(folded.values())
