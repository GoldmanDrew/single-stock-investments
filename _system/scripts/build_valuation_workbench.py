#!/usr/bin/env python3
"""Build truthful, reusable valuation follow-up views for any security."""
from __future__ import annotations

import argparse
import calendar
import json
import re
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

from universal_valuation_contract import build_universal_valuation_contract
from valuation_method_router import route_valuation

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "_system" / "reference" / "valuation_followups.json"
LEDGER = ROOT / "_system" / "research" / "committee_outcomes.jsonl"
CALIBRATION = ROOT / "_system" / "research" / "committee_calibration.json"
PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
MODEL_LEVELS = (
    "unmodeled",
    "evidence_blocked",
    "screening_grade",
    "stock_specific",
    "committee_reviewed",
    "owner_approved",
)
RETURN_PUBLISHABLE_LEVELS = {
    "stock_specific", "committee_reviewed", "owner_approved",
}
COMMITTEE_REVIEWED_STATES = {"owner_decision_pending", "outcome_tracking"}


def is_automated_generic_screen(valuation: dict) -> bool:
    methodology = valuation.get("valuation_methodology") or {}
    if methodology.get("automation") != "source_locked_first_pass":
        return False
    result = valuation.get("component_valuation_results") or {}
    additive = [
        row for row in (result.get("additive_components") or [])
        if row.get("treatment") == "additive"
    ]
    return (
        len(additive) == 1
        and str(additive[0].get("id") or additive[0].get("component_id"))
        == "operating_business_and_net_assets"
        and additive[0].get("method") == "owner_earnings_reinvestment_dcf"
    )


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {} if default is None else default


def add_months(value: str, months: int) -> str:
    source = date.fromisoformat(value[:10])
    month_index = source.month - 1 + months
    year = source.year + month_index // 12
    month = month_index % 12 + 1
    day = min(source.day, calendar.monthrange(year, month)[1])
    return date(year, month, day).isoformat()


def latest_committee_record(research: Path) -> tuple[Path | None, dict]:
    paths = sorted(research.glob("committee_????-??-??.json"))
    return (paths[-1], read_json(paths[-1])) if paths else (None, {})


def authoritative_owner_decision(research: Path, record: dict) -> dict:
    """Standalone signed owner decision wins; embedded decision is legacy."""
    standalone = read_json(research / "human_decision.json")
    if standalone.get("status") == "decided" and standalone.get("decision"):
        return standalone
    return record.get("human_decision") or {}


def committee_view(research: Path) -> dict:
    manifests = sorted(research.glob("committee_work/????-??-??/manifest.json"))
    manifest_path = manifests[-1] if manifests else None
    manifest = read_json(manifest_path) if manifest_path else {}
    work = manifest_path.parent if manifest_path else None
    raters = manifest.get("selected_raters") or []
    required = []
    for round_number in (1, 2):
        required.extend(f"round_{round_number}/{row.get('persona')}.json" for row in raters if row.get("persona"))
    required.extend([
        "proposer.json", "pre_mortem.json", "evidence_tribunal.json", "research_response.json",
        "valuation_reconciliation.json", "adversarial_review.json", "chair_synthesis.json",
    ])
    completed = [name for name in required if work and (work / name).exists()]
    missing = [name for name in required if name not in completed]
    record_path, record = latest_committee_record(research)
    record_date = str((record.get("review") or {}).get("as_of") or "")[:10]
    manifest_date = str(manifest.get("as_of") or "")[:10]
    record_is_current = bool(record) and (not manifest_date or record_date >= manifest_date)
    active_record = record if record_is_current else {}
    owner = authoritative_owner_decision(research, active_record)
    stage = str(manifest.get("stage") or "").lower()
    if owner.get("status") in {"complete", "decided"} and owner.get("decision"):
        status = "outcome_tracking"
        next_action = "Measure the recorded decision at each due 6-, 12-, and 24-month horizon."
    elif stage == "parked":
        # Without this branch a parked committee fell through to
        # independent_review_open, and this derived file then shadowed its own
        # source: every reader of the workbench saw an open review, and
        # run_security_decision_pipeline read the same status back and opened a
        # second committee over the held votes.
        parked = manifest.get("parked") or {}
        held = parked.get("votes_landed")
        status = "parked"
        next_action = (
            f"Committee parked ({parked.get('reason') or 'unknown'})"
            + (f" holding {held} vote(s)" if held else "")
            + ". Resume or discard it with select_committee_work.py --unpark "
            f"{str(manifest.get('ticker') or '').upper()} --unpark-date {manifest.get('as_of')} "
            "--unpark-mode resume|discard; nothing automatic will."
        )
    elif stage == "evidence_blocked":
        status = "evidence_blocked"
        next_action = "Close the committee's primary-evidence blockers before requesting an owner decision."
    elif active_record:
        status = "owner_decision_pending"
        next_action = "Owner records decision, sizing, and a direct response to the strongest dissent."
    elif required and not missing:
        status = "ready_to_assemble"
        next_action = "Validate and assemble the independent rounds, then route the synthesis to the owner."
    elif manifest:
        status = "independent_review_open"
        next_action = "Complete isolated rater outputs, proposer case, pre-mortem, and research response without sharing peer votes."
    else:
        status = "not_started"
        next_action = "Freeze the evidence packet and select three method-independent raters."
    return {
        "status": status,
        "as_of": manifest.get("as_of") or (active_record.get("review") or {}).get("as_of"),
        "packet_hash": manifest.get("packet_hash"),
        "stage": manifest.get("stage"),
        "parked": manifest.get("parked"),
        "selected_raters": [row.get("persona") for row in raters if row.get("persona")],
        "analysis_progress": {"completed": len(completed), "required": len(required)},
        "completed_outputs": completed,
        "missing_outputs": missing,
        "owner_status": owner.get("status") or "pending",
        "owner_decision": owner.get("decision"),
        "strongest_dissent": (active_record.get("synthesis") or {}).get("strongest_dissent"),
        # A superseded assembled record remains visible as previous_record_ref,
        # but its unresolved list must not shadow the fresh hash-bound review.
        # Those questions survive in committee_gap_carryforward.json inside the
        # new packet and are adjudicated there; they are not current findings.
        "unresolved_items": (active_record.get("synthesis") or {}).get("unresolved_items") or [],
        "next_action": next_action,
        "record_ref": record_path.relative_to(ROOT).as_posix() if record_path and record_is_current else None,
        "previous_record_ref": record_path.relative_to(ROOT).as_posix() if record_path and not record_is_current else None,
        "manifest_ref": manifest_path.relative_to(ROOT).as_posix() if manifest_path else None,
    }


def proof_map(valuation: dict) -> dict[str, dict]:
    return {
        str(row.get("component_id")): row
        for row in (valuation.get("economic_value_analysis") or {}).get("valuation_proof") or []
        if row.get("component_id")
    }


def evidence_view(ticker_cfg: dict, valuation: dict, committee: dict) -> dict:
    proof = proof_map(valuation)
    gaps = []
    for source in ticker_cfg.get("evidence_gaps") or []:
        row = dict(source)
        exposures = []
        methods = []
        for component_id in row.get("component_ids") or []:
            claim = proof.get(component_id) or {}
            base = (claim.get("range_per_share") or {}).get("base")
            if base is not None:
                exposures.append(float(base))
            if claim.get("method"):
                methods.append(claim["method"])
        row["base_value_exposure_per_share"] = round(sum(exposures), 2) if exposures else None
        row["current_methods"] = sorted(set(methods))
        row["source"] = "curated_followup"
        gaps.append(row)
    known_questions = {str(row.get("question", "")).strip().lower() for row in gaps}
    for index, item in enumerate(committee.get("unresolved_items") or [], 1):
        if str(item).strip().lower() in known_questions:
            continue
        gaps.append({
            "id": f"committee_unresolved_{index}",
            "priority": "high",
            "component_ids": [],
            "question": item,
            "evidence_required": "Resolve the committee's missing fact with primary evidence and update the affected valuation proof row.",
            "acceptance_test": "The committee item is explicitly closed, sourced, and reflected in the valuation range or documented as immaterial.",
            "valuation_effect": "Pending committee assessment.",
            "status": "open",
            "base_value_exposure_per_share": None,
            "current_methods": [],
            "source": "committee",
        })
    for index, error in enumerate((valuation.get("economic_value_analysis") or {}).get("validation_errors") or [], 1):
        gaps.append({
            "id": f"economic_validation_{index}", "priority": "critical", "component_ids": [],
            "question": error, "evidence_required": "Repair the economic-value contract and rerun strict validation.",
            "acceptance_test": "The economic-value validator reports complete with no validation errors.",
            "valuation_effect": "Blocks decision-grade valuation.", "status": "open",
            "base_value_exposure_per_share": None, "current_methods": [], "source": "validator",
        })
    gaps.sort(key=lambda row: (PRIORITY_ORDER.get(row.get("priority"), 9), row.get("id", "")))
    closed = {"resolved", "accepted", "not_applicable", "met"}
    open_gaps = [row for row in gaps if row.get("status") not in closed]
    critical = sum(row.get("priority") == "critical" for row in open_gaps)
    return {
        "status": "critical_gaps_open" if critical else ("gaps_open" if open_gaps else "clear"),
        "open_count": len(open_gaps),
        "critical_count": critical,
        "gaps": open_gaps,
    }


def method_fit_view(config: dict, ticker_cfg: dict, valuation: dict) -> dict:
    archetype = (valuation.get("classification_inputs") or {}).get("archetype")
    profile_id = ticker_cfg.get("method_profile") or (config.get("archetype_profile_map") or {}).get(archetype) or "unclassified"
    profile = (config.get("method_profiles") or {}).get(profile_id) or {}
    route = route_valuation(valuation, profile_id) if profile_id != "unclassified" else (valuation.get("valuation_method_route") or route_valuation(valuation))
    return {
        "profile_id": route.get("profile_id") or profile_id,
        "label": route.get("label") or profile.get("label") or profile_id.replace("_", " ").title(),
        "current_archetype": archetype,
        "primary_methods": route.get("primary_methods") or [],
        "corroborating_methods": route.get("corroborating_methods") or [],
        "primary_personas": route.get("primary_personas") or profile.get("primary_personas") or [],
        "cross_check_personas": route.get("cross_check_personas") or profile.get("cross_check_personas") or [],
        "silent_personas": route.get("silent_personas") or [],
        "routing_reasons": route.get("reasons") or [],
        "required_evidence": route.get("required_evidence") or [],
        "applicability_tests": profile.get("applicability_tests") or [],
        "failure_modes": route.get("failure_modes") or profile.get("failure_modes") or [],
        "validation_cohort": config.get("validation_cohort") or [],
        "rule": route.get("decision_rule") or "Use the universal economic-value contract for every security; change the primary method and raters only when the applicability tests support it.",
    }


def decision_view(valuation: dict, committee: dict) -> dict:
    contract = valuation.get("universal_valuation_contract") or build_universal_valuation_contract(valuation)
    contract_valuation = contract.get("valuation") or {}
    values = contract_valuation.get("present_value_today_per_share") or contract_valuation.get("value_per_share") or {}
    forward_returns = contract_valuation.get("forward_return_at_price_pct") or {}
    model_level = str(contract.get("model_level") or "").lower()
    if model_level not in MODEL_LEVELS:
        model_level = "stock_specific" if contract.get("status") == "decision_grade" else "evidence_blocked"
    if contract.get("status") == "decision_grade" and is_automated_generic_screen(valuation):
        model_level = "screening_grade"
    if model_level not in {"unmodeled", "evidence_blocked", "screening_grade"}:
        if committee.get("owner_decision"):
            model_level = "owner_approved"
        elif committee.get("status") in COMMITTEE_REVIEWED_STATES and committee.get("record_ref"):
            model_level = "committee_reviewed"
        else:
            model_level = "stock_specific"
    return_publishable = (
        contract.get("status") == "decision_grade"
        and model_level in RETURN_PUBLISHABLE_LEVELS
        and contract_valuation.get("forward_return_status") == "available"
    )
    published_returns = forward_returns if return_publishable else {case: None for case in ("low", "base", "high")}
    return {
        "status": contract.get("status"),
        "proof_status": contract.get("proof_status") or contract.get("status"),
        "model_level": model_level,
        "model_level_reason": contract.get("model_level_reason"),
        "return_publishable": return_publishable,
        "price_per_share": (contract.get("market") or {}).get("price_per_share"),
        "market_cap_m": (contract.get("market") or {}).get("market_cap_m"),
        "enterprise_value_m": (contract.get("market") or {}).get("enterprise_value_m"),
        "value_per_share": values,
        "present_value_today_per_share": values,
        "output_basis": contract_valuation.get("output_basis"),
        "output_basis_status": contract_valuation.get("output_basis_status"),
        "margin_of_safety_pct": contract_valuation.get("margin_of_safety_pct") or {},
        "upside_to_value_pct": contract_valuation.get("upside_to_value_pct") or {},
        "forward_return_at_price_pct": published_returns,
        # Compatibility field: it is the canonical forward return or null,
        # never the former annualized present-value/price gap.
        "annualized_return_at_price_pct": published_returns,
        "forward_return_status": "available" if return_publishable else "withheld",
        "forward_return_reason": (
            contract_valuation.get("forward_return_reason")
            if return_publishable
            else (
                "model maturity is not eligible to publish a return"
                if model_level not in RETURN_PUBLISHABLE_LEVELS
                else contract_valuation.get("forward_return_reason")
            )
        ),
        "required_return_pct": contract_valuation.get("required_return_pct"),
        "downside_to_low_pct": contract_valuation.get("downside_to_low_pct"),
        "unvalued_component_count": (contract.get("component_coverage") or {}).get("unvalued_component_count"),
        "unresolved_evidence_count": (contract.get("evidence") or {}).get("unresolved_count"),
        "proof_complete_pct": (contract.get("calculation_proof_summary") or {}).get("proof_complete_pct"),
        "model_hash": (contract.get("change_control") or {}).get("model_hash"),
        "dates": contract.get("dates") or {},
        "legacy_audit": contract.get("legacy_audit") or {},
        "decision_eligibility": contract.get("decision_eligibility") or {},
        "primary_power_zone": (contract.get("method_route") or {}).get("label"),
        "owner_decision": committee.get("owner_decision"),
        "next_action": committee.get("next_action"),
    }


def freshness_view(decision: dict, as_of: str) -> dict:
    """Make model, fact, and quote age visible without inventing precision."""
    dates = decision.get("dates") or {}
    thresholds = {
        "model_as_of": 365,
        "latest_fact_as_of": 548,
        "price_as_of": 7,
    }
    ages: dict[str, int | None] = {}
    warnings = []
    try:
        effective = date.fromisoformat(str(as_of)[:10])
    except (TypeError, ValueError):
        effective = None
    for field, limit in thresholds.items():
        raw = dates.get(field)
        try:
            age = (effective - date.fromisoformat(str(raw)[:10])).days if effective and raw else None
        except ValueError:
            age = None
        ages[field] = age
        if age is None:
            warnings.append(f"{field} is not dated")
        elif age > limit:
            warnings.append(f"{field} is {age} days old (review threshold {limit})")
    status = "current" if not warnings else (
        "stale" if any("days old" in warning for warning in warnings) else "undated"
    )
    return {
        "status": status,
        "as_of": str(as_of)[:10],
        "dates": dates,
        "age_days": ages,
        "review_threshold_days": thresholds,
        "warnings": warnings,
        "rule": "Freshness is disclosed separately from proof completeness; stale or undated inputs require review before a new capital decision.",
    }


def business_view(valuation: dict) -> dict:
    contract = valuation.get("universal_valuation_contract") or build_universal_valuation_contract(valuation)
    rows = contract.get("economic_ownership_map") or []
    return {
        "status": "complete" if not (contract.get("component_coverage") or {}).get("unvalued_component_count") else "incomplete",
        "components": rows,
        "component_coverage": contract.get("component_coverage") or {},
        "facts": (contract.get("input_classification") or {}).get("facts") or [],
        "estimates": (contract.get("input_classification") or {}).get("estimates") or [],
        "judgments": (contract.get("input_classification") or {}).get("judgments") or [],
    }


def valuation_view(valuation: dict) -> dict:
    contract = valuation.get("universal_valuation_contract") or build_universal_valuation_contract(valuation)
    return {
        "status": contract.get("status"),
        "proof_status": contract.get("proof_status") or contract.get("status"),
        "model_level": contract.get("model_level"),
        "model_level_reason": contract.get("model_level_reason"),
        "decision_eligibility": contract.get("decision_eligibility") or {},
        "dates": contract.get("dates") or {},
        "legacy_audit": contract.get("legacy_audit") or {},
        "market": contract.get("market") or {},
        "valuation": contract.get("valuation") or {},
        "components": contract.get("economic_ownership_map") or [],
        "scenario_contract": contract.get("scenario_contract") or {},
        "calculation_proof_summary": contract.get("calculation_proof_summary") or {},
        "model_checks": contract.get("model_checks") or {},
        "source_lineage": contract.get("source_lineage") or [],
        "change_control": contract.get("change_control") or {},
    }


def optionality_view(valuation: dict) -> dict:
    contract = valuation.get("universal_valuation_contract") or build_universal_valuation_contract(valuation)
    options = [row for row in contract.get("economic_ownership_map") or [] if row.get("category") in {"real_option", "dated_payoff"}]
    return {
        "status": "present" if options else "not_material_or_separately_identified",
        "option_count": len(options),
        "options": options,
        "rule": "Every option requires a beneficiary, probability, timing, remaining capital, failure case, and non-overlap control; absence of option value must be explicit rather than unvalued.",
    }


def ledger_rows() -> list[dict]:
    if not LEDGER.exists():
        return []
    rows = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def outcome_view(ticker: str, config: dict, committee: dict, as_of: str) -> dict:
    record = read_json(ROOT / committee["record_ref"]) if committee.get("record_ref") else {}
    owner = authoritative_owner_decision(ROOT / ticker / "research", record)
    decided = owner.get("status") in {"complete", "decided"}
    decision_date = owner.get("decided_at") or ((record.get("review") or {}).get("as_of") if decided else None)
    rows = [row for row in ledger_rows() if str(row.get("ticker", "")).upper() == ticker]
    schedule = []
    for months in config.get("measurement_horizons_months") or [6, 12, 24]:
        target = add_months(decision_date, int(months)) if decision_date else None
        measured = next((row for row in rows if row.get("horizon_months") == months or (target and row.get("measurement_date") == target)), None)
        if measured:
            status = "measured"
        elif not decision_date:
            status = "waiting_for_owner_decision"
        elif target <= as_of:
            status = "due"
        else:
            status = "scheduled"
        schedule.append({
            "horizon_months": months,
            "target_date": target,
            "status": status,
            "measurement_date": measured.get("measurement_date") if measured else None,
            "total_return_pct": measured.get("total_return_pct") if measured else None,
            "return_status": measured.get("return_status") if measured else None,
        })
    calibration = read_json(CALIBRATION)
    persona_rows = calibration.get("methods") or calibration.get("personas") or {}
    threshold = int(config.get("minimum_persona_outcomes_before_reweighting") or 20)
    eligible = sorted(persona for persona, row in persona_rows.items() if int(row.get("completed_outcomes") or row.get("n") or 0) >= threshold)
    zone_eligible = sorted(key for key, row in (calibration.get("persona_power_zones") or {}).items() if int(row.get("completed_outcomes") or 0) >= threshold)
    return {
        "status": "tracking" if decision_date else "waiting_for_owner_decision",
        "decision_date": decision_date,
        "schedule": schedule,
        "recorded_outcome_count": len(rows),
        "minimum_persona_outcomes_before_reweighting": threshold,
        "personas_eligible_for_weight_review": eligible,
        "persona_power_zones_eligible_for_weight_review": zone_eligible,
        "weighting_rule": f"Do not change a persona's relevance within a power zone until at least {threshold} attributable, dividend-aware outcomes exist there; never reweight automatically.",
    }


def component_map(valuation: dict) -> dict[str, dict]:
    result = valuation.get("component_valuation_results") or {}
    rows = [*(result.get("additive_components") or []), *(result.get("embedded_components") or [])]
    return {str(row.get("id")): row for row in rows if row.get("id")}


def complete_component_snapshots(research: Path) -> list[tuple[Path, dict]]:
    rows = []
    for path in sorted((research / "valuation_history").glob("valuation_????-??-??.json")):
        data = read_json(path)
        total = (data.get("component_valuation_results") or {}).get("total_equity_value_per_share") or {}
        if total.get("base") is not None:
            rows.append((path, data))
    return rows


def risk_field(row: dict, key: str):
    return (row.get("risk_and_timing") or {}).get(key)


def attribution_causes(old_proof: dict, new_proof: dict, old_component: dict, new_component: dict) -> list[str]:
    causes = []
    if (old_proof.get("quantity") or {}).get("value") != (new_proof.get("quantity") or {}).get("value"):
        causes.append("fundamentals")
    if old_proof.get("method") != new_proof.get("method") or old_proof.get("comparable_ids") != new_proof.get("comparable_ids") or old_proof.get("adjustment") != new_proof.get("adjustment"):
        causes.append("comparables_or_method")
    if risk_field(old_proof, "success_probability") != risk_field(new_proof, "success_probability"):
        causes.append("probability")
    if risk_field(old_proof, "timing_basis") != risk_field(new_proof, "timing_basis"):
        causes.append("timing")
    if risk_field(old_proof, "remaining_capital_m") != risk_field(new_proof, "remaining_capital_m") or risk_field(old_proof, "remaining_capital_basis") != risk_field(new_proof, "remaining_capital_basis"):
        causes.append("capital")
    if old_component.get("evidence_tier") != new_component.get("evidence_tier"):
        causes.append("evidence")
    return causes or ["assumption_or_unclassified"]


def attribution_view(research: Path, current: dict) -> dict:
    contract = current.get("universal_valuation_contract") or {}
    current_total = (
        (contract.get("valuation") or {}).get("value_per_share")
        if contract.get("schema_version") in {"2.0", "3.0"}
        else (current.get("component_valuation_results") or {}).get("total_equity_value_per_share")
    ) or {}
    current_point = {"as_of": current.get("as_of"), "low": current_total.get("low"), "base": current_total.get("base"), "high": current_total.get("high")}
    if current_total.get("base") is None:
        return {
            "status": "waiting_for_proof_complete_baseline",
            "current": current_point,
            "prior": None,
            "base_change_per_share": None,
            "base_change_pct": None,
            "drivers": [],
            "category_totals_per_share": {},
            "unexplained_per_share": None,
            "legacy_value_per_share": (contract.get("valuation") or {}).get("legacy_value_per_share"),
            "explanation": "A complete security value is intentionally withheld while material components are unpriced. Attribution restarts after the first proof-complete baseline.",
        }
    snapshots = complete_component_snapshots(research)
    current_as_of = str(current.get("as_of") or "")[:10]
    prior_candidates = [(path, data) for path, data in snapshots if str(data.get("as_of") or "")[:10] < current_as_of]
    if not prior_candidates:
        return {
            "status": "baseline_established",
            "current": current_point,
            "prior": None,
            "base_change_per_share": None,
            "base_change_pct": None,
            "drivers": [],
            "category_totals_per_share": {},
            "unexplained_per_share": None,
            "explanation": "The current component schedule is the first decision-grade baseline; attribution begins with the next dated valuation snapshot.",
        }
    prior_path, prior = prior_candidates[-1]
    prior_total = (prior.get("component_valuation_results") or {}).get("total_equity_value_per_share") or {}
    old_components, new_components = component_map(prior), component_map(current)
    old_proof, new_proof = proof_map(prior), proof_map(current)
    drivers = []
    category_totals = defaultdict(float)
    for component_id in sorted(set(old_components) | set(new_components)):
        old = old_components.get(component_id) or {}
        new = new_components.get(component_id) or {}
        old_base, new_base = float(old.get("base_per_share") or 0), float(new.get("base_per_share") or 0)
        delta = round(new_base - old_base, 2)
        if abs(delta) < 0.005 and old and new:
            continue
        causes = ["scope"] if not old or not new else attribution_causes(old_proof.get(component_id) or {}, new_proof.get(component_id) or {}, old, new)
        share = delta / len(causes)
        for cause in causes:
            category_totals[cause] += share
        drivers.append({
            "component_id": component_id,
            "label": new.get("label") or old.get("label") or component_id,
            "prior_base_per_share": old_base,
            "current_base_per_share": new_base,
            "change_per_share": delta,
            "causes": causes,
        })
    drivers.sort(key=lambda row: abs(row["change_per_share"]), reverse=True)
    old_base, new_base = float(prior_total.get("base") or 0), float(current_total.get("base") or 0)
    total_delta = round(new_base - old_base, 2)
    explained = round(sum(row["change_per_share"] for row in drivers), 2)
    return {
        "status": "complete",
        "current": current_point,
        "prior": {"as_of": prior.get("as_of"), "base": prior_total.get("base"), "ref": prior_path.relative_to(ROOT).as_posix()},
        "base_change_per_share": total_delta,
        "base_change_pct": round(total_delta / old_base * 100, 2) if old_base else None,
        "drivers": drivers,
        "category_totals_per_share": {key: round(value, 2) for key, value in sorted(category_totals.items())},
        "unexplained_per_share": round(total_delta - explained, 2),
        "explanation": "Component changes are classified from observable differences in quantity, comparable method, probability, timing, capital, evidence, and schedule scope.",
    }


def build(ticker: str, as_of: str | None = None) -> dict:
    ticker = ticker.upper()
    research = ROOT / ticker / "research"
    valuation = read_json(research / "valuation.json")
    canonical_route = read_json(research / "valuation_route.json")
    if canonical_route:
        # One route artifact controls the method shown in the workbench and the
        # specialists later seated by the Investment Committee.
        valuation["valuation_method_route"] = canonical_route
    reviewed_contract = read_json(research / "valuation_contract.json")
    if reviewed_contract:
        # The cohort contract merges curated evidence follow-ups and the
        # explicitly reviewed power-zone route.  Prefer it to the raw model's
        # computed contract so the dashboard cannot call an unresolved case
        # decision-grade merely because the arithmetic schedule is complete.
        valuation["universal_valuation_contract"] = reviewed_contract
        valuation["universal_valuation_contract"]["method_route"] = (
            canonical_route
            or valuation["universal_valuation_contract"].get("method_route")
            or valuation.get("valuation_method_route")
            or {}
        )
    scaffold = read_json(research / "valuation_model_scaffold.json")
    if not valuation or (scaffold and not valuation.get("method")):
        if not scaffold:
            raise FileNotFoundError(f"{ticker}: valuation.json and valuation_model_scaffold.json missing")
        effective_date = (as_of or date.today().isoformat())[:10]
        route = scaffold.get("method_route") or {}
        gap = {
            "id": "complete_component_model_required", "priority": "critical", "component_ids": [],
            "question": "A complete primary-sourced component valuation has not been built.",
            "evidence_required": "; ".join(scaffold.get("required_component_map") or []),
            "acceptance_test": "Every material economic claim is valued exactly once with causal low/base/high assumptions and primary evidence.",
            "valuation_effect": "Blocks decision-grade value and committee voting.", "status": "open", "source": "cohort_scaffold",
        }
        return {
            "schema_version": "3.0", "ticker": ticker, "as_of": effective_date,
            "proof_status": "evidence_blocked",
            "model_level": "unmodeled",
            "model_level_reason": "No completed economic ownership model exists.",
            "decision_eligibility": {"committee_eligible": False, "capital_actionable": False, "capital_authority_required": "human_decision"},
            "dates": {"model_as_of": None, "latest_fact_as_of": None, "oldest_fact_as_of": None, "price_as_of": None},
            "legacy_audit": {},
            "decision": {"status": "evidence_blocked", "proof_status": "evidence_blocked", "model_level": "unmodeled", "model_level_reason": "No completed economic ownership model exists.", "return_publishable": False, "price_per_share": None, "market_cap_m": None, "enterprise_value_m": None, "value_per_share": {}, "present_value_today_per_share": {}, "output_basis": None, "output_basis_status": "missing", "margin_of_safety_pct": {}, "upside_to_value_pct": {}, "forward_return_at_price_pct": {"low": None, "base": None, "high": None}, "annualized_return_at_price_pct": {"low": None, "base": None, "high": None}, "forward_return_status": "withheld", "forward_return_reason": "No completed forward cash-flow model exists.", "required_return_pct": None, "dates": {"model_as_of": None, "latest_fact_as_of": None, "oldest_fact_as_of": None, "price_as_of": None}, "legacy_audit": {}, "decision_eligibility": {"committee_eligible": False, "capital_actionable": False, "capital_authority_required": "human_decision"}, "downside_to_low_pct": None, "unvalued_component_count": 1, "unresolved_evidence_count": 1, "primary_power_zone": route.get("label"), "owner_decision": None, "next_action": scaffold.get("next_action")},
            "business": {"status": "incomplete", "components": [], "component_coverage": {"unvalued_component_count": 1}, "facts": [], "estimates": [], "judgments": []},
            "valuation": {"status": "evidence_blocked", "market": {}, "valuation": {}, "components": [], "scenario_contract": {"rule": "Build causal low/base/high scenarios before drawing a conclusion."}, "calculation_proof_summary": {"component_count": 0, "priced_component_count": 0, "proof_complete_pct": 0, "status_counts": {"unpriced": 1}, "all_material_components_priced": False, "calculation_errors": [], "aggregate_proof_hash": None}, "model_checks": {"all_material_components_priced": False}, "source_lineage": [], "change_control": {"model_hash": None, "method_versions": [], "change_log": []}},
            "optionality": {"status": "not_yet_mapped", "option_count": 0, "options": [], "rule": "Optionality remains unvalued until the component map is complete."},
            "committee": {"status": "not_started", "analysis_progress": {"completed": 0, "required": 0}, "owner_status": "pending", "owner_decision": None, "next_action": "Complete the component model before freezing an IC evidence packet."},
            "evidence": {"status": "critical_gaps_open", "open_count": 1, "critical_count": 1, "gaps": [gap]},
            "method_fit": {"profile_id": route.get("profile_id"), "label": route.get("label"), "primary_methods": route.get("primary_methods") or [], "corroborating_methods": route.get("corroborating_methods") or [], "primary_personas": route.get("primary_personas") or [], "cross_check_personas": route.get("cross_check_personas") or [], "silent_personas": route.get("silent_personas") or [], "routing_reasons": route.get("reasons") or [], "required_evidence": route.get("required_evidence") or [], "applicability_tests": [], "failure_modes": route.get("failure_modes") or [], "validation_cohort": [], "rule": route.get("decision_rule")},
            "outcomes": {"status": "waiting_for_owner_decision", "schedule": [], "recorded_outcome_count": 0, "minimum_persona_outcomes_before_reweighting": 20, "personas_eligible_for_weight_review": [], "weighting_rule": "No calibration before a completed IC decision and measured dividend-aware outcome."},
            "attribution": {"status": "waiting_for_baseline", "current": {"as_of": effective_date, "low": None, "base": None, "high": None}, "drivers": [], "explanation": "Attribution begins after the first decision-grade baseline."},
            "freshness": freshness_view({"dates": {}}, effective_date),
        }
    config = read_json(CONFIG)
    ticker_cfg = (config.get("tickers") or {}).get(ticker) or {}
    effective_date = (as_of or date.today().isoformat())[:10]
    committee = committee_view(research)
    evidence = evidence_view(ticker_cfg, valuation, committee)
    decision = decision_view(valuation, committee)
    # Followups / evidence gaps are the readiness authority for the dashboard.
    decision["unresolved_evidence_count"] = evidence.get("open_count") or 0
    if (evidence.get("open_count") or 0) > 0 or (evidence.get("critical_count") or 0) > 0:
        decision["status"] = "evidence_blocked"
        decision["proof_status"] = "evidence_blocked"
        decision["model_level"] = "evidence_blocked"
        decision["model_level_reason"] = "Curated primary-evidence follow-ups remain open."
        decision["return_publishable"] = False
        decision["forward_return_at_price_pct"] = {"low": None, "base": None, "high": None}
        decision["annualized_return_at_price_pct"] = {"low": None, "base": None, "high": None}
        decision["forward_return_status"] = "withheld"
        decision["forward_return_reason"] = "Primary-evidence follow-ups remain open."
        decision["decision_eligibility"] = {
            **(decision.get("decision_eligibility") or {}),
            "committee_eligible": False,
            "capital_actionable": False,
            "capital_authority_required": "human_decision",
            "reason": "Close primary-evidence gaps before committee review.",
        }
        decision["next_action"] = "Close critical evidence gaps before freezing a decision-grade packet."
    return {
        "schema_version": "3.0",
        "ticker": ticker,
        "as_of": effective_date,
        "proof_status": decision.get("proof_status"),
        "model_level": decision.get("model_level"),
        "model_level_reason": decision.get("model_level_reason"),
        "decision_eligibility": decision.get("decision_eligibility") or {},
        "dates": decision.get("dates") or {},
        "legacy_audit": decision.get("legacy_audit") or {},
        "decision": decision,
        "business": business_view(valuation),
        "valuation": valuation_view(valuation),
        "optionality": optionality_view(valuation),
        "committee": committee,
        "evidence": evidence,
        "method_fit": method_fit_view(config, ticker_cfg, valuation),
        "outcomes": outcome_view(ticker, config, committee, effective_date),
        "attribution": attribution_view(research, valuation),
        "freshness": freshness_view(decision, effective_date),
    }


def write(ticker: str, as_of: str | None = None) -> Path:
    result = build(ticker, as_of)
    path = ROOT / ticker.upper() / "research" / "valuation_workbench.json"
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tickers", nargs="+")
    parser.add_argument("--date")
    args = parser.parse_args()
    for ticker in args.tickers:
        path = write(ticker, args.date)
        print(path.relative_to(ROOT).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
