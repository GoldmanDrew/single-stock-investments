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

Cross-system map: SPX 0DTE runs as client **17** (live executor) and **18** (ibc_guard handshake probe — read-only connect/disconnect, never subscribes or transmits); ls-algo holds 0 (cancel coordinator), 41, 77, 90, 197/207 and worker ranges 241–273, 341–373, 551, 1041+; the sleeves use 71–73. The full three-repo coexistence contract is in the repo-root `CLAUDE.md` and mirrored in spx-0dte `AGENTS.md` and ls-algo `CLAUDE.md`.

The production registry records account alias, host, port, client ID, process owner, orderRef namespace, and kill switch. Client IDs are unique. The master observer's next valid order ID must exceed every order ID it observes, but it never transmits. The bridge persists `gateway_session_id`, `clientId`, `orderId`, `permId`, `orderRef`, `parentId`, `ocaGroup`, account alias, and producer.

## Recovery invariant

Before accepting commands after restart, the bridge reads open, completed, and executed orders; classifies every one by positive ownership; recovers hub intents by orderRef/permId/executions; and proves no unresolved working order exists. Manual/foreign/legacy orders are visible and never bound, modified, or cancelled. `reqGlobalCancel` is prohibited.

If transport fails after `placeOrder` and before acknowledgement, the intent becomes `SubmitUncertain`. Retry is prohibited until reconciliation by orderRef plus broker IDs and executions resolves the state.

## Live gate

Live mode remains disabled until SPX and LS stamp and soak positive orderRefs, all working orders classify, Gateway restart/cancel-fill-race/partial-fill/uncertain-send scenarios pass, the watchdog and backups are active, and a capped allowlisted live canary is explicitly approved.
