from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import committee_task_queue
import investment_committee_pipeline
import jsonschema
import select_committee_work


DIMS = ("explanatory_strength", "evidence_sufficiency", "downside_control", "return_vs_alternatives")


class CommitteeTaskQueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.work = self.root / "AAA" / "research" / "committee_work" / "2026-07-18"
        (self.work / "round_1").mkdir(parents=True)
        (self.work / "round_2").mkdir(parents=True)
        raters = [
            {"persona": "hohn", "independence_group": "competitive_advantage", "selection_reason": "test", "required_inputs_status": "complete"},
            {"persona": "pabrai", "independence_group": "asymmetry_downside", "selection_reason": "test", "required_inputs_status": "complete"},
            {"persona": "marks_credit_cycle", "independence_group": "credit_cycle", "selection_reason": "test", "required_inputs_status": "complete"},
        ]
        self.write(self.work / "manifest.json", {
            "ticker": "AAA", "as_of": "2026-07-18", "packet_hash": investment_committee_pipeline.packet_hash([]),
            "selected_raters": raters, "evidence": [], "stage": "round_one_open",
            "frozen_at": "2026-07-18T12:00:00+00:00",
        })
        research = self.root / "AAA" / "research"
        self.write(research / "valuation.json", {
            "ticker": "AAA", "inputs": {"price": 10, "shares_outstanding": 100},
            "economic_value_analysis": {"status": "complete", "valuation_proof": []},
            "component_valuation_results": {"status": "complete", "all_material_components_identified": True},
        })
        self.write(research / "valuation_contract.json", {"status": "decision_grade"})
        self.write(research / "valuation_route.json", {"profile_id": "quality_reinvestment"})
        for row in raters:
            (self.work / "round_1" / f"{row['persona']}.prompt.md").write_text("prompt", encoding="utf-8")
            (self.work / "round_2" / f"{row['persona']}.prompt.md").write_text("prompt", encoding="utf-8")
        (self.work / "pre_mortem.prompt.md").write_text("prompt", encoding="utf-8")
        (self.work / "chair_synthesis.prompt.md").write_text("prompt", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def write(path: Path, value: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    @staticmethod
    def vote(persona: str, group: str) -> dict:
        return {
            "persona": persona,
            "independence_group": group,
            "evidence_status": "sufficient",
            "scores": {dim: {"value": 4, "rationale": "supported"} for dim in DIMS},
            "vote": "approve",
            "expected_return_range_pct": [12, 18],
            "horizon_years": 5,
            "claims": [{"claim": "claim", "evidence_paths": ["valuation_contract.json"]}],
            "strongest_counter_explanation": "cycle",
            "most_important_missing_fact": "none material",
            "falsifiers": ["return below hurdle"],
            "specialist_findings": "within power zone",
            "confidence": "medium",
        }

    def test_five_call_baseline_materializes_support_deterministically(self):
        with patch.object(committee_task_queue, "ROOT", self.root), patch.object(
            investment_committee_pipeline, "ROOT", self.root
        ):
            first = committee_task_queue.next_tasks("AAA", "2026-07-18")
            self.assertEqual(len(first), 4)
            self.assertNotIn("proposer", {row["task_id"] for row in first})
            self.assertTrue((self.work / "proposer.json").exists())
            manifest = json.loads((self.work / "manifest.json").read_text())
            self.write(self.work / "pre_mortem.json", {
                "status": "complete", "failure_story": "cycle breaks", "earliest_warning_signals": [],
                "forensic_checks": ["cash conversion"], "short_source_coverage": "partial", "unresolved_items": [],
                "evidence_packet_hash": manifest["packet_hash"],
            })
            for row in manifest["selected_raters"]:
                self.write(self.work / "round_1" / f"{row['persona']}.json", self.vote(row["persona"], row["independence_group"]))
            second = committee_task_queue.next_tasks("AAA", "2026-07-18")
            self.assertEqual([row["task_id"] for row in second], ["chair-synthesis"])
            self.assertTrue((self.work / "valuation_reconciliation.json").exists())
            self.assertTrue((self.work / "adversarial_review.json").exists())
            self.assertEqual(len(list((self.work / "round_2").glob("*.json"))), 3)
            self.write(self.work / "chair_synthesis.json", {
                "status": "complete", "primary_method": "quality_reinvestment",
                "weighting_rationale": "method fit", "agreed_facts": [], "disputed_facts": [],
                "recommendation": "watch",
                "evidence_packet_hash": manifest["packet_hash"],
                "vote_set_hash": investment_committee_pipeline.vote_set_hash(
                    [self.vote(row["persona"], row["independence_group"]) for row in manifest["selected_raters"]],
                    manifest["packet_hash"],
                ),
                "monitoring_plan": {
                    "operational_milestones": [], "evidence_refresh_dates": [],
                    "valuation_refresh_triggers": ["filing"], "price_review_thresholds": [],
                    "thesis_break_conditions": [], "expected_catalyst_dates": [],
                    "outcome_horizons_months": [6, 12, 24],
                },
            })
            self.assertEqual(committee_task_queue.next_tasks("AAA", "2026-07-18"), [])
            output = investment_committee_pipeline.assemble(self.work)
            schema = json.loads((Path(__file__).resolve().parents[1] / "templates" / "committee_schema.json").read_text())
            jsonschema.validate(json.loads(output.read_text()), schema)

    def test_hash_bound_packet_requeues_legacy_unbound_vote(self):
        manifest_path = self.work / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["evidence_snapshot"] = (
            "AAA/research/committee_work/2026-07-18/evidence_snapshot"
        )
        self.write(manifest_path, manifest)
        self.write(self.work / "pre_mortem.json", {
            "status": "complete", "failure_story": "cycle breaks",
            "earliest_warning_signals": [], "forensic_checks": ["cash conversion"],
            "short_source_coverage": "partial", "unresolved_items": [],
            "evidence_packet_hash": manifest["packet_hash"],
        })
        first = manifest["selected_raters"][0]
        self.write(
            self.work / "round_1" / f"{first['persona']}.json",
            self.vote(first["persona"], first["independence_group"]),
        )
        with patch.object(committee_task_queue, "ROOT", self.root), patch.object(
            investment_committee_pipeline, "ROOT", self.root
        ):
            tasks = committee_task_queue.next_tasks("AAA", "2026-07-18")
        self.assertIn(f"round1-{first['persona']}", {row["task_id"] for row in tasks})

    def test_stale_chair_is_requeued_after_final_votes_exist(self):
        manifest = json.loads((self.work / "manifest.json").read_text())
        self.write(self.work / "pre_mortem.json", {
            "status": "complete", "failure_story": "cycle breaks",
            "earliest_warning_signals": [], "forensic_checks": ["cash conversion"],
            "short_source_coverage": "partial", "unresolved_items": [],
            "evidence_packet_hash": manifest["packet_hash"],
        })
        for row in manifest["selected_raters"]:
            vote = self.vote(row["persona"], row["independence_group"])
            self.write(self.work / "round_1" / f"{row['persona']}.json", vote)
        self.write(self.work / "chair_synthesis.json", {
            "status": "complete", "primary_method": "old", "weighting_rationale": "old",
            "agreed_facts": [], "disputed_facts": [], "recommendation": "watch",
            "monitoring_plan": {},
        })
        with patch.object(committee_task_queue, "ROOT", self.root), patch.object(
            investment_committee_pipeline, "ROOT", self.root
        ):
            tasks = committee_task_queue.next_tasks("AAA", "2026-07-18")
        self.assertEqual([row["task_id"] for row in tasks], ["chair-synthesis"])
        support = json.loads((self.work / "committee_support.json").read_text())
        self.assertEqual(support["final_vote_count"], 3)

    def test_auto_selector_derives_company_and_date_from_manifest_path(self):
        expected = [{"task_id": "pre_mortem"}]
        with patch.object(select_committee_work, "ROOT", self.root), patch.object(
            select_committee_work, "next_tasks", return_value=expected
        ) as queued:
            result = select_committee_work.select()
        self.assertEqual(result["ticker"], "AAA")
        self.assertEqual(result["committee_date"], "2026-07-18")
        self.assertEqual(result["action"], "advance")
        self.assertEqual(result["tasks"], expected)
        queued.assert_called_once_with("AAA", "2026-07-18")

    def test_auto_selector_refreshes_a_stale_frozen_packet(self):
        with patch.object(select_committee_work, "ROOT", self.root), patch.object(
            select_committee_work, "packet_is_current", return_value=False
        ), patch.object(select_committee_work, "next_tasks") as queued:
            result = select_committee_work.select()
        self.assertEqual(result["action"], "refresh")
        self.assertEqual(result["ticker"], "AAA")
        queued.assert_not_called()


if __name__ == "__main__":
    unittest.main()
