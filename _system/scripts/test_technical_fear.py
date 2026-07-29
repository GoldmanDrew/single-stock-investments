from __future__ import annotations

import math
import unittest
from datetime import date, timedelta

import build_technical_signals as technicals


def synthetic_rows(*, panic: bool) -> list[dict]:
    rows: list[dict] = []
    start = date(2022, 1, 1)
    close = 100.0
    for index in range(820):
        drift = 0.0004 + 0.003 * math.sin(index / 11)
        prior = close
        close = prior * (1 + drift)
        open_px = prior * (1 + 0.0005 * math.sin(index))
        high = max(open_px, close) * 1.008
        low = min(open_px, close) * 0.992
        volume = 1_000_000 * (1 + 0.08 * math.sin(index / 7))
        rows.append({
            "date": (start + timedelta(days=index)).isoformat(),
            "open": open_px,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        })
    if panic:
        for offset in range(5):
            index = len(rows) - 5 + offset
            prior = rows[index - 1]["close"]
            close = prior * (0.94 if offset < 4 else 0.88)
            rows[index].update({
                "open": prior * 0.995,
                "high": prior,
                "low": close * 0.985,
                "close": close,
                "volume": 2_000_000 + offset * 1_000_000,
            })
    return rows


class TechnicalFearTests(unittest.TestCase):
    def test_panic_requires_stabilization_before_confirmation(self):
        snapshot = technicals.calculate_snapshot(
            "TEST",
            synthetic_rows(panic=True),
            benchmark_rows=None,
            benchmark="SPY",
            source="synthetic",
        )
        fear = snapshot["capitulation"]
        self.assertGreaterEqual(fear["scores"]["panic"], 70)
        self.assertNotEqual(fear["state"], "confirmed_exhaustion")
        self.assertFalse(fear["confirmation"]["positive_session"])
        self.assertFalse(fear["confirmation"]["closed_upper_half"])

    def test_etf_dashboard_path_shape_metrics_are_present(self):
        snapshot = technicals.calculate_snapshot(
            "TEST",
            synthetic_rows(panic=False),
            benchmark_rows=None,
            benchmark="SPY",
            source="synthetic",
        )
        shape = snapshot["capitulation"]["path_shape"]
        self.assertIsNotNone(shape["volatility_concentration_ratio_20d"])
        self.assertIsNotNone(shape["trend_ratio_20d"])
        self.assertIsNotNone(shape["downside_variance_share_20d"])
        self.assertEqual(snapshot["data_grade"], "A")


if __name__ == "__main__":
    unittest.main()
