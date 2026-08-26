#!/usr/bin/env python3
"""Scan SEC EDGAR for activist filings on portfolio tickers (13D, proxy supplements)."""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta, timezone
import urllib.request
from pathlib import Path

from activist_common import (
    ACTIVIST_FORMS,
    CONDITIONAL_FORMS,
    CONDITIONAL_FORM_CAP,
    activist_reports_dir,
    append_scan_log,
    firm_name,
    load_ticker_index,
    now_iso,
    rel,
    save_ticker_index,
    ticker_meta,
    upsert_report,
)
from activist_date_parse import parse_local_report_metadata, normalize_partial_date, resolve_sec_filing_date
from sec_filer_parse import (
    CAMPAIGN_CLASSES,
    analyze_sec_filing,
    build_activist_title,
    form_from_filing_path,
    is_sec_filing_relpath,
    normalize_form,
    parse_schedule_13_xml,
    should_index_filing,
)

SEC_UA = "MarvinActivistScan contact@example.com"
SLEEP_SEC = 0.12
ROOT = Path(__file__).resolve().parents[2]
READ_LIMIT = 250_000


def sec_url(cik_path: str, accession: str, primary: str) -> str:
    nodash = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{cik_path}/{nodash}/{primary}"


def fetch_submissions(cik: str) -> dict:
    cik_padded = f"{int(cik):010d}"
    url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
    req = urllib.request.Request(url, headers={"User-Agent": SEC_UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def download(url: str, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 0:
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": SEC_UA})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
    except Exception as exc:
        append_scan_log({"source": "sec", "status": "download_fail", "url": url, "error": str(exc)})
        return False
    dest.write_bytes(data)
    return True


def read_filing_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:READ_LIMIT]
    except OSError:
        return ""


def form_from_filename(name: str) -> str:
    inferred = form_from_filing_path(name)
    if inferred:
        return inferred
    stem = name.split("_")[0]
    return stem.replace("-", " ")


def reindex_local_sec(
    ticker: str, *, include_passive: bool = False, fetch_xml: bool = False
) -> list[dict]:
    """Re-parse SEC filings already on disk.

    Offline by default. ``fetch_xml`` additionally pulls primary_doc.xml for
    post-2024-12-18 Schedules, which upgrades those rows from regex-scraped
    cover pages to the filer's own structured names, CIKs and Item 6 type.
    """
    hits: list[dict] = []
    index = load_ticker_index(ticker)
    non_sec = [
        r
        for r in (index.get("reports") or [])
        if r.get("source") not in {"sec_edgar", "local"}
        or not is_sec_filing_relpath(r.get("local_file"))
    ]
    sec_entries: list[dict] = []
    for side in ("long", "short"):
        base = activist_reports_dir(ticker, side)
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in {".htm", ".html", ".txt"}:
                continue
            rel_path = rel(path)
            if not is_sec_filing_relpath(rel_path):
                continue
            form = form_from_filing_path(path) or form_from_filename(path.name)
            text = read_filing_text(path)
            accession = _accession_from_name(path.name)
            xml_facts = {}
            if (
                fetch_xml
                and _is_schedule_13(form)
                and _has_structured_cover_page(_date_from_filing_name(path.name))
            ):
                cik = str((ticker_meta(ticker) or {}).get("cik") or "").lstrip("0")
                if cik:
                    xml_facts = fetch_schedule_13_xml(cik, accession)
            entry = _entry_from_analysis(
                ticker,
                form,
                path,
                text,
                source_url=report_source_url(index, path),
                accession=accession,
                xml_facts=xml_facts,
            )
            if not entry:
                continue
            if not should_index_filing(entry["filing_class"], include_passive=include_passive):
                continue
            hits.append(entry)
            sec_entries.append(entry)
    index["reports"] = non_sec + sec_entries
    save_ticker_index(ticker, index)
    return hits


def report_source_url(index: dict, path: Path) -> str | None:
    rel_path = rel(path)
    for report in index.get("reports") or []:
        if report.get("local_file") == rel_path:
            return report.get("source_url")
    return None


def _accession_from_name(name: str) -> str | None:
    m = __import__("re").search(r"acc(\d{10}_\d{2}_\d{6})", name)
    if not m:
        return None
    raw = m.group(1).replace("_", "")
    return f"{raw[:10]}-{raw[10:12]}-{raw[12:]}"


def _has_live_campaign(ticker: str, *, within_days: int = 400) -> bool:
    """True when this ticker already carries a recent activist campaign row.

    Gate for the high-volume conditional forms: an 8-K is worth reading for a
    board settlement only where a campaign exists to settle.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=within_days)).date().isoformat()
    for report in (load_ticker_index(ticker).get("reports") or []):
        if report.get("filing_class") in CAMPAIGN_CLASSES and (report.get("report_date") or "") >= cutoff:
            return True
    return False


# Structured cover pages are mandatory only from this date. Requesting one for
# an older filing is a guaranteed 404 -- and doing that for all ~14k local
# Schedules turned a minutes-long reindex into an hours-long one.
SCHEDULE_13_XML_FROM = "2024-12-18"


def _date_from_filing_name(name: str) -> str | None:
    match = re.search(r"_(\d{8})_", name)
    if not match:
        return None
    raw = match.group(1)
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"


def _has_structured_cover_page(filing_date: str | None) -> bool:
    return bool(filing_date) and filing_date >= SCHEDULE_13_XML_FROM


def _is_schedule_13(form: str) -> bool:
    return normalize_form(form) in {"SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A"}


def fetch_schedule_13_xml(cik_path: str, accession: str | None) -> dict:
    """Read the structured cover page for a Schedule 13D/G, when one exists.

    Mandatory since 2024-12-18. Absent for older filings, which 404 — that is
    expected, not an error, so failures are silent and the HTML path stands.
    """
    if not accession:
        return {}
    nodash = accession.replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{cik_path}/{nodash}/primary_doc.xml"
    req = urllib.request.Request(url, headers={"User-Agent": SEC_UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = resp.read().decode("utf-8", errors="ignore")
    except Exception:
        return {}
    time.sleep(SLEEP_SEC)
    return parse_schedule_13_xml(payload)


def _entry_from_analysis(
    ticker: str,
    form: str,
    dest: Path,
    text: str,
    *,
    source_url: str | None,
    accession: str | None,
    filing_date: str | None = None,
    xml_facts: dict | None = None,
) -> dict | None:
    form = normalize_form(form)
    issuer_name = (ticker_meta(ticker) or {}).get("company") or ""
    analysis = analyze_sec_filing(form, text, xml_facts=xml_facts, issuer_name=issuer_name)
    if not should_index_filing(analysis["filing_class"], include_passive=False):
        return None
    date_meta = resolve_sec_filing_date(dest, text, filing_date=filing_date)
    fd = date_meta.get("report_date")
    title = build_activist_title(analysis, form, ticker=ticker, report_date=fd)
    stake = (xml_facts or {}).get("stake_percent")
    extra = {}
    if stake is not None:
        extra["stake_percent"] = stake
    if (xml_facts or {}).get("reporting_person_ciks"):
        extra["reporting_person_ciks"] = xml_facts["reporting_person_ciks"]
    if (xml_facts or {}).get("cusip"):
        extra["cusip"] = xml_facts["cusip"]
    return {
        **extra,
        "firm_id": analysis["firm_id"],
        "firm_name": analysis["firm_name"],
        "side": "long",
        "report_date": fd,
        "title": title,
        "source": "sec_edgar",
        "source_url": source_url,
        "local_pdf": rel(dest) if dest.suffix.lower() == ".pdf" else None,
        "local_file": rel(dest),
        "form": form,
        "accession": accession,
        "filing_class": analysis["filing_class"],
        "filer_class": analysis.get("filer_class"),
        "include_in_feed": analysis["include_in_feed"],
        "reporting_persons": analysis.get("reporting_persons") or [],
        "filer_resolution": analysis.get("filer_resolution"),
        "status": "new",
        "tier": "context",
        "confidence": analysis["confidence"],
        **{k: v for k, v in date_meta.items() if k != "report_date"},
    }


def scan_ticker_sec(
    ticker: str,
    *,
    min_date: str = "2018-01-01",
    dry_run: bool = False,
    include_passive: bool = False,
    reindex_local: bool = False,
    fetch_xml: bool = False,
) -> list[dict]:
    if reindex_local:
        return reindex_local_sec(
            ticker, include_passive=include_passive, fetch_xml=fetch_xml
        )

    meta = ticker_meta(ticker)
    cik = meta.get("cik")
    if not cik:
        return []
    try:
        submissions = fetch_submissions(cik)
    except Exception as exc:
        append_scan_log({"source": "sec", "ticker": ticker, "status": "submissions_fail", "error": str(exc)})
        return []
    time.sleep(SLEEP_SEC)

    recent = submissions.get("filings", {}).get("recent") or {}
    forms = recent.get("form") or []
    hits: list[dict] = []
    cik_path = str(int(cik))
    campaign_active = _has_live_campaign(ticker)
    conditional_taken = 0

    for i, raw_form in enumerate(forms):
        # EDGAR reports "SCHEDULE 13D" for anything filed since the 2024-12-18
        # XML cutover; ACTIVIST_FORMS holds both spellings and normalize_form
        # collapses them so filenames and downstream classes stay stable.
        conditional = False
        if raw_form not in ACTIVIST_FORMS:
            if raw_form not in CONDITIONAL_FORMS or not campaign_active:
                continue
            if conditional_taken >= CONDITIONAL_FORM_CAP:
                continue
            conditional = True
        form = normalize_form(raw_form)
        filing_date = (recent.get("filingDate") or [""])[i]
        if filing_date < min_date:
            continue
        accession = (recent.get("accessionNumber") or [""])[i]
        primary = (recent.get("primaryDocument") or [""])[i]
        if not accession or not primary:
            continue
        url = sec_url(cik_path, accession, primary)
        ext = Path(primary).suffix or ".htm"
        # Keep the "/" — it puts amendments in an "SC-13D/" subdirectory as
        # "A_<date>...", which is the layout form_from_filing_path() reads back.
        dest_name = f"{form.replace(' ', '-')}_{filing_date.replace('-', '')}_acc{accession.replace('-', '_')}{ext}"
        dest = activist_reports_dir(ticker, "long") / dest_name
        if not dry_run:
            ok = download(url, dest)
            if not ok:
                continue
        text = read_filing_text(dest) if dest.exists() else ""
        xml_facts = (
            fetch_schedule_13_xml(cik_path, accession)
            if _is_schedule_13(form) and _has_structured_cover_page(filing_date)
            else {}
        )
        entry = _entry_from_analysis(
            ticker,
            form,
            dest,
            text,
            source_url=url,
            accession=accession,
            filing_date=filing_date,
            xml_facts=xml_facts,
        )
        if not entry:
            continue
        if not should_index_filing(entry["filing_class"], include_passive=include_passive):
            continue
        if conditional:
            conditional_taken += 1
        hits.append(entry)
        if not dry_run:
            index = load_ticker_index(ticker)
            if upsert_report(index, entry):
                save_ticker_index(ticker, index)
    return hits


def scan_portfolio_sec(
    tickers: list[str] | None = None,
    *,
    dry_run: bool = False,
    include_passive: bool = False,
    reindex_local: bool = False,
    fetch_xml: bool = False,
) -> dict:
    tickers = tickers or []
    all_hits: list[dict] = []
    skipped_passive = 0
    for ticker in tickers:
        hits = scan_ticker_sec(
            ticker,
            dry_run=dry_run,
            include_passive=include_passive,
            reindex_local=reindex_local,
            fetch_xml=fetch_xml,
        )
        for hit in hits:
            hit["ticker"] = ticker
        all_hits.extend(hits)
    return {
        "source": "sec_edgar",
        "generated_at": now_iso(),
        "ticker_count": len(tickers),
        "hit_count": len(all_hits),
        "skipped_passive_count": skipped_passive,
        "hits": all_hits,
    }
