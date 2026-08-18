from _system.trading.portfolio_hub.dual_publish import assert_producer_semantics, build_dual_publish_bundle, normalize_producer
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
