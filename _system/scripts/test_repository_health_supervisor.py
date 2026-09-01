from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import supervise_repository_health as supervisor


class RepositoryHealthSupervisorTests(unittest.TestCase):
    def test_receipt_and_feed_health_are_evaluated_without_graph_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = {
                "lanes": [{"name": "daily", "freshness_hours": 48}],
                "data_feeds": {
                    "sample": {"path": "dashboard/data/sample.json",
                               "stamp_field": "generated_at", "max_age_hours": 24,
                               "healer": "refresh sample"},
                },
            }
            graph = root / "_system/graph/graph_sources.json"
            graph.parent.mkdir(parents=True)
            graph.write_text(json.dumps(config), encoding="utf-8")
            receipt = root / "_system/data/lane_receipts/daily.json"
            receipt.parent.mkdir(parents=True)
            receipt.write_text(json.dumps({"last_success_at": "2026-08-17T10:00:00Z"}),
                               encoding="utf-8")
            feed = root / "dashboard/data/sample.json"
            feed.parent.mkdir(parents=True)
            feed.write_text(json.dumps({"generated_at": "2026-08-17T09:00:00Z"}),
                            encoding="utf-8")
            failures = supervisor.operational_failures(
                root, datetime(2026, 8, 17, 12, tzinfo=timezone.utc))
            self.assertEqual(failures, [])
            receipt.unlink()
            feed.write_text(json.dumps({"generated_at": "2026-08-15T09:00:00Z"}),
                            encoding="utf-8")
            failures = supervisor.operational_failures(
                root, datetime(2026, 8, 17, 12, tzinfo=timezone.utc))
            self.assertTrue(any(row.startswith("P3|") for row in failures))
            self.assertTrue(any(row.startswith("P6|") for row in failures))

    def test_stale_operational_lanes_dispatch_bounded_healers_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            graph = root / "_system/graph/graph_sources.json"
            graph.parent.mkdir(parents=True)
            graph.write_text(json.dumps({
                "lanes": [
                    {"name": "memory-digest", "freshness_hours": 24},
                    {"name": "market-risk", "freshness_hours": 24},
                    {"name": "research-watchdog", "freshness_hours": 24},
                ],
                "data_feeds": {},
            }), encoding="utf-8")
            with mock.patch.object(supervisor, "_head", return_value="abc"):
                result = supervisor.plan(root)
            self.assertEqual(result["dispatches"], [
                {"event_type": "memory-triage-run"},
                {"event_type": "heal-market-risk"},
                {"event_type": "research-watchdog-run"},
            ])

    def test_lane_workflows_install_and_order_their_recovery_dependencies(self):
        root = Path(__file__).resolve().parents[2]
        memory = (root / ".github/workflows/memory-digest.yml").read_text(encoding="utf-8")
        self.assertLess(memory.index("pip install"), memory.index("python -m pytest"))
        self.assertIn("types: [memory-triage-run]", memory)

        falsifier = (root / ".github/workflows/falsifier-resolution.yml").read_text(encoding="utf-8")
        self.assertIn("types: [falsifier-resolution-run]", falsifier)

        market = (root / ".github/workflows/market-risk-components.yml").read_text(encoding="utf-8")
        self.assertLess(
            market.index("Commit daily dashboard fallback snapshot"),
            market.index("Publish signed component snapshot"),
        )
        publish_block = market.split("name: Publish signed component snapshot", 1)[1]
        self.assertIn("continue-on-error: true", publish_block)


if __name__ == "__main__":
    unittest.main()
