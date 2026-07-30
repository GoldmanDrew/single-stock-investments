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

    def test_extreme_return_requires_independent_validation(self):
        fixture = component_fixture()
        fixture["component_valuation"]["components"][0]["valuation"]["calculation_proof"]["inputs"][0]["values"] = {
            "low": 200, "base": 300, "high": 400,
        }
        contract = compute_valuation(fixture)["universal_valuation_contract"]
        self.assertEqual(contract["status"], "evidence_blocked")
        self.assertTrue(contract["model_checks"]["extreme_return_validated"] is False)
        self.assertTrue(any("independent validation" in row.lower() for row in contract["evidence"]["blockers"]))

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
