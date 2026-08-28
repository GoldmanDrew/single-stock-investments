import sys
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
                "model_level": "evidence_blocked",
                "return_publishable": False,
                "annualized_return_at_price_pct": {"base": 168.08},
                "value_per_share": {"base": 51_299.85},
            },
            "evidence": {"open_count": 1, "critical_count": 1},
        }
        summary = valuation_decision_summary(
            "TEST", Path("TEST"), workbench=workbench, component={}
        )
        self.assertEqual(summary["status"], "evidence_blocked")
        self.assertEqual(summary["model_level"], "evidence_blocked")
        self.assertIsNone(summary["forward_return_at_price_pct"])
        self.assertIsNone(summary["annualized_return_at_price_pct"])

    def test_stock_specific_canonical_forward_return_is_publishable(self):
        workbench = {
            "decision": {
                "status": "decision_grade",
                "contract_status": "decision_grade",
                "model_level": "stock_specific",
                "return_publishable": True,
                "forward_return_at_price_pct": {"base": 12.5},
                "value_per_share": {"base": 100},
            },
            "evidence": {"open_count": 0, "critical_count": 0},
        }
        summary = valuation_decision_summary(
            "TEST", Path("TEST"), workbench=workbench, component={}
        )
        self.assertEqual(summary["model_level"], "stock_specific")
        self.assertEqual(summary["forward_return_at_price_pct"]["base"], 12.5)
        self.assertEqual(
            summary["annualized_return_at_price_pct"]["base"], 12.5
        )

    def test_old_annualized_return_is_audit_only_even_when_contract_passed(self):
        workbench = {
            "decision": {
                "status": "decision_grade",
                "model_level": "stock_specific",
                "annualized_return_at_price_pct": {"base": 44.0},
                "value_per_share": {"base": 100},
            },
            "evidence": {"open_count": 0, "critical_count": 0},
        }
        summary = valuation_decision_summary(
            "TEST", Path("TEST"), workbench=workbench, component={}
        )
        self.assertIsNone(summary["forward_return_at_price_pct"])
        self.assertFalse(summary["return_publishable"])
        self.assertEqual(
            summary["legacy_audit"]["annualized_return_at_price_pct"]["base"],
            44.0,
        )

    def test_screening_grade_never_publishes_forward_return(self):
        workbench = {
            "decision": {
                "status": "decision_grade",
                "model_level": "screening_grade",
                "return_publishable": True,
                "forward_return_at_price_pct": {"base": 99.0},
                "value_per_share": {"base": 100},
            },
            "evidence": {"open_count": 0, "critical_count": 0},
        }
        summary = valuation_decision_summary(
            "TEST", Path("TEST"), workbench=workbench, component={}
        )
        self.assertEqual(summary["model_level"], "screening_grade")
        self.assertIsNone(summary["forward_return_at_price_pct"])


if __name__ == "__main__":
    unittest.main()
