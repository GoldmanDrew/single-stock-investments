import json

from _system.trading.portfolio_hub.dual_publish import (
    MAX_D1_PAYLOAD_BYTES,
    assert_producer_semantics,
    build_dual_publish_bundle,
    normalize_producer,
)
import pytest


def spx_source():
    return {
        "schema": 2, "generated_at": "2026-08-17T14:00:00Z", "process": {"running": True},
        "risk": {"positions": [{"tranche_id": "t1", "symbol": "SPXW", "conid": 9001, "marked_pnl": 25}]},
    }


def ls_source():
    return {
        "generated_at": "2026-08-17T14:00:00Z", "book": {"nav": 1},
        "buckets": {
            "B1": {"exposure_rows": [{"symbol": "UPRO", "conid": 8001, "market_value": 100}]},
            "B5": {"exposure_rows": [{"symbol": "UVIX", "conid": 8005, "market_value": 20}]},
        },
    }


def test_dual_publish_keeps_spx_and_letf_semantics_apart() -> None:
    snapshots = build_dual_publish_bundle(spx=spx_source(), ls_risk=ls_source(), ls_bucket5_live=ls_source(), ls_bucket5_product={"schema_version": "bucket5_product_dashboard.v1", "generated_at": "2026-08-17T14:00:00Z", "rows": [{"date": "2026-08-16", "symbol": "UVIX"}]})
    by_producer = {row["producer"]: row for row in snapshots}
    assert set(by_producer) == {"spx_0dte", "ls_risk", "ls_bucket5_live", "ls_bucket5_product"}
    assert by_producer["ls_bucket5_live"]["rows"][0]["bucket"] == "B5"
    assert by_producer["ls_bucket5_product"]["rows"][0]["reconciliation_role"] == "research_only"
    assert by_producer["ls_bucket5_product"]["rows"][0]["conid"] is None
    for payload in snapshots:
        assert_producer_semantics(payload)


def test_dual_publish_rejects_shared_broker_conids() -> None:
    overlapping = ls_source()
    overlapping["buckets"]["B1"]["exposure_rows"][0]["conid"] = 9001
    with pytest.raises(ValueError, match="share broker conId"):
        build_dual_publish_bundle(spx=spx_source(), ls_risk=overlapping)


def test_b5_product_cannot_be_normalized_into_a_broker_link() -> None:
    payload = normalize_producer("ls_bucket5_product", {"schema_version": "x", "rows": [{"symbol": "UVIX", "conid": 1}]})
    with pytest.raises(ValueError, match="cannot broker-reconcile"):
        payload["rows"][0]["reconciliation_role"] = "broker_reconciling"
        assert_producer_semantics(payload)


def test_ls_summary_is_allowlisted_and_fits_the_d1_row_budget() -> None:
    # The summary used to forward every analytics panel wholesale, which put the
    # real payload at 2.38 MB against a ~1 MB D1 row. Feed it a panel that is not
    # on the allowlist and a huge one that is not either; neither may survive.
    source = {
        "generated_at": "2026-08-22T20:00:00Z",
        "book": {"gross": "1"},
        "buckets": {"bucket_1": {"exposure_rows": [
            {"symbol": "SPXL", "conid": 11, "strategy": "leveraged_etf"},
        ]}},
        "factor_panel": {"kept": True},
        "bucket_movers_panel": {"dropped": "x" * 50_000},
        "dividend_panel": {"dropped": "y" * 50_000},
        "pnl_panel": {"dropped": "z" * 50_000},
    }
    payload = normalize_producer("ls_risk", source)
    summary = payload["summary"]
    assert summary["factors"] == {"kept": True}
    for gone in ("bucket_movers", "dividends", "pnl", "hedged_pnl", "component_attribution", "drawdown", "movers"):
        assert gone not in summary, f"{gone} is not rendered by the dashboard and must not ship to D1"
    assert len(json.dumps(payload, separators=(",", ":")).encode()) < MAX_D1_PAYLOAD_BYTES


def test_an_oversized_snapshot_is_refused_before_it_reaches_d1() -> None:
    # R2 is written before the D1 insert, so an oversized payload half-lands and
    # reads as a partial publish. Fail in the adapter, where the message can say
    # which producer and how big.
    payload = normalize_producer("ls_risk", {
        "book": {"g": "1"}, "buckets": {"bucket_1": {"exposure_rows": []}},
    })
    payload["summary"]["factors"] = {"bloat": "x" * (MAX_D1_PAYLOAD_BYTES + 1)}
    with pytest.raises(ValueError, match="D1 row budget"):
        assert_producer_semantics(payload)


def test_a_bom_prefixed_producer_file_still_loads(tmp_path) -> None:
    # spx-0dte writes some live artifacts with a UTF-8 BOM; plain utf-8 raises.
    path = tmp_path / "live_status.json"
    path.write_text(json.dumps({"schema": 2, "risk": {"positions": []}}), encoding="utf-8-sig")
    payload = normalize_producer("spx_0dte", path)
    assert payload["producer"] == "spx_0dte"
