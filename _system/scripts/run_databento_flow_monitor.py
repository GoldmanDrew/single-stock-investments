#!/usr/bin/env python3
"""Stream Databento minute bars and publish forced-flow snapshots to the dashboard.

Required environment:
  DATABENTO_API_KEY
  MARKET_RISK_INGEST_URL
  MARKET_RISK_INGEST_TOKEN

Resilience contract (2026-08-10, after a 7-day silent outage):

  * A transient publish failure is operating weather, not a fatal condition.
    ``publish_with_retry`` retries with bounded exponential backoff and the
    stream keeps running when every attempt fails -- the next cycle publishes
    fresh data anyway, and re-establishing the Databento session is the
    expensive thing.
  * A 401/403 is NOT transient: retrying a rejected signing token forever is
    pointless, so it raises ``PublishAuthError`` and stops the monitor with
    exit code ``EXIT_AUTH_FAILURE`` for the supervisor to notice.
  * The stream itself reconnects with backoff; the process must not exit
    because one socket died.
  * Every cycle emits a heartbeat carrying ``consecutive_failures`` so the log
    itself shows health. All log output is ASCII (``ensure_ascii=True``) --
    the Windows cp1252 console kills the process on a single stray byte.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import math
import os
import random
import secrets
import socket
import statistics
import threading
import time
import urllib.error
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

PUBLISH_ATTEMPTS = 3                    # 1 try + 2 retries
PUBLISH_BACKOFF_SECONDS = 2.0           # 2s, 4s (then give up for this cycle)
PUBLISH_ESCALATION_AFTER = 10           # consecutive failed cycles -> escalate
AUTH_STATUS_CODES = (401, 403)          # permanent: a bad token never heals
STREAM_RECONNECT_SECONDS = 5.0
STREAM_RECONNECT_MAX_SECONDS = 300.0
STREAM_HEALTHY_SECONDS = 300.0          # a session this long resets the backoff
EXIT_AUTH_FAILURE = 2                   # supervisor contract: do NOT restart


class PublishAuthError(RuntimeError):
    """The ingest rejected the signing token (401/403).

    The one publish failure that is NOT retried: a rejected token is a
    configuration fact, and retrying it forever would look like liveness
    while publishing nothing.
    """

    def __init__(self, status: int, detail: str = "") -> None:
        super().__init__("ingest rejected the signing credential: HTTP %d"
                         % status)
        self.status = status
        self.detail = detail


def log_event(event: str, **fields) -> None:
    """One structured ASCII JSON object per line.

    ``ensure_ascii=True`` is load-bearing, not cosmetic: this process logs to
    a cp1252 console and a single non-ASCII byte in an error string would
    raise UnicodeEncodeError out of print() and kill the monitor -- the exact
    class of bug this module now exists to survive.
    """
    payload = {"event": event, "at": datetime.now(timezone.utc).isoformat()}
    payload.update(fields)
    print(json.dumps(payload, ensure_ascii=True, default=str), flush=True)


def _describe(exc: BaseException) -> tuple[str, str]:
    return type(exc).__name__, str(exc)[:240]


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


def publish_with_retry(
    url: str,
    token: str,
    snapshots: list[dict],
    components: list[dict] | None = None,
    *,
    attempts: int = PUBLISH_ATTEMPTS,
    base_delay: float = PUBLISH_BACKOFF_SECONDS,
    publisher=publish,
    sleeper=time.sleep,
    jitter=None,
) -> tuple[dict | None, dict | None]:
    """POST the snapshot, surviving transient network weather.

    Returns ``(payload, None)`` on success and ``(None, error)`` when every
    attempt failed, where ``error`` carries the last ``error_class`` and the
    attempt count. Raises :class:`PublishAuthError` immediately on 401/403 --
    the caller is expected to stop rather than retry a rejected token.

    Backoff is ``base_delay * 2 ** (attempt - 1)`` (2s, 4s, 8s ...) plus a
    jitter of up to one ``base_delay``, so a fleet of monitors recovering from
    the same outage does not re-synchronise onto the ingest.
    """
    jitter = jitter if jitter is not None else \
        (lambda: random.uniform(0.0, base_delay))
    error: dict | None = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            result = publisher(url, token, snapshots, components)
            return (result if isinstance(result, dict) else {}), None
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace")[:200]
            except Exception:                     # body already consumed
                detail = ""
            if exc.code in AUTH_STATUS_CODES:
                raise PublishAuthError(exc.code, detail) from exc
            error_class, message = _describe(exc)
            error = {"error_class": error_class, "error": message,
                     "http_status": exc.code, "detail": detail}
        except (urllib.error.URLError, socket.timeout, TimeoutError,
                json.JSONDecodeError, OSError) as exc:
            error_class, message = _describe(exc)
            error = {"error_class": error_class, "error": message,
                     "http_status": None}
        error = dict(error or {}, attempt=attempt, attempts=attempts)
        if attempt >= attempts:
            log_event("publish_attempt_failed", retrying=False, **error)
            break
        delay = round(base_delay * (2 ** (attempt - 1)) + jitter(), 3)
        log_event("publish_attempt_failed", retrying=True,
                  retry_in_seconds=delay, **error)
        sleeper(delay)
    return None, error


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


def write_state(state_path: Path, state_memory: dict) -> bool:
    """Persist the hysteresis memory. A failure here is logged, never fatal."""
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_state = state_path.with_suffix(".tmp")
        temporary_state.write_text(
            json.dumps(state_memory, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        temporary_state.replace(state_path)
        return True
    except OSError as exc:
        error_class, message = _describe(exc)
        log_event("state_write_failed", error_class=error_class,
                  error=message, path=str(state_path),
                  action="continue_streaming")
        return False


def publish_cycle(
    *,
    ingest_url: str,
    ingest_token: str,
    snapshots: list[dict],
    components: list[dict],
    consecutive_failures: int,
    state_memory: dict,
    state_path: Path,
    publisher=publish_with_retry,
) -> int:
    """Publish one snapshot batch and return the new consecutive-failure count.

    Never raises for a transient failure: the contract is LOG AND CONTINUE.
    Only :class:`PublishAuthError` (401/403) escapes, and only because a
    rejected token cannot heal by being retried.
    """
    result, error = publisher(ingest_url, ingest_token, snapshots, components)
    if result is None:
        consecutive_failures += 1
        detail = error or {}
        log_event("publish_failed",
                  consecutive_failures=consecutive_failures,
                  attempts=detail.get("attempts", PUBLISH_ATTEMPTS),
                  error_class=detail.get("error_class", "unknown"),
                  error=detail.get("error", ""),
                  action="continue_streaming")
        if (consecutive_failures >= PUBLISH_ESCALATION_AFTER
                and consecutive_failures % PUBLISH_ESCALATION_AFTER == 0):
            log_event("publish_escalation",
                      consecutive_failures=consecutive_failures,
                      threshold=PUBLISH_ESCALATION_AFTER,
                      action="continue_streaming",
                      detail="ingest unreachable for consecutive cycles;"
                             " the Databento stream is deliberately kept open"
                             " (re-establishing it is the expensive part)")
    else:
        consecutive_failures = 0
        # Preserved line shape -- something downstream parses this exact
        # object (and P7 reads its published_at as the live-feed stamp).
        print(json.dumps({
            "published_at": datetime.now(timezone.utc).isoformat(),
            "symbols": len(snapshots),
            "response": result.get("accepted"),
        }), flush=True)
    write_state(state_path, state_memory)
    log_event("heartbeat", symbols=len(snapshots),
              publish_ok=result is not None,
              consecutive_failures=consecutive_failures)
    return consecutive_failures


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
) -> int:
    import databento as db
    import databento_dbn as dbn

    bars: dict[str, deque] = defaultdict(lambda: deque(maxlen=240))
    last_event_ns: dict[str, int] = {}
    last_publish = 0.0
    consecutive_failures = 0
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

    reconnect_delay = STREAM_RECONNECT_SECONDS
    reconnects = 0
    while True:
        connected_at = time.monotonic()
        try:
            client = db.Live()
            client.subscribe(
                dataset=dataset,
                schema="ohlcv-1m",
                symbols=list(symbols),
                stype_in=stype_in,
                start=replay_start,
            )
            log_event("stream_connected", dataset=dataset,
                      symbols=len(symbols), reconnects=reconnects,
                      consecutive_publish_failures=consecutive_failures)
            connected_at = time.monotonic()
            # Instrument ids are per-session; the mapping must NOT survive a
            # reconnect or bars would be filed under the wrong symbol.
            symbol_by_instrument: dict[int, str] = {}
            for record in client:
                if isinstance(record, (dbn.SymbolMappingMsg,
                                       dbn.SymbolMappingMsgV1)):
                    symbol = str(record.stype_in_symbol)
                    symbol_by_instrument[int(record.instrument_id)] = symbol
                    continue
                if not isinstance(record, dbn.OHLCVMsg):
                    continue
                symbol = symbol_by_instrument.get(int(record.instrument_id))
                if not symbol:
                    continue
                event_ns = int(record.ts_event)
                # Reconnecting replays the session from `replay_start`, so
                # without this the same minute bar would be appended twice
                # and the flow snapshot would be computed on duplicates.
                if event_ns <= last_event_ns.get(symbol, -1):
                    continue
                last_event_ns[symbol] = event_ns
                scale = float(dbn.FIXED_PRICE_SCALE)
                bars[symbol].append({
                    "event_time": datetime.fromtimestamp(
                        event_ns / 1_000_000_000, tz=timezone.utc
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
                components = liquidity_components(
                    quotes, quote_lock, symbols, liquidity_source)
                # Claim the slot BEFORE publishing: a failing publish must not
                # turn every subsequent bar into another publish attempt.
                last_publish = now
                consecutive_failures = publish_cycle(
                    ingest_url=ingest_url,
                    ingest_token=ingest_token,
                    snapshots=snapshots,
                    components=components,
                    consecutive_failures=consecutive_failures,
                    state_memory=state_memory,
                    state_path=state_path,
                )
            log_event("stream_ended", reason="iterator exhausted",
                      reconnects=reconnects)
        except PublishAuthError as exc:
            log_event("publish_auth_failed", http_status=exc.status,
                      detail=exc.detail, action="exit",
                      exit_code=EXIT_AUTH_FAILURE,
                      remediation="re-mint MARKET_RISK_INGEST_TOKEN;"
                                  " retrying a rejected token forever would"
                                  " look alive while publishing nothing")
            return EXIT_AUTH_FAILURE
        except KeyboardInterrupt:
            log_event("stream_interrupted", action="exit")
            return 0
        except Exception as exc:  # noqa: BLE001 -- the stream must not be fatal
            error_class, message = _describe(exc)
            log_event("stream_error", error_class=error_class, error=message,
                      reconnects=reconnects, action="reconnect")
        if time.monotonic() - connected_at >= STREAM_HEALTHY_SECONDS:
            reconnect_delay = STREAM_RECONNECT_SECONDS   # the session was healthy
        reconnects += 1
        log_event("stream_reconnect", reconnects=reconnects,
                  sleep_seconds=round(reconnect_delay, 3))
        time.sleep(reconnect_delay)
        reconnect_delay = min(reconnect_delay * 2.0,
                              STREAM_RECONNECT_MAX_SECONDS)


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
    return run(
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


if __name__ == "__main__":
    raise SystemExit(main())
