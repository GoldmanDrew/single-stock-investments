import copy

from calculation_proof import evaluate_calculation_proof
from complete_tier1_proof_models import CONFIG, _build_owner_cash_model


def _fact(field_id, value, unit):
    return {
        "field_id": field_id,
        "value": value,
        "unit": unit,
        "locked": True,
        "source": {
            "ref": "_system/frameworks/power_zones.json",
            "locator": field_id,
            "as_of": "2025-12-31",
        },
    }


def test_owner_cash_models_are_ordered_and_currency_aware():
    prior = {
        "ticker": "LSEG",
        "classification_inputs": {"archetype": "croupier"},
        "inputs": {"price": 90.0, "price_as_of": "2026-08-28"},
    }
    ledger = {
        "facts": [
            _fact("normalized_owner_cash", 2445.0, "GBP millions"),
            _fact("shares_outstanding", 524000000.0, "shares"),
            _fact("debt_m", 8175.0, "GBP millions"),
        ]
    }
    model = _build_owner_cash_model("LSEG", prior, ledger, copy.deepcopy(CONFIG["LSEG"]))
    component = model["component_valuation_results"]["additive_components"][0]
    evaluated = evaluate_calculation_proof(component["calculation_proof"])
    assert evaluated["status"] == "valid"
    assert evaluated["output_unit"] == "GBP per share"
    assert evaluated["outputs"]["low"] < evaluated["outputs"]["base"] < evaluated["outputs"]["high"]
    assert model["inputs"]["price"] == 90.0
    assert model["valuation_methodology"]["model_level"] == "stock_specific"


def test_all_completion_configs_name_primary_sources_and_adapters():
    assert set(CONFIG) == {"F", "FISV", "LSEG", "VTRS"}
    for config in CONFIG.values():
        assert len(config["sources"]) == 2
        assert config["adapter"].endswith("_adapter")
        assert config["profile"]
        assert config["falsifier"]
