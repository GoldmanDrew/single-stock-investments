#!/usr/bin/env python3
"""Stream Databento minute bars and publish forced-flow snapshots to the dashboard.

Required environment:
  DATABENTO_API_KEY
  MARKET_RISK_INGEST_URL
  MARKET_RISK_INGEST_TOKEN
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import math
import os
import secrets
import statistics
import threading
import time
import urllib.request
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

from criticality.flow_stress import apply_state_hysteresis, calculate_flow_snapshot

DEFAULT_SYMBOLS = (
    "SPY", "QQQ", "IWM", "DIA", "EWJ", "VXX", "HYG", "LQD", "TLT", "UUP", "EFA", "EEM",
    "XLB", "XLC", "XLE", "XLF", "XLI", "XLK",
    "XLP", "XLRE", "XLU", "XLV", "XLY",
)
SECTORS = {
    "XLB", "XLC", "XLE", "XLF", "XLI", "XLK",
    "XLP", "XLRE", "XLU", "XLV", "XLY",
}


def publish(url: str, token: str, snapshots: list[dict], components: list[dict] | None = None) -> dict:
    body = json.dumps({
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "flow": snapshots,
        "components": components or [],
    }).encode("utf-8")
    timestamp = str(int(time.time()))
    nonce = secrets.token_hex(16)
    signed = timestamp.encode("ascii") + b"\n" + nonce.encode("ascii") + b"\n" + body
    signature = hmac.new(token.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Market-Risk-Timestamp": timestamp,
            "X-Market-Risk-Nonce": nonce,
            "X-Market-Risk-Signature": signature,
            "User-Agent": "MagisMarketRiskMonitor/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _quote_price(value, scale: float) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not number or number >= 9.22e18:
        return None
    return number / scale


def stream_liquidity(
    *, symbols: tuple[str, ...], dataset: str, schema: str, stype_in: str,
    quotes: dict[str, dict], lock: threading.Lock,
) -> None:
    """Maintain a best-bid/offer cache in a separate Databento live session."""
    import databento as db
    import databento_dbn as dbn

    while True:
        try:
            client = db.Live()
            client.subscribe(dataset=dataset, schema=schema, symbols=list(symbols), stype_in=stype_in, start=0)
            symbol_by_instrument: dict[int, str] = {}
            for record in client:
                mapped = getattr(record, "stype_out_symbol", None) or getattr(record, "stype_in_symbol", None)
                instrument_id = getattr(record, "instrument_id", None)
                if mapped:
                    if instrument_id is not None:
                        symbol_by_instrument[int(instrument_id)] = str(mapped).upper()
                    continue
                symbol = getattr(record, "symbol", None)
                if not symbol and instrument_id is not None:
                    symbol = symbol_by_instrument.get(int(instrument_id))
                if not symbol:
                    continue
                bid = _quote_price(getattr(record, "bid_px_00", None) or getattr(record, "bid_px", None), float(dbn.FIXED_PRICE_SCALE))
                ask = _quote_price(getattr(record, "ask_px_00", None) or getattr(record, "ask_px", None), float(dbn.FIXED_PRICE_SCALE))
                bid_size = getattr(record, "bid_sz_00", None)
                ask_size = getattr(record, "ask_sz_00", None)
                levels = getattr(record, "levels", None)
                if levels:
                    level = levels[0]
                    bid = bid or _quote_price(getattr(level, "bid_px", None), float(dbn.FIXED_PRICE_SCALE))
                    ask = ask or _quote_price(getattr(level, "ask_px", None), float(dbn.FIXED_PRICE_SCALE))
                    bid_size = bid_size or getattr(level, "bid_sz", None)
                    ask_size = ask_size or getattr(level, "ask_sz", None)
                if bid is None or ask is None or ask < bid:
                    continue
                mid = (bid + ask) / 2.0
                stamp = datetime.fromtimestamp(int(getattr(record, "ts_event", 0)) / 1e9, tz=timezone.utc)
                with lock:
                    quotes[str(symbol).upper()] = {
                        "symbol": str(symbol).upper(), "as_of": stamp.isoformat(),
                        "bid": bid, "ask": ask, "mid": mid,
                        "spread_bps": 0.0 if mid <= 0 else (ask - bid) / mid * 10_000.0,
                        "bid_size": None if bid_size is None else float(bid_size),
                        "ask_size": None if ask_size is None else float(ask_size),
                    }
        except Exception as exc:  # the price/volume monitor must remain independent
            print(json.dumps({"liquidity_stream_error": str(exc)[:240]}), flush=True)
            time.sleep(30)


def liquidity_components(quotes: dict[str, dict], lock: threading.Lock, symbols: tuple[str, ...], source: str) -> list[dict]:
    now = datetime.now(timezone.utc)
    with lock:
        rows = [dict(row) for row in quotes.values()]
    fresh = []
    for row in rows:
        try:
            age = (now - datetime.fromisoformat(row["as_of"])).total_seconds()
        except (ValueError, TypeError):
            continue
        if age <= 120:
            row["age_seconds"] = round(max(0.0, age), 1)
            fresh.append(row)
    spreads = [row["spread_bps"] for row in fresh]
    median_spread = statistics.median(spreads) if spreads else None
    coverage = len(fresh) / max(1, len(symbols))
    as_of = max((row["as_of"] for row in fresh), default=now.isoformat())
    aggregate = {
        "component": "databento_liquidity", "scope": "market", "symbol": "US_EQUITY",
        "as_of": as_of, "cadence": "intraday", "source": source,
        "model_version": "databento-touch-liquidity-v1", "entitlement_mode": "live",
        "quality_state": "ready" if coverage >= 0.6 else "limited",
        "score": None if median_spread is None else round(min(100.0, median_spread * 10.0), 2),
        "value": median_spread, "unit": "spread_bps", "label": "Databento top-of-book liquidity",
        "description": "Observed best-bid/offer spreads and touch sizes; separate from the OHLCV range proxy.",
        "coverage": round(coverage, 3), "fresh_symbols": len(fresh), "requested_symbols": len(symbols),
        "median_spread_bps": median_spread,
        "p95_spread_bps": sorted(spreads)[max(0, math.ceil(len(spreads) * .95) - 1)] if spreads else None,
        "quotes": sorted(fresh, key=lambda row: row["spread_bps"], reverse=True),
    }
    result = [aggregate]
    for row in fresh:
        if row["symbol"] not in SECTORS:
            continue
        result.append({
            "component": "databento_liquidity", "scope": "sector", "symbol": row["symbol"],
            "as_of": row["as_of"], "cadence": "intraday", "source": source,
            "model_version": "databento-touch-liquidity-v1", "entitlement_mode": "live",
            "quality_state": "ready", "score": round(min(100.0, row["spread_bps"] * 10.0), 2),
            "value": row["spread_bps"], "unit": "spread_bps", **row,
        })
    return result


def run(
    *,
    symbols: tuple[str, ...],
    dataset: str,
    publish_seconds: float,
    ingest_url: str,
    ingest_token: str,
    replay_start: str | int | None,
    stype_in: str,
    default_scope: str,
    state_path: Path,
    liquidity_schema: str,
) -> None:
    import databento as db
    import databento_dbn as dbn

    client = db.Live()
    client.subscribe(
        dataset=dataset,
        schema="ohlcv-1m",
        symbols=list(symbols),
        stype_in=stype_in,
        start=replay_start,
    )
    symbol_by_instrument: dict[int, str] = {}
    bars: dict[str, deque] = defaultdict(lambda: deque(maxlen=240))
    last_publish = 0.0
    source = f"databento:{dataset}:ohlcv-1m"
    quotes: dict[str, dict] = {}
    quote_lock = threading.Lock()
    liquidity_source = f"databento:{dataset}:{liquidity_schema}"
    threading.Thread(
        target=stream_liquidity,
        kwargs={"symbols": symbols, "dataset": dataset, "schema": liquidity_schema,
                "stype_in": stype_in, "quotes": quotes, "lock": quote_lock},
        daemon=True, name="databento-liquidity",
    ).start()
    try:
        state_memory = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        state_memory = {}

    for record in client:
        if isinstance(record, (dbn.SymbolMappingMsg, dbn.SymbolMappingMsgV1)):
            symbol = str(record.stype_in_symbol)
            symbol_by_instrument[int(record.instrument_id)] = symbol
            continue
        if not isinstance(record, dbn.OHLCVMsg):
            continue
        symbol = symbol_by_instrument.get(int(record.instrument_id))
        if not symbol:
            continue
        scale = float(dbn.FIXED_PRICE_SCALE)
        bars[symbol].append({
            "event_time": datetime.fromtimestamp(
                int(record.ts_event) / 1_000_000_000, tz=timezone.utc
            ).isoformat(),
            "open": float(record.open) / scale,
            "high": float(record.high) / scale,
            "low": float(record.low) / scale,
            "close": float(record.close) / scale,
            "volume": float(record.volume),
        })
        now = time.monotonic()
        if now - last_publish < publish_seconds:
            continue
        snapshots = []
        for item in symbols:
            if len(bars[item]) < 20:
                continue
            snapshot = calculate_flow_snapshot(
                item,
                list(bars[item]),
                scope="sector" if item in SECTORS else default_scope,
                source=source,
                entitlement_mode="live",
            )
            published_state, memory = apply_state_hysteresis(
                snapshot["raw_state"], state_memory.get(item)
            )
            state_memory[item] = memory
            snapshot["state"] = published_state
            snapshot["hysteresis"] = {
                "candidate": memory["candidate"],
                "candidate_count": memory["count"],
                "upgrade_dwell": 2,
                "downgrade_dwell": 3,
            }
            snapshots.append(snapshot)
        if not snapshots:
            continue
        components = liquidity_components(quotes, quote_lock, symbols, liquidity_source)
        result = publish(ingest_url, ingest_token, snapshots, components)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_state = state_path.with_suffix(".tmp")
        temporary_state.write_text(
            json.dumps(state_memory, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        temporary_state.replace(state_path)
        print(json.dumps({
            "published_at": datetime.now(timezone.utc).isoformat(),
            "symbols": len(snapshots),
            "response": result.get("accepted"),
        }), flush=True)
        last_publish = now


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument(
        "--dataset",
        default=os.getenv("DATABENTO_LIVE_DATASET", "EQUS.MINI"),
    )
    parser.add_argument("--publish-seconds", type=float, default=60.0)
    parser.add_argument("--stype-in", default="raw_symbol")
    parser.add_argument("--liquidity-schema", default="mbp-1")
    parser.add_argument(
        "--scope",
        choices=("market", "sector", "security"),
        default="market",
    )
    parser.add_argument(
        "--state-path",
        type=Path,
        default=Path("C:/Users/drewg/.magis-market-risk/flow-state.json"),
    )
    parser.add_argument(
        "--replay-start",
        default="0",
        help="Databento intraday replay start; 0 requests all available data.",
    )
    args = parser.parse_args()
    ingest_url = os.getenv("MARKET_RISK_INGEST_URL", "")
    ingest_token = os.getenv("MARKET_RISK_INGEST_TOKEN", "")
    if not os.getenv("DATABENTO_API_KEY"):
        parser.error("DATABENTO_API_KEY is required")
    if not ingest_url or not ingest_token:
        parser.error("MARKET_RISK_INGEST_URL and MARKET_RISK_INGEST_TOKEN are required")
    symbols = tuple(
        symbol.strip().upper() for symbol in args.symbols.split(",") if symbol.strip()
    )
    replay_start: str | int | None = 0 if args.replay_start == "0" else args.replay_start
    run(
        symbols=symbols,
        dataset=args.dataset,
        publish_seconds=max(15.0, args.publish_seconds),
        ingest_url=ingest_url,
        ingest_token=ingest_token,
        replay_start=replay_start,
        stype_in=args.stype_in,
        default_scope=args.scope,
        state_path=args.state_path,
        liquidity_schema=args.liquidity_schema,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
