from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_filing_evidence as bfe  # noqa: E402


class CharCapTests(unittest.TestCase):
    def test_short_text_is_untouched(self):
        text = "alpha\nbeta"
        self.assertEqual(bfe.apply_char_cap(text, 1000), text)

    def test_truncation_leaves_a_visible_marker(self):
        out = bfe.apply_char_cap("x" * 5000, 1000)
        self.assertIn("EXTRACT TRUNCATED", out)
        self.assertIn("5,000", out)

    def test_marker_makes_truncation_detectable_downstream(self):
        # The whole point: a capped extract must not be able to pass as whole.
        capped = bfe.apply_char_cap("y" * 900_000, 300_000)
        self.assertTrue(capped.rstrip().endswith("]"))
        self.assertIn("33.3%", capped)


class CoverageRecordTests(unittest.TestCase):
    def test_complete_extract_is_not_truncated(self):
        rec = bfe.coverage_record(500, "liquidity and capital resources", 1000)
        self.assertFalse(rec["truncated"])
        self.assertEqual(rec["coverage_pct"], 100.0)

    def test_truncated_extract_reports_partial_coverage(self):
        rec = bfe.coverage_record(1_283_894, "x" * 300_000, 300_000)
        self.assertTrue(rec["truncated"])
        self.assertEqual(rec["coverage_pct"], 23.4)

    def test_sections_are_split_present_and_missing(self):
        rec = bfe.coverage_record(100, "Liquidity and Capital Resources follow", 1000)
        self.assertIn("liquidity_and_capital_resources", rec["sections_present"])
        self.assertIn("notes_to_financial_statements", rec["sections_missing"])

    def test_zero_length_source_does_not_divide_by_zero(self):
        self.assertIsNone(bfe.coverage_record(0, "", 1000)["coverage_pct"])


class CleanFilingTextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(__file__).resolve().parent / "_tmp_bfe_test.htm"
        self.addCleanup(lambda: self.tmp.unlink(missing_ok=True))

    def test_returns_full_text_uncapped(self):
        body = "<p>" + ("word " * 60_000) + "</p>"
        self.tmp.write_text(body, encoding="utf-8")
        out = bfe.clean_filing_text(self.tmp)
        # Uncapped by construction; the caller decides the cap.
        self.assertGreater(len(out), 200_000)

    def test_extract_html_still_caps_for_back_compat(self):
        self.tmp.write_text("<p>" + ("word " * 60_000) + "</p>", encoding="utf-8")
        out = bfe.extract_html(self.tmp, 5_000)
        self.assertIn("EXTRACT TRUNCATED", out)


class FullTierCapTests(unittest.TestCase):
    def test_cap_covers_the_largest_observed_filings(self):
        # WHK 424B4 cleans to 1,283,894 chars; AAL 10-K to 884,518.
        self.assertGreaterEqual(bfe.FULL_TIER_CHAR_CAP, 1_300_000)


if __name__ == "__main__":
    unittest.main()
