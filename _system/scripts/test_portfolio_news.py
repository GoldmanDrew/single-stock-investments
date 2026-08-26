#!/usr/bin/env python3
"""Smoke tests for portfolio news classification and matching."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from portfolio_news_common import (  # noqa: E402
    POLICY_VERSION,
    classify_text,
    is_refresh_eligible,
    load_holding_configs,
    match_holding,
    passes_feed_gate,
    score_confidence,
    NewsItem,
)


def test_classify_guidance():
    cat, conf = classify_text("Amazon cuts full-year outlook amid cloud margin pressure")
    assert cat == "guidance"
    assert conf >= 0.7


def test_rejects_analyst_noise():
    cat, _ = classify_text("Analyst upgrades Amazon price target to $250")
    assert cat is None


def test_match_amzn_explicit():
    configs = load_holding_configs()
    ticker, tier = match_holding(
        "Amazon.com (NASDAQ: AMZN) announces $5B buyback authorization",
        "https://ir.aboutamazon.com/news",
        configs,
    )
    assert ticker == "AMZN"
    assert tier == "explicit"


def test_match_brand_alias():
    configs = load_holding_configs()
    ticker, tier = match_holding(
        "Google parent announces new $70B buyback authorization",
        "https://abc.xyz/investor/news",
        configs,
    )
    assert ticker == "GOOGL"
    assert tier == "high"


def test_match_local_market_base_ticker():
    configs = load_holding_configs()
    ticker, tier = match_holding(
        "Rightmove plc (LSE: RMV) raises full-year outlook",
        "https://www.rightmove.co.uk/news",
        configs,
    )
    assert ticker == "RMV.L"
    assert tier == "explicit"


def test_match_manual_exchange_alias():
    configs = load_holding_configs()
    ticker, tier = match_holding(
        "HKEX announces a new market-structure consultation",
        "https://www.hkexgroup.com/media-centre",
        configs,
    )
    assert ticker == "0388.HK"
    assert tier == "high"


def test_refresh_eligible_buyback():
    item = NewsItem(
        id="test:1",
        tickers=["CPRT"],
        category="buyback",
        confidence=0.88,
        match_tier="explicit",
        title="Copart announces new share repurchase program",
    )
    item.refresh_eligible = is_refresh_eligible(item)
    assert item.refresh_eligible is True
    assert passes_feed_gate(item, load_holding_configs()["CPRT"])


def test_otc_requires_explicit():
    cfg = load_holding_configs()["FRMO"]
    item = NewsItem(
        id="test:2",
        tickers=["FRMO"],
        category="buyback",
        confidence=0.88,
        match_tier="high",
        title="FRMO Corporation board approves repurchase plan",
    )
    assert passes_feed_gate(item, cfg) is False


def test_rejects_fund_flow_m_and_a():
    cat, _ = classify_text(
        "Northwestern Mutual Wealth Management Co. Acquires 186,584 Shares of Danaher Corporation $DHR"
    )
    assert cat is None


def test_rejects_routine_dividend():
    cat, _ = classify_text("S&P Global (SPGI) Declares Consistent Quarterly Dividend of $0.9")
    assert cat is None


def test_rejects_sec_filing_roundup():
    cat, _ = classify_text("Copart (CPRT) 10K Form and Latest SEC Filings 2026 - MarketBeat")
    assert cat is None


def test_rejects_opinion_spinoff_headline():
    cat, _ = classify_text(
        "Will S&P Global's (SPGI) Mobility Spin-Off and Dividend Steadiness Redefine Its Core Narrative?"
    )
    assert cat is None


def test_persist_writes_dashboard_portfolio_news():
    import ingest_portfolio_news as ingest  # noqa: WPS433

    configs = load_holding_configs()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        dashboard_path = root / "dashboard" / "portfolio_news.json"
        dashboard_path.parent.mkdir(parents=True)
        seen_path = root / "news_seen.json"
        with (
            patch.object(ingest, "PORTFOLIO_NEWS_PATH", dashboard_path),
            patch.object(ingest, "NEWS_SEEN_PATH", seen_path),
        ):
            ingest.persist([], configs)
        assert dashboard_path.exists()


def test_sanitize_existing_news_reassigns_or_quarantines_legacy_rows():
    import ingest_portfolio_news as ingest  # noqa: WPS433

    configs = load_holding_configs()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "source.json"
        dashboard = root / "dashboard.json"
        source.write_text(
            json.dumps(
                {
                    "policy_version": 3,
                    "items": [
                        {
                            "id": "wrong-a",
                            "tickers": ["A"],
                            "title": "GoDaddy launches a new commerce product",
                            "summary": "GoDaddy expands its merchant platform.",
                            "url": "https://example.com/godaddy",
                        },
                        {
                            "id": "unrelated-a",
                            "tickers": ["A"],
                            "title": "Eli Lilly raises annual guidance",
                            "summary": "Mounjaro sales accelerated.",
                            "url": "https://example.com/lilly",
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        kept, reassigned, dropped = ingest.sanitize_existing_news(
            configs,
            source_path=source,
            output_paths=(dashboard,),
        )
        assert (kept, reassigned, dropped) == (1, 1, 1)
        result = json.loads(dashboard.read_text(encoding="utf-8"))
        assert result["items"][0]["tickers"] == ["GDDY"]
        assert result["policy_version"] == POLICY_VERSION


def test_inv_search_names_include_accelsius():
    configs = load_holding_configs()
    if "INV" not in configs:
        return
    names = " ".join(configs["INV"].search_names).lower()
    assert "accelsius" in names
    assert "neucool" in names


if __name__ == "__main__":
    test_classify_guidance()
    test_rejects_analyst_noise()
    test_match_amzn_explicit()
    test_match_brand_alias()
    test_match_local_market_base_ticker()
    test_match_manual_exchange_alias()
    test_refresh_eligible_buyback()
    test_otc_requires_explicit()
    test_rejects_fund_flow_m_and_a()
    test_rejects_routine_dividend()
    test_rejects_sec_filing_roundup()
    test_rejects_opinion_spinoff_headline()
    test_persist_writes_dashboard_portfolio_news()
    test_sanitize_existing_news_reassigns_or_quarantines_legacy_rows()
    test_inv_search_names_include_accelsius()
    print("ok")
