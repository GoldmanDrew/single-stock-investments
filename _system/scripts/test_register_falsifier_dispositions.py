from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from register_falsifier_dispositions import register


class RegisterFalsifierDispositionsTests(unittest.TestCase):
    def test_registers_only_reviewed_complete_additive_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            research = root / "AAA" / "research"
            research.mkdir(parents=True)
            contract = {
                "method_route": {"profile_id": "scarce_asset_optionality"},
                "economic_ownership_map": [{
                    "component_id": "asset", "treatment": "additive",
                    "method": "net_asset_value", "falsifier": "Asset recovery misses the low case.",
                }],
            }
            (research / "valuation_contract.json").write_text(json.dumps(contract), encoding="utf-8")
            review = {
                "ticker": "AAA", "status": "reviewed_typed_untestable_dispositions",
                "historical_replay": {"status": "passed"},
                "registered_at": "2026-09-01T04:00:00Z",
                "information_cutoff_at": "2026-09-01T03:59:00Z",
                "registration_commit": "abc123", "analysis_run_id": "test-run",
                "component_dispositions": [{
                    "component_id": "asset", "metric": "asset recovery composite",
                    "rationale": "The required source adapter does not exist.",
                    "untestable_reason_code": "adapter_missing", "required_adapter": "asset_adapter",
                    "review_by": "2026-12-31", "unit": "issuer-defined asset composite",
                    "observation_plan": {
                        "metric_definition_id": "asset_recovery", "fiscal_period": "event-driven",
                        "observation_type": "event", "duration_basis": "event-driven",
                        "expected_publication_date": "2026-12-31", "accepted_forms": ["10-Q"],
                        "maximum_source_lag_days": 30,
                    },
                }],
            }
            review_path = research / "review.json"
            review_path.write_text(json.dumps(review), encoding="utf-8")
            result = register("AAA", review_path, root=root)
            payload = json.loads((research / "falsifier_specs.json").read_text(encoding="utf-8"))
        self.assertEqual(result["spec_count"], 1)
        self.assertTrue(payload["specs"][0]["untestable"])
        self.assertEqual(payload["specs"][0]["derived_from"], "Asset recovery misses the low case.")

    def test_refuses_partial_component_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            research = root / "AAA" / "research"
            research.mkdir(parents=True)
            (research / "valuation_contract.json").write_text(json.dumps({
                "economic_ownership_map": [
                    {"component_id": "a", "treatment": "additive", "falsifier": "a fails"},
                    {"component_id": "b", "treatment": "additive", "falsifier": "b fails"},
                ]
            }), encoding="utf-8")
            review = {
                "ticker": "AAA", "status": "reviewed_typed_untestable_dispositions",
                "historical_replay": {"status": "passed"}, "registered_at": "2026-09-01T04:00:00Z",
                "information_cutoff_at": "2026-09-01T03:59:00Z", "registration_commit": "abc",
                "analysis_run_id": "test", "component_dispositions": [],
            }
            review_path = research / "review.json"
            review_path.write_text(json.dumps(review), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "do not cover every additive component"):
                register("AAA", review_path, root=root)


if __name__ == "__main__":
    unittest.main()
