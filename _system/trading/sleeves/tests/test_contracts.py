from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from _system.trading.sleeves.contracts import (  # noqa: E402
    contract_spec,
    parse_occ_local,
    quote_px,
    spec_from_mapping,
)


def test_stock_spec():
    spec = contract_spec("CSU")
    assert spec["sec_type"] == "STK"
    assert spec["ticker"] == "CSU"
    assert spec["multiplier"] == 1.0


def test_option_spec_from_fields():
    spec = contract_spec(
        sec_type="OPT",
        underlying="AAPL",
        expiry="2026-08-21",
        strike=200,
        right="call",
    )
    assert spec["sec_type"] == "OPT"
    assert spec["underlying"] == "AAPL"
    assert spec["expiry"] == "20260821"
    assert spec["right"] == "C"
    assert spec["strike"] == 200
    assert spec["multiplier"] == 100
    assert spec["ticker"].startswith("AAPL")


def test_option_spec_from_occ_local():
    parsed = parse_occ_local("AAPL  260821C00200000")
    assert parsed is not None
    assert parsed["underlying"] == "AAPL"
    assert parsed["expiry"] == "20260821"
    assert parsed["right"] == "C"
    assert parsed["strike"] == 200
    spec = spec_from_mapping({"secType": "OPT", "localSymbol": "AAPL  260821C00200000"})
    assert spec["underlying"] == "AAPL"
    assert spec["strike"] == 200


def test_quote_px_prefers_last_then_mid():
    assert quote_px({"last": 10, "bid": 9, "ask": 11}) == 10
    assert quote_px({"last": None, "bid": 9, "ask": 11}) == 10
    assert quote_px({"bid": 4}) == 4
    assert quote_px({}) is None
