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
import os
import secrets
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


def publish(url: str, token: str, snapshots: list[dict]) -> dict:
    body = json.dumps({
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "flow": snapshots,
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
        result = publish(ingest_url, ingest_token, snapshots)
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
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
