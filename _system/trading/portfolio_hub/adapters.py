from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_spx_status(source: dict[str, Any], *, source_run_id: str | None = None) -> dict[str, Any]:
    """Allowlisted adapter for SPX schema-2 status; strategy math remains producer-owned."""
    risk = source.get("risk") or {}
    rows = []
    for index, position in enumerate(risk.get("positions") or []):
        strategy_id = str(position.get("position_id") or position.get("tranche_id") or f"legacy-{index}")
        rows.append({
            "row_id": f"spx:{strategy_id}",
            "account_alias": None,
            "conid": position.get("conid"),
            "model_code": position.get("model_code"),
            "symbol": position.get("local_symbol") or position.get("symbol") or "SPXW",
            "underlying": "SPX",
            "strategy": "spx_0dte",
            "bucket": None,
            "product_class": "defined_risk_options",
            "reconciliation_role": "broker_reconciling" if position.get("conid") else "detail_only",
            "exposure_basis": "broker_quantity" if position.get("conid") else "attribution",
            "metrics": {
                key: position.get(key) for key in (
                    "contracts", "quantity", "put_short", "put_long", "call_short", "call_long",
                    "credit", "stopped", "marked_pnl", "max_loss_no_stop", "planned_stop_loss",
                    "native_stop_loss", "defined_risk_margin", "return_on_margin_pct",
                    "delta", "gamma", "vega", "theta",
                ) if key in position
            },
            "lineage": {"producer_schema": source.get("schema"), "mark_quality": position.get("mark_quality")},
        })
    return {
        "schema_version": "strategy_snapshot.v1",
        "producer": "spx_0dte",
        "source_run_id": source_run_id or f"spx-{uuid.uuid4()}",
        "as_of": source.get("generated_at") or source.get("as_of") or _now(),
        "complete": bool(
            source.get("schema") == 2
            and ("pid_alive" in source or "process" in source)
            and isinstance(source.get("risk") or {}, dict)
        ),
        "supported_scopes": ["account", "strategy"],
        "rows": rows,
        "summary": {
            "process": source.get("pid_alive", source.get("process")),
            "halted": source.get("entries_halted", source.get("halted")),
            "flattened": source.get("flattened"),
            "open_count": source.get("open_count"), "marked_pnl": source.get("marked_pnl"),
            "closed_pnl": source.get("closed_pnl"), "total_pnl": source.get("total_pnl"),
            "contracts_traded": source.get("contracts_traded"),
            "open_contracts": source.get("open_contracts"),
            "execution_quality": source.get("execution_quality"),
            "risk_history": source.get("risk_history") or [],
            "heartbeat_ts": source.get("heartbeat_ts"),
        },
    }


def normalize_ls_snapshot(source: dict[str, Any], *, source_run_id: str | None = None) -> dict[str, Any]:
    """Minimal allowlisted export from current LS metrics; no raw paths or legacy aliases pass through."""
    rows = []
    bucket_payload = source.get("buckets") or {}
    for bucket_name, bucket in bucket_payload.items():
        bucket_id = str(bucket_name).lower().replace("bucket_", "b")
        if bucket_id not in {"b1", "b2", "b3", "b4", "b5", "unbucketed"}:
            continue
        for index, row in enumerate(bucket.get("exposure_rows") or []):
            role = "overlay" if bucket_id in {"b3", "b5"} else "additive"
            basis = "delta_overlay" if role == "overlay" else "attribution"
            if bucket_id == "b4" and row.get("view") == "pair_detail":
                role, basis = "detail_only", "pair_detail"
            rows.append({
                "row_id": f"ls:{bucket_id}:{row.get('position_id') or row.get('symbol') or index}",
                "account_alias": row.get("account_alias"), "conid": row.get("conid"), "model_code": row.get("model_code"),
                "symbol": row.get("symbol") or row.get("underlying"), "underlying": row.get("underlying"), "strategy": "leveraged_etf",
                "bucket": bucket_id.upper(), "product_class": row.get("product_class"),
                "reconciliation_role": role, "exposure_basis": basis,
                "metrics": {
                    **{key: row.get(key) for key in (
                        "quantity", "market_value", "gross_exposure", "net_exposure", "beta_exposure",
                        "delta_exposure", "borrow_rate", "net_notional_usd", "gross_notional_usd", "n_legs",
                    ) if key in row},
                    **({"symbols": row.get("symbols")} if row.get("symbols") else {}),
                    **({"margin_value": row.get("margin_requirement"), "margin_value_kind": "model_estimate"} if row.get("margin_requirement") is not None else {}),
                },
                "lineage": {"model_version": row.get("model_version"), "quality": row.get("quality")},
            })
        for index, row in enumerate(bucket.get("pnl_rows") or []):
            rows.append({
                "row_id": f"ls:pnl:{bucket_id}:{row.get('position_id') or row.get('symbol') or index}",
                "account_alias": row.get("account_alias"), "conid": row.get("conid"), "model_code": row.get("model_code"),
                "symbol": row.get("symbol") or row.get("underlying"), "underlying": row.get("underlying"), "strategy": "leveraged_etf",
                "bucket": bucket_id.upper(), "product_class": row.get("product_class"),
                "reconciliation_role": "additive", "exposure_basis": "attribution",
                "metrics": {
                    "session_pnl": row.get("total_pnl", row.get("session_total_pnl")),
                    "total_pnl": row.get("total_pnl"),
                    "realized_pnl": row.get("realized_pnl"),
                    "unrealized_pnl": row.get("unrealized_pnl"),
                    "borrow_fees": row.get("borrow_fees"),
                    "short_credit_interest": row.get("short_credit_interest"),
                    "cumulative_pnl": row.get("cumulative_pnl"),
                    "restatement": row.get("restatement_total"),
                },
                "lineage": {"session_date": row.get("session_date"), "denominator_kind": row.get("denominator_kind"), "denominator_value": row.get("denominator_value"), "currency": row.get("currency")},
            })
    return {
        "schema_version": "strategy_snapshot.v1", "producer": "ls_risk",
        "source_run_id": source_run_id or f"ls-{uuid.uuid4()}",
        "as_of": source.get("generated_at_utc") or source.get("generated_at") or source.get("as_of") or _now(),
        "complete": bool(source.get("book") and source.get("buckets")),
        "supported_scopes": ["account", "strategy", "bucket"], "rows": rows,
        "summary": {
            "book": source.get("book") or {},
            "pnl": source.get("pnl_panel") or {},
            "hedged_pnl": source.get("hedged_pnl_panel") or {},
            "movers": source.get("movers_panel") or {},
            "bucket_movers": source.get("bucket_movers_panel") or {},
            "component_attribution": source.get("component_attribution_panel") or {},
            "dividends": source.get("dividend_panel") or {},
            "factors": source.get("factor_panel") or {},
            "concentration": source.get("concentration_panel") or {},
            "slide_risk": source.get("slide_risk_panel") or {},
            "borrow_shocks": source.get("borrow_shock_panel") or {},
            "sleeves": source.get("bucket_sleeve_panel") or {},
            "drawdown": source.get("drawdown_panel") or {},
            "data_quality": source.get("data_quality") or {},
        },
    }


def normalize_ls_bucket5_product(source: dict[str, Any], *, source_run_id: str | None = None) -> dict[str, Any]:
    """Research-only B5 product export; deliberately cannot reconcile to the live B5 sleeve."""
    rows = []
    for index, row in enumerate(source.get("rows") or source.get("daily") or []):
        rows.append({
            "row_id": f"ls:b5-product:{row.get('id') or row.get('date') or index}",
            "account_alias": None, "conid": None, "model_code": None,
            "symbol": row.get("symbol"), "underlying": row.get("underlying"),
            "strategy": "bucket5_product_research", "bucket": "B5_PRODUCT",
            "product_class": row.get("product_class") or "vol_etp_insured_research",
            "reconciliation_role": "research_only", "exposure_basis": "research",
            "metrics": {key: value for key, value in row.items() if key not in {"source_path", "absolute_path"}},
            "lineage": {"producer_schema": source.get("schema_version") or source.get("schema")},
        })
    return {
        "schema_version": "strategy_snapshot.v1", "producer": "ls_bucket5_product",
        "source_run_id": source_run_id or f"ls-b5-product-{uuid.uuid4()}",
        "as_of": source.get("generated_at") or source.get("as_of") or _now(),
        "complete": bool(source.get("schema_version") or source.get("schema")),
        "supported_scopes": ["strategy"], "rows": rows,
    }


def normalize_ls_bucket5_live(source: dict[str, Any], *, source_run_id: str | None = None) -> dict[str, Any]:
    result = normalize_ls_snapshot(source, source_run_id=source_run_id or f"ls-b5-live-{uuid.uuid4()}")
    result["producer"] = "ls_bucket5_live"
    result["rows"] = [row for row in result["rows"] if row.get("bucket") == "B5"]
    result["supported_scopes"] = ["account", "strategy", "bucket"]
    return result
