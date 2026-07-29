#!/usr/bin/env python3
"""Fail only when an evidence blocker has no autonomous recovery task."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from portfolio_registry import ROOT, load_registry


def read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=("all-blocked", "ls-algo", "all"), default="all-blocked")
    args = parser.parse_args()
    errors = []
    registry = load_registry()
    for ticker, holding in sorted((registry.get("holdings") or {}).items()):
        sleeve = holding.get("investment_sleeve") or (holding.get("classification") or {}).get("investment_sleeve")
        research = ROOT / ticker / "research"
        contract = read(research / "valuation_contract.json")
        if args.scope == "ls-algo" and sleeve != "ls_algo_underlying":
            continue
        if args.scope == "all-blocked" and str(contract.get("status") or "evidence_blocked") == "decision_grade":
            continue
        workbench = read(research / "valuation_workbench.json")
        task_doc = read(research / "evidence_task_queue.json")
        identity = read(research / "security_identity.json")
        route = read(research / "valuation_route.json")
        task_ids = {str(row.get("id")) for row in task_doc.get("tasks") or []}
        if str(contract.get("status") or "evidence_blocked") != "decision_grade" and not task_ids:
            errors.append(f"{ticker}: evidence-blocked contract has no recovery tasks")
        for gap in ((workbench.get("evidence") or {}).get("gaps") or []):
            if str(gap.get("status") or "open").lower() not in {"closed", "complete", "resolved"}:
                gap_id = str(gap.get("id") or "")
                if gap_id and gap_id not in task_ids:
                    errors.append(f"{ticker}: blocker {gap_id} has no recovery task")
        if (str(holding.get("market") or "US") == "US"
                and identity.get("security_type") != "exchange_traded_fund"
                and not ((holding.get("download") or {}).get("cik"))
                and "sec_identity_required" not in task_ids):
            errors.append(f"{ticker}: missing CIK has no identity recovery task")
        if (
            (
                str(route.get("status") or "") == "default_needs_review"
                or not (route.get("primary_methods") or [])
                or float(route.get("score") or 0) <= 0
            )
            and "valuation_route_classification_required" not in task_ids
        ):
            errors.append(f"{ticker}: default Power Zone route has no classification recovery task")
        for task in task_doc.get("tasks") or []:
            if str(task.get("status") or "").lower() == "unavailable" and not task.get("last_error"):
                errors.append(f"{ticker}: unavailable task {task.get('id')} has no terminal error")
    if errors:
        for error in errors[:50]:
            print(f"ERROR: {error}")
        return 1
    print(f"OK: every {args.scope} blocker has an autonomous recovery task")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
