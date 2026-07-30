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

    def test_decision_grade_return_remains_publishable(self):
        workbench = {
            "decision": {
                "status": "decision_grade",
                "annualized_return_at_price_pct": {"base": 12.5},
                "value_per_share": {"base": 100},
            },
            "evidence": {"open_count": 0, "critical_count": 0},
        }
        summary = valuation_decision_summary(
            "TEST", Path("TEST"), workbench=workbench, component={}
        )
        self.assertEqual(
            summary["annualized_return_at_price_pct"]["base"], 12.5
        )


if __name__ == "__main__":
    unittest.main()
