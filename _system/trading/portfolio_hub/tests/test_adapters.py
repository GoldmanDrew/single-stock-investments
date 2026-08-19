from __future__ import annotations

from _system.trading.portfolio_hub.adapters import normalize_ls_snapshot, normalize_spx_status


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
