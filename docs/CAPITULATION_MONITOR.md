# Capitulation monitor

The capitulation monitor is a timing and risk overlay. It cannot change valuation
readiness, clear an evidence blocker, change stance, or modify intrinsic value.

## What was reused from the ETF dashboard

The stock dashboard reuses four price-path ideas that are already operational in
the ETF dashboard:

- historical percentiles beside absolute measurements;
- volatility concentration ratio (VCR), which separates a one-day jump from a
  persistent high-volatility path;
- daily-versus-weekly volatility shape (`trend_ratio_20d`);
- explicit data grades, coverage, timestamps, and last-good-data preservation.

ETF-specific borrow, leverage, rebalance-flow, and decay logic is intentionally
not imported.

## Scores

Every eligible security receives four scores from 0 to 100:

- **Pressure** — severity and persistence of the decline.
- **Panic** — whether price, volume/range, volatility, and relative weakness are
  becoming climactic.
- **Exhaustion** — whether the latest session shows stabilization after stress.
- **Confidence** — coverage of the independent signal families.

Panic is composed from four families:

1. price dislocation;
2. selling climax;
3. volatility stress;
4. relative and path stress.

The model uses up to three years of trailing observations when ranking the latest
reading. Family aggregation prevents correlated price measures from masquerading
as independent confirmation.

## State policy

States progress from `normal` to `stress_building`, `panic`,
`capitulation_candidate`, `exhaustion_emerging`, and
`confirmed_exhaustion`.

A severe decline is never sufficient for confirmation. A candidate needs broad
independent extremes plus a selling climax. Confirmation additionally requires
multiple stabilization checks, including a positive session, an upper-half
close, a reclaim of the prior high, or cooling volume.

## Market context

The dashboard calculates a separate SPY-based US market fear reading using the
same transparent price-tape model. CNN Fear & Greed is linked as an attributed
external reference and is never blended into stock scores.

## Automation

The weekday technical job:

1. fetches free adjusted OHLCV, using Yahoo first and Stooq as fallback;
2. preserves a last-good snapshot when both sources fail;
3. writes compact and full dashboard artifacts;
4. exports OHLCV, capitulation snapshots, and market context to D1 seed SQL;
5. publishes through the existing Cloudflare Pages deployment flow.

No backtest or return-optimization stage is part of this implementation.
