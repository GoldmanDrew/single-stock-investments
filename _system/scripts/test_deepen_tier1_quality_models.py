from __future__ import annotations

import copy

import deepen_tier1_quality_models as deepening


def test_deepening_replaces_generic_maturity_and_assumptions() -> None:
    model = {
        "ticker": "ABC",
        "method": "proof_first_automated",
        "inputs": {},
        "valuation_methodology": {"automation": "source_locked_first_pass", "horizon_years": 7},
        "component_valuation_results": {
            "additive_components": [{
                "id": "operating_business_and_net_assets",
                "calculation_proof": {
                    "inputs": [
                        {"id": "owner_earnings", "value": 1},
                        {"id": "cash", "value": 1},
                        {"id": "debt", "value": 1},
                        {"id": "shares_m", "value": 1},
                    ],
                    "assumptions": [
                        {"id": "reinvestment", "values": {}},
                        {"id": "incremental_roic", "values": {}},
                        {"id": "discount_rate", "values": {}},
                        {"id": "terminal_multiple", "values": {}},
                    ],
                },
            }]
        },
    }
    ledger = {
        "facts": [
            {"field_id": "normalized_owner_earnings_m", "value": 100, "locked": True, "source": {"ref": "a"}},
            {"field_id": "cash_m", "value": 20, "locked": True, "source": {"ref": "b"}},
            {"field_id": "debt_m", "value": 5, "locked": True, "source": {"ref": "c"}},
            {"field_id": "shares_outstanding", "value": 10_000_000, "locked": True, "source": {"ref": "d"}},
        ]
    }
    config = copy.deepcopy(deepening.CONFIG["CPRT"])
    updated = deepening.deepen_model(model, ledger, config)
    assert updated["method"] == "owner_earnings_reinvestment_dcf"
    assert updated["valuation_methodology"]["model_level"] == "stock_specific"
    assert updated["valuation_methodology"]["automation"] == "stock_specific_reviewed_assumptions"
    assert updated["inputs"]["cash_m"] == 20
    proof = updated["component_valuation_results"]["additive_components"][0]["calculation_proof"]
    assumptions = {row["id"]: row for row in proof["assumptions"]}
    assert assumptions["terminal_multiple"]["values"] == {"low": 18, "base": 24, "high": 30}
    assert proof["inputs"][3]["value"] == 10
