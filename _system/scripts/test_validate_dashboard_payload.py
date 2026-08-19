#!/usr/bin/env python3
"""Regression tests for dashboard payload shape and GitHub size limits."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from validate_dashboard_data import (  # noqa: E402
    DATA_PATH,
    GITHUB_HARD_LIMIT_BYTES,
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


if __name__ == "__main__":
    raise SystemExit(unittest.main())
