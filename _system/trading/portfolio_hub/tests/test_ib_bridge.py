from __future__ import annotations

import sys
import types
from decimal import Decimal

import pytest

from _system.trading.portfolio_hub.ib_bridge import (
    DEFAULT_BRIDGE_CLIENT_ID,
    BridgeProfile,
    BridgeUnavailable,
    IbOrderBridge,
    OrderOwnershipError,
)


# ib_async is not installed in CI; the bridge only imports it lazily inside the
# calls that build contracts and orders, so a tiny stub covers those paths.
class _Contract:
    def __init__(self, conId=0, **kw):
        self.conId, self.currency, self.multiplier = conId, "USD", None
        for k, v in kw.items():
            setattr(self, k, v)


class _LimitOrder:
    def __init__(self, action, quantity, price):
        self.action, self.totalQuantity, self.lmtPrice = action, quantity, price
        self.orderId, self.clientId, self.permId = 5001, 91, 900001
        self.orderRef, self.tif, self.outsideRth = "", "DAY", False
        self.account, self.transmit, self.whatIf = "", False, False


@pytest.fixture(autouse=True)
def _stub_ib_async(monkeypatch):
    module = types.ModuleType("ib_async")
    module.Contract = _Contract
    module.LimitOrder = _LimitOrder
    module.IB = object
    monkeypatch.setitem(sys.modules, "ib_async", module)
    return module


class FakeStatus:
    def __init__(self, status="Submitted", filled="0", remaining="10"):
        self.status, self.filled, self.remaining, self.avgFillPrice = status, filled, remaining, 0.0


class FakeTrade:
    def __init__(self, order, status=None):
        self.order, self.orderStatus, self.contract = order, status or FakeStatus(), _Contract(101)


class FakeOrder:
    def __init__(self, order_ref="", client_id=91, order_id=5001):
        self.orderRef, self.clientId, self.orderId, self.permId = order_ref, client_id, order_id, 900001


class FakeTicker:
    def __init__(self, bid=25.39, ask=25.41):
        self.bid, self.ask = bid, ask


class FakePosition:
    def __init__(self, conid, position):
        self.contract, self.position = _Contract(conid), position


class FakeIB:
    def __init__(self, *, open_orders=None, completed=None, ticker=None, positions=None):
        self._open = open_orders if open_orders is not None else []
        self._completed = completed or []
        self._ticker = ticker if ticker is not None else FakeTicker()
        self._positions = positions or []
        self.placed, self.cancelled, self.global_cancels = [], [], 0
        self.market_data_type = None

    def isConnected(self): return True
    def managedAccounts(self): return ["U123"]
    def reqMarketDataType(self, kind): self.market_data_type = kind
    def reqAllOpenOrders(self): return self._open
    def reqCompletedOrders(self, apiOnly=False): return self._completed
    def qualifyContracts(self, contract): return [_Contract(getattr(contract, "conId", 0) or 101, symbol=getattr(contract, "symbol", "MSFT"), secType=getattr(contract, "secType", "STK"))]

    def reqContractDetails(self, contract):
        # Contract details carry the contract itself; quote() reads minTick off
        # the detail while the resolver reads identity off detail.contract.
        resolved = _Contract(
            getattr(contract, "conId", 0) or 101,
            symbol=getattr(contract, "symbol", "MSFT"),
            secType=getattr(contract, "secType", "STK"),
            localSymbol=getattr(contract, "localSymbol", None) or getattr(contract, "symbol", "MSFT"),
            exchange=getattr(contract, "exchange", "SMART"),
            lastTradeDateOrContractMonth=getattr(contract, "lastTradeDateOrContractMonth", ""),
            strike=getattr(contract, "strike", 0.0),
            right=getattr(contract, "right", ""),
        )
        return [types.SimpleNamespace(minTick=0.01, contract=resolved, longName="Test Contract")]

    def reqSecDefOptParams(self, symbol, exchange, sec_type, conid):
        return [types.SimpleNamespace(
            tradingClass=symbol, exchange="SMART", multiplier="100",
            expirations={"20270129", "20260918"}, strikes={520.0, 540.0, 620.0},
        )]
    def reqMktData(self, *a, **kw): return self._ticker
    def cancelMktData(self, contract): pass
    def positions(self, account=None): return self._positions
    def sleep(self, seconds): pass
    def whatIfOrder(self, contract, order):
        return types.SimpleNamespace(
            initMarginChange="1250.00", maintMarginChange="750.00",
            equityWithLoanChange="-1.00", commission="1.00",
        )

    def placeOrder(self, contract, order):
        self.placed.append(order)
        return FakeTrade(order)

    def cancelOrder(self, order): self.cancelled.append(order)
    def reqGlobalCancel(self): self.global_cancels += 1  # must never be called
    def disconnect(self): pass


def bridge(ib, *, recovered=True):
    b = IbOrderBridge(BridgeProfile(account_id="U123", account_alias="primary"), ib=ib)
    if recovered:
        b.recover()
    return b


def ticket(**overrides):
    base = {
        "conid": 101, "action": "BUY", "quantity_decimal": "10",
        "limit_price_decimal": "25.40", "tif": "DAY", "outside_rth": False,
        "order_ref": "MAGIS|single_stock|drew|abc-123",
    }
    return {**base, **overrides}


def test_recovery_refuses_hub_orderrefs_owned_by_another_client():
    # A MAGIS ref from a client id that is not the bridge means a second session is
    # transmitting into the hub namespace; commands must not be accepted.
    ib = FakeIB(open_orders=[FakeTrade(FakeOrder("MAGIS|single_stock|drew|x", client_id=77))])
    with pytest.raises(OrderOwnershipError):
        bridge(ib, recovered=False).recover()


def test_recovery_classifies_hub_and_foreign_orders():
    ib = FakeIB(open_orders=[
        FakeTrade(FakeOrder("MAGIS|single_stock|drew|x", client_id=91)),
        FakeTrade(FakeOrder("", client_id=0, order_id=7)),
    ])
    result = bridge(ib, recovered=False).recover()
    assert result["hub_orders"] == ["MAGIS|single_stock|drew|x"]
    assert result["foreign_orders"] == ["order:7"]


def test_commands_are_refused_before_recovery_completes():
    with pytest.raises(BridgeUnavailable):
        bridge(FakeIB(), recovered=False).quote(101)


def test_quote_reports_live_nbbo_tick_and_position():
    ib = FakeIB(positions=[FakePosition(101, 25)])
    quote = bridge(ib).quote(101)
    assert (quote["bid"], quote["ask"]) == ("25.39", "25.41")
    assert quote["min_tick"] == "0.01"
    assert quote["current_position"] == "25"
    assert quote["as_of"].endswith("Z")


def test_quote_fails_closed_without_a_two_sided_market():
    # A missing side must raise, not degrade into a one-sided price that the
    # price-band check would then happily accept.
    ib = FakeIB(ticker=FakeTicker(bid=float("nan"), ask=25.41))
    with pytest.raises(BridgeUnavailable):
        bridge(ib).quote(101)


def test_what_if_returns_broker_margin_not_an_estimate():
    preview = bridge(FakeIB()).what_if(ticket())
    assert preview["value_kind"] == "ibkr_what_if"
    assert preview["initial_margin_change"] == "1250.00"
    assert preview["transmitted"] is False


def test_place_limit_stamps_the_hub_orderref_and_transmits():
    ib = FakeIB()
    result = bridge(ib).place_limit(ticket())
    assert result["transmitted"] is True
    assert result["order_ref"] == "MAGIS|single_stock|drew|abc-123"
    assert ib.placed[0].transmit is True
    assert ib.placed[0].orderRef == "MAGIS|single_stock|drew|abc-123"
    assert ib.placed[0].account == "U123"


def test_place_limit_refuses_an_order_without_a_hub_orderref():
    ib = FakeIB()
    with pytest.raises(OrderOwnershipError):
        bridge(ib).place_limit(ticket(order_ref="manual-123"))
    assert ib.placed == []


def test_cancel_requires_proven_ownership():
    ref = "MAGIS|single_stock|drew|abc-123"
    ib = FakeIB(open_orders=[FakeTrade(FakeOrder(ref, client_id=91, order_id=5001))])
    b = bridge(ib)

    with pytest.raises(OrderOwnershipError):
        b.cancel_owned_order("manual-1", 91, 5001)          # not a hub ref
    with pytest.raises(OrderOwnershipError):
        b.cancel_owned_order(ref, 77, 5001)                 # another client's order
    with pytest.raises(OrderOwnershipError):
        b.cancel_owned_order(ref, 91, 9999)                 # no matching working order
    assert ib.cancelled == []

    assert b.cancel_owned_order(ref, 91, 5001)["status"] == "PendingCancel"
    assert len(ib.cancelled) == 1
    assert ib.global_cancels == 0


def test_uncertain_send_is_resolved_by_orderref_across_open_and_completed():
    ref = "MAGIS|single_stock|drew|abc-123"
    completed = FakeTrade(FakeOrder(ref), FakeStatus("Filled", filled="10", remaining="0"))
    b = bridge(FakeIB(completed=[completed]))
    found = b.find_owned_order(ref)
    assert found["status"] == "Filled" and found["filled"] == "10"
    assert b.find_owned_order("MAGIS|single_stock|drew|missing") is None


def test_bridge_never_calls_global_cancel():
    # reqGlobalCancel would cancel manual and producer orders the hub does not own,
    # so no call site may exist. The prose ban in the module docstring is allowed;
    # an actual invocation is not.
    import inspect
    import re

    from _system.trading.portfolio_hub import ib_bridge

    assert not hasattr(IbOrderBridge, "cancel_all")
    assert not re.search(r"\.reqGlobalCancel\s*\(", inspect.getsource(ib_bridge))


def test_a_lost_acknowledgement_is_never_retried_by_the_bridge():
    """Transport failure after placeOrder must surface, not resend.

    GuardedOrderService moves the intent to SubmitUncertain and resolves it by
    reconciliation; a retry here could double the position.
    """
    class ExplodingIB(FakeIB):
        def placeOrder(self, contract, order):
            self.placed.append(order)
            raise ConnectionError("gateway dropped after transmit")

    ib = ExplodingIB()
    with pytest.raises(ConnectionError):
        bridge(ib).place_limit(ticket())
    assert len(ib.placed) == 1  # transmitted once, never retried here


def test_bridge_satisfies_the_guarded_service_order_broker_protocol():
    from _system.trading.portfolio_hub.orders import GuardedOrderService  # noqa: F401

    for method in ("quote", "what_if", "place_limit", "find_owned_order", "cancel_owned_order"):
        assert callable(getattr(IbOrderBridge, method))


def test_limit_order_quantity_is_always_positive():
    ib = FakeIB()
    bridge(ib).place_limit(ticket(action="SELL", quantity_decimal="-10"))
    assert ib.placed[0].totalQuantity == 10.0
    assert ib.placed[0].action == "SELL"
    assert Decimal(str(ib.placed[0].lmtPrice)) == Decimal("25.4")


class LeakTrackingIB(FakeIB):
    """Counts market-data lines so a leak is visible instead of theoretical."""

    def __init__(self, *, explode_on_sleep=False, **kw):
        super().__init__(**kw)
        self.open_lines = 0
        self.peak_lines = 0
        self.snapshot_flags = []
        self.explode_on_sleep = explode_on_sleep

    def reqMktData(self, contract, generic="", snapshot=False, regulatory=False):
        self.snapshot_flags.append(snapshot)
        self.open_lines += 1
        self.peak_lines = max(self.peak_lines, self.open_lines)
        return self._ticker

    def cancelMktData(self, contract):
        self.open_lines -= 1

    def sleep(self, seconds):
        if self.explode_on_sleep:
            raise TimeoutError("gateway stalled mid-quote")


def test_quote_requests_a_snapshot_not_a_streaming_line():
    # A streaming line is held until cancelled and is drawn from the account-wide
    # pool shared with the SPX 0DTE and LS producers on the same Gateway.
    ib = LeakTrackingIB(positions=[FakePosition(101, 25)])
    bridge(ib).quote(101)
    assert ib.snapshot_flags == [True]


def test_quote_releases_its_market_data_line_even_when_it_fails():
    ib = LeakTrackingIB(explode_on_sleep=True)
    with pytest.raises(TimeoutError):
        bridge(ib).quote(101)
    assert ib.open_lines == 0, "a failed quote leaked a market-data line"


def test_repeated_quotes_never_accumulate_market_data_lines():
    ib = LeakTrackingIB(positions=[FakePosition(101, 25)])
    b = bridge(ib)
    for _ in range(50):
        b.quote(101)
    assert ib.open_lines == 0
    assert ib.peak_lines == 1, f"held {ib.peak_lines} lines at once; the pool is shared with SPX"


def test_bridge_client_id_avoids_every_reserved_producer_id():
    # _system/trading/sleeves/config.yaml reserves 0, 17 (SPX), 41 (ls-algo),
    # 87 and 90, and the sleeves themselves take 71-73. A collision would
    # disconnect whichever process connected first.
    # Fixed IDs: 0 + 41 + 77 + 90 + 197/207 (ls-algo), 17 (SPX live executor),
    # 71-73 (sleeves), 82 (hub observer), 87 (historical). Ranges are ls-algo
    # worker pools: 241-273 (41+200+i), 341-373 (41+300+i), 551 (41+510),
    # 1041+ (41+1000+16i+leg). See CLAUDE.md (IB Gateway coexistence).
    # 18 is spx-0dte's ibc_guard handshake probe (read-only connect/disconnect,
    # never subscribes or transmits) -- added to the contract 2026-08-20.
    reserved = {0, 17, 18, 41, 77, 87, 90, 197, 207, 71, 72, 73, 82}
    reserved_ranges = [(241, 273), (341, 373), (551, 551), (1041, 2100)]

    def clear(client_id):
        return client_id not in reserved and not any(
            low <= client_id <= high for low, high in reserved_ranges
        )

    assert clear(DEFAULT_BRIDGE_CLIENT_ID)
    assert clear(BridgeProfile().client_id)
    assert clear(81)  # collector default (broker.py)


def test_bridge_never_binds_orders_created_by_other_clients():
    # reqAutoOpenOrders(True) would bind TWS-created orders to this client,
    # which is how a hub session could end up owning an SPX order.
    import inspect
    import re

    from _system.trading.portfolio_hub import ib_bridge

    assert not re.search(r"\.reqAutoOpenOrders\s*\(", inspect.getsource(ib_bridge))
