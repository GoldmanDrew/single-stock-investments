from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import run_security_decision_pipeline as pipeline


class SecurityDecisionPipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_root = pipeline.ROOT
        self.old_followups = pipeline.FOLLOWUPS
        pipeline.ROOT = Path(self.tmp.name)
        pipeline.FOLLOWUPS = pipeline.ROOT / "_system/reference/valuation_followups.json"

    def tearDown(self):
        pipeline.ROOT = self.old_root
        pipeline.FOLLOWUPS = self.old_followups
        self.tmp.cleanup()

    def write(self, relative: str, value: dict) -> None:
        path = pipeline.ROOT / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_contract_stage_marks_legacy_only_model_evidence_blocked(self):
        self.write(
            "AAA/research/valuation.json",
            {"ticker": "AAA", "method": "full", "inputs": {"price": 10}, "implied_return": {"base_pct": 15}},
        )
        self.write(
            "AAA/research/valuation_route.json",
            {"profile_id": "quality_reinvestment", "status": "routed", "label": "High-return compounder"},
        )
        result = pipeline.stage_contracts(["AAA"], dry_run=False)
        self.assertEqual(result["errors"], [])
        contract = json.loads((pipeline.ROOT / "AAA/research/valuation_contract.json").read_text())
        self.assertEqual(contract["status"], "evidence_blocked")
        self.assertTrue(contract["legacy_reference_present"])

    def test_contract_stage_refreshes_stale_values_and_keeps_only_open_curated_gaps(self):
        valuation = {
            "ticker": "MSB",
            "as_of": "2026-07-18",
            "method": "pending",
            "inputs": {"price": 25, "shares_outstanding": 100},
            "classification_inputs": {"archetype": "resource"},
            "component_valuation_results": {
                "status": "complete",
                "all_material_components_identified": True,
                "additive_components": [{
                    "id": "royalty", "label": "Royalty", "category": "operating_business",
                    "treatment": "additive", "method": "royalty_distribution_curve",
                    "evidence_tier": "primary", "evidence": "filing",
                    "low_per_share": 20, "base_per_share": 34, "high_per_share": 50,
                }],
                "embedded_components": [],
                "total_equity_value_per_share": {"low": 20, "base": 34, "high": 50},
            },
            "economic_value_analysis": {"validation_errors": [], "valuation_proof": []},
        }
        self.write("MSB/research/valuation.json", valuation)
        self.write("MSB/research/valuation_route.json", {"profile_id": "scarce_asset_optionality"})
        self.write("MSB/research/valuation_contract.json", {
            "status": "evidence_blocked", "valuation": {"value_per_share": {"base": 41}},
            "cohort_purpose": "royalty test",
        })
        self.write("_system/reference/valuation_followups.json", {
            "tickers": {"MSB": {"evidence_gaps": [
                {"id": "open_gap", "status": "open", "question": "Need reserve life."},
                {"id": "closed_gap", "status": "accepted", "question": "Cash reconciled."},
            ]}}
        })

        result = pipeline.stage_contracts(["MSB"], dry_run=False)

        self.assertEqual(result["errors"], [])
        contract = json.loads((pipeline.ROOT / "MSB/research/valuation_contract.json").read_text())
        self.assertIsNone(contract["valuation"]["value_per_share"]["base"])
        self.assertEqual(contract["valuation"]["legacy_value_per_share"]["base"], 34)
        self.assertIn("open_gap: Need reserve life.", contract["evidence"]["blockers"])
        self.assertTrue(any("valid calculation proof" in row for row in contract["evidence"]["blockers"]))
        self.assertEqual(contract["cohort_purpose"], "royalty test")
        self.assertEqual(contract["status"], "evidence_blocked")

    def test_price_trigger_does_not_bypass_evidence_gate(self):
        self.write(
            "BBB/research/valuation_workbench.json",
            {"decision": {"status": "evidence_blocked"}, "committee": {"status": "not_started"}},
        )
        self.write("BBB/research/pricing_analysis.json", {"price": 10, "primary_entry_price_15pct_base": 20})
        old_entries = pipeline.registry_entries
        pipeline.registry_entries = lambda: {"BBB": {"classification": {"stance": "watch"}}}
        try:
            result = pipeline.stage_committees(["BBB"], "2026-07-18", dry_run=True)
        finally:
            pipeline.registry_entries = old_entries
        self.assertEqual(result["initiated"], [])
        self.assertEqual(result["triggered_evidence_tasks"][0]["ticker"], "BBB")

    def test_pricing_stage_neutralizes_stale_artifact_when_proof_is_blocked(self):
        self.write(
            "STALE/research/valuation_workbench.json",
            {"decision": {"status": "evidence_blocked", "model_level": "evidence_blocked"}},
        )
        self.write(
            "STALE/research/pricing_analysis.json",
            {"schema_version": "2.0", "primary_entry_price_15pct_base": 99},
        )
        calls = []
        old_builder = pipeline.build_contract_pricing
        pipeline.build_contract_pricing = lambda ticker, as_of: calls.append((ticker, as_of))
        try:
            result = pipeline.stage_pricing(["STALE"], "2026-08-30", dry_run=False)
        finally:
            pipeline.build_contract_pricing = old_builder
        self.assertEqual(calls, [("STALE", "2026-08-30")])
        self.assertEqual(result["neutralized"], ["STALE"])
        self.assertEqual(result["skipped"], ["STALE"])
        self.assertEqual(result["errors"], [])

    def test_tier_two_cannot_auto_start_committee(self):
        self.write(
            "TWO/research/valuation_workbench.json",
            {
                "decision": {"status": "decision_grade", "model_level": "stock_specific"},
                "committee": {"status": "not_started"},
            },
        )
        self.write("TWO/research/committee_trigger.json", {"status": "open", "reason": "material change"})
        manifest = {"assignments": {"TWO": {"tier": 2}}}
        result = pipeline.stage_committees(
            ["TWO"], "2026-08-30", dry_run=True, tier_manifest=manifest
        )
        self.assertEqual(result["initiated"], [])
        self.assertEqual(result["tier_restricted"][0]["ticker"], "TWO")

    def test_tier_one_generic_screen_cannot_auto_start_committee(self):
        self.write(
            "SCREEN/research/valuation_workbench.json",
            {
                "decision": {"status": "decision_grade", "model_level": "screening_grade"},
                "committee": {"status": "not_started"},
            },
        )
        self.write("SCREEN/research/committee_trigger.json", {"status": "open", "reason": "material change"})
        manifest = {"assignments": {"SCREEN": {"tier": 1}}}
        result = pipeline.stage_committees(
            ["SCREEN"], "2026-08-30", dry_run=True, tier_manifest=manifest
        )
        self.assertEqual(result["initiated"], [])
        self.assertEqual(result["triggered_evidence_tasks"][0]["model_level"], "screening_grade")

    def test_tier_one_stock_specific_model_can_enter_committee_dry_run(self):
        self.write(
            "READY/research/valuation_workbench.json",
            {
                "decision": {"status": "decision_grade", "model_level": "stock_specific"},
                "committee": {"status": "not_started"},
            },
        )
        self.write("READY/research/committee_trigger.json", {"status": "open", "reason": "material change"})
        manifest = {"assignments": {"READY": {"tier": 1}}}
        result = pipeline.stage_committees(
            ["READY"], "2026-08-30", dry_run=True, tier_manifest=manifest
        )
        self.assertEqual(result["initiated"][0]["ticker"], "READY")

    def test_missing_model_gets_autonomous_evidence_blocked_scaffold(self):
        self.write("ZZZ/research/valuation_route.json", {
            "profile_id": "quality_reinvestment", "status": "routed", "label": "High-return compounder",
            "required_evidence": ["normalized owner earnings", "incremental return on capital"],
            "primary_methods": ["owner_earnings_reinvestment_dcf"], "corroborating_methods": ["reverse_dcf"],
            "silent_personas": [],
        })
        result = pipeline.stage_contracts(["ZZZ"], dry_run=False, as_of="2026-07-18")
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["scaffolded"], ["ZZZ"])
        scaffold = json.loads((pipeline.ROOT / "ZZZ/research/valuation_model_scaffold.json").read_text())
        contract = json.loads((pipeline.ROOT / "ZZZ/research/valuation_contract.json").read_text())
        self.assertIn("deterministic low/base/high calculation proof", scaffold["required_outputs"])
        self.assertEqual(contract["status"], "evidence_blocked")
        self.assertEqual(contract["component_coverage"]["unvalued_component_count"], 1)

    def test_priority_scope_is_core_hold_and_accumulate_only(self):
        old_entries = pipeline.registry_entries
        pipeline.registry_entries = lambda: {
            "CORE": {"classification": {"stance": "core"}},
            "HOLD": {"classification": {"stance": "hold"}},
            "WATCH": {"classification": {"stance": "watch"}},
        }
        try:
            self.assertEqual(pipeline.selected_tickers("priority"), ["CORE", "HOLD"])
        finally:
            pipeline.registry_entries = old_entries

    def test_priority_scope_uses_tier_one_and_two_manifest(self):
        manifest = {
            "assignments": {
                "ONE": {"tier": 1}, "TWO": {"tier": 2}, "THREE": {"tier": 3},
            }
        }
        self.assertEqual(
            pipeline.selected_tickers("priority", tier_manifest=manifest),
            ["ONE", "TWO"],
        )

    def test_contract_carries_falsifier_coverage_from_sidecar(self):
        # The sidecar is the durable source (contracts are regenerated);
        # the contract carries only a summary, and never a blocker from it.
        # The contract must actually carry the components and falsifier texts
        # the sidecar types: coverage_summary anchor-checks component_id
        # against economic_ownership_map and derived_from against the
        # contract's falsifier texts, so a spec typing nothing real counts as
        # unanchored, never typed.
        self.write(
            "AAA/research/valuation.json",
            {"ticker": "AAA", "method": "full", "inputs": {"price": 10},
             "component_valuation_results": {"additive_components": [
                 {"id": "ops", "label": "Operating business", "treatment": "additive",
                  "method": "owner_earnings", "falsifier": "Owner cash collapses"},
                 {"id": "governance", "label": "Governance", "treatment": "additive",
                  "method": "qualitative", "falsifier": "Board stops acting like owners"},
             ]}},
        )
        self.write("AAA/research/valuation_route.json", {"profile_id": "quality_reinvestment"})
        self.write("AAA/research/falsifier_specs.json", {
            "schema_version": "1.0",
            "ticker": "AAA",
            "specs": [
                {"component_id": "ops", "metric": "owner_cash", "comparator": "lt",
                 "threshold": 10.0, "unit": "USD_m", "due": "2027-01-31",
                 "source_hint": "owner_cash_m", "derived_from": "Owner cash collapses",
                 "untestable": False, "rationale": "Thesis needs positive owner cash."},
                {"component_id": "governance", "metric": "board_alignment",
                 "comparator": "lt", "threshold": None, "unit": "qualitative",
                 "due": None, "source_hint": None, "derived_from": "Board stops acting like owners",
                 "untestable": True, "rationale": "No data surface scores this."},
            ],
        })
        result = pipeline.stage_contracts(["AAA"], dry_run=False)
        self.assertEqual(result["errors"], [])
        contract = json.loads((pipeline.ROOT / "AAA/research/valuation_contract.json").read_text())
        coverage = contract["falsifier_coverage"]
        self.assertEqual(coverage["typed"], 1)
        self.assertEqual(coverage["untestable"], 1)
        self.assertEqual(coverage["unanchored"], 0)
        self.assertEqual(coverage["spec_ref"], "AAA/research/falsifier_specs.json")
        self.assertFalse(coverage["enforcement_enabled"])
        self.assertFalse(any("falsifier" in blocker.lower() for blocker in contract["evidence"]["blockers"]))

    def test_scaffold_contract_carries_falsifier_coverage(self):
        self.write("ZZZ/research/valuation_route.json", {
            "profile_id": "quality_reinvestment", "status": "routed",
            "required_evidence": [], "primary_methods": [], "corroborating_methods": [],
            "silent_personas": [],
        })
        result = pipeline.stage_contracts(["ZZZ"], dry_run=False, as_of="2026-08-10")
        self.assertEqual(result["errors"], [])
        contract = json.loads((pipeline.ROOT / "ZZZ/research/valuation_contract.json").read_text())
        self.assertEqual(contract["falsifier_coverage"]["typed"], 0)
        self.assertIsNone(contract["falsifier_coverage"]["spec_ref"])

    def test_targeted_summary_does_not_overwrite_universe_summary(self):
        path = pipeline.write_summary(
            "2026-07-18", "all", ["MSB"], {"dashboard": {"status": "refreshed"}}, False, explicit=True
        )
        self.assertEqual(path.name, "power_zone_security_run_2026-07-18_msb.json")
        self.assertEqual(path.parent, pipeline.ROOT / "_system/data/runs")
        self.assertFalse((pipeline.ROOT / "_system/data/runs/power_zone_universe_run_2026-07-18.json").exists())

    def test_prospective_gate_blocks_only_new_or_changed_components(self):
        self.write("_system/graph/graph_sources.json", {
            "falsifier_enforcement": {
                "prospective_enforcement_enabled": True,
                "prospective_since": "2026-08-12",
            }
        })
        component = {"component_id": "ops", "falsifier": "Owner cash collapses",
                     "method": "owner_earnings"}
        current = {"status": "decision_grade", "economic_ownership_map": [component],
                   "evidence": {"blockers": [], "unresolved_count": 0},
                   "falsifier_coverage": {}}
        gated = pipeline.apply_prospective_falsifier_gate(
            "AAA", current, {}, "2026-08-12")
        self.assertEqual(gated["status"], "evidence_blocked")
        self.assertEqual(gated["falsifier_coverage"]["prospective_gate"]
                         ["missing_components"], ["ops"])

        retry = {"status": "decision_grade", "economic_ownership_map": [component],
                 "evidence": {"blockers": [], "unresolved_count": 0},
                 "falsifier_coverage": {}}
        still_gated = pipeline.apply_prospective_falsifier_gate(
            "AAA", retry, gated, "2026-08-13")
        self.assertEqual(still_gated["status"], "evidence_blocked")
        self.assertEqual(still_gated["falsifier_coverage"]["prospective_gate"]
                         ["missing_components"], ["ops"])

        unchanged = {"status": "decision_grade",
                     "economic_ownership_map": [component],
                     "evidence": {"blockers": [], "unresolved_count": 0},
                     "falsifier_coverage": {}}
        allowed = pipeline.apply_prospective_falsifier_gate(
            "AAA", unchanged, {"economic_ownership_map": [component]},
            "2026-08-12")
        self.assertEqual(allowed["status"], "decision_grade")

        schema_enriched = {
            "status": "decision_grade",
            "economic_ownership_map": [{
                **component,
                "output_basis": "present_value_today",
                "evidence_level": "primary_verified",
                "method_provenance": {"output_basis": "present_value_today"},
            }],
            "evidence": {"blockers": [], "unresolved_count": 0},
            "falsifier_coverage": {},
        }
        migrated = pipeline.apply_prospective_falsifier_gate(
            "AAA", schema_enriched, {"economic_ownership_map": [component]},
            "2026-08-12")
        self.assertEqual(migrated["status"], "decision_grade")
        self.assertNotIn("prospective_gate", migrated["falsifier_coverage"])


if __name__ == "__main__":
    unittest.main()
