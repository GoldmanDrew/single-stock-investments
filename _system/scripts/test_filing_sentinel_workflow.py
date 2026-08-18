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
    create_adjudication_packets,
    create_consensus_audit_packets,
    failure_queue,
    ingest_blind_labels,
    label_ingest_report,
    lock_split,
    promotion_gate_report,
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

    def test_single_form_lane_does_not_report_impossible_form_shortfall(self) -> None:
        cases = [
            case("fs-a-1", "A", "10-Q", ["clean_control"], 2),
            case("fs-b-1", "B", "10-Q", ["semantic_section"], 1),
        ]
        selected, summary = quota_sample(cases, limit=2, taxonomy=self.taxonomy, allowed_forms={"10-Q"})
        self.assertEqual(len(selected), 2)
        self.assertNotIn("10-K", summary["form_targets"])
        self.assertNotIn("10-K", summary["quota_shortfalls"]["forms"])

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
            template = read_jsonl(Path(temp) / "labelers" / "extractor_labels.template.jsonl")[0]
            self.assertEqual(template["blind_id"], packet["blind_id"])
            self.assertIn("review_context_id", template)

    def test_reviewer_packets_have_different_deterministic_orders(self) -> None:
        cases = [case(f"fs-{ticker}-1", ticker, "10-Q", ["clean_control"]) for ticker in "ABCD"]
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            create_label_packets(cases, Path(first), batch_id="batch-order")
            create_label_packets(cases, Path(second), batch_id="batch-order")
            first_manifest = json.loads((Path(first) / "control" / "blind_manifest.json").read_text(encoding="utf-8"))
            blind_to_alias = {
                blind_id: entry["alias"]
                for entry in first_manifest["cases"].values()
                for blind_id in entry["blind_ids"].values()
            }
            extractor = [blind_to_alias[row["blind_id"]] for row in read_jsonl(Path(first) / "labelers" / "extractor_packet.jsonl")]
            skeptic = [blind_to_alias[row["blind_id"]] for row in read_jsonl(Path(first) / "labelers" / "skeptic_packet.jsonl")]
            repeated = [blind_to_alias[row["blind_id"]] for row in read_jsonl(Path(second) / "labelers" / "extractor_packet.jsonl")]
            self.assertEqual(extractor, list(reversed(skeptic)))
            self.assertEqual(extractor, repeated)

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
            report = label_ingest_report(cases, updated, queue)
            self.assertEqual(report["auto_consensus"], 1)
            self.assertEqual(report["valid_pair_consensus_rate"], 1.0)

    def test_promotion_gate_requires_distinct_review_contexts(self) -> None:
        candidate = case("fs-a-1", "A", "10-Q", ["high_adverse"])
        candidate["label_status"] = "labeled"
        candidate["provenance"]["blind_review_contexts"] = {"extractor": "extractor-run", "skeptic": "skeptic-run"}
        decision = {"case_id": "fs-a-1", "adjudicator": "analyst", "review_context_id": "adjudicator-run"}
        report = promotion_gate_report([candidate], [decision], include_auto=False)
        self.assertTrue(report["eligible"])
        self.assertEqual(report["eligible_promotions"], 1)

    def test_promotion_gate_blocks_missing_or_shared_contexts(self) -> None:
        candidate = case("fs-a-1", "A", "10-Q", ["high_adverse"])
        candidate["label_status"] = "labeled"
        candidate["provenance"]["blind_review_contexts"] = {"extractor": "same-run", "skeptic": "same-run"}
        decision = {"case_id": "fs-a-1", "adjudicator": "analyst", "review_context_id": "same-run"}
        report = promotion_gate_report([candidate], [decision], include_auto=False)
        self.assertFalse(report["eligible"])
        self.assertEqual(report["blocked_promotions"], 1)
        self.assertEqual(report["blocked_reason_counts"]["shared_blind_review_context"], 1)
        self.assertEqual(report["blocked_reason_counts"]["adjudicator_context_not_independent"], 1)

    def test_always_review_consensus_is_reported_separately(self) -> None:
        cases = [case("fs-a-1", "A", "10-Q", ["semantic_section"])]
        with tempfile.TemporaryDirectory() as temp:
            create_label_packets(cases, Path(temp), batch_id="batch-review")
            manifest = json.loads((Path(temp) / "control" / "blind_manifest.json").read_text(encoding="utf-8"))
            event = {"category": "governance_legal", "tags": ["investigation"], "direction": "strengthens", "severity": "high", "claim": "New investigation disclosure", "falsifier": "Comparable disclosure predates the period", "evidence_ids": ["ev-1"], "review_required": True}
            extractor = [{"blind_id": manifest["cases"]["fs-a-1"]["blind_ids"]["extractor"], "events": [event], "no_event_tags": [], "no_material_change": False}]
            skeptic = [{"blind_id": manifest["cases"]["fs-a-1"]["blind_ids"]["skeptic"], "events": [event], "no_event_tags": [], "no_material_change": False}]
            updated, queue = ingest_blind_labels(cases, manifest, extractor, skeptic, as_of="2026-08-04")
            self.assertEqual(updated[0]["label_status"], "candidate")
            self.assertEqual(queue[0]["reason"], "always_review_consensus")
            report = label_ingest_report(cases, updated, queue)
            self.assertEqual(report["queue_reasons"], {"always_review_consensus": 1})

    def test_severity_disagreement_requires_adjudication(self) -> None:
        cases = [case("fs-a-1", "A", "10-Q", ["high_adverse"])]
        with tempfile.TemporaryDirectory() as temp:
            create_label_packets(cases, Path(temp), batch_id="batch-severity")
            manifest = json.loads((Path(temp) / "control" / "blind_manifest.json").read_text(encoding="utf-8"))
            event = {"category": "operations", "tags": ["margin_contraction"], "direction": "strengthens", "severity": "medium", "claim": "Material decline", "falsifier": "Comparable metric recovers", "evidence_ids": ["ev-1"], "review_required": False}
            skeptic_event = copy.deepcopy(event)
            skeptic_event["severity"] = "low"
            extractor = [{"blind_id": manifest["cases"]["fs-a-1"]["blind_ids"]["extractor"], "events": [event], "no_event_tags": [], "no_material_change": False}]
            skeptic = [{"blind_id": manifest["cases"]["fs-a-1"]["blind_ids"]["skeptic"], "events": [skeptic_event], "no_event_tags": [], "no_material_change": False}]
            updated, queue = ingest_blind_labels(cases, manifest, extractor, skeptic, as_of="2026-08-04")
            self.assertEqual(updated[0]["label_status"], "candidate")
            self.assertEqual(queue[0]["reason"], "blind_disagreement")

    def test_rejected_tag_disagreement_requires_adjudication(self) -> None:
        cases = [case("fs-a-1", "A", "10-Q", ["clean_control"])]
        with tempfile.TemporaryDirectory() as temp:
            create_label_packets(cases, Path(temp), batch_id="batch-negative")
            manifest = json.loads((Path(temp) / "control" / "blind_manifest.json").read_text(encoding="utf-8"))
            extractor = [{"blind_id": manifest["cases"]["fs-a-1"]["blind_ids"]["extractor"], "events": [], "no_event_tags": ["restatement"], "no_material_change": True}]
            skeptic = [{"blind_id": manifest["cases"]["fs-a-1"]["blind_ids"]["skeptic"], "events": [], "no_event_tags": [], "no_material_change": True}]
            updated, queue = ingest_blind_labels(cases, manifest, extractor, skeptic, as_of="2026-08-04")
            self.assertEqual(updated[0]["label_status"], "candidate")
            self.assertEqual(queue[0]["reason"], "blind_disagreement")

    def test_adjudication_packets_carry_both_blind_views_without_promotion(self) -> None:
        queued = [{"case_id": "fs-a-1", "reason": "blind_disagreement", "case": case("fs-a-1", "A", "10-Q", ["semantic_section"]), "extractor": {"events": []}, "skeptic": {"events": []}}]
        with tempfile.TemporaryDirectory() as temp:
            result = create_adjudication_packets(queued, Path(temp), batch_id="adj-1")
            packet = read_jsonl(Path(temp) / "adjudicator_packet.jsonl")[0]
            template = read_jsonl(Path(temp) / "adjudication_decisions.template.jsonl")[0]
            self.assertEqual(result["packets"], 1)
            self.assertEqual(packet["task"]["gold_promotion"], "forbidden")
            self.assertEqual(template["case_id"], "fs-a-1")

    def test_consensus_audit_is_deterministic_and_bounded(self) -> None:
        cases = [case(f"fs-{ticker}-1", ticker, "10-Q", ["clean_control"]) for ticker in "ABCDE"]
        for item in cases:
            item["label_status"] = "labeled"
            item["expected"]["no_material_change"] = True
        cases[0]["expected"] = {"events": [{"category": "operations", "tags": ["revenue_growth"]}], "no_event_tags": [], "no_material_change": False}
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            create_consensus_audit_packets(cases, Path(first), batch_id="audit-1", sample_size=3)
            create_consensus_audit_packets(cases, Path(second), batch_id="audit-1", sample_size=3)
            first_ids = [row["case_id"] for row in read_jsonl(Path(first) / "consensus_audit_packet.jsonl")]
            second_ids = [row["case_id"] for row in read_jsonl(Path(second) / "consensus_audit_packet.jsonl")]
            self.assertEqual(len(first_ids), 3)
            self.assertEqual(first_ids, second_ids)
            self.assertIn("fs-A-1", first_ids)

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
