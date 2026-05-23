#!/usr/bin/env python3
"""Smoke tests for portfolio news classification and matching."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from portfolio_news_common import (  # noqa: E402
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


if __name__ == "__main__":
    test_classify_guidance()
    test_rejects_analyst_noise()
    test_match_amzn_explicit()
    test_refresh_eligible_buyback()
    test_otc_requires_explicit()
    test_rejects_fund_flow_m_and_a()
    test_rejects_routine_dividend()
    test_rejects_sec_filing_roundup()
    test_rejects_opinion_spinoff_headline()
    print("ok")
