# Magis sleeve desk

Local TWS/Gateway order desk for Drew and Michael. The hosted dashboard cannot talk to IB (`127.0.0.1` is blocked from HTTPS). This process runs on the machine that is logged into Interactive Brokers.

## One-session rule

The Magis account `U805366` already has a live Gateway on the NY4 VPS (ls-algo client 41, SPX 0DTE client 17). IB allows one market-data session.

**If NY4 is logged in, do not start local TWS.** Close the NY4 Gateway (or wait until it is down) before opening this desk. Starting local TWS will kick the live session.

## Install

```bash
pip install -r _system/trading/sleeves/requirements.txt
```

## Start

1. Log into TWS or IB Gateway on this machine (API port 7496 live / 7497 paper, trusted IP `127.0.0.1`).
2. From the repo root:

```bash
python -m _system.trading.sleeves.desk
```

3. Open http://127.0.0.1:8788

Dry-run is on by default (`execution.dry_run: true`, `allow_live: false` in `config.yaml`). Approve records a simulated fill and will HMAC-post to D1 if `SLEEVE_INGEST_URL` and `SLEEVE_INGEST_TOKEN` are set.

## Operators

| Operator | Client ID | orderRef | Capital |
|----------|-----------|----------|---------|
| Drew | 71 | DREW_SLEEVE | $100k + $100k extra margin |
| Michael | 72 | MICHAEL_SLEEVE | Residual NAV from IB sync |

## Sync Michael's book

Same IB pin as ls-algo and SPX 0DTE: host `127.0.0.1`, live port `7496`, account `U805366`, read-only client id **73**. Positions are requested with `reqPositionsMulti(account)` so sibling accounts stay quiet.

```bash
python -m _system.trading.sleeves.sync_ib
```

If NY4 is still logged in, TWS on this machine cannot connect. Pass yesterday's Flex file instead:

```bash
python -m _system.trading.sleeves.sync_ib --flex path/to/flex_positions.xml
```

The classifier keeps residual stocks and blacklist families in Michael, drops SPX/XSP options and systematic LETFs, and leaves Drew empty unless a row is tagged `DREW_SLEEVE`. It writes `dashboard/data/sleeves_*.json` and HMAC-posts both books when `SLEEVE_INGEST_TOKEN` is set.

Override host/port/account with `IBKR_HOST`, `IBKR_PORT`, `IBKR_ACCOUNT` if needed.

## Kill switch

Create `_system/trading/sleeves/KILL` (any contents). Every propose/approve fails until the file is removed.

## Live unlock

Only after a dry-run fill shows on the Drew tab: set `execution.allow_live: true` and `dry_run: false`, send a tiny Drew lot, confirm `orderRef=DREW_SLEEVE` on `U805366`, then restore dry-run.
