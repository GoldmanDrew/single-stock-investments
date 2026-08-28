# IBKR session and order ownership ADR

Status: implemented contract; production values must be registered before NY4 activation.

## Decision

One long-lived hub bridge is the sole transmitter for central orders. The collector calls that bridge for order observation rather than creating a second submitting session. A separate read-only collector client may collect positions/account values, but application code prevents it from transmitting; Gateway's global Read Only API setting is not relied upon because it can suppress required order information.

| Role | Default client ID | May transmit | Owns/cancels |
|---|---:|---|---|
| ~~Hub collector~~ | 81 | No | Nothing | **DISABLED 2026-08-25 — do not re-enable.** Masked on NY4 after reconnect-storming the shared Gateway (a session every 30s, ~780 connects/session, 213 systemd restarts during a healthy Monday RTH). It passed the concurrency rule the whole time because concurrency was not what did the harm. See repo-root `CLAUDE.md` rules 9-10; broker truth is now Flex over HTTPS, which uses no client ID. The ID stays reserved so nobody else takes it.
| Hub master observer | 82 | No | Nothing; observes all clients. (Was documented as 90, which collides with ls-algo's daily screener — `daily_screener.py` client_id=90. Never implemented at 90; reassigned before first use.) |
| Hub order bridge | 91 | Paper initially | Only positive `MAGIS|…` orderRefs submitted by client 91 |
| SPX producer | Existing registered value | Its strategy only | Positive SPX namespace after migration |
| LS producer | Existing registered value | Its strategy only | Positive LS namespace after migration |
| Manual TWS | 0 / registered operator | Manual only | Always foreign to hub |

Cross-system map: SPX 0DTE runs as client **17** (live executor), **18** (ibc_guard handshake probe — read-only connect/disconnect, never subscribes or transmits), **19** (market-data line probe — off-hours only, cancels every subscription it opens), **87** (ES/SPX basis sampler — read-only snapshots, holds no streaming lines), **88** (quote_sleeve_margin whatIf probe — off-hours, never transmits; added to the cross-repo registries 2026-08-25) and **97** (dead-executor watchdog, 17 + offset 80); ls-algo holds 0 (cancel coordinator), 41, 77, 90, 198 (bucket5 contract probe) and a leased worker pool at **100–129**; hub IDs are 81 (DISABLED 2026-08-25, reserved) and 91. The full three-repo coexistence contract is in the repo-root `CLAUDE.md` and mirrored in spx-0dte `AGENTS.md` and ls-algo `CLAUDE.md`.

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

## Client-ID reduction, 2026-08-23

ls-algo cut its reserved footprint from 602 client IDs to 35. Its worker
sessions now lease from a 100-129 pool and return the ID on disconnect, instead
of deriving one from the coordinator base (`+200+i`, `+300+i`,
`+1000+16i+leg`) -- three formulas whose combinatorial range reserved 594
integers to serve a peak of 12 simultaneous workers. IB only requires a client
ID to be unique among live connections, and ls-algo identifies its orders by
the `ETF_LS|` orderRef prefix rather than by clientId, so none of those workers
ever needed a stable or derivable number.

Two ls-algo IDs were deleted rather than renumbered: **92**, whose only code
path (`bucket5_monitor --live`) had no caller and which had collided with
spx-0dte's basis sampler on 87; and **197**, whose TWS signal provider never
ran because both NY4 and CI override it to yfinance.

**Hub IDs 71/72/73 and 82 were unreserved.** An audit of this repo's `main`
found no implementing code: `portfolio_hub` uses 81 (`broker.py`) and 91
(`paper.py`, `config.example.toml`), and the only mention of 71-73 anywhere in
the tree was this file asserting the reservation. Nothing was removed from the
hub -- only the claim on numbers it never used. **If sleeves are implemented,
register the IDs here first**, because ls-algo's pool now sits at 100-129 and
its guard will refuse anything it does not own, which is no protection for a
hub ID that was never written down.

The hub's own protection is unchanged and does not depend on any of this: the
positive-ownership rule below still stands on its own, and no ID guard removes
the need to classify every working order by `MAGIS|` orderRef before acting.

## Recovery invariant

Before accepting commands after restart, the bridge reads open, completed, and executed orders; classifies every one by positive ownership; recovers hub intents by orderRef/permId/executions; and proves no unresolved working order exists. Manual/foreign/legacy orders are visible and never bound, modified, or cancelled. `reqGlobalCancel` is prohibited.

If transport fails after `placeOrder` and before acknowledgement, the intent becomes `SubmitUncertain`. Retry is prohibited until reconciliation by orderRef plus broker IDs and executions resolves the state.

## Live gate

Live mode remains disabled until SPX and LS stamp and soak positive orderRefs, all working orders classify, Gateway restart/cancel-fill-race/partial-fill/uncertain-send scenarios pass, the watchdog and backups are active, and a capped allowlisted live canary is explicitly approved.
