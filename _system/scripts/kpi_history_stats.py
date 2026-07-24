#!/usr/bin/env python3
"""Magis KPI history series + z-scores (context only).

Sources:
  theme:{id}     → _system/reference/market-data/themes/{id}.csv
  ledger:T:kpi   → _system/reference/kpi/series/{TICKER}__{kpi_id}.csv

Used by build_world_model_snapshot.py to annotate strip rows and emit
strip.history_series for Magis UI sparklines / drilldown charts.
"""
from __future__ import annotations

import csv
import math
import re
import statistics
from pathlib import Path
from typing import Any

import world_model_common as wm

THEMES_CSV_DIR = wm.ROOT / "_system" / "reference" / "market-data" / "themes"
LEDGER_SERIES_DIR = wm.ROOT / "_system" / "reference" / "kpi" / "series"

THEME_MIN_N = 20
LEDGER_MIN_N = 5
TRAILING_N = 252
SPARK_N = 40
POINTS_EMIT_N = 252


def series_key_for(source: str | None, ticker: str, kpi_id: str) -> str:
    src = str(source or "").strip()
    if src.startswith("theme:"):
        return src
    safe_t = re.sub(r"[^\w.\-]+", "_", str(ticker or "").upper())
    safe_k = re.sub(r"[^\w.\-]+", "_", str(kpi_id or ""))
    return f"ledger:{safe_t}:{safe_k}"


def ledger_series_path(ticker: str, kpi_id: str) -> Path:
    safe_t = re.sub(r"[^\w.\-]+", "_", str(ticker or "").upper())
    safe_k = re.sub(r"[^\w.\-]+", "_", str(kpi_id or ""))
    return LEDGER_SERIES_DIR / f"{safe_t}__{safe_k}.csv"


def _read_csv_points(path: Path) -> list[tuple[str, float]]:
    if not path.exists():
        return []
    out: list[tuple[str, float]] = []
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            d = str(row.get("date") or row.get("as_of") or "")[:10]
            raw = row.get("value")
            if raw is None or raw == "" or not d:
                continue
            try:
                v = float(raw)
            except (TypeError, ValueError):
                continue
            if math.isnan(v) or math.isinf(v):
                continue
            out.append((d, v))
    out.sort(key=lambda x: x[0])
    # Dedupe by date keep last
    dedup: dict[str, float] = {}
    for d, v in out:
        dedup[d] = v
    return sorted(dedup.items(), key=lambda x: x[0])


def load_theme_points(series_id: str) -> list[tuple[str, float]]:
    return _read_csv_points(THEMES_CSV_DIR / f"{series_id}.csv")


def load_ledger_points(ticker: str, kpi_id: str) -> list[tuple[str, float]]:
    return _read_csv_points(ledger_series_path(ticker, kpi_id))


def append_ledger_point(ticker: str, kpi_id: str, as_of: str | None, value: Any) -> bool:
    """Append one observation; skip if same as_of already present. Returns True if wrote."""
    if value is None or not as_of:
        return False
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False
    if math.isnan(v) or math.isinf(v):
        return False
    d = str(as_of)[:10]
    path = ledger_series_path(ticker, kpi_id)
    existing = dict(_read_csv_points(path))
    if d in existing and abs(existing[d] - v) < 1e-12:
        return False
    existing[d] = v
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "value"])
        for dd in sorted(existing):
            w.writerow([dd, existing[dd]])
    return True


def compute_stats(
    points: list[tuple[str, float]],
    *,
    trailing: int = TRAILING_N,
    min_n: int = THEME_MIN_N,
) -> dict[str, Any]:
    if not points:
        return {
            "status": "no_series",
            "z_score": None,
            "mean": None,
            "stdev": None,
            "n": 0,
            "percentile": None,
            "window": f"trailing_{trailing}",
            "as_of": None,
            "latest": None,
        }
    window = points[-trailing:] if trailing and len(points) > trailing else list(points)
    values = [v for _, v in window]
    n = len(values)
    latest = values[-1]
    as_of = window[-1][0]
    if n < min_n:
        return {
            "status": "insufficient_history",
            "z_score": None,
            "mean": round(statistics.fmean(values), 6) if n else None,
            "stdev": None,
            "n": n,
            "percentile": None,
            "window": f"trailing_{trailing}",
            "as_of": as_of,
            "latest": latest,
        }
    mean = statistics.fmean(values)
    stdev = statistics.pstdev(values) if n > 1 else 0.0
    z = None
    if stdev > 1e-12:
        z = round((latest - mean) / stdev, 3)
    # Empirical percentile of latest (midrank)
    below = sum(1 for v in values if v < latest)
    equal = sum(1 for v in values if v == latest)
    pct = round(100.0 * (below + 0.5 * equal) / n, 1)
    return {
        "status": "ok" if z is not None else "insufficient_history",
        "z_score": z,
        "mean": round(mean, 6),
        "stdev": round(stdev, 6),
        "n": n,
        "percentile": pct,
        "window": f"trailing_{trailing}",
        "as_of": as_of,
        "latest": latest,
    }


def load_points_for_key(series_key: str) -> list[tuple[str, float]]:
    if series_key.startswith("theme:"):
        return load_theme_points(series_key.split(":", 1)[1])
    if series_key.startswith("ledger:"):
        parts = series_key.split(":", 2)
        if len(parts) == 3:
            return load_ledger_points(parts[1], parts[2])
    return []


def annotate_rows(rows: list[dict]) -> dict[str, dict]:
    """Annotate KPI strip rows in-place; return history_series map for UI."""
    series_cache: dict[str, list[tuple[str, float]]] = {}
    history_series: dict[str, dict] = {}

    for row in rows:
        ticker = str(row.get("ticker") or "")
        kpi_id = str(row.get("kpi_id") or "")
        source = row.get("source")
        key = series_key_for(source, ticker, kpi_id)
        kind = "theme" if key.startswith("theme:") else "ledger"

        # Sparse archive for non-theme actuals
        if kind == "ledger" and row.get("actual") is not None:
            as_of = row.get("last_checked") or row.get("as_of")
            append_ledger_point(ticker, kpi_id, as_of, row.get("actual"))

        if key not in series_cache:
            series_cache[key] = load_points_for_key(key)
        points = series_cache[key]
        min_n = THEME_MIN_N if kind == "theme" else LEDGER_MIN_N
        stats = compute_stats(points, trailing=TRAILING_N, min_n=min_n)

        # If theme CSV empty but row has actual, synthesize one-point (insufficient)
        if stats["status"] == "no_series" and row.get("actual") is not None:
            d = str(row.get("last_checked") or "")[:10] or "unknown"
            try:
                points = [(d, float(row["actual"]))]
                series_cache[key] = points
                stats = compute_stats(points, trailing=TRAILING_N, min_n=min_n)
            except (TypeError, ValueError):
                pass

        hist = {
            "series_key": key,
            "source_kind": kind,
            "z_score": stats.get("z_score"),
            "mean": stats.get("mean"),
            "stdev": stats.get("stdev"),
            "n": stats.get("n") or 0,
            "percentile": stats.get("percentile"),
            "window": stats.get("window"),
            "as_of": stats.get("as_of"),
            "status": stats.get("status"),
            "sparkline": [round(v, 6) for _, v in points[-SPARK_N:]],
        }
        row["history"] = hist
        row["series_key"] = key
        row["z_score"] = hist["z_score"]

        if key not in history_series and points:
            emit = points[-POINTS_EMIT_N:]
            history_series[key] = {
                "series_key": key,
                "source_kind": kind,
                "label": row.get("label") or kpi_id,
                "ticker_example": ticker,
                "kpi_id_example": kpi_id,
                "points": [{"d": d, "v": round(v, 6)} for d, v in emit],
                "stats": {
                    "z_score": stats.get("z_score"),
                    "mean": stats.get("mean"),
                    "stdev": stats.get("stdev"),
                    "n": stats.get("n"),
                    "percentile": stats.get("percentile"),
                    "window": stats.get("window"),
                    "as_of": stats.get("as_of"),
                    "status": stats.get("status"),
                    "latest": stats.get("latest"),
                },
            }

    return history_series


def bootstrap_ledger_from_monthly_history() -> int:
    """Seed ledger series from cold monthly Magis snapshots (one point per month)."""
    written = 0
    if not wm.KPI_HISTORY_DIR.exists():
        return 0
    for path in sorted(wm.KPI_HISTORY_DIR.glob("*.json")):
        cold = wm.load_json(path)
        for bucket in ("passes", "broken", "stale", "unchecked"):
            for row in cold.get(bucket) or []:
                src = str(row.get("source") or "")
                if src.startswith("theme:"):
                    continue
                if row.get("actual") is None:
                    continue
                as_of = row.get("last_checked") or cold.get("month")
                if append_ledger_point(
                    str(row.get("ticker") or ""),
                    str(row.get("kpi_id") or ""),
                    as_of,
                    row.get("actual"),
                ):
                    written += 1
    return written


if __name__ == "__main__":
    n = bootstrap_ledger_from_monthly_history()
    print(f"bootstrap ledger points written/updated: {n}")
