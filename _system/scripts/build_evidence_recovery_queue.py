#!/usr/bin/env python3
"""Compile every valuation blocker into executable, persistent evidence tasks."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from portfolio_registry import ROOT, load_registry

OUT = ROOT / "_system" / "data" / "evidence_recovery_queue.json"
DONE_STATUSES = {"evidence_ready", "closed", "complete", "resolved"}
TERMINAL_STATUSES = {"unavailable", "manual_only"}
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_TERMINAL_ERROR = "Automated collection exhausted retry budget without satisfying acceptance test."


def read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def collector_for(text: str) -> str:
    value = text.lower()
    if any(word in value for word in ("classification", "archetype", "power zone", "method route")):
        return "primary_documents_then_classification"
    if any(word in value for word in ("filing", "contract", "maturity", "debt", "shares", "tax", "legal", "royalty")):
        return "sec_primary_documents"
    if any(word in value for word in ("price", "market", "capacity", "utilization", "margin", "unit value")):
        return "market_and_filing_facts"
    return "primary_documents_then_model"


def _stable_blocker_id(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    return f"contract_blocker:{digest}"


def _task_from_gap(gap: dict, previous: dict | None = None) -> dict:
    previous = previous or {}
    text = " ".join(str(gap.get(key) or "") for key in ("question", "evidence_required", "acceptance_test"))
    task_id = str(gap.get("id") or _stable_blocker_id(text))
    return {
        "id": task_id,
        "priority": gap.get("priority") or "critical",
        "field_id": gap.get("field_id"),
        "method_id": gap.get("method_id"),
        "question": gap.get("question") or "Resolve the valuation-contract blocker with primary evidence.",
        "evidence_required": gap.get("evidence_required") or gap.get("question"),
        "acceptance_test": gap.get("acceptance_test")
        or "The blocker is absent after rebuilding the universal valuation contract.",
        "collector": gap.get("collector") or collector_for(text),
        "status": previous.get("status") or "pending_collection",
        "attempts": int(previous.get("attempts") or 0),
        "max_attempts": int(previous.get("max_attempts") or DEFAULT_MAX_ATTEMPTS),
        "last_attempt_at": previous.get("last_attempt_at"),
        "next_attempt_at": previous.get("next_attempt_at"),
        "last_error": previous.get("last_error"),
        "evidence_refs": previous.get("evidence_refs") or [],
    }


def _ensure_terminal_error(task: dict) -> dict:
    """Keep persisted terminal tasks explainable to the recovery validator."""
    if (
        str(task.get("status") or "").lower() in TERMINAL_STATUSES
        and not str(task.get("last_error") or "").strip()
    ):
        task["last_error"] = DEFAULT_TERMINAL_ERROR
    return task


def _contract_gaps(contract: dict) -> list[dict]:
    return [
        {
            "id": _stable_blocker_id(str(blocker)),
            "priority": "critical",
            "question": str(blocker),
            "evidence_required": str(blocker),
            "acceptance_test": "The blocker is absent after rebuilding the universal valuation contract.",
            "status": "open",
        }
        for blocker in ((contract.get("evidence") or {}).get("blockers") or [])
        if str(blocker).strip()
    ]


def _scope_includes(scope: str, holding: dict, contract: dict) -> bool:
    sleeve = holding.get("investment_sleeve") or (holding.get("classification") or {}).get("investment_sleeve")
    if scope == "ls-algo":
        return sleeve == "ls_algo_underlying"
    if scope == "all":
        return True
    return str(contract.get("status") or "evidence_blocked") != "decision_grade"


def build(scope: str = "all-blocked", *, write: bool = True) -> dict:
    registry = load_registry()
    rows = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    covered_blockers = 0
    terminal_tasks = 0
    for ticker, holding in sorted((registry.get("holdings") or {}).items()):
        research = ROOT / ticker / "research"
        contract = read(research / "valuation_contract.json")
        if not _scope_includes(scope, holding, contract):
            continue

        workbench = read(research / "valuation_workbench.json")
        route = read(research / "valuation_route.json")
        identity = read(research / "security_identity.json")
        previous = read(research / "evidence_task_queue.json")
        prior_by_id = {str(row.get("id") or ""): row for row in previous.get("tasks") or []}
        tasks_by_id: dict[str, dict] = {}

        # Preserve method-input and route tasks emitted by the readiness compiler.
        for prior_task in previous.get("tasks") or []:
            task_id = str(prior_task.get("id") or "")
            if task_id.startswith("method_input:") or task_id in {
                "valuation_route_classification_required",
                "complete_component_model_required",
                "sec_identity_required",
            }:
                tasks_by_id[task_id] = dict(prior_task)

        gaps = [
            gap
            for gap in ((workbench.get("evidence") or {}).get("gaps") or [])
            if str(gap.get("status") or "open").lower() not in DONE_STATUSES
        ]
        if not gaps:
            gaps = _contract_gaps(contract)

        route_is_default = (
            str(route.get("status") or "") == "default_needs_review"
            or not (route.get("primary_methods") or [])
            or float(route.get("score") or 0) <= 0
        )
        if route_is_default:
            gaps.insert(0, {
                "id": "valuation_route_classification_required",
                "priority": "critical",
                "field_id": "valuation_route",
                "method_id": (identity.get("primary_method") or ((route.get("primary_methods") or [None])[0])),
                "question": "Supply source-backed classification for a non-default Power Zone valuation route.",
                "evidence_required": "security archetype, economic ownership map, investment sleeve, and component categories",
                "acceptance_test": "The canonical route has a positive score and is not default_needs_review.",
                "collector": "primary_documents_then_classification",
                "status": "open",
            })

        if (
            str(holding.get("market") or "US") == "US"
            and identity.get("security_type") != "exchange_traded_fund"
            and not ((holding.get("download") or {}).get("cik"))
        ):
            gaps.insert(0, {
                "id": "sec_identity_required",
                "priority": "critical",
                "question": "Resolve the issuer SEC CIK before primary filing collection.",
                "evidence_required": "Committed SEC ticker/CIK mapping or verified SEC submissions identity.",
                "acceptance_test": "Registry download.cik is a ten-digit verified CIK.",
                "collector": "sec_primary_documents",
                "status": "open",
            })

        if not gaps and str(contract.get("status") or "evidence_blocked") != "decision_grade":
            required = route.get("required_evidence") or []
            gaps = [{
                "id": "complete_component_model_required",
                "priority": "critical",
                "field_id": "component_model",
                "method_id": identity.get("primary_method") or ((route.get("primary_methods") or [None])[0]),
                "question": "Build a complete primary-sourced component valuation.",
                "evidence_required": "; ".join(required),
                "acceptance_test": "Every material economic claim is valued exactly once using an approved deterministic proof.",
                "collector": "primary_documents_then_model",
                "status": "open",
            }]

        for gap in gaps:
            task_id = str(gap.get("id") or "")
            if task_id in tasks_by_id:
                continue
            tasks_by_id[task_id] = _task_from_gap(gap, prior_by_id.get(task_id))

        tasks = list(tasks_by_id.values())
        tasks = [_ensure_terminal_error(task) for task in tasks]
        for task in tasks:
            task.setdefault("max_attempts", DEFAULT_MAX_ATTEMPTS)
            task.setdefault("next_attempt_at", None)
            task.setdefault("last_error", None)

        incomplete = [task for task in tasks if str(task.get("status") or "").lower() not in DONE_STATUSES]
        if not incomplete:
            continue
        covered_blockers += len(incomplete)
        terminal_count = sum(str(task.get("status") or "").lower() in TERMINAL_STATUSES for task in incomplete)
        terminal_tasks += terminal_count

        method_id = previous.get("method_id") or identity.get("primary_method") or (
            (route.get("primary_methods") or [None])[0]
        )
        packet = {
            "schema_version": "3.0",
            "ticker": ticker,
            "updated_at": now,
            "method_id": method_id,
            "method_profile": route.get("profile_id") or identity.get("valuation_profile"),
            "route_status": route.get("status"),
            "ready_count": sum(str(task.get("status") or "").lower() in DONE_STATUSES for task in tasks),
            "task_count": len(tasks),
            "terminal_count": terminal_count,
            "tasks": tasks,
        }
        if write:
            research.mkdir(parents=True, exist_ok=True)
            (research / "evidence_task_queue.json").write_text(
                json.dumps(packet, indent=2) + "\n",
                encoding="utf-8",
            )

        trigger = read(research / "committee_trigger.json")
        pending_attempts = [
            int(task.get("attempts") or 0)
            for task in incomplete
            if str(task.get("status") or "").lower() not in TERMINAL_STATUSES
        ]
        next_attempts = sorted(
            str(task.get("next_attempt_at"))
            for task in incomplete
            if task.get("next_attempt_at")
        )
        rows.append({
            "ticker": ticker,
            "triggered": str(trigger.get("status") or "").lower() == "open",
            "decision_status": contract.get("status") or "evidence_blocked",
            "method_id": method_id,
            "method_profile": packet["method_profile"],
            "route_status": packet["route_status"],
            "critical_count": sum(task.get("priority") == "critical" for task in incomplete),
            "ready_count": packet["ready_count"],
            "task_count": packet["task_count"],
            "pending_count": len(incomplete) - terminal_count,
            "terminal_count": terminal_count,
            "min_attempts": min(pending_attempts) if pending_attempts else DEFAULT_MAX_ATTEMPTS,
            "next_attempt_at": next_attempts[0] if next_attempts else None,
            "task_ref": f"{ticker}/research/evidence_task_queue.json",
            # Embed the packet so sparse dashboard deployments and D1 sync do
            # not need all per-security directories checked out.
            "task_packet": packet,
        })

    rows.sort(key=lambda row: (
        row["terminal_count"] > 0,
        not row["triggered"],
        -row["critical_count"],
        row["min_attempts"],
        row["ticker"],
    ))
    payload = {
        "schema_version": "3.0",
        "generated_at": now,
        "scope": scope,
        "ticker_count": len(rows),
        "covered_blocker_count": covered_blockers,
        "terminal_task_count": terminal_tasks,
        "items": rows,
    }
    if write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"evidence recovery queue: {len(rows)} tickers / {covered_blockers} blockers ({scope})")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=("all-blocked", "ls-algo", "all"), default="all-blocked")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    build(args.scope, write=not args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
