import json
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_power_zone_pricing as pricing_module
from build_power_zone_pricing import (
    build_contract_pricing,
    build_economic_value_bridge,
    can_seed,
    entry_price_for_hurdle,
    implied_constant_growth,
)


class PowerZonePricingTests(unittest.TestCase):
    def _write_contract(self, root: Path, valuation: dict) -> None:
        research = root / "TEST" / "research"
        research.mkdir(parents=True)
        (research / "valuation.json").write_text(
            json.dumps({"ticker": "TEST", "inputs": {"price_source": "test quote"}}),
            encoding="utf-8",
        )
        (research / "valuation_contract.json").write_text(
            json.dumps({
                "schema_version": "3.0",
                "status": "decision_grade",
                "ticker": "TEST",
                "as_of": "2026-08-28",
                "market": {"price_per_share": 100, "price_as_of": "2026-08-27"},
                "valuation": valuation,
                "monitoring": {"falsifiers": []},
                "method_route": {},
            }),
            encoding="utf-8",
        )

    def test_entry_price_declines_as_hurdle_rises(self):
        scenario = {"growth_y1_5": 0.08, "growth_y6_10": 0.04, "exit_pfcf_y10": 15}
        prices = [entry_price_for_hurdle(2.0, scenario, hurdle, 7) for hurdle in (0.10, 0.12, 0.15, 0.20)]
        self.assertEqual(prices, sorted(prices, reverse=True))

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

    def test_present_value_contract_produces_non_actionable_unavailable_pricing(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self._write_contract(root, {
            "output_basis": "present_value_today",
            "value_per_share": {"low": 90, "base": 121, "high": 150},
            "present_value_today_per_share": {"low": 90, "base": 121, "high": 150},
            "forward_return_at_price_pct": {"low": None, "base": None, "high": None},
            "forward_return_status": "withheld",
            "margin_of_safety_pct": {"low": -11.11, "base": 17.36, "high": 33.33},
        })
        with unittest.mock.patch.object(pricing_module, "ROOT", root):
            result = build_contract_pricing("TEST")
        self.assertEqual(result["status"], "unavailable")
        self.assertFalse(result["actionable"])
        self.assertIsNone(result["primary_entry_price_15pct_base"])
        self.assertTrue(all(
            entry is None
            for case in result["entry_prices_by_hurdle_and_case"].values()
            for entry in case.values()
        ))
        self.assertIn("double-discount", result["unavailable_reason"])

    def test_future_payoff_contract_discounts_the_actual_dated_payoff(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self._write_contract(root, {
            "output_basis": "future_payoff",
            "value_per_share": {"low": 110, "base": 121, "high": 133.1},
            "future_payoff_per_share": {"low": 110, "base": 121, "high": 133.1},
            "future_payoff_horizon_years": 2,
            "forward_return_at_price_pct": {"low": 4.88, "base": 10.0, "high": 15.37},
            "forward_return_status": "available",
        })
        with unittest.mock.patch.object(pricing_module, "ROOT", root):
            result = build_contract_pricing("TEST")
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["entry_prices_by_hurdle_and_case"]["base"]["10pct"], 100.0)
        self.assertEqual(result["primary_entry_price_15pct_base"], 91.49)
        self.assertEqual(result["entry_price_method"], "discounted_dated_future_payoff")

    def test_cashflow_contract_uses_npv_of_the_schedule(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        schedules = {
            case: [
                {"year_fraction": 1, "amount_per_share": first},
                {"year_fraction": 2, "amount_per_share": terminal},
            ]
            for case, first, terminal in (
                ("low", 4, 100), ("base", 5, 110), ("high", 6, 120)
            )
        }
        self._write_contract(root, {
            "output_basis": "forward_cashflow_schedule",
            "value_per_share": {"low": 90, "base": 100, "high": 110},
            "forward_cashflow_schedule": schedules,
            "forward_return_at_price_pct": {"low": -2, "base": 7, "high": 15},
            "forward_return_status": "available",
        })
        with unittest.mock.patch.object(pricing_module, "ROOT", root):
            result = build_contract_pricing("TEST")
        expected = round(5 / 1.10 + 110 / (1.10 ** 2), 2)
        self.assertEqual(result["entry_prices_by_hurdle_and_case"]["base"]["10pct"], expected)
        self.assertEqual(result["entry_price_method"], "npv_of_forward_cashflow_schedule")


if __name__ == "__main__":
    unittest.main()
