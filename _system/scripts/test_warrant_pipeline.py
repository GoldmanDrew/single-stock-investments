#!/usr/bin/env python3
"""Unit tests for warrant gate ordering and immutable registry checks."""
from __future__ import annotations

import copy
import unittest
from datetime import date

from warrant_common import gate_state, validate_registry
from resolve_warrant_outcomes import corporate_action_terminal


def record() -> dict:
    return {
        "warrant_id": "0000000001:test:public",
        "version": 1,
        "issuer": "Test Issuer",
        "cik": "0000000001",
        "common_ticker": "TEST",
        "warrant_ticker": "TESTW",
        "lane": "chapter_11",
        "lifecycle": "active",
        "terms_complete": True,
        "terms": {
            "strike": 10.0,
            "currency": "USD",
            "share_ratio": 1.0,
            "issue_date": "2026-01-01",
            "expiry": "2030-01-01",
        },
        "survival": {"status": "pass", "missing_inputs": []},
        "source": {"url": "https://www.sec.gov/Archives/test"},
    }


class WarrantPipelineTests(unittest.TestCase):
    def test_all_gates_required_for_review_ready(self) -> None:
        gates = gate_state(
            record(),
            {"close": 3.0, "bid": 2.9, "ask": 3.1},
            {"close": 12.0},
        )
        self.assertEqual(gates["status"], "review_ready")
        self.assertTrue(all(gates[name]["pass"] for name in ("identity", "survival", "market")))

    def test_missing_two_sided_quote_blocks_execution(self) -> None:
        gates = gate_state(record(), {"close": 3.0}, {"close": 12.0})
        self.assertEqual(gates["status"], "market_blocked")
        self.assertIn("warrant bid", gates["market"]["missing"])
        self.assertIn("warrant ask", gates["market"]["missing"])

    def test_terms_precede_survival_and_market(self) -> None:
        candidate = record()
        candidate["terms_complete"] = False
        candidate["terms"]["strike"] = None
        candidate["survival"] = {"status": "review_required", "missing_inputs": ["debt"]}
        gates = gate_state(candidate, {}, {})
        self.assertEqual(gates["status"], "terms_blocked")

    def test_survival_precedes_market(self) -> None:
        candidate = record()
        candidate["survival"] = {"status": "review_required", "missing_inputs": ["liquidity"]}
        gates = gate_state(candidate, {}, {})
        self.assertEqual(gates["status"], "survival_blocked")

    def test_registry_rejects_duplicate_versions(self) -> None:
        first = record()
        second = copy.deepcopy(first)
        errors = validate_registry([first, second])
        self.assertTrue(any("duplicate warrant_id/version" in error for error in errors))

    def test_registry_rejects_incomplete_verified_terms(self) -> None:
        candidate = record()
        candidate["terms"].pop("expiry")
        errors = validate_registry([candidate])
        self.assertTrue(any("terms_complete but expiry missing" in error for error in errors))

    def test_redemption_cash_resolves_delisted_cohort(self) -> None:
        candidate = record()
        candidate["lifecycle"] = "redeemed"
        candidate["corporate_action"] = {
            "effective_at": "2026-06-01",
            "cash_per_warrant": 0.01,
        }
        terminal = corporate_action_terminal(candidate, date(2026, 7, 1))
        self.assertEqual(terminal["close"], 0.01)
        self.assertEqual(terminal["outcome_kind"], "redeemed")


if __name__ == "__main__":
    unittest.main()
