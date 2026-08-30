#!/usr/bin/env python3
"""Apply an evidence-backed pricing model and produce actionable entry prices."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from marvin_valuation import compute_valuation  # noqa: E402
from economic_value_framework import build_economic_value_analysis  # noqa: E402
from calculation_proof import floor_equity_value_range  # noqa: E402
from decision_authority import load_contract, load_route, read_json  # noqa: E402
from universal_valuation_contract import entry_price_for_contract_valuation  # noqa: E402

HURDLES = (0.10, 0.12, 0.15, 0.20)
VALUE_CASES = ("low", "base", "high")


def build_contract_pricing(ticker: str, as_of: str | None = None) -> dict:
    """Price a decision-grade contract only when dated forward economics exist.

    Present values are already discounted.  They remain useful for intrinsic
    value and margin-of-safety comparisons, but they cannot be discounted a
    second time into a purported hurdle entry price.
    """
    ticker = ticker.upper()
    research = ROOT / ticker / "research"
    valuation = read_json(research / "valuation.json")
    contract_source, contract = load_contract(research, valuation)
    if contract.get("status") != "decision_grade":
        raise ValueError(f"{ticker}: contract pricing requires decision_grade")
    market = contract.get("market") or {}
    value = floor_equity_value_range(
        (contract.get("valuation") or {}).get("value_per_share") or {},
        ndigits=4,
    )
    contract_valuation = contract.get("valuation") or {}
    output_basis = str(contract_valuation.get("output_basis") or "present_value_today")
    price = market.get("price_per_share")
    if price is None or any(value.get(case) is None for case in VALUE_CASES):
        raise ValueError(f"{ticker}: price and low/base/high contract values are required")
    entries = {
        case: {
            f"{int(hurdle * 100)}pct": (
                round(entry, 2) if entry is not None else None
            )
            for hurdle in HURDLES
            for entry in [entry_price_for_contract_valuation(contract_valuation, case, hurdle)]
        }
        for case in VALUE_CASES
    }
    primary_entry = entries["base"]["15pct"]
    pricing_status = "available" if primary_entry is not None else "unavailable"
    unavailable_reason = (
        None
        if pricing_status == "available"
        else (
            "present_value_today has no dated future payoff or cash-flow schedule; "
            "discounting it again would double-discount intrinsic value"
            if output_basis == "present_value_today"
            else "dated forward payoff or cash-flow inputs are incomplete"
        )
    )
    legacy_audit = contract.get("legacy_audit") or {
        "actionable": False,
        "status": "audit_only",
        "annualized_return_at_price_pct": contract_valuation.get("annualized_return_at_price_pct") or {},
        "note": "Legacy contract metrics retained for audit only; they do not set hurdle prices.",
    }
    legacy_audit = {**legacy_audit, "actionable": False, "status": "audit_only"}
    route = load_route(research, valuation, contract)
    pricing = {
        "schema_version": "3.0",
        "ticker": ticker,
        "as_of": (as_of or contract.get("as_of") or date.today().isoformat())[:10],
        "status": pricing_status,
        "unavailable_reason": unavailable_reason,
        "actionable": False,
        "authority": "valuation_contract",
        "contract_source": contract_source,
        "contract_status": contract.get("status"),
        "model_level": contract.get("model_level"),
        "price": float(price),
        "price_source": market.get("price_source") or (valuation.get("inputs") or {}).get("price_source"),
        "price_as_of": market.get("price_as_of") or (contract.get("dates") or {}).get("price_as_of"),
        "output_basis": output_basis,
        "component_value_per_share": value,
        "present_value_today_per_share": contract_valuation.get("present_value_today_per_share"),
        "future_payoff_per_share": contract_valuation.get("future_payoff_per_share"),
        "forward_cashflow_schedule": contract_valuation.get("forward_cashflow_schedule"),
        "forward_return_at_price_pct": contract_valuation.get("forward_return_at_price_pct") or {},
        "forward_return_status": contract_valuation.get("forward_return_status") or "withheld",
        "required_return_pct": contract_valuation.get("required_return_pct"),
        "margin_of_safety_pct": contract_valuation.get("margin_of_safety_pct") or {},
        "entry_prices_by_hurdle_and_case": entries,
        "primary_entry_price_15pct_base": primary_entry,
        "entry_price_status": pricing_status,
        "entry_price_method": (
            "discounted_dated_future_payoff"
            if output_basis == "future_payoff" and pricing_status == "available"
            else (
                "npv_of_forward_cashflow_schedule"
                if output_basis == "forward_cashflow_schedule" and pricing_status == "available"
                else None
            )
        ),
        "legacy_audit": legacy_audit,
        "decision": "owner_review_required",
        "pricing_conclusion": (
            "Hurdle prices are derived only from dated future cash flows or a dated payoff; they do not constitute a capital decision."
            if pricing_status == "available"
            else "No hurdle entry price is published because this contract contains a present value without its dated forward cash flows."
        ),
        "falsifiers": (contract.get("monitoring") or {}).get("falsifiers") or [],
        "power_zone": {"profile_id": route.get("profile_id"), "label": route.get("label"), "input_hash": route.get("input_hash")},
    }
    (research / "pricing_analysis.json").write_text(json.dumps(pricing, indent=2) + "\n", encoding="utf-8")
    return pricing


def deep_merge(target: dict, patch: dict) -> dict:
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            deep_merge(target[key], value)
        else:
            target[key] = value
    return target


def implied_constant_growth(price: float, fcf0: float, exit_multiple: float, years: int) -> float | None:
    if price <= 0 or fcf0 <= 0:
        return None
    lo, hi = -0.25, 1.0
    for _ in range(240):
        growth = (lo + hi) / 2
        fcf = fcf0
        cashflows = []
        for _year in range(1, years + 1):
            fcf *= 1 + growth
            cashflows.append(fcf)
        value = sum(cashflows[:-1]) + cashflows[-1] * (1 + exit_multiple)
        if value < price:
            lo = growth
        else:
            hi = growth
    return round(100 * (lo + hi) / 2, 1)


def entry_price_for_hurdle(fcf0: float, scenario: dict, hurdle: float, years: int) -> float:
    growth_late = scenario.get("growth_y6_end", scenario.get("growth_y6_10"))
    multiple = scenario.get("exit_pfcf_end", scenario.get("exit_pfcf_y10"))
    fcf = fcf0
    pv = 0.0
    for year in range(1, years + 1):
        growth = scenario["growth_y1_5"] if year <= 5 else growth_late
        fcf *= 1 + growth
        cash = fcf if year < years else fcf * (1 + multiple)
        pv += cash / (1 + hurdle) ** year
    return round(pv, 2)


def _sum_component_cases(rows: list[dict], component_ids: list[str]) -> dict:
    by_id = {row.get("id"): row for row in rows}
    missing = [component_id for component_id in component_ids if component_id not in by_id]
    if missing:
        raise ValueError(f"economic value bridge references missing components: {', '.join(missing)}")
    return {
        case: round(sum(float(by_id[component_id].get(f"{case}_per_share") or 0) for component_id in component_ids), 2)
        for case in VALUE_CASES
    }


def build_economic_value_bridge(data: dict, config: dict) -> dict | None:
    spec = data.get("economic_value") or config.get("economic_value_bridge")
    if not spec:
        return None
    normalized = dict(spec)
    if not normalized.get("economic_claim") and config.get("economic_claim_note"):
        normalized["economic_claim"] = {
            "description": config["economic_claim_note"],
            "unit_label": "common economic unit",
            "unit_count": (data.get("inputs") or {}).get("shares_outstanding"),
            "unit_source": "valuation.inputs.shares_outstanding",
            "enterprise_to_equity_reconciliation": "The complete additive component schedule includes cash, debt, minority claims, and reserves before division by economic units.",
        }
    return build_economic_value_analysis(data, normalized)


def build_pricing_analysis(data: dict, config: dict) -> dict:
    inputs = data["inputs"]
    price, fcf0 = float(inputs["price"]), float(inputs["fcf_per_share"])
    years = int(data.get("lawrence_horizon_years") or 7)
    component = data.get("component_valuation_results") or {}
    values = floor_equity_value_range(
        component.get("total_equity_value_per_share") or {},
        ndigits=4,
    )
    base_scenario = data["scenarios"]["base"]
    exit_multiple = base_scenario.get("exit_pfcf_end", base_scenario.get("exit_pfcf_y10"))
    entry = {
        case: {f"{int(h*100)}pct": entry_price_for_hurdle(fcf0, scenario, h, years) for h in HURDLES}
        for case, scenario in data["scenarios"].items()
    }
    current_supported = sum(
        row.get("base_per_share", 0)
        for row in component.get("additive_components", [])
        if row.get("category") != "real_option"
    )
    manifest_path = ROOT / data["ticker"] / "research" / "committee_work" / data["as_of"] / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    return {
        "schema_version": "1.0",
        "as_of": data["as_of"],
        "price": price,
        "price_source": inputs.get("price_source"),
        "economic_units": inputs.get("shares_outstanding"),
        "economic_claim_note": config.get("economic_claim_note"),
        "component_value_per_share": values,
        "upside_downside_pct": component.get("upside_downside_pct"),
        "base_value_supported_by_current_or_contracted_assets": round(current_supported, 2),
        "market_price_above_current_or_contracted_value": round(price - current_supported, 2),
        "market_implied_constant_owner_cash_growth_pct": implied_constant_growth(price, fcf0, float(exit_multiple), years),
        "implied_growth_contract": f"Constant {years}-year owner-cash growth with a {exit_multiple}x terminal owner-cash multiple; diagnostic, not forecast.",
        "entry_prices_by_hurdle_and_case": entry,
        "primary_entry_price_15pct_base": entry["base"]["15pct"],
        "decision": config["decision"],
        "strongest_counter_explanation": config["strongest_counter_explanation"],
        "falsifiers": config["falsifiers"],
        "pricing_conclusion": config["pricing_conclusion"],
        "economic_value_bridge": build_economic_value_bridge(data, config),
        "committee_routing": {
            "stage": manifest.get("stage", "not_initialized"),
            "packet_hash": manifest.get("packet_hash"),
            "selected_raters": [row.get("persona") for row in manifest.get("selected_raters", [])],
            "independence_groups": [row.get("independence_group") for row in manifest.get("selected_raters", [])],
        },
    }


def markdown_report(ticker: str, data: dict, pricing: dict) -> str:
    values = pricing["component_value_per_share"]
    rows = []
    for row in (data.get("component_valuation_results") or {}).get("additive_components", []):
        rows.append(f"| {row['label']} | {row['method']} | ${row['low_per_share']:.2f} | ${row['base_per_share']:.2f} | ${row['high_per_share']:.2f} |")
    hurdles = pricing["entry_prices_by_hurdle_and_case"]
    hurdle_rows = [f"| {case.title()} | ${vals['10pct']:.2f} | ${vals['12pct']:.2f} | ${vals['15pct']:.2f} | ${vals['20pct']:.2f} |" for case, vals in hurdles.items()]
    bridge = pricing.get("economic_value_bridge") or {}
    bridge_rows = []
    for group in bridge.get("component_groups") or []:
        comparable = group.get("comparable_value_per_share") or {}
        risked = group.get("risked_present_value_per_share") or {}
        comparable_base = f"${comparable['base']:.2f}" if comparable.get("base") is not None else "n/a"
        bridge_rows.append(
            f"| {group['label']} | {group.get('valuation_basis', '')} | {comparable_base} | ${risked.get('base', 0):.2f} | {group.get('overlap_control', '')} |"
        )
    proof_rows = []
    for row in bridge.get("valuation_proof") or []:
        value = row.get("range_per_share") or {}
        comparable = ", ".join(row.get("comparable_ids") or []) or row.get("comparable_role", "n/a")
        risk = row.get("risk_and_timing") or {}
        risk_text = "n/a" if not risk else (
            (f"p={float(risk['success_probability'])*100:.1f}%; " if risk.get("success_probability") is not None else "risked range; ")
            + str(risk.get("timing_basis") or "timing in range")
        )
        proof_rows.append(
            f"| {row.get('economic_claim', '')} | {row.get('method', '')} | {comparable} | "
            f"${float(value.get('low') or 0):.2f} / ${float(value.get('base') or 0):.2f} / ${float(value.get('high') or 0):.2f} | "
            f"{risk_text} | {row.get('overlap_control', '')} | {row.get('falsifier', '')} |"
        )
    gross = bridge.get("gross_comparable_nav_per_share") or {}
    bridge_section = ""
    if bridge:
        gross_line = (
            f"Complete comparable economic NAV: **${gross['low']:.2f} / ${gross['base']:.2f} / ${gross['high']:.2f}** per share (low/base/high)."
            if gross else
            "A complete comparable NAV is not asserted; comparable marks are used only where the economic asset and ownership claim are sufficiently defined."
        )
        wisdom = "\n".join(f"- {item}" for item in bridge.get("wisdom_applied") or [])
        limitations = "\n".join(f"- {item}" for item in bridge.get("limitations") or [])
        convergence_rows = []
        for case, vals in (bridge.get("nav_convergence_entry_prices") or {}).items():
            convergence_rows.append(f"| {case.title()} | ${vals['10pct']:.2f} | ${vals['12pct']:.2f} | ${vals['15pct']:.2f} | ${vals['20pct']:.2f} |")
        convergence_section = ""
        if convergence_rows:
            convergence_section = f"""
### NAV-convergence entry prices

| Scenario | 10% | 12% | 15% | 20% |
|---|---:|---:|---:|---:|
{chr(10).join(convergence_rows)}

{bridge.get('nav_convergence_contract', '')}
"""
        bridge_section = f"""
## Economic value versus accounting value

**GAAP role:** {bridge.get('gaap_role', 'reference only')}

**Accounting reference:** {bridge.get('accounting_reference', 'not material to the valuation conclusion')}

{gross_line}

| Economic component | Comparable basis | Comparable base / share | Risked base / share | Overlap control |
|---|---|---:|---:|---|
{chr(10).join(bridge_rows)}

### Deterministic valuation proof

| Economic claim | Method | Comparable | Low / base / high | Risk / timing | Overlap control | Falsifier |
|---|---|---|---:|---|---|---|
{chr(10).join(proof_rows)}

### Investor-wisdom rules applied

{wisdom or '- None documented.'}

### Limitations

{limitations or '- None documented.'}
{convergence_section}
"""
    return f"""# {ticker} pricing analysis

**As of:** {pricing['as_of']}

**Price:** ${pricing['price']:.2f}

**Decision:** {pricing['decision']}

## Price versus component value

| Component | Method | Low | Base | High |
|---|---|---:|---:|---:|
{chr(10).join(rows)}
| **Total** |  | **${values['low']:.2f}** | **${values['base']:.2f}** | **${values['high']:.2f}** |

Base value versus price: **{pricing['upside_downside_pct']['base']:.1f}%**. Current or contracted operating and financial assets support approximately **${pricing['base_value_supported_by_current_or_contracted_assets']:.2f}** per share; the market asks investors to pay another **${pricing['market_price_above_current_or_contracted_value']:.2f}** for growth, inventory, projects, or scarcity.

{bridge_section}

## What the price implies

At the stated terminal multiple, the price requires approximately **{pricing['market_implied_constant_owner_cash_growth_pct']:.1f}%** constant annual owner-cash growth for seven years. {pricing['implied_growth_contract']}

## Entry prices by required return

These prices are the present value of the explicit seven-year cash-flow and terminal-value scenarios at each hurdle. They are not arbitrary discounts to the current quote.

| Scenario | 10% | 12% | 15% | 20% |
|---|---:|---:|---:|---:|
{chr(10).join(hurdle_rows)}

## Decision explanation

{pricing['pricing_conclusion']}

**Strongest counter-explanation:** {pricing['strongest_counter_explanation']}

**Committee routing:** {pricing['committee_routing']['stage']} — {', '.join(pricing['committee_routing']['selected_raters']) or 'not initialized'}

**Falsifiers:**

{chr(10).join('- ' + item for item in pricing['falsifiers'])}

## Economic claim

{pricing['economic_claim_note']}
"""


def can_seed(data: dict) -> bool:
    """A default config is only honest when the valuation model is complete."""
    inputs = data.get("inputs") or {}
    base = (data.get("scenarios") or {}).get("base") or {}
    try:
        price_ok = float(inputs.get("price") or 0) > 0
        fcf_ok = float(inputs.get("fcf_per_share") or 0) > 0
    except (TypeError, ValueError):
        return False
    exit_ok = base.get("exit_pfcf_end") is not None or base.get("exit_pfcf_y10") is not None
    return price_ok and fcf_ok and base.get("growth_y1_5") is not None and exit_ok


def seed_default_config(ticker: str) -> Path | None:
    """Write a mechanical pricing_model.json for a ticker that lacks one.

    The seeded config never asserts a buy/sell decision. It marks the pricing
    run as machine-generated so the entry-price table exists on the dashboard
    while the decision language stays with the owner.
    """
    research = ROOT / ticker / "research"
    config_path = research / "pricing_model.json"
    if config_path.exists():
        return config_path
    valuation_path = research / "valuation.json"
    if not valuation_path.exists():
        return None
    data = json.loads(valuation_path.read_text(encoding="utf-8"))
    if not can_seed(data):
        return None
    route = data.get("valuation_method_route") or {}
    failure_modes = route.get("failure_modes") or []
    config = {
        "as_of": date.today().isoformat(),
        "seeded_by": "seed_default_config (mechanical; no analyst judgment recorded)",
        "decision": "watch_pending_owner_review",
        "strongest_counter_explanation": (
            failure_modes[0]
            if failure_modes
            else "The component schedule may overstate durable earning power; no analyst has yet argued the bear case."
        ),
        "falsifiers": failure_modes or [
            "Owner cash flow falls materially below the base scenario for two consecutive years.",
            "The component schedule fails reconciliation against the next primary filing.",
        ],
        "pricing_conclusion": (
            "Entry prices were computed mechanically from the routed power-zone profile "
            f"({route.get('label') or 'unrouted; owner-earnings default'}). "
            "They are decision inputs, not a decision; the owner must review the scenarios before acting."
        ),
        "economic_claim_note": (
            data.get("economic_claim_note")
            or "Per-share claims use fully diluted shares from valuation.inputs."
        ),
    }
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return config_path


def build(ticker: str) -> dict:
    research = ROOT / ticker / "research"
    valuation_path, config_path = research / "valuation.json", research / "pricing_model.json"
    data, config = json.loads(valuation_path.read_text(encoding="utf-8")), json.loads(config_path.read_text(encoding="utf-8"))
    deep_merge(data, config.get("valuation_patch") or {})
    data["as_of"] = config["as_of"]
    compute_valuation(data)
    pricing = build_pricing_analysis(data, config)
    data["pricing_analysis"] = pricing
    valuation_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    (research / "pricing_analysis.json").write_text(json.dumps(pricing, indent=2) + "\n", encoding="utf-8")
    report = research / f"pricing_analysis_{config['as_of']}.md"
    report.write_text(markdown_report(ticker, data, pricing), encoding="utf-8")
    return pricing


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tickers", nargs="+", type=str.upper)
    parser.add_argument(
        "--seed-default-config",
        action="store_true",
        help="Write a mechanical pricing_model.json when missing (decision language stays with the owner).",
    )
    args = parser.parse_args()
    for ticker in args.tickers:
        if args.seed_default_config:
            seeded = seed_default_config(ticker)
            if seeded is None:
                print(f"{ticker}: skipped (valuation.json missing or model incomplete; no config seeded)")
                continue
        result = build(ticker)
        print(f"{ticker}: price={result['price']} base={result['component_value_per_share']['base']} entry15={result['primary_entry_price_15pct_base']} decision={result['decision']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
