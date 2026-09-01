from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import falsifier_specs as fs  # noqa: E402


def good_spec(**overrides) -> dict:
    spec = {
        "component_id": "cash_and_liquidity",
        "metric": "cash_and_equivalents",
        "comparator": "lt",
        "threshold": 50000000,
        "unit": "USD",
        "due": "2026-06-30",
        "source_hint": "us-gaap:CashAndCashEquivalentsAtCarryingValue",
        "derived_from": "Cash burn drains the balance sheet before the catalyst",
        "untestable": False,
        "rationale": "Below 50M the bridge to the 2027 catalyst fails.",
    }
    spec.update(overrides)
    return spec


def good_sidecar(**overrides) -> dict:
    doc = {"schema_version": "1.0", "ticker": "TST", "specs": [good_spec()]}
    doc.update(overrides)
    return doc


def revision_spec(**overrides) -> dict:
    spec = good_spec(
        spec_id="cash-floor",
        spec_revision=1,
        authored_at="2026-01-01T00:00:00Z",
        analysis_run_id="test-run",
        contract_hash="a" * 64,
        method_id="net_asset_value",
        power_zone="asset_backed_optionality",
        probability_fires=0.25,
        calibration_eligible=False,
        severity=3,
        measurement_period_end="2026-06-30",
        observable_after="2026-07-31",
        resolution_deadline="2026-09-30",
        supersedes_spec_id=None,
        author="test",
        model_id="test-model",
        prompt_version="test-v1",
    )
    spec.update(overrides)
    return spec


class SpecValidationTests(unittest.TestCase):
    def test_valid_spec_accepted(self):
        self.assertEqual(fs.spec_errors(good_spec()), [])

    def test_valid_sidecar_accepted(self):
        self.assertEqual(fs.validate_sidecar(good_sidecar(), ticker="TST"), [])

    def test_bad_comparator_rejected(self):
        errors = fs.spec_errors(good_spec(comparator="ne"))
        self.assertTrue(any("comparator" in e for e in errors))

    def test_non_numeric_threshold_rejected(self):
        errors = fs.spec_errors(good_spec(threshold="fifty"))
        self.assertTrue(any("threshold" in e for e in errors))

    def test_boolean_threshold_rejected(self):
        errors = fs.spec_errors(good_spec(threshold=True))
        self.assertTrue(any("threshold" in e for e in errors))

    def test_outside_range_requires_pair(self):
        errors = fs.spec_errors(good_spec(comparator="outside_range", threshold=5))
        self.assertTrue(any("low, high" in e for e in errors))

    def test_outside_range_pair_accepted(self):
        spec = good_spec(comparator="outside_range", threshold=[10, 20])
        self.assertEqual(fs.spec_errors(spec), [])

    def test_outside_range_inverted_pair_rejected(self):
        spec = good_spec(comparator="outside_range", threshold=[20, 10])
        errors = fs.spec_errors(spec)
        self.assertTrue(any("low must not exceed high" in e for e in errors))

    def test_bad_due_date_rejected(self):
        errors = fs.spec_errors(good_spec(due="soon"))
        self.assertTrue(any("due" in e for e in errors))

    def test_missing_due_rejected_for_testable(self):
        errors = fs.spec_errors(good_spec(due=None))
        self.assertTrue(any("due" in e for e in errors))

    def test_untestable_spec_may_omit_due_source_and_threshold(self):
        spec = good_spec(untestable=True, due=None, source_hint=None, threshold=None)
        self.assertEqual(fs.spec_errors(spec), [])

    def test_missing_derived_from_rejected(self):
        errors = fs.spec_errors(good_spec(derived_from=""))
        self.assertTrue(any("derived_from" in e for e in errors))

    def test_missing_rationale_rejected(self):
        errors = fs.spec_errors(good_spec(rationale="   "))
        self.assertTrue(any("rationale" in e for e in errors))

    def test_non_bool_untestable_rejected(self):
        errors = fs.spec_errors(good_spec(untestable="no"))
        self.assertTrue(any("untestable" in e for e in errors))

    def test_ticker_mismatch_rejected(self):
        errors = fs.validate_sidecar(good_sidecar(ticker="OTHER"), ticker="TST")
        self.assertTrue(any("expected TST" in e for e in errors))

    def test_non_list_specs_rejected(self):
        errors = fs.validate_sidecar(good_sidecar(specs={"a": 1}))
        self.assertTrue(any("specs" in e for e in errors))

    def test_due_parsing(self):
        self.assertEqual(fs.parse_due("2026-06-30").isoformat(), "2026-06-30")
        self.assertIsNone(fs.parse_due("2026-13-01"))
        self.assertIsNone(fs.parse_due(None))

    def test_revision_history_validates_and_only_latest_revision_is_active(self):
        first = revision_spec()
        second = revision_spec(
            spec_id="cash-floor", spec_revision=2,
            supersedes_spec_id="cash-floor", threshold=45000000,
        )
        doc = good_sidecar(specs=[first, second])
        self.assertEqual(fs.validate_sidecar(doc, ticker="TST"), [])
        self.assertEqual(fs.active_specs(doc["specs"]), [second])

    def test_duplicate_immutable_revision_is_rejected(self):
        first = revision_spec()
        errors = fs.validate_sidecar(good_sidecar(specs=[first, dict(first)]), ticker="TST")
        self.assertTrue(any("duplicate immutable identity" in error for error in errors))


class ResolvabilityAndCoverageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, relative: str, value: dict) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def seed_evidence(self):
        self.write("TST/research/valuation_fact_ledger.json", {
            "facts": [
                {"field_id": "cash_m", "value": 42.0, "unit": "USD millions", "locked": True,
                 "source": {"ref": "TST/research/evidence/sec_companyfacts.json", "as_of": "2026-03-31"}},
                {"field_id": "unlocked_m", "value": 9.0, "unit": "USD millions", "locked": False},
            ],
        })
        self.write("TST/research/evidence/sec_companyfacts.json", {
            "facts": {"us-gaap": {"CashAndCashEquivalentsAtCarryingValue": {
                "units": {"USD": [{"end": "2026-06-30", "val": 40000000, "form": "10-Q"}]},
            }}},
        })

    def test_ledger_field_resolvable(self):
        self.seed_evidence()
        ok, reason = fs.metric_resolvable("TST", good_spec(source_hint="cash_m"), root=self.root)
        self.assertTrue(ok, reason)
        self.assertIn("fact ledger", reason)

    def test_unlocked_ledger_field_not_resolvable(self):
        self.seed_evidence()
        ok, reason = fs.metric_resolvable("TST", good_spec(source_hint="unlocked_m"), root=self.root)
        self.assertFalse(ok)

    def test_companyfacts_concept_resolvable(self):
        self.seed_evidence()
        ok, reason = fs.metric_resolvable("TST", good_spec(), root=self.root)
        self.assertTrue(ok, reason)
        self.assertIn("companyfacts", reason)

    def test_unknown_hint_not_resolvable(self):
        self.seed_evidence()
        ok, reason = fs.metric_resolvable("TST", good_spec(source_hint="us-gaap:DoesNotExist"), root=self.root)
        self.assertFalse(ok)
        self.assertIn("not found", reason)

    def test_untestable_spec_not_resolvable_by_declaration(self):
        ok, reason = fs.metric_resolvable("TST", good_spec(untestable=True), root=self.root)
        self.assertFalse(ok)
        self.assertIn("untestable", reason)

    def contract(self) -> dict:
        return {
            "economic_ownership_map": [
                {"component_id": "cash_and_liquidity",
                 "falsifier": "Cash burn drains the balance sheet before the catalyst"},
                {"component_id": "listing_option", "falsifier": "HK listing fails"},
            ],
            "monitoring": {"falsifiers": ["HK listing fails"]},
        }

    def test_coverage_counts_typed_prose_and_untestable(self):
        self.seed_evidence()
        self.write("TST/research/falsifier_specs.json", {
            "schema_version": "1.0",
            "ticker": "TST",
            "specs": [
                good_spec(),
                good_spec(component_id="listing_option", untestable=True, due=None,
                          source_hint=None, threshold=None,
                          derived_from="HK listing fails"),
                good_spec(comparator="bogus"),  # invalid: never counts as typed
            ],
        })
        coverage = fs.coverage_summary("TST", self.contract(), root=self.root)
        self.assertEqual(coverage["typed"], 1)
        self.assertEqual(coverage["untestable"], 1)
        self.assertEqual(coverage["invalid"], 1)
        self.assertEqual(coverage["unanchored"], 0)
        self.assertEqual(coverage["resolvable"], 1)
        self.assertEqual(coverage["unresolvable"], 0)
        # Both distinct prose falsifiers are typed (one testable, one
        # explicitly untestable): nothing remains prose-only.
        self.assertEqual(coverage["prose_only"], 0)
        self.assertEqual(coverage["spec_ref"], "TST/research/falsifier_specs.json")
        self.assertFalse(coverage["enforcement_enabled"])

    def test_superseding_testable_revision_removes_active_untestable_debt(self):
        self.seed_evidence()
        old = revision_spec(
            spec_id="cash-floor", spec_revision=1, untestable=True,
            due=None, source_hint=None, threshold=None, probability_fires=None,
            measurement_period_end=None, observable_after=None, resolution_deadline=None,
        )
        repaired = revision_spec(
            spec_id="cash-floor", spec_revision=2,
            supersedes_spec_id="cash-floor",
        )
        self.write("TST/research/falsifier_specs.json", {
            "schema_version": "3.0", "ticker": "TST", "specs": [old, repaired],
        })
        coverage = fs.coverage_summary("TST", self.contract(), root=self.root)
        self.assertEqual(coverage["typed"], 1)
        self.assertEqual(coverage["untestable"], 0)

    def test_coverage_without_sidecar(self):
        coverage = fs.coverage_summary("TST", self.contract(), root=self.root)
        self.assertEqual(coverage["typed"], 0)
        self.assertEqual(coverage["prose_only"], 2)
        self.assertEqual(coverage["unanchored"], 0)
        self.assertIsNone(coverage["spec_ref"])

    def test_fabricated_spec_counts_unanchored_never_typed(self):
        # Regression (verified): a spec with a phantom component_id, an
        # invented threshold and a derived_from matching nothing passed
        # validation and inflated typed coverage toward the 60% enforcement
        # threshold.  It must count as unanchored, never typed.
        self.seed_evidence()
        self.write("TST/research/falsifier_specs.json", {
            "schema_version": "1.0",
            "ticker": "TST",
            "specs": [
                good_spec(component_id="phantom_component",
                          derived_from="Invented falsifier matching nothing in the contract"),
            ],
        })
        coverage = fs.coverage_summary("TST", self.contract(), root=self.root)
        self.assertEqual(coverage["typed"], 0)
        self.assertEqual(coverage["unanchored"], 1)
        self.assertEqual(coverage["invalid"], 0)
        # Unanchored specs type nothing: both contract falsifiers stay prose.
        self.assertEqual(coverage["prose_only"], 2)

    def test_spec_errors_with_contract_reports_anchor_failures(self):
        contract = self.contract()
        errors = fs.spec_errors(good_spec(component_id="phantom_component"), contract=contract)
        self.assertTrue(any("component_id" in e and "phantom_component" in e for e in errors))
        errors = fs.spec_errors(
            good_spec(derived_from="Nothing like this appears in the contract"),
            contract=contract)
        self.assertTrue(any("derived_from" in e for e in errors))
        # An honestly anchored spec passes with the contract supplied.
        self.assertEqual(fs.spec_errors(good_spec(), contract=contract), [])
        # Without a contract, behavior is unchanged (structural checks only).
        self.assertEqual(fs.spec_errors(good_spec(component_id="phantom_component")), [])

    def test_monitoring_pseudo_id_anchors_monitoring_falsifiers(self):
        spec = good_spec(component_id="monitoring", derived_from="HK listing fails")
        self.assertEqual(fs.anchor_errors(spec, self.contract()), [])

    def test_derived_from_normalized_substring_match(self):
        # Case/whitespace-insensitive substring of the contract text anchors.
        spec = good_spec(derived_from="  CASH BURN drains   the balance sheet  ")
        self.assertEqual(fs.anchor_errors(spec, self.contract()), [])

    def test_coverage_counts_resolvability_of_typed_specs(self):
        self.seed_evidence()
        self.write("TST/research/falsifier_specs.json", {
            "schema_version": "1.0",
            "ticker": "TST",
            "specs": [
                good_spec(),  # resolvable via companyfacts concept
                good_spec(component_id="listing_option",
                          source_hint="us-gaap:DoesNotExist",
                          derived_from="HK listing fails"),  # typed but unresolvable
            ],
        })
        coverage = fs.coverage_summary("TST", self.contract(), root=self.root)
        self.assertEqual(coverage["typed"], 2)
        self.assertEqual(coverage["resolvable"], 1)
        self.assertEqual(coverage["unresolvable"], 1)

    def test_enforcement_flag_read_from_graph_sources(self):
        self.write("_system/graph/graph_sources.json", {
            "falsifier_enforcement": {"enforcement_enabled": True},
        })
        coverage = fs.coverage_summary("TST", self.contract(), root=self.root)
        self.assertTrue(coverage["enforcement_enabled"])


if __name__ == "__main__":
    unittest.main()
