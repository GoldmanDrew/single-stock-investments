#!/usr/bin/env python3
"""The uncorroborated-IRR gate must respect outlier_validation.

The check is named for *uncorroborated* IRRs but used to flag every extreme
return, corroborated or not. Because that error fails the build step, it
skipped the Cloudflare deploy entirely on five tickers that had already passed
outlier validation. These tests pin both directions: a corroborated outlier is
cleared, an uncorroborated one is not.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from validate_dashboard_data import extreme_return_corroborated  # noqa: E402


def _write(root: Path, ticker: str, body: str) -> None:
    research = root / ticker / "research"
    research.mkdir(parents=True, exist_ok=True)
    (research / "valuation_contract.json").write_text(body, encoding="utf-8")


class OutlierGateTests(unittest.TestCase):
    def test_corroborated_outlier_is_cleared(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write(root, "ABX", json.dumps(
                {"model_checks": {"extreme_return_validated": True}}))
            self.assertTrue(extreme_return_corroborated("ABX", root))

    def test_uncorroborated_outlier_still_flags(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write(root, "FOO", json.dumps(
                {"model_checks": {"extreme_return_validated": False}}))
            self.assertFalse(extreme_return_corroborated("FOO", root))

    def test_missing_model_checks_is_not_corroborated(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write(root, "BAR", json.dumps({"status": "decision_grade"}))
            self.assertFalse(extreme_return_corroborated("BAR", root))

    def test_missing_contract_is_not_corroborated(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertFalse(extreme_return_corroborated("NOPE", Path(td)))

    def test_malformed_contract_is_not_corroborated(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write(root, "BAD", "{not json")
            self.assertFalse(extreme_return_corroborated("BAD", root))

    def test_empty_ticker_is_not_corroborated(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertFalse(extreme_return_corroborated("", Path(td)))


class LiveOutlierTests(unittest.TestCase):
    """The five real tickers that were blocking the Cloudflare deploy."""

    FLAGGED = ("ABX", "AEHR", "AXON", "AXTI", "CEG")

    def test_flagged_tickers_are_corroborated_in_the_repo(self):
        for ticker in self.FLAGGED:
            if not (ROOT / ticker / "research" / "valuation_contract.json").exists():
                continue
            self.assertTrue(
                extreme_return_corroborated(ticker),
                f"{ticker}: extreme_return_validated is false, so it should be "
                "failing the IRR gate rather than being cleared",
            )




class PayloadFieldTests(unittest.TestCase):
    """The deploy job runs a sparse checkout with no ticker trees, so the row
    field must be authoritative and must not fall back to a missing file."""

    def test_row_field_wins_over_absent_tree(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertTrue(extreme_return_corroborated(
                "ABX", Path(td), decision={"extreme_return_validated": True}))

    def test_row_field_false_is_respected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write(root, "ABX", json.dumps(
                {"model_checks": {"extreme_return_validated": True}}))
            self.assertFalse(extreme_return_corroborated(
                "ABX", root, decision={"extreme_return_validated": False}))

    def test_absent_row_field_falls_back_to_contract(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write(root, "ABX", json.dumps(
                {"model_checks": {"extreme_return_validated": True}}))
            self.assertTrue(extreme_return_corroborated("ABX", root, decision={}))


class ThresholdCouplingTests(unittest.TestCase):
    """extreme_return_validated means "not extreme OR validated", so the two
    modules' thresholds must agree or an extreme return could be cleared
    without ever having been corroborated."""

    def test_thresholds_agree(self):
        from validate_dashboard_data import EXTREME_PUBLISHED_IRR_PCT
        from universal_valuation_contract import EXTREME_RETURN_PCT
        self.assertEqual(
            float(EXTREME_RETURN_PCT), float(EXTREME_PUBLISHED_IRR_PCT),
            "contract and dashboard extreme-return thresholds diverged; the "
            "corroboration check in extreme_return_corroborated is only sound "
            "while they match",
        )


if __name__ == "__main__":
    unittest.main()
