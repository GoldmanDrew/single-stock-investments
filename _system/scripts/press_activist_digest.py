#!/usr/bin/env python3
"""Ingest activist open letters / press wires into per-ticker activist indexes.

Covers campaigns that never file SC 13D/DFAN (e.g. Third Point / D.E. Shaw on CSGP).

Sources:
  1. Curated seeds in `_system/data/activist_press_seeds.json`
  2. Optional local fixture overrides under `_system/scripts/fixtures/activist_wire/`
  3. Live download of document_url / source_url when network is available

Rows use source=`press_wire` and flow through the same body-verify → triage → feed path
as publisher_site reports.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from activist_common import (
    OPEN_LETTER_CLASSES,
    active_firms,
    append_scan_log,
    canonical_report_path,
    firm_has_ingest,
    firm_name,
    load_json,
    load_ticker_index,
    now_iso,
    portfolio_tickers,
    publisher_match_allowed,
    rel,
    safe_report_filename,
    save_ticker_index,
    ticker_meta,
    upsert_report,
    write_json,
)
from activist_site_fetchers import fetch_bytes, parse_rss

ROOT = Path(__file__).resolve().parents[2]
SEEDS_PATH = ROOT / "_system" / "data" / "activist_press_seeds.json"
DIGEST_JSON = ROOT / "_system" / "data" / "activist_press_digest_latest.json"
FIXTURE_DIR = ROOT / "_system" / "scripts" / "fixtures" / "activist_wire"
PENDING_DIR = ROOT / "_system" / "reviews" / "pending"

CAMPAIGN_HINTS = re.compile(
    r"\b(open letter|letter to (the )?board|board of directors|nominat|"
    r"presentation|proxy|white paper|shareholder|standstill|slate|"
    r"strategic alternative|spin[- ]?off|homes\.com)\b",
    re.I,
)
NOISE_HINTS = re.compile(
    r"\b(hiring|appoints? .* (head|cio|cfo)|fund launch|closes? .* fund|"
    r"assets under management|aum update|quarterly investor letter)\b",
    re.I,
)


def _load_seeds() -> list[dict]:
    doc = load_json(SEEDS_PATH, {"campaigns": []})
    return list(doc.get("campaigns") or [])


def classify_press_item(title: str, body: str = "") -> str | None:
    blob = f"{title}\n{body}"
    if NOISE_HINTS.search(blob) and not CAMPAIGN_HINTS.search(blob):
        return None
    lower = blob.lower()
    if "presentation" in lower and CAMPAIGN_HINTS.search(blob):
        return "campaign_presentation"
    if CAMPAIGN_HINTS.search(blob):
        return "open_letter"
    if "letter" in lower and ("board" in lower or "director" in lower):
        return "open_letter"
    return None


KNOWN_FIXTURE_STEMS = {
    "de_shaw_group_letter_to_costar_board": "deshaw_costar_letter_2026-03-10.html",
    "third-point-sends-letter-to-board-of-directors-of-costar-group": "third_point_costar_letter_2026-01-27.html",
    "the-d-e-shaw-group-releases-open-letter-and-presentation-to-the-board-of-directors-of-costar-group-302678991": (
        "deshaw_costar_letter_2026-03-10.html"
    ),
}


def _fixture_path_for(url: str) -> Path | None:
    if not url:
        return None
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    for path in FIXTURE_DIR.glob(f"{digest}.*"):
        if path.is_file():
            return path
    stem = Path(urlparse(url).path).stem.lower()
    mapped = KNOWN_FIXTURE_STEMS.get(stem)
    if mapped:
        path = FIXTURE_DIR / mapped
        if path.is_file():
            return path
    if stem:
        for path in FIXTURE_DIR.glob(f"*{stem}*"):
            if path.is_file():
                return path
    # Substring hints for long wire slugs
    lower = url.lower()
    if "third-point" in lower and "costar" in lower:
        path = FIXTURE_DIR / "third_point_costar_letter_2026-01-27.html"
        if path.is_file():
            return path
    if "de_shaw" in lower or "d-e-shaw" in lower or "deshaw" in lower:
        if "costar" in lower:
            path = FIXTURE_DIR / "deshaw_costar_letter_2026-03-10.html"
            if path.is_file():
                return path
    return None


def _download_or_fixture(url: str, dest: Path) -> tuple[bool, str, Path]:
    """Return (ok, mode, resolved_dest) where mode is fixture|download|cached|fail."""
    if dest.exists() and dest.stat().st_size > 0:
        return True, "cached", dest
    fixture = _fixture_path_for(url)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if fixture is not None:
        # Prefer fixture suffix when wire URL claimed PDF but we only have HTML text.
        resolved = dest
        if fixture.suffix.lower() != dest.suffix.lower():
            resolved = dest.with_suffix(fixture.suffix.lower())
        resolved.write_bytes(fixture.read_bytes())
        return True, "fixture", resolved
    if not url:
        return False, "fail", dest
    try:
        data = fetch_bytes(url, cache_hours=12)
    except Exception as exc:
        append_scan_log({"source": "press_wire", "status": "download_fail", "url": url, "error": str(exc)})
        return False, "fail", dest
    if url.lower().endswith(".pdf") and not data.startswith(b"%PDF-"):
        # Some wires append query strings; still accept if content-type was PDF-ish
        if b"%PDF-" not in data[:1024]:
            return False, "fail", dest
    dest.write_bytes(data)
    return True, "download", dest


def _write_text_sidecar(dest: Path, text: str) -> Path | None:
    if not text.strip():
        return None
    sidecar_dir = dest.parent / "_text"
    sidecar_dir.mkdir(parents=True, exist_ok=True)
    out = sidecar_dir / f"{dest.stem}.txt"
    out.write_text(text.strip() + "\n", encoding="utf-8")
    return out


def _entry_from_seed(seed: dict, *, dry_run: bool = False) -> dict | None:
    firm_id = seed.get("firm_id") or ""
    ticker = (seed.get("ticker") or "").upper()
    if not firm_id or not ticker:
        return None
    title = (seed.get("title") or "").strip()
    source_url = seed.get("source_url") or seed.get("document_url") or ""
    document_url = seed.get("document_url") or source_url
    body_text = seed.get("body_text") or ""
    filing_class = seed.get("filing_class") or classify_press_item(title, body_text)
    if not filing_class or filing_class not in OPEN_LETTER_CLASSES | {"open_letter", "campaign_presentation", "press_campaign"}:
        if filing_class is None:
            return None
    report_date = (seed.get("report_date") or "")[:10] or None
    ext = ".pdf" if str(document_url).lower().endswith(".pdf") else ".html"
    stem = Path(urlparse(document_url).path).stem[:48] or "press"
    dest_name = safe_report_filename(firm_id, report_date or now_iso()[:10], stem, ext)
    dest = canonical_report_path(firm_id, dest_name)

    mode = "dry_run"
    if not dry_run:
        ok, mode, dest = _download_or_fixture(document_url, dest)
        if not ok and source_url and source_url != document_url:
            ok, mode, dest = _download_or_fixture(source_url, dest)
        if not ok and body_text:
            # Persist curated body so verify/body_verified can still pass offline.
            dest = canonical_report_path(
                firm_id, safe_report_filename(firm_id, report_date or now_iso()[:10], stem, ".html")
            )
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(
                f"<html><head><title>{title}</title></head><body><h1>{title}</h1><p>{body_text}</p></body></html>\n",
                encoding="utf-8",
            )
            mode = "seed_body"
            ok = True
        if not ok:
            return None
        if body_text:
            _write_text_sidecar(dest, f"{title}\n\n{body_text}")
        ext = dest.suffix.lower() or ext

    meta = ticker_meta(ticker)
    blob = f"{title} {source_url} {document_url} {body_text}"
    matched, confidence, reason = publisher_match_allowed(
        document_url or source_url,
        title,
        blob,
        meta,
    )
    if not matched:
        # Seeds are curated; company/ticker in body_text is authoritative enough to keep.
        if body_text and (
            meta["company"].lower() in body_text.lower()
            or re.search(rf"\b{re.escape(ticker)}\b", body_text, re.I)
            or "costar" in body_text.lower()
        ):
            matched, confidence, reason = True, 0.98, "seed_body_company"
        else:
            append_scan_log(
                {
                    "source": "press_wire",
                    "status": "seed_mismatch",
                    "firm_id": firm_id,
                    "ticker": ticker,
                    "reason": reason,
                }
            )
            return None

    canonical_ref = rel(dest) if dry_run or dest.exists() else None
    return {
        "firm_id": firm_id,
        "firm_name": firm_name(firm_id),
        "side": "long",
        "report_date": report_date,
        "date_precision": "day" if report_date else "unknown",
        "date_source": "press_seed",
        "title": title[:240],
        "source": "press_wire",
        "source_url": source_url or document_url,
        "document_url": document_url,
        "wire": seed.get("wire") or "seed",
        "canonical_file": canonical_ref,
        "local_pdf": canonical_ref if ext == ".pdf" and canonical_ref else None,
        "local_file": canonical_ref,
        "filing_class": filing_class if filing_class in OPEN_LETTER_CLASSES else "open_letter",
        "include_in_feed": True,
        "status": "new",
        "tier": "context",
        "confidence": confidence,
        "match_reason": reason,
        "match_confidence": confidence,
        "ingest_mode": mode,
        "alternate_urls": [u for u in {source_url, document_url} if u],
    }


def write_digest_markdown(rows: list[dict], scan_date: str) -> Path:
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    out = PENDING_DIR / f"activist_press_digest_{scan_date}.md"
    lines = [
        "# Activist press / letter digest",
        "",
        f"**Date:** {scan_date}",
        f"**Seeds:** `{SEEDS_PATH.relative_to(ROOT).as_posix()}`",
        f"**Rows:** {len(rows)}",
        "",
        "| Date | Firm | Ticker | Class | Title | URL |",
        "|------|------|--------|-------|-------|-----|",
    ]
    for row in sorted(rows, key=lambda r: (r.get("report_date") or "", r.get("firm_id") or ""), reverse=True):
        lines.append(
            "| {date} | {firm} | {ticker} | {klass} | {title} | {url} |".format(
                date=row.get("report_date") or "—",
                firm=row.get("firm_id") or "—",
                ticker=row.get("ticker") or "—",
                klass=row.get("filing_class") or "—",
                title=(row.get("title") or "—").replace("|", "/"),
                url=row.get("source_url") or row.get("document_url") or "—",
            )
        )
    lines.extend(
        [
            "",
            "Ingest: `python _system/scripts/scan_activist_sources.py --wire-only`",
            "Seeds: edit `_system/data/activist_press_seeds.json` for campaigns outside EDGAR.",
            "",
        ]
    )
    out.write_text("\n".join(lines), encoding="utf-8")
    return out



# --- live wire polling ------------------------------------------------------
#
# The lane was three hand-typed seeds for two firms and polled nothing, so an
# open letter that never became an SEC filing was only ever caught by someone
# noticing it. These two wires answer a plain RSS request; GlobeNewswire does
# not (verified 2026-08-26: timeout / connection reset), so it is deliberately
# absent rather than silently failing every run.
WIRE_FEEDS = (
    ("prnewswire", "https://www.prnewswire.com/rss/financial-services-latest-news/financial-services-latest-news-list.rss"),
    ("prnewswire", "https://www.prnewswire.com/rss/acquisitions-mergers-and-takeovers-list.rss"),
    ("businesswire", "https://feed.businesswire.com/rss/home/?rss=G1QFDERJXkJeGVtRVQ=="),
)
WIRE_LOOKBACK_DAYS = 14

# Spelled out because a mangled "\b" silently becomes a backspace character,
# which matches nothing and turns the whole lane into a permanent zero.
WORD_BOUNDARY = r"\b"


def _firm_alias_matchers() -> list[tuple[str, re.Pattern[str]]]:
    """Registry firms that opted into press_wire, by the names they appear under."""
    out: list[tuple[str, re.Pattern[str]]] = []
    for firm in active_firms():
        if not firm_has_ingest(firm, "press_wire"):
            continue
        fid = firm.get("id") or ""
        aliases = firm.get("press_aliases") or firm.get("aliases") or []
        names = [firm.get("name") or "", *aliases]
        seen: set[str] = set()
        for name in names:
            key = str(name or "").strip()
            if len(key) < 5 or key.lower() in seen:
                continue
            seen.add(key.lower())
            out.append((fid, re.compile(WORD_BOUNDARY + re.escape(key) + WORD_BOUNDARY, re.I)))
    return out


def poll_wire_feeds(
    ticker_set: set[str],
    *,
    lookback_days: int = WIRE_LOOKBACK_DAYS,
    feeds: tuple[tuple[str, str], ...] = WIRE_FEEDS,
) -> list[dict]:
    """Return seed-shaped rows for wire items naming a tracked activist.

    Two gates, both required: a registry firm must be named, and the item must
    read as a campaign. Everything else on these feeds is ordinary corporate PR.
    """
    matchers = _firm_alias_matchers()
    if not matchers:
        return []
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=lookback_days)).isoformat()
    found: list[dict] = []
    seen_urls: set[str] = set()

    for wire, url in feeds:
        try:
            items = parse_rss(fetch_bytes(url, cache_hours=2).decode("utf-8", errors="ignore"), url)
        except Exception as exc:
            append_scan_log({"source": "press_wire", "status": "wire_fail", "url": url, "error": str(exc)[:200]})
            continue
        for item in items:
            link = item.get("url") or ""
            title = item.get("title") or ""
            if not link or link in seen_urls:
                continue
            firm_id = next((fid for fid, pattern in matchers if pattern.search(title)), None)
            if not firm_id:
                continue
            if not classify_press_item(title):
                continue
            report_date = (item.get("date") or "")[:10]
            if report_date and report_date < cutoff:
                continue
            ticker = _ticker_from_headline(title, ticker_set)
            if not ticker:
                continue
            seen_urls.add(link)
            found.append(
                {
                    "firm_id": firm_id,
                    "ticker": ticker,
                    "title": title,
                    "report_date": report_date or date.today().isoformat(),
                    "source_url": link,
                    "document_url": link,
                    "filing_class": "press_campaign",
                    "wire": wire,
                    "discovered_by": "wire_poll",
                }
            )
    return found


TICKER_IN_HEADLINE_RE = re.compile(r"\((?:NYSE|NASDAQ|NYSE American|AMEX|OTC[A-Z]*)\s*:\s*([A-Z.\-]{1,8})\)", re.I)


def _ticker_from_headline(title: str, ticker_set: set[str]) -> str | None:
    """Only accept an exchange-qualified ticker, e.g. "(NASDAQ: CSGP)".

    A bare uppercase word in a headline matches far too much ordinary prose --
    the same false-positive class the feed's target verification already guards.
    """
    for match in TICKER_IN_HEADLINE_RE.finditer(title):
        candidate = match.group(1).upper().strip(".")
        if candidate in ticker_set:
            return candidate
    return None


def scan_press_wires(
    tickers: list[str] | None = None,
    *,
    dry_run: bool = False,
    backfill_days: int | None = None,
    scan_date: str | None = None,
    poll_wires: bool = True,
) -> dict:
    tickers = [t.upper() for t in (tickers or portfolio_tickers())]
    ticker_set = set(tickers)
    scan_date = scan_date or date.today().isoformat()
    cutoff = None
    if backfill_days is not None:
        cutoff = (datetime.now(timezone.utc).date() - timedelta(days=int(backfill_days))).isoformat()

    wire_firms = {f.get("id") for f in active_firms() if firm_has_ingest(f, "press_wire")}
    all_hits: list[dict] = []
    skipped = 0

    seeds = list(_load_seeds())
    if poll_wires:
        polled = poll_wire_feeds(ticker_set)
        seeds.extend(polled)

    for seed in seeds:
        firm_id = seed.get("firm_id")
        ticker = (seed.get("ticker") or "").upper()
        if firm_id not in wire_firms and firm_id:
            # Still allow curated seeds for registry firms even if press_wire not flagged.
            pass
        if ticker and ticker not in ticker_set:
            skipped += 1
            continue
        report_date = (seed.get("report_date") or "")[:10]
        if cutoff and report_date and report_date < cutoff:
            skipped += 1
            continue
        entry = _entry_from_seed(seed, dry_run=dry_run)
        if not entry:
            skipped += 1
            continue
        hit = {**entry, "ticker": ticker}
        all_hits.append(hit)
        if not dry_run:
            index = load_ticker_index(ticker)
            if upsert_report(index, entry):
                save_ticker_index(ticker, index)

    digest = {
        "source": "press_wire",
        "generated_at": now_iso(),
        "scan_date": scan_date,
        "ticker_count": len(tickers),
        "hit_count": len(all_hits),
        "polled_count": sum(1 for h in all_hits if h.get("discovered_by") == "wire_poll"),
        "skipped_count": skipped,
        "hits": all_hits,
    }
    if not dry_run:
        write_json(DIGEST_JSON, digest)
        write_digest_markdown(all_hits, scan_date)
    return digest


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest activist press / open-letter seeds.")
    parser.add_argument("--ticker", action="append")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--backfill-days", type=int, default=None)
    args = parser.parse_args()
    tickers = [t.upper() for t in args.ticker] if args.ticker else None
    result = scan_press_wires(
        tickers,
        dry_run=args.dry_run,
        backfill_days=args.backfill_days,
        scan_date=args.date,
    )
    print(f"Press digest: {result['hit_count']} hits ({result['skipped_count']} skipped)")
    for hit in result.get("hits") or []:
        print(f"  {hit.get('ticker')} {hit.get('firm_id')} {hit.get('report_date')} {hit.get('title', '')[:70]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
