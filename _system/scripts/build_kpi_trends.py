#!/usr/bin/env python3
"""Build dashboard/data/kpi_trends.json - second-derivative KPI signals per ticker.

Sources, in order of trust:
  - _system/reference/market-data/fundamentals/{TICKER}.json
        SEC XBRL companyfacts quarterly series (build_fundamental_series.py).
        Real fiscal period ends; quarterly scope enforced at extraction.
  - dashboard/data/equity_models.json  (model observation series)
  - dashboard/data/portfolio_news.json (monthly news-flow counts)

Quarterly fundamentals are analyzed on a year-over-year basis: growth compares
each quarter to the same quarter a year earlier (killing seasonality), and the
second derivative is the change in YoY growth between consecutive quarters.
Signals pass through smoothing, materiality gates, persistence confirmation,
TTM cross-check, metric-tier filtering, correlated-metric collapse, and a
per-ticker display cap so the Inflections view stays salient.

The legacy filing_facts_*.json source was removed: those extracts carry no
fiscal period or scope metadata, which produced false inflections (duplicate
snapshots + quarterly/annual mixing).
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

from kpi_signal_enhancements import (
    analyze_growth_regime,
    attach_human_summary,
    compute_leadership_risk,
    cross_metric_freshness,
    earnings_revision_signal,
    is_growth_artifact,
    passes_materiality,
    peer_relative_signal,
    regime_metric_priority,
    resolve_revenue_series,
    series_freshness,
    STALE_SERIES_MAX_DAYS,
)

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "dashboard" / "data" / "kpi_trends.json"
FUNDAMENTALS_DIR = ROOT / "_system" / "reference" / "market-data" / "fundamentals"
EQUITY_MODELS_PATH = ROOT / "dashboard" / "data" / "equity_models.json"
EQUITY_KPI_SERIES_PATH = ROOT / "dashboard" / "data" / "equity_kpi_series.json"
EARNINGS_CALENDAR_PATH = ROOT / "_system" / "data" / "earnings_calendar.json"
NEWS_PATH = ROOT / "dashboard" / "data" / "portfolio_news.json"
NEWS_HISTORY_PATH = ROOT / "_system" / "reference" / "market-data" / "news_flow_history.json"
REGISTRY_PATH = ROOT / "_system" / "portfolio" / "registry.json"
RESPIRATORY_DIR = ROOT / "_system" / "reference" / "market-data" / "respiratory"
HOLDINGS_THEMES_PATH = ROOT / "_system" / "portfolio" / "holdings_themes.json"

MIN_POINTS = 4
MAX_POINTS = 8
NEWS_WINDOW_MONTHS = 8

# YoY analysis knobs
YOY_MIN_QUARTERS = 8
YOY_MIN_GROWTH_POINTS = 4
YOY_MATCH_WINDOW = (330, 400)
GROWTH_OUTLIER_CAP = 5.0
DENOMINATOR_FLOOR_FRAC = 0.05

# Signal quality knobs
VOL_MULTIPLIER = 1.0
SMOOTH_WINDOW = 3
HIGH_CONFIDENCE_MULT = 2.0
MAX_PRIMARY_DISPLAY = 2
MAX_SECONDARY_DISPLAY = 1

METRIC_TIER_PRIMARY = frozenset({"revenues", "revenue", "operating_income", "cfo", "op_margin", "cfo_margin"})
METRIC_TIER_SECONDARY = frozenset({"net_income", "eps_basic", "news_flow", "burn_rate", "eps_revision"})
METRIC_TIER_EXCLUDED = frozenset({"cash", "total_assets", "stockholders_equity", "long_term_debt"})
# Exogenous demand drivers: shown as context, never scored as company fundamentals.
METRIC_TIER_CONTEXT = frozenset({"respiratory_test_volume"})
CORE_COLLAPSE_METRICS = frozenset({"revenues", "revenue", "operating_income", "cfo"})
REGIME_METRICS = frozenset({"revenues", "revenue", "operating_income", "cfo", "net_income", "eps_basic"})

MATERIALITY_FLOORS: dict[str, float] = {
    "revenues": 0.03,
    "revenue": 0.03,
    "operating_income": 0.05,
    "net_income": 0.05,
    "eps_basic": 0.05,
    "cfo": 0.05,
    "op_margin": 0.01,
    "cfo_margin": 0.01,
    "news_flow": 0.0,
}

BMS_WEIGHTS: dict[str, float] = {
    "revenues": 0.40,
    "revenue": 0.40,
    "operating_income": 0.30,
    "cfo": 0.20,
    "op_margin": 0.10,
}

METRIC_LABELS = {
    "revenues": "Revenue",
    "revenue": "Revenue",
    "operating_income": "Operating income",
    "net_income": "Net income",
    "eps_basic": "EPS (basic)",
    "cfo": "Operating cash flow",
    "total_assets": "Total assets",
    "stockholders_equity": "Stockholders' equity",
    "long_term_debt": "Long-term debt",
    "cash": "Cash",
    "news_flow": "News flow",
    "op_margin": "Operating margin",
    "cfo_margin": "Cash conversion (CFO/revenue)",
    "core_business": "Core business",
    "respiratory_test_volume": "US respiratory testing volume",
    "growth_regime.revenues": "Revenue growth regime",
    "growth_regime.revenue": "Revenue growth regime",
    "growth_regime.operating_income": "Operating income growth regime",
    "growth_regime.cfo": "Cash flow growth regime",
    "growth_regime.net_income": "Net income growth regime",
    "growth_regime.eps_basic": "EPS growth regime",
}


def load_json(path: Path, default=None):
    if not path.exists():
        return default if default is not None else {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default if default is not None else {}


def to_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_date(period: str) -> datetime | None:
    try:
        return datetime.strptime(str(period)[:10], "%Y-%m-%d")
    except (TypeError, ValueError):
        return None


def metric_base_name(metric: str) -> str:
    return str(metric or "").split(".")[-1]


def metric_tier(metric: str) -> str:
    base = metric_base_name(metric)
    if base in METRIC_TIER_PRIMARY:
        return "primary"
    if base in METRIC_TIER_SECONDARY:
        return "secondary"
    if base in METRIC_TIER_EXCLUDED:
        return "excluded"
    if base in METRIC_TIER_CONTEXT:
        return "context"
    return "primary"


def strength(metric: dict) -> float:
    return abs(metric.get("accel") or 0) / max(metric.get("threshold") or 1e-9, 1e-9)


def robust_vol(history: list[float]) -> float:
    """Median absolute deviation scaled to approximate std dev."""
    if not history:
        return 0.0
    if len(history) == 1:
        return abs(history[0])
    med = statistics.median(history)
    deviations = [abs(x - med) for x in history]
    mad = statistics.median(deviations)
    return mad * 1.4826 if mad > 0 else abs(history[-1])


def rolling_median(values: list[float], window: int = SMOOTH_WINDOW) -> list[float]:
    if len(values) < window:
        return list(values)
    out: list[float] = []
    for i in range(len(values)):
        if i + 1 < window:
            out.append(values[i])
        else:
            chunk = values[i + 1 - window : i + 1]
            out.append(statistics.median(chunk))
    return out


def classify_accel(latest_accel: float, history: list[float], *, floor: float) -> tuple[str, float]:
    vol = robust_vol(history)
    threshold = max(floor, VOL_MULTIPLIER * vol)
    if latest_accel > threshold:
        return "accelerating", threshold
    if latest_accel < -threshold:
        return "decelerating", threshold
    return "steady", threshold


def signal_tier_from_accels(accels: list[float], direction: str, threshold: float) -> str:
    if direction == "steady" or len(accels) < 2:
        return "steady" if direction == "steady" else "emerging"
    prev = accels[-2]
    if direction == "accelerating" and prev > threshold:
        return "confirmed"
    if direction == "decelerating" and prev < -threshold:
        return "confirmed"
    return "emerging"


def enrich_analysis(
    analysis: dict,
    *,
    metric_key: str,
    raw_accels: list[float],
    ttm_analysis: dict | None = None,
    series_meta: dict | None = None,
) -> dict:
    """Attach tier, persistence, materiality, strength, freshness, and TTM agreement."""
    direction = analysis["direction"]
    threshold = analysis["threshold"]
    material = passes_materiality(analysis.get("growth_latest"), metric_key, direction=direction)
    tier = signal_tier_from_accels(raw_accels, direction, threshold)
    if not material and direction != "steady":
        direction = "steady"
        tier = "steady"

    fresh = series_meta or {}
    stale = bool(fresh.get("stale"))
    if stale and direction != "steady":
        tier = "steady"
        direction = "steady"

    ttm_agrees: bool | None = None
    if ttm_analysis and analysis.get("basis") == "yoy":
        q_dir = direction
        t_dir = ttm_analysis.get("direction")
        if q_dir in ("accelerating", "decelerating"):
            if t_dir == q_dir:
                ttm_agrees = True
            elif t_dir in ("accelerating", "decelerating"):
                ttm_agrees = False

    if tier == "emerging" and ttm_agrees is True:
        tier = "confirmed"

    artifact = is_growth_artifact(
        growth_latest=analysis.get("growth_latest"),
        growth_prior=analysis.get("growth_prior"),
        level_prior=analysis.get("level_prior"),
        level_latest=analysis.get("level_latest"),
        level_yoy_base=analysis.get("level_yoy_base"),
    )

    accel = analysis.get("accel")
    out = {
        **analysis,
        "metric": analysis.get("metric") or metric_key,
        "direction": direction,
        "signal_tier": tier,
        "tier": metric_tier(metric_key),
        "material": material,
        "strength": round(strength({**analysis, "direction": direction}), 3),
        "confidence": (
            "high"
            if (
                accel is not None
                and threshold
                and abs(accel) >= HIGH_CONFIDENCE_MULT * threshold
                and not artifact
            )
            else "med"
        ),
        "ttm_agrees": ttm_agrees,
        "artifact": artifact,
        "display": False,
        "composite": False,
        "stale": stale,
        "latest_period": fresh.get("latest_period"),
        "series_age_days": fresh.get("age_days"),
        "revenue_proxy": bool(fresh.get("proxy")),
    }
    return attach_human_summary(out)


def compute_yoy_growths(
    ordered: list[tuple[str, float]],
    dates: list[datetime | None],
    values: list[float],
) -> tuple[list[tuple[str, float]], int, dict | None]:
    nonzero = [abs(v) for v in values if abs(v) > 1e-9]
    scale = statistics.median(nonzero) if nonzero else 0.0
    denom_floor = max(1e-9, DENOMINATOR_FLOOR_FRAC * scale)

    growths: list[tuple[str, float]] = []
    level_meta: dict | None = None
    suspect = 0
    lo, hi = YOY_MATCH_WINDOW
    for i in range(len(ordered)):
        match = None
        for j in range(i - 1, -1, -1):
            days = (dates[i] - dates[j]).days
            if lo <= days <= hi:
                match = j
                break
            if days > hi:
                break
        if match is None:
            continue
        prev, cur = values[match], values[i]
        if abs(prev) < denom_floor:
            suspect += 1
            continue
        growth = (cur - prev) / abs(prev)
        if abs(growth) > GROWTH_OUTLIER_CAP:
            suspect += 1
            continue
        growths.append((ordered[i][0], growth))
        prior_level = level_meta.get("level_latest") if level_meta else None
        level_meta = {
            "level_latest": cur,
            "level_yoy_base": prev,
            "level_prior": prior_level if prior_level is not None else prev,
            "period_latest": ordered[i][0],
            "period_yoy_base": ordered[match][0],
        }
        if len(growths) >= 2:
            # Prior growth period's level (previous YoY observation's current value).
            prev_growth_period = growths[-2][0]
            for period, value in ordered:
                if period == prev_growth_period:
                    level_meta["level_prior"] = value
                    break
    return growths, suspect, level_meta


def analyze_growth_values(
    gvals: list[float],
    *,
    floor: float,
    metric_key: str,
    basis: str,
    mode: str,
    points: list[dict],
    suspect: int = 0,
    series_meta: dict | None = None,
) -> dict | None:
    min_growth = YOY_MIN_GROWTH_POINTS if basis == "yoy" else 3
    if len(gvals) < min_growth:
        return None

    raw_accels = [b - a for a, b in zip(gvals, gvals[1:])]
    if basis == "yoy":
        smoothed = rolling_median(gvals)
        accels = [b - a for a, b in zip(smoothed, smoothed[1:])]
    else:
        smoothed = gvals
        accels = raw_accels
    direction, threshold = classify_accel(accels[-1], accels[:-1], floor=floor)

    analysis = {
        "direction": direction,
        "basis": basis,
        "growth_latest": round(gvals[-1], 4),
        "growth_prior": round(gvals[-2], 4),
        "growth_smoothed_latest": round(smoothed[-1], 4),
        "accel": round(accels[-1], 4),
        "accel_raw": round(raw_accels[-1], 4),
        "threshold": round(threshold, 4),
        "mode": mode,
        "suspect_points": suspect,
        "points": points,
    }
    return enrich_analysis(
        analysis,
        metric_key=metric_key,
        raw_accels=accels,
        series_meta=series_meta,
    )


def _levels_for_period(
    ordered: list[tuple[str, float]],
    dates: list[datetime | None],
    period: str,
) -> tuple[float | None, float | None]:
    """Return (year_ago_level, current_level) for a fiscal period."""
    lo, hi = YOY_MATCH_WINDOW
    target = None
    for i, (p, _v) in enumerate(ordered):
        if p == period:
            target = i
            break
    if target is None or dates[target] is None:
        return None, None
    match = None
    for j in range(target - 1, -1, -1):
        if dates[j] is None:
            continue
        days = (dates[target] - dates[j]).days
        if lo <= days <= hi:
            match = j
            break
        if days > hi:
            break
    cur = ordered[target][1]
    base = ordered[match][1] if match is not None else None
    return base, cur


def quarterly_to_ttm(ordered: list[tuple[str, float]]) -> list[tuple[str, float]]:
    if len(ordered) < 4:
        return []
    return [(ordered[i][0], sum(v for _p, v in ordered[i - 3 : i + 1])) for i in range(3, len(ordered))]


def analyze_quarterly_yoy(
    series: list[dict],
    *,
    metric_key: str = "",
    series_meta: dict | None = None,
) -> dict | None:
    """Second derivative of year-over-year growth for a quarterly series."""
    cleaned: dict[str, float] = {}
    for point in series:
        value = to_float(point.get("value"))
        period = str(point.get("period") or "")[:10]
        if value is None or not parse_date(period):
            continue
        cleaned[period] = value
    ordered = sorted(cleaned.items())
    if len(ordered) < YOY_MIN_QUARTERS:
        return None

    meta = dict(series_meta or series_freshness(series))
    dates = [parse_date(p) for p, _v in ordered]
    values = [v for _p, v in ordered]
    growths, suspect, level_meta = compute_yoy_growths(ordered, dates, values)
    if len(growths) < YOY_MIN_GROWTH_POINTS:
        return None

    gvals = [g for _p, g in growths]
    floor = MATERIALITY_FLOORS.get(metric_base_name(metric_key), 0.03)
    points = [{"period": p, "value": v} for p, v in ordered[-MAX_POINTS:]]

    result = analyze_growth_values(
        gvals,
        floor=floor,
        metric_key=metric_key,
        basis="yoy",
        mode="pct",
        points=points,
        suspect=suspect,
        series_meta=meta,
    )
    if result is None:
        return None

    if level_meta:
        if level_meta.get("level_latest") is not None:
            result["level_latest"] = level_meta["level_latest"]
        if level_meta.get("level_prior") is not None:
            result["level_prior"] = level_meta["level_prior"]
        if level_meta.get("level_yoy_base") is not None:
            result["level_yoy_base"] = level_meta["level_yoy_base"]
        result["artifact"] = is_growth_artifact(
            growth_latest=result.get("growth_latest"),
            growth_prior=result.get("growth_prior"),
            level_prior=result.get("level_prior"),
            level_latest=result.get("level_latest"),
            level_yoy_base=result.get("level_yoy_base"),
        )
        attach_human_summary(result)

    ttm_ordered = quarterly_to_ttm(ordered)
    if len(ttm_ordered) >= YOY_MIN_QUARTERS:
        ttm_dates = [parse_date(p) for p, _v in ttm_ordered]
        ttm_values = [v for _p, v in ttm_ordered]
        ttm_growths, _, _ = compute_yoy_growths(ttm_ordered, ttm_dates, ttm_values)
        if len(ttm_growths) >= YOY_MIN_GROWTH_POINTS:
            ttm_gvals = [g for _p, g in ttm_growths]
            ttm_result = analyze_growth_values(
                ttm_gvals,
                floor=floor,
                metric_key=metric_key,
                basis="yoy",
                mode="pct",
                points=[{"period": p, "value": v} for p, v in ttm_ordered[-MAX_POINTS:]],
                series_meta=meta,
            )
            if ttm_result:
                smooth = rolling_median(gvals)
                ttm_accels = [b - a for a, b in zip(smooth, smooth[1:])] if len(smooth) > 1 else []
                base = {k: v for k, v in result.items() if k not in (
                    "signal_tier", "tier", "material", "strength", "confidence",
                    "ttm_agrees", "display", "composite", "stale", "latest_period",
                    "series_age_days", "revenue_proxy", "human_summary", "artifact",
                )}
                result = enrich_analysis(
                    base,
                    metric_key=metric_key,
                    raw_accels=ttm_accels,
                    ttm_analysis=ttm_result,
                    series_meta=meta,
                )
                result["ttm_direction"] = ttm_result.get("direction")
                result["ttm_growth_latest"] = ttm_result.get("growth_latest")

    return result


def yoy_growth_series(series: list[dict]) -> list[tuple[str, float]]:
    cleaned: dict[str, float] = {}
    for point in series:
        value = to_float(point.get("value"))
        period = str(point.get("period") or "")[:10]
        if value is None or not parse_date(period):
            continue
        cleaned[period] = value
    ordered = sorted(cleaned.items())
    if len(ordered) < YOY_MIN_QUARTERS:
        return []
    dates = [parse_date(p) for p, _v in ordered]
    values = [v for _p, v in ordered]
    growths, _, _ = compute_yoy_growths(ordered, dates, values)
    return growths


def series_level_context(
    series: list[dict],
    *,
    latest_period: str | None,
    prior_period: str | None = None,
) -> dict[str, float | None]:
    """Map fiscal periods to raw levels for regime human summaries / artifact gates."""
    cleaned: dict[str, float] = {}
    for point in series:
        value = to_float(point.get("value"))
        period = str(point.get("period") or "")[:10]
        if value is None or not parse_date(period):
            continue
        cleaned[period] = value
    ordered = sorted(cleaned.items())
    dates = [parse_date(p) for p, _v in ordered]
    level_latest = cleaned.get(latest_period) if latest_period else None
    level_prior = cleaned.get(prior_period) if prior_period else None
    level_yoy_base = None
    if latest_period:
        level_yoy_base, cur = _levels_for_period(ordered, dates, latest_period)
        if level_latest is None:
            level_latest = cur
    return {
        "level_prior": level_prior,
        "level_latest": level_latest,
        "level_yoy_base": level_yoy_base,
    }


def build_regime_metric(
    growths: list[tuple[str, float]],
    *,
    metric_key: str,
    series: list[dict],
    evidence_ref: str,
    series_meta: dict | None = None,
) -> dict | None:
    latest_period = growths[-1][0] if growths else None
    prior_period = growths[-2][0] if len(growths) >= 2 else None
    levels = series_level_context(series, latest_period=latest_period, prior_period=prior_period)
    regime = analyze_growth_regime(
        growths,
        metric_key=metric_key,
        level_prior=levels.get("level_prior"),
        level_latest=levels.get("level_latest"),
        level_yoy_base=levels.get("level_yoy_base"),
    )
    if not regime:
        return None
    meta = series_meta or series_freshness(series)
    if meta.get("stale"):
        return None
    regime.update(
        {
            "source": "sec_fundamentals",
            "evidence_ref": evidence_ref,
            "points": [
                {"period": str(x.get("period") or "")[:10], "value": x.get("value")}
                for x in series[-MAX_POINTS:]
                if x.get("period")
            ],
            "stale": False,
            "latest_period": meta.get("latest_period"),
            "series_age_days": meta.get("age_days"),
            "revenue_proxy": bool(meta.get("proxy")),
        }
    )
    return attach_human_summary(regime)


def analyze_series(
    points: list[tuple[str, float]],
    *,
    mode: str = "pct",
    metric_key: str = "",
) -> dict | None:
    """Sequential first/second derivative for non-quarterly series."""
    cleaned: dict[str, float] = {}
    for period, value in points:
        if not period or value is None:
            continue
        cleaned[str(period)[:10]] = float(value)
    ordered = sorted(cleaned.items())[-MAX_POINTS:]
    if len(ordered) < MIN_POINTS:
        return None

    values = [v for _p, v in ordered]
    growths: list[float] = []
    for prev, cur in zip(values, values[1:]):
        if mode == "diff":
            growths.append(cur - prev)
        else:
            if abs(prev) < 1e-9:
                return None
            growth = (cur - prev) / abs(prev)
            if abs(growth) > GROWTH_OUTLIER_CAP:
                return None
            growths.append(growth)
    if len(growths) < 3:
        return None

    floor = 1.0 if mode == "diff" else MATERIALITY_FLOORS.get(metric_base_name(metric_key), 0.02)
    return analyze_growth_values(
        growths,
        floor=floor,
        metric_key=metric_key,
        basis="seq",
        mode=mode,
        points=[{"period": p, "value": v} for p, v in ordered],
    )


def derive_ratio_series(numerator: list[dict], denominator: list[dict]) -> list[dict]:
    num_map = {
        str(p.get("period") or "")[:10]: to_float(p.get("value"))
        for p in numerator
        if to_float(p.get("value")) is not None
    }
    denom_map = {
        str(p.get("period") or "")[:10]: to_float(p.get("value"))
        for p in denominator
        if to_float(p.get("value")) is not None
    }
    out: list[dict] = []
    for period in sorted(set(num_map) & set(denom_map)):
        denom = denom_map[period]
        if denom is None or abs(denom) < 1e-9:
            continue
        out.append({"period": period, "value": num_map[period] / denom})
    return out


def collapse_core_signals(metrics: list[dict]) -> list[dict]:
    """When multiple core operating metrics align, emit one composite signal."""
    firing = [
        m
        for m in metrics
        if metric_base_name(m.get("metric") or "") in CORE_COLLAPSE_METRICS
        and m.get("direction") in ("accelerating", "decelerating")
        and m.get("signal_tier") in ("confirmed", "emerging")
        and m.get("tier") != "excluded"
    ]
    if len(firing) < 2:
        return metrics

    by_direction: dict[str, list[dict]] = {}
    for m in firing:
        by_direction.setdefault(m["direction"], []).append(m)

    composites: list[dict] = []
    for direction, group in by_direction.items():
        if len(group) < 2:
            continue
        group.sort(key=strength, reverse=True)
        tiers = {m.get("signal_tier") for m in group}
        signal_tier = "confirmed" if tiers == {"confirmed"} or (tiers <= {"confirmed", "emerging"} and "confirmed" in tiers) else "emerging"
        avg_strength = statistics.mean(strength(m) for m in group)
        lead = group[0]
        composite = attach_human_summary(
            {
                "metric": "core_business",
                "label": METRIC_LABELS["core_business"],
                "source": lead.get("source"),
                "evidence_ref": lead.get("evidence_ref"),
                "direction": direction,
                "signal_tier": signal_tier,
                "tier": "primary",
                "basis": lead.get("basis"),
                "mode": "pct",
                "growth_latest": lead.get("growth_latest"),
                "growth_prior": lead.get("growth_prior"),
                "level_prior": lead.get("level_prior"),
                "level_latest": lead.get("level_latest"),
                "level_yoy_base": lead.get("level_yoy_base"),
                "accel": lead.get("accel"),
                "threshold": lead.get("threshold"),
                "strength": round(avg_strength, 3),
                "confidence": "high" if avg_strength >= HIGH_CONFIDENCE_MULT else "med",
                "material": True,
                "ttm_agrees": any(m.get("ttm_agrees") for m in group if m.get("ttm_agrees") is not None) or None,
                "composite": True,
                "composite_members": [m.get("metric") for m in group],
                "display": True,
                "points": lead.get("points") or [],
            }
        )
        composites.append(composite)
        for m in group:
            m["display"] = False
            m["collapsed_into"] = "core_business"

    return composites + metrics


def apply_display_cap(metrics: list[dict]) -> None:
    """Cap visible inflections: composites first, then one regime, then 2 primary + 1 secondary.

    Artifact / sign-flip signals stay in the payload for All signals but are not
    displayed by default. When multiple regime rows fire, keep the highest-priority
    metric only (revenue > operating income > CFO > net income / EPS).
    """
    for m in metrics:
        if m.get("composite"):
            if m.get("artifact"):
                m["display"] = False
            continue
        if m.get("stale"):
            m["display"] = False
            continue
        # Exogenous demand drivers keep the display flag their builder set and are
        # excluded from the fundamentals display budget below.
        if m.get("tier") == "context":
            continue
        if m.get("tier") == "excluded":
            m["display"] = False
            continue
        if m.get("signal_type") == "regime":
            m["display"] = False
            continue
        if m.get("direction") not in ("accelerating", "decelerating", "downshift", "upshift"):
            m["display"] = False
            continue
        if m.get("signal_tier") == "steady":
            m["display"] = False
            continue
        if m.get("artifact"):
            m["display"] = False
            continue
        if "display" not in m or m.get("collapsed_into"):
            m["display"] = False

    regime_candidates = sorted(
        [
            m
            for m in metrics
            if m.get("signal_type") == "regime"
            and not m.get("stale")
            and not m.get("artifact")
            and m.get("direction") in ("downshift", "upshift")
            and m.get("signal_tier") in ("confirmed", "emerging")
        ],
        key=lambda m: (
            regime_metric_priority(m.get("metric") or ""),
            -(m.get("strength") or 0),
        ),
    )
    for m in regime_candidates[:1]:
        m["display"] = True

    candidates = [
        m
        for m in metrics
        if not m.get("composite")
        and m.get("signal_type") != "regime"
        and m.get("direction") in ("accelerating", "decelerating")
        and m.get("signal_tier") in ("confirmed", "emerging")
        and m.get("tier") != "excluded"
        and not m.get("collapsed_into")
        and not m.get("stale")
        and not m.get("artifact")
    ]
    primary = sorted([m for m in candidates if m.get("tier") == "primary"], key=strength, reverse=True)
    secondary = sorted([m for m in candidates if m.get("tier") == "secondary"], key=strength, reverse=True)

    shown = sum(1 for m in metrics if m.get("display") and m.get("tier") != "context")
    for m in primary[: max(0, MAX_PRIMARY_DISPLAY - shown)]:
        m["display"] = True
        shown += 1
    displayed_now = sum(1 for x in metrics if x.get("display") and x.get("tier") != "context")
    for m in secondary[: max(0, MAX_SECONDARY_DISPLAY - (shown - displayed_now))]:
        if not m.get("display"):
            m["display"] = True


def compute_business_momentum(metrics: list[dict]) -> dict | None:
    score = 0.0
    weight_sum = 0.0
    for m in metrics:
        if m.get("stale"):
            continue
        base = metric_base_name(m.get("metric") or "")
        if m.get("signal_type") == "regime":
            if m.get("direction") == "downshift":
                sign = -1.0
                weight = BMS_WEIGHTS.get(base.replace("growth_regime.", ""), 0.25)
            elif m.get("direction") == "upshift":
                sign = 1.0
                weight = BMS_WEIGHTS.get(base.replace("growth_regime.", ""), 0.25)
            else:
                continue
            score += sign * weight * min(m.get("strength") or 1.0, 3.0)
            weight_sum += weight
            continue
        weight = BMS_WEIGHTS.get(base)
        if not weight or m.get("direction") not in ("accelerating", "decelerating"):
            continue
        sign = 1.0 if m["direction"] == "accelerating" else -1.0
        score += sign * weight * min(strength(m), 3.0)
        weight_sum += weight
    if weight_sum <= 0:
        return None
    normalized = score / weight_sum
    if normalized > 0.15:
        direction = "accelerating"
        label = "Business momentum improving"
    elif normalized < -0.15:
        direction = "decelerating"
        label = "Business momentum fading"
    else:
        direction = "steady"
        label = "Business momentum neutral"
    return {
        "score": round(normalized, 3),
        "direction": direction,
        "label": label,
    }


def finalize_ticker_entry(entry: dict, *, leadership_risk: dict | None = None) -> None:
    metrics = entry.get("metrics") or []
    for m in metrics:
        if not m.get("human_summary"):
            attach_human_summary(m)
    metrics[:] = collapse_core_signals(metrics)
    apply_display_cap(metrics)

    summary = {
        "accelerating": 0,
        "decelerating": 0,
        "steady": 0,
        "confirmed": 0,
        "emerging": 0,
        "displayed": 0,
        "regime_downshift": 0,
        "stale_suppressed": 0,
    }
    for m in metrics:
        direction = m.get("direction") or "steady"
        if m.get("signal_type") == "regime" and direction == "downshift":
            summary["regime_downshift"] += 1
        elif direction in summary:
            summary[direction] += 1
        tier = m.get("signal_tier")
        if tier in ("confirmed", "emerging"):
            summary[tier] += 1
        if m.get("stale") and m.get("direction") not in ("steady", None):
            summary["stale_suppressed"] += 1
        if m.get("display"):
            summary["displayed"] += 1

    entry["summary"] = summary
    entry["business_momentum"] = compute_business_momentum(metrics)
    if leadership_risk:
        entry["leadership_risk"] = leadership_risk


def fundamentals_series() -> dict[str, dict[str, list[dict]]]:
    """ticker -> metric -> quarterly series from the XBRL cache."""
    out: dict[str, dict[str, list[dict]]] = {}
    if not FUNDAMENTALS_DIR.is_dir():
        return out
    for path in sorted(FUNDAMENTALS_DIR.glob("*.json")):
        if path.stem.startswith("_"):
            continue
        doc = load_json(path)
        metrics = doc.get("metrics") if isinstance(doc, dict) else None
        if not isinstance(metrics, dict):
            continue
        out[str(doc.get("ticker") or path.stem).upper()] = metrics
    return out


def derive_burn_rate_series(cfo: list[dict], cash: list[dict]) -> list[dict]:
    """Quarterly cash burn (positive = consuming cash) for pre-revenue names."""
    cfo_map = {
        str(p.get("period") or "")[:10]: to_float(p.get("value"))
        for p in cfo
        if to_float(p.get("value")) is not None
    }
    out: list[dict] = []
    for period, value in sorted(cfo_map.items()):
        if value is None or value >= 0:
            continue
        out.append({"period": period, "value": abs(value)})
    return out


RESPIRATORY_DRIVER_SERIES = ("flu_clinical_specimens", "rsv_naat_tests", "sars_cov2_naat_tests")
RESPIRATORY_MIN_WEEKS = 12
# Materiality is measured against the series' own recent volatility rather than a
# magic number. The window is deliberately short: 2021-2023 YoY swings (+388% to
# -60%) are COVID unwind, and including them inflates the threshold to ~25pp and
# suppresses everything. Post-COVID robust vol runs ~12pp.
RESPIRATORY_VOL_WINDOW = 8
RESPIRATORY_MIN_THRESHOLD = 0.10


def _read_weekly_csv(path: Path) -> dict[str, float]:
    if not path.exists():
        return {}
    out: dict[str, float] = {}
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                value = to_float(row.get("value"))
                day = str(row.get("date") or "")[:10]
                if value is not None and day:
                    out[day] = value
    except OSError:
        return {}
    return out


def respiratory_quarterly_volume() -> dict[str, dict]:
    """Total US respiratory NAAT volume, averaged weekly, by calendar quarter.

    Calendar quarters are deliberate: this is an exogenous driver read, not a
    revenue estimate, so it does not need any issuer's fiscal calendar.
    """
    weekly: dict[str, float] = {}
    counts: dict[str, int] = {}
    for series_id in RESPIRATORY_DRIVER_SERIES:
        for day, value in _read_weekly_csv(RESPIRATORY_DIR / f"{series_id}.csv").items():
            weekly[day] = weekly.get(day, 0.0) + value
            counts[day] = counts.get(day, 0) + 1
    if not weekly:
        return {}
    # Only weeks where every series reported, so the sum is comparable across time.
    full = {d: v for d, v in weekly.items() if counts.get(d) == len(RESPIRATORY_DRIVER_SERIES)}
    buckets: dict[str, list[float]] = {}
    for day, value in full.items():
        parsed = parse_date(day)
        if not parsed:
            continue
        buckets.setdefault(f"{parsed.year}-Q{(parsed.month - 1) // 3 + 1}", []).append(value)
    return {
        q: {"mean_weekly": sum(v) / len(v), "weeks": len(v)}
        for q, v in buckets.items()
        if len(v) >= RESPIRATORY_MIN_WEEKS
    }


def respiratory_context_metric() -> dict | None:
    """Latest complete quarter's YoY change in US respiratory testing volume.

    Reported on the *level* of YoY change, not its second derivative: a demand
    base that is persistently 25% below last year matters to a diagnostics issuer
    even when the rate of decline is unchanged, which an inflection test reads as
    'steady'. Emitted as context - excluded from business momentum and from the
    primary/secondary display competition.
    """
    quarters = respiratory_quarterly_volume()
    if len(quarters) < 5:
        return None
    ordered = sorted(quarters)

    def yoy_at(label: str) -> float | None:
        year, q = label.split("-Q")
        prior = f"{int(year) - 1}-Q{q}"
        if prior not in quarters or quarters[prior]["mean_weekly"] <= 0:
            return None
        return quarters[label]["mean_weekly"] / quarters[prior]["mean_weekly"] - 1

    history = [(label, yoy_at(label)) for label in ordered]
    history = [(label, g) for label, g in history if g is not None]
    if not history:
        return None
    latest, growth = history[-1]
    prior_growth = history[-2][1] if len(history) >= 2 else None

    window = [g for _label, g in history[-RESPIRATORY_VOL_WINDOW:]]
    threshold = max(RESPIRATORY_MIN_THRESHOLD, robust_vol(window))

    if growth <= -threshold:
        direction = "decelerating"
        phrase = f"ran {abs(growth) * 100:.0f}% below"
    elif growth >= threshold:
        direction = "accelerating"
        phrase = f"ran {growth * 100:.0f}% above"
    else:
        direction = "steady"
        phrase = f"was within {threshold * 100:.0f}% of"

    quarter_ends = {"1": "03-31", "2": "06-30", "3": "09-30", "4": "12-31"}
    points = []
    for label in ordered[-MAX_POINTS:]:
        py, pq = label.split("-Q")
        points.append({
            "period": f"{py}-{quarter_ends[pq]}",
            "value": round(quarters[label]["mean_weekly"], 1),
        })
    return {
        "metric": "respiratory_test_volume",
        "label": METRIC_LABELS["respiratory_test_volume"],
        "source": "respiratory_panel",
        "evidence_ref": "_system/reference/market-data/respiratory/manifest.json",
        "signal_type": "demand_driver",
        "direction": direction,
        "signal_tier": "context",
        "tier": "context",
        "basis": "yoy",
        "mode": "pct",
        "growth_latest": round(growth, 4),
        "growth_prior": round(prior_growth, 4) if prior_growth is not None else None,
        "accel": None,
        "threshold": round(threshold, 4),
        "material": abs(growth) >= threshold,
        "strength": round(abs(growth) / threshold, 3),
        "confidence": "high",
        "ttm_agrees": None,
        "artifact": False,
        "composite": False,
        "stale": False,
        "display": direction != "steady",
        "latest_period": latest,
        "points": points,
        "human_summary": (
            f"US respiratory testing volume {phrase} the year-ago quarter in {latest} "
            f"(flu + RSV + COVID NAAT). Demand context, not a revenue estimate."
        ),
    }


def respiratory_context_tickers() -> list[str]:
    themes = (load_json(HOLDINGS_THEMES_PATH, {}).get("themes") or {})
    block = themes.get("respiratory_diagnostics") or {}
    return [str(t).upper() for t in (block.get("tickers") or [])]


def resolve_data_tier(
    ticker: str,
    *,
    has_fundamentals: bool,
    has_equity: bool,
    has_news_signal: bool,
    has_cik: bool,
) -> str:
    if has_fundamentals:
        return "sec_fundamentals"
    if has_equity:
        return "equity_model"
    if has_cik:
        return "sec_pending"
    if has_news_signal:
        return "news_governance"
    return "none"


def equity_panel_series(models_doc: dict) -> dict[str, dict[str, list[tuple[str, float]]]]:
    """Semi-annual panel rows from equity model bundles."""
    out: dict[str, dict[str, list[tuple[str, float]]]] = {}
    for ticker, entry in ((models_doc or {}).get("tickers") or {}).items():
        panel = entry.get("panel") or []
        if not isinstance(panel, list):
            continue
        by_field: dict[str, list[tuple[str, float]]] = {}
        for row in panel:
            if not isinstance(row, dict):
                continue
            period = (row.get("period_end") or row.get("period") or "")[:10]
            if not period:
                continue
            for field in ("revenue", "net_income", "ordinary", "base_fee", "perf_fee"):
                value = to_float(row.get(field))
                if value is None:
                    continue
                metric = "revenues" if field == "revenue" else field
                by_field.setdefault(metric, []).append((period, value))
        if by_field:
            out[str(ticker).upper()] = by_field
    return out


def load_earnings_by_ticker() -> dict[str, list[dict]]:
    doc = load_json(EARNINGS_CALENDAR_PATH, {})
    grouped: dict[str, list[dict]] = {}
    for event in (doc or {}).get("events") or []:
        ticker = str(event.get("portfolio_ticker") or event.get("ticker") or "").upper()
        if not ticker:
            continue
        grouped.setdefault(ticker, []).append(event)
    for path in sorted(ROOT.glob("*/research/evidence/earnings_calendar.json")):
        per_ticker_doc = load_json(path, {})
        ticker = str(per_ticker_doc.get("ticker") or path.parts[0]).upper()
        for event in (per_ticker_doc or {}).get("events") or []:
            grouped.setdefault(ticker, []).append(event)
    return grouped


def apply_peer_relative_overlays(by_ticker: dict[str, dict], registry: dict) -> int:
    """Compare revenue YoY growth to investment-sleeve peers."""
    holdings = registry.get("holdings") or {}
    sleeve_growth: dict[str, list[tuple[str, float]]] = {}
    for ticker, entry in by_ticker.items():
        holding = holdings.get(ticker) or {}
        sleeve = (holding.get("classification") or {}).get("investment_sleeve") or "unclassified"
        for metric in entry.get("metrics") or []:
            if metric.get("metric") not in ("revenues", "revenue"):
                continue
            if metric.get("direction") not in ("accelerating", "decelerating", "steady"):
                continue
            growth = metric.get("growth_latest")
            if growth is None:
                continue
            sleeve_growth.setdefault(sleeve, []).append((ticker, float(growth)))

    added = 0
    for ticker, entry in by_ticker.items():
        holding = holdings.get(ticker) or {}
        sleeve = (holding.get("classification") or {}).get("investment_sleeve") or "unclassified"
        peers = sleeve_growth.get(sleeve) or []
        own_growth = None
        for metric in entry.get("metrics") or []:
            if metric.get("metric") in ("revenues", "revenue") and metric.get("growth_latest") is not None:
                own_growth = float(metric["growth_latest"])
                break
        if own_growth is None:
            continue
        peer_vals = [g for tk, g in peers if tk != ticker]
        signal = peer_relative_signal(own_growth, peer_vals, metric_key="revenues")
        if not signal:
            continue
        signal["source"] = "peer_relative"
        signal["evidence_ref"] = "_system/portfolio/registry.json"
        entry.setdefault("metrics", []).append(signal)
        added += 1
    return added


def apply_earnings_revision_signals(by_ticker: dict[str, dict], earnings_by_ticker: dict[str, list[dict]]) -> int:
    added = 0
    for ticker, events in earnings_by_ticker.items():
        signal = earnings_revision_signal(events)
        if not signal:
            continue
        entry = by_ticker.setdefault(ticker, {"metrics": []})
        signal["source"] = "earnings_revision"
        signal["evidence_ref"] = "_system/data/earnings_calendar.json"
        entry.setdefault("metrics", []).append(signal)
        added += 1
    return added


def ensure_universe_coverage(
    by_ticker: dict[str, dict],
    universe: list[str],
    *,
    fundamentals: set[str],
    equity_tickers: set[str],
    resolvable_ciks: set[str],
    news_doc: dict | None,
) -> None:
    for ticker in universe:
        entry = by_ticker.setdefault(ticker, {"metrics": []})
        has_fundamentals = ticker in fundamentals
        has_equity = ticker in equity_tickers
        has_news = any(
            m.get("metric") == "news_flow"
            for m in (entry.get("metrics") or [])
        )
        entry["data_tier"] = resolve_data_tier(
            ticker,
            has_fundamentals=has_fundamentals,
            has_equity=has_equity,
            has_news_signal=has_news,
            has_cik=ticker in resolvable_ciks,
        )
        if not entry.get("summary"):
            entry["summary"] = {
                "accelerating": 0,
                "decelerating": 0,
                "steady": 0,
                "confirmed": 0,
                "emerging": 0,
                "displayed": 0,
                "regime_downshift": 0,
                "stale_suppressed": 0,
            }


def equity_model_series(ticker: str, models_doc: dict) -> dict[str, list[tuple[str, float]]]:
    """Extract observation series (lists of {period, <numeric>}) from equity models."""
    entry = ((models_doc or {}).get("tickers") or {}).get(ticker) or {}
    forms = (entry.get("production") or {}).get("forms") or {}
    out: dict[str, list[tuple[str, float]]] = {}
    for form_key, form in forms.items():
        if not isinstance(form, dict):
            continue
        observations = form.get("observations")
        if not isinstance(observations, list):
            continue
        by_field: dict[str, list[tuple[str, float]]] = {}
        for obs in observations:
            if not isinstance(obs, dict):
                continue
            period = obs.get("period")
            if not period:
                continue
            for field, raw in obs.items():
                if field == "period":
                    continue
                value = to_float(raw)
                if value is None:
                    continue
                by_field.setdefault(field, []).append((str(period)[:10], value))
        for field, points in by_field.items():
            out[f"{form_key}.{field}"] = points
    return out


def news_flow_series(news_doc: dict) -> dict[str, list[tuple[str, float]]]:
    """Monthly news item counts per ticker from the current feed window."""
    items = (news_doc or {}).get("items") or []
    counts: dict[str, dict[str, float]] = {}
    for item in items:
        published = str(item.get("published_utc") or "")[:7]
        if not published or len(published) != 7:
            continue
        for ticker in item.get("tickers") or []:
            bucket = counts.setdefault(str(ticker).upper(), {})
            bucket[published] = bucket.get(published, 0.0) + 1
    return {
        ticker: [(f"{m}-01", v) for m, v in sorted(by_month.items())]
        for ticker, by_month in counts.items()
    }


def merged_news_history(news_doc: dict, *, write: bool = True) -> dict[str, list[tuple[str, float]]]:
    """Merge the current 30-day feed into a persistent monthly history."""
    history = load_json(NEWS_HISTORY_PATH, {})
    by_ticker: dict[str, dict[str, float]] = {
        str(t).upper(): {str(m): float(v) for m, v in (months or {}).items()}
        for t, months in (history.get("by_ticker") or {}).items()
    }
    months_observed = set(history.get("months_observed") or [])

    current = news_flow_series(news_doc)
    for ticker, points in current.items():
        bucket = by_ticker.setdefault(ticker, {})
        for period, count in points:
            month = period[:7]
            months_observed.add(month)
            bucket[month] = max(bucket.get(month, 0.0), count)

    if write:
        NEWS_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        NEWS_HISTORY_PATH.write_text(
            json.dumps(
                {
                    "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "months_observed": sorted(months_observed),
                    "by_ticker": by_ticker,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    this_month = datetime.now(timezone.utc).strftime("%Y-%m")
    usable_months = sorted(m for m in months_observed if m < this_month)
    out: dict[str, list[tuple[str, float]]] = {}
    for ticker, bucket in by_ticker.items():
        out[ticker] = [(f"{m}-01", bucket.get(m, 0.0)) for m in usable_months[-NEWS_WINDOW_MONTHS:]]
    return out


def build_trends() -> dict:
    models_doc = load_json(EQUITY_MODELS_PATH)
    news_doc = load_json(NEWS_PATH)
    news_series = merged_news_history(news_doc if isinstance(news_doc, dict) else {})
    fundamentals = fundamentals_series()
    registry = load_json(REGISTRY_PATH, {})
    universe = sorted((registry.get("holdings") or {}).keys())

    by_ticker: dict[str, dict] = {}
    suspect_excluded = 0

    def add_metric(ticker: str, metric: str, source: str, analysis: dict, evidence_ref: str | None) -> None:
        entry = by_ticker.setdefault(ticker, {"metrics": []})
        entry["metrics"].append(
            {
                "metric": metric,
                "label": METRIC_LABELS.get(metric_base_name(metric), metric.replace("_", " ").title()),
                "source": source,
                "evidence_ref": evidence_ref,
                **analysis,
            }
        )

    for ticker, metrics in sorted(fundamentals.items()):
        evidence_ref = f"_system/reference/market-data/fundamentals/{ticker}.json"
        freshness = cross_metric_freshness(metrics)
        revenue_series, rev_meta = resolve_revenue_series(metrics)
        derived: dict[str, list[dict]] = {}
        if revenue_series and not rev_meta.get("proxy"):
            if metrics.get("operating_income"):
                derived["op_margin"] = derive_ratio_series(metrics["operating_income"], revenue_series)
            if metrics.get("cfo"):
                derived["cfo_margin"] = derive_ratio_series(metrics["cfo"], revenue_series)

        rev_latest = to_float(revenue_series[-1].get("value")) if revenue_series else None
        pre_revenue = (
            not revenue_series
            or rev_meta.get("proxy")
            or (rev_latest is not None and abs(rev_latest) < 1_000_000)
        )
        if pre_revenue and metrics.get("cfo"):
            burn = derive_burn_rate_series(metrics["cfo"], metrics.get("cash") or [])
            if len(burn) >= MIN_POINTS:
                derived["burn_rate"] = burn

        all_metrics = {**metrics, **derived}
        growths_by_metric: dict[str, list[tuple[str, float]]] = {}

        for metric, series in sorted(all_metrics.items()):
            if metric == "revenues" and rev_meta.get("stale"):
                continue

            meta = freshness.get(metric) or series_freshness(series)
            if metric == "revenues" and rev_meta.get("proxy"):
                meta = {**rev_meta, "proxy": True}

            if metric in REGIME_METRICS and not meta.get("stale"):
                growths = yoy_growth_series(series)
                if growths:
                    growths_by_metric[metric] = growths

            analysis = analyze_quarterly_yoy(series, metric_key=metric, series_meta=meta)
            if analysis is None:
                continue

            suspect_excluded += analysis.pop("suspect_points", 0) or 0
            add_metric(ticker, metric, "sec_fundamentals", analysis, evidence_ref)

        for metric, growths in growths_by_metric.items():
            if metric not in REGIME_METRICS:
                continue
            series = all_metrics.get(metric) or []
            meta = freshness.get(metric) or series_freshness(series)
            regime = build_regime_metric(
                growths,
                metric_key=metric,
                series=series,
                evidence_ref=evidence_ref,
                series_meta=meta,
            )
            if regime:
                add_metric(ticker, regime["metric"], "sec_fundamentals", regime, evidence_ref)

    equity_model_tickers: set[str] = set()
    equity_kpi_doc = load_json(EQUITY_KPI_SERIES_PATH, {})
    panel_by_ticker = equity_panel_series(models_doc if isinstance(models_doc, dict) else {})

    def ingest_equity_points(ticker: str, metric: str, points: list[tuple[str, float]], evidence: str) -> None:
        analysis = analyze_series(points, mode="pct", metric_key=metric)
        if analysis:
            equity_model_tickers.add(ticker)
            add_metric(ticker, metric, "equity_model", analysis, evidence)

    for ticker in sorted(((models_doc or {}).get("tickers") or {}).keys()):
        for metric, points in equity_model_series(ticker, models_doc).items():
            ingest_equity_points(ticker, metric, points, "dashboard/data/equity_models.json")

    for ticker, fields in panel_by_ticker.items():
        for metric, points in fields.items():
            ingest_equity_points(ticker, metric, points, "dashboard/data/equity_models.json")

    for ticker, block in sorted(((equity_kpi_doc or {}).get("tickers") or {}).items()):
        tk = str(ticker).upper()
        for metric, series in (block.get("metrics") or {}).items():
            points = [
                (str(row.get("period") or "")[:10], float(row["value"]))
                for row in series
                if row.get("period") and to_float(row.get("value")) is not None
            ]
            if len(points) >= MIN_POINTS:
                ingest_equity_points(
                    tk,
                    metric,
                    points,
                    "dashboard/data/equity_kpi_series.json",
                )

    for ticker, points in news_series.items():
        analysis = analyze_series(points, mode="diff", metric_key="news_flow")
        if analysis and analysis["direction"] != "steady":
            add_metric(ticker, "news_flow", "news_flow", analysis, "dashboard/data/portfolio_news.json")

    from build_fundamental_series import resolve_ciks  # noqa: WPS433

    cik_map = resolve_ciks()
    resolvable_ciks = set(cik_map.keys())
    fundamentals_set = set(fundamentals.keys())
    earnings_by_ticker = load_earnings_by_ticker()
    peer_overlay_count = apply_peer_relative_overlays(by_ticker, registry)
    earnings_revision_count = apply_earnings_revision_signals(by_ticker, earnings_by_ticker)

    respiratory_metric = respiratory_context_metric()
    respiratory_count = 0
    if respiratory_metric:
        for ticker in respiratory_context_tickers():
            entry = by_ticker.setdefault(ticker, {"metrics": []})
            entry.setdefault("metrics", []).append(dict(respiratory_metric))
            respiratory_count += 1
    ensure_universe_coverage(
        by_ticker,
        universe,
        fundamentals=fundamentals_set,
        equity_tickers=equity_model_tickers,
        resolvable_ciks=resolvable_ciks,
        news_doc=news_doc if isinstance(news_doc, dict) else {},
    )

    missing_fundamentals = sorted(t for t in resolvable_ciks if t not in fundamentals_set)
    missing_cik = sorted(t for t in universe if t not in resolvable_ciks)
    no_trend_data = sorted(
        t for t in universe if (by_ticker.get(t) or {}).get("data_tier") in ("none", "sec_pending", "news_governance")
    )

    confirmed_count = 0
    emerging_count = 0
    displayed_count = 0
    regime_count = 0
    peer_relative_count = 0
    stale_suppressed = 0
    leadership_elevated = 0
    strength_values: list[float] = []

    for ticker, entry in by_ticker.items():
        leadership = compute_leadership_risk(ticker, news_doc if isinstance(news_doc, dict) else {})
        finalize_ticker_entry(entry, leadership_risk=leadership)
        if leadership.get("level") in ("elevated", "watch"):
            leadership_elevated += 1
        for metric in entry.get("metrics") or []:
            if metric.get("signal_tier") == "confirmed":
                confirmed_count += 1
            elif metric.get("signal_tier") == "emerging":
                emerging_count += 1
            if metric.get("signal_type") == "regime" and metric.get("direction") == "downshift":
                regime_count += 1
            if metric.get("signal_type") == "peer_relative":
                peer_relative_count += 1
            if metric.get("stale"):
                stale_suppressed += 1
            if metric.get("display"):
                displayed_count += 1
                strength_values.append(metric.get("strength") or 0)

    inflection_count = sum(
        1
        for entry in by_ticker.values()
        for metric in entry["metrics"]
        if metric.get("direction") != "steady" and metric.get("tier") != "excluded"
    )
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ticker_count": len(by_ticker),
        "inflection_count": inflection_count,
        "coverage": {
            "universe": len(universe),
            "resolvable_ciks": len(resolvable_ciks),
            "fundamentals_tickers": len(fundamentals),
            "equity_model_tickers": len(equity_model_tickers),
            "analyzed_tickers": sum(
                1 for t in universe if (by_ticker.get(t) or {}).get("data_tier") == "sec_fundamentals"
                or any((by_ticker.get(t) or {}).get("metrics"))
            ),
            "missing_fundamentals": missing_fundamentals,
            "missing_cik": missing_cik,
            "no_trend_data": no_trend_data,
            "suspect_points_excluded": suspect_excluded,
            "confirmed_count": confirmed_count,
            "emerging_count": emerging_count,
            "displayed_count": displayed_count,
            "regime_downshift_count": regime_count,
            "peer_relative_count": peer_relative_count,
            "earnings_revision_count": earnings_revision_count,
            "respiratory_context_count": respiratory_count,
            "stale_suppressed_count": stale_suppressed,
            "leadership_risk_watch": leadership_elevated,
            "avg_strength": round(statistics.mean(strength_values), 3) if strength_values else 0.0,
            "stale_max_days": STALE_SERIES_MAX_DAYS,
        },
        "by_ticker": by_ticker,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build KPI trend (second derivative) JSON.")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    payload = build_trends()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    cov = payload["coverage"]
    print(
        f"Wrote {args.output.relative_to(ROOT)} "
        f"({payload['ticker_count']} tickers, {cov['displayed_count']} displayed / "
        f"{payload['inflection_count']} raw inflections, "
        f"confirmed {cov['confirmed_count']}, emerging {cov['emerging_count']}, "
        f"fundamentals {cov['fundamentals_tickers']}/{cov['universe']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
