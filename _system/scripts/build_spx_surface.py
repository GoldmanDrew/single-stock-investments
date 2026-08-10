#!/usr/bin/env python3
"""Build coarse SPX implied-vol surface snapshots from CBOE's delayed-quote feed.

Tier 2 of ``_system/proposals/vol_surface_visibility_plan_2026-08-10.md``.

Source
------
``https://cdn.cboe.com/api/global/delayed_quotes/options/_SPX.json`` -- keyless,
roughly 15 minutes delayed, serves the whole SPX/SPXW chain with CBOE's own IVs
and greeks. No entitlement, no key, no vendor relationship: everything here is a
*coarse* research overlay, never an execution or valuation input.

What is derived per snapshot
----------------------------
* spot (``data.current_price``, falling back to ``data.close``),
* per-tenor (1w / 1m / 3m / 6m, each the expiry *nearest* the target DTE -- the
  actual expiry and DTE are always recorded, the tenor label is never asserted
  as exact): ATM IV, 25-delta risk reversal, 25-delta butterfly, put-skew slope,
* a naive dealer-gamma proxy.

ASSUMPTIONS THAT ARE NOT OBSERVATIONS
-------------------------------------
1. ``dealer_gamma_proxy`` uses the *convention* that dealers are long calls and
   short puts (sign +1 on calls, -1 on puts). Nothing in this feed observes
   dealer positioning; the sign convention is an assumption inherited from the
   common street proxy, and it can be exactly backwards in any given regime.
   Emitted as ``sign_convention`` in the payload.
2. Open interest on a delayed feed is **start-of-day**: it does not include
   today's trading. Emitted as ``oi_caveat`` in the payload.
3. ATM IV is interpolated at **spot**, not at the forward. This feed carries no
   rate or dividend strip, so a forward cannot be derived without inventing
   inputs; at 6m tenors the forward sits above spot and the spot-referenced ATM
   IV therefore reads slightly high on a downward-sloping skew. Emitted as
   ``atm_reference``.
4. ``gamma_flip_estimate`` is deliberately **omitted**. Computing it honestly
   requires re-pricing gamma across hypothetical spot levels, which stacks a
   zero-rate / zero-dividend Black-Scholes assumption and a sticky-strike vol
   assumption on top of (1) and (2). A number built on four unverifiable
   assumptions is a fabrication, not an estimate.

Quality filter
--------------
The raw chain contains rows that are not usable quotes: no-bid wings, crossed
quotes, and nonsense IVs on deep-ITM strikes (a 200-strike call quotes an IV of
7.03 -- 703%). Every aggregate here uses only rows that carry a two-sided quote
(bid > 0, ask > bid), finite greeks, and an IV inside [0.01, 3.0]. Rejections
are counted by reason and published, so a silently thinning chain is visible.

Never fails the lane on a source hiccup: a fetch failure preserves the prior
history untouched and stamps ``quality_state='stale'`` on the latest payload,
following ``build_criticality_signals.py``.
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import re
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "dashboard" / "data"
HISTORY_NAME = "spx_surface_history.jsonl"
LATEST_NAME = "spx_surface_latest.json"

SOURCE_URL = "https://cdn.cboe.com/api/global/delayed_quotes/options/_SPX.json"
DELAYED_MINUTES = 15
USER_AGENT = "Mozilla/5.0 (compatible; MagisVolSurfaceResearch/1.0; +research-only)"
SCHEMA_VERSION = 1
MODEL_VERSION = "spx-surface-v1"

# Tenor label -> target calendar days-to-expiry. The selected expiry is the one
# nearest the target; the realised DTE is always reported alongside.
TENOR_TARGETS = (("1w", 7), ("1m", 30), ("3m", 91), ("6m", 182))

IV_MIN = 0.01
IV_MAX = 3.0
TARGET_DELTA = 0.25
# Put-skew slope is fitted over this moneyness band (K / S).
PUT_SKEW_BAND = (0.90, 1.00)
CONTRACT_MULTIPLIER = 100

OSI_RE = re.compile(r"^([A-Za-z]+)(\d{6})([CP])(\d{8})$")

REJECT_REASONS = (
    "unparsed_symbol",
    "missing_or_nonfinite_greeks",
    "no_bid",
    "crossed_or_locked_quote",
    "iv_out_of_bounds",
)


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------


def _finite(value):
    """Return value as a finite float, or None."""
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _round(value, digits=6):
    value = _finite(value)
    return None if value is None else round(value, digits)


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


# ---------------------------------------------------------------------------
# fetch
# ---------------------------------------------------------------------------


def fetch_chain(url: str = SOURCE_URL, *, attempts: int = 3, timeout: int = 45) -> dict:
    """Fetch and decode the CBOE delayed-quote JSON.

    Sends a descriptive User-Agent and asks for gzip (the payload is ~1.8MB
    compressed, ~20MB raw). Retries with linear backoff; raises on final failure
    so the caller can take the preserve-prior path.
    """
    last_error = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                },
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                encoding = (response.headers.get("Content-Encoding") or "").lower()
            if "gzip" in encoding:
                raw = gzip.decompress(raw)
            return json.loads(raw.decode("utf-8", errors="replace"))
        except (urllib.error.URLError, OSError, ValueError) as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(2 * attempt)
    raise RuntimeError(f"CBOE fetch failed after {attempts} attempts: {last_error}")


def load_fixture(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# parsing and filtering
# ---------------------------------------------------------------------------


def parse_osi(symbol) -> dict | None:
    """Parse an OSI option symbol, e.g. ``SPX260821C00200000``.

    Layout: variable-length alphabetic root, YYMMDD expiry, C or P, then an
    8-digit strike in thousandths (``00200000`` -> 200.0). Returns None for
    anything that does not parse or does not carry a real calendar date, so a
    malformed row is skipped rather than poisoning an aggregate.
    """
    if not isinstance(symbol, str):
        return None
    match = OSI_RE.match(symbol.strip())
    if not match:
        return None
    root, yymmdd, right, strike_raw = match.groups()
    try:
        expiry = datetime.strptime(yymmdd, "%y%m%d").date()
    except ValueError:
        return None
    strike = int(strike_raw) / 1000.0
    if strike <= 0:
        return None
    return {
        "symbol": symbol.strip(),
        "root": root.upper(),
        "expiry": expiry,
        "right": right.upper(),
        "strike": strike,
    }


def classify_row(row: dict) -> tuple[dict | None, str | None]:
    """Return (clean_row, None) or (None, reject_reason) for one raw chain row.

    Reason precedence is fixed so the counts are stable across runs:
    unparsed symbol, then missing greeks, then no bid, then crossed quote,
    then implausible IV.
    """
    parsed = parse_osi((row or {}).get("option"))
    if parsed is None:
        return None, "unparsed_symbol"

    iv = _finite(row.get("iv"))
    delta = _finite(row.get("delta"))
    gamma = _finite(row.get("gamma"))
    if iv is None or delta is None or gamma is None:
        return None, "missing_or_nonfinite_greeks"

    bid = _finite(row.get("bid"))
    ask = _finite(row.get("ask"))
    if bid is None or bid <= 0:
        return None, "no_bid"
    if ask is None or ask <= bid:
        return None, "crossed_or_locked_quote"

    if iv < IV_MIN or iv > IV_MAX:
        return None, "iv_out_of_bounds"

    open_interest = _finite(row.get("open_interest"))
    oi_coerced = open_interest is None or open_interest < 0
    if oi_coerced:
        open_interest = 0.0

    clean = dict(parsed)
    clean.update(
        {
            "iv": iv,
            "delta": delta,
            "gamma": gamma,
            "bid": bid,
            "ask": ask,
            "open_interest": open_interest,
            "oi_coerced_zero": oi_coerced,
        }
    )
    return clean, None


def filter_rows(options) -> tuple[list[dict], dict]:
    """Apply the quality filter to the whole chain, counting rejects by reason."""
    kept: list[dict] = []
    rejected = {reason: 0 for reason in REJECT_REASONS}
    oi_coerced = 0
    for row in options or []:
        clean, reason = classify_row(row)
        if clean is None:
            rejected[reason] = rejected.get(reason, 0) + 1
            continue
        if clean["oi_coerced_zero"]:
            oi_coerced += 1
        kept.append(clean)
    quality = {
        "rows_total": len(options or []),
        "rows_used": len(kept),
        "rows_rejected": sum(rejected.values()),
        "rows_rejected_by_reason": rejected,
        "rows_open_interest_coerced_zero": oi_coerced,
        "filter": {
            "requires_two_sided_quote": "bid > 0 and ask > bid",
            "iv_bounds": [IV_MIN, IV_MAX],
            "requires_finite_greeks": ["iv", "delta", "gamma"],
        },
    }
    return kept, quality


# ---------------------------------------------------------------------------
# tenor selection
# ---------------------------------------------------------------------------


def group_chains(rows: list[dict], as_of: date) -> list[dict]:
    """Group quality rows into (expiry, root) chains with a calendar DTE.

    SPX (AM-settled) and SPXW (PM-settled) can share an expiry date but are
    different contracts with different vols, so they are kept as separate
    chains rather than blended.
    """
    buckets: dict[tuple, list[dict]] = {}
    for row in rows:
        buckets.setdefault((row["expiry"], row["root"]), []).append(row)
    chains = []
    for (expiry, root), members in buckets.items():
        chains.append(
            {
                "expiry": expiry,
                "root": root,
                "dte": (expiry - as_of).days,
                "rows": members,
            }
        )
    chains.sort(key=lambda item: (item["dte"], item["root"]))
    return chains


def select_tenor(chains: list[dict], target_dte: int, *, min_dte: int = 1) -> dict | None:
    """Pick the chain whose DTE is nearest the target.

    Same-day / expired chains are excluded (``min_dte``). Ties on distance are
    broken by the chain with more usable rows, then by root name, so selection
    is deterministic.
    """
    eligible = [chain for chain in chains if chain["dte"] >= min_dte]
    if not eligible:
        return None
    return min(
        eligible,
        key=lambda chain: (
            abs(chain["dte"] - target_dte),
            -len(chain["rows"]),
            chain["root"],
        ),
    )


# ---------------------------------------------------------------------------
# per-tenor metrics
# ---------------------------------------------------------------------------


def interpolate_iv_at(rows: list[dict], spot: float) -> tuple[float | None, dict]:
    """Linearly interpolate IV at ``spot`` from the two bracketing strikes.

    Returns (iv, detail). Detail records the bracketing strikes so the number is
    auditable. If spot sits outside the available strike range the nearest
    strike's IV is used and ``extrapolated`` is flagged.
    """
    points = sorted({(row["strike"], row["iv"]) for row in rows})
    detail = {"n_strikes": len(points), "extrapolated": False}
    if not points:
        return None, detail
    if len(points) == 1:
        detail["extrapolated"] = True
        detail["strikes"] = [points[0][0]]
        return points[0][1], detail

    below = [point for point in points if point[0] <= spot]
    above = [point for point in points if point[0] >= spot]
    if not below or not above:
        nearest = min(points, key=lambda point: abs(point[0] - spot))
        detail["extrapolated"] = True
        detail["strikes"] = [nearest[0]]
        return nearest[1], detail

    low = below[-1]
    high = above[0]
    detail["strikes"] = [low[0], high[0]]
    if high[0] == low[0]:
        return low[1], detail
    weight = (spot - low[0]) / (high[0] - low[0])
    return low[1] + weight * (high[1] - low[1]), detail


def atm_iv(rows: list[dict], spot: float) -> dict:
    """ATM IV: interpolate calls and puts separately at spot, then average.

    Averaging the two legs is the documented choice: put-call parity makes the
    two curves theoretically identical, so the average is a cheap consistency
    check -- a wide call/put gap means one leg's quotes are stale, and the gap
    is published (``call_put_gap``) rather than hidden by the average.
    """
    calls = [row for row in rows if row["right"] == "C"]
    puts = [row for row in rows if row["right"] == "P"]
    call_iv, call_detail = interpolate_iv_at(calls, spot)
    put_iv, put_detail = interpolate_iv_at(puts, spot)

    legs = [value for value in (call_iv, put_iv) if value is not None]
    value = sum(legs) / len(legs) if legs else None
    gap = None
    if call_iv is not None and put_iv is not None:
        gap = call_iv - put_iv
    return {
        "atm_iv": _round(value),
        "atm_iv_call": _round(call_iv),
        "atm_iv_put": _round(put_iv),
        "atm_call_put_gap": _round(gap),
        "atm_reference": "spot",
        "atm_method": "linear interpolation in strike between the two strikes "
        "bracketing spot, calls and puts computed separately then averaged",
        "atm_n_strikes_call": call_detail["n_strikes"],
        "atm_n_strikes_put": put_detail["n_strikes"],
        "atm_strikes_call": call_detail.get("strikes"),
        "atm_strikes_put": put_detail.get("strikes"),
        "atm_extrapolated": bool(
            call_detail["extrapolated"] or put_detail["extrapolated"]
        ),
    }


def select_by_delta(rows: list[dict], right: str, target: float) -> dict | None:
    """Nearest |delta| to the target among quality rows of the given right.

    Ties are broken by the higher strike so selection is deterministic.
    """
    candidates = [row for row in rows if row["right"] == right]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda row: (abs(abs(row["delta"]) - target), -row["strike"]),
    )


def fit_put_skew_slope(rows: list[dict], spot: float) -> dict:
    """Least-squares dIV / d(1% moneyness) over the 90%-100% moneyness puts.

    x is percent moneyness, ``100 * (K / S - 1)``, so the slope is in IV
    fraction per 1 percentage point of moneyness. A normal equity skew is
    negative: IV rises as strikes fall.
    """
    band_low, band_high = PUT_SKEW_BAND
    points = []
    for row in rows:
        if row["right"] != "P" or spot <= 0:
            continue
        moneyness = row["strike"] / spot
        if band_low <= moneyness <= band_high:
            points.append((100.0 * (moneyness - 1.0), row["iv"]))
    detail = {
        "put_skew_slope": None,
        "put_skew_slope_units": "IV fraction per 1% of moneyness (K/S - 1)",
        "put_skew_band_moneyness": [band_low, band_high],
        "put_skew_n_points": len(points),
        "put_skew_r_squared": None,
    }
    if len(points) < 3:
        detail["put_skew_status"] = "insufficient_points"
        return detail

    n = float(len(points))
    mean_x = sum(point[0] for point in points) / n
    mean_y = sum(point[1] for point in points) / n
    sxx = sum((point[0] - mean_x) ** 2 for point in points)
    sxy = sum((point[0] - mean_x) * (point[1] - mean_y) for point in points)
    if sxx <= 0:
        detail["put_skew_status"] = "degenerate_x"
        return detail
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x
    syy = sum((point[1] - mean_y) ** 2 for point in points)
    residual = sum(
        (point[1] - (intercept + slope * point[0])) ** 2 for point in points
    )
    detail["put_skew_slope"] = _round(slope)
    detail["put_skew_intercept"] = _round(intercept)
    detail["put_skew_r_squared"] = _round(1.0 - residual / syy) if syy > 0 else None
    detail["put_skew_status"] = "ok"
    return detail


def build_tenor(label: str, target_dte: int, chain: dict | None, spot: float) -> dict:
    if chain is None:
        return {
            "tenor": label,
            "target_dte": target_dte,
            "status": "no_chain_available",
        }
    rows = chain["rows"]
    payload = {
        "tenor": label,
        "target_dte": target_dte,
        "expiry": chain["expiry"].isoformat(),
        "root": chain["root"],
        "dte": chain["dte"],
        "dte_error_vs_target": chain["dte"] - target_dte,
        "n_rows_used": len(rows),
        "status": "ok",
    }
    payload.update(atm_iv(rows, spot))

    call_25 = select_by_delta(rows, "C", TARGET_DELTA)
    put_25 = select_by_delta(rows, "P", TARGET_DELTA)
    rr = bf = None
    if call_25 is not None and put_25 is not None:
        rr = call_25["iv"] - put_25["iv"]
        if payload.get("atm_iv") is not None:
            bf = (call_25["iv"] + put_25["iv"]) / 2.0 - payload["atm_iv"]
    payload.update(
        {
            "rr_25d": _round(rr),
            "bf_25d": _round(bf),
            "delta_target": TARGET_DELTA,
            "call_25d": _leg(call_25),
            "put_25d": _leg(put_25),
        }
    )
    payload.update(fit_put_skew_slope(rows, spot))
    return payload


def _leg(row: dict | None) -> dict | None:
    if row is None:
        return None
    return {
        "symbol": row["symbol"],
        "strike": row["strike"],
        "delta": _round(row["delta"], 4),
        "iv": _round(row["iv"]),
    }


# ---------------------------------------------------------------------------
# dealer gamma proxy
# ---------------------------------------------------------------------------


def dealer_gamma_proxy(rows: list[dict], spot: float) -> dict:
    """Naive dealer gamma exposure proxy.

    value = sum over quality rows of
        sign * gamma * open_interest * 100 * spot^2 * 0.01

    i.e. the dollar change in aggregate delta for a 1% move in spot, with
    sign +1 on calls and -1 on puts. BOTH inputs to that sign are assumptions,
    not observations, and both are carried in the returned payload:

    * ``sign_convention`` -- nobody publishes who is long what. "Dealers long
      calls, short puts" is a street convention; if it is wrong for the current
      regime, this number has the wrong sign.
    * ``oi_caveat`` -- open interest on a 15-minute-delayed feed is
      start-of-day and excludes everything traded today.

    ``gamma_flip_estimate`` is intentionally absent: see the module docstring.
    """
    total = 0.0
    contracts = 0
    call_gamma = 0.0
    put_gamma = 0.0
    for row in rows:
        sign = 1.0 if row["right"] == "C" else -1.0
        notional = (
            row["gamma"]
            * row["open_interest"]
            * CONTRACT_MULTIPLIER
            * spot
            * spot
            * 0.01
        )
        total += sign * notional
        if row["right"] == "C":
            call_gamma += notional
        else:
            put_gamma += notional
        contracts += 1
    return {
        "value": _round(total, 2),
        "units": "USD delta change per 1% move in spot",
        "method": "proxy",
        "formula": "sum(sign * gamma * open_interest * 100 * spot^2 * 0.01)",
        "sign_convention": "ASSUMPTION, not an observation: dealers assumed long "
        "calls (+1) and short puts (-1). Dealer positioning is not published; if "
        "this convention is wrong for the current regime the sign of this value "
        "is wrong.",
        "oi_caveat": "Open interest from the 15-minute-delayed CBOE feed is "
        "start-of-day and excludes today's trading, so intraday positioning "
        "changes are invisible here.",
        "contracts_used": contracts,
        "call_gamma_notional": _round(call_gamma, 2),
        "put_gamma_notional": _round(put_gamma, 2),
        "gamma_flip_estimate_status": "omitted",
        "gamma_flip_omitted_reason": "A defensible flip level needs gamma "
        "re-priced across hypothetical spot levels, which would stack a "
        "zero-rate/zero-dividend Black-Scholes assumption and a sticky-strike "
        "vol assumption on top of the sign and start-of-day-OI assumptions. "
        "Omitted rather than fabricated.",
        "research_only": True,
    }


# ---------------------------------------------------------------------------
# snapshot assembly
# ---------------------------------------------------------------------------


def _snapshot_date(raw: dict) -> tuple[str, str | None]:
    """(as_of ISO date, raw snapshot timestamp)."""
    stamp = raw.get("timestamp")
    if isinstance(stamp, str) and stamp.strip():
        text = stamp.strip()
        try:
            return date.fromisoformat(text[:10]).isoformat(), text
        except ValueError:
            pass
        return datetime.now(timezone.utc).date().isoformat(), text
    return datetime.now(timezone.utc).date().isoformat(), None


def build_snapshot(raw: dict) -> dict:
    """Turn one raw CBOE payload into a surface snapshot."""
    data = (raw or {}).get("data") or {}
    as_of, snapshot_timestamp = _snapshot_date(raw or {})

    spot = _finite(data.get("current_price"))
    spot_source = "data.current_price"
    if spot is None or spot <= 0:
        spot = _finite(data.get("close"))
        spot_source = "data.close"
    if spot is None or spot <= 0:
        raise ValueError("no usable spot in payload (current_price and close both bad)")

    rows, quality = filter_rows(data.get("options"))
    chains = group_chains(rows, date.fromisoformat(as_of))

    tenors = []
    for label, target in TENOR_TARGETS:
        tenors.append(build_tenor(label, target, select_tenor(chains, target), spot))

    ok_tenors = sum(1 for tenor in tenors if tenor.get("atm_iv") is not None)
    if quality["rows_used"] == 0:
        quality_state = "unavailable"
    elif ok_tenors == len(TENOR_TARGETS):
        quality_state = "ok"
    elif ok_tenors:
        quality_state = "partial"
    else:
        quality_state = "unavailable"

    quality["n_chains"] = len(chains)
    quality["tenors_resolved"] = ok_tenors

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_version": MODEL_VERSION,
        "research_only": True,
        "as_of": as_of,
        "source": {
            "url": SOURCE_URL,
            "delayed_minutes": DELAYED_MINUTES,
            "snapshot_timestamp": snapshot_timestamp,
            "provider": "cboe_delayed_quotes",
        },
        "spot": {
            "value": _round(spot, 4),
            "source_field": spot_source,
            "current_price": _round(data.get("current_price"), 4),
            "close": _round(data.get("close"), 4),
            "iv30_feed": _round(data.get("iv30"), 4),
        },
        "tenors": tenors,
        "dealer_gamma_proxy": dealer_gamma_proxy(rows, spot),
        "quality": quality,
        "quality_state": quality_state,
        "fetch_status": "ok",
    }


# ---------------------------------------------------------------------------
# history (append-only, idempotent per as_of date)
# ---------------------------------------------------------------------------


def read_history(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and parsed.get("as_of"):
            rows.append(parsed)
    return rows


def upsert_history(path: Path, snapshot: dict) -> list[dict]:
    """Replace the row for ``snapshot['as_of']`` (never duplicate it) and rewrite.

    Re-running on the same day is idempotent by construction: the date is the
    key, so the second run overwrites the first rather than appending.
    """
    rows = [row for row in read_history(path) if row.get("as_of") != snapshot["as_of"]]
    rows.append(snapshot)
    rows.sort(key=lambda row: str(row.get("as_of")))
    text = "".join(
        json.dumps(row, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
        for row in rows
    )
    _write_text_atomic(path, text)
    return rows


def stale_payload(latest_path: Path, error: str) -> dict:
    """Preserve the prior latest payload, stamped stale. Never fails the lane."""
    prior = None
    if latest_path.exists():
        try:
            prior = json.loads(latest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            prior = None
    if isinstance(prior, dict) and prior.get("as_of"):
        payload = dict(prior)
    else:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "model_version": MODEL_VERSION,
            "research_only": True,
            "as_of": None,
            "source": {
                "url": SOURCE_URL,
                "delayed_minutes": DELAYED_MINUTES,
                "snapshot_timestamp": None,
            },
            "spot": None,
            "tenors": [],
            "dealer_gamma_proxy": None,
            "quality": {
                "rows_total": 0,
                "rows_used": 0,
                "rows_rejected_by_reason": {reason: 0 for reason in REJECT_REASONS},
            },
        }
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    payload["quality_state"] = "stale"
    payload["fetch_status"] = "preserved_after_fetch_failure"
    payload["fetch_error"] = str(error)[:240]
    return payload


# ---------------------------------------------------------------------------
# build / CLI
# ---------------------------------------------------------------------------


def build(
    *,
    output_dir: Path,
    fixture: Path | None = None,
    dry_run: bool = False,
    url: str = SOURCE_URL,
) -> dict:
    output_dir = Path(output_dir)
    latest_path = output_dir / LATEST_NAME
    history_path = output_dir / HISTORY_NAME

    try:
        raw = load_fixture(fixture) if fixture else fetch_chain(url)
        snapshot = build_snapshot(raw)
    except Exception as exc:  # noqa: BLE001 - a source hiccup must not fail the lane
        payload = stale_payload(latest_path, str(exc))
        if not dry_run:
            _write_json_atomic(latest_path, payload)
        return payload

    if not dry_run:
        upsert_history(history_path, snapshot)
        _write_json_atomic(latest_path, snapshot)
    return snapshot


def summarize(payload: dict) -> dict:
    tenors = {}
    for tenor in payload.get("tenors") or []:
        tenors[tenor.get("tenor")] = {
            "expiry": tenor.get("expiry"),
            "dte": tenor.get("dte"),
            "atm_iv": tenor.get("atm_iv"),
            "rr_25d": tenor.get("rr_25d"),
            "bf_25d": tenor.get("bf_25d"),
            "put_skew_slope": tenor.get("put_skew_slope"),
        }
    quality = payload.get("quality") or {}
    gamma = payload.get("dealer_gamma_proxy") or {}
    spot = payload.get("spot") or {}
    return {
        "as_of": payload.get("as_of"),
        "quality_state": payload.get("quality_state"),
        "fetch_status": payload.get("fetch_status"),
        "spot": spot.get("value") if isinstance(spot, dict) else spot,
        "rows_total": quality.get("rows_total"),
        "rows_used": quality.get("rows_used"),
        "rows_rejected_by_reason": quality.get("rows_rejected_by_reason"),
        "dealer_gamma_proxy": gamma.get("value") if isinstance(gamma, dict) else None,
        "tenors": tenors,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build SPX vol-surface snapshots")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for spx_surface_history.jsonl and spx_surface_latest.json",
    )
    parser.add_argument(
        "--fixture",
        help="Load a saved CBOE JSON payload instead of hitting the network",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute and print the summary without writing any file",
    )
    parser.add_argument("--url", default=SOURCE_URL)
    args = parser.parse_args(argv)

    payload = build(
        output_dir=Path(args.output_dir),
        fixture=Path(args.fixture) if args.fixture else None,
        dry_run=args.dry_run,
        url=args.url,
    )
    print(json.dumps(summarize(payload), sort_keys=True, indent=2))
    return 0 if payload.get("quality_state") in {"ok", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
