"""Shared persona-lens logic — deterministic, reads valuation.json only."""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PERSONAS_PATH = ROOT / "_system" / "lenses" / "personas.json"
UNIVERSE_STATS_PATH = ROOT / "_system" / "lenses" / "universe_percentiles.json"
REGISTRY_PATH = ROOT / "_system" / "portfolio" / "registry.json"

STANCES = ["accumulate", "hold", "watch", "pass", "pending", "silent"]
STANCE_RANK = {s: i for i, s in enumerate(["accumulate", "hold", "watch", "pass", "pending", "silent"])}


def load_json(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def load_personas() -> dict:
    data = load_json(PERSONAS_PATH) or {}
    return data


def list_tickers_with_valuation() -> list[str]:
    tickers: list[str] = []
    for p in ROOT.iterdir():
        if not p.is_dir() or p.name.startswith((".", "_")):
            continue
        if (p / "research" / "valuation.json").exists():
            tickers.append(p.name)
    return sorted(tickers)


_registry_class_cache: dict[str, dict] | None = None


def registry_classification(ticker: str) -> dict:
    """Portfolio-registry classification for a ticker ({} when absent).
    Cached module-wide so --all runs load registry.json once."""
    global _registry_class_cache
    if _registry_class_cache is None:
        registry = load_json(REGISTRY_PATH) or {}
        entries = {**(registry.get("watchlist") or {}), **(registry.get("holdings") or {})}
        _registry_class_cache = {
            name: (entry or {}).get("classification") or {}
            for name, entry in entries.items()
        }
    return _registry_class_cache.get(ticker, {})


_UNCLASSIFIED = {"", "pending", "unknown", "-"}


def _first_classified(*values):
    for value in values:
        if value is None:
            continue
        if str(value).strip().lower() in _UNCLASSIFIED:
            continue
        return value
    return None


def resolve_classification(val: dict, registry_class: dict | None = None) -> dict:
    """Layered classification read: explicit top-level valuation keys win,
    then classification_inputs, then the portfolio registry. The old
    top-level-only payoff_lens read left 130 tickers' classifications --
    41 asset names among them -- invisible to the personas built for them."""
    ci = val.get("classification_inputs") or {}
    reg = registry_class or {}
    return {
        field: _first_classified(val.get(field), ci.get(field), reg.get(field))
        for field in ("archetype", "moat", "dhando", "payoff_lens", "cycle")
    }


def load_contract(ticker: str) -> dict:
    """The universal valuation contract, when one exists ({} otherwise)."""
    contract = load_json(ROOT / ticker / "research" / "valuation_contract.json")
    return contract if isinstance(contract, dict) else {}


def extract_shared_context(val: dict, registry_class: dict | None = None,
                           contract: dict | None = None) -> dict:
    ci = val.get("classification_inputs") or {}
    resolved = resolve_classification(val, registry_class)
    inputs = val.get("inputs") or {}
    results = val.get("results") or val.get("results_lawrence_legacy") or {}
    scenarios = val.get("scenarios") or {}
    implied = val.get("implied_return") or {}
    synthesis = val.get("synthesis") or {}

    price = _num(inputs.get("price"))
    fcf = _num(inputs.get("fcf_per_share"))
    fcf_yield = (fcf / price * 100.0) if price and fcf and price > 0 else None

    base = _num((results.get("base") or {}).get("return_pct"))
    bear = _num((results.get("bear") or {}).get("return_pct"))
    bull = _num((results.get("bull") or {}).get("return_pct"))
    if base is None:
        base = _num(implied.get("base_pct"))
    if bear is None:
        bear = _num(implied.get("bear_pct"))
    if bull is None:
        bull = _num(implied.get("bull_pct"))

    # Contract fallback: contract-first compilers (the scarce-asset and other
    # routed methods) leave the legacy results/implied_return fields empty and
    # write returns to valuation_contract.json instead; without this fallback
    # every persona sits at 'pending' on exactly those tickers (WHK class).
    # Fallback only -- explicit legacy numbers keep precedence.
    return_source = "valuation"
    if base is None and bear is None and bull is None:
        contract_returns = ((contract or {}).get("valuation") or {}).get(
            "annualized_return_at_price_pct") or {}
        base = _num(contract_returns.get("base"))
        bear = _num(contract_returns.get("low"))
        bull = _num(contract_returns.get("high"))
        if base is not None or bear is not None or bull is not None:
            return_source = "contract"

    synthesis_pct = _num(synthesis.get("total_synthesis_pct"))
    if synthesis_pct is None:
        synthesis_pct = _num(implied.get("synthesis_pct"))
    filing_gate = _num(implied.get("lawrence_stance_gate_pct") or implied.get("falsifier_adjusted_pct"))

    growth_y1_5 = _num((scenarios.get("base") or {}).get("growth_y1_5"))
    if growth_y1_5 is not None and growth_y1_5 <= 1:
        growth_y1_5_pct = growth_y1_5 * 100.0
    else:
        growth_y1_5_pct = growth_y1_5

    net_debt = _num(inputs.get("net_debt_bn") or inputs.get("net_debt_millions"))
    ebitda = _num(inputs.get("ebitda_bn") or inputs.get("ebitda_millions"))
    net_debt_ebitda = None
    if net_debt is not None and ebitda and ebitda > 0:
        net_debt_ebitda = net_debt / ebitda

    downside_upside_ratio = None
    if bear is not None and bull is not None and bull > 0:
        downside_upside_ratio = abs(bear) / max(bull, 0.01)

    roic_proxy = _num(inputs.get("roic") or inputs.get("roe"))
    if roic_proxy is not None and roic_proxy <= 1:
        roic_proxy = roic_proxy * 100.0

    qual = synthesis.get("qualitative_adjustments") or []
    predictive_attribute = any(
        "predictive" in str(q.get("factor", "")).lower() or "catalyst" in str(q.get("factor", "")).lower()
        for q in qual
    )
    payoff_lens = str(resolved["payoff_lens"] or "pending").lower()
    catalyst_present = payoff_lens in ("asset", "event") or predictive_attribute
    capex = _num(inputs.get("capex") or inputs.get("capital_expenditures"))
    revenue = _num(inputs.get("revenue") or inputs.get("sales"))
    capex_to_sales = capex / revenue if capex is not None and revenue and revenue > 0 else None

    return {
        "return_source": return_source,
        "archetype": str(resolved["archetype"] or "unknown").lower(),
        "moat": str(resolved["moat"] or "unproven").lower(),
        "dhando": str(resolved["dhando"] or "pending").lower(),
        "cycle": resolved["cycle"] if resolved["cycle"] is not None else ci.get("cycle"),
        "payoff_lens": payoff_lens,
        "lawrence_bucket": (val.get("lawrence_bucket") or "other").lower(),
        "irr_method": (val.get("method") or val.get("irr_method") or "pending").lower(),
        "price": price,
        "fcf_yield": round(fcf_yield, 2) if fcf_yield is not None else None,
        "base_return_pct": base,
        "bear_return_pct": bear,
        "bull_return_pct": bull,
        "synthesis_pct": synthesis_pct,
        "filing_gate_pct": filing_gate,
        "growth_y1_5_pct": growth_y1_5_pct,
        "net_debt_ebitda": round(net_debt_ebitda, 2) if net_debt_ebitda is not None else None,
        "downside_upside_ratio": round(downside_upside_ratio, 3) if downside_upside_ratio is not None else None,
        "roic_proxy": round(roic_proxy, 2) if roic_proxy is not None else None,
        "predictive_attribute": predictive_attribute,
        "catalyst_present": catalyst_present,
        "bear_case_present": bear is not None,
        "capex_to_sales": capex_to_sales,
        "reinvestment_material": bool(
            ci.get("reinvestment_material")
            or ci.get("capacity_sensitive")
            or (capex_to_sales is not None and abs(capex_to_sales) >= 0.05)
        ),
        "credit_material": bool(
            ci.get("credit_material")
            or (net_debt_ebitda is not None and net_debt_ebitda >= 1.5)
            or inputs.get("fixed_claims_material")
        ),
        "incremental_roic": _num(inputs.get("incremental_roic")),
        "maintenance_capex_pct": _num(inputs.get("maintenance_capex_pct")),
        "industry_capacity_growth": _num(inputs.get("industry_capacity_growth")),
        "interest_coverage": _num(inputs.get("interest_coverage")),
        "maturity_wall": inputs.get("maturity_wall") or inputs.get("next_material_maturity"),
        "asset_nav_per_share": _num(inputs.get("asset_nav_per_share")),
        "realization_probability": _num(inputs.get("realization_probability")),
        "time_to_catalyst": _num(inputs.get("time_to_catalyst_years")),
        "earnings_yield": round(fcf_yield, 2) if fcf_yield is not None else None,
        "owner_earnings_yield": round(fcf_yield, 2) if fcf_yield is not None else None,
    }


def build_universe_stats(tickers: list[str] | None = None) -> dict:
    tickers = tickers or list_tickers_with_valuation()
    fcf_yields: list[float] = []
    base_irrs: list[float] = []
    roics: list[float] = []
    for t in tickers:
        val = load_json(ROOT / t / "research" / "valuation.json")
        if not isinstance(val, dict):
            continue
        ctx = extract_shared_context(val, registry_classification(t),
                                     load_contract(t))
        if ctx["fcf_yield"] is not None:
            fcf_yields.append(ctx["fcf_yield"])
        if ctx["base_return_pct"] is not None:
            base_irrs.append(ctx["base_return_pct"])
        if ctx["roic_proxy"] is not None:
            roics.append(ctx["roic_proxy"])

    def percentiles(vals: list[float]) -> dict:
        if not vals:
            return {"count": 0, "p33": None, "p50": None, "p66": None}
        s = sorted(vals)
        n = len(s)

        def pct(p: float) -> float:
            idx = min(n - 1, max(0, int(p * (n - 1))))
            return s[idx]

        return {"count": n, "p33": pct(0.33), "p50": pct(0.5), "p66": pct(0.66)}

    return {
        "ticker_count": len(tickers),
        "fcf_yield": percentiles(fcf_yields),
        "base_irr": percentiles(base_irrs),
        "roic_proxy": percentiles(roics),
    }


def _num(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _criterion_met(criterion: dict, ctx: dict, stats: dict) -> bool:
    check = criterion.get("check")
    if check == "always":
        return True
    if check == "archetype_any":
        return ctx["archetype"] in {v.lower() for v in criterion.get("values", [])}
    if check == "moat_any":
        return ctx["moat"] in {v.lower() for v in criterion.get("values", [])}
    if check == "dhando_any":
        return ctx["dhando"] in {v.lower() for v in criterion.get("values", [])}
    if check == "dhando_not":
        return ctx["dhando"] not in {v.lower() for v in criterion.get("values", [])}
    if check == "payoff_lens_any":
        return ctx["payoff_lens"] in {v.lower() for v in criterion.get("values", [])}
    if check == "fcf_yield_gte":
        v = ctx.get("fcf_yield")
        return v is not None and v >= float(criterion.get("threshold", 0))
    if check == "base_irr_present":
        return ctx.get("base_return_pct") is not None
    if check == "leverage_lte":
        v = ctx.get("net_debt_ebitda")
        if v is None:
            return True
        return v <= float(criterion.get("threshold", 3))
    if check == "bear_return_gte":
        v = ctx.get("bear_return_pct")
        return v is not None and v >= float(criterion.get("threshold", -100))
    if check == "irr_method_not":
        return ctx.get("irr_method") not in {v.lower() for v in criterion.get("values", [])}
    if check == "predictive_attribute_or_asset":
        return ctx.get("predictive_attribute") or ctx.get("payoff_lens") == "asset"
    if check == "capex_or_reinvestment_material":
        return bool(ctx.get("reinvestment_material"))
    if check == "leverage_or_fixed_claims_material":
        return bool(ctx.get("credit_material"))
    if check == "cycle_not":
        value = str(ctx.get("cycle") or "unknown").lower()
        return value not in {str(v).lower() for v in criterion.get("values", [])}
    if check == "bear_case_present":
        return bool(ctx.get("bear_case_present"))
    if check == "catalyst_present":
        return bool(ctx.get("catalyst_present"))
    if check == "fcf_yield_percentile_gte":
        p = (stats.get("fcf_yield") or {}).get("p66")
        v = ctx.get("fcf_yield")
        if p is None or v is None:
            return False
        return v >= p
    if check == "base_irr_percentile_gte":
        p = (stats.get("base_irr") or {}).get("p50")
        v = ctx.get("base_return_pct")
        if p is None or v is None:
            return False
        thr = criterion.get("threshold", 0.5)
        ref = (stats.get("base_irr") or {}).get("p33") if thr <= 0.34 else (stats.get("base_irr") or {}).get("p50")
        return ref is not None and v >= ref
    return False


def derive_relevance(criteria: list[dict], ctx: dict, stats: dict) -> tuple[float, list[dict]]:
    if not criteria:
        return 0.0, []
    met_flags = []
    audit = []
    for c in criteria:
        ok = _criterion_met(c, ctx, stats)
        met_flags.append(ok)
        audit.append({"id": c.get("id"), "check": c.get("check"), "met": ok})
    met = sum(met_flags)
    total = len(met_flags)
    if met == total:
        rel = 1.0
    elif met >= 1:
        rel = 0.5
    else:
        rel = 0.0
    return rel, audit


def apply_sparsity(lenses: list[dict], max_high: int) -> None:
    highs = [l for l in lenses if l.get("relevance") == 1.0]
    if len(highs) <= max_high:
        return
    highs.sort(key=lambda l: (-l.get("criteria_met", 0), l.get("persona", "")))
    for l in highs[max_high:]:
        l["relevance"] = 0.5
        l["sparsity_demoted"] = True


def valuation_richness(ctx: dict) -> float:
    base = ctx.get("base_return_pct")
    fcf_yield = ctx.get("fcf_yield")
    parts: list[float] = []
    if base is not None and base < 15:
        parts.append(min(1.0, max(0.0, (15 - base) / 15.0)))
    if fcf_yield is not None and fcf_yield < 4:
        parts.append(min(1.0, max(0.0, (4 - fcf_yield) / 4.0)))
    if not parts:
        return 0.0
    return min(1.0, sum(parts) / len(parts))


def compress_horizon(base_yrs: int, richness: float) -> int:
    return max(1, round(base_yrs * (1.0 - 0.5 * richness)))


def metric_count_for_richness(richness: float) -> int:
    if richness < 0.33:
        return 3
    if richness < 0.66:
        return 2
    return 1


def persona_return(fn: str, ctx: dict) -> float | None:
    base = ctx.get("base_return_pct")
    bear = ctx.get("bear_return_pct")
    bull = ctx.get("bull_return_pct")
    fcf_yield = ctx.get("fcf_yield")
    growth = ctx.get("growth_y1_5_pct")

    if fn == "lawrence_base":
        return base
    if fn == "lawrence_synthesis":
        return ctx.get("synthesis_pct") if ctx.get("synthesis_pct") is not None else base
    if fn == "pabrai_bear_bounded":
        if ctx.get("dhando") in ("full", "partial") and bear is not None:
            return bear
        return base
    if fn == "stahl_long_horizon":
        if ctx.get("moat") == "widening" and bull is not None:
            return bull
        return base
    if fn == "munger_quality":
        if ctx.get("moat") in ("widening", "stable"):
            return base
        return bear if bear is not None else base
    if fn == "greenblatt_magic":
        if fcf_yield is None:
            return base
        g = growth if growth is not None else 5.0
        return round(fcf_yield + min(g, 8.0), 2)
    if fn == "buffett_owner_earnings":
        if ctx.get("moat") in ("widening", "stable") and base is not None:
            return base
        return base * 0.85 if base is not None else None
    if fn == "hk_dated_payoff":
        ret = base
        if ret is not None and ctx.get("predictive_attribute"):
            ret = ret + 2.0
        return ret
    return base


def verdict_from_return(
    ret: float | None,
    bar_pct: float,
    relevance: float,
    moat: str,
    dhando: str,
) -> str:
    if relevance <= 0:
        return "silent"
    if ret is None:
        return "pending"
    moat_bad = moat in ("eroding", "unproven")
    dhando_bad = dhando == "none"
    if moat_bad or dhando_bad:
        if ret >= bar_pct:
            return "watch"
        return "pass"
    if ret > 20:
        return "accumulate"
    if ret >= bar_pct:
        return "hold"
    if ret >= 0:
        return "watch"
    return "pass"


def conviction(ret: float | None, bar_pct: float) -> float:
    if ret is None:
        return 0.0
    return round(min(1.0, abs(ret - bar_pct) / 20.0), 3)


def build_key_metrics(names: list[str], ctx: dict, limit: int) -> list[dict]:
    mapping = {
        "fcf_yield": ctx.get("fcf_yield"),
        "base_return_pct": ctx.get("base_return_pct"),
        "bear_return_pct": ctx.get("bear_return_pct"),
        "bull_return_pct": ctx.get("bull_return_pct"),
        "growth_y1_5": ctx.get("growth_y1_5_pct"),
        "downside_upside_ratio": ctx.get("downside_upside_ratio"),
        "net_debt_ebitda": ctx.get("net_debt_ebitda"),
        "dhando": ctx.get("dhando"),
        "moat": ctx.get("moat"),
        "archetype": ctx.get("archetype"),
        "payoff_lens": ctx.get("payoff_lens"),
        "earnings_yield": ctx.get("earnings_yield"),
        "roic_proxy": ctx.get("roic_proxy"),
        "owner_earnings_yield": ctx.get("owner_earnings_yield"),
        "synthesis_pct": ctx.get("synthesis_pct"),
        "filing_gate_pct": ctx.get("filing_gate_pct"),
        "catalyst_present": ctx.get("catalyst_present"),
        "predictive_attribute": ctx.get("predictive_attribute"),
        "incremental_roic": ctx.get("incremental_roic"),
        "maintenance_capex_pct": ctx.get("maintenance_capex_pct"),
        "industry_capacity_growth": ctx.get("industry_capacity_growth"),
        "cycle": ctx.get("cycle"),
        "interest_coverage": ctx.get("interest_coverage"),
        "maturity_wall": ctx.get("maturity_wall"),
        "asset_nav_per_share": ctx.get("asset_nav_per_share"),
        "realization_probability": ctx.get("realization_probability"),
        "time_to_catalyst": ctx.get("time_to_catalyst"),
    }
    out = []
    for name in names[:limit]:
        out.append({"name": name, "value": mapping.get(name)})
    return out


def weighted_median(pairs: list[tuple[float, float]]) -> float | None:
    if not pairs:
        return None
    pairs = sorted(pairs, key=lambda x: x[0])
    total_w = sum(w for _, w in pairs)
    if total_w <= 0:
        return None
    half = total_w / 2.0
    cum = 0.0
    for ret, w in pairs:
        cum += w
        if cum >= half:
            return ret
    return pairs[-1][0]


def build_valuation_blend(lenses: list[dict]) -> dict:
    contributors = [
        l
        for l in lenses
        if l.get("relevance", 0) > 0 and l.get("return_pct") is not None and l.get("verdict") != "silent"
    ]
    silent = [l["persona"] for l in lenses if l.get("verdict") == "silent" or l.get("relevance", 0) <= 0]
    if not contributors:
        return {
            "unit": "expected_annual_return_at_price",
            "blended_return_pct": None,
            "band_pct": None,
            "weighted_median_pct": None,
            "median_mean_flag": False,
            "low_coverage": True,
            "contributors": [],
            "excluded_silent": silent,
        }
    weighted_sum = sum(l["relevance"] * l["return_pct"] for l in contributors)
    weight_sum = sum(l["relevance"] for l in contributors)
    blended = round(weighted_sum / weight_sum, 2) if weight_sum else None
    returns = [l["return_pct"] for l in contributors]
    band = [round(min(returns), 2), round(max(returns), 2)]
    wmed = weighted_median([(l["return_pct"], l["relevance"]) for l in contributors])
    wmed_r = round(wmed, 2) if wmed is not None else None
    flag = blended is not None and wmed_r is not None and abs(blended - wmed_r) > 3.0
    return {
        "unit": "expected_annual_return_at_price",
        "blended_return_pct": blended,
        "band_pct": band,
        "weighted_median_pct": wmed_r,
        "median_mean_flag": flag,
        "low_coverage": len(contributors) == 1,
        "contributors": [
            {
                "persona": l["persona"],
                "label": l.get("label"),
                "relevance": l["relevance"],
                "return_pct": l["return_pct"],
                "verdict": l["verdict"],
            }
            for l in contributors
        ],
        "excluded_silent": silent,
    }


def build_consensus(lenses: list[dict], blend: dict, portfolio_bar: float, ctx: dict) -> dict:
    active = [l for l in lenses if l.get("relevance", 0) > 0 and l.get("verdict") not in ("silent", "pending")]
    if not active:
        return {
            "stance": "pending",
            "agreement_pct": 0,
            "dissents": [],
            "lawrence_divergence": False,
        }

    stance_counts: dict[str, float] = {}
    for l in active:
        stance_counts[l["verdict"]] = stance_counts.get(l["verdict"], 0) + l["relevance"]

    consensus_stance = max(stance_counts.items(), key=lambda kv: (kv[1], -STANCE_RANK.get(kv[0], 99)))[0]

    blended_ret = blend.get("blended_return_pct")
    if blended_ret is not None:
        consensus_stance = verdict_from_return(
            blended_ret,
            portfolio_bar,
            1.0,
            ctx.get("moat", "unproven"),
            ctx.get("dhando", "pending"),
        )

    agree_weight = sum(l["relevance"] for l in active if l["verdict"] == consensus_stance)
    total_weight = sum(l["relevance"] for l in active)
    agreement_pct = round(100.0 * agree_weight / total_weight) if total_weight else 0

    dissents = []
    for l in active:
        if l["verdict"] == consensus_stance:
            continue
        km = l.get("key_metrics") or []
        key_metric = km[0]["name"] if km else "return_pct"
        key_val = km[0]["value"] if km else l.get("return_pct")
        dissents.append(
            {
                "persona": l["persona"],
                "label": l.get("label"),
                "verdict": l["verdict"],
                "return_pct": l.get("return_pct"),
                "key_metric": f"{key_metric}={key_val}",
                "conviction": l.get("conviction", 0),
                "falsifier": l.get("falsifier"),
            }
        )
    dissents.sort(key=lambda d: -d.get("conviction", 0))

    lawrence = next((l for l in lenses if l["persona"] == "lawrence"), None)
    lawrence_stance = lawrence.get("verdict") if lawrence else None
    lawrence_divergence = bool(
        lawrence_stance and consensus_stance and lawrence_stance != consensus_stance
    )

    return {
        "stance": consensus_stance,
        "agreement_pct": agreement_pct,
        "dissents": dissents,
        "lawrence_divergence": lawrence_divergence,
        "portfolio_bar_pct": portfolio_bar,
    }


def build_lenses_for_ticker(ticker: str, stats: dict | None = None) -> dict | None:
    val_path = ROOT / ticker / "research" / "valuation.json"
    if not val_path.exists():
        return None
    val = load_json(val_path)
    if not isinstance(val, dict):
        return None

    personas_cfg = load_personas()
    stats = stats or load_json(UNIVERSE_STATS_PATH) or build_universe_stats()
    ctx = extract_shared_context(val, registry_classification(ticker),
                                 load_contract(ticker))
    richness = valuation_richness(ctx)
    portfolio_bar = float(personas_cfg.get("portfolio_bar_pct", 15))
    max_high = int(personas_cfg.get("max_high_relevance", 3))

    lenses: list[dict] = []
    for pid, spec in (personas_cfg.get("personas") or {}).items():
        criteria = spec.get("criteria") or []
        rel, audit = derive_relevance(criteria, ctx, stats)
        criteria_met = sum(1 for a in audit if a.get("met"))
        horizon = compress_horizon(int(spec.get("horizon_base_yrs", 7)), richness)
        mcount = metric_count_for_richness(richness)
        ret = persona_return(spec.get("return_fn", "lawrence_base"), ctx) if rel > 0 else None
        bar = float(spec.get("bar_min_return_pct", portfolio_bar))
        verdict = verdict_from_return(ret, bar, rel, ctx["moat"], ctx["dhando"])
        conv = conviction(ret, bar)

        entry: dict[str, Any] = {
            "persona": pid,
            "label": spec.get("label", pid),
            "relevance": rel,
            "criteria_met": criteria_met,
            "criteria_total": len(criteria),
            "criteria_audit": audit,
            "horizon_yrs": horizon,
            "metric_count": mcount,
            "return_pct": round(ret, 2) if ret is not None else None,
            "meets_bar": ret is not None and ret >= bar,
            "verdict": verdict,
            "conviction": conv,
            "falsifier": spec.get("falsifier"),
            "key_metrics": build_key_metrics(spec.get("key_metrics") or [], ctx, mcount),
            "source": spec.get("source"),
        }
        if rel <= 0:
            entry["why_silent"] = _silent_reason(audit, spec)
        lenses.append(entry)

    apply_sparsity(lenses, max_high)
    blend = build_valuation_blend(lenses)
    consensus = build_consensus(lenses, blend, portfolio_bar, ctx)

    as_of = val.get("as_of") or val_path.stat().st_mtime
    if isinstance(as_of, (int, float)):
        from datetime import datetime, timezone

        as_of = datetime.fromtimestamp(as_of, tz=timezone.utc).strftime("%Y-%m-%d")

    return {
        "ticker": ticker,
        "as_of": str(as_of)[:10],
        "shared_inputs_ref": f"valuation.json@{str(as_of)[:10]}",
        "valuation_richness": round(richness, 3),
        "lenses": lenses,
        "valuation_blend": blend,
        "consensus": consensus,
    }


def _silent_reason(audit: list[dict], spec: dict) -> str:
    failed = [a["id"] for a in audit if not a.get("met")]
    if failed:
        return f"Universe criteria not met: {', '.join(failed)}"
    return spec.get("falsifier") or "Outside persona universe"


def stable_json(obj: dict) -> str:
    return json.dumps(obj, indent=2, sort_keys=True) + "\n"
