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
) -> dict:
    moat_bad = moat in ("eroding", "unproven")
    dhando_bad = dhando == "none"

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
    proposal = propose_stance(base_pct, moat, dhando, method)

    data["method"] = method
    data["results"] = {k: {"return_pct": v["return_pct"]} for k, v in results.items()}
    data["implied_return"] = {
        "base_pct": base_pct,
        "label": return_label,
        "display": f"{base_pct}% (base)" if base_pct is not None else "pending",
    }
    data["stance_proposal"] = proposal
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

    computed = compute_valuation(data)

    if args.write:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(computed, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {path.relative_to(ROOT)}")

    if args.json or not args.write:
        print(json.dumps(computed, indent=2))


if __name__ == "__main__":
    main()
