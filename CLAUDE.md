# CLAUDE.md — single-stock-investments

## IB Gateway coexistence (three systems, one Gateway) — DO NOT VIOLATE

The NY4 Gateway is shared by **spx-0dte**, **ls-algo**, and **this repo's
portfolio hub**. SPX 0DTE is the protected party: nothing on our side may
disconnect it or block its reconnect. The identical contract lives in all
three repos (spx-0dte `AGENTS.md`, ls-algo `CLAUDE.md`); a change here must
be mirrored there in the same PR. The hub-side detail lives in
`_system/trading/portfolio_hub/CLIENT_ID_REGISTRY.md`.

**Client-ID map (verified 2026-08-20 against source):**

| System | IDs |
|---|---|
| spx-0dte | **17** (live executor), **18** (ibc_guard handshake probe — read-only connect/disconnect, never subscribes or transmits), **19** (market-data line probe — off-hours only, refuses 09:20–16:10 ET, cancels every subscription it opens), **87** (ES/SPX basis sampler — read-only, snapshot requests only, no streaming lines held) |
| ls-algo | 0 (cancel coordinator, orderRef-filtered), 41 (rebalancer base), 77 (flow program), 90 (daily screener), 197/207 (bucket5 probes), workers 241–273, 341–373, 551, 1041+ |
| this repo | 71/72/73 (sleeves drew/michael/sync), ~~81~~ (collector — **DISABLED INDEFINITELY 2026-08-25**, reconnect storm; see `deploy/portfolio-hub-collector.service`), 82 (master observer, reserved — **not 90**, which is ls-algo's screener), **91** (order bridge, sole hub transmitter — not yet deployed) |
| Operator TWS | manual only |

**Rule 0 — the one that governs the rest. During market hours on a market day
(09:30–16:00 ET, Mon–Fri, US holidays excluded) no agent initiates anything that
touches the Gateway.** Not a connect, not a probe, not a "quick read-only check",
not a unit restart. Diagnose from logs, the local ledger, D1 and the committed
payload — none of which need a socket. If a task truly requires the Gateway
during RTH, stop and ask the user in chat and say why it cannot wait until after
16:15 ET; approval for one such action never carries to the next. Off-hours, and
after 16:15 ET on a weekday, is the normal window. This is mirrored for Cursor in
`.cursor/rules/ib-gateway-safety.mdc` (`alwaysApply: true`); the two must agree.

Rules that keep SPX safe (test-enforced where noted):

1. **Never `reqGlobalCancel`** — cancels every working order account-wide,
   including SPX's. No call site may exist (`test_ib_bridge.py` enforces).
   Cancellation requires a `MAGIS|` orderRef submitted by client 91.
2. **Never take another system's client ID** — the hazard is grabbing an ID
   while its owner is mid-reconnect, locking it out. The reserved set is
   pinned in `test_ib_bridge.py`; new IDs go in this table in all three repos
   before first use.
3. **Connection slots:** the Gateway accepts ~32 API connections total; the
   hub holds at most 2 (81 + 91) and never opens worker pools. ls-algo caps
   itself at 26 for the same reason. **Counting concurrent sockets is not
   sufficient** — the hub collector passed this rule while connecting and
   disconnecting client 81 every 30 seconds, ~780 connects per session, and was
   masked on 2026-08-25 for it. A long-lived session is required, not merely a
   small number of simultaneous ones.
4. **Market-data lines are one account-wide pool** shared with SPX's option
   NBBO stream. The bridge uses `snapshot=True` only, cancels in `finally`,
   and is leak-tested (50 quotes → 0 open lines, ≤1 concurrent). Keep it
   that way; never add a streaming subscription to the hub.
5. **`reqAutoOpenOrders` must never appear in this repo** (test-enforced) —
   binding TWS orders is how a hub session could end up owning SPX orders.
6. **Never stop/restart the Gateway process** or flip its global Read-Only
   API toggle. SPX rides through IBKR's daily restart window by design.
   **Sole carve-out (2026-08-20):** spx-0dte's `ibc_guard` may issue ONE
   remedial restart per day when the API handshake is provably wedged (port
   accepts TCP, client-18 probe handshake fails ≥2 consecutive 5-min checks
   during session hours). In that state every system on this Gateway is
   equally disconnected, so the restart harms no one — it pages Slack when it
   fires. Mirror this clause in spx-0dte `AGENTS.md` and ls-algo `CLAUDE.md`.
7. **Background jobs deployed to NY4** (Whisper backfill, collectors) run
   `Nice≥15` + `CPUQuota` + `IOSchedulingClass=idle` so the SPX executor never
   waits on CPU. The box has **4 cores**. Enforced with systemd drop-ins at
   `~/.config/systemd/user/<unit>.service.d/10-spx-coexistence.conf`. Retry loops
   need a real backoff: at the stock `RestartSec=5` the collector produced
   **6,785 restarts and ~315k journal lines in one day** against a Gateway that
   was intentionally down.
9. **NEVER POLL THE GATEWAY FROM THIS REPO. This rule has no exceptions.**
   Broker truth arrives via **IBKR Flex**, which is an HTTPS report service and
   touches no Gateway, no TWS API socket and no client ID. There is no
   `collect` command in this repo and there must never be one again.

   Why this is a rule and not a preference: the hub collector (client 81) held
   a *single* connection at a time and so passed rule 3 for months, while
   opening and closing that connection **every 30 seconds** -- about 780
   connects per session. On Monday 2026-08-24, an ordinary day with no outage,
   systemd logged **213 restarts of it during RTH alone**; on 2026-08-25 it
   logged 1,057 start/stop events before the SPX side masked it. It was a
   standing denial-of-service against the Gateway carrying the live SPX 0DTE
   executor, and it read as healthy the entire time because the thing being
   counted (concurrent sockets) was not the thing doing the harm.

   The three failures that combined, all of which any future design must avoid:
   * **Churn.** A session opened and closed per poll. Any Gateway session must
     be long-lived; a small number of concurrent connections is not the same as
     a small number of connection *events*.
   * **Crash-to-restart.** A failed connect escaped and killed the process, so
     an upstream outage became a restart loop. Connection failure must be
     caught in-process with real backoff and a daily cap.
   * **Polling at all.** Nothing on this dashboard needs sub-daily broker
     truth. It is a research and allocation surface, not an execution screen.
     Intraday state belongs to the systems that own it.

   Applies to any future component, in any language, under any name. If a
   design needs a repeating Gateway connection to work, the design is wrong.
   The only Gateway contact this repo may ever make is a **human-initiated,
   single-shot** order action (see rule 10).

10. **Order placement, if it exists, is event-driven and never scheduled.**
    No standing Gateway session, no poll loop against IB. A connection may be
    opened only in response to a specific human action on a specific ticket,
    must be released when that ticket reaches a terminal state, and must be
    rate-limited with a circuit breaker that fails closed. The command channel
    is polled against **D1 over HTTPS**, never against the Gateway.

11. **`ibc.service` is a session service.** It starts, runs a few hours, and exits
   `0/SUCCESS` after the close; weekends it is down entirely. A
   `ConnectionRefusedError` on 127.0.0.1:**7496** is therefore normal off-hours,
   **not a fault**. Never "fix" it by restarting anything, and never by touching
   `ibc.service` (see rule 6).

**What is actually deployed on NY4 (verified 2026-08-22).** Do not re-derive this
from `portfolio_hub/deploy/README.md`: that README installs to `/opt` + `/etc` +
`/var/lib` under *system* systemd, but the real install is under **`/home/spx`
with `spx`'s *user* systemd**, which is invisible to `systemctl list-units`. Use
`sudo -u spx XDG_RUNTIME_DIR=/run/user/1000 systemctl --user list-units --all
'portfolio-hub*'`. The repo there is `/home/spx/single-stock-investments`, a
**file copy with no `.git`** — so changes merged to `main` do NOT reach it until
someone copies them. That is how owner attribution broke silently: the copy
predated the Michael split, `allocation_policy.py` was absent entirely, and every
position fell through to Michael's residual book. Ledger is
`/home/spx/portfolio-hub/portfolio.db`; account id `U805366` and
`IBKR_ACCOUNT_ALIAS=U805366` (same string, different concept — the alias is a hub
partition key, never read from IB).
