import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from investment_committee_pipeline import (
    escalation_decision,
    packet_hash,
    select_raters,
    validate_chair_binding,
    validate_vote,
    vote_set_hash,
)


class InvestmentCommitteePipelineTests(unittest.TestCase):
    def test_packet_hash_is_order_independent(self):
        rows = [
            {"path": "B", "sha256": "b" * 64, "bytes": 2},
            {"path": "A", "sha256": "a" * 64, "bytes": 1},
        ]
        self.assertEqual(packet_hash(rows), packet_hash(list(reversed(rows))))

    def test_vote_set_hash_is_order_independent_and_chair_bound(self):
        votes = [
            {"persona": "b", "independence_group": "two", "vote": "watch"},
            {"persona": "a", "independence_group": "one", "vote": "approve"},
        ]
        packet = "a" * 64
        digest = vote_set_hash(votes, packet)
        self.assertEqual(digest, vote_set_hash(list(reversed(votes)), packet))
        self.assertEqual(validate_chair_binding({
            "evidence_packet_hash": packet,
            "vote_set_hash": digest,
        }, packet, digest), [])
        self.assertTrue(validate_chair_binding({}, packet, digest))

    def test_raters_have_three_distinct_error_profiles(self):
        valuation = {"component_review_queue": {"items": [
            {"recommended_raters": ["hk", "marathon_capital_cycle"]},
            {"recommended_raters": ["hk", "klarman_asset_value"]},
        ]}}
        raters = select_raters(valuation)
        self.assertEqual(len(raters), 3)
        self.assertEqual(len({r["independence_group"] for r in raters}), 3)
        self.assertEqual(raters[0]["persona"], "hk")

    def test_power_zone_route_personas_lead_rater_selection(self):
        valuation = {
            "valuation_method_route": {
                "primary_personas": ["hk", "stahl"],
                "cross_check_personas": ["klarman_asset_value", "marks_credit_cycle"],
                "silent_personas": [
                    "hohn",
                    "pabrai",
                    "buffett_weschler",
                    "greenblatt",
                    "marathon_capital_cycle",
                ],
            },
            "component_review_queue": {"items": [{"recommended_raters": ["pabrai"]}]},
        }
        raters = select_raters(valuation)
        personas = [r["persona"] for r in raters]
        self.assertEqual(personas, ["hk", "klarman_asset_value", "marks_credit_cycle"])
        self.assertEqual(len({r["independence_group"] for r in raters}), 3)
        self.assertNotIn("pabrai", personas)
        self.assertIn("power-zone method route", raters[0]["selection_reason"])

    def test_silenced_route_without_three_groups_raises(self):
        valuation = {
            "valuation_method_route": {
                "primary_personas": ["hk", "stahl"],
                "cross_check_personas": [],
                "silent_personas": [
                    "hohn",
                    "pabrai",
                    "buffett_weschler",
                    "greenblatt",
                    "marathon_capital_cycle",
                    "marks_credit_cycle",
                    "klarman_asset_value",
                    "munger",
                    "moi",
                ],
            },
        }
        with self.assertRaises(ValueError):
            select_raters(valuation)

    def test_incomplete_vote_is_rejected(self):
        expected = {"persona": "hk", "independence_group": "scarce_assets"}
        errors = validate_vote({"persona": "hk", "independence_group": "scarce_assets"}, expected)
        self.assertIn("all four calibrated scores are required", errors)
        self.assertIn("invalid vote", errors)

    def test_unanimous_sufficient_round_does_not_escalate(self):
        votes = []
        for _ in range(3):
            votes.append({
                "vote": "approve",
                "evidence_status": "sufficient",
                "scores": {dim: {"value": 4, "rationale": "clear"} for dim in (
                    "explanatory_strength", "evidence_sufficiency", "downside_control", "return_vs_alternatives"
                )},
                "expected_return_range_pct": [12, 18],
            })
        result = escalation_decision(votes)
        self.assertFalse(result["required"])
        self.assertEqual(result["baseline_llm_calls"], 5)

    def test_insufficient_evidence_admits_targeted_research_and_second_round(self):
        votes = []
        for index in range(3):
            votes.append({
                "vote": "defer" if index == 0 else "watch",
                "evidence_status": "insufficient_evidence" if index == 0 else "sufficient",
                "scores": {dim: {"value": 2 + index, "rationale": "varies"} for dim in (
                    "explanatory_strength", "evidence_sufficiency", "downside_control", "return_vs_alternatives"
                )},
                "expected_return_range_pct": [5 + index, 10 + index],
            })
        result = escalation_decision(votes)
        self.assertTrue(result["required"])
        self.assertTrue(result["research_required"])
        self.assertEqual(result["maximum_llm_calls"], 9)


if __name__ == "__main__":
    unittest.main()
