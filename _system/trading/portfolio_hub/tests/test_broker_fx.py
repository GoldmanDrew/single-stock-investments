from __future__ import annotations

import types
from decimal import Decimal

from _system.trading.portfolio_hub.broker import BrokerProfile, IBAsyncCollector


def collector() -> IBAsyncCollector:
    return IBAsyncCollector(BrokerProfile(
        host="127.0.0.1", port=7496, client_id=81,
        account_id="U805366", account_alias="U805366",
    ))


def translate(native_ccy, native_value, reported_value, rates=None):
    return IBAsyncCollector._fx_translation(
        native_ccy, "USD", Decimal(str(native_value)), Decimal(str(reported_value)), rates,
    )


# ------------------------------------------------- the ratio that carried nothing

def test_a_ratio_within_rounding_of_one_is_not_an_fx_rate():
    """The exact-equality guard never fired; these are the values it let through.

    Observed on U805366 2026-08-24: marketValue is rounded to 2dp while
    position x marketPrice is full precision, so the ratio is 1 plus float noise
    and `== Decimal(1)` is always False.
    """
    for native_ccy, native, reported in (
        ("JPY", "4956299.92680000", "4956299.93"),   # ratio 1.000000000645...
        ("CAD", "918572.90325667928", "918572.9"),   # ratio 0.999999996454...
    ):
        rate, source = translate(native_ccy, native, reported)
        assert rate is None, f"{native_ccy} ratio must not be published as a rate"
        assert source == "fx_unavailable"


def test_an_exactly_one_ratio_is_still_refused():
    assert translate("EUR", "1000", "1000") == (None, "fx_unavailable")


def test_a_real_inferred_rate_still_passes():
    """A genuine translation is far from parity and must survive the tolerance."""
    rate, source = translate("JPY", "5064000", "34435.20")
    assert source == "ibkr_portfolio_translation"
    assert rate is not None and rate < Decimal("0.01")


# ---------------------------------------------- IBKR's own rate wins outright

def test_the_stated_rate_is_preferred_over_any_inference():
    rate, source = translate("JPY", "4956299.93", "4956299.93", {"JPY": Decimal("0.00680")})
    assert source == "ibkr_exchange_rate"
    assert rate == Decimal("0.00680")


def test_a_stated_rate_near_parity_is_accepted():
    """EUR and CHF have both traded near 1.0; the tolerance must not reach them."""
    rate, source = translate("CHF", "1000", "1000", {"CHF": Decimal("1.00004")})
    assert source == "ibkr_exchange_rate"
    assert rate == Decimal("1.00004")


def test_same_currency_is_identity_regardless_of_the_rate_table():
    assert translate("USD", "100", "100", {"USD": Decimal("7")}) == (Decimal(1), "identity")


def test_a_zero_or_negative_stated_rate_is_ignored():
    for bad in (Decimal("0"), Decimal("-0.68")):
        rate, source = translate("JPY", "1000", "1000", {"JPY": bad})
        assert source == "fx_unavailable", f"{bad} must not be treated as a rate"


# --------------------------------------------- the published row, end to end

class _Contract:
    def __init__(self, currency="JPY"):
        self.conId, self.symbol, self.localSymbol = 174264756, "3905", "3905"
        self.secType, self.currency, self.exchange = "STK", currency, "TSEJ"
        self.primaryExchange, self.strike, self.right = "TSEJ", 0, ""
        self.multiplier, self.lastTradeDateOrContractMonth = None, ""


class _PortfolioRow:
    def __init__(self, currency="JPY"):
        self.contract = _Contract(currency)
        self.account, self.position, self.averageCost = "U805366", 3000.0, 2274.95
        self.marketPrice, self.marketValue = 1652.1, 4956299.93
        self.unrealizedPNL, self.realizedPNL = -1868548.40, 0.0


def test_base_value_is_translated_not_relabelled():
    row = collector()._portfolio_position(
        _PortfolioRow(), "", "2026-08-24T16:20:57Z", "USD", {"JPY": Decimal("0.00680")},
    )
    assert row["fx_source"] == "ibkr_exchange_rate"
    native = Decimal(row["market_value_native"])
    base = Decimal(row["market_value_base"])
    assert native != base, "a JPY row published at its native magnitude is the whole bug"
    # ~JPY 4.96m is ~USD 34k, not USD 4.96m.
    assert Decimal("33000") < base < Decimal("35000")
    # P&L travels with it; an untranslated loss would be off by the same factor.
    assert Decimal(row["unrealized_pnl_base"]) > Decimal("-13000")
    assert row["quality"] == "live"


def test_an_untranslatable_row_is_flagged_and_still_published():
    row = collector()._portfolio_position(
        _PortfolioRow(), "", "2026-08-24T16:20:57Z", "USD", {},
    )
    assert row["fx_source"] == "fx_unavailable"
    assert row["fx_rate_to_base"] is None
    # The envelope requires a decimal here, so the native figure stays -- paired
    # with a source and a quality that forbid using it as base.
    assert Decimal(row["market_value_base"]) == Decimal(row["market_value"])
    assert row["quality"] == "estimated"


def test_a_base_currency_row_is_untouched():
    row = collector()._portfolio_position(
        _PortfolioRow("USD"), "", "2026-08-24T16:20:57Z", "USD", {},
    )
    assert row["fx_source"] == "identity"
    assert Decimal(row["fx_rate_to_base"]) == Decimal(1)


# ------------------------------------------------------ reading the rate table

def test_exchange_rates_are_read_from_the_account_value_cache():
    ib = types.SimpleNamespace(
        managedAccounts=lambda: ["U805366"],
        accountValues=lambda account: [
            types.SimpleNamespace(tag="ExchangeRate", currency="JPY", value="0.00680"),
            types.SimpleNamespace(tag="ExchangeRate", currency="cad", value="0.72635"),
            types.SimpleNamespace(tag="ExchangeRate", currency="XXX", value="not-a-number"),
            types.SimpleNamespace(tag="NetLiquidation", currency="USD", value="12000000"),
        ],
    )
    rates = IBAsyncCollector._exchange_rates(ib)
    assert rates == {"JPY": Decimal("0.00680"), "CAD": Decimal("0.72635")}


def test_a_missing_rate_cache_is_not_fatal():
    def explode(account):
        raise RuntimeError("no account updates subscribed")

    ib = types.SimpleNamespace(managedAccounts=lambda: ["U805366"], accountValues=explode)
    assert IBAsyncCollector._exchange_rates(ib) == {}
