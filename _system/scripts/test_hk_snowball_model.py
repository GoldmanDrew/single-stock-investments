#!/usr/bin/env python3
"""Unit tests for HK snowball / power-law model helpers."""
from __future__ import annotations

import math
import sys
from datetime import date, timedelta
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import build_hk_snowball_model as hk  # noqa: E402


def test_milestones_half_time_low_value():
    """Geometric series: at 50% time, value << 50% of terminal (snowball shape)."""
    origin = date(2010, 1, 1)
    series = []
    for i in range(0, 101):
        d = origin + timedelta(days=i * 36)  # ~10 years
        # roughly t^3 style growth in index space
        t = max(i / 100.0, 1e-6)
        series.append((d, 100.0 * (t**3)))
    stops = {s["time_frac"]: s for s in hk.milestones(series, origin=origin)}
    half = stops[0.50]["pct_of_terminal"]
    assert half is not None and half < 20.0, half
    assert abs(stops[1.0]["pct_of_terminal"] - 100.0) < 1e-6


def test_power_law_fit_recovers_t6():
    origin = date(2011, 1, 1)
    A_true, k_true = 2.5, 6.0
    series = []
    for years in range(2, 16):
        d = origin + timedelta(days=int(years * 365.25))
        t = hk.years_since(origin, d)
        series.append((d, A_true * (t**k_true)))
    # densify
    dense = []
    for i in range(0, 400):
        d = origin + timedelta(days=800 + i * 12)
        t = hk.years_since(origin, d)
        dense.append((d, A_true * (t**k_true)))
    fit = hk.fit_power_law(dense, origin=origin)
    assert fit["ok"], fit
    assert abs(fit["k"] - 6.0) < 0.05, fit
    assert abs(math.log(fit["A"]) - math.log(A_true)) < 0.15, fit
    assert fit["r2_log"] is not None and fit["r2_log"] > 0.999


def test_halving_doubles_cost():
    as_of = date(2026, 8, 4)
    supply = hk.cost_curve(as_of, current_all_in=65000.0)
    assert supply["as_of_cost_usd"] == 65000.0
    assert supply["halving_2028_cost_usd"] == 130000.0
    assert supply["halving_2028_premium_band_usd"] == 227500.0
    # post-2024 epoch vs post-2020: one halving back => half
    by_date = {p["date"]: p["all_in_cost_usd"] for p in supply["curve"] if p["event"] == "halving"}
    assert by_date["2024-04-20"] == 65000.0  # same epoch as as_of (after 2024)
    assert by_date["2020-05-11"] == 32500.0
    assert by_date["2028-04-15"] == 130000.0


def test_dial_labels():
    assert hk.dial_label(64000, 150000, 65000) == "below_model"
    assert hk.dial_label(50000, 150000, 65000) == "below_cost_floor"
    assert hk.dial_label(155000, 150000, 65000) == "on_schedule"
    assert hk.dial_label(220000, 150000, 65000) == "above_model"


def test_model_2028_order_of_magnitude_vs_hk():
    """With a near-t^6 synthetic path, 2028 print should be same OOM as HK ~$270k."""
    origin = hk.BTC_ORIGIN
    # Calibrate A so that at ~15.3 years (Apr 2028 from 2011) price ~270k with k=5.8
    k = 5.8
    t_2028 = hk.years_since(origin, hk.NEXT_HALVING)
    A = 270438.05 / (t_2028**k)
    series = []
    for i in range(0, 500):
        d = origin + timedelta(days=400 + i * 10)
        if d > date(2026, 8, 1):
            break
        t = hk.years_since(origin, d)
        series.append((d, A * (t**k)))
    fit = hk.fit_power_law(series, origin=origin)
    assert fit["ok"]
    mp = hk.model_price(fit, hk.NEXT_HALVING)
    assert mp is not None
    # Same order of magnitude as commentary $270,438
    assert 100_000 < mp < 700_000, mp
    ratio = mp / hk.HK_MODEL_2028
    assert 0.4 < ratio < 2.5, (mp, ratio)


def main() -> int:
    test_milestones_half_time_low_value()
    test_power_law_fit_recovers_t6()
    test_halving_doubles_cost()
    test_dial_labels()
    test_model_2028_order_of_magnitude_vs_hk()
    print("test_hk_snowball_model: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
