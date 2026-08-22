#!/usr/bin/env python3
"""Build the volatility-metrics history and latest snapshot (tier 1 of the
vol-surface visibility plan, `_system/proposals/vol_surface_visibility_plan_2026-08-10.md`).

Sources
-------
Yahoo chart v8 daily closes provide the ten-year base history and a separate
120-day repair request for each index:
``^VIX ^VIX9D ^VIX3M ^VIX6M ^VIX1D ^VVIX ^SKEW ^MOVE`` plus ``^GSPC`` for
realized vol. Official Cboe daily files independently repair the recent Cboe
index tail. CNBC supplies an independent delayed MOVE close, and the source-
stamped ``_system/data/vol_metrics_move_outage_backfill.csv`` repairs the
2026-07-20..08-11 vendor hole that was no longer recoverable from Yahoo after
the fact. ``^VIX1D`` only exists from 2023-04-24 (index launch), so its z-scores
stay null before then; that never affects any other metric because every metric
is z-scored over its **own** observations.

Nothing is forward filled. Every fallback contributes real dated observations,
and partial recovery is merged with committed history rather than replacing it.
The published spine is capped at the latest completed US session (18:00 New
York cutoff), avoiding a mixture of today's partial Yahoo candle and yesterday's
official closes.

The ``spx_0dte`` block is **retired** and reports nulls. It used to carry
``options_stress`` z-scores forward out of ``market_risk_components.json``,
built then from the spx-0dte trading repository's intraday signals. That feed
is gone and ``options_stress`` now derives from this file, so reading it back
would make this module its own upstream and present one number as two agreeing
sources. Use ``metrics.skew``, ``metrics.slope_vix_3m`` and
``metrics.iv_rv_spread`` instead -- each carries its own trailing z-score.

Conventions
-----------
Term structure is expressed as **near / far**, so a number **below 1.0 is
contango** (the normal upward-sloping vol curve) and **above 1.0 is
backwardation** (stress):

* ``slope_9d_vix  = VIX9D / VIX``   (9-day vs 30-day)
* ``slope_vix_3m  = VIX / VIX3M``   (30-day vs 3-month) -- the regime anchor
* ``slope_3m_6m   = VIX3M / VIX6M`` (3-month vs 6-month)

``regime.term_state`` is read off ``slope_vix_3m`` with a +/- 2% dead band:
below 0.98 contango, above 1.02 backwardation, otherwise flat. When ^VIX3M has
no print for the session the state falls back to the committed SPX chain
snapshot (30d ATM IV / 91d ATM IV) under a wider +/- 5% band -- see
``resolve_term_state`` -- and stamps ``term_state_source`` /
``term_state_is_fallback`` so the basis is never ambiguous.

Feed health is read off the COLUMN, not the request. A vendor that answers 200
with a series that simply stopped produces no fetch exception, so
``symbols_ok`` used to keep naming a feed that had been dark for weeks. Any
metric whose newest ``DARK_SESSION_THRESHOLD`` sessions are all null is listed
in ``coverage.symbols_dark`` / ``coverage.metrics_dark``, drops out of
``symbols_ok``, and forces ``quality_state='stale'``.

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
A per-source failure moves to the next source. A total per-symbol failure
preserves committed history and stamps the output stale. Three trailing nulls
or three holes in the recent window also make the snapshot stale even if the
transport returned 200 or a later print resumed. The command exits nonzero for
any stale snapshot, so the scheduled commit step cannot publish a fresh
timestamp over unhealthy columns.

Outputs
-------
* ``dashboard/data/vol_metrics_history.jsonl`` -- one object per trading date,
  ascending, full backfill, rewritten deterministically from source each run.
* ``dashboard/data/vol_metrics_latest.json`` -- current levels, z-scores, the
  vol-regime tile and the spx-0dte block.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import statistics
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_technical_signals import _request  # noqa: E402

SCHEMA_VERSION = 1
MODEL_VERSION = "vol-metrics-v2"
# Recent-window size for interior-gap detection (see build_latest).
GAP_WINDOW_SESSIONS = 25
# Consecutive trailing nulls after which a metric's column is DARK, not merely
# lagging. A vendor that publishes a session or two late (^SKEW routinely, and
# ^MOVE historically) is normal; a column that has printed nothing for three
# straight sessions is a dead feed and must not be reported as healthy. See
# `dark_metrics` in build_latest for why a 200-OK fetch is not evidence of one.
DARK_SESSION_THRESHOLD = 3
# Three or more holes in the recent window are also unhealthy even when a new
# print arrives afterward. This prevents one recovered observation from hiding
# the multi-week outage that preceded it.
RECENT_GAP_STALE_THRESHOLD = 3
YAHOO_TAIL_LOOKBACK_DAYS = 120
DEFAULT_OUTPUT_DIR = ROOT / "dashboard" / "data"
HISTORY_NAME = "vol_metrics_history.jsonl"
LATEST_NAME = "vol_metrics_latest.json"
COMPONENTS_NAME = "market_risk_components.json"
SURFACE_NAME = "spx_surface_latest.json"

# Ten years, not six. Six started the file at 2020-07-13 -- AFTER the March
# 2020 crash -- so the whole archive described a single post-COVID regime and
# the two most instructive "implied vol was cheap right up until it wasn't"
# episodes sat outside it: Feb 2018 (Volmageddon) and Feb-Mar 2020. Yahoo
# serves ^VIX from 1990 and ^VIX3M / ^VVIX from 2007, so ~2016 is reachable
# without a paid source. Going further is a data-size decision, not a coverage
# one: the history file is ~1.2KB per session, so 10y is ~3MB against 1.8MB
# today, and 20y (which would reach 2008) would be ~6MB shipped to every
# browser on load. If 2008 is wanted, the right shape is a pre-aggregated
# monthly file for the long strip plus a daily tail, not a bigger JSONL.
#
# ONE-TIME EFFECT: the builder rewrites the whole history deterministically,
# and z-scores are strictly trailing, so rows in 2020-2021 whose 252/1260
# windows are currently truncated will be RECOMPUTED against the fuller
# window on the next run. Those numbers change because they were incomplete,
# not because the method changed; later rows are unaffected.
LOOKBACK_DAYS = 365 * 10 + 30
TRADING_DAYS = 252
WINDOW_1Y = 252
WINDOW_5Y = 1260
MIN_OBSERVATIONS = 30
RV_WINDOW = 20
TERM_DEAD_BAND = 0.02
# The chain fallback measures a DIFFERENT thing from VIX/VIX3M: an ATM IV ratio
# against a variance-strip ratio. On 2026-08-11 the chain read 0.828 where the
# last real VIX/VIX3M print (2026-07-17) was 0.914 -- the strip carries the
# skew, the ATM point does not, so the chain ratio runs systematically lower.
# The 2% dead band calibrated on VIX/VIX3M therefore cannot be reused here. A
# wider band means the fallback answers only when the reading is unambiguous
# under any plausible calibration offset, and says `unknown` when it is not.
CHAIN_TERM_DEAD_BAND = 0.05
# Target constant maturities the chain fallback tries to match, in days. The
# nearest listed tenor is used and its ACTUAL dte is reported.
CHAIN_NEAR_TARGET_DTE = 30
CHAIN_FAR_TARGET_DTE = 91
# Widest acceptable miss against those targets before the pair is unusable.
CHAIN_MAX_DTE_ERROR = 45
# Daily observations are not comparable until the US session has settled.
# The scheduled lane runs late evening; local/manual runs during market hours
# must not mix today's partial Yahoo candle with yesterday's official closes.
SESSION_COMPLETE_HOUR_ET = 18
NEW_YORK = ZoneInfo("America/New_York")

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

# Cboe publishes these daily files directly and updates them independently of
# Yahoo. They are an authoritative repair path for the recent tail and a full
# fallback when Yahoo is unavailable.
CBOE_DAILY_CODES = {
    "^VIX": "VIX",
    "^VIX1D": "VIX1D",
    "^VIX9D": "VIX9D",
    "^VIX3M": "VIX3M",
    "^VIX6M": "VIX6M",
    "^VVIX": "VVIX",
    "^SKEW": "SKEW",
}
CBOE_DAILY_BASE = "https://cdn.cboe.com/api/global/us_indices/daily_prices"
CNBC_MOVE_URL = (
    "https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol?"
    "symbols=.MOVE&requestMethod=quick&noform=1&partnerId=2&fund=1&exthrs=0&output=json"
)
MOVE_REPAIR_PATH = ROOT / "_system" / "data" / "vol_metrics_move_outage_backfill.csv"

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


def completed_session_cutoff(now: datetime | None = None) -> str:
    """Latest US weekday whose daily close is safe to publish.

    Calendar holidays need no hard-coded calendar: filtering source dates to
    this upper bound naturally lands on the prior actual observation.
    """
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    local = current.astimezone(NEW_YORK)
    candidate = local.date()
    if candidate.weekday() >= 5 or local.hour < SESSION_COMPLETE_HOUR_ET:
        candidate -= timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate.isoformat()


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


def _fetch_yahoo_close_series(symbol: str, start: datetime, end: datetime) -> dict:
    """Fetch one Yahoo window.

    A separate recent-window request is intentional. In July/August 2026 Yahoo
    returned a successful ten-year MOVE response ending on July 17 while a
    short-window request from the same endpoint contained newer observations.
    """
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


def _parse_daily_date(value: str) -> str | None:
    text = str(value or "").strip()
    for pattern in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, pattern).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


def fetch_cboe_close_series(symbol: str) -> dict:
    """Date -> official Cboe daily close for a supported Cboe index."""
    code = CBOE_DAILY_CODES.get(symbol)
    if not code:
        raise ValueError(f"no Cboe daily source configured for {symbol}")
    url = f"{CBOE_DAILY_BASE}/{code}_History.csv"
    raw = _request(url)
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    series = {}
    for raw in reader:
        row = {str(key or "").strip().upper(): value for key, value in raw.items()}
        day = _parse_daily_date(row.get("DATE"))
        close = _finite(row.get("CLOSE"))
        if close is None:
            close = _finite(row.get(code))
        if day and close is not None and close > 0:
            series[day] = close
    if not series:
        raise ValueError(f"Cboe returned no usable closes for {symbol}")
    return series


def read_move_repair_series(path: Path = MOVE_REPAIR_PATH) -> dict:
    """Read the audited one-time MOVE outage backfill.

    Yahoo omitted 2026-07-20..2026-08-11 from every chart response after the
    fact. Those daily closes were independently verified and are kept as a
    small source-stamped CSV rather than buried as unexplained code constants.
    """
    if not Path(path).is_file():
        return {}
    series = {}
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            day = _parse_daily_date(row.get("date"))
            close = _finite(row.get("close"))
            if day and close is not None and close > 0 and row.get("source_url"):
                series[day] = close
    return series


def fetch_cnbc_move_latest() -> dict:
    """Independent delayed MOVE close used to repair/cross-check the tail."""
    payload = json.loads(_request(CNBC_MOVE_URL))
    quotes = ((payload.get("FormattedQuoteResult") or {}).get("FormattedQuote") or [])
    quote = next((item for item in quotes if item.get("symbol") == ".MOVE"), None)
    if not quote:
        raise ValueError("CNBC returned no .MOVE quote")
    day = _parse_daily_date(quote.get("last_time"))
    if day is None:
        try:
            day = datetime.fromisoformat(str(quote.get("last_time"))).strftime("%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("CNBC returned an invalid .MOVE date") from exc
    close = _finite(str(quote.get("last") or "").replace(",", ""))
    if close is None or close <= 0:
        raise ValueError("CNBC returned no usable .MOVE close")
    return {day: close}


def fetch_close_series(symbol: str) -> dict:
    """Self-healing composite daily series.

    Yahoo supplies the long history. A second short request repairs range-
    dependent truncation; official Cboe daily files overlay the recent Cboe
    tail (or provide the full fallback); an audited CSV closes the historical
    MOVE outage, then CNBC independently supplies the last delayed MOVE close.
    Any one live source may fail without discarding the others.
    """
    end = datetime.now(timezone.utc)
    starts = (
        end - timedelta(days=LOOKBACK_DAYS),
        end - timedelta(days=YAHOO_TAIL_LOOKBACK_DAYS),
    )
    series = {}
    errors = []
    for start in starts:
        try:
            series.update(_fetch_yahoo_close_series(symbol, start, end))
        except Exception as exc:  # noqa: BLE001 - alternate source is the recovery path
            errors.append(f"Yahoo:{str(exc)[:120]}")

    if symbol in CBOE_DAILY_CODES:
        try:
            official = fetch_cboe_close_series(symbol)
            if series:
                cutoff = (end - timedelta(days=YAHOO_TAIL_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
                official = {day: value for day, value in official.items() if day >= cutoff}
            series.update(official)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Cboe:{str(exc)[:120]}")

    if symbol == "^MOVE":
        for day, value in read_move_repair_series().items():
            series.setdefault(day, value)
        try:
            series.update(fetch_cnbc_move_latest())
        except Exception as exc:  # noqa: BLE001
            errors.append(f"CNBC:{str(exc)[:120]}")

    if not series:
        raise ValueError(f"all sources failed for {symbol}: {'; '.join(errors)}")
    return series


def read_spx_0dte(components_path: Path) -> dict:
    """Retired. Reports nulls with a status saying why.

    This block used to carry the ``options_stress`` z-scores forward out of
    ``market_risk_components.json``, back when that component was built from a
    checkout of the spx-0dte trading repository's intraday signals.

    That feed is gone, and ``options_stress`` is now derived from *this file* --
    the chain snapshot plus the very z-scores in ``metrics`` below. Reading it
    back in would put this module's own output in its input and dress one
    number up as two independent sources agreeing with each other. So the block
    stays, reporting null with a reason, and the numbers it used to mirror are
    available directly: ``metrics.skew``, ``metrics.slope_vix_3m`` and
    ``metrics.iv_rv_spread``, each with its own trailing z-score.

    ``components_path`` is accepted and ignored so callers need not change.
    """
    block = {key: None for key in SPX_0DTE_KEYS}
    block["source_as_of"] = None
    block["source"] = None
    block["available"] = False
    block["status"] = "retired:options_stress_now_derives_from_this_file"
    return block


def read_chain_term(surface_path: Path) -> dict:
    """Near/far ATM implied vol from the committed SPX chain snapshot.

    This is the fallback input for ``term_state`` when the listed term-structure
    complex goes dark. It reads the SAME artifact the risk page already draws,
    so the tile and the term-structure chart below it can never disagree.

    Absent or unusable snapshot -> a block of nulls with a status saying why;
    nothing here is ever inferred from the index feeds it is standing in for.
    """
    block = {
        "ratio": None,
        "near_dte": None,
        "far_dte": None,
        "near_atm_iv": None,
        "far_atm_iv": None,
        "source_as_of": None,
        "available": False,
        "status": "chain_not_read",
    }
    if not surface_path.exists():
        block["status"] = "surface_file_missing"
        return block
    try:
        payload = json.loads(surface_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        block["status"] = f"surface_unreadable:{str(exc)[:80]}"
        return block
    block["source_as_of"] = payload.get("as_of")
    tenors = [
        {"dte": _finite(item.get("dte")), "iv": _finite(item.get("atm_iv"))}
        for item in (payload.get("tenors") or [])
        if isinstance(item, dict)
    ]
    tenors = [item for item in tenors if item["dte"] is not None and item["iv"] is not None]
    if len(tenors) < 2:
        block["status"] = "surface_has_fewer_than_two_priced_tenors"
        return block

    def nearest(target):
        return min(tenors, key=lambda item: abs(item["dte"] - target))

    near = nearest(CHAIN_NEAR_TARGET_DTE)
    far = nearest(CHAIN_FAR_TARGET_DTE)
    if near["dte"] == far["dte"]:
        block["status"] = "surface_near_and_far_resolve_to_the_same_tenor"
        return block
    near_miss = abs(near["dte"] - CHAIN_NEAR_TARGET_DTE)
    far_miss = abs(far["dte"] - CHAIN_FAR_TARGET_DTE)
    if near_miss > CHAIN_MAX_DTE_ERROR or far_miss > CHAIN_MAX_DTE_ERROR:
        block["status"] = (
            f"surface_tenors_too_far_from_target:near_off_{near_miss}d_far_off_{far_miss}d"
        )
        return block
    ratio = _ratio(near["iv"], far["iv"])
    if ratio is None:
        block["status"] = "surface_ratio_not_computable"
        return block
    block.update(
        {
            "ratio": _round(ratio, 6),
            "near_dte": int(near["dte"]),
            "far_dte": int(far["dte"]),
            "near_atm_iv": _round(near["iv"], 6),
            "far_atm_iv": _round(far["iv"], 6),
            "available": True,
            "status": "ok",
        }
    )
    return block


FORWARD_HORIZONS = (21, 63)
# Percentile edges for the conditioning buckets. Deliberately coarse: the
# effective sample size (see below) is a few dozen independent windows, which
# cannot support decile resolution without inventing precision.
FORWARD_BUCKETS = (
    ("cheapest", 0.0, 20.0),
    ("cheap", 20.0, 40.0),
    ("middle", 40.0, 60.0),
    ("rich", 60.0, 80.0),
    ("richest", 80.0, 100.01),
)


def _forward_window_stats(closes: list, start: int, horizon: int) -> dict | None:
    """Realised drawdown and vol over ``closes[start : start+horizon]``."""
    end = start + horizon
    if end >= len(closes):
        return None
    window = closes[start:end + 1]
    if any(value is None or value <= 0 for value in window):
        return None
    peak = window[0]
    worst = 0.0
    for value in window:
        peak = max(peak, value)
        worst = min(worst, value / peak - 1.0)
    returns = [
        math.log(window[i] / window[i - 1])
        for i in range(1, len(window))
    ]
    vol = (
        statistics.stdev(returns) * math.sqrt(TRADING_DAYS) * 100.0
        if len(returns) > 1
        else None
    )
    return {
        "max_drawdown_pct": worst * 100.0,
        "realized_vol": vol,
        "total_return_pct": (window[-1] / window[0] - 1.0) * 100.0,
    }


def build_forward_conditioning(rows: list, metric: str = "iv_rv_spread") -> dict:
    """What happened NEXT, historically, at today's percentile of ``metric``.

    A z-score says where a reading sits in its own distribution. It says
    nothing about what followed, which is the only question a reader actually
    has when the page reports that implied vol is at the 13th percentile of
    the last year. This buckets every session by its POINT-IN-TIME trailing
    percentile -- the same `_pct1y` the tiles already show, computed from data
    available on that date, so the bucketing carries no look-ahead -- and
    reports the realised forward outcome of each bucket.

    Three honesty constraints, all of which the numbers are useless without:

    * The forward windows OVERLAP. Consecutive sessions share 20 of their 21
      forward days, so 300 observations in a bucket are nowhere near 300
      independent trials. `independent_windows` divides by the horizon and is
      the number to reason about; `observations` is reported beside it only so
      the ratio is visible.
    * The last `horizon` sessions have no forward window and are EXCLUDED, not
      zero-filled. `truncated_sessions` says how many.
    * This is hindsight by construction. It describes what followed similar
      readings in this sample; it is not a forecast, and the sample is one
      market over one decade.
    """
    ordered = sorted(rows, key=lambda row: row.get("date") or "")
    closes = [_finite(row.get(SPX_KEY)) for row in ordered]
    out = {
        "metric": metric,
        "buckets_by_horizon": {},
        "basis": (
            "sessions bucketed by their own trailing 1-year percentile of"
            f" {metric} (point-in-time, no look-ahead); outcome is the realised"
            " forward path of spx_close"
        ),
        "caveat": (
            "Overlapping windows: consecutive sessions share all but one"
            " forward day, so independent_windows -- not observations -- is the"
            " effective sample size. Hindsight by construction; not a forecast."
        ),
        "research_only": True,
    }

    for horizon in FORWARD_HORIZONS:
        buckets = {
            name: {"drawdowns": [], "vols": [], "returns": []}
            for name, _, _ in FORWARD_BUCKETS
        }
        truncated = 0
        unusable = 0
        for index, row in enumerate(ordered):
            pct = _finite(row.get(f"{metric}_pct1y"))
            if pct is None:
                continue
            if index + horizon >= len(ordered):
                truncated += 1
                continue
            stats = _forward_window_stats(closes, index, horizon)
            if stats is None:
                unusable += 1
                continue
            for name, low, high in FORWARD_BUCKETS:
                if low <= pct < high:
                    buckets[name]["drawdowns"].append(stats["max_drawdown_pct"])
                    buckets[name]["vols"].append(stats["realized_vol"])
                    buckets[name]["returns"].append(stats["total_return_pct"])
                    break

        summary = {}
        for name, low, high in FORWARD_BUCKETS:
            drawdowns = buckets[name]["drawdowns"]
            vols = [v for v in buckets[name]["vols"] if v is not None]
            returns = buckets[name]["returns"]
            count = len(drawdowns)
            summary[name] = {
                "percentile_range": [low, min(high, 100.0)],
                "observations": count,
                # Overlap correction: n distinct start dates sharing a horizon-day
                # window contribute roughly n/horizon independent draws.
                "independent_windows": round(count / horizon, 1) if count else 0.0,
                "median_max_drawdown_pct": _round(statistics.median(drawdowns), 2) if count else None,
                "worst_max_drawdown_pct": _round(min(drawdowns), 2) if count else None,
                "median_realized_vol": _round(statistics.median(vols), 2) if vols else None,
                "median_total_return_pct": _round(statistics.median(returns), 2) if returns else None,
                "share_drawdown_over_5pct": (
                    _round(sum(1 for d in drawdowns if d <= -5.0) / count, 3) if count else None
                ),
            }
        out["buckets_by_horizon"][str(horizon)] = {
            "horizon_sessions": horizon,
            "buckets": summary,
            "truncated_sessions": truncated,
            "unusable_sessions": unusable,
        }
    return out


def current_forward_bucket(pct) -> str | None:
    """Which conditioning bucket a live percentile falls in (None if absent)."""
    value = _finite(pct)
    if value is None:
        return None
    for name, low, high in FORWARD_BUCKETS:
        if low <= value < high:
            return name
    return None


def trailing_dark_sessions(rows: list, key: str) -> int:
    """Consecutive trailing sessions on which ``key`` did not print.

    Counts backwards from the newest row and stops at the first observation, so
    a metric that printed today is zero sessions dark no matter how many holes
    sit behind it. Interior gaps are reported separately by ``metrics_with_gaps``.
    """
    count = 0
    for row in reversed(rows):
        if _finite(row.get(key)) is not None:
            break
        count += 1
    return count


# --------------------------------------------------------------------------
# series assembly
# --------------------------------------------------------------------------
def collect_series(fetcher, prior_rows: list) -> tuple:
    """Fetch every symbol; merge partial recovery with committed history."""
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
            # A fallback may only provide a recent tail or latest close. Keep
            # all valid committed observations and let newly fetched values
            # win on overlap; recovery must never erase good history.
            merged = {
                date: value
                for date, row in prior_by_date.items()
                if (value := _finite(row.get(key))) is not None
            }
            merged.update({date: float(value) for date, value in series.items()})
            series_map[key] = merged
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
    """Completed trading dates: VIX's calendar, then SPX, then prior."""
    cutoff = completed_session_cutoff()
    for key in ("vix", SPX_KEY, "vix3m", "vix9d"):
        dates = series_map.get(key) or {}
        if dates:
            return sorted(day for day in dates if day <= cutoff)
    return sorted({row["date"] for row in prior_rows if row["date"] <= cutoff})


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


def term_state(slope_vix_3m, dead_band: float = TERM_DEAD_BAND) -> str:
    """Near/far ratio -> regime label. Below 1 is contango, above is stress."""
    slope = _finite(slope_vix_3m)
    if slope is None:
        return "unknown"
    if slope < 1.0 - dead_band:
        return "contango"
    if slope > 1.0 + dead_band:
        return "backwardation"
    return "flat"


def resolve_term_state(slope_vix_3m, chain: dict) -> dict:
    """Term state from VIX/VIX3M, falling back to the SPX chain when it is dark.

    The primary basis is the listed complex. When Yahoo stops printing ^VIX3M --
    which it did after 2026-07-17, without ever failing a request -- the tile
    used to read `unknown` while the term-structure chart directly beneath it
    showed an unambiguous curve built from a chain snapshot that WAS current.
    Two panels on one page cannot disagree about whether the answer exists.

    The fallback is deliberately conservative: it answers only outside a 5%
    dead band (see CHAIN_TERM_DEAD_BAND), because an ATM ratio is not the same
    measurement as a variance-strip ratio and the primary thresholds are not
    transferable. Inside that band it returns `unknown` and says why, rather
    than reporting a state it cannot support.
    """
    block = {
        "term_state": "unknown",
        "term_state_source": "none",
        "term_state_basis": "no term-structure input is available from either the listed complex or the chain",
        "term_state_is_fallback": False,
        "slope_vix_3m": _round(_finite(slope_vix_3m), 6),
        "chain_term_ratio": chain.get("ratio"),
        "chain_term_detail": chain,
    }
    primary = _finite(slope_vix_3m)
    if primary is not None:
        block.update(
            {
                "term_state": term_state(primary),
                "term_state_source": "vix_vix3m",
                "term_state_basis": (
                    "slope_vix_3m = VIX/VIX3M; <0.98 contango, >1.02 backwardation"
                ),
            }
        )
        return block

    if not chain.get("available"):
        block["term_state_basis"] = (
            "VIX3M has no print for this session and the SPX chain fallback is unusable "
            f"({chain.get('status')}), so no term state is claimed"
        )
        return block

    ratio = _finite(chain.get("ratio"))
    state = term_state(ratio, CHAIN_TERM_DEAD_BAND)
    near = chain.get("near_dte")
    far = chain.get("far_dte")
    stamp = str(chain.get("source_as_of") or "unknown date")[:10]
    if state in ("unknown", "flat"):
        # `flat` under the wide band means "inside the uncertainty", not "the
        # curve is flat" -- publishing it as a state would overstate the fallback.
        block["term_state_basis"] = (
            f"VIX3M is dark, and the SPX chain ratio ({near}d/{far}d ATM IV = "
            f"{'n/a' if ratio is None else format(ratio, '.4f')}, snapshot {stamp}) sits inside the "
            f"+/-{CHAIN_TERM_DEAD_BAND:.0%} band where an ATM ratio cannot be mapped onto the "
            "VIX/VIX3M thresholds with confidence, so no term state is claimed"
        )
        return block
    block.update(
        {
            "term_state": state,
            "term_state_source": "spx_chain_atm",
            "term_state_is_fallback": True,
            "term_state_basis": (
                f"FALLBACK -- VIX3M has no print for this session. State read off the SPX chain "
                f"instead: {near}d ATM IV / {far}d ATM IV = {ratio:.4f} (snapshot {stamp}); "
                f"<{1 - CHAIN_TERM_DEAD_BAND:.2f} contango, >{1 + CHAIN_TERM_DEAD_BAND:.2f} backwardation. "
                "The band is wider than the VIX/VIX3M one because an ATM ratio carries no skew "
                "and runs systematically below the variance-strip ratio it stands in for."
            ),
        }
    )
    return block


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


def build_latest(
    rows: list,
    spx_0dte: dict,
    stale: dict,
    failed: dict,
    generated_at: str,
    chain: dict | None = None,
) -> dict:
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
    # A 200-OK fetch is not evidence of a live feed. Yahoo kept answering for
    # ^VIX3M / ^VIX9D / ^VIX6M / ^VIX1D / ^MOVE after 2026-07-17 while returning
    # a series that simply stopped -- no exception, no empty payload, so
    # `collect_series` recorded no failure and `symbols_ok` went on naming every
    # one of them for sixteen sessions. Health has to be read off the COLUMN,
    # not off the request: a metric whose newest DARK_SESSION_THRESHOLD sessions
    # are all null is a dead feed regardless of what the transport said.
    dark = {}
    for key in FETCH_KEYS:
        sessions = trailing_dark_sessions(rows, key)
        if sessions >= DARK_SESSION_THRESHOLD:
            dark[key] = {
                "symbol": LEVEL_SYMBOLS.get(key, SPX_SYMBOL),
                "sessions_dark": sessions,
                "last_value_date": metrics.get(key, {}).get("last_value_date"),
                "detected_by": "column_trailing_nulls",
                "note": (
                    "the fetch did not fail; the vendor answered and the series "
                    "stopped, so this is only visible in the data"
                ),
            }
    ok = [
        LEVEL_SYMBOLS.get(key, SPX_SYMBOL)
        for key in FETCH_KEYS
        if key not in stale and key not in failed and key not in dark
    ]
    gap_stale = {
        key: detail
        for key, detail in gaps.items()
        if detail["sessions_missing"] >= RECENT_GAP_STALE_THRESHOLD
    }
    quality = "stale" if (stale or failed or dark or gap_stale) else "ready"
    regime = resolve_term_state(
        latest.get("slope_vix_3m"),
        chain if chain is not None else {"available": False, "status": "chain_not_supplied", "ratio": None},
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "model_version": MODEL_VERSION,
        "research_only": True,
        "cadence": "daily",
        "as_of": latest["date"],
        "source": (
            "composite:yahoo-chart-v8(full+recent-tail),cboe-daily-official,"
            "cnbc-move-delayed; spx-0dte via market_risk_components.json"
        ),
        "metrics": metrics,
        "regime": {
            "vix": latest.get("vix"),
            "vix_pct1y": latest.get("vix_pct1y"),
            "term_state": regime["term_state"],
            "term_state_basis": regime["term_state_basis"],
            "term_state_source": regime["term_state_source"],
            "term_state_is_fallback": regime["term_state_is_fallback"],
            "chain_term_ratio": regime["chain_term_ratio"],
            "chain_term_detail": regime["chain_term_detail"],
            "slope_vix_3m": latest.get("slope_vix_3m"),
            "vvix_vix_ratio": latest.get("vvix_vix_ratio"),
            "iv_rv_spread": latest.get("iv_rv_spread"),
            "spx_rv20": latest.get("spx_rv20"),
        },
        "spx_0dte": spx_0dte,
        "forward_conditioning": {
            **build_forward_conditioning(rows),
            "current_bucket": current_forward_bucket(
                metrics.get("iv_rv_spread", {}).get("pct1y")
                or metrics.get("iv_rv_spread", {}).get("last_pct1y")
            ),
            "current_pct1y": (
                metrics.get("iv_rv_spread", {}).get("pct1y")
                or metrics.get("iv_rv_spread", {}).get("last_pct1y")
            ),
        },
        "coverage": {
            "symbols_ok": sorted(ok),
            "symbols_stale": sorted(
                LEVEL_SYMBOLS.get(key, SPX_SYMBOL) for key in list(stale) + list(failed)
            ),
            "rows": len(rows),
            "first_date": rows[0]["date"],
            "last_date": latest["date"],
            "symbols_dark": sorted(LEVEL_SYMBOLS.get(key, SPX_SYMBOL) for key in dark),
            "metrics_lagging": lagging,
            "metrics_with_gaps": gaps,
            "metrics_gap_stale": gap_stale,
            "metrics_dark": dark,
            "dark_threshold_sessions": DARK_SESSION_THRESHOLD,
            "gap_stale_threshold_sessions": RECENT_GAP_STALE_THRESHOLD,
            "source_strategy": {
                "long_history": "Yahoo chart-v8 ten-year window",
                "tail_repair": f"Yahoo chart-v8 {YAHOO_TAIL_LOOKBACK_DAYS}-day window",
                "cboe_repair": "official Cboe daily index files",
                "move_outage_backfill": str(MOVE_REPAIR_PATH.relative_to(ROOT)).replace("\\", "/"),
                "move_cross_check": "CNBC delayed .MOVE close",
                "merge_rule": "committed history preserved; fresh observations win by date",
                "session_cutoff": (
                    f"completed US weekdays only; current session admitted after "
                    f"{SESSION_COMPLETE_HOUR_ET}:00 America/New_York"
                ),
            },
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
    surface_path: Path | None = None,
) -> dict:
    output_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    fetcher = fetcher or fetch_close_series
    history_path = output_dir / HISTORY_NAME
    latest_path = output_dir / LATEST_NAME
    components = components_path if components_path else output_dir / COMPONENTS_NAME
    surface = surface_path if surface_path else output_dir / SURFACE_NAME

    prior_rows = read_history(history_path)
    series_map, stale, failed = collect_series(fetcher, prior_rows)
    rows = build_history_rows(series_map, prior_rows, stale, failed)
    if not rows:
        raise SystemExit("no trading dates available from any source and no prior history")

    spx_0dte = read_spx_0dte(Path(components))
    chain = read_chain_term(Path(surface))
    generated_at = datetime.now(timezone.utc).isoformat()
    latest = build_latest(rows, spx_0dte, stale, failed, generated_at, chain=chain)

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
        "symbols_dark": len(latest["coverage"].get("symbols_dark") or []),
        "term_state_source": latest["regime"]["term_state_source"],
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
    # A stale build must alert the scheduled lane and prevent its commit step
    # from laundering old columns behind a fresh generated_at timestamp.
    return 0 if result["latest"]["quality_state"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
