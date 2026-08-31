import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import build_tier1_decision_readiness as readiness


class Tier1DecisionReadinessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.write(readiness.POLICY_REL, {
            "policy_id": "test",
            "tier_1_readiness": {
                "minimum_explicit_falsifiers": 1,
                "maximum_age_days": {
                    "model_as_of": 365,
                    "latest_fact_as_of": 180,
                    "price_as_of": 7,
                },
            },
        })

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, relative, payload):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def add_tier1(self, ticker, *, workbench, contract):
        tiers_path = self.root / readiness.TIERS_REL
        tiers = json.loads(tiers_path.read_text(encoding="utf-8")) if tiers_path.exists() else {
            "as_of": "2026-08-30", "assignments": {},
        }
        tiers["assignments"][ticker] = {
            "tier": 1,
            "label": "Active capital decision",
            "assignment_reasons": [{"qualifying_tier": 1, "code": "positive_position"}],
        }
        self.write(readiness.TIERS_REL, tiers)
        self.write(f"{ticker}/research/valuation_workbench.json", workbench)
        self.write(f"{ticker}/research/valuation_contract.json", contract)

    @staticmethod
    def workbench(**overrides):
        payload = {
            "proof_status": "decision_grade",
            "model_level": "stock_specific",
            "dates": {
                "model_as_of": "2026-08-20",
                "latest_fact_as_of": "2026-08-20",
                "price_as_of": "2026-08-29",
            },
            "evidence": {"status": "clear", "open_count": 0, "critical_count": 0, "gaps": []},
            "committee": {"status": "not_started", "owner_status": "pending", "next_action": "Start review."},
            "decision": {},
        }
        payload.update(overrides)
        return payload

    @staticmethod
    def contract(**overrides):
        payload = {
            "proof_status": "decision_grade",
            "model_level": "stock_specific",
            "monitoring": {"falsifiers": ["Observable failure"]},
        }
        payload.update(overrides)
        return payload

    def test_critical_evidence_precedes_model_and_committee_work(self):
        blocked = self.workbench(
            proof_status="evidence_blocked",
            model_level="evidence_blocked",
            evidence={
                "status": "critical_gaps_open", "open_count": 2, "critical_count": 1,
                "gaps": [{"id": "source", "priority": "critical", "status": "open", "acceptance_test": "Reconcile the filing."}],
            },
        )
        self.add_tier1("BLOCK", workbench=blocked, contract=self.contract(proof_status="evidence_blocked"))
        self.add_tier1("READY", workbench=self.workbench(), contract=self.contract())

        payload = readiness.build("2026-08-30", self.root)

        self.assertEqual([row["ticker"] for row in payload["items"]], ["BLOCK", "READY"])
        first = payload["items"][0]
        self.assertEqual(first["readiness_state"], "research_blocked")
        self.assertEqual(first["priority"]["bucket"], "critical_evidence")
        self.assertEqual(first["next_action"], "Reconcile the filing.")

    def test_screening_model_is_deepening_work_not_committee_ready(self):
        self.add_tier1(
            "SCREEN",
            workbench=self.workbench(model_level="screening_grade"),
            contract=self.contract(model_level="screening_grade"),
        )

        row = readiness.build("2026-08-30", self.root)["items"][0]

        self.assertEqual(row["readiness_state"], "model_deepening_required")
        self.assertIn("stock_specific_model_required", {item["code"] for item in row["blockers"]})

    def test_failed_proof_does_not_inherit_a_committee_action(self):
        self.add_tier1(
            "PROOF",
            workbench=self.workbench(
                proof_status="evidence_blocked",
                model_level="evidence_blocked",
                committee={"status": "independent_review_open", "next_action": "Complete the vote."},
            ),
            contract=self.contract(proof_status="evidence_blocked"),
        )

        row = readiness.build("2026-08-30", self.root)["items"][0]

        self.assertEqual(row["priority"]["bucket"], "proof_completion")
        self.assertIn("contract proof", row["next_action"])
        self.assertNotIn("vote", row["next_action"])

    def test_stale_price_blocks_committee_start_and_is_explicit(self):
        workbench = self.workbench()
        workbench["dates"]["price_as_of"] = "2026-08-01"
        self.add_tier1("STALE", workbench=workbench, contract=self.contract())

        row = readiness.build("2026-08-30", self.root)["items"][0]

        self.assertEqual(row["readiness_state"], "freshness_refresh_required")
        self.assertEqual(row["freshness"]["price_as_of"]["age_days"], 29)
        self.assertIn("price_as_of_stale", {item["code"] for item in row["blockers"]})

    def test_ready_model_advances_to_committee_but_never_capital_authority(self):
        self.add_tier1("READY", workbench=self.workbench(), contract=self.contract())

        payload = readiness.build("2026-08-30", self.root)
        row = payload["items"][0]

        self.assertEqual(row["readiness_state"], "committee_ready")
        self.assertEqual(row["next_action"], "Start review.")
        self.assertEqual(payload["semantics"]["capital_authority"], "human_decision_only")
        self.assertEqual(payload["validation"]["status"], "pass")

    def test_output_is_deterministic(self):
        self.add_tier1("READY", workbench=self.workbench(), contract=self.contract())
        first = readiness.build("2026-08-30", self.root)
        second = readiness.build("2026-08-30", self.root)
        self.assertEqual(readiness.render(first), readiness.render(second))


if __name__ == "__main__":
    unittest.main()
