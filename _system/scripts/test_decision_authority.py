from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from decision_authority import contract_return_display, resolve_authority


class DecisionAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.research = Path(self.tmp.name) / "AAA" / "research"
        self.research.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name: str, value: dict) -> None:
        (self.research / name).write_text(json.dumps(value), encoding="utf-8")

    def test_evidence_blocked_contract_suppresses_legacy_stance(self):
        valuation = {
            "ticker": "AAA",
            "implied_return": {"base_pct": 99},
            "stance_proposal": {"suggested": "accumulate"},
        }
        self.write("valuation.json", valuation)
        self.write("valuation_contract.json", {"status": "evidence_blocked", "valuation": {}})
        authority = resolve_authority(self.research, valuation)
        self.assertEqual(authority["authority_level"], "valuation_contract")
        self.assertFalse(authority["actionable"])
        self.assertIsNone(authority["stance"])

    def test_human_decision_is_the_only_actionable_authority(self):
        self.write("valuation.json", {"ticker": "AAA"})
        self.write(
            "valuation_contract.json",
            {
                "schema_version": "3.0",
                "status": "decision_grade",
                "model_level": "stock_specific",
                "valuation": {
                    "output_basis": "future_payoff",
                    "forward_return_status": "available",
                    "forward_return_at_price_pct": {"low": 4, "base": 12, "high": 20},
                },
            },
        )
        self.write("human_decision.json", {"status": "decided", "decision": "hold", "sizing": "5%"})
        authority = resolve_authority(self.research)
        self.assertTrue(authority["actionable"])
        self.assertEqual(authority["stance"], "hold")
        self.assertEqual(authority["sizing"], "5%")
        self.assertEqual(contract_return_display(authority), "12% forward return (contract base)")

    def test_legacy_annualized_contract_field_is_not_a_forward_return(self):
        self.write("valuation.json", {"ticker": "AAA"})
        self.write(
            "valuation_contract.json",
            {
                "schema_version": "3.0",
                "status": "decision_grade",
                "model_level": "stock_specific",
                "valuation": {
                    "output_basis": "future_payoff",
                    "forward_return_status": "available",
                    "annualized_return_at_price_pct": {"low": 4, "base": 99, "high": 120},
                },
            },
        )
        authority = resolve_authority(self.research)
        self.assertEqual(authority["return_range_pct"], {"low": None, "base": None, "high": None})
        self.assertIsNone(contract_return_display(authority))

    def test_legacy_is_visible_but_never_actionable(self):
        self.write("valuation.json", {"ticker": "AAA", "approved_stance": "core", "implied_return": {"base_pct": 15}})
        authority = resolve_authority(self.research)
        self.assertEqual(authority["status"], "legacy_only")
        self.assertFalse(authority["actionable"])
        self.assertIsNone(authority["stance"])


if __name__ == "__main__":
    unittest.main()
