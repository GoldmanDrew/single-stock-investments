from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from _system.trading.sleeves.performance import conviction_calibration, independence_score, xirr  # noqa: E402


def test_xirr_simple_round_trip():
    start = date(2024, 1, 1)
    end = date(2025, 1, 1)
    rate = xirr([(start, -100.0), (end, 110.0)])
    assert rate is not None
    assert abs(rate - 0.1) < 0.002


def test_independence_same_cluster_penalized():
    names = [
        {"ticker": "A", "cluster": "ai_infra", "market_value": 50},
        {"ticker": "B", "cluster": "ai_infra", "market_value": 50},
    ]
    same = independence_score(names)
    split = independence_score([
        {"ticker": "A", "cluster": "ai_infra", "market_value": 50},
        {"ticker": "C", "cluster": "oil", "market_value": 50},
    ])
    assert same["score"] < split["score"]
    assert same["mean_abs_corr"] == 1.0
    assert split["mean_abs_corr"] == 0.0


def test_conviction_calibration_buckets():
    rows = [
        {"conviction": 5, "irr": 0.2, "plc_event": False, "years_held": 3},
        {"conviction": 2, "irr": -0.1, "plc_event": True, "years_held": 0.5},
    ]
    cal = conviction_calibration(rows)
    five = next(x for x in cal if x["conviction"] == 5)
    two = next(x for x in cal if x["conviction"] == 2)
    assert five["avg_irr"] == 0.2
    assert two["plc_rate"] == 1.0
