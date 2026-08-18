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
                    "quantity", "marked_pnl", "max_loss_no_stop", "planned_stop_loss",
                    "native_stop_loss", "defined_risk_margin", "delta", "gamma", "vega",
                ) if key in position
            },
            "lineage": {"producer_schema": source.get("schema"), "mark_quality": position.get("mark_quality")},
        })
    return {
        "schema_version": "strategy_snapshot.v1",
        "producer": "spx_0dte",
        "source_run_id": source_run_id or f"spx-{uuid.uuid4()}",
        "as_of": source.get("generated_at") or source.get("as_of") or _now(),
        "complete": bool(source.get("schema") == 2 and source.get("process")),
        "supported_scopes": ["account", "strategy"],
        "rows": rows,
        "summary": {
            "process": source.get("process"), "halted": source.get("halted"), "flattened": source.get("flattened"),
            "open_count": source.get("open_count"), "marked_pnl": source.get("marked_pnl"),
            "closed_pnl": source.get("closed_pnl"), "total_pnl": source.get("total_pnl"),
            "execution_quality": source.get("execution_quality"),
        },
    }


def normalize_ls_snapshot(source: dict[str, Any], *, source_run_id: str | None = None) -> dict[str, Any]:
    """Minimal allowlisted export from current LS metrics; no raw paths or legacy aliases pass through."""
    rows = []
    bucket_payload = source.get("buckets") or {}
    for bucket_name, bucket in bucket_payload.items():
        bucket_id = str(bucket_name).lower()
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
                "symbol": row.get("symbol"), "underlying": row.get("underlying"), "strategy": "leveraged_etf",
                "bucket": bucket_id.upper(), "product_class": row.get("product_class"),
                "reconciliation_role": role, "exposure_basis": basis,
                "metrics": {
                    **{key: row.get(key) for key in ("quantity", "market_value", "gross_exposure", "net_exposure", "beta_exposure", "delta_exposure", "borrow_rate") if key in row},
                    **({"margin_value": row.get("margin_requirement"), "margin_value_kind": "model_estimate"} if row.get("margin_requirement") is not None else {}),
                },
                "lineage": {"model_version": row.get("model_version"), "quality": row.get("quality")},
            })
        for index, row in enumerate(bucket.get("pnl_rows") or []):
            rows.append({
                "row_id": f"ls:pnl:{bucket_id}:{row.get('position_id') or row.get('symbol') or index}",
                "account_alias": row.get("account_alias"), "conid": row.get("conid"), "model_code": row.get("model_code"),
                "symbol": row.get("symbol"), "underlying": row.get("underlying"), "strategy": "leveraged_etf",
                "bucket": bucket_id.upper(), "product_class": row.get("product_class"),
                "reconciliation_role": "additive", "exposure_basis": "attribution",
                "metrics": {"session_pnl": row.get("session_total_pnl"), "cumulative_pnl": row.get("cumulative_pnl"), "restatement": row.get("restatement_total")},
                "lineage": {"session_date": row.get("session_date"), "denominator_kind": row.get("denominator_kind"), "denominator_value": row.get("denominator_value"), "currency": row.get("currency")},
            })
    return {
        "schema_version": "strategy_snapshot.v1", "producer": "ls_risk",
        "source_run_id": source_run_id or f"ls-{uuid.uuid4()}",
        "as_of": source.get("generated_at") or source.get("as_of") or _now(),
        "complete": bool(source.get("book") and source.get("buckets")),
        "supported_scopes": ["account", "strategy", "bucket"], "rows": rows,
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
