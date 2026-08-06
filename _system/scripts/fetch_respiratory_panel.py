#!/usr/bin/env python3
"""Fetch US respiratory-virus testing volumes (context layer for diagnostics holdings).

Weekly national test volumes for influenza, RSV and SARS-CoV-2, plus outpatient
ILI visits. Consumed by build_qdel_respiratory_model.py and surfaced on the
dashboard KPI (Inflections) tab as labelled demand context.

  python3 _system/scripts/fetch_respiratory_panel.py            # fetch all series
  python3 _system/scripts/fetch_respiratory_panel.py --offline  # rebuild manifest from cached CSVs

Sources:
  - Delphi Epidata (CMU) mirror of CDC FluView: influenza clinical-lab specimens
    and ILINet outpatient visits. No API key required.
  - CDC Socrata dataset rgnm-fkqb: NAAT test volumes by pathogen (RSV, SARS-CoV-2).

Both sources revise. Delphi exposes issue/vintage history, so a point-in-time
backtest must pin `issues=` rather than reading the settled series; see
docs/respiratory-kpi.md. This fetcher stores the *settled* (latest-issue) series
for dashboard context only.

Network failures degrade gracefully: cached CSV history is kept and the manifest
records an error note rather than dropping the series.
"""
from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "_system" / "reference" / "market-data" / "respiratory"
MANIFEST = OUT_DIR / "manifest.json"
UA = "MarvinResearch/1.0 (respiratory-panel)"

DELPHI = "https://api.delphi.cmu.edu/epidata/{endpoint}/?{query}"
SOCRATA = "https://data.cdc.gov/resource/rgnm-fkqb.json?{query}"

# Series are stale if the newest week-end is older than this. CDC publishes
# weekly with ~5 day lag; 21 days absorbs a holiday slip without false alarms.
STALENESS_MAX_DAYS = 21

SERIES_META = {
    "flu_clinical_specimens": {
        "label": "Influenza clinical-lab specimens tested (weekly, US)",
        "good_for": "respiratory_test_volume",
        "source": "delphi:fluview_clinical:total_specimens",
    },
    "flu_positives": {
        "label": "Influenza A+B positive tests (weekly, US)",
        "good_for": "respiratory_positivity",
        "source": "delphi:fluview_clinical:total_a+total_b",
    },
    "ili_visits": {
        "label": "ILINet outpatient influenza-like-illness visits (weekly, US)",
        "good_for": "respiratory_patient_volume",
        "source": "delphi:fluview:num_ili",
    },
    "rsv_naat_tests": {
        "label": "RSV NAAT tests performed (weekly, US)",
        "good_for": "respiratory_test_volume",
        "source": "cdc:rgnm-fkqb:RSV",
    },
    "sars_cov2_naat_tests": {
        "label": "SARS-CoV-2 NAAT tests performed (weekly, US)",
        "good_for": "respiratory_test_volume",
        "source": "cdc:rgnm-fkqb:SARS-COV-2",
    },
}


def _http_get(url: str, timeout: int = 60, retries: int = 3) -> str | None:
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


def epiweek_end(epiweek: int | str) -> str:
    """MMWR epiweek -> ISO date of the week-ending Saturday."""
    text = str(epiweek)
    year, week = int(text[:4]), int(text[4:])
    anchor = date(year, 1, 4)
    anchor -= timedelta(days=anchor.weekday())
    return (anchor + timedelta(weeks=week - 1, days=5)).isoformat()


def current_epiweek_range() -> str:
    today = date.today()
    return f"201901-{today.year + 1}01"


def to_float(raw) -> float | None:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value


def fetch_delphi() -> dict[str, dict[str, float]]:
    """Return {series_id: {iso_date: value}} for the FluView-derived series."""
    out: dict[str, dict[str, float]] = {}
    span = current_epiweek_range()

    body = _http_get(DELPHI.format(endpoint="fluview_clinical", query=urllib.parse.urlencode(
        {"regions": "nat", "epiweeks": span})))
    if body:
        try:
            rows = json.loads(body).get("epidata") or []
        except json.JSONDecodeError:
            rows = []
        specimens: dict[str, float] = {}
        positives: dict[str, float] = {}
        for row in rows:
            iso = epiweek_end(row.get("epiweek"))
            total = to_float(row.get("total_specimens"))
            if total is not None:
                specimens[iso] = total
            pos = (to_float(row.get("total_a")) or 0.0) + (to_float(row.get("total_b")) or 0.0)
            if row.get("total_a") is not None or row.get("total_b") is not None:
                positives[iso] = pos
        if specimens:
            out["flu_clinical_specimens"] = specimens
        if positives:
            out["flu_positives"] = positives

    body = _http_get(DELPHI.format(endpoint="fluview", query=urllib.parse.urlencode(
        {"regions": "nat", "epiweeks": span})))
    if body:
        try:
            rows = json.loads(body).get("epidata") or []
        except json.JSONDecodeError:
            rows = []
        visits = {}
        for row in rows:
            value = to_float(row.get("num_ili"))
            if value is not None:
                visits[epiweek_end(row.get("epiweek"))] = value
        if visits:
            out["ili_visits"] = visits
    return out


def fetch_cdc_pathogen(pathogen: str) -> dict[str, float]:
    """Weekly national NAAT test counts for one pathogen (paged Socrata read)."""
    where = f"level='National' AND pathogen='{pathogen}'"
    if pathogen == "RSV":
        where += " AND subtype='Combined Type'"
    values: dict[str, float] = {}
    offset = 0
    while True:
        query = urllib.parse.urlencode({
            "$select": "mmwrweek_end,tests",
            "$where": where,
            "$order": "mmwrweek_end",
            "$limit": 1000,
            "$offset": offset,
        })
        body = _http_get(SOCRATA.format(query=query))
        if not body:
            break
        try:
            rows = json.loads(body)
        except json.JSONDecodeError:
            break
        for row in rows:
            value = to_float(row.get("tests"))
            week = str(row.get("mmwrweek_end") or "")[:10]
            if value is not None and week:
                values[week] = value
        if len(rows) < 1000:
            break
        offset += 1000
    return values


def read_csv(path: Path) -> dict[str, float]:
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


def write_csv(path: Path, values: dict[str, float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "value"])
        for day in sorted(values):
            writer.writerow([day, values[day]])


def build(offline: bool = False) -> dict:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fetched: dict[str, dict[str, float]] = {}
    errors: dict[str, str] = {}

    if not offline:
        fetched.update(fetch_delphi())
        for series_id, pathogen in (("rsv_naat_tests", "RSV"), ("sars_cov2_naat_tests", "SARS-COV-2")):
            values = fetch_cdc_pathogen(pathogen)
            if values:
                fetched[series_id] = values
        for series_id in SERIES_META:
            if series_id not in fetched:
                errors[series_id] = "fetch returned no rows; kept cached history"

    today = date.today()
    series_out: dict[str, dict] = {}
    for series_id, meta in SERIES_META.items():
        path = OUT_DIR / f"{series_id}.csv"
        cached = read_csv(path)
        merged = {**cached, **fetched.get(series_id, {})}
        if merged:
            write_csv(path, merged)
        if not merged:
            series_out[series_id] = {**meta, "latest": None, "as_of": None, "weeks": 0,
                                     "stale": True, "error": errors.get(series_id, "no data")}
            continue
        latest_day = max(merged)
        age = (today - date.fromisoformat(latest_day)).days
        series_out[series_id] = {
            **meta,
            "path": str(path.relative_to(ROOT)).replace("\\", "/"),
            "latest": merged[latest_day],
            "as_of": latest_day,
            "weeks": len(merged),
            "first_week": min(merged),
            "age_days": age,
            "stale": age > STALENESS_MAX_DAYS,
            "error": errors.get(series_id),
        }

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of": today.isoformat(),
        "staleness_max_days": STALENESS_MAX_DAYS,
        "disclaimer": (
            "Context only. US respiratory testing volumes are a demand driver, not a "
            "revenue estimate. Out-of-sample testing found no incremental forecasting "
            "value for QDEL respiratory revenue over a trend+seasonality baseline "
            "(see QDEL/research/respiratory_model.json)."
        ),
        "series": series_out,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch US respiratory-virus testing panel.")
    parser.add_argument("--offline", action="store_true", help="rebuild manifest from cached CSVs only")
    args = parser.parse_args()

    payload = build(offline=args.offline)
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    fresh = sum(1 for s in payload["series"].values() if not s.get("stale"))
    weeks = max((s.get("weeks") or 0) for s in payload["series"].values())
    print(f"Wrote {MANIFEST.relative_to(ROOT)} ({fresh}/{len(payload['series'])} series fresh, {weeks} weeks)")
    for sid, s in sorted(payload["series"].items()):
        flag = "STALE" if s.get("stale") else "ok"
        print(f"  {sid:<24} {str(s.get('as_of')):<12} {s.get('weeks') or 0:>4}w  {flag}"
              + (f"  [{s['error']}]" if s.get("error") else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
