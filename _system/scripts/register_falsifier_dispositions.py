#!/usr/bin/env python3
"""Register reviewed v3 untestable dispositions for contract components."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from falsifier_specs import anchor_errors, spec_errors  # noqa: E402


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def digest(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def register(ticker: str, review_path: Path, *, root: Path = ROOT) -> dict:
    ticker = ticker.upper()
    review = read_json(review_path)
    if review.get("ticker") != ticker:
        raise ValueError(f"{review_path}: ticker must equal {ticker}")
    if review.get("status") != "reviewed_typed_untestable_dispositions":
        raise ValueError(f"{review_path}: review status is not approved for registration")
    if (review.get("historical_replay") or {}).get("status") != "passed":
        raise ValueError(f"{review_path}: historical replay must pass")

    contract_path = root / ticker / "research" / "valuation_contract.json"
    contract = read_json(contract_path)
    components = {
        str(row.get("component_id")): row
        for row in contract.get("economic_ownership_map") or []
        if isinstance(row, dict) and row.get("treatment") == "additive"
    }
    review_ref = review_path.relative_to(root).as_posix()
    contract_hash = digest(contract)
    profile = str((contract.get("method_route") or {}).get("profile_id") or "unrouted")
    specs = []
    seen = set()
    for row in review.get("component_dispositions") or []:
        component_id = str(row.get("component_id") or "")
        if component_id in seen:
            raise ValueError(f"{ticker}: duplicate disposition for {component_id}")
        seen.add(component_id)
        component = components.get(component_id)
        if component is None:
            raise ValueError(f"{ticker}: unknown additive component {component_id}")
        derived_from = str(component.get("falsifier") or "").strip()
        if not derived_from:
            raise ValueError(f"{ticker} {component_id}: contract falsifier is missing")
        plan = row.get("observation_plan") or {}
        unit = str(row.get("unit") or "issuer-defined evidence composite")
        spec = {
            "spec_schema_version": "3.0",
            "spec_id": row.get("spec_id") or f"{ticker.lower()}-{slug(component_id)}-disposition-2026q3",
            "spec_revision": 1,
            "authored_at": review["registered_at"],
            "analysis_run_id": review["analysis_run_id"],
            "contract_hash": contract_hash,
            "method_id": component.get("method") or "unregistered_component_method",
            "power_zone": profile,
            "component_id": component_id,
            "metric": row["metric"],
            "comparator": row.get("comparator") or "lt",
            "threshold": None,
            "unit": unit,
            "measurement_period_end": None,
            "observable_after": None,
            "resolution_deadline": None,
            "source_hint": None,
            "probability_fires": None,
            "calibration_eligible": False,
            "severity": int(row.get("severity") or 4),
            "derived_from": derived_from,
            "untestable": True,
            "rationale": row["rationale"],
            "supersedes_spec_id": None,
            "author": review.get("author") or "codex",
            "model_id": review.get("model_id") or f"{ticker.lower()}-component-proof-v1",
            "prompt_version": review.get("prompt_version") or "tier1-research-blocker-closure-v1",
            "forecast_class": "ex_ante",
            "forecast_role": "primary",
            "information_cutoff_at": review["information_cutoff_at"],
            "registered_at": review["registered_at"],
            "registration_commit": review["registration_commit"],
            "component_fingerprint": digest(component),
            "correlation_group": row.get("correlation_group") or f"{ticker.lower()}-{slug(component_id)}",
            "observation_plan": {
                "metric_definition_id": plan["metric_definition_id"],
                "metric_definition_version": "1.0",
                "source_adapter": row["required_adapter"],
                "fiscal_period": plan["fiscal_period"],
                "observation_type": plan["observation_type"],
                "duration_basis": plan["duration_basis"],
                "canonical_unit": unit,
                "expected_publication_date": plan["expected_publication_date"],
                "accepted_forms": plan["accepted_forms"],
                "maximum_source_lag_days": int(plan["maximum_source_lag_days"]),
                "historical_replay": {"status": "passed", "evidence_ref": review_ref},
                "outcome_unavailable_at_registration": True,
            },
            "threshold_basis": {
                "source_ref": review_ref,
                "rule": row.get("threshold_rule") or (
                    "No numeric threshold is registered until the required adapter can reproduce the component proof."
                ),
            },
            "untestable_reason_code": row["untestable_reason_code"],
            "required_adapter": row["required_adapter"],
            "review_by": row["review_by"],
        }
        errors = spec_errors(spec, len(specs)) + anchor_errors(spec, contract, len(specs))
        if errors:
            raise ValueError(f"{ticker} {component_id}: " + "; ".join(errors))
        specs.append(spec)

    if set(components) != seen:
        missing = sorted(set(components) - seen)
        raise ValueError(f"{ticker}: dispositions do not cover every additive component: {missing}")
    payload = {"schema_version": "3.0", "ticker": ticker, "specs": specs}
    output = root / ticker / "research" / "falsifier_specs.json"
    write_json(output, payload)
    return {"ticker": ticker, "spec_count": len(specs), "output": output.relative_to(root).as_posix()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ticker", type=str.upper)
    parser.add_argument("review", type=Path)
    args = parser.parse_args()
    print(json.dumps(register(args.ticker, args.review.resolve()), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
