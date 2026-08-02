from __future__ import annotations

import math
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "_system" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from criticality.flow_stress import apply_state_hysteresis, calculate_flow_snapshot


def bars(count: int = 90, *, selloff: bool = False) -> list[dict]:
    start = datetime(2026, 7, 29, 13, 30, tzinfo=timezone.utc)
    price = 100.0
    rows = []
    for index in range(count):
        shock = -0.004 * max(0, index - count + 12) if selloff else 0.0
        change = 0.00015 + math.sin(index / 8.0) * 0.0007 + shock
        open_price = price
        price *= 1.0 + change
        spread = 0.001 + (0.004 if selloff and index >= count - 12 else 0.0)
        rows.append({
            "event_time": (start + timedelta(minutes=index)).isoformat(),
            "open": open_price,
            "high": max(open_price, price) * (1 + spread),
            "low": min(open_price, price) * (1 - spread),
            "close": price,
            "volume": 100_000 * (1 + 0.01 * index)
            * (4 if selloff and index >= count - 12 else 1),
        })
    return rows


class FlowStressTest(unittest.TestCase):
    def test_snapshot_has_bounded_scores_and_provenance(self):
        result = calculate_flow_snapshot("SPY", bars())
        self.assertEqual(result["model_version"], "forced-flow-intraday-v1")
        self.assertEqual(result["entitlement_mode"], "live")
        self.assertEqual(result["quality_state"], "ready")
        for value in result["scores"].values():
            if value is not None:
                self.assertGreaterEqual(value, 0)
                self.assertLessEqual(value, 100)

    def test_selloff_increases_pressure(self):
        calm = calculate_flow_snapshot("SPY", bars())
        stress = calculate_flow_snapshot("SPY", bars(selloff=True))
        self.assertGreater(stress["scores"]["pressure"], calm["scores"]["pressure"])
        self.assertGreater(stress["scores"]["panic"], calm["scores"]["panic"])

    def test_short_history_fails_loudly(self):
        with self.assertRaises(ValueError):
            calculate_flow_snapshot("SPY", bars(10))

    def test_hysteresis_requires_dwell_and_delays_downgrade(self):
        state, memory = apply_state_hysteresis("stress", None)
        self.assertEqual(state, "normal")
        state, memory = apply_state_hysteresis("stress", memory)
        self.assertEqual(state, "stress")
        for _ in range(2):
            state, memory = apply_state_hysteresis("normal", memory)
            self.assertEqual(state, "stress")
        state, memory = apply_state_hysteresis("normal", memory)
        self.assertEqual(state, "normal")


if __name__ == "__main__":
    unittest.main()
