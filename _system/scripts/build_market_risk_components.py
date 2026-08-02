#!/usr/bin/env python3
"""Build and optionally publish the dashboard's reusable market-risk data stack."""
from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import json
import math
import secrets
import statistics
import time
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ETF_ROOT = Path.home() / "Projects/quant/etf-dashboard"
DEFAULT_LS_ROOT = Path.home() / "Projects/quant/ls-algo"
DEFAULT_SPX_ROOT = Path.home() / "Projects/options-trading/spx-0dte"
OUTPUT = ROOT / "dashboard" / "data" / "market_risk_components.json"
MODEL_VERSION = "market-risk-components-v1"
SECTOR_ETFS = {"XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY"}


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def iso(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) == 10:
        return f"{text}T20:00:00+00:00"
    return text.replace("Z", "+00:00")


def business_age(value: Any, today: date | None = None) -> int | None:
    stamp = iso(value)
    if not stamp:
        return None
    try:
        start = datetime.fromisoformat(stamp).date()
    except ValueError:
        return None
    end = today or datetime.now(timezone.utc).date()
    if start >= end:
        return 0
    count = 0
    cursor = start
    while cursor < end:
        cursor = date.fromordinal(cursor.toordinal() + 1)
        if cursor.weekday() < 5:
            count += 1
    return count


def quality(as_of: Any, cadence: str) -> str:
    age = business_age(as_of)
    if age is None:
        return "unavailable"
    limits = {"intraday": (0, 1), "daily": (1, 3), "event": (2, 5)}
    ready, delayed = limits.get(cadence, (1, 3))
    if age <= ready:
        return "ready"
    if age <= delayed:
        return "delayed"
    return "stale"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def rows_from_mapping(value: Any) -> list[dict]:
    if isinstance(value, dict):
        return [item for item in value.values() if isinstance(item, dict)]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def component(
    name: str, symbol: str, as_of: Any, cadence: str, source: str, payload: dict,
    *, score: float | None = None, value: float | None = None, unit: str | None = None,
    scope: str = "market", entitlement_mode: str = "derived",
) -> dict:
    stamp = iso(as_of) or datetime.now(timezone.utc).isoformat()
    return {
        "component": name,
        "scope": scope,
        "symbol": symbol,
        "as_of": stamp,
        "cadence": cadence,
        "source": source,
        "model_version": MODEL_VERSION,
        "entitlement_mode": entitlement_mode,
        "quality_state": quality(stamp, cadence),
        "score": None if score is None else round(max(0.0, min(100.0, score)), 2),
        "value": None if value is None else round(value, 6),
        "unit": unit,
        **payload,
    }


def top_rows(rows: Iterable[dict], field: str, fields: tuple[str, ...], limit: int = 12) -> list[dict]:
    ranked = sorted(rows, key=lambda row: abs(finite(row.get(field)) or 0.0), reverse=True)
    return [{key: row.get(key) for key in fields} for row in ranked[:limit]]


def build_letf(root: Path) -> list[dict]:
    output: list[dict] = []
    specs = (
        ("letf_rebalance_close", "data/letf_rebalance_flows_latest.json", "daily",
         "net_moc_dollars", "gross_moc_dollars", "net_moc_pct_auction_volume", "date"),
        ("letf_rebalance_intraday", "data/letf_rebalance_flows_intraday_latest.json", "intraday",
         "estimated_net_close_rebalance_dollars", "estimated_gross_close_rebalance_dollars",
         "estimated_close_rebalance_pct_auction_volume", "as_of"),
    )
    for name, relative, cadence, net_field, gross_field, auction_field, row_time in specs:
        path = root / relative
        if not path.exists():
            continue
        data = read_json(path)
        rows = rows_from_mapping(data.get("by_underlying"))
        if not rows:
            continue
        as_of = data.get("as_of") or data.get("latest_date") or data.get("build_time")
        if not as_of:
            as_of = max((row.get(row_time) for row in rows if row.get(row_time)), default=None)
        net = sum(finite(row.get(net_field)) or 0.0 for row in rows)
        gross = sum(finite(row.get(gross_field)) or 0.0 for row in rows)
        auction_values = [abs(finite(row.get(auction_field)) or 0.0) for row in rows]
        if name.endswith("close"):
            percentiles = [finite(row.get("abs_net_moc_pctile_60d")) for row in rows]
            percentiles = [value for value in percentiles if value is not None]
            score = 100.0 * statistics.mean(sorted(percentiles, reverse=True)[:20]) if percentiles else 0.0
        else:
            score = min(100.0, 20.0 * max(auction_values, default=0.0))
        output.append(component(
            name, "US_EQUITY", as_of, cadence, f"etf-dashboard:{relative}", {
                "label": "Leveraged ETF close rebalance" if cadence == "daily" else "Leveraged ETF intraday close estimate",
                "description": "Mechanical leveraged/inverse ETF rebalance estimate; separate from vol-target fund selling.",
                "net_dollars": round(net, 2),
                "gross_dollars": round(gross, 2),
                "underlyings": len(rows),
                "buy_underlyings": sum((finite(row.get(net_field)) or 0.0) > 0 for row in rows),
                "sell_underlyings": sum((finite(row.get(net_field)) or 0.0) < 0 for row in rows),
                "peak_abs_pct_auction_volume": round(max(auction_values, default=0.0), 5),
                "auction_share_assumption": data.get("auction_share_of_adv_assumption"),
                "swap_hedge_share_assumption": data.get("swap_hedge_share_assumption"),
                "top": top_rows(rows, auction_field, (
                    "underlying", net_field, auction_field, "n_funds", "n_funds_priced",
                    "return_d1_so_far", "underlying_return_d1", "tradable_float_quality",
                )),
                "method": data.get("method"),
            }, score=score, value=net, unit="USD", entitlement_mode="estimated",
        ))
        for row in rows:
            symbol = str(row.get("underlying") or "").upper()
            if symbol not in SECTOR_ETFS:
                continue
            auction = abs(finite(row.get(auction_field)) or 0.0)
            sector_score = (
                100.0 * (finite(row.get("abs_net_moc_pctile_60d")) or 0.0)
                if cadence == "daily" else min(100.0, auction * 20.0)
            )
            output.append(component(
                name, symbol, row.get(row_time) or as_of, cadence,
                f"etf-dashboard:{relative}", {
                    "label": f"{symbol} leveraged ETF rebalance",
                    "description": "Sector-level mechanical close-flow estimate from leveraged and inverse ETF wrappers.",
                    "net_dollars": round(finite(row.get(net_field)) or 0.0, 2),
                    "gross_dollars": round(finite(row.get(gross_field)) or 0.0, 2),
                    "pct_auction_volume": finite(row.get(auction_field)),
                    "pct_adv_20d": finite(row.get("net_moc_pct_adv_20d") or row.get("estimated_close_rebalance_pct_adv_20d")),
                    "underlying_return": finite(row.get("underlying_return_d1") or row.get("return_d1_so_far")),
                    "funds": row.get("n_funds") or row.get("n_funds_priced"),
                }, score=sector_score, value=finite(row.get(net_field)), unit="USD",
                scope="sector", entitlement_mode="estimated",
            ))
    return output


def build_holdings(root: Path) -> list[dict]:
    path = root / "data/etf_holdings_latest.json"
    if not path.exists():
        return []
    data = read_json(path)
    by_symbol = data.get("by_symbol") or {}
    positions = [row for rows in by_symbol.values() if isinstance(rows, list) for row in rows if isinstance(row, dict)]
    latest = data.get("latest_date") or max((row.get("as_of_date") for row in positions), default=None)
    sources = sorted({str(row.get("source")) for row in positions if row.get("source")})
    return [component(
        "etf_holdings_coverage", "LEVERAGED_ETFS", latest, "daily",
        "etf-dashboard:data/etf_holdings_latest.json", {
            "label": "Leveraged ETF holdings coverage",
            "description": "Issuer holdings and derivative positions used to map wrapper flows to underlying securities.",
            "funds": len(by_symbol),
            "positions": len(positions),
            "sources": sources,
            "derivative_positions": sum(str(row.get("security_type") or "").upper() in {"SWAP", "FUTURE", "OPTION"} for row in positions),
        }, value=float(len(by_symbol)), unit="funds",
    )]


def csv_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def median(rows: list[dict], field: str) -> float | None:
    values = [finite(row.get(field)) for row in rows]
    clean = [value for value in values if value is not None]
    return statistics.median(clean) if clean else None


def truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def build_ls_algo(root: Path) -> list[dict]:
    path = root / "data/etf_screened_today.csv"
    rows = csv_rows(path)
    if not rows:
        return []
    as_of = max((row.get("asof_date") for row in rows if row.get("asof_date")), default=None)
    rv_pctile = median(rows, "und_rv_20d_pctile") or 0.0
    borrow_spike_share = sum(truthy(row.get("borrow_spiking")) for row in rows) / len(rows)
    score = 70.0 * rv_pctile + 30.0 * min(1.0, borrow_spike_share * 5.0)
    return [component(
        "volatility_borrow", "LEVERAGED_ETFS", as_of, "daily",
        "ls-algo:data/etf_screened_today.csv", {
            "label": "Volatility, beta and borrow context",
            "description": "Cross-sectional ls-algo screen; describes volatility and financing stress in leveraged ETF products.",
            "products": len(rows),
            "underlyings": len({row.get("Underlying") for row in rows if row.get("Underlying")}),
            "median_underlying_rv_20d_annual": median(rows, "und_rv_20d_daily_annual"),
            "median_underlying_rv_20d_percentile": rv_pctile,
            "median_beta": median(rows, "Delta"),
            "median_borrow_fee_annual": median(rows, "borrow_fee_annual"),
            "borrow_spiking_count": sum(truthy(row.get("borrow_spiking")) for row in rows),
            "high_intraday_risk_count": sum(truthy(row.get("high_intraday_risk")) for row in rows),
            "purgatory_count": sum(truthy(row.get("purgatory")) for row in rows),
            "top": top_rows(rows, "und_rv_20d_pctile", (
                "ETF", "Underlying", "Delta", "borrow_fee_annual", "borrow_spiking",
                "und_rv_20d_daily_annual", "und_rv_20d_pctile", "und_vol_shape_20d",
                "high_intraday_risk", "product_class",
            )),
        }, score=score, value=median(rows, "und_rv_20d_daily_annual"), unit="annualized_volatility",
    )]


def latest_signal_file(root: Path) -> Path | None:
    base = root / "data/processed/symbol=SPXW"
    candidates = sorted(base.glob("date=*/signals.csv"), reverse=True)
    return candidates[0] if candidates else None


def build_options(root: Path) -> list[dict]:
    output: list[dict] = []
    signals_path = latest_signal_file(root)
    if signals_path:
        rows = csv_rows(signals_path)
        if rows:
            last = rows[-1]
            fields = ("straddle_residual_z", "skew_z", "term_ratio_z", "realized_vs_implied_z")
            peak = {field: max((abs(finite(row.get(field)) or 0.0) for row in rows), default=0.0) for field in fields}
            score = min(100.0, 25.0 * max(peak.values(), default=0.0))
            output.append(component(
                "options_stress", "SPX", last.get("timestamp"), "intraday",
                f"spx-0dte:{signals_path.relative_to(root).as_posix()}", {
                    "label": "SPX 0DTE options stress",
                    "description": "Sanitized market features only; no orders, positions, fills or P&L leave the trading repository.",
                    "observations": len(rows),
                    "latest": {field: finite(last.get(field)) for field in fields},
                    "latest_vix": finite(last.get("vix")),
                    "latest_straddle": finite(last.get("straddle")),
                    "latest_underlying": finite(last.get("underlying_price")),
                    "intraday_peak_abs_z": peak,
                }, score=score, value=finite(last.get("skew_z")), unit="z_score", entitlement_mode="derived",
            ))
    vix_path = root / "data/calendar/vix_daily.csv"
    vix_rows = csv_rows(vix_path)
    if vix_rows:
        last = vix_rows[-1]
        close = finite(last.get("close"))
        prior = finite(last.get("prior_close"))
        score = 0.0 if close is None else min(100.0, max(0.0, (close - 12.0) * 3.0))
        output.append(component(
            "vix_regime", "VIX", last.get("date"), "daily",
            "spx-0dte:data/calendar/vix_daily.csv", {
                "label": "VIX cash regime",
                "description": "Daily VIX OHLC context used by the SPX 0DTE research stack.",
                "open": finite(last.get("open")), "high": finite(last.get("high")),
                "low": finite(last.get("low")), "close": close, "prior_close": prior,
                "change_pct": None if not close or not prior else round((close / prior - 1.0) * 100.0, 3),
            }, score=score, value=close, unit="index_points", entitlement_mode="free_delayed",
        ))
    return output


def build_breadth(root: Path) -> list[dict]:
    path = root / "dashboard/data/technical_summary.json"
    if not path.exists():
        return []
    data = read_json(path)
    summary = data.get("summary") or {}
    states = summary.get("fear_states") or {}
    setups = summary.get("setups") or {}
    available = int(summary.get("available") or 0)
    if not available:
        return []
    stressed = int(states.get("stress_building") or 0)
    panic = int(states.get("panic") or 0)
    candidate = int(states.get("capitulation_candidate") or 0)
    exhaustion = int(states.get("exhaustion_emerging") or 0)
    stress_share = (stressed + panic + candidate + exhaustion) / available
    severe_share = (panic + candidate + exhaustion) / available
    score = min(100.0, 100.0 * (0.55 * stress_share + 1.8 * severe_share))
    internal = (data.get("market_context") or {}).get("internal") or {}
    return [component(
        "market_breadth", "SSI_UNIVERSE", internal.get("as_of") or data.get("generated_at"), "daily",
        "single-stock-investments:dashboard/data/technical_summary.json", {
            "label": "Single-stock stress breadth",
            "description": "Breadth across the dashboard universe; this is an SSI coverage set, not an index constituent-weighted breadth measure.",
            "requested": summary.get("requested"), "available": available, "failed": summary.get("failed"),
            "fear_states": states, "setups": setups,
            "stress_share": round(stress_share, 4), "severe_share": round(severe_share, 4),
            "market_scores": internal.get("scores"), "market_state": internal.get("state"),
            "interpretation": internal.get("interpretation"),
        }, score=score, value=stress_share, unit="share_of_universe", entitlement_mode="derived",
    )]


def unavailable(name: str, symbol: str, source: str, description: str, cadence: str = "intraday") -> dict:
    row = component(name, symbol, datetime.now(timezone.utc).isoformat(), cadence, source, {
        "label": name.replace("_", " ").title(), "description": description,
    }, entitlement_mode="not_connected")
    row["quality_state"] = "unavailable"
    return row


def build(etf_root: Path, ls_root: Path, spx_root: Path, ssi_root: Path = ROOT) -> dict:
    groups = {
        "etf_rebalance": build_letf(etf_root),
        "etf_holdings": build_holdings(etf_root),
        "ls_algo": build_ls_algo(ls_root),
        "spx_options": build_options(spx_root),
        "market_breadth": build_breadth(ssi_root),
    }
    components = [item for rows in groups.values() for item in rows]
    present = {item["component"] for item in components}
    if "letf_rebalance_intraday" not in present:
        components.append(unavailable("letf_rebalance_intraday", "US_EQUITY", "etf-dashboard", "Intraday LETF output has not been generated."))
    if "options_stress" not in present:
        components.append(unavailable("options_stress", "SPX", "spx-0dte", "No sanitized SPX options signal file was found."))
    components.append(unavailable(
        "dealer_gamma", "SPX", "options-positioning-provider",
        "Open-interest gamma/vanna/charm positioning is not yet licensed or connected.", "daily",
    ))
    components.append(unavailable(
        "observed_vol_target_flows", "US_EQUITY", "institutional-flow-provider",
        "Observed vol-control and risk-parity holdings are not public; current vol-target output remains a scenario estimate.", "daily",
    ))
    generated = datetime.now(timezone.utc).isoformat()
    ready = sum(item["quality_state"] == "ready" for item in components)
    delayed = sum(item["quality_state"] == "delayed" for item in components)
    stale = sum(item["quality_state"] == "stale" for item in components)
    missing = sum(item["quality_state"] == "unavailable" for item in components)
    return {
        "schema_version": 1,
        "model_version": MODEL_VERSION,
        "generated_at": generated,
        "source": "single-stock-investments:market-risk-component-builder",
        "research_only": True,
        "components": components,
        "coverage": {"ready": ready, "delayed": delayed, "stale": stale, "unavailable": missing, "total": len(components)},
        "sources": ["etf-dashboard", "ls-algo", "spx-0dte"],
    }


def write_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def publish(url: str, token: str, payload: dict) -> dict:
    body = json.dumps({
        "schema_version": 1,
        "generated_at": payload["generated_at"],
        "source": payload["source"],
        "components": payload["components"],
    }, separators=(",", ":")).encode("utf-8")
    timestamp = str(int(time.time()))
    nonce = secrets.token_hex(16)
    signature = hmac.new(token.encode(), f"{timestamp}\n{nonce}\n".encode() + body, hashlib.sha256).hexdigest()
    request = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json", "X-Market-Risk-Timestamp": timestamp,
        "X-Market-Risk-Nonce": nonce, "X-Market-Risk-Signature": signature,
        "User-Agent": "MagisMarketRiskComponents/1.0",
    })
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--etf-root", type=Path, default=DEFAULT_ETF_ROOT)
    parser.add_argument("--ls-root", type=Path, default=DEFAULT_LS_ROOT)
    parser.add_argument("--spx-root", type=Path, default=DEFAULT_SPX_ROOT)
    parser.add_argument("--ssi-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    payload = build(args.etf_root, args.ls_root, args.spx_root, args.ssi_root)
    write_atomic(args.output, payload)
    result = None
    if args.publish:
        import os
        url = os.getenv("MARKET_RISK_INGEST_URL", "")
        token = os.getenv("MARKET_RISK_INGEST_TOKEN", "")
        if not url or not token:
            parser.error("MARKET_RISK_INGEST_URL and MARKET_RISK_INGEST_TOKEN are required with --publish")
        result = publish(url, token, payload)
    print(json.dumps({"coverage": payload["coverage"], "published": result and result.get("accepted")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
