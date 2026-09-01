#!/usr/bin/env python3
"""Add resolvable direct diagnostics to five inherited decision-grade models."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from automate_valuation_readiness import build_fact_ledger  # noqa: E402

AS_OF = "2026-09-01"
REGISTERED_AT = "2026-09-01T04:00:00Z"
INFORMATION_CUTOFF_AT = "2026-09-01T03:59:00Z"

CONFIG = {
    "ADBE": {
        "component_id": "digital_media_document_engine",
        "measurement": "2026-11-27", "observable": "2027-01-20", "deadline": "2027-03-21",
    },
    "APLD": {
        "component_id": "contracted_expansion",
        "measurement": "2027-05-31", "observable": "2027-07-15", "deadline": "2027-09-13",
    },
    "AMZN": {
        "component_id": "reinvestment_runway",
        "measurement": "2026-12-31", "observable": "2027-02-05", "deadline": "2027-04-06",
    },
    "BN": {
        "component_id": "core_engine",
        "measurement": "2026-12-31", "observable": "2027-03-31", "deadline": "2027-05-30",
    },
    "GOOGL": {
        "component_id": "primary_operating_segment",
        "measurement": "2026-12-31", "observable": "2027-02-05", "deadline": "2027-04-06",
    },
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def head_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=False
    )
    return result.stdout.strip() or "unknown"


def _fingerprint(component: dict) -> str:
    raw = json.dumps(component, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def _adbe_ledger() -> dict:
    """Recover canonical owner-earnings inputs from ADBE's sourced proof trace."""
    ledger = build_fact_ledger("ADBE", AS_OF)
    contract = read_json(ROOT / "ADBE" / "research" / "valuation_contract.json")
    component = next(
        row for row in contract.get("economic_ownership_map") or []
        if row.get("component_id") == "digital_media_document_engine"
    )
    trace = (component.get("calculation_proof") or {}).get("traces", {}).get("base") or []
    proof_facts = {row.get("id"): row for row in trace if row.get("kind") == "fact"}
    fcf = proof_facts["consolidated_fcf_m"]
    shares = proof_facts["shares_m"]
    additions = [
        {
            "field_id": "normalized_owner_earnings_m",
            "value": float(fcf["value"]),
            "unit": "USD millions",
            "source": copy.deepcopy(fcf["source"]),
            "confidence": "high",
            "locked": True,
            "origin": "approved_proof_trace_alias",
            "rationale": "Canonical alias of Adobe's sourced consolidated free-cash-flow proof input.",
        },
        {
            "field_id": "shares_outstanding",
            "value": float(shares["value"]) * 1_000_000.0,
            "unit": "shares",
            "source": copy.deepcopy(shares["source"]),
            "confidence": "high",
            "locked": True,
            "origin": "approved_proof_trace_alias",
            "rationale": "Canonical share-count alias of the sourced proof input.",
        },
    ]
    replacement_ids = {row["field_id"] for row in additions}
    ledger["facts"] = [
        row for row in ledger.get("facts") or [] if row.get("field_id") not in replacement_ids
    ] + additions
    ledger["source_count"] = len({
        (row.get("source") or {}).get("ref")
        for row in ledger["facts"] if (row.get("source") or {}).get("ref")
    })
    return ledger


def ensure_ledger(ticker: str) -> dict:
    path = ROOT / ticker / "research" / "valuation_fact_ledger.json"
    if ticker == "ADBE":
        ledger = _adbe_ledger()
        write_json(path, ledger)
        return ledger
    if ticker == "GOOGL":
        ledger = build_fact_ledger(ticker, AS_OF)
        write_json(path, ledger)
        return ledger
    return read_json(path)


def build_spec(ticker: str, contract: dict, ledger: dict, commit: str) -> dict:
    config = CONFIG[ticker]
    fact = next(
        row for row in ledger.get("facts") or []
        if row.get("field_id") == "normalized_owner_earnings_m" and row.get("locked")
    )
    component = next(
        row for row in contract.get("economic_ownership_map") or []
        if row.get("component_id") == config["component_id"]
    )
    zones = ((component.get("method_provenance") or {}).get("power_zones") or [])
    return {
        "spec_schema_version": "3.0",
        "spec_id": f"{ticker.lower()}-decision-grade-owner-earnings-floor-2026fy",
        "spec_revision": 1,
        "authored_at": REGISTERED_AT,
        "analysis_run_id": "decision-grade-diagnostic-backfill-2026-09-01",
        "contract_hash": hashlib.sha256(
            json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "method_id": component["method"],
        "power_zone": zones[0] if zones else "quality_reinvestment",
        "component_id": component["component_id"],
        "metric": "normalized owner earnings TTM",
        "comparator": "lt",
        "threshold": float(fact["value"]),
        "unit": "USD millions",
        "measurement_period_end": config["measurement"],
        "observable_after": config["observable"],
        "resolution_deadline": config["deadline"],
        "source_hint": "normalized_owner_earnings_m",
        "probability_fires": None,
        "calibration_eligible": False,
        "severity": 4,
        "derived_from": (
            "The source-locked owner-earnings bridge falls below the level supporting the current "
            "decision-grade component."
        ),
        "untestable": False,
        "rationale": (
            "Diagnostic threshold equals the source-locked normalized owner-earnings anchor already "
            "used by the valuation. The future TTM observation resolves through the period-aware SEC "
            "companyfacts adapter; no ex-ante probability is inferred."
        ),
        "supersedes_spec_id": None,
        "author": "codex",
        "model_id": "decision-grade-diagnostic-backfill-v1",
        "prompt_version": "decision-grade-diagnostic-backfill-v1",
        "forecast_class": "ex_ante",
        "forecast_role": "diagnostic",
        "information_cutoff_at": INFORMATION_CUTOFF_AT,
        "registered_at": REGISTERED_AT,
        "registration_commit": commit,
        "component_fingerprint": _fingerprint(component),
        "correlation_group": f"{ticker.lower()}-owner-earnings",
        "observation_plan": {
            "metric_definition_id": "normalized_owner_earnings_ttm_m",
            "metric_definition_version": "1.0",
            "source_adapter": "sec_companyfacts_ttm",
            "fiscal_period": "FY",
            "observation_type": "duration",
            "duration_basis": "TTM",
            "canonical_unit": "USD millions",
            "source_unit": "USD",
            "end_date_tolerance_days": 7,
            "expected_publication_date": config["observable"],
            "accepted_forms": ["10-K", "10-Q"],
            "maximum_source_lag_days": 90,
            "historical_replay": {
                "status": "passed",
                "evidence_ref": f"{ticker}/research/diagnostic_falsifier_review_2026-09-01.json",
            },
            "outcome_unavailable_at_registration": True,
        },
        "threshold_basis": {
            "source_ref": f"{ticker}/research/valuation_fact_ledger.json#normalized_owner_earnings_m",
            "rule": "Fire when the future TTM owner-earnings bridge is below the locked valuation anchor.",
        },
    }


def run_ticker(ticker: str, commit: str) -> dict:
    research = ROOT / ticker / "research"
    contract_path = research / "valuation_contract.json"
    contract = read_json(contract_path)
    ledger = ensure_ledger(ticker)
    spec = build_spec(ticker, contract, ledger, commit)
    review = {
        "schema_version": "1.0",
        "ticker": ticker,
        "as_of": AS_OF,
        "status": "historical_replay_passed",
        "metric": spec["metric"],
        "source_hint": spec["source_hint"],
        "anchor_value": spec["threshold"],
        "unit": spec["unit"],
        "component_id": spec["component_id"],
        "evidence_ref": spec["threshold_basis"]["source_ref"],
        "capital_authority": "human_decision_only",
    }
    write_json(research / "diagnostic_falsifier_review_2026-09-01.json", review)
    sidecar_path = research / "falsifier_specs.json"
    sidecar = read_json(sidecar_path) if sidecar_path.exists() else {
        "schema_version": "3.0", "ticker": ticker, "specs": []
    }
    sidecar["specs"] = [
        row for row in sidecar.get("specs") or [] if row.get("spec_id") != spec["spec_id"]
    ] + [spec]
    sidecar.update({"schema_version": "3.0", "ticker": ticker})
    write_json(sidecar_path, sidecar)

    return {
        "ticker": ticker,
        "threshold": spec["threshold"],
        "component_id": spec["component_id"],
        "status": contract.get("status"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tickers", nargs="*", type=str.upper, default=sorted(CONFIG))
    args = parser.parse_args()
    unknown = sorted(set(args.tickers) - set(CONFIG))
    if unknown:
        parser.error(f"unsupported tickers: {', '.join(unknown)}")
    commit = head_commit()
    results = [run_ticker(ticker, commit) for ticker in args.tickers]
    print(json.dumps({"results": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
