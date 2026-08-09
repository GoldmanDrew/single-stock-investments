#!/usr/bin/env python3
"""Refresh valuation.json calculation_proof inputs from the current fact ledger.

The full readiness run (``automate_valuation_readiness.run_ticker``) rewrites the
whole model, which collapses a hand-built ``valuation.json`` to the compiler
skeleton.  This is the narrow call: it recompiles the model with the ticker's own
method compiler - the same ``_proof_fact`` writer path - and then splices back
only the ``calculation_proof.inputs`` arrays plus the compiler-owned monetary
mirrors under ``inputs``.  Assumptions, the calculation graph, scenarios,
synthesis and human_review are left exactly as they were.

Needed after a fact ledger is re-locked (for example the 2026-08-09 non-USD
currency correction): the ledger moved to USD but the proof inputs kept the raw
EUR figures still labelled "USD millions".

Usage:
    python refresh_valuation_proof_inputs.py --tickers ASML NVO
    python refresh_valuation_proof_inputs.py --tickers ASML --dry-run
Output is ASCII-only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from automate_valuation_readiness import METHOD_COMPILERS, ROOT, read_json, write_json

# Live market marks and their provenance are fetched into ``inputs`` by the
# pricing pass, not by the compiler; never let a recompile clobber them.
PRICE_KEYS = {"price", "price_as_of", "price_source"}


def iter_components(model: dict):
    results = model.get("component_valuation_results") or {}
    for key in ("additive_components", "embedded_components"):
        for component in results.get(key) or []:
            if isinstance(component, dict):
                yield component


def refresh(ticker: str, dry_run: bool = False) -> dict:
    research = ROOT / ticker / "research"
    model = read_json(research / "valuation.json")
    if not model:
        return {"ticker": ticker, "status": "skipped", "reason": "no valuation.json"}
    before_keys = sorted(model)
    identity = read_json(research / "security_identity.json")
    ledger = read_json(research / "valuation_fact_ledger.json")
    method_id = str(identity.get("primary_method") or "")
    compiler = METHOD_COMPILERS.get(method_id)
    if compiler is None:
        return {"ticker": ticker, "status": "skipped",
                "reason": f"no compiler for routed method '{method_id or 'unknown'}'"}
    as_of = str(model.get("as_of") or ledger.get("as_of") or "")
    fresh = compiler(ticker, as_of, identity, ledger)
    if not fresh:
        return {"ticker": ticker, "status": "skipped",
                "reason": "compiler produced no model (method inputs incomplete or invalid)"}

    fresh_by_id = {}
    for component in iter_components(fresh):
        for key in (component.get("id"), component.get("overlap_key")):
            if key:
                fresh_by_id.setdefault(str(key), component)

    changes, warnings = [], []
    for component in iter_components(model):
        proof = component.get("calculation_proof")
        if not isinstance(proof, dict) or not isinstance(proof.get("inputs"), list):
            continue
        match = fresh_by_id.get(str(component.get("id") or "")) or fresh_by_id.get(
            str(component.get("overlap_key") or ""))
        new_proof = (match or {}).get("calculation_proof") or {}
        new_inputs = new_proof.get("inputs")
        if not isinstance(new_inputs, list):
            warnings.append(f"{component.get('id')}: no recompiled proof to refresh from")
            continue
        old_by_id = {str(row.get("id")): row for row in proof["inputs"] if isinstance(row, dict)}
        new_by_id = {str(row.get("id")): row for row in new_inputs if isinstance(row, dict)}
        if set(old_by_id) != set(new_by_id):
            warnings.append(
                f"{component.get('id')}: proof input ids differ from the compiler "
                f"({sorted(set(old_by_id) ^ set(new_by_id))}); left untouched")
            continue
        for node_id, new_row in new_by_id.items():
            old_row = old_by_id[node_id]
            if old_row == new_row:
                continue
            where = f"{component.get('id')}.{node_id}"
            if old_row.get("value") != new_row.get("value"):
                changes.append(f"{where}: {old_row.get('value')} -> "
                               f"{new_row.get('value')} {new_row.get('unit')}")
            elif not old_row.get("fx_conversion") and new_row.get("fx_conversion"):
                changes.append(f"{where}: fx_conversion provenance attached")
            else:
                # Same number, different evidence text (a reworded rate source,
                # a re-locked locator): still a real staleness worth reporting.
                changes.append(f"{where}: source provenance refreshed")
        proof["inputs"] = [new_by_id[str(row.get("id"))] for row in proof["inputs"]]

    model_inputs = model.get("inputs")
    if isinstance(model_inputs, dict):
        for key, value in (fresh.get("inputs") or {}).items():
            # Only refresh mirrors the model already carries: adding compiler
            # keys to a hand-built model would change its meaning, not fix it.
            if key in PRICE_KEYS or key not in model_inputs:
                continue
            if model_inputs[key] != value:
                changes.append(f"inputs.{key}: {model_inputs[key]} -> {value}")
                model_inputs[key] = value

    after_keys = sorted(model)
    if changes and not dry_run:
        write_json(research / "valuation.json", model)
    return {
        "ticker": ticker,
        "status": "unchanged" if not changes else ("would_update" if dry_run else "updated"),
        "method_id": method_id,
        "top_level_keys_before": before_keys,
        "top_level_keys_after": after_keys,
        "keys_lost": sorted(set(before_keys) - set(after_keys)),
        "changes": changes,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh valuation.json proof inputs from the fact ledger.")
    parser.add_argument("--tickers", nargs="+", type=str.upper, required=True)
    parser.add_argument("--dry-run", action="store_true", help="Report the changes without writing.")
    args = parser.parse_args()
    results = [refresh(ticker, args.dry_run) for ticker in args.tickers]
    print(json.dumps({"results": results}, indent=2))
    return 1 if any(result.get("keys_lost") for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
