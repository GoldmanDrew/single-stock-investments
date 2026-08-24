from __future__ import annotations

import json

from _system.trading.portfolio_hub.adapters import (
    normalize_ls_bucket5_live,
    normalize_ls_snapshot,
    normalize_spx_status,
)


def test_ls_adapter_accepts_published_bucket_names_and_metrics():
    payload = normalize_ls_snapshot({
        "generated_at_utc": "2026-08-19T12:00:00Z",
        "book": {"nav_usd": 1_000_000, "pnl_today_usd": 1250},
        "buckets": {
            "bucket_1": {
                "exposure_rows": [{
                    "underlying": "NVDA", "symbols": ["NVDL", "NVD"],
                    "net_notional_usd": 10_000, "gross_notional_usd": 30_000, "n_legs": 2,
                }],
                "pnl_rows": [{
                    "symbol": "NVDL", "underlying": "NVDA", "realized_pnl": 100,
                    "unrealized_pnl": 50, "borrow_fees": -5, "short_credit_interest": 1,
                    "total_pnl": 146,
                }],
            },
        },
        "slide_risk_panel": {"available": True, "shocks_pct": [-10, -5, 5]},
    }, source_run_id="ls-test")

    assert payload["complete"] is True
    assert payload["as_of"] == "2026-08-19T12:00:00Z"
    assert len(payload["rows"]) == 2
    assert payload["rows"][0]["bucket"] == "B1"
    assert payload["rows"][0]["metrics"]["gross_notional_usd"] == 30_000
    assert payload["rows"][1]["metrics"]["session_pnl"] == 146
    assert payload["summary"]["slide_risk"]["available"] is True


def test_spx_adapter_accepts_live_status_v2_and_contract_positions():
    payload = normalize_spx_status({
        "schema": 2,
        "generated_at": "2026-08-19T13:00:00Z",
        "pid_alive": True,
        "entries_halted": False,
        "flattened": False,
        "open_count": 1,
        "total_pnl": 750,
        "risk": {"positions": [{
            "tranche_id": "t1", "contracts": 5, "put_short": 6400, "put_long": 6390,
            "marked_pnl": 750, "defined_risk_margin": 4_000,
        }]},
        "risk_history": [{"ts": "2026-08-19T12:59:00Z", "total_pnl": 700}],
    }, source_run_id="spx-test")

    assert payload["complete"] is True
    assert payload["summary"]["process"] is True
    assert payload["summary"]["halted"] is False
    assert payload["rows"][0]["metrics"]["contracts"] == 5
    assert payload["summary"]["risk_history"][0]["total_pnl"] == 700


# The B5 fixtures below are the real shapes taken from ls-algo's latest.json on
# NY4 (run 2026-08-22): the exposure rows genuinely carry `symbols` and no
# `symbol`, and the put ladder genuinely lives outside `buckets`.
B5_LIVE_SOURCE = {
    "generated_at_utc": "2026-08-22T19:56:07Z",
    "book": {"nav_usd": 4_860_017},
    "buckets": {
        "bucket_5": {
            "exposure_rows": [
                {"underlying": "SVIX", "symbols": "UVIX", "n_legs": 1,
                 "net_notional_usd": 30_119.26, "gross_notional_usd": 30_119.26},
                {"underlying": "SVIX", "symbols": "SVIX", "n_legs": 1,
                 "net_notional_usd": -22_293.74, "gross_notional_usd": 22_293.74},
            ],
            "pnl_rows": [],
        },
    },
    "bucket5_live": {
        "schema": 3, "mode": "production", "health": "green", "kill_mode": None,
        "strategy_version": "b5-live-1",
        "contract_preflight": {"underlying": {"conId": 137851301, "symbol": "XSP"}},
        "coverage": [
            {"rung_id": "otm10", "held_contracts": 2, "target_contracts": 10, "coverage_ratio": 0.2},
            {"rung_id": "otm30", "held_contracts": 12, "target_contracts": 80, "coverage_ratio": 0.15},
        ],
        "puts": {
            "open_contracts": 20,
            "accounting": {"position_scope": "all_valid_xsp_puts_in_scoped_flex_query",
                           "account_scope": "flex_query_scope", "put_cost_basis_usd": 9456.2456},
            "lots": [
                {"conId": "907480782", "local_symbol": "XSP   270129P00694000", "rung_id": "otm10",
                 "right": "P", "strike": 694.0, "expiry": "20270129", "remaining_contracts": 2,
                 "cost_basis_usd": 2370.0, "mark_value_usd": 1087.35, "mark_multiple": 0.4588,
                 "dte_business_days": 110, "roll_due": False},
                {"conId": "907480285", "local_symbol": "XSP   270129P00540000", "rung_id": "otm30",
                 "right": "P", "strike": 540.0, "expiry": "20270129", "remaining_contracts": 12,
                 "cost_basis_usd": 3564.0, "mark_value_usd": 3090.0, "mark_multiple": 0.867,
                 "dte_business_days": 110, "roll_due": False},
            ],
        },
    },
}


def test_b5_exposure_rows_name_the_instrument_held_not_the_underlying():
    """Both B5 legs share the SVIX underlying; only one of them is SVIX."""
    rows = normalize_ls_snapshot(B5_LIVE_SOURCE, source_run_id="ls-b5")["rows"]
    exposure = [row for row in rows if row["metrics"].get("n_legs") is not None]
    assert [row["symbol"] for row in exposure] == ["UVIX", "SVIX"]
    assert {row["underlying"] for row in exposure} == {"SVIX"}


def test_ls_snapshot_carries_the_b5_put_ladder_that_lives_outside_buckets():
    rows = normalize_ls_snapshot(B5_LIVE_SOURCE, source_run_id="ls-b5")["rows"]
    hedge = [row for row in rows if row.get("product_class") == "index_put_hedge"]
    assert len(hedge) == 2, "the XSP ladder must survive the walk over `buckets`"
    assert all(row["bucket"] == "B5" for row in hedge)
    assert [row["conid"] for row in hedge] == [907480782, 907480285]
    # Padding in the IB local symbol is collapsed, not preserved.
    assert hedge[0]["symbol"] == "XSP 270129P00694000"
    assert hedge[0]["metrics"]["contracts"] == 2
    assert hedge[0]["metrics"]["coverage_ratio"] == 0.2
    # A conId means the row reconciles against the broker.
    assert hedge[0]["reconciliation_role"] == "broker_reconciling"


def test_b5_hedge_publishes_value_and_never_invents_a_notional():
    """Market value and index notional differ by orders of magnitude for a put."""
    rows = normalize_ls_snapshot(B5_LIVE_SOURCE, source_run_id="ls-b5")["rows"]
    hedge = next(row for row in rows if row.get("product_class") == "index_put_hedge")
    assert hedge["metrics"]["market_value"] == 1087.35
    assert hedge["metrics"]["cost_basis"] == 2370.0
    assert round(hedge["metrics"]["unrealized_pnl"], 2) == -1282.65
    assert "net_notional_usd" not in hedge["metrics"]
    assert "gross_notional_usd" not in hedge["metrics"]
    assert hedge["position_units"] == "contracts"


def test_bucket5_live_producer_reads_the_live_panel_not_just_the_bucket_slice():
    payload = normalize_ls_bucket5_live(B5_LIVE_SOURCE, source_run_id="ls-b5-live")
    assert payload["producer"] == "ls_bucket5_live"
    assert all(row["bucket"] == "B5" for row in payload["rows"])
    assert any(row.get("product_class") == "index_put_hedge" for row in payload["rows"])
    # The sleeve state that only `bucket5_live` carries.
    assert payload["summary"]["b5_open_contracts"] == 20
    assert payload["summary"]["b5_health"] == "green"
    assert len(payload["summary"]["b5_coverage"]) == 2
    assert payload["summary"]["b5_put_accounting"]["account_scope"] == "flex_query_scope"


def test_a_snapshot_without_the_b5_live_panel_still_normalizes():
    payload = normalize_ls_snapshot(
        {"generated_at_utc": "2026-08-22T19:56:07Z", "book": {"nav_usd": 1},
         "buckets": {"bucket_5": {"exposure_rows": [], "pnl_rows": []}}},
        source_run_id="ls-empty",
    )
    assert payload["rows"] == []


def test_rows_declare_their_kind_so_pnl_never_renders_as_a_holding():
    """The positions table filters on kind now, not on 'has a notional'."""
    source = json.loads(json.dumps(B5_LIVE_SOURCE))
    source["buckets"]["bucket_5"]["pnl_rows"] = [
        {"symbol": "SVIX", "underlying": "SVIX", "total_pnl": 146, "realized_pnl": 100},
    ]
    rows = normalize_ls_snapshot(source, source_run_id="ls-kind")["rows"]
    kinds = {}
    for row in rows:
        kinds.setdefault(row["row_kind"], []).append(row)
    assert set(kinds) == {"exposure", "pnl", "position"}
    assert len(kinds["pnl"]) == 1 and kinds["pnl"][0]["metrics"]["session_pnl"] == 146
    # Every row the positions table will render carries a quantity of some form.
    for row in kinds["exposure"] + kinds["position"]:
        metrics = row["metrics"]
        assert any(metrics.get(key) is not None for key in ("contracts", "quantity", "n_legs"))
