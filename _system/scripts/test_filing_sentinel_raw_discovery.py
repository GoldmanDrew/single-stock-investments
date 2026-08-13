#!/usr/bin/env python3
"""Tests for raw historical filing discovery helpers."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from filing_sentinel_raw_discovery import RAW_FILING_RE, _section_categories, _term_evidence, comparable_prior, html_to_text  # noqa: E402


class FilingSentinelRawDiscoveryTests(unittest.TestCase):
    def test_filing_name_metadata_pattern(self) -> None:
        match = RAW_FILING_RE.match("10-Q_20260508_rpt20260331_acc0001104659_26_057725.htm")
        self.assertIsNotNone(match)
        self.assertEqual(match.group("form"), "10-Q")
        self.assertEqual(match.group("period"), "20260331")

    def test_html_extraction_removes_markup_and_scripts(self) -> None:
        text = html_to_text("<html><script>ignore()</script><p>Going concern disclosure.</p><div>Cash flow.</div></html>")
        self.assertIn("Going concern disclosure.", text)
        self.assertNotIn("ignore", text)

    def test_new_high_risk_term_has_hashed_evidence(self) -> None:
        item = _term_evidence("The company disclosed a material weakness in internal control.", r"material weakness", evidence_id="ev-1", source_role="current")
        self.assertEqual(item["evidence_id"], "ev-1")
        self.assertEqual(len(item["content_sha256"]), 64)
        self.assertIn("material weakness", item["excerpt"])

    def test_section_categories_route_disclosure(self) -> None:
        categories = _section_categories("Legal proceedings and material weakness in internal control were discussed.")
        self.assertIn("governance_legal", categories)
        self.assertIn("accounting", categories)

    def test_comparable_prior_prefers_prior_year_not_prior_quarter(self) -> None:
        current = {"period_end": "2026-03-31"}
        rows = [
            {"period_end": "2025-03-31", "name": "prior-year"},
            {"period_end": "2025-12-31", "name": "prior-quarter"},
        ]
        self.assertEqual(comparable_prior(current, rows)["name"], "prior-year")


if __name__ == "__main__":
    raise SystemExit(unittest.main())
