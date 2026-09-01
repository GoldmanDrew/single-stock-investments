import copy
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from committee_calibration import summarize
from marvin_valuation import compute_valuation
from specialized_valuation_methods import calculate
from universal_valuation_contract import strict_contract_errors
from valuation_method_registry import registry
from valuation_method_router import route_valuation


def component_fixture(explicit=True):
    data = {
        "ticker": "TEST", "as_of": "2026-07-15", "method": "pending",
        "inputs": {"price": 50, "shares_outstanding": 100_000_000},
        "classification_inputs": {"archetype": "resource"},
    }
    if explicit:
        data["component_valuation"] = {
            "all_material_components_identified": True,
            "components": [{
                "id": "asset", "label": "Asset", "category": "operating_business", "overlap_key": "asset", "treatment": "additive",
                "valuation": {
                    "method": "owner_earnings_reinvestment_dcf", "evidence_tier": "primary", "evidence": "filing", "low": 40, "base": 60, "high": 90,
                    "valuation_status": "calculated",
                    "calculation_proof": {
                        "schema_version": "1.0", "method_id": "owner_earnings_reinvestment_dcf", "method_version": "1.0", "output_unit": "USD_per_share",
                        "inputs": [{"id": "value", "kind": "fact", "values": {"low": 40, "base": 60, "high": 90}, "unit": "USD_per_share", "locked": True, "source": {"ref": "filing", "locator": "valuation schedule", "as_of": "2026-07-15"}}],
                        "assumptions": [], "calculations": [], "outputs": {"low": "value", "base": "value", "high": "value"}
                    },
                },
            }],
        }
        data["economic_value"] = {
            "schema_version": "1.0", "gaap_role": "cross_check",
            "economic_claim": {"description": "One share", "unit_label": "share", "unit_count": 100_000_000, "unit_source": "filing", "enterprise_to_equity_reconciliation": "All claims included once."},
            "component_groups": [{"id": "asset", "label": "Asset", "component_ids": ["asset"], "economic_claim": "Shareholder claim", "valuation_basis": "owner cash", "adjustments": "risked cases", "overlap_control": "unique"}],
        }
    return data


class GeneralizedValuationSystemTests(unittest.TestCase):
    def test_router_covers_all_seven_power_zones(self):
        cases = {
            "resource": "scarce_asset_optionality", "compounder": "quality_reinvestment", "commodity_cyclical": "capital_cycle",
            "bank": "credit_and_normalized_returns", "special_situation": "catalyst_asset_value",
            "regulated_utility": "predictable_cash_flow", "biotech": "binary_milestone",
        }
        for archetype, expected in cases.items():
            with self.subTest(archetype=archetype):
                result = route_valuation({"classification_inputs": {"archetype": archetype}})
                self.assertEqual(result["profile_id"], expected)
                self.assertLessEqual(len(result["corroborating_methods"]), 2)
                self.assertTrue(result["silent_personas"])

    def test_universal_contract_has_zero_unvalued_components_only_when_explicit(self):
        complete = compute_valuation(component_fixture())
        contract = complete["universal_valuation_contract"]
        self.assertEqual(contract["component_coverage"]["unvalued_component_count"], 0)
        self.assertEqual(contract["status"], "decision_grade")
        self.assertEqual(strict_contract_errors(complete), [])
        incomplete = compute_valuation({**component_fixture(False), "method": "pending"})
        self.assertEqual(incomplete["universal_valuation_contract"]["status"], "evidence_blocked")
        self.assertIn("unvalued_component_count must equal zero", strict_contract_errors(incomplete))

    def test_embedded_sensitivity_does_not_block_additive_proof_completeness(self):
        fixture = component_fixture()
        fixture["component_valuation"]["components"].append({
            "id": "embedded_option",
            "label": "Embedded option sensitivity",
            "category": "optionality",
            "overlap_key": "embedded_option",
            "treatment": "embedded",
            "included_in_component_id": "asset",
            "valuation": {
                "method": "legacy_sensitivity",
                "evidence_tier": "primary_derived",
                "evidence": "Included in the additive asset value.",
                "low": 0,
                "base": 0,
                "high": 2,
            },
        })
        contract = compute_valuation(fixture)["universal_valuation_contract"]
        self.assertEqual(contract["component_coverage"]["unvalued_component_count"], 0)
        self.assertTrue(contract["calculation_proof_summary"]["all_material_components_priced"])
        self.assertEqual(contract["status"], "decision_grade")

    def test_universal_contract_blocks_decision_grade_without_market_price(self):
        fixture = component_fixture()
        fixture["inputs"]["price"] = None
        contract = compute_valuation(fixture)["universal_valuation_contract"]
        self.assertEqual(contract["status"], "evidence_blocked")
        self.assertTrue(
            any("Market price per share is missing" in row for row in contract["evidence"]["blockers"])
        )

    def test_primary_derived_inputs_are_not_labeled_primary_verified(self):
        fixture = component_fixture()
        fixture["component_valuation"]["components"][0]["valuation"]["evidence_tier"] = "primary_derived"
        contract = compute_valuation(fixture)["universal_valuation_contract"]
        self.assertEqual(contract["economic_ownership_map"][0]["evidence_level"], "primary_derived")

    def test_cross_ticker_source_cannot_be_decision_grade(self):
        fixture = component_fixture()
        proof = fixture["component_valuation"]["components"][0]["valuation"]["calculation_proof"]
        proof["inputs"][0]["source"]["ref"] = "OTHER/research/evidence/10-K.htm"
        contract = compute_valuation(fixture)["universal_valuation_contract"]
        self.assertEqual(contract["status"], "evidence_blocked")
        self.assertTrue(any("belongs to OTHER" in row for row in contract["evidence"]["blockers"]))

    def test_human_review_source_cannot_be_decision_grade(self):
        fixture = component_fixture()
        proof = fixture["component_valuation"]["components"][0]["valuation"]["calculation_proof"]
        proof["inputs"][0]["source"]["locator"] = "Provisional share count [HUMAN REVIEW]"
        contract = compute_valuation(fixture)["universal_valuation_contract"]
        self.assertEqual(contract["status"], "evidence_blocked")
        self.assertTrue(any("human review" in row.lower() for row in contract["evidence"]["blockers"]))

    def test_stale_owner_earnings_fact_cannot_be_decision_grade(self):
        fixture = component_fixture()
        fixture["as_of"] = "2026-07-30"
        proof = fixture["component_valuation"]["components"][0]["valuation"]["calculation_proof"]
        proof["inputs"][0]["id"] = "owner_earnings"
        proof["inputs"][0]["source"]["as_of"] = "2010-12-31"
        contract = compute_valuation(fixture)["universal_valuation_contract"]
        self.assertEqual(contract["status"], "evidence_blocked")
        self.assertTrue(any("stale" in row.lower() for row in contract["evidence"]["blockers"]))

    def test_present_value_today_never_produces_a_forward_return(self):
        fixture = component_fixture()
        fixture["component_valuation"]["components"][0]["valuation"]["calculation_proof"]["inputs"][0]["values"] = {
            "low": 200, "base": 300, "high": 400,
        }
        contract = compute_valuation(fixture)["universal_valuation_contract"]
        valuation = contract["valuation"]
        self.assertEqual(contract["status"], "decision_grade")
        self.assertEqual(valuation["output_basis"], "present_value_today")
        self.assertEqual(valuation["present_value_today_per_share"], {"low": 200.0, "base": 300.0, "high": 400.0})
        self.assertEqual(valuation["forward_return_at_price_pct"], {"low": None, "base": None, "high": None})
        self.assertEqual(valuation["annualized_return_at_price_pct"], {"low": None, "base": None, "high": None})
        self.assertEqual(valuation["forward_return_status"], "withheld")
        self.assertTrue(contract["model_checks"]["present_value_is_not_treated_as_future_payoff"])
        self.assertTrue(contract["model_checks"]["extreme_return_validated"])
        self.assertIsNotNone(contract["legacy_audit"]["annualized_return_at_price_pct"]["base"])

    def test_dated_future_payoff_computes_present_value_and_forward_return(self):
        fixture = component_fixture()
        proof = fixture["component_valuation"]["components"][0]["valuation"]["calculation_proof"]
        proof["method_id"] = "dated_future_payoff_per_share"
        proof["output_basis"] = "future_payoff"
        fixture["component_valuation"]["components"][0]["valuation"]["method"] = "dated_future_payoff_per_share"
        proof["inputs"][0]["values"] = {"low": 55, "base": 60.5, "high": 66.55}
        fixture["component_valuation"]["components"][0]["valuation"].update(
            {"low": 55, "base": 60.5, "high": 66.55}
        )
        fixture["valuation_methodology"] = {
            "output_basis": {"type": "future_payoff", "horizon_years": 2},
            "required_return_pct": 10,
        }
        contract = compute_valuation(fixture)["universal_valuation_contract"]
        valuation = contract["valuation"]
        self.assertEqual(contract["status"], "decision_grade")
        self.assertEqual(valuation["future_payoff_per_share"], {"low": 55.0, "base": 60.5, "high": 66.55})
        self.assertAlmostEqual(valuation["present_value_today_per_share"]["base"], 50.0, places=4)
        self.assertAlmostEqual(valuation["forward_return_at_price_pct"]["base"], 10.0, places=2)
        self.assertEqual(valuation["forward_return_status"], "available")
        self.assertEqual(valuation["required_return_pct"], 10.0)

    def test_approved_present_value_method_cannot_be_relabelled_as_future_payoff(self):
        fixture = component_fixture()
        proof = fixture["component_valuation"]["components"][0]["valuation"]["calculation_proof"]
        proof["output_basis"] = "future_payoff"
        fixture["valuation_methodology"] = {
            "output_basis": {"type": "future_payoff", "horizon_years": 2},
            "required_return_pct": 10,
        }
        contract = compute_valuation(fixture)["universal_valuation_contract"]
        self.assertEqual(contract["status"], "evidence_blocked")
        self.assertFalse(contract["model_checks"]["output_basis_valid"])
        self.assertTrue(any(
            "conflicts with approved method-card basis" in row
            for row in contract["evidence"]["blockers"]
        ))

    def test_dated_cashflow_schedule_uses_npv_and_true_irr(self):
        fixture = component_fixture()
        fixture["inputs"]["price"] = 100
        proof = fixture["component_valuation"]["components"][0]["valuation"]["calculation_proof"]
        proof["method_id"] = "dated_forward_cashflow_schedule_per_share"
        proof["output_basis"] = "forward_cashflow_schedule"
        fixture["component_valuation"]["components"][0]["valuation"]["method"] = "dated_forward_cashflow_schedule_per_share"
        proof["inputs"][0]["values"] = {"low": 100, "base": 120, "high": 140}
        fixture["component_valuation"]["components"][0]["valuation"].update(
            {"low": 100, "base": 120, "high": 140}
        )
        fixture["valuation_methodology"] = {
            "output_basis": {
                "type": "forward_cashflow_schedule",
                "cashflows": {
                    "low": [
                        {"year": 1, "amount_per_share": 50},
                        {"year": 2, "amount_per_share": 50},
                    ],
                    "base": [
                        {"year": 1, "amount_per_share": 60},
                        {"year": 2, "amount_per_share": 60},
                    ],
                    "high": [
                        {"year": 1, "amount_per_share": 70},
                        {"year": 2, "amount_per_share": 70},
                    ],
                },
            },
            "required_return_pct": 10,
        }
        contract = compute_valuation(fixture)["universal_valuation_contract"]
        valuation = contract["valuation"]
        self.assertEqual(contract["status"], "decision_grade")
        self.assertAlmostEqual(valuation["present_value_today_per_share"]["base"], 104.1322, places=4)
        self.assertAlmostEqual(valuation["forward_return_at_price_pct"]["base"], 13.07, places=2)
        self.assertNotEqual(
            valuation["forward_return_at_price_pct"]["base"],
            contract["legacy_audit"]["annualized_return_at_price_pct"]["base"],
        )

    def test_true_extreme_forward_return_requires_independent_validation(self):
        fixture = component_fixture()
        proof = fixture["component_valuation"]["components"][0]["valuation"]["calculation_proof"]
        proof["method_id"] = "dated_future_payoff_per_share"
        proof["output_basis"] = "future_payoff"
        fixture["component_valuation"]["components"][0]["valuation"]["method"] = "dated_future_payoff_per_share"
        proof["inputs"][0]["values"] = {"low": 100, "base": 150, "high": 200}
        fixture["component_valuation"]["components"][0]["valuation"].update(
            {"low": 100, "base": 150, "high": 200}
        )
        fixture["valuation_methodology"] = {
            "output_basis": {"type": "future_payoff", "horizon_years": 1},
            "required_return_pct": 10,
        }
        contract = compute_valuation(fixture)["universal_valuation_contract"]
        self.assertEqual(contract["valuation"]["forward_return_at_price_pct"]["base"], 200.0)
        self.assertEqual(contract["status"], "evidence_blocked")
        self.assertFalse(contract["model_checks"]["extreme_return_validated"])
        self.assertTrue(any("independent validation" in row.lower() for row in contract["evidence"]["blockers"]))

        fixture["valuation_methodology"]["outlier_validation"] = {
            "status": "passed",
            "independent_methods": ["reverse_expectations"],
            "evidence_refs": ["TEST/research/evidence/independent-payoff-check.md"],
        }
        validated = compute_valuation(fixture)["universal_valuation_contract"]
        self.assertEqual(validated["status"], "decision_grade")
        self.assertTrue(validated["model_checks"]["extreme_return_validated"])

    def test_all_approved_method_cards_declare_an_output_basis(self):
        approved = list(registry().values())
        self.assertTrue(approved)
        self.assertTrue(all(row.get("output_basis") for row in approved))
        self.assertTrue(
            all(
                row["output_basis"]
                in {"present_value_today", "future_payoff", "forward_cashflow_schedule"}
                for row in approved
            )
        )

    def test_specialized_calculators_are_ordered_and_auditable(self):
        specs = {
            "scarce_asset_optionality": {"units": 100, "scenarios": {case: {"value_per_unit": value, "realization_probability": .8, "discount_rate": .1, "years_to_realization": 2} for case, value in zip(("low", "base", "high"), (5, 10, 20))}},
            "quality_reinvestment": {"owner_earnings": 5, "scenarios": {case: {"years": 5, "reinvestment_rate": .3, "incremental_after_tax_roic": roic, "discount_rate": .1, "terminal_owner_earnings_multiple": multiple} for case, roic, multiple in (("low", .05, 10), ("base", .15, 15), ("high", .25, 20))}},
            "capital_cycle": {"capacity_units": 100, "shares": 10, "scenarios": {case: {"utilization": util, "revenue_per_unit": 10, "normalized_margin": margin, "maintenance_capital": 10, "tax_rate": .2, "owner_cash_multiple": 8, "net_debt": 5} for case, util, margin in (("low", .5, .1), ("base", .7, .2), ("high", .9, .3))}},
            "credit_and_normalized_returns": {"tangible_equity": 1000, "shares": 100, "scenarios": {case: {"normalized_roe": roe, "cost_of_equity": .1, "excess_return_duration_years": years, "stress_losses": loss} for case, roe, years, loss in (("low", .08, 2, 100), ("base", .12, 5, 50), ("high", .16, 8, 10))}},
            "catalyst_asset_value": {"scenarios": {case: [{"probability": p, "payoff": payoff, "years": 1, "discount_rate": .1}, {"probability": 1-p, "payoff": 5}] for case, p, payoff in (("low", .2, 20), ("base", .6, 30), ("high", .9, 40))}},
            "predictable_cash_flow": {"distribution_per_share": 2, "scenarios": {case: {"growth": growth, "required_return": required} for case, growth, required in (("low", 0, .12), ("base", .03, .1), ("high", .05, .09))}},
            "binary_milestone": {"scenarios": {case: {"net_cash": 20, "shares": 10, "assets": [{"success_probability": p, "success_value": value, "remaining_cost": 2}]} for case, p, value in (("low", .1, 10), ("base", .4, 30), ("high", .8, 50))}},
        }
        for profile, spec in specs.items():
            with self.subTest(profile=profile):
                result = calculate(profile, copy.deepcopy(spec))
                self.assertLessEqual(result["low"], result["base"])
                self.assertLessEqual(result["base"], result["high"])

    def test_catalyst_event_tree_must_be_exhaustive(self):
        spec = {"scenarios": {case: [{"probability": .8, "payoff": 10}] for case in ("low", "base", "high")}}
        with self.assertRaisesRegex(ValueError, "sum to 1"):
            calculate("catalyst_asset_value", spec)

    def test_calibration_is_segmented_by_persona_and_power_zone(self):
        row = {"return_status": "complete", "total_return_pct": 12, "power_zone": "capital_cycle", "votes": [{"persona": "marks_credit_cycle", "vote": "approve", "expected_return_range_pct": [8, 15]}]}
        result = summarize([row])
        self.assertIn("marks_credit_cycle:capital_cycle", result["persona_power_zones"])
        self.assertEqual(result["persona_power_zones"]["marks_credit_cycle:capital_cycle"]["calibration_use"], "descriptive")


if __name__ == "__main__":
    unittest.main()
