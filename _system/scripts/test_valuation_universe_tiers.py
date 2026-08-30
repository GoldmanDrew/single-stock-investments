from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import build_valuation_universe_tiers as tiers


class ValuationUniverseTierTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.write("_system/portfolio/registry.json", {
            "holdings": {
                "HELD": {"classification": {"stance": "watch"}},
                "PRIORITY": {"classification": {"stance": "hold"}},
                "COMMITTEE": {"classification": {"stance": "watch"}},
                "BROAD": {"classification": {"stance": "watch"}},
            },
            "watchlist": {},
        })
        self.write("_system/portfolio/valuation_universe_policy.json", {
            "schema_version": "1.0",
            "policy_id": "valuation_universe_tiers_v1",
            "committee_eligible_model_levels": [
                "stock_specific", "committee_reviewed", "owner_approved",
            ],
            "overrides": {},
        })
        self.write("_system/portfolio/paper/taxable.json", {
            "account_id": "taxable",
            "positions": [{"ticker": "HELD", "shares": 10}],
        })
        self.write("_system/portfolio/paper/roth.json", {
            "account_id": "roth",
            "positions": [],
        })
        self.write("_system/portfolio/classification.json", {
            "HELD": {"stance": "watch"},
            "PRIORITY": {"stance": "hold"},
            "COMMITTEE": {"stance": "watch"},
            "BROAD": {"stance": "watch"},
        })
        self.write("_system/reference/valuation_followups.json", {"tickers": {}})

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, relative: str, value: dict) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def build(self) -> dict:
        return tiers.build_manifest(self.root, "2026-08-28")

    def test_registry_holdings_bucket_is_not_active_position_evidence(self):
        manifest = self.build()
        self.assertEqual(manifest["assignments"]["HELD"]["tier"], 1)
        self.assertEqual(manifest["assignments"]["PRIORITY"]["tier"], 2)
        self.assertEqual(manifest["assignments"]["BROAD"]["tier"], 3)
        held_reasons = {row["code"] for row in manifest["assignments"]["HELD"]["assignment_reasons"]}
        broad_reasons = {row["code"] for row in manifest["assignments"]["BROAD"]["assignment_reasons"]}
        self.assertIn("active_paper_position", held_reasons)
        self.assertNotIn("registry_holding", held_reasons)
        self.assertEqual(broad_reasons, {"broad_universe_default"})

    def test_active_committee_workbench_is_imminent_decision(self):
        self.write("COMMITTEE/research/valuation_workbench.json", {
            "decision": {"status": "decision_grade", "model_level": "stock_specific"},
            "committee": {"status": "independent_review_open"},
        })
        manifest = self.build()
        row = manifest["assignments"]["COMMITTEE"]
        self.assertEqual(row["tier_id"], "tier_1")
        self.assertIn("active_committee_workflow", {reason["code"] for reason in row["assignment_reasons"]})

    def test_automated_model_grade_alone_stays_broad_and_non_actionable(self):
        self.write("BROAD/research/valuation_workbench.json", {
            "decision": {"status": "decision_grade", "model_level": "screening_grade"},
            "committee": {"status": "not_started"},
        })
        manifest = self.build()
        row = manifest["assignments"]["BROAD"]
        self.assertEqual(row["tier"], 3)
        self.assertTrue(row["workflow_policy"]["screening_only"])
        self.assertFalse(row["workflow_policy"]["committee_auto_start_allowed"])
        self.assertFalse(row["workflow_policy"]["automated_models_can_authorize_capital"])
        self.assertEqual(row["actionability_cap"], "human_decision_only")

    def test_curated_followup_and_proposed_plan_are_tier_two_only(self):
        self.write("_system/reference/valuation_followups.json", {"tickers": {"BROAD": {}}})
        self.write("_system/portfolio/taxable_target_weights.json", {
            "status": "proposed",
            "weights": [{"ticker": "COMMITTEE", "weight_pct": 5}],
        })
        manifest = self.build()
        self.assertEqual(manifest["assignments"]["BROAD"]["tier"], 2)
        self.assertEqual(manifest["assignments"]["COMMITTEE"]["tier"], 2)

    def test_owner_override_can_promote_or_demote_without_granting_authority(self):
        self.write("_system/portfolio/valuation_universe_policy.json", {
            "schema_version": "1.0",
            "policy_id": "valuation_universe_tiers_v1",
            "committee_eligible_model_levels": ["stock_specific"],
            "overrides": {
                "HELD": {"tier": 3, "reason": "Owner paused research."},
                "BROAD": {"tier": 1, "reason": "Owner requests immediate underwriting."},
            },
        })
        manifest = self.build()
        held = manifest["assignments"]["HELD"]
        broad = manifest["assignments"]["BROAD"]
        self.assertEqual(held["tier"], 3)
        self.assertEqual(broad["tier"], 1)
        self.assertFalse(held["workflow_policy"]["automated_models_can_authorize_capital"])
        self.assertFalse(broad["workflow_policy"]["automated_models_can_authorize_capital"])
        self.assertIn("owner_tier_override", {row["code"] for row in held["assignment_reasons"]})

    def test_missing_required_position_source_is_visible_and_fail_closed(self):
        (self.root / "_system/portfolio/paper/roth.json").unlink()
        manifest = self.build()
        self.assertEqual(manifest["validation"]["status"], "degraded")
        self.assertTrue(any("paper/roth.json" in error for error in manifest["source_errors"]))
        self.assertEqual(manifest["assignments"]["BROAD"]["tier"], 3)

    def test_manifest_is_deterministic_and_complete(self):
        first = self.build()
        second = self.build()
        self.assertEqual(first, second)
        self.assertEqual(first["summary"]["universe_count"], 4)
        self.assertEqual(first["summary"]["assignment_count"], 4)
        self.assertEqual(sum(first["summary"]["tier_counts"].values()), 4)
        self.assertEqual(tiers.validate_manifest(first), [])


if __name__ == "__main__":
    unittest.main()
