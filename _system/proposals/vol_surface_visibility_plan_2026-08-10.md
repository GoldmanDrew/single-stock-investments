# SPX vol-surface and vol-metrics visibility plan — 2026-08-10

**Status:** proposed (tier 1 is implementable immediately with sources already
in the family; tier 3 names the data that must be bought). Companion to the
risk-page healing shipped 2026-08-10 (P6 data-feed invariant, honest fallback
labeling, once-daily committed component snapshot).

## What we already have (verified inventory)

- **`options_stress` component** (built by `build_market_risk_components.py`
  from the private `spx-0dte` repo): `straddle_residual_z`, `skew_z`,
  `term_ratio_z`, `realized_vs_implied_z` — real SPX options-derived z-scores,
  computed every workflow run, published to D1. Until today only `skew_z` was
  rendered; the other two are now on the tile, but **no history view exists**.
- **VIX cash OHLC** (`spx-0dte:data/calendar/vix_daily.csv`) and an intraday
  VIX print.
- **Yahoo chart API** plumbing (`fetch_yahoo_history`) already used by the
  criticality/technical builders — serves `^VIX`, `^VIX9D`, `^VIX3M`,
  `^VIX6M`, `^VVIX`, `^SKEW`, `^VIX1D` daily closes keylessly.
- **FRED `VIXCLS`** already consumed by the Darwin regime classifier.
- **Realized vol machinery**: 20d RV per LETF underlying and per holding
  (`rv_20d`, `vol_acceleration`) in the technical builder.
- **Databento**: minute-bar equities feed (local token). No options (OPRA)
  subscription.
- The theme-panel config already computes a VIX3M−VIX slope for world-model
  panels — the calculation exists, just not on the risk page.

## Tier 1 — z-score history panel, no new data (build now)

**`build_vol_metrics.py`** (data-pipeline lane, daily after the technical
refresh): append one row per trading day to
`dashboard/data/vol_metrics_history.jsonl` (committed; registered as a P6
feed) with:

| Metric | Source | Z-score basis |
|---|---|---|
| VIX, VIX9D, VIX3M, VIX6M, VIX1D | Yahoo (FRED VIXCLS cross-check) | 1y and 5y trailing |
| Term slope 9D/VIX, VIX/3M, 3M/6M | derived | 1y trailing |
| VVIX, VVIX/VIX ratio | Yahoo | 1y trailing |
| SKEW index | Yahoo | 1y trailing |
| SPX 20d realized vol; VIX − RV20 (implied-realized spread) | Yahoo SPX closes | 1y trailing |
| `straddle_residual_z`, `skew_z`, `term_ratio_z`, `realized_vs_implied_z` | spx-0dte via the components snapshot | already z-scores; store raw + percentile |

Backfill: Yahoo serves 5y+ history for every index above, so the Yahoo-derived
columns get **full z-score history on day one**; the spx-0dte columns
accumulate from now (or backfill from that repo's archive if it retains daily
outputs — worth checking, it likely does).

**Visualization** (new section on `#/risk`, `criticality-viz.js`): a
**z-score heatmap strip** — metrics as rows, last ~120 sessions as columns,
cells colored by |z| with sign (the "compare the z-score over time in an easy
to visualize way" ask); a term-structure chart (current curve vs 1m ago vs 1y
median, inversion shaded); and a compact "vol regime" tile (VIX percentile,
slope state, VVIX/VIX, IV−RV) feeding the existing component stack. Load the
`dataviz` conventions before building the charts.

## Tier 2 — coarse SPX surface snapshots, free source (build next)

CBOE's delayed-quotes JSON (`cdn.cboe.com/api/global/delayed_quotes/options/
_SPX.json`, keyless, 15-min delayed) serves the full SPX chain with IVs and
greeks. A daily post-close snapshot job derives: ATM IV by expiry (1w/1m/3m/
6m), 25Δ risk reversal and butterfly per tenor, put-skew slope, and a
**naive dealer-gamma proxy** (Σ gamma × OI × sign-convention) that can honestly
fill the `dealer_gamma` tile as an *estimate* (labeled as such — the tile is
currently hard-coded `unavailable`). Snapshots accumulate in
`dashboard/data/spx_surface_history.jsonl`; surface z-scores become meaningful
after ~60 sessions and get added to the heatmap rows.

Caveats to encode as guards: delayed OI is start-of-day; the gamma proxy's
dealer-sign assumption is a convention, not an observation — label both on the
tile.

## Tier 3 — what needs additional data (your call)

1. **Historical full surface** (immediate deep z-history instead of
   accumulating): ORATS (~$99–200/mo API with 2007+ history), CBOE DataShop
   (one-off historical purchase), or OptionMetrics (institutional). One-off
   DataShop history + tier-2 daily accumulation is the cheapest credible path.
2. **Real dealer positioning** (vs the tier-2 proxy): SqueezeMetrics/SpotGamma
   subscriptions, or build from OPRA via a **Databento options add-on** (you
   already have the Databento relationship; this also unblocks the local flow
   monitor's alert journal properly).
3. **MOVE index** (rates vol — relevant given the criticality monitor already
   tracks TLT/HYG/LQD): ICE-licensed; Yahoo serves `^MOVE` delayed and is the
   pragmatic free option.
4. **Vol-target/CTA flow estimates** (`observed_vol_target_flows` tile,
   hard-coded unavailable): vendor research (DB, GS, Nomura estimates) has no
   free equivalent; either buy or retire the tile honestly.

## Self-healing hooks

Every artifact above registers in `graph_sources.json` `data_feeds` (P6) with
its healer command, so a silent stall becomes a hard invariant violation
naming the fix. The spx-0dte-derived columns inherit the existing HMAC
publish path; Yahoo/CBOE fetchers follow the technical-builder pattern
(preserve-prior-row + `quality_state='stale'` on fetch failure, never fail
the lane on a source hiccup).
