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

## Plain-language setup

The primary ticker read is expressed in investment language instead of
z-scores:

- **Direction** combines price versus the 50- and 200-day averages with 60-day
  performance versus the market benchmark.
- **Pressure** uses RSI plus the panic/exhaustion model to distinguish oversold
  from an actual stabilization signal.
- **Participation** uses Chaikin Money Flow, relative volume, and ATR to show
  whether volume confirms accumulation or distribution.

Trend and stretch z-scores remain in the technical payload for research and
model diagnostics, but they are no longer primary interface elements. Trend z
measures the stock's multi-horizon and benchmark-relative return versus its own
history. Stretch z measures distance from the 50- and 200-day averages versus
the stock's own history.

## Float and short interest

The free market-structure refresh collects float shares, shares outstanding,
reported shares short, short interest as a percentage of float, change from the
prior report, and days to cover. Each distinct report date is retained so the
dashboard and D1 build a history without overwriting prior observations.

Reported short interest is deliberately kept separate from FINRA daily
short-sale volume. Short interest is a position snapshot reported twice per
month; daily short-sale volume is transaction flow and must not be labeled as
short interest.

The integrated decision picture links modeled valuation, business/KPI momentum,
the stock's technical setup, and internal SPY market context. It can identify
agreement or conflict, but technical or macro inputs cannot clear evidence gates
or change valuation authority.

## Automation

The weekday technical job:

1. fetches free float and reported short-interest data;
2. fetches free adjusted OHLCV, using Yahoo first and Stooq as fallback;
3. preserves a last-good snapshot when sources fail;
4. writes compact and full dashboard artifacts;
5. exports OHLCV, capitulation, market-structure, and market-context snapshots
   to D1 seed SQL;
6. publishes through the existing Cloudflare Pages deployment flow.

No backtest or return-optimization stage is part of this implementation.
