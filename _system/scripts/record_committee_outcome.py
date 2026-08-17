#!/usr/bin/env python3
"""Record a verified, dividend-aware committee outcome and refresh calibration."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

from build_total_return_panel import compute_period_total_return
from build_valuation_workbench import write as write_valuation_workbench
from committee_calibration import summarize

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "_system" / "research" / "committee_outcomes.jsonl"
CALIBRATION = ROOT / "_system" / "research" / "committee_calibration.json"


def latest_committee(ticker: str, committee_date: str | None = None) -> tuple[Path, dict]:
    research = ROOT / ticker / "research"
    decision_path = research / "human_decision.json"
    if committee_date:
        paths = [research / f"committee_{committee_date}.json"]
    elif decision_path.exists():
        decision = json.loads(decision_path.read_text(encoding="utf-8"))
        source = str(decision.get("committee_source") or "")
        paths = [research / Path(source).name] if source else []
    else:
        paths = sorted(research.glob("committee_????-??-??.json"))
    paths = [path for path in paths if path.exists()]
    if not paths:
        raise FileNotFoundError(f"{ticker}: no committee record")
    records = [(path, json.loads(path.read_text(encoding="utf-8"))) for path in paths]
    complete = [pair for pair in records if pair[1].get("final_state") in {
        "committee_complete_decision_pending", "owner_decision_pending", "outcome_tracking"}]
    if complete:
        return complete[-1]
    return records[-1]


def upsert(rows: list[dict], record: dict) -> list[dict]:
    def key(row: dict) -> tuple:
        measurement_key = ("horizon", row.get("horizon_months")) if row.get("horizon_months") else ("date", row.get("measurement_date"))
        return row.get("ticker"), row.get("decision_date"), measurement_key

    record_key = key(record)
    kept = [row for row in rows if key(row) != record_key]
    kept.append(record)
    return sorted(kept, key=lambda row: (row["measurement_date"], row["ticker"], row["decision_date"]))


def _measurement_key(row: dict) -> tuple:
    measurement = (("horizon", row.get("horizon_months"))
                   if row.get("horizon_months")
                   else ("date", row.get("measurement_date")))
    return row.get("ticker"), row.get("decision_date"), measurement


def current_revisions(rows: list[dict]) -> list[dict]:
    """Return the latest immutable revision for every logical measurement."""
    current = {}
    for row in rows:
        key = _measurement_key(row)
        if key not in current or int(row.get("revision") or 1) >= int(current[key].get("revision") or 1):
            current[key] = row
    return sorted(current.values(), key=lambda row: (
        row.get("measurement_date") or "", row.get("ticker") or "",
        row.get("decision_date") or ""))


def _authoritative_decision(ticker: str, committee_path: Path, committee: dict) -> dict:
    """Load the owner's standalone signed decision, with a legacy fallback."""
    path = ROOT / ticker / "research" / "human_decision.json"
    if path.exists():
        decision = json.loads(path.read_text(encoding="utf-8"))
        if decision.get("status") != "decided" or not decision.get("decision"):
            raise ValueError("standalone owner decision must have status=decided")
        expected_ref = str(committee_path.relative_to(ROOT)).replace("\\", "/")
        supplied_ref = str(decision.get("committee_source") or "")
        if supplied_ref and supplied_ref not in {committee_path.name, expected_ref}:
            raise ValueError("owner decision points to a different committee record")
        packet_hash = str((committee.get("evidence_packet") or {}).get("packet_hash") or "")
        if packet_hash and decision.get("committee_packet_hash") != packet_hash:
            raise ValueError("owner decision packet hash does not match frozen committee evidence")
        return decision
    legacy = committee.get("human_decision") or {}
    if legacy.get("status") == "complete" and legacy.get("decision"):
        return legacy
    raise ValueError("a decided standalone owner decision is required before measuring an outcome")


def record(ticker: str, *, committee_date: str | None = None,
           measurement_date: str | None = None, horizon_months: int | None = None,
           error_attribution: list[str] | None = None, write: bool = False) -> dict:
    """Build and optionally append one attributable committee outcome."""
    ticker = ticker.upper()
    measurement_date = measurement_date or date.today().isoformat()
    committee_path, committee = latest_committee(ticker, committee_date)
    human_decision = _authoritative_decision(ticker, committee_path, committee)
    decision_date = human_decision.get("decided_at") or (committee.get("review") or {}).get("as_of")
    if not decision_date:
        raise ValueError("owner decision timestamp is required")
    outcome = compute_period_total_return(ticker, decision_date, measurement_date)
    valuation = json.loads((ROOT / ticker / "research" / "valuation.json").read_text(encoding="utf-8"))
    component = valuation.get("component_valuation_results") or {}
    contract = valuation.get("universal_valuation_contract") or {}
    power_zone = (contract.get("method_route") or valuation.get("valuation_method_route") or {}).get("profile_id")
    votes = (committee.get("round_two") or {}).get("votes") or []
    expected_ranges = [vote.get("expected_return_range_pct") for vote in votes
                       if isinstance(vote.get("expected_return_range_pct"), list)]
    expected_midpoint = None
    if expected_ranges:
        expected_midpoint = round(sum((float(r[0]) + float(r[1])) / 2
                                      for r in expected_ranges) / len(expected_ranges), 2)
    base_record = {
        **outcome,
        "ticker": ticker,
        "decision_date": decision_date,
        "measurement_date": measurement_date,
        "horizon_months": horizon_months,
        "committee_ref": str(committee_path.relative_to(ROOT)).replace("\\", "/"),
        "committee_packet_hash": (committee.get("evidence_packet") or {}).get("packet_hash"),
        "owner_decision": human_decision.get("decision"),
        "decision_id": human_decision.get("decision_id") or
                       f"{ticker}|{decision_date}|{committee_path.name}",
        "outcome_class": "owner_decision",
        "owner_sizing": human_decision.get("sizing"),
        "decision_price": (valuation.get("inputs") or {}).get("price"),
        "decision_value_range_per_share": component.get("total_equity_value_per_share"),
        "economic_value_status": (valuation.get("economic_value_analysis") or {}).get("status"),
        "universal_contract_status": contract.get("status"),
        "power_zone": power_zone,
        "expected_return_midpoint_pct": expected_midpoint,
        "forecast_midpoint_error_pct": (
            round(float(outcome["total_return_pct"]) - expected_midpoint, 2)
            if outcome.get("total_return_pct") is not None and expected_midpoint is not None else None),
        "component_forecast_snapshot": component.get("additive_components") or [],
        "votes": votes,
        "error_attribution": sorted(set(error_attribution or [])),
    }
    existing = ([json.loads(line) for line in LEDGER.read_text(encoding="utf-8").splitlines()
                 if line.strip()] if LEDGER.exists() else [])
    prior = [row for row in existing if _measurement_key(row) == _measurement_key(base_record)]
    prior_latest = max(prior, key=lambda row: int(row.get("revision") or 1), default=None)
    revision = int((prior_latest or {}).get("revision") or 0) + 1
    outcome_id = hashlib.sha256(json.dumps(
        {"key": _measurement_key(base_record), "revision": revision},
        sort_keys=True).encode("utf-8")).hexdigest()[:24]
    result = {
        **base_record,
        "outcome_id": outcome_id,
        "revision": revision,
        "supersedes_outcome_id": (prior_latest or {}).get("outcome_id"),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    print(json.dumps(result, indent=2))
    if write:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with LEDGER.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(result, sort_keys=True) + "\n")
        rows = current_revisions(existing + [result])
        CALIBRATION.write_text(json.dumps(summarize(rows), indent=2) + "\n", encoding="utf-8")
        from build_calibration_brief import build as build_calibration_brief
        build_calibration_brief(ROOT)
        write_valuation_workbench(ticker, measurement_date)
        print(f"Appended {LEDGER} and refreshed {CALIBRATION}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker")
    parser.add_argument("--committee-date")
    parser.add_argument("--measurement-date", default=date.today().isoformat())
    parser.add_argument("--horizon-months", type=int, choices=(6, 12, 24))
    parser.add_argument("--error-attribution", action="append", choices=("economic_claim", "cash_flow", "capital_intensity", "comparable", "option_probability", "timing", "leverage", "governance", "other"), default=[])
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    record(args.ticker, committee_date=args.committee_date,
           measurement_date=args.measurement_date,
           horizon_months=args.horizon_months,
           error_attribution=args.error_attribution, write=args.write)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
