#!/usr/bin/env python3
"""Derive and operate the repository's single epistemic work queue.

Canonical ledgers remain authoritative. This controller only builds a
reproducible projection and appends state transitions/run receipts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from falsifier_specs import (calibration_eligibility, forecast_dates, read_json,
                             spec_payload_hash)
from resolve_falsifiers import load_outcomes

ROOT = Path(__file__).resolve().parents[2]
QUEUE_REL = Path("_system/data/epistemic_work_queue.json")
STATE_REL = Path("_system/data/epistemic_state.jsonl")
STATUS_REL = Path("_system/research/epistemic_loop_status.json")
AUTHORING_VIEW_REL = Path("_system/data/falsifier_authoring_queue.json")
RUNS_REL = Path("_system/data/runs/epistemic_loop")
TERMINAL = {"succeeded", "terminal_unresolvable", "cancelled"}


def _jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _head(root: Path) -> str:
    result = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                            text=True, capture_output=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _work_id(kind: str, ticker: str = "", identity: str = "", period: str = "") -> str:
    raw = f"{kind}|{ticker.upper()}|{identity}|{period}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _state_projection(events: list[dict]) -> dict[str, dict]:
    current = {}
    for event in events:
        work_id = str(event.get("work_id") or "")
        if work_id:
            current[work_id] = event
    return current


def _component_fingerprint(component: dict) -> str:
    raw = json.dumps(component, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def _source_ready_owner_earnings(root: Path, ticker: str) -> bool:
    doc = read_json(root / ticker / "research/evidence/sec_companyfacts.json")
    gaap = (doc.get("facts") or {}).get("us-gaap") or {}
    return ("NetCashProvidedByUsedInOperatingActivities" in gaap
            and any(tag in gaap for tag in (
                "PaymentsToAcquireProductiveAssets",
                "PaymentsToAcquirePropertyPlantAndEquipment",
                "PaymentsForProceedsFromOtherPropertyPlantAndEquipment")))


def _source_ready_cash(root: Path, ticker: str) -> bool:
    doc = read_json(root / ticker / "research/evidence/sec_companyfacts.json")
    gaap = (doc.get("facts") or {}).get("us-gaap") or {}
    return any(tag in gaap for tag in (
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ))


def _prospective_missing_components(contract: dict) -> set[str] | None:
    """Return the fail-closed recovery set, or None for a normal contract.

    A contract blocked only by the prospective falsifier gate must remain
    authorable. Otherwise the gate suppresses the exact work required to clear
    itself. Other evidence blockers retain their fail-closed behavior.
    """
    if contract.get("status") == "decision_grade":
        return None
    gate = ((contract.get("falsifier_coverage") or {}).get("prospective_gate") or {})
    missing = {str(value) for value in gate.get("missing_components") or [] if value}
    blockers = [str(value) for value in (contract.get("evidence") or {}).get("blockers") or []]
    if (contract.get("status") == "evidence_blocked" and missing and blockers
            and all(value.startswith("prospective_falsifier_gate:") for value in blockers)):
        return missing
    return set()


def _authoring_metric(root: Path, ticker: str, component: dict,
                      prospective_recovery: bool) -> tuple[str, bool] | None:
    """Select a resolvable metric without broadening the normal pilot cohort."""
    method = str(component.get("method") or "")
    if not prospective_recovery and method != "owner_earnings_reinvestment_dcf":
        return None
    if method == "net_asset_value":
        return "cash_and_equivalents_usd", _source_ready_cash(root, ticker)
    return "normalized_owner_earnings_ttm_m_v2", _source_ready_owner_earnings(root, ticker)


def _forecast_tasks(root: Path, today: date, state: dict[str, dict]) -> list[dict]:
    outcomes = load_outcomes(root / "_system/research/falsifier_outcomes.jsonl")
    resolved = {str(row.get("spec_hash")) for row in outcomes if row.get("spec_hash")}
    attempts = _jsonl(root / "_system/research/falsifier_evidence_attempts.jsonl")
    latest_attempt = {}
    for attempt in attempts:
        key = str(attempt.get("spec_hash") or "")
        if key:
            latest_attempt[key] = attempt
    tasks = []
    for path in sorted(root.glob("*/research/falsifier_specs.json")):
        ticker = path.parents[1].name.upper()
        for spec in read_json(path).get("specs") or []:
            spec_hash = spec_payload_hash(spec)
            if spec_hash in resolved:
                continue
            measurement, observable, deadline = forecast_dates(spec)
            if spec.get("untestable"):
                # Legacy untestable declarations are diagnostic coverage debt,
                # not executable adapter tasks. A v3 author must name the
                # concrete missing adapter before automation can own it.
                if not spec.get("required_adapter"):
                    continue
                identity = str(spec.get("spec_id") or spec_hash)
                work_id = _work_id("build_evidence_adapter", ticker, identity,
                                   measurement.isoformat() if measurement else "")
                tasks.append({
                    "work_id": work_id, "task_type": "build_evidence_adapter",
                    "ticker": ticker, "spec_id": spec.get("spec_id"),
                    "spec_hash": spec_hash, "priority": 55,
                    "reason": str(spec.get("untestable_reason_code") or "legacy_unresolved_adapter"),
                    "required_output": str(spec.get("required_adapter") or "typed observation adapter"),
                    "acceptance_tests": ["historical replay passes", "period and unit semantics are explicit"],
                })
                continue
            if observable and observable <= today:
                attempt = latest_attempt.get(spec_hash) or {}
                reason = str(attempt.get("reason_code") or "observable_unresolved")
                state_name = "needs_semantic_review" if reason in {
                    "period_end_mismatch", "fiscal_period_mismatch", "unit_mismatch",
                    "ttm_period_inputs_missing", "adapter_missing"} else "queued"
                work_id = _work_id("resolve_falsifier", ticker,
                                   str(spec.get("spec_id") or spec_hash),
                                   measurement.isoformat() if measurement else "")
                tasks.append({
                    "work_id": work_id, "task_type": "resolve_falsifier",
                    "ticker": ticker, "spec_id": spec.get("spec_id"),
                    "spec_hash": spec_hash, "measurement_period_end":
                    measurement.isoformat() if measurement else None,
                    "deadline": deadline.isoformat() if deadline else None,
                    "priority": 95 if deadline and (deadline - today).days <= 7 else 80,
                    "reason": reason, "suggested_state": state_name,
                    "source_ref": str(path.relative_to(root)).replace("\\", "/"),
                    "acceptance_tests": ["normalized observation matches frozen period and unit",
                                         "outcome pins exact spec and evidence hashes"],
                })
    return tasks


def _authoring_tasks(root: Path, state: dict[str, dict]) -> list[dict]:
    tasks = []
    new_tasks = []
    policy = read_json(root / "_system/config/epistemic_loop_policy.json")
    inventory = policy.get("forecast_inventory") or {}
    eligible_total = 0
    for sidecar_path in root.glob("*/research/falsifier_specs.json"):
        eligible_total += sum(calibration_eligibility(spec)[0]
                              for spec in read_json(sidecar_path).get("specs") or [])
    new_limit = int(inventory.get("pilot_size") or 5) if not eligible_total else int(
        inventory.get("active_target_per_route") or 30)
    for contract_path in sorted(root.glob("*/research/valuation_contract.json")):
        ticker = contract_path.parents[1].name.upper()
        contract = read_json(contract_path)
        missing_filter = _prospective_missing_components(contract)
        if missing_filter == set():
            continue
        prospective_recovery = missing_filter is not None
        route = read_json(root / ticker / "research/valuation_route.json")
        if route.get("profile_id") != "quality_reinvestment":
            continue
        sidecar = read_json(root / ticker / "research/falsifier_specs.json")
        eligible_components = {str(spec.get("component_id")) for spec in sidecar.get("specs") or []
                               if calibration_eligibility(spec)[0]}
        for component in contract.get("economic_ownership_map") or []:
            if not isinstance(component, dict):
                continue
            component_id = str(component.get("component_id") or "")
            if (not component_id or component_id in eligible_components
                    or (missing_filter is not None and component_id not in missing_filter)):
                continue
            metric = _authoring_metric(root, ticker, component, prospective_recovery)
            if metric is None:
                continue
            metric_definition_id, source_ready = metric
            method = str(component.get("method") or "")
            fingerprint = _component_fingerprint(component)
            drafts = []
            for draft_path in (root / ticker / "research/falsifier_drafts").glob("*.json"):
                draft = read_json(draft_path)
                if draft.get("component_fingerprint") == fingerprint:
                    drafts.append((draft_path, draft))
            if drafts:
                draft_path, draft = sorted(drafts, key=lambda pair: pair[0].name)[-1]
                draft_status = str(draft.get("status") or "awaiting_review")
                if draft_status == "published":
                    continue
                if draft_status == "rejected":
                    draft_id = str(draft.get("draft_id") or draft_path.stem)
                    work_id = _work_id(
                        "author_forecast", ticker,
                        f"{fingerprint}|revision|{draft_id}",
                    )
                    tasks.append({
                        "work_id": work_id, "task_type": "author_forecast",
                        "ticker": ticker, "component_id": component_id,
                        "component_fingerprint": fingerprint,
                        "contract_hash": hashlib.sha256(contract_path.read_bytes()).hexdigest(),
                        "method_id": method, "power_zone": "quality_reinvestment",
                        "metric_definition_id": metric_definition_id,
                        "source_preflight_candidate": source_ready,
                        "draft_ref": str(draft_path.relative_to(root)).replace("\\", "/"),
                        "rejection_reasons": list(draft.get("rejection_reasons") or []),
                        "frozen_component": component,
                        "priority": 92, "reason": "forecast_draft_rejected",
                        "acceptance_tests": [
                            "author addresses every independent-review reason",
                            "target period remains unobservable at registration",
                            "current metric-definition replay passes",
                            "threshold and probability reconcile to cutoff evidence",
                            "a separate reviewer approves the revision",
                        ],
                    })
                    continue
                task_type = "publish_forecast" if draft_status == "approved" else "review_forecast"
                work_id = _work_id(task_type, ticker, str(draft.get("draft_id") or draft_path.stem))
                tasks.append({
                    "work_id": work_id, "task_type": task_type, "ticker": ticker,
                    "component_id": component_id, "component_fingerprint": fingerprint,
                    "draft_ref": str(draft_path.relative_to(root)).replace("\\", "/"),
                    "priority": 90 if task_type == "publish_forecast" else 85,
                    "reason": f"forecast_draft_{draft_status}",
                    "acceptance_tests": (["approved draft promotes without editing prior revisions"]
                                         if task_type == "publish_forecast" else
                                         ["reviewer differs from author and authoring run",
                                          "threshold materiality and source replay are challenged",
                                          "approve or reject with a typed reason"]),
                })
                continue
            work_id = _work_id("author_forecast", ticker, fingerprint)
            new_tasks.append({
                "work_id": work_id, "task_type": "author_forecast",
                "ticker": ticker, "component_id": component_id,
                "component_fingerprint": fingerprint,
                "contract_hash": hashlib.sha256(contract_path.read_bytes()).hexdigest(),
                "method_id": method, "power_zone": "quality_reinvestment",
                "metric_definition_id": metric_definition_id,
                "priority": 75 if source_ready else 45,
                "source_preflight_candidate": source_ready,
                "reason": "first_route_cohort_deficit",
                "source_ref": str(contract_path.relative_to(root)).replace("\\", "/"),
                "frozen_component": component,
                "acceptance_tests": [
                    "target period is not observable at registration",
                    "historical adapter replay passes",
                    "threshold is economically material",
                    "independent reviewer approves",
                ],
            })
    new_tasks.sort(key=lambda item: (not item["source_preflight_candidate"], item["ticker"], item["component_id"]))
    return tasks + new_tasks[:new_limit]


def _committee_tasks(root: Path, today: date) -> list[dict]:
    monitoring = read_json(root / "_system/research/committee_monitoring.json")
    tasks = []
    for item in monitoring.get("items") or []:
        if item.get("status") not in {"due", "needs_semantic_review"}:
            continue
        work_id = _work_id("record_committee_outcome", str(item.get("ticker")),
                           str(item.get("committee_ref")), str(item.get("horizon_months")))
        tasks.append({
            "work_id": work_id, "task_type": "record_committee_outcome",
            "ticker": item.get("ticker"), "priority": 70,
            "committee_ref": item.get("committee_ref"),
            "horizon_months": item.get("horizon_months"),
            "deadline": item.get("due_date"),
            "reason": item.get("last_attempt_reason") or "committee_horizon_due",
            "suggested_state": ("needs_semantic_review" if item.get("status") ==
                                "needs_semantic_review" else "queued"),
            "acceptance_tests": ["split-and-dividend-aware return is provenance complete",
                                 "existing horizon is not duplicated"],
        })
    return tasks


def _memory_tasks(root: Path) -> list[dict]:
    summary = read_json(root / "_system/reviews/pending/memory_triage_summary.json")
    tasks = []
    proposal = summary.get("proposal_loop") or summary
    undecided = int(proposal.get("undecided") or proposal.get("pending_count") or 0)
    pending_delivery = int(proposal.get("routed_delivery_pending") or 0)
    if undecided or pending_delivery:
        identity = f"{summary.get('as_of') or summary.get('generated_at')}|{undecided}|{pending_delivery}"
        work_id = _work_id("memory_triage", identity=identity)
        tasks.append({
            "work_id": work_id, "task_type": "memory_triage", "priority": 50,
            "reason": f"{undecided}_undecided_proposals|{pending_delivery}_pending_deliveries",
            "acceptance_tests": ["nondurable items are routed or dropped",
                                 "durable items remain human promotion only",
                                 "delivery acknowledgement is recorded"],
        })
    return tasks


def build(root: Path = ROOT, today: date | None = None, write: bool = True) -> dict:
    today = today or date.today()
    head = _head(root)
    events = _jsonl(root / STATE_REL)
    state = _state_projection(events)
    items = (_forecast_tasks(root, today, state) + _authoring_tasks(root, state)
             + _committee_tasks(root, today) + _memory_tasks(root))
    for item in items:
        prior = state.get(item["work_id"]) or {}
        item["state"] = (prior.get("state") if prior.get("state") not in TERMINAL
                         else prior.get("state")) or item.pop("suggested_state", "queued")
        item["attempts"] = int(prior.get("attempts") or 0)
        item["lease_owner"] = prior.get("lease_owner")
        item["lease_expires_at"] = prior.get("lease_expires_at")
        item["input_sha"] = head
    items.sort(key=lambda item: (-int(item.get("priority") or 0), item["work_id"]))
    queue = {
        "schema_version": "1.0", "as_of": today.isoformat(), "input_sha": head,
        "items": items,
        "counts": {state_name: sum(item["state"] == state_name for item in items)
                   for state_name in sorted({item["state"] for item in items})},
    }
    calibration = read_json(root / "_system/research/falsifier_calibration.json")
    brief = read_json(root / "_system/research/calibration_brief.json")
    eligible_active = 0
    diagnostic_active = 0
    for path in root.glob("*/research/falsifier_specs.json"):
        for spec in read_json(path).get("specs") or []:
            if spec.get("untestable"):
                continue
            if calibration_eligibility(spec)[0]:
                eligible_active += 1
            else:
                diagnostic_active += 1
    health = "HALTED" if calibration.get("status") == "integrity_failure" else (
        "CALIBRATION_READY" if brief.get("global_status") == "eligible_for_prompt_challenge" else
        "COLLECTING" if eligible_active else "BOOTSTRAP_BLOCKED")
    status = {
        "schema_version": "1.0", "as_of": today.isoformat(), "input_sha": head,
        "health_state": health,
        "eligible_active_forecasts": eligible_active,
        "diagnostic_active_forecasts": diagnostic_active,
        "resolved_outcomes": int(calibration.get("resolved_outcomes") or 0),
        "eligible_scored_outcomes": int(calibration.get("eligible_scored_outcomes") or 0),
        "calibration_release_hash": brief.get("release_hash"),
        "calibration_status": brief.get("global_status") or "insufficient_outcomes",
        "queue": {"total": len(items), **queue["counts"]},
        "owner_only_blockers": ["durable_memory_promotion", "live_capital_decision",
                                "new_framework", "disputed_ground_truth"],
    }
    if write:
        for relative, payload in ((QUEUE_REL, queue), (STATUS_REL, status)):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        authoring = {**queue, "items": [item for item in items if item["task_type"] in
                                        {"author_forecast", "review_forecast", "publish_forecast"}]}
        (root / AUTHORING_VIEW_REL).write_text(json.dumps(authoring, indent=2) + "\n", encoding="utf-8")
        receipt = {
            "schema_version": "1.0", "run_type": "epistemic_loop_controller",
            "run_date": today.isoformat(), "input_sha": head, "output_sha": head,
            "status": "no_work" if not items else "success",
            "counts": {"work_items": len(items), "authoring_items": len(authoring["items"])},
            "outputs": [str(QUEUE_REL).replace("\\", "/"), str(STATUS_REL).replace("\\", "/")],
        }
        receipt_path = root / RUNS_REL / f"run_{today.isoformat()}_{head[:12]}.json"
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return {"queue": queue, "status": status}


def transition(root: Path, work_id: str, state: str, reason: str | None,
               actor: str | None) -> dict:
    allowed = {"queued", "leased", "heartbeat", "waiting_observation", "retry_wait",
               "needs_semantic_review", "needs_human", "succeeded",
               "terminal_unresolvable", "cancelled"}
    if state not in allowed:
        raise ValueError(f"invalid state {state}")
    now = datetime.now(timezone.utc)
    event = {
        "event_id": hashlib.sha256(f"{work_id}|{state}|{now.isoformat()}".encode()).hexdigest()[:24],
        "work_id": work_id, "state": state, "reason": reason,
        "actor": actor or "epistemic-loop-controller", "recorded_at": now.isoformat(),
    }
    if state == "leased":
        policy = read_json(root / "_system/config/epistemic_loop_policy.json")
        minutes = int((policy.get("leases") or {}).get("agent_minutes") or 120)
        event["lease_owner"] = actor
        event["lease_expires_at"] = (now + timedelta(minutes=minutes)).isoformat()
    path = root / STATE_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")
    return event


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--transition")
    parser.add_argument("--state")
    parser.add_argument("--reason")
    parser.add_argument("--actor")
    args = parser.parse_args()
    if args.transition:
        if not args.state:
            parser.error("--state is required with --transition")
        print(json.dumps(transition(args.root, args.transition, args.state,
                                    args.reason, args.actor), indent=2))
        return 0
    result = build(args.root, date.fromisoformat(args.date), not args.dry_run)
    print(json.dumps({"health": result["status"]["health_state"],
                      "work_items": len(result["queue"]["items"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
