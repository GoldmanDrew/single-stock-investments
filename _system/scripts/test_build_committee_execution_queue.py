from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_committee_execution_queue as queue


class CommitteeExecutionQueueTests(unittest.TestCase):
    def test_blocked_research_never_emits_review_task_and_active_packet_does(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for ticker, state in (("BLOCK", "research_blocked"), ("LIVE", "committee_in_progress")):
                work = root / ticker / "research" / "committee_work" / "2026-09-01"
                work.mkdir(parents=True)
                (work / "manifest.json").write_text(json.dumps({
                    "packet_hash": "a" * 64,
                }), encoding="utf-8")
                (root / ticker / "research" / "valuation_workbench.json").write_text(json.dumps({
                    "committee": {
                        "as_of": "2026-09-01", "current_phase": "isolated_round_one",
                        "analysis_progress": {"completed": 1, "required": 13},
                        "next_outputs": ["pre_mortem.json", "round_1/hohn.json"],
                    },
                }), encoding="utf-8")
            readiness = {"as_of": "2026-09-01", "items": [
                {"ticker": "BLOCK", "readiness_state": "research_blocked", "next_action": "fix"},
                {"ticker": "LIVE", "readiness_state": "committee_in_progress", "next_action": "vote"},
            ]}
            with patch.object(queue, "build_readiness", return_value=readiness):
                result = queue.build(root=root)
        self.assertEqual(result["items"][0]["review_tasks"], [])
        self.assertEqual(
            [row["task_id"] for row in result["items"][1]["review_tasks"]],
            ["pre_mortem", "round1-hohn"],
        )
        self.assertEqual(result["summary"]["review_task_count"], 2)


if __name__ == "__main__":
    unittest.main()
