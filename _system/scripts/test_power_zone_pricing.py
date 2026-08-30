import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_power_zone_pricing as pricing
from build_power_zone_pricing import (
    build_economic_value_bridge,
    can_seed,
    entry_price_for_hurdle,
    implied_constant_growth,
)
from universal_valuation_contract import entry_price_for_contract_valuation


class PowerZonePricingTests(unittest.TestCase):
    def test_entry_price_declines_as_hurdle_rises(self):
        scenario = {"growth_y1_5": 0.08, "growth_y6_10": 0.04, "exit_pfcf_y10": 15}
        prices = [entry_price_for_hurdle(2.0, scenario, hurdle, 7) for hurdle in (0.10, 0.12, 0.15, 0.20)]
        self.assertEqual(prices, sorted(prices, reverse=True))

    def test_present_value_contract_has_no_hurdle_entry_price(self):
        valuation = {
            "output_basis": "present_value_today",
            "present_value_today_per_share": {"low": 80, "base": 100, "high": 120},
        }
        self.assertIsNone(entry_price_for_contract_valuation(valuation, "base", 0.15))

    def test_blocked_workbench_rewrites_stale_pricing_as_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            research = root / "BLOCKED" / "research"
            research.mkdir(parents=True)
            (research / "valuation.json").write_text("{}", encoding="utf-8")
            (research / "valuation_route.json").write_text(
                json.dumps({"profile_id": "quality_reinvestment"}), encoding="utf-8"
            )
            (research / "valuation_workbench.json").write_text(json.dumps({
                "proof_status": "evidence_blocked",
                "model_level": "evidence_blocked",
                "decision": {
                    "status": "evidence_blocked",
                    "model_level": "evidence_blocked",
                },
            }), encoding="utf-8")
            (research / "valuation_contract.json").write_text(json.dumps({
                "schema_version": "3.0",
                "status": "decision_grade",
                "model_level": "stock_specific",
                "as_of": "2026-08-30",
                "market": {"price_per_share": 100},
                "valuation": {
                    "output_basis": "present_value_today",
                    "value_per_share": {"low": 80, "base": 100, "high": 120},
                    "present_value_today_per_share": {"low": 80, "base": 100, "high": 120},
                    "forward_return_at_price_pct": {"low": None, "base": None, "high": None},
                },
            }), encoding="utf-8")
            old_root = pricing.ROOT
            pricing.ROOT = root
            try:
                result = pricing.build_contract_pricing("BLOCKED", "2026-08-30")
            finally:
                pricing.ROOT = old_root
        self.assertEqual(result["schema_version"], "3.0")
        self.assertEqual(result["proof_status"], "evidence_blocked")
        self.assertEqual(result["entry_price_status"], "unavailable")
        self.assertEqual(result["decision"], "screening_only")
        self.assertTrue(all(
            value is None
            for case in result["entry_prices_by_hurdle_and_case"].values()
            for value in case.values()
        ))

    def test_future_payoff_hurdle_price_discounts_the_dated_payoff_once(self):
        valuation = {
            "output_basis": "future_payoff",
            "future_payoff_per_share": {"low": 80, "base": 100, "high": 120},
            "future_payoff_horizon_years": 2,
        }
        prices = [
            entry_price_for_contract_valuation(valuation, "base", hurdle)
            for hurdle in (0.10, 0.12, 0.15, 0.20)
        ]
        self.assertEqual(prices, sorted(prices, reverse=True))
        self.assertAlmostEqual(prices[2], 100 / (1.15 ** 2), places=4)

    def test_cashflow_schedule_hurdle_price_is_schedule_npv(self):
        valuation = {
            "output_basis": "forward_cashflow_schedule",
            "forward_cashflow_schedule": {
                "base": [
                    {"year": 1, "amount_per_share": 60},
                    {"year": 2, "amount_per_share": 60},
                ]
            },
        }
        entry = entry_price_for_contract_valuation(valuation, "base", 0.10)
        self.assertAlmostEqual(entry, 60 / 1.10 + 60 / (1.10 ** 2), places=4)

    def test_implied_growth_reprices_to_observed_price(self):
        growth = implied_constant_growth(100, 5, 15, 7)
        self.assertIsNotNone(growth)
        self.assertGreater(growth, -25)
        self.assertLess(growth, 100)

    def test_can_seed_requires_complete_model_inputs(self):
        complete = {
            "inputs": {"price": 50, "fcf_per_share": 3},
            "scenarios": {"base": {"growth_y1_5": 0.05, "growth_y6_10": 0.03, "exit_pfcf_y10": 14}},
        }
        self.assertTrue(can_seed(complete))
        self.assertFalse(
            can_seed(
                {
                    "inputs": {"price": 50},
                    "scenarios": {"base": {"growth_y1_5": 0.05, "exit_pfcf_y10": 14}},
                }
            )
        )
        self.assertFalse(
            can_seed(
                {
                    "inputs": {"price": 50, "fcf_per_share": 3},
                    "scenarios": {"base": {"exit_pfcf_y10": 14}},
                }
            )
        )
        self.assertFalse(
            can_seed(
                {
                    "inputs": {"price": 50, "fcf_per_share": -1},
                    "scenarios": {"base": {"growth_y1_5": 0.05, "exit_pfcf_y10": 14}},
                }
            )
        )

    def test_economic_bridge_requires_complete_non_overlapping_coverage(self):
        data = {
            "inputs": {"price": 10},
            "component_valuation_results": {
                "total_equity_value_per_share": {"low": 4, "base": 5, "high": 6},
                "additive_components": [
                    {"id": "asset", "low_per_share": 4, "base_per_share": 5, "high_per_share": 6}
                ],
            },
        }
        config = {"economic_value_bridge": {
            "component_groups": [{"label": "Asset", "component_ids": ["asset"]}],
            "gross_comparable_nav_per_share": {"low": 8, "base": 10, "high": 12},
        }}
        bridge = build_economic_value_bridge(data, config)
        self.assertTrue(bridge["complete_component_coverage"])
        self.assertEqual(bridge["gross_to_risked_discount_pct"]["base"], 50.0)


if __name__ == "__main__":
    unittest.main()
