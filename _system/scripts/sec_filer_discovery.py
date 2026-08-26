#!/usr/bin/env python3
"""Filer-driven activist discovery: walk what registry firms file, not what our tickers receive.

`sec_activist_scan.py` is issuer-driven — it walks portfolio tickers and reads
whatever landed on them. That can only ever confirm activism at names we already
own; a campaign at a company we do not hold is never fetched, which is precisely
when an activist thesis is worth reading early.

This module inverts it. For each active registry firm it resolves the filer CIK,
lists what that firm filed with EDGAR, and resolves the subject issuer of each
Schedule 13D/G from the structured cover page. Rows for issuers outside the book
are the point of the exercise, not noise.

Read-only HTTPS against sec.gov. No IB Gateway involvement of any kind.
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from activist_common import (
    ACTIVIST_FORMS,
    active_firms,
    firm_has_ingest,
    load_json,
    now_iso,
    portfolio_tickers,
    write_json,
)
from sec_filer_parse import normalize_form, parse_schedule_13_xml

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "_system" / "frameworks" / "activist_firm_registry.json"
OUTPUT_PATH = ROOT / "_system" / "data" / "activist_filer_discovery.json"
SEC_UA = "MagisCapitalResearch activist-discovery contact@magiscapital.example"
SLEEP_SEC = 0.15
RETRY_SLEEP_SEC = 2.0
MAX_RETRIES = 3
DEFAULT_MIN_DATE = "2025-01-01"
DEFAULT_PER_FIRM = 40

COMPANY_INFO_RE = re.compile(r"<company-info>(.*?)</company-info>", re.S)
CIK_RE = re.compile(r"<cik>(\d+)</cik>")
CONFORMED_RE = re.compile(r"<conformed-name>([^<]+)</conformed-name>")
ENTRY_RE = re.compile(r"<entry>(.*?)</entry>", re.S)


def _tag(block: str, tag: str) -> str:
    m = re.search(rf"<{tag}>([^<]*)</{tag}>", block)
    return (m.group(1) or "").strip() if m else ""


def fetch(url: str) -> str:
    """GET with SEC-appropriate throttling and 503 backoff."""
    last: Exception | None = None
    for attempt in range(MAX_RETRIES):
        req = urllib.request.Request(
            url, headers={"User-Agent": SEC_UA, "Accept-Encoding": "gzip"}
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
                encoding = resp.headers.get("Content-Encoding")
            if encoding == "gzip":
                raw = gzip.decompress(raw)
            time.sleep(SLEEP_SEC)
            return raw.decode("utf-8", errors="ignore")
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code in (403, 429, 503):
                time.sleep(RETRY_SLEEP_SEC * (attempt + 1))
                continue
            raise
        except Exception as exc:  # transient network
            last = exc
            time.sleep(RETRY_SLEEP_SEC * (attempt + 1))
    raise last if last else RuntimeError("fetch failed")


def firm_search_names(firm: dict) -> list[str]:
    names = [firm.get("name") or ""]
    names.extend(firm.get("aliases") or [])
    # Personal names ("Paul Singer") match the wrong EDGAR entity; entity-shaped
    # names only.
    return [n for n in names if n and len(n.split()) >= 2]


def lookup_filer(name: str, *, form: str = "SCHEDULE 13D") -> dict | None:
    """Resolve one filer name to its EDGAR CIK plus recent filings."""
    query = urllib.parse.urlencode(
        {
            "action": "getcompany",
            "company": name,
            "type": form,
            "dateb": "",
            "owner": "include",
            "count": "100",
            "output": "atom",
        }
    )
    try:
        xml = fetch(f"https://www.sec.gov/cgi-bin/browse-edgar?{query}")
    except Exception:
        return None

    info = COMPANY_INFO_RE.search(xml)
    if not info:
        return None
    cik_match = CIK_RE.search(info.group(1))
    if not cik_match:
        # Multiple companies matched; the feed lists them without a single
        # company-info block. Ambiguous, so decline rather than guess.
        return None
    conformed = CONFORMED_RE.search(info.group(1))

    filings = []
    for block in ENTRY_RE.findall(xml):
        filing_type = normalize_form(_tag(block, "filing-type"))
        filings.append(
            {
                "form": filing_type,
                "filing_date": _tag(block, "filing-date"),
                "accession": _tag(block, "accession-number"),
                "index_url": _tag(block, "filing-href"),
            }
        )
    return {
        "cik": cik_match.group(1).lstrip("0"),
        "conformed_name": (conformed.group(1).strip() if conformed else name),
        "filings": filings,
    }


def resolve_issuer(cik: str, accession: str) -> dict:
    """Read the subject issuer off a Schedule 13D/G structured cover page."""
    if not accession:
        return {}
    nodash = accession.replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{nodash}/primary_doc.xml"
    try:
        facts = parse_schedule_13_xml(fetch(url))
    except Exception:
        return {}
    return {
        "issuer_name": facts.get("issuer_name") or "",
        "issuer_cik": facts.get("issuer_cik") or "",
        "cusip": facts.get("cusip") or "",
        "stake_percent": facts.get("stake_percent"),
    }


def _registry_cik(firm: dict) -> str:
    return str(firm.get("sec_cik") or "").lstrip("0")


def discover(
    *,
    firm_ids: list[str] | None = None,
    min_date: str = DEFAULT_MIN_DATE,
    per_firm: int = DEFAULT_PER_FIRM,
    resolve_issuers: bool = True,
    write_registry_ciks: bool = True,
) -> dict:
    holdings = {t.upper() for t in portfolio_tickers()}
    firms = [f for f in active_firms() if firm_has_ingest(f, "sec_13d")]
    if firm_ids:
        wanted = {f.lower() for f in firm_ids}
        firms = [f for f in firms if (f.get("id") or "").lower() in wanted]

    rows: list[dict] = []
    resolved_ciks: dict[str, str] = {}
    unresolved: list[str] = []

    for firm in firms:
        fid = firm.get("id") or ""
        cik = _registry_cik(firm)
        record = None
        if cik:
            record = {"cik": cik, "conformed_name": firm.get("name") or fid, "filings": []}
            for form in ("SCHEDULE 13D", "SCHEDULE 13G", "DFAN14A"):
                found = lookup_filer(firm.get("name") or fid, form=form)
                if found and found["cik"] == cik:
                    record["filings"].extend(found["filings"])
        else:
            for name in firm_search_names(firm):
                record = lookup_filer(name)
                if record:
                    break
        if not record or not record.get("cik"):
            unresolved.append(fid)
            continue

        resolved_ciks[fid] = record["cik"]
        seen: set[str] = set()
        kept = 0
        for filing in record["filings"]:
            if kept >= per_firm:
                break
            if filing["form"] not in ACTIVIST_FORMS:
                continue
            if filing["filing_date"] < min_date:
                continue
            if filing["accession"] in seen:
                continue
            seen.add(filing["accession"])
            kept += 1
            row = {
                "firm_id": fid,
                "firm_name": firm.get("name") or fid,
                "filer_cik": record["cik"],
                "form": filing["form"],
                "filing_date": filing["filing_date"],
                "accession": filing["accession"],
                "index_url": filing["index_url"],
            }
            if resolve_issuers and filing["form"] in {
                "SC 13D",
                "SC 13D/A",
                "SC 13G",
                "SC 13G/A",
            }:
                row.update(resolve_issuer(record["cik"], filing["accession"]))
            rows.append(row)

    if write_registry_ciks and resolved_ciks:
        _persist_ciks(resolved_ciks)

    rows.sort(key=lambda r: (r.get("filing_date") or "", r.get("firm_id") or ""), reverse=True)
    off_book = [r for r in rows if r.get("issuer_name") and not _in_book(r, holdings)]
    return {
        "generated_at": now_iso(),
        "min_date": min_date,
        "firm_count": len(firms),
        "resolved_firm_count": len(resolved_ciks),
        "unresolved_firms": sorted(unresolved),
        "row_count": len(rows),
        "off_book_count": len(off_book),
        "rows": rows,
    }


def _in_book(row: dict, holdings: set[str]) -> bool:
    """Best-effort book membership by issuer name token overlap.

    Ticker is not on the filing, so this is advisory: it decides whether a row
    is highlighted as new, never whether it is kept.
    """
    name = (row.get("issuer_name") or "").upper()
    if not name:
        return False
    token = re.sub(r"[^A-Z ]", "", name).split()
    return bool(token) and token[0] in holdings


def _persist_ciks(resolved: dict[str, str]) -> None:
    doc = load_json(REGISTRY_PATH, {"firms": []})
    firms = doc.get("firms") or []
    changed = False
    for firm in firms:
        fid = firm.get("id")
        cik = resolved.get(fid)
        if cik and str(firm.get("sec_cik") or "") != cik:
            firm["sec_cik"] = cik
            changed = True
    if changed:
        REGISTRY_PATH.write_text(
            json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--firm", action="append", help="Limit to these registry firm ids")
    parser.add_argument("--min-date", default=DEFAULT_MIN_DATE)
    parser.add_argument("--per-firm", type=int, default=DEFAULT_PER_FIRM)
    parser.add_argument(
        "--no-issuers", action="store_true", help="Skip the per-filing issuer lookup"
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not write output files")
    args = parser.parse_args()

    result = discover(
        firm_ids=args.firm,
        min_date=args.min_date,
        per_firm=args.per_firm,
        resolve_issuers=not args.no_issuers,
        write_registry_ciks=not args.dry_run,
    )
    if not args.dry_run:
        write_json(OUTPUT_PATH, result)
    # ASCII only: the Windows console is cp1252 and raises on "·"/em-dashes.
    print(
        f"filers resolved {result['resolved_firm_count']}/{result['firm_count']} | "
        f"{result['row_count']} filings | {result['off_book_count']} at issuers outside the book"
    )
    for row in result["rows"][:10]:
        issuer = row.get("issuer_name") or "?"
        print(f"  {row['filing_date']}  {row['form']:10} {row['firm_id']:18} -> {issuer}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
