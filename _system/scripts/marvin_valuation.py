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
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLASS_PATH = ROOT / "_system" / "portfolio" / "classification.json"
AI_HYPERSCALERS = frozenset({"GOOGL", "AMZN", "META", "MSFT"})
SEGMENT_DISCOUNT_DEFAULT = 0.10


def cashflows_full(
    price: float,
    fcf0: float,
    growth1: float,
    growth2: float,
    exit_mult: float,
    years: int = 10,
) -> list[float]:
    stream = [-price]
    fcf = fcf0
    for year in range(1, years + 1):
        g = growth1 if year <= 5 else growth2
        fcf *= 1 + g
        if year < years:
            stream.append(fcf)
        else:
            stream.append(fcf + fcf * exit_mult)
    return stream


def irr(cfs: list[float], guess: float = 0.12, tol: float = 1e-7, max_iter: int = 200) -> float:
    rate = guess
    for _ in range(max_iter):
        npv = sum(cf / (1 + rate) ** i for i, cf in enumerate(cfs))
        dnpv = sum(-i * cf / (1 + rate) ** (i + 1) for i, cf in enumerate(cfs))
        if abs(dnpv) < 1e-12:
            break
        step = npv / dnpv
        rate -= step
        if abs(step) < tol:
            break
    return rate


def run_full_scenario(price: float, fcf0: float, scenario: dict) -> dict:
    cfs = cashflows_full(
        price=price,
        fcf0=fcf0,
        growth1=scenario["growth_y1_5"],
        growth2=scenario["growth_y6_10"],
        exit_mult=scenario["exit_pfcf_y10"],
    )
    rate = irr(cfs)
    return {"return_pct": round(rate * 100, 1), "cashflows": [round(x, 2) for x in cfs]}


def run_scenario_method(price: float, per_share0: float, scenario: dict) -> dict:
    """Scenario method — same math as full but metric may be EPS/owner earnings."""
    metric_key = scenario.get("metric_key", "growth_y1_5")
    g1 = scenario.get("growth_y1_5", scenario.get("growth", 0.05))
    g2 = scenario.get("growth_y6_10", g1 * 0.75)
    exit_mult = scenario.get("exit_multiple", scenario.get("exit_pfcf_y10", 15))
    cfs = cashflows_full(price, per_share0, g1, g2, exit_mult)
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
    years: int = 10,
) -> float:
    fcf = fcf0
    pv = 0.0
    for year in range(1, years + 1):
        g = g1 if year <= 5 else g2
        fcf *= 1 + g
        pv += fcf / (1 + r) ** year
    pv += (fcf * exit_mult) / (1 + r) ** years
    return pv


def solve_segment_implied_rate(
    price: float,
    segments: list[dict],
    drags: list[float],
    years: int = 10,
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
                    seg["growth_y6_10"],
                    seg["exit_pfcf_y10"],
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
    years = int(build.get("horizon_years", 10))
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
                "growth_y6_10": float(seg.get("growth_y6_10", 0.06)),
                "exit_pfcf_y10": float(seg.get("exit_pfcf_y10", 18)),
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
            seg["growth_y6_10"],
            seg["exit_pfcf_y10"],
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
    recon = build.setdefault("reconciliation", {})
    recon.update(out)
    return out


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
        pct = run_full_scenario(float(price), float(fcf0), sc)["return_pct"]
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
                "display": f"FCF ~${trough}/sh (not 10yr IRR)",
                "stance_gate": False,
            }
        )

    seg = compute_segment_overlay(data)
    if seg and price:
        rows.append(
            {
                "case": "Segment sum",
                "method": f"segment @ {seg['explicit_discount_rate_pct']:.0f}%",
                "key_inputs": f"PV ${seg['sum_pv_per_share_at_explicit_discount']}/sh vs P₀ ${price}",
                "return_pct": None,
                "display": f"${seg['sum_pv_per_share_at_explicit_discount']}/sh",
                "stance_gate": False,
            }
        )
        rows.append(
            {
                "case": "Segment implied",
                "method": "reverse DCF (segments)",
                "key_inputs": "Services + Cloud + drags; options $0",
                "return_pct": seg["implied_business_return_pct"],
                "stance_gate": False,
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
        return_label = "10yr IRR"
    elif method == "scenario":
        ps = inputs.get("per_share") or inputs.get("fcf_per_share")
        if price is None or ps is None:
            raise ValueError("scenario method requires inputs.price and inputs.per_share")
        for name, sc in data.get("scenarios", {}).items():
            results[name] = run_scenario_method(price, ps, sc)
        return_label = "scenario IRR"
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
    data["results"] = {k: {"return_pct": v["return_pct"]} for k, v in results.items()}
    proposal = propose_stance(base_pct, moat, dhando, method, data=data)
    data["stance_proposal"] = proposal

    if data.get("valuation_mode") == "optionality" and data.get("optionality_gate"):
        gate = data["optionality_gate"]
        primary_pct = gate.get("primary_return_pct")
        if primary_pct is not None:
            label = gate.get("primary_label", "primary return")
            data["implied_return"] = {
                "base_pct": primary_pct,
                "lawrence_base_pct": base_pct,
                "label": label,
                "display": f"{primary_pct}% ({label})",
            }
            return data

    data["implied_return"] = {
        "base_pct": base_pct,
        "label": return_label,
        "display": f"{base_pct}% (base)" if base_pct is not None else "pending",
    }

    data["overlay_results"] = compute_ai_overlay_rows(data, results)
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
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(computed, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {path.relative_to(ROOT)}")

    if args.json or not args.write:
        print(json.dumps(computed, indent=2))


if __name__ == "__main__":
    main()
