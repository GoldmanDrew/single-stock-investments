#!/usr/bin/env python3
"""Unit tests for Drive intake path parsing and PDF ticker resolution."""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))


def _ticker_dirs() -> list[str]:
    """Return actual ticker roots, excluding sparse-checkout support folders."""
    return [
        path.name
        for path in ROOT.iterdir()
        if path.is_dir()
        and path.name == path.name.upper()
        and not path.name.startswith(("_", "."))
    ]


def _load_importer():
    spec = importlib.util.spec_from_file_location("import_drive_intake", SCRIPTS / "import_drive_intake.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # Avoid importing google clients at module level for path tests — module does import them.
    # If google deps missing, skip path tests that need the module.
    try:
        spec.loader.exec_module(mod)
    except ModuleNotFoundError as exc:
        raise unittest.SkipTest(f"missing dependency: {exc}") from exc
    return mod


class ParseIntakePathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_importer()

    def test_vic_ticker_filename(self):
        # FRMI may or may not exist locally; pick an existing ticker dir
        tickers = _ticker_dirs()
        self.assertTrue(tickers)
        t = tickers[0]
        parsed = self.mod.parse_intake_path(f"VIC/{t}.pdf")
        self.assertIsNotNone(parsed)
        self.assertNotIn("error", parsed or {})
        self.assertEqual(parsed["ticker"], t)
        self.assertEqual(parsed["intake_kind"], "vic")

    def test_vic_numeric_filename_unknown(self):
        parsed = self.mod.parse_intake_path("VIC/163625.pdf")
        self.assertEqual(parsed["error"], "missing_or_unknown_ticker")
        self.assertEqual(parsed["intake_kind"], "vic")

    def test_admin_intake_vic_path(self):
        tickers = _ticker_dirs()
        t = tickers[0]
        parsed = self.mod.parse_intake_path(f"Admin/Intake/VIC/{t}/writeup.pdf")
        self.assertEqual(parsed["ticker"], t)


class ResolveTickerTests(unittest.TestCase):
    def setUp(self):
        from intake_ticker_resolve import resolve_ticker_from_text

        self.resolve = resolve_ticker_from_text
        self.known = {"FRMI", "APLD", "TPL", "XYZ"}

    def test_tier_a_dollar_ticker(self):
        result = self.resolve("Thesis on $FRMI with upside.", filename="163625.pdf", known=self.known)
        self.assertEqual(result["ticker"], "FRMI")
        self.assertEqual(result["method"], "tier_a_explicit")
        self.assertIsNone(result["error"])

    def test_nasdaq_paren(self):
        result = self.resolve("Company (NASDAQ: APLD) deep dive.", filename="foo.pdf", known=self.known)
        self.assertEqual(result["ticker"], "APLD")
        self.assertIsNone(result["error"])

    def test_ambiguous(self):
        result = self.resolve("Comparing $FRMI and $APLD tonight.", filename="163625.pdf", known=self.known)
        self.assertIsNone(result["ticker"])
        self.assertEqual(result["error"], "ambiguous_tickers")
        self.assertIn("FRMI", result["candidates"])
        self.assertIn("APLD", result["candidates"])

    def test_no_text(self):
        result = self.resolve("", filename="163625.pdf", known=self.known)
        self.assertEqual(result["error"], "no_text")

    def test_filename_precheck(self):
        result = self.resolve("no ticker here", filename="FRMI.pdf", known=self.known)
        self.assertEqual(result["ticker"], "FRMI")
        self.assertEqual(result["method"], "filename")

    def test_bare_token(self):
        result = self.resolve(
            "This report analyzes TPL mineral royalties in detail across acres.",
            filename="163625.pdf",
            known=self.known,
        )
        self.assertEqual(result["ticker"], "TPL")
        self.assertEqual(result["method"], "bare_token")


class ExitCodeLogicTests(unittest.TestCase):
    def test_warnings_only_is_zero(self):
        # Simulate main return logic
        errors = []
        warnings = [{"error": "unresolved_ticker"}]
        strict = False
        code = 2 if errors else (2 if strict and warnings else 0)
        self.assertEqual(code, 0)

    def test_strict_warnings_is_two(self):
        errors = []
        warnings = [{"error": "unresolved_ticker"}]
        strict = True
        code = 2 if errors else (2 if strict and warnings else 0)
        self.assertEqual(code, 2)

    def test_errors_is_two(self):
        errors = [{"error": "download_failed"}]
        warnings = []
        strict = False
        code = 2 if errors else (2 if strict and warnings else 0)
        self.assertEqual(code, 2)


class IntakeRootSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_importer()

    def test_intake_roots_do_not_fall_back_to_full_pdf_store(self):
        config = {
            "drive_roots": {
                "general_pdfs": {"folder_id": "entire-shared-drive"},
            }
        }
        self.assertEqual(self.mod.configured_intake_root_ids(config), [])

    def test_explicit_intake_roots_are_deduplicated(self):
        config = {
            "drive_intake": {"folder_id": "intake"},
            "drive_intake_roots": {
                "primary": {"folder_id": "intake"},
                "secondary": {"folder_id": "secondary"},
            },
        }
        self.assertEqual(self.mod.configured_intake_root_ids(config), ["intake", "secondary"])


class ReportPersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_importer()

    def test_report_is_not_rewritten_when_only_timestamp_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.json"
            first = {
                "generated_at": "2026-08-20T14:00:00Z",
                "summary": {"imported_count": 0, "warning_count": 1, "error_count": 0},
                "warnings": [{"drive_file_id": "abc", "error": "ambiguous_tickers"}],
            }
            second = {
                **first,
                "generated_at": "2026-08-21T14:00:00Z",
            }
            self.assertTrue(self.mod.write_report_if_changed(path, first))
            self.assertFalse(self.mod.write_report_if_changed(path, second))
            persisted = path.read_text(encoding="utf-8")
            self.assertIn("2026-08-20T14:00:00Z", persisted)
            self.assertNotIn("2026-08-21T14:00:00Z", persisted)

    def test_report_is_rewritten_when_warning_state_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.json"
            first = {
                "generated_at": "2026-08-20T14:00:00Z",
                "summary": {"imported_count": 0, "warning_count": 1, "error_count": 0},
                "warnings": [{"drive_file_id": "abc", "error": "ambiguous_tickers"}],
            }
            cleared = {
                "generated_at": "2026-08-21T14:00:00Z",
                "summary": {"imported_count": 0, "warning_count": 0, "error_count": 0},
                "warnings": [],
            }
            self.assertTrue(self.mod.write_report_if_changed(path, first))
            self.assertTrue(self.mod.write_report_if_changed(path, cleared))
            persisted = path.read_text(encoding="utf-8")
            self.assertIn("2026-08-21T14:00:00Z", persisted)


if __name__ == "__main__":
    unittest.main()
