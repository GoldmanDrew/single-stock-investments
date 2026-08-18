from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

import epistemic_loop_controller as controller


class ControllerTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
