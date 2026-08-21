# Ubuntu host runbook — IB Gateway and the order bridge

Everything that can transmit an order runs on this one machine. The dashboard is
a client of it, never the other way round.

```
                    Cloudflare (public, Access-authenticated)
                 ┌────────────────────────────────────────┐
   browser ────► │  order-intents  (request, approve)     │ ◄── nothing transmits here
                 │  D1: portfolio_order_requests          │
                 └──────────────▲─────────────────────────┘
                                │ the hub polls OUT, signed HMAC
                                │ (the edge never calls in)
        ┌───────────────────────┴────────────────────────┐
        │                  Ubuntu host                   │
        │  portfolio-hub-bridge     client 91  transmits │
        │  portfolio-hub-collector  client 81  read-only │
        │  SQLite WAL ledger — system of record          │
        │  IB Gateway (IBC, headless under Xvfb)         │
        └───────────────────────┬────────────────────────┘
                                ▼
                              IBKR
```

## Units

| Unit | Client ID | Transmits | Purpose | Status |
|---|---:|---|---|---|
| `ibgateway.service` | — | — | IB Gateway under IBC, headless | host-provided |
| `portfolio-hub-collector.service` | 81 | No | Snapshots positions, values, open orders | existing |
| `portfolio-hub-publisher.timer` | — | — | Pushes snapshot + projection to the edge | existing |
| `portfolio-hub-health.timer` | — | — | Freshness and outbox checks | existing |
| `portfolio-hub-backup.timer` | — | — | SQLite online backup | existing |
| **`portfolio-hub-bridge.service`** | **91** | **Yes** | **The only transmitter; runs the order command loop** | **new** |

Client IDs are fixed by `CLIENT_ID_REGISTRY.md` and must be unique across every
process touching this Gateway, including the SPX and LS producers.

## Install

```bash
sudo cp _system/trading/portfolio_hub/deploy/portfolio-hub-bridge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now portfolio-hub-bridge
```

## Secrets

Never in source. Add to the existing `/etc/portfolio-hub/portfolio-hub.env`
(mode `0600`, owner `portfolio-hub`):

```
IBKR_BRIDGE_CLIENT_ID=91
PORTFOLIO_APPROVAL_SECRET=<32+ chars, this host only>
PORTFOLIO_COMMAND_BASE_URL=https://<dashboard host>
# Live stays off until the CLIENT_ID_REGISTRY.md gate is satisfied in full.
PORTFOLIO_LIVE_ENABLED=0
PORTFOLIO_KILL_SWITCH=0
```

`PORTFOLIO_APPROVAL_SECRET` must exist nowhere else. It is what makes an
approval unforgeable by anything running at the edge — a browser can record that
a human clicked Approve, but only this host can mint the token that lets an
order transmit.

## Market data

The bridge fails closed without a two-sided quote, so every venue you intend to
trade needs a market-data subscription on this account. Tokyo is the case that
already bit us: without TSE data, JPY positions return `marketPrice = 0`, no FX
rate can be derived, and those rows publish as `fx_source: "fx_unavailable"` —
shown as "not converted" and sorted last, never silently treated as USD.

## Kill switch

```bash
sudo sed -i 's/^PORTFOLIO_KILL_SWITCH=.*/PORTFOLIO_KILL_SWITCH=1/' /etc/portfolio-hub/portfolio-hub.env
sudo systemctl restart portfolio-hub-bridge
```

This rejects new intents. It deliberately does **not** cancel working orders:
`reqGlobalCancel` is prohibited and has no call site, and orders the hub does not
own are never touched. Cancel hub orders individually from the dashboard; cancel
foreign or manual orders in TWS.

## Restart behaviour

The bridge runs the `CLIENT_ID_REGISTRY.md` recovery invariant on every start:
read open, completed and executed orders, classify each as hub / foreign /
legacy, and refuse commands if any `MAGIS|` orderRef is owned by another client
ID. A bridge that cannot prove ownership does not accept work — it does not
guess, because guessing is how a position gets doubled.

IB Gateway restarts daily on IBKR's schedule; `Restart=always` reconnects. Do not
paper over a reconnect loop by widening the restart interval — read the Gateway
log first.

## Podcast Whisper backfill (background tenant)

The same host runs the transcript backfill, because it is the only machine that
is already up for days at a time. It is a background tenant and is configured to
lose every CPU contest with the bridge — an order preview has a 10-second quote
budget and must never queue behind a transcription.

```bash
sudo cp _system/trading/portfolio_hub/deploy/podcast-whisper-backfill.service /etc/systemd/system/
sudo systemctl daemon-reload
python _system/scripts/whisper_backfill_daemon.py --status   # look before starting
sudo systemctl start podcast-whisper-backfill                # runs until drained
```

Why this is not a CI job: the backlog is ~1,515 episodes against a weekly lane
that drains 20, so it never converges — and raising the CI batch does not work,
because a job that overruns its wall clock lands nothing at all. Run
32280009523 lost two hours exactly that way.

It is built to be killed. State is checkpointed per item in the vault's
`whisper_backlog.json`, so a restart loses at most the episode in flight.
Results are pushed to the vault every 30 minutes — an unpushed transcript is an
unbacked-up one. Items failing four times are parked rather than retried, so one
dead audio URL cannot eat the budget.

```bash
sudo systemctl stop podcast-whisper-backfill    # safe at any moment
python _system/scripts/whisper_backfill_daemon.py --hours 8   # bounded run instead
```

Expect days, not hours: faster-whisper `base` int8 on CPU runs at a few times
realtime, and these are long episodes. `--status` is the honest progress meter.

## Verifying the boundary before enabling live

```bash
# 1. Unauthenticated reads must 401.
curl -sS -o /dev/null -w '%{http_code}\n' https://<host>/api/v2/portfolio/book
curl -sS -o /dev/null -w '%{http_code}\n' https://<host>/api/v2/portfolio/order-intents

# 2. The edge exposes no transmit path. Both must be 404/405, never 200.
curl -sS -o /dev/null -w '%{http_code}\n' -X POST https://<host>/api/v2/portfolio/orders

# 3. The bridge classifies every working order.
sudo journalctl -u portfolio-hub-bridge -n 50 | grep -i 'recovered\|ownership'
```

Then work the `CLIENT_ID_REGISTRY.md` live gate in order: producers stamp
positive orderRefs, every working order classifies, the restart /
cancel-fill-race / partial-fill / uncertain-send drills pass, watchdog and
backups are active, and only then a capped allowlisted canary.
