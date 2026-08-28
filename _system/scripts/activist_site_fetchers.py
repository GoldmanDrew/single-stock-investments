"""Per-firm site/RSS fetchers for activist publisher reports."""
from __future__ import annotations

import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

from activist_common import append_scan_log

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 MarvinActivistScan/1.0"
SLEEP_SEC = 1.0
CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "activist_site_cache"


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.links.append((href, ""))

    def handle_data(self, data: str) -> None:
        if self.links:
            href, text = self.links[-1]
            self.links[-1] = (href, text + data)


def fetch_bytes(url: str, *, cache_hours: int = 6) -> bytes:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_key = re.sub(r"[^a-zA-Z0-9._-]+", "_", urlparse(url).netloc + urlparse(url).path)[:120]
    cache_path = CACHE_DIR / f"{cache_key}.bin"
    if cache_path.exists() and (time.time() - cache_path.stat().st_mtime) < cache_hours * 3600:
        return cache_path.read_bytes()
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    cache_path.write_bytes(data)
    time.sleep(SLEEP_SEC)
    return data


def fetch_text(url: str) -> str:
    return fetch_bytes(url).decode("utf-8", errors="ignore")


def parse_rss(xml_text: str, base_url: str) -> list[dict]:
    out: list[dict] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return out
    channel = root.find("channel")
    items = root.findall(".//item") if channel is None else channel.findall("item")
    for item in items:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or item.findtext("{http://purl.org/dc/elements/1.1/}date") or "")[:16]
        if not link:
            continue
        out.append({"url": urljoin(base_url, link), "title": title or link, "published": pub})
    return out


def parse_html_links(base_url: str, html: str) -> list[dict]:
    parser = LinkParser()
    parser.feed(html)
    out: list[dict] = []
    seen: set[str] = set()
    for href, text in parser.links:
        full = urljoin(base_url, href)
        if full in seen:
            continue
        seen.add(full)
        title = re.sub(r"\s+", " ", text).strip()
        if not title:
            title = Path(urlparse(full).path).name.replace("-", " ")
        out.append({"url": full, "title": title, "published": ""})
    return out


NAV_CHROME = frozenset(
    {
        "who-we-are", "what-we-do", "overview", "biographies", "biography", "leadership",
        "strategy", "values", "offices", "office", "terms-of-use", "terms", "disclaimer",
        "legal", "legal-disclaimer", "giving-back", "team", "people", "founder",
        "core-principles", "our-firm", "firm", "approach", "philosophy", "history",
        "search", "home", "index", "sitemap", "accessibility", "diversity", "esg",
        "responsible-investment", "investment-strategy", "investor-relations",
        "media-enquiries", "press-enquiries", "disclosures", "regulatory",
    }
)
# Parked / expired firm domains that still answer 200 with a sales page.
PARKED_HOSTS = ("hugedomains.com", "sedoparking.com", "afternic.com", "dan.com")
REPORT_KEYWORDS = (
    "report",
    "research",
    "short",
    "investigation",
    "analysis",
    "letter",
    "open-letter",
    "open letter",
    "presentation",
    "nomination",
    "proxy",
    "white-paper",
    "white paper",
    "campaign",
    "statement",
)


def likely_report(url: str, title: str, domain: str) -> bool:
    lower = f"{url} {title}".lower()
    if any(
        x in lower
        for x in (
            "privacy",
            "contact",
            "about",
            "subscribe",
            "login",
            "cart",
            "twitter.com",
            "linkedin.com",
            "careers",
            "cookie",
        )
    ):
        return False
    host = urlparse(url).netloc.lower()
    if any(parked in host for parked in PARKED_HOSTS):
        return False
    if url.lower().endswith(".pdf"):
        return True
    if domain and domain not in host and not host.endswith(domain):
        return False
    path = urlparse(url).path.strip("/")
    if not path or path in {"feed", "comments", "wp-json"}:
        return False
    # Reject site furniture by slug. Every segment is checked so
    # "/who-we-are/leadership" is rejected on either half.
    segments = [seg for seg in path.split("/") if seg]
    if any(seg in NAV_CHROME for seg in segments):
        return False
    if any(x in lower for x in REPORT_KEYWORDS):
        return True
    # A date in the path is the other reliable marker of a dated publication.
    if re.search(r"/20\d{2}[/-]", url):
        return True
    # Deliberately no generic "any short path" fallback. It matched essentially
    # every navigation link on a firm's homepage, so the crawler reported
    # hundreds of "reports" that were really nav chrome — the publisher lane
    # looked productive while yielding nothing usable.
    return False


def fetch_long_newsroom(firm: dict) -> list[dict]:
    """Crawl configured newsroom paths / RSS for long activist firms."""
    domains = [d for d in (firm.get("domains") or []) if d]
    if not domains:
        return []
    paths = firm.get("newsroom_paths") or ["/news/", "/media/", "/"]
    rss_urls = list(firm.get("rss_urls") or [])
    out: list[dict] = []
    seen: set[str] = set()

    for rss in rss_urls:
        try:
            items = parse_rss(fetch_text(rss), rss)
            for item in items:
                if item["url"] in seen:
                    continue
                domain = urlparse(item["url"]).netloc.lower()
                if any(likely_report(item["url"], item["title"], d) for d in domains) or any(
                    d in domain for d in domains
                ):
                    if likely_report(item["url"], item["title"], domains[0]):
                        seen.add(item["url"])
                        out.append(item)
        except Exception as exc:
            append_scan_log({"firm_id": firm.get("id"), "status": "rss_fail", "url": rss, "error": str(exc)})

    for domain in domains:
        for feed_path in ("/feed/", "/feed/rss/", "/?feed=rss2"):
            try:
                base = f"https://{domain}"
                items = parse_rss(fetch_text(base + feed_path), base)
                for item in items:
                    if item["url"] in seen:
                        continue
                    if likely_report(item["url"], item["title"], domain):
                        seen.add(item["url"])
                        out.append(item)
                if out:
                    break
            except Exception:
                continue
        domain_reachable = False
        for path in paths:
            try:
                page = f"https://{domain}{path}"
                links = parse_html_links(page, fetch_text(page))
                domain_reachable = True
                for item in links:
                    if item["url"] in seen:
                        continue
                    if likely_report(item["url"], item["title"], domain):
                        seen.add(item["url"])
                        out.append(item)
            except Exception as exc:
                append_scan_log(
                    {"firm_id": firm.get("id"), "status": "newsroom_fail", "url": f"https://{domain}{path}", "error": str(exc)}
                )
        # Do not stop at the first domain that yielded anything. Icahn lists
        # ielp.com before carlicahn.com; ielp.com answers but carries no
        # reports, and breaking there meant the domain that actually publishes
        # the open letters was never fetched.
        if domain_reachable and len(out) >= 5:
            break
    return out


def fetch_hindenburg(_firm: dict) -> list[dict]:
    base = "https://hindenburgresearch.com/"
    try:
        rss = fetch_text(base + "feed/")
        items = parse_rss(rss, base)
        return [i for i in items if likely_report(i["url"], i["title"], "hindenburgresearch.com")]
    except Exception as exc:
        append_scan_log({"firm_id": "hindenburg", "status": "rss_fail", "error": str(exc)})
        return []


def fetch_wordpress_rss(firm: dict) -> list[dict]:
    domain = (firm.get("domains") or [""])[0]
    if not domain:
        return []
    base = f"https://{domain}/"
    for feed_path in ("/feed/", "/feed/rss/", "/?feed=rss2"):
        try:
            rss = fetch_text(base.rstrip("/") + feed_path)
            items = parse_rss(rss, base)
            hits = [i for i in items if likely_report(i["url"], i["title"], domain)]
            if hits:
                return hits
        except Exception:
            continue
    try:
        html = fetch_text(base)
        links = [i for i in parse_html_links(base, html) if likely_report(i["url"], i["title"], domain)]
        return links
    except Exception as exc:
        append_scan_log({"firm_id": firm.get("id"), "status": "site_fail", "error": str(exc)})
        return []


def fetch_kerrisdale(firm: dict) -> list[dict]:
    domain = (firm.get("domains") or ["kerrisdalecap.com"])[0]
    for path in ("/", "/research/", "/reports/"):
        try:
            html = fetch_text(f"https://{domain}{path}")
            links = parse_html_links(f"https://{domain}{path}", html)
            hits = [i for i in links if likely_report(i["url"], i["title"], domain)]
            if hits:
                return hits
        except Exception:
            continue
    return fetch_wordpress_rss(firm)


def fetch_spruce_point(firm: dict) -> list[dict]:
    domain = (firm.get("domains") or ["sprucepointcap.com"])[0]
    for path in ("/research/", "/reports/", "/"):
        try:
            html = fetch_text(f"https://{domain}{path}")
            links = parse_html_links(f"https://{domain}{path}", html)
            hits = [i for i in links if likely_report(i["url"], i["title"], domain) or i["url"].lower().endswith(".pdf")]
            if hits:
                return hits
        except Exception:
            continue
    return []


FIRM_FETCHERS = {
    "hindenburg": fetch_hindenburg,
    "muddy_waters": fetch_wordpress_rss,
    "grizzly": fetch_wordpress_rss,
    "wolfpack": fetch_wordpress_rss,
    "viceroy": fetch_wordpress_rss,
    "iceberg": fetch_wordpress_rss,
    "culper": fetch_wordpress_rss,
    "blue_orca": fetch_wordpress_rss,
    "kerrisdale": fetch_kerrisdale,
    "spruce_point": fetch_spruce_point,
    "j_capital": fetch_wordpress_rss,
    "long_newsroom": fetch_long_newsroom,
}


def fetch_firm_reports(firm: dict) -> list[dict]:
    parser = firm.get("site_parser") or firm.get("id")
    if parser in FIRM_FETCHERS:
        fn = FIRM_FETCHERS[parser]
    elif firm.get("side") in ("long", "both") or firm.get("newsroom_paths") or firm.get("rss_urls"):
        fn = fetch_long_newsroom
    else:
        fn = fetch_wordpress_rss
    try:
        return fn(firm)
    except Exception as exc:
        append_scan_log({"firm_id": firm.get("id"), "status": "fetcher_fail", "error": str(exc)})
        return []
