#!/usr/bin/env python3
"""Fetch SEC filing metadata (stake, intent, firm) when local copy is missing."""
from __future__ import annotations

import re
import time
import urllib.request
from pathlib import Path

from activist_common import ROOT, resolve_report_file
from sec_filer_parse import (
    ACTIVIST_INTENT_RE,
    UNRESOLVED_FIRM_ID,
    analyze_sec_filing,
    form_from_filing_path,
    is_sec_filing_relpath,
    normalize_form,
    parse_schedule_13_xml,
    parse_stake_percent,
    strip_html,
)

SEC_UA = "MarvinActivistScan marvin@single-stock-investments.local"
SLEEP_SEC = 0.12
CACHE_DIR = ROOT / "_system" / "data" / "activist_sec_cache"
READ_LIMIT = 400_000


def _cache_path(accession: str | None, source_url: str | None) -> Path | None:
    if accession:
        safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", accession)
        return CACHE_DIR / f"{safe}.html"
    if source_url:
        safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", source_url[-120:])
        return CACHE_DIR / f"url_{safe}.html"
    return None


def fetch_sec_text(source_url: str, *, accession: str | None = None) -> str:
    cache = _cache_path(accession, source_url)
    if cache and cache.exists() and cache.stat().st_size > 0:
        return cache.read_text(encoding="utf-8", errors="ignore")[:READ_LIMIT]
    req = urllib.request.Request(source_url, headers={"User-Agent": SEC_UA})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    text = data.decode("utf-8", errors="ignore")[:READ_LIMIT]
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(text, encoding="utf-8")
    time.sleep(SLEEP_SEC)
    return text


SCHEDULE_13_FORMS = frozenset({"SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A"})


def _fetch_schedule_13_xml(report: dict) -> dict:
    """Structured cover page for one report, or {} when absent (pre-2024 filings)."""
    accession = report.get("accession")
    source_url = report.get("source_url") or ""
    if not accession or "/edgar/data/" not in source_url:
        return {}
    cik = source_url.split("/edgar/data/", 1)[1].split("/", 1)[0]
    nodash = accession.replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{nodash}/primary_doc.xml"
    try:
        return parse_schedule_13_xml(fetch_sec_text(url, accession=f"{accession}-xml"))
    except Exception:
        return {}


def filing_form(report: dict) -> str:
    form = report.get("form") or ""
    if form:
        return form
    ref = report.get("local_file") or report.get("canonical_file") or ""
    if ref:
        inferred = form_from_filing_path(ref)
        if inferred:
            return inferred
    name = Path(str(ref or "")).name
    stem = name.split("_")[0]
    return stem.replace("-", " ") if stem else "SC 13D"


def enrich_report(report: dict, *, fetch: bool = True) -> dict:
    """Return a copy with stake_percent / intent / firm fields filled when possible."""
    out = dict(report)
    if out.get("source") != "sec_edgar" and not is_sec_filing_relpath(out.get("local_file")):
        return out

    _ref, _is_pdf, exists = resolve_report_file(out)
    text = ""
    if exists and _ref:
        try:
            text = (ROOT / _ref).read_text(encoding="utf-8", errors="ignore")[:READ_LIMIT]
        except OSError:
            text = ""
    elif fetch and out.get("source_url"):
        try:
            text = fetch_sec_text(out["source_url"], accession=out.get("accession"))
            out["enriched_from_url"] = True
        except Exception as exc:
            out["enrich_error"] = str(exc)[:200]
            return out

    if not text:
        return out

    form = filing_form(out)
    # Prefer the filer's own structured cover page when one exists (mandatory
    # for Schedules 13D/G since 2024-12-18); fall back to the HTML regexes.
    xml_facts = {}
    if fetch and normalize_form(form) in SCHEDULE_13_FORMS:
        xml_facts = _fetch_schedule_13_xml(out)
    analysis = analyze_sec_filing(form, text, xml_facts=xml_facts)
    if xml_facts.get("stake_percent") is not None:
        out["stake_percent"] = xml_facts["stake_percent"]
    if xml_facts.get("reporting_person_ciks"):
        out["reporting_person_ciks"] = xml_facts["reporting_person_ciks"]
    if analysis.get("filer_class"):
        out["filer_class"] = analysis["filer_class"]
    intent = ACTIVIST_INTENT_RE.search(strip_html(text[:120_000]))

    # Only fall back to the cover-page regex when the structured filing did not
    # already give us percent-of-class -- the XML is the filer's own number.
    if out.get("stake_percent") is None:
        stake = parse_stake_percent(text)
        if stake is not None:
            out["stake_percent"] = stake
    if intent:
        out["activist_intent"] = True
        out["intent_phrases"] = [intent.group(0).strip()]
    else:
        out.setdefault("activist_intent", False)

    if out.get("firm_id") in (None, "", UNRESOLVED_FIRM_ID) and analysis.get("firm_id") != UNRESOLVED_FIRM_ID:
        out["firm_id"] = analysis["firm_id"]
        out["firm_name"] = analysis.get("firm_name")
        out["confidence"] = analysis.get("confidence")
        out["filer_resolution"] = analysis.get("filer_resolution")
        out["reporting_persons"] = analysis.get("reporting_persons") or out.get("reporting_persons") or []

    if not out.get("filing_class"):
        out["filing_class"] = analysis.get("filing_class")
    if out.get("include_in_feed") is None:
        out["include_in_feed"] = analysis.get("include_in_feed", True)

    return out
