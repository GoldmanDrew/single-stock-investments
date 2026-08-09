import importlib.util
import copy
import hashlib
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("automation", SCRIPTS / "automate_valuation_readiness.py")
automation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(automation)

from calculation_proof import evaluate_calculation_proof
from universal_valuation_contract import build_universal_valuation_contract, strict_contract_errors


def fact(field_id, value, unit):
    return {"field_id": field_id, "value": value, "unit": unit, "locked": True,
            "source": {"ref": "_system/reference/valuation_method_registry.json", "locator": field_id, "as_of": "2026-07-19"}}


class ValuationAutomationTests(unittest.TestCase):
    def test_etf_identity_never_routes_to_operating_company_default(self):
        identity = automation.resolve_identity("FUND", {"company": "Example Index ETF", "market": "US"}, {}, "2026-07-19")
        self.assertEqual(identity["security_type"], "exchange_traded_fund")
        self.assertEqual(identity["primary_method"], "net_asset_value")

    def test_power_zone_route_is_method_authority(self):
        route = {
            "status": "routed",
            "score": 6,
            "profile_id": "capital_cycle",
            "primary_methods": ["midcycle_capacity_value"],
            "input_hash": "abc",
        }
        identity = automation.resolve_identity(
            "CYCLE",
            {"company": "Example Steel", "market": "US"},
            {},
            "2026-07-19",
            route,
        )
        self.assertEqual(identity["primary_method"], "midcycle_capacity_value")
        self.assertEqual(identity["valuation_profile"], "capital_cycle")
        self.assertEqual(identity["method_source"], "power_zone_route")

    def test_default_route_creates_classification_recovery_task(self):
        route = {
            "status": "default_needs_review",
            "score": 0,
            "profile_id": "quality_reinvestment",
            "primary_methods": ["owner_earnings_reinvestment_dcf"],
        }
        identity = automation.resolve_identity(
            "UNKNOWN",
            {"company": "Unknown Company", "market": "US"},
            {},
            "2026-07-19",
            route,
        )
        plan = automation.evidence_plan("UNKNOWN", identity, {"facts": []}, "2026-07-19")
        task_ids = {row["id"] for row in plan["tasks"]}
        self.assertIn("valuation_route_classification_required", task_ids)

    def test_every_approved_method_has_typed_input_requirements(self):
        expected = {
            "royalty_distribution_curve",
            "net_asset_value",
            "owner_earnings_reinvestment_dcf",
            "midcycle_capacity_value",
            "capital_structure_and_excess_return",
            "probability_weighted_catalyst_nav",
            "risk_adjusted_milestone_value",
            "owner_cash_or_dividend_discount",
        }
        self.assertTrue(expected.issubset(automation.FIELD_REQUIREMENTS))
        self.assertTrue(all(automation.FIELD_REQUIREMENTS[method] for method in expected))
        self.assertTrue(expected.issubset(automation.METHOD_INPUT_SCHEMAS))
        self.assertTrue(expected.issubset(automation.METHOD_COMPILERS))

    def test_dispatcher_compiles_every_power_zone_method(self):
        fixtures = {
            "royalty_distribution_curve": {
                "contractual_royalty_tiers": .05, "production_by_period": 100,
                "realized_pricing_or_contractual_index": .2, "bonus_thresholds": 1,
                "trust_expenses_and_taxes": .5, "reserve_life": 5,
                "units_outstanding": 10, "discount_rate": .1,
            },
            "net_asset_value": {
                "asset_quantity": 10, "unit_value": 20, "ownership_claim": .8,
                "senior_claims": 15, "tax_and_realization_costs": 5,
                "shares_outstanding": 10_000_000,
            },
            "midcycle_capacity_value": {
                "capacity": 100, "utilization": .75, "revenue_per_unit": 2,
                "normalized_margin": .2, "maintenance_capital_m": 5, "tax_rate": .2,
                "debt_m": 20, "shares_outstanding": 10_000_000,
            },
            "capital_structure_and_excess_return": {
                "tangible_equity_m": 100, "normalized_roe": .14, "cost_of_equity": .1,
                "excess_return_duration": 5, "stress_losses_m": 10, "senior_claims_m": 0,
                "shares_outstanding": 10_000_000,
            },
            "probability_weighted_catalyst_nav": {
                "event_tree": 3, "outcome_probabilities": .6, "outcome_payoffs": 100,
                "remaining_costs": 10, "outcome_timing": 1, "discount_rates": .1,
                "shares_outstanding": 10_000_000,
            },
            "risk_adjusted_milestone_value": {
                "asset_milestones": 2, "base_rate_success_probabilities": .4,
                "success_values": 200, "milestone_timing": 2, "remaining_costs": 20,
                "cash_runway": 25, "dilution": 5, "shares_outstanding": 10_000_000,
            },
            "owner_cash_or_dividend_discount": {
                "sustainable_distribution": 10, "sustainable_growth": .02,
                "required_return": .1, "maintenance_funding": 2,
                "dilution_per_share": .2, "shares_outstanding": 10_000_000,
            },
            "component_owner_cash_and_unit_nav": {
                "economic_ownership_map": {"owner_cash_component": 1, "unit_nav_component": 1},
                "normalized_owner_cash": 10, "asset_quantity": 5, "unit_value": 20,
                "senior_claims": 10, "tax_and_realization_costs": 5,
                "shares_outstanding": 10_000_000,
            },
        }
        approved = {
            "royalty_distribution_curve", "net_asset_value", "owner_earnings_reinvestment_dcf",
            "midcycle_capacity_value", "capital_structure_and_excess_return",
            "probability_weighted_catalyst_nav", "risk_adjusted_milestone_value",
            "owner_cash_or_dividend_discount",
        }
        for method_id, values in fixtures.items():
            with self.subTest(method_id=method_id):
                rows = [
                    fact(field_id, value, automation.METHOD_INPUT_SCHEMAS[method_id][field_id].get("unit", "value"))
                    for field_id, value in values.items()
                ]
                identity = {
                    "primary_method": method_id, "archetype": "test",
                    "valuation_profile": "test", "method_source": "power_zone_route",
                }
                valuation = automation.compile_valuation("TEST", "2026-07-19", identity, {"facts": rows})
                self.assertIsNotNone(valuation)
                components = valuation["component_valuation_results"]["additive_components"]
                self.assertGreaterEqual(len(components), 1)
                for component in components:
                    self.assertIn(component["method"], approved)
                    evaluated = evaluate_calculation_proof(component["calculation_proof"])
                    self.assertEqual(evaluated["status"], "valid", evaluated["checks"]["errors"])

    def test_evidence_ready_requires_matching_locked_field(self):
        identity = {"primary_method": "owner_earnings_reinvestment_dcf"}
        ledger = {"facts": [fact("cash_m", 20, "USD millions")]}
        plan = automation.evidence_plan("TEST", identity, ledger, "2026-07-19")
        statuses = {row["field_id"]: row["status"] for row in plan["tasks"]}
        self.assertEqual(statuses["cash_m"], "evidence_ready")
        self.assertEqual(statuses["debt_m"], "pending_collection")

    def test_compiler_emits_valid_monotonic_proof(self):
        identity = {"primary_method": "owner_earnings_reinvestment_dcf", "archetype": "compounder"}
        ledger = {"facts": [
            fact("normalized_owner_earnings_m", 100, "USD millions"),
            fact("shares_outstanding", 10_000_000, "shares"),
            fact("cash_m", 20, "USD millions"), fact("debt_m", 5, "USD millions"),
        ]}
        valuation = automation.compile_owner_earnings("TEST", "2026-07-19", identity, ledger)
        proof = valuation["component_valuation_results"]["additive_components"][0]["calculation_proof"]
        result = evaluate_calculation_proof(proof)
        self.assertEqual(result["status"], "valid", result["checks"]["errors"])
        self.assertLessEqual(result["outputs"]["low"], result["outputs"]["base"])
        self.assertLessEqual(result["outputs"]["base"], result["outputs"]["high"])
        # Market price is required for decision_grade (live mark from fetch_equity_prices).
        valuation.setdefault("inputs", {})["price"] = 100.0
        contract = build_universal_valuation_contract(valuation, "quality_reinvestment")
        self.assertEqual(contract["status"], "decision_grade", contract.get("evidence", {}).get("blockers"))
        self.assertEqual(strict_contract_errors(valuation), [])

    def test_owner_earnings_growth_is_charged_its_reinvestment_cost(self):
        """Regression: c72fe6094e6 dropped the retention haircut, so the full
        owner-earnings figure was discounted as distributable cash while growth
        was still driven by the reinvestment rate. That is the method card's
        "growth without capital cost" failure mode and it inflated every
        automation-compiled valuation."""
        identity = {"primary_method": "owner_earnings_reinvestment_dcf", "archetype": "compounder"}
        ledger = {"facts": [
            fact("normalized_owner_earnings_m", 100, "USD millions"),
            fact("shares_outstanding", 10_000_000, "shares"),
            fact("cash_m", 20, "USD millions"), fact("debt_m", 5, "USD millions"),
        ]}
        valuation = automation.compile_owner_earnings("TEST", "2026-07-19", identity, ledger)
        proof = valuation["component_valuation_results"]["additive_components"][0]["calculation_proof"]
        nodes = {node["id"]: node for node in proof["calculations"]}

        # Distributable cash must be owner earnings net of the reinvestment
        # that buys the growth, never the full owner-earnings figure.
        self.assertEqual(nodes["distribution_rate"]["op"], "subtract")
        self.assertEqual(nodes["distribution_rate"]["args"], [1, "reinvestment"])
        for year in range(1, 8):
            cash = nodes[f"owner_cash_y{year}"]
            self.assertEqual(cash["args"], [f"owner_earnings_y{year}", "distribution_rate"],
                             f"owner_cash_y{year} must charge growth its capital cost")

        # And it has to bite numerically: re-evaluating the same proof with the
        # haircut removed is exactly the pre-fix graph, which must value higher.
        inflated = copy.deepcopy(proof)
        for node in inflated["calculations"]:
            if node["id"].startswith("owner_cash_y"):
                node["args"] = [node["args"][0], 1]
        corrected = evaluate_calculation_proof(proof)
        uncorrected = evaluate_calculation_proof(inflated)
        self.assertEqual(corrected["status"], "valid", corrected["checks"]["errors"])
        for case in ("low", "base", "high"):
            self.assertLess(corrected["outputs"][case], uncorrected["outputs"][case],
                            f"{case} case must fall once reinvestment is charged")

    def test_negative_owner_earnings_cannot_clear_model_gate(self):
        identity = {"primary_method": "owner_earnings_reinvestment_dcf"}
        ledger = {"facts": [
            fact("normalized_owner_earnings_m", -10, "USD millions"),
            fact("shares_outstanding", 10_000_000, "shares"),
            fact("cash_m", 20, "USD millions"), fact("debt_m", 5, "USD millions"),
        ]}
        plan = automation.evidence_plan("TEST", identity, ledger, "2026-07-19")
        statuses = {row["field_id"]: row["status"] for row in plan["tasks"]}
        self.assertEqual(statuses["normalized_owner_earnings_m"], "pending_collection")
        self.assertEqual(statuses["component_model"], "pending_collection")

    def test_share_selector_rejects_stale_dei_class_artifact(self):
        companyfacts = {
            "facts": {
                "dei": {
                    "EntityCommonStockSharesOutstanding": {
                        "units": {"shares": [{
                            "val": 1,
                            "end": "2019-03-18",
                            "filed": "2019-03-25",
                            "form": "10-Q",
                        }]}
                    }
                },
                "us-gaap": {
                    "WeightedAverageNumberOfDilutedSharesOutstanding": {
                        "units": {"shares": [{
                            "val": 443_000_000,
                            "end": "2026-03-31",
                            "filed": "2026-05-11",
                            "form": "10-Q",
                        }]}
                    }
                },
            }
        }
        tag, row = automation._select_share_companyfact(companyfacts)
        self.assertEqual(tag, "WeightedAverageNumberOfDilutedSharesOutstanding")
        self.assertEqual(row["val"], 443_000_000)

    def test_share_selector_rejects_current_dei_count_that_does_not_reconcile(self):
        companyfacts = {
            "facts": {
                "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [{
                    "val": 1, "end": "2026-04-30", "filed": "2026-05-11", "form": "10-Q",
                }]}}},
                "us-gaap": {"WeightedAverageNumberOfDilutedSharesOutstanding": {"units": {"shares": [{
                    "val": 443_000_000, "end": "2026-03-31", "filed": "2026-05-11", "form": "10-Q",
                }]}}},
            }
        }
        tag, row = automation._select_share_companyfact(companyfacts)
        self.assertEqual(tag, "WeightedAverageNumberOfDilutedSharesOutstanding")
        self.assertEqual(row["val"], 443_000_000)

    def test_share_selector_keeps_current_dei_when_weighted_fact_is_stale(self):
        companyfacts = {
            "facts": {
                "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [{
                    "val": 1_675_000_000, "end": "2025-12-31", "filed": "2026-02-27", "form": "40-F",
                }]}}},
                "us-gaap": {"WeightedAverageNumberOfDilutedSharesOutstanding": {"units": {"shares": [{
                    "val": 950_000_000, "end": "2010-12-31", "filed": "2011-03-31", "form": "40-F",
                }]}}},
            }
        }
        tag, row = automation._select_share_companyfact(companyfacts)
        self.assertEqual(tag, "EntityCommonStockSharesOutstanding")
        self.assertEqual(row["val"], 1_675_000_000)

    def test_ifrs_filer_resolves_shares_without_a_dei_tag(self):
        """Regression: an IFRS foreign private issuer has no
        dei:EntityCommonStockSharesOutstanding, so NVO sat evidence_blocked on
        shares_outstanding with a perfectly good ifrs-full count in the same
        companyfacts payload."""
        companyfacts = {
            "facts": {
                "ifrs-full": {
                    "NumberOfSharesOutstanding": {"units": {"shares": [
                        {"val": 4_441_000_000, "end": "2024-12-31",
                         "filed": "2025-02-05", "form": "20-F"},
                        {"val": 4_444_000_000, "end": "2025-12-31",
                         "filed": "2026-02-04", "form": "20-F"},
                    ]}},
                    "AdjustedWeightedAverageShares": {"units": {"shares": [
                        {"val": 4_447_700_000, "end": "2025-12-31",
                         "filed": "2026-02-04", "form": "20-F"},
                    ]}},
                }
            }
        }
        tag, row = automation._select_share_companyfact(companyfacts)
        self.assertEqual(tag, "NumberOfSharesOutstanding")
        self.assertEqual(row["namespace"], "ifrs-full")
        self.assertEqual(row["val"], 4_444_000_000)

    def test_ifrs_weighted_shares_still_screen_a_stale_point_in_time_count(self):
        """The IFRS fallback must not disable the divergence guard: a
        class-member artifact is rejected in favour of the weighted count."""
        companyfacts = {
            "facts": {
                "ifrs-full": {
                    "NumberOfSharesOutstanding": {"units": {"shares": [{
                        "val": 1_074_872_000, "end": "2025-12-31",
                        "filed": "2026-02-04", "form": "20-F"}]}},
                    "WeightedAverageShares": {"units": {"shares": [{
                        "val": 4_443_000_000, "end": "2025-12-31",
                        "filed": "2026-02-04", "form": "20-F"}]}},
                }
            }
        }
        tag, row = automation._select_share_companyfact(companyfacts)
        self.assertEqual(tag, "WeightedAverageShares")
        self.assertEqual(row["val"], 4_443_000_000)

    def test_cover_page_shares_sum_every_class_when_the_taxonomy_is_silent(self):
        """Last-resort fallback for a filer whose companyfacts carry no share
        concept at all: the 20-F cover item enumerates the classes."""
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        docs = root / "FPI" / "investor-documents" / "sec-edgar"
        docs.mkdir(parents=True)
        filing = docs / "20-F_20260204_rpt20251231_acc0000353278_26_000012.htm"
        filing.write_text(
            "<p>Securities registered pursuant to Section 12(b) of the Act:</p>\n"
            "<p>Indicate the number of outstanding shares of each of the issuer's "
            "classes of capital or common stock as of the close of the period "
            "covered by the Annual Report:</p>\n"
            "<p>A shares, nominal value DKK 0.10 each: 1,074,872,000</p>\n"
            "<p>B shares, nominal value DKK 0.10 each: 3,390,128,000</p>\n"
            "<p>Indicate by check mark if the registrant is a well-known seasoned "
            "issuer. 999,999,999</p>\n",
            encoding="utf-8")
        with unittest.mock.patch.object(automation, "ROOT", root):
            row = automation._cover_page_share_count("FPI")
        self.assertIsNotNone(row)
        # Both classes, and nothing from beyond the cover item's terminator.
        self.assertEqual(row["value"], 4_465_000_000.0)
        self.assertEqual(row["unit"], "shares")
        self.assertTrue(row["locked"])
        self.assertEqual(row["source"]["as_of"], "2025-12-31")
        self.assertIn("cover page", row["source"]["locator"])
        self.assertIn("1,074,872,000", row["source"]["locator"])
        self.assertEqual(row["source"]["ref"], str(filing.relative_to(root)).replace("\\", "/"))
        self.assertEqual(row["source"]["content_sha256"],
                         hashlib.sha256(filing.read_bytes()).hexdigest())

    def test_cover_page_shares_return_nothing_rather_than_guess(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        docs = root / "FPI" / "investor-documents" / "sec-edgar"
        docs.mkdir(parents=True)
        (docs / "20-F_20260204_rpt20251231_acc0000353278_26_000012.htm").write_text(
            "<p>Indicate the number of outstanding shares of each of the issuer's "
            "classes:</p><p>Not applicable.</p><p>Indicate by check mark</p>",
            encoding="utf-8")
        with unittest.mock.patch.object(automation, "ROOT", root):
            self.assertIsNone(automation._cover_page_share_count("FPI"))

    def test_non_usd_companyfact_refuses_to_lock_without_fx_evidence(self):
        """Regression: NVO (IFRS, DKK filer) locked DKK companyfacts values as
        "USD millions", a ~6.4x overstatement waiting for a shares fact. A
        non-USD source unit must either convert through an evidenced FX row or
        refuse to lock."""
        self.assertIsNone(automation._usd_conversion(
            "NVO", "cash_m", "DKK", "2025-12-31", {}))
        # A recognized rate that is too stale to cover the fact must also refuse.
        stale = {"rates": {"DKK": [{
            "rate_per_usd": 6.3565, "as_of": "2024-12-31", "source": "ECB reference rate",
        }]}}
        self.assertIsNone(automation._usd_conversion(
            "NVO", "cash_m", "DKK", "2025-12-31", stale))
        # A non-monetary unit key can never silently pass as USD.
        self.assertIsNone(automation._usd_conversion(
            "NVO", "cash_m", "shares", "2025-12-31", {}))

    def test_non_usd_companyfact_converts_through_evidenced_fx_row(self):
        payload = {"rates": {"DKK": [
            {"rate_per_usd": 7.0, "as_of": "2025-06-30", "source": "ECB reference rate"},
            {"rate_per_usd": 6.3565, "as_of": "2025-12-31", "source": "ECB reference rate"},
        ]}}
        divisor, fx = automation._usd_conversion(
            "NVO", "operating_cash_flow_m", "DKK", "2025-12-31", payload)
        self.assertEqual(divisor, 6.3565)
        self.assertEqual(fx["from_currency"], "DKK")
        self.assertEqual(fx["to_currency"], "USD")
        self.assertEqual(fx["rate_as_of"], "2025-12-31")
        self.assertTrue(fx["rate_source"])
        self.assertTrue(fx["evidence_ref"].endswith("fx_rates.json"))
        # USD source units pass through unchanged with no conversion row.
        self.assertEqual(automation._usd_conversion(
            "TEST", "cash_m", "USD", "2025-12-31", {}), (1.0, None))

    def test_zero_base_value_requires_explicit_terminal_outcome(self):
        identity = {"primary_method": "owner_earnings_reinvestment_dcf", "archetype": "compounder"}
        ledger = {"facts": [
            fact("normalized_owner_earnings_m", 1, "USD millions"),
            fact("shares_outstanding", 10_000_000, "shares"),
            fact("cash_m", 0, "USD millions"),
            fact("debt_m", 1_000_000, "USD millions"),
        ]}
        valuation = automation.compile_owner_earnings("ZERO", "2026-07-19", identity, ledger)
        valuation.setdefault("inputs", {})["price"] = 50.0
        contract = build_universal_valuation_contract(valuation, "quality_reinvestment")
        self.assertEqual(contract["valuation"]["value_per_share"]["base"], 0.0)
        self.assertEqual(contract["status"], "evidence_blocked")
        self.assertFalse(contract["model_checks"]["positive_base_or_explicit_zero_value"])

        explicit = copy.deepcopy(valuation)
        explicit.pop("universal_valuation_contract", None)
        explicit["valuation_methodology"]["zero_value_policy"] = {
            "allowed": True,
            "outcome": "insolvent_equity",
            "rationale": "Senior claims exceed every supported asset and cash-flow case.",
            "evidence_refs": ["issuer-10-k:debt-and-liquidity-note"],
        }
        explicit_contract = build_universal_valuation_contract(explicit, "quality_reinvestment")
        self.assertEqual(explicit_contract["status"], "decision_grade")
        self.assertTrue(explicit_contract["model_checks"]["positive_base_or_explicit_zero_value"])


if __name__ == "__main__":
    unittest.main()
