#!/usr/bin/env python3
"""Canonical portfolio Power Zone router.

This is the only production entry point for valuation-method routing and
Investment Committee reviewer eligibility.  It combines the economic method
route with the specialist applicability rules and persists one auditable route
artifact per security.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

from build_power_zones import blended_score, calibration_rates, score_ticker_zone
from persona_groups import INDEPENDENCE_GROUPS as GROUPS
from valuation_method_router import route_valuation

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "_system" / "portfolio" / "registry.json"
CONFIG_PATH = ROOT / "_system" / "frameworks" / "power_zones.json"


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {} if default is None else default


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def canonical_hash(value: dict) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def registry_entries() -> dict[str, dict]:
    registry = read_json(REGISTRY_PATH)
    return {**(registry.get("watchlist") or {}), **(registry.get("holdings") or {})}


def merged_classification(ticker: str, valuation: dict, holding: dict) -> dict:
    registry_class = (holding or {}).get("classification") or {}
    direct = {
        key: (holding or {}).get(key)
        for key in ("investment_sleeve", "archetype", "moat", "dhando", "cycle")
        if (holding or {}).get(key) is not None
    }
    valuation_class = valuation.get("classification_inputs") or {}
    return {**registry_class, **direct, **{k: v for k, v in valuation_class.items() if v not in (None, "", "pending", "unknown")}}


def specialist_fit(classification: dict, config: dict) -> list[dict]:
    rates = calibration_rates()
    rows = []
    for persona, zone in (config.get("zones") or {}).items():
        result = score_ticker_zone(classification, zone)
        if not result.get("in_power_zone"):
            continue
        result = {
            "persona": persona,
            "label": zone.get("label") or persona,
            "independence_group": GROUPS.get(persona, persona),
            **result,
            "match_rate": rates.get(persona),
            "score": blended_score(float(result.get("fit") or 0), rates.get(persona)),
        }
        rows.append(result)
    return sorted(rows, key=lambda row: (-row["score"], row["persona"]))


def _seatability(method_route: dict, fits: list[dict]) -> dict:
    silent = set(method_route.get("silent_personas") or [])
    ranked = list(dict.fromkeys([
        *(method_route.get("primary_personas") or []),
        *(method_route.get("cross_check_personas") or []),
        *(row["persona"] for row in fits),
    ]))
    candidates = []
    groups = set()
    for persona in ranked:
        if persona in silent:
            continue
        group = GROUPS.get(persona, persona)
        candidates.append({"persona": persona, "independence_group": group})
        groups.add(group)
    return {
        "candidate_count": len(candidates),
        "independence_group_count": len(groups),
        "committee_seatable": len(groups) >= 3,
        "candidates": candidates,
    }


def build_route(ticker: str, as_of: str | None = None) -> dict:
    ticker = ticker.upper()
    holding = registry_entries().get(ticker) or {}
    research = ROOT / ticker / "research"
    valuation = read_json(research / "valuation.json")
    classification = merged_classification(ticker, valuation, holding)
    valuation_for_route = dict(valuation)
    valuation_for_route["classification_inputs"] = classification
    identity = read_json(research / "security_identity.json")
    explicit = identity.get("valuation_profile") or (
        (read_json(ROOT / "_system" / "reference" / "valuation_followups.json").get("tickers") or {})
        .get(ticker, {})
        .get("method_profile")
    )
    if identity.get("archetype"):
        classification["archetype"] = identity["archetype"]
        valuation_for_route["classification_inputs"] = classification
    method_route = route_valuation(valuation_for_route, explicit)
    config = read_json(CONFIG_PATH)
    fits = specialist_fit(classification, config)
    seatability = _seatability(method_route, fits)
    inputs = {
        "ticker": ticker,
        "classification": classification,
        "component_categories": sorted({
            str(row.get("category") or "")
            for row in [
                *((valuation.get("component_valuation_results") or {}).get("additive_components") or []),
                *((valuation.get("component_valuation_results") or {}).get("embedded_components") or []),
            ]
            if row.get("category")
        }),
        "explicit_profile": explicit,
        "security_identity": identity,
        "config_updated": config.get("updated"),
    }
    status = method_route.get("status") or "default_needs_review"
    if not seatability["committee_seatable"]:
        status = "reviewer_coverage_blocked"
    output = {
        **method_route,
        "schema_version": "2.0",
        "ticker": ticker,
        "as_of": (as_of or valuation.get("as_of") or date.today().isoformat())[:10],
        "status": status,
        "route_source": "canonical_power_zone_router",
        "config_path": "_system/frameworks/power_zones.json",
        "config_updated": config.get("updated"),
        "classification": classification,
        "specialist_power_zones": fits,
        "committee": seatability,
        "input_hash": canonical_hash(inputs),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "decision_rule": (
            "Power Zones select the fitting economic method and eligible independent reviewers; "
            "they never choose the valuation answer or capital decision."
        ),
    }
    return output


def write_route(ticker: str, as_of: str | None = None) -> Path:
    path = ROOT / ticker.upper() / "research" / "valuation_route.json"
    write_json(path, build_route(ticker, as_of))
    return path


def universe_tickers(scope: str) -> list[str]:
    entries = registry_entries()
    if scope == "valued":
        return sorted(t for t in entries if (ROOT / t / "research" / "valuation.json").exists())
    if scope == "priority":
        followups = read_json(ROOT / "_system" / "reference" / "valuation_followups.json")
        followup_names = set((followups.get("tickers") or {})) & set(entries)
        portfolio_names = {
            ticker
            for ticker, holding in entries.items()
            if str(((holding or {}).get("classification") or {}).get("stance") or "").lower()
            in {"core", "hold", "accumulate"}
        }
        return sorted(followup_names | portfolio_names)
    return sorted(entries)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tickers", nargs="*", type=str.upper)
    parser.add_argument("--scope", choices=("all", "valued", "priority"), default="all")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    tickers = args.tickers or universe_tickers(args.scope)
    statuses: dict[str, int] = {}
    for ticker in tickers:
        route = build_route(ticker, args.date)
        statuses[route["status"]] = statuses.get(route["status"], 0) + 1
        if not args.dry_run:
            write_json(ROOT / ticker / "research" / "valuation_route.json", route)
    print(json.dumps({"tickers": len(tickers), "statuses": statuses, "dry_run": args.dry_run}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
