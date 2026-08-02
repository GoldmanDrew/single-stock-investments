"""Transparent intraday forced-flow and exhaustion proxies."""
from __future__ import annotations

import math
import statistics
from datetime import datetime, timezone
from typing import Sequence

FLOW_MODEL_VERSION = "forced-flow-intraday-v1"
MINUTES_PER_YEAR = 252 * 390
STATE_RANK = {
    "normal": 0,
    "observe": 1,
    "stress": 2,
    "exhaustion_candidate": 3,
    "confirmed_exhaustion": 4,
}


def apply_state_hysteresis(
    raw_state: str,
    prior: dict | None,
    *,
    upgrade_dwell: int = 2,
    downgrade_dwell: int = 3,
) -> tuple[str, dict]:
    """Require repeated observations before changing the published state."""
    if raw_state not in STATE_RANK:
        raise ValueError(f"unknown flow state: {raw_state}")
    prior = dict(prior or {})
    current = str(prior.get("state") or "normal")
    if current not in STATE_RANK:
        current = "normal"
    candidate = str(prior.get("candidate") or current)
    count = int(prior.get("count") or 0)
    if raw_state == current:
        return current, {"state": current, "candidate": current, "count": 0}
    if raw_state != candidate:
        candidate = raw_state
        count = 1
    else:
        count += 1
    required = (
        upgrade_dwell
        if STATE_RANK[raw_state] > STATE_RANK[current]
        else downgrade_dwell
    )
    if count >= required:
        current = raw_state
        candidate = current
        count = 0
    return current, {"state": current, "candidate": candidate, "count": count}


def _finite(value) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _clip(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _z_score(current: float, history: Sequence[float]) -> float:
    clean = [value for value in history if math.isfinite(value)]
    if len(clean) < 10:
        return 0.0
    spread = statistics.stdev(clean)
    return (current - statistics.mean(clean)) / spread if spread > 1e-12 else 0.0


def _weighted(values: Sequence[tuple[float | None, float]]) -> float:
    usable = [(value, weight) for value, weight in values if value is not None]
    total = sum(weight for _, weight in usable)
    if not total:
        return 0.0
    return sum(float(value) * weight for value, weight in usable) / total


def _returns(closes: Sequence[float]) -> list[float]:
    return [
        math.log(closes[index] / closes[index - 1])
        for index in range(1, len(closes))
        if closes[index] > 0 and closes[index - 1] > 0
    ]


def _realized_vol(returns: Sequence[float], window: int) -> float | None:
    tail = list(returns[-window:])
    if len(tail) < max(3, window // 2):
        return None
    return math.sqrt(sum(value * value for value in tail) / len(tail) * MINUTES_PER_YEAR)


def _window_return(closes: Sequence[float], window: int) -> float | None:
    if len(closes) <= window or closes[-window - 1] <= 0:
        return None
    return closes[-1] / closes[-window - 1] - 1.0


def _vol_target_reduction(returns: Sequence[float]) -> tuple[float | None, float | None]:
    if len(returns) < 40:
        return None, None
    current = _realized_vol(returns, 20)
    prior = _realized_vol(returns[:-20], 20)
    if current is None or prior is None or current <= 0 or prior <= 0:
        return None, None
    reductions = []
    for target in (0.08, 0.10, 0.12):
        prior_weight = min(1.0, target / prior)
        current_weight = min(1.0, target / current)
        reductions.append(max(0.0, prior_weight - current_weight) * 100.0)
    return min(reductions), max(reductions)


def calculate_flow_snapshot(
    symbol: str,
    bars: Sequence[dict],
    *,
    scope: str = "market",
    source: str = "databento:EQUS.MINI:ohlcv-1m",
    entitlement_mode: str = "live",
) -> dict:
    """Calculate one explainable flow snapshot from chronological minute bars."""
    clean = [
        row for row in bars
        if _finite(row.get("close")) is not None and _finite(row.get("close")) > 0
    ]
    if len(clean) < 20:
        raise ValueError("forced-flow snapshot requires at least 20 minute bars")
    closes = [float(row["close"]) for row in clean]
    returns = _returns(closes)
    volumes = [_finite(row.get("volume")) or 0.0 for row in clean]
    ranges = [
        (
            (float(row["high"]) - float(row["low"])) / float(row["close"])
            if _finite(row.get("high")) is not None
            and _finite(row.get("low")) is not None
            and float(row["close"]) > 0
            else 0.0
        )
        for row in clean
    ]
    last = clean[-1]
    rv5 = _realized_vol(returns, 5)
    rv30 = _realized_vol(returns, 30)
    volatility_acceleration = rv5 / rv30 if rv5 is not None and rv30 else None
    return5 = _window_return(closes, 5)
    minute_sigma = (
        rv30 / math.sqrt(MINUTES_PER_YEAR)
        if rv30 is not None and rv30 > 0 else None
    )
    return_stress_z = (
        -return5 / (minute_sigma * math.sqrt(5))
        if return5 is not None and minute_sigma else None
    )
    downside_variance = sum(value * value for value in returns[-15:] if value < 0)
    total_variance = sum(value * value for value in returns[-15:])
    downside_share = downside_variance / total_variance if total_variance > 0 else 0.0
    negative_share = (
        sum(value < 0 for value in returns[-15:]) / len(returns[-15:])
        if returns[-15:] else 0.0
    )
    volume_z = _z_score(volumes[-1], volumes[-61:-1])
    range_z = _z_score(ranges[-1], ranges[-61:-1])
    volume_score = _clip(50.0 + 15.0 * volume_z)
    range_score = _clip(50.0 + 15.0 * range_z)
    return_score = (
        _clip(50.0 + 15.0 * return_stress_z)
        if return_stress_z is not None else None
    )
    acceleration_score = (
        _clip(50.0 + 35.0 * (volatility_acceleration - 1.0))
        if volatility_acceleration is not None else None
    )
    pressure = _weighted(
        (
            (return_score, 0.30),
            (acceleration_score, 0.25),
            (100.0 * downside_share, 0.20),
            (100.0 * negative_share, 0.10),
            (volume_score, 0.075),
            (range_score, 0.075),
        )
    )
    panic = _weighted(
        (
            (pressure, 0.55),
            (volume_score, 0.20),
            (range_score, 0.20),
            (100.0 * downside_share, 0.05),
        )
    )

    previous_rv5 = _realized_vol(returns[:-5], 5)
    prior_return5 = _window_return(closes[:-5], 5)
    current_open = _finite(last.get("open"))
    current_high = _finite(last.get("high"))
    current_low = _finite(last.get("low"))
    current_close = float(last["close"])
    close_location = (
        (2.0 * current_close - current_high - current_low) / (current_high - current_low)
        if current_high is not None and current_low is not None and current_high > current_low
        else 0.0
    )
    confirmations = {
        "positive_interval": bool(
            current_open is not None and current_close > current_open
        ),
        "closed_upper_half": close_location > 0,
        "volatility_decelerating": bool(
            rv5 is not None and previous_rv5 is not None and rv5 < previous_rv5
        ),
        "selling_decelerating": bool(
            return5 is not None and prior_return5 is not None and return5 > prior_return5
        ),
        "volume_cooling": bool(
            len(volumes) >= 10 and volumes[-1] < max(volumes[-10:-1])
        ),
    }
    exhaustion = _weighted(
        (
            (100.0 if confirmations["positive_interval"] else 0.0, 0.15),
            (_clip((close_location + 1.0) * 50.0), 0.20),
            (100.0 if confirmations["volatility_decelerating"] else 0.0, 0.25),
            (100.0 if confirmations["selling_decelerating"] else 0.0, 0.25),
            (100.0 if confirmations["volume_cooling"] else 0.0, 0.15),
        )
    )
    confirmation_count = sum(confirmations.values())
    if panic >= 75 and exhaustion >= 65 and confirmation_count >= 3:
        state = "confirmed_exhaustion"
    elif panic >= 70 and exhaustion >= 45:
        state = "exhaustion_candidate"
    elif panic >= 70:
        state = "stress"
    elif pressure >= 55:
        state = "observe"
    else:
        state = "normal"

    reduction_low, reduction_high = _vol_target_reduction(returns)
    as_of = (
        str(last.get("event_time") or last.get("ts") or last.get("date") or "")
        or datetime.now(timezone.utc).isoformat()
    )
    return {
        "scope": scope,
        "symbol": symbol.upper(),
        "as_of": as_of,
        "model_version": FLOW_MODEL_VERSION,
        "state": state,
        "raw_state": state,
        "scores": {
            "pressure": round(pressure, 1),
            "panic": round(panic, 1),
            "exhaustion": round(exhaustion, 1),
            "liquidity": None,
            "breadth": None,
        },
        "features": {
            "return_5m_pct": None if return5 is None else round(return5 * 100.0, 3),
            "realized_vol_5m_pct": None if rv5 is None else round(rv5 * 100.0, 2),
            "realized_vol_30m_pct": None if rv30 is None else round(rv30 * 100.0, 2),
            "volatility_acceleration": (
                None if volatility_acceleration is None
                else round(volatility_acceleration, 3)
            ),
            "downside_variance_share_15m": round(downside_share, 3),
            "negative_interval_share_15m": round(negative_share, 3),
            "volume_z": round(volume_z, 3),
            "range_z": round(range_z, 3),
            "close_location": round(close_location, 3),
        },
        "vol_target": {
            "estimated_exposure_reduction_pct_low": (
                None if reduction_low is None else round(reduction_low, 3)
            ),
            "estimated_exposure_reduction_pct_high": (
                None if reduction_high is None else round(reduction_high, 3)
            ),
            "target_volatility_scenarios": [0.08, 0.10, 0.12],
            "interpretation": "Scenario proxy, not observed fund holdings or trades.",
        },
        "confirmation": confirmations,
        "source": source,
        "entitlement_mode": entitlement_mode,
        "quality_state": "ready" if len(clean) >= 60 else "limited",
        "bar_count": len(clean),
        "policy": "Pressure and exhaustion require independent confirmation.",
    }
