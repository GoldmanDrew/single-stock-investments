from __future__ import annotations

from decimal import Decimal

import pytest

from _system.trading.portfolio_hub.command_poller import OrderCommandLoop
from _system.trading.portfolio_hub.ib_bridge import fingerprint_for
from _system.trading.portfolio_hub.paper import PaperOrderBroker

from .test_ib_bridge import FakeIB, _stub_ib_async, bridge  # noqa: F401  (fixture import)


# --------------------------------------------------------------- fingerprint

def test_fingerprint_names_a_contract_a_human_can_check():
    """The old fingerprint was '<conid>|STK||SMART' and named nothing."""
    text = fingerprint_for({
        "conid": 907480285, "symbol": "XSP", "local_symbol": "XSP 270129P00540000",
        "sec_type": "OPT", "strike": 540.0, "right": "P", "expiry": "20270129",
        "multiplier": "100", "exchange": "SMART", "currency": "USD",
    })
    for fragment in ("XSP 270129P00540000", "540 P", "20270129", "100x", "SMART/USD", "conId 907480285"):
        assert fragment in text, f"a person could not verify the strike without {fragment!r}"


def test_stock_fingerprint_stays_short_and_omits_option_coordinates():
    text = fingerprint_for({
        "conid": 272093, "symbol": "MSFT", "local_symbol": "MSFT", "sec_type": "STK",
        "exchange": "SMART", "currency": "USD",
    })
    assert text == "MSFT | STK | SMART/USD | conId 272093"


def test_fingerprint_marks_an_unknown_multiplier_rather_than_assuming_100():
    text = fingerprint_for({
        "conid": 1, "symbol": "XSP", "sec_type": "OPT", "strike": 540.0,
        "right": "P", "expiry": "20270129", "exchange": "SMART", "currency": "USD",
    })
    assert "?x" in text and "100x" not in text


# ------------------------------------------------------------------ resolver

def test_resolve_returns_contract_details_for_a_stock(_stub_ib_async):
    resolved = bridge(FakeIB()).resolve({"symbol": "MSFT", "sec_type": "STK", "kind": "contract"})
    assert len(resolved) == 1
    assert resolved[0]["symbol"] == "MSFT"
    assert resolved[0]["conid"]


def test_option_chain_uses_one_request_not_a_strike_loop(_stub_ib_async):
    ib = FakeIB()
    calls = {"details": 0}
    original = ib.reqContractDetails

    def counted(contract):
        calls["details"] += 1
        return original(contract)

    ib.reqContractDetails = counted
    rows = bridge(ib).resolve({"symbol": "XSP", "sec_type": "OPT", "kind": "option_chain"})
    # Looping reqContractDetails over strikes is what walks into IBKR's pacing
    # limits mid-session; the chain must come from reqSecDefOptParams instead.
    assert calls["details"] == 0
    assert {row["expiry"] for row in rows} == {"20260918", "20270129"}
    assert rows[0]["strikes"] == [520.0, 540.0, 620.0]


def test_contract_identity_is_taken_from_the_broker(_stub_ib_async):
    identity = bridge(FakeIB()).contract_identity(272093)
    assert identity["conid"] == 272093
    assert "fingerprint" in identity
    assert "conId 272093" in identity["fingerprint"]


# ------------------------------------------------- loop guards around options

class _Channel:
    def __init__(self, requests=None, lookups=None):
        self._requests, self._lookups = requests or [], lookups or []
        self.published, self.lookup_published = [], []

    def claim(self): return self._requests
    def claim_lookups(self): return self._lookups
    def publish(self, request_id, update): self.published.append((request_id, update))
    def publish_lookup(self, lookup_id, update): self.lookup_published.append((lookup_id, update))


class _Service:
    def __init__(self, broker): self.broker = broker


def _quotes(conid):
    return {"bid": "5.10", "ask": "5.20", "min_tick": "0.01", "multiplier": "100"}


def _loop(channel, *, options_enabled=False, broker=None):
    return OrderCommandLoop(
        _Service(broker or PaperOrderBroker(_quotes)), channel,
        account_alias="U123", live_enabled=False, options_enabled=options_enabled,
    )


def _option_row(**overrides):
    base = {
        "request_id": "r1", "conid": 907480285, "sec_type": "OPT", "action": "BUY",
        "quantity_decimal": "2", "limit_price_decimal": "5.15", "owner": "drew",
        "strategy": "single_stock", "mode": "paper", "tif": "DAY", "state": "requested",
    }
    return {**base, **overrides}


def test_options_are_refused_while_their_own_interlock_is_off():
    channel = _Channel(requests=[_option_row()])
    _loop(channel, options_enabled=False).tick()
    assert channel.published, "an off interlock must reject the ticket, not drop it silently"
    _, update = channel.published[0]
    assert update["state"] == "rejected"
    assert "options interlock" in update["reject_reason"]


def test_the_options_interlock_is_separate_from_the_live_interlock():
    """Enabling live stock trading must not enable options by side effect."""
    loop = OrderCommandLoop(_Service(PaperOrderBroker(_quotes)), _Channel(),
                            account_alias="U123", live_enabled=True)
    assert loop.live_enabled is True
    assert loop.options_enabled is False


def test_a_conid_that_disagrees_with_the_declared_sec_type_is_refused():
    """A form saying STK over an option conId would otherwise transmit an option."""
    broker = PaperOrderBroker(_quotes, contracts={
        907480285: {"symbol": "XSP", "sec_type": "OPT", "local_symbol": "XSP 270129P00540000",
                    "strike": 540.0, "right": "P", "expiry": "20270129", "multiplier": "100"},
    })
    channel = _Channel(requests=[_option_row(sec_type="STK")])
    _loop(channel, options_enabled=True, broker=broker).tick()
    _, update = channel.published[0]
    assert update["state"] == "rejected"
    assert "is a OPT, not the STK" in update["reject_reason"]


# ------------------------------------------------------------ lookup pumping

def test_lookups_are_resolved_and_published():
    channel = _Channel(lookups=[{"lookup_id": "l1", "kind": "contract", "symbol": "MSFT", "sec_type": "STK"}])
    assert _loop(channel).resolve_lookups() is True
    lookup_id, update = channel.lookup_published[0]
    assert lookup_id == "l1"
    assert update["state"] == "resolved"
    assert update["matches"][0]["symbol"] == "MSFT"


def test_a_failing_lookup_is_published_as_failed_rather_than_left_to_spin():
    class _Broken(PaperOrderBroker):
        def resolve(self, request): raise RuntimeError("gateway is down")

    channel = _Channel(lookups=[{"lookup_id": "l2", "kind": "contract", "symbol": "NOPE", "sec_type": "STK"}])
    _loop(channel, broker=_Broken(_quotes)).resolve_lookups()
    _, update = channel.lookup_published[0]
    assert update["state"] == "failed"
    assert "gateway is down" in update["error"]


def test_an_empty_resolution_is_a_failure_not_an_empty_success():
    class _Empty(PaperOrderBroker):
        def resolve(self, request): return []

    channel = _Channel(lookups=[{"lookup_id": "l3", "kind": "contract", "symbol": "ZZZZ", "sec_type": "STK"}])
    _loop(channel, broker=_Empty(_quotes)).resolve_lookups()
    _, update = channel.lookup_published[0]
    assert update["state"] == "failed"
    assert "no contract" in update["error"]


def test_a_lookup_channel_outage_never_stops_the_order_loop():
    """Orders must keep flowing even when contract resolution is broken."""
    class _NoLookups(_Channel):
        def claim_lookups(self): raise RuntimeError("lookup route missing")

    channel = _NoLookups(requests=[_option_row()])
    _loop(channel, options_enabled=False).tick()
    assert channel.published, "the order half must still have run"


def test_a_half_point_strike_keeps_its_half():
    text = fingerprint_for({
        "conid": 2, "symbol": "SPY", "sec_type": "OPT", "strike": 542.5,
        "right": "C", "expiry": "20260918", "multiplier": "100",
    })
    assert "542.5 C" in text
