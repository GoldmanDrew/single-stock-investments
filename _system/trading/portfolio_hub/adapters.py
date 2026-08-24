from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _display_symbol(row: dict[str, Any]) -> Any:
    """What the row actually holds, not merely what it tracks.

    ls-algo's aggregate exposure rows carry `symbols` -- the instruments held --
    and `underlying`, what they track, but no singular `symbol`. Falling straight
    through to `underlying` renamed a long UVIX leg "SVIX" on the B5 tab, because
    both legs of the volatility pair share the SVIX underlying, so the page
    showed the same ticker twice for two different instruments. `symbols` is a
    bare string on a single-leg row and a list on a multi-leg one.
    """
    if row.get("symbol"):
        return row["symbol"]
    symbols = row.get("symbols")
    if isinstance(symbols, str) and symbols:
        return symbols
    if isinstance(symbols, (list, tuple)) and symbols:
        return " / ".join(str(symbol) for symbol in symbols)
    return row.get("underlying")


def _bucket5_hedge_rows(source: dict[str, Any]) -> list[dict[str, Any]]:
    """The B5 index-put ladder, which does not appear under `buckets` at all.

    ls-algo publishes the volatility-ETP legs in `buckets.bucket_5` but keeps the
    XSP put ladder that insures them in a separate top-level `bucket5_live`
    panel. An adapter that walks only `buckets` therefore forwarded the risk and
    dropped the hedge, and the B5 tab rendered what looked like a naked short-vol
    pair. These lots carry a conId, so they reconcile against the broker like any
    other position.

    Deliberately no notional: a long put's market value and the index notional it
    covers differ by orders of magnitude, and signing a delta-adjusted notional
    needs a delta this producer does not publish. Emitting either one under a
    column labelled "notional" would repeat the mislabelling this change fixes,
    so the hedge publishes value and cost and leaves notional absent.
    """
    live = source.get("bucket5_live") or {}
    puts = live.get("puts") or {}
    underlying = ((live.get("contract_preflight") or {}).get("underlying") or {}).get("symbol") or "XSP"
    coverage = {
        str(row.get("rung_id")): row
        for row in (live.get("coverage") or [])
        if row.get("rung_id")
    }
    rows = []
    for index, lot in enumerate(puts.get("lots") or []):
        conid = lot.get("conId", lot.get("conid"))
        try:
            conid = int(conid)
        except (TypeError, ValueError):
            conid = None
        # IB local symbols pad the root out to six characters ("XSP   270129P...").
        local_symbol = " ".join(str(lot.get("local_symbol") or "").split())
        rung = coverage.get(str(lot.get("rung_id"))) or {}
        cost, mark = lot.get("cost_basis_usd"), lot.get("mark_value_usd")
        unrealized = None
        if isinstance(cost, (int, float)) and isinstance(mark, (int, float)):
            unrealized = mark - cost
        rows.append({
            "row_id": f"ls:b5:put:{lot.get('rung_id') or conid or index}",
            "row_kind": "position",
            "account_alias": None, "conid": conid, "model_code": None,
            "symbol": local_symbol or f"{underlying} put",
            "underlying": underlying,
            "strategy": "leveraged_etf",
            "bucket": "B5",
            "product_class": "index_put_hedge",
            "reconciliation_role": "broker_reconciling" if conid else "detail_only",
            "exposure_basis": "broker_quantity" if conid else "attribution",
            "position_units": "contracts",
            "metrics": {
                "contracts": lot.get("remaining_contracts", lot.get("entry_contracts")),
                "market_value": mark, "cost_basis": cost,
                "unrealized_pnl": unrealized, "marked_pnl": unrealized,
                "mark_multiple": lot.get("mark_multiple"),
                "dte_business_days": lot.get("dte_business_days"),
                "strike": lot.get("strike"), "expiry": lot.get("expiry"),
                "right": lot.get("right"), "rung_id": lot.get("rung_id"),
                "roll_due": lot.get("roll_due"),
                **({"coverage_ratio": rung.get("coverage_ratio")} if rung.get("coverage_ratio") is not None else {}),
                **({"target_contracts": rung.get("target_contracts")} if rung.get("target_contracts") is not None else {}),
            },
            "lineage": {
                "producer_schema": live.get("schema"),
                "strategy_version": live.get("strategy_version"),
                "quality": live.get("health"),
                "position_scope": ((puts.get("accounting") or {}).get("position_scope")),
                "account_scope": ((puts.get("accounting") or {}).get("account_scope")),
                "value_kind": "producer_mark",
            },
        })
    return rows


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
                "row_kind": "exposure",
                "account_alias": row.get("account_alias"), "conid": row.get("conid"), "model_code": row.get("model_code"),
                "symbol": _display_symbol(row), "underlying": row.get("underlying"), "strategy": "leveraged_etf",
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
                # Attribution only. It carries no quantity or value, so the
                # positions table must not render it as if it were a holding.
                "row_kind": "pnl",
                "account_alias": row.get("account_alias"), "conid": row.get("conid"), "model_code": row.get("model_code"),
                "symbol": _display_symbol(row), "underlying": row.get("underlying"), "strategy": "leveraged_etf",
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
    # The B5 hedge lives outside `buckets` entirely; see _bucket5_hedge_rows.
    rows.extend(_bucket5_hedge_rows(source))
    return {
        "schema_version": "strategy_snapshot.v1", "producer": "ls_risk",
        "source_run_id": source_run_id or f"ls-{uuid.uuid4()}",
        "as_of": source.get("generated_at_utc") or source.get("generated_at") or source.get("as_of") or _now(),
        "complete": bool(source.get("book") and source.get("buckets")),
        "supported_scopes": ["account", "strategy", "bucket"], "rows": rows,
        # Allowlisted, and it has to stay that way. The docstring above promises a
        # "minimal allowlisted export", but this block used to forward thirteen
        # analytics panels wholesale, which made the payload 2.38 MB. D1 caps a row
        # around 1 MB, so storeStrategySnapshot's INSERT would have failed on every
        # publish -- and the read path ships payload_json straight to the browser,
        # so even a larger cap would have meant a multi-megabyte page load.
        #
        # These seven are exactly what portfolio-viz.js renders for ls_risk; the
        # dropped panels (bucket_movers 830 KB, dividends 246 KB, pnl 206 KB,
        # hedged_pnl 203 KB, component_attribution 114 KB, drawdown, movers) had no
        # reader. LS P&L reaches the page through rows[].metrics, not summary.pnl.
        # Nothing is lost: ingest archives the FULL payload to R2 first, so the
        # dropped detail stays retrievable at portfolio/strategy/<producer>/<date>/.
        # Adding a key here means checking the size again.
        "summary": {
            "book": source.get("book") or {},
            "factors": source.get("factor_panel") or {},
            "concentration": source.get("concentration_panel") or {},
            "slide_risk": source.get("slide_risk_panel") or {},
            "borrow_shocks": source.get("borrow_shock_panel") or {},
            "sleeves": source.get("bucket_sleeve_panel") or {},
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
    """The live B5 sleeve: the volatility-ETP legs and the put ladder insuring them.

    This used to be `normalize_ls_snapshot` filtered to B5 and nothing more, which
    made it a byte-for-byte duplicate of the ls_risk B5 slice under a name that
    promised the live sleeve. It never read `bucket5_live`, so the coverage
    ladder, the put accounting and the kill/health state stayed on the producer
    box. The rows come from the shared walk (which now includes the hedge); what
    is added here is the sleeve state that only this panel carries.
    """
    result = normalize_ls_snapshot(source, source_run_id=source_run_id or f"ls-b5-live-{uuid.uuid4()}")
    live = source.get("bucket5_live") or {}
    result["producer"] = "ls_bucket5_live"
    result["rows"] = [row for row in result["rows"] if row.get("bucket") == "B5"]
    result["supported_scopes"] = ["account", "strategy", "bucket"]
    result["summary"] = {
        **result.get("summary", {}),
        "b5_mode": live.get("mode"), "b5_health": live.get("health"),
        "b5_kill_mode": live.get("kill_mode"),
        "b5_strategy_version": live.get("strategy_version"),
        "b5_coverage": live.get("coverage") or [],
        "b5_put_accounting": (live.get("puts") or {}).get("accounting") or {},
        "b5_open_contracts": (live.get("puts") or {}).get("open_contracts"),
        "b5_tracking": live.get("tracking") or {},
    }
    return result
