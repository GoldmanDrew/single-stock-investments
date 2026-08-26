"""Shared utilities for activist report ingestion and indexing."""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "_system" / "frameworks" / "activist_firm_registry.json"
PORTFOLIO_REGISTRY = ROOT / "_system" / "portfolio" / "registry.json"
US_TICKER_CONFIG = Path(__file__).resolve().parent / "us_ticker_config.json"
GLOBAL_SCAN_PATH = ROOT / "_system" / "data" / "activist_scan_latest.json"
SCAN_LOG_PATH = ROOT / "_system" / "data" / "activist_scan_log.json"
# EDGAR renamed the beneficial-ownership submission types when Schedules 13D/G
# moved to structured XML on 2024-12-18: data.sec.gov now reports "SCHEDULE 13D"
# where it used to report "SC 13D". Both spellings must pass the form filter —
# the filter runs on the raw EDGAR label, before normalization — and
# sec_filer_parse.normalize_form() collapses them to the canonical left-hand
# name for everything downstream.
FORM_ALIASES = {
    "SCHEDULE 13D": "SC 13D",
    "SCHEDULE 13D/A": "SC 13D/A",
    "SCHEDULE 13G": "SC 13G",
    "SCHEDULE 13G/A": "SC 13G/A",
    "SCHEDULE13D": "SC 13D",
    "SCHEDULE13G": "SC 13G",
}

ACTIVIST_FORMS = frozenset(
    {
        # Beneficial ownership (both the legacy and post-2024 EDGAR spellings)
        "SC 13D",
        "SC 13D/A",
        "SC 13G",
        "SC 13G/A",
        *FORM_ALIASES,
        # Contested proxy solicitations (management-side numbering)
        "DEFC14A",
        "PREC14A",
        "DFAN14A",
        # Non-management proxy statements — the dissident's own solicitation.
        # DEFC/PREC only cover contests the registrant files under; a dissident
        # running its own slate files DEFN14A/PREN14A and was invisible before.
        "DEFN14A",
        "PREN14A",
        # Notice of exempt solicitation (Rule 14a-6(g)) — the low-cost lever
        # activists and shareholder proponents use instead of a full contest.
        "PX14A6G",
        # The company's answer. Without it a campaign reads as a one-sided claim.
        "DEFA14A",
    }
)

# Publisher / wire rows share the same body-verification + false-positive gates.
PUBLISHER_SOURCES = frozenset({"publisher_site", "local", "press_wire"})
OPEN_LETTER_CLASSES = frozenset(
    {"open_letter", "campaign_presentation", "press_campaign", "publisher_report"}
)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def load_json(path: Path, default=None):
    if not path.exists():
        return default if default is not None else {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default if default is not None else {}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_firm_registry() -> dict:
    return load_json(REGISTRY_PATH, {"firms": []})


def active_firms(*, side: str | None = None) -> list[dict]:
    firms = load_firm_registry().get("firms") or []
    out = [f for f in firms if f.get("active", True)]
    if side:
        out = [f for f in out if f.get("side") in (side, "both")]
    return out


def firm_ingest_methods(firm: dict | None) -> list[str]:
    """Return normalized ingest methods; supports legacy ingest_method string."""
    if not firm:
        return []
    methods = firm.get("ingest_methods")
    if isinstance(methods, list) and methods:
        return [str(m).strip() for m in methods if str(m).strip()]
    legacy = firm.get("ingest_method")
    if legacy:
        return [str(legacy).strip()]
    return []


def firm_has_ingest(firm: dict | None, method: str) -> bool:
    return method in firm_ingest_methods(firm)


def firms_for_ingest(method: str, *, side: str | None = None) -> list[dict]:
    out = [f for f in active_firms(side=side) if firm_has_ingest(f, method)]
    return out


def _boundary_pattern(term: str) -> re.Pattern[str]:
    """Compile a firm term so it only matches on word boundaries.

    Without \\b an alias like "amber" matches inside "chamber" and "tci" inside
    unrelated prose. Only anchor the side that starts/ends alphanumeric, so a
    term such as "3d investment partners" or "l.p." still matches.
    """
    body = re.escape(term)
    left = r"\b" if term[:1].isalnum() else ""
    right = r"\b" if term[-1:].isalnum() else ""
    return re.compile(f"{left}{body}{right}", re.I)


@lru_cache(maxsize=1)
def _firm_matchers_cached(registry_stamp: tuple) -> tuple[tuple[str, re.Pattern[str]], ...]:
    matchers: list[tuple[str, str]] = []
    for firm in load_firm_registry().get("firms") or []:
        fid = firm.get("id") or ""
        terms = [firm.get("name", "")]
        terms.extend(firm.get("aliases") or [])
        terms.extend(firm.get("sec_filer_patterns") or [])
        seen: set[str] = set()
        for term in terms:
            key = str(term or "").strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            matchers.append((fid, key))
    # Longest term first: a filing naming both "Engine Capital Management" and a
    # shorter generic alias should resolve to the most specific firm, not to
    # whichever happens to sit earlier in the registry file.
    matchers.sort(key=lambda pair: (-len(pair[1]), pair[0]))
    return tuple((fid, _boundary_pattern(key)) for fid, key in matchers)


def _registry_stamp() -> tuple:
    try:
        stat = REGISTRY_PATH.stat()
    except OSError:
        return (0, 0)
    return (stat.st_mtime_ns, stat.st_size)


def firm_matchers() -> list[tuple[str, re.Pattern[str]]]:
    return list(_firm_matchers_cached(_registry_stamp()))


def match_firm_id(text: str) -> str | None:
    if not text:
        return None
    for fid, pattern in _firm_matchers_cached(_registry_stamp()):
        if pattern.search(text):
            return fid
    return None


def portfolio_tickers() -> list[str]:
    reg = load_json(PORTFOLIO_REGISTRY, {})
    holdings = reg.get("holdings") or {}
    if holdings:
        return sorted(holdings.keys())
    tickers = []
    skip = {"_system", "dashboard", ".git", ".github", ".cursor", "_external"}
    for p in ROOT.iterdir():
        if p.is_dir() and p.name not in skip and not p.name.startswith((".", "_")):
            tickers.append(p.name)
    return sorted(tickers)


GENERIC_COMPANY_TOKENS = frozenset(
    {
        "digital",
        "group",
        "holdings",
        "capital",
        "partners",
        "management",
        "investments",
        "inc",
        "corp",
        "corporation",
        "company",
        "companies",
        "international",
        "global",
        "services",
        "technologies",
        "technology",
        "resources",
        "energy",
        "financial",
        "trust",
        "fund",
        "limited",
        "ltd",
        "plc",
        "the",
        "and",
        # Industry words shared across many issuers — matching on these alone
        # produced false positives (e.g. Charter *Communications* <- Zoom
        # *Communications*, Dorchester *Minerals* <- Nova *Minerals*).
        "communications",
        "minerals",
        "mining",
        "metals",
        "uranium",
        "networks",
        "systems",
        "sciences",
        "pharmaceuticals",
        "pharma",
        "therapeutics",
        "semiconductor",
        "industries",
        "industrial",
        "materials",
        "properties",
        "realty",
        "royalty",
        "royalties",
        "petroleum",
        "exploration",
        "enterprises",
        "solutions",
        "brands",
        "labs",
        "media",
        "markets",
        "exchange",
        "bancorp",
        "bank",
        "insurance",
        "power",
        "electric",
        "motors",
        "airlines",
        "foods",
        "software",
        "platforms",
    }
)

LEGAL_ENTITY_SUFFIX_TOKENS = frozenset(
    {
        "co",
        "company",
        "corp",
        "corporation",
        "inc",
        "incorporated",
        "limited",
        "llc",
        "lp",
        "ltd",
        "plc",
    }
)


def _normalized_words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def _matches_company_phrase(text: str, company: str) -> bool:
    """Match a normalized full/core issuer name across URL punctuation and legal suffixes."""
    company_words = _normalized_words(company)
    if not company_words:
        return False
    hay = f" {' '.join(_normalized_words(text))} "
    phrases = [" ".join(company_words)]
    core_words = list(company_words)
    while core_words and core_words[-1] in LEGAL_ENTITY_SUFFIX_TOKENS:
        core_words.pop()
    if len(core_words) >= 2:
        phrases.append(" ".join(core_words))
    return any(f" {phrase} " in hay for phrase in phrases)


def _distinctive_aliases(company: str, ticker: str) -> set[str]:
    aliases = {ticker.upper(), company}
    for token in re.split(r"[\s,./]+", company):
        token = token.strip()
        if len(token) >= 5 and token.lower() not in GENERIC_COMPANY_TOKENS:
            aliases.add(token)
    return aliases


def ticker_meta(ticker: str) -> dict:
    ticker = ticker.upper()
    reg = load_json(PORTFOLIO_REGISTRY, {})
    holding = (reg.get("holdings") or {}).get(ticker) or {}
    us_cfg = load_json(US_TICKER_CONFIG, {})
    download = holding.get("download") or {}
    cik = download.get("cik")
    if not cik:
        cik = (us_cfg.get(ticker) or {}).get("cik")
    company = holding.get("company") or ticker
    return {
        "ticker": ticker,
        "company": company,
        "cik": str(cik).strip() if cik else None,
        "aliases": sorted(_distinctive_aliases(company, ticker), key=len, reverse=True),
    }


CANONICAL_REPORTS_DIR = ROOT / "_system" / "reference" / "activist-reports"


def activist_reports_dir(ticker: str, side: str) -> Path:
    return ROOT / ticker / "third-party-analyses" / "activist_reports" / side


def canonical_report_path(firm_id: str, dest_name: str) -> Path:
    return CANONICAL_REPORTS_DIR / firm_id / dest_name


def activist_index_path(ticker: str) -> Path:
    return ROOT / ticker / "third-party-analyses" / "activist_reports_index.json"


def load_ticker_index(ticker: str) -> dict:
    path = activist_index_path(ticker)
    data = load_json(path, {"ticker": ticker.upper(), "reports": []})
    data.setdefault("ticker", ticker.upper())
    data.setdefault("reports", [])
    return data


def save_ticker_index(ticker: str, index: dict) -> Path:
    path = activist_index_path(ticker)
    index["updated_at"] = now_iso()
    write_json(path, index)
    return path


def report_key(entry: dict) -> str:
    return "|".join(
        [
            entry.get("firm_id") or "",
            entry.get("report_date") or "",
            entry.get("source_url") or "",
            entry.get("canonical_file") or "",
            entry.get("local_pdf") or "",
            entry.get("local_file") or "",
            entry.get("accession") or "",
        ]
    )


def resolve_report_file(report: dict) -> tuple[str | None, bool, bool]:
    """Return (repo-relative path, is_pdf, exists on disk)."""
    candidates: list[tuple[str, bool]] = []
    if report.get("canonical_file"):
        ref = str(report["canonical_file"]).replace("\\", "/")
        candidates.append((ref, ref.lower().endswith(".pdf")))
    if report.get("local_pdf"):
        ref = str(report["local_pdf"]).replace("\\", "/")
        candidates.append((ref, True))
    if report.get("local_file"):
        ref = str(report["local_file"]).replace("\\", "/")
        candidates.append((ref, ref.lower().endswith(".pdf")))
    for ref, is_pdf in candidates:
        path = ROOT / ref
        if path.exists() and path.stat().st_size > 0:
            return ref, is_pdf, True
    if candidates:
        ref, is_pdf = candidates[0]
        return ref, is_pdf, False
    return None, False, False


def publisher_match_blob(report: dict) -> str:
    """Text used to match publisher/local/wire reports to a ticker (excludes repo paths).

    Including local_file makes every ``{TICKER}/third-party-analyses/...`` path
    match its folder ticker regardless of document content.
    """
    parts = [
        report.get("title") or "",
        report.get("source_url") or "",
        report.get("document_url") or "",
        report.get("firm_name") or "",
    ]
    return " ".join(p for p in parts if p)


NON_REPORT_SLUGS = frozenset(
    {
        "about",
        "authors",
        "careers",
        "contact",
        "items",
        "legal",
        "legal-disclaimer",
        "lostpassword",
        "news",
        "newsroom",
        "podcast",
        "privacy",
        "privacy-policy",
        "products",
        "publications",
        "research",
        "single-project",
        "social-media-disclaimer",
        "team",
        "terms",
        "terms-of-use",
    }
)


def classify_publisher_page(url: str, title: str = "") -> tuple[bool, str]:
    """Reject publisher navigation/policy pages before ticker matching."""
    from urllib.parse import urlparse

    parsed = urlparse(url or "")
    path = parsed.path.strip("/")
    slug = path.split("/")[-1].lower() if path else ""
    normalized_title = re.sub(r"\s+", " ", title or "").strip().lower()
    if not slug:
        return False, "publisher_homepage"
    if slug in NON_REPORT_SLUGS:
        return False, f"non_report_slug:{slug}"
    if any(
        phrase in normalized_title
        for phrase in (
            "legal disclaimer",
            "privacy policy",
            "social media disclaimer",
            "all rights reserved",
            "page not found",
        )
    ):
        return False, "non_report_title"
    return True, "report_candidate"


def publisher_match_allowed(url: str, title: str, blob: str, meta: dict) -> tuple[bool, float, str]:
    is_report, page_reason = classify_publisher_page(url, title)
    if not is_report:
        return False, 0.0, page_reason
    if url_target_mismatch(url, title, meta):
        return False, 0.0, "url_mismatch"
    matched, confidence, reason = match_report_to_ticker(blob, meta)
    if not matched or confidence < 0.9:
        return False, confidence, reason
    if reason.startswith("alias:"):
        return False, confidence, reason
    return True, confidence, reason


def prune_ghost_index_entries(ticker: str, *, dry_run: bool = False) -> int:
    """Drop index rows whose local file is missing and no publisher URL remains."""
    index = load_ticker_index(ticker)
    kept: list[dict] = []
    removed = 0
    meta = ticker_meta(ticker)
    for report in index.get("reports") or []:
        _ref, _is_pdf, exists = resolve_report_file(report)
        source_url = report.get("source_url")
        title = report.get("title") or ""
        url = source_url or report.get("local_file") or ""
        if not exists and not source_url:
            removed += 1
            continue
        if report.get("source") in PUBLISHER_SOURCES and url:
            if url_target_mismatch(url, title, meta) and not exists:
                removed += 1
                continue
        kept.append(report)
    if removed and not dry_run:
        index["reports"] = kept
        save_ticker_index(ticker, index)
    return removed


def upsert_report(index: dict, entry: dict) -> bool:
    key = report_key(entry)
    reports = index.setdefault("reports", [])
    local_file = entry.get("local_file")
    if local_file and entry.get("source") == "local":
        for i, existing in enumerate(reports):
            if existing.get("local_file") == local_file:
                merged = {**existing, **entry}
                if merged != existing:
                    reports[i] = merged
                    return True
                return False
    for i, existing in enumerate(reports):
        if report_key(existing) == key:
            merged = {**existing, **entry}
            if merged != existing:
                reports[i] = merged
                return True
            return False
    reports.append(entry)
    return True


def side_for_firm(firm_id: str, default: str = "long") -> str:
    for firm in load_firm_registry().get("firms") or []:
        if firm.get("id") == firm_id:
            return firm.get("side") if firm.get("side") != "both" else default
    return default


def firm_name(firm_id: str) -> str:
    for firm in load_firm_registry().get("firms") or []:
        if firm.get("id") == firm_id:
            return firm.get("name") or firm_id
    return firm_id


def match_report_to_ticker(text: str, meta: dict, *, min_confidence: float = 0.0) -> tuple[bool, float, str]:
    hay = (text or "").lower()
    ticker = meta["ticker"].lower()
    company = (meta.get("company") or "").lower()

    # Resolve the issuer name before ticker symbols.  Short symbols such as A,
    # T, ON, IT, ED, and MAR are ordinary prose/month tokens and are never
    # sufficient without explicit market notation.
    if company and len(company) >= 6 and _matches_company_phrase(hay, company):
        return True, 0.98, "company_name"

    # Lead brand token from the company name (e.g. "costar" from "CoStar Group").
    # Treated as company evidence (not a weak alias) so open letters titled
    # "…Letter to CoStar Board" survive publisher_match_allowed.
    if company:
        for token in re.split(r"[\s,./]+", company):
            token_l = token.strip().lower()
            if len(token_l) < 6 or token_l in GENERIC_COMPANY_TOKENS:
                continue
            if re.search(rf"\b{re.escape(token_l)}\b", hay, re.I):
                return True, 0.95, "company_brand"
            break

    explicit_patterns = (
        rf"\${re.escape(ticker)}\b",
        rf"\b(?:nyse|nasdaq|amex|tsx|lse|asx)\s*[:\-]\s*{re.escape(ticker)}\b",
        rf"\b(?:ticker|symbol)\s*[:\-]\s*{re.escape(ticker)}\b",
    )
    if any(re.search(pattern, hay, re.I) for pattern in explicit_patterns):
        return True, 0.99, "ticker_explicit"

    if len(ticker) >= 4 and re.search(rf"\b{re.escape(ticker)}\b", hay, re.I):
        return True, 0.94, "ticker_symbol"

    ticker_compact = re.sub(r"[.\-]", "", ticker)
    if len(ticker_compact) >= 4 and re.search(rf"\b{re.escape(ticker_compact)}\b", hay, re.I):
        return True, 0.98, "ticker_compact"

    for alias in meta.get("aliases") or []:
        alias_l = str(alias).strip().lower()
        if len(alias_l) < 6 or alias_l in GENERIC_COMPANY_TOKENS:
            continue
        if alias_l in hay:
            return True, 0.82, f"alias:{alias_l}"

    return False, 0.0, "no_match"


def text_matches_ticker(text: str, meta: dict) -> bool:
    matched, confidence, _reason = match_report_to_ticker(text, meta)
    return matched and confidence >= 0.9


def url_target_mismatch(url: str, title: str, meta: dict) -> bool:
    """True when URL/title clearly names a different company (site false-positive guard)."""
    from urllib.parse import urlparse

    blob = f"{url} {title}".lower()
    ticker = meta["ticker"].lower()
    company = (meta.get("company") or "").lower()
    if len(ticker) >= 4 and re.search(rf"\b{re.escape(ticker)}\b", blob, re.I):
        return False
    if company and len(company) >= 6 and _matches_company_phrase(blob, company):
        return False

    slug = urlparse(url or "").path.strip("/").split("/")[-1].lower()
    if not slug or re.fullmatch(r"[\d-]+", slug):
        return False
    slug_tokens = {t for t in re.split(r"[-_]+", slug) if len(t) >= 3}
    ours = {ticker.replace(".", "")}
    ours.update(
        t.lower()
        for t in re.split(r"[\s,./]+", company)
        if len(t) >= 4 and t.lower() not in GENERIC_COMPANY_TOKENS
    )
    overlap = slug_tokens & ours
    distinctive_overlap = {t for t in overlap if t not in GENERIC_COMPANY_TOKENS and len(t) >= 4}
    if slug_tokens and not distinctive_overlap:
        return True
    return False


def safe_report_filename(firm_id: str, report_date: str, suffix: str, ext: str = ".pdf") -> str:
    date_part = (report_date or date.today().isoformat())[:10]
    stem = re.sub(r"[^a-zA-Z0-9._-]+", "-", f"{firm_id}_{date_part}_{suffix}").strip("-")
    return f"{stem}{ext}"


def load_global_scan() -> dict:
    return load_json(GLOBAL_SCAN_PATH, {"reports": [], "generated_at": None})


def save_global_scan(payload: dict) -> None:
    write_json(GLOBAL_SCAN_PATH, payload)


def append_scan_log(entry: dict) -> None:
    log = load_json(SCAN_LOG_PATH, {"entries": []})
    log.setdefault("entries", []).append({**entry, "at": now_iso()})
    log["entries"] = log["entries"][-500:]
    write_json(SCAN_LOG_PATH, log)
