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
OUTPUT_BASES = {
    "present_value_today",
    "future_payoff",
    "forward_cashflow_schedule",
}
MODEL_LEVELS = {
    "unmodeled",
    "evidence_blocked",
    "screening_grade",
    "stock_specific",
    "committee_reviewed",
    "owner_approved",
}


def _null_range() -> dict:
    return {case: None for case in CASES}


def _basis_name(value) -> str | None:
    if isinstance(value, dict):
        value = value.get("type") or value.get("basis") or value.get("output_basis")
    value = str(value or "").strip().lower()
    return value if value in OUTPUT_BASES else None


def _resolve_output_basis(methodology: dict, components: list[dict]) -> tuple[str, str, list[str]]:
    """Resolve one security-level basis and reject mixed, implicit economics.

    Existing method cards are present-value methods.  That safe default keeps
    their intrinsic values usable while preventing the old PV/price gap from
    being annualized.  Future-payoff and cash-flow models must declare their
    basis explicitly in the component proof (and, when supplied, agree with
    the top-level methodology declaration).
    """
    errors: list[str] = []
    top_raw = methodology.get("output_basis")
    top_basis = _basis_name(top_raw)
    if top_raw is not None and top_basis is None:
        errors.append(
            "valuation_methodology.output_basis must be one of "
            + ", ".join(sorted(OUTPUT_BASES))
        )
    declared: list[tuple[str, str]] = []
    for row in components:
        component_id = str(row.get("id") or row.get("component_id") or "component")
        proof = row.get("calculation_proof") or {}
        method = approved_method(proof.get("method_id"), proof.get("method_version")) or {}
        proof_raw = proof.get("output_basis")
        row_raw = row.get("output_basis")
        method_raw = method.get("output_basis")
        raw = proof_raw if proof_raw is not None else row_raw
        if raw is None:
            raw = method_raw
        basis = _basis_name(raw)
        if raw is not None and basis is None:
            errors.append(
                f"{component_id}: output_basis must be one of "
                + ", ".join(sorted(OUTPUT_BASES))
            )
        if basis:
            declared.append((component_id, basis))
        explicit_component_basis = _basis_name(
            proof_raw if proof_raw is not None else row_raw
        )
        method_basis = _basis_name(method_raw)
        if (
            explicit_component_basis
            and method_basis
            and explicit_component_basis != method_basis
        ):
            errors.append(
                f"{component_id}: explicit output_basis {explicit_component_basis} "
                f"conflicts with approved method-card basis {method_basis}"
            )
    bases = {basis for _component_id, basis in declared}
    resolved = top_basis or (next(iter(bases)) if len(bases) == 1 else None)
    if len(bases) > 1:
        errors.append(
            "Additive component outputs mix incompatible bases: "
            + ", ".join(f"{component_id}={basis}" for component_id, basis in declared)
        )
    if resolved and top_basis:
        for component_id, basis in declared:
            if basis != top_basis:
                errors.append(
                    f"{component_id}: component output_basis {basis} conflicts with contract basis {top_basis}"
                )
    if resolved:
        status = "explicit" if top_basis else "method_declared"
        return resolved, status, errors
    if errors:
        return "present_value_today", "invalid_defaulted_to_present_value", errors
    return "present_value_today", "defaulted_for_legacy_safety", errors


def _legacy_annualized_value_gap(
    value: float | None,
    price: float | None,
    years: int,
    distributions: float = 0,
) -> float | None:
    """Former PV/price annualization retained only as a non-actionable audit."""
    if value is None or price is None or price <= 0 or years <= 0 or value + distributions <= 0:
        return None
    result = ((float(value) + distributions) / float(price)) ** (1 / years) - 1
    return round(result * 100, 2) if isfinite(result) else None


def _annualized_future_payoff(
    payoff: float | None,
    price: float | None,
    years: float | None,
) -> float | None:
    if payoff is None or price is None or years is None:
        return None
    try:
        payoff_value = float(payoff)
        price_value = float(price)
        years_value = float(years)
    except (TypeError, ValueError):
        return None
    if payoff_value <= 0 or price_value <= 0 or years_value <= 0:
        return None
    result = (payoff_value / price_value) ** (1.0 / years_value) - 1.0
    return round(result * 100, 2) if isfinite(result) else None


def _year_fraction(as_of: str | None, future_date: str | None) -> float | None:
    try:
        start = date.fromisoformat(str(as_of)[:10])
        end = date.fromisoformat(str(future_date)[:10])
    except (TypeError, ValueError):
        return None
    days = (end - start).days
    return round(days / 365.25, 8) if days > 0 else None


def normalize_forward_cashflow_schedule(raw, as_of: str | None) -> tuple[dict, list[str]]:
    """Normalize low/base/high dated per-share cash flows for IRR and NPV."""
    errors: list[str] = []
    schedule = {case: [] for case in CASES}
    if not isinstance(raw, dict):
        return schedule, [
            "forward_cashflow_schedule requires low/base/high per-share cash-flow arrays"
        ]
    for case in CASES:
        rows = raw.get(case)
        if not isinstance(rows, list) or not rows:
            errors.append(f"forward_cashflow_schedule.{case} must contain at least one dated cash flow")
            continue
        positive = False
        normalized = []
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                errors.append(f"forward_cashflow_schedule.{case}[{index}] must be an object")
                continue
            amount = row.get("amount_per_share", row.get("amount"))
            try:
                amount_value = float(amount)
            except (TypeError, ValueError):
                errors.append(
                    f"forward_cashflow_schedule.{case}[{index}].amount_per_share must be numeric"
                )
                continue
            if not isfinite(amount_value):
                errors.append(
                    f"forward_cashflow_schedule.{case}[{index}].amount_per_share must be finite"
                )
                continue
            year = row.get("year", row.get("years_from_as_of"))
            try:
                year_value = float(year) if year is not None else None
            except (TypeError, ValueError):
                year_value = None
            if (year_value is None or year_value <= 0) and row.get("date"):
                year_value = _year_fraction(as_of, row.get("date"))
            if year_value is None or year_value <= 0:
                errors.append(
                    f"forward_cashflow_schedule.{case}[{index}] requires a positive future year or date"
                )
                continue
            positive = positive or amount_value > 0
            normalized.append({
                "year": round(year_value, 8),
                "date": str(row.get("date"))[:10] if row.get("date") else None,
                "amount_per_share": round(amount_value, 8),
                "label": row.get("label"),
            })
        normalized.sort(key=lambda item: item["year"])
        schedule[case] = normalized
        if normalized and not positive:
            errors.append(f"forward_cashflow_schedule.{case} must contain a positive cash flow")
    return schedule, errors


def _npv(rate: float, cashflows: list[dict]) -> float:
    return sum(
        float(row["amount_per_share"]) / ((1.0 + rate) ** float(row["year"]))
        for row in cashflows
    )


def _cashflow_irr(price: float | None, cashflows: list[dict]) -> float | None:
    try:
        price_value = float(price)
    except (TypeError, ValueError):
        return None
    if price_value <= 0 or not cashflows:
        return None
    signs = [-1]
    signs.extend(
        1 if float(row["amount_per_share"]) > 0 else -1
        for row in cashflows
        if float(row["amount_per_share"]) != 0
    )
    if sum(1 for left, right in zip(signs, signs[1:]) if left != right) != 1:
        return None

    def value(rate: float) -> float:
        return -price_value + _npv(rate, cashflows)

    low, high = -0.999999, 1.0
    low_value, high_value = value(low), value(high)
    while low_value * high_value > 0 and high < 1_000:
        high *= 2
        high_value = value(high)
    if low_value * high_value > 0:
        return None
    for _ in range(240):
        mid = (low + high) / 2
        mid_value = value(mid)
        if abs(mid_value) < 1e-12:
            low = high = mid
            break
        if low_value * mid_value <= 0:
            high = mid
            high_value = mid_value
        else:
            low = mid
            low_value = mid_value
    result = (low + high) / 2
    return round(result * 100, 2) if isfinite(result) else None


def entry_price_for_contract_valuation(
    valuation: dict,
    case: str,
    hurdle: float,
) -> float | None:
    """Compute a hurdle entry only from dated future economics."""
    if case not in CASES or hurdle <= -1:
        return None
    basis = _basis_name(valuation.get("output_basis")) or "present_value_today"
    if basis == "present_value_today":
        return None
    if basis == "future_payoff":
        payoff = (valuation.get("future_payoff_per_share") or {}).get(case)
        years = valuation.get("future_payoff_horizon_years")
        try:
            if payoff is None or years is None or float(years) <= 0:
                return None
            result = float(payoff) / ((1.0 + hurdle) ** float(years))
        except (TypeError, ValueError):
            return None
        return round(result, 4) if isfinite(result) else None
    rows = (valuation.get("forward_cashflow_schedule") or {}).get(case) or []
    if not rows:
        return None
    result = _npv(hurdle, rows)
    return round(result, 4) if isfinite(result) else None


def _normalize_pct(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not isfinite(number) or number < 0:
        return None
    return round(number * 100, 4) if number <= 1 else round(number, 4)


def _required_return_pct(methodology: dict, rows: list[dict]) -> float | None:
    raw = methodology.get("required_return_pct")
    if raw is None:
        raw = methodology.get("required_return")
    direct = _normalize_pct(raw)
    if direct is not None:
        return direct
    candidates = []
    for row in rows:
        proof = row.get("calculation_proof") or {}
        for assumption in proof.get("assumptions") or []:
            if str(assumption.get("id") or "").lower() not in {
                "discount_rate", "required_return", "cost_of_equity",
            }:
                continue
            value = assumption.get("value")
            if value is None:
                values = assumption.get("values") or {}
                value = values.get("base")
            normalized = _normalize_pct(value)
            if normalized is not None:
                candidates.append(normalized)
    unique = sorted(set(candidates))
    return unique[0] if len(unique) == 1 else None


def _margin_of_safety(value: float | None, price: float | None) -> float | None:
    try:
        intrinsic, quote = float(value), float(price)
    except (TypeError, ValueError):
        return None
    if intrinsic <= 0 or quote < 0:
        return None
    return round((intrinsic - quote) / intrinsic * 100, 2)


def _upside_to_value(value: float | None, price: float | None) -> float | None:
    try:
        intrinsic, quote = float(value), float(price)
    except (TypeError, ValueError):
        return None
    if quote <= 0:
        return None
    return round((intrinsic / quote - 1.0) * 100, 2)


def _is_automated_generic_screen(valuation: dict, components: list[dict]) -> bool:
    methodology = valuation.get("valuation_methodology") or {}
    if methodology.get("automation") != "source_locked_first_pass":
        return False
    additive = [row for row in components if row.get("treatment") == "additive"]
    if len(additive) != 1:
        return False
    row = additive[0]
    return (
        str(row.get("id") or row.get("component_id")) == "operating_business_and_net_assets"
        and row.get("method") == "owner_earnings_reinvestment_dcf"
    )


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
    output_basis, output_basis_status, basis_errors = _resolve_output_basis(
        methodology, additive
    )
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
            "Market price per share is missing or non-positive; cannot mark decision_grade or compare value with price."
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
                "output_basis": provenance.get("output_basis"),
                "power_zones": provenance.get("power_zones"),
                "equation": provenance.get("equation"),
                "sources": provenance.get("sources"),
            } if provenance else None),
            "comparable_ids": legacy_proof.get("comparable_ids") or [],
            "range_per_share": {case: calculated_range.get(case) for case in CASES},
            "output_basis": (
                _basis_name((row.get("calculation_proof") or {}).get("output_basis"))
                or _basis_name(row.get("output_basis"))
                or _basis_name((provenance or {}).get("output_basis"))
                or output_basis
            ),
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

    # Embedded rows disclose sensitivities that are already captured inside an
    # additive component.  They must not make the proof summary disagree with
    # component coverage: only additive rows contribute independent value to
    # the security total and therefore require standalone calculation proof.
    additive_rows = [row for row in evaluated_rows if row.get("treatment") == "additive"]
    proof_summary = proof_completeness(additive_rows)
    unvalued_count = sum(
        1 for row in evaluated_rows
        if row.get("treatment") == "additive" and row.get("valuation_status") not in PRICED_STATUSES
    )
    if not components:
        unvalued_count = 1
        evidence_blockers.append("A complete economic ownership map has not been supplied.")
    evidence_blockers.extend(validation_errors)
    evidence_blockers.extend(double_counting_flags)
    evidence_blockers.extend(basis_errors)

    priced = _sum_priced(additive_rows)
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
    required_return_pct = _required_return_pct(methodology, components)
    basis_config = methodology.get("output_basis")
    basis_config = basis_config if isinstance(basis_config, dict) else {}
    future_payoff_date = (
        basis_config.get("payoff_date")
        or methodology.get("future_payoff_date")
    )
    payoff_years = _year_fraction(data.get("as_of"), future_payoff_date)
    if payoff_years is None:
        explicit_years = (
            basis_config.get("horizon_years")
            or methodology.get("future_payoff_horizon_years")
            or methodology.get("horizon_years")
            or data.get("lawrence_horizon_years")
        )
        try:
            payoff_years = float(explicit_years) if explicit_years is not None else None
        except (TypeError, ValueError):
            payoff_years = None

    schedule = {case: [] for case in CASES}
    semantic_errors: list[str] = []
    if output_basis == "forward_cashflow_schedule":
        raw_schedule = (
            basis_config.get("cashflows")
            or basis_config.get("forward_cashflow_schedule")
            or methodology.get("forward_cashflow_schedule")
            or methodology.get("forward_cashflow_schedule_per_share")
        )
        schedule, schedule_errors = normalize_forward_cashflow_schedule(
            raw_schedule, data.get("as_of")
        )
        semantic_errors.extend(schedule_errors)
    elif output_basis == "future_payoff" and not (payoff_years and payoff_years > 0):
        semantic_errors.append(
            "future_payoff output_basis requires a positive explicit horizon_years or a payoff_date after as_of"
        )

    output_range = dict(total)
    present_value_today = _null_range()
    future_payoff = _null_range()
    if output_basis == "present_value_today":
        present_value_today = dict(total)
    elif output_basis == "future_payoff":
        future_payoff = dict(total)
        if required_return_pct is None:
            semantic_errors.append(
                "future_payoff output_basis requires required_return_pct to derive intrinsic value today"
            )
        elif payoff_years and payoff_years > 0:
            rate = required_return_pct / 100.0
            discounted = {
                case: (
                    round(float(total[case]) / ((1.0 + rate) ** payoff_years), 4)
                    if total.get(case) is not None else None
                )
                for case in CASES
            }
            present_value_today = floor_equity_value_range(discounted, ndigits=4)
    else:
        if required_return_pct is None:
            semantic_errors.append(
                "forward_cashflow_schedule output_basis requires required_return_pct to derive intrinsic value today"
            )
        elif not semantic_errors:
            rate = required_return_pct / 100.0
            discounted = {
                case: round(_npv(rate, schedule.get(case) or []), 4)
                for case in CASES
            }
            present_value_today = floor_equity_value_range(discounted, ndigits=4)

    if output_basis == "future_payoff" and payoff_years and payoff_years > 0:
        forward_returns = {
            case: _annualized_future_payoff(total.get(case), price, payoff_years)
            for case in CASES
        }
        forward_return_reason = "dated_future_payoff"
    elif output_basis == "forward_cashflow_schedule" and not semantic_errors:
        forward_returns = {
            case: _cashflow_irr(price, schedule.get(case) or []) for case in CASES
        }
        forward_return_reason = "dated_forward_cashflow_schedule"
    else:
        forward_returns = _null_range()
        forward_return_reason = (
            "present_value_today cannot be annualized as a future payoff"
            if output_basis == "present_value_today"
            else "dated forward economics are incomplete"
        )
    forward_return_status = (
        "available"
        if all(forward_returns.get(case) is not None for case in CASES)
        else "withheld"
    )
    if output_basis in {"future_payoff", "forward_cashflow_schedule"} and forward_return_status != "available":
        semantic_errors.append(
            "forward return is not uniquely computable for every scenario from the supplied dated economics"
        )

    margins = {
        case: _margin_of_safety(present_value_today.get(case), price) for case in CASES
    }
    upside_to_value = {
        case: _upside_to_value(present_value_today.get(case), price) for case in CASES
    }
    legacy_returns = {
        case: _legacy_annualized_value_gap(total.get(case), price, years, distributions)
        for case in CASES
    }
    evidence_blockers.extend(semantic_errors)
    source_acceptance_errors = _source_acceptance_errors(
        str(data.get("ticker") or ""), data.get("as_of"), evaluated_rows
    )
    evidence_blockers.extend(source_acceptance_errors)
    extreme_return = (
        forward_returns.get("base") is not None
        and abs(float(forward_returns["base"])) >= EXTREME_RETURN_PCT
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

    proof_status = (
        "decision_grade"
        if not evidence_blockers and unvalued_count == 0
        else "evidence_blocked"
    )
    requested_model_level = str(methodology.get("model_level") or "").strip().lower()
    if not components:
        model_level = "unmodeled"
        model_level_reason = "No completed economic ownership model exists."
    elif proof_status != "decision_grade":
        model_level = "evidence_blocked"
        model_level_reason = "Required evidence, calculation, or component coverage remains open."
    elif _is_automated_generic_screen(data, components):
        model_level = "screening_grade"
        model_level_reason = (
            "The source-locked automated owner-earnings template uses generic assumption bounds; "
            "it is useful for triage but is not stock-specific underwriting."
        )
    elif requested_model_level in {"screening_grade", "stock_specific"}:
        model_level = requested_model_level
        model_level_reason = "Valuation methodology explicitly declares this reviewed maturity level."
    else:
        model_level = "stock_specific"
        model_level_reason = "The proof-complete model uses stock-specific components and assumptions."
    committee_eligible = proof_status == "decision_grade" and model_level == "stock_specific"
    fact_dates = sorted({
        str(row.get("as_of"))[:10]
        for row in source_lineage
        if row.get("as_of")
    })
    dates = {
        "model_as_of": str(data.get("as_of") or "")[:10] or None,
        "latest_fact_as_of": fact_dates[-1] if fact_dates else None,
        "oldest_fact_as_of": fact_dates[0] if fact_dates else None,
        "price_as_of": str(inputs.get("price_as_of") or "")[:10] or None,
    }
    legacy_audit = {
        "actionable": False,
        "status": "audit_only",
        "annualized_return_at_price_pct": legacy_returns,
        "formula": "((present_value_or_output + undated_distributions) / price) ** (1 / horizon_years) - 1",
        "reason_non_actionable": (
            "This legacy calculation treated a present value as a future payoff and cannot be used "
            "as a forward return, hurdle entry price, ranking signal, or capital decision."
        ),
    }

    contract = {
        "schema_version": "3.0",
        "status": proof_status,
        "proof_status": proof_status,
        "model_level": model_level,
        "model_level_reason": model_level_reason,
        "decision_eligibility": {
            "committee_eligible": committee_eligible,
            "capital_actionable": False,
            "capital_authority_required": "human_decision",
            "reason": (
                "Stock-specific proof is eligible for independent committee review."
                if committee_eligible
                else "Model must be stock-specific and evidence-clear before committee review."
            ),
        },
        "ticker": data.get("ticker"),
        "as_of": data.get("as_of"),
        "dates": dates,
        "legacy_audit": legacy_audit,
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
            "price_source": inputs.get("price_source"),
            "price_as_of": inputs.get("price_as_of"),
        },
        "valuation": {
            "output_basis": output_basis,
            "output_basis_status": output_basis_status,
            "output_range_per_share": output_range,
            "value_per_share": present_value_today,
            "present_value_today_per_share": present_value_today,
            "future_payoff_per_share": future_payoff,
            "future_payoff_date": str(future_payoff_date)[:10] if future_payoff_date else None,
            "future_payoff_horizon_years": (
                round(float(payoff_years), 8)
                if output_basis == "future_payoff" and payoff_years is not None
                else None
            ),
            "forward_cashflow_schedule": (
                schedule if output_basis == "forward_cashflow_schedule" else None
            ),
            "priced_components_per_share": priced,
            "legacy_value_per_share": legacy_total or None,
            "probability_weighted_value_per_share": present_value_today.get("base"),
            "expected_distributions_per_share": distributions,
            "forward_return_at_price_pct": forward_returns,
            "forward_return_status": forward_return_status,
            "forward_return_reason": forward_return_reason,
            "annualized_return_at_price_pct": forward_returns,
            "annualized_return_field_status": "compatibility_alias_of_forward_return",
            "required_return_pct": required_return_pct,
            "margin_of_safety_pct": margins,
            "margin_of_safety_definition": (
                "(intrinsic_value_today - market_price) / intrinsic_value_today; "
                "positive means the quote is below intrinsic value"
            ),
            "upside_to_value_pct": upside_to_value,
            "downside_to_low_pct": upside_to_value.get("low"),
            "horizon_years": years,
            "equity_liability_floor": 0.0,
            "interpretation": (
                "output_basis states what the proof produced. value_per_share and "
                "present_value_today_per_share are intrinsic values today and are withheld while "
                "any material additive component is unpriced or dated future economics cannot be "
                "discounted at an explicit required return. priced_components_per_share is the raw "
                "proof-output sum. A present value is never annualized or discounted again."
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
            "output_basis_valid": not basis_errors,
            "dated_forward_economics_valid": not semantic_errors,
            "present_value_is_not_treated_as_future_payoff": (
                output_basis != "present_value_today"
                or forward_return_status == "withheld"
            ),
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
        "decision_rule": (
            "Proof status and investment readiness are separate. Every material claim must be valued "
            "exactly once by a valid calculation proof, every evidence blocker must be resolved, and "
            "the model must be stock-specific before committee review. Only a human decision can "
            "authorize capital."
        ),
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
    if not (contract.get("model_checks") or {}).get("output_basis_valid"):
        errors.append("valuation output basis is invalid or mixed across additive components")
    if not (contract.get("model_checks") or {}).get("dated_forward_economics_valid"):
        errors.append("dated future payoff/cash-flow economics are incomplete or invalid")
    return sorted(set(errors))
