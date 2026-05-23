#!/usr/bin/env python3
"""Shared portfolio news policy, classification, and ticker matching."""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "_system" / "portfolio" / "registry.json"
PORTFOLIO_NEWS_PATH = ROOT / "dashboard" / "data" / "portfolio_news.json"
NEWS_SEEN_PATH = ROOT / "_system" / "data" / "news_seen.json"

POLICY_VERSION = 2
FEED_MIN_CONFIDENCE = 0.80
REFRESH_MIN_CONFIDENCE = 0.85
OTC_EXPLICIT_ONLY = frozenset({"FRMO", "KEWL", "OTCM"})
POLYGON_MARKETS = frozenset({"US", "CA"})

PUBLISHER_ALLOWLIST = frozenset({
    "reuters",
    "bloomberg",
    "globenewswire",
    "business wire",
    "pr newswire",
    "benzinga",
    "accesswire",
    "marketwatch",
    "wall street journal",
    "financial times",
    "cnbc",
    "sec",
})

REFRESH_CATEGORIES = frozenset({
    "m_and_a",
    "spinoff",
    "restructuring",
    "capital_raise",
    "buyback",
    "dividend_policy",
    "royalty_trust",
    "accounting",
    "activist",
    "corporate_action",
    "guidance",
    "earnings_material",
    "management",
    "regulatory",
    "major_contract",
    "capacity_ops",
    "market_structure",
    "platform_pricing",
    "index_inclusion",
    "ai_material",
    "legal",
    "labor",
})

FEED_ONLY_CATEGORIES = frozenset({"forward_split", "insider_block"})

NEGATIVE_PATTERNS: list[re.Pattern] = [
    re.compile(r"\banalyst(s)?\b", re.I),
    re.compile(r"\bprice\s+target", re.I),
    re.compile(r"\b(up|down)grade", re.I),
    re.compile(r"\bunusual\s+option", re.I),
    re.compile(r"\bshort\s+interest", re.I),
    re.compile(r"\bstock\s+(rises|falls|jumps|drops|slides|soars|tumbles)\b", re.I),
    re.compile(r"\bshares?\s+(rise|fall|jump|drop|slide|soar|tumble)\b", re.I),
    re.compile(r"\bedges?\s+higher\b", re.I),
    re.compile(r"\bmarket\s+wrap\b", re.I),
    re.compile(r"\b(?:top|best)\s+\d+\s+stocks\b", re.I),
    re.compile(r"\bpresenting\s+at\b", re.I),
    re.compile(r"\bconference\s+call\s+scheduled\b", re.I),
    re.compile(r"\besg\s+(score|rating)\b", re.I),
    re.compile(r"\bJim Cramer\b", re.I),
    re.compile(r"\brequire action from\b.*\binvestors\b", re.I),
    re.compile(r"\bhas \$\d[\d,.]* (million|billion)? stake in\b", re.I),
    re.compile(r"\bin focus:\b", re.I),
    re.compile(r"\bobv divergence\b", re.I),
    re.compile(r"\bseeking alpha\b.*\?", re.I),
    re.compile(r"\bto present at\b", re.I),
    re.compile(r"\bpresent at the\b", re.I),
    re.compile(r"\blatest sec filings\b", re.I),
    re.compile(r"\bsec filings?\s*[-–—]", re.I),
    re.compile(r"\b10k form and latest\b", re.I),
    re.compile(r"\bshares acquired by\b", re.I),
    re.compile(r"\bacquires (?:new )?\d[\d,]* shares (?:in|of)\b", re.I),
    re.compile(r"\bacquires new shares in\b", re.I),
    re.compile(r"\bacquires \d[\d,]* shares of\b", re.I),
    re.compile(r"\bdeclares consistent quarterly dividend\b", re.I),
    re.compile(r"\bconsistent quarterly dividend\b", re.I),
    re.compile(r"\bredefine its core narrative\b", re.I),
    re.compile(r"\bstock down as\b", re.I),
    re.compile(r"\blarge[-\s]?cap stock picks\b", re.I),
    re.compile(r"\bwhy .{0,40} is down\b", re.I),
    re.compile(r"\?\s*-\s*(yahoo finance|marketbeat|simplywall)", re.I),
]

POSITIVE_PATTERNS: dict[str, list[re.Pattern]] = {
    "m_and_a": [
        re.compile(r"\bacquir(e|es|ed|ing|ition)\b", re.I),
        re.compile(r"\bmerger\b", re.I),
        re.compile(r"\bdivest(iture|s|ed|ing)?\b", re.I),
        re.compile(r"\btake[-\s]?private\b", re.I),
        re.compile(r"\bjoint\s+venture\b", re.I),
        re.compile(r"\basset\s+sale\b", re.I),
    ],
    "spinoff": [
        re.compile(r"\bspin[-\s]?off\b", re.I),
        re.compile(r"\bseparation\s+of\b", re.I),
        re.compile(r"\bdistribution\s+of\s+shares\b", re.I),
    ],
    "restructuring": [
        re.compile(r"\bbankruptcy\b", re.I),
        re.compile(r"\bchapter\s+11\b", re.I),
        re.compile(r"\brestructur", re.I),
        re.compile(r"\bgoing\s+concern\b", re.I),
        re.compile(r"\brecapitaliz", re.I),
    ],
    "capital_raise": [
        re.compile(r"\b(equity|debt|convertible)\s+(offering|raise|issuance)\b", re.I),
        re.compile(r"\bsecondary\s+offering\b", re.I),
        re.compile(r"\bPIPE\b"),
        re.compile(r"\bcovenant\s+breach\b", re.I),
    ],
    "buyback": [
        re.compile(r"\bshare\s+repurchase\b", re.I),
        re.compile(r"\bstock\s+buyback\b", re.I),
        re.compile(r"\bbuyback\s+(program|authorization|plan)\b", re.I),
    ],
    "dividend_policy": [
        re.compile(r"\b(dividend|distribution)\s+(cut|suspend|reduction|increase|initiat)", re.I),
        re.compile(r"\b(special|quarterly)\s+dividend\b", re.I),
    ],
    "royalty_trust": [
        re.compile(r"\broyalty\s+trust\b", re.I),
        re.compile(r"\bcash\s+distribution\b", re.I),
        re.compile(r"\btrust\s+distribution\b", re.I),
        re.compile(r"\breserve\s+(revision|estimate)\b", re.I),
    ],
    "accounting": [
        re.compile(r"\brestate(ment|d)\b", re.I),
        re.compile(r"\bmaterial\s+weakness\b", re.I),
        re.compile(r"\bauditor\s+(change|resign)", re.I),
    ],
    "activist": [
        re.compile(r"\b13[dD]\b"),
        re.compile(r"\bactivist\s+investor\b", re.I),
        re.compile(r"\bproxy\s+fight\b", re.I),
    ],
    "corporate_action": [
        re.compile(r"\bdelist", re.I),
        re.compile(r"\bticker\s+change\b", re.I),
        re.compile(r"\breverse\s+split\b", re.I),
    ],
    "forward_split": [
        re.compile(r"\bstock\s+split\b", re.I),
        re.compile(r"\bforward\s+split\b", re.I),
        re.compile(r"\b\d+[-\s]for[-\s]1\b", re.I),
    ],
    "guidance": [
        re.compile(r"\bguidance\b", re.I),
        re.compile(r"\boutlook\b", re.I),
        re.compile(r"\bpre[-\s]?announce", re.I),
        re.compile(r"\b(withdraw(s|n)?|cuts?|raises?)\s+(outlook|guidance|forecast)\b", re.I),
    ],
    "earnings_material": [
        re.compile(r"\b(miss(es|ed)?|beat(s|ing)?)\s+(estimates|expectations)\b", re.I),
        re.compile(r"\bmargin\s+(compression|expansion|pressure)\b", re.I),
        re.compile(r"\b(revenue|sales)\s+(miss|decline|shortfall)\b", re.I),
        re.compile(r"\bunexpected\s+(loss|profit|results)\b", re.I),
    ],
    "management": [
        re.compile(r"\b(CEO|CFO|chief executive|chief financial|board chair)\b", re.I),
        re.compile(r"\bappoint(s|ed|ment)\s+(CEO|CFO|chief)\b", re.I),
        re.compile(r"\bresign(s|ed|ation)\s+(as\s+)?(CEO|CFO|chief)\b", re.I),
    ],
    "regulatory": [
        re.compile(r"\b(FDA|antitrust|DOJ|FTC|SEC)\b"),
        re.compile(r"\b(regulatory\s+approval|clearance|consent\s+decree|fine|penalty)\b", re.I),
        re.compile(r"\blicen(s|c)e\s+(loss|revocation|approval)\b", re.I),
    ],
    "major_contract": [
        re.compile(r"\b(contract|agreement|deal)\s+(award|win|signed|signed)\b", re.I),
        re.compile(r"\b(multi[-\s]?year|long[-\s]?term)\s+(contract|agreement|deal)\b", re.I),
        re.compile(r"\bloses?\s+(contract|customer|client)\b", re.I),
    ],
    "capacity_ops": [
        re.compile(r"\b(plant|facility|data\s+center|mine)\s+(open|close|closure|shutdown)\b", re.I),
        re.compile(r"\bforce\s+majeure\b", re.I),
        re.compile(r"\boutage\b", re.I),
        re.compile(r"\bproduction\s+(halt|disruption)\b", re.I),
    ],
    "market_structure": [
        re.compile(r"\b(index|listing)\s+(inclusion|rebalancing|rule\s+change)\b", re.I),
        re.compile(r"\badded\s+to\s+(the\s+)?(S&P|Russell|MSCI|Nasdaq)\b", re.I),
        re.compile(r"\bexchange\s+(rule|fee|listing\s+standard)\b", re.I),
    ],
    "platform_pricing": [
        re.compile(r"\b(price\s+increase|fee\s+increase|take[-\s]?rate)\b", re.I),
        re.compile(r"\bpricing\s+(change|update)\b", re.I),
    ],
    "index_inclusion": [
        re.compile(r"\badded\s+to\s+(the\s+)?(S&P\s+500|Russell|MSCI|Nasdaq\s+100)\b", re.I),
        re.compile(r"\bindex\s+inclusion\b", re.I),
        re.compile(r"\bjoins\s+(the\s+)?(S&P|Russell|MSCI)\b", re.I),
    ],
    "ai_material": [
        re.compile(r"\b(AI|artificial intelligence)\b"),
        re.compile(r"\b(capex|capital expenditure|margin|monetiz)\b", re.I),
    ],
    "legal": [
        re.compile(r"\b(lawsuit|litigation|settlement|patent\s+(dispute|infringement))\b", re.I),
        re.compile(r"\b(\$\d[\d,.]*\s*(million|billion|M|B))\b", re.I),
    ],
    "labor": [
        re.compile(r"\b(strike|walkout|labor\s+dispute|union)\b", re.I),
        re.compile(r"\blayoff(s)?\b", re.I),
    ],
    "insider_block": [
        re.compile(r"\b(insider|Form\s+4)\b", re.I),
        re.compile(r"\b(\$\d[\d,.]*\s*(million|billion|M|B))\b", re.I),
        re.compile(r"\b(0\.[5-9]\d?|[1-9]\d?(\.\d+)?)\s*%\s+(stake|holding|position)\b", re.I),
    ],
}

CATEGORY_PRIORITY = {
    "restructuring": 100,
    "m_and_a": 95,
    "guidance": 90,
    "earnings_material": 88,
    "regulatory": 85,
    "accounting": 84,
    "royalty_trust": 83,
    "capital_raise": 82,
    "activist": 80,
    "spinoff": 78,
    "corporate_action": 75,
    "management": 70,
    "major_contract": 68,
    "capacity_ops": 66,
    "market_structure": 64,
    "index_inclusion": 63,
    "platform_pricing": 62,
    "buyback": 60,
    "dividend_policy": 58,
    "ai_material": 55,
    "legal": 50,
    "labor": 48,
    "forward_split": 40,
    "insider_block": 30,
}

HOLDING_OVERRIDES: dict[str, dict] = {
    "AMZN": {
        "search_names": ["Amazon", "Amazon.com"],
        "exclude_patterns": [r"Amazon rainforest", r"Amazon River", r"Amazon (jungle|forest)"],
        "polygon_ticker": "AMZN",
    },
    "GOOGL": {
        "search_names": ["Alphabet", "Google"],
        "exclude_patterns": [r"Google Doodle", r"Google Maps tips"],
        "polygon_ticker": "GOOGL",
    },
    "BN": {
        "search_names": ["Brookfield Corporation", "Brookfield"],
        "polygon_ticker": "BN",
    },
    "CSU": {"search_names": ["Constellation Software"], "polygon_ticker": "CSU"},
    "8697.T": {
        "search_names": ["Japan Exchange Group", "JPX"],
        "google_locale": {"hl": "ja", "gl": "JP", "ceid": "JP:ja"},
        "ticker_tokens": ["8697", "8697.T"],
    },
    "3905.T": {
        "search_names": ["DataSection", "データセクション"],
        "google_locale": {"hl": "ja", "gl": "JP", "ceid": "JP:ja"},
        "ticker_tokens": ["3905", "3905.T"],
    },
    "TEQ.ST": {
        "search_names": ["Teqnion"],
        "ticker_tokens": ["TEQ", "TEQ.ST"],
    },
    "SJT": {
        "search_names": ["San Juan Basin Royalty Trust", "San Juan Basin"],
        "polygon_ticker": "SJT",
    },
    "QDEL": {"search_names": ["QuidelOrtho", "Quidel"], "polygon_ticker": "QDEL"},
    "KEWL": {"search_names": ["Keweenaw Land Association", "Keweenaw Land"]},
    "FRMO": {"search_names": ["FRMO Corporation", "FRMO"]},
    "OTCM": {"search_names": ["OTC Markets Group", "OTC Markets"]},
}

_TICKER_STOPWORDS = frozenset({
    "ETF", "ETFS", "NAV", "AUM", "USD", "USA", "CEO", "CFO", "SEC", "IRS",
    "API", "PDF", "NYSE", "NASDAQ", "AMEX", "IPO", "OTC", "AI", "IT", "US",
    "THE", "AND", "FOR", "NEW", "INC", "LTD", "CORP", "LLC",
})

_PAREN_TICKER_RE = re.compile(
    r"\(\s*(?:(?:NASDAQ|NYSE|NYSE\s*ARCA|ARCA|TSX|CBOE|OTC)"
    r"(?:\s*Exchange)?(?:,\s*Inc\.?)?\s*:\s*)?([A-Z0-9.\-]{1,10})\s*\)"
)
_EXCHANGE_TICKER_RE = re.compile(
    r"\b(?:NASDAQ|NYSE|NYSE\s*ARCA|ARCA|TSX|CBOE|OTC)"
    r"(?:\s*Exchange)?(?:,\s*Inc\.?)?\s*:\s*([A-Z0-9.\-]{1,10})\b"
)
_DOLLAR_TICKER_RE = re.compile(r"\$([A-Z0-9.\-]{1,10})\b")
_MANAGEMENT_REFRESH_RE = re.compile(
    r"\b(CEO|CFO|chief executive|chief financial|board chair)\b", re.I
)
_AI_MATERIAL_RE = re.compile(r"\b(capex|capital expenditure|margin|monetiz|revenue|cost)\b", re.I)
_ROYALTY_TRUST_MATERIAL_RE = re.compile(
    r"\b(distribution|payout|reserve|excess production|distributable|going concern|"
    r"no \w+ cash|cash distribution|production costs?)\b",
    re.I,
)
_EARNINGS_MATERIAL_RE = re.compile(
    r"\b(miss(es|ed)?|unexpected|margin|guidance|outlook|shortfall|compression|"
    r"withdraw(s|n)?)\b",
    re.I,
)
_MANAGEMENT_COMMENTARY_RE = re.compile(
    r"\b(Jim Cramer|fan of|before anyone else|podcast|breaking down)\b", re.I,
)
_FUND_FLOW_M_AND_A_RE = re.compile(
    r"\b("
    r"acquires (?:new )?\d[\d,]* shares (?:in|of)|"
    r"acquires new shares in|"
    r"shares acquired by|"
    r"acquired by [A-Za-z][\w\s]{0,40}(?:Capital|Wealth|Financial|Advisors|Partners|Management|Mutual)"
    r")\b",
    re.I,
)
_DIVIDEND_ROUTINE_RE = re.compile(
    r"\b(consistent|maintains|regular|unchanged|steady)\s+(quarterly\s+)?dividend\b", re.I,
)
_SEC_FILING_ROUNDUP_RE = re.compile(
    r"\b(10k form|10-k form|latest sec filings|sec filings?\s*[-–—])", re.I,
)
_OPINION_HEADLINE_RE = re.compile(
    r"^(will|should|why|how)\b.*\?", re.I,
)


@dataclass
class HoldingNewsConfig:
    ticker: str
    company: str
    market: str
    exchange: str
    search_names: list[str]
    ticker_tokens: list[str]
    polygon_ticker: str | None
    exclude_patterns: list[re.Pattern]
    google_locale: dict[str, str]
    ir_domains: list[str]
    explicit_only: bool


@dataclass
class NewsItem:
    id: str
    tickers: list[str] = field(default_factory=list)
    company: str | None = None
    category: str = "other"
    confidence: float = 0.7
    match_tier: str | None = None
    published_utc: str | None = None
    title: str | None = None
    summary: str | None = None
    url: str | None = None
    publisher: str | None = None
    source: str = "unknown"
    linked_filing: str | None = None
    refresh_eligible: bool = False
    policy_version: int = POLICY_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


def _norm_ticker(sym: object) -> str:
    return str(sym).strip().upper().replace(".", "-")


def load_registry() -> dict:
    if not REGISTRY_PATH.exists():
        return {"holdings": {}}
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def build_holding_config(ticker: str, holding: dict) -> HoldingNewsConfig:
    override = HOLDING_OVERRIDES.get(ticker, {})
    company = holding.get("company") or ticker
    search_names = list(override.get("search_names") or [company])
    if company not in search_names:
        search_names.insert(0, company)

    tokens = override.get("ticker_tokens") or [ticker]
    if ticker not in tokens:
        tokens = [ticker, *tokens]

    market = holding.get("market") or "US"
    polygon_ticker = override.get("polygon_ticker")
    if polygon_ticker is None and market in POLYGON_MARKETS:
        polygon_ticker = ticker.split(".")[0] if "." in ticker else ticker

    exclude_raw = override.get("exclude_patterns") or []
    ir_roots = (holding.get("download") or {}).get("ir_roots") or []
    ir_domains: list[str] = []
    for root in ir_roots:
        m = re.search(r"https?://([^/]+)", str(root))
        if m:
            ir_domains.append(m.group(1).lower())

    return HoldingNewsConfig(
        ticker=ticker,
        company=company,
        market=market,
        exchange=holding.get("exchange") or "",
        search_names=search_names,
        ticker_tokens=list(dict.fromkeys(tokens)),
        polygon_ticker=polygon_ticker,
        exclude_patterns=[re.compile(p, re.I) for p in exclude_raw],
        google_locale=override.get("google_locale")
        or {"hl": "en-US", "gl": "US", "ceid": "US:en"},
        ir_domains=ir_domains,
        explicit_only=ticker in OTC_EXPLICIT_ONLY,
    )


def load_holding_configs() -> dict[str, HoldingNewsConfig]:
    reg = load_registry()
    out: dict[str, HoldingNewsConfig] = {}
    for ticker, holding in sorted((reg.get("holdings") or {}).items()):
        out[ticker] = build_holding_config(ticker, holding)
    return out


def classify_text(text: str) -> tuple[str | None, float]:
    if not text or not text.strip():
        return None, 0.0

    if any(p.search(text) for p in NEGATIVE_PATTERNS):
        # Hard reject obvious commentary / price noise before scoring positives.
        return None, 0.0

    neg_hits = 0
    scores: dict[str, int] = {}
    for cat, patterns in POSITIVE_PATTERNS.items():
        hits = sum(1 for p in patterns if p.search(text))
        if hits:
            scores[cat] = hits

    if not scores:
        return None, 0.0

    if scores.get("ai_material"):
        if not _AI_MATERIAL_RE.search(text):
            scores.pop("ai_material", None)
    if scores.get("insider_block"):
        if not re.search(r"\b(insider|Form\s+4)\b", text, re.I):
            scores.pop("insider_block", None)
    if scores.get("royalty_trust"):
        if not _ROYALTY_TRUST_MATERIAL_RE.search(text):
            scores.pop("royalty_trust", None)
    if scores.get("earnings_material"):
        if not _EARNINGS_MATERIAL_RE.search(text):
            scores.pop("earnings_material", None)
    if scores.get("management") and _MANAGEMENT_COMMENTARY_RE.search(text):
        scores.pop("management", None)
    if scores.get("m_and_a") and _FUND_FLOW_M_AND_A_RE.search(text):
        scores.pop("m_and_a", None)
    if scores.get("dividend_policy") and _DIVIDEND_ROUTINE_RE.search(text):
        scores.pop("dividend_policy", None)
    if scores.get("regulatory") and _SEC_FILING_ROUNDUP_RE.search(text):
        scores.pop("regulatory", None)
    if _OPINION_HEADLINE_RE.search((text or "").split("\n")[0]):
        return None, 0.0

    if not scores:
        return None, 0.0

    cat = max(scores.keys(), key=lambda c: (CATEGORY_PRIORITY.get(c, 0), scores[c]))
    confidence = min(0.95, 0.70 + 0.08 * scores[cat])
    return cat, round(confidence, 3)


def _name_in_text(name: str, text: str) -> bool:
    if not name or not text:
        return False
    pat = re.compile(rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])", re.I)
    return bool(pat.search(text))


def _token_in_text(token: str, text: str) -> bool:
    token = token.strip()
    if not token:
        return False
    if token.startswith("$"):
        return token.lower() in text.lower()
    pat = re.compile(rf"(?<![A-Za-z0-9.\-]){re.escape(token)}(?![A-Za-z0-9.\-])", re.I)
    return bool(pat.search(text))


def _extract_tickers_from_text(text: str) -> set[str]:
    out: set[str] = set()
    for regex in (_PAREN_TICKER_RE, _EXCHANGE_TICKER_RE, _DOLLAR_TICKER_RE):
        for match in regex.findall(text or ""):
            sym = str(match).upper()
            if sym and sym not in _TICKER_STOPWORDS:
                out.add(sym)
    for match in re.findall(r"(?<![A-Z0-9])([A-Z]{2,6})(?![a-z])", text or ""):
        if match not in _TICKER_STOPWORDS:
            out.add(match)
    return out


def match_holding(
    text: str,
    url: str | None,
    configs: dict[str, HoldingNewsConfig],
    *,
    polygon_tickers: Iterable[str] | None = None,
) -> tuple[str | None, str | None]:
    """Return (ticker, match_tier) or (None, None)."""
    blob = text or ""
    url_l = (url or "").lower()
    poly = {_norm_ticker(t) for t in (polygon_tickers or [])}

    explicit_hits: list[str] = []
    high_hits: list[str] = []

    for ticker, cfg in configs.items():
        if cfg.exclude_patterns and any(p.search(blob) for p in cfg.exclude_patterns):
            continue

        title_explicit = False
        for token in cfg.ticker_tokens:
            if _token_in_text(token, blob) or _token_in_text(f"${token}", blob):
                title_explicit = True
                break
            norm = _norm_ticker(token)
            if norm in {_norm_ticker(t) for t in _extract_tickers_from_text(blob)}:
                title_explicit = True
                break

        if cfg.polygon_ticker and _norm_ticker(cfg.polygon_ticker) in poly:
            title_explicit = True

        if title_explicit:
            explicit_hits.append(ticker)
            continue

        if any(_name_in_text(name, blob) for name in cfg.search_names):
            if cfg.ir_domains and any(d in url_l for d in cfg.ir_domains):
                high_hits.append(ticker)
            elif "sec.gov" in url_l:
                high_hits.append(ticker)
            elif any(_name_in_text(name, blob[:200]) for name in cfg.search_names):
                high_hits.append(ticker)

    if explicit_hits:
        return sorted(set(explicit_hits))[0], "explicit"
    if high_hits:
        return sorted(set(high_hits))[0], "high"
    return None, None


def score_confidence(
    base: float,
    *,
    match_tier: str | None,
    publisher: str | None,
    url: str | None,
    neg_hits: int = 0,
) -> float:
    conf = base
    if match_tier == "explicit":
        conf += 0.10
    elif match_tier == "high":
        conf += 0.05
    pub = (publisher or "").lower()
    if any(a in pub for a in PUBLISHER_ALLOWLIST):
        conf += 0.05
    if url and "sec.gov" in url.lower():
        conf += 0.05
    if neg_hits:
        conf = max(0.55, conf - 0.15 * neg_hits)
    return round(min(0.98, conf), 3)


def is_refresh_eligible(item: NewsItem) -> bool:
    if item.category in FEED_ONLY_CATEGORIES:
        return False
    if item.category not in REFRESH_CATEGORIES:
        return False
    if item.category == "management" and item.title:
        if not _MANAGEMENT_REFRESH_RE.search(f"{item.title}\n{item.summary or ''}"):
            return False
    if item.category == "forward_split":
        return False
    if (item.match_tier or "") not in {"explicit", "high"}:
        return False
    return float(item.confidence or 0) >= REFRESH_MIN_CONFIDENCE


def passes_feed_gate(item: NewsItem, cfg: HoldingNewsConfig | None) -> bool:
    if (item.match_tier or "") not in {"explicit", "high"}:
        return False
    if float(item.confidence or 0) < FEED_MIN_CONFIDENCE:
        return False
    if cfg and cfg.explicit_only and item.match_tier != "explicit":
        return False
    return True


def parse_published_iso(raw: str | None) -> str | None:
    if not raw:
        return None
    raw = raw.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        if "T" in raw:
            dt = datetime.fromisoformat(raw)
        else:
            dt = datetime.strptime(raw[:10], "%Y-%m-%d").replace(tzinfo=UTC)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC).isoformat()
    except ValueError:
        return None


def published_dt(item: dict | NewsItem) -> datetime | None:
    raw = item.published_utc if isinstance(item, NewsItem) else item.get("published_utc")
    iso = parse_published_iso(raw)
    if not iso:
        return None
    return datetime.fromisoformat(iso)


def load_portfolio_news_items() -> list[dict]:
    if not PORTFOLIO_NEWS_PATH.exists():
        return []
    try:
        payload = json.loads(PORTFOLIO_NEWS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return list(payload.get("items") or [])


def load_ticker_news_items(ticker: str) -> list[dict]:
    path = ROOT / ticker / "research" / "news" / "news_index.json"
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return list(payload.get("items") or [])


def latest_refresh_news_activity(ticker: str, since: datetime | None = None) -> datetime | None:
    """Latest published_utc of refresh-eligible news for ticker."""
    latest: datetime | None = None
    items = load_ticker_news_items(ticker) or [
        it for it in load_portfolio_news_items() if ticker in (it.get("tickers") or [])
    ]
    for raw in items:
        if not raw.get("refresh_eligible"):
            continue
        dt = published_dt(raw)
        if dt is None:
            continue
        if since and dt <= since:
            continue
        if latest is None or dt > latest:
            latest = dt
    return latest


def normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    u = url.strip()
    u = re.sub(r"[?#].*$", "", u)
    return u.rstrip("/").lower()
