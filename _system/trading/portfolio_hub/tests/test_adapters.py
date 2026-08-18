from _system.trading.portfolio_hub.adapters import normalize_ls_bucket5_live, normalize_ls_bucket5_product, normalize_ls_snapshot, normalize_spx_status


def test_spx_adapter_preserves_model_lineage_without_inventing_broker_links() -> None:
    result = normalize_spx_status({"schema": 2, "generated_at": "2026-08-17T14:00:00Z", "process": {"running": True}, "risk": {"positions": [{"tranche_id": "t1", "symbol": "SPXW", "marked_pnl": 25}]}})
    assert result["complete"] is True
    assert result["rows"][0]["reconciliation_role"] == "detail_only"


def test_ls_adapter_keeps_overlay_and_factor_bases_separate() -> None:
    source = {"generated_at": "2026-08-17T14:00:00Z", "book": {"nav": 1}, "buckets": {
        "B1": {"exposure_rows": [{"symbol": "UPRO", "market_value": 100}]},
        "B3": {"exposure_rows": [{"symbol": "SPY", "delta_exposure": -50}]},
        "B4": {"exposure_rows": [{"symbol": "PAIR", "view": "pair_detail"}]},
        "B5": {"pnl_rows": [{"symbol": "UVIX", "session_total_pnl": 5, "cumulative_pnl": 20}]},
    }}
    rows = normalize_ls_snapshot(source)["rows"]
    by_id = {row["row_id"]: row for row in rows}
    assert by_id["ls:b1:UPRO"]["reconciliation_role"] == "additive"
    assert by_id["ls:b3:SPY"]["exposure_basis"] == "delta_overlay"
    assert by_id["ls:b4:PAIR"]["reconciliation_role"] == "detail_only"
    assert by_id["ls:pnl:b5:UVIX"]["metrics"]["session_pnl"] == 5


def test_b5_product_is_research_only_not_live_b5_accounting() -> None:
    result = normalize_ls_bucket5_product({"schema_version": "bucket5_product_dashboard.v1", "generated_at": "2026-08-17T14:00:00Z", "rows": [{"date": "2026-08-16", "symbol": "UVIX"}]})
    assert result["producer"] == "ls_bucket5_product"
    assert result["rows"][0]["reconciliation_role"] == "research_only"
    assert result["rows"][0]["conid"] is None


def test_b5_live_keeps_only_accounting_rows() -> None:
    source = {"book": {"nav": 1}, "buckets": {"B1": {"exposure_rows": [{"symbol": "UPRO"}]}, "B5": {"exposure_rows": [{"symbol": "UVIX", "conid": 55}]}}}
    result = normalize_ls_bucket5_live(source)
    assert result["producer"] == "ls_bucket5_live"
    assert [row["symbol"] for row in result["rows"]] == ["UVIX"]
