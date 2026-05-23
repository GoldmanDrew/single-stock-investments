#!/usr/bin/env python3
"""Ingest valuation-relevant portfolio news into dashboard JSON and per-ticker indexes.

Sources:
  - Polygon bulk /v2/reference/news (US/CA holdings)
  - Google News RSS (all holdings)

Writes:
  dashboard/data/portfolio_news.json
  {TICKER}/research/news/news_index.json
  _system/data/news_seen.json
  _system/reviews/pending/news_{date}.md
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from collections import deque
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests

from portfolio_news_common import (
    FEED_MIN_CONFIDENCE,
    NEGATIVE_PATTERNS,
    POLICY_VERSION,
    POLYGON_MARKETS,
    PORTFOLIO_NEWS_PATH,
    ROOT,
    HoldingNewsConfig,
    NewsItem,
    build_holding_config,
    classify_text,
    is_refresh_eligible,
    load_holding_configs,
    match_holding,
    normalize_url,
    parse_published_iso,
    passes_feed_gate,
    score_confidence,
)

LOGGER = logging.getLogger("portfolio_news_ingest")

NEWS_SEEN_PATH = ROOT / "_system" / "data" / "news_seen.json"
REVIEWS_DIR = ROOT / "_system" / "reviews" / "pending"

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY") or os.getenv("POLYGON_IO_API_KEY") or ""
HTTP_TIMEOUT_SEC = int(os.getenv("PORTFOLIO_NEWS_HTTP_TIMEOUT_SEC", "30"))
HTTP_RETRY_TOTAL = int(os.getenv("PORTFOLIO_NEWS_HTTP_RETRY_TOTAL", "3"))
NEWS_WINDOW_DAYS = int(os.getenv("PORTFOLIO_NEWS_WINDOW_DAYS", "30"))
NEWS_PAGE_LIMIT = int(os.getenv("PORTFOLIO_NEWS_PAGE_LIMIT", "1000"))
NEWS_MAX_PAGES = int(os.getenv("PORTFOLIO_NEWS_MAX_PAGES", "15"))
POLYGON_REQS_PER_MIN = int(os.getenv("PORTFOLIO_NEWS_POLYGON_REQS_PER_MIN", "5"))
ENABLE_POLYGON = os.getenv("PORTFOLIO_NEWS_ENABLE_POLYGON", "1") not in {"0", "false", "False", ""}
ENABLE_GOOGLE = os.getenv("PORTFOLIO_NEWS_ENABLE_GOOGLE", "1") not in {"0", "false", "False", ""}
GOOGLE_MAX_PER_QUERY = int(os.getenv("PORTFOLIO_NEWS_GOOGLE_MAX_PER_QUERY", "50"))

_REQUEST_TIMESTAMPS: deque[float] = deque()


def build_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "marvin-portfolio-news/1.0 (+https://goldmandrew.github.io/single-stock-investments)",
        "Accept": "application/json, application/rss+xml, application/xml, text/xml",
    })
    return s


def _rate_limit_polygon() -> None:
    if POLYGON_REQS_PER_MIN <= 0:
        return
    now = time.monotonic()
    while _REQUEST_TIMESTAMPS and (now - _REQUEST_TIMESTAMPS[0]) >= 60.0:
        _REQUEST_TIMESTAMPS.popleft()
    if len(_REQUEST_TIMESTAMPS) < POLYGON_REQS_PER_MIN:
        return
    wait_s = max(0.05, 60.0 - (now - _REQUEST_TIMESTAMPS[0]) + 0.05)
    time.sleep(wait_s)


def _polygon_get(session: requests.Session, url: str, params: dict | None = None) -> dict | None:
    if not POLYGON_API_KEY:
        return None
    p = dict(params or {})
    p.setdefault("apiKey", POLYGON_API_KEY)
    for attempt in range(max(1, HTTP_RETRY_TOTAL + 1)):
        _rate_limit_polygon()
        try:
            resp = session.get(url, params=p, timeout=HTTP_TIMEOUT_SEC)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("polygon request failed: %s", exc)
            time.sleep(0.4 * (attempt + 1))
            continue
        _REQUEST_TIMESTAMPS.append(time.monotonic())
        if resp.status_code == 429:
            time.sleep(min(20.0, 2.0 * (attempt + 1)))
            continue
        if resp.status_code >= 400:
            LOGGER.warning("polygon GET %s -> %s", url, resp.status_code)
            return None
        try:
            return resp.json()
        except Exception:  # noqa: BLE001
            return None
    return None


def _bulk_paginate(
    session: requests.Session,
    url: str,
    params: dict,
    *,
    max_pages: int,
) -> list[dict]:
    out: list[dict] = []
    next_url: str | None = url
    next_params: dict | None = params
    for _ in range(max_pages):
        if not next_url:
            break
        payload = _polygon_get(session, next_url, next_params)
        next_params = None
        if not payload:
            break
        results = payload.get("results") or []
        out.extend(results)
        next_url = payload.get("next_url")
        if next_url and POLYGON_API_KEY and "apiKey=" not in next_url:
            sep = "&" if "?" in next_url else "?"
            next_url = f"{next_url}{sep}apiKey={POLYGON_API_KEY}"
    return out


def _polygon_universe(configs: dict[str, HoldingNewsConfig]) -> dict[str, str]:
    """Map polygon symbol -> portfolio ticker."""
    out: dict[str, str] = {}
    for ticker, cfg in configs.items():
        if cfg.market not in POLYGON_MARKETS or not cfg.polygon_ticker:
            continue
        out[_norm_poly(cfg.polygon_ticker)] = ticker
        out[_norm_poly(ticker)] = ticker
    return out


def _norm_poly(sym: str) -> str:
    return sym.strip().upper().replace(".", "-")


def phase_polygon_news(
    session: requests.Session,
    configs: dict[str, HoldingNewsConfig],
) -> list[NewsItem]:
    if not ENABLE_POLYGON or not POLYGON_API_KEY:
        LOGGER.info("polygon phase skipped (disabled or missing API key)")
        return []

    poly_map = _polygon_universe(configs)
    if not poly_map:
        return []

    since = (datetime.now(UTC) - timedelta(days=NEWS_WINDOW_DAYS)).date().isoformat()
    raw = _bulk_paginate(
        session,
        "https://api.polygon.io/v2/reference/news",
        {
            "published_utc.gte": since,
            "order": "desc",
            "limit": NEWS_PAGE_LIMIT,
            "sort": "published_utc",
        },
        max_pages=NEWS_MAX_PAGES,
    )

    items: list[NewsItem] = []
    for row in raw:
        related_poly = {_norm_poly(t) for t in (row.get("tickers") or [])}
        portfolio_tickers = sorted({poly_map[t] for t in related_poly if t in poly_map})
        if not portfolio_tickers:
            continue

        title = (row.get("title") or "").strip()
        description = (row.get("description") or "").strip()
        text = f"{title}\n{description}"
        category, base_conf = classify_text(text)
        if not category:
            continue

        neg_hits = sum(1 for p in NEGATIVE_PATTERNS if p.search(text))
        if neg_hits:
            continue

        ticker, tier = match_holding(
            text,
            row.get("article_url"),
            configs,
            polygon_tickers=portfolio_tickers,
        )
        if not ticker:
            ticker = portfolio_tickers[0]
            tier = "explicit"

        cfg = configs[ticker]
        pub = row.get("publisher") or {}
        publisher = pub.get("name") if isinstance(pub, dict) else None
        conf = score_confidence(
            base_conf,
            match_tier=tier,
            publisher=publisher,
            url=row.get("article_url"),
            neg_hits=neg_hits,
        )
        art_id = row.get("id") or row.get("article_url") or title
        item = NewsItem(
            id=f"polygon_news:{art_id}",
            tickers=[ticker],
            company=cfg.company,
            category=category,
            confidence=conf,
            match_tier=tier,
            published_utc=parse_published_iso(row.get("published_utc")),
            title=title or None,
            summary=description or None,
            url=row.get("article_url"),
            publisher=publisher,
            source="polygon",
        )
        item.refresh_eligible = is_refresh_eligible(item)
        if passes_feed_gate(item, cfg):
            items.append(item)

    LOGGER.info("polygon: raw=%d kept=%d", len(raw), len(items))
    return items


def _google_query(cfg: HoldingNewsConfig) -> str:
    names = " OR ".join(f'"{n}"' for n in cfg.search_names[:3])
    tokens = " OR ".join(
        t if t.startswith("$") else (f"${t}" if t.isalpha() and len(t) <= 5 else f'"{t}"')
        for t in cfg.ticker_tokens[:2]
    )
    return f"({names}) OR ({tokens})"


def _fetch_google_news_rss(session: requests.Session, query: str, locale: dict[str, str]) -> list[dict]:
    params = {
        "q": query,
        "hl": locale.get("hl", "en-US"),
        "gl": locale.get("gl", "US"),
        "ceid": locale.get("ceid", "US:en"),
    }
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(params)
    try:
        resp = session.get(url, timeout=HTTP_TIMEOUT_SEC)
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("google RSS failed: %s", exc)
        return []
    if resp.status_code != 200 or not resp.content:
        return []
    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError:
        return []

    items: list[dict] = []
    for node in root.iter("item"):
        def _text(tag: str) -> str:
            el = node.find(tag)
            return (el.text or "").strip() if el is not None and el.text else ""

        title = _text("title")
        link = _text("link")
        pub_date = _text("pubDate")
        description = re.sub(r"<[^>]+>", " ", _text("description"))
        description = re.sub(r"\s+", " ", description).strip()
        src_el = node.find("source")
        source = (src_el.text or "").strip() if src_el is not None and src_el.text else ""
        items.append({
            "title": title,
            "link": link,
            "pub_date": pub_date,
            "description": description,
            "source": source,
        })
        if len(items) >= GOOGLE_MAX_PER_QUERY:
            break
    return items


def _parse_rfc822(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC).isoformat()
    except (TypeError, ValueError, IndexError):
        return None


def phase_google_news(
    session: requests.Session,
    configs: dict[str, HoldingNewsConfig],
    *,
    tickers: list[str] | None = None,
) -> list[NewsItem]:
    if not ENABLE_GOOGLE:
        LOGGER.info("google phase skipped (disabled)")
        return []

    cutoff = datetime.now(UTC) - timedelta(days=NEWS_WINDOW_DAYS)
    items: list[NewsItem] = []
    selected = tickers or sorted(configs.keys())

    for ticker in selected:
        cfg = configs.get(ticker)
        if not cfg:
            continue
        query = _google_query(cfg)
        rows = _fetch_google_news_rss(session, query, cfg.google_locale)
        for row in rows:
            title = row.get("title") or ""
            description = row.get("description") or ""
            text = f"{title}\n{description}"
            category, base_conf = classify_text(text)
            if not category:
                continue

            neg_hits = sum(1 for p in NEGATIVE_PATTERNS if p.search(text))
            if neg_hits:
                continue

            matched, tier = match_holding(text, row.get("link"), configs)
            if matched != ticker:
                continue
            if not tier:
                continue

            pub_iso = _parse_rfc822(row.get("pub_date"))
            if pub_iso:
                try:
                    if datetime.fromisoformat(pub_iso) < cutoff:
                        continue
                except ValueError:
                    pass

            conf = score_confidence(
                base_conf,
                match_tier=tier,
                publisher=row.get("source"),
                url=row.get("link"),
                neg_hits=neg_hits,
            )
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower())[:60].strip("-") or "item"
            pub_day = (pub_iso or "")[:10] or "unknown"
            item = NewsItem(
                id=f"gnews:{slug}:{pub_day}:{ticker}",
                tickers=[ticker],
                company=cfg.company,
                category=category,
                confidence=conf,
                match_tier=tier,
                published_utc=pub_iso,
                title=title or None,
                summary=description or None,
                url=row.get("link"),
                publisher=row.get("source") or None,
                source="google_news",
            )
            item.refresh_eligible = is_refresh_eligible(item)
            if passes_feed_gate(item, cfg):
                items.append(item)

    LOGGER.info("google: kept=%d tickers=%d", len(items), len(selected))
    return items


def _load_filing_urls() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for ticker_dir in ROOT.iterdir():
        if not ticker_dir.is_dir() or ticker_dir.name.startswith(".") or ticker_dir.name in {"_system", "dashboard"}:
            continue
        manifest = ticker_dir / "investor-documents" / "DOWNLOAD_MANIFEST.json"
        if not manifest.exists():
            continue
        try:
            rows = json.loads(manifest.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        urls: set[str] = set()
        for row in rows:
            for key in ("url", "link", "primaryDocument", "source_url"):
                val = row.get(key)
                if val:
                    urls.add(str(val))
        if urls:
            out[ticker_dir.name] = urls
    return out


def link_filings(items: list[NewsItem], filing_urls: dict[str, set[str]]) -> None:
    for item in items:
        ticker = item.tickers[0] if item.tickers else None
        if not ticker or not item.url:
            continue
        norm = normalize_url(item.url)
        for url in filing_urls.get(ticker, ()):
            if normalize_url(url) == norm:
                rel = f"{ticker}/investor-documents/"
                item.linked_filing = rel
                break


def _load_seen() -> dict:
    if not NEWS_SEEN_PATH.exists():
        return {"ids": [], "urls": []}
    try:
        payload = json.loads(NEWS_SEEN_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"ids": [], "urls": []}
    payload.setdefault("ids", [])
    payload.setdefault("urls", [])
    return payload


def dedupe_items(items: list[NewsItem]) -> list[NewsItem]:
    best: dict[str, NewsItem] = {}
    rank = {"explicit": 3, "high": 2}
    for item in items:
        key = normalize_url(item.url) or item.id
        prev = best.get(key)
        if prev is None:
            best[key] = item
            continue
        if float(item.confidence or 0) > float(prev.confidence or 0):
            best[key] = item
            continue
        if float(item.confidence or 0) == float(prev.confidence or 0):
            if rank.get(item.match_tier or "", 0) > rank.get(prev.match_tier or "", 0):
                best[key] = item
    out = list(best.values())
    out.sort(
        key=lambda it: (
            published_dt_or_min(it),
            it.tickers[0] if it.tickers else "",
        ),
        reverse=True,
    )
    return out


def published_dt_or_min(item: NewsItem) -> datetime:
    iso = parse_published_iso(item.published_utc)
    if iso:
        return datetime.fromisoformat(iso)
    return datetime.min.replace(tzinfo=UTC)


def persist(items: list[NewsItem], configs: dict[str, HoldingNewsConfig]) -> None:
    PORTFOLIO_NEWS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "build_time": datetime.now(UTC).isoformat(),
        "window_days": NEWS_WINDOW_DAYS,
        "policy_version": POLICY_VERSION,
        "feed_min_confidence": FEED_MIN_CONFIDENCE,
        "items": [it.to_dict() for it in items],
    }
    PORTFOLIO_NEWS_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    seen = _load_seen()
    seen_ids = set(seen.get("ids") or [])
    seen_urls = set(seen.get("urls") or [])

    by_ticker: dict[str, list[dict]] = {}
    for item in items:
        ticker = item.tickers[0] if item.tickers else None
        if not ticker:
            continue
        by_ticker.setdefault(ticker, []).append(item.to_dict())
        seen_ids.add(item.id)
        if item.url:
            nu = normalize_url(item.url)
            if nu:
                seen_urls.add(nu)

    for ticker, rows in by_ticker.items():
        news_dir = ROOT / ticker / "research" / "news"
        news_dir.mkdir(parents=True, exist_ok=True)
        index_path = news_dir / "news_index.json"
        prior: list[dict] = []
        if index_path.exists():
            try:
                prior = list(json.loads(index_path.read_text(encoding="utf-8")).get("items") or [])
            except (json.JSONDecodeError, OSError):
                prior = []
        merged: dict[str, dict] = {r.get("id"): r for r in prior if r.get("id")}
        for row in rows:
            merged[row["id"]] = row
        merged_rows = sorted(
            merged.values(),
            key=lambda r: parse_published_iso(r.get("published_utc")) or "",
            reverse=True,
        )
        index_path.write_text(
            json.dumps(
                {
                    "updated": datetime.now(UTC).isoformat(),
                    "ticker": ticker,
                    "company": configs[ticker].company if ticker in configs else ticker,
                    "items": merged_rows[:200],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    NEWS_SEEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    NEWS_SEEN_PATH.write_text(
        json.dumps(
            {
                "updated": datetime.now(UTC).isoformat(),
                "ids": sorted(seen_ids)[-5000:],
                "urls": sorted(seen_urls)[-5000:],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def write_review_markdown(items: list[NewsItem]) -> Path:
    REVIEWS_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    path = REVIEWS_DIR / f"news_{today}.md"
    refresh_items = [it for it in items if it.refresh_eligible]
    lines = [
        f"# Portfolio news scan — {today}",
        "",
        f"Build: {datetime.now(UTC).isoformat()} · Window: {NEWS_WINDOW_DAYS} days · Policy v{POLICY_VERSION}",
        "",
        f"**Feed items:** {len(items)} · **Refresh-eligible:** {len(refresh_items)}",
        "",
    ]
    if not items:
        lines.extend(["No new validated headlines in this window.", ""])
    else:
        lines.extend(["## Refresh-eligible (valuation / cash flow)", ""])
        if refresh_items:
            for it in refresh_items[:25]:
                lines.append(
                    f"- **{it.tickers[0]}** · `{it.category}` · {it.confidence:.2f} · "
                    f"[{it.title}]({it.url})"
                )
        else:
            lines.append("- None")
        lines.extend(["", "## All feed items", ""])
        for it in items[:40]:
            flag = " **[refresh]**" if it.refresh_eligible else ""
            lines.append(
                f"- **{it.tickers[0]}** · `{it.category}` · {it.confidence:.2f}{flag} · "
                f"{it.publisher or 'unknown'} · [{it.title}]({it.url})"
            )
    lines.extend(["", "---", "", "[HUMAN REVIEW] Triage false positives before acting on headlines.", ""])
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Ingest portfolio news")
    parser.add_argument(
        "--tickers",
        help="Optional comma-separated subset (e.g. AMZN,SJT)",
        default="",
    )
    parser.add_argument("--skip-polygon", action="store_true")
    parser.add_argument("--skip-google", action="store_true")
    parser.add_argument("--no-review", action="store_true", help="Skip pending review markdown")
    args = parser.parse_args()

    global ENABLE_POLYGON, ENABLE_GOOGLE  # noqa: PLW0603
    if args.skip_polygon:
        ENABLE_POLYGON = False
    if args.skip_google:
        ENABLE_GOOGLE = False

    subset = [t.strip() for t in args.tickers.split(",") if t.strip()] or None
    configs = load_holding_configs()
    if subset:
        configs = {k: v for k, v in configs.items() if k in subset}

    session = build_session()
    items: list[NewsItem] = []
    items.extend(phase_polygon_news(session, configs))
    items.extend(phase_google_news(session, configs, tickers=subset or sorted(configs.keys())))

    filing_urls = _load_filing_urls()
    link_filings(items, filing_urls)
    items = dedupe_items(items)

    persist(items, configs)
    if not args.no_review:
        review_path = write_review_markdown(items)
        LOGGER.info("review: %s", review_path)

    refresh_n = sum(1 for it in items if it.refresh_eligible)
    LOGGER.info("done: items=%d refresh_eligible=%d -> %s", len(items), refresh_n, PORTFOLIO_NEWS_PATH)


if __name__ == "__main__":
    main()
