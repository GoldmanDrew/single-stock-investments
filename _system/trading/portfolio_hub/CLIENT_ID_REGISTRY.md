# IBKR session and order ownership ADR

Status: implemented contract; production values must be registered before NY4 activation.

## Decision

One long-lived hub bridge is the sole transmitter for central orders. The collector calls that bridge for order observation rather than creating a second submitting session. A separate read-only collector client may collect positions/account values, but application code prevents it from transmitting; Gateway's global Read Only API setting is not relied upon because it can suppress required order information.

| Role | Default client ID | May transmit | Owns/cancels |
|---|---:|---|---|
| Hub collector | 81 | No | Nothing |
| Hub master observer | 82 | No | Nothing; observes all clients. (Was documented as 90, which collides with ls-algo's daily screener — `daily_screener.py` client_id=90. Never implemented at 90; reassigned before first use.) |
| Hub order bridge | 91 | Paper initially | Only positive `MAGIS|…` orderRefs submitted by client 91 |
| SPX producer | Existing registered value | Its strategy only | Positive SPX namespace after migration |
| LS producer | Existing registered value | Its strategy only | Positive LS namespace after migration |
| Manual TWS | 0 / registered operator | Manual only | Always foreign to hub |

Cross-system map: SPX 0DTE runs as client **17** (live executor), **18** (ibc_guard handshake probe — read-only connect/disconnect, never subscribes or transmits), **19** (market-data line probe — off-hours only, cancels every subscription it opens), **87** (ES/SPX basis sampler — read-only snapshots, holds no streaming lines) and **97** (dead-executor watchdog, 17 + offset 80); ls-algo holds 0 (cancel coordinator), 41, 77, 90, **92** (bucket5 EOD monitor), 197/198 (bucket5 probes) and worker ranges 241–273, 341–373, 551, 1041–1568; the sleeves use 71–73. The full three-repo coexistence contract is in the repo-root `CLAUDE.md` and mirrored in spx-0dte `AGENTS.md` and ls-algo `CLAUDE.md`.

Gateway restart tolerance (2026-08-20): spx-0dte's `ibc_guard` may issue ONE
remedial Gateway restart per session day when the API handshake is provably
wedged (all clients equally disconnected). Hub collector and bridge reconnect
logic must treat that like IBKR's nightly restart: reconnect, re-classify open
orders, never assume a dropped session implies operator action.

The production registry records account alias, host, port, client ID, process owner, orderRef namespace, and kill switch. Client IDs are unique. The master observer's next valid order ID must exceed every order ID it observes, but it never transmits. The bridge persists `gateway_session_id`, `clientId`, `orderId`, `permId`, `orderRef`, `parentId`, `ocaGroup`, account alias, and producer.

## Client-ID audit, 2026-08-22

This registry's own note — that the master observer was moved off 90 before
first use because it collided with ls-algo's screener — is the pattern that
worked. It failed elsewhere, because it depended on a human reading a table.

An audit of source across all three repos found three drifts. **87** was live in
both spx-0dte (`sample_es_basis.py`) and ls-algo (`bucket5_monitor.py`); this
registry and ls-algo's `CLAUDE.md` both assigned it to spx-0dte, so ls-algo
moved to **92** and SPX was untouched. ls-algo's **207** reservation was a
phantom — its bucket5 contract probe runs on **198**, registered nowhere. And
**97** (spx-0dte's watchdog) was absent from all three tables.

ls-algo now enforces its side in code: `config/ib_client_ids.yml` is the
machine-readable allocation, `assert_allocated()` runs inside its `connect_ib`
so a foreign ID raises before the socket opens, and a test scans its source for
unregistered IDs and `--client-id` defaults. The hub's own protection is
unchanged and remains the positive-ownership rule below — no ID guard removes
the need to classify every working order by `MAGIS|` orderRef before acting on
it. Hub IDs 71–73, 81, 82 and 91 are recorded in ls-algo's YAML as foreign, so
an ls-algo process can no longer take one even by mistake.

## Recovery invariant

Before accepting commands after restart, the bridge reads open, completed, and executed orders; classifies every one by positive ownership; recovers hub intents by orderRef/permId/executions; and proves no unresolved working order exists. Manual/foreign/legacy orders are visible and never bound, modified, or cancelled. `reqGlobalCancel` is prohibited.

If transport fails after `placeOrder` and before acknowledgement, the intent becomes `SubmitUncertain`. Retry is prohibited until reconciliation by orderRef plus broker IDs and executions resolves the state.

## Live gate

Live mode remains disabled until SPX and LS stamp and soak positive orderRefs, all working orders classify, Gateway restart/cancel-fill-race/partial-fill/uncertain-send scenarios pass, the watchdog and backups are active, and a capped allowlisted live canary is explicitly approved.
