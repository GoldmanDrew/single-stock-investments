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

from functools import lru_cache

from activist_common import (
    ACTIVIST_FORMS,
    active_firms,
    firm_has_ingest,
    load_json,
    now_iso,
    portfolio_tickers,
    ticker_meta,
    write_json,
)
from sec_filer_parse import (
    FUND_PERIODIC_FORMS,
    SECTION_16_FORMS,
    normalize_form,
    parse_schedule_13_xml,
)

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "_system" / "frameworks" / "activist_firm_registry.json"
OUTPUT_PATH = ROOT / "_system" / "data" / "activist_filer_discovery.json"
SEC_UA = "MagisCapitalResearch activist-discovery contact@magiscapital.example"
# browse-edgar (cgi-bin) rate-limits harder than the Archives endpoints and
# answers 503 rather than 429, so pace it and back off generously.
SLEEP_SEC = 0.6
RETRY_SLEEP_SEC = 5.0
MAX_RETRIES = 4
DEFAULT_MIN_DATE = "2025-01-01"
DEFAULT_PER_FIRM = 40
# Flush resolved CIKs to the registry this often, so an interrupted run keeps its work.
CIK_FLUSH_EVERY = 5
# Filer-side forms. These describe the firm rather than any one issuer, so an
# issuer-driven scan can never see them. Form 4s in particular are the only
# ownership signal that moves BETWEEN 13D/A amendments.
SECTION_16_QUERY_FORM = "4"
FUND_QUERY_FORMS = ("13F-HR", "N-PX")
# Form labels to try when resolving a CIK by name. Both 13D spellings,
# since EDGAR renamed the submission type on 2024-12-18 and a firm last
# active before then is invisible to a query for the new one.
CIK_PROBE_FORMS = ("SC 13D", "SCHEDULE 13D", "SC 13G", "DFAN14A")

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


# EDGAR matches `company=` as a prefix of its own conformed name, which is
# often shorter than ours: we call it "Engine Capital Management", EDGAR calls
# it "ENGINE CAPITAL, L.P.". Searching the full name returns nothing at all --
# not an error, just an empty feed -- so try progressively shorter prefixes.
TRAILING_DESCRIPTORS = (
    "management", "managements", "advisors", "advisers", "partners",
    "capital", "investments", "investment", "group", "associates", "llc",
    "lp", "l.p.", "inc", "inc.", "ltd", "ltd.", "limited", "holdings",
)


def firm_search_names(firm: dict) -> list[str]:
    """Candidate names to try against EDGAR, most specific first.

    EDGAR's `company=` is a prefix match on ITS conformed name, which often
    shares only the distinctive first word with ours: we say "Macellum Capital
    Management", EDGAR says "Macellum Advisors GP, LLC". Stopping the walk at
    two words meant that firm was never queried at all and came back as "no
    EDGAR entity".

    The firm's own name may shorten to a single distinctive word. Aliases may
    not -- they include personal names like "Paul Singer", where a one-word
    query matches the wrong entity entirely.
    """
    out: list[str] = []
    seen: set[str] = set()

    def add(candidate: str) -> None:
        key = candidate.lower()
        if key and key not in seen:
            seen.add(key)
            out.append(candidate)

    seeds = [(firm.get("name") or "", True)]
    seeds.extend((alias, False) for alias in (firm.get("aliases") or []))
    for seed, allow_single_word in seeds:
        words = [w for w in str(seed or "").replace(",", " ").split() if w]
        floor = 1 if allow_single_word else 2
        if len(words) < 2:
            continue
        while len(words) >= floor:
            add(" ".join(words))
            tail = words[-1].lower().strip(".,")
            if len(words) > floor and tail in TRAILING_DESCRIPTORS:
                words = words[:-1]
                continue
            if len(words) == 2 and floor == 1:
                # Try the distinctive stem alone, but only when it is long
                # enough not to match half of EDGAR.
                stem = words[0]
                if len(stem) >= 5 and stem.lower() not in TRAILING_DESCRIPTORS:
                    add(stem)
            break
    return out


def lookup_filer(
    name: str, *, form: str = "SCHEDULE 13D", cik: str | None = None
) -> dict | None:
    """List what one filer filed, by CIK when we know it and by name otherwise.

    Querying by CIK is exact. Name search is a prefix match against EDGAR's own
    conformed name, which is frequently spelled differently from ours -- so a
    firm whose CIK we already hold would otherwise still come back empty just
    because "Engine Capital Management" is "ENGINE CAPITAL, L.P." over there.
    """
    params = {
        "action": "getcompany",
        "type": form,
        "dateb": "",
        "owner": "include",
        "count": "100",
        "output": "atom",
    }
    if cik:
        params["CIK"] = str(cik)
    else:
        params["company"] = name
    query = urllib.parse.urlencode(params)
    # Deliberately NOT swallowed. Returning None on a failed request makes a
    # 503 indistinguishable from "EDGAR has no such filer", which is how this
    # backfill reported 36 firms as having no entity when the truth was that
    # sec.gov was rate-limiting -- Ancora and Browning West both resolve fine
    # on a request that actually completes.
    xml = fetch(f"https://www.sec.gov/cgi-bin/browse-edgar?{query}")

    info = COMPANY_INFO_RE.search(xml)
    if info:
        cik_match = CIK_RE.search(info.group(1))
        conformed = CONFORMED_RE.search(info.group(1))
    else:
        # EDGAR sometimes answers without a company-info block even for a single
        # match. Accept it when exactly one CIK appears in the whole feed;
        # several means the query was ambiguous, so decline rather than guess.
        ciks = set(CIK_RE.findall(xml))
        if len(ciks) != 1:
            return None
        cik_match = CIK_RE.search(xml)
        conformed = CONFORMED_RE.search(xml)
    if not cik_match:
        return None

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
    include_section_16: bool = True,
    include_fund_periodic: bool = True,
    flush_rows: bool = True,
) -> dict:
    allowed_forms = set(ACTIVIST_FORMS)
    if include_section_16:
        allowed_forms |= set(SECTION_16_FORMS)
    if include_fund_periodic:
        allowed_forms |= set(FUND_PERIODIC_FORMS)

    holdings = {t.upper() for t in portfolio_tickers()}
    firms = [f for f in active_firms() if firm_has_ingest(f, "sec_13d")]
    if firm_ids:
        wanted = {f.lower() for f in firm_ids}
        firms = [f for f in firms if (f.get("id") or "").lower() in wanted]

    rows: list[dict] = []
    resolved_ciks: dict[str, str] = {}
    unresolved: list[str] = []
    # Firms we could not even ask about. Kept apart from `unresolved`,
    # which means EDGAR answered and had nothing.
    lookup_errors: list[str] = []

    for firm in firms:
        fid = firm.get("id") or ""
        cik = _registry_cik(firm)
        record = None
        if cik:
            record = {"cik": cik, "conformed_name": firm.get("name") or fid, "filings": []}
            forms = ["SCHEDULE 13D", "SC 13D", "SCHEDULE 13G", "SC 13G", "DFAN14A"]
            if include_section_16:
                forms.append(SECTION_16_QUERY_FORM)
            if include_fund_periodic:
                forms.extend(FUND_QUERY_FORMS)
            for form in forms:
                try:
                    found = lookup_filer(firm.get("name") or fid, form=form, cik=cik)
                except Exception as exc:
                    lookup_errors.append(f"{fid}/{form}: {type(exc).__name__}: {str(exc)[:60]}")
                    continue
                if found and found["cik"] == cik:
                    record["filings"].extend(found["filings"])
        else:
            # Both spellings, because a firm last active before the rename only
            # appears under "SC 13D" and would otherwise read as "no entity".
            for name in firm_search_names(firm):
                for probe_form in CIK_PROBE_FORMS:
                    try:
                        record = lookup_filer(name, form=probe_form)
                    except Exception as exc:
                        lookup_errors.append(f"{fid}: {type(exc).__name__}: {str(exc)[:80]}")
                        record = None
                        break
                    if record:
                        break
                if record or any(e.startswith(f"{fid}:") for e in lookup_errors):
                    break
        if not record or not record.get("cik"):
            if not any(e.startswith(f"{fid}:") for e in lookup_errors):
                unresolved.append(fid)
            continue

        resolved_ciks[fid] = record["cik"]
        # Persist as we go. EDGAR name search is slow and 503s under load, so a
        # full pass can outlive its timeout -- an all-or-nothing write at the
        # end meant an interrupted run resolved nothing at all.
        if write_registry_ciks and len(resolved_ciks) % CIK_FLUSH_EVERY == 0:
            _persist_ciks(resolved_ciks)
            print(
                f"  ... {len(resolved_ciks)} firms done, {len(rows)} filings "
                f"({len(unresolved)} unresolved so far)",
                flush=True,
            )
            if flush_rows:
                # A full sweep outlives its own timeout; writing only at the end
                # meant an interrupted run produced nothing at all.
                write_json(
                    OUTPUT_PATH,
                    _assemble(
                        rows, firms, resolved_ciks, unresolved, lookup_errors,
                        min_date, holdings, complete=False,
                    ),
                )
        seen: set[str] = set()
        kept = 0
        for filing in record["filings"]:
            if kept >= per_firm:
                break
            if filing["form"] not in allowed_forms:
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

    return _assemble(
        rows, firms, resolved_ciks, unresolved, lookup_errors, min_date, holdings, complete=True
    )


def _assemble(rows, firms, resolved_ciks, unresolved, lookup_errors, min_date, holdings, *, complete):
    rows = list(rows)
    rows.sort(key=lambda r: (r.get("filing_date") or "", r.get("firm_id") or ""), reverse=True)
    cik_map = _issuer_cik_to_ticker(_portfolio_stamp())
    for row in rows:
        issuer_cik = str(row.get("issuer_cik") or "").lstrip("0")
        row["in_book"] = _in_book(row, holdings)
        row["book_ticker"] = cik_map.get(issuer_cik)
    off_book = [r for r in rows if r.get("issuer_name") and not r["in_book"]]
    return {
        "generated_at": now_iso(),
        # False when the pass was cut short. Anything reading this file needs to
        # know it is looking at a partial sweep rather than "these are all the
        # campaigns" -- a truncated run that looks complete is the same trap as
        # a dark feed answering 200.
        "complete": complete,
        "min_date": min_date,
        "firm_count": len(firms),
        "resolved_firm_count": len(resolved_ciks),
        "unresolved_firms": sorted(unresolved),
        "lookup_error_count": len(lookup_errors),
        "lookup_errors": lookup_errors[:40],
        "row_count": len(rows),
        "off_book_count": len(off_book),
        "rows": rows,
    }


@lru_cache(maxsize=1)
def _issuer_cik_to_ticker(stamp: tuple) -> dict[str, str]:
    """Reverse map from EDGAR issuer CIK to the ticker we hold it under.

    The structured cover page carries the issuer CIK, which is exact. The
    previous test compared the first word of the issuer name against the ticker
    set, which is neither -- it missed every multi-word issuer and could collide
    on a common first word.
    """
    out: dict[str, str] = {}
    for ticker in portfolio_tickers():
        cik = str((ticker_meta(ticker) or {}).get("cik") or "").lstrip("0")
        if cik:
            out[cik] = ticker.upper()
    return out


def _in_book(row: dict, holdings: set[str]) -> bool:
    """Whether this filing targets a company we hold.

    Advisory: it decides whether a row is highlighted as new, never whether it
    is kept.
    """
    issuer_cik = str(row.get("issuer_cik") or "").lstrip("0")
    if issuer_cik:
        return issuer_cik in _issuer_cik_to_ticker(_portfolio_stamp())
    # No structured cover page (pre-2024-12-18): fall back to an exact
    # normalized name match against the book, never a first-word prefix.
    name = _normalize_issuer(row.get("issuer_name"))
    if not name:
        return False
    return any(name == _normalize_issuer(ticker_meta(t).get("company")) for t in holdings)


def _normalize_issuer(value: str | None) -> str:
    text = re.sub(r"[^a-z0-9 ]", " ", str(value or "").lower())
    # Word-bounded: without \b this strips "inc" out of "Incyte" and "co" out
    # of "Costar", collapsing unrelated issuers onto the same key.
    text = re.sub(r"\b(inc|corp|corporation|company|co|ltd|plc|lp|llc|the)\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _portfolio_stamp() -> tuple:
    try:
        stat = (ROOT / "_system" / "portfolio" / "registry.json").stat()
    except OSError:
        return (0, 0)
    return (stat.st_mtime_ns, stat.st_size)


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
    parser.add_argument(
        "--no-section-16", action="store_true", help="Skip Form 4 accumulation filings"
    )
    parser.add_argument(
        "--no-fund-periodic", action="store_true", help="Skip 13F-HR / N-PX filings"
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not write output files")
    args = parser.parse_args()

    result = discover(
        firm_ids=args.firm,
        min_date=args.min_date,
        per_firm=args.per_firm,
        resolve_issuers=not args.no_issuers,
        write_registry_ciks=not args.dry_run,
        include_section_16=not args.no_section_16,
        include_fund_periodic=not args.no_fund_periodic,
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
