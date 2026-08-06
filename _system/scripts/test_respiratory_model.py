#!/usr/bin/env python3
"""Tests for the respiratory demand panel and the QDEL respiratory baseline model."""
from __future__ import annotations

import json
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from build_kpi_trends import (  # noqa: E402
    apply_display_cap,
    metric_tier,
    respiratory_context_metric,
    respiratory_context_tickers,
    respiratory_quarterly_volume,
)
from build_qdel_respiratory_model import (  # noqa: E402
    loocv_dollars,
    ols_fit,
    r_squared,
    seasonal_dummies,
)


class OlsTests(unittest.TestCase):
    def test_recovers_known_line(self) -> None:
        xs = [0.0, 1.0, 2.0, 3.0, 4.0]
        y = [3.0 + 2.0 * x for x in xs]
        coefs = ols_fit([[1.0, x] for x in xs], y)
        self.assertAlmostEqual(coefs[0], 3.0, places=6)
        self.assertAlmostEqual(coefs[1], 2.0, places=6)

    def test_singular_design_returns_none(self) -> None:
        X = [[1.0, 1.0], [1.0, 1.0], [1.0, 1.0]]
        self.assertIsNone(ols_fit(X, [1.0, 2.0, 3.0]))

    def test_perfect_fit_r_squared_is_one(self) -> None:
        xs = [1.0, 2.0, 3.0, 4.0]
        y = [2.0 * x for x in xs]
        self.assertAlmostEqual(r_squared([[1.0, x] for x in xs], y), 1.0, places=6)

    def test_loocv_penalises_overfitting(self) -> None:
        """A model with as many parameters as points fits perfectly but predicts badly."""
        xs = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
        y = [1.0, 3.0, 2.0, 5.0, 4.0, 6.0, 5.0, 8.0]
        simple = loocv_dollars([[1.0, x] for x in xs], y, y, log_space=False)
        noisy = loocv_dollars([[1.0, x, x * x, x ** 3, x ** 4] for x in xs], y, y, log_space=False)
        self.assertIsNotNone(simple)
        self.assertIsNotNone(noisy)
        self.assertLess(simple, noisy)

    def test_log_space_loocv_back_transforms(self) -> None:
        y = [10.0, 20.0, 40.0, 80.0, 160.0]
        ly = [math.log(v) for v in y]
        X = [[1.0, float(i)] for i in range(len(y))]
        err = loocv_dollars(X, ly, y, log_space=True)
        self.assertIsNotNone(err)
        self.assertLess(err, 1.0)  # exact exponential -> near-zero error in dollars


class SeasonalDummyTests(unittest.TestCase):
    def test_q1_is_the_base_level(self) -> None:
        self.assertEqual(seasonal_dummies("2025Q1"), [0.0, 0.0, 0.0])

    def test_each_quarter_sets_one_flag(self) -> None:
        for label, expected in (("2025Q2", 0), ("2025Q3", 1), ("2025Q4", 2)):
            dummies = seasonal_dummies(label)
            self.assertEqual(sum(dummies), 1.0)
            self.assertEqual(dummies[expected], 1.0)


class RespiratoryPanelTests(unittest.TestCase):
    def test_quarterly_buckets_are_complete_quarters(self) -> None:
        quarters = respiratory_quarterly_volume()
        if not quarters:
            self.skipTest("respiratory panel not fetched")
        self.assertTrue(all(v["weeks"] >= 12 for v in quarters.values()))

    def test_context_metric_is_tiered_as_context(self) -> None:
        metric = respiratory_context_metric()
        if metric is None:
            self.skipTest("respiratory panel not fetched")
        self.assertEqual(metric["tier"], "context")
        self.assertEqual(metric["signal_tier"], "context")
        self.assertEqual(metric["source"], "respiratory_panel")
        self.assertEqual(metric_tier("respiratory_test_volume"), "context")

    def test_summary_reads_cleanly_in_every_direction(self) -> None:
        metric = respiratory_context_metric()
        if metric is None:
            self.skipTest("respiratory panel not fetched")
        summary = metric["human_summary"]
        self.assertNotIn("  ", summary)
        self.assertTrue(summary.endswith("not a revenue estimate."))
        self.assertIn(metric["latest_period"], summary)

    def test_threshold_is_data_driven_not_zero(self) -> None:
        metric = respiratory_context_metric()
        if metric is None:
            self.skipTest("respiratory panel not fetched")
        self.assertGreaterEqual(metric["threshold"], 0.10)


class DisplayCapTests(unittest.TestCase):
    """Context rows must never consume a fundamentals display slot."""

    def _fundamental(self, metric: str, strength: float) -> dict:
        return {
            "metric": metric, "tier": "primary", "direction": "decelerating",
            "signal_tier": "emerging", "accel": -0.5, "threshold": 0.1,
            "strength": strength, "display": False,
        }

    def test_context_row_does_not_crowd_out_fundamentals(self) -> None:
        context = {
            "metric": "respiratory_test_volume", "tier": "context", "signal_tier": "context",
            "direction": "decelerating", "display": True, "strength": 1.0,
        }
        metrics = [context, self._fundamental("revenues", 3.0), self._fundamental("cfo", 2.0)]
        apply_display_cap(metrics)
        fundamentals_shown = [m for m in metrics if m.get("display") and m["tier"] != "context"]
        self.assertEqual(len(fundamentals_shown), 2, "both primary signals should still display")
        self.assertTrue(context["display"], "context row should remain displayed")

    def test_context_row_survives_the_cap_untouched(self) -> None:
        context = {
            "metric": "respiratory_test_volume", "tier": "context", "signal_tier": "context",
            "direction": "steady", "display": False, "strength": 0.4,
        }
        apply_display_cap([context])
        self.assertFalse(context["display"], "steady context row stays hidden")


class QdelEvidenceTests(unittest.TestCase):
    EVIDENCE = ROOT / "QDEL" / "research" / "evidence" / "respiratory_revenue_quarterly.json"

    def test_evidence_file_is_well_formed(self) -> None:
        doc = json.loads(self.EVIDENCE.read_text(encoding="utf-8"))
        self.assertEqual(doc["ticker"], "QDEL")
        self.assertGreaterEqual(len(doc["observations"]), 13)
        self.assertTrue(doc.get("source_documents"), "revenue figures must cite their source")

    def test_observations_are_chronological_and_positive(self) -> None:
        doc = json.loads(self.EVIDENCE.read_text(encoding="utf-8"))
        ends = [o["period_end"] for o in doc["observations"]]
        self.assertEqual(ends, sorted(ends))
        self.assertTrue(all(o["respiratory_usd_m"] > 0 for o in doc["observations"]))

    def test_respiratory_share_matches_filed_percentage(self) -> None:
        """Q1 FY26: 10-Q states respiratory was 11% of total revenue ($619.8M)."""
        doc = json.loads(self.EVIDENCE.read_text(encoding="utf-8"))
        q1 = next(o for o in doc["observations"] if o["fiscal_quarter"] == "2026Q1")
        self.assertAlmostEqual(q1["respiratory_usd_m"] / 619.8 * 100, 11.0, delta=0.5)


class QdelModelTests(unittest.TestCase):
    MODEL = ROOT / "QDEL" / "research" / "respiratory_model.json"

    def setUp(self) -> None:
        if not self.MODEL.exists():
            self.skipTest("model not built")
        self.doc = json.loads(self.MODEL.read_text(encoding="utf-8"))

    def test_baseline_carries_no_testing_term(self) -> None:
        self.assertEqual(self.doc["baseline"]["specification"], "seasonal_trend_log")

    def test_testing_augmented_specs_rank_below_baseline(self) -> None:
        ladder = {r["specification"]: r["loocv_rmse_usd_m"] for r in self.doc["candidate_ladder"]}
        baseline = ladder["seasonal_trend_log"]
        augmented = [v for k, v in ladder.items() if k.startswith("seasonal_trend_log_plus_")]
        self.assertTrue(augmented, "augmented specs should be evaluated, not skipped")
        for value in augmented:
            self.assertGreater(value, baseline,
                               "a testing term that now helps means the finding has flipped — "
                               "update docs/respiratory-kpi.md before changing this test")

    def test_forward_view_stays_positive(self) -> None:
        for row in self.doc["forward_view"]:
            self.assertGreater(row["point_estimate_usd_m"], 0)
            self.assertGreaterEqual(row["low_usd_m"], 0)

    def test_beats_seasonal_naive_benchmark(self) -> None:
        bench = self.doc["benchmarks"]["seasonal_naive_with_drift"]["rmse_usd_m"]
        model = self.doc["baseline_on_comparable_subset"]["rmse_usd_m"]
        self.assertLess(model, bench)


if __name__ == "__main__":
    unittest.main(verbosity=2)
