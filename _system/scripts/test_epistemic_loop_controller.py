from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

import epistemic_loop_controller as controller


class ControllerTests(unittest.TestCase):
    def _write_prospective_blocked_contract(self, root: Path, components: list[dict]) -> Path:
        research = root / "TST/research"
        (research / "evidence").mkdir(parents=True)
        component_ids = [component["component_id"] for component in components]
        (research / "valuation_contract.json").write_text(json.dumps({
            "status": "evidence_blocked",
            "economic_ownership_map": components,
            "evidence": {
                "blockers": [
                    "prospective_falsifier_gate: new/materially changed components lack "
                    "eligible, source-preflighted v3 forecasts or typed v3 untestable "
                    f"dispositions: {', '.join(component_ids)}"
                ]
            },
            "falsifier_coverage": {
                "prospective_gate": {"missing_components": component_ids}
            },
        }), encoding="utf-8")
        (research / "valuation_route.json").write_text(
            json.dumps({"profile_id": "quality_reinvestment"}), encoding="utf-8")
        (research / "evidence/sec_companyfacts.json").write_text(json.dumps({
            "facts": {"us-gaap": {
                "NetCashProvidedByUsedInOperatingActivities": {},
                "PaymentsToAcquireProductiveAssets": {},
                "CashAndCashEquivalentsAtCarryingValue": {},
            }}
        }), encoding="utf-8")
        policy = root / "_system/config/epistemic_loop_policy.json"
        policy.parent.mkdir(parents=True)
        policy.write_text(json.dumps({"forecast_inventory": {"pilot_size": 5}}),
                          encoding="utf-8")
        return research

    def test_empty_repository_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "_system/research").mkdir(parents=True)
            (root / "_system/research/falsifier_calibration.json").write_text(
                '{"status":"insufficient_outcomes"}\n', encoding="utf-8")
            result = controller.build(root, date(2026, 8, 17), write=True)
            self.assertEqual(result["status"]["health_state"], "BOOTSTRAP_BLOCKED")
            self.assertEqual(result["status"]["eligible_active_forecasts"], 0)
            self.assertTrue((root / controller.QUEUE_REL).exists())
            self.assertTrue(list((root / controller.RUNS_REL).glob("*.json")))

    def test_transition_is_append_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "_system/config").mkdir(parents=True)
            (root / "_system/config/epistemic_loop_policy.json").write_text(
                json.dumps({"leases": {"agent_minutes": 30}}), encoding="utf-8")
            controller.transition(root, "w1", "leased", "test", "agent-a")
            controller.transition(root, "w1", "succeeded", "done", "agent-a")
            rows = (root / controller.STATE_REL).read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(rows), 2)
            self.assertEqual(json.loads(rows[-1])["state"], "succeeded")

    def test_nested_memory_summary_creates_delivery_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "_system/reviews/pending/memory_triage_summary.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({
                "as_of": "2026-08-17",
                "proposal_loop": {"undecided": 3, "routed_delivery_pending": 2},
            }), encoding="utf-8")
            tasks = controller._memory_tasks(root)
            self.assertEqual(len(tasks), 1)
            self.assertIn("3_undecided_proposals", tasks[0]["reason"])
            self.assertIn("2_pending_deliveries", tasks[0]["reason"])

    def test_prospective_only_blocker_still_emits_authoring_tasks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_prospective_blocked_contract(root, [
                {"component_id": "core", "method": "owner_cash_or_dividend_discount"},
                {"component_id": "net_claims", "method": "net_asset_value"},
            ])
            tasks = controller._authoring_tasks(root, {})
            by_component = {task["component_id"]: task for task in tasks}
            self.assertEqual(set(by_component), {"core", "net_claims"})
            self.assertEqual(
                by_component["core"]["metric_definition_id"],
                "normalized_owner_earnings_ttm_m_v2",
            )
            self.assertEqual(
                by_component["net_claims"]["metric_definition_id"],
                "cash_and_equivalents_usd",
            )
            self.assertTrue(all(task["source_preflight_candidate"] for task in tasks))

    def test_rejected_current_draft_returns_to_authoring(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            component = {
                "component_id": "runway",
                "method": "owner_earnings_reinvestment_dcf",
            }
            research = self._write_prospective_blocked_contract(root, [component])
            fingerprint = controller._component_fingerprint(component)
            drafts = research / "falsifier_drafts"
            drafts.mkdir()
            (drafts / "draft-1.json").write_text(json.dumps({
                "draft_id": "draft-1",
                "component_fingerprint": fingerprint,
                "status": "rejected",
                "rejection_reasons": ["source_recipe_stale"],
            }), encoding="utf-8")
            tasks = controller._authoring_tasks(root, {})
            self.assertEqual(len(tasks), 1)
            self.assertEqual(tasks[0]["task_type"], "author_forecast")
            self.assertEqual(tasks[0]["reason"], "forecast_draft_rejected")
            self.assertEqual(tasks[0]["rejection_reasons"], ["source_recipe_stale"])


if __name__ == "__main__":
    unittest.main()
