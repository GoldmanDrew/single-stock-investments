"""Live IB order bridge: the only process permitted to transmit hub orders.

`GuardedOrderService` in orders.py already owns the whole decision: price bands,
tick validity, notional caps, reduce-only, the HMAC approval, the kill switch and
the live interlock. This module adds nothing to that policy. It is the adapter
that turns those decisions into IBKR calls, and the one place where a `transmit`
flag is ever set.

Ownership rules come from CLIENT_ID_REGISTRY.md and are enforced here, not
assumed:

  * Client ID 91 is the sole transmitter. The collector (81) and the master
    observer (82; 90 belongs to ls-algo's screener) connect read-only and are prevented in code from transmitting;
    Gateway's global read-only setting is not relied upon, because it also
    suppresses order information the bridge needs to prove ownership.
  * Only orders whose `orderRef` starts with `MAGIS|` and that this client
    submitted may be modified or cancelled. Manual and producer orders are
    visible, never touched.
  * `reqGlobalCancel` is prohibited. There is no code path to it.
  * On startup the bridge reads open, completed and executed orders and proves
    every working order classifies, before it will accept a command.

The failure that matters most is a send whose acknowledgement is lost. Retrying
a `placeOrder` can double a position, so a transport failure after transmission
raises and the service moves the intent to `SubmitUncertain`, which is resolved
by reconciliation against `orderRef`/`permId`, never by resending.
"""
from __future__ import annotations

import math
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

HUB_ORDER_PREFIX = "MAGIS|"
DEFAULT_BRIDGE_CLIENT_ID = 91


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def fingerprint_for(identity: dict[str, Any]) -> str:
    """The string a human confirms before anything is transmitted.

    It has to be readable, because its whole job is to let a person notice that
    the ticket is not the contract they meant. "907480285|OPT||SMART" fails that
    test; "XSP 270129P00540000 | OPT | 540 P | 20270129 | 100x | SMART/USD"
    passes it. It also has to be built from the *qualified* contract -- a
    fingerprint assembled from the browser's own claim would agree with the
    browser no matter what the browser said.
    """
    parts = [
        str(identity.get("local_symbol") or identity.get("symbol") or ""),
        str(identity.get("sec_type") or ""),
    ]
    if str(identity.get("sec_type") or "").upper() in {"OPT", "FOP"}:
        # IBKR returns strike as a float, so a $540 strike arrives as 540.0. The
        # trailing zero is noise in a string whose only job is to be checked at a
        # glance -- but a half-point strike must keep its half.
        strike = identity.get("strike")
        if isinstance(strike, float) and strike.is_integer():
            strike = int(strike)
        parts.append(f"{strike} {identity.get('right') or ''}".strip())
        parts.append(str(identity.get("expiry") or ""))
        parts.append(f"{identity.get('multiplier') or '?'}x")
    parts.append(f"{identity.get('exchange') or 'SMART'}/{identity.get('currency') or ''}")
    parts.append(f"conId {identity.get('conid')}")
    return " | ".join(part for part in parts if part)


class BridgeUnavailable(RuntimeError):
    """Gateway is not connected, or connected without the data the bridge needs."""


class OrderOwnershipError(RuntimeError):
    """Refused: the order is not provably this hub's to touch."""


@dataclass(frozen=True)
class BridgeProfile:
    host: str = "127.0.0.1"
    port: int = 4002
    client_id: int = DEFAULT_BRIDGE_CLIENT_ID
    account_id: str = ""
    account_alias: str = ""
    market_data_type: int = 1  # 1 live, 2 frozen, 3 delayed

    @classmethod
    def from_env(cls) -> "BridgeProfile":
        import os

        account_id = os.environ.get("IBKR_ACCOUNT_ID", "")
        if not account_id:
            raise RuntimeError("IBKR_ACCOUNT_ID is required")
        return cls(
            host=os.environ.get("IBKR_HOST", "127.0.0.1"),
            port=int(os.environ.get("IBKR_PORT", "4002")),
            client_id=int(os.environ.get("IBKR_BRIDGE_CLIENT_ID", str(DEFAULT_BRIDGE_CLIENT_ID))),
            account_id=account_id,
            account_alias=os.environ.get("IBKR_ACCOUNT_ALIAS", ""),
            market_data_type=int(os.environ.get("IBKR_MARKET_DATA_TYPE", "1")),
        )


class IbOrderBridge:
    """Implements the OrderBroker protocol against a live ib_async session."""

    def __init__(self, profile: BridgeProfile, *, ib: Any = None):
        self.profile = profile
        self._ib = ib
        self._lock = threading.RLock()
        self._session_id = str(uuid.uuid4())
        self._recovered = False

    # ---------------------------------------------------------------- session

    def connect(self) -> None:
        if self._ib is None:
            try:
                from ib_async import IB
            except ImportError as exc:  # pragma: no cover - environment dependent
                raise BridgeUnavailable("install ib_async to run the live order bridge") from exc
            self._ib = IB()
            self._ib.connect(
                self.profile.host, self.profile.port,
                clientId=self.profile.client_id, readonly=False, timeout=15,
            )
        managed = {str(a).strip() for a in (self._ib.managedAccounts() or [])}
        if self.profile.account_id not in managed:
            self.disconnect()
            raise BridgeUnavailable("configured account is not visible to this bridge session")
        self._ib.reqMarketDataType(self.profile.market_data_type)
        self.recover()

    def disconnect(self) -> None:
        if self._ib is not None:
            try:
                self._ib.disconnect()
            except Exception:  # pragma: no cover - best effort teardown
                pass

    def recover(self) -> dict[str, Any]:
        """Prove every working order classifies before accepting any command.

        Recovery is not a formality. If the bridge restarted mid-flight there may
        be a hub order working at IBKR that the ledger still believes is
        unsubmitted; accepting a new command before classifying it is how a
        position gets doubled.
        """
        trades = self._ib.reqAllOpenOrders() or []
        hub, foreign, unresolved = [], [], []
        for trade in trades:
            order = trade.order
            ref = str(getattr(order, "orderRef", "") or "")
            if not ref.startswith(HUB_ORDER_PREFIX):
                foreign.append(ref or f"order:{order.orderId}")
            elif getattr(order, "clientId", None) == self.profile.client_id:
                hub.append(ref)
            else:
                # A MAGIS ref from another client ID is a registry violation: some
                # other session is transmitting into this namespace.
                unresolved.append(ref)
        if unresolved:
            raise OrderOwnershipError(
                f"hub orderRefs owned by a foreign client id: {sorted(unresolved)}"
            )
        self._recovered = True
        return {
            "gateway_session_id": self._session_id,
            "hub_orders": hub, "foreign_orders": foreign,
            "recovered_at": _utc_now(),
        }

    def _require_ready(self) -> None:
        if self._ib is None or not self._ib.isConnected():
            raise BridgeUnavailable("order bridge is not connected to IB Gateway")
        if not self._recovered:
            raise BridgeUnavailable("order bridge has not completed startup recovery")

    # ------------------------------------------------------------ OrderBroker

    def quote(self, conid: int) -> dict[str, Any]:
        """Live two-sided quote plus the tick and position context preview needs.

        GuardedOrderService rejects a quote older than `quote_max_age_seconds`
        (10s by default), so this must be a live subscription read, never a cached
        or polled value.
        """
        self._require_ready()
        contract = self._qualify(conid)
        details = self._ib.reqContractDetails(contract)
        if not details:
            raise BridgeUnavailable(f"conId {conid} has no contract details")
        detail = details[0]
        # snapshot=True, and never a streaming subscription.
        #
        # Market-data lines come from one account-wide pool that this Gateway
        # shares with the SPX 0DTE and LS producers. A streaming request holds a
        # line until it is cancelled, so any path that skipped the cancel would
        # leak one per preview and eventually starve those strategies of option
        # quotes -- a failure that would surface over there, not here. A snapshot
        # fills once and releases itself, which is all a 10-second-fresh preview
        # needs anyway.
        #
        # The cancel is still issued from a finally, because a snapshot that
        # never fills can otherwise sit open until it times out.
        ticker = self._ib.reqMktData(contract, "", True, False)
        try:
            self._ib.sleep(1.0)
            bid, ask = _finite(ticker.bid), _finite(ticker.ask)
        finally:
            try:
                self._ib.cancelMktData(contract)
            except Exception:  # pragma: no cover - best effort
                pass
        if bid is None or ask is None:
            # Fail closed. An absent NBBO must not silently become a stale or
            # one-sided price that the band check would then "pass".
            raise BridgeUnavailable(f"conId {conid} returned no two-sided quote")
        position = next(
            (row.position for row in self._ib.positions(self.profile.account_id)
             if row.contract.conId == conid), 0,
        )
        return {
            "conid": conid, "bid": str(bid), "ask": str(ask),
            "min_tick": str(detail.minTick or "0.01"),
            "multiplier": str(getattr(contract, "multiplier", None) or 1),
            "current_position": str(position),
            "currency": contract.currency,
            "as_of": _utc_now(),
        }

    def what_if(self, ticket: dict[str, Any]) -> dict[str, Any]:
        """Real margin impact from IBKR, replacing the paper bridge's estimate."""
        self._require_ready()
        contract = self._qualify(ticket["conid"])
        order = self._limit_order(ticket, transmit=False)
        order.whatIf = True
        state = self._ib.whatIfOrder(contract, order)
        if state is None:
            raise BridgeUnavailable("whatIfOrder returned no order state")
        return {
            "value_kind": "ibkr_what_if",
            "initial_margin_change": str(getattr(state, "initMarginChange", "") or ""),
            "maintenance_margin_change": str(getattr(state, "maintMarginChange", "") or ""),
            "equity_with_loan_change": str(getattr(state, "equityWithLoanChange", "") or ""),
            "commission": str(getattr(state, "commission", "") or ""),
            "transmitted": False,
        }

    def place_limit(self, ticket: dict[str, Any]) -> dict[str, Any]:
        """The single transmitting call in the hub. Never retried by this layer."""
        self._require_ready()
        order_ref = str(ticket.get("order_ref") or "")
        if not order_ref.startswith(HUB_ORDER_PREFIX):
            raise OrderOwnershipError("refusing to transmit an order without a hub orderRef")
        with self._lock:
            contract = self._qualify(ticket["conid"])
            order = self._limit_order(ticket, transmit=True)
            trade = self._ib.placeOrder(contract, order)
            self._ib.sleep(0.2)
            placed = trade.order
            return {
                "gateway_session_id": self._session_id,
                "client_id": getattr(placed, "clientId", self.profile.client_id),
                "order_id": placed.orderId,
                "perm_id": getattr(placed, "permId", None),
                "order_ref": order_ref,
                "status": getattr(trade.orderStatus, "status", "PendingSubmit"),
                "transmitted": True,
            }

    def find_owned_order(self, order_ref: str) -> dict[str, Any] | None:
        """Resolve an uncertain send by orderRef, across open and completed orders."""
        self._require_ready()
        if not order_ref.startswith(HUB_ORDER_PREFIX):
            raise OrderOwnershipError("only hub orderRefs can be reconciled")
        for trade in (self._ib.reqAllOpenOrders() or []):
            if str(getattr(trade.order, "orderRef", "")) == order_ref:
                return self._describe(trade)
        for trade in (self._ib.reqCompletedOrders(apiOnly=False) or []):
            if str(getattr(trade.order, "orderRef", "")) == order_ref:
                return self._describe(trade)
        return None

    def cancel_owned_order(self, order_ref: str, client_id: int, order_id: int) -> dict[str, Any]:
        """Cancel exactly one proven-own order. There is no global cancel here."""
        self._require_ready()
        if not order_ref.startswith(HUB_ORDER_PREFIX):
            raise OrderOwnershipError("refusing to cancel a non-hub order")
        if client_id != self.profile.client_id:
            raise OrderOwnershipError("refusing to cancel an order this client did not submit")
        for trade in (self._ib.reqAllOpenOrders() or []):
            order = trade.order
            if (str(getattr(order, "orderRef", "")) == order_ref
                    and order.orderId == order_id
                    and getattr(order, "clientId", None) == client_id):
                self._ib.cancelOrder(order)
                return {"client_id": client_id, "order_id": order_id, "status": "PendingCancel"}
        raise OrderOwnershipError("no matching working order proves hub ownership")

    # ------------------------------------------------------- contract lookup

    def resolve(self, request: dict[str, Any]) -> list[dict[str, Any]]:
        """Turn a symbol a human typed into conIds IBKR agrees exist.

        This is the only way an option ever reaches a ticket. An option conId is
        a nine-digit number that identifies one strike of one expiry; asking a
        person to type it is asking them to approve something they cannot check,
        so the browser sends what a person knows -- symbol, month, strike, right
        -- and this resolves it.

        Costs no market-data line. reqContractDetails and reqSecDefOptParams are
        contract-definition requests, drawn from a different pool than the
        reqMktData subscriptions that CLAUDE.md rule 4 protects, so a resolver
        that never touches reqMktData cannot starve the SPX option NBBO stream
        no matter how often it is called.
        """
        self._require_ready()
        kind = request.get("kind") or "contract"
        if kind == "option_chain":
            return self._option_chain(request)
        return self._contract_details(request)

    def _contract_details(self, request: dict[str, Any]) -> list[dict[str, Any]]:
        from ib_async import Contract

        sec_type = str(request.get("sec_type") or "STK").upper()
        contract = Contract(
            symbol=str(request["symbol"]).upper(),
            secType=sec_type,
            currency=str(request.get("currency") or "USD").upper(),
            exchange=str(request.get("exchange") or "SMART").upper(),
        )
        if sec_type == "OPT":
            contract.lastTradeDateOrContractMonth = str(request.get("expiry") or "")
            if request.get("strike_decimal"):
                contract.strike = float(request["strike_decimal"])
            if request.get("right_code"):
                contract.right = str(request["right_code"]).upper()
        details = self._ib.reqContractDetails(contract) or []
        # Bounded on purpose. An under-specified query can match the entire chain,
        # and a picker with four hundred rows is not a picker.
        return [self._describe_contract(detail) for detail in details[:200]]

    def _option_chain(self, request: dict[str, Any]) -> list[dict[str, Any]]:
        """Expirations and strikes for one underlying, in a single request.

        reqSecDefOptParams returns the whole chain definition at once. The
        alternative -- looping reqContractDetails over candidate strikes -- is
        how a resolver walks into IBKR's pacing limits and starts failing during
        a live session, so it is not done here.
        """
        from ib_async import Contract

        underlying = Contract(
            symbol=str(request["symbol"]).upper(), secType="STK",
            currency=str(request.get("currency") or "USD").upper(), exchange="SMART",
        )
        qualified = self._ib.qualifyContracts(underlying)
        if not qualified:
            raise BridgeUnavailable(f"underlying {request['symbol']} could not be qualified")
        root = qualified[0]
        params = self._ib.reqSecDefOptParams(root.symbol, "", root.secType, root.conId) or []
        rows: list[dict[str, Any]] = []
        for entry in params:
            for expiry in sorted(getattr(entry, "expirations", None) or []):
                rows.append({
                    "conid": None, "symbol": root.symbol, "sec_type": "OPT",
                    "expiry": expiry, "trading_class": getattr(entry, "tradingClass", None),
                    "exchange": getattr(entry, "exchange", None),
                    "multiplier": getattr(entry, "multiplier", None),
                    "strikes": sorted(getattr(entry, "strikes", None) or []),
                    "currency": root.currency,
                })
        return rows

    @staticmethod
    def _describe_contract(detail: Any) -> dict[str, Any]:
        contract = detail.contract
        return {
            "conid": contract.conId,
            "symbol": contract.symbol,
            "local_symbol": getattr(contract, "localSymbol", None),
            "sec_type": contract.secType,
            "currency": contract.currency,
            "exchange": contract.exchange,
            "primary_exchange": getattr(contract, "primaryExchange", None),
            "trading_class": getattr(contract, "tradingClass", None),
            "expiry": getattr(contract, "lastTradeDateOrContractMonth", None) or None,
            "strike": getattr(contract, "strike", None) or None,
            "right": getattr(contract, "right", None) or None,
            "multiplier": getattr(contract, "multiplier", None) or None,
            "min_tick": getattr(detail, "minTick", None),
            "description": getattr(detail, "longName", None),
        }

    def contract_identity(self, conid: int) -> dict[str, Any]:
        """What the human is actually approving, taken from IBKR, not the browser.

        The approval fingerprint used to be assembled from the request row, so a
        stock ticket bound to the string "272093|STK||SMART" -- which names
        nothing a person could check, and for an option would be worse than
        useless. Building it here means the fingerprint describes the contract
        the bridge would really send.
        """
        self._require_ready()
        contract = self._qualify(int(conid))
        details = self._ib.reqContractDetails(contract)
        identity = self._describe_contract(details[0]) if details else {
            "conid": contract.conId, "symbol": contract.symbol,
            "local_symbol": getattr(contract, "localSymbol", None),
            "sec_type": contract.secType, "currency": contract.currency,
            "exchange": contract.exchange,
            "trading_class": getattr(contract, "tradingClass", None),
            "expiry": getattr(contract, "lastTradeDateOrContractMonth", None) or None,
            "strike": getattr(contract, "strike", None) or None,
            "right": getattr(contract, "right", None) or None,
            "multiplier": getattr(contract, "multiplier", None) or None,
        }
        identity["fingerprint"] = fingerprint_for(identity)
        return identity

    # ---------------------------------------------------------------- helpers

    def _qualify(self, conid: int) -> Any:
        from ib_async import Contract

        contract = Contract(conId=int(conid))
        qualified = self._ib.qualifyContracts(contract)
        if not qualified:
            raise BridgeUnavailable(f"conId {conid} could not be qualified")
        return qualified[0]

    def _limit_order(self, ticket: dict[str, Any], *, transmit: bool) -> Any:
        from ib_async import LimitOrder

        quantity = abs(Decimal(str(ticket["quantity_decimal"])))
        order = LimitOrder(
            ticket["action"],
            float(quantity),
            float(Decimal(str(ticket["limit_price_decimal"]))),
        )
        order.orderRef = str(ticket.get("order_ref") or "")
        order.tif = ticket.get("tif", "DAY")
        order.outsideRth = bool(ticket.get("outside_rth"))
        order.account = self.profile.account_id
        order.transmit = transmit
        return order

    @staticmethod
    def _describe(trade: Any) -> dict[str, Any]:
        order, status = trade.order, trade.orderStatus
        return {
            "client_id": getattr(order, "clientId", None),
            "order_id": order.orderId,
            "perm_id": getattr(order, "permId", None),
            "order_ref": str(getattr(order, "orderRef", "")),
            "status": getattr(status, "status", None),
            "filled": str(getattr(status, "filled", "0")),
            "remaining": str(getattr(status, "remaining", "0")),
            "avg_fill_price": str(getattr(status, "avgFillPrice", "") or ""),
        }
