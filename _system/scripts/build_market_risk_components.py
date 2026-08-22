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
OUTPUT = ROOT / "dashboard" / "data" / "market_risk_components.json"

# SPX risk marks come from this repo's own committed SPX tab, not from a
# checkout of the spx-0dte trading repository. See build_spx().
SPX_SURFACE_LATEST = "dashboard/data/spx_surface_latest.json"
VOL_METRICS_LATEST = "dashboard/data/vol_metrics_latest.json"
VOL_METRICS_HISTORY = "dashboard/data/vol_metrics_history.jsonl"
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


def load_snapshot(path: Path, ok_states: tuple[str, ...] = ("ready", "ok", "delayed")) -> dict:
    """A committed dashboard snapshot, or {} when it is absent or unhealthy.

    Health is read off the payload, never off the file existing. Both upstream
    builders write a well-formed file with a failed fetch recorded *inside* it,
    so an existence check would hand back a snapshot already known to be bad.
    """
    if not path.exists():
        return {}
    try:
        payload = read_json(path)
    except (OSError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    if str(payload.get("fetch_status") or "ok") != "ok":
        return {}
    state = str(payload.get("quality_state") or "")
    if state and state not in ok_states:
        return {}
    return payload


def tenor_near(tenors: Any, target: int) -> dict:
    """The chain tenor closest to `target` DTE.

    The surface builder aims at 7/30/91/182 but publishes whatever the chain
    actually offered that session, so match on distance rather than trusting a
    fixed slot.
    """
    usable = [row for row in (tenors or [])
              if isinstance(row, dict) and finite(row.get("dte")) is not None]
    if not usable:
        return {}
    return min(usable, key=lambda row: abs((finite(row.get("dte")) or 0.0) - target))


def prior_vix_close(ssi_root: Path, latest_date: str) -> float | None:
    """The ^VIX close of the session before `latest_date`.

    Read off the committed history spine rather than differencing whatever
    happens to be in the file, so a rerun on the same session cannot report a
    0% change against itself.
    """
    path = ssi_root / VOL_METRICS_HISTORY
    if not path.exists() or not latest_date:
        return None
    prior = None
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if not isinstance(row, dict) or str(row.get("date") or "") >= latest_date:
                continue
            value = finite(row.get("vix"))
            if value is not None:
                prior = value
    except (OSError, ValueError):
        return None
    return prior


def build_spx(ssi_root: Path) -> list[dict]:
    """SPX risk marks read off this dashboard's own SPX tab.

    These components used to require a sparse checkout of the spx-0dte trading
    repository. That cross-repo read is gone -- it broke on a token that no
    longer resolves, and the hub has no business reaching into the trading repo
    for figures it already publishes itself. Everything here now comes from two
    artifacts this repo builds and commits:

      * spx_surface_latest.json -- the CBOE delayed SPX chain: the EOD spot
        mark, ATM implied vol per tenor, the 25-delta risk reversal and
        butterfly, and the open-interest dealer-gamma proxy.
      * vol_metrics_latest.json -- the listed vol complex: the real ^VIX close
        with its own trailing z-scores, 20-day realized vol on ^GSPC, and the
        implied-minus-realized spread.

    Z-scores are taken from vol_metrics, which computes them on strictly
    trailing windows over ~2,500 sessions. Nothing here re-z-scores an already
    z-scored figure, and an absent source yields null rather than a zero.
    """
    surface = load_snapshot(ssi_root / SPX_SURFACE_LATEST)
    vol = load_snapshot(ssi_root / VOL_METRICS_LATEST)
    if not surface and not vol:
        return []

    output: list[dict] = []
    metrics = vol.get("metrics") or {}
    regime = vol.get("regime") or {}
    spot = surface.get("spot") or {}
    front = tenor_near(surface.get("tenors"), 30)
    back = tenor_near(surface.get("tenors"), 91)
    atm_30 = finite(front.get("atm_iv"))
    atm_91 = finite(back.get("atm_iv"))

    def metric(name: str, field: str = "value") -> float | None:
        return finite((metrics.get(name) or {}).get(field))

    spx_close = finite(spot.get("close")) or finite(spot.get("value"))
    skew_z = metric("skew", "z1y")
    term_z = metric("slope_vix_3m", "z1y")
    rv_z = metric("iv_rv_spread", "z1y")

    # Near/far, matching build_vol_metrics' convention: below 1.0 is contango
    # (the normal upward-sloping curve); above 1.0 is backwardation, i.e. stress.
    term_ratio = None if not atm_30 or not atm_91 else round(atm_30 / atm_91, 6)
    peaks = [abs(value) for value in (skew_z, term_z, rv_z) if value is not None]
    output.append(component(
        "options_stress", "SPX", surface.get("as_of") or vol.get("as_of"), "daily",
        f"single-stock-investments:{SPX_SURFACE_LATEST}", {
            "label": "SPX surface stress",
            "description": (
                "EOD SPX chain marks from this dashboard's own SPX tab (CBOE delayed "
                "quotes), scored against the listed vol complex. No orders, positions, "
                "fills or P&L are involved."
            ),
            "observations": int((vol.get("coverage") or {}).get("rows") or 0),
            "latest": {
                "skew_z": skew_z,
                "term_ratio_z": term_z,
                "realized_vs_implied_z": rv_z,
                # Retired with the spx-0dte intraday feed. The straddle residual
                # was a minute-bar construct; nothing in the EOD chain reproduces
                # it, so it reports null rather than a look-alike.
                "straddle_residual_z": None,
            },
            "latest_vix": metric("vix"),
            "latest_underlying": spx_close,
            "spx_eod_mark": spx_close,
            "atm_iv_30d": atm_30,
            "atm_iv_91d": atm_91,
            "rr_25d_30d": finite(front.get("rr_25d")),
            "bf_25d_30d": finite(front.get("bf_25d")),
            "term_ratio": term_ratio,
            "term_state": regime.get("term_state"),
            "spx_rv20": finite(regime.get("spx_rv20")),
            "iv_rv_spread": finite(regime.get("iv_rv_spread")),
            "z_basis": (
                "trailing 252-session z-scores from vol_metrics_latest.json; "
                "straddle_residual_z retired with the spx-0dte intraday feed"
            ),
        },
        score=min(100.0, 25.0 * max(peaks)) if peaks else 0.0,
        value=skew_z, unit="z_score", entitlement_mode="derived",
    ))

    vix_close = metric("vix")
    if vix_close is not None:
        prior_close = prior_vix_close(ssi_root, str(metrics.get("vix", {}).get("last_value_date") or ""))
        # The real ^VIX close out of the listed complex, not a chain proxy: the
        # spx-0dte vix_daily.csv this replaces was the same underlying index.
        score = min(100.0, max(0.0, (vix_close - 12.0) * 3.0))
        output.append(component(
            "vix_regime", "VIX", metrics.get("vix", {}).get("last_value_date") or vol.get("as_of"),
            "daily", f"single-stock-investments:{VOL_METRICS_LATEST}", {
                "label": "VIX cash regime",
                "description": (
                    "^VIX daily close from the dashboard's volatility-metrics spine "
                    "(Yahoo chart-v8 with official Cboe repair)."
                ),
                "close": vix_close,
                "prior_close": prior_close,
                "change_pct": None if not vix_close or not prior_close
                else round((vix_close / prior_close - 1.0) * 100.0, 3),
                "z1y": metric("vix", "z1y"),
                "pct1y": metric("vix", "pct1y"),
                "spx_rv20": finite(regime.get("spx_rv20")),
                "iv_rv_spread": finite(regime.get("iv_rv_spread")),
                "term_state": regime.get("term_state"),
                "vvix_vix_ratio": finite(regime.get("vvix_vix_ratio")),
            }, score=score, value=vix_close, unit="index_points", entitlement_mode="free_delayed",
        ))

    gamma = surface.get("dealer_gamma_proxy") or {}
    gamma_value = finite(gamma.get("value"))
    if gamma_value is not None:
        call_gamma = finite(gamma.get("call_gamma_notional")) or 0.0
        put_gamma = finite(gamma.get("put_gamma_notional")) or 0.0
        gross = abs(call_gamma) + abs(put_gamma)
        # Short-gamma is the stress reading: dealers hedging a negative book
        # amplify moves. Positive net gamma dampens them, so it scores zero.
        score = 0.0 if gamma_value >= 0 or not gross else min(100.0, 100.0 * abs(gamma_value) / gross)
        output.append(component(
            "dealer_gamma", "SPX", surface.get("as_of"), "daily",
            f"single-stock-investments:{SPX_SURFACE_LATEST}", {
                "label": "Dealer gamma (open-interest proxy)",
                "description": (
                    "Open-interest gamma proxy from the delayed CBOE chain. This is NOT "
                    "licensed dealer positioning: the sign convention is an assumption "
                    "and open interest is start-of-day, so intraday positioning is invisible."
                ),
                "call_gamma_notional": call_gamma,
                "put_gamma_notional": put_gamma,
                "net_gamma_notional": gamma_value,
                "contracts_used": gamma.get("contracts_used"),
                "method": gamma.get("method"),
                "formula": gamma.get("formula"),
                "sign_convention": gamma.get("sign_convention"),
                "oi_caveat": gamma.get("oi_caveat"),
                "gamma_flip_estimate_status": gamma.get("gamma_flip_estimate_status"),
                "gamma_flip_omitted_reason": gamma.get("gamma_flip_omitted_reason"),
                # The figure is USD, so it carries unit "USD" and formats as
                # -$47.5B. What the USD measures lives here rather than in the
                # unit, which the dashboard formats against a fixed set.
                "unit_description": gamma.get("units"),
                "research_only": True,
            }, score=score, value=gamma_value, unit="USD", entitlement_mode="derived",
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


def build(etf_root: Path, ls_root: Path, ssi_root: Path = ROOT) -> dict:
    groups = {
        "etf_rebalance": build_letf(etf_root),
        "etf_holdings": build_holdings(etf_root),
        "ls_algo": build_ls_algo(ls_root),
        "spx_options": build_spx(ssi_root),
        "market_breadth": build_breadth(ssi_root),
    }
    components = [item for rows in groups.values() for item in rows]
    present = {item["component"] for item in components}
    if "letf_rebalance_intraday" not in present:
        components.append(unavailable("letf_rebalance_intraday", "US_EQUITY", "etf-dashboard", "Intraday LETF output has not been generated."))
    if "options_stress" not in present:
        components.append(unavailable(
            "options_stress", "SPX", f"single-stock-investments:{SPX_SURFACE_LATEST}",
            "The committed SPX chain and vol-metrics snapshots are both absent or unhealthy.", "daily",
        ))
    if "vix_regime" not in present:
        components.append(unavailable(
            "vix_regime", "VIX", f"single-stock-investments:{VOL_METRICS_LATEST}",
            "No ^VIX close in the committed vol-metrics snapshot.", "daily",
        ))
    if "dealer_gamma" not in present:
        components.append(unavailable(
            "dealer_gamma", "SPX", f"single-stock-investments:{SPX_SURFACE_LATEST}",
            "No open-interest gamma proxy in the committed SPX chain snapshot.", "daily",
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
        "sources": ["etf-dashboard", "ls-algo", "single-stock-investments"],
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
    parser.add_argument("--ssi-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    payload = build(args.etf_root, args.ls_root, args.ssi_root)
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
