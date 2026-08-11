#!/usr/bin/env python3
"""Deterministically route a security to fitting valuation power zones.

The router standardizes method selection without forcing unlike securities into
one model.  It uses disclosed economics and component structure, records every
reason, selects one primary profile and at most two corroborating methods, and
explicitly silences personas whose error profile is not useful for the case.
"""
from __future__ import annotations

from collections import defaultdict

PROFILE_ORDER = (
    "scarce_asset_optionality",
    "quality_reinvestment",
    "capital_cycle",
    "credit_and_normalized_returns",
    "catalyst_asset_value",
    "predictable_cash_flow",
    "binary_milestone",
)

PROFILES = {
    "scarce_asset_optionality": {
        "label": "Scarce assets, royalties, and optionality",
        "archetypes": {"optionality", "resource", "land_owner", "scarce_strategic_asset", "holding_co", "croupier"},
        "categories": {"real_option", "infrastructure"},
        "method_tokens": {"unit_nav", "royalty", "acre", "land", "replacement", "option"},
        "primary_methods": ["component_owner_cash_and_unit_nav"],
        "corroborating_methods": ["comparable_transactions", "replacement_cost_or_reverse_nav"],
        "primary_personas": ["hk", "stahl"],
        "cross_check_personas": ["klarman_asset_value", "marks_credit_cycle"],
        "required_evidence": ["legal economic claim", "non-overlapping physical inventory", "unit economics", "realization timing", "remaining owner capital"],
        "failure_modes": ["gross asset value mistaken for shareholder value", "operating cash flow and NAV counted twice", "remote options treated as contracted cash"],
    },
    "quality_reinvestment": {
        "label": "High-return compounder",
        "archetypes": {"compounder", "platform", "serial_acquirer", "croupier"},
        "categories": {"operating_business"},
        "method_tokens": {"owner_cash", "reinvestment", "dcf"},
        "primary_methods": ["owner_earnings_reinvestment_dcf"],
        "corroborating_methods": ["reverse_dcf", "incremental_roic_runway"],
        "primary_personas": ["buffett_weschler", "hohn"],
        "cross_check_personas": ["munger", "marathon_capital_cycle"],
        "required_evidence": ["normalized owner earnings", "incremental return on capital", "reinvestment runway", "diluted share count", "competitive-advantage mechanism"],
        "failure_modes": ["growth projected without its capital cost", "stock compensation or acquisitions omitted", "terminal value unsupported by a durable mechanism"],
    },
    "capital_cycle": {
        "label": "Capital cycle and normalized industry economics",
        "archetypes": {"commodity_cyclical", "cyclical", "turnaround"},
        "categories": {"operating_business", "infrastructure"},
        "method_tokens": {"midcycle", "capacity", "replacement", "cycle"},
        "primary_methods": ["midcycle_capacity_value"],
        "corroborating_methods": ["replacement_cost", "downcycle_liquidity_stress"],
        "primary_personas": ["marathon_capital_cycle"],
        "cross_check_personas": ["marks_credit_cycle", "pabrai"],
        "required_evidence": ["industry capacity and additions", "utilization", "normalized unit margins", "maintenance versus growth capital", "low-case liquidity"],
        "failure_modes": ["peak margins capitalized", "supply response ignored", "replacement cost used for assets that cannot earn their cost of capital"],
    },
    "credit_and_normalized_returns": {
        "label": "Credit, funding, and normalized financial returns",
        "archetypes": {"bank", "insurer", "financial_balance_sheet", "leveraged_equity"},
        "categories": {"financial_asset", "liability_or_reserve"},
        "method_tokens": {"tangible_book", "excess_return", "credit", "refinancing", "stress_loss"},
        "primary_methods": ["capital_structure_and_excess_return"],
        "corroborating_methods": ["stress_loss_waterfall", "normalized_tangible_book"],
        "primary_personas": ["marks_credit_cycle"],
        "cross_check_personas": ["buffett_weschler", "klarman_asset_value"],
        "required_evidence": ["capital structure and maturities", "normalized losses", "regulatory or covenant capital", "funding cost", "distributable excess capital"],
        "failure_modes": ["industrial EV multiple applied to a financial balance sheet", "regulatory capital treated as distributable", "refinancing and off-balance-sheet claims omitted"],
    },
    "catalyst_asset_value": {
        "label": "Catalyst-backed asset value",
        "archetypes": {"special_situation", "holding_company", "holding_co", "turnaround"},
        "categories": {"dated_payoff", "financial_asset"},
        "method_tokens": {"liquidation", "break_value", "dated_payoff", "transaction_nav", "catalyst"},
        "primary_methods": ["probability_weighted_catalyst_nav"],
        "corroborating_methods": ["break_value", "timing_adjusted_payoff"],
        "primary_personas": ["klarman_asset_value", "greenblatt"],
        "cross_check_personas": ["pabrai", "marks_credit_cycle"],
        "required_evidence": ["finite event tree", "catalyst control and timing", "break value", "tax and legal claims", "financing through realization"],
        "failure_modes": ["catalyst assumed rather than evidenced", "delay and break cases omitted", "gross proceeds used before tax and senior claims"],
    },
    "predictable_cash_flow": {
        "label": "Predictable cash-flow security",
        "archetypes": {"utility", "regulated_utility", "infrastructure", "mature_cash_generator"},
        "categories": {"operating_business", "infrastructure"},
        "method_tokens": {"dividend", "regulated", "contracted", "owner_cash"},
        "primary_methods": ["owner_cash_or_dividend_discount"],
        "corroborating_methods": ["regulated_asset_base", "yield_and_reverse_dcf"],
        "primary_personas": ["buffett_weschler", "hohn"],
        "cross_check_personas": ["marks_credit_cycle"],
        "required_evidence": ["cash-flow durability", "maintenance capital", "funding plan", "distribution policy", "contract or regulatory reset terms"],
        "failure_modes": ["dividend treated as earning power", "growth capital and dilution omitted", "contract renewal or regulatory reset ignored"],
    },
    "binary_milestone": {
        "label": "Binary and milestone-driven assets",
        "archetypes": {"biotech", "pre_profit", "binary_special_situation", "exploration"},
        "categories": {"real_option"},
        "method_tokens": {"milestone", "probability", "pipeline", "risk_adjusted"},
        "primary_methods": ["risk_adjusted_milestone_value"],
        "corroborating_methods": ["cash_runway_and_dilution", "failure_recovery_value"],
        "primary_personas": ["greenblatt", "klarman_asset_value"],
        "cross_check_personas": ["marks_credit_cycle", "pabrai"],
        "required_evidence": ["asset-by-asset milestones", "base-rate probability", "time and cash to milestone", "dilution", "failure recovery"],
        "failure_modes": ["unsupported success probabilities", "cash burn and dilution omitted", "pipeline value counted in both revenue forecast and option schedule"],
    },
}

ALIASES = {
    "infrastructure_compounder": "predictable_cash_flow",
    "probability_weighted_special_situation": "binary_milestone",
}

# The silenceable-persona universe is the canonical registry, not the union of
# profile mentions: deriving it from PROFILES silently exempted lawrence and
# moi from ever being routed silent.
from persona_groups import PERSONA_IDS

ALL_PERSONAS = sorted(PERSONA_IDS)


def _tokens(data: dict) -> tuple[set[str], set[str]]:
    result = data.get("component_valuation_results") or {}
    rows = [*(result.get("additive_components") or []), *(result.get("embedded_components") or [])]
    categories = {str(row.get("category") or "").lower() for row in rows}
    methods = " ".join(str(row.get("method") or "").lower() for row in rows)
    return categories, {token for token in methods.replace("-", "_").split() if token}


def route_valuation(data: dict, explicit_profile: str | None = None) -> dict:
    classification = data.get("classification_inputs") or {}
    archetype = str(classification.get("archetype") or "").lower()
    sleeve = str(classification.get("investment_sleeve") or "").lower()
    categories, method_words = _tokens(data)
    raw_methods = " ".join(method_words)
    scores: dict[str, float] = defaultdict(float)
    reasons: dict[str, list[str]] = defaultdict(list)
    explicit = ALIASES.get(explicit_profile or "", explicit_profile)
    for profile_id in PROFILE_ORDER:
        profile = PROFILES[profile_id]
        if archetype and archetype in profile["archetypes"]:
            scores[profile_id] += 6
            reasons[profile_id].append(f"archetype={archetype}")
        matches = sorted(categories & profile["categories"])
        if matches:
            scores[profile_id] += min(3, len(matches))
            reasons[profile_id].append("component categories=" + ", ".join(matches))
        token_matches = sorted(token for token in profile["method_tokens"] if token in raw_methods)
        if token_matches:
            scores[profile_id] += min(3, len(token_matches))
            reasons[profile_id].append("existing methods=" + ", ".join(token_matches))
        if sleeve and "real_assets" in sleeve and profile_id == "scarce_asset_optionality":
            scores[profile_id] += 2
            reasons[profile_id].append(f"investment_sleeve={sleeve}")
        if explicit == profile_id:
            scores[profile_id] += 10
            reasons[profile_id].append("explicit reviewed profile")
    ranked = sorted(PROFILE_ORDER, key=lambda pid: (-scores[pid], PROFILE_ORDER.index(pid)))
    primary_id = ranked[0] if scores[ranked[0]] > 0 else "quality_reinvestment"
    primary = PROFILES[primary_id]
    secondary_profiles = [pid for pid in ranked[1:] if scores[pid] > 0][:2]
    selected_personas = list(dict.fromkeys(primary["primary_personas"] + primary["cross_check_personas"]))
    output = {
        "schema_version": "1.0",
        "status": "routed" if scores[primary_id] > 0 else "default_needs_review",
        "profile_id": primary_id,
        "label": primary["label"],
        "score": scores[primary_id],
        "reasons": reasons[primary_id] or ["No decisive classification was supplied; owner-earnings is the conservative operating default."],
        "primary_methods": primary["primary_methods"],
        "corroborating_methods": primary["corroborating_methods"][:2],
        "primary_personas": primary["primary_personas"],
        "cross_check_personas": primary["cross_check_personas"],
        "silent_personas": [p for p in ALL_PERSONAS if p not in selected_personas],
        "required_evidence": primary["required_evidence"],
        "failure_modes": primary["failure_modes"],
        "secondary_profiles": [{"profile_id": pid, "score": scores[pid], "reasons": reasons[pid]} for pid in secondary_profiles],
        "scorecard": {pid: {"score": scores[pid], "reasons": reasons[pid]} for pid in PROFILE_ORDER},
        "decision_rule": "Use one primary method and no more than two corroborating methods; irrelevant methods and personas remain silent.",
    }
    data["valuation_method_route"] = output
    return output
