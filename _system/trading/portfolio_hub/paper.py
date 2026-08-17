from __future__ import annotations

import itertools
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable


class PaperOrderBroker:
    """Deterministic paper bridge for drills and Python-client integration tests."""

    def __init__(self, quote_provider: Callable[[int], dict[str, Any]], *, client_id: int = 91):
        self.quote_provider = quote_provider
        self.client_id = client_id
        self._ids = itertools.count(1_000)
        self._orders: dict[str, dict[str, Any]] = {}

    def quote(self, conid: int) -> dict[str, Any]:
        quote = deepcopy(self.quote_provider(conid))
        quote.setdefault("as_of", datetime.now(timezone.utc).isoformat())
        quote.setdefault("multiplier", "1")
        quote.setdefault("min_tick", "0.01")
        quote.setdefault("current_position", "0")
        return quote

    def what_if(self, ticket: dict[str, Any]) -> dict[str, Any]:
        notional = Decimal(ticket["quantity_decimal"]) * Decimal(ticket["limit_price_decimal"])
        return {
            "value_kind": "paper_estimate", "initial_margin_change": str(abs(notional) * Decimal("0.50")),
            "maintenance_margin_change": str(abs(notional) * Decimal("0.30")), "commission": "1.00",
            "transmitted": False,
        }

    def place_limit(self, ticket: dict[str, Any]) -> dict[str, Any]:
        order_id = next(self._ids)
        result = {"gateway_session_id": "paper-session", "client_id": self.client_id, "order_id": order_id, "perm_id": order_id + 1_000_000, "status": "Submitted"}
        self._orders[ticket["order_ref"]] = {**deepcopy(ticket), **result}
        return result

    def find_owned_order(self, order_ref: str) -> dict[str, Any] | None:
        return deepcopy(self._orders.get(order_ref))

    def cancel_owned_order(self, order_ref: str, client_id: int, order_id: int) -> dict[str, Any]:
        order = self._orders.get(order_ref)
        if not order or order["client_id"] != client_id or order["order_id"] != order_id:
            raise ValueError("paper order ownership mismatch")
        order["status"] = "PendingCancel"
        return {"client_id": client_id, "order_id": order_id, "status": "PendingCancel"}
