#!/usr/bin/env python3
"""Evaluate and audit deterministic component valuation calculation proofs.

The proof format is intentionally small.  Facts and assumptions are declared as
typed nodes, calculations form a directed acyclic graph, and low/base/high
outputs must be reachable from that graph.  No Python expressions or arbitrary
code are accepted from a model file.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from math import isfinite
from pathlib import Path
from typing import Any

CASES = ("low", "base", "high")
ROOT = Path(__file__).resolve().parents[2]
PRICED_STATUSES = {"calculated", "bounded_estimate"}
ALL_STATUSES = PRICED_STATUSES | {"unpriced", "legacy_sensitivity"}
OPS = {
    "add", "subtract", "multiply", "divide", "sum", "negative", "minimum",
    "maximum", "power", "discount", "present_value",
}


def floor_equity_value_range(
    values: dict | None,
    *,
    ndigits: int | None = None,
) -> dict:
    """Limited-liability floor for security equity value per share.

    Individual components (debt, reserves, funding gaps) may be negative.
    The summed long-equity claim cannot. Returns a new low/base/high dict
    with each present numeric case floored at 0.
    """
    out: dict[str, float | None] = {}
    src = values or {}
    for case in CASES:
        raw = src.get(case)
        if raw is None:
            out[case] = None
            continue
        floored = max(0.0, float(raw))
        out[case] = round(floored, ndigits) if ndigits is not None else floored
    return out


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _case_value(row: dict, case: str, label: str) -> float:
    values = row.get("values")
    if isinstance(values, dict):
        if case not in values:
            raise ValueError(f"{label} is missing {case} value")
        return _number(values[case], f"{label}.{case}")
    return _number(row.get("value"), label)


def _resolve(arg: Any, values: dict[str, float], node_id: str) -> float:
    if isinstance(arg, str):
        if arg not in values:
            raise ValueError(f"{node_id} references unknown or later node {arg}")
        return values[arg]
    return _number(arg, f"{node_id} literal")


def _apply(op: str, args: list[float], node: dict) -> float:
    if op == "add":
        if len(args) != 2: raise ValueError("add requires two arguments")
        return args[0] + args[1]
    if op == "subtract":
        if len(args) != 2: raise ValueError("subtract requires two arguments")
        return args[0] - args[1]
    if op == "multiply":
        if len(args) != 2: raise ValueError("multiply requires two arguments")
        return args[0] * args[1]
    if op == "divide":
        if len(args) != 2: raise ValueError("divide requires two arguments")
        if args[1] == 0: raise ValueError("divide denominator cannot be zero")
        return args[0] / args[1]
    if op == "sum":
        if not args: raise ValueError("sum requires at least one argument")
        return sum(args)
    if op == "negative":
        if len(args) != 1: raise ValueError("negative requires one argument")
        return -args[0]
    if op == "minimum":
        if not args: raise ValueError("minimum requires at least one argument")
        return min(args)
    if op == "maximum":
        if not args: raise ValueError("maximum requires at least one argument")
        return max(args)
    if op == "power":
        if len(args) != 2: raise ValueError("power requires two arguments")
        return args[0] ** args[1]
    if op == "discount":
        if len(args) != 3: raise ValueError("discount requires value, rate, and years")
        if args[1] <= -1 or args[2] < 0: raise ValueError("invalid discount rate or years")
        return args[0] / ((1 + args[1]) ** args[2])
    if op == "present_value":
        # Alternating cash flow and year arguments followed by the discount rate.
        if len(args) < 3 or len(args) % 2 != 1:
            raise ValueError("present_value requires cash/year pairs followed by a discount rate")
        rate = args[-1]
        if rate <= -1: raise ValueError("invalid present_value discount rate")
        return sum(args[i] / ((1 + rate) ** args[i + 1]) for i in range(0, len(args) - 1, 2))
    raise ValueError(f"unsupported operation {op}")


def _fmt(value: float) -> str:
    return f"{value:.8g}"


def _formula(node: dict, resolved: list[float]) -> tuple[str, str]:
    op = node["op"]
    args = node.get("args") or []
    symbols = {"add": "+", "subtract": "-", "multiply": "×", "divide": "÷", "power": "^"}
    if op in symbols and len(args) == 2:
        return f"{args[0]} {symbols[op]} {args[1]}", f"{_fmt(resolved[0])} {symbols[op]} {_fmt(resolved[1])}"
    if op == "negative":
        return f"-({args[0]})", f"-({_fmt(resolved[0])})"
    return f"{op}({', '.join(map(str, args))})", f"{op}({', '.join(_fmt(x) for x in resolved)})"


def _validate_source(row: dict, errors: list[str]) -> None:
    source = row.get("source") or {}
    if row.get("kind") == "fact":
        if not source.get("ref"):
            errors.append(f"{row.get('id')}: fact requires source.ref")
        if not source.get("locator"):
            errors.append(f"{row.get('id')}: fact requires source.locator")
        if not source.get("as_of"):
            errors.append(f"{row.get('id')}: fact requires source.as_of")
        if row.get("locked") is not True:
            errors.append(f"{row.get('id')}: fact must be locked")


def _validate_assumption(row: dict, errors: list[str]) -> None:
    if row.get("kind") != "judgment":
        return
    if not row.get("rationale"):
        errors.append(f"{row.get('id')}: judgment requires rationale")
    bounds = row.get("allowed_range")
    if not isinstance(bounds, dict) or bounds.get("min") is None or bounds.get("max") is None:
        errors.append(f"{row.get('id')}: judgment requires allowed_range min/max")
        return
    try:
        low, high = _number(bounds["min"], "allowed min"), _number(bounds["max"], "allowed max")
        for case in CASES:
            value = _case_value(row, case, str(row.get("id")))
            if not low <= value <= high:
                errors.append(f"{row.get('id')}.{case}: {value} outside allowed range [{low}, {high}]")
    except ValueError as exc:
        errors.append(str(exc))


@lru_cache(maxsize=4096)
def _local_content_hash(ref: str) -> str | None:
    path = ROOT / ref
    return hashlib.sha256(path.read_bytes()).hexdigest() if ref and path.is_file() else None


def _source_record(source: dict | None) -> dict | None:
    if not source:
        return None
    result = dict(source)
    ref = str(source.get("ref") or "")
    content_hash = _local_content_hash(ref)
    if content_hash:
        result["content_sha256"] = content_hash
    result["source_id"] = canonical_hash({
        "ref": result.get("ref"), "locator": result.get("locator"),
        "as_of": result.get("as_of"), "content_sha256": result.get("content_sha256"),
    })
    return result


def evaluate_calculation_proof(proof: dict) -> dict:
    """Return an audit-ready evaluation; never raises for malformed user data."""
    errors: list[str] = []
    if proof.get("schema_version") != "1.0":
        errors.append("calculation_proof.schema_version must be 1.0")
    for key in ("method_id", "method_version", "output_unit"):
        if not proof.get(key): errors.append(f"calculation_proof.{key} is required")
    inputs = [*(proof.get("inputs") or []), *(proof.get("assumptions") or [])]
    ids: set[str] = set()
    for row in inputs:
        node_id = str(row.get("id") or "")
        if not node_id: errors.append("input or assumption id is required"); continue
        if node_id in ids: errors.append(f"duplicate node id {node_id}")
        ids.add(node_id)
        if row.get("kind") not in {"fact", "estimate", "judgment"}:
            errors.append(f"{node_id}: kind must be fact, estimate, or judgment")
        if not row.get("unit"): errors.append(f"{node_id}: unit is required")
        _validate_source(row, errors)
        _validate_assumption(row, errors)
    for node in proof.get("calculations") or []:
        node_id = str(node.get("id") or "")
        if not node_id: errors.append("calculation id is required"); continue
        if node_id in ids: errors.append(f"duplicate node id {node_id}")
        ids.add(node_id)
        if node.get("op") not in OPS: errors.append(f"{node_id}: unsupported operation {node.get('op')}")
        if not node.get("unit"): errors.append(f"{node_id}: unit is required")

    traces, outputs = {}, {}
    output_nodes = proof.get("outputs") or {}
    for case in CASES:
        values: dict[str, float] = {}
        case_trace = []
        try:
            for row in inputs:
                value = _case_value(row, case, str(row.get("id")))
                values[row["id"]] = value
                source = _source_record(row.get("source"))
                traced = {
                    "id": row["id"], "label": row.get("label") or row["id"],
                    "kind": row.get("kind"), "value": round(value, 8), "unit": row.get("unit"),
                    "source": source, "rationale": row.get("rationale"),
                }
                # A value converted out of the source currency must stay
                # distinguishable from an unconverted one downstream; without
                # this the contract trace shows "USD millions" against a EUR/DKK
                # concept with nothing saying a rate was applied.
                if isinstance(row.get("fx_conversion"), dict) and row["fx_conversion"]:
                    traced["fx_conversion"] = row["fx_conversion"]
                case_trace.append(traced)
            for node in proof.get("calculations") or []:
                resolved = [_resolve(arg, values, node["id"]) for arg in node.get("args") or []]
                value = _apply(node["op"], resolved, node)
                if not isfinite(value): raise ValueError(f"{node['id']} produced a non-finite value")
                values[node["id"]] = value
                formula, substituted = _formula(node, resolved)
                case_trace.append({
                    "id": node["id"], "label": node.get("label") or node["id"], "kind": "calculation",
                    "value": round(value, 8), "unit": node.get("unit"), "operation": node["op"],
                    "formula": formula, "substituted_formula": substituted,
                    "dependencies": node.get("args") or [],
                })
            output_id = output_nodes.get(case)
            if not output_id: raise ValueError(f"outputs.{case} is required")
            if output_id not in values: raise ValueError(f"outputs.{case} references unknown node {output_id}")
            outputs[case] = round(values[output_id], 4)
            traces[case] = case_trace
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            errors.append(f"{case}: {exc}")
    if len(outputs) == 3 and not outputs["low"] <= outputs["base"] <= outputs["high"]:
        errors.append("calculated outputs must satisfy low <= base <= high")
    lineage = []
    for row in inputs:
        if row.get("source"):
            lineage.append({"node_id": row.get("id"), **(_source_record(row["source"]) or {})})
    evaluation = {
        "status": "valid" if not errors else "invalid",
        "method_id": proof.get("method_id"),
        "method_version": proof.get("method_version"),
        "outputs": outputs,
        "output_unit": proof.get("output_unit"),
        "traces": traces,
        "source_lineage": lineage,
        "checks": {"passed": not errors, "errors": sorted(set(errors))},
    }
    evaluation["proof_hash"] = canonical_hash({"proof": proof, "outputs": outputs, "source_lineage": lineage})
    return evaluation


def component_proof(component: dict) -> dict:
    requested = component.get("valuation_status")
    proof = component.get("calculation_proof")
    legacy = {
        case: component.get(f"{case}_per_share")
        for case in CASES
        if component.get(f"{case}_per_share") is not None
    }
    if proof:
        evaluated = evaluate_calculation_proof(proof)
        status = requested if requested in PRICED_STATUSES else "bounded_estimate"
        if evaluated["status"] != "valid": status = "unpriced"
        return {"valuation_status": status, "evaluation": evaluated, "legacy_range_per_share": legacy or None}
    status = requested if requested in ALL_STATUSES else ("legacy_sensitivity" if legacy else "unpriced")
    return {
        "valuation_status": status,
        "evaluation": None,
        "legacy_range_per_share": component.get("legacy_range_per_share") or legacy or None,
    }


def proof_completeness(rows: list[dict]) -> dict:
    counts = {status: 0 for status in sorted(ALL_STATUSES)}
    errors = []
    hashes = []
    for row in rows:
        status = row.get("valuation_status") or "unpriced"
        counts[status] = counts.get(status, 0) + 1
        evaluation = row.get("calculation_proof")
        if evaluation:
            hashes.append(evaluation.get("proof_hash"))
            errors.extend(evaluation.get("checks", {}).get("errors") or [])
    total = len(rows)
    priced = sum(counts.get(status, 0) for status in PRICED_STATUSES)
    return {
        "component_count": total,
        "priced_component_count": priced,
        "proof_complete_pct": round(priced / total * 100, 1) if total else 0.0,
        "status_counts": counts,
        "all_material_components_priced": bool(total) and priced == total,
        "calculation_errors": sorted(set(errors)),
        "aggregate_proof_hash": canonical_hash(sorted(x for x in hashes if x)),
    }
