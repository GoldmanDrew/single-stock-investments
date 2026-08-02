# Market-risk component pipeline

The batch component publisher runs in GitHub Actions. It executes every 30 minutes during U.S. weekdays from 08:07 through 18:07 America/New_York, with an offset end-of-day snapshot at approximately 18:37. The schedule is deliberately offset from the top of the hour to reduce scheduled-run contention.

Workflow: `.github/workflows/market-risk-components.yml`

The workflow checks out:

- `single-stock-investments` for the builder and SSI breadth snapshot;
- `GoldmanDrew/etf-dashboard` for leveraged-ETF flows and holdings;
- `GoldmanDrew/ls-algo` for volatility and borrow context;
- `magis-capital-partners/spx-0dte` for sanitized options and VIX features.

It publishes a signed snapshot to the Cloudflare market-risk ingest Worker and verifies that the generated artifact contains the expected component coverage. Required repository secrets are `MARKET_RISK_INGEST_TOKEN` and `LS_ALGO_TOKEN`; the ingest URL is a non-secret workflow variable.

The Databento flow/liquidity monitor is intentionally separate. It is a persistent market-hours stream and remains on the Windows worker (`Magis Market Risk Databento Monitor`) because a scheduled GitHub-hosted job is not a durable streaming runtime.

The legacy Windows batch task (`Magis Market Risk Component Pipeline`) was disabled after the first successful GitHub Actions publish. To run a local fallback manually:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\_system\scripts\run_market_risk_component_pipeline.ps1
```

Do not run the local batch publisher and GitHub Actions publisher simultaneously; both write the same snapshot lane.
