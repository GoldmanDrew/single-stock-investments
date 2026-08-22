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
| this repo | 71/72/73 (sleeves drew/michael/sync), 81 (collector, read-only), 82 (master observer, reserved — **not 90**, which is ls-algo's screener), **91** (order bridge, sole hub transmitter) |
| Operator TWS | manual only |

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
   itself at 26 for the same reason.
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
   `Nice≥15` + `CPUQuota` so the SPX executor never waits on CPU.
