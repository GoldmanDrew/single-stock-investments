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
MODEL_VERSION = "technical-z-v1"
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


def _request(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as response:
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
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    adjusted = (((result.get("indicators") or {}).get("adjclose") or [{}])[0]).get("adjclose") or []
    rows = []
    for index, timestamp in enumerate(timestamps):
        close = _finite(adjusted[index] if index < len(adjusted) else None)
        if close is None:
            close = _finite(closes[index] if index < len(closes) else None)
        if close is None or close <= 0:
            continue
        rows.append(
            {
                "date": datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d"),
                "close": close,
                "volume": _finite(volumes[index] if index < len(volumes) else None),
            }
        )
    if len(rows) < 120:
        raise ValueError(f"Yahoo returned {len(rows)} usable rows")
    return rows, f"yahoo:{symbol}"


def fetch_history(ticker: str, market: str, exchange: str, quote_ticker: str | None) -> tuple[list[dict], str]:
    errors = []
    stooq = stooq_symbol(quote_ticker or ticker, market)
    if stooq:
        try:
            return fetch_stooq_history(stooq)
        except Exception as exc:  # fail over to the second free source
            errors.append(f"stooq={exc}")
    yahoo = yahoo_symbol_for(quote_ticker or ticker, market, exchange)
    try:
        return fetch_yahoo_history(yahoo)
    except Exception as exc:
        errors.append(f"yahoo={exc}")
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
    for index, close in enumerate(closes):
        if index + 1 < window:
            series.append(None)
            continue
        average = statistics.fmean(closes[index - window + 1 : index + 1])
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
    for index, close in enumerate(closes):
        start = max(0, index - window + 1)
        peak = max(closes[start : index + 1])
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
    trend_regime, stretch_regime, interpretation = _regimes(trend_z, stretch_z)
    quality = "ready" if len(rows) >= 260 else "limited" if len(rows) >= 120 else "unavailable"
    return {
        "ticker": ticker,
        "as_of": rows[-1]["date"],
        "model_version": MODEL_VERSION,
        "source": source,
        "benchmark": benchmark,
        "data_quality": quality,
        "observation_count": len(rows),
        "latest": {
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
    summary_payload["by_ticker"] = {
        ticker: {key: value for key, value in row.items() if key != "history"}
        for ticker, row in current.items()
    }
    SUMMARY_OUTPUT.write_text(
        json.dumps(summary_payload, separators=(",", ":"), ensure_ascii=False),
        encoding="utf-8",
    )


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
    benchmark_errors: dict[str, str] = {}
    for market in markets:
        symbol = BENCHMARKS.get(market, "SPY")
        try:
            benchmark_history[market], _ = fetch_yahoo_history(symbol)
        except Exception as exc:
            benchmark_errors[market] = str(exc)

    current: dict[str, dict] = {}
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
    for row in current.values():
        setup = str((row.get("regime") or {}).get("setup") or "unavailable")
        setups[setup] = setups.get(setup, 0) + 1
    payload = {
        "generated_at": generated_at,
        "model_version": MODEL_VERSION,
        "methodology": {
            "purpose": "Timing and risk overlay only; never changes valuation readiness.",
            "history_window": "up to five years of daily closes",
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
                1 for row in current.values() if row.get("fetch_status") != "preserved_after_fetch_failure"
            ),
            "failed": len(errors),
            "setups": setups,
        },
        "benchmark_errors": benchmark_errors,
        "errors": errors,
        "by_ticker": dict(sorted(current.items())),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
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
