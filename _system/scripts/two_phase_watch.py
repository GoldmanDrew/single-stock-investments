#!/usr/bin/env python3
"""INV Accelsius two-phase cooling watch.

Scans named artifacts (filings, transcripts, allowlisted IR, event PDF indexes,
syndicated Google News) and writes:

  INV/research/evidence/two_phase_watch_ledger.json
  INV/research/evidence/two_phase_watch_YYYY-MM-DD.md

Rank 1-3 hits also write ``_system/reviews/pending/INV_two_phase_watch_{date}.md``.
Never edits valuation.json. Never scrapes LinkedIn HTML.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import UTC, date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
INV_DIR = ROOT / "INV"
EVIDENCE_DIR = INV_DIR / "research" / "evidence"
LEDGER_PATH = EVIDENCE_DIR / "two_phase_watch_ledger.json"
COMPETITIVE_DIR = INV_DIR / "investor-documents" / "competitive"
SEEN_URLS_PATH = COMPETITIVE_DIR / "seen_urls.json"
REVIEWS_DIR = ROOT / "_system" / "reviews" / "pending"
GITHUB_REPO = "magis-capital-partners/single-stock-investments"

WATCH_TICKERS = ("NVDA", "AMD", "VRT", "JCI", "SMCI", "DELL", "HPE", "INV")
OEM_TICKERS = {"SMCI", "DELL", "HPE"}
CHIP_TICKERS = {"NVDA", "AMD"}
MAX_FILE_BYTES = 8_000_000
MAX_FILES_PER_TICKER = 48
MAX_EVENT_PDFS = 20
HTTP_TIMEOUT = 30
USER_AGENT = "MarvinTwoPhaseWatch/1.0 (research@magis; +https://github.com/magis-capital-partners/single-stock-investments)"

LOGGER = logging.getLogger("two_phase_watch")

COOLING_RE = re.compile(
    r"two[- ]phase|pumped two[- ]phase|OMNICOOL|COOLERCHIPS|NeuCool|Accelsius|"
    r"ZutaCore|Zuta.?Core|\bW45\b|\bW50\b|direct[- ]to[- ]chip|"
    r"refrigerant.{0,40}cool",
    re.I,
)
VRT_EXTRA_RE = re.compile(r"MegaMod|\bCDU\b", re.I)
LIQUID_COOL_RE = re.compile(r"liquid\s+cool|two[- ]phase|refrigerant", re.I)
HYPERSCALER_RE = re.compile(
    r"\b(AWS|Amazon Web Services|Google Cloud|Microsoft Azure|\bAzure\b|"
    r"\bMeta\b|\bOracle\b|hyperscaler)\b",
    re.I,
)
PRODUCTION_RE = re.compile(
    r"\b(production|deployed|megawatt|\bMW\b|purchase order|\bPO\b|"
    r"contracted|factory[- ]integrated)\b",
    re.I,
)
REF_DESIGN_RE = re.compile(
    r"reference design|\bMGX\b|Instinct|thermal (?:design )?guide",
    re.I,
)
SKU_RE = re.compile(r"\bSKU\b|factory[- ]integrated|shipping|generally available|\bGA\b", re.I)
LAB_RE = re.compile(r"\bGTC\b|Inception|HyperStart|\blab\b|booth|Equinix", re.I)
PAPER_RE = re.compile(r"Heydari|Manaserh|ARPA-E|OMNICOOL|COOLERCHIPS|Hot Chips", re.I)
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")
DATE_IN_NAME = re.compile(r"(20\d{2})[-_]?([01]\d)[-_]?([0-3]\d)")
HREF_RE = re.compile(r"""href\s*=\s*['"]([^'"]+)['"]""", re.I)

VENDOR_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Accelsius", re.compile(r"Accelsius|NeuCool", re.I)),
    ("Vertiv", re.compile(r"\bVertiv\b", re.I)),
    ("Boyd", re.compile(r"\bBoyd\b", re.I)),
    ("ZutaCore", re.compile(r"Zuta.?Core", re.I)),
    ("JCI", re.compile(r"Johnson Controls|\bJCI\b", re.I)),
    ("Legrand", re.compile(r"\bLegrand\b", re.I)),
)

IR_PAGES: tuple[tuple[str, str], ...] = (
    ("accelsius-home", "https://accelsius.com/"),
    ("accelsius-news", "https://accelsius.com/news/"),
    ("innventure-news", "https://www.innventure.com/news/"),
    ("innventure-ir", "https://ir.innventure.com/"),
    ("innventure-ir-news", "https://ir.innventure.com/news-events/press-releases"),
)

EVENT_INDEXES: tuple[dict[str, str], ...] = (
    {
        "id": "arpa-e-coolerchips",
        "url": "https://arpa-e.energy.gov/technologies/programs/coolerchips",
        "source": "arpa-e",
    },
    {
        "id": "hot-chips",
        "url": "https://www.hotchips.org/",
        "source": "hot-chips",
    },
    {
        "id": "ocp-summit",
        "url": "https://www.opencompute.org/summit/global-summit",
        "source": "ocp",
    },
    {
        "id": "amd-instinct",
        "url": "https://www.amd.com/en/products/accelerators/instinct.html",
        "source": "amd-instinct",
    },
    {
        "id": "nvidia-gtc",
        "url": "https://www.nvidia.com/en-us/on-demand/",
        "source": "gtc",
    },
)

THEME_NEWS_QUERIES: tuple[tuple[str, str], ...] = (
    (
        "news",
        'Accelsius OR NeuCool OR "two-phase cooling" (NVIDIA OR Vertiv OR AMD)',
    ),
    (
        "linkedin_syndicated",
        'site:linkedin.com (Accelsius OR NeuCool OR "two-phase cooling")',
    ),
)

SEED_HITS: tuple[dict[str, Any], ...] = (
    {
        "title": "Heydari, Hot Chips 2024: Next-Generation Cooling For NVIDIA Accelerated Computing",
        "quote": "NVIDIA thermal path for two-phase / next-generation cooling of accelerated computing (Heydari).",
        "source_kind": "event_pdf",
        "source_ticker": "NVDA",
        "source_url": "https://www.hotchips.org/",
        "local_path": "",
        "rank": 6,
        "vendor_named": [],
        "falsifier": False,
        "first_seen": "2024-08-01",
    },
    {
        "title": "ARPA-E OMNICOOL: NVIDIA + Vertiv + Boyd",
        "quote": "OMNICOOL pumped two-phase plus immersion; PI Ali Heydari; partners Vertiv and Boyd. Accelsius is not on the team.",
        "source_kind": "event_pdf",
        "source_ticker": "NVDA",
        "source_url": "https://arpa-e.energy.gov/technologies/programs/coolerchips",
        "local_path": "",
        "rank": 6,
        "vendor_named": ["Vertiv", "Boyd"],
        "falsifier": False,
        "first_seen": "2026-01-01",
    },
    {
        "title": "INV board letter 19 Aug 2026: DarkNX booking removed; earnout forfeited",
        "quote": "The DarkNX booking that satisfied the Accelsius earnout was subsequently removed. Senior management and directors forfeit those earnout shares.",
        "source_kind": "filing",
        "source_ticker": "INV",
        "source_url": "https://www.innventure.com/news/innventure-board-issues-letter-to-shareholders",
        "local_path": "INV/investor-documents/sec-edgar/8-K_20260819_rpt20260819_acc0001628280_26_057840.htm",
        "rank": 1,
        "vendor_named": ["Accelsius"],
        "falsifier": True,
        "first_seen": "2026-08-19",
    },
    {
        "title": "JCI Series B lead; Accelsius NeuCool two-phase D2C",
        "quote": "Johnson Controls led Accelsius Series B; strategic channel for NeuCool two-phase direct-to-chip.",
        "source_kind": "ir",
        "source_ticker": "JCI",
        "source_url": "https://accelsius.com/",
        "local_path": "",
        "rank": 3,
        "vendor_named": ["Accelsius", "JCI"],
        "falsifier": False,
        "first_seen": "2025-01-01",
    },
)


class _HrefParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for key, val in attrs:
            if key.lower() == "href" and val:
                self.hrefs.append(val)


def today_iso() -> str:
    return date.today().isoformat()


def github_blob(rel: str) -> str:
    return f"https://github.com/{GITHUB_REPO}/blob/main/{rel.replace(chr(92), '/')}"


def hit_id(source_url: str, quote: str) -> str:
    raw = f"{(source_url or '').strip().lower()}|{(quote or '').strip().lower()[:160]}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def strip_markup(text: str) -> str:
    cleaned = TAG_RE.sub(" ", text or "")
    return WS_RE.sub(" ", cleaned).strip()


def excerpt_around(text: str, match: re.Match[str], width: int = 140) -> str:
    start = max(0, match.start() - width)
    end = min(len(text), match.end() + width)
    snippet = strip_markup(text[start:end])
    if start:
        snippet = "…" + snippet
    if end < len(text):
        snippet = snippet + "…"
    return snippet[:280]


def named_vendors(text: str) -> list[str]:
    found: list[str] = []
    for name, pat in VENDOR_PATTERNS:
        if pat.search(text) and name not in found:
            found.append(name)
    return found


def rank_hit(
    text: str,
    *,
    source_ticker: str,
    source_kind: str,
    title: str = "",
) -> tuple[int, bool, list[str]]:
    """Return (rank, falsifier, vendors). Lower rank is more material."""
    blob = f"{title}\n{text}"
    vendors = named_vendors(blob)
    accelsius = "Accelsius" in vendors
    vertiv_or_boyd = "Vertiv" in vendors or "Boyd" in vendors

    if source_ticker == "INV" and re.search(
        r"DarkNX|earnout|forfeit|going concern|\bSEPA\b", blob, re.I
    ):
        falsifier = bool(
            re.search(r"removed|forfeit|going concern|dilut|\bSEPA\b", blob, re.I)
        )
        return 1, falsifier, vendors or ["Accelsius"]

    if accelsius and HYPERSCALER_RE.search(blob) and PRODUCTION_RE.search(blob):
        return 1, False, vendors

    if source_ticker in CHIP_TICKERS and REF_DESIGN_RE.search(blob) and vendors:
        return 2, (not accelsius) and vertiv_or_boyd, vendors

    if source_ticker in OEM_TICKERS and (COOLING_RE.search(blob) or SKU_RE.search(blob)) and vendors:
        return 3, (not accelsius) and vertiv_or_boyd, vendors

    if vertiv_or_boyd and not accelsius and re.search(r"two[- ]phase|generally available|\bGA\b", blob, re.I):
        return 4, True, vendors

    if LAB_RE.search(blob):
        return 5, False, vendors

    if PAPER_RE.search(blob):
        return 6, False, vendors

    return 5, False, vendors


def date_from_name(name: str) -> str:
    m = DATE_IN_NAME.search(name.replace("\\", "/"))
    if not m:
        return ""
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
    except ValueError:
        return ""


def _tls_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    return ctx


def http_get(url: str, *, accept: str = "text/html,application/xhtml+xml,application/pdf,*/*") -> tuple[bytes, str, int]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": accept},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT, context=_tls_context()) as resp:
            body = resp.read()
            ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip()
            return body, ctype, int(getattr(resp, "status", 200) or 200)
    except urllib.error.HTTPError as exc:
        return b"", "", int(exc.code)
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("GET failed %s: %s", url, exc)
        return b"", "", 0


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def save_json(path: Path, doc: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def make_hit(
    *,
    title: str,
    quote: str,
    source_kind: str,
    source_ticker: str,
    source_url: str,
    local_path: str,
    rank: int,
    vendor_named: list[str],
    falsifier: bool,
    first_seen: str,
    last_seen: str | None = None,
) -> dict[str, Any]:
    return {
        "id": hit_id(source_url or local_path, quote),
        "first_seen": first_seen,
        "last_seen": last_seen or first_seen,
        "rank": rank,
        "source_kind": source_kind,
        "source_ticker": source_ticker,
        "title": title[:240],
        "quote": (quote or "")[:280],
        "source_url": source_url,
        "local_path": local_path,
        "vendor_named": vendor_named,
        "falsifier": bool(falsifier),
    }


def cooling_match(text: str, ticker: str) -> re.Match[str] | None:
    m = COOLING_RE.search(text)
    if m:
        return m
    if ticker == "VRT" and VRT_EXTRA_RE.search(text) and LIQUID_COOL_RE.search(text):
        return VRT_EXTRA_RE.search(text)
    return None


def candidate_files(ticker: str) -> list[Path]:
    ticker_dir = ROOT / ticker
    if not ticker_dir.is_dir():
        return []
    out: list[Path] = []
    patterns = [
        ticker_dir / "research" / "evidence" / "_text",
        ticker_dir / "investor-documents" / "transcripts",
        ticker_dir / "research" / "evidence",
        ticker_dir / "investor-documents" / "sec-edgar",
    ]
    skip_bits = ("skip", "binary", ".git")
    for folder in patterns:
        if not folder.is_dir():
            continue
        for path in folder.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".txt", ".md", ".htm", ".html"}:
                continue
            rel = path.as_posix().lower()
            if any(bit in rel for bit in skip_bits):
                continue
            name = path.name.lower()
            if folder.name == "evidence" and path.parent.name != "_text":
                if not name.startswith("management_digest"):
                    continue
            if folder.name == "sec-edgar":
                if not any(tag in name for tag in ("10-k", "10-q", "8-k", "10k", "10q", "8k")):
                    continue
            try:
                if path.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            out.append(path)
    out.sort(key=lambda p: (date_from_name(p.name) or "0000", p.stat().st_mtime), reverse=True)
    return out[:MAX_FILES_PER_TICKER]


def scan_local(today: str) -> tuple[list[dict[str, Any]], list[str]]:
    hits: list[dict[str, Any]] = []
    gaps: list[str] = []
    for ticker in WATCH_TICKERS:
        files = candidate_files(ticker)
        if not files:
            gaps.append(f"{ticker}: no local filing/transcript extracts")
            continue
        found = False
        for path in files:
            try:
                raw = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            match = cooling_match(raw, ticker)
            if not match:
                continue
            found = True
            quote = excerpt_around(raw, match)
            rel = path.relative_to(ROOT).as_posix()
            kind = "transcript" if "transcript" in rel.lower() else "filing"
            rank, falsifier, vendors = rank_hit(
                quote, source_ticker=ticker, source_kind=kind, title=path.name
            )
            hits.append(
                make_hit(
                    title=path.name,
                    quote=quote,
                    source_kind=kind,
                    source_ticker=ticker,
                    source_url=github_blob(rel),
                    local_path=rel,
                    rank=rank,
                    vendor_named=vendors,
                    falsifier=falsifier,
                    first_seen=date_from_name(path.name) or today,
                    last_seen=today,
                )
            )
        if not found:
            gaps.append(f"{ticker}: scanned {len(files)} files, no cooling keyword")
    return hits, gaps


def scan_news_index(today: str) -> list[dict[str, Any]]:
    path = INV_DIR / "research" / "news" / "news_index.json"
    doc = load_json(path, {})
    items = doc.get("items") if isinstance(doc, dict) else doc
    if not isinstance(items, list):
        return []
    hits: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "")
        summary = str(item.get("summary") or "")
        blob = f"{title}\n{summary}"
        if not cooling_match(blob, "INV"):
            continue
        publisher = str(item.get("publisher") or "")
        url = str(item.get("url") or "")
        kind = "linkedin_syndicated" if "linkedin" in (publisher + url).lower() else "news"
        rank, falsifier, vendors = rank_hit(
            blob, source_ticker="INV", source_kind=kind, title=title
        )
        if kind == "linkedin_syndicated" and rank < 5:
            # Syndicated social copy stays context unless rank 1 hyperscaler production.
            if rank > 1:
                rank = max(rank, 5)
                falsifier = False
        hits.append(
            make_hit(
                title=title or "INV news",
                quote=strip_markup(summary or title)[:280],
                source_kind=kind,
                source_ticker="INV",
                source_url=url,
                local_path="INV/research/news/news_index.json",
                rank=rank,
                vendor_named=vendors,
                falsifier=falsifier,
                first_seen=(str(item.get("published_utc") or "")[:10] or today),
                last_seen=today,
            )
        )
    return hits


def _absolute_href(base: str, href: str) -> str | None:
    href = href.strip()
    if not href or href.startswith(("#", "javascript:", "mailto:")):
        return None
    return urllib.parse.urljoin(base, href)


def _ir_downloadable(url: str) -> bool:
    low = url.lower()
    if "linkedin.com" in low:
        return False
    if low.endswith(".pdf"):
        return True
    if any(bit in low for bit in ("press-release", "news-release", "news-releases")):
        return True
    if "innventure.com/news/" in low:
        path = urllib.parse.urlparse(url).path.strip("/")
        # slug article, not the index
        return path.startswith("news/") and path.count("/") == 1 and len(path) > 8
    return False
    hits: list[dict[str, Any]] = []
    notes: list[str] = []
    dest = COMPETITIVE_DIR / "ir"
    dest.mkdir(parents=True, exist_ok=True)
    for name, url in IR_PAGES:
        body, _ctype, status = http_get(url)
        time.sleep(0.4)
        if status == 404:
            notes.append(f"IR 404: {url}")
            continue
        if status != 200 or not body:
            notes.append(f"IR miss {status}: {url}")
            continue
        html = body.decode("utf-8", errors="ignore")
        parser = _HrefParser()
        try:
            parser.feed(html)
        except Exception:  # noqa: BLE001
            parser.hrefs = HREF_RE.findall(html)
        text = strip_markup(html)
        match = cooling_match(text, "INV")
        if match:
            quote = excerpt_around(text, match)
            rank, falsifier, vendors = rank_hit(
                quote, source_ticker="INV", source_kind="ir", title=name
            )
            hits.append(
                make_hit(
                    title=f"IR page {name}",
                    quote=quote,
                    source_kind="ir",
                    source_ticker="INV",
                    source_url=url,
                    local_path="",
                    rank=rank,
                    vendor_named=vendors,
                    falsifier=falsifier,
                    first_seen=today,
                    last_seen=today,
                )
            )
        saved = 0
        for href in parser.hrefs:
            abs_url = _absolute_href(url, href)
            if not abs_url or abs_url in seen:
                continue
            low = abs_url.lower()
            if not _ir_downloadable(abs_url):
                continue
            if abs_url in seen:
                continue
            if saved >= 8:
                break
            file_body, ctype, st = http_get(abs_url)
            time.sleep(0.3)
            if st != 200 or not file_body:
                continue
            ext = ".pdf" if ("pdf" in (ctype or "").lower() or low.endswith(".pdf")) else ".htm"
            if ext == ".htm" and len(file_body) > 250_000:
                notes.append(f"IR skip oversized HTML {abs_url}")
                continue
            seen.add(abs_url)
            slug = re.sub(r"[^a-z0-9]+", "-", urllib.parse.urlparse(abs_url).path.lower())[:60].strip("-") or "ir"
            dest_path = dest / f"{today}_{slug}{ext}"
            if not dest_path.exists():
                dest_path.write_bytes(file_body)
            rel = dest_path.relative_to(ROOT).as_posix()
            inner = file_body.decode("utf-8", errors="ignore") if ext != ".pdf" else abs_url
            m2 = cooling_match(inner, "INV") if ext != ".pdf" else COOLING_RE.search(abs_url + " " + href)
            if not m2:
                continue
            quote = excerpt_around(inner, m2) if ext != ".pdf" else abs_url
            rank, falsifier, vendors = rank_hit(
                quote, source_ticker="INV", source_kind="ir", title=slug
            )
            hits.append(
                make_hit(
                    title=slug,
                    quote=quote,
                    source_kind="ir",
                    source_ticker="INV",
                    source_url=abs_url,
                    local_path=rel,
                    rank=rank,
                    vendor_named=vendors,
                    falsifier=falsifier,
                    first_seen=today,
                    last_seen=today,
                )
            )
            saved += 1
    return hits, notes


def fetch_event_indexes(today: str, seen: set[str]) -> tuple[list[dict[str, Any]], list[str]]:
    hits: list[dict[str, Any]] = []
    notes: list[str] = []
    downloaded = 0
    for spec in EVENT_INDEXES:
        url = spec["url"]
        source = spec["source"]
        dest = COMPETITIVE_DIR / "events" / source
        dest.mkdir(parents=True, exist_ok=True)
        body, _ctype, status = http_get(url)
        time.sleep(0.4)
        if status != 200 or not body:
            notes.append(f"event index miss {status}: {url}")
            continue
        html = body.decode("utf-8", errors="ignore")
        hrefs = HREF_RE.findall(html)
        for href in hrefs:
            if downloaded >= MAX_EVENT_PDFS:
                break
            abs_url = _absolute_href(url, href)
            if not abs_url or abs_url in seen:
                continue
            blob = f"{href} {abs_url}"
            if not (COOLING_RE.search(blob) or PAPER_RE.search(blob) or "pdf" in abs_url.lower()):
                continue
            if "linkedin.com" in abs_url.lower():
                continue
            if not abs_url.lower().endswith(".pdf") and "pdf" not in abs_url.lower():
                if not (COOLING_RE.search(blob) or PAPER_RE.search(blob)):
                    continue
            if not abs_url.lower().endswith(".pdf"):
                continue
            file_body, ctype, st = http_get(abs_url, accept="application/pdf,*/*")
            time.sleep(0.3)
            if st != 200 or not file_body:
                continue
            if "pdf" not in ctype.lower() and not abs_url.lower().endswith(".pdf"):
                continue
            seen.add(abs_url)
            slug = re.sub(r"[^a-z0-9]+", "-", urllib.parse.urlparse(abs_url).path.lower())[:70].strip("-") or "event"
            dest_path = dest / f"{today}_{slug}.pdf"
            if not dest_path.exists():
                dest_path.write_bytes(file_body)
            rel = dest_path.relative_to(ROOT).as_posix()
            rank, falsifier, vendors = rank_hit(
                blob, source_ticker="NVDA" if source in {"arpa-e", "gtc", "hot-chips"} else "AMD",
                source_kind="event_pdf",
                title=slug,
            )
            hits.append(
                make_hit(
                    title=slug,
                    quote=strip_markup(href)[:280] or abs_url,
                    source_kind="event_pdf",
                    source_ticker="NVDA" if source != "amd-instinct" else "AMD",
                    source_url=abs_url,
                    local_path=rel,
                    rank=rank,
                    vendor_named=vendors,
                    falsifier=falsifier,
                    first_seen=today,
                    last_seen=today,
                )
            )
            downloaded += 1
        if downloaded >= MAX_EVENT_PDFS:
            break
    notes.append(f"event PDFs downloaded this run: {downloaded} (cap {MAX_EVENT_PDFS})")
    return hits, notes


def fetch_theme_news(today: str) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for kind, query in THEME_NEWS_QUERIES:
        params = urllib.parse.urlencode(
            {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
        )
        url = "https://news.google.com/rss/search?" + params
        body, _ctype, status = http_get(url, accept="application/rss+xml,application/xml,text/xml")
        time.sleep(0.4)
        if status != 200 or not body:
            LOGGER.warning("theme news miss %s %s", kind, status)
            continue
        try:
            root = ET.fromstring(body)
        except ET.ParseError:
            continue
        for node in root.iter("item"):
            title_el = node.find("title")
            link_el = node.find("link")
            desc_el = node.find("description")
            src_el = node.find("source")
            title = (title_el.text or "").strip() if title_el is not None else ""
            link = (link_el.text or "").strip() if link_el is not None else ""
            desc = strip_markup(desc_el.text or "") if desc_el is not None else ""
            publisher = (src_el.text or "").strip() if src_el is not None else ""
            blob = f"{title}\n{desc}"
            if not cooling_match(blob, "INV"):
                continue
            source_kind = kind
            if "linkedin" in (publisher + link + kind).lower():
                source_kind = "linkedin_syndicated"
            rank, falsifier, vendors = rank_hit(
                blob, source_ticker="INV", source_kind=source_kind, title=title
            )
            if source_kind == "linkedin_syndicated" and rank > 1:
                rank = max(rank, 5)
                falsifier = False
            hits.append(
                make_hit(
                    title=title or "theme news",
                    quote=(desc or title)[:280],
                    source_kind=source_kind,
                    source_ticker="INV",
                    source_url=link,
                    local_path="",
                    rank=rank,
                    vendor_named=vendors,
                    falsifier=falsifier,
                    first_seen=today,
                    last_seen=today,
                )
            )
    return hits


def seed_hits() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in SEED_HITS:
        out.append(
            make_hit(
                title=row["title"],
                quote=row["quote"],
                source_kind=row["source_kind"],
                source_ticker=row["source_ticker"],
                source_url=row["source_url"],
                local_path=row.get("local_path") or "",
                rank=int(row["rank"]),
                vendor_named=list(row.get("vendor_named") or []),
                falsifier=bool(row.get("falsifier")),
                first_seen=str(row["first_seen"]),
                last_seen=str(row["first_seen"]),
            )
        )
    return out


def merge_hits(existing: list[dict[str, Any]], incoming: list[dict[str, Any]], today: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_id: dict[str, dict[str, Any]] = {}
    for hit in existing:
        hid = str(hit.get("id") or hit_id(hit.get("source_url") or "", hit.get("quote") or ""))
        hit = dict(hit)
        hit["id"] = hid
        by_id[hid] = hit
    new_rows: list[dict[str, Any]] = []
    for hit in incoming:
        hid = str(hit.get("id") or "")
        if hid in by_id:
            prev = by_id[hid]
            prev["last_seen"] = today
            if int(hit.get("rank") or 9) < int(prev.get("rank") or 9):
                prev["rank"] = hit["rank"]
                prev["falsifier"] = hit.get("falsifier", prev.get("falsifier"))
            if hit.get("local_path") and not prev.get("local_path"):
                prev["local_path"] = hit["local_path"]
            continue
        hit = dict(hit)
        hit["first_seen"] = hit.get("first_seen") or today
        hit["last_seen"] = today
        by_id[hid] = hit
        new_rows.append(hit)
    merged = sorted(
        by_id.values(),
        key=lambda h: (h.get("last_seen") or "", -int(h.get("rank") or 9), h.get("title") or ""),
        reverse=True,
    )
    return merged, new_rows


def ledger_status(hits: list[dict[str, Any]], new_rows: list[dict[str, Any]], as_of: str) -> str:
    try:
        as_of_d = date.fromisoformat(as_of)
        if (date.today() - as_of_d).days > 10:
            return "stale"
    except ValueError:
        pass
    if any(int(h.get("rank") or 9) <= 3 and h.get("first_seen") == as_of for h in new_rows):
        return "new_hits"
    if new_rows:
        return "new_hits"
    return "no_material_hit"


def highest_open_rank(hits: list[dict[str, Any]]) -> int | None:
    ranks = [int(h.get("rank") or 9) for h in hits]
    return min(ranks) if ranks else None


def write_note(
    ledger: dict[str, Any],
    gaps: list[str],
    notes: list[str],
    today: str,
    new_rows: list[dict[str, Any]] | None = None,
) -> Path:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_DIR / f"two_phase_watch_{today}.md"
    hits = list(ledger.get("hits") or [])
    new_today = list(new_rows) if new_rows is not None else [
        h for h in hits if h.get("first_seen") == today
    ]
    lines = [
        f"# Two-phase cooling watch — {today}",
        "",
        f"**Status:** {ledger.get('status')}",
        f"**Highest open rank:** {ledger.get('highest_open_rank')}",
        f"**Hits in ledger:** {len(hits)}",
        "",
        "Does not set stance or base IRR. Rank 5-6 stay context. Rank 1-3 go to review pending.",
        "",
        "## New this run",
        "",
    ]
    if not new_today:
        lines.append("No new hits. No material hit is a valid outcome.")
        lines.append("")
    else:
        shown = sorted(new_today, key=lambda h: int(h.get("rank") or 9))
        extra = max(0, len(shown) - 30)
        lines.append("| Rank | Ticker | Kind | Title | Vendors |")
        lines.append("|------|--------|------|-------|---------|")
        for hit in shown[:30]:
            vendors = ", ".join(hit.get("vendor_named") or []) or "—"
            flag = " (falsifier)" if hit.get("falsifier") else ""
            lines.append(
                f"| {hit.get('rank')} | {hit.get('source_ticker')} | {hit.get('source_kind')} | "
                f"{hit.get('title')}{flag} | {vendors} |"
            )
        if extra:
            lines.append("")
            lines.append(f"{extra} additional new hits are in the ledger (not listed).")
        lines.append("")
        for hit in shown[:12]:
            lines.append(f"### {hit.get('title')}")
            lines.append("")
            lines.append(f"> {hit.get('quote')}")
            lines.append("")
            if hit.get("source_url"):
                lines.append(f"Source: {hit.get('source_url')}")
            if hit.get("local_path"):
                lines.append(f"Local: `{hit.get('local_path')}`")
            lines.append("")
    if gaps:
        lines.append("## Coverage gaps")
        lines.append("")
        for gap in gaps:
            lines.append(f"- {gap}")
        lines.append("")
    if notes:
        lines.append("## Collector notes")
        lines.append("")
        for note in notes:
            lines.append(f"- {note}")
        lines.append("")
    lines.append("Spec: `INV/research/two_phase_cooling_watch.md`.")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_pending_review(new_rows: list[dict[str, Any]], today: str) -> Path | None:
    material = [h for h in new_rows if int(h.get("rank") or 9) <= 3]
    if not material:
        return None
    REVIEWS_DIR.mkdir(parents=True, exist_ok=True)
    path = REVIEWS_DIR / f"INV_two_phase_watch_{today}.md"
    lines = [
        f"# INV two-phase watch — rank 1-3 — {today}",
        "",
        "Human verdict needed. Do **not** auto-edit `INV/research/valuation.json`.",
        "",
        "| Rank | Ticker | Title | Vendors | Falsifier |",
        "|------|--------|-------|---------|-----------|",
    ]
    for hit in material:
        lines.append(
            f"| {hit.get('rank')} | {hit.get('source_ticker')} | {hit.get('title')} | "
            f"{', '.join(hit.get('vendor_named') or []) or '—'} | "
            f"{'yes' if hit.get('falsifier') else 'no'} |"
        )
    lines.extend(["", "Quotes:", ""])
    for hit in material:
        lines.append(f"- {hit.get('title')}: {hit.get('quote')}")
        if hit.get("source_url"):
            lines.append(f"  {hit.get('source_url')}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def compact_for_dashboard(ticker: str | None = "INV") -> dict[str, Any] | None:
    if ticker and ticker.upper() != "INV":
        return None
    ledger = load_json(LEDGER_PATH, None)
    if not isinstance(ledger, dict) or not ledger.get("hits"):
        return None
    as_of = str(ledger.get("as_of") or "")
    status = str(ledger.get("status") or "no_material_hit")
    try:
        if as_of and (date.today() - date.fromisoformat(as_of)).days > 10:
            status = "stale"
    except ValueError:
        pass
    hits = list(ledger.get("hits") or [])
    counts: dict[str, int] = {}
    for hit in hits:
        key = str(int(hit.get("rank") or 0))
        counts[key] = counts.get(key, 0) + 1
    compact_hits = []
    for hit in hits[:8]:
        rel = hit.get("local_path") or ""
        compact_hits.append(
            {
                "rank": hit.get("rank"),
                "date": hit.get("first_seen") or hit.get("last_seen"),
                "source_kind": hit.get("source_kind"),
                "source_ticker": hit.get("source_ticker"),
                "title": hit.get("title"),
                "quote": hit.get("quote"),
                "vendor_named": hit.get("vendor_named") or [],
                "falsifier": bool(hit.get("falsifier")),
                "source_url": hit.get("source_url"),
                "github_url": github_blob(rel) if rel else hit.get("source_url"),
            }
        )
    highest = ledger.get("highest_open_rank")
    chip = False
    try:
        if highest is not None and int(highest) <= 3 and as_of:
            chip = (date.today() - date.fromisoformat(as_of)).days <= 14
    except ValueError:
        chip = False
    return {
        "as_of": as_of,
        "status": status,
        "highest_open_rank": highest,
        "count_by_rank": counts,
        "hits": compact_hits,
        "note_path": f"INV/research/evidence/two_phase_watch_{as_of}.md" if as_of else "",
        "spec_path": "INV/research/two_phase_cooling_watch.md",
        "show_header_chip": chip,
    }


def patch_inv_shard(compact: dict[str, Any] | None) -> None:
    if not compact:
        return
    path = ROOT / "dashboard" / "data" / "tickers" / "INV.json"
    if not path.exists():
        return
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    if not isinstance(doc, dict):
        return
    doc["two_phase_watch"] = compact
    path.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def should_fetch_events(force: bool) -> bool:
    if force:
        return True
    return date.today().month in {3, 8, 10}


def run(
    *,
    fetch_ir_pages: bool,
    fetch_events: bool,
    fetch_news: bool,
    skip_local: bool,
    today: str | None = None,
) -> dict[str, Any]:
    day = today or today_iso()
    existing = load_json(LEDGER_PATH, {})
    old_hits = list(existing.get("hits") or []) if isinstance(existing, dict) else []
    seen = set(load_json(SEEN_URLS_PATH, []))
    incoming: list[dict[str, Any]] = seed_hits()
    gaps: list[str] = []
    notes: list[str] = []

    if not skip_local:
        local_hits, local_gaps = scan_local(day)
        incoming.extend(local_hits)
        gaps.extend(local_gaps)
        incoming.extend(scan_news_index(day))

    if fetch_ir_pages:
        ir_hits, ir_notes = fetch_ir(day, seen)
        incoming.extend(ir_hits)
        notes.extend(ir_notes)

    if fetch_events:
        ev_hits, ev_notes = fetch_event_indexes(day, seen)
        incoming.extend(ev_hits)
        notes.extend(ev_notes)

    if fetch_news:
        incoming.extend(fetch_theme_news(day))

    merged, new_rows = merge_hits(old_hits, incoming, day)
    status = ledger_status(merged, new_rows, day)
    ledger = {
        "schema_version": 1,
        "ticker": "INV",
        "as_of": day,
        "highest_open_rank": highest_open_rank(merged),
        "status": status,
        "coverage_gaps": gaps,
        "hits": merged,
    }
    save_json(LEDGER_PATH, ledger)
    save_json(SEEN_URLS_PATH, sorted(seen))
    note_path = write_note(ledger, gaps, notes, day, new_rows)
    review_path = write_pending_review(new_rows, day)
    compact = compact_for_dashboard("INV")
    patch_inv_shard(compact)
    LOGGER.info(
        "two_phase_watch as_of=%s status=%s hits=%d new=%d note=%s review=%s",
        day,
        status,
        len(merged),
        len(new_rows),
        note_path,
        review_path,
    )
    return ledger


def main() -> None:
    parser = argparse.ArgumentParser(description="INV two-phase cooling watch")
    parser.add_argument("--ir", action="store_true", help="Fetch Accelsius / Innventure IR allowlist")
    parser.add_argument("--events", action="store_true", help="Fetch event PDF indexes")
    parser.add_argument("--news", action="store_true", help="Fetch Google News theme queries")
    parser.add_argument("--skip-local", action="store_true", help="Skip on-disk filing/transcript scan")
    parser.add_argument("--auto-events", action="store_true", help="Fetch events in March/August/October")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    events = args.events or (args.auto_events and should_fetch_events(False))
    run(
        fetch_ir_pages=args.ir,
        fetch_events=events,
        fetch_news=args.news,
        skip_local=args.skip_local,
    )


if __name__ == "__main__":
    main()
