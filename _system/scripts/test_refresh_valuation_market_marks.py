from __future__ import annotations

import copy
import json
from unittest.mock import patch

import pytest

import refresh_valuation_market_marks as marks


def _contract(price: float, price_as_of: str) -> dict:
    return {
        "ticker": "ABC",
        "status": "decision_grade",
        "proof_status": "decision_grade",
        "model_level": "stock_specific",
        "dates": {"model_as_of": "2026-06-30", "price_as_of": price_as_of},
        "market": {"price_per_share": price, "fully_diluted_shares": 10.0},
        "economic_ownership_map": [{
            "component_id": "core",
            "category": "operating_business",
            "treatment": "additive",
            "method": "owner_cash_or_dividend_discount",
            "method_version": "1.0",
            "range_per_share": {"low": 8.0, "base": 12.0, "high": 16.0},
            "scenario_assumptions": {"base": {"growth": 0.03}},
        }],
        "valuation": {
            "output_basis": "present_value_today",
            "output_basis_status": "valid",
            "output_range_per_share": {"low": 8.0, "base": 12.0, "high": 16.0},
            "value_per_share": {"low": 8.0, "base": 12.0, "high": 16.0},
            "present_value_today_per_share": {"low": 8.0, "base": 12.0, "high": 16.0},
            "future_payoff_per_share": {"low": None, "base": None, "high": None},
            "priced_components_per_share": {"low": 8.0, "base": 12.0, "high": 16.0},
            "forward_return_at_price_pct": {"low": None, "base": None, "high": None},
            "forward_return_status": "withheld",
            "forward_return_reason": "present value",
            "annualized_return_at_price_pct": {"low": None, "base": None, "high": None},
            "annualized_return_field_status": "compatibility_alias_of_forward_return",
            "margin_of_safety_pct": {"low": -25.0, "base": 16.67, "high": 37.5},
            "upside_to_value_pct": {"low": -20.0, "base": 20.0, "high": 60.0},
            "downside_to_low_pct": -20.0,
        },
        "legacy_audit": {"annualized_return_at_price_pct": {"base": 3.0}},
        "change_control": {"model_hash": "old", "change_log": []},
    }


def test_refresh_preserves_reviewed_status_and_economics(tmp_path) -> None:
    research = tmp_path / "ABC" / "research"
    research.mkdir(parents=True)
    reviewed = _contract(10.0, "2026-06-30")
    (research / "valuation.json").write_text(
        json.dumps({"ticker": "ABC", "inputs": {"price": 11.0, "price_as_of": "2026-08-31"}}),
        encoding="utf-8",
    )
    (research / "valuation_contract.json").write_text(json.dumps(reviewed), encoding="utf-8")
    candidate = _contract(11.0, "2026-08-31")
    candidate["status"] = "evidence_blocked"  # Full revalidation may find unrelated new gates.
    candidate["economic_ownership_map"][0]["calculation_proof"] = {"source_lineage": ["new provenance"]}
    candidate["valuation"]["margin_of_safety_pct"] = {"low": -37.5, "base": 8.33, "high": 31.25}

    with patch.object(marks, "ROOT", tmp_path), patch.object(
        marks, "build_universal_valuation_contract", return_value=candidate
    ):
        result = marks.refresh("ABC")

    updated = json.loads((research / "valuation_contract.json").read_text(encoding="utf-8"))
    assert result["status"] == "updated"
    assert updated["status"] == "decision_grade"
    assert updated["model_level"] == "stock_specific"
    assert updated["economic_ownership_map"] == reviewed["economic_ownership_map"]
    assert updated["market"]["price_per_share"] == 11.0
    assert updated["dates"]["price_as_of"] == "2026-08-31"
    assert updated["valuation"]["margin_of_safety_pct"]["base"] == 8.33


def test_refresh_refuses_an_economic_change(tmp_path) -> None:
    research = tmp_path / "ABC" / "research"
    research.mkdir(parents=True)
    reviewed = _contract(10.0, "2026-06-30")
    (research / "valuation.json").write_text(json.dumps({"ticker": "ABC"}), encoding="utf-8")
    (research / "valuation_contract.json").write_text(json.dumps(reviewed), encoding="utf-8")
    candidate = copy.deepcopy(reviewed)
    candidate["economic_ownership_map"][0]["range_per_share"]["base"] = 13.0

    with patch.object(marks, "ROOT", tmp_path), patch.object(
        marks, "build_universal_valuation_contract", return_value=candidate
    ), pytest.raises(ValueError, match="economic basis changed"):
        marks.refresh("ABC")
