#!/usr/bin/env python3
"""Fetch thematic macro / industry indicator panels (context layer).

Broadly ingested context (FRED, Yahoo, etf-dashboard, EIA, repo filings) consumed
narrowly by tagged holdings via apply_context_overlay.py. Tailwinds inform stance
and overlay sizing only; they never auto-inflate Lawrence base IRR.

  python3 _system/scripts/fetch_theme_panel.py            # fetch all themes
  python3 _system/scripts/fetch_theme_panel.py --theme ai_power_land
  python3 _system/scripts/fetch_theme_panel.py --offline   # recompute manifest from cached CSVs only

Network failures degrade gracefully: cached CSV history is kept and the last
known value is reused, with an error note in the manifest.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
CONFIG = SCRIPTS / "theme_panel_config.json"
THEMES_DIR = ROOT / "_system" / "reference" / "market-data" / "themes"
FILING_PANELS_DIR = THEMES_DIR / "filing_panels"
RETURNS_DIR = ROOT / "_system" / "reference" / "market-data" / "returns"
EXTERNAL_ROOT = ROOT / "_system" / "reference" / "market-data" / "external"
UA = "MarvinResearch/1.0 (theme-panel)"
TODAY = date.today().isoformat()

FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={id}"
STOOQ_DAILY_URL = "https://stooq.com/q/d/l/?s={symbol}&i=d"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart"

HYPERSCALERS = ("GOOGL", "AMZN", "META", "MSFT")
EXPERT_HORIZONS_DIR = ROOT / "_system" / "reference" / "world_model" / "expert_horizons"


def _load_dotenv() -> None:
    """Best-effort load of EIA/FRED keys from local .env files (no dependency)."""
    for path in (ROOT / ".env", ROOT / "_system" / ".env", ROOT.parent / ".env"):
        if not path.exists():
            continue
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ and val:
                    os.environ[key] = val
        except OSError:
            continue


def load_config() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def _http_get(url: str, timeout: int = 30, retries: int = 3) -> str | None:
    import time

    req = urllib.request.Request(url, headers={"User-Agent": UA})
    delay = 1.0
    for attempt in range(retries):
        try:
            return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", errors="ignore")
        except Exception:
            if attempt + 1 >= retries:
                return None
            time.sleep(delay)
            delay = min(delay * 2, 8.0)
    return None


def _sync_external() -> None:
    """Best-effort etf-dashboard sync before reading local paths."""
    try:
        sys.path.insert(0, str(SCRIPTS))
        from darwin.import_external_data import sync_external_market_data  # noqa: WPS433

        sync_external_market_data()
    except Exception:
        pass


def _etf_metrics_path() -> Path | None:
    try:
        sys.path.insert(0, str(SCRIPTS))
        from darwin.external_sources import etf_data_path  # noqa: WPS433

        p = etf_data_path("etf_metrics_daily.csv")
        if p:
            return p
    except Exception:
        pass
    for candidate in (
        EXTERNAL_ROOT / "etf_metrics_daily.csv",
        ROOT / "_external" / "etf-dashboard" / "data" / "etf_metrics_daily.csv",
    ):
        if candidate.exists():
            return candidate
    return None


def _external_json(name: str) -> Path | None:
    try:
        sys.path.insert(0, str(SCRIPTS))
        from darwin.external_sources import etf_data_path  # noqa: WPS433

        p = etf_data_path(name)
        if p:
            return p
    except Exception:
        pass
    for candidate in (
        EXTERNAL_ROOT / name,
        ROOT / "_external" / "etf-dashboard" / "data" / name,
    ):
        if candidate.exists():
            return candidate
    return None


def fetch_fred(fred_id: str, timeout: int = 12) -> tuple[list[tuple[str, float]], str | None]:
    raw = _http_get(FRED_URL.format(id=fred_id), timeout=timeout, retries=2)
    if raw is None:
        return [], "network"
    rows: list[tuple[str, float]] = []
    for line in raw.splitlines()[1:]:
        parts = line.split(",")
        if len(parts) < 2:
            continue
        d, v = parts[0].strip(), parts[1].strip()
        if not d or v in ("", "."):
            continue
        try:
            rows.append((d, float(v)))
        except ValueError:
            continue
    return rows, (None if rows else "empty")


def fetch_stooq_daily(symbol: str) -> tuple[list[tuple[str, float]], str | None]:
    raw = _http_get(STOOQ_DAILY_URL.format(symbol=symbol.lower()))
    if raw is None:
        return [], "network"
    rows: list[tuple[str, float]] = []
    for line in raw.splitlines()[1:]:
        parts = line.split(",")
        if len(parts) < 5:
            continue
        d = parts[0].strip()
        try:
            close = float(parts[4].strip())
        except ValueError:
            continue
        if d:
            rows.append((d, close))
    return rows, (None if rows else "empty")


def fetch_yahoo_daily(symbol: str, days: int = 400) -> tuple[list[tuple[str, float]], str | None]:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    url = (
        f"{YAHOO_CHART_URL}/{symbol}?period1={int(start.timestamp())}"
        f"&period2={int(end.timestamp())}&interval=1d"
    )
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        payload = json.loads(urllib.request.urlopen(req, timeout=25).read())
        result = payload["chart"]["result"][0]
        timestamps = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
    except Exception:
        return [], "network"
    rows: list[tuple[str, float]] = []
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        d = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        rows.append((d, float(close)))
    rows.sort()
    return rows, (None if rows else "empty")


def fetch_eia(route: str, facets: dict | None) -> tuple[list[tuple[str, float]], str | None]:
    key = os.environ.get("EIA_API_KEY")
    if not key:
        return [], "no_eia_key"
    params = [
        f"api_key={key}",
        "frequency=monthly",
        "data[0]=value",
        "sort[0][column]=period",
        "sort[0][direction]=desc",
        "length=60",
    ]
    for k, v in (facets or {}).items():
        params.append(f"facets[{k}][]={v}")
    url = f"https://api.eia.gov/v2/{route}/data/?" + "&".join(params)
    raw = _http_get(url)
    if raw is None:
        return [], "network"
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return [], "bad_json"
    rows: list[tuple[str, float]] = []
    for rec in (payload.get("response") or {}).get("data") or []:
        d = str(rec.get("period") or "")
        val = rec.get("value")
        if d and val is not None:
            try:
                rows.append((d, float(val)))
            except (ValueError, TypeError):
                continue
    rows.sort()
    return rows, (None if rows else "empty")


def fetch_etf_dashboard_daily(ticker: str, column: str = "underlying_adj_close") -> tuple[list[tuple[str, float]], str | None]:
    path = _etf_metrics_path()
    if not path:
        return [], "no_etf_metrics"
    rows: list[tuple[str, float]] = []
    with path.open(encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (row.get("ticker") or "").upper() != ticker.upper():
                continue
            d = (row.get("date") or "")[:10]
            try:
                val = float(row.get(column) or row.get("close_price") or row.get("etf_adj_close") or "")
            except ValueError:
                continue
            if d and val > 0:
                rows.append((d, val))
    rows.sort()
    return rows, (None if rows else "empty")


def read_filing_panel(panel: str, metric: str) -> tuple[list[tuple[str, float]], str | None]:
    path = FILING_PANELS_DIR / panel
    if not path.exists():
        return [], "no_panel"
    rows: list[tuple[str, float]] = []
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            d = (row.get("as_of") or row.get("date") or "")[:10]
            try:
                val = float(row.get(metric) or "")
            except ValueError:
                continue
            if d:
                rows.append((d, val))
    rows.sort()
    return rows, (None if rows else "empty")


def _daily_from_returns_monthly(ticker: str) -> list[tuple[str, float]]:
    """Approximate daily index from monthly returns vault (month-end levels)."""
    key = ticker.replace(".", "_")
    path = RETURNS_DIR / f"{key}.csv"
    if not path.exists():
        return []
    levels: list[tuple[str, float]] = []
    level = 100.0
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            d = (row.get("date") or "")[:10]
            try:
                r = float(row.get("monthly_return") or "")
            except ValueError:
                continue
            if d:
                level *= 1.0 + r
                levels.append((d, level))
    return levels


def computed_spread(leg_a: str, leg_b: str, window_days: int) -> tuple[list[tuple[str, float]], str | None, str]:
    rows_a, err_a = fetch_yahoo_daily(leg_a)
    rows_b, err_b = fetch_yahoo_daily(leg_b)
    if not rows_a:
        rows_a = _daily_from_returns_monthly(leg_a)
    if not rows_b:
        rows_b = _daily_from_returns_monthly(leg_b)
    if not rows_a or not rows_b:
        return [], err_a or err_b or "insufficient_data", ""
    map_b = {d: v for d, v in rows_b}
    out: list[tuple[str, float]] = []
    for i, (d, va) in enumerate(rows_a):
        if i < window_days:
            continue
        d0, v0 = rows_a[i - window_days]
        vb = map_b.get(d)
        vb0 = map_b.get(d0)
        if vb and vb0 and v0 > 0 and vb0 > 0:
            ret_a = (va / v0 - 1.0) * 100.0
            ret_b = (vb / vb0 - 1.0) * 100.0
            out.append((d, round(ret_a - ret_b, 2)))
    label = f"spread:{leg_a}-{leg_b}:{window_days}d"
    return out, (None if out else "empty"), label


def computed_ratio(numerator: str, denominator: str) -> tuple[list[tuple[str, float]], str | None, str]:
    rows_n, _ = fetch_yahoo_daily(numerator)
    rows_d, _ = fetch_yahoo_daily(denominator)
    if not rows_n or not rows_d:
        return [], "insufficient_data", ""
    map_d = {d: v for d, v in rows_d}
    out: list[tuple[str, float]] = []
    for d, vn in rows_n:
        vd = map_d.get(d)
        if vd and vd > 0:
            out.append((d, round(vn / vd, 4)))
    label = f"ratio:{numerator}/{denominator}"
    return out, (None if out else "empty"), label


def computed_realized_vol(ticker: str, window_days: int) -> tuple[list[tuple[str, float]], str | None, str]:
    rows, err = fetch_yahoo_daily(ticker)
    if not rows:
        rows = _daily_from_returns_monthly(ticker)
    if len(rows) < window_days + 2:
        return [], err or "insufficient_data", ""
    out: list[tuple[str, float]] = []
    for i in range(window_days, len(rows)):
        window = rows[i - window_days : i + 1]
        rets = []
        for j in range(1, len(window)):
            p0, p1 = window[j - 1][1], window[j][1]
            if p0 > 0:
                rets.append(math.log(p1 / p0))
        if len(rets) >= window_days - 1:
            var = sum(r * r for r in rets) / len(rets)
            ann = math.sqrt(var * 252) * 100.0
            out.append((window[-1][0], round(ann, 2)))
    label = f"realized_vol:{ticker}:{window_days}d"
    return out, (None if out else "empty"), label


def _resolve_json_path(data: dict, json_path: str):
    cur = data
    for part in str(json_path or "").split("."):
        if not part:
            continue
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def _derive_vrp_health_score(data: dict) -> float | None:
    """Compose 0-100 health from current etf-dashboard vrp_health schema."""
    cov = data.get("iv_coverage_front_pct")
    if cov is None:
        cov = ((data.get("front_leg_quote_coverage") or {}).get("leg_iv_pct"))
    try:
        cov_f = float(cov)
    except (TypeError, ValueError):
        return None
    if cov_f <= 1.0:
        cov_f *= 100.0
    stale_n = len(data.get("stale_sleeves") or [])
    missing_n = len(data.get("missing_chain_ybs") or [])
    err_n = len(data.get("errors") or [])
    penalty = min(40.0, 5.0 * stale_n + 4.0 * missing_n + 8.0 * err_n)
    return round(max(0.0, min(100.0, cov_f - penalty)), 2)


def etf_dashboard_snapshot(
    snapshot_file: str,
    json_path: str,
    *,
    derive: str | None = None,
) -> tuple[list[tuple[str, float]], str | None, str]:
    path = _external_json(snapshot_file)
    if not path:
        return [], "no_snapshot", ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return [], "bad_json", ""
    cur = _resolve_json_path(data, json_path) if json_path else None
    label = f"etf_dashboard:{snapshot_file}:{json_path or derive or 'derived'}"
    if cur is None and derive == "vrp_health_score":
        cur = _derive_vrp_health_score(data)
        label = f"etf_dashboard:{snapshot_file}:derived_health_score"
    if cur is None:
        return [], "path_missing", ""
    as_of = str(
        data.get("holdings_as_of")
        or data.get("as_of")
        or data.get("build_time")
        or data.get("generated_at")
        or TODAY
    )[:10]
    try:
        val = float(cur)
    except (TypeError, ValueError):
        return [], "not_numeric", ""
    return [(as_of, val)], None, label


def computed_vix_term_slope() -> tuple[list[tuple[str, float]], str | None, str]:
    """VIX3M - VIX: positive = contango (typical), negative = inversion stress."""
    near, err_n = fetch_yahoo_daily("^VIX")
    far, err_f = fetch_yahoo_daily("^VIX3M")
    if not near or not far:
        return [], err_n or err_f or "insufficient_data", ""
    map_f = {d: v for d, v in far}
    out: list[tuple[str, float]] = []
    for d, vn in near:
        vf = map_f.get(d)
        if vf is None:
            continue
        out.append((d, round(vf - vn, 3)))
    return out, (None if out else "empty"), "vix_term:VIX3M-VIX"


def expert_horizon_years(domain: str) -> tuple[list[tuple[str, float]], str | None, str]:
    """Append-only public arrival-date quotes → years_ahead time series."""
    path = EXPERT_HORIZONS_DIR / f"{domain}.csv"
    if not path.exists():
        return [], "no_horizon_csv", ""
    rows: list[tuple[str, float]] = []
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            d = (row.get("date") or "")[:10]
            try:
                years = float(row.get("years_ahead") or "")
            except ValueError:
                continue
            if d:
                rows.append((d, years))
    rows.sort()
    return rows, (None if rows else "empty"), f"expert_horizon:{domain}"


def hyperscaler_capex_guide() -> tuple[list[tuple[str, float]], str | None, list[str]]:
    """Sum latest disclosed annual capex guide across hyperscalers from ai_overlay."""
    import re

    total = 0.0
    contributors: list[str] = []
    for tk in HYPERSCALERS:
        vp = ROOT / tk / "research" / "valuation.json"
        if not vp.exists():
            continue
        try:
            val = json.loads(vp.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        ov = val.get("ai_overlay") or {}
        capex_bn = None
        stress = ov.get("capex_stress_2026") or {}
        if isinstance(stress.get("capex_bn"), (int, float)):
            capex_bn = float(stress["capex_bn"])
        if capex_bn is None:
            guide = ((ov.get("in_model") or {}).get("capex_2026_guide")) or ""
            nums = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", str(guide))]
            if nums:
                capex_bn = max(nums)
        if capex_bn is not None:
            total += capex_bn
            contributors.append(f"{tk}:{capex_bn:.0f}")
    if not contributors:
        return [], "no_overlay_data", []
    return [(TODAY, round(total, 1))], None, contributors


def read_cached_csv(path: Path) -> list[tuple[str, float]]:
    if not path.exists():
        return []
    rows: list[tuple[str, float]] = []
    with path.open(encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)
        for r in reader:
            if len(r) < 2:
                continue
            try:
                rows.append((r[0], float(r[1])))
            except ValueError:
                continue
    return rows


def write_csv(path: Path, rows: list[tuple[str, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "value"])
        for d, v in rows:
            w.writerow([d, v])


def yoy(rows: list[tuple[str, float]]) -> tuple[float | None, float | None, float | None]:
    """Return (latest, prior_year_value, yoy_pct)."""
    if not rows:
        return None, None, None
    rows = sorted(rows)
    latest_date, latest_val = rows[-1]
    try:
        ld = datetime.strptime(latest_date[:10], "%Y-%m-%d").date()
    except ValueError:
        ld = None
    prior = None
    if ld is not None:
        best_gap = None
        for d, v in rows[:-1]:
            try:
                dd = datetime.strptime(d[:10], "%Y-%m-%d").date()
            except ValueError:
                continue
            gap = abs((ld - dd).days - 365)
            if (ld - dd).days >= 250 and (best_gap is None or gap < best_gap):
                best_gap, prior = gap, v
    pct = None
    if prior not in (None, 0):
        pct = round(100.0 * (latest_val - prior) / abs(prior), 1)
    return latest_val, prior, pct


def direction(pct: float | None) -> str:
    if pct is None:
        return "flat"
    if pct > 1.0:
        return "up"
    if pct < -1.0:
        return "down"
    return "flat"


def _apply_fallback(spec: dict, rows: list[tuple[str, float]], err: str | None) -> tuple[list[tuple[str, float]], str | None, str]:
    if rows or not spec.get("fallback"):
        return rows, err, ""
    fb = spec["fallback"]
    fb_src = fb.get("source")
    extra_label = ""
    if fb_src == "yahoo_daily":
        sym = fb.get("yahoo_symbol", "")
        rows, err = fetch_yahoo_daily(sym)
        extra_label = f"yahoo:{sym}"
        if fb.get("scale_note"):
            extra_label += f" ({fb['scale_note']})"
    elif fb_src == "etf_dashboard":
        rows, err = fetch_etf_dashboard_daily(
            fb.get("ticker", ""),
            fb.get("column", "underlying_adj_close"),
        )
        extra_label = f"etf_dashboard:{fb.get('ticker')}"
    elif fb_src == "computed_spread":
        rows, err, extra_label = computed_spread(
            fb.get("leg_a", ""),
            fb.get("leg_b", ""),
            int(fb.get("window_days", 21)),
        )
        if fb.get("note"):
            extra_label = f"{extra_label} ({fb['note']})"
    elif fb_src == "fred":
        rows, err = fetch_fred(fb.get("fred_id", ""))
        extra_label = f"fred:{fb.get('fred_id')}"
        if fb.get("note"):
            extra_label = f"{extra_label} ({fb['note']})"
    return rows, err, extra_label


def process_series(spec: dict, offline: bool) -> dict:
    sid = spec["id"]
    src = spec.get("source")
    csv_path = THEMES_DIR / f"{sid}.csv"
    cached = read_cached_csv(csv_path)
    rows: list[tuple[str, float]] = []
    err: str | None = None
    extra: dict = {}
    source_label = str(src)

    if offline:
        rows, err = cached, (None if cached else "offline_no_cache")
    elif src == "fred":
        # Prefer configured fallback (Yahoo/ETF) when present — FRED often blocked in CI/cloud.
        if spec.get("fallback"):
            rows, err, fb_label = _apply_fallback(spec, [], "fred_deferred")
            if rows:
                source_label = fb_label
            else:
                rows, err = fetch_fred(spec["fred_id"])
                rows, err, fb_label = _apply_fallback(spec, rows, err)
                if fb_label:
                    source_label = fb_label
        else:
            rows, err = fetch_fred(spec["fred_id"])
            rows, err, fb_label = _apply_fallback(spec, rows, err)
            if fb_label:
                source_label = fb_label
    elif src == "stooq_daily":
        rows, err = fetch_stooq_daily(spec["stooq"])
    elif src == "yahoo_daily":
        rows, err = fetch_yahoo_daily(spec.get("yahoo_symbol", ""))
        source_label = f"yahoo:{spec.get('yahoo_symbol')}"
    elif src == "eia":
        rows, err = fetch_eia(spec.get("eia_route", ""), spec.get("eia_facets"))
        rows, err, fb_label = _apply_fallback(spec, rows, err)
        if fb_label:
            source_label = fb_label
        else:
            source_label = f"eia:{spec.get('eia_route')}"
    elif src == "repo_valuation":
        rows, err, contributors = hyperscaler_capex_guide()
        if contributors:
            extra["contributors"] = contributors
    elif src == "etf_dashboard":
        rows, err = fetch_etf_dashboard_daily(
            spec.get("ticker", ""),
            spec.get("column", "underlying_adj_close"),
        )
        source_label = f"etf_dashboard:{spec.get('ticker')}"
    elif src == "filing_panel":
        rows, err = read_filing_panel(spec.get("panel", ""), spec.get("metric", ""))
        source_label = f"filing_panel:{spec.get('panel')}:{spec.get('metric')}"
    elif src == "computed_spread":
        rows, err, source_label = computed_spread(
            spec.get("leg_a", ""),
            spec.get("leg_b", ""),
            int(spec.get("window_days", 21)),
        )
    elif src == "computed_ratio":
        rows, err, source_label = computed_ratio(
            spec.get("numerator", ""),
            spec.get("denominator", ""),
        )
    elif src == "computed_realized_vol":
        rows, err, source_label = computed_realized_vol(
            spec.get("ticker", "SPY"),
            int(spec.get("window_days", 20)),
        )
    elif src == "etf_dashboard_snapshot":
        rows, err, source_label = etf_dashboard_snapshot(
            spec.get("snapshot_file", ""),
            spec.get("json_path", ""),
            derive=spec.get("derive"),
        )
    elif src == "computed_vix_term_slope":
        rows, err, source_label = computed_vix_term_slope()
    elif src == "expert_horizon":
        rows, err, source_label = expert_horizon_years(spec.get("domain", ""))
        # Expert quotes are sparse; use a wide monthly-style gate by default.
        if "staleness_max_days" not in spec:
            spec = {**spec, "staleness_max_days": 120}
    else:
        err = f"unknown_source:{src}"

    if not rows and cached:
        rows = cached
        err = err or "reused_cache"
    if rows:
        merged = {d: v for d, v in cached}
        merged.update({d: v for d, v in rows})
        rows = sorted(merged.items())
        write_csv(csv_path, rows)

    latest_val, prior_val, pct = yoy(rows)
    latest_date = rows[-1][0] if rows else None
    # Monthly / sparse series need wider staleness than daily macro.
    default_stale_days = 45 if src in ("fred", "eia", "filing_panel", "expert_horizon") else 10
    stale_days = int(spec.get("staleness_max_days") or default_stale_days)
    stale = True
    if latest_date:
        try:
            ld = datetime.strptime(latest_date[:10], "%Y-%m-%d").date()
            stale = (date.today() - ld).days > stale_days
        except ValueError:
            stale = True

    if src == "fred" and not spec.get("fallback"):
        source_label = f"fred:{spec.get('fred_id')}"
    elif src == "stooq_daily":
        source_label = f"stooq:{spec.get('stooq')}"
    elif src == "eia" and not str(source_label).startswith("fred:"):
        source_label = f"eia:{spec.get('eia_route')}"
    elif src == "repo_valuation":
        source_label = "repo:valuation.json/ai_overlay"

    out = {
        "label": spec.get("label", sid),
        "latest": latest_val,
        "as_of": latest_date,
        "prior_year": prior_val,
        "yoy_pct": pct,
        "direction": direction(pct),
        "good_for": spec.get("good_for"),
        "source": source_label,
        "optional": bool(spec.get("optional")),
        "stale": stale,
        "error": err,
        "note": spec.get("note"),
    }
    out.update(extra)
    return out


def build(theme_filter: str | None, offline: bool) -> dict:
    _load_dotenv()
    if not offline:
        _sync_external()
    cfg = load_config()
    THEMES_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = THEMES_DIR / "manifest.json"
    prior: dict = {}
    if manifest_path.exists():
        try:
            prior = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            prior = {}
    manifest: dict = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of": TODAY,
        "staleness_max_days": cfg.get("staleness_max_days", 10),
        "disclaimer": "Context only. Tailwinds inform stance and overlay sizing; never auto-inflate Lawrence base IRR (human review promotes to base).",
        "themes": dict(prior.get("themes") or {}),
    }
    for theme_id, theme in (cfg.get("themes") or {}).items():
        if theme_filter and theme_id != theme_filter:
            continue
        series_out: dict = {}
        for spec in theme.get("series") or []:
            # Keep explicit per-series gates; do not force daily gate onto monthly FRED.
            if "staleness_max_days" not in spec and spec.get("source") in (
                "fred",
                "eia",
                "filing_panel",
                "expert_horizon",
            ):
                spec = {**spec, "staleness_max_days": 45}
            res = process_series(spec, offline)
            series_out[spec["id"]] = res
            flag = "STALE" if res["stale"] else "ok"
            print(f"  [{theme_id}] {spec['id']}: latest={res['latest']} yoy={res['yoy_pct']}% {flag} err={res['error']}")
        manifest["themes"][theme_id] = {
            "label": theme.get("label"),
            "description": theme.get("description"),
            "series": series_out,
        }
    (THEMES_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--theme", help="Only refresh one theme id")
    ap.add_argument("--offline", action="store_true", help="Recompute manifest from cached CSVs only")
    args = ap.parse_args()
    build(args.theme, args.offline)
    print(f"Theme panel manifest written to {THEMES_DIR / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
