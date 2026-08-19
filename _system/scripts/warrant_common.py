#!/usr/bin/env python3
"""Shared warrant registry, market, and gate helpers.

The warrant registry is append-only JSONL.  Live market state and derived
dashboard rows are separate artifacts so a transient vendor failure can never
rewrite contractual terms.
"""
from __future__ import annotations

import json
import math
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
WARRANT_DIR = ROOT / "_system" / "data" / "warrants"
REGISTRY_PATH = WARRANT_DIR / "warrant_registry.jsonl"
REGISTRY_AMENDMENTS_PATH = WARRANT_DIR / "warrant_registry_amendments.jsonl"
EVENTS_PATH = WARRANT_DIR / "warrant_events.jsonl"
MARKET_PATH = WARRANT_DIR / "warrant_market.json"
MARKET_HISTORY_PATH = WARRANT_DIR / "warrant_market_history.jsonl"
COHORTS_PATH = WARRANT_DIR / "warrant_cohorts.jsonl"
OUTCOMES_PATH = WARRANT_DIR / "warrant_outcomes.jsonl"
CALIBRATION_PATH = WARRANT_DIR / "warrant_calibration.json"
DISCOVERY_STATE_PATH = WARRANT_DIR / "discovery_state.json"
DASHBOARD_PATH = ROOT / "dashboard" / "data" / "warrants.json"

SEC_UA = os.environ.get(
    "WARRANT_SEC_USER_AGENT",
    "MagisResearchBot/1.0 (warrant research; contact: research@magiscapital.com)",
)
YAHOO_UA = "Mozilla/5.0 (compatible; MagisWarrantMonitor/1.0)"

LANES = {
    "chapter_11",
    "despac",
    "rights_offering",
    "distressed_exchange",
    "settlement",
    "distribution",
    "rescue_financing",
    "other",
}
LIFECYCLES = {
    "candidate",
    "active",
    "redeemed",
    "exchanged",
    "expired",
    "delisted",
    "cancelled",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def today() -> str:
    return date.today().isoformat()


def parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, payload: Any) -> None:
    """Atomic JSON write used by scheduled refreshes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, newline="\n"
    ) as handle:
        handle.write(text)
        tmp = Path(handle.name)
    tmp.replace(path)


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path.name}:{line_number}: invalid JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{path.name}:{line_number}: row must be an object")
        rows.append(value)
    return rows


def append_jsonl(path: Path, rows: Iterable[dict], *, identity_key: str | None = None) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    incoming = list(rows)
    if not incoming:
        return 0
    existing_ids: set[str] = set()
    if identity_key and path.exists():
        for row in load_jsonl(path):
            value = row.get(identity_key)
            if value is not None:
                existing_ids.add(str(value))
    added = [r for r in incoming if not identity_key or str(r.get(identity_key)) not in existing_ids]
    if not added:
        return 0
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for row in added:
            handle.write(json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n")
    return len(added)


def latest_registry(rows: list[dict] | None = None) -> list[dict]:
    rows = rows if rows is not None else (
        load_jsonl(REGISTRY_PATH) + load_jsonl(REGISTRY_AMENDMENTS_PATH)
    )
    latest: dict[str, dict] = {}
    for row in rows:
        warrant_id = str(row.get("warrant_id") or "")
        if not warrant_id:
            continue
        current = latest.get(warrant_id)
        if current is None or int(row.get("version") or 0) > int(current.get("version") or 0):
            latest[warrant_id] = row
    return sorted(latest.values(), key=lambda row: (str(row.get("lifecycle")), str(row.get("warrant_ticker"))))


def validate_registry(rows: list[dict] | None = None) -> list[str]:
    rows = rows if rows is not None else (
        load_jsonl(REGISTRY_PATH) + load_jsonl(REGISTRY_AMENDMENTS_PATH)
    )
    errors: list[str] = []
    versions: set[tuple[str, int]] = set()
    for index, row in enumerate(rows, 1):
        prefix = f"row {index}"
        warrant_id = str(row.get("warrant_id") or "")
        version = int(row.get("version") or 0)
        if not warrant_id:
            errors.append(f"{prefix}: missing warrant_id")
        if version < 1:
            errors.append(f"{prefix}: version must be >= 1")
        key = (warrant_id, version)
        if key in versions:
            errors.append(f"{prefix}: duplicate warrant_id/version {warrant_id}/{version}")
        versions.add(key)
        if row.get("lane") not in LANES:
            errors.append(f"{prefix}: invalid lane {row.get('lane')!r}")
        if row.get("lifecycle") not in LIFECYCLES:
            errors.append(f"{prefix}: invalid lifecycle {row.get('lifecycle')!r}")
        source = row.get("source") or {}
        if not str(source.get("url") or "").startswith("https://"):
            errors.append(f"{prefix}: source.url must be HTTPS")
        terms = row.get("terms") or {}
        if row.get("terms_complete"):
            for field in ("strike", "currency", "share_ratio", "expiry"):
                if terms.get(field) in (None, ""):
                    errors.append(f"{prefix}: terms_complete but {field} missing")
        if row.get("lifecycle") == "active" and parse_date(terms.get("expiry")):
            if parse_date(terms.get("expiry")) < date.today():
                errors.append(f"{prefix}: active security is past contractual expiry")
    return errors


def _http_json(url: str, *, user_agent: str, timeout: int = 30) -> dict | None:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": user_agent, "Accept": "application/json,*/*"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            value = json.loads(response.read().decode("utf-8"))
            return value if isinstance(value, dict) else None
    except (
        urllib.error.HTTPError,
        urllib.error.URLError,
        TimeoutError,
        OSError,
        json.JSONDecodeError,
    ):
        return None


def fetch_yahoo_chart(symbol: str, *, range_: str = "1mo") -> dict | None:
    encoded = urllib.parse.quote(symbol, safe="")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}?range={range_}&interval=1d"
    doc = _http_json(url, user_agent=YAHOO_UA)
    try:
        result = doc["chart"]["result"][0]
        timestamps = result.get("timestamp") or []
        quotes = (result.get("indicators") or {}).get("quote") or []
        quote = quotes[0] if quotes else {}
    except (TypeError, KeyError, IndexError):
        return None
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    observations = [
        (stamp, closes[i], volumes[i] if i < len(volumes) else None)
        for i, stamp in enumerate(timestamps)
        if i < len(closes) and closes[i] is not None
    ]
    if not observations:
        return None
    stamp, close, volume = observations[-1]
    valid_volumes = [float(v) for _, _, v in observations[-20:] if v is not None]
    previous = observations[-2][1] if len(observations) > 1 else None
    return {
        "symbol": symbol,
        "close": round(float(close), 6),
        "previous_close": round(float(previous), 6) if previous is not None else None,
        "volume": int(volume) if volume is not None else None,
        "adv20": round(sum(valid_volumes) / len(valid_volumes), 2) if valid_volumes else None,
        "quote_date": datetime.fromtimestamp(int(stamp), tz=timezone.utc).date().isoformat(),
        "exchange": (result.get("meta") or {}).get("exchangeName"),
        "currency": (result.get("meta") or {}).get("currency"),
        "source": "yahoo_chart_v8_delayed_close",
        "fetched_at": utc_now(),
        "bid": None,
        "ask": None,
    }


def finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def market_pair(record: dict, market_doc: dict) -> tuple[dict, dict]:
    rows = market_doc.get("quotes") or {}
    return rows.get(str(record.get("warrant_id"))) or {}, rows.get(f"common:{record.get('warrant_id')}") or {}


def gate_state(record: dict, warrant_quote: dict, common_quote: dict) -> dict:
    terms = record.get("terms") or {}
    identity_missing = [
        name
        for name, value in {
            "CIK": record.get("cik"),
            "common ticker": record.get("common_ticker"),
            "warrant ticker": record.get("warrant_ticker"),
            "source": (record.get("source") or {}).get("url"),
            "strike": terms.get("strike"),
            "share ratio": terms.get("share_ratio"),
            "expiry": terms.get("expiry"),
        }.items()
        if value in (None, "")
    ]
    identity_pass = bool(record.get("terms_complete")) and not identity_missing
    survival = record.get("survival") or {}
    survival_missing = list(survival.get("missing_inputs") or [])
    survival_pass = survival.get("status") == "pass" and not survival_missing
    market_missing: list[str] = []
    if finite_number(common_quote.get("close")) is None:
        market_missing.append("common close")
    if finite_number(warrant_quote.get("close")) is None:
        market_missing.append("warrant close")
    if finite_number(warrant_quote.get("bid")) is None:
        market_missing.append("warrant bid")
    if finite_number(warrant_quote.get("ask")) is None:
        market_missing.append("warrant ask")
    market_pass = not market_missing
    lifecycle = record.get("lifecycle")
    if lifecycle not in {"active", "candidate"}:
        status = lifecycle
    elif not identity_pass:
        status = "terms_blocked"
    elif not survival_pass:
        status = "survival_blocked"
    elif not market_pass:
        status = "market_blocked"
    else:
        status = "review_ready"
    return {
        "identity": {"pass": identity_pass, "missing": identity_missing},
        "survival": {"pass": survival_pass, "missing": survival_missing},
        "market": {"pass": market_pass, "missing": market_missing},
        "status": status,
    }


def quote_age_days(quote: dict) -> int | None:
    """Days since the delayed mark was last fetched, else last print date.

    A successful Yahoo pull with an old last-trade date is still a current
    delayed mark. Illiquid names were failing P6 because quote_date lagged
    fetched_at by more than five days while the vendor fetch itself was fresh.
    """
    stamp = parse_date(quote.get("fetched_at")) or parse_date(quote.get("quote_date"))
    return (date.today() - stamp).days if stamp else None
