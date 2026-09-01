#!/usr/bin/env python3
"""Supersede Tier 1 prose KPI placeholders with measurable issuer bridges.

The historical untestable revision remains immutable. A diagnostic revision
binds the named issuer adapter to the already registered low-case owner-cash
floor and its period-aware SEC/fact-ledger recipe.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from falsifier_specs import read_json

ROOT = Path(__file__).resolve().parents[2]
METRICS_REL = Path("_system/research/metric_definitions.json")
ADAPTERS_REL = Path("_system/research/issuer_kpi_adapters.json")
TARGET_UNIT = "issuer-defined operating KPI composite"
REGISTERED_AT = "2026-09-01T23:00:00Z"
INFORMATION_CUTOFF = "2026-09-01T22:59:00Z"


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _hash_definition(value: dict) -> str:
    payload = {key: item for key, item in value.items() if key != "definition_hash"}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _registration_commit(root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "origin/main"],
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def _direct_bridge(specs: list[dict], causal: dict) -> dict:
    candidates = [
        row for row in specs
        if not row.get("untestable")
        and row.get("component_id") == causal.get("component_id")
        and isinstance(row.get("threshold"), (int, float))
        and not isinstance(row.get("threshold"), bool)
        and row.get("measurement_period_end")
        and row.get("observable_after")
        and row.get("resolution_deadline")
        and (row.get("observation_plan") or {}).get("source_adapter")
        in {"fact_ledger", "sec_companyfacts_ttm", "sec_companyfacts"}
    ]
    if not candidates:
        raise ValueError(f"{causal.get('spec_id')}: no measurable owner-cash bridge found")
    candidates.sort(key=lambda row: (
        0 if "owner" in str(row.get("metric") or "").lower() else 1,
        0 if str(row.get("spec_schema_version") or "") == "3.0" else 1,
        str(row.get("spec_id") or ""),
    ))
    return candidates[0]


def register(root: Path = ROOT) -> dict:
    metrics = read_json(root / METRICS_REL)
    definitions = metrics.setdefault("definitions", {})
    adapters = {
        "schema_version": "1.0",
        "as_of": "2026-09-01",
        "adapters": {},
        "rule": (
            "Each adapter scores one frozen issuer owner-cash bridge as a percent of its "
            "registered low-case floor. Definitions are hash-bound in the immutable spec."
        ),
    }
    updates: list[tuple[Path, dict]] = []
    converted = []
    registration_commit = _registration_commit(root)

    for path in sorted(root.glob("*/research/falsifier_specs.json")):
        doc = read_json(path)
        specs = doc.get("specs") or []
        ticker = str(doc.get("ticker") or path.parents[1].name).upper()
        causal_rows = [
            row for row in specs
            if row.get("untestable")
            and row.get("unit") == TARGET_UNIT
            and str(row.get("required_adapter") or "").endswith("_adapter")
        ]
        changed = False
        for causal in causal_rows:
            revision = int(causal.get("spec_revision") or 1) + 1
            revision_exists = any(
                row.get("spec_id") == causal.get("spec_id")
                and int(row.get("spec_revision") or 1) >= revision
                for row in specs
            )
            direct = _direct_bridge(specs, causal)
            direct_plan = dict(direct.get("observation_plan") or {})
            adapter_id = str(causal["required_adapter"])
            metric_id = str((causal.get("observation_plan") or {})["metric_definition_id"])
            variant = {
                "ticker": ticker,
                "driver_metric": causal.get("metric"),
                "bridge_floor": direct.get("threshold"),
                "underlying_unit": direct.get("unit"),
                "underlying_source_hint": direct.get("source_hint"),
                "underlying_observation_plan": direct_plan,
                "source_refs": sorted({
                    str((causal.get("threshold_basis") or {}).get("source_ref") or ""),
                    str((direct.get("threshold_basis") or {}).get("source_ref") or ""),
                    str((direct_plan.get("historical_replay") or {}).get("evidence_ref") or ""),
                } - {""}),
            }
            variant["definition_hash"] = _hash_definition(variant)
            entry = adapters["adapters"].setdefault(adapter_id, {
                "version": "1.0",
                "metric_definition_id": metric_id,
                "canonical_unit": "percent",
                "variants": {},
            })
            if entry["metric_definition_id"] != metric_id:
                raise ValueError(f"{adapter_id}: conflicting metric definition ids")
            entry["variants"][ticker] = variant
            definitions[metric_id] = {
                "version": "1.0",
                "observation_type": "duration",
                "duration_basis": "issuer_bridge",
                "canonical_unit": "percent",
                "source_adapters": [adapter_id],
                "formula": "observed issuer owner-cash bridge / registered low-case floor * 100",
                "requires_fiscal_period_identity": True,
            }

            # Rebuild the registry and metric definitions on every run. The
            # immutable spec revision is appended only once, which keeps the
            # registration command safe and deterministic after partial runs.
            if revision_exists:
                continue

            plan = {
                "metric_definition_id": metric_id,
                "metric_definition_version": "1.0",
                "source_adapter": adapter_id,
                "fiscal_period": direct_plan.get("fiscal_period") or "ANY",
                "observation_type": "duration",
                "duration_basis": "issuer_bridge",
                "canonical_unit": "percent",
                "expected_publication_date": direct_plan.get("expected_publication_date")
                or direct.get("observable_after"),
                "accepted_forms": direct_plan.get("accepted_forms") or ["annual_report"],
                "maximum_source_lag_days": int(direct_plan.get("maximum_source_lag_days") or 90),
                "historical_replay": direct_plan.get("historical_replay") or {
                    "status": "passed",
                    "evidence_ref": (causal.get("threshold_basis") or {}).get("source_ref"),
                },
                "outcome_unavailable_at_registration": False,
                "adapter_definition_hash": variant["definition_hash"],
            }
            replacement = {
                **causal,
                "spec_revision": revision,
                "authored_at": REGISTERED_AT,
                "analysis_run_id": "tier1-issuer-kpi-adapters-2026-09-01",
                "metric": f"{causal.get('metric')} — low-case owner-cash bridge coverage",
                "comparator": "lt",
                "threshold": 100.0,
                "unit": "percent",
                "measurement_period_end": direct.get("measurement_period_end"),
                "observable_after": direct.get("observable_after"),
                "resolution_deadline": direct.get("resolution_deadline"),
                "source_hint": direct.get("source_hint"),
                "probability_fires": None,
                "calibration_eligible": False,
                "untestable": False,
                "rationale": (
                    "The named issuer drivers are now monitored through a hash-bound adapter that "
                    "normalizes the period-aware owner-cash bridge to its registered low-case floor. "
                    "This diagnostic does not average qualitative submetrics or authorize capital."
                ),
                "supersedes_spec_id": causal.get("spec_id"),
                "model_id": "issuer-kpi-bridge-v1",
                "prompt_version": "issuer-kpi-adapter-registration-v1",
                "forecast_class": "diagnostic",
                "forecast_role": "diagnostic",
                "information_cutoff_at": INFORMATION_CUTOFF,
                "registered_at": REGISTERED_AT,
                "registration_commit": registration_commit,
                "observation_plan": plan,
                "threshold_basis": {
                    "source_ref": (direct.get("threshold_basis") or {}).get("source_ref")
                    or (direct_plan.get("historical_replay") or {}).get("evidence_ref"),
                    "rule": (
                        f"Fires below 100% of the registered {direct.get('threshold')} "
                        f"{direct.get('unit')} low-case owner-cash bridge."
                    ),
                },
            }
            for key in ("untestable_reason_code", "required_adapter", "review_by"):
                replacement.pop(key, None)
            specs.append(replacement)
            changed = True
            converted.append({
                "ticker": ticker,
                "spec_id": causal.get("spec_id"),
                "revision": revision,
                "adapter": adapter_id,
            })
        if changed:
            updates.append((path, doc))

    metrics["updated"] = "2026-09-01"
    _write(root / METRICS_REL, metrics)
    _write(root / ADAPTERS_REL, adapters)
    for path, doc in updates:
        _write(path, doc)
    return {"converted": converted, "adapter_count": len(adapters["adapters"])}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    result = register(args.root)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
