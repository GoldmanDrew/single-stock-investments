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

    def test_targeted_summary_does_not_overwrite_universe_summary(self):
        path = pipeline.write_summary(
            "2026-07-18", "all", ["MSB"], {"dashboard": {"status": "refreshed"}}, False, explicit=True
        )
        self.assertEqual(path.name, "power_zone_security_run_2026-07-18_msb.json")
        self.assertEqual(path.parent, pipeline.ROOT / "_system/data/runs")
        self.assertFalse((pipeline.ROOT / "_system/data/runs/power_zone_universe_run_2026-07-18.json").exists())


if __name__ == "__main__":
    unittest.main()
