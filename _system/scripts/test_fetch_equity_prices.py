from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

import fetch_equity_prices as prices


class _Response:
    def __init__(self, payload: dict):
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_yahoo_window_crosses_month_boundary() -> None:
    observed: dict[str, str] = {}
    payload = {
        "chart": {
            "result": [{
                "timestamp": [int(datetime(2026, 8, 28, tzinfo=timezone.utc).timestamp())],
                "indicators": {"quote": [{"close": [9000.0]}]},
            }]
        }
    }

    class _SeptemberFirst(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 1, 12, tzinfo=tz or timezone.utc)

    def fake_urlopen(request, timeout=0):
        observed["url"] = request.full_url
        return _Response(payload)

    with patch.object(prices, "datetime", _SeptemberFirst), patch.object(
        prices.urllib.request, "urlopen", fake_urlopen
    ):
        close, quote_date, error = prices.fetch_yahoo_close("LSEG.L")

    assert close == 9000.0
    assert quote_date == "2026-08-28"
    assert error is None
    query = parse_qs(urlparse(observed["url"]).query)
    assert int(query["period2"][0]) - int(query["period1"][0]) == 14 * 24 * 60 * 60


def test_london_quote_is_normalized_to_gbp() -> None:
    with patch.object(prices, "registry_row", return_value={"market": "UK", "exchange": "LSE"}), patch.object(
        prices, "fetch_stooq_close", return_value=(None, None, "not available")
    ), patch.object(prices, "fetch_yahoo_close", return_value=(9000.0, "2026-08-28", None)):
        close, quote_date, source = prices.fetch_price("LSEG")

    assert close == 90.0
    assert quote_date == "2026-08-28"
    assert source == "Yahoo LSEG.L close 2026-08-28 (GBX converted to GBP)"


def test_market_mark_does_not_rewrite_model_as_of(tmp_path) -> None:
    research = tmp_path / "ABC" / "research"
    research.mkdir(parents=True)
    valuation = {
        "ticker": "ABC",
        "as_of": "2026-06-30",
        "inputs": {"price": 10.0, "price_as_of": "2026-06-30"},
    }
    (research / "valuation.json").write_text(json.dumps(valuation), encoding="utf-8")

    with patch.object(prices, "ROOT", tmp_path), patch.object(
        prices, "fetch_price", return_value=(12.5, "2026-08-31", "test close")
    ):
        assert prices.merge_ticker("ABC", force=True)

    updated = json.loads((research / "valuation.json").read_text(encoding="utf-8"))
    assert updated["as_of"] == "2026-06-30"
    assert updated["inputs"]["price"] == 12.5
    assert updated["inputs"]["price_as_of"] == "2026-08-31"
