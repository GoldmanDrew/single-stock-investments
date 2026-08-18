from __future__ import annotations

from decimal import Decimal

import pytest

from _system.trading.portfolio_hub.ledger import PortfolioLedger


def snapshot(*, complete: bool = True) -> dict:
    return {
        "schema_version": "account_snapshot.v1",
        "source_run_id": "run-1",
        "account_alias": "paper-primary",
        "gateway_session_id": "session-1",
        "as_of": "2026-08-17T14:00:00Z",
        "complete": complete,
        "base_currency": "USD",
        "account_values": [
            {"tag": "NetLiquidation", "value": "1000000.00", "currency": "USD", "segment": None, "model_code": None, "source": "ibkr_account_summary", "as_of": "2026-08-17T14:00:00Z"}
        ],
        "positions": [
            {"account_alias": "paper-primary", "conid": 101, "model_code": "", "symbol": "TEST", "local_symbol": "TEST", "description": "Test Corp", "sec_type": "STK", "currency": "USD", "exchange": "SMART", "expiry": None, "strike": None, "right": None, "multiplier": None, "quantity": "100", "average_cost": "10", "mark": "12", "market_value": "1200", "unrealized_pnl": "200", "realized_pnl": "0", "daily_pnl": "15", "source": "ibkr_live", "as_of": "2026-08-17T14:00:00Z", "quality": "live"}
        ],
        "open_orders": [{"client_id": 0, "order_id": 700, "perm_id": 900, "conid": 101, "symbol": "TEST", "action": "SELL", "order_type": "LMT", "total_quantity": "5", "limit_price": "13", "tif": "DAY", "status": "Submitted", "order_ref": "", "ownership": "foreign", "parent_id": 0, "oca_group": None, "as_of": "2026-08-17T14:00:00Z"}],
    }


@pytest.fixture()
def ledger(tmp_path):
    result = PortfolioLedger(tmp_path / "portfolio.db")
    result.migrate()
    yield result
    result.close()


def test_snapshot_allocation_and_read_model_reconcile(ledger: PortfolioLedger) -> None:
    snapshot_id = ledger.ingest_account_snapshot(snapshot())
    ledger.add_allocation(account_alias="paper-primary", conid=101, owner="drew", strategy="single_stock", quantity="60", effective_at="2026-08-17T13:00:00Z")
    ledger.add_allocation(account_alias="paper-primary", conid=101, owner="michael", strategy="single_stock", quantity="40", effective_at="2026-08-17T13:00:00Z")
    ledger.add_cash_event(account_alias="paper-primary", owner="drew", strategy="single_stock", currency="USD", amount="5000", event_type="opening_capital", effective_at="2026-08-17T13:00:00Z", source="bootstrap", source_event_id="cash-1")

    assert ledger.reconcile_allocations(snapshot_id) == []
    drew = ledger.latest_portfolio("paper-primary", "drew")
    assert drew["status"] == "complete"
    assert drew["positions"][0]["quantity_decimal"] == "60"
    assert len(ledger.pending_outbox()) == 5
    projection = ledger.allocation_projection("paper-primary")
    assert projection["source_run_id"] == "run-1"
    assert {row["owner"] for row in projection["allocations"]} == {"drew", "michael"}
    assert projection["cash_events"][0]["amount_decimal"] == "5000"
    assert ledger.latest_account_snapshot_payload("paper-primary")["open_orders"][0]["ownership"] == "foreign"


def test_residual_is_visible_and_incomplete_snapshot_never_means_flat(ledger: PortfolioLedger) -> None:
    snapshot_id = ledger.ingest_account_snapshot(snapshot())
    ledger.add_allocation(account_alias="paper-primary", conid=101, owner="drew", strategy="single_stock", quantity="75", effective_at="2026-08-17T13:00:00Z")
    breaks = ledger.reconcile_allocations(snapshot_id, Decimal("0"))
    assert breaks[0]["details"]["residual"] == "25"

    bad = snapshot(complete=False)
    bad["source_run_id"] = "run-incomplete"
    incomplete_id = ledger.ingest_account_snapshot(bad)
    with pytest.raises(ValueError, match="incomplete"):
        ledger.reconcile_allocations(incomplete_id)


def test_source_run_is_business_idempotent(ledger: PortfolioLedger) -> None:
    first = ledger.ingest_account_snapshot(snapshot())
    assert ledger.ingest_account_snapshot(snapshot()) == first
    changed = snapshot()
    changed["positions"][0]["quantity"] = "99"
    with pytest.raises(ValueError, match="different content"):
        ledger.ingest_account_snapshot(changed)


def test_broker_event_idempotency(ledger: PortfolioLedger) -> None:
    assert ledger.record_broker_event("paper:exec:one", "execution", "paper-primary", {"execId": "one"})
    assert not ledger.record_broker_event("paper:exec:one", "execution", "paper-primary", {"execId": "one"})


def test_online_backup_is_restorable(ledger: PortfolioLedger, tmp_path) -> None:
    ledger.ingest_account_snapshot(snapshot())
    backup = ledger.backup(tmp_path / "backup" / "portfolio.db")
    restored = PortfolioLedger(backup)
    try:
        assert restored.latest_portfolio("paper-primary")["status"] == "complete"
    finally:
        restored.close()
