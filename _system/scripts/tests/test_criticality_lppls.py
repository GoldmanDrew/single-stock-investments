from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "_system" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from criticality.lppls import fit_ensemble, fit_lppls


def synthetic_lppls(
    count: int = 240,
    *,
    tc: float = 265.0,
    m: float = 0.52,
    omega: float = 8.4,
    b: float = -0.16,
) -> list[float]:
    values = []
    for index in range(count):
        dt = tc - index
        f = dt**m
        log_price = (
            5.2
            + b * f
            + 0.012 * f * math.cos(omega * math.log(dt))
            - 0.007 * f * math.sin(omega * math.log(dt))
        )
        values.append(math.exp(log_price))
    return values


class LpplsTest(unittest.TestCase):
    def test_fit_recovers_direction_and_critical_time(self):
        prices = synthetic_lppls()
        fit = fit_lppls(prices, max_nfev=300)
        self.assertEqual(fit.direction, "positive_bubble")
        self.assertAlmostEqual(fit.tc_index, 265.0, delta=8.0)
        self.assertGreater(fit.omega, 6.0)
        self.assertLess(fit.omega, 13.0)

    def test_negative_bubble_direction(self):
        fit = fit_lppls(synthetic_lppls(b=0.16), max_nfev=300)
        self.assertEqual(fit.direction, "negative_bubble")

    def test_ensemble_is_bounded_and_exposes_uncertainty(self):
        result = fit_ensemble(
            synthetic_lppls(count=300, tc=330),
            horizons=(120, 250),
            nested_fractions=(0.8, 0.9, 1.0),
            max_nfev=220,
        )
        self.assertEqual(result["model_version"], "lppls-ensemble-v1")
        self.assertLessEqual(result["fit_count"], result["attempted_count"])
        self.assertGreater(result["fit_count"], 0)
        for value in result["confidence"].values():
            self.assertGreaterEqual(value, 0)
            self.assertLessEqual(value, 100)
        self.assertIn("critical_time", result)
        self.assertIn("policy", result)

    def test_invalid_prices_fail_loudly(self):
        with self.assertRaises(ValueError):
            fit_lppls([100.0] * 39)
        with self.assertRaises(ValueError):
            fit_lppls([100.0] * 50 + [0.0])


if __name__ == "__main__":
    unittest.main()
