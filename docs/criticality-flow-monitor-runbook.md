# Criticality & Forced-Flow Monitor Runbook

## What is live

- Daily LPPLS ensemble snapshots for major U.S./global risk proxies, rates/credit proxies, and 11 sector ETFs.
- Static fallback at `dashboard/data/criticality_summary.json`.
- D1 storage for criticality and intraday forced-flow snapshots.
- Read APIs for latest, sector, and historical snapshots.
- Authenticated snapshot ingestion.
- Dashboard three-stage rail and sector heatmap.
- Optional Databento live minute-bar publisher.

All outputs are research-only and have no trading or exposure authority.

## Daily refresh

Install dependencies:

```powershell
python -m pip install -r _system/scripts/requirements-criticality.txt
```

Build all market and sector snapshots:

```powershell
python _system/scripts/build_criticality_signals.py --workers 4
```

Build a test subset:

```powershell
python _system/scripts/build_criticality_signals.py --symbols SPY,QQQ,XLK
```

The weekday technical workflow runs the full build after the existing
fear/capitulation refresh.

## D1 and API

Migration:

`dashboard/cloudflare/migrations/0005_criticality_monitor.sql`

Routes:

- `GET /api/v1/market-risk/latest`
- `GET /api/v1/market-risk/sectors`
- `GET /api/v1/market-risk/history?symbol=SPY&limit=90`
- `GET /api/v1/market-risk/alerts?open=false&limit=100`
- `GET /api/v1/market-risk/health`
- `POST /api/v1/market-risk/ingest`

Configure a Cloudflare Pages secret named `MARKET_RISK_INGEST_TOKEN`. Use at
least 24 random characters. Do not commit it.

The token is an HMAC signing secret, not a browser or Databento credential. The
publisher signs `timestamp + nonce + exact request body`; it does not send the
token itself. Cloudflare rejects signatures more than five minutes old and
records each nonce so a captured request cannot be replayed. Public dashboard
read APIs do not receive or require this secret. The deploy workflow synchronizes
the GitHub Actions secret of the same name into Cloudflare Pages.

The normal D1 seed exporter includes the current static criticality snapshot:

```powershell
python _system/scripts/export_dashboard_d1_seed.py
```

## Databento intraday monitor

The live publisher follows Databento's official `Live` client and `ohlcv-1m`
subscription model. It replays available intraday bars on startup, retains a
rolling 240-minute buffer, calculates flow/exhaustion snapshots, and publishes
at most once per minute.

Required environment:

```text
DATABENTO_API_KEY
MARKET_RISK_INGEST_URL
MARKET_RISK_INGEST_TOKEN
```

Example URL:

```text
https://<dashboard-host>/api/v1/market-risk/ingest
```

Start:

```powershell
pwsh -File _system/scripts/run_databento_flow_monitor.ps1
```

On the primary Windows research host, the Databento key is stored outside the
repository as a DPAPI-encrypted, current-user-only credential. The PowerShell
launcher decrypts it into the child process environment and clears it afterward.
The encrypted file cannot be decrypted by another Windows user or on another
machine.

The separate market-risk signing secret is protected the same way at
`C:\Users\drewg\.magis-market-risk\market-risk-ingest-token.dpapi`.

Optional controls:

```powershell
python _system/scripts/run_databento_flow_monitor.py `
  --dataset EQUS.MINI `
  --symbols SPY,QQQ,IWM,XLK,XLF `
  --publish-seconds 60
```

If the selected Databento dataset or account lacks live US-equity entitlement,
the publisher fails loudly. The dashboard retains the EOD fallback and labels it
as EOD; it does not silently claim that delayed data is live.

## Model interpretation

### Criticality

The LPPLS score is the fraction and concentration of qualified nested-window
fits. The critical-time range is an instability region, not a promised crash or
reversal date.

### Mechanical pressure

The intraday pressure score combines:

- standardized five-minute downside return,
- realized-volatility acceleration,
- downside variance and negative-minute concentration,
- volume and price-range shocks.

### Exhaustion

The exhaustion score requires several of:

- a positive interval,
- an upper-half close,
- realized-volatility deceleration,
- selling deceleration,
- volume cooling.

The volatility-targeting output is a range across 8%, 10%, and 12% target-vol
scenarios. It is an estimated exposure-change proxy, not observed fund flow.

## Validation

```powershell
python -m unittest `
  _system.scripts.tests.test_criticality_lppls `
  _system.scripts.tests.test_flow_stress `
  _system.scripts.tests.test_dashboard_d1_export -v
```

Before using alerts operationally:

1. Run in shadow mode for at least four to eight weeks.
2. Preserve every snapshot and source-quality state.
3. Compare against the existing capitulation model and simple VIX/realized-vol
   thresholds.
4. Review missed events, time in alarm, and false-alarm duration.
5. Do not translate the signal into exposure changes without a separately
   approved point-in-time backtest and policy.

## Source references

- Databento live client:
  https://databento.com/docs/api-reference-live/basics/encodings
- Databento equity OHLCV example:
  https://databento.com/docs/examples/equities/equities-introduction
- Stable LPPLS calibration:
  https://arxiv.org/abs/1108.0099
- LPPLS multiscale confidence indicator:
  https://arxiv.org/abs/1804.06261
