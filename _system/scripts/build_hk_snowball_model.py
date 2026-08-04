#!/usr/bin/env python3
"""Build Horizon Kinetics-style BTC snowball / power-law + supply-cost dashboard JSON.

Context only — never auto-inflates Lawrence base IRR.
See HK Q2 2026 Commentary: demand ~t^k (k slightly under 6) vs supply (halving cost floor).

  python _system/scripts/build_hk_snowball_model.py
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CRYPTO_DIR = ROOT / "_system" / "reference" / "market-data" / "crypto"
EQUITY_DIR = ROOT / "_system" / "reference" / "market-data" / "equity"
OUT_DASHBOARD = ROOT / "dashboard" / "data" / "hk_snowball_model.json"
OUT_REF = CRYPTO_DIR / "hk_snowball_model.json"

# HK commentary anchors
BTC_ORIGIN = date(2011, 1, 1)  # demand-model origin used in commentary examples
AMZN_ORIGIN = date(1997, 5, 15)
NEXT_HALVING = date(2028, 4, 15)
HK_MODEL_2028 = 270438.05  # commentary quote (illustrative)
DEFAULT_KWH = 0.05  # HK illustrative electricity cost
DEFAULT_CURRENT_ALL_IN = 65000.0  # HK illustrative current all-in cost
PREMIUM_ABOVE_COST = 1.75  # ~75% premium above production cost
POWER_SHARE = 0.60
K_LO, K_HI = 4.0, 6.5
MILESTONE_FRACS = (0.25, 0.50, 0.75, 0.90, 1.00)

# Known subsidy halvings (UTC calendar dates, approximate)
HALVINGS = [
    date(2012, 11, 28),
    date(2016, 7, 9),
    date(2020, 5, 11),
    date(2024, 4, 20),
    NEXT_HALVING,
]

DISCLAIMER = "Context only. Not a trade signal. Not in base IRR."

SCRIPTS = Path(__file__).resolve().parent
CRYPTO_CFG = SCRIPTS / "crypto_panel_config.json"

# Subsidy BTC per block by post-halving epoch index
SUBSIDY_BY_HALVING_INDEX = {
    0: 50.0,
    1: 25.0,
    2: 12.5,
    3: 6.25,
    4: 3.125,
    5: 1.5625,
}


def load_snowball_cfg() -> dict:
    if not CRYPTO_CFG.exists():
        return {}
    try:
        cfg = json.loads(CRYPTO_CFG.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return cfg.get("snowball") or {}


def block_subsidy_on(d: date) -> float:
    n = halvings_before(d)
    if n <= 0:
        return SUBSIDY_BY_HALVING_INDEX[0]
    if n >= 5:
        return SUBSIDY_BY_HALVING_INDEX[5]
    return SUBSIDY_BY_HALVING_INDEX.get(n, 3.125)


def all_in_cost_usd(
    hash_eh: float,
    *,
    subsidy_btc: float,
    efficiency_j_th: float,
    electricity_usd_kwh: float,
    power_share: float,
) -> float | None:
    """Network electricity cost per coin / power_share => all-in production cost."""
    if hash_eh <= 0 or subsidy_btc <= 0 or power_share <= 0:
        return None
    power_w = hash_eh * 1e6 * efficiency_j_th
    kwh_per_day = power_w * 24.0 / 1000.0
    elec_per_day = kwh_per_day * electricity_usd_kwh
    coins_per_day = 144.0 * subsidy_btc
    elec_per_coin = elec_per_day / coins_per_day
    return elec_per_coin / power_share


def live_cost_path(
    hash_eh: list[tuple[date, float]],
    *,
    efficiency_j_th: float,
    electricity_usd_kwh: float,
    power_share: float,
    premium_multiple: float,
) -> list[dict]:
    out: list[dict] = []
    for d, h in hash_eh:
        cost = all_in_cost_usd(
            h,
            subsidy_btc=block_subsidy_on(d),
            efficiency_j_th=efficiency_j_th,
            electricity_usd_kwh=electricity_usd_kwh,
            power_share=power_share,
        )
        if cost is None or cost <= 0:
            continue
        out.append(
            {
                "d": d.isoformat(),
                "v": round(cost, 2),
                "all_in_cost_usd": round(cost, 2),
                "premium_band_usd": round(cost * premium_multiple, 2),
            }
        )
    if out:
        last_v = out[-1]["v"]
        out.append(
            {
                "d": NEXT_HALVING.isoformat(),
                "v": round(last_v * 2.0, 2),
                "all_in_cost_usd": round(last_v * 2.0, 2),
                "premium_band_usd": round(last_v * 2.0 * premium_multiple, 2),
                "event": "halving_projection",
            }
        )
    return out


def _read_csv(path: Path) -> list[tuple[date, float]]:
    if not path.exists():
        return []
    rows: list[tuple[date, float]] = []
    with path.open(encoding="utf-8", newline="") as f:
        for i, row in enumerate(csv.DictReader(f)):
            try:
                d = date.fromisoformat(str(row.get("date") or "").strip())
                v = float(row.get("value"))
            except (TypeError, ValueError):
                continue
            if v <= 0:
                continue
            rows.append((d, v))
    rows.sort(key=lambda x: x[0])
    return rows


def years_since(origin: date, d: date) -> float:
    return max((d - origin).days / 365.25, 1e-6)


def milestones(
    series: list[tuple[date, float]],
    *,
    origin: date | None = None,
    fracs: tuple[float, ...] = MILESTONE_FRACS,
) -> list[dict]:
    if len(series) < 2:
        return []
    t0 = origin or series[0][0]
    t1 = series[-1][0]
    span = max((t1 - t0).days, 1)
    terminal = series[-1][1]
    out: list[dict] = []
    for frac in fracs:
        target = t0 + timedelta(days=int(round(span * frac)))
        # nearest observation on or before target (else first)
        price = series[0][1]
        obs_d = series[0][0]
        for d, v in series:
            if d <= target:
                price, obs_d = v, d
            else:
                break
        out.append(
            {
                "time_frac": frac,
                "target_date": target.isoformat(),
                "obs_date": obs_d.isoformat(),
                "price": round(price, 6),
                "pct_of_terminal": round(100.0 * price / terminal, 2) if terminal else None,
            }
        )
    return out


def fit_power_law(
    series: list[tuple[date, float]],
    *,
    origin: date = BTC_ORIGIN,
    k_fixed: float | None = None,
) -> dict:
    """OLS on log P = log A + k log(t), optionally constrain k to [K_LO, K_HI]."""
    xs: list[float] = []
    ys: list[float] = []
    for d, p in series:
        t = years_since(origin, d)
        if t < 0.25 or p <= 0:
            continue
        xs.append(math.log(t))
        ys.append(math.log(p))
    n = len(xs)
    if n < 30:
        return {"ok": False, "error": "insufficient_points", "n": n}

    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    var_x = sum((x - mean_x) ** 2 for x in xs)
    if var_x <= 0:
        return {"ok": False, "error": "zero_variance", "n": n}
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    k_free = cov / var_x
    log_a_free = mean_y - k_free * mean_x

    if k_fixed is not None:
        k = float(k_fixed)
    else:
        k = min(max(k_free, K_LO), K_HI)
    # Re-estimate A at chosen k: minimize sum (log P - log A - k log t)^2
    log_a = mean_y - k * mean_x
    a = math.exp(log_a)

    # R^2 in log space at constrained k
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    ss_res = sum((y - (log_a + k * x)) ** 2 for x, y in zip(xs, ys))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else None

    return {
        "ok": True,
        "origin": origin.isoformat(),
        "n": n,
        "k": round(k, 6),
        "k_free": round(k_free, 6),
        "A": a,
        "log_A": log_a,
        "r2_log": round(r2, 6) if r2 is not None else None,
        "k_constrained": k_fixed is None and (k != k_free),
    }


def model_price(fit: dict, d: date) -> float | None:
    if not fit.get("ok"):
        return None
    origin = date.fromisoformat(fit["origin"])
    t = years_since(origin, d)
    return float(fit["A"]) * (t ** float(fit["k"]))


def downsample(series: list[tuple[date, float]], max_points: int = 400) -> list[dict]:
    if len(series) <= max_points:
        return [{"d": d.isoformat(), "v": round(v, 6)} for d, v in series]
    step = max(len(series) // max_points, 1)
    picked = series[::step]
    if picked[-1][0] != series[-1][0]:
        picked.append(series[-1])
    return [{"d": d.isoformat(), "v": round(v, 6)} for d, v in picked]


def next_10x_date(fit: dict, spot: float, as_of: date) -> dict | None:
    """Solve A * t^k = 10 * spot for calendar date."""
    if not fit.get("ok") or spot <= 0:
        return None
    target = 10.0 * spot
    origin = date.fromisoformat(fit["origin"])
    a, k = float(fit["A"]), float(fit["k"])
    if a <= 0 or k <= 0:
        return None
    t_years = (target / a) ** (1.0 / k)
    days = int(round(t_years * 365.25))
    hit = origin + timedelta(days=days)
    return {
        "target_price": round(target, 2),
        "date": hit.isoformat(),
        "years_from_origin": round(t_years, 3),
        "years_from_as_of": round((hit - as_of).days / 365.25, 3),
    }


def halvings_before(d: date) -> int:
    return sum(1 for h in HALVINGS if h <= d)


def cost_curve(
    as_of: date,
    *,
    current_all_in: float = DEFAULT_CURRENT_ALL_IN,
    electricity_usd_kwh: float = DEFAULT_KWH,
    power_share: float = POWER_SHARE,
    premium_multiple: float = PREMIUM_ABOVE_COST,
    efficiency_j_th: float = 30.0,
    cost_path: list[dict] | None = None,
    source: str = "hk_step",
) -> dict:
    """Anchor all-in cost at as_of; walk ± halvings (each halves/doubles cost)."""
    n_now = halvings_before(as_of)
    points: list[dict] = []
    for h in HALVINGS:
        delta = halvings_before(h) - n_now
        cost = current_all_in * (2.0 ** delta)
        points.append(
            {
                "date": h.isoformat(),
                "event": "halving",
                "all_in_cost_usd": round(cost, 2),
                "premium_band_usd": round(cost * premium_multiple, 2),
            }
        )
    points.append(
        {
            "date": as_of.isoformat(),
            "event": "as_of",
            "all_in_cost_usd": round(current_all_in, 2),
            "premium_band_usd": round(current_all_in * premium_multiple, 2),
        }
    )
    points.sort(key=lambda p: p["date"])
    cost_2028 = current_all_in * 2.0
    return {
        "assumptions": {
            "electricity_usd_kwh": electricity_usd_kwh,
            "power_share_of_cost": power_share,
            "efficiency_j_th": efficiency_j_th,
            "current_all_in_usd": current_all_in,
            "current_all_in_source": source,
            "premium_multiple": premium_multiple,
            "next_halving": NEXT_HALVING.isoformat(),
            "note": (
                "Live path uses hashrate x efficiency x $/kWh / power_share. "
                "Halving projection doubles cost. HK $65k step used when live inputs missing."
            ),
        },
        "as_of_cost_usd": round(current_all_in, 2),
        "halving_2028_cost_usd": round(cost_2028, 2),
        "halving_2028_premium_band_usd": round(cost_2028 * premium_multiple, 2),
        "hk_commentary_band_usd": {"low": 150000, "high": 250000},
        "curve": points,
        "cost_path": cost_path or [],
    }


def dial_label(spot: float, model: float | None, floor: float) -> str:
    if model is None or model <= 0:
        return "insufficient_model"
    ratio = spot / model
    if spot < floor * 0.95:
        return "below_cost_floor"
    if ratio < 0.70:
        return "below_model"
    if ratio > 1.30:
        return "above_model"
    return "on_schedule"


def resolve_current_all_in(
    hash_eh: list[tuple[date, float]],
    *,
    efficiency_j_th: float,
    electricity_usd_kwh: float,
    power_share: float,
    hk_fallback: float,
) -> tuple[float, str]:
    if not hash_eh:
        return hk_fallback, "hk_step_fallback"
    live = all_in_cost_usd(
        hash_eh[-1][1],
        subsidy_btc=block_subsidy_on(hash_eh[-1][0]),
        efficiency_j_th=efficiency_j_th,
        electricity_usd_kwh=electricity_usd_kwh,
        power_share=power_share,
    )
    if live is None or live <= 0:
        return hk_fallback, "hk_step_fallback"
    return float(live), "live_hashrate_energy"


def build(*, as_of: date | None = None) -> Path:
    btc = _read_csv(CRYPTO_DIR / "btc_spot_usd.csv")
    # Merge committed pre-Yahoo seed even if fetch has not re-run yet
    seed = _read_csv(CRYPTO_DIR / "btc_spot_usd_seed_pre_yahoo.csv")
    if seed:
        merged = {d: v for d, v in seed}
        merged.update({d: v for d, v in btc})
        btc = sorted(merged.items())
    amzn = _read_csv(EQUITY_DIR / "amzn_weekly_usd.csv")
    hash_eh = _read_csv(CRYPTO_DIR / "btc_hash_rate_eh.csv")
    snow = load_snowball_cfg()
    efficiency_j_th = float(snow.get("efficiency_j_th") or 30)
    electricity_usd_kwh = float(snow.get("electricity_usd_kwh") or DEFAULT_KWH)
    power_share = float(snow.get("power_share") or POWER_SHARE)
    premium_multiple = float(snow.get("premium_multiple") or PREMIUM_ABOVE_COST)
    hk_fallback = float(snow.get("hk_current_all_in_usd") or DEFAULT_CURRENT_ALL_IN)

    if not btc:
        raise SystemExit("missing btc_spot_usd.csv — run fetch_crypto_panel.py first")

    as_of = as_of or btc[-1][0]
    spot = btc[-1][1]
    # Prefer observations from model origin forward for fit
    fit_series = [(d, v) for d, v in btc if d >= BTC_ORIGIN]
    if len(fit_series) < 30:
        fit_series = btc

    fit = fit_power_law(fit_series, origin=BTC_ORIGIN)

    # Unconstrained diagnostic (any k) for transparency vs HK ~t^6 claim
    def _fit_unconstrained() -> dict:
        xs, ys = [], []
        for d, p in fit_series:
            t = years_since(BTC_ORIGIN, d)
            if t < 0.25 or p <= 0:
                continue
            xs.append(math.log(t))
            ys.append(math.log(p))
        n = len(xs)
        if n < 30:
            return {"ok": False}
        mx, my = sum(xs) / n, sum(ys) / n
        vx = sum((x - mx) ** 2 for x in xs)
        if vx <= 0:
            return {"ok": False}
        k = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / vx
        log_a = my - k * mx
        return {"ok": True, "k": round(k, 6), "A": math.exp(log_a), "n": n}

    fit_raw = _fit_unconstrained()

    model_now = model_price(fit, as_of)
    model_2028 = model_price(fit, NEXT_HALVING)

    # Theoretical path (monthly samples)
    theo: list[dict] = []
    if fit.get("ok") and fit_series:
        d0, d1 = fit_series[0][0], max(fit_series[-1][0], NEXT_HALVING)
        cursor = date(d0.year, d0.month, 1)
        while cursor <= d1:
            mp = model_price(fit, cursor)
            if mp is not None:
                theo.append({"d": cursor.isoformat(), "v": round(mp, 4)})
            if cursor.month == 12:
                cursor = date(cursor.year + 1, 1, 1)
            else:
                cursor = date(cursor.year, cursor.month + 1, 1)

    current_all_in, cost_source = resolve_current_all_in(
        hash_eh,
        efficiency_j_th=efficiency_j_th,
        electricity_usd_kwh=electricity_usd_kwh,
        power_share=power_share,
        hk_fallback=hk_fallback,
    )
    path = live_cost_path(
        hash_eh,
        efficiency_j_th=efficiency_j_th,
        electricity_usd_kwh=electricity_usd_kwh,
        power_share=power_share,
        premium_multiple=premium_multiple,
    )
    # Downsample dense cost path for JSON size
    if len(path) > 400:
        step = max(len(path) // 350, 1)
        kept = path[::step]
        if path[-1] not in kept:
            kept.append(path[-1])
        path = kept
    supply = cost_curve(
        as_of,
        current_all_in=current_all_in,
        electricity_usd_kwh=electricity_usd_kwh,
        power_share=power_share,
        premium_multiple=premium_multiple,
        efficiency_j_th=efficiency_j_th,
        cost_path=path,
        source=cost_source,
    )

    residual_pct = None
    if model_now and model_now > 0:
        residual_pct = round(100.0 * (spot - model_now) / model_now, 2)

    label = dial_label(spot, model_now, supply["as_of_cost_usd"])

    # Hashrate overlay (optional)
    hash_points = downsample(hash_eh, max_points=200) if hash_eh else []

    payload = {
        "schema_version": "1.1",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of": as_of.isoformat(),
        "disclaimer": DISCLAIMER,
        "source_commentary": (
            "Horizon Kinetics Q2 2026 Commentary: "
            "Math Model of Compounding / What's With the Price of Bitcoin?"
        ),
        "hk_reference": {
            "model_2028": HK_MODEL_2028,
            "supply_low": 150000,
            "supply_high": 250000,
            "current_all_in_commentary": DEFAULT_CURRENT_ALL_IN,
        },
        "spot": {
            "btc_usd": round(spot, 4),
            "source": "btc_spot_usd.csv",
        },
        "milestones": {
            "btc": {
                "origin": (btc[0][0].isoformat() if btc else None),
                "terminal_date": as_of.isoformat(),
                "terminal_price": round(spot, 4),
                "stops": milestones(btc),
            },
            "amzn": {
                "origin": (amzn[0][0].isoformat() if amzn else AMZN_ORIGIN.isoformat()),
                "terminal_date": amzn[-1][0].isoformat() if amzn else None,
                "terminal_price": round(amzn[-1][1], 4) if amzn else None,
                "stops": milestones(amzn) if amzn else [],
                "note": "Kept for research; not shown on dashboard panel.",
            },
        },
        "demand": {
            "form": "P(t) = A * (years_since_origin)^k",
            "fit": fit,
            "fit_unconstrained": fit_raw,
            "model_price_as_of": round(model_now, 2) if model_now else None,
            "model_price_2028_04_15": round(model_2028, 2) if model_2028 else None,
            "hk_commentary_model_2028": HK_MODEL_2028,
            "residual_pct_vs_model": residual_pct,
            "next_10x": next_10x_date(fit, spot, as_of),
            "actual_path": downsample(fit_series, max_points=450),
            "model_path": theo,
            "interpretation": "Demand ~ t^k near t^6. Each 10x takes longer.",
        },
        "supply": supply,
        "hashrate": {
            "unit": "EH/s",
            "points": hash_points,
            "latest": round(hash_eh[-1][1], 4) if hash_eh else None,
            "as_of": hash_eh[-1][0].isoformat() if hash_eh else None,
        },
        "dial": {
            "label": label,
            "spot_vs_model_pct": residual_pct,
            "spot_vs_cost_floor_pct": (
                round(100.0 * (spot - supply["as_of_cost_usd"]) / supply["as_of_cost_usd"], 2)
                if supply["as_of_cost_usd"]
                else None
            ),
            "plain_english": {
                "on_schedule": "Near the long demand path. Drawdowns along a rising cost floor are normal.",
                "below_model": "Below the long demand path. Normal mid-cycle drawdown.",
                "above_model": "Above the long demand path.",
                "below_cost_floor": "Near or under the production-cost floor. Stressed miner economics.",
                "insufficient_model": "Not enough history to fit the demand path.",
            }.get(label, ""),
        },
        "calibration_notes": {
            "hk_demand_2028_usd": HK_MODEL_2028,
            "hk_supply_band_2028_usd": [150000, 250000],
            "hk_current_all_in_usd": DEFAULT_CURRENT_ALL_IN,
            "hk_kwh_assumption": electricity_usd_kwh,
            "our_demand_2028_usd": round(model_2028, 2) if model_2028 else None,
            "our_k": fit.get("k"),
            "our_k_unconstrained": fit_raw.get("k") if isinstance(fit_raw, dict) else None,
            "history_start_btc": fit_series[0][0].isoformat() if fit_series else None,
            "cost_source": cost_source,
            "live_cost_as_of": round(current_all_in, 2),
            "note": (
                "Demand fit uses Yahoo BTC-USD plus pre-Yahoo seed/blockchain backfill. "
                "Origin 2011-01-01. Live cost from hashrate energy model; HK markers are reference only."
            ),
        },
    }

    OUT_DASHBOARD.parent.mkdir(parents=True, exist_ok=True)
    CRYPTO_DIR.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2) + "\n"
    OUT_DASHBOARD.write_text(text, encoding="utf-8")
    OUT_REF.write_text(text, encoding="utf-8")
    return OUT_DASHBOARD


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--as-of", help="YYYY-MM-DD override")
    args = ap.parse_args()
    as_of = date.fromisoformat(args.as_of) if args.as_of else None
    out = build(as_of=as_of)
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
