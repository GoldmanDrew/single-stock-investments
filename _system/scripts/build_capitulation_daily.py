#!/usr/bin/env python3
"""Always-on DAILY-bar capitulation model for the risk page's pressure rails.

Why this exists
---------------
The published "mechanical pressure / exhaustion" rails are a model of how far
into capitulation a selloff has progressed. That model lives in
``_system/scripts/criticality/flow_stress.py`` and is driven by a Databento
streaming monitor that runs on the owner's machine over intraday MINUTE bars.
When that machine is off, the rails are empty -- they were empty for a week
from 2026-08-03.

This builder runs the SAME model on DAILY bars inside CI, so the panel always
has an honest reading. The intraday feed becomes an enrichment (faster, finer)
rather than a single point of failure.

No forked math
--------------
Every score here comes from ``flow_stress.calculate_flow_snapshot`` and every
ladder transition from that same function plus
``flow_stress.apply_state_hysteresis``. This module contains NO copy of the
component weights and NO copy of the state thresholds. A second copy would
drift; ``test_build_capitulation_daily.py`` asserts the two agree bar-for-bar
on a synthetic series.

Reinterpretations on daily bars (each one deliberate and documented)
-------------------------------------------------------------------
``calculate_flow_snapshot`` expresses every window as a COUNT OF BARS, so the
reinterpretation is exactly "bar = session" instead of "bar = minute":

1. return_stress_z    -- 5-minute return vs the 30-minute per-bar sigma
                      -> 5-SESSION return vs the 30-SESSION per-bar sigma.
2. vol acceleration   -- realized vol over 5 vs 30 minutes
                      -> realized vol over 5 vs 30 SESSIONS.
3. downside variance share and negative-return share
                      -- last 15 minutes -> last 15 SESSIONS.
4. volume z / range z -- last bar vs the prior 60 minutes
                      -> last SESSION vs the prior 60 SESSIONS.
5. positive_interval  -- close > open within the minute
                      -> close > open within the SESSION.
6. closed_upper_half / close_location
                      -- close location inside the current MINUTE's high-low
                      -> close location inside the DAY's high-low range.
7. volatility_decelerating / selling_decelerating
                      -- 5-minute realized vol / 5-minute return vs the prior
                         5-minute block -> the same over 5-SESSION blocks.
8. volume_cooling     -- today's volume below the max of the last 10 MINUTES
                      -> below the max of the last 10 SESSIONS.

Nothing is reweighted, because nothing had to be dropped: all six pressure
components, all four panic components and all five exhaustion confirmations are
computable on daily bars.

The one genuinely intraday output is OMITTED rather than silently reinterpreted:
``vol_target`` (the vol-targeting exposure-reduction proxy) compares an
ANNUALIZED realized vol against 8/10/12% targets, and ``flow_stress``
annualizes with ``MINUTES_PER_YEAR``. That constant cancels out of every score
this module publishes -- ``volatility_acceleration`` is a ratio of two
annualized vols, and ``minute_sigma = rv30 / sqrt(MINUTES_PER_YEAR)`` is just
the per-bar standard deviation -- but it does NOT cancel out of ``vol_target``.
Republishing that block off daily bars would state a wrong number in percent,
so this payload does not carry it at all.

Prices are dividend-adjusted (Yahoo adjclose ratio applied to OHLC), matching
``build_technical_signals.fetch_yahoo_history``, so a distribution date is not
read as a one-day selloff.

Drawdown context -- the honesty property
----------------------------------------
Capitulation only means something inside a selloff. "Exhaustion 95" at
all-time highs is not a bottom signal, it is a quiet up-day: four of the five
exhaustion confirmations (close in the upper half, vol decelerating, selling
decelerating, volume cooling) fire on any calm advance. The current dashboard
shows exactly that nonsense today.

So every row carries ``drawdown_pct`` from the trailing 252-session closing
high, ``days_since_high``, and ``in_drawdown`` (threshold: drawdown at or below
-5.0%, ``IN_DRAWDOWN_THRESHOLD_PCT``), and ``exhaustion_meaningful`` is False
unless BOTH:

* the raw (pre-hysteresis) ladder state is at least ``stress`` -- i.e. panic
  cleared the ladder's stress threshold. This is expressed as a STATE_RANK
  comparison against the imported ladder rather than a copied ``panic >= 70``,
  so the two can never disagree; and
* the symbol is in drawdown.

``exhaustion_meaningful_reason`` always names which gate decided.

Outputs (``--output-dir``, default ``dashboard/data``)
-----------------------------------------------------
* ``capitulation_daily.json``       -- market / symbols / sectors snapshot.
* ``capitulation_daily_history.jsonl`` -- one market-level (SPY) row per date,
  idempotent by date, so the ladder can be charted over time.
* ``capitulation_daily_state.json``  -- hysteresis memory, one
  ``apply_state_hysteresis``-shaped record per symbol plus the ``as_of`` it was
  last advanced on. Dwell is counted in TRADING DATES, so re-running the
  builder twice in one day cannot walk the ladder twice.

Failure policy: a per-symbol fetch failure preserves the prior published row
and stamps it ``quality_state='stale'`` /
``fetch_status='preserved_after_fetch_failure'`` (same contract as
``build_criticality_signals.py``). The process always exits 0: this lane also
commits the technical snapshots, and a vendor hiccup must not skip that.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_technical_signals import _finite, _request  # noqa: E402
from criticality.flow_stress import (  # noqa: E402
    STATE_RANK,
    apply_state_hysteresis,
    calculate_flow_snapshot,
)

SCHEMA_VERSION = 1
MODEL_VERSION = "capitulation-daily-v1"
OUTPUT_NAME = "capitulation_daily.json"
HISTORY_NAME = "capitulation_daily_history.jsonl"
STATE_NAME = "capitulation_daily_state.json"
DEFAULT_OUTPUT_DIR = ROOT / "dashboard" / "data"

MARKET_SYMBOL = "SPY"
SOURCE = "yahoo:chart-v8:1d"
BASIS = (
    "daily bars (Yahoo) - reinterpretation of the intraday forced-flow model; "
    "see module docstring"
)

# ~2 years of calendar days. Yahoo returns ~500 sessions, which covers the
# 252-session drawdown window with room to spare (the model itself only reads
# the last ~61 bars).
LOOKBACK_DAYS = 365 * 2 + 30
MIN_BARS = 120
DRAWDOWN_WINDOW = 252
IN_DRAWDOWN_THRESHOLD_PCT = -5.0
# Exhaustion is only readable as capitulation once the ladder itself calls the
# tape stressed. Derived from the imported ladder, never from a copied number.
MEANINGFUL_MIN_RANK = STATE_RANK["stress"]

UNIVERSE = {
    "SPY": {"name": "S&P 500", "scope": "market"},
    "QQQ": {"name": "Nasdaq 100", "scope": "market"},
    "IWM": {"name": "Russell 2000", "scope": "market"},
    "DIA": {"name": "Dow Jones", "scope": "market"},
    "EWJ": {"name": "Japan", "scope": "market"},
    "VXX": {"name": "Short-term VIX futures ETN", "scope": "market"},
    "HYG": {"name": "High-yield credit", "scope": "market"},
    "LQD": {"name": "Investment-grade credit", "scope": "market"},
    "TLT": {"name": "Long Treasury", "scope": "market"},
    "UUP": {"name": "US dollar", "scope": "market"},
    "EFA": {"name": "Developed markets ex-US", "scope": "market"},
    "EEM": {"name": "Emerging markets", "scope": "market"},
    "XLB": {"name": "Materials", "scope": "sector"},
    "XLC": {"name": "Communication Services", "scope": "sector"},
    "XLE": {"name": "Energy", "scope": "sector"},
    "XLF": {"name": "Financials", "scope": "sector"},
    "XLI": {"name": "Industrials", "scope": "sector"},
    "XLK": {"name": "Technology", "scope": "sector"},
    "XLP": {"name": "Consumer Staples", "scope": "sector"},
    "XLRE": {"name": "Real Estate", "scope": "sector"},
    "XLU": {"name": "Utilities", "scope": "sector"},
    "XLV": {"name": "Health Care", "scope": "sector"},
    "XLY": {"name": "Consumer Discretionary", "scope": "sector"},
}
SECTORS = {symbol for symbol, meta in UNIVERSE.items() if meta["scope"] == "sector"}


def _dump(payload) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def fetch_daily_history(symbol: str) -> list[dict]:
    """Dividend-adjusted daily OHLCV bars, oldest first, from Yahoo chart v8.

    ``build_technical_signals.fetch_yahoo_history`` takes only a symbol and a
    fixed 5-year lookback, so this builds its own chart-v8 URL over the shorter
    window while reusing that module's ``_request`` (User-Agent, timeout).
    """
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
    results = ((payload.get("chart") or {}).get("result")) or []
    if not results:
        raise ValueError(f"Yahoo returned no result for {symbol}")
    result = results[0]
    timestamps = result.get("timestamp") or []
    indicators = result.get("indicators") or {}
    quote = (indicators.get("quote") or [{}])[0]
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    adjusted = ((indicators.get("adjclose") or [{}])[0]).get("adjclose") or []

    def pick(values, index):
        return _finite(values[index] if index < len(values) else None)

    rows = []
    for index, timestamp in enumerate(timestamps):
        raw_close = pick(closes, index)
        close = pick(adjusted, index) or raw_close
        if close is None or close <= 0:
            continue
        ratio = close / raw_close if raw_close and raw_close > 0 else 1.0

        def scaled(values):
            value = pick(values, index)
            return None if value is None else value * ratio

        rows.append(
            {
                "date": datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime(
                    "%Y-%m-%d"
                ),
                "open": scaled(opens),
                "high": scaled(highs),
                "low": scaled(lows),
                "close": close,
                "volume": pick(volumes, index),
            }
        )
    if len(rows) < MIN_BARS:
        raise ValueError(f"Yahoo returned {len(rows)} usable daily bars for {symbol}")
    return rows


def drawdown_context(bars: list[dict], window: int = DRAWDOWN_WINDOW) -> dict:
    """Drawdown from the trailing closing high, plus how long ago that high was."""
    closes = [float(row["close"]) for row in bars if _finite(row.get("close"))]
    if not closes:
        return {
            "drawdown_pct": None,
            "days_since_high": None,
            "in_drawdown": False,
            "drawdown_window_sessions": 0,
        }
    tail = closes[-window:]
    peak = max(tail)
    peak_index = len(tail) - 1 - tail[::-1].index(peak)
    drawdown = (tail[-1] / peak - 1.0) * 100.0 if peak > 0 else 0.0
    return {
        "drawdown_pct": round(drawdown, 2),
        "days_since_high": len(tail) - 1 - peak_index,
        "in_drawdown": bool(drawdown <= IN_DRAWDOWN_THRESHOLD_PCT),
        "drawdown_window_sessions": len(tail),
    }


def exhaustion_meaning(
    raw_state: str,
    panic: float | None,
    drawdown_pct: float | None,
    in_drawdown: bool,
) -> tuple[bool, str]:
    """Is a high exhaustion score readable as capitulation, or is it a calm day?

    Gate 1 is the ladder itself: unless the raw state reached ``stress`` the
    panic score never cleared the ladder's stress threshold, and the exhaustion
    confirmations are just describing an ordinary session. Comparing STATE_RANK
    rather than copying ``panic >= 70`` keeps this in lockstep with
    ``flow_stress``.

    Gate 2 is drawdown: there is nothing to capitulate out of at the highs.
    """
    rank = STATE_RANK.get(raw_state, 0)
    panic_text = "n/a" if panic is None else f"{panic:.1f}"
    if rank < MEANINGFUL_MIN_RANK:
        return False, (
            f"panic {panic_text} did not reach the ladder's stress threshold "
            f"(raw state '{raw_state}'); these confirmations describe routine "
            "stabilization, not capitulation"
        )
    if not in_drawdown:
        drawdown_text = "n/a" if drawdown_pct is None else f"{drawdown_pct:.2f}%"
        return False, (
            f"drawdown {drawdown_text} is shallower than "
            f"{IN_DRAWDOWN_THRESHOLD_PCT:.1f}% off the "
            f"{DRAWDOWN_WINDOW}-session high; no selloff to capitulate from"
        )
    return True, (
        f"panic {panic_text} cleared the stress threshold while "
        f"{drawdown_pct:.2f}% off the {DRAWDOWN_WINDOW}-session high"
    )


def calculate_symbol(symbol: str, bars: list[dict], prior_state: dict | None) -> dict:
    """One published row: flow_stress scores + drawdown context + dwell state."""
    ordered = sorted(bars, key=lambda row: str(row.get("date") or ""))
    meta = UNIVERSE.get(symbol, {"name": symbol, "scope": "market"})
    snapshot = calculate_flow_snapshot(
        symbol,
        ordered,
        scope="sector" if symbol in SECTORS else meta["scope"],
        source=SOURCE,
        entitlement_mode="eod",
    )
    scores = snapshot["scores"]
    raw_state = snapshot["raw_state"]
    as_of = snapshot["as_of"]

    prior_state = dict(prior_state or {})
    if prior_state.get("as_of") == as_of and prior_state.get("state") in STATE_RANK:
        # Same trading date as the last advance: dwell is counted in sessions,
        # so a re-run must not walk the ladder a second time.
        state = str(prior_state["state"])
        memory = {
            "state": state,
            "candidate": str(prior_state.get("candidate") or state),
            "count": int(prior_state.get("count") or 0),
        }
    else:
        state, memory = apply_state_hysteresis(raw_state, prior_state)
    memory = dict(memory)
    memory["as_of"] = as_of

    context = drawdown_context(ordered)
    meaningful, reason = exhaustion_meaning(
        raw_state,
        scores.get("panic"),
        context["drawdown_pct"],
        context["in_drawdown"],
    )
    confirmations = dict(snapshot["confirmation"])
    row = {
        "symbol": symbol,
        "name": meta["name"],
        "scope": "sector" if symbol in SECTORS else meta["scope"],
        "as_of": as_of,
        "state": state,
        "state_rank": STATE_RANK[state],
        "raw_state": raw_state,
        "raw_state_rank": STATE_RANK[raw_state],
        "pressure": scores["pressure"],
        "panic": scores["panic"],
        "exhaustion": scores["exhaustion"],
        "exhaustion_meaningful": meaningful,
        "exhaustion_meaningful_reason": reason,
        "confirmations": confirmations,
        "confirmation_count": sum(bool(value) for value in confirmations.values()),
        "drawdown_pct": context["drawdown_pct"],
        "days_since_high": context["days_since_high"],
        "in_drawdown": context["in_drawdown"],
        "drawdown_window_sessions": context["drawdown_window_sessions"],
        "features": snapshot["features"],
        "bar_count": snapshot["bar_count"],
        "source": SOURCE,
        "entitlement_mode": "eod",
        "quality_state": snapshot["quality_state"],
        "fetch_status": "fresh",
    }
    return {"row": row, "state_memory": memory}


def _prior_rows(payload: dict) -> dict:
    """Index the previously published rows by symbol so failures can preserve."""
    rows: dict[str, dict] = {}
    market = payload.get("market")
    if isinstance(market, dict) and market.get("symbol"):
        rows[str(market["symbol"])] = market
    for key in ("symbols", "sectors"):
        for row in payload.get(key) or []:
            if isinstance(row, dict) and row.get("symbol"):
                rows[str(row["symbol"])] = row
    return rows


def _preserve(prior: dict, error: str) -> dict:
    preserved = dict(prior)
    preserved["quality_state"] = "stale"
    preserved["fetch_status"] = "preserved_after_fetch_failure"
    preserved["fetch_error"] = str(error)[:240]
    return preserved


def read_history(path: Path) -> list[dict]:
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


def merge_history(prior_rows: list[dict], row: dict | None) -> list[dict]:
    """Upsert one market-level row, keyed by date -- idempotent across re-runs."""
    by_date = {str(item["date"]): item for item in prior_rows if item.get("date")}
    if row and row.get("date"):
        by_date[str(row["date"])] = row
    return [by_date[key] for key in sorted(by_date)]


def history_row(row: dict, generated_at: str) -> dict | None:
    if not row or not row.get("as_of"):
        return None
    return {
        "date": row["as_of"],
        "symbol": row.get("symbol"),
        "generated_at": generated_at,
        "model_version": MODEL_VERSION,
        "state": row.get("state"),
        "state_rank": row.get("state_rank"),
        "raw_state": row.get("raw_state"),
        "pressure": row.get("pressure"),
        "panic": row.get("panic"),
        "exhaustion": row.get("exhaustion"),
        "exhaustion_meaningful": row.get("exhaustion_meaningful"),
        "confirmation_count": row.get("confirmation_count"),
        "drawdown_pct": row.get("drawdown_pct"),
        "days_since_high": row.get("days_since_high"),
        "in_drawdown": row.get("in_drawdown"),
        "quality_state": row.get("quality_state"),
    }


def _sort_key(row: dict):
    return (-int(row.get("state_rank") or 0), -float(row.get("panic") or 0.0))


def build(
    *,
    output_dir: Path | None = None,
    fetcher=None,
    workers: int = 4,
    symbols: set[str] | None = None,
    dry_run: bool = False,
) -> dict:
    output_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    fetcher = fetcher or fetch_daily_history
    output_path = output_dir / OUTPUT_NAME
    history_path = output_dir / HISTORY_NAME
    state_path = output_dir / STATE_NAME

    prior_payload = _read_json(output_path)
    prior_by_symbol = _prior_rows(prior_payload)
    prior_state = _read_json(state_path)
    prior_state_by_symbol = prior_state.get("symbols") or {}

    selected = [
        symbol for symbol in UNIVERSE
        if not symbols or symbol in symbols
    ]
    rows: dict[str, dict] = {}
    state_memory: dict[str, dict] = {
        symbol: dict(value)
        for symbol, value in prior_state_by_symbol.items()
        if isinstance(value, dict)
    }
    errors: dict[str, str] = {}

    def build_one(symbol: str) -> dict:
        bars = fetcher(symbol)
        return calculate_symbol(symbol, bars, prior_state_by_symbol.get(symbol))

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(build_one, symbol): symbol for symbol in selected}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001 - never fail the lane
                errors[symbol] = str(exc)[:240]
                if symbol in prior_by_symbol:
                    rows[symbol] = _preserve(prior_by_symbol[symbol], str(exc))
                continue
            rows[symbol] = result["row"]
            state_memory[symbol] = result["state_memory"]

    generated_at = datetime.now(timezone.utc).isoformat()
    market_row = rows.get(MARKET_SYMBOL)
    as_of = (market_row or {}).get("as_of") or max(
        (row.get("as_of") or "" for row in rows.values()), default=""
    )
    stale_count = sum(
        row.get("fetch_status") == "preserved_after_fetch_failure"
        for row in rows.values()
    )
    if not rows:
        quality_state = "unavailable"
    elif market_row is None or market_row.get("fetch_status") == "preserved_after_fetch_failure":
        quality_state = "stale"
    elif errors:
        quality_state = "limited"
    else:
        quality_state = "ready"

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "model_version": MODEL_VERSION,
        "research_only": True,
        "as_of": as_of or None,
        "cadence": "daily",
        "basis": BASIS,
        "drawdown": {
            "window_sessions": DRAWDOWN_WINDOW,
            "in_drawdown_threshold_pct": IN_DRAWDOWN_THRESHOLD_PCT,
        },
        "market": market_row,
        "symbols": sorted(
            (row for symbol, row in rows.items() if symbol not in SECTORS),
            key=_sort_key,
        ),
        "sectors": sorted(
            (row for symbol, row in rows.items() if symbol in SECTORS),
            key=_sort_key,
        ),
        "coverage": {
            "symbols_ok": sum(
                row.get("fetch_status") != "preserved_after_fetch_failure"
                for row in rows.values()
            ),
            "symbols_failed": len(errors),
            "symbols_requested": len(selected),
            "symbols_stale": stale_count,
            "failures": dict(sorted(errors.items())),
        },
        "quality_state": quality_state,
        "policy": "Pressure and exhaustion require independent confirmation.",
    }

    history_rows = merge_history(
        read_history(history_path),
        history_row(market_row, generated_at) if market_row else None,
    )
    history_text = "".join(_dump(item) + "\n" for item in history_rows)
    state_payload = {
        "schema_version": SCHEMA_VERSION,
        "model_version": MODEL_VERSION,
        "updated_at": generated_at,
        "symbols": dict(sorted(state_memory.items())),
    }

    if not dry_run:
        _write_text_atomic(output_path, _dump(payload) + "\n")
        _write_text_atomic(history_path, history_text)
        _write_text_atomic(state_path, _dump(state_payload) + "\n")

    return {
        "payload": payload,
        "history_rows": history_rows,
        "history_text": history_text,
        "state": state_payload,
        "output_path": output_path,
        "history_path": history_path,
        "state_path": state_path,
        "dry_run": dry_run,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the daily capitulation model")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--symbols",
        help="Optional comma-separated subset, for example SPY,QQQ,XLK",
    )
    args = parser.parse_args()
    subset = (
        {item.strip().upper() for item in args.symbols.split(",") if item.strip()}
        if args.symbols else None
    )
    try:
        result = build(
            output_dir=args.output_dir,
            workers=args.workers,
            symbols=subset,
            dry_run=args.dry_run,
        )
    except Exception as exc:  # noqa: BLE001 - this lane also commits other artifacts
        print(f"[warn] capitulation-daily: build failed: {str(exc)[:240]}")
        return 0
    payload = result["payload"]
    market = payload.get("market") or {}
    print(
        _dump(
            {
                "as_of": payload.get("as_of"),
                "quality_state": payload.get("quality_state"),
                "coverage": {
                    key: value
                    for key, value in payload["coverage"].items()
                    if key != "failures"
                },
                "market": {
                    "symbol": market.get("symbol"),
                    "state": market.get("state"),
                    "raw_state": market.get("raw_state"),
                    "pressure": market.get("pressure"),
                    "panic": market.get("panic"),
                    "exhaustion": market.get("exhaustion"),
                    "exhaustion_meaningful": market.get("exhaustion_meaningful"),
                    "drawdown_pct": market.get("drawdown_pct"),
                    "days_since_high": market.get("days_since_high"),
                    "in_drawdown": market.get("in_drawdown"),
                },
                "dry_run": result["dry_run"],
            }
        )
    )
    if payload["coverage"]["failures"]:
        for symbol, error in payload["coverage"]["failures"].items():
            print(f"[warn] capitulation-daily: {symbol} preserved prior row: {error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
