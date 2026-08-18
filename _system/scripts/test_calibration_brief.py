from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import build_calibration_brief


class CalibrationBriefTests(unittest.TestCase):
    def test_same_route_minimum_and_source_hashes_are_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            research = root / "_system/research"
            research.mkdir(parents=True)
            (research / "falsifier_calibration.json").write_text(json.dumps({
                "minimum_outcomes": 20,
                "buckets": {"owner_cash|quality": {
                    "method_id": "owner_cash", "power_zone": "quality",
                    "hit": 3, "miss": 6, "unresolvable": 1,
                }},
            }), encoding="utf-8")
            (research / "committee_calibration.json").write_text(json.dumps({
                "persona_power_zones": {"munger:quality": {
                    "persona": "munger", "power_zone": "quality",
                    "completed_outcomes": 21, "expected_range_hit_rate_pct": 60,
                }},
            }), encoding="utf-8")
            brief = build_calibration_brief.build(root)
            self.assertEqual(brief["routes"]["quality"]["falsifier_methods"]
                             ["owner_cash"]["learning_status"],
                             "plumbing_only")
            self.assertEqual(brief["routes"]["quality"]["committee_personas"]
                             ["munger"]["learning_status"], "eligible_for_review")
            self.assertEqual(len(brief["source_hashes"]["falsifier_calibration"]), 64)
            self.assertIsNone(brief["release_hash"])
            self.assertEqual(len(brief["candidate_digest"]), 64)


if __name__ == "__main__":
    unittest.main()
