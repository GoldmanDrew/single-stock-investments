"""The receipt that counts Gateway connection events.

The collector was not invisible for want of a dashboard. It was invisible
because what got counted -- concurrent sockets -- was not what did the harm, so
it read healthy while opening roughly 780 connections a session. This receipt
reads the same attempt rows the brake writes, so the watched number and the
enforced number cannot drift apart.
"""
from __future__ import annotations

import json

import pytest

from _system.trading.portfolio_hub.cli import main
from _system.trading.portfolio_hub.gateway_budget import BudgetLimits, ConnectionBudget
from _system.trading.portfolio_hub.ledger import PortfolioLedger


class FakeClock:
    def __init__(self, start: float):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def seed(tmp_path, events: int, *, purpose: str = "preview for request 4f2a"):
    import time

    ledger = PortfolioLedger(tmp_path / "portfolio.db")
    ledger.migrate()
    clock = FakeClock(time.time() - 600)
    budget = ConnectionBudget(limits=BudgetLimits(max_per_hour=10_000, max_per_day=10_000),
                              clock=clock, store=ledger.budget_store())
    for _ in range(events):
        budget.reserve(purpose)
        clock.advance(1)
    ledger.close()
    return tmp_path / "portfolio.db"


def run(db, capsys, *extra):
    code = main(["--db", str(db), "gateway-receipt", *extra])
    return json.loads(capsys.readouterr().out), code


def test_an_idle_desk_reads_quiet_and_never_as_a_fault(tmp_path, capsys):
    """Zero is the expected healthy reading, not a missing-data error."""
    db = seed(tmp_path, 0)
    payload, code = run(db, capsys)
    assert code == 0
    assert payload["status"] == "quiet"
    assert payload["connection_events_last_day"] == 0
    assert payload["alarms"] == []


def test_a_handful_of_human_tickets_stays_quiet(tmp_path, capsys):
    db = seed(tmp_path, 4)
    payload, code = run(db, capsys)
    assert code == 0
    assert payload["status"] == "quiet"
    assert payload["connection_events_last_day"] == 4


def test_a_loop_forming_alarms_well_below_the_hard_cap(tmp_path, capsys):
    """The point is to fire on a day the brake never engaged.

    A receipt that only alarms at the 60/day cap reports nothing the budget did
    not already refuse.
    """
    db = seed(tmp_path, 25)
    with pytest.raises(SystemExit) as exit_info:
        run(db, capsys)
    assert exit_info.value.code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "alarm"
    assert any("24h" in alarm for alarm in payload["alarms"])


def test_the_receipt_attributes_events_to_what_caused_them(tmp_path, capsys):
    """'Something connected' is not diagnosable."""
    db = seed(tmp_path, 3, purpose="preview for request 4f2a")
    payload, _ = run(db, capsys)
    assert payload["by_purpose"] == {"preview for request 4f2a": 3}
    assert payload["newest_event"].endswith("Z")


def test_an_open_breaker_alarms_even_when_the_counts_are_low(tmp_path, capsys):
    """Three failed connects is a quiet day by volume and a wedged Gateway by meaning."""
    import time

    ledger = PortfolioLedger(tmp_path / "portfolio.db")
    ledger.migrate()
    budget = ConnectionBudget(limits=BudgetLimits(trip_after_failures=2, trip_seconds=900,
                                                  max_per_hour=100),
                              clock=time.time, store=ledger.budget_store())
    for _ in range(2):
        budget.reserve("failing connect"); budget.record_failure()
    ledger.close()

    with pytest.raises(SystemExit) as exit_info:
        run(tmp_path / "portfolio.db", capsys)
    assert exit_info.value.code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["breaker_open"] is True
    assert any("circuit breaker open" in alarm for alarm in payload["alarms"])
