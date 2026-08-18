from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any


OWNERS = {"drew", "michael"}
STRATEGIES = {"single_stock", "spx_0dte", "letf", "cash", "other"}
BUCKETS = {"b1", "b2", "b3", "b4", "b5"}


def _tag_map(local_tags: dict[str, Any]) -> dict[str, Any]:
    return local_tags.get("tags") if isinstance(local_tags.get("tags"), dict) else local_tags or {}


def _owner_from(value: Any) -> str | None:
    owner = str(value.get("owner") if isinstance(value, dict) else value).lower()
    return owner if owner in OWNERS else None


def _strategy_from(value: Any, symbol: str) -> tuple[str, str | None]:
    if isinstance(value, dict):
        strategy = str(value.get("strategy") or "").lower()
        bucket = str(value.get("bucket") or "").lower() or None
        if strategy in STRATEGIES:
            return strategy, bucket if bucket in BUCKETS else None
        if bucket in BUCKETS:
            return "letf", bucket
    upper = symbol.upper()
    if upper in {"SPX", "SPXW"} or upper.startswith("SPXW"):
        return "spx_0dte", None
    return "single_stock", None


def _producer_hints(producer_rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    hints: dict[int, dict[str, Any]] = {}
    for row in producer_rows:
        try:
            conid = int(row.get("conid"))
        except (TypeError, ValueError):
            continue
        strategy = str(row.get("strategy") or "").lower()
        bucket = str(row.get("bucket") or "").lower() or None
        if strategy == "leveraged_etf":
            strategy = "letf"
        if strategy in STRATEGIES:
            hints[conid] = {"strategy": strategy, "bucket": bucket if bucket in BUCKETS else None, "producer": row.get("producer")}
    return hints


def build_bootstrap_plan(
    *,
    broker_positions: list[dict[str, Any]],
    local_tags: dict[str, Any],
    hosted_rows: list[dict[str, Any]],
    cash_balances: list[dict[str, Any]] | None = None,
    producer_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create a review artifact; never guesses when a ticker maps to multiple broker contracts."""
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_conid: dict[tuple[str, int, str], dict[str, Any]] = {}
    for row in broker_positions:
        by_symbol[str(row.get("symbol") or "").upper()].append(row)
        key = (str(row["account_alias"]), int(row["conid"]), str(row.get("model_code") or ""))
        by_conid[key] = row
    owner_by_symbol: dict[str, set[str]] = defaultdict(set)
    tag_meta: dict[str, Any] = {}
    for key, value in _tag_map(local_tags).items():
        symbol = str(key).upper()
        owner = _owner_from(value)
        if owner:
            owner_by_symbol[symbol].add(owner)
            tag_meta[symbol] = value
    for row in hosted_rows:
        owner = str(row.get("owner") or "").lower()
        symbol = str(row.get("ticker") or row.get("symbol") or "").upper()
        if owner in OWNERS and symbol:
            owner_by_symbol[symbol].add(owner)
            tag_meta.setdefault(symbol, row)
    producer_by_conid = _producer_hints(producer_rows or [])
    proposed, conflicts, unresolved, quarantined = [], [], [], []
    matched_keys: set[tuple[str, int, str]] = set()
    seen_symbols: set[str] = set()
    for symbol, owners in sorted(owner_by_symbol.items()):
        matches = by_symbol.get(symbol, [])
        seen_symbols.add(symbol)
        if len(owners) != 1:
            item = {"symbol": symbol, "reason": "owner_conflict", "owners": sorted(owners), "quarantined": True}
            conflicts.append(item)
            quarantined.append(item)
            continue
        if len(matches) != 1:
            item = {
                "symbol": symbol, "reason": "ambiguous_or_missing_contract",
                "candidate_conids": [row.get("conid") for row in matches], "quarantined": True,
            }
            unresolved.append(item)
            quarantined.append(item)
            continue
        row = matches[0]
        key = (str(row["account_alias"]), int(row["conid"]), str(row.get("model_code") or ""))
        matched_keys.add(key)
        hint = producer_by_conid.get(int(row["conid"])) or {}
        strategy, bucket = _strategy_from(tag_meta.get(symbol), symbol)
        if hint:
            strategy = hint["strategy"]
            bucket = hint.get("bucket")
        proposed.append({
            "bootstrap_id": str(uuid.uuid4()), "account_alias": row["account_alias"], "conid": row["conid"],
            "model_code": row.get("model_code") or "", "symbol": symbol, "owner": next(iter(owners)),
            "strategy": strategy, "bucket": bucket, "quantity": row["quantity"],
            "confidence": "legacy_inferred", "approved": False,
        })
    for key, row in sorted(by_conid.items()):
        symbol = str(row.get("symbol") or "").upper()
        if key in matched_keys or symbol in seen_symbols:
            continue
        hint = producer_by_conid.get(int(row["conid"])) or {}
        strategy, bucket = hint.get("strategy") or "unallocated", hint.get("bucket")
        item = {
            "account_alias": row["account_alias"], "conid": row["conid"], "model_code": row.get("model_code") or "",
            "symbol": symbol, "quantity": row["quantity"], "owner": "unallocated",
            "strategy": strategy if strategy in STRATEGIES else "unallocated", "bucket": bucket,
            "reason": "no_unique_owner_evidence", "quarantined": True,
        }
        unresolved.append(item)
        quarantined.append(item)
    cash_events = []
    quarantined_cash = []
    for cash in cash_balances or []:
        event = {
            "bootstrap_id": str(uuid.uuid4()),
            "account_alias": cash["account_alias"],
            "currency": cash.get("currency") or "USD",
            "amount": str(cash.get("amount") or cash.get("quantity") or "0"),
            "event_type": cash.get("event_type") or "opening_capital",
            "owner": "unallocated",
            "strategy": "cash",
            "approved": False,
            "quarantined": True,
            "reason": "cash_requires_explicit_owner_approval",
        }
        cash_events.append(event)
        quarantined_cash.append(event)
    return {
        "schema_version": "allocation_bootstrap_review.v1",
        "proposed": proposed,
        "conflicts": conflicts,
        "unresolved": unresolved,
        "quarantined": quarantined,
        "cash_events": cash_events,
        "quarantined_cash": quarantined_cash,
    }


def apply_approved_bootstrap(ledger, review: dict[str, Any], *, effective_at: str) -> dict[str, list[str]]:
    created_lots: list[str] = []
    created_cash: list[str] = []
    for row in review.get("proposed") or []:
        if not row.get("approved"):
            continue
        created_lots.append(ledger.add_allocation(
            account_alias=row["account_alias"], conid=int(row["conid"]), model_code=row.get("model_code") or "",
            owner=row["owner"], strategy=row["strategy"], bucket=row.get("bucket"), quantity=row["quantity"],
            confidence="legacy_inferred", effective_at=effective_at, source_event_id=row["bootstrap_id"],
            note="reviewed legacy allocation bootstrap",
        ))
    for row in review.get("cash_events") or []:
        if not row.get("approved"):
            continue
        created_cash.append(ledger.add_cash_event(
            account_alias=row["account_alias"], owner=row["owner"], strategy=row.get("strategy") or "cash",
            currency=row["currency"], amount=row["amount"], event_type=row.get("event_type") or "opening_capital",
            effective_at=effective_at, source="bootstrap",             source_event_id=row["bootstrap_id"],
        ))
    return {"allocations": created_lots, "cash_events": created_cash}
