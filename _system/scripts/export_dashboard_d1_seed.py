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
DEFAULT_TECHNICAL_SUMMARY = ROOT / "dashboard" / "data" / "technical_summary.json"
DEFAULT_CRITICALITY_SUMMARY = ROOT / "dashboard" / "data" / "criticality_summary.json"
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


def stable_id(*parts: Any) -> str:
    payload = "\x1f".join(str(part or "") for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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
    technical_summary = read_json(DEFAULT_TECHNICAL_SUMMARY)
    technical_by_ticker = technical_summary.get("by_ticker") or {}
    criticality_summary = read_json(DEFAULT_CRITICALITY_SUMMARY)

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
    document_ids: set[str] = set()
    fact_count = 0
    valuation_run_count = 0
    component_count = 0
    technical_snapshot_count = 0
    market_structure_snapshot_count = 0
    price_observation_count = 0
    criticality_snapshot_count = 0
    flow_stress_snapshot_count = 0

    for symbol, snapshot in sorted((criticality_summary.get("by_symbol") or {}).items()):
        confidence = snapshot.get("confidence") or {}
        critical_time = snapshot.get("critical_time") or {}
        sql.append(upsert(
            "criticality_snapshots",
            [
                "scope", "symbol", "as_of", "horizon", "model_version", "direction",
                "criticality_score", "positive_confidence", "negative_confidence",
                "qualified_confidence", "tc_p10_days", "tc_median_days", "tc_p90_days",
                "fit_count", "qualified_count", "source", "entitlement_mode",
                "quality_state", "payload_json",
            ],
            [
                snapshot.get("scope") or "market",
                symbol,
                snapshot.get("as_of"),
                "multi",
                snapshot.get("model_version") or criticality_summary.get("model_version"),
                snapshot.get("direction") or "none",
                number(snapshot.get("score")) or 0,
                number(confidence.get("positive")) or 0,
                number(confidence.get("negative")) or 0,
                number(confidence.get("qualified")) or 0,
                number(critical_time.get("p10")),
                number(critical_time.get("median")),
                number(critical_time.get("p90")),
                int(snapshot.get("fit_count") or 0),
                int(snapshot.get("qualified_count") or 0),
                snapshot.get("source"),
                snapshot.get("entitlement_mode") or "eod",
                snapshot.get("quality_state") or snapshot.get("status") or "limited",
                compact_json(snapshot),
            ],
            ["scope", "symbol", "as_of", "horizon", "model_version"],
        ))
        criticality_snapshot_count += 1

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
        # The standalone technical artifact refreshes more frequently than core.json.
        # Prefer it so D1 receives the newest model and OHLCV fields immediately.
        technicals = technical_by_ticker.get(ticker) or row.get("technicals") or {}
        technical_as_of = technicals.get("as_of")
        latest_price = (technicals.get("latest") or {}).get("close")
        if technical_as_of and number(latest_price) is not None:
            latest_technical = technicals.get("latest") or {}
            sql.append(upsert(
                "price_observations",
                ["ticker", "observed_on", "adjusted_close", "volume", "source", "imported_at"],
                [
                    ticker,
                    technical_as_of,
                    number(latest_price),
                    number((technicals.get("latest") or {}).get("volume")),
                    technicals.get("source") or "unknown",
                    imported_at,
                ],
                ["ticker", "observed_on"],
            ))
            price_observation_count += 1
            sql.append(upsert(
                "ohlcv_observations",
                [
                    "ticker", "observed_on", "adjusted_open", "adjusted_high", "adjusted_low",
                    "adjusted_close", "volume", "source", "imported_at",
                ],
                [
                    ticker,
                    technical_as_of,
                    number(latest_technical.get("open")),
                    number(latest_technical.get("high")),
                    number(latest_technical.get("low")),
                    number(latest_price),
                    number(latest_technical.get("volume")),
                    technicals.get("source") or "unknown",
                    imported_at,
                ],
                ["ticker", "observed_on"],
            ))
        if technical_as_of and technicals.get("model_version"):
            scores = technicals.get("scores") or {}
            regime = technicals.get("regime") or {}
            sql.append(upsert(
                "technical_snapshots",
                [
                    "ticker", "as_of_date", "model_version", "benchmark", "data_quality",
                    "trend_z", "stretch_z", "relative_strength_z", "volume_surprise_z",
                    "volatility_regime_z", "drawdown_z", "trend_regime", "stretch_regime",
                    "setup_regime", "payload_json",
                ],
                [
                    ticker,
                    technical_as_of,
                    technicals.get("model_version"),
                    technicals.get("benchmark"),
                    technicals.get("data_quality") or "unavailable",
                    number(scores.get("trend_z")),
                    number(scores.get("stretch_z")),
                    number(scores.get("relative_strength_60d_z")),
                    number(scores.get("volume_surprise_z")),
                    number(scores.get("volatility_regime_z")),
                    number(scores.get("drawdown_z")),
                    regime.get("trend"),
                    regime.get("stretch"),
                    regime.get("setup"),
                    compact_json(technicals),
                ],
                ["ticker", "as_of_date", "model_version"],
            ))
            technical_snapshot_count += 1
            capitulation = technicals.get("capitulation") or {}
            capitulation_scores = capitulation.get("scores") or {}
            capitulation_families = capitulation.get("families") or {}
            if capitulation.get("model_version") and capitulation.get("state"):
                sql.append(upsert(
                    "capitulation_snapshots",
                    [
                        "ticker", "as_of_date", "model_version", "state",
                        "pressure_score", "panic_score", "exhaustion_score", "confidence_score",
                        "price_dislocation_score", "selling_climax_score",
                        "volatility_stress_score", "relative_path_stress_score",
                        "data_grade", "payload_json",
                    ],
                    [
                        ticker,
                        technical_as_of,
                        capitulation.get("model_version"),
                        capitulation.get("state"),
                        number(capitulation_scores.get("pressure")),
                        number(capitulation_scores.get("panic")),
                        number(capitulation_scores.get("exhaustion")),
                        number(capitulation_scores.get("confidence")),
                        number(capitulation_families.get("price_dislocation")),
                        number(capitulation_families.get("selling_climax")),
                        number(capitulation_families.get("volatility_stress")),
                        number(capitulation_families.get("relative_path_stress")),
                        technicals.get("data_grade"),
                        compact_json(capitulation),
                    ],
                    ["ticker", "as_of_date", "model_version"],
                ))
            market_structure = technicals.get("market_structure") or {}
            market_structure_as_of = market_structure.get("as_of")
            if market_structure_as_of:
                sql.append(upsert(
                    "market_structure_snapshots",
                    [
                        "ticker", "as_of_date", "float_shares", "shares_outstanding",
                        "float_percent_outstanding", "short_interest_shares",
                        "short_percent_float", "short_change_pct", "days_to_cover",
                        "source", "payload_json",
                    ],
                    [
                        ticker,
                        market_structure_as_of,
                        number(market_structure.get("float_shares")),
                        number(market_structure.get("shares_outstanding")),
                        number(market_structure.get("float_percent_outstanding")),
                        number(market_structure.get("short_interest_shares")),
                        number(market_structure.get("short_percent_float")),
                        number(market_structure.get("short_change_pct")),
                        number(market_structure.get("days_to_cover")),
                        market_structure.get("source"),
                        compact_json(market_structure),
                    ],
                    ["ticker", "as_of_date"],
                ))
                market_structure_snapshot_count += 1

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

        shard_ref = str(row.get("detail_shard") or "")
        shard_path = ROOT / "dashboard" / shard_ref
        if not shard_path.is_file():
            shard_path = ROOT / "dashboard" / "data" / "tickers" / f"{ticker}.json"
        detail = read_json(shard_path)
        workbench = detail.get("valuation_workbench") or {}
        wb_valuation = workbench.get("valuation") or {}
        valuation_body = wb_valuation.get("valuation") or {}
        wb_decision = workbench.get("decision") or decision
        wb_method = workbench.get("method_fit") or {}
        proof_summary = wb_valuation.get("calculation_proof_summary") or {}
        wb_components = wb_valuation.get("components") or []

        if workbench and wb_components:
            model_hash = str(
                wb_decision.get("model_hash")
                or (wb_valuation.get("change_control") or {}).get("model_hash")
                or source_hash
            )
            valuation_run_id = stable_id(ticker, model_hash, generated_at)
            primary_methods = wb_method.get("primary_methods") or []
            primary_method = str(primary_methods[0] if primary_methods else route.get("primary_methods", ["unknown"])[0])
            values = valuation_body.get("value_per_share") or wb_decision.get("value_per_share") or {}
            output_unit = next(
                (
                    (component.get("calculation_proof") or {}).get("output_unit")
                    for component in wb_components
                    if isinstance(component.get("calculation_proof"), dict)
                    and (component.get("calculation_proof") or {}).get("output_unit")
                ),
                "USD per share",
            )
            sql.append(upsert(
                "valuation_runs",
                [
                    "valuation_run_id", "ticker", "method_id", "method_version",
                    "power_zone_profile", "as_of_date", "status", "input_hash", "proof_hash",
                    "value_low", "value_base", "value_high", "output_unit", "run_id", "payload_json",
                ],
                [
                    valuation_run_id, ticker, primary_method, "1.0",
                    wb_method.get("profile_id") or route.get("profile_id"),
                    workbench.get("as_of") or generated_at[:10],
                    wb_decision.get("status") or "evidence_blocked",
                    model_hash,
                    proof_summary.get("aggregate_proof_hash"),
                    number(values.get("low")), number(values.get("base")), number(values.get("high")),
                    output_unit, run_id,
                    compact_json({
                        "decision": wb_decision,
                        "method_fit": {
                            "profile_id": wb_method.get("profile_id"),
                            "primary_methods": primary_methods,
                            "routing_reasons": wb_method.get("routing_reasons") or [],
                        },
                        "calculation_proof_summary": proof_summary,
                    }),
                ],
                ["valuation_run_id"],
            ))
            valuation_run_count += 1
            for component in wb_components:
                component_id = str(component.get("component_id") or component.get("id") or "")
                if not component_id:
                    continue
                component_values = component.get("range_per_share") or {}
                proof = component.get("calculation_proof") or {}
                sql.append(upsert(
                    "valuation_components",
                    [
                        "valuation_run_id", "component_id", "label", "category", "treatment",
                        "method_id", "method_version", "value_low", "value_base", "value_high",
                        "overlap_key", "proof_hash", "payload_json",
                    ],
                    [
                        valuation_run_id, component_id, component.get("label"), component.get("category"),
                        component.get("treatment") or "additive", component.get("method"),
                        component.get("method_version") or proof.get("method_version"),
                        number(component_values.get("low")), number(component_values.get("base")),
                        number(component_values.get("high")), component.get("overlap_key"),
                        proof.get("proof_hash"),
                        compact_json({
                            key: component.get(key)
                            for key in (
                                "evidence_tier", "evidence", "falsifier", "valuation_status",
                                "ownership_claim", "ownership_percentage", "assumption_type",
                            )
                            if component.get(key) is not None
                        }),
                    ],
                    ["valuation_run_id", "component_id"],
                ))
                component_count += 1

                traces = proof.get("traces") or {}
                base_trace = {
                    str(trace.get("id") or ""): trace
                    for trace in (traces.get("base") or [])
                    if isinstance(trace, dict)
                }
                for lineage in proof.get("source_lineage") or []:
                    if not isinstance(lineage, dict) or not lineage.get("ref"):
                        continue
                    node_id = str(lineage.get("node_id") or "")
                    source_id = str(lineage.get("source_id") or stable_id(
                        ticker, lineage.get("ref"), lineage.get("locator"), lineage.get("as_of")
                    ))
                    document_id = stable_id(ticker, source_id)
                    if document_id not in document_ids:
                        sql.append(upsert(
                            "source_documents",
                            [
                                "document_id", "ticker", "source_type", "source_ref", "source_locator",
                                "as_of_date", "content_sha256", "metadata_json",
                            ],
                            [
                                document_id, ticker, "valuation_primary_evidence", lineage.get("ref"),
                                lineage.get("locator"), lineage.get("as_of"), source_id,
                                compact_json({"component_id": component_id, "source_id": source_id}),
                            ],
                            ["document_id"],
                        ))
                        document_ids.add(document_id)
                    trace = base_trace.get(node_id) or {}
                    fact_id = stable_id(ticker, component_id, node_id, source_id, generated_at)
                    sql.append(upsert(
                        "facts",
                        [
                            "fact_id", "ticker", "field_id", "value_number", "value_text", "unit",
                            "currency", "as_of_date", "confidence", "locked", "source_document_id",
                            "source_locator", "derivation_json", "method_version", "run_id",
                        ],
                        [
                            fact_id, ticker, node_id or "source_lineage",
                            number(trace.get("value")),
                            None if number(trace.get("value")) is not None else trace.get("value"),
                            trace.get("unit"), None, lineage.get("as_of"), "source_locked", True,
                            document_id, lineage.get("locator"),
                            compact_json({
                                "component_id": component_id,
                                "kind": trace.get("kind"),
                                "operation": trace.get("operation"),
                                "dependencies": trace.get("dependencies") or [],
                            }),
                            component.get("method_version") or proof.get("method_version") or "1.0",
                            run_id,
                        ],
                        ["fact_id"],
                    ))
                    fact_count += 1

    market_context = technical_summary.get("market_context") or {}
    internal_market = market_context.get("internal") or {}
    cnn_reference = market_context.get("cnn_reference") or {}
    if internal_market.get("as_of"):
        sql.append(upsert(
            "market_context_snapshots",
            [
                "context_key", "as_of_date", "model_version", "state", "panic_score",
                "source", "source_url", "payload_json",
            ],
            [
                "US_MARKET_FEAR",
                internal_market.get("as_of"),
                technical_summary.get("model_version") or "technical-fear-v2",
                internal_market.get("state"),
                number((internal_market.get("scores") or {}).get("panic")),
                internal_market.get("source"),
                cnn_reference.get("url"),
                compact_json(market_context),
            ],
            ["context_key", "as_of_date", "model_version"],
        ))
        internal_scores = internal_market.get("scores") or {}
        sql.append(upsert(
            "flow_stress_snapshots",
            [
                "scope", "symbol", "as_of", "model_version", "state",
                "pressure_score", "panic_score", "exhaustion_score",
                "liquidity_score", "breadth_score", "vol_target_pressure_low",
                "vol_target_pressure_high", "source", "entitlement_mode",
                "quality_state", "payload_json",
            ],
            [
                "market",
                "SPY",
                internal_market.get("as_of"),
                (internal_market.get("model_version") or "capitulation-v1"),
                internal_market.get("state") or "normal",
                number(internal_scores.get("pressure")),
                number(internal_scores.get("panic")),
                number(internal_scores.get("exhaustion")),
                None,
                None,
                None,
                None,
                internal_market.get("source") or "technical_summary",
                "eod",
                "ready" if internal_scores else "limited",
                compact_json(internal_market),
            ],
            ["scope", "symbol", "as_of", "model_version"],
        ))
        flow_stress_snapshot_count += 1

    sql.extend([
        f"DELETE FROM facts WHERE run_id <> {quote(run_id)};",
        f"DELETE FROM valuation_runs WHERE run_id <> {quote(run_id)};",
        "DELETE FROM source_documents WHERE document_id NOT IN (SELECT DISTINCT source_document_id FROM facts WHERE source_document_id IS NOT NULL);",
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
        "source_document_count": len(document_ids),
        "fact_count": fact_count,
        "valuation_run_count": valuation_run_count,
        "valuation_component_count": component_count,
        "technical_snapshot_count": technical_snapshot_count,
        "market_structure_snapshot_count": market_structure_snapshot_count,
        "price_observation_count": price_observation_count,
        "criticality_snapshot_count": criticality_snapshot_count,
        "flow_stress_snapshot_count": flow_stress_snapshot_count,
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
