from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone

import pytest

from _system.trading.portfolio_hub.ledger import PortfolioLedger
from _system.trading.portfolio_hub.orders import GuardedOrderService, OrderIntent


class FakeBroker:
    def __init__(self, uncertain: bool = False):
        self.uncertain = uncertain
        self.placed = []

    def quote(self, conid):
        return {"conid": conid, "bid": "9.99", "ask": "10.01", "as_of": datetime.now(timezone.utc).isoformat(), "multiplier": "1", "min_tick": "0.01", "current_position": "10"}

    def what_if(self, ticket):
        assert ticket["whatIf"] is True and ticket["transmit"] is True
        return {"initial_margin_change": "500", "maintenance_margin_change": "400", "commission": "1"}

    def place_limit(self, ticket):
        self.placed.append(ticket)
        if self.uncertain:
            raise ConnectionError("socket lost after send")
        return {"gateway_session_id": "gw-1", "client_id": 91, "order_id": 1001, "perm_id": 5001}

    def find_owned_order(self, order_ref):
        return {"order_ref": order_ref, "perm_id": 5001} if self.uncertain else None

    def cancel_owned_order(self, order_ref, client_id, order_id):
        assert order_ref.startswith("MAGIS|")
        return {"client_id": client_id, "order_id": order_id}


@pytest.fixture()
def ledger(tmp_path):
    result = PortfolioLedger(tmp_path / "orders.db")
    result.migrate()
    yield result
    result.close()


def make_intent(mode="paper"):
    return OrderIntent(account_alias="paper-primary", conid=101, contract_fingerprint="101|STK|USD|SMART", action="BUY", quantity=Decimal("10"), limit_price=Decimal("10"), owner="drew", strategy="single_stock", mode=mode)


def approve(service, created):
    previewed = service.preview(created["intent_uuid"])
    approval = service.issue_approval(previewed["intent_uuid"])
    return service.approve(previewed["intent_uuid"], approval["token"], approval["contract_fingerprint"])


def test_exact_ticket_approval_and_paper_submit(ledger):
    broker = FakeBroker()
    service = GuardedOrderService(ledger, broker, "test-secret")
    created = service.create(make_intent())
    approved = approve(service, created)
    submitted = service.submit(approved["intent_uuid"])
    assert submitted["state"] == "Acknowledged"
    assert submitted["perm_id"] == 5001
    assert submitted["order_ref"].startswith("MAGIS|single_stock|drew|")


def test_disconnect_after_send_blocks_retry_until_reconciled(ledger):
    broker = FakeBroker(uncertain=True)
    service = GuardedOrderService(ledger, broker, "test-secret")
    approved = approve(service, service.create(make_intent()))
    uncertain = service.submit(approved["intent_uuid"])
    assert uncertain["state"] == "SubmitUncertain"
    with pytest.raises(ValueError, match="must be Approved"):
        service.submit(approved["intent_uuid"])
    assert service.reconcile_uncertain(approved["intent_uuid"])["state"] == "Acknowledged"


def test_live_is_fail_closed(ledger):
    service = GuardedOrderService(ledger, FakeBroker(), "test-secret", live_enabled=False)
    approved = approve(service, service.create(make_intent("live")))
    assert service.submit(approved["intent_uuid"])["state"] == "Rejected"


def test_notional_limit_rejects_before_submit(ledger):
    service = GuardedOrderService(ledger, FakeBroker(), "test-secret", max_notional=Decimal("50"))
    created = service.create(make_intent())
    assert service.preview(created["intent_uuid"])["state"] == "Rejected"


def test_partial_fill_duplicate_and_cancel_fill_race(ledger):
    service = GuardedOrderService(ledger, FakeBroker(), "test-secret")
    submitted = service.submit(approve(service, service.create(make_intent()))["intent_uuid"])
    first = {"account_alias": "paper-primary", "exec_id": "e1", "conid": 101, "quantity": "4", "price": "10", "side": "BOT", "executed_at": "2026-08-17T14:00:00Z"}
    assert service.record_execution(submitted["intent_uuid"], first)["state"] == "PartiallyFilled"
    service.record_execution(submitted["intent_uuid"], first)
    assert ledger.connection.execute("SELECT COUNT(*) FROM executions").fetchone()[0] == 1
    assert service.request_cancel(submitted["intent_uuid"])["state"] == "CancelPending"
    last = {**first, "exec_id": "e2", "quantity": "6", "executed_at": "2026-08-17T14:00:01Z"}
    assert service.record_execution(submitted["intent_uuid"], last)["state"] == "Filled"
    assert service.apply_broker_status(submitted["intent_uuid"], "Cancelled")["state"] == "Filled"


def test_default_sell_is_reduce_only_and_cannot_cross_zero(ledger):
    service = GuardedOrderService(ledger, FakeBroker(), "test-secret")
    intent = OrderIntent(account_alias="paper-primary", conid=101, contract_fingerprint="101|STK|USD|SMART", action="SELL", quantity=Decimal("11"), limit_price=Decimal("10"), owner="drew", strategy="single_stock")
    created = service.create(intent)
    assert created["reduce_only"] == 1
    assert service.preview(created["intent_uuid"])["state"] == "Rejected"
