#!/usr/bin/env python3
"""Refresh price-dependent contract fields without re-underwriting the model.

The full contract compiler intentionally revalidates evidence and prospective
falsifiers.  A quote refresh is narrower: it may change the market mark and the
outputs mathematically derived from that mark, but it must not rewrite source
lineage, assumptions, component values, model maturity, or committee status.

This command builds a candidate contract from the updated valuation input,
proves that its economic basis still matches the reviewed contract, and then
copies only the price-dependent fields into the reviewed artifact.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from universal_valuation_contract import (  # noqa: E402
    build_universal_valuation_contract,
    canonical_hash,
)

PRICE_DEPENDENT_VALUATION_FIELDS = (
    "forward_return_at_price_pct",
    "forward_return_status",
    "forward_return_reason",
    "annualized_return_at_price_pct",
    "annualized_return_field_status",
    "margin_of_safety_pct",
    "upside_to_value_pct",
    "downside_to_low_pct",
)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def economic_basis(contract: dict) -> dict:
    """Return the reviewed economics that a price-only refresh cannot change."""
    valuation = contract.get("valuation") or {}
    components = []
    for row in contract.get("economic_ownership_map") or []:
        components.append({
            key: row.get(key)
            for key in (
                "component_id",
                "category",
                "treatment",
                "included_in_component_id",
                "ownership_claim",
                "ownership_percentage",
                "quantity",
                "method",
                "method_version",
                "comparable_ids",
                "range_per_share",
                "valuation_status",
                "scenario_assumptions",
                "probability_and_timing",
                "tax_and_realization_adjustments",
                "overlap_key",
            )
        })
    return {
        "ticker": contract.get("ticker"),
        "model_as_of": (contract.get("dates") or {}).get("model_as_of"),
        "fully_diluted_shares": (contract.get("market") or {}).get("fully_diluted_shares"),
        "components": components,
        "valuation": {
            key: valuation.get(key)
            for key in (
                "output_basis",
                "output_basis_status",
                "output_range_per_share",
                "value_per_share",
                "present_value_today_per_share",
                "future_payoff_per_share",
                "future_payoff_date",
                "future_payoff_horizon_years",
                "forward_cashflow_schedule",
                "priced_components_per_share",
                "required_return_pct",
                "horizon_years",
            )
        },
    }


def refresh(ticker: str, *, dry_run: bool = False) -> dict:
    ticker = ticker.upper()
    research = ROOT / ticker / "research"
    valuation_path = research / "valuation.json"
    contract_path = research / "valuation_contract.json"
    valuation = read_json(valuation_path)
    reviewed = read_json(contract_path)
    profile_id = str(((reviewed.get("method_route") or {}).get("profile_id")) or "") or None
    candidate = build_universal_valuation_contract(copy.deepcopy(valuation), profile_id)

    if economic_basis(reviewed) != economic_basis(candidate):
        raise ValueError(
            f"{ticker}: economic basis changed; run the full evidence/falsifier review instead of a market-mark refresh"
        )

    updated = copy.deepcopy(reviewed)
    updated.setdefault("dates", {})["price_as_of"] = (candidate.get("dates") or {}).get("price_as_of")
    updated["market"] = copy.deepcopy(candidate.get("market") or {})
    updated_valuation = updated.setdefault("valuation", {})
    candidate_valuation = candidate.get("valuation") or {}
    for field in PRICE_DEPENDENT_VALUATION_FIELDS:
        updated_valuation[field] = copy.deepcopy(candidate_valuation.get(field))
    updated.setdefault("legacy_audit", {})["annualized_return_at_price_pct"] = copy.deepcopy(
        (candidate.get("legacy_audit") or {}).get("annualized_return_at_price_pct")
    )
    change_control = updated.setdefault("change_control", {})
    change_control["model_hash"] = canonical_hash(
        {key: value for key, value in updated.items() if key != "change_control"}
    )

    changed = updated != reviewed
    if changed and not dry_run:
        write_json(contract_path, updated)
    return {
        "ticker": ticker,
        "status": "would_update" if changed and dry_run else ("updated" if changed else "unchanged"),
        "price": (updated.get("market") or {}).get("price_per_share"),
        "price_as_of": (updated.get("dates") or {}).get("price_as_of"),
        "proof_status": updated.get("proof_status"),
        "model_level": updated.get("model_level"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tickers", nargs="+", type=str.upper)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    results = []
    failures = []
    for ticker in args.tickers:
        try:
            results.append(refresh(ticker, dry_run=args.dry_run))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            failures.append({"ticker": ticker, "error": str(exc)})
    print(json.dumps({"results": results, "failures": failures}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
