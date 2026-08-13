from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from _system.trading.sleeves.flex_positions import parse_flex_positions  # noqa: E402
from _system.trading.sleeves.store import SleeveStore  # noqa: E402
from _system.trading.sleeves.sync_ib import merge_flex_marks, sync_holdings  # noqa: E402

FIXTURE = Path(__file__).with_name("fixtures") / "flex_positions_sample.xml"


def test_merge_flex_marks_replaces_cost_as_mark():
    ib_rows = [{
        "conId": 1, "symbol": "MSFT", "mark": 300, "avgCost": 300,
        "marketValue": 3000, "costUsd": 3000, "name": "MSFT",
    }]
    flex_rows = [{
        "conId": 1, "symbol": "MSFT", "mark": 400, "marketValue": 4000,
        "costUsd": 3000, "name": "MICROSOFT CORP",
    }]
    merged = merge_flex_marks(ib_rows, flex_rows)
    assert merged[0]["mark"] == 400
    assert merged[0]["marketValue"] == 4000
    assert merged[0]["name"] == "MICROSOFT CORP"
    rows = parse_flex_positions(FIXTURE, account_id="U805366")
    assert {r["symbol"] for r in rows} >= {"MSFT", "TQQQ", "APLD"}
    msft = next(r for r in rows if r["symbol"] == "MSFT")
    assert msft["marketValue"] == 4000


def test_sync_from_flex_fills_michael_and_leaves_drew_empty(tmp_path):
    store = SleeveStore(tmp_path)
    result = sync_holdings(store, flex_path=FIXTURE, ingest=False, write_dashboard=False)
    assert result["source"].startswith("flex:")
    michael_tickers = {p["ticker"] for p in result["michael"]["positions"]}
    assert "MSFT" in michael_tickers
    assert "APLD" in michael_tickers
    assert "TQQQ" not in michael_tickers
    assert result["drew"]["positions"] == []
    assert result["drew"]["header"]["open_names"] == 0
    assert result["buckets"].get("spx_0dte", 0) >= 1
    assert result["buckets"].get("etf_ls", 0) >= 1
