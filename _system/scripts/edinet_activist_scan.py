#!/usr/bin/env python3
"""Japan large-shareholding reports (大量保有報告書) from EDINET.

The SEC scan needs a CIK, so every non-US holding in the book has zero activist
coverage: 3905.T, 7176.T, 8697.T, 9984.T, 0388.HK and the European and Canadian
names all have ``cik = None``. Japan is the second-most-active activism market
in the world -- a record 56 campaigns in 2025 -- and it files with the FSA, not
the SEC.

EDINET's 大量保有報告書 is Japan's Schedule 13D equivalent: a report required
above 5% ownership, with a change report (変更報告書) on each material move.

CREDENTIAL REQUIRED. EDINET API v2 needs a free subscription key, requested at
https://api.edinet-fsa.go.jp/ and supplied here as ``EDINET_API_KEY``. Without
it this module reports "not configured" and exits cleanly -- it never pretends
to have looked.

The 200-that-is-really-401 trap
-------------------------------
An unauthenticated request returns **HTTP 200** with ``{"StatusCode": 401}`` in
the body. Any caller checking ``resp.status`` sees success and reads an empty
result list, which is indistinguishable from "no filings today". This module
reads the status out of the payload, which is where EDINET actually puts it.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from activist_common import (
    append_scan_log,
    match_firm_id,
    now_iso,
    portfolio_tickers,
    write_json,
)

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = ROOT / "_system" / "data" / "activist_jp_edinet.json"
API_ROOT = "https://api.edinet-fsa.go.jp/api/v2"
USER_AGENT = "MagisCapitalResearch activist-jp"
SLEEP_SEC = 0.3
DEFAULT_LOOKBACK_DAYS = 14

# 府令コード25 = 大量保有 (large shareholding). 350 is the initial report,
# 360 the change report -- the pair maps onto SC 13D and SC 13D/A.
LARGE_SHAREHOLDING_ORDINANCE = "25"
LARGE_SHAREHOLDING_DOC_TYPES = {"350", "360"}
DOC_TYPE_LABEL = {
    "350": "大量保有報告書 (initial)",
    "360": "変更報告書 (amendment)",
}


class EdinetNotConfigured(RuntimeError):
    """No subscription key available."""


class EdinetApiError(RuntimeError):
    """EDINET answered, but the payload carries a non-200 StatusCode."""


def api_key() -> str | None:
    return os.environ.get("EDINET_API_KEY") or None


def fetch_documents(day: str, *, key: str) -> list[dict]:
    """Document index for one calendar day.

    Raises EdinetApiError when the body reports a failure, regardless of the
    HTTP status -- see the module docstring.
    """
    query = urllib.parse.urlencode({"date": day, "type": "2"})
    request = urllib.request.Request(
        f"{API_ROOT}/documents.json?{query}",
        headers={"User-Agent": USER_AGENT, "Ocp-Apim-Subscription-Key": key},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8", errors="ignore"))
    time.sleep(SLEEP_SEC)

    status = payload.get("StatusCode") or payload.get("metadata", {}).get("status")
    if status is not None and int(status) != 200:
        raise EdinetApiError(
            f"EDINET returned StatusCode {status} for {day}: "
            f"{payload.get('message') or payload.get('metadata', {}).get('message')}"
        )
    return payload.get("results") or []


def sec_code_to_ticker(sec_code: str | None) -> str | None:
    """EDINET carries a 5-digit securities code; the book uses 4 digits + .T."""
    code = (sec_code or "").strip()
    if len(code) < 4 or not code[:4].isdigit():
        return None
    return f"{code[:4]}.T"


def is_large_shareholding(row: dict) -> bool:
    return (
        str(row.get("ordinanceCode") or "") == LARGE_SHAREHOLDING_ORDINANCE
        and str(row.get("docTypeCode") or "") in LARGE_SHAREHOLDING_DOC_TYPES
    )


def row_to_entry(row: dict, *, holdings: set[str]) -> dict | None:
    ticker = sec_code_to_ticker(row.get("secCode"))
    if not ticker:
        return None
    filer = (row.get("filerName") or "").strip()
    doc_type = str(row.get("docTypeCode") or "")
    doc_id = row.get("docID") or ""
    return {
        "ticker": ticker,
        "in_book": ticker in holdings,
        "firm_id": match_firm_id(filer),
        "filer_name": filer,
        "form": DOC_TYPE_LABEL.get(doc_type, doc_type),
        "doc_type_code": doc_type,
        "report_date": (row.get("submitDateTime") or "")[:10],
        "issuer_name": (row.get("filerName") or "").strip(),
        "subject_name": (row.get("docDescription") or "").strip(),
        "doc_id": doc_id,
        "source_url": f"{API_ROOT}/documents/{doc_id}?type=2" if doc_id else None,
        "viewer_url": (
            f"https://disclosure2.edinet-fsa.go.jp/WZEK0040.aspx?"
            f"S100{doc_id[-6:]}" if doc_id else None
        ),
        "source": "edinet",
        "side": "long",
    }


def scan(
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    key: str | None = None,
    today: date | None = None,
) -> dict:
    key = key or api_key()
    if not key:
        raise EdinetNotConfigured(
            "EDINET_API_KEY is not set. Request a free key at https://api.edinet-fsa.go.jp/ "
            "and add it to the repository secrets as EDINET_API_KEY."
        )

    holdings = {t.upper() for t in portfolio_tickers()}
    today = today or datetime.now(timezone.utc).date()
    rows: list[dict] = []
    days_scanned = 0
    failures: list[str] = []

    for offset in range(lookback_days):
        day = (today - timedelta(days=offset)).isoformat()
        try:
            documents = fetch_documents(day, key=key)
        except EdinetApiError as exc:
            # A credential or quota problem repeats every day; stop rather than
            # log the same failure fourteen times.
            failures.append(str(exc))
            append_scan_log({"source": "edinet", "status": "api_error", "error": str(exc)[:200]})
            break
        except Exception as exc:
            failures.append(f"{day}: {type(exc).__name__}: {exc}")
            append_scan_log({"source": "edinet", "status": "fetch_fail", "error": str(exc)[:200]})
            continue
        days_scanned += 1
        for row in documents:
            if not is_large_shareholding(row):
                continue
            entry = row_to_entry(row, holdings=holdings)
            if entry:
                rows.append(entry)

    rows.sort(key=lambda r: (r.get("report_date") or ""), reverse=True)
    in_book = [r for r in rows if r["in_book"]]
    matched = [r for r in rows if r.get("firm_id")]
    return {
        "generated_at": now_iso(),
        "source": "edinet",
        "lookback_days": lookback_days,
        "days_scanned": days_scanned,
        "row_count": len(rows),
        "in_book_count": len(in_book),
        "registry_matched_count": len(matched),
        "failures": failures,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        result = scan(lookback_days=args.lookback_days)
    except EdinetNotConfigured as exc:
        # Not a failure: the lane is built and idle until a key exists.
        print(f"EDINET lane not configured: {exc}")
        return 0

    if not args.dry_run:
        write_json(OUTPUT_PATH, result)
    print(
        f"EDINET: {result['row_count']} large-shareholding reports over "
        f"{result['days_scanned']} day(s) | {result['in_book_count']} on holdings | "
        f"{result['registry_matched_count']} by a tracked firm"
    )
    for row in result["rows"][:10]:
        mark = "*" if row["in_book"] else " "
        print(f"  {mark} {row['report_date']}  {row['ticker']:9} {row['filer_name'][:44]}")
    if result["failures"]:
        print(f"  {len(result['failures'])} failure(s); first: {result['failures'][0][:120]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
