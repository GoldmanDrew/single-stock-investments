from __future__ import annotations

import itertools
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable


class PaperOrderBroker:
    """Deterministic paper bridge for drills and Python-client integration tests."""

    # Nothing here reaches IBKR, and the policy layer relies on being told so.
    transmits = False

    def __init__(self, quote_provider: Callable[[int], dict[str, Any]], *, client_id: int = 91,
                 contracts: dict[int, dict[str, Any]] | None = None):
        self.quote_provider = quote_provider
        self.client_id = client_id
        # Known contract identities for drills; anything absent resolves to a
        # generic stock rather than raising, because a paper run must not depend
        # on a fixture the caller did not know to supply.
        self.contracts = dict(contracts or {})
        self._ids = itertools.count(1_000)
        self._orders: dict[str, dict[str, Any]] = {}

    def quote(self, conid: int) -> dict[str, Any]:
        quote = deepcopy(self.quote_provider(conid))
        quote.setdefault("as_of", datetime.now(timezone.utc).isoformat())
        quote.setdefault("multiplier", "1")
        quote.setdefault("min_tick", "0.01")
        quote.setdefault("current_position", "0")
        return quote

    def resolve(self, request: dict[str, Any]) -> list[dict[str, Any]]:
        """Deterministic stand-in so a drill exercises the resolver path too."""
        symbol = str(request.get("symbol") or "").upper()
        sec_type = str(request.get("sec_type") or "STK").upper()
        conid = 900_000 + (abs(hash((symbol, sec_type, request.get("expiry"), request.get("strike_decimal"), request.get("right_code")))) % 90_000)
        return [{
            "conid": conid, "symbol": symbol, "sec_type": sec_type,
            "local_symbol": symbol, "currency": request.get("currency") or "USD",
            "exchange": request.get("exchange") or "SMART",
            "expiry": request.get("expiry"), "strike": request.get("strike_decimal"),
            "right": request.get("right_code"),
            "multiplier": "100" if sec_type == "OPT" else "1",
        }]

    def contract_identity(self, conid: int) -> dict[str, Any]:
        from .ib_bridge import fingerprint_for

        identity = dict(self.contracts.get(int(conid)) or {
            "conid": int(conid), "symbol": f"PAPER{conid}", "sec_type": "STK",
            "currency": "USD", "exchange": "SMART", "multiplier": "1",
        })
        identity["conid"] = int(conid)
        identity["fingerprint"] = fingerprint_for(identity)
        return identity

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


class PaperRoutedBroker:
    """Live prices and live margin, with no route to the exchange.

    The paper desk is only worth having if its numbers are real: a preview
    priced off a simulated book teaches nothing, and the whole point of the
    guarded workflow -- price bands, tick validity, IBKR's own margin answer --
    depends on the quote being the real NBBO.

    So the read paths go to the live bridge and the write paths go to the paper
    ledger. `resolve`, `contract_identity`, `quote` and `what_if` are all
    read-only at IBKR (`quote` uses a self-cancelling snapshot, never a
    streaming line; `what_if` sets whatIf=True and transmit=False), while
    `place_limit` and `cancel_owned_order` never leave this process.

    This is what a bridge should be started with. Routing live is a separate,
    deliberate act -- see cli.py's `--route`.
    """

    transmits = False

    def __init__(self, live: Any, paper: PaperOrderBroker):
        self.live = live
        self.paper = paper

    # -- read: the real broker, because the numbers have to be real ----------
    def resolve(self, request: dict[str, Any]) -> list[dict[str, Any]]:
        return self.live.resolve(request)

    def contract_identity(self, conid: int) -> dict[str, Any]:
        return self.live.contract_identity(conid)

    def quote(self, conid: int) -> dict[str, Any]:
        return self.live.quote(conid)

    def what_if(self, ticket: dict[str, Any]) -> dict[str, Any]:
        return self.live.what_if(ticket)

    # -- write: never the real broker ---------------------------------------
    def place_limit(self, ticket: dict[str, Any]) -> dict[str, Any]:
        return self.paper.place_limit(ticket)

    def find_owned_order(self, order_ref: str) -> dict[str, Any] | None:
        return self.paper.find_owned_order(order_ref)

    def cancel_owned_order(self, order_ref: str, client_id: int, order_id: int) -> dict[str, Any]:
        return self.paper.cancel_owned_order(order_ref, client_id, order_id)
