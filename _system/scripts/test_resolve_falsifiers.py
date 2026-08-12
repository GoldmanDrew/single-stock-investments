from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import resolve_falsifiers as resolver  # noqa: E402

TODAY = date(2026, 8, 10)


def spec(**overrides) -> dict:
    base = {
        "component_id": "cash_and_liquidity",
        "metric": "cash_and_equivalents",
        "comparator": "lt",
        "threshold": 50000000,
        "unit": "USD",
        "due": "2026-06-30",
        "source_hint": "us-gaap:CashAndCashEquivalentsAtCarryingValue",
        "derived_from": "Cash burn drains the balance sheet before the catalyst",
        "untestable": False,
        "rationale": "Below 50M the bridge to the catalyst fails.",
    }
    base.update(overrides)
    return base


class CompareTests(unittest.TestCase):
    def test_all_comparators(self):
        self.assertEqual(resolver.compare(1, "lt", 2), "hit")
        self.assertEqual(resolver.compare(2, "lt", 2), "miss")
        self.assertEqual(resolver.compare(2, "lte", 2), "hit")
        self.assertEqual(resolver.compare(3, "lte", 2), "miss")
        self.assertEqual(resolver.compare(3, "gt", 2), "hit")
        self.assertEqual(resolver.compare(2, "gt", 2), "miss")
        self.assertEqual(resolver.compare(2, "gte", 2), "hit")
        self.assertEqual(resolver.compare(1, "gte", 2), "miss")
        self.assertEqual(resolver.compare(5, "outside_range", [10, 20]), "hit")
        self.assertEqual(resolver.compare(25, "outside_range", [10, 20]), "hit")
        self.assertEqual(resolver.compare(15, "outside_range", [10, 20]), "miss")
        with self.assertRaises(ValueError):
            resolver.compare(1, "ne", 2)


class ResolverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.seed()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, relative: str, value: dict) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def seed(self):
        # One synthetic ticker with a matured hit (companyfacts), a matured
        # miss (fact ledger), an unmatured spec, an unresolvable metric, and
        # an untestable prose placeholder.
        self.write("TST/research/falsifier_specs.json", {
            "schema_version": "1.0",
            "ticker": "TST",
            "specs": [
                # Matured HIT: latest at/after due is 40M < 50M threshold.
                # The pre-due 90M observation must NOT be selected.
                spec(),
                # Matured MISS via fact-ledger locked row: 42.0 > 10.0 is
                # false for comparator gt -> thesis survived.
                spec(component_id="ops", metric="owner_cash", comparator="gt",
                     threshold=100.0, source_hint="owner_cash_m", unit="USD millions",
                     derived_from="Owner cash collapses"),
                # Unmatured: due after the resolution date.
                spec(component_id="listing_option", metric="listing_milestone",
                     due="2027-01-31", derived_from="Listing never prices"),
                # Matured but unresolvable: concept absent everywhere.
                spec(component_id="pe_liability", metric="redemption_paid",
                     source_hint="us-gaap:DoesNotExist",
                     derived_from="Redemptions drain the parent"),
                # Untestable: resolver must skip it entirely.
                spec(component_id="governance", metric="board_alignment",
                     untestable=True, due=None, source_hint=None, threshold=None,
                     derived_from="Management stops acting like owners"),
            ],
        })
        self.write("TST/research/evidence/sec_companyfacts.json", {
            "facts": {"us-gaap": {"CashAndCashEquivalentsAtCarryingValue": {
                "units": {"USD": [
                    {"end": "2026-03-31", "val": 90000000, "form": "10-Q", "filed": "2026-05-14"},
                    {"end": "2026-06-30", "val": 40000000, "form": "10-Q", "filed": "2026-08-05"},
                ]},
            }}},
        })
        self.write("TST/research/valuation_fact_ledger.json", {
            "facts": [
                {"field_id": "owner_cash_m", "value": 42.0, "unit": "USD millions", "locked": True,
                 "source": {"ref": "TST/research/evidence/sec_companyfacts.json", "as_of": "2026-06-30"}},
            ],
        })
        self.write("TST/research/valuation_contract.json", {
            # Falsifier prose must anchor every spec's derived_from: the
            # resolver refuses to score a spec anchored to nothing (a verdict
            # on a fabricated spec would pollute the outcomes ledger).
            "economic_ownership_map": [
                {"component_id": "cash_and_liquidity", "method": "net_asset_value",
                 "falsifier": "Cash burn drains the balance sheet before the catalyst"},
                {"component_id": "ops", "method": "midcycle_capacity_value",
                 "falsifier": "Owner cash collapses"},
                {"component_id": "pe_liability", "method": "net_asset_value",
                 "falsifier": "Redemptions drain the parent"},
                {"component_id": "listing_option", "method": "risk_adjusted_milestone_value",
                 "falsifier": "Listing never prices"},
            ],
            "monitoring": {"falsifiers": [
                "Listing never prices",
                "Management stops acting like owners",
                "Debt balloons past the covenant ceiling",
            ]},
        })
        self.write("TST/research/valuation_route.json", {"profile_id": "capital_cycle"})
        # A leading-underscore directory with a sidecar must be ignored.
        self.write("_junk/research/falsifier_specs.json", {"specs": [spec()]})

    def outcomes(self) -> list[dict]:
        return resolver.load_outcomes(self.root / resolver.OUTCOMES_REL)

    def test_first_run_produces_exact_outcomes_and_calibration(self):
        result = resolver.run(self.root, TODAY, apply=True)
        rows = self.outcomes()
        self.assertEqual(len(rows), 3)
        by_component = {row["component_id"]: row for row in rows}

        hit = by_component["cash_and_liquidity"]
        self.assertEqual(hit["verdict"], "hit")
        self.assertEqual(hit["resolved_value"], 40000000)
        self.assertEqual(hit["resolved_as_of"], "2026-06-30")  # not the pre-due 90M row
        self.assertEqual(hit["resolved_unit"], "USD")
        self.assertIn("sec_companyfacts.json#us-gaap:CashAndCashEquivalentsAtCarryingValue@2026-06-30",
                      hit["evidence_ref"])
        self.assertEqual(hit["method_id"], "net_asset_value")
        self.assertEqual(hit["power_zone"], "capital_cycle")
        self.assertEqual(hit["resolved_on"], "2026-08-10")

        miss = by_component["ops"]
        self.assertEqual(miss["verdict"], "miss")
        self.assertEqual(miss["resolved_value"], 42.0)
        self.assertEqual(miss["evidence_ref"], "TST/research/valuation_fact_ledger.json#owner_cash_m")
        self.assertEqual(miss["method_id"], "midcycle_capacity_value")

        unresolvable = by_component["pe_liability"]
        self.assertEqual(unresolvable["verdict"], "unresolvable")
        self.assertIsNone(unresolvable["resolved_value"])
        self.assertIsNone(unresolvable["evidence_ref"])

        self.assertNotIn("listing_option", by_component)  # unmatured
        self.assertNotIn("governance", by_component)  # untestable
        counts = result["counts"]
        self.assertEqual(counts["sidecars"], 1)  # _junk ignored
        self.assertEqual((counts["hit"], counts["miss"], counts["unresolvable"]), (1, 1, 1))
        self.assertEqual(counts["unmatured"], 1)
        self.assertEqual(counts["untestable"], 1)

        calibration = json.loads((self.root / resolver.CALIBRATION_REL).read_text(encoding="utf-8"))
        self.assertEqual(calibration["status"], "insufficient_outcomes")
        self.assertEqual(calibration["minimum_outcomes"], 20)
        self.assertEqual(calibration["resolved_outcomes"], 3)
        self.assertEqual(calibration["scored_outcomes"], 2)
        nav = calibration["buckets"]["net_asset_value|capital_cycle"]
        self.assertEqual((nav["hit"], nav["miss"], nav["unresolvable"]), (1, 0, 1))
        midcycle = calibration["buckets"]["midcycle_capacity_value|capital_cycle"]
        self.assertEqual((midcycle["hit"], midcycle["miss"], midcycle["unresolvable"]), (0, 1, 0))
        self.assertIn("weights never change automatically", calibration["warning"])

    def test_second_run_is_idempotent(self):
        resolver.run(self.root, TODAY, apply=True)
        first = (self.root / resolver.OUTCOMES_REL).read_text(encoding="utf-8")
        result = resolver.run(self.root, TODAY, apply=True)
        self.assertEqual(result["new_rows"], [])
        self.assertEqual(result["counts"]["already_resolved"], 3)
        self.assertEqual((self.root / resolver.OUTCOMES_REL).read_text(encoding="utf-8"), first)
        calibration = json.loads((self.root / resolver.CALIBRATION_REL).read_text(encoding="utf-8"))
        self.assertEqual(calibration["resolved_outcomes"], 3)

    def test_dry_run_writes_nothing(self):
        result = resolver.run(self.root, TODAY, apply=False)
        self.assertEqual(len(result["new_rows"]), 3)
        self.assertFalse((self.root / resolver.OUTCOMES_REL).exists())
        self.assertFalse((self.root / resolver.CALIBRATION_REL).exists())

    def test_refuses_to_zero_calibration_when_ledger_missing(self):
        resolver.run(self.root, TODAY, apply=True)
        (self.root / resolver.OUTCOMES_REL).unlink()
        with self.assertRaises(SystemExit):
            resolver.run(self.root, TODAY, apply=True)

    def test_apply_with_no_new_rows_still_creates_ledger(self):
        # Regression (verified): the first scheduled run went red because the
        # resolver only created falsifier_outcomes.jsonl when new_rows was
        # non-empty, while the workflow's `git add --sparse` of that path
        # exits 128 when the file does not exist.  --apply must always create
        # the ledger; empty is a valid state.
        self.write("TST/research/falsifier_specs.json", {
            "schema_version": "1.0",
            "ticker": "TST",
            "specs": [spec(due="2027-06-30")],  # unmatured: zero new outcomes
        })
        result = resolver.run(self.root, TODAY, apply=True)
        self.assertEqual(result["new_rows"], [])
        path = self.root / resolver.OUTCOMES_REL
        self.assertTrue(path.exists(), "ledger file must exist after --apply even with no new rows")
        self.assertEqual(path.read_text(encoding="utf-8"), "")
        self.assertTrue((self.root / resolver.CALIBRATION_REL).exists())
        # And the empty ledger does not trip the fail-closed zeroing guard.
        second = resolver.run(self.root, TODAY, apply=True)
        self.assertEqual(second["new_rows"], [])

    def test_fabricated_spec_is_never_scored(self):
        # A structurally valid spec whose component_id and derived_from anchor
        # to nothing in the contract must be rejected at scoring time, not
        # scored into the outcomes ledger.
        self.write("TST/research/falsifier_specs.json", {
            "schema_version": "1.0", "ticker": "TST",
            "specs": [spec(component_id="phantom_component",
                           derived_from="An invented falsifier matching no contract prose",
                           due="2026-01-31")],
        })
        result = resolver.run(self.root, date(2026, 8, 10), apply=True)
        self.assertEqual(result["counts"]["invalid"], 1)
        self.assertEqual(result["counts"]["hit"] + result["counts"]["miss"]
                         + result["counts"]["unresolvable"], 0)
        self.assertEqual(self.outcomes(), [])

    def test_two_distinct_specs_same_component_and_due_both_score(self):
        # Regression (verified repro): a cash-lt floor AND a debt-gt ceiling
        # on the same component and due date.  The old dedupe key
        # (ticker, component_id, due) silently dropped the second spec in the
        # same pass: the genuine debt hit never scored and the run miscounted
        # it as already_resolved.
        self.write("TST/research/falsifier_specs.json", {
            "schema_version": "1.0",
            "ticker": "TST",
            "specs": [
                # 40M cash < 10M threshold is false -> miss (thesis survived).
                spec(metric="cash_and_equivalents", comparator="lt",
                     threshold=10000000),
                # 50M debt > 30M threshold -> the genuine hit.
                spec(metric="total_debt", comparator="gt", threshold=30000000,
                     source_hint="us-gaap:DebtCurrent",
                     derived_from="Debt balloons past the covenant ceiling"),
            ],
        })
        self.write("TST/research/evidence/sec_companyfacts.json", {
            "facts": {"us-gaap": {
                "CashAndCashEquivalentsAtCarryingValue": {"units": {"USD": [
                    {"end": "2026-06-30", "val": 40000000, "form": "10-Q", "filed": "2026-08-05"},
                ]}},
                "DebtCurrent": {"units": {"USD": [
                    {"end": "2026-06-30", "val": 50000000, "form": "10-Q", "filed": "2026-08-05"},
                ]}},
            }},
        })
        result = resolver.run(self.root, TODAY, apply=True)
        self.assertEqual(len(result["new_rows"]), 2)
        self.assertEqual(result["counts"]["already_resolved"], 0)
        rows = self.outcomes()
        by_metric = {row["spec"]["metric"]: row["verdict"] for row in rows}
        self.assertEqual(by_metric, {"cash_and_equivalents": "miss", "total_debt": "hit"})
        # Re-runs stay idempotent on the widened key.
        second = resolver.run(self.root, TODAY, apply=True)
        self.assertEqual(second["new_rows"], [])
        self.assertEqual(second["counts"]["already_resolved"], 2)

    def test_pre_due_ledger_fact_never_resolves(self):
        # Regression (verified repro): a spec due 2026-06-30 scored 'hit'
        # from a locked ledger fact dated 2025-09-30.  A verdict on pre-due
        # data is not a resolution: the ledger path requires source as_of on
        # or after due, else companyfacts, else unresolvable.
        self.write("TST/research/falsifier_specs.json", {
            "schema_version": "1.0",
            "ticker": "TST",
            "specs": [spec(component_id="ops", metric="owner_cash", comparator="gt",
                           threshold=100.0, source_hint="owner_cash_m",
                           unit="USD millions", derived_from="Owner cash collapses")],
        })
        self.write("TST/research/valuation_fact_ledger.json", {
            "facts": [
                {"field_id": "owner_cash_m", "value": 42.0, "unit": "USD millions",
                 "locked": True,
                 "source": {"ref": "TST/research/evidence/sec_companyfacts.json",
                            "as_of": "2025-09-30"}},
            ],
        })
        result = resolver.run(self.root, TODAY, apply=True)
        rows = self.outcomes()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["verdict"], "unresolvable")
        self.assertIsNone(rows[0]["resolved_value"])
        self.assertIsNone(rows[0]["evidence_ref"])
        self.assertEqual(result["counts"]["unresolvable"], 1)

    def test_stale_ledger_fact_falls_through_to_companyfacts(self):
        # A locked ledger row dated before due must fall through to the
        # at/after-due companyfacts observation instead of resolving stale.
        hint = "us-gaap:CashAndCashEquivalentsAtCarryingValue"
        self.write("TST/research/falsifier_specs.json", {
            "schema_version": "1.0",
            "ticker": "TST",
            "specs": [spec()],  # source_hint is the companyfacts concept
        })
        self.write("TST/research/valuation_fact_ledger.json", {
            "facts": [
                {"field_id": hint, "value": 90000000.0, "unit": "USD", "locked": True,
                 "source": {"as_of": "2026-03-31"}},
            ],
        })
        resolver.run(self.root, TODAY, apply=True)
        rows = self.outcomes()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["resolved_value"], 40000000)
        self.assertEqual(rows[0]["resolved_as_of"], "2026-06-30")
        self.assertEqual(rows[0]["verdict"], "hit")
        self.assertIn("sec_companyfacts.json", rows[0]["evidence_ref"])


if __name__ == "__main__":
    unittest.main()
