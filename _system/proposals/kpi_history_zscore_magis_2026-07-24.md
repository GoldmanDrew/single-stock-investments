# Magis KPI history, time series, and z-scores (2026-07-24)

**Status:** implemented  
**Scope:** World Model / Magis morning strip (Insights → Tickers). Context only — does not set capital stance.

## Problem

Passing / failing KPI tables show a single **Actual** vs a fixed **Gate**. Operators cannot see whether the level is normal, elevated, or depressed versus the series’ own history.

## Design principles

1. **Reuse dense history first.** `theme:*` KPIs already have append-only CSVs under `_system/reference/market-data/themes/`. Prefer those over inventing a second daily store.
2. **Archive sparse KPIs.** `valuation:*` and `manual` actuals get an append-only ledger series file written on each snapshot (dedupe by `as_of` date).
3. **Z-score is descriptive, not a gate.** Pass/fail stays on the fixed expected op/value. Z never alone marks strip `broken`.
4. **Share series across tickers.** One `theme:vix_level` series serves every ledger that binds it; strip rows carry `series_key` + stats, not a duplicated copy of the full series.
5. **House valuation boundary unchanged.** History/z are Magis claim context (orientation), not Power Zone / contract / IC inputs.

## Architecture

```
theme CSV  ──┐
             ├─► kpi_history_stats.py ──► annotate strip rows + history_series
ledger CSV ──┘         │
                       ├─► dashboard/data/world_model.json (schema 2.2)
                       └─► _system/reference/kpi/series/*.csv (sparse archive)
```

| Layer | Path | Role |
|-------|------|------|
| Theme history | `market-data/themes/{id}.csv` | Dense market series |
| Ledger archive | `kpi/series/{TICKER}__{kpi_id}.csv` | Sparse filing/manual actuals |
| Stats helper | `_system/scripts/kpi_history_stats.py` | Load points, mean/σ/z, sparkline |
| Hot strip | `dashboard/data/world_model.json` | Rows + shared `history_series` |
| UI | `dashboard/insights-viz.js` | Z column, sparkline, expand chart |

## Stats contract (per strip row)

```json
"history": {
  "series_key": "theme:vix_level",
  "z_score": -0.41,
  "mean": 18.2,
  "stdev": 4.1,
  "n": 252,
  "window": "trailing_252",
  "percentile": 38.1,
  "as_of": "2026-07-23",
  "source_kind": "theme",
  "status": "ok"
}
```

- **Window:** trailing up to 252 observations (theme); all available for ledger archive (min 5).
- **z:** `(latest − mean) / stdev` on the window (latest included). `null` if `n` below min or `stdev == 0`.
- **percentile:** empirical rank of latest in window (0–100).
- **status:** `ok` | `insufficient_history` | `no_series`.

Shared payload on strip:

```json
"history_series": {
  "theme:vix_level": {
    "label": "VIX index level",
    "unit": "index",
    "points": [{"d": "2025-07-24", "v": 16.2}, "... last ≤252"],
    "stats": { "mean": ..., "stdev": ..., "n": ..., "z_score": ..., "percentile": ... }
  }
}
```

## UI

| Surface | Behavior |
|---------|----------|
| Passing / alert tables | Columns: … Actual · **Spark** · **Z** · Gate · Class |
| Z badge | `|z| < 1` muted · `1–2` warn · `≥2` strong; `n/a` if insufficient |
| Click Actual / Spark / Z | Expand row panel: SVG time series, mean ±1σ band, latest marker, stats line |
| Cap | Pass table still capped at 80 rows for strip; history available on all rows in JSON |

## Cadence

Weekly `world-model-weekly` already runs `build_world_model_snapshot.py`. Annotation is free there. Theme depth grows via `fetch_theme_panel.py`; ledger archive depth grows each snapshot.

## Out of scope (later)

- Changing Magis gates based on z
- Intra-day tick history
- Cross-sectional peer z (fundamentals `kpi_trends` already covers YoY regime elsewhere)
- Promoting z into `valuation.json` / human decision

## Verification

```bash
python _system/scripts/test_world_model.py
python _system/scripts/build_world_model_snapshot.py --skip-resolve
```

Expect strip rows with `history.z_score` for theme KPIs; Magis UI shows Z + expandable chart.
