import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from build_dashboard_data import valuation_decision_summary


class DashboardValuationPublishingTests(unittest.TestCase):
    def test_blocked_return_is_not_published_to_front_page(self):
        workbench = {
            "decision": {
                "status": "evidence_blocked",
                "annualized_return_at_price_pct": {"base": 168.08},
                "value_per_share": {"base": 51_299.85},
            },
            "evidence": {"open_count": 1, "critical_count": 1},
        }
        summary = valuation_decision_summary(
            "TEST", Path("TEST"), workbench=workbench, component={}
        )
        self.assertEqual(summary["status"], "evidence_blocked")
        self.assertIsNone(summary["annualized_return_at_price_pct"])

    def contract_summary(self, contract: dict, workbench: dict | None = None) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            ticker_dir = Path(tmp) / "TEST"
            research = ticker_dir / "research"
            research.mkdir(parents=True)
            (research / "valuation_contract.json").write_text(
                json.dumps(contract), encoding="utf-8"
            )
            return valuation_decision_summary(
                "TEST",
                ticker_dir,
                workbench=workbench or {
                    "decision": {"status": contract.get("status")},
                    "evidence": {"open_count": 0, "critical_count": 0},
                },
                component={},
            )

    def test_present_value_contract_does_not_publish_a_forward_return(self):
        summary = self.contract_summary({
            "schema_version": "3.0",
            "status": "decision_grade",
            "proof_status": "decision_grade",
            "model_level": "stock_specific",
            "market": {"price_per_share": 80},
            "valuation": {
                "output_basis": "present_value_today",
                "present_value_today_per_share": {"low": 90, "base": 100, "high": 110},
                "forward_return_at_price_pct": {"low": None, "base": None, "high": None},
                "forward_return_status": "withheld",
                "margin_of_safety_pct": {"low": 11.11, "base": 20, "high": 27.27},
            },
        })
        self.assertFalse(summary["return_publishable"])
        self.assertIsNone(summary["forward_return_at_price_pct"])
        self.assertEqual(summary["margin_of_safety_pct"]["base"], 20)

    def test_stock_specific_dated_forward_return_is_publishable(self):
        summary = self.contract_summary({
            "schema_version": "3.0",
            "status": "decision_grade",
            "proof_status": "decision_grade",
            "model_level": "stock_specific",
            "market": {"price_per_share": 80},
            "valuation": {
                "output_basis": "future_payoff",
                "present_value_today_per_share": {"low": 90, "base": 100, "high": 110},
                "forward_return_at_price_pct": {"low": 6, "base": 12.5, "high": 18},
                "forward_return_status": "available",
                "margin_of_safety_pct": {"low": 11.11, "base": 20, "high": 27.27},
            },
        })
        self.assertTrue(summary["return_publishable"])
        self.assertEqual(summary["forward_return_at_price_pct"]["base"], 12.5)
        self.assertEqual(summary["annualized_return_at_price_pct"]["base"], 12.5)

    def test_generic_screen_cannot_publish_even_a_dated_return(self):
        summary = self.contract_summary({
            "schema_version": "3.0",
            "status": "decision_grade",
            "proof_status": "decision_grade",
            "model_level": "screening_grade",
            "valuation": {
                "output_basis": "future_payoff",
                "present_value_today_per_share": {"base": 100},
                "forward_return_at_price_pct": {"low": 5, "base": 12.5, "high": 20},
                "forward_return_status": "available",
            },
        })
        self.assertFalse(summary["return_publishable"])
        self.assertIsNone(summary["forward_return_at_price_pct"])


if __name__ == "__main__":
    unittest.main()
