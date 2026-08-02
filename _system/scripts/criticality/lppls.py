"""Deterministic LPPLS calibration and ensemble summaries.

This is a research-only implementation of the stable LPPLS parameterization:

    log p(t) = A + B f + C1 f cos(omega log(dt))
                     + C2 f sin(omega log(dt))
    f = (tc - t) ** m

The nonlinear search is limited to (tc, m, omega). The four remaining
coefficients are solved by linear least squares at every evaluation.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np
from scipy.optimize import least_squares

MODEL_VERSION = "lppls-ensemble-v1"
M_BOUNDS = (0.1, 0.9)
OMEGA_BOUNDS = (6.0, 13.0)


@dataclass(frozen=True)
class Fit:
    window: int
    tc_index: float
    m: float
    omega: float
    a: float
    b: float
    c1: float
    c2: float
    rmse: float
    relative_rmse: float
    oscillations: float
    damping: float | None
    relative_amplitude: float | None
    qualified: bool
    filter_reasons: tuple[str, ...]

    @property
    def direction(self) -> str:
        if self.b < 0:
            return "positive_bubble"
        if self.b > 0:
            return "negative_bubble"
        return "none"

    def as_dict(self, last_index: float) -> dict:
        return {
            "window": self.window,
            "direction": self.direction,
            "tc_days": round(self.tc_index - last_index, 2),
            "m": round(self.m, 5),
            "omega": round(self.omega, 5),
            "a": round(self.a, 8),
            "b": round(self.b, 8),
            "c1": round(self.c1, 8),
            "c2": round(self.c2, 8),
            "rmse": round(self.rmse, 8),
            "relative_rmse": round(self.relative_rmse, 6),
            "oscillations": round(self.oscillations, 3),
            "damping": None if self.damping is None else round(self.damping, 4),
            "relative_amplitude": (
                None if self.relative_amplitude is None
                else round(self.relative_amplitude, 4)
            ),
            "qualified": self.qualified,
            "filter_reasons": list(self.filter_reasons),
        }


def _linear_solution(
    t: np.ndarray,
    log_prices: np.ndarray,
    tc: float,
    m: float,
    omega: float,
) -> tuple[np.ndarray, np.ndarray] | None:
    dt = tc - t
    if np.any(dt <= 0):
        return None
    log_dt = np.log(dt)
    f = np.power(dt, m)
    design = np.column_stack(
        (
            np.ones_like(t),
            f,
            f * np.cos(omega * log_dt),
            f * np.sin(omega * log_dt),
        )
    )
    try:
        coefficients, _, rank, _ = np.linalg.lstsq(design, log_prices, rcond=None)
    except np.linalg.LinAlgError:
        return None
    if rank < 4 or not np.all(np.isfinite(coefficients)):
        return None
    return coefficients, design @ coefficients


def _quality(
    *,
    t: np.ndarray,
    tc: float,
    m: float,
    omega: float,
    b: float,
    c1: float,
    c2: float,
    relative_rmse: float,
) -> tuple[float, float | None, float | None, tuple[str, ...]]:
    dt_start = tc - float(t[0])
    dt_end = tc - float(t[-1])
    oscillations = omega / (2.0 * math.pi) * math.log(dt_start / dt_end)
    amplitude = math.hypot(c1, c2)
    relative_amplitude = amplitude / abs(b) if abs(b) > 1e-12 else None
    damping = m * abs(b) / (omega * amplitude) if amplitude > 1e-12 else None
    reasons: list[str] = []
    if oscillations < 2.5:
        reasons.append("too_few_oscillations")
    if relative_amplitude is None or relative_amplitude >= 1.0:
        reasons.append("oscillation_amplitude_too_large")
    if damping is None or damping < 0.5:
        reasons.append("weak_damping")
    if relative_rmse > 0.035:
        reasons.append("fit_error_too_large")
    return oscillations, damping, relative_amplitude, tuple(reasons)


def fit_lppls(
    prices: Sequence[float],
    *,
    window: int | None = None,
    max_nfev: int = 180,
) -> Fit:
    """Fit one LPPLS window with deterministic nonlinear starting points."""
    values = np.asarray(prices, dtype=float)
    if window is not None:
        values = values[-window:]
    if len(values) < 40:
        raise ValueError("LPPLS requires at least 40 positive observations")
    if np.any(~np.isfinite(values)) or np.any(values <= 0):
        raise ValueError("LPPLS prices must be finite and positive")

    log_prices = np.log(values)
    t = np.arange(len(values), dtype=float)
    last = float(t[-1])
    horizon = max(10.0, len(values) * 0.33)
    lower = np.array([last + 1.0, M_BOUNDS[0], OMEGA_BOUNDS[0]])
    upper = np.array([last + horizon, M_BOUNDS[1], OMEGA_BOUNDS[1]])
    scale = max(float(np.std(log_prices)), 1e-8)

    def residual(parameters: np.ndarray) -> np.ndarray:
        solution = _linear_solution(
            t, log_prices, float(parameters[0]), float(parameters[1]), float(parameters[2])
        )
        if solution is None:
            return np.full_like(log_prices, 1e3)
        return (solution[1] - log_prices) / scale

    starts = (
        (0.06, 0.25, 7.0),
        (0.12, 0.45, 9.0),
        (0.22, 0.65, 11.0),
        (0.30, 0.80, 12.5),
    )
    best = None
    for tc_fraction, m, omega in starts:
        x0 = np.array([last + max(1.5, horizon * tc_fraction), m, omega])
        result = least_squares(
            residual,
            x0=x0,
            bounds=(lower, upper),
            max_nfev=max_nfev,
            xtol=1e-8,
            ftol=1e-8,
            gtol=1e-8,
        )
        loss = float(np.dot(result.fun, result.fun))
        if best is None or loss < best[0]:
            best = (loss, result.x)
    if best is None:
        raise RuntimeError("LPPLS nonlinear calibration did not return a solution")

    tc, m, omega = (float(value) for value in best[1])
    solution = _linear_solution(t, log_prices, tc, m, omega)
    if solution is None:
        raise RuntimeError("LPPLS linear calibration failed")
    coefficients, fitted = solution
    a, b, c1, c2 = (float(value) for value in coefficients)
    residuals = fitted - log_prices
    rmse = float(np.sqrt(np.mean(np.square(residuals))))
    # Convert log residuals back to proportional price errors. This keeps the
    # qualification threshold interpretable across low- and high-volatility assets.
    relative_rmse = float(np.sqrt(np.mean(np.square(np.expm1(residuals)))))
    oscillations, damping, relative_amplitude, reasons = _quality(
        t=t,
        tc=tc,
        m=m,
        omega=omega,
        b=b,
        c1=c1,
        c2=c2,
        relative_rmse=relative_rmse,
    )
    return Fit(
        window=len(values),
        tc_index=tc,
        m=m,
        omega=omega,
        a=a,
        b=b,
        c1=c1,
        c2=c2,
        rmse=rmse,
        relative_rmse=relative_rmse,
        oscillations=oscillations,
        damping=damping,
        relative_amplitude=relative_amplitude,
        qualified=not reasons,
        filter_reasons=reasons,
    )


def _percentile(values: Iterable[float], percentile: float) -> float | None:
    items = list(values)
    if not items:
        return None
    return float(np.percentile(np.asarray(items, dtype=float), percentile))


def fit_ensemble(
    prices: Sequence[float],
    *,
    horizons: Sequence[int] = (60, 120, 250, 500, 750),
    nested_fractions: Sequence[float] = (0.70, 0.78, 0.86, 0.94, 1.0),
    max_nfev: int = 180,
) -> dict:
    """Fit nested windows and return confidence and critical-time distributions."""
    values = [float(value) for value in prices]
    fits: list[Fit] = []
    errors: list[dict] = []
    attempted_windows: set[int] = set()
    for horizon in horizons:
        for fraction in nested_fractions:
            window = min(len(values), max(40, int(round(horizon * fraction))))
            if window in attempted_windows or window > len(values):
                continue
            attempted_windows.add(window)
            try:
                fits.append(fit_lppls(values, window=window, max_nfev=max_nfev))
            except (ValueError, RuntimeError) as exc:
                errors.append({"window": window, "error": str(exc)})

    qualified = [fit for fit in fits if fit.qualified]
    positive = [fit for fit in qualified if fit.direction == "positive_bubble"]
    negative = [fit for fit in qualified if fit.direction == "negative_bubble"]
    attempted = len(attempted_windows)
    positive_confidence = 100.0 * len(positive) / attempted if attempted else 0.0
    negative_confidence = 100.0 * len(negative) / attempted if attempted else 0.0
    dominant = positive if len(positive) >= len(negative) else negative
    direction = (
        "positive_bubble" if dominant is positive and positive
        else "negative_bubble" if negative
        else "none"
    )
    last_index = float(max((fit.window for fit in fits), default=1) - 1)
    tc_days = [
        fit.tc_index - float(fit.window - 1)
        for fit in dominant
    ]
    dispersion = (
        _percentile(tc_days, 90) - _percentile(tc_days, 10)
        if tc_days else None
    )
    dominant_confidence = max(positive_confidence, negative_confidence)
    concentration = (
        max(0.0, min(100.0, 100.0 - 3.0 * dispersion))
        if dispersion is not None else 0.0
    )
    criticality_score = dominant_confidence * (0.65 + 0.35 * concentration / 100.0)
    return {
        "model_version": MODEL_VERSION,
        "direction": direction,
        "score": round(criticality_score, 1),
        "confidence": {
            "positive": round(positive_confidence, 1),
            "negative": round(negative_confidence, 1),
            "qualified": round(100.0 * len(qualified) / attempted, 1) if attempted else 0.0,
        },
        "critical_time": {
            "unit": "trading_days_after_as_of",
            "p10": None if not tc_days else round(_percentile(tc_days, 10), 1),
            "median": None if not tc_days else round(_percentile(tc_days, 50), 1),
            "p90": None if not tc_days else round(_percentile(tc_days, 90), 1),
            "dispersion": None if dispersion is None else round(dispersion, 1),
        },
        "fit_count": len(fits),
        "qualified_count": len(qualified),
        "attempted_count": attempted,
        "status": "ready" if attempted and len(fits) / attempted >= 0.8 else "limited",
        "fits": [
            fit.as_dict(float(fit.window - 1))
            for fit in sorted(fits, key=lambda item: item.window)
        ],
        "errors": errors,
        "interpretation": (
            "Qualified positive-bubble fits dominate the current ensemble."
            if direction == "positive_bubble"
            else "Qualified negative-bubble fits dominate the current ensemble."
            if direction == "negative_bubble"
            else "No qualified LPPLS direction dominates the current ensemble."
        ),
        "policy": (
            "The critical-time range describes regime instability, not a promised "
            "crash or reversal date."
        ),
    }
