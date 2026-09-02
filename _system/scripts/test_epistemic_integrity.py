from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_falsifier_history
import falsifier_specs
import resolve_falsifiers
from falsifier_evidence_adapters import resolve_legacy_spec, resolve_spec
from promote_falsifier_drafts import promote


def v3_spec(**overrides) -> dict:
    spec = {
        "spec_id": "tst-core-cash-2026q2",
        "spec_revision": 1,
        "spec_schema_version": "3.0",
        "forecast_class": "ex_ante",
        "forecast_role": "primary",
        "authored_at": "2026-01-01T12:00:00Z",
        "information_cutoff_at": "2026-01-01T12:00:00Z",
        "registered_at": "2026-01-02T12:00:00Z",
        "registration_commit": "a" * 40,
        "analysis_run_id": "run-1",
        "author": "author-agent",
        "model_id": "model-v1",
        "prompt_version": "prompt-v1",
        "contract_hash": "b" * 64,
        "component_fingerprint": "c" * 64,
        "method_id": "owner_earnings_reinvestment_dcf",
        "power_zone": "quality_reinvestment",
        "component_id": "core",
        "correlation_group": "TST|core|cash|2026Q2",
        "industry": "software",
        "metric": "cash_and_equivalents",
        "comparator": "lt",
        "threshold": 50_000_000,
        "threshold_basis": {"source_ref": "TST/research/valuation_contract.json#core",
                            "rule": "low-case liquidity floor"},
        "unit": "USD",
        "measurement_period_end": "2026-06-30",
        "observable_after": "2026-08-01",
        "resolution_deadline": "2026-09-30",
        "source_hint": "us-gaap:CashAndCashEquivalentsAtCarryingValue",
        "observation_plan": {
            "metric_definition_id": "cash_and_equivalents_usd",
            "metric_definition_version": "1.0",
            "source_adapter": "sec_companyfacts",
            "fiscal_period": "Q2",
            "fiscal_year": 2026,
            "observation_type": "instant",
            "duration_basis": "instant",
            "accepted_forms": ["10-Q"],
            "canonical_unit": "USD",
            "end_date_tolerance_days": 7,
            "expected_publication_date": "2026-08-01",
            "maximum_source_lag_days": 30,
            "outcome_unavailable_at_registration": True,
            "historical_replay": {"status": "passed", "evidence_ref": "fixture:cash"},
        },
        "review": {"status": "approved", "reviewer": "review-agent",
                   "reviewed_at": "2026-01-02T11:00:00Z"},
        "probability_fires": 0.25,
        "severity": 4,
        "component_value_impact_pct": 12.0,
        "total_equity_value_impact_pct": 2.5,
        "derived_from": "Cash falls below the low-case liquidity floor",
        "untestable": False,
        "calibration_eligible": True,
        "rationale": "Below the threshold the low-case funding bridge fails.",
        "supersedes_spec_id": None,
    }
    spec.update(overrides)
    return spec


class EligibilityTests(unittest.TestCase):
    def test_valid_v3_is_eligible(self):
        spec = v3_spec()
        self.assertEqual(falsifier_specs.spec_errors(spec), [])
        self.assertEqual(falsifier_specs.calibration_eligibility(spec), (True, "eligible"))

    def test_lookahead_and_same_agent_review_fail_closed(self):
        spec = v3_spec(registered_at="2026-08-02T00:00:00Z")
        self.assertIn("registered_after_observability", falsifier_specs.calibration_eligibility(spec)[1])
        spec = v3_spec(review={"status": "approved", "reviewer": "author-agent",
                               "reviewed_at": "2026-01-02T11:00:00Z"})
        self.assertIn("independent_review_missing", falsifier_specs.calibration_eligibility(spec)[1])

    def test_twenty_legacy_outcomes_never_unlock(self):
        rows = []
        for index in range(20):
            legacy = {**v3_spec(), "spec_schema_version": "2.0",
                      "calibration_eligible": False, "probability_fires": None,
                      "spec_id": f"legacy-{index}"}
            rows.append({
                "ticker": f"T{index:02d}", "component_id": "core",
                "method_id": "owner_earnings_reinvestment_dcf",
                "power_zone": "quality_reinvestment", "verdict": "hit",
                "measurement_period_end": "2026-06-30", "evidence_ref": "fixture",
                "spec": legacy, "spec_hash": falsifier_specs.spec_payload_hash(legacy),
            })
        result = resolve_falsifiers.build_calibration(rows)
        self.assertEqual(result["status"], "insufficient_outcomes")
        self.assertEqual(result["eligible_scored_outcomes"], 0)
        bucket = result["buckets"]["owner_earnings_reinvestment_dcf|quality_reinvestment"]
        self.assertEqual(bucket["learning_status"], "plumbing_only")

    def test_diverse_prospective_cohort_unlocks_challenge(self):
        rows = []
        industries = ["software", "industrial", "consumer"]
        for index in range(20):
            measurement = "2026-06-30" if index < 10 else "2026-09-30"
            spec = v3_spec(
                spec_id=f"eligible-{index}",
                correlation_group=f"T{index:02d}|core|cash|{measurement}",
                industry=industries[index % len(industries)],
                measurement_period_end=measurement,
            )
            verdict = "hit" if index % 4 == 0 else "miss"
            rows.append({
                "ticker": f"T{index:02d}", "component_id": "core",
                "method_id": spec["method_id"], "power_zone": spec["power_zone"],
                "verdict": verdict, "measurement_period_end": measurement,
                "evidence_ref": "fixture", "spec": spec,
                "spec_hash": falsifier_specs.spec_payload_hash(spec),
            })
        result = resolve_falsifiers.build_calibration(rows)
        bucket = result["buckets"]["owner_earnings_reinvestment_dcf|quality_reinvestment"]
        self.assertEqual(bucket["learning_status"], "eligible_for_prompt_challenge")
        self.assertEqual(bucket["effective_outcomes"], 20)
        self.assertEqual(result["status"], "ready")


class PeriodAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        source_defs = Path(__file__).resolve().parents[1] / "research/metric_definitions.json"
        target = self.root / "_system/research/metric_definitions.json"
        target.parent.mkdir(parents=True)
        target.write_text(source_defs.read_text(encoding="utf-8"), encoding="utf-8")
        evidence = self.root / "TST/research/evidence/sec_companyfacts.json"
        evidence.parent.mkdir(parents=True)
        evidence.write_text(json.dumps({"facts": {"us-gaap": {
            "CashAndCashEquivalentsAtCarryingValue": {"units": {"USD": [
                {"end": "2026-06-28", "val": 40_000_000, "form": "10-Q",
                 "filed": "2026-08-05", "fy": 2026, "fp": "Q2"},
                {"end": "2026-09-27", "val": 30_000_000, "form": "10-Q",
                 "filed": "2026-11-01", "fy": 2026, "fp": "Q3"}
            ]}}
        }}}), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_qdel_style_weekend_period_resolves_by_fiscal_identity(self):
        result = resolve_spec("TST", v3_spec(), self.root, date(2026, 8, 10))
        self.assertEqual(result["value"], 40_000_000)
        self.assertEqual(result["as_of"], "2026-06-28")

    def test_adjacent_quarter_cannot_resolve_target(self):
        spec = v3_spec(observation_plan={**v3_spec()["observation_plan"],
                                        "fiscal_period": "Q1"})
        result = resolve_spec("TST", spec, self.root, date(2026, 12, 1))
        self.assertIsNone(result["value"])
        self.assertEqual(result["blocker_reason"], "fiscal_period_mismatch")

    def test_legacy_cash_uses_fiscal_identity_but_stays_diagnostic(self):
        legacy = {
            "spec_id": "legacy-qdel", "spec_revision": 1,
            "authored_at": "2026-08-10T00:00:00Z",
            "analysis_run_id": "legacy-migration-2026-08-12",
            "contract_hash": "a" * 64, "method_id": "net_asset_value",
            "power_zone": "quality_reinvestment", "component_id": "core",
            "metric": "cash_and_equivalents", "comparator": "lt",
            "threshold": 50.0, "unit": "USD millions",
            "measurement_period_end": "2026-06-30", "observable_after": "2026-08-01",
            "resolution_deadline": "2026-09-30", "source_hint": "cash_m",
            "probability_fires": None, "calibration_eligible": False,
            "severity": 3, "derived_from": "legacy", "untestable": False,
            "rationale": "legacy diagnostic", "author": "legacy_unrecorded",
            "model_id": "legacy_unrecorded", "prompt_version": "legacy_unrecorded"
        }
        result = resolve_legacy_spec("TST", legacy, self.root, date(2026, 12, 1))
        self.assertEqual(result["value"], 40.0)
        self.assertEqual(result["unit"], "USD millions")
        self.assertIn("legacy_diagnostic", result["adapter"])
        self.assertEqual(falsifier_specs.calibration_eligibility(legacy)[0], False)


class HistoryTests(unittest.TestCase):
    def test_edit_and_delete_are_rejected_but_supersession_passes(self):
        prior = v3_spec()
        base = {"TST": {"specs": [prior]}}
        edited = {**prior, "threshold": 1}
        self.assertTrue(any("edited" in error for error in
                            check_falsifier_history.history_errors(base, {"TST": {"specs": [edited]}})))
        self.assertTrue(any("deleted" in error for error in
                            check_falsifier_history.history_errors(base, {"TST": {"specs": []}})))
        replacement = v3_spec(spec_id="replacement", spec_revision=2,
                              supersedes_spec_id=prior["spec_id"])
        self.assertEqual(check_falsifier_history.history_errors(
            base, {"TST": {"specs": [prior, replacement]}}), [])

    def test_approved_draft_promotes_once(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            definitions = Path(__file__).resolve().parents[1] / "research/metric_definitions.json"
            target = root / "_system/research/metric_definitions.json"
            target.parent.mkdir(parents=True)
            target.write_bytes(definitions.read_bytes())
            component = {"component_id": "core", "method": "owner_earnings_reinvestment_dcf"}
            fingerprint = hashlib.sha256(json.dumps(
                component, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            spec = v3_spec(component_fingerprint=fingerprint)
            research = root / "TST/research"
            (research / "falsifier_drafts").mkdir(parents=True)
            (research / "valuation_contract.json").write_text(json.dumps({
                "economic_ownership_map": [component]}), encoding="utf-8")
            draft_path = research / "falsifier_drafts/draft-1.json"
            draft_path.write_text(json.dumps({
                "schema_version": "1.0", "draft_id": "draft-1", "work_id": "work-1",
                "input_sha": "abcdef0", "component_fingerprint": fingerprint,
                "status": "approved", "spec": spec}), encoding="utf-8")
            self.assertEqual(len(promote(root)["promoted"]), 1)
            self.assertEqual(len(promote(root)["promoted"]), 0)
            sidecar = json.loads((research / "falsifier_specs.json").read_text())
            self.assertEqual(len(sidecar["specs"]), 1)

    def test_malformed_draft_is_reported_instead_of_silently_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            draft_path = root / "TST/research/falsifier_drafts/bad.json"
            draft_path.parent.mkdir(parents=True)
            draft_path.write_text('{"status":"awaiting_review", // invalid\n}',
                                  encoding="utf-8")
            result = promote(root, write=False)
            self.assertEqual(len(result["blocked"]), 1)
            self.assertIn("invalid draft JSON", result["blocked"][0]["reasons"][0])


if __name__ == "__main__":
    unittest.main()
