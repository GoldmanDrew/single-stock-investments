from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from build_committee_monitoring import build
from freeze_committee_forecasts import freeze
import record_committee_forecast_outcomes as recorder


class CommitteeForecastLoopTests(unittest.TestCase):
    def test_freezes_and_schedules_non_actionable_forecast_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            research = root / "TST/research"
            research.mkdir(parents=True)
            (research / "committee_2026-01-15.json").write_text(json.dumps({
                "ticker": "TST", "final_state": "owner_decision_pending",
                "review": {"as_of": "2026-01-15"},
                "evidence_packet": {"packet_hash": "abc"},
                "round_two": {"votes": [{"reviewer": "risk", "stance": "defer"}]}
            }), encoding="utf-8")
            self.assertEqual(len(freeze(root)), 1)
            self.assertEqual(len(freeze(root)), 0)
            monitoring = build("2026-02-15", root)
            self.assertEqual(monitoring["counts"]["due"], 1)
            self.assertEqual(monitoring["items"][0]["item_type"], "committee_forecast")

    def test_incomplete_return_stays_retryable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            research = root / "_system/research"
            research.mkdir(parents=True)
            (research / "committee_forecasts.jsonl").write_text(json.dumps({
                "forecast_id": "f1", "ticker": "TST", "forecast_date": "2026-01-01",
                "outcome_horizons_months": [1], "votes": []
            }) + "\n", encoding="utf-8")
            original = recorder.compute_period_total_return
            recorder.compute_period_total_return = lambda *_args: {
                "return_status": "evidence_blocked", "error": "coverage missing"}
            try:
                result = recorder.record_due(root, "2026-02-01")
            finally:
                recorder.compute_period_total_return = original
            self.assertEqual(result["recorded"], 0)
            self.assertEqual(result["attempts"], 1)
            self.assertEqual((research / "committee_forecast_outcomes.jsonl").read_text(), "")
            self.assertEqual(build("2026-02-01", root)["counts"]["due"], 1)


if __name__ == "__main__":
    unittest.main()
