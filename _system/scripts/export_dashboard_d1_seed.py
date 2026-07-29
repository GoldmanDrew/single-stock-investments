#!/usr/bin/env python3
"""Export the current sharded dashboard snapshot as idempotent D1 SQL."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CORE = ROOT / "dashboard" / "data" / "core.json"
DEFAULT_OUTPUT = ROOT / "dashboard" / "cloudflare" / "generated" / "dashboard_seed.sql"
DEFAULT_EVIDENCE_QUEUE = ROOT / "_system" / "data" / "evidence_recovery_queue.json"
DONE_STATUSES = {"evidence_ready", "closed", "complete", "resolved"}
PROFILE_DEFAULT_METHOD = {
    "quality_reinvestment": "owner_earnings_reinvestment_dcf",
    "scarce_asset_optionality": "component_owner_cash_and_unit_nav",
    "predictable_cash_flow": "owner_cash_or_dividend_discount",
    "capital_cycle": "midcycle_capacity_value",
    "catalyst_asset_value": "probability_weighted_catalyst_nav",
    "binary_milestone": "risk_adjusted_milestone_value",
    "credit_and_normalized_returns": "capital_structure_and_excess_return",
}


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def quote(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def number(value: Any) -> float | None:
    try:
        result = float(value)
        return result if result == result and result not in {float("inf"), float("-inf")} else None
    except (TypeError, ValueError):
        return None


def upsert(table: str, columns: list[str], values: list[Any], conflict: list[str]) -> str:
    assignments = ", ".join(
        f"{column}=excluded.{column}" for column in columns if column not in conflict
    )
    return (
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES "
        f"({', '.join(quote(value) for value in values)}) "
        f"ON CONFLICT ({', '.join(conflict)}) DO UPDATE SET {assignments};"
    )


def _fallback_tasks(ticker: str, row: dict, queue_item: dict, route: dict) -> list[dict]:
    decision = row.get("valuation_decision") or {}
    if str(decision.get("status") or "evidence_blocked") == "decision_grade":
        return []
    if (
        str(route.get("status") or "") == "default_needs_review"
        or not (route.get("primary_methods") or [])
        or float(route.get("score") or 0) <= 0
    ):
        return [{
            "id": "valuation_route_classification_required",
            "priority": "critical",
            "field_id": "valuation_route",
            "method_id": ((route.get("primary_methods") or [None])[0]),
            "question": "Supply source-backed classification for a non-default Power Zone valuation route.",
            "evidence_required": "security archetype, economic ownership map, investment sleeve, and component categories",
            "acceptance_test": "The canonical route has a positive score and is not default_needs_review.",
            "collector": "primary_documents_then_classification",
            "status": "pending_collection",
            "attempts": 0,
            "max_attempts": 5,
            "evidence_refs": [],
        }]
    return [{
        "id": queue_item.get("next_gap_id") or decision.get("next_gap_id") or "complete_component_model_required",
        "priority": "critical",
        "field_id": "component_model",
        "method_id": ((route.get("primary_methods") or [None])[0]),
        "question": (
            queue_item.get("next_gap_question")
            or decision.get("next_action")
            or "Build a complete primary-sourced component valuation."
        ),
        "evidence_required": "; ".join(route.get("required_evidence") or []),
        "acceptance_test": "Every material economic claim is valued exactly once using an approved deterministic proof.",
        "collector": "primary_documents_then_model",
        "status": "pending_collection",
        "attempts": 0,
        "max_attempts": 5,
        "evidence_refs": [],
    }]


def export(
    core_path: Path,
    output: Path,
    evidence_queue_path: Path = DEFAULT_EVIDENCE_QUEUE,
) -> dict:
    raw = core_path.read_bytes()
    core = json.loads(raw)
    source_hash = hashlib.sha256(raw).hexdigest()
    generated_at = str(core.get("generated_at") or datetime.now(timezone.utc).isoformat())
    run_id = f"dashboard:{generated_at}:{source_hash[:16]}"
    imported_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    summary = core.get("summary") or {}
    rows = core.get("tickers") or []
    queue_by_ticker = {
        str(item.get("ticker") or ""): item
        for item in ((core.get("valuation_queue") or {}).get("items") or [])
    }
    aggregate_task_packets = {
        str(item.get("ticker") or "").upper(): item.get("task_packet") or {}
        for item in (read_json(evidence_queue_path).get("items") or [])
        if item.get("task_packet")
    }

    sql = [
        "-- Generated by _system/scripts/export_dashboard_d1_seed.py",
        "PRAGMA foreign_keys = ON;",
        upsert(
            "pipeline_runs",
            ["run_id", "generated_at", "source_sha256", "status", "ticker_count", "summary_json", "imported_at"],
            [run_id, generated_at, source_hash, "complete", len(rows), compact_json(summary), imported_at],
            ["run_id"],
        ),
    ]
    task_count = 0
    blocked_without_source_task = 0
    for row in rows:
        ticker = str(row.get("ticker") or "").upper()
        if not ticker:
            continue
        classification = row.get("classification") or {}
        decision = row.get("valuation_decision") or {}
        values = decision.get("value_per_share") or {}
        returns = decision.get("annualized_return_at_price_pct") or {}
        route = read_json(ROOT / ticker / "research" / "valuation_route.json")
        if not route:
            route = dict(((row.get("power_zones") or {}).get("valuation_route") or {}))
            profile_id = route.get("profile_id") or decision.get("method_profile")
            if profile_id:
                route["profile_id"] = profile_id
                route.setdefault(
                    "primary_methods",
                    [PROFILE_DEFAULT_METHOD.get(profile_id)]
                    if PROFILE_DEFAULT_METHOD.get(profile_id)
                    else [],
                )
            route.setdefault(
                "score",
                1 if route.get("status") and route.get("status") != "default_needs_review" else 0,
            )
        queue_item = queue_by_ticker.get(ticker) or {}

        sql.append(upsert(
            "securities",
            [
                "ticker", "company", "market", "exchange_code", "investment_sleeve",
                "stance", "archetype", "last_research_at", "latest_run_id", "updated_at",
            ],
            [
                ticker,
                row.get("company") or ticker,
                row.get("market"),
                row.get("exchange"),
                classification.get("investment_sleeve"),
                classification.get("stance"),
                classification.get("archetype"),
                row.get("last_research"),
                run_id,
                generated_at,
            ],
            ["ticker"],
        ))
        sql.append(upsert(
            "valuation_current",
            [
                "ticker", "decision_status", "provisional", "method_profile", "primary_power_zone",
                "price_per_share", "value_low", "value_base", "value_high",
                "annualized_return_base_pct", "open_gap_count", "critical_gap_count",
                "next_gap_id", "next_gap_question", "source_as_of", "latest_run_id",
                "payload_json", "updated_at",
            ],
            [
                ticker,
                decision.get("status") or "evidence_blocked",
                bool(decision.get("provisional", True)),
                decision.get("method_profile") or route.get("profile_id"),
                decision.get("primary_power_zone") or route.get("label"),
                number(decision.get("price_per_share")),
                number(values.get("low")),
                number(values.get("base")),
                number(values.get("high")),
                number(returns.get("base")),
                int(decision.get("open_gap_count") or 0),
                int(decision.get("critical_gap_count") or 0),
                decision.get("next_gap_id") or queue_item.get("next_gap_id"),
                queue_item.get("next_gap_question"),
                classification.get("analysis_as_of") or row.get("last_research"),
                run_id,
                compact_json(decision),
                generated_at,
            ],
            ["ticker"],
        ))

        task_doc = (
            read_json(ROOT / ticker / "research" / "evidence_task_queue.json")
            or aggregate_task_packets.get(ticker)
            or {}
        )
        tasks = task_doc.get("tasks") or _fallback_tasks(ticker, row, queue_item, route)
        if (
            str(decision.get("status") or "evidence_blocked") != "decision_grade"
            and not (task_doc.get("tasks") or [])
        ):
            blocked_without_source_task += 1
        for task in tasks:
            task_id = str(task.get("id") or "")
            if not task_id:
                continue
            task_count += 1
            sql.append(upsert(
                "evidence_tasks",
                [
                    "ticker", "task_id", "priority", "field_id", "method_id", "question",
                    "evidence_required", "acceptance_test", "collector", "status", "attempts",
                    "max_attempts", "last_attempt_at", "next_attempt_at", "last_error",
                    "evidence_refs_json", "latest_run_id", "updated_at",
                ],
                [
                    ticker,
                    task_id,
                    task.get("priority") or "critical",
                    task.get("field_id"),
                    task.get("method_id") or task_doc.get("method_id"),
                    task.get("question"),
                    task.get("evidence_required"),
                    task.get("acceptance_test"),
                    task.get("collector"),
                    task.get("status") or "pending_collection",
                    int(task.get("attempts") or 0),
                    int(task.get("max_attempts") or 5),
                    task.get("last_attempt_at"),
                    task.get("next_attempt_at"),
                    task.get("last_error"),
                    compact_json(task.get("evidence_refs") or []),
                    run_id,
                    task_doc.get("updated_at") or generated_at,
                ],
                ["ticker", "task_id"],
            ))

    sql.extend([
        f"DELETE FROM evidence_tasks WHERE latest_run_id <> {quote(run_id)};",
        f"DELETE FROM securities WHERE latest_run_id <> {quote(run_id)};",
        "DELETE FROM pipeline_runs WHERE generated_at < datetime('now', '-365 days');",
        "",
    ])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(sql), encoding="utf-8")
    report = {
        "run_id": run_id,
        "generated_at": generated_at,
        "source_sha256": source_hash,
        "ticker_count": len(rows),
        "task_count": task_count,
        "blocked_without_source_task_count": blocked_without_source_task,
        "output": output.as_posix(),
        "bytes": output.stat().st_size,
    }
    print(json.dumps(report, indent=2))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core", type=Path, default=DEFAULT_CORE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    export(args.core, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
