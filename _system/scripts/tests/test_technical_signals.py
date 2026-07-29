from __future__ import annotations

import importlib.util
import math
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "build_technical_signals",
    ROOT / "_system" / "scripts" / "build_technical_signals.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def price_rows(days: int, daily_return: float, *, volume_base: float = 1_000_000) -> list[dict]:
    start = date(2022, 1, 3)
    price = 100.0
    rows = []
    for index in range(days):
        price *= 1.0 + daily_return + math.sin(index / 17) * 0.002
        rows.append(
            {
                "date": (start + timedelta(days=index)).isoformat(),
                "close": price,
                "volume": volume_base * (1.0 + math.sin(index / 13) * 0.1),
            }
        )
    return rows


class TechnicalSignalsTest(unittest.TestCase):
    def test_snapshot_contains_bounded_reproducible_scores(self):
        stock = price_rows(900, 0.0010)
        benchmark = price_rows(900, 0.0003)
        snapshot = MODULE.calculate_snapshot(
            "TEST",
            stock,
            benchmark_rows=benchmark,
            benchmark="SPY",
            source="synthetic:test",
        )
        self.assertEqual(snapshot["data_quality"], "ready")
        self.assertEqual(snapshot["model_version"], "technical-z-v1")
        self.assertEqual(len(snapshot["history"]), 260)
        for value in snapshot["scores"].values():
            if value is not None:
                self.assertLessEqual(abs(value), 4.0)
        self.assertIn(
            snapshot["regime"]["setup"],
            {"improving", "deteriorating", "extended", "washed_out", "neutral"},
        )

    def test_missing_benchmark_degrades_without_inventing_relative_strength(self):
        snapshot = MODULE.calculate_snapshot(
            "TEST",
            price_rows(400, 0.0002),
            benchmark_rows=None,
            benchmark="SPY",
            source="synthetic:test",
        )
        self.assertIsNone(snapshot["scores"]["relative_strength_60d_z"])
        self.assertIsNotNone(snapshot["scores"]["trend_z"])

    def test_technicals_do_not_contain_valuation_authority_fields(self):
        snapshot = MODULE.calculate_snapshot(
            "TEST",
            price_rows(400, 0.0002),
            benchmark_rows=price_rows(400, 0.0001),
            benchmark="SPY",
            source="synthetic:test",
        )
        forbidden = {"decision_status", "stance", "provisional", "evidence_blocked"}
        self.assertTrue(forbidden.isdisjoint(snapshot))


if __name__ == "__main__":
    unittest.main()
