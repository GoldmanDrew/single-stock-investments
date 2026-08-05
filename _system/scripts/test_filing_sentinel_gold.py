#!/usr/bin/env python3
"""Tests for Filing Sentinel gold-set validation, mining rules, and evaluation."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from filing_sentinel_gold import (  # noqa: E402
    DEFAULT_GOLD,
    _metric_proposal,
    evaluate,
    load_taxonomy,
    read_jsonl,
    validate_dataset,
)

PERFECT = ROOT / "_system" / "scripts" / "fixtures" / "filing_sentinel_perfect_predictions.jsonl"


class FilingSentinelGoldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.taxonomy = load_taxonomy()
        cls.gold = read_jsonl(DEFAULT_GOLD)

    def test_locked_gold_set_validates(self) -> None:
        self.assertEqual(validate_dataset(self.gold, self.taxonomy, require_gold=True), [])

    def test_excerpt_tampering_is_detected(self) -> None:
        rows = copy.deepcopy(self.gold)
        rows[0]["evidence"][0]["excerpt"] += " altered"
        errors = validate_dataset(rows, self.taxonomy, require_gold=True)
        self.assertTrue(any("hash mismatch" in error for error in errors))

    def test_ticker_leakage_is_detected(self) -> None:
        rows = copy.deepcopy(self.gold)
        duplicate = copy.deepcopy(rows[0])
        duplicate["case_id"] = "fs-qdel-leakage-check"
        duplicate["split"] = "train"
        duplicate["filing"]["source_ref"] += "?duplicate"
        rows.append(duplicate)
        errors = validate_dataset(rows, self.taxonomy, require_gold=True)
        self.assertTrue(any("ticker leakage" in error for error in errors))

    def test_non_comparable_prior_period_is_detected(self) -> None:
        rows = copy.deepcopy(self.gold)
        rows[0]["filing"]["comparison_period_end"] = "2025-09-30"
        errors = validate_dataset(rows, self.taxonomy, require_gold=True)
        self.assertTrue(any("roughly one year" in error for error in errors))

    def test_perfect_predictions_pass_all_gates(self) -> None:
        report = evaluate(self.gold, read_jsonl(PERFECT), self.taxonomy)
        self.assertTrue(report["passed"])
        self.assertEqual(report["metrics"]["precision"], 1.0)
        self.assertEqual(report["metrics"]["recall"], 1.0)
        self.assertEqual(report["metrics"]["citation_precision"], 1.0)

    def test_false_alert_and_miss_fail_quality_gates(self) -> None:
        predictions = read_jsonl(PERFECT)
        predictions[0]["events"] = [{
            "category": "transaction", "tags": ["wind_down"], "direction": "strengthens",
            "evidence_ids": ["not-real"],
        }]
        report = evaluate(self.gold, predictions, self.taxonomy)
        self.assertFalse(report["passed"])
        self.assertGreater(report["metrics"]["false_positives"], 0)
        self.assertGreater(report["metrics"]["false_negatives"], 0)

    def test_forbidden_extra_tag_fails_even_when_event_matches(self) -> None:
        predictions = read_jsonl(PERFECT)
        predictions[0]["events"][0]["tags"].append("restatement")
        report = evaluate(self.gold, predictions, self.taxonomy)
        self.assertFalse(report["passed"])
        self.assertEqual(report["metrics"]["forbidden_tag_violations"], 1)

    def test_hard_negative_parser_flag_never_becomes_proposal(self) -> None:
        config = self.taxonomy["metric_proposals"]["revenues"]
        proposal, reason = _metric_proposal(
            "revenues",
            {"current": 0, "prior": 16313, "parser_confidence": "high", "parser_flags": ["segment_context"]},
            config,
        )
        self.assertIsNone(proposal)
        self.assertIn("parser_hard_negative", reason)

    def test_material_high_confidence_change_becomes_candidate_proposal(self) -> None:
        config = self.taxonomy["metric_proposals"]["operating_income"]
        proposal, reason = _metric_proposal(
            "operating_income",
            {"current": 919.2, "prior": 1960.9, "parser_confidence": "high", "parser_flags": []},
            config,
        )
        self.assertIsNone(reason)
        self.assertEqual(proposal["tags"], ["margin_contraction"])
        self.assertEqual(proposal["direction"], "strengthens")


if __name__ == "__main__":
    raise SystemExit(unittest.main())
