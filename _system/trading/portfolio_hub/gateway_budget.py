"""How often this repo is allowed to touch IB Gateway, and what stops it.

This module contains no connection code on purpose. It is the limit, and the
limit exists before the capability does.

CLAUDE.md rule 9 bans polling the Gateway outright; rule 10 permits exactly one
exception -- a human-initiated, single-shot order action. The gap between those
two is narrow and easy to fall through, because "connect when a ticket needs it"
degrades into "connect constantly" the moment tickets stop reaching a terminal
state. That is precisely how the collector behaved: every individual connection
was defensible, and the aggregate was a denial-of-service against the Gateway
carrying the live SPX 0DTE executor.

So the budget counts connection *events*, not concurrent sessions. Concurrency
was the thing the old rule measured and it stayed at one the whole time the
collector was doing damage.

Three independent brakes, any of which refuses on its own:

  * a rolling hourly cap -- more than a handful of connections an hour means
    something is looping, whatever it believes it is doing;
  * a daily cap -- a slow leak that stays under the hourly cap still stops;
  * a consecutive-failure trip -- N failures in a row opens the breaker for a
    cooldown, so a wedged or Authenticating Gateway is never hammered. This is
    the brake the collector did not have: its failures fed straight back into
    retries.

All three are durable when a store is supplied. They used to live only in
memory on a `time.monotonic` basis, which meant a process restart cleared the
hourly cap, the daily cap and the breaker together -- and a restart is precisely
what a reconnect storm is made of. Each brake was defensible; the composition
handed the storm a clean slate every 60 seconds. The counts now go through
`BudgetStore` to the ledger, and the clock is wall clock so the windows still
mean something on the other side of a restart.

Every refusal is explicit and carries a reason, because a silent refusal in an
order path is indistinguishable from an order that quietly did not happen.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Callable, Protocol


class GatewayBudgetExceeded(RuntimeError):
    """Refused: connecting now would breach the coexistence budget."""


class BudgetStore(Protocol):
    """Where the brakes persist. Deliberately a protocol, not a database.

    Keeping this an interface is what lets the limit stay free of storage
    machinery, the same way it stays free of connection machinery. The concrete
    SQLite implementation lives with the ledger; this module never learns what
    a table is.
    """

    def load(self) -> tuple[list[float], int, float | None]:
        """Return (attempt timestamps, consecutive failures, tripped_until)."""

    def record_attempt(self, when: float, purpose: str | None = None) -> None: ...

    def save_breaker(self, consecutive_failures: int, tripped_until: float | None) -> None: ...

    def forget_before(self, cutoff: float) -> None: ...


@dataclass
class BudgetLimits:
    # A human placing orders touches the Gateway a handful of times an hour.
    # The collector managed roughly 120. Anything approaching that is a loop.
    max_per_hour: int = 12
    max_per_day: int = 60
    # Consecutive failures before the breaker opens. Three is enough to ride out
    # a transient refusal and few enough that a wedged Gateway stops us fast.
    trip_after_failures: int = 3
    # How long the breaker stays open. Long enough that a human notices and
    # looks, rather than the system quietly recovering into the same loop.
    trip_seconds: float = 900.0


@dataclass
class ConnectionBudget:
    """A rolling ledger of Gateway connection attempts, and the brakes on them."""

    limits: BudgetLimits = field(default_factory=BudgetLimits)
    clock: Callable[[], float] = field(default=None)  # type: ignore[assignment]
    # Optional so the tests, the drills and `--once` runs need no database. When
    # absent the budget behaves exactly as it always did: correct, and volatile.
    store: BudgetStore | None = None

    def __post_init__(self) -> None:
        if self.clock is None:
            import time

            # Wall clock, not monotonic. Monotonic is the better choice for a
            # duration measured inside one process and the wrong one for a
            # window that has to survive the process: two runs of this program
            # share no monotonic origin, so a restart would silently reset every
            # count to zero. A backwards NTP step holds the breaker open longer
            # than asked, which fails closed; a forward step rolls a window
            # early, and on an NTP-disciplined host is sub-second.
            self.clock = time.time
        self._attempts: list[float] = []
        self._consecutive_failures = 0
        self._tripped_until: float | None = None
        self._lock = threading.RLock()
        if self.store is not None:
            # Adopt whatever the last process left behind, including an open
            # breaker. Starting clean here is the bug this parameter exists for.
            self._attempts, self._consecutive_failures, self._tripped_until = self.store.load()

    # ------------------------------------------------------------- inspection

    def state(self) -> dict[str, object]:
        with self._lock:
            now = self.clock()
            self._forget_old(now)
            return {
                "last_hour": self._count_since(now - 3600),
                "last_day": self._count_since(now - 86_400),
                "max_per_hour": self.limits.max_per_hour,
                "max_per_day": self.limits.max_per_day,
                "consecutive_failures": self._consecutive_failures,
                "tripped": self._tripped_until is not None and now < self._tripped_until,
                "tripped_for_seconds": None if self._tripped_until is None
                else max(0.0, round(self._tripped_until - now, 1)),
            }

    def refusal_reason(self) -> str | None:
        """Why a connection would be refused right now, or None if it is allowed."""
        with self._lock:
            now = self.clock()
            self._forget_old(now)
            if self._tripped_until is not None and now < self._tripped_until:
                remaining = int(self._tripped_until - now)
                return (
                    f"gateway circuit breaker is open after "
                    f"{self._consecutive_failures} consecutive failures; "
                    f"{remaining}s remaining. No automatic retry."
                )
            hour = self._count_since(now - 3600)
            if hour >= self.limits.max_per_hour:
                return (
                    f"gateway connection budget spent: {hour} connections in the last hour "
                    f"(limit {self.limits.max_per_hour})"
                )
            day = self._count_since(now - 86_400)
            if day >= self.limits.max_per_day:
                return (
                    f"gateway connection budget spent: {day} connections in the last day "
                    f"(limit {self.limits.max_per_day})"
                )
            return None

    # -------------------------------------------------------------- recording

    def reserve(self, purpose: str | None = None) -> None:
        """Claim one connection, or raise.

        The attempt is recorded *before* the connection is made, not after. A
        connect that hangs or dies still consumed a slot -- counting only
        successes would let a failing connect loop for free, which is the exact
        shape of the collector's restart storm.
        """
        with self._lock:
            reason = self.refusal_reason()
            if reason:
                raise GatewayBudgetExceeded(reason)
            when = self.clock()
            self._attempts.append(when)
            if self.store is not None:
                # Written before the socket is opened, in the same order as the
                # in-memory list. A crash between this line and the connect must
                # still leave the attempt charged.
                self.store.record_attempt(when, purpose)

    def record_success(self) -> None:
        with self._lock:
            self._consecutive_failures = 0
            self._tripped_until = None
            self._persist_breaker()

    def record_failure(self) -> None:
        """A failed connection. Enough of these in a row opens the breaker."""
        with self._lock:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self.limits.trip_after_failures:
                self._tripped_until = self.clock() + self.limits.trip_seconds
            self._persist_breaker()

    def reset(self) -> None:
        """Manual re-arm. Deliberately not called by any automatic path."""
        with self._lock:
            self._consecutive_failures = 0
            self._tripped_until = None
            self._persist_breaker()

    # ---------------------------------------------------------------- helpers

    def _persist_breaker(self) -> None:
        if self.store is not None:
            self.store.save_breaker(self._consecutive_failures, self._tripped_until)

    def _count_since(self, cutoff: float) -> int:
        return sum(1 for stamp in self._attempts if stamp >= cutoff)

    def _forget_old(self, now: float) -> None:
        horizon = now - 86_400
        if self._attempts and self._attempts[0] < horizon:
            self._attempts = [stamp for stamp in self._attempts if stamp >= horizon]
            if self.store is not None:
                # Only when memory actually dropped something, so a quiet desk
                # is not issuing a DELETE on every state() call.
                self.store.forget_before(horizon)
