# August 5, 2024 first-pass dataset

## Data availability

- Databento: `{"attempted": false, "files": [], "errors": {}, "reason": "DATABENTO_API_KEY missing"}`.
- ThetaData: `{"attempted": true, "files": [], "errors": {"SPY": {"type": "_MultiThreadedRendezvous", "permission_denied": true}}}`.
- Free fallback: Yahoo daily OHLCV plus official Cboe VIX daily history.

## Current resolution

This first pass is daily and supports event-window and sector comparisons. It
does not yet establish intraday forced-flow exhaustion. That requires entitled
intraday trades/quotes, futures, options, closing-auction, and preferably fund
flow or position data.

## Mechanical proxy

The prototype vol-target weight is `min(1, 10% / 20-day realized volatility)`.
The daily sell proxy is the decrease in this weight multiplied by dollar volume.
It is a sensitivity tool, not an estimate of actual industry AUM or orders.

## Next empirical tests

1. Estimate multiple volatility horizons and rebalance rules, including delayed
   and thresholded rebalancing.
2. Map the inferred equity sale to plausible AUM ranges instead of dollar volume.
3. Test whether proxy deceleration predicts forward returns outside August 2024.
4. Add futures, options, order-book liquidity, auction imbalance, ETF flows, and
   sector constituent breadth.
5. Freeze all parameters before evaluating a holdout event set.
