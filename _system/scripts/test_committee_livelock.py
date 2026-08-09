"""Regression tests for the committee livelock failure modes.

1. copy-on-freeze keeps a packet stable while daily compilers rewrite evidence
2. votes are bound to the packet hash they claim to answer
3. repeated re-freezes without votes park the committee instead of looping
4. an assembled record from a superseded packet stops hiding live work
5. initialize() is not a second door around 3: it refuses a work dir that
   already holds votes or a park block
6. a parked committee is visible to, and resumable by, the human it defers to
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_valuation_workbench
import committee_task_queue
import investment_committee_pipeline as pipeline
import jsonschema
import run_security_decision_pipeline
import select_committee_work
import validate_committee_pr_artifacts

DIMS = ("explanatory_strength", "evidence_sufficiency", "downside_control", "return_vs_alternatives")
RATERS = [
    {"persona": "hohn", "independence_group": "competitive_advantage", "selection_reason": "test", "required_inputs_status": "complete"},
    {"persona": "pabrai", "independence_group": "asymmetry_downside", "selection_reason": "test", "required_inputs_status": "complete"},
    {"persona": "marks_credit_cycle", "independence_group": "credit_cycle", "selection_reason": "test", "required_inputs_status": "complete"},
]


def vote(persona: str, group: str, evidence_hash: str | None = None) -> dict:
    row = {
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
    if evidence_hash:
        row["evidence_hash"] = evidence_hash
    return row


class CommitteeFixture(unittest.TestCase):
    """One decision-grade ticker with a real work dir, isolated under a temp ROOT."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.research = self.root / "AAA" / "research"
        self.work = self.research / "committee_work" / "2026-07-18"
        (self.research / "evidence").mkdir(parents=True)
        (self.research / "thesis.md").write_text("# AAA\n\nThe cash engine compounds.\n", encoding="utf-8")
        (self.research / "deep_dive_2026-07-01.md").write_text("deep dive body\n", encoding="utf-8")
        (self.research / "adversarial_2026-07-02.md").write_text("adversarial body\n", encoding="utf-8")
        self.write(self.research / "valuation.json", {
            "ticker": "AAA",
            "inputs": {"price": 10, "shares_outstanding": 100},
            "economic_value_analysis": {"status": "complete", "valuation_proof": []},
            "component_valuation_results": {"status": "complete", "all_material_components_identified": True},
        })
        self.write(self.research / "valuation_contract.json", {
            "status": "decision_grade",
            "calculation_proof_summary": {"all_material_components_priced": True},
            "model_checks": {"identity": True},
        })
        self.write(self.research / "valuation_route.json", {"profile_id": "quality_reinvestment", "status": "resolved"})

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def write(path: Path, value: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def initialize(self) -> dict:
        with patch.object(pipeline, "ROOT", self.root):
            pipeline.initialize("AAA", "2026-07-18")
        return json.loads((self.work / "manifest.json").read_text(encoding="utf-8"))

    def legacy_manifest(self, evidence: list[dict], **extra) -> dict:
        manifest = {
            "pipeline_version": "3.0-token-efficient",
            "ticker": "AAA",
            "as_of": "2026-07-18",
            "stage": "round_one_open",
            "packet_hash": pipeline.packet_hash(evidence),
            "evidence": evidence,
            "selected_raters": RATERS,
            "frozen_at": "2026-07-18T12:00:00+00:00",
            **extra,
        }
        self.write(self.work / "manifest.json", manifest)
        return manifest

    def land_votes(self, manifest: dict) -> list[Path]:
        """Three hash-bound votes answering the frozen packet."""
        paths = []
        (self.work / "round_1").mkdir(parents=True, exist_ok=True)
        for row in manifest["selected_raters"]:
            path = self.work / "round_1" / f"{row['persona']}.json"
            self.write(path, vote(row["persona"], row["independence_group"], manifest["packet_hash"]))
            paths.append(path)
        return paths

    def assert_votes_preserved(self, votes: list[Path], packet: str) -> None:
        parked = json.loads((self.work / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(parked["stage"], "parked")
        self.assertEqual(parked["parked"]["reason"], "evidence_drift_with_votes")
        self.assertEqual(parked["parked"]["votes_landed"], len(votes))
        for path in votes:
            self.assertTrue(path.exists(), path)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["evidence_hash"], packet)
        self.assertEqual(list(self.research.glob("committee_work/*-superseded-*")), [])
        self.assertEqual(parked["packet_hash"], packet)


class CommitteeLivelockTests(CommitteeFixture):
    # 1 - copy-on-freeze
    def test_packet_survives_a_live_evidence_rewrite(self):
        manifest = self.initialize()
        self.assertTrue(pipeline.has_snapshot(manifest))
        self.assertTrue((self.work / pipeline.SNAPSHOT_DIR / "thesis.md").exists())
        # the daily compiler rewrites the live research tree under the committee
        (self.research / "thesis.md").write_text("# AAA\n\nRewritten by the daily job.\n", encoding="utf-8")
        self.write(self.research / "valuation.json", {"ticker": "AAA", "rewritten": True})
        with patch.object(pipeline, "ROOT", self.root):
            self.assertTrue(pipeline.verify_packet(manifest))
            self.assertTrue(pipeline.live_evidence_drifted(manifest))
        with patch.object(select_committee_work, "ROOT", self.root), patch.object(pipeline, "ROOT", self.root):
            self.assertIsNone(select_committee_work.refresh_reason(manifest))

    def test_editing_a_frozen_copy_still_invalidates_the_packet(self):
        manifest = self.initialize()
        (self.work / pipeline.SNAPSHOT_DIR / "thesis.md").write_text("tampered\n", encoding="utf-8")
        with patch.object(pipeline, "ROOT", self.root):
            self.assertFalse(pipeline.verify_packet(manifest))
        with patch.object(select_committee_work, "ROOT", self.root), patch.object(pipeline, "ROOT", self.root):
            self.assertEqual(
                select_committee_work.refresh_reason(manifest),
                "frozen_copies_missing_or_modified",
            )

    def test_legacy_packet_without_snapshot_keeps_live_file_behaviour(self):
        with patch.object(pipeline, "ROOT", self.root):
            evidence = [pipeline.file_reference(self.research / "thesis.md")]
            manifest = self.legacy_manifest(evidence)
            self.assertTrue(pipeline.verify_packet(manifest))
            (self.research / "thesis.md").write_text("rewritten\n", encoding="utf-8")
            self.assertFalse(pipeline.verify_packet(manifest))

    def test_current_legacy_packet_adopts_copies_without_superseding(self):
        with patch.object(pipeline, "ROOT", self.root), patch.object(select_committee_work, "ROOT", self.root):
            evidence = [pipeline.file_reference(self.research / "thesis.md")]
            manifest = self.legacy_manifest(evidence, refresh_requested=True)
            before = manifest["packet_hash"]
            work = select_committee_work.refresh("AAA", "2026-07-18")
            self.assertEqual(work, self.work)
            adopted = json.loads((self.work / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(adopted["packet_hash"], before)
        self.assertTrue(pipeline.has_snapshot(adopted))
        self.assertEqual(adopted["stage"], "round_one_open")
        self.assertEqual(list(self.research.glob("committee_work/*-superseded-*")), [])

    # 2 - hash-bound votes
    def test_vote_without_evidence_hash_is_rejected_on_a_frozen_packet(self):
        manifest = self.initialize()
        packet = manifest["packet_hash"]
        (self.work / "round_1").mkdir(exist_ok=True)
        self.write(self.work / "round_1" / "hohn.json", vote("hohn", "competitive_advantage"))
        with patch.object(pipeline, "ROOT", self.root):
            _, errors = pipeline.load_round(self.work, 1, [manifest["selected_raters"][0]])
        self.assertTrue(any("evidence_hash is required" in message for message in errors), errors)
        self.write(self.work / "round_1" / "hohn.json", vote("hohn", "competitive_advantage", packet))
        with patch.object(pipeline, "ROOT", self.root):
            _, errors = pipeline.load_round(self.work, 1, [manifest["selected_raters"][0]])
        self.assertEqual(errors, [])

    def test_vote_answering_a_superseded_packet_is_rejected(self):
        manifest = self.initialize()
        (self.work / "round_1").mkdir(exist_ok=True)
        self.write(self.work / "round_1" / "hohn.json", vote("hohn", "competitive_advantage", "a" * 64))
        with patch.object(pipeline, "ROOT", self.root):
            _, errors = pipeline.load_round(self.work, 1, [manifest["selected_raters"][0]])
        self.assertTrue(any("answers a different packet" in message for message in errors), errors)

    def test_legacy_packet_accepts_an_absent_hash_but_never_a_wrong_one(self):
        with patch.object(pipeline, "ROOT", self.root):
            evidence = [pipeline.file_reference(self.research / "thesis.md")]
            self.legacy_manifest(evidence)
            (self.work / "round_1").mkdir(parents=True, exist_ok=True)
            self.write(self.work / "round_1" / "hohn.json", vote("hohn", "competitive_advantage"))
            _, errors = pipeline.load_round(self.work, 1, [RATERS[0]])
            self.assertEqual(errors, [])
            self.write(self.work / "round_1" / "hohn.json", vote("hohn", "competitive_advantage", "b" * 64))
            _, errors = pipeline.load_round(self.work, 1, [RATERS[0]])
        self.assertTrue(any("answers a different packet" in message for message in errors), errors)

    def test_pr_gate_rejects_a_vote_bound_to_another_packet(self):
        manifest = self.initialize()
        persona = manifest["selected_raters"][0]["persona"]
        group = manifest["selected_raters"][0]["independence_group"]
        rel = f"AAA/research/committee_work/2026-07-18/round_1/{persona}.json"
        (self.work / "round_1").mkdir(exist_ok=True)
        self.write(self.work / "round_1" / f"{persona}.json", vote(persona, group, "e" * 64))
        errors = validate_committee_pr_artifacts.validate_paths([rel], root=self.root)
        self.assertTrue(any("answers a different packet" in message for message in errors), errors)
        self.write(self.work / "round_1" / f"{persona}.json", vote(persona, group, manifest["packet_hash"]))
        self.assertEqual(validate_committee_pr_artifacts.validate_paths([rel], root=self.root), [])

    def test_pr_gate_refuses_edits_to_the_frozen_copies(self):
        self.initialize()
        errors = validate_committee_pr_artifacts.validate_paths(
            [f"AAA/research/committee_work/2026-07-18/{pipeline.SNAPSHOT_DIR}/thesis.md"],
            root=self.root,
        )
        self.assertTrue(any("unsupported committee artifact path" in message for message in errors), errors)

    def test_assembled_record_with_frozen_copies_matches_the_schema(self):
        with patch.object(pipeline, "ROOT", self.root), patch.object(committee_task_queue, "ROOT", self.root):
            manifest = self.initialize()
            packet = manifest["packet_hash"]
            committee_task_queue.next_tasks("AAA", "2026-07-18")
            self.write(self.work / "pre_mortem.json", {
                "status": "complete", "failure_story": "cycle breaks", "earliest_warning_signals": [],
                "forensic_checks": ["cash conversion"], "short_source_coverage": "partial", "unresolved_items": [],
            })
            for row in manifest["selected_raters"]:
                self.write(
                    self.work / "round_1" / f"{row['persona']}.json",
                    vote(row["persona"], row["independence_group"], packet),
                )
            committee_task_queue.next_tasks("AAA", "2026-07-18")
            self.write(self.work / "chair_synthesis.json", {
                "status": "complete", "primary_method": "quality_reinvestment",
                "weighting_rationale": "method fit", "agreed_facts": [], "disputed_facts": [],
                "recommendation": "watch",
                "monitoring_plan": {
                    "operational_milestones": [], "evidence_refresh_dates": [],
                    "valuation_refresh_triggers": ["filing"], "price_review_thresholds": [],
                    "thesis_break_conditions": [], "expected_catalyst_dates": [],
                    "outcome_horizons_months": [6, 12, 24],
                },
            })
            self.assertEqual(committee_task_queue.next_tasks("AAA", "2026-07-18"), [])
            # the live tree moves while the committee finishes; assembly must not care
            (self.research / "thesis.md").write_text("rewritten mid-committee\n", encoding="utf-8")
            output = pipeline.assemble(self.work)
        record = json.loads(output.read_text(encoding="utf-8"))
        schema = json.loads((Path(__file__).resolve().parents[1] / "templates" / "committee_schema.json").read_text(encoding="utf-8"))
        jsonschema.validate(record, schema)
        self.assertEqual(record["round_two"]["evidence_hash"], packet)
        self.assertTrue(all(row["evidence_hash"] == packet for row in record["round_one"]["votes"]))
        self.assertTrue(all(row["snapshot_path"] for row in record["evidence_packet"]["references"]))

    # 3 - supersede circuit breaker
    def test_refresh_limit_parks_the_committee_and_files_triage(self):
        with patch.object(pipeline, "ROOT", self.root), patch.object(select_committee_work, "ROOT", self.root):
            manifest = self.initialize()
            manifest["refresh_count"] = pipeline.MAX_REFRESHES_WITHOUT_VOTES
            manifest["refresh_requested"] = True
            pipeline.write_json(self.work / "manifest.json", manifest)
            select_committee_work.refresh("AAA", "2026-07-18")
            parked = json.loads((self.work / "manifest.json").read_text(encoding="utf-8"))
            triage = json.loads(pipeline.triage_path().read_text(encoding="utf-8"))
            result = select_committee_work.select()
        self.assertEqual(parked["stage"], "parked")
        self.assertEqual(parked["parked"]["reason"], "refresh_limit")
        self.assertEqual([row["ticker"] for row in triage["parked"]], ["AAA"])
        self.assertEqual(triage["parked"][0]["committee_date"], "2026-07-18")
        self.assertEqual(list(self.research.glob("committee_work/*-superseded-*")), [])
        self.assertEqual(result["action"], "none")

    def test_refresh_below_the_limit_still_supersedes_and_counts(self):
        with patch.object(pipeline, "ROOT", self.root), patch.object(select_committee_work, "ROOT", self.root):
            manifest = self.initialize()
            manifest["refresh_requested"] = True
            pipeline.write_json(self.work / "manifest.json", manifest)
            select_committee_work.refresh("AAA", "2026-07-18")
            fresh = json.loads((self.work / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(fresh["refresh_count"], 1)
        self.assertEqual(fresh["stage"], "round_one_open")
        self.assertEqual(len(list(self.research.glob("committee_work/*-superseded-*"))), 1)

    def test_existing_supersede_archives_count_against_the_breaker(self):
        with patch.object(pipeline, "ROOT", self.root), patch.object(select_committee_work, "ROOT", self.root):
            evidence = [pipeline.file_reference(self.research / "thesis.md")]
            self.legacy_manifest(evidence)
            for index in range(pipeline.MAX_REFRESHES_WITHOUT_VOTES):
                (self.work.parent / f"2026-07-18-superseded-{index:08d}").mkdir(parents=True)
            (self.research / "thesis.md").write_text("rewritten by the daily job\n", encoding="utf-8")
            select_committee_work.refresh("AAA", "2026-07-18")
            parked = json.loads((self.work / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(parked["stage"], "parked")
        self.assertEqual(parked["parked"]["reason"], "refresh_limit")
        self.assertEqual(parked["parked"]["refresh_count"], pipeline.MAX_REFRESHES_WITHOUT_VOTES)

    def test_drifted_legacy_packet_with_votes_parks_instead_of_discarding_them(self):
        with patch.object(pipeline, "ROOT", self.root), patch.object(select_committee_work, "ROOT", self.root):
            evidence = [pipeline.file_reference(self.research / "thesis.md")]
            self.legacy_manifest(evidence)
            (self.work / "round_1").mkdir(parents=True, exist_ok=True)
            self.write(self.work / "round_1" / "hohn.json", vote("hohn", "competitive_advantage"))
            (self.research / "thesis.md").write_text("rewritten by the daily job\n", encoding="utf-8")
            select_committee_work.refresh("AAA", "2026-07-18")
            parked = json.loads((self.work / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(parked["stage"], "parked")
        self.assertEqual(parked["parked"]["reason"], "evidence_drift_with_votes")
        self.assertEqual(parked["parked"]["votes_landed"], 1)
        self.assertTrue((self.work / "round_1" / "hohn.json").exists())
        self.assertEqual(list(self.research.glob("committee_work/*-superseded-*")), [])

    def test_frozen_packet_with_votes_parks_on_an_explicit_refresh_request(self):
        with patch.object(pipeline, "ROOT", self.root), patch.object(select_committee_work, "ROOT", self.root):
            manifest = self.initialize()
            votes = self.land_votes(manifest)
            manifest["refresh_requested"] = True
            pipeline.write_json(self.work / "manifest.json", manifest)
            select_committee_work.refresh("AAA", "2026-07-18")
        self.assert_votes_preserved(votes, manifest["packet_hash"])

    def test_frozen_packet_with_votes_parks_when_the_snapshot_dir_is_gone(self):
        with patch.object(pipeline, "ROOT", self.root), patch.object(select_committee_work, "ROOT", self.root):
            manifest = self.initialize()
            votes = self.land_votes(manifest)
            shutil.rmtree(self.work / pipeline.SNAPSHOT_DIR)
            self.assertEqual(
                select_committee_work.refresh_reason(manifest),
                "frozen_copies_missing_or_modified",
            )
            select_committee_work.refresh("AAA", "2026-07-18")
        self.assert_votes_preserved(votes, manifest["packet_hash"])

    def test_frozen_packet_with_votes_parks_when_one_frozen_copy_is_missing(self):
        with patch.object(pipeline, "ROOT", self.root), patch.object(select_committee_work, "ROOT", self.root):
            manifest = self.initialize()
            votes = self.land_votes(manifest)
            (self.work / pipeline.SNAPSHOT_DIR / "thesis.md").unlink()
            select_committee_work.refresh("AAA", "2026-07-18")
        self.assert_votes_preserved(votes, manifest["packet_hash"])

    def test_frozen_packet_with_votes_parks_when_one_frozen_copy_is_modified(self):
        with patch.object(pipeline, "ROOT", self.root), patch.object(select_committee_work, "ROOT", self.root):
            manifest = self.initialize()
            votes = self.land_votes(manifest)
            (self.work / pipeline.SNAPSHOT_DIR / "thesis.md").write_text("tampered\n", encoding="utf-8")
            select_committee_work.refresh("AAA", "2026-07-18")
        self.assert_votes_preserved(votes, manifest["packet_hash"])

    def test_refresh_limit_never_outranks_landed_votes(self):
        """A packet over the refresh budget with votes parks for the votes, not the budget."""
        with patch.object(pipeline, "ROOT", self.root), patch.object(select_committee_work, "ROOT", self.root):
            manifest = self.initialize()
            votes = self.land_votes(manifest)
            manifest["refresh_count"] = pipeline.MAX_REFRESHES_WITHOUT_VOTES
            manifest["refresh_requested"] = True
            pipeline.write_json(self.work / "manifest.json", manifest)
            select_committee_work.refresh("AAA", "2026-07-18")
        self.assert_votes_preserved(votes, manifest["packet_hash"])

    # 2b - vote binding fails closed
    def test_a_vote_without_a_manifest_fails_closed(self):
        with patch.object(pipeline, "ROOT", self.root):
            (self.work / "round_1").mkdir(parents=True, exist_ok=True)
            self.write(self.work / "round_1" / "hohn.json", vote("hohn", "competitive_advantage"))
            binding = pipeline.vote_binding(self.work)
            self.assertEqual(binding["hash_binding"], "required")
            _, errors = pipeline.load_round(self.work, 1, [RATERS[0]])
        self.assertTrue(any("no frozen packet hash" in message for message in errors), errors)

    def test_a_stale_assembled_archive_is_never_overwritten(self):
        manifest = self.initialize()
        with patch.object(pipeline, "ROOT", self.root):
            for tail in ("1" * 56, "2" * 56):
                self.write(self.research / "committee_2026-07-18.json", {
                    "ticker": "AAA",
                    "evidence_packet": {"packet_hash": "dddddddd" + tail},
                })
                pipeline.archive_stale_assembled("AAA", "2026-07-18", manifest["packet_hash"])
        archives = sorted(path.name for path in self.research.glob("committee_2026-07-18-superseded-*.json"))
        self.assertEqual(archives, [
            "committee_2026-07-18-superseded-dddddddd-2.json",
            "committee_2026-07-18-superseded-dddddddd.json",
        ])
        first = json.loads((self.research / "committee_2026-07-18-superseded-dddddddd.json").read_text(encoding="utf-8"))
        self.assertEqual(first["evidence_packet"]["packet_hash"], "dddddddd" + "1" * 56)

    # 4 - ADBE-class deadlock
    def test_assembled_record_from_a_superseded_packet_does_not_hide_live_work(self):
        manifest = self.initialize()
        self.write(self.research / "committee_2026-07-18.json", {
            "ticker": "AAA",
            "final_state": "evidence_blocked",
            "evidence_packet": {"packet_hash": "c" * 64},
        })
        with patch.object(select_committee_work, "ROOT", self.root), patch.object(
            pipeline, "ROOT", self.root
        ), patch.object(select_committee_work, "next_tasks", return_value=[{"task_id": "pre_mortem"}]):
            result = select_committee_work.select()
        self.assertEqual(result["action"], "advance")
        self.assertEqual(result["ticker"], "AAA")
        self.assertTrue(result["stale_assembled"])
        self.assertNotEqual(manifest["packet_hash"], "c" * 64)

    def test_assembled_record_for_the_same_packet_is_still_skipped(self):
        manifest = self.initialize()
        self.write(self.research / "committee_2026-07-18.json", {
            "ticker": "AAA",
            "final_state": "evidence_blocked",
            "evidence_packet": {"packet_hash": manifest["packet_hash"]},
        })
        with patch.object(select_committee_work, "ROOT", self.root), patch.object(
            pipeline, "ROOT", self.root
        ), patch.object(select_committee_work, "next_tasks") as queued:
            result = select_committee_work.select()
        self.assertEqual(result["action"], "none")
        queued.assert_not_called()

    def test_stale_assembled_record_is_archived_out_of_the_reader_glob(self):
        manifest = self.initialize()
        self.write(self.research / "committee_2026-07-18.json", {
            "ticker": "AAA",
            "evidence_packet": {"packet_hash": "d" * 64},
        })
        with patch.object(pipeline, "ROOT", self.root):
            archive = pipeline.archive_stale_assembled("AAA", "2026-07-18", manifest["packet_hash"])
        self.assertIsNotNone(archive)
        self.assertEqual(archive.name, "committee_2026-07-18-superseded-dddddddd.json")
        self.assertFalse((self.research / "committee_2026-07-18.json").exists())
        self.assertEqual(list(self.research.glob("committee_????-??-??.json")), [])

    # queue health
    def test_a_packet_needing_refresh_does_not_block_other_live_work(self):
        with patch.object(pipeline, "ROOT", self.root):
            evidence = [pipeline.file_reference(self.research / "thesis.md")]
            self.legacy_manifest(evidence)
            (self.research / "thesis.md").write_text("rewritten\n", encoding="utf-8")
            other = self.root / "BBB" / "research" / "committee_work" / "2026-07-19"
            other.mkdir(parents=True)
            self.write(other / "manifest.json", {
                "ticker": "BBB", "as_of": "2026-07-19", "stage": "round_one_open",
                "packet_hash": pipeline.packet_hash([]), "evidence": [], "selected_raters": RATERS,
            })
            with patch.object(select_committee_work, "ROOT", self.root), patch.object(
                select_committee_work, "next_tasks", return_value=[{"task_id": "pre_mortem"}]
            ):
                result = select_committee_work.select()
        self.assertEqual(result["action"], "advance")
        self.assertEqual(result["ticker"], "BBB")


class InitializeIsNotASecondDoorTests(CommitteeFixture):
    """5 - re-initializing over live work must be refused, not silently done."""

    def test_initialize_refuses_a_work_dir_that_already_holds_votes(self):
        with patch.object(pipeline, "ROOT", self.root):
            manifest = self.initialize()
            votes = self.land_votes(manifest)
            with self.assertRaises(FileExistsError) as caught:
                pipeline.initialize("AAA", "2026-07-18")
            after = json.loads((self.work / "manifest.json").read_text(encoding="utf-8"))
            _, errors = pipeline.load_round(self.work, 1, manifest["selected_raters"])
        self.assertIn("vote file(s) already answer this packet", str(caught.exception))
        self.assertEqual(after["packet_hash"], manifest["packet_hash"])
        self.assertEqual(after["stage"], "round_one_open")
        self.assertEqual(errors, [])
        for path in votes:
            self.assertTrue(path.exists(), path)

    def test_initialize_refuses_a_parked_work_dir_and_keeps_its_votes_valid(self):
        with patch.object(pipeline, "ROOT", self.root), patch.object(select_committee_work, "ROOT", self.root):
            manifest = self.initialize()
            votes = self.land_votes(manifest)
            manifest["refresh_requested"] = True
            pipeline.write_json(self.work / "manifest.json", manifest)
            select_committee_work.refresh("AAA", "2026-07-18")
            with self.assertRaises(FileExistsError) as caught:
                pipeline.initialize("AAA", "2026-07-18")
            parked = json.loads((self.work / "manifest.json").read_text(encoding="utf-8"))
            _, errors = pipeline.load_round(self.work, 1, manifest["selected_raters"])
        self.assertIn("the committee is parked", str(caught.exception))
        self.assertEqual(parked["stage"], "parked")
        self.assertEqual(parked["parked"]["reason"], "evidence_drift_with_votes")
        self.assertEqual(parked["packet_hash"], manifest["packet_hash"])
        self.assertEqual(parked.get("refresh_count", 0), 0)
        # the whole point: the three preserved votes are still valid answers
        self.assertEqual(errors, [])
        self.assertEqual(len(votes), 3)

    def test_initialize_still_opens_a_clean_work_dir(self):
        with patch.object(pipeline, "ROOT", self.root):
            self.initialize()
            shutil.rmtree(self.work)
            manifest = self.initialize()
        self.assertEqual(manifest["stage"], "round_one_open")

    def test_parked_is_a_busy_committee_state_for_the_security_pipeline(self):
        self.assertIn("parked", run_security_decision_pipeline.BUSY_COMMITTEE_STATES)

    def test_the_security_pipeline_never_reinitializes_an_existing_packet_date(self):
        with patch.object(pipeline, "ROOT", self.root), patch.object(select_committee_work, "ROOT", self.root):
            manifest = self.initialize()
            self.land_votes(manifest)
            manifest["refresh_requested"] = True
            pipeline.write_json(self.work / "manifest.json", manifest)
            select_committee_work.refresh("AAA", "2026-07-18")
            with patch.object(run_security_decision_pipeline, "ROOT", self.root), patch.object(
                run_security_decision_pipeline, "registry_entries", return_value={"AAA": {}}
            ):
                result = run_security_decision_pipeline.stage_committees(["AAA"], "2026-07-18", dry_run=False)
            after = json.loads((self.work / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(result["initiated"], [])
        self.assertEqual([row["stage"] for row in result["active"]], ["parked"])
        self.assertEqual(after["stage"], "parked")
        self.assertEqual(after["packet_hash"], manifest["packet_hash"])

    def test_the_workbench_reports_parked_instead_of_an_open_review(self):
        with patch.object(pipeline, "ROOT", self.root), patch.object(select_committee_work, "ROOT", self.root):
            manifest = self.initialize()
            self.land_votes(manifest)
            manifest["refresh_requested"] = True
            pipeline.write_json(self.work / "manifest.json", manifest)
            select_committee_work.refresh("AAA", "2026-07-18")
        with patch.object(build_valuation_workbench, "ROOT", self.root):
            view = build_valuation_workbench.committee_view(self.research)
        self.assertEqual(view["status"], "parked")
        self.assertEqual(view["stage"], "parked")
        self.assertEqual(view["parked"]["reason"], "evidence_drift_with_votes")
        self.assertIn("--unpark AAA --unpark-date 2026-07-18", view["next_action"])
        schema = json.loads(
            (Path(__file__).resolve().parents[1] / "templates" / "valuation_workbench_schema.json").read_text(encoding="utf-8")
        )
        jsonschema.validate({"committee": view}, {"type": "object", "properties": schema["properties"]})


class UnparkTests(CommitteeFixture):
    """6 - stage=parked is not a dead end."""

    def park_with_votes(self) -> dict:
        manifest = self.initialize()
        self.land_votes(manifest)
        manifest["refresh_requested"] = True
        pipeline.write_json(self.work / "manifest.json", manifest)
        select_committee_work.refresh("AAA", "2026-07-18")
        return manifest

    def test_parked_committees_are_listed_for_the_human(self):
        with patch.object(pipeline, "ROOT", self.root), patch.object(select_committee_work, "ROOT", self.root):
            self.park_with_votes()
            # select() and the refresh backlog both skip a terminal stage
            self.assertEqual(select_committee_work.select()["action"], "none")
            self.assertEqual(select_committee_work.refresh_backlog(), [])
            rows = select_committee_work.parked_committees()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ticker"], "AAA")
        self.assertEqual(rows[0]["committee_date"], "2026-07-18")
        self.assertEqual(rows[0]["state"], "parked")
        self.assertEqual(rows[0]["votes_landed"], 3)
        self.assertEqual(rows[0]["reason"], "evidence_drift_with_votes")

    def test_resume_keeps_the_votes_when_the_frozen_copies_still_verify(self):
        with patch.object(pipeline, "ROOT", self.root), patch.object(select_committee_work, "ROOT", self.root):
            manifest = self.park_with_votes()
            work = select_committee_work.unpark("AAA", "2026-07-18", "resume")
            resumed = json.loads((work / "manifest.json").read_text(encoding="utf-8"))
            _, errors = pipeline.load_round(self.work, 1, manifest["selected_raters"])
            triage = json.loads(pipeline.triage_path().read_text(encoding="utf-8"))
            still_parked = select_committee_work.parked_committees()
        self.assertEqual(resumed["stage"], "round_one_open")
        self.assertNotIn("parked", resumed)
        self.assertNotIn("refresh_requested", resumed)
        self.assertEqual(resumed["packet_hash"], manifest["packet_hash"])
        self.assertEqual(resumed["unparked"]["packet"], "unchanged")
        self.assertEqual(resumed["unparked"]["votes_kept"], 3)
        self.assertEqual(errors, [])
        self.assertEqual(triage["parked"], [])
        self.assertEqual(still_parked, [])

    def test_resume_with_damaged_frozen_copies_refreezes_and_invalidates_the_votes(self):
        with patch.object(pipeline, "ROOT", self.root), patch.object(select_committee_work, "ROOT", self.root):
            manifest = self.park_with_votes()
            old_packet = manifest["packet_hash"]
            # the frozen copies the votes answered are gone, and live evidence moved
            shutil.rmtree(self.work / pipeline.SNAPSHOT_DIR)
            (self.research / "thesis.md").write_text("# AAA\n\nRewritten after the park.\n", encoding="utf-8")
            work = select_committee_work.unpark("AAA", "2026-07-18", "resume")
            resumed = json.loads((work / "manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(pipeline.verify_packet(resumed))
            tasks_reopened = pipeline.vote_files(self.work)
        self.assertNotEqual(resumed["packet_hash"], old_packet)
        self.assertEqual(resumed["stage"], "round_one_open")
        self.assertEqual(resumed["unparked"]["packet"], "re_frozen_from_live_evidence")
        self.assertEqual(resumed["unparked"]["superseded_packet_hash"], old_packet)
        self.assertEqual(resumed["unparked"]["votes_kept"], 0)
        self.assertEqual(len(resumed["unparked"]["invalidated_votes"]), 3)
        # the stale votes are out of the rounds, so the rounds are open again ...
        self.assertEqual(tasks_reopened, [])
        # ... but kept on disk, clearly labelled, never silently accepted
        archived = sorted((self.work / "invalidated_votes" / old_packet[:8] / "round_1").glob("*.json"))
        self.assertEqual(len(archived), 3)
        self.assertEqual(
            json.loads(archived[0].read_text(encoding="utf-8"))["evidence_hash"], old_packet
        )
        # the re-issued prompts quote the new packet, never the dead one
        prompt = (self.work / "round_1" / "hohn.prompt.md").read_text(encoding="utf-8")
        self.assertIn(resumed["packet_hash"], prompt)
        self.assertNotIn(old_packet, prompt)

    def test_a_resumed_committee_is_selectable_work_again(self):
        with patch.object(pipeline, "ROOT", self.root), patch.object(select_committee_work, "ROOT", self.root):
            self.park_with_votes()
            select_committee_work.unpark("AAA", "2026-07-18", "resume")
            with patch.object(select_committee_work, "next_tasks", return_value=[{"task_id": "pre_mortem"}]):
                result = select_committee_work.select()
        self.assertEqual(result["action"], "advance")
        self.assertEqual(result["ticker"], "AAA")

    def test_discard_archives_the_parked_packet_and_freezes_a_new_one(self):
        with patch.object(pipeline, "ROOT", self.root), patch.object(select_committee_work, "ROOT", self.root):
            manifest = self.park_with_votes()
            old_packet = manifest["packet_hash"]
            (self.research / "thesis.md").write_text("# AAA\n\nRewritten after the park.\n", encoding="utf-8")
            work = select_committee_work.unpark("AAA", "2026-07-18", "discard")
            fresh = json.loads((work / "manifest.json").read_text(encoding="utf-8"))
            triage = json.loads(pipeline.triage_path().read_text(encoding="utf-8"))
        self.assertEqual(work, self.work)
        self.assertEqual(fresh["stage"], "round_one_open")
        self.assertNotEqual(fresh["packet_hash"], old_packet)
        self.assertEqual(fresh["refresh_count"], 0)
        self.assertEqual(fresh["unparked"]["mode"], "discard")
        self.assertEqual(fresh["unparked"]["discarded_votes"], 3)
        self.assertEqual(pipeline.vote_files(self.work), [])
        self.assertEqual(triage["parked"], [])
        archives = list(self.research.glob("committee_work/2026-07-18-parked-discarded-*"))
        self.assertEqual(len(archives), 1)
        discarded = sorted((archives[0] / "round_1").glob("*.json"))
        self.assertEqual(len(discarded), 3)
        self.assertEqual(
            json.loads((archives[0] / "manifest.json").read_text(encoding="utf-8"))["stage"], "superseded"
        )

    def test_unpark_refuses_a_committee_that_is_not_parked(self):
        with patch.object(pipeline, "ROOT", self.root), patch.object(select_committee_work, "ROOT", self.root):
            self.initialize()
            with self.assertRaises(ValueError) as caught:
                select_committee_work.unpark("AAA", "2026-07-18", "resume")
        self.assertIn("not 'parked'", str(caught.exception))

    def test_unpark_refuses_an_unknown_mode_and_a_missing_committee(self):
        with patch.object(pipeline, "ROOT", self.root), patch.object(select_committee_work, "ROOT", self.root):
            with self.assertRaises(ValueError):
                select_committee_work.unpark("AAA", "2026-07-18", "delete")
            with self.assertRaises(FileNotFoundError):
                select_committee_work.unpark("AAA", "2026-07-19", "resume")

    def test_a_triage_row_left_behind_by_a_manual_edit_is_reported_as_stale(self):
        with patch.object(pipeline, "ROOT", self.root), patch.object(select_committee_work, "ROOT", self.root):
            self.park_with_votes()
            manifest = json.loads((self.work / "manifest.json").read_text(encoding="utf-8"))
            manifest["stage"] = "round_one_open"
            manifest.pop("parked")
            pipeline.write_json(self.work / "manifest.json", manifest)
            rows = select_committee_work.parked_committees()
        self.assertEqual([row["state"] for row in rows], ["stale_triage_entry"])


class CommitteeWorkflowGateTests(unittest.TestCase):
    def test_refresh_job_is_gated_on_the_agent_execution_flag(self):
        workflow = (
            Path(__file__).resolve().parents[2] / ".github" / "workflows" / "investment-committee.yml"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "if: needs.prepare.outputs.action == 'refresh' && vars.COMMITTEE_AGENTS_ENABLED == 'true'",
            workflow,
        )
        self.assertIn("Queue bounded human committee review", workflow)
        self.assertNotIn("CURSOR_API_KEY", workflow)

    def test_a_held_refresh_reports_the_queue_instead_of_a_silent_green_run(self):
        workflow = (
            Path(__file__).resolve().parents[2] / ".github" / "workflows" / "investment-committee.yml"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "if: steps.pending.outputs.action == 'refresh' && vars.COMMITTEE_AGENTS_ENABLED != 'true'",
            workflow,
        )
        self.assertIn("select_committee_work.py --refresh-backlog", workflow)
        self.assertIn("GITHUB_STEP_SUMMARY", workflow)

    def test_every_run_surfaces_the_parked_queue_exactly_once(self):
        workflow = (
            Path(__file__).resolve().parents[2] / ".github" / "workflows" / "investment-committee.yml"
        ).read_text(encoding="utf-8")
        # --refresh-backlog prints the parked section itself, so the standalone
        # step is skipped in exactly the case that step runs.
        self.assertIn("select_committee_work.py --parked", workflow)
        self.assertIn(
            "if: always() && (steps.pending.outputs.action != 'refresh' "
            "|| vars.COMMITTEE_AGENTS_ENABLED == 'true')",
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
