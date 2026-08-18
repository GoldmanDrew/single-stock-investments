from __future__ import annotations

import hashlib
import hmac
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from _system.trading.sleeves.book import build_book  # noqa: E402
from _system.trading.sleeves.classify_positions import classify_positions, expand_blacklist_symbols  # noqa: E402
from _system.trading.sleeves.config_loader import load_blacklist, load_etf_ls_universe, load_etf_to_under  # noqa: E402
from _system.trading.sleeves.ingest import sign_body  # noqa: E402
from _system.trading.sleeves.orders import approve_trade, propose_trade  # noqa: E402
from _system.trading.sleeves.store import SleeveStore  # noqa: E402


def test_hmac_matches_js_scheme():
    token = "a" * 32
    body = b'{"kind":"fill"}'
    headers = sign_body(token, body, timestamp="1710000000", nonce="ab" * 16)
    message = b"1710000000\n" + ("ab" * 16).encode() + b"\n" + body
    expected = hmac.new(token.encode(), message, hashlib.sha256).hexdigest()
    assert headers["x-sleeve-signature"] == expected
    assert headers["x-sleeve-timestamp"] == "1710000000"


def test_ib_sync_seeds_michael_and_drew_fill_roundtrip(tmp_path):
    store = SleeveStore(tmp_path)
    family = expand_blacklist_symbols(load_blacklist(), load_etf_to_under())
    letf = load_etf_ls_universe()
    classified = classify_positions(
        [
            {"symbol": "CSU", "qty": 100, "mark": 400, "marketValue": 40000, "secType": "STK"},
            {"symbol": "APLZ", "qty": 200, "mark": 20, "marketValue": 4000, "secType": "STK"},
            {"symbol": "TQQQ", "qty": 50, "mark": 40, "marketValue": 2000, "secType": "STK", "orderRef": "ETF_LS|X"},
            {"symbol": "SPX", "qty": -1, "secType": "OPT", "tradingClass": "SPXW"},
        ],
        blacklist_family=family,
        etf_ls_symbols=letf,
    )
    store.replace_positions(classified)
    michael = build_book("michael", store)
    tickers = {p["ticker"] for p in michael["positions"]}
    assert "CSU" in tickers
    assert "APLZ" in tickers
    assert "TQQQ" not in tickers
    assert "SPX" not in tickers
    quote = {
        "last": 50.0,
        "as_of": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "account": "TEST_ACCOUNT",
        "qualified_name": "GTX",
        "currency": "USD",
        "exchange": "SMART",
    }
    proposal = propose_trade(
        owner="drew", ticker="GTX", side="BUY", qty=5, limit_price=50, quote=quote,
        holding_period_years=5, plc_thesis="Permanent loss if membership economics collapse.",
        conviction=4, cluster="idiosyncratic", store=store,
    )
    fill = approve_trade(proposal_id=proposal["proposal_id"], typed_ticker="GTX", quote=quote, store=store)
    drew = build_book("drew", store)
    ingest_payload = {"kind": "fill", "fill": fill, "book": drew}
    assert ingest_payload["book"]["positions"][0]["ticker"] == "GTX"
    assert json.dumps(ingest_payload)
