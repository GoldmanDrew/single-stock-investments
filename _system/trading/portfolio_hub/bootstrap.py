from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any


def build_bootstrap_plan(*, broker_positions: list[dict[str, Any]], local_tags: dict[str, Any], hosted_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Create a review artifact; never guesses when a ticker maps to multiple broker contracts."""
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in broker_positions:
        by_symbol[str(row.get("symbol") or "").upper()].append(row)
    owner_by_symbol: dict[str, set[str]] = defaultdict(set)
    raw_tags = local_tags.get("tags") if isinstance(local_tags.get("tags"), dict) else local_tags
    for key, value in (raw_tags or {}).items():
        owner = str(value.get("owner") if isinstance(value, dict) else value).lower()
        if owner in {"drew", "michael"}:
            owner_by_symbol[str(key).upper()].add(owner)
    for row in hosted_rows:
        owner = str(row.get("owner") or "").lower(); symbol = str(row.get("ticker") or row.get("symbol") or "").upper()
        if owner in {"drew", "michael"} and symbol:
            owner_by_symbol[symbol].add(owner)
    proposed, conflicts, unresolved = [], [], []
    for symbol, owners in sorted(owner_by_symbol.items()):
        matches = by_symbol.get(symbol, [])
        if len(owners) != 1:
            conflicts.append({"symbol": symbol, "reason": "owner_conflict", "owners": sorted(owners)})
        elif len(matches) != 1:
            unresolved.append({"symbol": symbol, "reason": "ambiguous_or_missing_contract", "candidate_conids": [row.get("conid") for row in matches]})
        else:
            row = matches[0]
            proposed.append({
                "bootstrap_id": str(uuid.uuid4()), "account_alias": row["account_alias"], "conid": row["conid"],
                "model_code": row.get("model_code") or "", "symbol": symbol, "owner": next(iter(owners)),
                "strategy": "single_stock", "bucket": None, "quantity": row["quantity"],
                "confidence": "legacy_inferred", "approved": False,
            })
    return {"schema_version": "allocation_bootstrap_review.v1", "proposed": proposed, "conflicts": conflicts, "unresolved": unresolved}


def apply_approved_bootstrap(ledger, review: dict[str, Any], *, effective_at: str) -> list[str]:
    created = []
    for row in review.get("proposed") or []:
        if not row.get("approved"):
            continue
        created.append(ledger.add_allocation(
            account_alias=row["account_alias"], conid=int(row["conid"]), model_code=row.get("model_code") or "",
            owner=row["owner"], strategy=row["strategy"], bucket=row.get("bucket"), quantity=row["quantity"],
            confidence="legacy_inferred", effective_at=effective_at, source_event_id=row["bootstrap_id"],
            note="reviewed legacy allocation bootstrap",
        ))
    return created
