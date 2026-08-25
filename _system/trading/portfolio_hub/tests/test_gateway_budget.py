from __future__ import annotations

import pytest

from _system.trading.portfolio_hub.gateway_budget import (
    BudgetLimits,
    ConnectionBudget,
    GatewayBudgetExceeded,
)


class FakeClock:
    def __init__(self, start: float = 1_000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def budget(**limits) -> tuple[ConnectionBudget, FakeClock]:
    clock = FakeClock()
    return ConnectionBudget(limits=BudgetLimits(**limits), clock=clock), clock


# ------------------------------------------------- the limit contains no client

def test_the_budget_module_contains_no_connection_machinery():
    """The limit exists before the capability, and stays independent of it.

    Checks for the machinery, not the word: `connect` appears throughout the
    prose here because the module is *about* connections. What must be absent is
    anything that could open one.
    """
    import ast
    import inspect

    from _system.trading.portfolio_hub import gateway_budget

    tree = ast.parse(inspect.getsource(gateway_budget))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    for forbidden in ("ib_async", "ib_insync", "socket", "http", "urllib", "requests"):
        assert forbidden not in imported, f"gateway_budget must not import {forbidden}"

    source = inspect.getsource(gateway_budget)
    for port in ("7496", "4002", "4001", "7497"):
        assert port not in source, f"gateway_budget must not name port {port}"


# ------------------------------------------------------------------ hourly cap

def test_the_hourly_cap_refuses_the_connection_after_it():
    b, _ = budget(max_per_hour=3)
    for _ in range(3):
        b.reserve()
    with pytest.raises(GatewayBudgetExceeded, match="3 connections in the last hour"):
        b.reserve()


def test_the_hourly_window_rolls():
    b, clock = budget(max_per_hour=2)
    b.reserve(); b.reserve()
    assert b.refusal_reason() is not None
    clock.advance(3601)
    assert b.refusal_reason() is None, "an hour later the window has rolled"
    b.reserve()


def test_a_slow_leak_under_the_hourly_cap_still_hits_the_daily_cap():
    b, clock = budget(max_per_hour=100, max_per_day=5)
    for _ in range(5):
        b.reserve()
        clock.advance(3600)  # one per hour, never trips the hourly brake
    with pytest.raises(GatewayBudgetExceeded, match="in the last day"):
        b.reserve()


# ------------------------------------------------------------ circuit breaker

def test_consecutive_failures_open_the_breaker():
    b, _ = budget(trip_after_failures=3)
    for _ in range(3):
        b.reserve()
        b.record_failure()
    reason = b.refusal_reason()
    assert reason is not None and "circuit breaker is open" in reason
    assert "No automatic retry" in reason


def test_a_success_clears_the_failure_run():
    """Transient refusals must not accumulate into a trip across a whole day."""
    b, _ = budget(trip_after_failures=3)
    b.reserve(); b.record_failure()
    b.reserve(); b.record_failure()
    b.reserve(); b.record_success()
    b.reserve(); b.record_failure()
    assert b.refusal_reason() is None, "two failures either side of a success are not three in a row"


def test_the_breaker_stays_open_for_the_cooldown_then_closes():
    b, clock = budget(trip_after_failures=2, trip_seconds=900, max_per_hour=100)
    for _ in range(2):
        b.reserve(); b.record_failure()
    assert b.state()["tripped"] is True
    clock.advance(899)
    assert b.state()["tripped"] is True, "the cooldown is not nearly over"
    clock.advance(2)
    assert b.state()["tripped"] is False
    b.reserve()


def test_the_breaker_does_not_re_arm_itself_on_a_timer_alone():
    """After the cooldown the failure count survives, so one more failure re-trips."""
    b, clock = budget(trip_after_failures=2, trip_seconds=10, max_per_hour=100)
    for _ in range(2):
        b.reserve(); b.record_failure()
    clock.advance(11)
    b.reserve(); b.record_failure()
    assert b.state()["tripped"] is True, "a still-broken gateway must trip again immediately"


# --------------------------------------------------- the collector's own shape

def test_a_failing_reconnect_loop_is_stopped_within_a_few_attempts():
    """The collector managed 213 restarts in one RTH session. This is that shape."""
    b, clock = budget(max_per_hour=12, trip_after_failures=3, trip_seconds=900)
    attempts = 0
    for _ in range(500):
        if b.refusal_reason():
            break
        b.reserve()
        b.record_failure()
        attempts += 1
        clock.advance(60)  # one attempt a minute, as systemd RestartSec=60 would
    assert attempts == 3, f"a dead gateway must stop us in 3 attempts, took {attempts}"


def test_an_attempt_is_charged_even_when_the_connection_fails():
    """Counting only successes would let a failing connect loop for free."""
    b, _ = budget(max_per_hour=2, trip_after_failures=99)
    b.reserve(); b.record_failure()
    b.reserve(); b.record_failure()
    assert b.refusal_reason() is not None


# ------------------------------------------------------------------- failsafe

def test_refusal_reasons_are_always_explicit():
    """A silent refusal in an order path looks the same as a lost order."""
    b, _ = budget(max_per_hour=1)
    b.reserve()
    with pytest.raises(GatewayBudgetExceeded) as excinfo:
        b.reserve()
    assert str(excinfo.value).strip(), "a refusal must carry a reason"


def test_reset_is_manual_and_never_on_an_automatic_path():
    import inspect

    from _system.trading.portfolio_hub import command_poller, gateway_budget

    assert "def reset" in inspect.getsource(gateway_budget.ConnectionBudget)
    assert ".reset()" not in inspect.getsource(command_poller), \
        "the loop must never re-arm its own breaker"


def test_state_reports_enough_to_diagnose_without_reading_the_code():
    b, _ = budget(max_per_hour=5)
    b.reserve()
    state = b.state()
    assert state["last_hour"] == 1
    assert state["max_per_hour"] == 5
    assert state["tripped"] is False
