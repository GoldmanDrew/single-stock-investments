# IBKR session and order ownership ADR

Status: implemented contract; production values must be registered before NY4 activation.

## Decision

One long-lived hub bridge is the sole transmitter for central orders. The collector calls that bridge for order observation rather than creating a second submitting session. A separate read-only collector client may collect positions/account values, but application code prevents it from transmitting; Gateway's global Read Only API setting is not relied upon because it can suppress required order information.

| Role | Default client ID | May transmit | Owns/cancels |
|---|---:|---|---|
| Hub collector | 81 | No | Nothing |
| Hub master observer | 82 | No | Nothing; observes all clients |
| Hub order bridge | 91 | Paper initially | Only positive `MAGIS|…` orderRefs submitted by client 91 |
| SPX producer | 17 (`spx-0dte` live executor) | Its strategy only | Positive SPX namespace after migration |
| SPX gateway probe | 18 (`spx-0dte` ibc_guard) | Never | Nothing; read-only connect/disconnect handshake probe |
| LS producer | 41 base + registered worker ranges (`ls-algo`) | Its strategy only | Positive LS namespace after migration |
| Manual TWS | 0 / registered operator | Manual only | Always foreign to hub |

2026-08-20 corrections: the master observer is **82**, not 90 — client 90 is
`ls-algo`'s daily screener (see the shared coexistence table in this repo's
`CLAUDE.md`, `ls-algo/CLAUDE.md`, and `spx-0dte/AGENTS.md`; two clients on one
ID lock each other out during reconnect). The observer is not yet implemented
in code; 82 is reserved for it. Client 18 was registered the same day for
spx-0dte's Gateway handshake probe.

Gateway restart tolerance (2026-08-20): spx-0dte's `ibc_guard` may issue ONE
remedial Gateway restart per session day when the API handshake is provably
wedged (all clients equally disconnected). Hub collector and bridge reconnect
logic must treat that like IBKR's nightly restart: reconnect, re-classify open
orders, never assume a dropped session implies operator action.

The production registry records account alias, host, port, client ID, process owner, orderRef namespace, and kill switch. Client IDs are unique. The master observer's next valid order ID must exceed every order ID it observes, but it never transmits. The bridge persists `gateway_session_id`, `clientId`, `orderId`, `permId`, `orderRef`, `parentId`, `ocaGroup`, account alias, and producer.

## Recovery invariant

Before accepting commands after restart, the bridge reads open, completed, and executed orders; classifies every one by positive ownership; recovers hub intents by orderRef/permId/executions; and proves no unresolved working order exists. Manual/foreign/legacy orders are visible and never bound, modified, or cancelled. `reqGlobalCancel` is prohibited.

If transport fails after `placeOrder` and before acknowledgement, the intent becomes `SubmitUncertain`. Retry is prohibited until reconciliation by orderRef plus broker IDs and executions resolves the state.

## Live gate

Live mode remains disabled until SPX and LS stamp and soak positive orderRefs, all working orders classify, Gateway restart/cancel-fill-race/partial-fill/uncertain-send scenarios pass, the watchdog and backups are active, and a capped allowlisted live canary is explicitly approved.
