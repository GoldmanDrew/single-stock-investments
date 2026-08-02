# Systematic Flows and Volatility Research

This project tests whether the exhaustion of forced, volatility-driven selling can
identify the end of equity drawdowns at the market and sector levels. The first
case study is the August 5, 2024 Japan/carry/VIX shock.

## Research question

The claim is not simply that a high VIX marks a bottom. The testable mechanism is:

1. Realized volatility rises and mechanical risk-control strategies reduce exposure.
2. The induced selling pressure becomes observable in returns, volume, liquidity,
   correlation, and volatility.
3. Selling pressure eventually peaks and decelerates.
4. Assets with the greatest mechanically induced dislocation subsequently rebound,
   conditional on fundamentals and liquidity normalizing.

The VIX level is treated as one noisy state variable. BIS evidence on August 5
shows that the pre-open VIX print near 66 was affected by illiquid option quotes,
so the research design requires confirmation from prices, spreads, volume, breadth,
and cross-asset behavior.

## Local layout

- `papers/`: downloaded external papers; each PDF is validated before cataloging.
- `internal_ls_algo/`: research-only snapshot copied from `ls-algo`; the operational
  repository is not modified.
- `catalogs/`: paper and material provenance.
- `config/`: symbols, event dates, and data-source settings. No credentials are stored.
- `scripts/`: access checks, collection, and analysis.
- `data/raw/`: immutable source extracts.
- `data/processed/`: normalized panels.
- `outputs/`: event tables and diagnostics.

## Run

From the repository root:

```powershell
python _system/research/systematic_flows_volatility/scripts/check_data_access.py
python _system/research/systematic_flows_volatility/scripts/collect_and_analyze_event.py
```

The collector uses:

1. Databento intraday data when `DATABENTO_API_KEY` is available.
2. ThetaData intraday data when `THETADATA_API_KEY` and the required entitlement
   are available.
3. Yahoo Finance daily OHLCV and the official Cboe VIX history as reproducible
   free fallbacks.

## Interpretation guardrails

- A high volatility level is not, by itself, evidence that forced selling has ended.
- A flow proxy is not direct holdings data. Validate it against known rebalancing
  schedules, closing-volume concentration, futures activity, and fund flows.
- Any threshold is trained outside the event being evaluated.
- Market and sector signals are evaluated both in event time and across a broader
  sample of volatility shocks to avoid a one-vignette result.
- Transaction costs, execution time, beta-estimation error, and look-ahead bias are
  explicit parts of the final backtest.

## Google Drive

The organized library is under:

`Research Sources/Systematic Flows and Volatility`

Folder URL:
https://drive.google.com/drive/folders/1D_KxJNIE_cTg8vih3_Tcik8fxu_mzyH4

