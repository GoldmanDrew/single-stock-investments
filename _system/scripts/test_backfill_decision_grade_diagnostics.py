from backfill_decision_grade_diagnostics import build_spec
from falsifier_specs import spec_errors


def test_build_spec_is_typed_and_anchored():
    component = {
        "component_id": "core_engine",
        "method": "owner_earnings_reinvestment_dcf",
        "method_provenance": {"power_zones": ["quality_reinvestment"]},
    }
    contract = {"economic_ownership_map": [component]}
    ledger = {
        "facts": [{
            "field_id": "normalized_owner_earnings_m",
            "value": 100,
            "unit": "USD millions",
            "locked": True,
        }]
    }
    spec = build_spec("BN", contract, ledger, "abc123")
    assert spec["threshold"] == 100.0
    assert spec["untestable"] is False
    assert spec["observation_plan"]["source_adapter"] == "sec_companyfacts_ttm"
    assert spec_errors(spec) == []
