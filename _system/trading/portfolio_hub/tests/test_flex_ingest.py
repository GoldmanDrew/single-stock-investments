from __future__ import annotations

from decimal import Decimal

import pytest

from _system.trading.portfolio_hub.flex_ingest import build_account_snapshot, publish_flex_snapshot


# Shapes taken from the real U805366 positions file on NY4 (2026-08-21): CSU is
# genuinely reported as several tax lots, and the CAD rate really is 0.72635.
FLEX_XML = """<?xml version="1.0" encoding="UTF-8"?>
<FlexQueryResponse>
 <FlexStatements count="1">
  <FlexStatement accountId="U805366" fromDate="20260821" toDate="20260821" period="LastBusinessDay">
   <OpenPositions>
    <OpenPosition accountId="U805366" currency="CAD" fxRateToBase="0.72635" assetCategory="STK"
      symbol="CSU" description="CONSTELLATION SOFTWARE INC" conid="39194759" isin="CA21037X1006"
      position="200" markPrice="3050.51" positionValue="610102" costBasisMoney="26566"
      fifoPnlUnrealized="583536" listingExchange="TSE" model=""/>
    <OpenPosition accountId="U805366" currency="CAD" fxRateToBase="0.72635" assetCategory="STK"
      symbol="CSU" description="CONSTELLATION SOFTWARE INC" conid="39194759" isin="CA21037X1006"
      position="100.1304" markPrice="3050.51" positionValue="305457.57" costBasisMoney="13283"
      fifoPnlUnrealized="292174.57" listingExchange="TSE" model=""/>
    <OpenPosition accountId="U805366" currency="USD" fxRateToBase="1" assetCategory="STK"
      symbol="GTX" description="GARRETT MOTION INC" conid="332922484"
      position="164492" markPrice="26.18" positionValue="4306400.56" costBasisMoney="764887"
      fifoPnlUnrealized="3541513.56" listingExchange="NASDAQ" model=""/>
    <OpenPosition accountId="U805366" currency="USD" fxRateToBase="1" assetCategory="OPT"
      symbol="XSP   270129P00540000" description="XSP 29JAN27 540 P" conid="907480285"
      position="12" markPrice="2.575" positionValue="3090" costBasisMoney="3573.12"
      multiplier="100" strike="540" expiry="20270129" putCall="P" listingExchange="CBOE" model=""/>
    <OpenPosition accountId="U805366" currency="NOK" assetCategory="STK"
      symbol="NOSTALGIC" description="NO RATE PUBLISHED" conid="55500001"
      position="126" markPrice="9.32" positionValue="1173.81" costBasisMoney="1271" model=""/>
   </OpenPositions>
  </FlexStatement>
 </FlexStatements>
</FlexQueryResponse>
"""


@pytest.fixture()
def flex_file(tmp_path):
    path = tmp_path / "flex_positions.xml"
    path.write_text(FLEX_XML, encoding="utf-8")
    return path


def snapshot(flex_file):
    return build_account_snapshot(flex_file, account_alias="U805366")


# ---------------------------------------------------------------- no gateway

def test_nothing_in_this_path_can_reach_the_gateway():
    """The rule this module exists to satisfy (CLAUDE.md rule 9)."""
    import inspect

    from _system.trading.portfolio_hub import flex, flex_ingest

    for module in (flex, flex_ingest):
        source = inspect.getsource(module)
        for forbidden in ("ib_async", "ib_insync", "connectAsync", "clientId", "reqMktData", "7496", "4002"):
            assert forbidden not in source, f"{module.__name__} must not reference {forbidden}"


def test_the_collector_is_gone_from_the_package():
    with pytest.raises(ImportError):
        __import__("_system.trading.portfolio_hub.broker", fromlist=["IBAsyncCollector"])


# ------------------------------------------------------------- lot folding

def test_tax_lots_fold_into_one_position_per_contract(flex_file):
    """Flex reports per-lot; portfolio_positions is keyed per contract."""
    rows = snapshot(flex_file)["positions"]
    keys = [(row["conid"], row["model_code"]) for row in rows]
    assert len(keys) == len(set(keys)), "a repeated conId would collide on the primary key"
    csu = next(row for row in rows if row["conid"] == 39194759)
    assert Decimal(csu["quantity"]) == Decimal("300.1304"), "lot quantities add"
    assert Decimal(csu["market_value"]) == Decimal("915559.57"), "lot values add"


def test_average_cost_is_weighted_not_the_mean_of_lot_averages(flex_file):
    csu = next(row for row in snapshot(flex_file)["positions"] if row["conid"] == 39194759)
    # (26566 + 13283) / 300.1304
    assert abs(Decimal(csu["average_cost"]) - Decimal("132.77")) < Decimal("0.01")


# ------------------------------------------------------------------- currency

def test_the_stated_flex_rate_is_used_and_nothing_is_inferred(flex_file):
    csu = next(row for row in snapshot(flex_file)["positions"] if row["conid"] == 39194759)
    assert csu["fx_source"] == "ibkr_flex_rate"
    assert Decimal(csu["fx_rate_to_base"]) == Decimal("0.72635")
    # CA$915,559.57 is about USD 665k, and must never again be published as
    # USD 915,559.57.
    base = Decimal(csu["market_value_base"])
    assert Decimal("660000") < base < Decimal("670000")
    assert base != Decimal(csu["market_value"])


def test_a_row_with_no_rate_is_flagged_rather_than_relabelled(flex_file):
    row = next(row for row in snapshot(flex_file)["positions"] if row["conid"] == 55500001)
    assert row["fx_source"] == "fx_unavailable"
    assert row["fx_rate_to_base"] is None
    assert row["quality"] == "estimated"
    assert snapshot(flex_file)["flex"]["untranslated_rows"] == 1


def test_a_base_currency_row_is_identity(flex_file):
    gtx = next(row for row in snapshot(flex_file)["positions"] if row["conid"] == 332922484)
    assert gtx["fx_source"] == "identity"
    assert Decimal(gtx["market_value_base"]) == Decimal(gtx["market_value"])


def test_pnl_is_translated_with_the_same_rate(flex_file):
    csu = next(row for row in snapshot(flex_file)["positions"] if row["conid"] == 39194759)
    native = Decimal(csu["unrealized_pnl"])
    base = Decimal(csu["unrealized_pnl_base"])
    assert base == native * Decimal("0.72635")


# ------------------------------------------------------------ contract identity

def test_option_identity_survives_the_transform(flex_file):
    opt = next(row for row in snapshot(flex_file)["positions"] if row["conid"] == 907480285)
    assert opt["sec_type"] == "OPT"
    assert opt["quantity_unit"] == "contracts"
    assert opt["expiry"] == "20270129"
    assert opt["strike"] == "540"
    assert opt["right"] == "P"
    assert opt["multiplier"] == "100"


# --------------------------------------------------------------- honest gaps

def test_a_positions_only_snapshot_is_never_marked_complete(flex_file):
    """The read model serves complete runs; this one has no account values."""
    payload = snapshot(flex_file)
    assert payload["complete"] is False
    assert payload["account_values"] == []
    assert payload["completeness"]["account_summary"] is False
    assert "equity summary" in payload["completeness"]["note"]


def test_the_snapshot_declares_flex_as_its_source(flex_file):
    payload = snapshot(flex_file)
    assert payload["gateway_session_id"] is None
    assert all(row["source"] == "ibkr_flex" for row in payload["positions"])


# ------------------------------------------------------------------ freshness

def test_a_stale_file_is_refused_rather_than_republished(flex_file, monkeypatch):
    """A producer that stops writing leaves a well-formed file behind."""
    monkeypatch.setattr("_system.trading.portfolio_hub.flex_ingest.file_age_hours", lambda path, now=None: 99.0)
    result = publish_flex_snapshot(object(), positions=flex_file, account_alias="U805366", stale_hours=30)
    assert result["published"] is False
    assert "99.0h old" in result["reason"]


def test_a_missing_file_is_reported_not_raised(tmp_path):
    result = publish_flex_snapshot(object(), positions=tmp_path / "nope.xml", account_alias="U805366")
    assert result["published"] is False
    assert "does not exist" in result["reason"]


def test_a_dry_run_ingests_locally_and_publishes_nothing(flex_file):
    class _Ledger:
        def __init__(self): self.ingested = []
        def ingest_account_snapshot(self, payload): self.ingested.append(payload)

    ledger = _Ledger()
    result = publish_flex_snapshot(ledger, positions=flex_file, account_alias="U805366", dry_run=True)
    assert result["published"] is False
    assert result["gateway_contacted"] is False
    assert result["position_rows"] == 4
    assert len(ledger.ingested) == 1
