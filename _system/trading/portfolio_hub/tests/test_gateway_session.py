from __future__ import annotations

import pytest

from _system.trading.portfolio_hub.gateway_budget import BudgetLimits, ConnectionBudget
from _system.trading.portfolio_hub.gateway_session import (
    GatewaySessionFactory,
    GatewayUnavailable,
)


class FakeBroker:
    def __init__(self):
        self.disconnected = 0

    def disconnect(self):
        self.disconnected += 1


def factory(connect=None, **limits):
    broker = FakeBroker()
    events: list[dict] = []
    made = GatewaySessionFactory(
        connect or (lambda: broker),
        budget=ConnectionBudget(limits=BudgetLimits(**limits)) if limits else None,
        on_event=events.append,
    )
    return made, broker, events


# ---------------------------------------------------------- always disconnects

def test_a_session_disconnects_when_the_work_succeeds():
    sessions, broker, _ = factory()
    with sessions.session("preview"):
        pass
    assert broker.disconnected == 1


def test_a_session_disconnects_when_the_work_raises():
    """A leak during an exception is exactly when nobody is looking."""
    sessions, broker, _ = factory()
    with pytest.raises(ValueError):
        with sessions.session("preview"):
            raise ValueError("preview blew up")
    assert broker.disconnected == 1, "the socket must be released on the failure path too"


def test_a_failing_disconnect_does_not_mask_the_original_error():
    class Stubborn(FakeBroker):
        def disconnect(self):
            raise RuntimeError("teardown failed")

    sessions = GatewaySessionFactory(lambda: Stubborn())
    with pytest.raises(ValueError, match="the real problem"):
        with sessions.session("preview"):
            raise ValueError("the real problem")


# --------------------------------------------------------- budget is enforced

def test_the_budget_is_consulted_before_connecting():
    attempts = []

    def connect():
        attempts.append(1)
        return FakeBroker()

    sessions = GatewaySessionFactory(
        connect, budget=ConnectionBudget(limits=BudgetLimits(max_per_hour=2)))
    for _ in range(2):
        with sessions.session("preview"):
            pass
    with pytest.raises(GatewayUnavailable, match="budget spent"):
        with sessions.session("preview"):
            pass
    assert len(attempts) == 2, "the refused session must not have connected"


def test_a_failed_connect_is_charged_and_counted():
    def connect():
        raise ConnectionRefusedError("nope")

    budget = ConnectionBudget(limits=BudgetLimits(trip_after_failures=2, max_per_hour=50))
    sessions = GatewaySessionFactory(connect, budget=budget)
    for _ in range(2):
        with pytest.raises(GatewayUnavailable):
            with sessions.session("preview"):
                pass
    assert budget.state()["tripped"] is True
    # And once tripped, it refuses without even attempting.
    with pytest.raises(GatewayUnavailable, match="circuit breaker"):
        with sessions.session("preview"):
            pass


def test_nothing_in_this_module_retries():
    """The collector's fatal shape was failure feeding back into another attempt.

    Asserted against the AST rather than the text: this module's prose is full
    of the word "retry" because it exists to explain that it does not. What must
    be absent is a loop or a sleep -- the machinery a retry needs.
    """
    import ast
    import inspect

    from _system.trading.portfolio_hub import gateway_session

    tree = ast.parse(inspect.getsource(gateway_session))
    loops = [node for node in ast.walk(tree) if isinstance(node, (ast.While, ast.For, ast.AsyncFor))]
    assert not loops, f"gateway_session must contain no loops; found {len(loops)}"

    calls = {
        node.func.attr for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "sleep" not in calls, "a sleep here would be a retry wearing a different name"


# ------------------------------------------------------------------- lazy work

def test_constructing_the_live_factory_connects_to_nothing():
    """The order loop holds one of these all day without contacting IBKR."""
    from _system.trading.portfolio_hub.gateway_session import build_live_session_factory

    sessions = build_live_session_factory(route="paper")
    assert sessions.sessions_opened == 0
    assert sessions.refusal_reason() is None


def test_events_name_the_purpose_so_a_connection_is_traceable():
    sessions, _, events = factory()
    with sessions.session("preview for request 4f2a"):
        pass
    kinds = [event["event"] for event in events]
    assert kinds == ["gateway_opened", "gateway_closed"]
    assert all(event["purpose"] == "preview for request 4f2a" for event in events)


def test_a_refusal_is_reported_as_an_event_not_swallowed():
    sessions = GatewaySessionFactory(lambda: FakeBroker(),
                                     budget=ConnectionBudget(limits=BudgetLimits(max_per_hour=0)))
    seen: list[dict] = []
    sessions._on_event = seen.append
    with pytest.raises(GatewayUnavailable):
        with sessions.session("preview"):
            pass
    assert seen and seen[0]["event"] == "gateway_refused"
    assert seen[0]["reason"]
