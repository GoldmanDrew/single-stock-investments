#!/usr/bin/env python3
"""Build free, reproducible technical z-score snapshots for dashboard holdings.

The signal is deliberately an execution/risk overlay. It never changes valuation
readiness, stance, or evidence status.
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
import urllib.request
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from darwin.prices import stooq_symbol  # noqa: E402
from fetch_equity_prices import yahoo_symbol_for  # noqa: E402
from portfolio_registry import load_registry  # noqa: E402

OUTPUT = ROOT / "dashboard" / "data" / "technical_signals.json"
SUMMARY_OUTPUT = ROOT / "dashboard" / "data" / "technical_summary.json"
USER_AGENT = "Mozilla/5.0 (compatible; MagisTechnicalResearch/1.0)"
MODEL_VERSION = "technical-fear-v2"
TRADING_DAYS = 252
LOOKBACK_DAYS = 365 * 5 + 30
BENCHMARKS = {
    "US": "SPY",
    "OTC": "SPY",
    "CA": "XIC.TO",
    "EU": "IEUR",
    "UK": "ISF.L",
    "SE": "^OMX",
    "JP": "1321.T",
    "AU": "STW.AX",
    "IN": "^NSEI",
}


def _finite(value) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _round(value, digits: int = 3):
    value = _finite(value)
    return None if value is None else round(value, digits)


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
        encoding="utf-8",
    )
    temporary.replace(path)


def _request(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as response:
        return response.read()


def fetch_stooq_history(symbol: str) -> tuple[list[dict], str]:
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=LOOKBACK_DAYS)
    url = (
        "https://stooq.com/q/d/l/?"
        + urllib.parse.urlencode(
            {
                "s": symbol.lower(),
                "d1": start.strftime("%Y%m%d"),
                "d2": end.strftime("%Y%m%d"),
                "i": "d",
            }
        )
    )
    raw = _request(url).decode("utf-8", errors="replace")
    rows = []
    for row in csv.DictReader(io.StringIO(raw)):
        close = _finite(row.get("Close"))
        if not row.get("Date") or close is None or close <= 0:
            continue
        rows.append(
            {
                "date": row["Date"],
                "open": _finite(row.get("Open")),
                "high": _finite(row.get("High")),
                "low": _finite(row.get("Low")),
                "close": close,
                "volume": _finite(row.get("Volume")),
            }
        )
    if len(rows) < 120:
        raise ValueError(f"Stooq returned {len(rows)} usable rows")
    return rows, f"stooq:{symbol.lower()}"


def fetch_yahoo_history(symbol: str) -> tuple[list[dict], str]:
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
                "events": "div,splits",
            }
        )
    )
    payload = json.loads(_request(url))
    result = payload["chart"]["result"][0]
    timestamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    adjusted = (((result.get("indicators") or {}).get("adjclose") or [{}])[0]).get("adjclose") or []
    rows = []
    for index, timestamp in enumerate(timestamps):
        raw_close = _finite(closes[index] if index < len(closes) else None)
        close = _finite(adjusted[index] if index < len(adjusted) else None) or raw_close
        if close is None or close <= 0:
            continue
        adjustment = close / raw_close if raw_close and raw_close > 0 else 1.0
        def adjusted_value(values):
            value = _finite(values[index] if index < len(values) else None)
            return value * adjustment if value is not None else None
        rows.append(
            {
                "date": datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d"),
                "open": adjusted_value(opens),
                "high": adjusted_value(highs),
                "low": adjusted_value(lows),
                "close": close,
                "volume": _finite(volumes[index] if index < len(volumes) else None),
            }
        )
    if len(rows) < 120:
        raise ValueError(f"Yahoo returned {len(rows)} usable rows")
    return rows, f"yahoo:{symbol}"


def fetch_history(ticker: str, market: str, exchange: str, quote_ticker: str | None) -> tuple[list[dict], str]:
    errors = []
    yahoo = yahoo_symbol_for(quote_ticker or ticker, market, exchange)
    try:
        return fetch_yahoo_history(yahoo)
    except Exception as exc:
        errors.append(f"yahoo={exc}")
    stooq = stooq_symbol(quote_ticker or ticker, market)
    if stooq:
        try:
            return fetch_stooq_history(stooq)
        except Exception as exc:
            errors.append(f"stooq={exc}")
    raise RuntimeError("; ".join(errors))


def _return(values: list[float], index: int, window: int) -> float | None:
    if index < window or values[index - window] <= 0:
        return None
    return values[index] / values[index - window] - 1.0


def _mean(values: list[float | None]) -> float | None:
    clean = [float(value) for value in values if _finite(value) is not None]
    return statistics.fmean(clean) if clean else None


def _stdev(values: list[float | None]) -> float | None:
    clean = [float(value) for value in values if _finite(value) is not None]
    return statistics.stdev(clean) if len(clean) >= 2 else None


def _zscore(series: list[float | None]) -> float | None:
    if not series or _finite(series[-1]) is None:
        return None
    clean = [float(value) for value in series[-756:] if _finite(value) is not None]
    if len(clean) < 40:
        return None
    current = clean[-1]
    history = clean[:-1]
    mean = statistics.fmean(history)
    sd = statistics.stdev(history) if len(history) >= 2 else 0
    if sd <= 1e-12:
        return 0.0
    return max(-4.0, min(4.0, (current - mean) / sd))


def _rolling_return_z(closes: list[float], window: int) -> tuple[float | None, float | None]:
    series = [_return(closes, index, window) for index in range(len(closes))]
    return series[-1], _zscore(series)


def _rolling_distance_z(closes: list[float], window: int) -> tuple[float | None, float | None]:
    series: list[float | None] = []
    rolling_sum = 0.0
    for index, close in enumerate(closes):
        rolling_sum += close
        if index >= window:
            rolling_sum -= closes[index - window]
        if index + 1 < window:
            series.append(None)
            continue
        average = rolling_sum / window
        series.append(close / average - 1.0 if average > 0 else None)
    return series[-1], _zscore(series)


def _rolling_volatility_z(closes: list[float], window: int = 20) -> tuple[float | None, float | None]:
    log_returns: list[float | None] = [None]
    for before, after in zip(closes, closes[1:]):
        log_returns.append(math.log(after / before) if before > 0 and after > 0 else None)
    series: list[float | None] = []
    for index in range(len(closes)):
        if index + 1 < window:
            series.append(None)
            continue
        sample = log_returns[index - window + 1 : index + 1]
        sd = _stdev(sample)
        series.append(sd * math.sqrt(TRADING_DAYS) if sd is not None else None)
    return series[-1], _zscore(series)


def _rolling_drawdown_z(closes: list[float], window: int = 252) -> tuple[float | None, float | None]:
    series: list[float | None] = []
    peaks: deque[int] = deque()
    for index, close in enumerate(closes):
        while peaks and peaks[0] <= index - window:
            peaks.popleft()
        while peaks and closes[peaks[-1]] <= close:
            peaks.pop()
        peaks.append(index)
        peak = closes[peaks[0]]
        series.append(close / peak - 1.0 if peak > 0 else None)
    return series[-1], _zscore(series)


def _rolling_volume_z(volumes: list[float | None], window: int = 20) -> tuple[float | None, float | None]:
    series: list[float | None] = []
    for index, volume in enumerate(volumes):
        if volume is None or volume <= 0 or index < window:
            series.append(None)
            continue
        prior = [value for value in volumes[index - window : index] if value is not None and value > 0]
        average = _mean(prior)
        series.append(math.log(volume / average) if average and average > 0 else None)
    return series[-1], _zscore(series)


def _relative_strength_z(rows: list[dict], benchmark_rows: list[dict] | None, window: int = 60):
    if not benchmark_rows:
        return None, None
    benchmark = {row["date"]: row["close"] for row in benchmark_rows}
    aligned = [(row["close"], benchmark.get(row["date"])) for row in rows if benchmark.get(row["date"])]
    if len(aligned) <= window:
        return None, None
    stock = [pair[0] for pair in aligned]
    index = [pair[1] for pair in aligned]
    series = []
    for position in range(len(aligned)):
        stock_return = _return(stock, position, window)
        index_return = _return(index, position, window)
        series.append(
            stock_return - index_return
            if stock_return is not None and index_return is not None
            else None
        )
    return series[-1], _zscore(series)


def _weighted_z(parts: list[tuple[float | None, float]]) -> float | None:
    usable = [(float(value), weight) for value, weight in parts if _finite(value) is not None]
    if not usable:
        return None
    total = sum(weight for _, weight in usable)
    return sum(value * weight for value, weight in usable) / total if total else None


def _percentile_latest(series: list[float | None], *, minimum: int = 40) -> float | None:
    if not series or _finite(series[-1]) is None:
        return None
    clean = [float(value) for value in series[-756:] if _finite(value) is not None]
    if len(clean) < minimum:
        return None
    current = clean[-1]
    history = clean[:-1]
    if not history:
        return None
    return sum(value <= current for value in history) / len(history)


def _fear_percentile(series: list[float | None], *, lower_is_fear: bool = False) -> float | None:
    percentile = _percentile_latest(series)
    if percentile is None:
        return None
    return 100.0 * (1.0 - percentile if lower_is_fear else percentile)


def _weighted_score(parts: list[tuple[float | None, float]]) -> float | None:
    usable = [(max(0.0, min(100.0, float(value))), weight) for value, weight in parts if _finite(value) is not None]
    if not usable:
        return None
    total = sum(weight for _, weight in usable)
    return sum(value * weight for value, weight in usable) / total if total else None


def _rolling_feature_series(rows: list[dict]) -> dict[str, list[float | None]]:
    closes = [float(row["close"]) for row in rows]
    volumes = [_finite(row.get("volume")) for row in rows]
    log_returns: list[float | None] = [None]
    for before, after in zip(closes, closes[1:]):
        log_returns.append(math.log(after / before) if before > 0 and after > 0 else None)

    features: dict[str, list[float | None]] = {
        key: [] for key in (
            "return_1d", "return_5d", "return_20d", "drawdown_252d", "distance_50d",
            "volume_log_20d", "true_range_atr", "gap", "close_location", "rv_20d",
            "vol_acceleration", "vcr_20d", "trend_ratio_20d", "negative_consistency_20d",
            "downside_share_20d",
        )
    }
    true_ranges: list[float | None] = []
    peaks_252d: deque[int] = deque()
    sum_50d = 0.0
    for index, row in enumerate(rows):
        close = closes[index]
        prior_close = closes[index - 1] if index else None
        open_px = _finite(row.get("open"))
        high = _finite(row.get("high"))
        low = _finite(row.get("low"))
        features["return_1d"].append(_return(closes, index, 1))
        features["return_5d"].append(_return(closes, index, 5))
        features["return_20d"].append(_return(closes, index, 20))

        while peaks_252d and peaks_252d[0] <= index - 252:
            peaks_252d.popleft()
        while peaks_252d and closes[peaks_252d[-1]] <= close:
            peaks_252d.pop()
        peaks_252d.append(index)
        peak = closes[peaks_252d[0]]
        features["drawdown_252d"].append(close / peak - 1.0 if peak > 0 else None)
        sum_50d += close
        if index >= 50:
            sum_50d -= closes[index - 50]
        if index >= 49:
            average_50d = sum_50d / 50.0
            features["distance_50d"].append(close / average_50d - 1.0 if average_50d > 0 else None)
        else:
            features["distance_50d"].append(None)

        if index >= 20 and volumes[index] and volumes[index] > 0:
            prior_volumes = [value for value in volumes[index - 20 : index] if value and value > 0]
            average_volume = _mean(prior_volumes)
            features["volume_log_20d"].append(
                math.log(volumes[index] / average_volume) if average_volume and average_volume > 0 else None
            )
        else:
            features["volume_log_20d"].append(None)

        if high is not None and low is not None and high >= low:
            true_range = max(
                high - low,
                abs(high - prior_close) if prior_close is not None else 0.0,
                abs(low - prior_close) if prior_close is not None else 0.0,
            )
            close_location = ((close - low) / (high - low) * 2.0 - 1.0) if high > low else 0.0
        else:
            true_range = None
            close_location = None
        true_ranges.append(true_range)
        if index >= 20 and true_range is not None:
            prior_ranges = [value for value in true_ranges[index - 20 : index] if value is not None]
            atr = _mean(prior_ranges)
            features["true_range_atr"].append(true_range / atr if atr and atr > 0 else None)
        else:
            features["true_range_atr"].append(None)
        features["gap"].append(
            open_px / prior_close - 1.0 if open_px and prior_close and prior_close > 0 else None
        )
        features["close_location"].append(close_location)

        if index >= 20:
            tail20 = [value for value in log_returns[index - 19 : index + 1] if value is not None]
            sd20 = _stdev(tail20)
            rv20 = sd20 * math.sqrt(TRADING_DAYS) if sd20 is not None else None
            features["rv_20d"].append(rv20)
            tail5 = [value for value in log_returns[index - 4 : index + 1] if value is not None]
            sd5 = _stdev(tail5)
            rv5 = sd5 * math.sqrt(TRADING_DAYS) if sd5 is not None else None
            features["vol_acceleration"].append(rv5 / rv20 if rv5 is not None and rv20 and rv20 > 0 else None)
            squares = [value * value for value in tail20]
            sum_sq = sum(squares)
            features["vcr_20d"].append(max(squares) / sum_sq if squares and sum_sq > 0 else None)
            weekly = [sum(tail20[start : start + 5]) for start in range(0, len(tail20), 5)]
            daily_rms_rv = math.sqrt(sum_sq / len(tail20) * TRADING_DAYS) if tail20 else None
            weekly_rms_rv = (
                math.sqrt(sum(value * value for value in weekly) / len(weekly) * (TRADING_DAYS / 5.0))
                if weekly else None
            )
            features["trend_ratio_20d"].append(
                weekly_rms_rv / daily_rms_rv
                if weekly_rms_rv is not None and daily_rms_rv and daily_rms_rv > 0 else None
            )
            features["negative_consistency_20d"].append(sum(value < 0 for value in tail20) / len(tail20) if tail20 else None)
            downside = sum(value * value for value in tail20 if value < 0)
            features["downside_share_20d"].append(downside / sum_sq if sum_sq > 0 else None)
        else:
            for key in (
                "rv_20d", "vol_acceleration", "vcr_20d", "trend_ratio_20d",
                "negative_consistency_20d", "downside_share_20d",
            ):
                features[key].append(None)
    return features


def _capitulation_snapshot(rows: list[dict], relative60_z: float | None) -> dict:
    features = _rolling_feature_series(rows)
    latest = {key: values[-1] for key, values in features.items()}
    pct = {
        "return_1d_fear": _fear_percentile(features["return_1d"], lower_is_fear=True),
        "return_5d_fear": _fear_percentile(features["return_5d"], lower_is_fear=True),
        "return_20d_fear": _fear_percentile(features["return_20d"], lower_is_fear=True),
        "drawdown_fear": _fear_percentile(features["drawdown_252d"], lower_is_fear=True),
        "distance_50d_fear": _fear_percentile(features["distance_50d"], lower_is_fear=True),
        "volume_climax": _fear_percentile(features["volume_log_20d"]),
        "range_climax": _fear_percentile(features["true_range_atr"]),
        "gap_fear": _fear_percentile(features["gap"], lower_is_fear=True),
        "volatility_fear": _fear_percentile(features["rv_20d"]),
        "vol_acceleration": _fear_percentile(features["vol_acceleration"]),
        "vcr": _fear_percentile(features["vcr_20d"]),
        "trend_shape": _fear_percentile(features["trend_ratio_20d"]),
        "negative_consistency": _fear_percentile(features["negative_consistency_20d"]),
        "downside_share": _fear_percentile(features["downside_share_20d"]),
    }
    close_location_fear = (
        max(0.0, min(100.0, (1.0 - latest["close_location"]) * 50.0))
        if latest["close_location"] is not None else None
    )
    relative_fear = (
        max(0.0, min(100.0, 50.0 - 22.0 * relative60_z))
        if relative60_z is not None else None
    )
    families = {
        "price_dislocation": _weighted_score([
            (pct["return_1d_fear"], 0.15), (pct["return_5d_fear"], 0.25),
            (pct["return_20d_fear"], 0.20), (pct["drawdown_fear"], 0.20),
            (pct["distance_50d_fear"], 0.20),
        ]),
        "selling_climax": _weighted_score([
            (pct["volume_climax"], 0.28), (pct["range_climax"], 0.28),
            (pct["gap_fear"], 0.16), (close_location_fear, 0.18), (pct["vcr"], 0.10),
        ]),
        "volatility_stress": _weighted_score([
            (pct["volatility_fear"], 0.38), (pct["vol_acceleration"], 0.27),
            (pct["vcr"], 0.15), (pct["downside_share"], 0.20),
        ]),
        "relative_path_stress": _weighted_score([
            (relative_fear, 0.45), (pct["negative_consistency"], 0.30),
            (pct["trend_shape"], 0.25),
        ]),
    }
    pressure = _weighted_score([
        (families["price_dislocation"], 0.50),
        (families["relative_path_stress"], 0.30),
        (pct["negative_consistency"], 0.20),
    ])
    panic = _weighted_score([
        (families["price_dislocation"], 0.30),
        (families["selling_climax"], 0.35),
        (families["volatility_stress"], 0.20),
        (families["relative_path_stress"], 0.15),
    ])

    last = rows[-1]
    prior = rows[-2] if len(rows) > 1 else {}
    prior_high = _finite(prior.get("high"))
    close = _finite(last.get("close"))
    volume = _finite(last.get("volume"))
    recent_volumes = [_finite(row.get("volume")) for row in rows[-6:-1]]
    recent_peak_volume = max([value for value in recent_volumes if value is not None], default=None)
    confirmation = {
        "positive_session": bool(latest["return_1d"] is not None and latest["return_1d"] > 0),
        "closed_upper_half": bool(latest["close_location"] is not None and latest["close_location"] > 0),
        "reclaimed_prior_high": bool(close and prior_high and close > prior_high),
        "volume_cooled": bool(volume and recent_peak_volume and volume < 0.75 * recent_peak_volume),
    }
    exhaustion = _weighted_score([
        (100.0 if confirmation["positive_session"] else 0.0, 0.20),
        (max(0.0, min(100.0, (latest["close_location"] + 1.0) * 50.0)) if latest["close_location"] is not None else None, 0.30),
        (100.0 if confirmation["reclaimed_prior_high"] else 0.0, 0.30),
        (100.0 if confirmation["volume_cooled"] else 0.0, 0.20),
    ])

    coverage_inputs = [
        *families.values(), pressure, panic, exhaustion, latest["vcr_20d"],
        latest["trend_ratio_20d"], latest["true_range_atr"], latest["close_location"],
    ]
    coverage = 100.0 * sum(value is not None for value in coverage_inputs) / len(coverage_inputs)
    extreme_families = sum((value or 0) >= 70 for value in families.values())
    confirmations = sum(confirmation.values())
    candidate = bool(
        panic is not None and panic >= 80
        and (families["selling_climax"] or 0) >= 65
        and extreme_families >= 3 and coverage >= 75
    )
    if candidate and exhaustion is not None and exhaustion >= 65 and confirmations >= 2:
        state = "confirmed_exhaustion"
    elif candidate and exhaustion is not None and exhaustion >= 40:
        state = "exhaustion_emerging"
    elif candidate:
        state = "capitulation_candidate"
    elif panic is not None and panic >= 70:
        state = "panic"
    elif pressure is not None and pressure >= 60:
        state = "stress_building"
    else:
        state = "normal"
    explanations = {
        "normal": "No broad technical fear condition",
        "stress_building": "Persistent weakness, but selling is not climactic",
        "panic": "Selling pressure is extreme; exhaustion is not established",
        "capitulation_candidate": "Independent price, volume/range, volatility and relative signals are extreme",
        "exhaustion_emerging": "Climactic selling is showing early reversal evidence",
        "confirmed_exhaustion": "Climactic selling plus multiple stabilization signals",
    }
    return {
        "model_version": "capitulation-v1",
        "state": state,
        "interpretation": explanations[state],
        "scores": {
            "pressure": _round(pressure, 1),
            "panic": _round(panic, 1),
            "exhaustion": _round(exhaustion, 1),
            "confidence": _round(coverage, 1),
        },
        "families": {key: _round(value, 1) for key, value in families.items()},
        "percentiles": {key: _round(value, 1) for key, value in pct.items()},
        "path_shape": {
            "volatility_concentration_ratio_20d": _round(latest["vcr_20d"]),
            "trend_ratio_20d": _round(latest["trend_ratio_20d"]),
            "negative_session_share_20d": _round(latest["negative_consistency_20d"]),
            "downside_variance_share_20d": _round(latest["downside_share_20d"]),
        },
        "intraday": {
            "gap_pct": _round(latest["gap"] * 100 if latest["gap"] is not None else None, 2),
            "true_range_vs_atr": _round(latest["true_range_atr"], 2),
            "close_location": _round(latest["close_location"], 2),
        },
        "confirmation": confirmation,
        "independent_extreme_families": extreme_families,
        "policy": "A severe decline alone is not confirmed capitulation; stabilization evidence is required.",
    }


def _regimes(trend_z: float | None, stretch_z: float | None) -> tuple[str, str, str]:
    if trend_z is None or stretch_z is None:
        return "unavailable", "unavailable", "Insufficient price history"
    trend = "strong" if trend_z >= 1.25 else "weak" if trend_z <= -1.25 else "stable"
    stretch = "extended" if stretch_z >= 2 else "washed_out" if stretch_z <= -2 else "normal"
    if stretch == "extended":
        setup = "extended"
    elif stretch == "washed_out":
        setup = "washed_out"
    elif trend_z >= 0.75:
        setup = "improving"
    elif trend_z <= -0.75:
        setup = "deteriorating"
    else:
        setup = "neutral"
    phrase = {
        "extended": "Strong price pressure, but unusually extended",
        "washed_out": "Unusually depressed versus its own trend",
        "improving": "Relative trend is improving",
        "deteriorating": "Relative trend is deteriorating",
        "neutral": "No unusual technical condition",
    }[setup]
    return trend, stretch, phrase


def calculate_snapshot(
    ticker: str,
    rows: list[dict],
    *,
    benchmark_rows: list[dict] | None,
    benchmark: str,
    source: str,
) -> dict:
    rows = sorted({row["date"]: row for row in rows}.values(), key=lambda row: row["date"])
    closes = [float(row["close"]) for row in rows]
    volumes = [_finite(row.get("volume")) for row in rows]
    ret20, ret20_z = _rolling_return_z(closes, 20)
    ret60, ret60_z = _rolling_return_z(closes, 60)
    ret120, ret120_z = _rolling_return_z(closes, 120)
    distance50, distance50_z = _rolling_distance_z(closes, 50)
    distance200, distance200_z = _rolling_distance_z(closes, 200)
    relative60, relative60_z = _relative_strength_z(rows, benchmark_rows, 60)
    volatility20, volatility_z = _rolling_volatility_z(closes, 20)
    drawdown, drawdown_z = _rolling_drawdown_z(closes, 252)
    volume_surprise, volume_z = _rolling_volume_z(volumes, 20)
    trend_z = _weighted_z(
        [(ret20_z, 0.20), (ret60_z, 0.25), (ret120_z, 0.20), (relative60_z, 0.35)]
    )
    stretch_z = _weighted_z([(distance50_z, 0.55), (distance200_z, 0.45)])
    capitulation = _capitulation_snapshot(rows, relative60_z)
    trend_regime, stretch_regime, interpretation = _regimes(trend_z, stretch_z)
    quality = "ready" if len(rows) >= 260 else "limited" if len(rows) >= 120 else "unavailable"
    has_ohlc = all(_finite(rows[-1].get(key)) is not None for key in ("open", "high", "low", "close"))
    data_grade = (
        "A" if len(rows) >= 756 and has_ohlc and volumes[-1] is not None
        else "B" if len(rows) >= 260 and has_ohlc
        else "C" if len(rows) >= 120
        else "D"
    )
    return {
        "ticker": ticker,
        "as_of": rows[-1]["date"],
        "model_version": MODEL_VERSION,
        "source": source,
        "benchmark": benchmark,
        "data_quality": quality,
        "data_grade": data_grade,
        "data_grade_reason": (
            "3y+ adjusted OHLCV and benchmark coverage"
            if data_grade == "A"
            else "1y+ adjusted OHLC with partial volume or benchmark coverage"
            if data_grade == "B"
            else "Limited history or close-only source"
            if data_grade == "C"
            else "Insufficient technical history"
        ),
        "observation_count": len(rows),
        "latest": {
            "open": _round(rows[-1].get("open"), 4),
            "high": _round(rows[-1].get("high"), 4),
            "low": _round(rows[-1].get("low"), 4),
            "close": _round(closes[-1], 4),
            "volume": _round(volumes[-1], 0),
        },
        "scores": {
            "trend_z": _round(trend_z),
            "stretch_z": _round(stretch_z),
            "relative_strength_60d_z": _round(relative60_z),
            "volume_surprise_z": _round(volume_z),
            "volatility_regime_z": _round(volatility_z),
            "drawdown_z": _round(drawdown_z),
        },
        "measures": {
            "return_20d_pct": _round(ret20 * 100 if ret20 is not None else None, 2),
            "return_60d_pct": _round(ret60 * 100 if ret60 is not None else None, 2),
            "return_120d_pct": _round(ret120 * 100 if ret120 is not None else None, 2),
            "relative_return_60d_pct": _round(relative60 * 100 if relative60 is not None else None, 2),
            "distance_50d_pct": _round(distance50 * 100 if distance50 is not None else None, 2),
            "distance_200d_pct": _round(distance200 * 100 if distance200 is not None else None, 2),
            "realized_volatility_20d_pct": _round(
                volatility20 * 100 if volatility20 is not None else None, 2
            ),
            "drawdown_1y_pct": _round(drawdown * 100 if drawdown is not None else None, 2),
            "volume_vs_20d_log": _round(volume_surprise),
        },
        "regime": {
            "trend": trend_regime,
            "stretch": stretch_regime,
            "setup": (
                "extended"
                if stretch_regime == "extended"
                else "washed_out"
                if stretch_regime == "washed_out"
                else "improving"
                if trend_z is not None and trend_z >= 0.75
                else "deteriorating"
                if trend_z is not None and trend_z <= -0.75
                else "neutral"
            ),
            "interpretation": interpretation,
        },
        "capitulation": capitulation,
        "history": [[row["date"], _round(row["close"], 4)] for row in rows[-260:]],
    }


def _registry_rows() -> list[dict]:
    holdings = load_registry().get("holdings") or {}
    return [
        {
            "ticker": str(ticker).upper(),
            "market": str(row.get("market") or "US").upper(),
            "exchange": str(row.get("exchange") or ""),
            "quote_ticker": row.get("quote_ticker") or row.get("display_ticker") or ticker,
        }
        for ticker, row in sorted(holdings.items())
        if not str(ticker).upper().endswith(".CVR")
    ]


def write_summary(payload: dict) -> None:
    current = payload.get("by_ticker") or {}
    summary_payload = {
        key: value for key, value in payload.items() if key not in {"by_ticker", "errors"}
    }
    summary_payload.setdefault("summary", {})["fresh"] = sum(
        1 for row in current.values()
        if row.get("model_version") == MODEL_VERSION
        and row.get("fetch_status") != "preserved_after_fetch_failure"
    )
    summary_payload["by_ticker"] = {
        ticker: {key: value for key, value in row.items() if key != "history"}
        for ticker, row in current.items()
    }
    _write_json_atomic(SUMMARY_OUTPUT, summary_payload)


def build(*, limit: int = 0, workers: int = 12, tickers: set[str] | None = None) -> dict:
    prior = {}
    if OUTPUT.exists():
        try:
            prior = json.loads(OUTPUT.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            prior = {}
    registry = _registry_rows()
    if tickers:
        registry = [row for row in registry if row["ticker"] in tickers]
    if limit:
        registry = registry[:limit]

    markets = sorted({row["market"] for row in registry})
    benchmark_history: dict[str, list[dict]] = {}
    benchmark_sources: dict[str, str] = {}
    benchmark_errors: dict[str, str] = {}
    for market in markets:
        symbol = BENCHMARKS.get(market, "SPY")
        try:
            benchmark_history[market], benchmark_sources[market] = fetch_yahoo_history(symbol)
        except Exception as exc:
            benchmark_errors[market] = str(exc)

    selected_tickers = set(tickers or set())
    current: dict[str, dict] = dict(prior.get("by_ticker") or {}) if selected_tickers else {}
    errors: dict[str, str] = {}

    def fetch_one(meta: dict):
        history, source = fetch_history(
            meta["ticker"], meta["market"], meta["exchange"], meta.get("quote_ticker")
        )
        benchmark = BENCHMARKS.get(meta["market"], "SPY")
        return calculate_snapshot(
            meta["ticker"],
            history,
            benchmark_rows=benchmark_history.get(meta["market"]),
            benchmark=benchmark,
            source=source,
        )

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(fetch_one, meta): meta for meta in registry}
        for future in as_completed(futures):
            meta = futures[future]
            ticker = meta["ticker"]
            try:
                current[ticker] = future.result()
                print(f"OK {ticker}: {current[ticker]['regime']['setup']}")
            except Exception as exc:
                errors[ticker] = str(exc)
                old = ((prior.get("by_ticker") or {}).get(ticker))
                if old:
                    preserved = dict(old)
                    preserved["fetch_status"] = "preserved_after_fetch_failure"
                    preserved["fetch_error"] = str(exc)[:240]
                    current[ticker] = preserved
                print(f"WARN {ticker}: {exc}", file=sys.stderr)

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    setups: dict[str, int] = {}
    fear_states: dict[str, int] = {}
    for row in current.values():
        setup = str((row.get("regime") or {}).get("setup") or "unavailable")
        setups[setup] = setups.get(setup, 0) + 1
        fear_state = str((row.get("capitulation") or {}).get("state") or "unavailable")
        fear_states[fear_state] = fear_states.get(fear_state, 0) + 1
    market_context = {
        "internal": None,
        "cnn_reference": {
            "label": "CNN Fear & Greed",
            "url": "https://www.cnn.com/markets/fear-and-greed",
            "status": "reference_link",
            "note": "External market-sentiment reference; not blended into stock scores.",
        },
    }
    us_benchmark = benchmark_history.get("US")
    if us_benchmark:
        try:
            spy_snapshot = calculate_snapshot(
                "SPY",
                us_benchmark,
                benchmark_rows=None,
                benchmark="SPY",
                source=benchmark_sources.get("US", "yahoo:SPY"),
            )
            market_context["internal"] = {
                "label": "US market fear",
                "as_of": spy_snapshot.get("as_of"),
                "source": spy_snapshot.get("source"),
                "scores": (spy_snapshot.get("capitulation") or {}).get("scores"),
                "families": (spy_snapshot.get("capitulation") or {}).get("families"),
                "state": (spy_snapshot.get("capitulation") or {}).get("state"),
                "interpretation": (spy_snapshot.get("capitulation") or {}).get("interpretation"),
            }
        except Exception as exc:
            market_context["internal_error"] = str(exc)[:240]
    payload = {
        "generated_at": generated_at,
        "model_version": MODEL_VERSION,
        "methodology": {
            "purpose": "Timing and risk overlay only; never changes valuation readiness.",
            "history_window": "up to five years of adjusted daily OHLCV",
            "capitulation_model": {
                "scores": ["pressure", "panic", "exhaustion", "confidence"],
                "families": [
                    "price_dislocation",
                    "selling_climax",
                    "volatility_stress",
                    "relative_path_stress",
                ],
                "etf_dashboard_reuse": [
                    "historical percentiles",
                    "volatility concentration ratio",
                    "daily-versus-weekly trend ratio",
                    "data grades and explicit freshness",
                ],
                "confirmation_required": True,
            },
            "trend_weights": {
                "return_20d_z": 0.20,
                "return_60d_z": 0.25,
                "return_120d_z": 0.20,
                "sector_or_market_relative_60d_z": 0.35,
            },
            "stretch_weights": {"distance_50d_z": 0.55, "distance_200d_z": 0.45},
            "z_clip": 4.0,
        },
        "summary": {
            "requested": len(registry),
            "available": len(current),
            "fresh": sum(
                1 for row in current.values()
                if row.get("model_version") == MODEL_VERSION
                and row.get("fetch_status") != "preserved_after_fetch_failure"
            ),
            "failed": len(errors),
            "setups": setups,
            "fear_states": fear_states,
        },
        "market_context": market_context,
        "benchmark_errors": benchmark_errors,
        "errors": errors,
        "by_ticker": dict(sorted(current.items())),
    }
    _write_json_atomic(OUTPUT, payload)
    write_summary(payload)
    print(f"Wrote {OUTPUT} ({len(current)} signals, {len(errors)} fetch failures)")
    print(f"Wrote {SUMMARY_OUTPUT} (compact holdings overlay)")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tickers", nargs="*", help="Optional ticker subset")
    parser.add_argument("--limit", type=int, default=0, help="Limit registry rows for a smoke run")
    parser.add_argument("--workers", type=int, default=12, help="Concurrent free-source requests")
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Rebuild the compact overlay from the existing full signal artifact",
    )
    args = parser.parse_args()
    if args.summary_only:
        payload = json.loads(OUTPUT.read_text(encoding="utf-8"))
        write_summary(payload)
        print(f"Wrote {SUMMARY_OUTPUT} from {OUTPUT}")
        return 0
    build(
        limit=max(0, args.limit),
        workers=max(1, args.workers),
        tickers={ticker.upper() for ticker in args.tickers} or None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
