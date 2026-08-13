#!/usr/bin/env python3
"""Workflow tests for evidence-safe sampling and blind-label controls."""
from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from filing_sentinel_gold import _sha256, load_taxonomy, read_jsonl  # noqa: E402
from filing_sentinel_workflow import (  # noqa: E402
    create_label_packets,
    failure_queue,
    ingest_blind_labels,
    lock_split,
    quota_sample,
)


def case(case_id: str, ticker: str, form: str, strata: list[str], priority: int = 10) -> dict:
    excerpt = f"Evidence for {case_id}"
    return {
        "schema_version": 1,
        "case_id": case_id,
        "label_status": "candidate",
        "split": "train",
        "ticker": ticker,
        "filing": {"form": form, "filed_at": "2026-01-01", "period_end": "2025-12-31", "source_ref": f"{ticker}/filing.htm", "source_sha256": None},
        "evidence": [{"evidence_id": "ev-1", "locator": "line 1", "excerpt": excerpt, "content_sha256": _sha256(excerpt), "source_ref": f"{ticker}/private"}],
        "proposals": [],
        "mining_reasons": [],
        "section_signals": [],
        "sampling": {"strata": strata},
        "expected": {"events": [], "no_event_tags": [], "no_material_change": False},
        "candidate_priority": priority,
        "provenance": {"origin": "test", "created_at": "2026-08-04", "adjudicated_by": [], "rationale": "test"},
    }


class FilingSentinelWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.taxonomy = load_taxonomy()

    def test_split_is_stable_and_issuer_based(self) -> None:
        policy = self.taxonomy["split_policy"]
        self.assertEqual(lock_split("ABC", policy), lock_split("ABC", policy))
        self.assertIn(lock_split("ABC", policy), {"train", "dev", "test"})

    def test_quota_sample_reserves_both_filing_forms(self) -> None:
        cases = [
            case("fs-a-1", "A", "10-K", ["high_adverse"], 20),
            case("fs-b-1", "B", "10-K", ["hard_negative"], 19),
            case("fs-c-1", "C", "10-Q", ["clean_control"], 1),
            case("fs-d-1", "D", "10-Q", ["semantic_section"], 1),
        ]
        selected, summary = quota_sample(cases, limit=4, taxonomy=self.taxonomy)
        self.assertEqual(len(selected), 4)
        self.assertGreaterEqual(summary["selected_by_form"].get("10-Q", 0), 2)
        self.assertGreaterEqual(summary["selected_by_form"].get("10-K", 0), 2)

    def test_packets_hide_ticker_and_proposals(self) -> None:
        cases = [case("fs-a-1", "SECRET", "10-Q", ["high_adverse"])]
        with tempfile.TemporaryDirectory() as temp:
            result = create_label_packets(cases, Path(temp), batch_id="batch-1")
            packet = read_jsonl(Path(temp) / "labelers" / "extractor_packet.jsonl")[0]
            serialized = json.dumps(packet)
            self.assertEqual(result["cases"], 1)
            self.assertNotIn("SECRET", serialized)
            self.assertNotIn("proposals", serialized)
            self.assertNotIn("source_ref", serialized)

    def test_blind_agreement_becomes_labeled(self) -> None:
        cases = [case("fs-a-1", "A", "10-Q", ["high_adverse"])]
        with tempfile.TemporaryDirectory() as temp:
            create_label_packets(cases, Path(temp), batch_id="batch-1")
            manifest = json.loads((Path(temp) / "control" / "blind_manifest.json").read_text(encoding="utf-8"))
            event = {"event_id": "test-event", "category": "operations", "tags": ["margin_contraction"], "direction": "strengthens", "severity": "medium", "claim": "Test change", "falsifier": "Test falsifier", "evidence_ids": ["ev-1"], "review_required": False}
            extractor = [{"blind_id": manifest["cases"]["fs-a-1"]["blind_ids"]["extractor"], "events": [event], "no_event_tags": [], "no_material_change": False}]
            skeptic = [{"blind_id": manifest["cases"]["fs-a-1"]["blind_ids"]["skeptic"], "events": [event], "no_event_tags": [], "no_material_change": False}]
            updated, queue = ingest_blind_labels(cases, manifest, extractor, skeptic, as_of="2026-08-04")
            self.assertEqual(updated[0]["label_status"], "labeled")
            self.assertEqual(queue, [])

    def test_disagreement_and_test_failures_are_not_training_examples(self) -> None:
        cases = [case("fs-a-1", "A", "10-Q", ["high_adverse"])]
        cases[0]["split"] = "test"
        cases[0]["label_status"] = "gold"
        cases[0]["expected"] = {"events": [{"category": "operations", "tags": ["margin_contraction"], "direction": "strengthens"}], "no_event_tags": [], "no_material_change": False}
        queue = failure_queue(cases, [{"case_id": "fs-a-1", "events": []}])
        self.assertEqual(queue[0]["failure_type"], "false_negative")
        self.assertFalse(queue[0]["eligible_for_training"])


if __name__ == "__main__":
    raise SystemExit(unittest.main())
