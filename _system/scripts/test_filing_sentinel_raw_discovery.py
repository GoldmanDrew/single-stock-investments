#!/usr/bin/env python3
"""Tests for raw historical filing discovery helpers."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from filing_sentinel_gold import write_jsonl  # noqa: E402
from filing_sentinel_raw_discovery import HIGH_RISK_TERMS, RAW_FILING_RE, _section_categories, _term_evidence, cohort_ledger_issuers, comparable_prior, html_to_text, raw_filings, register_cohort_candidates, validate_cohort_ledger  # noqa: E402


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

    def test_xbrl_restatement_member_is_not_a_restatement_lead(self) -> None:
        pattern = next(pattern for _, tag, pattern, _ in HIGH_RISK_TERMS if tag == "restatement")
        self.assertIsNone(_term_evidence("srt:RestatementAdjustmentMember 2025-03-31", pattern, evidence_id="ev-1", source_role="current"))
        self.assertIsNotNone(_term_evidence("The company will restate prior financial statements.", pattern, evidence_id="ev-1", source_role="current"))

    def test_dismissed_investigation_does_not_become_auditor_change(self) -> None:
        pattern = next(pattern for _, tag, pattern, _ in HIGH_RISK_TERMS if tag == "auditor_change")
        text = "The investigation was officially dismissed with no charges. " + ("other disclosure " * 30) + "The auditor reviewed the statements."
        self.assertIsNone(_term_evidence(text, pattern, evidence_id="ev-1", source_role="current"))
        self.assertIsNotNone(_term_evidence("The company dismissed its independent registered public accounting firm.", pattern, evidence_id="ev-1", source_role="current"))

    def test_comparable_prior_prefers_prior_year_not_prior_quarter(self) -> None:
        current = {"period_end": "2026-03-31"}
        rows = [
            {"period_end": "2025-03-31", "name": "prior-year"},
            {"period_end": "2025-12-31", "name": "prior-quarter"},
        ]
        self.assertEqual(comparable_prior(current, rows)["name"], "prior-year")

    def test_raw_filings_excludes_prior_cohort_issuers(self) -> None:
        # Exclusion is enforced before a prior issuer can consume a cohort slot.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            filing_dir = root / "AAPL" / "investor-documents" / "sec-edgar"
            filing_dir.mkdir(parents=True)
            (filing_dir / "10-Q_20260501_rpt20260331_acc0001_26_000001.htm").write_text("<p>Quarterly report</p>", encoding="utf-8")
            with patch("filing_sentinel_raw_discovery.ROOT", root):
                baseline = raw_filings(universe="all", tickers={"AAPL"}, since="2023-01-01", per_ticker=1, forms={"10-Q"}, max_issuers=1, issuer_offset=0)
                excluded = raw_filings(universe="all", tickers={"AAPL"}, since="2023-01-01", per_ticker=1, forms={"10-Q"}, max_issuers=1, issuer_offset=0, excluded_issuers={"AAPL"})
            self.assertEqual(len(baseline), 1)
            self.assertEqual(excluded, [])

    def test_cohort_ledger_registers_and_excludes_issuers(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            candidates = root / "cohort.jsonl"
            ledger = root / "ledger.jsonl"
            write_jsonl(candidates, [
                {"case_id": "fs-a-1", "ticker": "A", "filing": {"form": "10-Q"}},
                {"case_id": "fs-b-1", "ticker": "B", "filing": {"form": "10-Q"}},
            ])
            result = register_cohort_candidates(ledger, [candidates], as_of="2026-08-14")
            repeated = register_cohort_candidates(ledger, [candidates], as_of="2026-08-14")
            self.assertEqual(result["registered"], 1)
            self.assertEqual(repeated["registered"], 0)
            self.assertEqual(cohort_ledger_issuers(ledger), {"A", "B"})
            self.assertTrue(validate_cohort_ledger(ledger)["valid"])

    def test_cohort_ledger_rejects_issuer_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = root / "first.jsonl"
            second = root / "second.jsonl"
            ledger = root / "ledger.jsonl"
            write_jsonl(first, [{"case_id": "fs-a-1", "ticker": "A", "filing": {"form": "10-Q"}}])
            write_jsonl(second, [{"case_id": "fs-a-2", "ticker": "A", "filing": {"form": "10-K"}}])
            register_cohort_candidates(ledger, [first], as_of="2026-08-14")
            with self.assertRaisesRegex(ValueError, "overlaps registered issuers: A"):
                register_cohort_candidates(ledger, [second], as_of="2026-08-14")

    def test_cohort_ledger_detects_candidate_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            candidates = root / "cohort.jsonl"
            ledger = root / "ledger.jsonl"
            write_jsonl(candidates, [{"case_id": "fs-a-1", "ticker": "A", "filing": {"form": "10-Q"}}])
            register_cohort_candidates(ledger, [candidates], as_of="2026-08-14")
            write_jsonl(candidates, [{"case_id": "fs-b-1", "ticker": "B", "filing": {"form": "10-Q"}}])
            report = validate_cohort_ledger(ledger)
            self.assertFalse(report["valid"])
            self.assertIn("candidate hash changed", " ".join(report["errors"]))


if __name__ == "__main__":
    raise SystemExit(unittest.main())
