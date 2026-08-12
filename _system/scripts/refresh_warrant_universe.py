#!/usr/bin/env python3
"""Refresh delayed warrant marks and discover accession-locked SEC events.

Network failures are fail-soft: the last-known-good market file remains usable,
while discovery_state.json records the failure streak for the graph health loop.
"""
from __future__ import annotations

import argparse
import urllib.parse
from datetime import date, timedelta

from warrant_common import (
    COHORTS_PATH,
    DISCOVERY_STATE_PATH,
    EVENTS_PATH,
    MARKET_HISTORY_PATH,
    MARKET_PATH,
    SEC_UA,
    append_jsonl,
    fetch_yahoo_chart,
    latest_registry,
    read_json,
    today,
    utc_now,
    write_json,
    _http_json,
)


def refresh_market(*, capture_cohort: bool) -> tuple[int, int]:
    prior = read_json(MARKET_PATH, {}) or {}
    quotes = dict(prior.get("quotes") or {})
    successes = 0
    failures = 0
    history: list[dict] = []
    cohorts: list[dict] = []
    month = today()[:7]

    for record in latest_registry():
        if record.get("lifecycle") not in {"active", "candidate"}:
            continue
        warrant_id = str(record["warrant_id"])
        warrant_symbol = str((record.get("vendor_symbols") or {}).get("yahoo") or "")
        common_symbol = str(record.get("common_ticker") or "")
        pair: dict[str, dict | None] = {
            warrant_id: fetch_yahoo_chart(warrant_symbol) if warrant_symbol else None,
            f"common:{warrant_id}": fetch_yahoo_chart(common_symbol) if common_symbol else None,
        }
        for key, quote in pair.items():
            role = "common" if key.startswith("common:") else "warrant"
            if quote:
                quote = {**quote, "warrant_id": warrant_id, "role": role}
                quotes[key] = quote
                successes += 1
                history.append(
                    {
                        "observation_id": f"{warrant_id}:{quote['quote_date']}:{role}",
                        "warrant_id": warrant_id,
                        "role": role,
                        "ticker": quote.get("symbol"),
                        "quote_date": quote.get("quote_date"),
                        "close": quote.get("close"),
                        "volume": quote.get("volume"),
                        "adv20": quote.get("adv20"),
                        "source": quote.get("source"),
                        "observed_at": quote.get("fetched_at"),
                    }
                )
            else:
                failures += 1

        warrant_quote = pair.get(warrant_id) or quotes.get(warrant_id) or {}
        common_quote = pair.get(f"common:{warrant_id}") or quotes.get(f"common:{warrant_id}") or {}
        if capture_cohort and warrant_quote.get("close") is not None and common_quote.get("close") is not None:
            cohorts.append(
                {
                    "cohort_id": f"{warrant_id}:{month}",
                    "warrant_id": warrant_id,
                    "lane": record.get("lane"),
                    "captured_at": utc_now(),
                    "baseline_date": warrant_quote.get("quote_date"),
                    "baseline_warrant_close": warrant_quote.get("close"),
                    "baseline_common_close": common_quote.get("close"),
                    "initial_contract_state": "verified" if record.get("terms_complete") else "blocked",
                    "initial_survival_state": (record.get("survival") or {}).get("status"),
                    "horizons_days": [90, 365],
                    "point_in_time": True,
                }
            )

    now = utc_now()
    payload = {
        "schema_version": "1.0",
        "generated_at": now,
        "last_successful_refresh": now if successes else prior.get("last_successful_refresh"),
        "source": "Yahoo chart-v8 delayed daily closes; not executable quotes",
        "quotes": quotes,
        "summary": {
            "successful_symbols": successes,
            "failed_symbols": failures,
            "preserved_last_known_good": failures > 0,
            "two_sided_quotes": sum(
                1 for q in quotes.values() if q.get("bid") is not None and q.get("ask") is not None
            ),
        },
    }
    write_json(MARKET_PATH, payload)
    append_jsonl(MARKET_HISTORY_PATH, history, identity_key="observation_id")
    append_jsonl(COHORTS_PATH, cohorts, identity_key="cohort_id")
    return successes, failures


def _sec_url(cik: str, accession: str, filename: str) -> str:
    cik_num = str(int(cik))
    return f"https://www.sec.gov/Archives/edgar/data/{cik_num}/{accession.replace('-', '')}/{filename}"


def _event_lane(source: dict) -> str:
    items = {str(item) for item in source.get("items") or []}
    name = " ".join(source.get("display_names") or []).lower()
    description = str(source.get("file_description") or "").lower()
    if "1.03" in items or any(token in name for token in ("qvc group", "chapter 11", "bankrupt")):
        return "chapter_11"
    if "acquisition corp" in name or "public warrant agreement" in description:
        return "despac"
    if "3.02" in items:
        return "rescue_financing"
    return "other"


def _candidate_score(source: dict) -> int:
    """Research-priority heuristic only; never an opportunity score."""
    file_type = str(source.get("file_type") or "").upper()
    description = str(source.get("file_description") or "").lower()
    items = {str(item) for item in source.get("items") or []}
    name = " ".join(source.get("display_names") or []).upper()
    score = 0
    if file_type.startswith("EX-4"):
        score += 4
    if "warrant" in description:
        score += 5
    if "1.03" in items:
        score += 5
    if "3.02" in items:
        score += 2
    if "ACQUISITION CORP" in name:
        score += 1
    if any(token.rstrip(",)").endswith("W") for token in name.replace("(", " ").split()):
        score += 2
    return score


def discover_sec(*, days: int, limit: int) -> tuple[int, bool, str | None]:
    end = date.today()
    start = end - timedelta(days=max(1, days))
    params = {
        # Unquoted terms are deliberate.  Exact-phrase EFTS search silently
        # dropped exhibits whose HTML inserts inline tags between the words.
        "q": "warrant agreement",
        "dateRange": "custom",
        "startdt": start.isoformat(),
        "enddt": end.isoformat(),
        "forms": "8-K,8-K/A,8-A12B,8-A12G,S-1,S-3,S-4,F-4,424B3,424B4,SC TO-I",
        "from": "0",
        "size": str(max(1, min(limit, 100))),
    }
    url = "https://efts.sec.gov/LATEST/search-index?" + urllib.parse.urlencode(params)
    doc = _http_json(url, user_agent=SEC_UA, timeout=45)
    if not doc:
        return 0, False, "SEC EFTS request failed"
    hits = ((doc.get("hits") or {}).get("hits") or [])[:limit]
    by_accession: dict[str, dict] = {}
    for hit in hits:
        source = hit.get("_source") or {}
        ciks = source.get("ciks") or []
        accession = str(source.get("adsh") or "")
        hit_id = str(hit.get("_id") or "")
        filename = hit_id.split(":", 1)[1] if ":" in hit_id else ""
        if not ciks or not accession or not filename:
            continue
        cik = str(ciks[0]).zfill(10)
        event = {
                "event_id": f"warrant-sec:{cik}:{accession}",
                "observed_at": utc_now(),
                "filed_at": source.get("file_date"),
                "issuer": (source.get("display_names") or [""])[0],
                "cik": cik,
                "form": source.get("form") or (source.get("root_forms") or [None])[0],
                "items": source.get("items") or [],
                "file_type": source.get("file_type"),
                "description": source.get("file_description"),
                "accession": accession,
                "source_url": _sec_url(cik, accession, filename),
                "lane_hint": _event_lane(source),
                "identity_status": "unresolved",
                "resolution_state": "pending",
                "terms_status": "unparsed",
                "review_reason": "New warrant-language filing; verify transferability, series identity, and exact agreement terms.",
                "research_priority_score": _candidate_score(source),
            }
        prior = by_accession.get(accession)
        if prior is None or int(event["research_priority_score"]) > int(prior["research_priority_score"]):
            by_accession[accession] = event
    events = list(by_accession.values())
    added = append_jsonl(EVENTS_PATH, events, identity_key="event_id")
    return added, True, None


def update_discovery_state(*, success: bool, added: int, error: str | None) -> None:
    prior = read_json(DISCOVERY_STATE_PATH, {}) or {}
    streak = 0 if success else int(prior.get("consecutive_failures") or 0) + 1
    write_json(
        DISCOVERY_STATE_PATH,
        {
            "schema_version": "1.0",
            "updated_at": utc_now(),
            "last_success_at": utc_now() if success else prior.get("last_success_at"),
            "last_added_count": added,
            "consecutive_failures": streak,
            "unhealthy": streak >= 3,
            "last_error": error,
            "healer": "python _system/scripts/refresh_warrant_universe.py --discover --refresh-market --capture-cohort",
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-market", action="store_true")
    parser.add_argument("--capture-cohort", action="store_true")
    parser.add_argument("--discover", action="store_true")
    parser.add_argument("--discover-days", type=int, default=14)
    parser.add_argument("--discover-limit", type=int, default=50)
    args = parser.parse_args()

    if args.refresh_market:
        successes, failures = refresh_market(capture_cohort=args.capture_cohort)
        print(f"warrant market: {successes} symbol(s) refreshed; {failures} failed; LKG preserved")
    if args.discover:
        added, success, error = discover_sec(days=args.discover_days, limit=args.discover_limit)
        update_discovery_state(success=success, added=added, error=error)
        print(f"warrant SEC discovery: added={added} success={success}")
    if not args.refresh_market and not args.discover:
        parser.error("choose --refresh-market and/or --discover")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
