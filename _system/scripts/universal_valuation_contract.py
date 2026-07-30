#!/usr/bin/env python3
"""Build the common, proof-first decision contract emitted by every valuation."""
from __future__ import annotations

from datetime import date
from math import isfinite
import re

from calculation_proof import (
    CASES,
    PRICED_STATUSES,
    canonical_hash,
    component_proof,
    floor_equity_value_range,
    proof_completeness,
)
from valuation_method_registry import approved_method
from valuation_method_router import route_valuation

PRIMARY_EVIDENCE = {"primary", "primary_verified", "primary_derived", "filing", "contract", "audited"}
NON_TICKER_SOURCE_ROOTS = {"_system", "_external", "dashboard", "investor-documents"}
HARD_STALE_DAYS = 1095
EXTREME_RETURN_PCT = 25.0


def _annualized(value: float | None, price: float | None, years: int, distributions: float = 0) -> float | None:
    if value is None or price is None or price <= 0 or years <= 0 or value + distributions <= 0:
        return None
    result = ((float(value) + distributions) / float(price)) ** (1 / years) - 1
    return round(result * 100, 2) if isfinite(result) else None


def _source_acceptance_errors(ticker: str, as_of: str | None, rows: list[dict]) -> list[str]:
    errors = []
    try:
        contract_date = date.fromisoformat(str(as_of)[:10])
    except (TypeError, ValueError):
        contract_date = None
    for row in rows:
        component_id = str(row.get("component_id") or "component")
        proof = row.get("calculation_proof") or {}
        for source in proof.get("source_lineage") or []:
            ref = str(source.get("ref") or "").replace("\\", "/")
            locator = str(source.get("locator") or "")
            root = ref.split("/", 1)[0] if "/" in ref else ""
            if (
                root
                and root not in NON_TICKER_SOURCE_ROOTS
                and not root.startswith("_")
                and root.upper() != ticker.upper()
                and re.fullmatch(r"[A-Za-z0-9._-]+", root)
            ):
                errors.append(
                    f"{component_id}: source {ref} belongs to {root}, not {ticker}"
                )
            if "human review" in locator.lower():
                errors.append(
                    f"{component_id}: source locator explicitly requires human review"
                )
            source_date = source.get("as_of")
            if contract_date and source_date:
                try:
                    age_days = (contract_date - date.fromisoformat(str(source_date)[:10])).days
                except ValueError:
                    age_days = 0
                if age_days > HARD_STALE_DAYS:
                    errors.append(
                        f"{component_id}: source fact {source.get('node_id')} is stale "
                        f"({source_date}; {age_days} days old)"
                    )
    return errors


def _input_kind(row: dict) -> str:
    proof = row.get("calculation_proof") or {}
    kinds = {item.get("kind") for item in [*(proof.get("inputs") or []), *(proof.get("assumptions") or [])]}
    if "judgment" in kinds:
        return "judgment"
    if "estimate" in kinds:
        return "estimate"
    if kinds == {"fact"}:
        return "fact"
    tier = str(row.get("evidence_tier") or "").lower()
    if tier in PRIMARY_EVIDENCE:
        return "fact"
    if row.get("driver_model") or tier in {"model_input", "vendor", "secondary_corroborated"}:
        return "estimate"
    return "judgment"


def _standard_evidence_level(row: dict) -> str:
    tier = str(row.get("evidence_tier") or "").lower()
    if tier in {"primary_derived", "calculated"}:
        return "primary_derived"
    if tier in PRIMARY_EVIDENCE or "filing" in tier or "contract" in tier:
        return "primary_verified"
    if tier in {"secondary", "secondary_corroborated", "golden_case"}:
        return "secondary_corroborated"
    if tier in {"vendor", "market_data"}:
        return "vendor_sourced"
    if tier in {"speculative", "illustrative_only", "unverified"}:
        return "speculative"
    return "analyst_estimated"


def _sum_priced(rows: list[dict]) -> dict:
    result = {}
    for case in CASES:
        values = [row.get("range_per_share", {}).get(case) for row in rows if row.get("valuation_status") in PRICED_STATUSES]
        result[case] = round(sum(float(value) for value in values if value is not None), 4)
    return result


def build_universal_valuation_contract(data: dict, explicit_profile: str | None = None) -> dict:
    result = data.get("component_valuation_results") or {}
    economic = data.get("economic_value_analysis") or {}
    inputs = data.get("inputs") or {}
    route = route_valuation(data, explicit_profile)
    raw_components = [*(result.get("additive_components") or []), *(result.get("embedded_components") or [])]
    additive = [row for row in raw_components if row.get("treatment") == "additive"]
    embedded = [row for row in raw_components if row.get("treatment") != "additive"]
    components = [*additive, *embedded]
    price = inputs.get("price")
    shares = inputs.get("shares_outstanding")
    if shares is None and inputs.get("shares_millions") is not None:
        shares = float(inputs["shares_millions"]) * 1_000_000
    methodology = data.get("valuation_methodology") or {}
    years = int(methodology.get("horizon_years") or data.get("lawrence_horizon_years") or 7)
    distributions = float(methodology.get("expected_distributions_per_share") or 0)
    validation_errors = list(economic.get("validation_errors") or [])
    evidence_blockers: list[str] = []
    try:
        price_ok = price is not None and float(price) > 0
    except (TypeError, ValueError):
        price_ok = False
    if not price_ok:
        evidence_blockers.append(
            "Market price per share is missing or non-positive; cannot mark decision_grade or compute entry prices."
        )
    records, evaluated_rows = [], []
    buckets = {"facts": [], "estimates": [], "judgments": []}
    old_proof = {str(row.get("component_id")): row for row in economic.get("valuation_proof") or []}

    overlap_seen: dict[str, str] = {}
    double_counting_flags = []
    for row in components:
        component_id = str(row.get("id"))
        proof_result = component_proof(row)
        evaluation = proof_result.get("evaluation")
        status = proof_result["valuation_status"]
        provenance = approved_method(
            evaluation.get("method_id") if evaluation else None,
            evaluation.get("method_version") if evaluation else None,
        )
        if evaluation and not provenance:
            status = "unpriced"
            evidence_blockers.append(
                f"{component_id}: method {evaluation.get('method_id')}@{evaluation.get('method_version')} is not approved"
            )
        calculated_range = evaluation.get("outputs") if evaluation and evaluation.get("status") == "valid" else {}
        kind = _input_kind(row)
        item = {
            "component_id": component_id, "label": row.get("label"), "kind": kind,
            "evidence_tier": row.get("evidence_tier"), "evidence": row.get("evidence"),
            "method": row.get("method"), "valuation_status": status,
        }
        buckets[kind + "s"].append(item)
        overlap_key = row.get("overlap_key") or component_id
        if row.get("treatment") == "additive" and overlap_key in overlap_seen:
            double_counting_flags.append(f"{component_id} overlaps additive component {overlap_seen[overlap_key]} via {overlap_key}")
        elif row.get("treatment") == "additive":
            overlap_seen[overlap_key] = component_id
        if row.get("treatment") == "additive" and status not in PRICED_STATUSES:
            evidence_blockers.append(f"{component_id}: material component is {status}; a valid calculation proof is required")
        if evaluation and evaluation.get("status") != "valid":
            evidence_blockers.extend(f"{component_id}: {message}" for message in evaluation.get("checks", {}).get("errors") or [])

        legacy_proof = old_proof.get(component_id) or {}
        record = {
            "component_id": component_id,
            "label": row.get("label"),
            "category": row.get("category"),
            "treatment": row.get("treatment"),
            "included_in_component_id": row.get("included_in_component_id"),
            "ownership_claim": legacy_proof.get("economic_claim") or row.get("label"),
            "ownership_percentage": ((row.get("driver_model") or {}).get("scenarios") or {}).get("base", {}).get("ownership_pct", 1.0),
            "quantity": legacy_proof.get("quantity"),
            "method": row.get("method"),
            "method_version": (row.get("calculation_proof") or {}).get("method_version"),
            "method_provenance": ({
                "method_id": provenance.get("method_id"),
                "version": provenance.get("version"),
                "label": provenance.get("label"),
                "power_zones": provenance.get("power_zones"),
                "equation": provenance.get("equation"),
                "sources": provenance.get("sources"),
            } if provenance else None),
            "comparable_ids": legacy_proof.get("comparable_ids") or [],
            "range_per_share": {case: calculated_range.get(case) for case in CASES},
            "legacy_range_per_share": proof_result.get("legacy_range_per_share"),
            "valuation_status": status,
            "calculation_proof": evaluation,
            "evidence_tier": row.get("evidence_tier"),
            "evidence_level": _standard_evidence_level(row),
            "evidence": row.get("evidence"),
            "scenario_assumptions": row.get("scenario_assumptions") or row.get("assumption_summary"),
            "probability_and_timing": legacy_proof.get("risk_and_timing"),
            "tax_and_realization_adjustments": legacy_proof.get("adjustment") or row.get("cross_check"),
            "falsifier": legacy_proof.get("falsifier") or row.get("falsifier"),
            "overlap_key": overlap_key,
            "assumption_type": kind,
        }
        records.append(record)
        evaluated_rows.append(record)

    proof_summary = proof_completeness(evaluated_rows)
    unvalued_count = sum(
        1 for row in evaluated_rows
        if row.get("treatment") == "additive" and row.get("valuation_status") not in PRICED_STATUSES
    )
    if not components:
        unvalued_count = 1
        evidence_blockers.append("A complete economic ownership map has not been supplied.")
    evidence_blockers.extend(validation_errors)
    evidence_blockers.extend(double_counting_flags)

    priced = _sum_priced([row for row in evaluated_rows if row.get("treatment") == "additive"])
    # Keep priced_components_per_share as the raw additive sum for audit.
    # Security value_per_share floors at 0 (limited liability of equity).
    total = floor_equity_value_range(priced, ndigits=4) if unvalued_count == 0 else {case: None for case in CASES}
    zero_value_policy = methodology.get("zero_value_policy") or {}
    zero_value_evidence_refs = (
        [str(ref).strip() for ref in (zero_value_policy.get("evidence_refs") or []) if str(ref).strip()]
        if isinstance(zero_value_policy, dict)
        else []
    )
    explicit_zero_value = (
        isinstance(zero_value_policy, dict)
        and zero_value_policy.get("allowed") is True
        and bool(str(zero_value_policy.get("rationale") or "").strip())
        and bool(zero_value_evidence_refs)
        and str(zero_value_policy.get("outcome") or "").lower()
        in {"wipeout", "liquidation_shortfall", "insolvent_equity", "no_recovery"}
    )
    base_value = total.get("base")
    if (
        unvalued_count == 0
        and base_value is not None
        and float(base_value) <= 0
        and not explicit_zero_value
    ):
        evidence_blockers.append(
            "Base equity value is zero or negative. Supply an explicit zero_value_policy "
            "with a supported terminal outcome, rationale, and evidence_refs before decision_grade."
        )
    legacy_total = (
        (data.get("legacy_component_valuation_snapshot") or {}).get("value_per_share")
        or ((result.get("total_equity_value_per_share") or {}) if result else {})
    )
    market_cap = float(price) * float(shares) / 1_000_000 if price is not None and shares else None
    debt = inputs.get("total_debt_m", inputs.get("debt_m"))
    cash = inputs.get("cash_m")
    enterprise_value = market_cap + float(debt or 0) - float(cash or 0) if market_cap is not None and (debt is not None or cash is not None) else None
    returns = {case: _annualized(total.get(case), price, years, distributions) for case in CASES}
    source_acceptance_errors = _source_acceptance_errors(
        str(data.get("ticker") or ""), data.get("as_of"), evaluated_rows
    )
    evidence_blockers.extend(source_acceptance_errors)
    extreme_return = (
        returns.get("base") is not None
        and abs(float(returns["base"])) >= EXTREME_RETURN_PCT
    )
    outlier_validation = methodology.get("outlier_validation") or {}
    extreme_return_validated = (
        not extreme_return
        or (
            isinstance(outlier_validation, dict)
            and outlier_validation.get("status") == "passed"
            and len(outlier_validation.get("independent_methods") or []) >= 1
            and bool(outlier_validation.get("evidence_refs"))
        )
    )
    if not extreme_return_validated:
        evidence_blockers.append(
            "Extreme annualized return requires independent validation with a "
            "second method and source-backed evidence."
        )
    top_drivers = sorted(({
        "component_id": row.get("component_id"), "label": row.get("label"),
        "valuation_status": row.get("valuation_status"),
        "base_per_share": row.get("range_per_share", {}).get("base"),
        "legacy_base_per_share": (row.get("legacy_range_per_share") or {}).get("base"),
        "range_width_per_share": (
            round(float(row["range_per_share"]["high"]) - float(row["range_per_share"]["low"]), 4)
            if row.get("range_per_share", {}).get("high") is not None and row.get("range_per_share", {}).get("low") is not None else None
        ),
        "scenario_assumptions": row.get("scenario_assumptions"),
    } for row in evaluated_rows if row.get("treatment") == "additive"), key=lambda x: abs(float(x.get("range_width_per_share") or 0)), reverse=True)
    source_lineage = []
    for row in records:
        for source in ((row.get("calculation_proof") or {}).get("source_lineage") or []):
            source_lineage.append({"component_id": row["component_id"], **source})

    contract = {
        "schema_version": "2.0",
        "status": "decision_grade" if not evidence_blockers and unvalued_count == 0 else "evidence_blocked",
        "ticker": data.get("ticker"),
        "as_of": data.get("as_of"),
        "economic_ownership_map": records,
        "component_coverage": {
            "all_material_components_identified": bool(result.get("all_material_components_identified")),
            "material_component_count": len(components),
            "additive_component_count": len(additive),
            "embedded_component_count": len(embedded),
            "unvalued_component_count": unvalued_count,
            "double_counting_flags": double_counting_flags,
        },
        "input_classification": buckets,
        "method_route": route,
        "market": {
            "price_per_share": price, "fully_diluted_shares": shares,
            "market_cap_m": round(market_cap, 2) if market_cap is not None else None,
            "enterprise_value_m": round(enterprise_value, 2) if enterprise_value is not None else None,
        },
        "valuation": {
            "value_per_share": total,
            "priced_components_per_share": priced,
            "legacy_value_per_share": legacy_total or None,
            "probability_weighted_value_per_share": total.get("base"),
            "expected_distributions_per_share": distributions,
            "annualized_return_at_price_pct": returns,
            "downside_to_low_pct": round((float(total["low"]) / float(price) - 1) * 100, 2) if price and total.get("low") is not None else None,
            "horizon_years": years,
            "equity_liability_floor": 0.0,
            "interpretation": (
                "value_per_share is withheld while any material additive component is unpriced; "
                "priced_components_per_share is the raw additive sum (may be negative). "
                "When complete, value_per_share applies a 0 floor (limited liability)."
            ),
        },
        "scenario_contract": {
            "rule": "Cases must change cited causal operating, capital, probability, timing, or financing drivers—not only a terminal multiple.",
            "top_value_drivers": top_drivers[:5],
            "reverse_expectations": (data.get("valuation_views") or {}).get("reverse_expectations") or data.get("reverse_expectations"),
        },
        "calculation_proof_summary": proof_summary,
        "source_lineage": source_lineage,
        "model_checks": {
            "calculation_graphs_valid": not proof_summary.get("calculation_errors"),
            "component_sum_reconciles": unvalued_count == 0,
            "no_double_counting": not double_counting_flags,
            "all_material_components_priced": unvalued_count == 0,
            "positive_base_or_explicit_zero_value": (
                base_value is not None and (float(base_value) > 0 or explicit_zero_value)
            ),
            "low_base_high_ordered": all(
                row.get("range_per_share", {}).get("low") is None
                or row["range_per_share"]["low"] <= row["range_per_share"]["base"] <= row["range_per_share"]["high"]
                for row in records
            ),
            "source_identity_and_freshness_valid": not source_acceptance_errors,
            "extreme_return_validated": extreme_return_validated,
        },
        "evidence": {
            "unresolved_count": len(set(evidence_blockers)),
            "blockers": sorted(set(evidence_blockers)),
            "validation_errors": validation_errors,
        },
        "monitoring": {
            "falsifiers": [row["falsifier"] for row in records if row.get("falsifier")],
            "required_refresh_triggers": ["new filing or material operating update", "capital-structure change", "material price move", "component milestone or falsifier"],
        },
        "change_control": {
            "model_hash": None,
            "method_versions": sorted({f"{row.get('method')}@{row.get('method_version')}" for row in records if row.get("method_version")}),
            "change_log": data.get("valuation_change_log") or [],
            "rule": "A source fact is locked. Every assumption change requires a reason, author, timestamp, and before/after value.",
        },
        "decision_rule": "No security is decision-grade until every material claim is valued exactly once by a valid calculation proof and every material evidence blocker is resolved.",
    }
    contract["change_control"]["model_hash"] = canonical_hash({k: v for k, v in contract.items() if k != "change_control"})
    data["universal_valuation_contract"] = contract
    return contract


def strict_contract_errors(data: dict) -> list[str]:
    contract = data.get("universal_valuation_contract") or build_universal_valuation_contract(data)
    errors = list((contract.get("evidence") or {}).get("validation_errors") or [])
    errors.extend((contract.get("calculation_proof_summary") or {}).get("calculation_errors") or [])
    if (contract.get("component_coverage") or {}).get("unvalued_component_count"):
        errors.append("unvalued_component_count must equal zero")
    if (contract.get("component_coverage") or {}).get("double_counting_flags"):
        errors.append("double-counting flags remain open")
    if not (contract.get("model_checks") or {}).get("component_sum_reconciles"):
        errors.append("component sum does not reconcile to a complete security value")
    if not (contract.get("model_checks") or {}).get("positive_base_or_explicit_zero_value"):
        errors.append(
            "base equity value must be positive unless an explicit source-backed "
            "zero-value policy is present"
        )
    return sorted(set(errors))
