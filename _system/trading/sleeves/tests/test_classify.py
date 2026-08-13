from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from _system.trading.sleeves.classify_positions import (  # noqa: E402
    classify_position,
    expand_blacklist_symbols,
    classify_positions,
)
from _system.trading.sleeves.config_loader import load_blacklist, load_etf_to_under  # noqa: E402


def test_expand_blacklist_includes_mapped_etfs():
    blocked = expand_blacklist_symbols({"APLD", "SMR"}, {"APLZ": "APLD", "APLX": "APLD", "SMZ": "SMR", "AAOX": "AAOI"})
    assert "APLD" in blocked and "APLZ" in blocked and "APLX" in blocked
    assert "SMR" in blocked and "SMZ" in blocked
    assert "AAOX" not in blocked


def test_snapshot_blacklist_covers_configured_names():
    family = expand_blacklist_symbols(load_blacklist(), load_etf_to_under())
    for name in ("JPM", "BRK-B", "AXP", "APLD", "SMR", "CBRS", "APLZ", "APLX", "SMZ"):
        assert name in family


def test_spxw_excluded():
    cls = classify_position(
        {"symbol": "SPX", "secType": "OPT", "tradingClass": "SPXW", "localSymbol": "SPXW  260813C05000000"},
        blacklist_family={"APLD"},
        etf_ls_symbols={"TQQQ"},
    )
    assert cls.bucket == "spx_0dte"


def test_etf_ls_excluded_unless_blacklist_family():
    tqqq = classify_position({"symbol": "TQQQ", "secType": "STK"}, blacklist_family={"APLD"}, etf_ls_symbols={"TQQQ"})
    assert tqqq.bucket == "etf_ls"
    aplz = classify_position({"symbol": "APLZ", "secType": "STK"}, blacklist_family={"APLD", "APLZ"}, etf_ls_symbols={"TQQQ", "APLZ"})
    assert aplz.bucket == "michael"
    assert aplz.reason == "blacklist_family"


def test_order_ref_etf_ls():
    cls = classify_position(
        {"symbol": "SOXL", "secType": "STK", "orderRef": "ETF_LS|ESTABLISH|NVDA|SOXL"},
        blacklist_family=set(),
        etf_ls_symbols=set(),
    )
    assert cls.bucket == "etf_ls"


def test_residual_and_drew():
    msft = classify_position({"symbol": "MSFT", "secType": "STK"}, blacklist_family=set(), etf_ls_symbols={"TQQQ"})
    assert msft.bucket == "michael" and msft.reason == "residual"
    drew = classify_position(
        {"symbol": "MSFT", "secType": "STK", "orderRef": "DREW_SLEEVE"},
        blacklist_family=set(),
        etf_ls_symbols=set(),
    )
    assert drew.bucket == "drew"


def test_classify_positions_audit():
    rows = classify_positions(
        [
            {"symbol": "MSFT", "qty": 10},
            {"symbol": "SPX", "secType": "OPT", "tradingClass": "SPXW"},
        ],
        blacklist_family=set(),
        etf_ls_symbols=set(),
    )
    assert rows[0]["classification"]["bucket"] == "michael"
    assert rows[1]["classification"]["bucket"] == "spx_0dte"
