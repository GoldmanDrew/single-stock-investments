#!/usr/bin/env python3
"""Regression tests for dashboard payload shape and GitHub size limits."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from validate_dashboard_data import (  # noqa: E402
    DATA_PATH,
    GITHUB_HARD_LIMIT_BYTES,
    resolve_payload_path,
)


class DashboardPayloadTests(unittest.TestCase):
    def test_dashboard_data_under_github_limit(self):
        self.assertTrue(DATA_PATH.exists(), "dashboard_data.json missing")
        size = DATA_PATH.stat().st_size
        self.assertLess(
            size,
            GITHUB_HARD_LIMIT_BYTES,
            f"dashboard_data.json is {size / (1024 * 1024):.1f}MB",
        )

    def test_dashboard_data_does_not_embed_insights(self):
        payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        self.assertNotIn("insights", payload)
        self.assertEqual(
            (payload.get("insights_ref") or {}).get("path"),
            "dashboard/data/insights/manifest.json",
        )

    def test_deploy_only_prefers_the_payload_the_spa_boots_from(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            monolith = root / "dashboard_data.json"
            core = root / "core.json"
            monolith.write_text("{}", encoding="utf-8")
            core.write_text("{}", encoding="utf-8")
            self.assertEqual(
                resolve_payload_path(monolith=monolith, core=core, deploy_only=True),
                core,
            )

    def test_full_build_validation_still_prefers_the_monolith(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            monolith = root / "dashboard_data.json"
            core = root / "core.json"
            monolith.write_text("{}", encoding="utf-8")
            core.write_text("{}", encoding="utf-8")
            self.assertEqual(
                resolve_payload_path(monolith=monolith, core=core, deploy_only=False),
                monolith,
            )


if __name__ == "__main__":
    raise SystemExit(unittest.main())
