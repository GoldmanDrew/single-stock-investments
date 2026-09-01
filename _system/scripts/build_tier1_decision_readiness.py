#!/usr/bin/env python3
"""Compile the governed Tier 1 decision-readiness operating queue.

Tier assignment says where research attention belongs.  This artifact says
what has to happen next.  It never upgrades a model, clears an evidence gap,
starts a committee, or authorizes capital; it only orders the work already
described by the valuation contract, workbench, and universe policy.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
POLICY_REL = Path("_system/portfolio/valuation_universe_policy.json")
TIERS_REL = Path("_system/data/valuation_universe_tiers.json")
OUTPUT_REL = Path("_system/data/tier1_decision_readiness.json")

REVIEWED_MODEL_LEVELS = {"stock_specific", "committee_reviewed", "owner_approved"}
ACTIVE_COMMITTEE_STATES = {
    "independent_review_open",
    "conditional_escalation",
    "chair_pending",
    "ready_to_assemble",
    "parked",
    "committee_complete_decision_pending",
    "owner_decision_pending",
    "outcome_tracking",
}


def _read_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _iso_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def _age_days(value: Any, as_of: date) -> int | None:
    parsed = _iso_date(value)
    return (as_of - parsed).days if parsed else None


def _first_gap(workbench: dict) -> dict:
    gaps = (workbench.get("evidence") or {}).get("gaps") or []
    open_gaps = [row for row in gaps if isinstance(row, dict) and row.get("status") not in {
        "resolved", "accepted", "not_applicable", "met",
    }]
    return next((row for row in open_gaps if row.get("priority") == "critical"), None) or (
        open_gaps[0] if open_gaps else {}
    )


def _freshness(dates: dict, requirements: dict, as_of: date) -> tuple[dict, list[dict]]:
    maximums = requirements.get("maximum_age_days") or {}
    result: dict[str, dict] = {}
    blockers: list[dict] = []
    for field in ("model_as_of", "latest_fact_as_of", "price_as_of"):
        value = dates.get(field)
        age = _age_days(value, as_of)
        maximum = int(maximums.get(field, 0) or 0)
        status = "current"
        if age is None:
            status = "missing"
        elif maximum and age > maximum:
            status = "stale"
        result[field] = {
            "date": value,
            "age_days": age,
            "maximum_age_days": maximum or None,
            "status": status,
        }
        if status != "current":
            blockers.append({
                "code": f"{field}_{status}",
                "severity": "high" if field == "price_as_of" else "medium",
                "detail": (
                    f"{field} is missing"
                    if age is None
                    else f"{field} is {age} days old; Tier 1 maximum is {maximum}"
                ),
            })
    return result, blockers


def _priority_and_state(
    *,
    proof_status: str,
    model_level: str,
    open_count: int,
    critical_count: int,
    freshness_blockers: list[dict],
    falsifier_count: int,
    minimum_falsifiers: int,
    committee: dict,
) -> tuple[int, str, str]:
    if critical_count:
        return 10, "critical_evidence", "research_blocked"
    if open_count:
        return 20, "evidence_closure", "research_blocked"
    if proof_status != "decision_grade":
        return 30, "proof_completion", "research_blocked"
    if model_level not in REVIEWED_MODEL_LEVELS:
        return 40, "model_deepening", "model_deepening_required"
    if freshness_blockers:
        return 50, "freshness_refresh", "freshness_refresh_required"
    if falsifier_count < minimum_falsifiers:
        return 60, "falsifier_design", "falsifier_design_required"

    committee_status = str(committee.get("status") or "not_started")
    owner_status = str(committee.get("owner_status") or "pending")
    if model_level == "owner_approved" or owner_status == "decided":
        return 100, "complete", "owner_approved"
    if committee_status in ACTIVE_COMMITTEE_STATES:
        if committee_status in {"committee_complete_decision_pending", "owner_decision_pending"}:
            return 80, "owner_decision", "owner_decision_ready"
        return 70, "committee_completion", "committee_in_progress"
    return 65, "committee_start", "committee_ready"


def _next_action(
    state: str,
    workbench: dict,
    contract: dict,
    freshness_blockers: list[dict],
) -> str:
    gap = _first_gap(workbench)
    committee = workbench.get("committee") or {}
    decision = workbench.get("decision") or {}
    if state == "research_blocked" and gap:
        return str(
            gap.get("acceptance_test")
            or gap.get("question")
            or gap.get("next_action")
            or "Close the highest-priority evidence gap with primary-source proof."
        )
    if state == "research_blocked":
        return "Complete the source-linked contract proof and resolve every failed model check before committee work."
    if state == "model_deepening_required":
        return str(
            contract.get("next_action")
            or decision.get("next_action")
            or "Build a stock-specific component model with source-linked calculation proof."
        )
    if state == "freshness_refresh_required":
        fields = ", ".join(row["code"].rsplit("_", 1)[0] for row in freshness_blockers)
        return f"Refresh stale or missing Tier 1 inputs: {fields}."
    if state == "falsifier_design_required":
        return "Author an explicit, observable falsifier and its monitoring source."
    if state in {"committee_ready", "committee_in_progress", "owner_decision_ready"}:
        return str(committee.get("next_action") or "Advance the independent committee review.")
    return "Maintain the signed human decision and monitor its refresh triggers."


def build(as_of: str | None = None, root: Path = ROOT) -> dict:
    tiers = _read_json(root / TIERS_REL)
    policy = _read_json(root / POLICY_REL)
    as_of_value = (as_of or tiers.get("as_of") or datetime.utcnow().date().isoformat())[:10]
    as_of_date = _iso_date(as_of_value)
    if as_of_date is None:
        raise ValueError(f"invalid as_of date: {as_of_value}")
    requirements = policy.get("tier_1_readiness") or {}
    minimum_falsifiers = int(requirements.get("minimum_explicit_falsifiers", 1) or 1)
    items = []

    for ticker, assignment in sorted((tiers.get("assignments") or {}).items()):
        if int((assignment or {}).get("tier") or 3) != 1:
            continue
        research = root / ticker / "research"
        workbench = _read_json(research / "valuation_workbench.json")
        contract = _read_json(research / "valuation_contract.json")
        evidence = workbench.get("evidence") or contract.get("evidence") or {}
        committee = workbench.get("committee") or {}
        dates = workbench.get("dates") or contract.get("dates") or {}
        model_level = str(
            workbench.get("model_level") or contract.get("model_level") or "unmodeled"
        )
        proof_status = str(
            workbench.get("proof_status") or contract.get("proof_status")
            or contract.get("status") or "missing"
        )
        open_count = int(evidence.get("open_count") or 0)
        critical_count = int(evidence.get("critical_count") or 0)
        falsifiers = [
            row for row in ((contract.get("monitoring") or {}).get("falsifiers") or [])
            if str(row or "").strip()
        ]
        freshness, freshness_blockers = _freshness(dates, requirements, as_of_date)
        rank, bucket, state = _priority_and_state(
            proof_status=proof_status,
            model_level=model_level,
            open_count=open_count,
            critical_count=critical_count,
            freshness_blockers=freshness_blockers,
            falsifier_count=len(falsifiers),
            minimum_falsifiers=minimum_falsifiers,
            committee=committee,
        )

        blockers: list[dict] = []
        if critical_count:
            blockers.append({"code": "critical_evidence_gaps", "severity": "critical", "count": critical_count})
        if open_count:
            blockers.append({"code": "open_evidence_gaps", "severity": "high", "count": open_count})
        if proof_status != "decision_grade":
            blockers.append({"code": "proof_not_decision_grade", "severity": "high", "value": proof_status})
        if model_level not in REVIEWED_MODEL_LEVELS:
            blockers.append({"code": "stock_specific_model_required", "severity": "high", "value": model_level})
        blockers.extend(freshness_blockers)
        if len(falsifiers) < minimum_falsifiers:
            blockers.append({
                "code": "explicit_falsifier_required",
                "severity": "medium",
                "count": len(falsifiers),
                "minimum": minimum_falsifiers,
            })

        items.append({
            "ticker": ticker,
            "tier": 1,
            "tier_label": assignment.get("label"),
            "tier_reason_codes": [
                row.get("code") for row in (assignment.get("assignment_reasons") or [])
                if row.get("qualifying_tier") == 1
            ],
            "proof_status": proof_status,
            "model_level": model_level,
            "evidence_status": evidence.get("status") or ("gaps_open" if open_count else "clear"),
            "open_gap_count": open_count,
            "critical_gap_count": critical_count,
            "falsifier_count": len(falsifiers),
            "freshness": freshness,
            "committee": {
                "status": committee.get("status") or "not_started",
                "stage": committee.get("stage"),
                "owner_status": committee.get("owner_status") or "pending",
                "completed": (committee.get("analysis_progress") or {}).get("completed", 0),
                "required": (committee.get("analysis_progress") or {}).get("required", 0),
                "remaining": max(
                    0,
                    int((committee.get("analysis_progress") or {}).get("required", 0) or 0)
                    - int((committee.get("analysis_progress") or {}).get("completed", 0) or 0),
                ),
                "invalid_output_count": len(committee.get("invalid_outputs") or []),
                "current_phase": committee.get("current_phase"),
                "next_outputs": committee.get("next_outputs") or [],
            },
            "readiness_state": state,
            "priority": {"rank": rank, "bucket": bucket},
            "blockers": blockers,
            "next_action": _next_action(state, workbench, contract, freshness_blockers),
            "source_refs": {
                "tier_assignment": TIERS_REL.as_posix(),
                "contract": f"{ticker}/research/valuation_contract.json",
                "workbench": f"{ticker}/research/valuation_workbench.json",
            },
        })

    items.sort(key=lambda row: (
        row["priority"]["rank"],
        -row["critical_gap_count"],
        # Within the active committee bucket, repair invalid legacy outputs
        # first, then finish the packets with the least valid work remaining.
        0 if (row.get("committee") or {}).get("invalid_output_count") else 1,
        int((row.get("committee") or {}).get("remaining") or 999),
        row["ticker"],
    ))
    states = Counter(row["readiness_state"] for row in items)
    buckets = Counter(row["priority"]["bucket"] for row in items)
    tier_1_count = sum(
        int((row or {}).get("tier") or 3) == 1
        for row in (tiers.get("assignments") or {}).values()
    )
    validation_errors = []
    if len(items) != tier_1_count:
        validation_errors.append(f"compiled {len(items)} items for {tier_1_count} Tier 1 assignments")
    if len({row["ticker"] for row in items}) != len(items):
        validation_errors.append("duplicate Tier 1 readiness items")
    if any((row.get("tier") != 1) for row in items):
        validation_errors.append("non-Tier 1 item entered the Tier 1 readiness queue")

    return {
        "schema_version": "1.0",
        "as_of": as_of_value,
        "policy_id": policy.get("policy_id"),
        "policy_ref": POLICY_REL.as_posix(),
        "tier_manifest_ref": TIERS_REL.as_posix(),
        "semantics": {
            "purpose": "order Tier 1 research and review work without changing evidence, model, committee, or owner state",
            "capital_authority": "human_decision_only",
        },
        "requirements": requirements,
        "summary": {
            "tier_1_count": len(items),
            "action_required_count": sum(row["readiness_state"] != "owner_approved" for row in items),
            "owner_approved_count": states.get("owner_approved", 0),
            "committee_ready_count": states.get("committee_ready", 0),
            "research_blocked_count": states.get("research_blocked", 0),
            "model_deepening_required_count": states.get("model_deepening_required", 0),
            "freshness_refresh_required_count": states.get("freshness_refresh_required", 0),
            "readiness_state_counts": dict(sorted(states.items())),
            "priority_bucket_counts": dict(sorted(buckets.items())),
        },
        "items": items,
        "validation": {
            "status": "fail" if validation_errors else "pass",
            "errors": validation_errors,
            "checks": {
                "exactly_one_item_per_tier_1_security": not validation_errors,
                "capital_authority_is_human_only": True,
            },
        },
    }


def render(payload: dict) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    payload = build(args.date, args.root)
    target = args.out or args.root / OUTPUT_REL
    expected = render(payload)
    if args.check:
        actual = target.read_text(encoding="utf-8") if target.exists() else ""
        if actual != expected:
            print(f"Tier 1 readiness queue is stale: {target}")
            return 1
        print(f"Tier 1 readiness queue is current: {target}")
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(expected, encoding="utf-8")
    print(json.dumps(payload["summary"], sort_keys=True))
    return 0 if payload["validation"]["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
