#!/usr/bin/env python3
"""Unified valuation + stance proposal for Marvin decision stack.

Usage:
  python _system/scripts/marvin_valuation.py --ticker ICE
  python _system/scripts/marvin_valuation.py --file ICE/research/valuation.json
  python _system/scripts/marvin_valuation.py --ticker ICE --write   # persist results
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from growth_theory import enrich_growth_explanation, load_filing_facts, theory_scenario  # noqa: E402
from economic_value_framework import build_economic_value_analysis  # noqa: E402
from calculation_proof import floor_equity_value_range  # noqa: E402
from universal_valuation_contract import build_universal_valuation_contract  # noqa: E402
from lawrence_horizon import LAWRENCE_HORIZON_YEARS, RETURN_LABEL, SYNTHESIS_LABEL  # noqa: E402
from valuation_synthesis import compute_synthesis  # noqa: E402
CLASS_PATH = ROOT / "_system" / "portfolio" / "classification.json"
AI_HYPERSCALERS = frozenset({"GOOGL", "AMZN", "META", "MSFT"})
SEGMENT_DISCOUNT_DEFAULT = 0.10


def cashflows_full(
    price: float,
    fcf0: float,
    growth1: float,
    growth2: float,
    exit_mult: float,
    years: int = LAWRENCE_HORIZON_YEARS,
) -> list[float]:
    stream = [-price]
    fcf = fcf0
    for year in range(1, years + 1):
        g = growth1 if year <= min(5, years) else growth2
        fcf *= 1 + g
        if year < years:
            stream.append(fcf)
        else:
            stream.append(fcf + fcf * exit_mult)
    return stream


def _npv_at(rate: float, cfs: list[float]) -> float:
    return sum(cf / (1 + rate) ** i for i, cf in enumerate(cfs))


def _irr_bisect(cfs: list[float], tol: float = 1e-7) -> float | None:
    """Bracket IRR when Newton diverges (common when price >> cumulative cash flows)."""
    brackets = [(-0.99, 0.99), (-0.5, 0.5), (-0.25, 0.25)]
    for lo, hi in brackets:
        n_lo, n_hi = _npv_at(lo, cfs), _npv_at(hi, cfs)
        if n_lo * n_hi > 0:
            continue
        for _ in range(200):
            mid = (lo + hi) / 2
            n_mid = _npv_at(mid, cfs)
            if abs(n_mid) < tol:
                return mid
            if n_lo * n_mid <= 0:
                hi, n_hi = mid, n_mid
            else:
                lo, n_lo = mid, n_mid
        return (lo + hi) / 2
    return None


def irr(cfs: list[float], guess: float = 0.12, tol: float = 1e-7, max_iter: int = 200) -> float:
    rate = guess
    for _ in range(max_iter):
        npv = _npv_at(rate, cfs)
        dnpv = sum(-i * cf / (1 + rate) ** (i + 1) for i, cf in enumerate(cfs))
        if abs(dnpv) < 1e-12:
            break
        step = npv / dnpv
        rate -= step
        if abs(step) < tol:
            break
    if abs(rate) > 5 or abs(_npv_at(rate, cfs)) > 1.0:
        alt = _irr_bisect(cfs, tol=tol)
        if alt is not None:
            return alt
    return rate


def run_full_scenario(
    price: float,
    fcf0: float,
    scenario: dict,
    years: int = LAWRENCE_HORIZON_YEARS,
) -> dict:
    growth_late = scenario.get("growth_y6_end", scenario.get("growth_y6_10"))
    exit_multiple = scenario.get("exit_pfcf_end", scenario.get("exit_pfcf_y10"))
    if growth_late is None or exit_multiple is None:
        raise ValueError("scenario requires growth_y6_end/legacy growth_y6_10 and exit_pfcf_end/legacy exit_pfcf_y10")
    cfs = cashflows_full(
        price=price,
        fcf0=fcf0,
        growth1=scenario["growth_y1_5"],
        growth2=growth_late,
        exit_mult=exit_multiple,
        years=years,
    )
    rate = irr(cfs)
    return {"return_pct": round(rate * 100, 1), "cashflows": [round(x, 2) for x in cfs]}


def run_scenario_method(price: float, per_share0: float, scenario: dict) -> dict:
    """Scenario method — same math as full but metric may be EPS/owner earnings."""
    metric_key = scenario.get("metric_key", "growth_y1_5")
    g1 = scenario.get("growth_y1_5", scenario.get("growth", 0.05))
    g2 = scenario.get("growth_y6_end", scenario.get("growth_y6_10", g1 * 0.75))
    exit_mult = scenario.get("exit_multiple", scenario.get("exit_pfcf_end", scenario.get("exit_pfcf_y10", 15)))
    cfs = cashflows_full(price, per_share0, g1, g2, exit_mult, years=LAWRENCE_HORIZON_YEARS)
    return {"return_pct": round(irr(cfs) * 100, 1)}


def run_yield_curve(scenario: dict) -> dict:
    """HK yield curve — annualized return to a dated payoff."""
    price = scenario["price"]
    payoff = scenario["payoff"]
    years = scenario["years"]
    if price <= 0 or years <= 0:
        return {"return_pct": None}
    total_return = payoff / price
    ann = total_return ** (1 / years) - 1
    return {"return_pct": round(ann * 100, 1), "payoff": payoff, "years": years}


def irr_band(pct: float | None) -> str:
    if pct is None:
        return "pending"
    if pct > 20:
        return ">20%"
    if pct >= 15:
        return "15–20%"
    return "<15%"


def propose_stance(
    base_return: float | None,
    moat: str,
    dhando: str,
    irr_method: str,
    data: dict | None = None,
) -> dict:
    moat_bad = moat in ("eroding", "unproven")
    dhando_bad = dhando == "none"
    results = (data or {}).get("results", {})
    gate = (data or {}).get("optionality_gate", {})
    valuation_mode = (data or {}).get("valuation_mode")

    if valuation_mode == "optionality" and gate:
        primary_key = gate.get("primary_metric", "base")
        primary_return = gate.get("primary_return_pct")
        if primary_return is None and isinstance(results.get(primary_key), dict):
            primary_return = results[primary_key].get("return_pct")
        if primary_return is None:
            primary_return = base_return
        bull_return = results.get("bull", {}).get("return_pct") if results else None
        floor_pass = gate.get("floor_pass", False)
        incumbent = gate.get("incumbent_sleeve", False)

        if irr_method == "pending" or primary_return is None:
            suggested = "pending"
            band = "pending"
        elif dhando_bad or not floor_pass:
            suggested = "watch"
            band = irr_band(primary_return)
        elif primary_return > 20 and dhando in ("full", "partial"):
            suggested = "accumulate"
            band = ">20%"
        elif primary_return >= 15 or (floor_pass and bull_return and bull_return >= 18):
            suggested = "hold"
            band = "15–20%" if primary_return and primary_return >= 15 else "optionality"
        elif floor_pass and dhando in ("full", "partial") and (primary_return >= 7 or incumbent):
            suggested = "hold" if incumbent else "watch"
            band = "optionality"
        else:
            suggested = "watch"
            band = irr_band(primary_return) if primary_return is not None else "optionality"

        return {
            "suggested": suggested,
            "irr_band": band,
            "gates": {
                "moat_ok": not moat_bad,
                "dhando_ok": not dhando_bad,
                "floor_pass": floor_pass,
                "valuation_mode": "optionality",
            },
            "override_reason": gate.get("override_reason"),
        }

    if irr_method == "pending" or base_return is None:
        suggested = "pending"
        band = "pending"
    elif moat_bad or dhando_bad:
        suggested = "watch"
        band = irr_band(base_return)
    elif base_return > 20 and dhando in ("full", "partial"):
        suggested = "accumulate"
        band = ">20%"
    elif base_return >= 15:
        suggested = "hold"
        band = "15–20%"
    else:
        suggested = "watch"
        band = "<15%"

    return {
        "suggested": suggested,
        "irr_band": band,
        "gates": {
            "moat_ok": not moat_bad,
            "dhando_ok": not dhando_bad,
        },
        "override_reason": None,
    }


def pv_stream(
    fcf0: float,
    g1: float,
    g2: float,
    exit_mult: float,
    r: float,
    years: int = LAWRENCE_HORIZON_YEARS,
) -> float:
    fcf = fcf0
    pv = 0.0
    for year in range(1, years + 1):
        g = g1 if year <= min(5, years) else g2
        fcf *= 1 + g
        pv += fcf / (1 + r) ** year
    pv += (fcf * exit_mult) / (1 + r) ** years
    return pv


def solve_segment_implied_rate(
    price: float,
    segments: list[dict],
    drags: list[float],
    years: int = LAWRENCE_HORIZON_YEARS,
) -> float:
    """Discount rate where sum of segment PVs + drags = price."""
    rate = 0.10
    for _ in range(200):

        def total_pv(r: float) -> float:
            pv = 0.0
            for seg in segments:
                pv += pv_stream(
                    seg["owner_cash_y0_per_share"],
                    seg["growth_y1_5"],
                    seg["growth_y6_end"],
                    seg["exit_pfcf_end"],
                    r,
                    years,
                )
            for d in drags:
                pv += sum(-d / (1 + r) ** y for y in range(1, years + 1))
            return pv

        pv = total_pv(rate)
        eps = 1e-5
        d = (total_pv(rate + eps) - pv) / eps
        if abs(d) < 1e-12:
            break
        rate -= (pv - price) / d
    return rate


def compute_segment_overlay(data: dict) -> dict | None:
    build = data.get("segment_build") or {}
    if data.get("valuation_overlay") != "segment_cashflow" and not build.get("segments"):
        return None
    price = (data.get("inputs") or {}).get("price")
    if not price:
        return None
    years = int(build.get("horizon_years", LAWRENCE_HORIZON_YEARS))
    r_explicit = float(build.get("discount_rate_explicit", SEGMENT_DISCOUNT_DEFAULT))

    segments = []
    for seg in build.get("segments", []):
        f0 = seg.get("owner_cash_y0_per_share")
        if f0 is None:
            continue
        segments.append(
            {
                "owner_cash_y0_per_share": float(f0),
                "growth_y1_5": float(seg.get("growth_y1_5", 0.08)),
                "growth_y6_end": float(seg.get("growth_y6_end", seg.get("growth_y6_10", 0.06))),
                "exit_pfcf_end": float(seg.get("exit_pfcf_end", seg.get("exit_pfcf_y10", 18))),
            }
        )
    if not segments:
        return None

    drags: list[float] = []
    for opt in build.get("options", []):
        if opt.get("annual_drag_per_share") is not None:
            drags.append(float(opt["annual_drag_per_share"]))
    corp = (build.get("corporate_drag") or {}).get("alphabet_level_drag_per_share")
    if corp is not None:
        drags.append(float(corp))

    pv_at_r = 0.0
    for seg in segments:
        pv_at_r += pv_stream(
            seg["owner_cash_y0_per_share"],
            seg["growth_y1_5"],
            seg["growth_y6_end"],
            seg["exit_pfcf_end"],
            r_explicit,
            years,
        )
    for d in drags:
        pv_at_r += sum(-d / (1 + r_explicit) ** y for y in range(1, years + 1))

    raw_implied = solve_segment_implied_rate(price, segments, drags, years) * 100
    implied_pct = round(raw_implied, 1) if raw_implied >= 0.05 else round(raw_implied, 2)
    out = {
        "sum_pv_per_share_at_explicit_discount": round(pv_at_r, 1),
        "explicit_discount_rate_pct": round(r_explicit * 100, 1),
        "implied_business_return_pct": implied_pct,
        "lawrence_base_irr_pct": (data.get("results") or {}).get("base", {}).get("return_pct"),
    }
    if (data.get("valuation_methodology") or {}).get("mode") == "separated_views":
        build["reconciliation"] = {
            **out,
            "owner_cash_segment_sum_per_share": round(sum(s["owner_cash_y0_per_share"] for s in segments), 2),
            "owner_cash_total_per_share": (data.get("inputs") or {}).get("fcf_per_share"),
            "slack_notes": "Segment cross-check excludes the small consolidated tax-timing reconciliation; no asset-option value is included."
        }
    else:
        recon = build.setdefault("reconciliation", {})
        recon.update(out)
    return out


def _constant_growth_required(price: float, fcf0: float, exit_multiple: float, years: int) -> float | None:
    """Solve the constant owner-cash growth rate implied by price."""
    lo, hi = -0.25, 0.50
    for _ in range(200):
        mid = (lo + hi) / 2
        value = sum(fcf0 * (1 + mid) ** y for y in range(1, years + 1))
        value += fcf0 * (1 + mid) ** years * exit_multiple
        if value < price:
            lo = mid
        else:
            hi = mid
    return round(((lo + hi) / 2) * 100, 1)


COMPONENT_RANGE_KEYS = ("low", "base", "high")
COMPONENT_REVIEW_ROUTING = {
    "operating_business": ["hohn", "marathon_capital_cycle"],
    "infrastructure": ["hohn", "marathon_capital_cycle"],
    "financial_asset": ["greenblatt", "marks_credit_cycle"],
    "real_option": ["klarman_asset_value", "hk"],
    "liability_or_reserve": ["marks_credit_cycle", "pabrai"],
    "dated_payoff": ["greenblatt", "pabrai"],
}


def _driver_component_range_per_share(valuation: dict, shares: float | None) -> dict[str, float]:
    """Value a component from auditable economic drivers.

    The scarce-strategic-asset power zone uses three deliberately small models:
    revenue DCFs for producing assets, unit NAVs for dormant assets, and
    probability-weighted outcomes for pre-contract projects.  Each scenario is
    calculated independently; the engine never interpolates an analyst's base.
    """
    model = valuation.get("driver_model") or {}
    model_type = model.get("type")
    scenarios = model.get("scenarios") or {}
    if not shares or shares <= 0:
        raise ValueError("driver_model requires inputs.shares_outstanding")
    missing = [key for key in COMPONENT_RANGE_KEYS if key not in scenarios]
    if missing:
        raise ValueError(f"driver_model missing scenarios: {', '.join(missing)}")

    def revenue_dcf(case: dict) -> float:
        revenue = float(model["starting_revenue_m"])
        margin = float(case["after_tax_owner_cash_margin"])
        growth_1 = float(case["growth_y1_5"])
        growth_2 = float(case["growth_y6_10"])
        terminal_multiple = float(case["terminal_owner_cash_multiple"])
        discount_rate = float(case["discount_rate"])
        years = int(model.get("horizon_years", 10))
        incremental_roic = case.get("incremental_after_tax_roic")
        prior_owner_cash = revenue * margin
        present_value_m = 0.0
        owner_cash = prior_owner_cash
        for year in range(1, years + 1):
            growth = growth_1 if year <= 5 else growth_2
            revenue *= 1 + growth
            pre_growth_investment_cash = revenue * margin
            growth_investment = 0.0
            if incremental_roic is not None:
                roic = float(incremental_roic)
                if roic <= 0:
                    raise ValueError("incremental_after_tax_roic must be positive")
                incremental_cash = max(0.0, pre_growth_investment_cash - prior_owner_cash)
                growth_investment = incremental_cash / roic
            owner_cash = pre_growth_investment_cash - growth_investment
            present_value_m += owner_cash / (1 + discount_rate) ** year
            prior_owner_cash = pre_growth_investment_cash
        present_value_m += owner_cash * terminal_multiple / (1 + discount_rate) ** years
        return present_value_m * 1_000_000 / shares

    def unit_nav(case: dict) -> float:
        units = float(model["units"])
        gross_value = units * float(case["value_per_unit"])
        realization = float(case.get("realization_probability", 1.0))
        friction = float(case.get("friction_pct", 0.0))
        claim = float(case.get("economic_claim_pct", 1.0))
        return gross_value * realization * (1 - friction) * claim / shares

    def project_option(case: dict) -> float:
        success_value_m = float(case["success_value_m"])
        probability = float(case["success_probability"])
        ownership = float(case.get("ownership_pct", 1.0))
        remaining_cost_m = float(case.get("remaining_cost_m", 0.0))
        value_m = success_value_m * probability * ownership - remaining_cost_m
        return value_m * 1_000_000 / shares

    calculators = {
        "revenue_owner_cash_dcf": revenue_dcf,
        "reinvestment_return_dcf": revenue_dcf,
        "unit_nav": unit_nav,
        "milestone_project_option": project_option,
    }
    if model_type not in calculators:
        raise ValueError(f"unsupported driver_model type: {model_type}")
    values = {key: calculators[model_type](scenarios[key]) for key in COMPONENT_RANGE_KEYS}
    if not values["low"] <= values["base"] <= values["high"]:
        raise ValueError("driver_model range must satisfy low <= base <= high")
    return {key: round(value, 2) for key, value in values.items()}


def resolve_share_count(inputs: dict | None) -> float | None:
    """Return absolute share count for $/share math.

    `inputs.shares_outstanding` must be the absolute share count (e.g. 361037249).
    If it was mistakenly stored in millions and matches `shares_outstanding_m`,
    expand by 1e6 so total_value_m / shares does not produce multi-million $/share.
    """
    inputs = inputs or {}
    shares = inputs.get("shares_outstanding")
    shares_m = inputs.get("shares_outstanding_m")
    if shares is None and shares_m is None:
        return None
    if shares is not None and shares_m is not None:
        shares_f, shares_m_f = float(shares), float(shares_m)
        if shares_m_f > 0 and abs(shares_f - shares_m_f) < 1e-6 and shares_f < 100_000:
            return shares_m_f * 1_000_000
        return shares_f
    if shares_m is not None and shares is None:
        return float(shares_m) * 1_000_000
    return float(shares) if shares is not None else None


def _component_range_per_share(component: dict, shares: float | None) -> dict[str, float]:
    """Return a component's low/base/high range per share.

    Direct per-share ranges are preferred. Total-value ranges are supported so
    the same schema works for operating companies, funds, banks, and asset
    owners without forcing a synthetic per-share input upstream.
    """
    valuation = component.get("valuation") or {}
    if valuation.get("driver_model"):
        return _driver_component_range_per_share(valuation, shares)
    basis = valuation.get("basis", "per_share")
    missing = [key for key in COMPONENT_RANGE_KEYS if valuation.get(key) is None]
    if missing:
        raise ValueError(f"component {component.get('id', '?')} missing valuation.{', '.join(missing)}")
    if basis == "per_share":
        values = {key: float(valuation[key]) for key in COMPONENT_RANGE_KEYS}
    elif basis == "total_value_m":
        if not shares or shares <= 0:
            raise ValueError(f"component {component.get('id', '?')} total_value_m requires inputs.shares_outstanding")
        values = {key: float(valuation[key]) * 1_000_000 / float(shares) for key in COMPONENT_RANGE_KEYS}
    else:
        raise ValueError(f"component {component.get('id', '?')} has unsupported valuation basis: {basis}")
    if not values["low"] <= values["base"] <= values["high"]:
        raise ValueError(f"component {component.get('id', '?')} range must satisfy low <= base <= high")
    return {key: round(value, 2) for key, value in values.items()}


def compute_component_valuation(data: dict) -> dict | None:
    """Compute a universal, complete component valuation when supplied.

    Raw low/base/high estimates remain accepted as migration inputs, but the
    proof-first universal contract excludes them unless `calculation_proof`
    deterministically reproduces the outputs. This supports operating
    companies, banks, funds, pre-profit businesses, real assets, and holding
    companies without allowing an unsupported range to become decision-grade.
    """
    schedule = data.get("component_valuation")
    if not isinstance(schedule, dict):
        return None
    components = schedule.get("components") or []
    if not components:
        raise ValueError("component_valuation requires components[]")
    if not schedule.get("all_material_components_identified"):
        raise ValueError("component_valuation requires all_material_components_identified: true")

    shares = resolve_share_count(data.get("inputs") or {})
    price = (data.get("inputs") or {}).get("price")
    seen_ids: set[str] = set()
    seen_keys: set[str] = set()
    totals = {key: 0.0 for key in COMPONENT_RANGE_KEYS}
    additive: list[dict] = []
    embedded: list[dict] = []

    for component in components:
        component_id = component.get("id")
        overlap_key = component.get("overlap_key")
        if not component_id or not overlap_key:
            raise ValueError("every component requires id and overlap_key")
        if component_id in seen_ids or overlap_key in seen_keys:
            raise ValueError(f"duplicate component id or overlap_key: {component_id}/{overlap_key}")
        seen_ids.add(component_id)
        seen_keys.add(overlap_key)
        if not component.get("label") or not component.get("category"):
            raise ValueError(f"component {component_id} requires label and category")
        valuation = component.get("valuation") or {}
        if not valuation.get("method") or not valuation.get("evidence"):
            raise ValueError(f"component {component_id} requires valuation.method and valuation.evidence")
        values = _component_range_per_share(component, shares)
        treatment = component.get("treatment", "additive")
        if treatment not in ("additive", "embedded"):
            raise ValueError(f"component {component_id} treatment must be additive or embedded")
        row = {
            "id": component_id,
            "label": component["label"],
            "category": component["category"],
            "overlap_key": overlap_key,
            "treatment": treatment,
            "included_in_component_id": component.get("included_in_component_id"),
            "method": valuation["method"],
            "valuation_status": valuation.get("valuation_status"),
            "calculation_proof": valuation.get("calculation_proof"),
            "evidence_tier": valuation.get("evidence_tier", "analyst_estimate"),
            "evidence": valuation["evidence"],
            "cross_check": valuation.get("cross_check"),
            "driver_model_type": (valuation.get("driver_model") or {}).get("type"),
            "driver_model": valuation.get("driver_model"),
            "assumption_summary": valuation.get("assumption_summary"),
            "falsifier": valuation.get("falsifier"),
            "scenario_assumptions": (valuation.get("driver_model") or {}).get("scenarios"),
            "low_per_share": values["low"],
            "base_per_share": values["base"],
            "high_per_share": values["high"],
        }
        if treatment == "embedded":
            parent = component.get("included_in_component_id")
            if not parent:
                raise ValueError(f"embedded component {component_id} requires included_in_component_id")
            embedded.append(row)
        else:
            additive.append(row)
            for key in COMPONENT_RANGE_KEYS:
                totals[key] += values[key]

    additive_ids = {row["id"] for row in additive}
    for row in embedded:
        if row["included_in_component_id"] not in additive_ids:
            raise ValueError(f"embedded component {row['id']} must point to an additive component")

    raw_total = {key: round(value, 2) for key, value in totals.items()}
    total = floor_equity_value_range(raw_total, ndigits=2)
    floor_applied = any(raw_total[key] < 0 for key in COMPONENT_RANGE_KEYS)
    output = {
        "status": "complete",
        "decision_rule": (
            "Use the complete low/base/high component schedule. Embedded components are estimated "
            "but not added twice. Security equity value per share is floored at 0 (limited liability)."
        ),
        "all_material_components_identified": True,
        "additive_components": additive,
        "embedded_components": embedded,
        "total_equity_value_per_share": total,
        "material_component_count": len(components),
        "additive_component_count": len(additive),
        "embedded_component_count": len(embedded),
    }
    if floor_applied:
        output["total_equity_value_per_share_pre_floor"] = raw_total
        output["equity_liability_floor"] = 0.0
    if price is not None:
        output["market_price_per_share"] = float(price)
        upside = {
            key: round((total[key] / float(price) - 1) * 100, 1) for key in COMPONENT_RANGE_KEYS
        }
        # Guardrail: multi-million % gaps almost always mean shares were in millions.
        if any(abs(v) > 50_000 for v in upside.values()):
            output["upside_downside_pct_invalid"] = upside
            output["upside_downside_pct"] = None
            output["upside_sanity_error"] = (
                "Suppressed absurd upside/downside vs price; check inputs.shares_outstanding units"
            )
        else:
            output["upside_downside_pct"] = upside
    data["component_valuation_results"] = output
    return output


def build_component_review_queue(data: dict) -> dict | None:
    """Create structured, component-level work for an investment committee.

    This deliberately assigns review *questions*, not fictional investor votes.
    A rater must still supply an evidence-backed accept/challenge/reject finding
    in a committee record before the queue is considered closed.
    """
    result = data.get("component_valuation_results") or {}
    if result.get("status") != "complete":
        return None
    items = []
    for component in [*(result.get("additive_components") or []), *(result.get("embedded_components") or [])]:
        low, base, high = (component["low_per_share"], component["base_per_share"], component["high_per_share"])
        width = round((high - low) / max(abs(base), 0.01) * 100, 1)
        category = component.get("category", "")
        items.append({
            "component_id": component["id"],
            "label": component["label"],
            "treatment": component["treatment"],
            "range_per_share": {"low": low, "base": base, "high": high},
            "range_width_pct_of_base": width,
            "evidence_tier": component.get("evidence_tier"),
            "recommended_raters": COMPONENT_REVIEW_ROUTING.get(category, ["pabrai", "greenblatt"]),
            "mandatory_checks": [
                "Is the valuation method appropriate for this economic claim?",
                "Is the security's ownership claim and economic-unit denominator reconciled correctly?",
                "Does the evidence support the low/base/high range and its timing?",
                "Are comparable assets truly like-for-like after production, contract, location, capital, ownership, and realization adjustments?",
                "For an option, are success probability, time to realization, and remaining owner-funded capital explicit?",
                "Is the component additive, or already embedded in another component?",
                "What observation would move the base estimate materially?",
            ],
            "status": "open",
        })
    queue = {
        "status": "ready_for_committee_review",
        "decision_rule": "Each assigned rater records accept, challenge, or reject with a proposed range and evidence. The aggregator may not silently average disputed ranges.",
        "items": items,
    }
    data["component_review_queue"] = queue
    return queue


def infer_minimal_component_valuation(data: dict) -> dict | None:
    """Fallback for any security with an existing full/scenario valuation.

    This is intentionally a one-component operating estimate, not a claim that
    the issuer has no other material assets. It gives every covered security a
    compatible output while signalling that an explicit schedule is required
    before asset-level conclusions can be made.
    """
    if data.get("component_valuation"):
        return None
    method = data.get("method")
    inputs, base = data.get("inputs") or {}, (data.get("scenarios") or {}).get("base") or {}
    if method == "yield_curve" and base.get("payoff") is not None:
        value = float(base["payoff"])
        output = {
            "status": "inferred_minimal",
            "decision_rule": "Dated-payoff fallback. Add an explicit component_valuation schedule before drawing asset-level conclusions.",
            "all_material_components_identified": False,
            "additive_components": [{
                "id": "dated_payoff_fallback",
                "label": "Dated payoff (fallback)",
                "category": "dated_payoff",
                "treatment": "additive",
                "method": "dated_payoff",
                "evidence_tier": "model_input",
                "evidence": "scenarios.base.payoff",
                "low_per_share": value,
                "base_per_share": value,
                "high_per_share": value,
            }],
            "embedded_components": [],
            "total_equity_value_per_share": {key: value for key in COMPONENT_RANGE_KEYS},
            "material_component_count": 1,
            "additive_component_count": 1,
            "embedded_component_count": 0,
        }
        if inputs.get("price") is not None:
            output["market_price_per_share"] = float(inputs["price"])
            upside = round((value / float(inputs["price"]) - 1) * 100, 1)
            output["upside_downside_pct"] = {key: upside for key in COMPONENT_RANGE_KEYS}
        data["component_valuation_results"] = output
        return output
    if method not in ("full", "scenario"):
        return None
    fcf0 = inputs.get("fcf_per_share") or inputs.get("per_share")
    if fcf0 is None or not base:
        return None
    g1 = float(base.get("growth_y1_5", base.get("growth", 0.0)))
    g2 = float(base.get("growth_y6_end", base.get("growth_y6_10", g1)))
    exit_multiple = float(base.get("exit_pfcf_end", base.get("exit_pfcf_y10", base.get("exit_multiple", 15))))
    values = {
        "low": pv_stream(float(fcf0), g1, g2, exit_multiple, 0.12),
        "base": pv_stream(float(fcf0), g1, g2, exit_multiple, 0.10),
        "high": pv_stream(float(fcf0), g1, g2, exit_multiple, 0.08),
    }
    output = {
        "status": "inferred_minimal",
        "decision_rule": "Operating-only fallback. Add an explicit component_valuation schedule before drawing asset-level conclusions.",
        "all_material_components_identified": False,
        "additive_components": [{
            "id": "operating_business_fallback",
            "label": "Operating business (fallback)",
            "category": "operating_business",
            "treatment": "additive",
            "method": "owner_cash_dcf",
            "evidence_tier": "model_input",
            "evidence": "inputs.fcf_per_share and scenarios.base",
            **{f"{key}_per_share": round(value, 2) for key, value in values.items()},
        }],
        "embedded_components": [],
        "total_equity_value_per_share": {key: round(value, 2) for key, value in values.items()},
        "material_component_count": 1,
        "additive_component_count": 1,
        "embedded_component_count": 0,
    }
    if inputs.get("price") is not None:
        output["market_price_per_share"] = float(inputs["price"])
        output["upside_downside_pct"] = {
            key: round((values[key] / float(inputs["price"]) - 1) * 100, 1) for key in COMPONENT_RANGE_KEYS
        }
    data["component_valuation_results"] = output
    return output


def compute_separated_valuation_views(data: dict) -> dict | None:
    """Compute non-overlapping operating, asset, and expectations views."""
    methodology = data.get("valuation_methodology") or {}
    if methodology.get("mode") != "separated_views":
        return None
    inputs = data.get("inputs") or {}
    price = inputs.get("price")
    fcf0 = inputs.get("fcf_per_share")
    base = (data.get("scenarios") or {}).get("base") or {}
    if price is None or fcf0 is None or not base:
        raise ValueError("separated_views requires price, fcf_per_share, and a base scenario")
    years = int(methodology.get("horizon_years", LAWRENCE_HORIZON_YEARS))
    if years != LAWRENCE_HORIZON_YEARS:
        raise ValueError(f"separated_views horizon must match engine horizon ({LAWRENCE_HORIZON_YEARS})")

    asset_ledger = methodology.get("asset_ledger") or []
    component_result = data.get("component_valuation_results")
    seen: set[str] = set()
    supported = 0.0
    for item in asset_ledger:
        key = item.get("overlap_key")
        if not key:
            raise ValueError("every asset_ledger item requires overlap_key")
        if key in seen:
            raise ValueError(f"duplicate asset_ledger overlap_key: {key}")
        seen.add(key)
        evidence_status = item.get("evidence_status")
        include = bool(item.get("include_in_decision_value"))
        value = item.get("value_per_share")
        if include and evidence_status != "supported":
            raise ValueError(f"unsupported asset cannot enter decision value: {key}")
        if include:
            if value is None:
                raise ValueError(f"included asset requires value_per_share: {key}")
            supported += float(value)

    g1 = float(base["growth_y1_5"])
    g2 = float(base.get("growth_y6_end", base.get("growth_y6_10")))
    exit_mult = float(base.get("exit_pfcf_end", base.get("exit_pfcf_y10")))
    hurdles = methodology.get("entry_hurdles_pct") or [10, 12, 15]
    entry_prices = {
        f"{float(h):g}%": round(pv_stream(float(fcf0), g1, g2, exit_mult, float(h) / 100, years) + supported, 2)
        for h in hurdles
    }
    segment_result = compute_segment_overlay(data)
    views = {
        "decision_rule": "Do not average operating returns, component value, and reverse expectations.",
        "operating": {
            "owner_cash_per_share": float(fcf0),
            "scenario_returns_pct": {k: v.get("return_pct") for k, v in (data.get("results") or {}).items()},
            "segment_cross_check": segment_result,
        },
        "assets": {
            "legacy_supported_decision_value_per_share": round(supported, 2),
            "ledger": asset_ledger,
            "legacy_non_supported_count": sum(1 for x in asset_ledger if x.get("evidence_status") != "supported"),
        },
        "components": component_result,
        "reverse_expectations": {
            "price": float(price),
            "exit_multiple": exit_mult,
            "constant_owner_cash_growth_required_pct": _constant_growth_required(float(price), float(fcf0), exit_mult, years),
            "warning": "Required growth is a diagnostic, not a forecast.",
        },
        "entry_prices": entry_prices,
    }
    data["valuation_views"] = views
    data["synthesis"] = {
        "status": "disabled_separated_views",
        "reason": "Correlated operating paths and unsupported asset options must not be averaged into a consensus return.",
    }
    # Keep qualitative research context without leaving a second numerical
    # answer that a downstream agent could mistake for the stance gate.
    data.pop("results_growth_theory", None)
    growth_explanation = data.get("growth_explanation")
    if isinstance(growth_explanation, dict):
        growth_explanation["status"] = "context_only_separated_views"
        growth_explanation["decision_use"] = False
    data["legacy_output_policy"] = {
        "results_lawrence_legacy": "compatibility alias of the current operating scenarios; not a separate valuation",
        "growth_explanation": "qualitative scenario context only; legacy numerical paths do not enter the decision",
        "nav_overlay": "audit history only when decision_use is false",
        "option_scan": "inventory disclosure only; asset value enters only through valuation_views.assets",
    }
    lens_consensus = data.get("lens_consensus")
    if isinstance(lens_consensus, dict):
        lens_consensus["in_base_irr"] = False
        lens_consensus["disclaimer"] = (
            "Advisory persona context only. It does not replace the operating stance gate "
            "or enter valuation_views."
        )
    return views


def compute_ai_overlay_rows(data: dict, lawrence_results: dict) -> list[dict]:
    """Extra valuation bridge rows — not stance gate unless noted."""
    rows: list[dict] = []
    ai = data.get("ai_overlay") or {}
    price = (data.get("inputs") or {}).get("price")
    method = data.get("method", "full")

    bull = ai.get("ai_inflection_bull") or {}
    fcf0 = bull.get("fcf_per_share_y0")
    if price and fcf0 is not None:
        sc = {
            "growth_y1_5": bull.get("growth_y1_5", 0.15),
            "growth_y6_10": bull.get("growth_y6_10", 0.10),
            "exit_pfcf_y10": bull.get("exit_pfcf_y10", 28),
        }
        pct = run_full_scenario(float(price), float(fcf0), sc, years=LAWRENCE_HORIZON_YEARS)["return_pct"]
        g1, g2, ex = sc["growth_y1_5"], sc["growth_y6_10"], sc["exit_pfcf_y10"]
        rows.append(
            {
                "case": "AI inflection",
                "method": f"{method} (normalized FCF)",
                "key_inputs": f"FCF₀=${fcf0} g1={g1*100:.0f}% g2={g2*100:.0f}% exit={ex:.0f}×",
                "return_pct": pct,
                "stance_gate": False,
                "notes": bull.get("fcf_y0_note", "[Assumption] post-capex normalization"),
            }
        )
        ai.setdefault("ai_inflection_bull", {})["computed_return_pct"] = pct

    stress = ai.get("capex_stress_2026") or ai.get("capex_stress") or {}
    trough = stress.get("implied_fcf_per_share")
    if trough is not None and price:
        rows.append(
            {
                "case": "Capex stress Y0",
                "method": "illustrative trough",
                "key_inputs": f"OCF {stress.get('ocf_bn_assumption')}B − capex {stress.get('capex_bn')}B",
                "return_pct": None,
                "display": f"FCF ~${trough}/sh (not {RETURN_LABEL})",
                "stance_gate": False,
            }
        )

    return rows


def compute_growth_theory_results(data: dict, price: float, fcf0: float) -> dict:
    """Optional JSON reference: theory-implied + falsifier-adjusted IRR (not primary display)."""
    ge = data.get("growth_explanation")
    if not ge or data.get("method") not in ("full", "scenario"):
        return {}

    enrich_growth_explanation(data, load_filing_facts(data.get("ticker", "")))
    out: dict[str, dict] = {}

    for path_key in ("theory_implied", "falsifier_adjusted"):
        sc = theory_scenario(data, path_key)
        if price and fcf0 is not None:
            out[path_key] = run_full_scenario(price, fcf0, sc, years=LAWRENCE_HORIZON_YEARS)

    if out:
        data["results_growth_theory"] = {k: {"return_pct": v["return_pct"]} for k, v in out.items()}
    return out


def apply_primary_implied_return(data: dict, lawrence_base_pct: float | None, return_label: str) -> None:
    """Primary IRR = Lawrence scenarios.base (display and stance)."""
    data["implied_return"] = {
        "base_pct": lawrence_base_pct,
        "label": return_label,
        "display": f"{lawrence_base_pct}% (base)" if lawrence_base_pct is not None else "pending",
    }

    gate = data.get("optionality_gate")
    if gate:
        gate["primary_metric"] = "lawrence_base"
        gate["primary_label"] = return_label
        gate["primary_return_pct"] = lawrence_base_pct


def growth_theory_bridge_rows(data: dict) -> list[dict]:
    gt = data.get("results_growth_theory") or {}
    ge = data.get("growth_explanation") or {}
    rows: list[dict] = []
    ti = gt.get("theory_implied", {}).get("return_pct")
    fa = gt.get("falsifier_adjusted", {}).get("return_pct")
    legacy = data.get("implied_return", {}).get("lawrence_legacy_pct")
    theory = ge.get("theory_implied") or {}
    fals = ge.get("falsifier_adjusted") or {}

    if ti is not None and theory:
        g1, g2 = theory.get("y1_5", 0) * 100, theory.get("y6_10", 0) * 100
        rows.append(
            {
                "case": "Theory-implied",
                "method": "segment-derived growth",
                "key_inputs": f"Y1-5 {g1:.1f}% Y6-10 {g2:.1f}% ({theory.get('derivation', '')})",
                "return_pct": ti,
                "stance_gate": False,
                "notes": "Bottom-up from segment_build",
            }
        )
    if fa is not None and fals:
        g1, g2 = fals.get("y1_5", 0) * 100, fals.get("y6_10", 0) * 100
        trig = len(fals.get("triggered") or [])
        rows.append(
            {
                "case": "Falsifier-adjusted",
                "method": "theory + filing falsifiers",
                "key_inputs": f"Y1-5 {g1:.1f}% Y6-10 {g2:.1f}%; {trig} triggered",
                "return_pct": fa,
                "stance_gate": True,
                "notes": "Primary IRR for display and stance",
            }
        )
    if legacy is not None:
        rows.append(
            {
                "case": "Lawrence legacy",
                "method": "historical scenarios.base",
                "key_inputs": "Pre-theory-derivation ledger",
                "return_pct": legacy,
                "stance_gate": False,
                "notes": "Reference only",
            }
        )
    return rows


def load_classification(ticker: str) -> dict:
    if not CLASS_PATH.exists():
        return {}
    data = json.loads(CLASS_PATH.read_text(encoding="utf-8"))
    return data.get(ticker, {})


def compute_valuation(data: dict) -> dict:
    method = data.get("method", data.get("irr_method", "full"))
    inputs = data.get("inputs", {})
    price = inputs.get("price")
    class_in = data.get("classification_inputs", {})
    moat = class_in.get("moat") or load_classification(data.get("ticker", "")).get("moat", "unproven")
    dhando = class_in.get("dhando") or load_classification(data.get("ticker", "")).get("dhando", "pending")

    results: dict[str, dict] = {}

    if method == "full":
        fcf0 = inputs.get("fcf_per_share")
        if price is None or fcf0 is None:
            raise ValueError("full method requires inputs.price and inputs.fcf_per_share")
        for name, sc in data.get("scenarios", {}).items():
            results[name] = run_full_scenario(price, fcf0, sc)
        return_label = RETURN_LABEL
        data["lawrence_horizon_years"] = LAWRENCE_HORIZON_YEARS
    elif method == "scenario":
        ps = inputs.get("per_share") or inputs.get("fcf_per_share")
        if price is None or ps is None:
            raise ValueError("scenario method requires inputs.price and inputs.per_share")
        for name, sc in data.get("scenarios", {}).items():
            results[name] = run_scenario_method(price, ps, sc)
        return_label = RETURN_LABEL
        data["lawrence_horizon_years"] = LAWRENCE_HORIZON_YEARS
    elif method == "yield_curve":
        for name, sc in data.get("scenarios", {}).items():
            results[name] = run_yield_curve(sc)
        return_label = "annualized return"
    elif method == "pending":
        results = {}
        return_label = "pending"
    else:
        raise ValueError(f"Unknown method: {method}")

    base_pct = results.get("base", {}).get("return_pct") if results else None
    data["method"] = method
    data["results_lawrence_legacy"] = {k: {"return_pct": v["return_pct"]} for k, v in results.items()}
    data["results"] = dict(data["results_lawrence_legacy"])

    fcf0 = inputs.get("fcf_per_share") or inputs.get("per_share")
    separated_mode = (data.get("valuation_methodology") or {}).get("mode") == "separated_views"
    if method in ("full", "scenario") and data.get("growth_explanation") and not separated_mode:
        compute_growth_theory_results(data, float(price) if price else 0, float(fcf0) if fcf0 else 0)

    if method in ("full", "scenario"):
        sb = data.get("segment_build")
        if isinstance(sb, dict):
            sb["horizon_years"] = LAWRENCE_HORIZON_YEARS

    apply_primary_implied_return(data, base_pct, return_label)
    data["stance_proposal"] = propose_stance(base_pct, moat, dhando, method, data=data)

    data["overlay_results"] = compute_ai_overlay_rows(data, results)
    compute_component_valuation(data) or infer_minimal_component_valuation(data)
    build_economic_value_analysis(data)
    build_component_review_queue(data)
    build_universal_valuation_contract(data)
    separated_views = compute_separated_valuation_views(data)

    # Lawrence yield_curve / holdco dated payoffs keep scenarios.base as stance gate.
    if method not in ("yield_curve",) and separated_views is None:
        compute_synthesis(data)
        synthesis_pct = (data.get("synthesis") or {}).get("total_synthesis_pct")
        if synthesis_pct is not None:
            ir = data.setdefault("implied_return", {})
            ir["base_pct"] = synthesis_pct
            ir["synthesis_pct"] = synthesis_pct
            ir["label"] = SYNTHESIS_LABEL
            ir["display"] = f"{synthesis_pct}% (total synthesis)"
            data["stance_proposal"] = propose_stance(synthesis_pct, moat, dhando, method, data=data)
    elif separated_views is not None:
        # One primary operating return; other views remain separate diagnostics.
        apply_primary_implied_return(data, base_pct, return_label)
        gate = data.get("optionality_gate")
        if isinstance(gate, dict):
            gate["primary_return_pct"] = base_pct
        data["stance_proposal"] = propose_stance(base_pct, moat, dhando, method, data=data)

    ticker = data.get("ticker", "")
    if ticker in AI_HYPERSCALERS and not data.get("ai_overlay"):
        data.setdefault("ai_overlay", {})["status"] = "missing — run ai_infrastructure_valuation.md"

    data["as_of"] = data.get("as_of") or str(date.today())
    return data


def valuation_path_for_ticker(ticker: str) -> Path:
    return ROOT / ticker / "research" / "valuation.json"


def migrate_irr_model(path: Path) -> dict | None:
    """Load legacy irr_model.json shape."""
    legacy = path.parent / "irr_model.json"
    if not path.exists() and legacy.exists():
        raw = json.loads(legacy.read_text(encoding="utf-8"))
        migrated = {
            "ticker": raw.get("ticker"),
            "as_of": raw.get("as_of", str(date.today())),
            "method": raw.get("irr_method", "full"),
            "lawrence_bucket": raw.get("lawrence_bucket"),
            "inputs": raw.get("inputs", {}),
            "scenarios": raw.get("scenarios", {}),
            "classification_inputs": {},
        }
        if raw.get("stance_mapping"):
            migrated["stance_proposal"] = {
                "suggested": raw["stance_mapping"].get("suggested_stance"),
                "irr_band": raw["stance_mapping"].get("base_irr_band"),
                "override_reason": None,
            }
        return migrated
    return None


def load_valuation(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    migrated = migrate_irr_model(path)
    if migrated:
        return migrated
    raise FileNotFoundError(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Marvin valuation + stance proposal")
    parser.add_argument("--ticker", help="Ticker symbol")
    parser.add_argument("--file", type=Path, help="Path to valuation.json")
    parser.add_argument("--write", action="store_true", help="Write computed results back to file")
    parser.add_argument("--json", action="store_true", help="Print full JSON output")
    args = parser.parse_args()

    if args.file:
        path = args.file
    elif args.ticker:
        path = valuation_path_for_ticker(args.ticker.strip())
    else:
        parser.error("Provide --ticker or --file")

    data = load_valuation(path)
    if not data.get("classification_inputs"):
        ticker = data.get("ticker") or args.ticker
        if ticker:
            data["classification_inputs"] = {
                k: load_classification(ticker).get(k)
                for k in ("moat", "dhando", "archetype", "cycle")
            }

    prior = data.get("stance_proposal") or {}
    prior_override = prior.get("override_reason")
    prior_approved = data.get("approved_stance") or prior.get("approved_stance")
    prior_human = data.get("human_review")

    computed = compute_valuation(data)

    if prior_override:
        computed.setdefault("stance_proposal", {})["override_reason"] = prior_override
    if prior_approved:
        computed["approved_stance"] = prior_approved
        computed.setdefault("stance_proposal", {})["approved_stance"] = prior_approved
    if prior_human:
        computed["human_review"] = prior_human

    if args.write:
        path = path.resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(computed, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {path.relative_to(ROOT)}")
        ticker_name = computed.get("ticker") or (path.parent.parent.name if path.parent.name == "research" else "")
        if ticker_name:
            sys.path.insert(0, str(ROOT / "_system" / "scripts"))
            try:
                from darwin.pit import archive_valuation_on_write
                from darwin.research_events import append_event

                archive_valuation_on_write(path.parent.parent, computed)
                if computed.get("as_of"):
                    append_event(
                        ticker_name,
                        "valuation_refresh",
                        str(computed["as_of"])[:10],
                        path.relative_to(ROOT).as_posix(),
                    )
            except ImportError:
                pass

    if args.json or not args.write:
        print(json.dumps(computed, indent=2))


if __name__ == "__main__":
    main()
