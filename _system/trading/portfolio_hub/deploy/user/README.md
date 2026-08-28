# Arming the order bridge on NY4

`deploy/README.md` one level up installs to `/opt` + `/etc` + `/var/lib` under
**system** systemd. That layout does not exist on NY4. The real install is
`/home/spx` under **spx's user systemd**, which `systemctl list-units` cannot
see. This directory holds units that match the box.

```bash
sudo -u spx XDG_RUNTIME_DIR=/run/user/1000 systemctl --user list-units --all 'portfolio-hub*'
```

Verified 2026-08-24: the box runs `portfolio-hub-collector.service` (client 81,
read-only), `portfolio-hub-publisher.{service,timer}` and
`portfolio-strategy-publish.{service,timer}`. **There is no bridge unit.** The
whole guarded order path — contract resolution, preview, approval, fills — is
built and dormant because nothing polls it.

## What this is not

Starting this unit is not a deploy chore. It is the only thing in this repo
permitted to reach IB Gateway at all. Read CLAUDE.md rules 9 and 10 before
touching it, and never start, stop or restart it inside 09:30–16:00 ET on a
market day.

## It holds no connection

The collector was deleted on 2026-08-25 for reconnect-storming the Gateway. This
process is built so it cannot repeat that, structurally rather than by tuning:

* **It polls D1 over HTTPS, never IB.** On an idle desk — which is nearly always
  — it runs all day having made zero Gateway contact. There is a test asserting
  that 50 idle ticks produce zero connections.
* **A connection follows a human action, not a timer.** A session opens only
  when a claimed ticket needs the broker, covers all of that tick's work in one
  connection, and closes in a `finally`. Killing the process cannot leak a
  client-91 socket because nothing is held between ticks.
* **A failed connect produces a rejected ticket, not a retry.** `gateway_session`
  contains no loop and no sleep, asserted against its AST. The person who asked
  gets told why; asking again is the retry mechanism.
* **Three independent brakes.** `gateway_budget.py` caps connections per hour
  (12) and per day (60), and opens a circuit breaker after 3 consecutive
  failures for 15 minutes. It contains no connection code at all, so the limit
  cannot be bypassed by editing the thing it limits. Against a dead Gateway it
  stops after 3 attempts — the collector managed 213 in one session.

Both caps are env-tunable (`PORTFOLIO_GATEWAY_MAX_PER_HOUR`,
`PORTFOLIO_GATEWAY_MAX_PER_DAY`). Raising them is a decision to argue for, not a
knob to turn when something is refused.

## Why it starts on `--route paper`

`GuardedOrderService.submit()` short-circuits `dry_run` and nothing else, and
the browser pins every ticket it creates to `mode: paper`. Wired directly to
`IbOrderBridge`, a "paper" ticket would therefore have called
`place_limit(transmit=True)` — a real order, under a button labelled
`PAPER · NEVER TRANSMITTED`. Three guards now stand in the way, and the first
deployment leans on all of them:

| Guard | Where | Effect |
|---|---|---|
| `--route paper` | `cli.py` | `place_limit` goes to the paper ledger; the Gateway is still used for quotes, margin and contract resolution |
| `broker.transmits` | `orders.py` `submit()` | a non-live ticket on a transmitting broker is rejected, not filled |
| `mode != "live"` | `ib_bridge.py` `place_limit()` | the one function that reaches IBKR refuses anything not explicitly live |

`--route paper` still opens a real Gateway session, so previews carry the real
NBBO and IBKR's own `whatIf` margin. That is the point: a preview priced off a
simulated book proves nothing about a price band.

## Prerequisites

1. **The repo copy must be current.** `/home/spx/single-stock-investments` has
   no `.git`; merging to `main` does not reach it. Copy the hub package before
   starting anything.
2. **`secrets.env` needs exactly two values it does not have** (checked
   2026-08-24). Everything else the bridge reads is already there:
   `IBKR_HOST`, `IBKR_PORT`, `IBKR_ACCOUNT_ID`, `IBKR_ACCOUNT_ALIAS`,
   `PORTFOLIO_INGEST_TOKEN`.

   | Missing variable | Purpose |
   |---|---|
   | `PORTFOLIO_APPROVAL_SECRET` | HMAC key binding an approval to one exact contract. **≥32 chars or the CLI exits.** Never leaves the box; the browser only ever sees the fingerprint and the expiry. |
   | `PORTFOLIO_COMMAND_BASE_URL` | Origin the bridge polls for tickets — `https://single-stock-investments-2wt.pages.dev`, i.e. `PORTFOLIO_INGEST_URL` without its path. The client refuses anything that is not HTTPS or loopback. |

   Interlocks, all explicitly off for the first run:
   `PORTFOLIO_LIVE_ENABLED=0`, `PORTFOLIO_OPTIONS_ENABLED=0`,
   `PORTFOLIO_KILL_SWITCH=0`.

   **Do not rely on the port default.** `BridgeProfile.from_env()` falls back to
   `4002`, but this Gateway listens on **7496** (verified: a `java` process bound
   to `0.0.0.0:7496`). `IBKR_PORT=7496` is already in `secrets.env`, so the
   `EnvironmentFile=` line is what makes the bridge connect at all — a dry run
   without sourcing it will silently try the wrong port and look like a Gateway
   outage. `IBKR_BRIDGE_CLIENT_ID` is absent on purpose; the default is 91.

## Procedure

Off-hours only. Every step is reversible until the last one.

```bash
# 1. Refresh the copy (no .git on the box).
scp -r _system/trading/portfolio_hub spx-ny4-spx:/home/spx/single-stock-investments/_system/trading/

# 2. Generate the approval secret. It stays on the box; do not copy it anywhere.
ssh spx-ny4-spx 'umask 077; printf "PORTFOLIO_APPROVAL_SECRET=%s\n" "$(openssl rand -hex 32)" \
  >> /home/spx/.config/portfolio-hub/secrets.env'

# 3. Add the remaining variables, then confirm all six resolve.
ssh spx-ny4-spx 'set -a; . /home/spx/.config/portfolio-hub/secrets.env; set +a
  for v in PORTFOLIO_APPROVAL_SECRET PORTFOLIO_COMMAND_BASE_URL PORTFOLIO_INGEST_TOKEN \
           IBKR_ACCOUNT_ID IBKR_ACCOUNT_ALIAS PORTFOLIO_OPTIONS_ENABLED; do
    printf "%-28s %s\n" "$v" "$([ -n "${!v}" ] && echo set || echo MISSING)"; done'

# 4. Dry run BEFORE installing the unit. One tick, then exit. This proves the
#    connection, ownership recovery, the claim route and the paper route without
#    leaving anything running.
ssh spx-ny4-spx 'cd /home/spx/single-stock-investments && set -a
  . /home/spx/.config/portfolio-hub/secrets.env; set +a
  /home/spx/portfolio-hub-venv/bin/python -m _system.trading.portfolio_hub \
    --db /home/spx/portfolio-hub/portfolio.db order-bridge \
    --account "$IBKR_ACCOUNT_ALIAS" --route paper --once'
# Expect: {"route": "paper", "standing_gateway_connection": false, "budget": {...}}
# then {"desk_open": ..., "sessions_opened": N, "budget": {...}}.
#
# sessions_opened tells you what actually happened. On a quiet desk it is 0 and
# NO CONNECTION WAS MADE -- that is a successful dry run, not a failure to
# connect. It is only non-zero if a ticket was genuinely waiting.
#
# Any OrderOwnershipError means a MAGIS orderRef is held by a foreign client id.
# Stop and investigate -- do not install over it.

# 5. Install and start.
scp _system/trading/portfolio_hub/deploy/user/portfolio-hub-bridge.service \
  spx-ny4-spx:/home/spx/.config/systemd/user/
ssh spx-ny4-spx 'XDG_RUNTIME_DIR=/run/user/1000 systemctl --user daemon-reload
  XDG_RUNTIME_DIR=/run/user/1000 systemctl --user enable --now portfolio-hub-bridge.service
  XDG_RUNTIME_DIR=/run/user/1000 systemctl --user status portfolio-hub-bridge --no-pager | head -20'
```

## Verifying it is alive and harmless

```bash
ssh spx-ny4-spx 'XDG_RUNTIME_DIR=/run/user/1000 journalctl --user -u portfolio-hub-bridge -n 40 --no-pager'
```

Then drive one ticket from the dashboard: Portfolio → Drew → Orders. A stock
ticket should resolve a contract, reach `previewed` with a readable fingerprint
and a real bid/ask, accept an approval, and settle as an acknowledged **paper**
fill. An option ticket should be rejected with `options interlock off` — that is
the interlock working, not a bug.

Confirm nothing was transmitted:

```bash
ssh spx-ny4-spx 'sqlite3 /home/spx/portfolio-hub/portfolio.db \
  "SELECT mode, state, COUNT(*) FROM order_intents GROUP BY mode, state;
   SELECT gateway_session_id, COUNT(*) FROM order_intents WHERE order_id IS NOT NULL GROUP BY 1;"'
```

Every filled row should carry `gateway_session_id = paper-session`. Anything
else means the route is not what this document says it is — stop the unit.

## Backing it out

```bash
ssh spx-ny4-spx 'XDG_RUNTIME_DIR=/run/user/1000 systemctl --user disable --now portfolio-hub-bridge.service'
```

That releases client 91 and leaves the ledger intact. Working orders are
unaffected — the bridge never issues `reqGlobalCancel`, and on restart it
re-runs ownership recovery before accepting any command. **Never** back out by
touching `ibc.service` or the Gateway process (CLAUDE.md rule 6).

## Enabling options, later and separately

`PORTFOLIO_OPTIONS_ENABLED=1` is its own decision, made after the stock path has
run for a while. It does not need `PORTFOLIO_LIVE_ENABLED`; the two are
deliberately independent so enabling live stock trading cannot enable options by
side effect. Note what stays refused regardless:

* same-day expiry, unconditionally — 0DTE on this account belongs to SPX;
* `outside_rth` on an option;
* sell-to-open, via the `reduce_only` default, so this desk cannot go short an
  option;
* multi-leg — single conId only, no BAG, no ComboLegs.

## Going live, much later

`--route live` in the unit **and** `PORTFOLIO_LIVE_ENABLED=1`. Either alone does
nothing: the route decides which broker fills, the interlock decides whether a
`mode=live` ticket is accepted at all, and the browser cannot ask for `live`.
Raise `max_notional` from its $25,000 default only as a separate, argued change.
