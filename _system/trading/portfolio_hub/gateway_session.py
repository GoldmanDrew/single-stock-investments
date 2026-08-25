"""A Gateway connection that exists only for the duration of one piece of work.

CLAUDE.md rule 10: order placement is event-driven and never scheduled. This is
the mechanism. The command loop polls **D1 over HTTPS** and holds no IB
connection at all; when -- and only when -- a claimed ticket actually needs the
broker, it opens a session here, does that ticket's broker work, and closes it.

The difference from the collector is not the size of a number. The collector
connected because a timer fired. This connects because a human approved a
ticket, and if no human does anything it never connects at all. An idle desk
makes zero Gateway contact, which is the state it is in almost all of the time.

Two properties matter more than the rest:

  * **A failed connect produces a rejected ticket, not a retry.** The collector's
    fatal shape was failure feeding back into another attempt; here the failure
    is reported to the person who asked, and the next attempt requires them to
    ask again. Nothing in this module retries anything.
  * **The budget is consulted before the connection and charged regardless of
    outcome.** See gateway_budget.py, which deliberately contains no connection
    code so the limit cannot be bypassed by editing the thing it limits.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Callable, Iterator

from .gateway_budget import ConnectionBudget, GatewayBudgetExceeded


class GatewayUnavailable(RuntimeError):
    """A session could not be opened. Carries the reason; never retried here."""


class GatewaySessionFactory:
    """Opens one short-lived Gateway session per unit of broker work."""

    def __init__(
        self,
        connect: Callable[[], Any],
        *,
        budget: ConnectionBudget | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ):
        # `connect` returns a *connected* broker. Keeping construction out of
        # this module means the session logic can be tested without ib_async
        # present, and means this file never imports it.
        self._connect = connect
        self.budget = budget or ConnectionBudget()
        self._on_event = on_event or (lambda event: None)
        self.sessions_opened = 0

    def refusal_reason(self) -> str | None:
        return self.budget.refusal_reason()

    @contextmanager
    def session(self, purpose: str) -> Iterator[Any]:
        """Connect, yield the broker, and disconnect -- always.

        `purpose` is recorded so the journal says which ticket caused a
        connection. "Something connected" is not diagnosable; "preview for
        request 4f2a" is.
        """
        try:
            self.budget.reserve()
        except GatewayBudgetExceeded as exc:
            self._on_event({"event": "gateway_refused", "purpose": purpose, "reason": str(exc)})
            raise GatewayUnavailable(str(exc)) from exc

        try:
            broker = self._connect()
        except Exception as exc:
            # Charged and counted. Three of these in a row opens the breaker.
            self.budget.record_failure()
            self._on_event({"event": "gateway_connect_failed", "purpose": purpose, "error": str(exc)})
            raise GatewayUnavailable(f"gateway connect failed: {exc}") from exc

        self.budget.record_success()
        self.sessions_opened += 1
        self._on_event({"event": "gateway_opened", "purpose": purpose, "budget": self.budget.state()})
        try:
            yield broker
        finally:
            # Releasing is not optional and not conditional. A leaked session
            # holds one of the ~32 API slots this Gateway shares with SPX, and a
            # leak during an exception is exactly when nobody is looking.
            try:
                broker.disconnect()
            except Exception as exc:  # pragma: no cover - best effort teardown
                self._on_event({"event": "gateway_release_failed", "purpose": purpose, "error": str(exc)})
            else:
                self._on_event({"event": "gateway_closed", "purpose": purpose})


def build_live_session_factory(
    *, route: str = "paper", budget: ConnectionBudget | None = None,
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> GatewaySessionFactory:
    """The real factory. Imports ib_async lazily, inside the connect call.

    Constructing this object touches nothing. The import and the socket both
    happen inside `connect()`, so a process can hold a factory indefinitely
    without having contacted IBKR -- which is the normal state of the order
    loop.
    """
    def connect() -> Any:
        from .ib_bridge import BridgeProfile, IbOrderBridge

        gateway = IbOrderBridge(BridgeProfile.from_env())
        gateway.connect()  # refuses to serve until ownership recovery passes
        if route == "live":
            return gateway
        from .paper import PaperOrderBroker, PaperRoutedBroker

        routed = PaperRoutedBroker(gateway, PaperOrderBroker(gateway.quote))
        # The wrapper has no socket; teardown has to reach the gateway itself.
        routed.disconnect = gateway.disconnect  # type: ignore[attr-defined]
        return routed

    return GatewaySessionFactory(connect, budget=budget, on_event=on_event)
