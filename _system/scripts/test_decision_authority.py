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
                "status": "decision_grade",
                "valuation": {"forward_return_at_price_pct": {"low": 4, "base": 12, "high": 20}},
            },
        )
        self.write("human_decision.json", {"status": "decided", "decision": "hold", "sizing": "5%"})
        authority = resolve_authority(self.research)
        self.assertTrue(authority["actionable"])
        self.assertEqual(authority["stance"], "hold")
        self.assertEqual(authority["sizing"], "5%")
        self.assertEqual(authority["model_level"], "owner_approved")
        self.assertEqual(contract_return_display(authority), "12% (forward return, contract base)")

    def test_old_annualized_value_gap_is_audit_only(self):
        valuation = {"ticker": "AAA", "method": "full"}
        self.write("valuation.json", valuation)
        self.write(
            "valuation_contract.json",
            {
                "status": "decision_grade",
                "valuation": {
                    "annualized_return_at_price_pct": {"low": 4, "base": 99, "high": 120},
                },
            },
        )
        authority = resolve_authority(self.research, valuation)
        self.assertEqual(authority["model_level"], "stock_specific")
        self.assertEqual(authority["return_range_pct"], {"low": None, "base": None, "high": None})
        self.assertFalse(authority["return_publishable"])
        self.assertIsNone(contract_return_display(authority))

    def test_screening_model_cannot_publish_even_canonical_forward_return(self):
        valuation = {
            "ticker": "AAA",
            "method": "proof_first_automated",
            "valuation_methodology": {"automation": "source_locked_first_pass"},
            "component_valuation_results": {
                "additive_components": [{
                    "id": "operating_business_and_net_assets",
                    "method": "owner_earnings_reinvestment_dcf",
                }],
            },
        }
        self.write("valuation.json", valuation)
        self.write(
            "valuation_contract.json",
            {
                "status": "decision_grade",
                "valuation": {"forward_return_at_price_pct": {"base": 22}},
            },
        )
        authority = resolve_authority(self.research, valuation)
        self.assertEqual(authority["model_level"], "screening_grade")
        self.assertIsNone(authority["return_range_pct"]["base"])
        self.assertIsNone(contract_return_display(authority))

    def test_legacy_is_visible_but_never_actionable(self):
        self.write("valuation.json", {"ticker": "AAA", "approved_stance": "core", "implied_return": {"base_pct": 15}})
        authority = resolve_authority(self.research)
        self.assertEqual(authority["status"], "legacy_only")
        self.assertFalse(authority["actionable"])
        self.assertIsNone(authority["stance"])


if __name__ == "__main__":
    unittest.main()
