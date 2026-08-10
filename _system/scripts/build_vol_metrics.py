#!/usr/bin/env python3
"""Build the volatility-metrics history and latest snapshot (tier 1 of the
vol-surface visibility plan, `_system/proposals/vol_surface_visibility_plan_2026-08-10.md`).

Sources
-------
Yahoo chart v8 daily closes, keyless, one request per index:
``^VIX ^VIX9D ^VIX3M ^VIX6M ^VIX1D ^VVIX ^SKEW ^MOVE`` plus ``^GSPC`` for
realized vol. ``^VIX1D`` only exists from 2023-04-24 (index launch), so its
z-scores stay null before then; that never affects any other metric because
every metric is z-scored over its **own** observations.

Yahoo publishes ``^SKEW`` and ``^MOVE`` on a lag (observed 2026-08-10: SKEW one
session behind, MOVE ~17 sessions behind), so the latest row's ``skew`` /
``move`` are legitimately null. Nothing is forward filled: each metric in
``vol_metrics_latest.json`` carries ``value`` (strictly as of ``as_of``, may be
null) alongside ``last_value`` / ``last_value_date``, and
``coverage.metrics_lagging`` names every metric whose last observation predates
``as_of`` with how many sessions behind it is.

SPX 0DTE options-derived z-scores (``straddle_residual_z``, ``skew_z``,
``term_ratio_z``, ``realized_vs_implied_z``) are carried from the
``options_stress`` component of ``dashboard/data/market_risk_components.json``
onto the **latest row only** -- they are already z-scores and are stored raw,
never re-z-scored, never invented (absent source -> nulls).

Conventions
-----------
Term structure is expressed as **near / far**, so a number **below 1.0 is
contango** (the normal upward-sloping vol curve) and **above 1.0 is
backwardation** (stress):

* ``slope_9d_vix  = VIX9D / VIX``   (9-day vs 30-day)
* ``slope_vix_3m  = VIX / VIX3M``   (30-day vs 3-month) -- the regime anchor
* ``slope_3m_6m   = VIX3M / VIX6M`` (3-month vs 6-month)

``regime.term_state`` is read off ``slope_vix_3m`` with a +/- 2% dead band:
below 0.98 contango, above 1.02 backwardation, otherwise flat.

``spx_rv20`` is the 20-trading-day close-to-close realized vol of ^GSPC from
log returns, annualized by sqrt(252) and expressed in vol points (x100) so it
is directly comparable to VIX. ``iv_rv_spread = VIX - spx_rv20``.

Z-scores
--------
Every metric carries ``_z1y`` (252-session trailing window), ``_z5y`` (1260)
and ``_pct1y`` (trailing percentile rank 0-100 on the 252 window). Windows are
**strictly trailing**: a row's statistics use only observations up to and
including that row, so appending later rows can never change an earlier row's
z-score. The window includes the current observation; the standard deviation is
the sample (n-1) stdev, matching `build_technical_signals.py`. A window with
fewer than 30 observations, or a zero standard deviation, emits **null** -- never
a fabricated 0.

Failure handling
----------------
A per-symbol fetch failure never fails the run: that symbol's column is rebuilt
from the previously committed history file, the affected rows are stamped
``quality_state='stale'`` with ``fetch_status`` and ``stale_metrics``, exactly
like `build_criticality_signals.py` preserves a prior row.

Outputs
-------
* ``dashboard/data/vol_metrics_history.jsonl`` -- one object per trading date,
  ascending, full backfill, rewritten deterministically from source each run.
* ``dashboard/data/vol_metrics_latest.json`` -- current levels, z-scores, the
  vol-regime tile and the spx-0dte block.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_technical_signals import _request  # noqa: E402

SCHEMA_VERSION = 1
MODEL_VERSION = "vol-metrics-v1"
# Recent-window size for interior-gap detection (see build_latest).
GAP_WINDOW_SESSIONS = 25
DEFAULT_OUTPUT_DIR = ROOT / "dashboard" / "data"
HISTORY_NAME = "vol_metrics_history.jsonl"
LATEST_NAME = "vol_metrics_latest.json"
COMPONENTS_NAME = "market_risk_components.json"

LOOKBACK_DAYS = 365 * 6 + 30
TRADING_DAYS = 252
WINDOW_1Y = 252
WINDOW_5Y = 1260
MIN_OBSERVATIONS = 30
RV_WINDOW = 20
TERM_DEAD_BAND = 0.02

# metric key -> Yahoo symbol. ``spx_close`` is an input for realized vol and is
# carried on each row for reproducibility; it is not z-scored.
LEVEL_SYMBOLS = {
    "vix": "^VIX",
    "vix9d": "^VIX9D",
    "vix3m": "^VIX3M",
    "vix6m": "^VIX6M",
    "vix1d": "^VIX1D",
    "vvix": "^VVIX",
    "skew": "^SKEW",
    "move": "^MOVE",
}
SPX_KEY = "spx_close"
SPX_SYMBOL = "^GSPC"
FETCH_KEYS = list(LEVEL_SYMBOLS) + [SPX_KEY]

DERIVED_KEYS = [
    "slope_9d_vix",
    "slope_vix_3m",
    "slope_3m_6m",
    "vvix_vix_ratio",
    "spx_rv20",
    "iv_rv_spread",
]
METRIC_KEYS = list(LEVEL_SYMBOLS) + DERIVED_KEYS

SPX_0DTE_KEYS = [
    "straddle_residual_z",
    "skew_z",
    "term_ratio_z",
    "realized_vs_implied_z",
]


# --------------------------------------------------------------------------
# small numeric helpers
# --------------------------------------------------------------------------
def _finite(value):
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _round(value, digits: int = 6):
    value = _finite(value)
    return None if value is None else round(value, digits)


def _ratio(numerator, denominator):
    top = _finite(numerator)
    bottom = _finite(denominator)
    if top is None or bottom is None or bottom == 0:
        return None
    return top / bottom


def trailing_zscore(window: list, min_observations: int = MIN_OBSERVATIONS):
    """Z-score of the last value of ``window`` against the whole window.

    ``window`` may contain None. Returns None when fewer than
    ``min_observations`` finite values are present, when the last value is
    missing, or when the sample standard deviation is zero.
    """
    if not window:
        return None
    current = _finite(window[-1])
    if current is None:
        return None
    clean = [value for value in (_finite(item) for item in window) if value is not None]
    if len(clean) < min_observations:
        return None
    sd = statistics.stdev(clean)
    if sd <= 0.0:
        return None
    return (current - statistics.fmean(clean)) / sd


def trailing_percentile(window: list, min_observations: int = MIN_OBSERVATIONS):
    """Percentile rank (0-100) of the last value within the trailing window."""
    if not window:
        return None
    current = _finite(window[-1])
    if current is None:
        return None
    clean = [value for value in (_finite(item) for item in window) if value is not None]
    if len(clean) < min_observations:
        return None
    at_or_below = sum(1 for value in clean if value <= current)
    return 100.0 * at_or_below / len(clean)


def rolling_zscores(series: list, window: int, min_observations: int = MIN_OBSERVATIONS) -> list:
    """Strictly trailing z-scores, one per element of ``series``."""
    out = []
    for index in range(len(series)):
        start = max(0, index - window + 1)
        out.append(trailing_zscore(series[start : index + 1], min_observations))
    return out


def rolling_percentiles(series: list, window: int, min_observations: int = MIN_OBSERVATIONS) -> list:
    out = []
    for index in range(len(series)):
        start = max(0, index - window + 1)
        out.append(trailing_percentile(series[start : index + 1], min_observations))
    return out


def realized_vol_series(closes: list, window: int = RV_WINDOW) -> list:
    """Annualized close-to-close realized vol in vol points (x100).

    ``closes[i]`` maps to ``out[i]``. Element ``i`` uses the ``window`` log
    returns ending at ``i`` (that is, closes ``i-window`` .. ``i``), so it is
    strictly backward looking and None until enough history exists.
    """
    returns: list = [None]
    for previous, current in zip(closes, closes[1:]):
        before = _finite(previous)
        after = _finite(current)
        if before is None or after is None or before <= 0 or after <= 0:
            returns.append(None)
        else:
            returns.append(math.log(after / before))
    out: list = []
    for index in range(len(closes)):
        if index < window:
            out.append(None)
            continue
        sample = [
            value for value in returns[index - window + 1 : index + 1] if value is not None
        ]
        if len(sample) < window:
            out.append(None)
            continue
        sd = statistics.stdev(sample)
        out.append(sd * math.sqrt(TRADING_DAYS) * 100.0)
    return out


# --------------------------------------------------------------------------
# io
# --------------------------------------------------------------------------
def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    temporary.replace(path)


def _dump(payload) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def read_history(path: Path) -> list:
    if not path.exists():
        return []
    rows = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("date"):
            rows.append(row)
    return rows


def fetch_close_series(symbol: str) -> dict:
    """Date (YYYY-MM-DD) -> close, from the keyless Yahoo chart v8 endpoint."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=LOOKBACK_DAYS)
    encoded = urllib.parse.quote(symbol, safe="")
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}?"
        + urllib.parse.urlencode(
            {
                "period1": int(start.timestamp()),
                "period2": int(end.timestamp()) + 86400,
                "interval": "1d",
            }
        )
    )
    payload = json.loads(_request(url))
    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        raise ValueError(f"Yahoo returned no result for {symbol}")
    result = result[0]
    timestamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    series: dict = {}
    for index, timestamp in enumerate(timestamps):
        close = _finite(closes[index] if index < len(closes) else None)
        if close is None or close <= 0:
            continue
        date = datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d")
        series[date] = close
    if not series:
        raise ValueError(f"Yahoo returned no usable closes for {symbol}")
    return series


def read_spx_0dte(components_path: Path) -> dict:
    """Carry the options_stress z-scores forward. Absent -> nulls, never invented."""
    block = {key: None for key in SPX_0DTE_KEYS}
    block["source_as_of"] = None
    block["source"] = None
    block["available"] = False
    if not components_path.exists():
        block["status"] = "components_file_missing"
        return block
    try:
        payload = json.loads(components_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        block["status"] = f"components_unreadable:{str(exc)[:80]}"
        return block
    component = None
    for candidate in payload.get("components") or []:
        if isinstance(candidate, dict) and candidate.get("component") == "options_stress":
            component = candidate
            break
    if component is None:
        block["status"] = "options_stress_component_absent"
        return block
    latest = component.get("latest") or {}
    found = False
    for key in SPX_0DTE_KEYS:
        value = _round(latest.get(key), 6)
        block[key] = value
        found = found or value is not None
    block["source_as_of"] = component.get("as_of")
    block["source"] = component.get("source")
    block["available"] = found
    block["status"] = "ok" if found else "options_stress_values_absent"
    return block


# --------------------------------------------------------------------------
# series assembly
# --------------------------------------------------------------------------
def collect_series(fetcher, prior_rows: list) -> tuple:
    """Fetch every symbol; fall back to the committed history on failure."""
    prior_by_date = {row["date"]: row for row in prior_rows}
    series_map: dict = {}
    stale: dict = {}
    failed: dict = {}
    for key in FETCH_KEYS:
        symbol = LEVEL_SYMBOLS.get(key, SPX_SYMBOL)
        try:
            series = fetcher(symbol)
            if not series:
                raise ValueError(f"empty series for {symbol}")
            series_map[key] = {date: float(value) for date, value in series.items()}
            continue
        except Exception as exc:  # noqa: BLE001 - a source hiccup must not fail the lane
            message = str(exc)[:240]
        preserved = {}
        for date, row in prior_by_date.items():
            value = _finite(row.get(key))
            if value is not None:
                preserved[date] = value
        series_map[key] = preserved
        if preserved:
            stale[key] = {
                "symbol": symbol,
                "fetch_status": "preserved_after_fetch_failure",
                "fetch_error": message,
                "preserved_rows": len(preserved),
            }
        else:
            failed[key] = {
                "symbol": symbol,
                "fetch_status": "failed_no_prior_history",
                "fetch_error": message,
            }
    return series_map, stale, failed


def build_spine(series_map: dict, prior_rows: list) -> list:
    """Trading dates for the history: VIX's calendar, then SPX, then prior."""
    for key in ("vix", SPX_KEY, "vix3m", "vix9d"):
        dates = series_map.get(key) or {}
        if dates:
            return sorted(dates)
    return sorted({row["date"] for row in prior_rows})


def compute_rows(series_map: dict, spine: list) -> list:
    """One raw (pre-z) metric row per spine date."""
    spx_dates = sorted(series_map.get(SPX_KEY) or {})
    spx_closes = [series_map[SPX_KEY][date] for date in spx_dates]
    rv_by_date = dict(zip(spx_dates, realized_vol_series(spx_closes)))

    rows = []
    for date in spine:
        row = {"date": date}
        for key in LEVEL_SYMBOLS:
            row[key] = _round((series_map.get(key) or {}).get(date), 4)
        row[SPX_KEY] = _round((series_map.get(SPX_KEY) or {}).get(date), 4)
        row["slope_9d_vix"] = _round(_ratio(row["vix9d"], row["vix"]), 6)
        row["slope_vix_3m"] = _round(_ratio(row["vix"], row["vix3m"]), 6)
        row["slope_3m_6m"] = _round(_ratio(row["vix3m"], row["vix6m"]), 6)
        row["vvix_vix_ratio"] = _round(_ratio(row["vvix"], row["vix"]), 6)
        row["spx_rv20"] = _round(rv_by_date.get(date), 4)
        row["iv_rv_spread"] = (
            _round(row["vix"] - row["spx_rv20"], 4)
            if row["vix"] is not None and row["spx_rv20"] is not None
            else None
        )
        rows.append(row)
    return rows


def attach_zscores(rows: list) -> None:
    """Add ``<metric>_z1y``, ``_z5y`` and ``_pct1y`` in place (strictly trailing)."""
    for key in METRIC_KEYS:
        series = [row.get(key) for row in rows]
        z1y = rolling_zscores(series, WINDOW_1Y)
        z5y = rolling_zscores(series, WINDOW_5Y)
        pct = rolling_percentiles(series, WINDOW_1Y)
        for index, row in enumerate(rows):
            row[f"{key}_z1y"] = _round(z1y[index], 4)
            row[f"{key}_z5y"] = _round(z5y[index], 4)
            row[f"{key}_pct1y"] = _round(pct[index], 2)


def term_state(slope_vix_3m) -> str:
    slope = _finite(slope_vix_3m)
    if slope is None:
        return "unknown"
    if slope < 1.0 - TERM_DEAD_BAND:
        return "contango"
    if slope > 1.0 + TERM_DEAD_BAND:
        return "backwardation"
    return "flat"


def build_history_rows(series_map: dict, prior_rows: list, stale: dict, failed: dict) -> list:
    spine = build_spine(series_map, prior_rows)
    rows = compute_rows(series_map, spine)
    attach_zscores(rows)
    stale_metrics = sorted(stale)
    quality = "stale" if stale_metrics else "ready"
    for row in rows:
        row["quality_state"] = quality
        if stale_metrics:
            row["stale_metrics"] = stale_metrics
            row["fetch_status"] = "preserved_after_fetch_failure"
        if failed:
            row["unavailable_metrics"] = sorted(failed)
    return rows


def build_latest(rows: list, spx_0dte: dict, stale: dict, failed: dict, generated_at: str) -> dict:
    latest = rows[-1]
    metrics = {}
    lagging = {}
    gaps = {}
    for key in METRIC_KEYS:
        # `value` is strictly the observation on `as_of` and may be null: Yahoo
        # publishes ^SKEW and ^MOVE on a lag, so the tile needs the last real
        # observation plus its own date rather than a forward-filled guess.
        last_row = None
        last_index = None
        for index in range(len(rows) - 1, -1, -1):
            if rows[index].get(key) is not None:
                last_row = rows[index]
                last_index = index
                break
        metrics[key] = {
            "value": latest.get(key),
            "z1y": latest.get(f"{key}_z1y"),
            "z5y": latest.get(f"{key}_z5y"),
            "pct1y": latest.get(f"{key}_pct1y"),
            "last_value": last_row.get(key) if last_row else None,
            "last_value_date": last_row.get("date") if last_row else None,
            "last_z1y": last_row.get(f"{key}_z1y") if last_row else None,
            "last_z5y": last_row.get(f"{key}_z5y") if last_row else None,
            "last_pct1y": last_row.get(f"{key}_pct1y") if last_row else None,
        }
        if last_row is None:
            lagging[key] = {"last_value_date": None, "sessions_behind": None}
        elif last_row["date"] != latest["date"]:
            lagging[key] = {
                "last_value_date": last_row["date"],
                "sessions_behind": len(rows) - 1 - last_index,
            }
        # Interior gaps are invisible to a last-print check: a metric that
        # stopped printing for three weeks and then resumed reads as
        # perfectly fresh, because only its newest observation is examined.
        # Observed 2026-08-10: the whole term-structure complex (vix9d /
        # vix3m / vix6m / vix1d and the three slopes) was null from
        # 2026-07-20 through 2026-08-07 while metrics_lagging named only
        # move and skew. Report null DENSITY over a recent window too.
        window = rows[-GAP_WINDOW_SESSIONS:]
        missing = [r["date"] for r in window if r.get(key) is None]
        if missing:
            gaps[key] = {
                "sessions_missing": len(missing),
                "window_sessions": len(window),
                "first_missing": missing[0],
                "last_missing": missing[-1],
                # A metric absent for the WHOLE window is a dead feed, not a
                # gap; report it rather than filtering it out, or the worst
                # case becomes the one case this check cannot see.
                "window_fully_missing": len(missing) == len(window),
            }
    ok = [
        LEVEL_SYMBOLS.get(key, SPX_SYMBOL)
        for key in FETCH_KEYS
        if key not in stale and key not in failed
    ]
    quality = "stale" if (stale or failed) else "ready"
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "model_version": MODEL_VERSION,
        "research_only": True,
        "cadence": "daily",
        "as_of": latest["date"],
        "source": "yahoo:chart-v8; spx-0dte via market_risk_components.json",
        "metrics": metrics,
        "regime": {
            "vix": latest.get("vix"),
            "vix_pct1y": latest.get("vix_pct1y"),
            "term_state": term_state(latest.get("slope_vix_3m")),
            "term_state_basis": "slope_vix_3m = VIX/VIX3M; <0.98 contango, >1.02 backwardation",
            "slope_vix_3m": latest.get("slope_vix_3m"),
            "vvix_vix_ratio": latest.get("vvix_vix_ratio"),
            "iv_rv_spread": latest.get("iv_rv_spread"),
            "spx_rv20": latest.get("spx_rv20"),
        },
        "spx_0dte": spx_0dte,
        "coverage": {
            "symbols_ok": sorted(ok),
            "symbols_stale": sorted(
                LEVEL_SYMBOLS.get(key, SPX_SYMBOL) for key in list(stale) + list(failed)
            ),
            "rows": len(rows),
            "first_date": rows[0]["date"],
            "last_date": latest["date"],
            "metrics_lagging": lagging,
            "metrics_with_gaps": gaps,
            "stale_detail": {LEVEL_SYMBOLS.get(k, SPX_SYMBOL): v for k, v in stale.items()},
            "unavailable_detail": {LEVEL_SYMBOLS.get(k, SPX_SYMBOL): v for k, v in failed.items()},
        },
        "quality_state": quality,
    }


def build(
    *,
    output_dir: Path | None = None,
    fetcher=None,
    dry_run: bool = False,
    components_path: Path | None = None,
) -> dict:
    output_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    fetcher = fetcher or fetch_close_series
    history_path = output_dir / HISTORY_NAME
    latest_path = output_dir / LATEST_NAME
    components = components_path if components_path else output_dir / COMPONENTS_NAME

    prior_rows = read_history(history_path)
    series_map, stale, failed = collect_series(fetcher, prior_rows)
    rows = build_history_rows(series_map, prior_rows, stale, failed)
    if not rows:
        raise SystemExit("no trading dates available from any source and no prior history")

    spx_0dte = read_spx_0dte(Path(components))
    generated_at = datetime.now(timezone.utc).isoformat()
    latest = build_latest(rows, spx_0dte, stale, failed, generated_at)

    history_text = "".join(_dump(row) + "\n" for row in rows)
    if not dry_run:
        _write_text_atomic(history_path, history_text)
        _write_text_atomic(latest_path, _dump(latest) + "\n")
    return {
        "rows": rows,
        "latest": latest,
        "history_text": history_text,
        "history_path": history_path,
        "latest_path": latest_path,
        "dry_run": dry_run,
    }


def summarize(result: dict) -> dict:
    latest = result["latest"]
    return {
        "rows": len(result["rows"]),
        "first_date": result["rows"][0]["date"],
        "as_of": latest["as_of"],
        "quality_state": latest["quality_state"],
        "symbols_ok": len(latest["coverage"]["symbols_ok"]),
        "symbols_stale": len(latest["coverage"]["symbols_stale"]),
        "vix": latest["metrics"]["vix"]["value"],
        "vix_z1y": latest["metrics"]["vix"]["z1y"],
        "vix_z5y": latest["metrics"]["vix"]["z5y"],
        "term_state": latest["regime"]["term_state"],
        "iv_rv_spread": latest["regime"]["iv_rv_spread"],
        "spx_0dte": latest["spx_0dte"]["status"],
        "dry_run": result["dry_run"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build vol metrics history and latest snapshot")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute and print the summary without writing any file",
    )
    args = parser.parse_args()
    result = build(output_dir=Path(args.output_dir), dry_run=args.dry_run)
    print(json.dumps(summarize(result), sort_keys=True))
    return 0 if result["latest"]["quality_state"] != "unavailable" else 1


if __name__ == "__main__":
    raise SystemExit(main())
