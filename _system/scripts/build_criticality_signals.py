#!/usr/bin/env python3
"""Build daily LPPLS criticality snapshots for market and sector ETFs."""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_technical_signals import fetch_yahoo_history  # noqa: E402
from criticality.lppls import MODEL_VERSION, fit_ensemble  # noqa: E402

OUTPUT = ROOT / "dashboard" / "data" / "criticality_summary.json"
UNIVERSE = {
    "SPY": {"name": "S&P 500", "scope": "market"},
    "QQQ": {"name": "Nasdaq 100", "scope": "market"},
    "IWM": {"name": "Russell 2000", "scope": "market"},
    "DIA": {"name": "Dow Jones", "scope": "market"},
    "EWJ": {"name": "Japan", "scope": "market"},
    "^N225": {"name": "Nikkei 225", "scope": "market"},
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


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    temporary.replace(path)


def calculate_symbol(symbol: str, rows: list[dict], source: str) -> dict:
    clean = [
        row for row in sorted(rows, key=lambda item: item["date"])
        if row.get("close") is not None and float(row["close"]) > 0
    ]
    ensemble = fit_ensemble([float(row["close"]) for row in clean])
    meta = UNIVERSE[symbol]
    return {
        "symbol": symbol,
        "name": meta["name"],
        "scope": meta["scope"],
        "as_of": clean[-1]["date"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "entitlement_mode": "eod",
        "quality_state": ensemble["status"],
        **ensemble,
    }


def build(*, workers: int = 4, symbols: set[str] | None = None) -> dict:
    prior = {}
    if OUTPUT.exists():
        try:
            prior = json.loads(OUTPUT.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            prior = {}
    prior_by_symbol = prior.get("by_symbol") or {}
    selected = {
        symbol: meta for symbol, meta in UNIVERSE.items()
        if not symbols or symbol in symbols
    }
    by_symbol: dict[str, dict] = {}
    errors: dict[str, str] = {}

    def build_one(symbol: str) -> dict:
        rows, source = fetch_yahoo_history(symbol)
        return calculate_symbol(symbol, rows, source)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(build_one, symbol): symbol for symbol in selected}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                by_symbol[symbol] = future.result()
            except Exception as exc:
                errors[symbol] = str(exc)
                if symbol in prior_by_symbol:
                    preserved = dict(prior_by_symbol[symbol])
                    preserved["quality_state"] = "stale"
                    preserved["fetch_status"] = "preserved_after_fetch_failure"
                    preserved["fetch_error"] = str(exc)[:240]
                    by_symbol[symbol] = preserved

    generated_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "schema_version": 1,
        "model_version": MODEL_VERSION,
        "generated_at": generated_at,
        "cadence": "daily",
        "research_only": True,
        "by_symbol": dict(sorted(by_symbol.items())),
        "market": [
            by_symbol[symbol] for symbol in selected
            if symbol in by_symbol and selected[symbol]["scope"] == "market"
        ],
        "sectors": [
            by_symbol[symbol] for symbol in selected
            if symbol in by_symbol and selected[symbol]["scope"] == "sector"
        ],
        "errors": errors,
        "summary": {
            "requested": len(selected),
            "available": len(by_symbol),
            "errors": len(errors),
            "fresh": sum(
                row.get("fetch_status") != "preserved_after_fetch_failure"
                for row in by_symbol.values()
            ),
            "stale": sum(
                row.get("fetch_status") == "preserved_after_fetch_failure"
                for row in by_symbol.values()
            ),
        },
    }
    _write_json_atomic(OUTPUT, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--symbols",
        help="Optional comma-separated subset, for example SPY,QQQ,XLK",
    )
    args = parser.parse_args()
    selected = (
        {item.strip().upper() for item in args.symbols.split(",") if item.strip()}
        if args.symbols else None
    )
    payload = build(workers=args.workers, symbols=selected)
    print(json.dumps(payload["summary"], sort_keys=True))
    return 0 if payload["summary"]["available"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
