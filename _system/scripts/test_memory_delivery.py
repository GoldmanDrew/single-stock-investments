from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import deliver_routed_memory


class MemoryDeliveryTests(unittest.TestCase):
    def test_only_real_research_destinations_are_acknowledged_idempotently(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "QDEL/research").mkdir(parents=True)
            ledger_path = root / "_system/memory/triage_ledger.json"
            ledger_path.parent.mkdir(parents=True)
            decisions = {
                "good": {
                    "decision": "routed", "destination": "QDEL/research",
                    "delivery_status": "pending", "content": "QDEL lead",
                    "source_ref": "_system/memory/daily/2026-08-11.md",
                    "date": "2026-08-17",
                },
                "ambiguous": {
                    "decision": "routed",
                    "destination": "_system/memory/triage_ledger.json",
                    "delivery_status": "pending", "content": "unknown lead",
                    "source_ref": "_system/memory/daily/2026-08-11.md",
                    "date": "2026-08-17",
                },
            }
            ledger_path.write_text(json.dumps({"version": 2, "decisions": decisions}),
                                   encoding="utf-8")

            first = deliver_routed_memory.deliver(root)
            second = deliver_routed_memory.deliver(root)
            self.assertEqual(first, {"eligible": 1, "written": 1,
                                     "acknowledged": 1, "ambiguous_pending": 1})
            self.assertEqual(second["written"], 0)
            rows = (root / deliver_routed_memory.INBOX_REL).read_text(
                encoding="utf-8").splitlines()
            self.assertEqual(len(rows), 1)
            self.assertEqual(json.loads(rows[0])["status"], "proposed_observation")
            projected = json.loads(ledger_path.read_text(encoding="utf-8"))["decisions"]
            self.assertEqual(projected["good"]["delivery_status"], "acknowledged")
            self.assertEqual(projected["ambiguous"]["delivery_status"], "pending")


if __name__ == "__main__":
    unittest.main()
