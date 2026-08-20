#!/usr/bin/env python3
"""Merge multi-source insights into dashboard/data/insights.json."""
from __future__ import annotations

import json
import csv
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))
from document_store import (  # noqa: E402
    best_document_label,
    best_document_url,
    document_id_for_ref,
    letter_evidence_label,
    letter_evidence_url,
)
from insight_format import format_letter_claim  # noqa: E402
from fund_registry import canonicalize_fund_identity  # noqa: E402
from fund_identity import consolidate_letter_funds_stable  # noqa: E402
from ticker_identity import identity_match_ok  # noqa: E402
from filing_facts import (  # noqa: E402
    filing_metadata_from_text_path,
    source_filing_ref_from_text_path,
)
from vault_paths import (  # noqa: E402
    letters_ref,
    letters_root,
    path_to_letters_ref,
    path_to_podcasts_ref,
    podcasts_root,
)
from fund_families import (  # noqa: E402
    collapse_display_label,
    commentary_hash,
    consensus_vote_key,
    family_display,
    family_id_for_fund,
    normalize_commentary,
    propose_fund_families,
    write_family_proposals,
)
from filing_review import (  # noqa: E402
    filing_metric_needs_review,
    filing_metric_passes_magnitude,
    filing_metric_passes_sanity,
)
from event_triage import triage_events, write_triage_queue  # noqa: E402
from insider_materiality import score_form4_event  # noqa: E402

OUTPUT = ROOT / "dashboard" / "data" / "insights.json"
ARCHIVE_OUTPUT = ROOT / "_system" / "reference" / "data-sources" / "insights_record_archive.json"
LETTERS_INSIGHTS = letters_root() / "insights.json"
PODCASTS_INSIGHTS = podcasts_root() / "insights.json"
PODCASTS_INSIGHTS_INDEX_MIRROR = ROOT / "_system" / "reference" / "podcasts" / "insights_index_mirror.json"
PODCASTS_INSIGHTS_MIRROR = ROOT / "_system" / "reference" / "podcasts" / "insights_mirror.json"  # legacy full clone
# Full letter corpus is built offline (letter-backfill) and committed in dashboard/data/.
# CI vault clones often lag; never regress below this floor on deploy rebuilds.
MIN_LETTER_CORPUS = 15000
MIN_CLASSIFIED_LETTER_CORPUS = 12000
LETTER_REGRESSION_RATIO = 0.95
NEWS_PATH = ROOT / "dashboard" / "data" / "portfolio_news.json"
THEMES_DIR = ROOT / "_system" / "reference" / "market-data" / "themes"
INSIDER_DIR = ROOT / "_system" / "reference" / "market-data" / "insider"
INSIDER_MANIFEST = INSIDER_DIR / "manifest.json"
EARNINGS_CACHE = ROOT / "_system" / "data" / "earnings_calendar.json"
TERMINALVALUE_SOURCES = ROOT / "_system" / "reference" / "data-sources" / "terminalvalue_candidates.json"
SOURCE_UNIVERSE_PATH = ROOT / "_system" / "reference" / "data-sources" / "source_universe.json"
SUMZERO_INDEX = ROOT / "_system" / "reference" / "data-sources" / "sumzero_ideas_index.json"
KPI_TRENDS_PATH = ROOT / "dashboard" / "data" / "kpi_trends.json"
DOCUMENT_REGISTRY_PATH = ROOT / "dashboard" / "data" / "document_registry.json"
DRIVE_AUDIT_PATH = ROOT / "_system" / "reference" / "document-store" / "drive_audit_latest.json"
REDDIT_MENTIONS_PATH = ROOT / "_system" / "reference" / "market-data" / "social" / "reddit_mentions_latest.json"
TRACKED_FUNDS_RECORDS_PATH = (
    ROOT / "_system" / "reference" / "market-data" / "ownership" / "tracked_funds" / "records" / "latest.json"
)
REDDIT_SOURCES_PATH = ROOT / "_system" / "reference" / "market-data" / "social" / "reddit_sources.json"
GITHUB_REPO = "GoldmanDrew/single-stock-investments"
SECURITY_MASTER_PATH = ROOT / "_system" / "reference" / "securities" / "security_master.json"

VALID_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,11}$")
DOCUMENT_SUFFIXES = {".pdf", ".htm", ".html", ".md", ".txt", ".json"}

SOURCE_META = {
    "kpi_trend": {"label": "Inflection", "materiality": 0.95, "quality": 0.92, "axis": "fundamentals"},
    "filing": {"label": "Filing", "materiality": 0.96, "quality": 1.0, "axis": "fundamentals"},
    "earnings": {"label": "Earnings", "materiality": 0.94, "quality": 0.96, "axis": "fundamentals"},
    "insider": {"label": "Insider", "materiality": 0.86, "quality": 0.9, "axis": "ownership"},
    "specialist_13f": {"label": "Specialist 13F", "materiality": 0.88, "quality": 0.92, "axis": "ownership"},
    "tracked_fund_13f": {"label": "Tracked Fund 13F", "materiality": 0.84, "quality": 0.9, "axis": "ownership"},
    "superinvestor_letter": {"label": "Letter", "materiality": 0.8, "quality": 0.82, "axis": "ownership"},
    "podcast_episode": {"label": "Podcast", "materiality": 0.72, "quality": 0.75, "axis": "variant_view"},
    "sumzero_research": {"label": "SumZero", "materiality": 0.64, "quality": 0.68, "axis": "variant_view"},
    "reddit_mention": {"label": "Reddit", "materiality": 0.42, "quality": 0.4, "axis": "context"},
    "news": {"label": "News", "materiality": 0.72, "quality": 0.7, "axis": "catalyst"},
    "third_party": {"label": "Research", "materiality": 0.58, "quality": 0.58, "axis": "variant_view"},
    "macro": {"label": "Macro", "materiality": 0.62, "quality": 0.54, "axis": "macro"},
    "theme": {"label": "Theme", "materiality": 0.58, "quality": 0.5, "axis": "macro"},
}

MODEL_IMPACT_TERMS = (
    "irr",
    "valuation",
    "guidance",
    "falsifier",
    "margin",
    "revenue",
    "earnings",
    "capex",
    "capital allocation",
    "buyback",
    "dividend",
    "regulatory",
    "lawsuit",
    "approval",
    "acquisition",
    "contract",
    "insider purchase",
    "risk",
    "catalyst",
)

LETTER_BOILERPLATE_PHRASES = (
    "no offer to purchase",
    "no offer to sell",
    "could lose all or a substantial",
    "past performance",
    "not investment advice",
    "forward-looking",
    "confidential",
    "subscribe",
    "being able to jog",
)

# Non-letter inventory/readme paths that should not appear in fund registry.
from vault_paths import letters_ref  # noqa: E402

LETTER_META_SOURCE_FILES = {
    letters_ref("readme.md"),
    letters_ref("readme.pdf"),
}


def is_letter_meta_entry(letter: dict) -> bool:
    """Skip README and other non-letter inventory rows."""
    for key in ("source_file", "source_document"):
        ref = str(letter.get(key) or "").replace("\\", "/").lower()
        if ref in LETTER_META_SOURCE_FILES:
            return True
        if ref.endswith("/readme.md") or ref.endswith("/readme.pdf"):
            return True
    fund_id = str(letter.get("fund_id") or "").lower()
    fund = str(letter.get("fund") or "").lower()
    if fund_id == "readme" or fund == "readme":
        return True
    return False


# Non-letter document_type values from build_superinvestor_insights.classify_document.
NONLETTER_DOCUMENT_TYPES = frozenset(
    {
        "conference_idea",
        "monitor",
        "transcript",
        "product_marketing",
        "sell_side_research",
        "other_research",
    }
)
LETTERISH_DOCUMENT_TYPES = frozenset({"investor_letter", "fund_report"})
NONLETTER_FILENAME_HINT = re.compile(
    r"\b(conference|sohn|idea dinner|conference recap|monitors?|event driven trades|"
    r"ed monitor|transcript|meeting notes?|presentation|factsheet|fact sheet|"
    r"prospectus|tear sheet|deck|primer|playbook|white paper|blackbook|"
    r"guide|survey|research report)\b",
    re.I,
)


def is_letter_eligible_for_index(letter: dict) -> bool:
    """Whether a vault letter row should appear in letter_index / fund aggregates.

    Missing ``letter_eligible`` used to default to include, which let stale
    conference/deck rows leak into the Letters table. Prefer an explicit flag,
    then document_type, then a filename safety net.
    """
    if is_letter_meta_entry(letter):
        return False
    if "letter_eligible" in letter:
        return bool(letter.get("letter_eligible"))
    doc_type = str(letter.get("document_type") or "").strip().lower()
    if doc_type in NONLETTER_DOCUMENT_TYPES:
        return False
    if doc_type in LETTERISH_DOCUMENT_TYPES:
        return True
    label_bits = [
        str(letter.get("fund") or ""),
        str(letter.get("fund_id") or ""),
        Path(str(letter.get("source_file") or letter.get("source_document") or "")).stem,
    ]
    label = " ".join(label_bits)
    if NONLETTER_FILENAME_HINT.search(label.replace("_", " ").replace("-", " ")):
        return False
    return True


def unique_tickers(values: list) -> list[str]:
    """Preserve first-seen order; drop empties and case-normalized duplicates."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        ticker = str(raw or "").strip().upper()
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        out.append(ticker)
    return out


def letter_document_label(letter: dict) -> str:
    """Short stem label so multi-issue funds (HFA/KEDM) stay distinguishable."""
    ref = str(letter.get("source_file") or letter.get("source_document") or "")
    stem = Path(ref.replace("\\", "/")).stem.strip()
    if not stem:
        return ""
    fund = str(letter.get("fund") or "").strip()
    fund_id = str(letter.get("fund_id") or "").strip()
    cleaned = stem
    for prefix in (fund, fund_id, fund.replace(" ", "-"), fund_id.replace("_", "-")):
        if not prefix:
            continue
        for sep in ("-", "_", " "):
            needle = f"{prefix}{sep}"
            if cleaned.lower().startswith(needle.lower()):
                cleaned = cleaned[len(needle) :].lstrip("-_ ")
                break
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -_")
    if len(cleaned) > 48:
        cleaned = cleaned[:45].rstrip() + "…"
    return cleaned


def canonicalize_letter_fund(letter: dict) -> dict:
    """Return a letter with legacy quarter-specific fund aliases collapsed."""
    fund_id, fund = canonicalize_fund_identity(letter.get("fund_id"), letter.get("fund"))
    if fund_id == letter.get("fund_id") and fund == letter.get("fund"):
        return letter
    return {**letter, "fund_id": fund_id, "fund": fund}


COMPANY_STOPWORDS = {
    "inc",
    "corp",
    "corporation",
    "company",
    "co",
    "limited",
    "ltd",
    "plc",
    "group",
    "holdings",
    "holding",
    "class",
    "ordinary",
    "common",
    "shares",
    "trust",
    "partners",
    "limited",
    "sa",
    "nv",
    "ag",
    "the",
    "and",
    "of",
}

NEWS_AXIS = {
    "earnings_material": "fundamentals",
    "regulatory": "risk",
    "ai_material": "catalyst",
    "capital_allocation": "capital_allocation",
    "insider_block": "ownership",
    "mna": "catalyst",
    "legal": "risk",
    "index_inclusion": "catalyst",
    "index_addition": "catalyst",
    "index_deletion": "catalyst",
    "index_change": "catalyst",
}

INDEX_NEWS_CATEGORIES = {"index_inclusion", "index_addition", "index_deletion", "index_change"}

METRIC_LABELS = {
    "revenues": "Revenue",
    "revenue": "Revenue",
    "operating_income": "Operating income",
    "net_income": "Net income",
    "eps_basic": "Basic EPS",
    "eps_diluted": "Diluted EPS",
    "cash": "Cash",
    "stockholders_equity": "Equity",
    "long_term_debt": "Long-term debt",
}


def normalize_date(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", s)
    if m:
        return m.group(1)
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def parse_date(value):
    normalized = normalize_date(value)
    if not normalized:
        return None
    try:
        return datetime.strptime(normalized, "%Y-%m-%d").date()
    except ValueError:
        return None


def today_utc():
    return datetime.now(timezone.utc).date()


def to_float(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        ref = path_to_letters_ref(path) or path_to_podcasts_ref(path)
        if ref:
            return ref
        return str(path).replace("\\", "/")


def source_document_ref(ref: str | None) -> str | None:
    """Prefer the human-readable source document over extracted text/inventory files."""
    if not ref:
        return None
    clean = str(ref).strip()
    if not clean:
        return None
    if clean.startswith(("http://", "https://")):
        return clean
    base = clean.split("#", 1)[0].replace("\\", "/")
    suffix = f"#{clean.split('#', 1)[1]}" if "#" in clean else ""
    # Podcast transcripts live in the vault; keep logical .txt/.meta refs (no PDF twin).
    if base.startswith("_system/reference/podcasts/"):
        return base + suffix
    path = ROOT / base
    if "superinvestor-letters" in base and path.suffix.lower() in {".txt", ".md"}:
        return relative_path(path.with_suffix(".pdf")) + suffix
    candidates: list[Path] = []
    if base.endswith(".pdf.txt"):
        candidates.append(ROOT / base[: -len(".txt")])
    if path.suffix.lower() in {".txt", ".md"}:
        candidates.append(path.with_suffix(".pdf"))
    if path.suffix.lower() not in {".json"}:
        candidates.append(path)
    for candidate in candidates:
        if candidate.exists():
            return relative_path(candidate) + suffix
    return clean


def evidence_url(ref: str | None, letter: dict | None = None) -> str | None:
    if letter:
        source_ref = source_document_ref(letter.get("source_document") or letter.get("source_file"))
        return letter_evidence_url(letter, GITHUB_REPO, source_ref)
    doc_ref = source_document_ref(ref)
    if not doc_ref:
        return None
    return best_document_url(doc_ref, GITHUB_REPO)


def evidence_label(ref: str | None, letter: dict | None = None, url: str | None = None) -> str:
    if letter:
        source_ref = source_document_ref(letter.get("source_document") or letter.get("source_file"))
        resolved = url or letter_evidence_url(letter, GITHUB_REPO, source_ref)
        return letter_evidence_label(resolved, source_ref)
    doc_ref = source_document_ref(ref)
    if not doc_ref:
        return "source"
    resolved = url or best_document_url(doc_ref, GITHUB_REPO)
    if resolved and "superinvestor-letters" in str(doc_ref):
        return letter_evidence_label(resolved, doc_ref)
    return best_document_label(doc_ref)


def letter_evidence_fields(letter: dict) -> dict:
    source_ref = source_document_ref(letter.get("source_document") or letter.get("source_file"))
    url = letter_evidence_url(letter, GITHUB_REPO, source_ref)
    return {
        "evidence_ref": source_ref,
        "evidence_url": url,
        "evidence_label": letter_evidence_label(url, source_ref),
        "source_document": source_ref,
    }


def evidence_document_id(ref: str | None) -> str | None:
    doc_ref = source_document_ref(ref)
    if not doc_ref:
        return None
    return document_id_for_ref(doc_ref)


def short_text(value: str | None, limit: int = 260) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def valid_ticker(value: str | None) -> bool:
    return bool(value and VALID_TICKER_RE.match(str(value).upper()))


def load_json(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def prior_letter_count(prior: dict | None) -> int:
    if not prior:
        return 0
    return int(prior.get("letter_count") or len(prior.get("letter_index") or []))


def count_vault_letters() -> int:
    letters_doc = load_json(LETTERS_INSIGHTS) or {"letters": []}
    letters = [
        letter
        for letter in (letters_doc.get("letters") or [])
        if is_letter_eligible_for_index(letter)
    ]
    return len(letters)


def letter_corpus_floor(document: dict | None) -> int:
    policy_version = int((document or {}).get("classification_policy_version") or 0)
    return MIN_CLASSIFIED_LETTER_CORPUS if policy_version >= 4 else MIN_LETTER_CORPUS


# A rebuilt corpus may be LARGER and still worse. Discussant attribution is the
# expensive part -- a letter only yields a discussant if its position passes
# strong_letter_ticker_evidence -- and an unclassified bulk import raises the
# letter count while producing almost none. Observed 2026-08-11: the vault went
# 12,808 -> 18,889 letters and ticker_discussants collapsed 648 -> 130, because
# `vault_count >= prior_count` returned "vault corpus current" and handed the
# richer field over to the poorer rebuild. Count is a proxy for the corpus;
# it is not a proxy for what the corpus yields.
DISCUSSANT_REGRESSION_RATIO = 0.75
# Podcast discovery adds episodes every week and upstream occasionally prunes a
# few, so a small dip is normal. A drop past this is not drift, it is a lane
# rebuilding from a vault it never cloned -- the 3,711 -> 3,601 regression on
# 2026-08-20 was 97%, which is why the threshold sits close to 1.
PODCAST_REGRESSION_RATIO = 0.98


def prior_discussant_count(prior: dict | None) -> int:
    return len((prior or {}).get("ticker_discussants") or {})


def should_preserve_letter_corpus(
    prior: dict | None,
    vault_count: int,
    rebuilt_discussants: int | None = None,
) -> tuple[bool, str]:
    prior_count = prior_letter_count(prior)
    corpus_floor = letter_corpus_floor(prior)
    if prior_count < corpus_floor:
        return False, f"prior corpus {prior_count} below preserve floor {corpus_floor}"
    # Quality check runs BEFORE the count check: a bigger corpus that yields
    # materially fewer discussants is a regression wearing a growth costume.
    prior_disc = prior_discussant_count(prior)
    if (
        rebuilt_discussants is not None
        and prior_disc > 0
        and rebuilt_discussants < int(prior_disc * DISCUSSANT_REGRESSION_RATIO)
    ):
        return True, (
            f"rebuild yields {rebuilt_discussants} ticker_discussants vs prior "
            f"{prior_disc} (vault {vault_count} letters vs prior {prior_count}); "
            "corpus grew but attribution regressed"
        )
    if vault_count >= prior_count:
        return False, "vault corpus current"
    if vault_count < corpus_floor:
        return True, f"vault {vault_count} letters below floor {corpus_floor} (prior {prior_count})"
    if vault_count < int(prior_count * LETTER_REGRESSION_RATIO):
        return True, f"vault {vault_count} regressed from prior {prior_count}"
    return False, "vault within tolerance of prior"


def can_replace_preserved_letter_corpus(source_doc: dict, vault_count: int) -> bool:
    """Only replace a committed corpus with a complete classified vault rebuild."""
    policy_version = int(source_doc.get("classification_policy_version") or 0)
    return policy_version >= 4 and vault_count >= MIN_CLASSIFIED_LETTER_CORPUS


def load_preserved_letter_records() -> list[dict]:
    archive = load_json(ARCHIVE_OUTPUT)
    if not isinstance(archive, dict):
        return []
    records = archive.get("records") or []
    return [record for record in records if record.get("source") == "superinvestor_letter"]


def load_prior_insights() -> dict | None:
    """Prior payload for the corpus-preservation checks.

    insights.json is a 72MB monolith that duplicates the per-section shards
    already committed under dashboard/data/insights/. Dropping it outright is
    not safe: `prior` is the baseline `should_preserve_letter_corpus` and the
    ticker_discussants guard compare against, and with no prior every check
    reads as "nothing to protect" -- so a sparse or unclassified rebuild would
    replace a good corpus unopposed. Reconstruct the handful of fields those
    checks need from the shards when the monolith is absent.
    """
    prior = load_json(OUTPUT)
    if isinstance(prior, dict) and prior:
        return prior

    shard_dir = OUTPUT.parent / "insights"
    if not shard_dir.is_dir():
        return None
    merged: dict = {}
    for name in ("letters", "consensus", "registry", "profiles", "tickers"):
        shard = load_json(shard_dir / f"{name}.json")
        if isinstance(shard, dict):
            merged.update({k: v for k, v in shard.items() if k != "generated_at"})
    if not merged:
        return None
    merged.setdefault("letter_count", len(merged.get("letter_index") or []))
    print(
        f"prior insights reconstructed from committed shards "
        f"(letters={merged['letter_count']}, "
        f"ticker_discussants={len(merged.get('ticker_discussants') or {})}); "
        f"{OUTPUT.name} absent",
        file=sys.stderr,
    )
    return merged


def preserved_letter_payload_fields(prior: dict) -> dict:
    keys = (
        "classification_policy_version",
        "letter_count",
        "letter_index",
        "consensus",
        "fund_registry",
        "fund_profiles",
        "fund_identity_audit",
        "ticker_discussants",
    )
    return {key: prior[key] for key in keys if key in prior}


def insight_record(**kwargs) -> dict:
    base = {
        "in_base_irr": False,
        "confidence": "med",
        "event_type": None,
        "impact_axis": None,
    }
    base.update(kwargs)
    if base.get("as_of"):
        base["as_of"] = normalize_date(base.get("as_of")) or base.get("as_of")
    return base


INVERTED_TREND_METRICS = {"long_term_debt"}


# Flow metrics carry the operating signal; balance-sheet drift stays in the
# Inflections tab but does not flood the insights event stream.
INSIGHT_TREND_METRICS = {
    "revenues",
    "revenue",
    "operating_income",
    "net_income",
    "eps_basic",
    "cfo",
    "news_flow",
    "op_margin",
    "cfo_margin",
    "core_business",
    "growth_regime",
}
MAX_INFLECTION_EVENTS_PER_TICKER = 2


def metric_base_name(metric: str) -> str:
    return str(metric or "").split(".")[-1]


def _kpi_growth_text(metric: dict) -> str:
    growth_latest = metric.get("growth_latest")
    growth_prior = metric.get("growth_prior")
    if growth_latest is None or growth_prior is None:
        return "recent periods"
    yoy = metric.get("basis") == "yoy"
    if metric.get("mode") == "diff":
        return f"{growth_prior:+.0f} to {growth_latest:+.0f} per period"
    suffix = " YoY" if yoy else ""
    return f"{growth_prior:+.1%} to {growth_latest:+.1%}{suffix}"


def _kpi_inflection_claim(metric: dict, *, source_label: str) -> str:
    summary = (metric.get("human_summary") or "").strip()
    if summary:
        return f"{summary} Source: {source_label}."

    label = metric.get("label") or metric.get("metric") or "KPI"
    trend = metric.get("direction") or "steady"
    growth_text = _kpi_growth_text(metric)
    signal_tier = metric.get("signal_tier") or "steady"
    if metric.get("signal_type") == "regime":
        baseline = metric.get("baseline_median")
        baseline_text = f" (baseline median {baseline:+.1%} YoY)" if baseline is not None else ""
        persistence = (
            "for two consecutive quarters"
            if signal_tier == "confirmed"
            else "in the latest quarter"
        )
        return (
            f"{label}: YoY growth moved to {growth_text}{baseline_text} {persistence}. "
            f"Source: {source_label}."
        )
    persistence = (
        "for two consecutive quarters"
        if signal_tier == "confirmed"
        else "in the latest quarter"
    )
    members = metric.get("composite_members") or []
    if metric.get("composite") and members:
        member_labels = ", ".join(m.replace("_", " ") for m in members[:4])
        lead = (
            f"Core operating metrics ({member_labels}) are {trend} together — "
            f"growth moved from {growth_text} {persistence}"
        )
    else:
        lead = f"{label} growth moved from {growth_text} {persistence}"
    ttm_note = ""
    if metric.get("ttm_agrees") is True:
        ttm_note = " Trailing-twelve-month growth confirms the same direction."
    elif metric.get("ttm_agrees") is False:
        ttm_note = " Trailing-twelve-month growth does not yet confirm."
    return f"{lead}.{ttm_note} Source: {source_label}."


def from_kpi_trends(doc: dict | None) -> list[dict]:
    """Turn second-derivative KPI signals into ranked inflection records."""
    out: list[dict] = []
    for ticker, entry in ((doc or {}).get("by_ticker") or {}).items():
        candidates = []
        for metric in entry.get("metrics") or []:
            direction_raw = metric.get("direction")
            is_regime = metric.get("signal_type") == "regime"
            if is_regime:
                if direction_raw not in ("downshift", "upshift"):
                    continue
            elif direction_raw not in ("accelerating", "decelerating"):
                continue
            if not metric.get("display"):
                continue
            base_name = str(metric.get("metric") or "").split(".")[-1]
            if (
                base_name not in INSIGHT_TREND_METRICS
                and not str(metric.get("metric") or "").startswith("growth_regime.")
                and metric.get("source") != "equity_model"
            ):
                continue
            if metric.get("tier") == "excluded" or metric.get("stale"):
                continue
            metric_strength = metric.get("strength")
            if metric_strength is None:
                metric_strength = abs(metric.get("accel") or 0) / max(metric.get("threshold") or 1e-9, 1e-9)
            signal_tier = metric.get("signal_tier") or "steady"
            rank = metric_strength + (2.0 if metric.get("composite") else 0.0) + (1.5 if is_regime else 0.0) + (1.0 if signal_tier == "confirmed" else 0.0)
            candidates.append((rank, metric))
        candidates.sort(key=lambda x: -x[0])
        for _rank, metric in candidates[:MAX_INFLECTION_EVENTS_PER_TICKER]:
            is_regime = metric.get("signal_type") == "regime"
            trend = metric.get("direction")
            points = metric.get("points") or []
            as_of = metric.get("as_of") or (points[-1].get("period") if points else None) or (doc or {}).get("generated_at")
            label = metric.get("label") or metric.get("metric") or "KPI"
            base_name = metric_base_name(metric.get("metric") or "")
            good_when_up = base_name not in INVERTED_TREND_METRICS
            if is_regime:
                direction = "bearish" if trend == "downshift" else "bullish"
                title = f"{label}"
                event_type = "regime_shift"
            else:
                if trend == "accelerating":
                    direction = "bullish" if good_when_up else "bearish"
                else:
                    direction = "bearish" if good_when_up else "bullish"
                title = f"{label} {trend}"
                event_type = "inflection"
            source_label = {
                "sec_fundamentals": "SEC XBRL quarterly filings",
                "equity_model": "the equity model",
                "news_flow": "news-flow counts",
            }.get(metric.get("source") or "", "the underlying series")
            confidence = metric.get("confidence") or "med"
            out.append(
                insight_record(
                    source="kpi_trend",
                    as_of=as_of,
                    scope="ticker",
                    ref=str(ticker).upper(),
                    title=title,
                    claim=_kpi_inflection_claim(metric, source_label=source_label),
                    direction=direction,
                    confidence=confidence,
                    evidence_ref=metric.get("evidence_ref"),
                    event_type=event_type,
                    impact_axis="fundamentals",
                    trend=trend,
                    trend_metric=metric.get("metric"),
                    trend_points=points[-8:],
                    trend_accel=metric.get("accel"),
                    trend_basis=metric.get("basis"),
                    trend_source=metric.get("source"),
                    trend_signal_tier=metric.get("signal_tier"),
                    trend_composite=metric.get("composite"),
                )
            )

        leadership = entry.get("leadership_risk") or {}
        if leadership.get("level") in ("elevated", "watch"):
            factors = leadership.get("factors") or []
            factor_text = "; ".join(f.get("title", "") for f in factors[:2] if f.get("title"))
            out.append(
                insight_record(
                    source="kpi_trend",
                    as_of=(factors[0].get("as_of") if factors else None) or (doc or {}).get("generated_at"),
                    scope="ticker",
                    ref=str(ticker).upper(),
                    title=leadership.get("label") or "Leadership risk",
                    claim=f"{leadership.get('label')}. {factor_text}".strip(),
                    direction="bearish" if leadership.get("level") == "elevated" else "neutral",
                    confidence="high" if leadership.get("level") == "elevated" else "med",
                    event_type="leadership_risk",
                    impact_axis="governance",
                )
            )
    return out


def from_superinvestor_letters(doc: dict) -> list[dict]:
    out: list[dict] = []
    for letter in doc.get("letters") or []:
        fund = letter.get("fund", "Unknown")
        fund_id = letter.get("fund_id") or fund
        as_of = letter.get("letter_date")
        source_ref = source_document_ref(letter.get("source_document") or letter.get("source_file"))
        letter_ev = letter_evidence_fields(letter)
        for th in letter.get("themes") or []:
            out.append(
                insight_record(
                    source="superinvestor_letter",
                    as_of=as_of,
                    scope="theme",
                    ref=th.get("theme"),
                    claim=f"{fund}: {th.get('theme')} — {th.get('stance', 'neutral')}",
                    direction={"constructive": "bullish", "cautious": "bearish"}.get(th.get("stance"), "neutral"),
                    evidence_ref=source_ref,
                    evidence_url=letter_ev["evidence_url"],
                    evidence_label=letter_ev["evidence_label"],
                    event_type="letter_theme",
                    impact_axis="macro",
                    fund=fund,
                    fund_id=fund_id,
                    quarter=letter.get("quarter"),
                    tickers=th.get("tickers") or [],
                )
            )
        for pos in letter.get("positions") or []:
            tk = pos.get("ticker")
            if not tk:
                continue
            action = pos.get("action", "discussed")
            commentary = pos.get("commentary") or pos.get("thesis") or ""
            claim = (
                format_letter_claim(tk, fund, action, letter.get("quarter"), commentary)
                if commentary
                else f"{fund} {action} {tk}"
            )
            out.append(
                insight_record(
                    source="superinvestor_letter",
                    as_of=as_of,
                    scope="ticker",
                    ref=tk,
                    claim=claim,
                    direction={"add": "bullish", "trim": "bearish"}.get(action, "neutral"),
                    evidence_ref=source_ref,
                    evidence_url=letter_ev["evidence_url"],
                    evidence_label=letter_ev["evidence_label"],
                    event_type="letter_position",
                    impact_axis="ownership",
                    fund=fund,
                    fund_id=fund_id,
                    quarter=letter.get("quarter"),
                    action=action,
                    position_action=action,
                    commentary=commentary,
                )
            )
    return out


def load_podcast_insights_doc() -> dict:
    """Prefer vault catalog; fall back to slim CI index (no highlight/theme fan-out)."""
    doc = load_json(PODCASTS_INSIGHTS)
    if isinstance(doc, dict) and (doc.get("episodes") or doc.get("episode_count")):
        return doc
    # Legacy full mirror (pre-de-dupe) still readable if present
    legacy = load_json(PODCASTS_INSIGHTS_MIRROR)
    if isinstance(legacy, dict) and (legacy.get("episodes") or legacy.get("episode_count")):
        return legacy
    slim = load_json(PODCASTS_INSIGHTS_INDEX_MIRROR)
    if isinstance(slim, dict) and (slim.get("podcast_index") or slim.get("episode_count")):
        rows = list(slim.get("podcast_index") or [])
        episodes = []
        for row in rows:
            guests = row.get("guests") or []
            guest_objs = [
                {"display": g} if not isinstance(g, dict) else g for g in guests
            ]
            tickers = list(row.get("tickers") or [])
            hc = int(row.get("highlight_count") or 0)
            episodes.append(
                {
                    "episode_id": row.get("episode_id"),
                    "show_id": row.get("show_id"),
                    "show_title": row.get("show_title"),
                    "title": row.get("title"),
                    "published": row.get("published"),
                    "tickers": tickers,
                    "guests": guest_objs,
                    "persona_ids": row.get("persona_ids") or [],
                    "has_pz_guest": bool(row.get("has_pz_guest")),
                    "has_officer_hit": bool(row.get("has_officer_hit")),
                    "near_universe": bool(row.get("near_universe")),
                    "in_book": bool(row.get("in_book")),
                    "highlights": [{"text": t} for t in (row.get("highlight_previews") or [])]
                    + ([{}] * max(0, hc - len(row.get("highlight_previews") or []))),
                    "themes": row.get("themes") or [],
                    "positions": [{"ticker": t, "action": "discussed"} for t in tickers],
                    "source_document": row.get("source_document"),
                    "link": row.get("link"),
                }
            )
        return {
            "generated_at": slim.get("generated_at"),
            "schema_version": slim.get("schema_version", 1),
            "schema_kind": "index_mirror",
            "episode_count": slim.get("episode_count") or len(episodes),
            "episodes": episodes,
            "podcast_index": rows,
        }
    return {"episodes": []}


def from_podcast_episodes(doc: dict) -> list[dict]:
    # Slim CI index has tickers but not full theme/position commentary — skip fan-out.
    if doc.get("schema_kind") == "index_mirror":
        return []
    out: list[dict] = []
    for ep in doc.get("episodes") or []:
        show = ep.get("show_title") or ep.get("show_id") or "Podcast"
        as_of = ep.get("published")
        source_ref = source_document_ref(ep.get("source_document"))
        guests = ep.get("guests") or []
        guest_labels = ", ".join(
            g.get("display") or g.get("guest_id") or "" for g in guests if g.get("display") or g.get("guest_id")
        )
        persona_ids = ep.get("persona_ids") or []
        for th in ep.get("themes") or []:
            out.append(
                insight_record(
                    source="podcast_episode",
                    as_of=as_of,
                    scope="theme",
                    ref=th.get("theme"),
                    claim=f"{show}: {th.get('theme')} — {th.get('stance', 'neutral')}",
                    direction={"constructive": "bullish", "cautious": "bearish"}.get(
                        th.get("stance"), "neutral"
                    ),
                    evidence_ref=source_ref,
                    event_type="podcast_theme",
                    impact_axis="macro",
                    show=show,
                    show_id=ep.get("show_id"),
                    episode_id=ep.get("episode_id"),
                    title=ep.get("title"),
                    guests=guest_labels,
                    persona_ids=persona_ids,
                    has_pz_guest=bool(ep.get("has_pz_guest")),
                    has_officer_hit=bool(ep.get("has_officer_hit")),
                    near_universe=bool(ep.get("near_universe")),
                    tickers=th.get("tickers") or ep.get("tickers") or [],
                    in_base_irr=False,
                )
            )
        for pos in ep.get("positions") or []:
            tk = pos.get("ticker")
            if not tk:
                continue
            commentary = pos.get("commentary") or ""
            claim = f"{show} discussed {tk}"
            if guest_labels:
                claim += f" ({guest_labels})"
            if commentary:
                claim += f" — {commentary[:180]}"
            out.append(
                insight_record(
                    source="podcast_episode",
                    as_of=as_of,
                    scope="ticker",
                    ref=tk,
                    claim=claim,
                    direction="neutral",
                    evidence_ref=source_ref,
                    event_type="podcast_position",
                    impact_axis="variant_view",
                    show=show,
                    show_id=ep.get("show_id"),
                    episode_id=ep.get("episode_id"),
                    title=ep.get("title"),
                    guests=guest_labels,
                    persona_ids=persona_ids,
                    has_pz_guest=bool(ep.get("has_pz_guest")),
                    has_officer_hit=bool(ep.get("has_officer_hit")),
                    near_universe=bool(ep.get("near_universe")),
                    action=pos.get("action") or "discussed",
                    commentary=commentary,
                    in_base_irr=False,
                )
            )
        # Officer / near-universe company hits without positions still surface
        if not (ep.get("positions") or []) and (
            ep.get("has_officer_hit") or ep.get("has_pz_guest") or ep.get("near_universe")
        ):
            companies = ep.get("companies") or []
            for c in companies:
                tk = c.get("ticker") or c.get("company_key")
                if not tk:
                    continue
                out.append(
                    insight_record(
                        source="podcast_episode",
                        as_of=as_of,
                        scope="ticker" if c.get("ticker") else "theme",
                        ref=tk,
                        claim=f"{show}: officer/company episode — {ep.get('title') or tk}",
                        direction="neutral",
                        evidence_ref=source_ref,
                        event_type="podcast_officer",
                        impact_axis="variant_view",
                        show=show,
                        show_id=ep.get("show_id"),
                        episode_id=ep.get("episode_id"),
                        title=ep.get("title"),
                        guests=guest_labels,
                        persona_ids=persona_ids,
                        has_pz_guest=bool(ep.get("has_pz_guest")),
                        has_officer_hit=True,
                        near_universe=bool(c.get("near_universe") or ep.get("near_universe")),
                        in_book=bool(c.get("in_book")),
                        in_base_irr=False,
                    )
                )
    return out


def podcast_index_rows(doc: dict) -> list[dict]:
    if doc.get("schema_kind") == "index_mirror" and doc.get("podcast_index"):
        return list(doc["podcast_index"])
    try:
        from build_podcast_insights import index_row_from_episode  # noqa: WPS433
    except Exception:
        index_row_from_episode = None  # type: ignore
    rows = []
    for ep in doc.get("episodes") or []:
        if index_row_from_episode is not None:
            rows.append(index_row_from_episode(ep))
            continue
        rows.append(
            {
                "episode_id": ep.get("episode_id"),
                "show_id": ep.get("show_id"),
                "show_title": ep.get("show_title"),
                "title": ep.get("title"),
                "published": ep.get("published"),
                "tickers": ep.get("tickers") or [],
                "guests": [g.get("display") or g.get("guest_id") for g in (ep.get("guests") or [])],
                "persona_ids": ep.get("persona_ids") or [],
                "has_pz_guest": bool(ep.get("has_pz_guest")),
                "has_officer_hit": bool(ep.get("has_officer_hit")),
                "near_universe": bool(ep.get("near_universe")),
                "in_book": bool(ep.get("in_book")),
                "highlight_count": len(ep.get("highlights") or []),
                "highlight_previews": [
                    (h.get("quote") or h.get("text") or "")[:220]
                    for h in (ep.get("highlights") or [])[:2]
                    if isinstance(h, dict) and (h.get("quote") or h.get("text"))
                ],
                "themes": [
                    {"theme": th.get("theme"), "stance": th.get("stance") or "neutral"}
                    for th in (ep.get("themes") or [])[:6]
                    if isinstance(th, dict) and th.get("theme")
                ],
                "source_document": ep.get("source_document"),
                "link": ep.get("link"),
            }
        )
    return rows


def podcast_by_show(doc: dict) -> dict:
    """Show browser index: episode_ids only (group client-side from podcast_index)."""
    by: dict[str, dict] = {}
    for ep in doc.get("episodes") or []:
        sid = ep.get("show_id") or "unknown"
        profile = by.setdefault(
            sid,
            {
                "show_id": sid,
                "show_title": ep.get("show_title") or sid,
                "episode_count": 0,
                "episode_ids": [],
            },
        )
        eid = ep.get("episode_id")
        if eid:
            profile["episode_ids"].append(eid)
        profile["episode_count"] = len(profile["episode_ids"])
    return by


def from_valuation_context(ticker: str, val: dict) -> list[dict]:
    """Ticker valuation context for Insights.

    Portfolio macro lives in dashboard ``portfolio_macro_regime`` (not per-ticker
    macro fan-out). Only non-negligible insider conviction bands are emitted here.
    """
    out: list[dict] = []
    overlay = val.get("context_overlay") or {}
    as_of = overlay.get("as_of") or val.get("as_of")
    # Intentionally skip theme/macro indicators — see macro_regime_panel.py.

    insider = val.get("insider_signal") or {}
    if insider.get("band") and insider.get("band") != "negligible":
        ics = insider.get("ics")
        try:
            ics_f = float(ics) if ics is not None else None
        except (TypeError, ValueError):
            ics_f = None
        scored = score_form4_event(
            {
                "action": "purchase" if (ics_f or 0) >= 4 else "sale",
                "transaction_code": "P" if (ics_f or 0) >= 4 else "S",
                "value_usd": None,
                "as_of": insider.get("as_of") or as_of,
                "ics": ics_f,
            },
            in_holdings=True,
            ics=ics_f,
        )
        out.append(
            insight_record(
                source="insider",
                as_of=insider.get("as_of") or as_of,
                scope="ticker",
                ref=ticker,
                title=f"Insider conviction: {insider.get('band')}",
                claim=f"Insider conviction band: {insider.get('band')} (ICS {insider.get('ics')})",
                direction="bearish" if (ics_f or 0) < 4 else "bullish",
                evidence_ref=f"{ticker}/research/valuation.json#insider_signal",
                event_type="insider_signal",
                impact_axis="ownership",
                confidence="low",
                ics=ics_f,
                band=insider.get("band"),
                materiality=scored["materiality"],
                materiality_components=scored["materiality_components"],
                tier=scored["tier"],
            )
        )
    return out


def from_third_party(ticker_dir: Path, ticker: str) -> list[dict]:
    out: list[dict] = []
    inv_path = ticker_dir / "third-party-analyses" / "source_inventory_2026-06-07.json"
    if not inv_path.exists():
        invs = sorted(ticker_dir.glob("third-party-analyses/source_inventory_*.json"), reverse=True)
        inv_path = invs[0] if invs else None
    if not inv_path or not inv_path.exists():
        return out
    doc = load_json(inv_path)
    if not isinstance(doc, dict):
        return out
    seen_refs: set[str] = set()
    for src in doc.get("sources") or []:
        title = src.get("title") or src.get("source") or "Third party"
        raw_ref = src.get("url") or src.get("source_url") or src.get("path")
        source_ref = source_document_ref(raw_ref) or relative_path(inv_path)
        if source_ref in seen_refs:
            continue
        seen_refs.add(source_ref)
        status = src.get("status") or "context"
        confidence = "med" if status in {"approved", "context"} else "low"
        use = src.get("use") or status
        out.append(
            insight_record(
                source="third_party",
                as_of=src.get("date") or doc.get("as_of") or doc.get("scan_date"),
                scope="ticker",
                ref=ticker,
                title=title,
                claim=f"{title} ({status}; {use})",
                direction="neutral",
                evidence_ref=source_ref,
                evidence_url=evidence_url(source_ref),
                evidence_label=evidence_label(source_ref),
                inventory_ref=relative_path(inv_path),
                event_type="research_source",
                impact_axis="variant_view",
                confidence=confidence,
                publisher=src.get("source_id") or src.get("publisher") or "Third-party research",
                source_path=raw_ref,
                document_type=Path(str(source_ref).split("#", 1)[0]).suffix.lower().lstrip("."),
            )
        )
    return out[:5]


def from_sumzero_ideas(doc: dict | None, front_tickers: set[str]) -> list[dict]:
    if not isinstance(doc, dict):
        return []
    out: list[dict] = []
    for item in doc.get("matched_documents") or []:
        match = item.get("match") or {}
        ticker = str(match.get("ticker") or "").upper()
        if ticker not in front_tickers or not valid_ticker(ticker):
            continue
        title = item.get("title") or item.get("filename") or "SumZero idea"
        direction = item.get("direction") or "neutral"
        match_type = match.get("match_type") or "archive_match"
        evidence = item.get("local_pdf_path") or f"{relative_path(SUMZERO_INDEX)}#document-{item.get('id')}"
        if direction == "bearish":
            event_type = "sumzero_short"
            axis = "risk"
            claim = f"SumZero short/risk idea indexed: {title}."
        elif direction == "bullish":
            event_type = "sumzero_long"
            axis = "variant_view"
            claim = f"SumZero long/variant idea indexed: {title}."
        else:
            event_type = "sumzero_idea"
            axis = "variant_view"
            claim = f"SumZero outside research idea indexed: {title}."
        out.append(
            insight_record(
                source="sumzero_research",
                as_of=item.get("document_date") or item.get("last_modified"),
                scope="ticker",
                ref=ticker,
                title=f"SumZero: {title}",
                claim=(
                    f"{claim} Match: {match_type.replace('_', ' ')}"
                    f"{' via ' + match.get('matched_alias') if match.get('matched_alias') else ''}; "
                    f"archive member `{item.get('archive_member')}`."
                ),
                direction=direction,
                evidence_ref=evidence,
                evidence_url=evidence_url(evidence),
                evidence_label=evidence_label(evidence),
                evidence_document_id=evidence_document_id(evidence),
                event_type=event_type,
                impact_axis=axis,
                confidence=match.get("confidence") or "med",
                publisher="SumZero Ideas",
                document_type=item.get("document_type"),
                archive_member=item.get("archive_member"),
                theme_tags=item.get("theme_tags") or [],
                match_type=match_type,
            )
        )
    out.sort(key=lambda r: (r.get("as_of") or "", confidence_weight(r.get("confidence"))), reverse=True)
    return out[:250]


def from_theme_panel() -> list[dict]:
    out: list[dict] = []
    if not THEMES_DIR.exists():
        return out
    for csv_path in THEMES_DIR.glob("*.csv"):
        try:
            lines = csv_path.read_text(encoding="utf-8").strip().splitlines()
            if len(lines) < 2:
                continue
            header = [h.strip().lower() for h in lines[0].split(",")]
            last = lines[-1].split(",")
            date_idx = header.index("date") if "date" in header else 0
            val_idx = 1 if len(last) > 1 else 0
            out.append(
                insight_record(
                    source="theme",
                    as_of=last[date_idx].strip() if date_idx < len(last) else None,
                    scope="portfolio",
                    ref=csv_path.stem,
                    claim=f"Theme panel {csv_path.stem}: latest {last[val_idx].strip()}",
                    direction="neutral",
                    evidence_ref=str(csv_path.relative_to(ROOT)).replace("\\", "/"),
                    event_type="macro_theme",
                    impact_axis="macro",
                    confidence="low",
                )
            )
        except (ValueError, IndexError):
            continue
    return out


def _index_action_from_text(text: str) -> str | None:
    low = (text or "").lower()
    if re.search(r"\b(removed|deleted|dropped|deletion|exclusion)\b", low):
        return "delete"
    if re.search(r"\b(reclass|reshuffl|index\s+shift|index\s+moves?|index\s+change)\b", low):
        return "reclassify"
    if re.search(r"\b(added|joins|joining|inclusion|addition|will replace|replaces)\b", low):
        return "add"
    return None


def from_news(doc: dict) -> list[dict]:
    """News insights. Index changes only when subject-gated extract matches a portfolio ticker."""
    try:
        from index_event_extract import extract_index_events
    except ImportError:
        extract_index_events = None  # type: ignore

    out: list[dict] = []
    for item in doc.get("items") or doc.get("news") or []:
        tickers = item.get("tickers") or ([item.get("ticker")] if item.get("ticker") else [])
        if not tickers:
            tickers = [None]
        category = item.get("category") or "news"
        title = item.get("title") or "News item"
        summary = item.get("summary") or title
        event_type = category
        extra: dict = {}
        subject_events: list[dict] = []
        # Subject extract is the gate for any category (CPRT reclass often lands in management)
        if extract_index_events and any(tickers):
            subject_events = extract_index_events(
                title,
                summary,
                candidate_tickers=[t for t in tickers if t],
            )
            if subject_events:
                event_type = "index_change"
                extra["index_event"] = True
                extra["index_action"] = subject_events[0].get("action")
                extra["index_id"] = subject_events[0].get("index")
                extra["quality_gated"] = True
                tickers = [e["ticker"] for e in subject_events]
            elif category in INDEX_NEWS_CATEGORIES:
                # Index-tagged news without subject match stays ordinary (no SpaceX→AMZN)
                event_type = category
        elif category in INDEX_NEWS_CATEGORIES:
            # Fallback without extractor: do not promote to index_change
            event_type = category
        for ticker in tickers:
            rec = insight_record(
                source="news",
                as_of=item.get("published_utc") or item.get("date"),
                scope="ticker" if ticker else item.get("scope", "portfolio"),
                ref=str(ticker).upper() if ticker else item.get("title"),
                title=title,
                claim=summary,
                direction="neutral",
                evidence_ref=item.get("url"),
                evidence_url=item.get("url"),
                evidence_label="article",
                event_type=event_type,
                impact_axis=NEWS_AXIS.get(category, "catalyst") if event_type != "index_change" else "catalyst",
                publisher=item.get("publisher") or item.get("source"),
                confidence="med" if float(item.get("confidence") or 0) >= 0.8 else "low",
                match_tier=item.get("match_tier"),
            )
            if extra:
                rec.update(extra)
            out.append(rec)
    return out[:120]


def from_index_membership(doc: dict) -> list[dict]:
    """Surface quality-gated index events from index_membership.json into the events feed."""
    out: list[dict] = []
    for ticker, row in (doc.get("by_ticker") or {}).items():
        for ev in row.get("confirmed_events") or []:
            if not (ev.get("confidence") == "provider_confirmed" or ev.get("quality_gated")):
                continue
            action = ev.get("action") or "change"
            index_id = ev.get("index") or "index"
            title = ev.get("title") or f"{ticker} {action} {index_id}"
            out.append(
                insight_record(
                    source="index_membership",
                    as_of=ev.get("announced") or ev.get("effective") or doc.get("as_of"),
                    scope="ticker",
                    ref=str(ticker).upper(),
                    title=title,
                    claim=f"{action} {index_id}; effective {ev.get('effective') or 'TBD'} ({ev.get('confidence')})",
                    direction="bullish" if action == "add" else ("bearish" if action == "delete" else "neutral"),
                    evidence_ref=ev.get("source_url"),
                    evidence_url=ev.get("source_url"),
                    evidence_label="index_notice",
                    event_type="index_change",
                    impact_axis="catalyst",
                    confidence="high" if ev.get("confidence") == "provider_confirmed" else "med",
                    index_action=action,
                    index_id=index_id,
                    index_effective=ev.get("effective"),
                    index_event=True,
                    quality_gated=True,
                )
            )
    return out[:80]


def pct_change(current: float | None, prior: float | None) -> float | None:
    if current is None or prior in (None, 0):
        return None
    return (current - prior) / abs(prior) * 100.0


def filing_metric_confidence(metric: dict) -> str:
    parser_conf = str(metric.get("parser_confidence") or "low").lower()
    if parser_conf == "high":
        return "high"
    if parser_conf == "medium":
        return "med"
    return "low"


def filing_verification_block(ticker: str, doc: dict, metric: dict, name: str) -> dict:
    source_text = doc.get("source_text")
    filing_meta = doc.get("filing_meta") or filing_metadata_from_text_path(source_text)
    source_filing = doc.get("source_filing_ref") or source_filing_ref_from_text_path(ticker, source_text)
    extract_ref = None
    if source_text:
        extract_ref = f"{ticker}/research/{source_text}".replace("\\", "/")
    filing_label = filing_meta.get("filing_form") or "Filing"
    return {
        "filing_form": filing_meta.get("filing_form"),
        "filing_date": filing_meta.get("filing_date"),
        "period_end": filing_meta.get("period_end"),
        "xbrl_tag": metric.get("tag"),
        "metric": name,
        "prior_value": metric.get("prior"),
        "current_value": metric.get("current"),
        "unit": "USD thousands",
        "comparison": metric.get("comparison") or "YoY annual",
        "source_filing_ref": source_filing,
        "extract_ref": extract_ref,
        "extract_snippet": metric.get("extract_snippet"),
        "all_values": metric.get("all_values") or [],
        "parser_confidence": metric.get("parser_confidence") or "low",
        "parser_flags": metric.get("parser_flags") or [],
        "pair_score": metric.get("pair_score"),
        "source_label": filing_label,
    }


def filing_evidence_fields(ticker: str, doc: dict) -> dict:
    source_text = doc.get("source_text")
    source_filing = doc.get("source_filing_ref") or source_filing_ref_from_text_path(ticker, source_text)
    extract_ref = None
    if source_text:
        extract_ref = f"{ticker}/research/{source_text}".replace("\\", "/")
    filing_meta = doc.get("filing_meta") or filing_metadata_from_text_path(source_text)
    filing_label = filing_meta.get("filing_form") or "Filing"
    return {
        "source_filing_ref": source_filing,
        "extract_ref": extract_ref,
        "evidence_ref": source_filing or extract_ref,
        "evidence_url": evidence_url(source_filing or extract_ref),
        "evidence_label": filing_label if source_filing else "extract",
        "extract_url": evidence_url(extract_ref),
        "extract_label": "extract",
        "filing_label": filing_label,
    }


def metric_direction(metric: str, change: float) -> str:
    if metric == "long_term_debt":
        return "bearish" if change > 0 else "bullish"
    if metric in {"cash", "stockholders_equity"}:
        return "bullish" if change > 0 else "bearish"
    return "bullish" if change > 0 else "bearish"


def from_filing_facts(ticker_dir: Path, ticker: str) -> list[dict]:
    evidence_dir = ticker_dir / "research" / "evidence"
    if not evidence_dir.exists():
        return []
    files = sorted(evidence_dir.glob("filing_facts_*.json"), reverse=True)
    if not files:
        return []
    latest = files[0]
    doc = load_json(latest)
    if not isinstance(doc, dict):
        return []

    metrics = doc.get("metrics") or {}
    evidence = filing_evidence_fields(ticker, doc)
    candidates: list[dict] = []
    for name, metric in metrics.items():
        if not isinstance(metric, dict):
            continue
        current = to_float(metric.get("current"))
        prior = to_float(metric.get("prior"))
        change = pct_change(current, prior)
        if change is None and current is not None and prior is None and current > 0 and name == "long_term_debt":
            candidates.append(
                {
                    "name": name,
                    "label": METRIC_LABELS.get(name, name.replace("_", " ").title()),
                    "current": current,
                    "prior": prior,
                    "change": None,
                    "abs_change": current,
                    "change_type": "new_balance",
                    "metric": metric,
                }
            )
            continue
        if change is None:
            continue
        if not filing_metric_passes_sanity(name, metric, change):
            continue
        if not filing_metric_passes_magnitude(name, metric, change):
            continue
        label = METRIC_LABELS.get(name, name.replace("_", " ").title())
        candidates.append(
            {
                "name": name,
                "label": label,
                "current": current,
                "prior": prior,
                "change": change,
                "abs_change": abs(change),
                "metric": metric,
            }
        )

    out: list[dict] = []
    for item in sorted(candidates, key=lambda x: x["abs_change"], reverse=True)[:2]:
        metric = item["metric"]
        verification = filing_verification_block(ticker, doc, metric, item["name"])
        needs_review = filing_metric_needs_review(metric, item.get("change"))
        confidence = filing_metric_confidence(metric)
        change = item.get("change")
        if item.get("change_type") == "new_balance":
            title = f"{item['label']} newly reported at {item['current']:,.1f}"
            claim = (
                f"{item['label']} was not reported in the prior period and is now "
                f"{item['current']:,.1f} (USD thousands)."
            )
            direction = "bearish" if item["name"] == "long_term_debt" else "bullish"
        else:
            title = f"{item['label']} {'up' if change > 0 else 'down'} {abs(change):.0f}%"
            claim = (
                f"{item['label']} moved {change:+.1f}% versus the prior period "
                f"({item['prior']:,.1f} to {item['current']:,.1f})."
            )
            direction = metric_direction(item["name"], change)
        out.append(
            insight_record(
                source="filing",
                as_of=doc.get("as_of"),
                scope="ticker",
                ref=ticker,
                title=title,
                claim=claim,
                direction=direction,
                evidence_ref=evidence.get("source_filing_ref") or evidence.get("extract_ref") or relative_path(latest),
                evidence_url=evidence.get("evidence_url"),
                evidence_label=evidence.get("evidence_label"),
                source_filing_ref=evidence.get("source_filing_ref"),
                extract_ref=evidence.get("extract_ref"),
                extract_url=evidence.get("extract_url"),
                extract_label=evidence.get("extract_label"),
                verification=verification,
                needs_review=needs_review,
                event_type="filing_metric",
                impact_axis="fundamentals",
                confidence=confidence,
                metric_name=item["name"],
                change_pct=change,
                prior_value=item["prior"],
                current_value=item["current"],
            )
        )

    if not out and metrics:
        evidence = filing_evidence_fields(ticker, doc)
        out.append(
            insight_record(
                source="filing",
                as_of=doc.get("as_of"),
                scope="ticker",
                ref=ticker,
                title="Filing facts refreshed",
                claim=f"Filing parser captured {len(metrics)} metrics from the latest local evidence file.",
                direction="neutral",
                evidence_ref=evidence.get("source_filing_ref") or evidence.get("extract_ref") or relative_path(latest),
                evidence_url=evidence.get("evidence_url"),
                evidence_label=evidence.get("evidence_label") or "Filing",
                source_filing_ref=evidence.get("source_filing_ref"),
                extract_ref=evidence.get("extract_ref"),
                extract_url=evidence.get("extract_url"),
                event_type="filing_refresh",
                impact_axis="fundamentals",
                confidence="low",
                needs_review=False,
            )
        )
    return out


def insider_csv_path(csv_ref: str | None) -> Path | None:
    if not csv_ref:
        return None
    ref = Path(str(csv_ref).replace("\\", "/"))
    if ref.parts and ref.parts[0] == "insider":
        return INSIDER_DIR.parent / ref
    return INSIDER_DIR / ref


def _insider_ics_for_ticker(ticker: str) -> float | None:
    val_path = ROOT / ticker / "research" / "valuation.json"
    if not val_path.exists():
        return None
    val = load_json(val_path)
    if not isinstance(val, dict):
        return None
    ics = (val.get("insider_signal") or {}).get("ics")
    try:
        return float(ics) if ics is not None else None
    except (TypeError, ValueError):
        return None


def from_insider_transactions(
    our_tickers: set[str],
    *,
    holdings_tickers: set[str] | None = None,
) -> list[dict]:
    manifest = load_json(INSIDER_MANIFEST)
    if not isinstance(manifest, dict):
        return []
    holdings = holdings_tickers or set()
    out: list[dict] = []
    for ticker, meta in (manifest.get("tickers") or {}).items():
        ticker = str(ticker).upper()
        if our_tickers and ticker not in our_tickers:
            continue
        csv_path = insider_csv_path((meta or {}).get("csv"))
        if not csv_path or not csv_path.exists():
            continue
        rows: list[dict] = []
        try:
            with csv_path.open(newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    code = (row.get("transaction_code") or "").upper()
                    acquired = (row.get("acquired_disposed") or "").upper()
                    value = abs(to_float(row.get("value_usd")) or 0.0)
                    if code not in {"P", "S"} and acquired not in {"A", "D"}:
                        continue
                    if value < 25000 and code != "P":
                        continue
                    rows.append(row)
        except OSError:
            continue
        grouped: dict[tuple, dict] = {}
        actors_by_day: dict[str, set[str]] = {}
        for row in rows:
            code = (row.get("transaction_code") or "").upper()
            acquired = (row.get("acquired_disposed") or "").upper()
            value = abs(to_float(row.get("value_usd")) or 0.0)
            if code not in {"P", "S"} and acquired not in {"A", "D"}:
                continue
            if value < 25000 and code != "P":
                continue
            is_buy = code == "P" or acquired == "A"
            action = "purchase" if is_buy else "sale"
            actor = short_text(row.get("insider") or "Insider", 80)
            as_of = normalize_date(row.get("filing_date") or row.get("transaction_date") or meta.get("as_of"))
            filing_ref = row.get("source_path") or relative_path(csv_path)
            is_10b5 = str(row.get("is_10b5_1") or "").lower() in {"1", "true", "yes"}
            key = (ticker, as_of or "", actor.lower(), action, filing_ref)
            bucket = grouped.setdefault(
                key,
                {
                    "ticker": ticker,
                    "as_of": as_of,
                    "actor": actor,
                    "action": action,
                    "filing_ref": filing_ref,
                    "shares": 0.0,
                    "value": 0.0,
                    "confidence": "low",
                    "transaction_code": code or ("P" if is_buy else "S"),
                    "acquired_disposed": acquired or ("A" if is_buy else "D"),
                    "is_10b5_1": is_10b5,
                    "is_director": str(row.get("is_director") or "").lower() in {"1", "true", "yes"},
                    "is_officer": str(row.get("is_officer") or "").lower() in {"1", "true", "yes"},
                    "title": row.get("officer_title") or row.get("title") or "",
                },
            )
            shares = to_float(row.get("shares")) or 0.0
            bucket["shares"] += shares
            bucket["value"] += value
            bucket["is_10b5_1"] = bucket["is_10b5_1"] or is_10b5
            if value >= 100000:
                bucket["confidence"] = "med"
            if as_of:
                actors_by_day.setdefault(as_of, set()).add(actor.lower())
        distinct_insiders = len({b["actor"].lower() for b in grouped.values()})
        cluster_size = max((len(v) for v in actors_by_day.values()), default=1)
        ics = _insider_ics_for_ticker(ticker)
        in_holdings = ticker in holdings
        in_watchlist = bool(our_tickers and ticker in our_tickers and not in_holdings)
        ranked = sorted(grouped.values(), key=lambda b: (b["value"], b["as_of"] or ""), reverse=True)
        for bucket in ranked[:2]:
            value = bucket["value"]
            shares = bucket["shares"]
            value_text = f"${value:,.0f}" if value else "undisclosed value"
            share_text = f"{shares:,.0f} shares" if shares else "shares"
            score_row = {
                "action": bucket["action"],
                "transaction_code": bucket.get("transaction_code"),
                "acquired_disposed": bucket.get("acquired_disposed"),
                "value_usd": value,
                "as_of": bucket["as_of"] or meta.get("as_of"),
                "is_10b5_1": bucket.get("is_10b5_1"),
                "is_director": bucket.get("is_director"),
                "is_officer": bucket.get("is_officer"),
                "title": bucket.get("title"),
                "cluster_size": cluster_size,
                "distinct_insiders": distinct_insiders,
            }
            scored = score_form4_event(
                score_row,
                in_holdings=in_holdings,
                in_watchlist=in_watchlist,
                ics=ics,
            )
            out.append(
                insight_record(
                    source="insider",
                    as_of=bucket["as_of"] or meta.get("as_of"),
                    scope="ticker",
                    ref=ticker,
                    title=f"Insider {bucket['action']}: {bucket['actor']}",
                    claim=f"{bucket['actor']} reported an insider {bucket['action']} of {share_text} ({value_text}).",
                    direction="bullish" if bucket["action"] == "purchase" else "bearish",
                    evidence_ref=bucket["filing_ref"],
                    event_type="form4_transaction",
                    impact_axis="ownership",
                    confidence=bucket["confidence"],
                    value_usd=value,
                    action=bucket["action"],
                    ics=ics,
                    materiality=scored["materiality"],
                    materiality_components=scored["materiality_components"],
                    tier=scored["tier"],
                )
            )
    return out


def from_specialist_13f(our_tickers: set[str]) -> list[dict]:
    records_path = ROOT / "_system" / "reference" / "market-data" / "ownership" / "records" / "latest.json"
    doc = load_json(records_path)
    if not isinstance(doc, dict):
        return []
    out: list[dict] = []
    for row in doc.get("records") or []:
        ticker = str(row.get("ticker") or "").upper()
        if ticker not in our_tickers:
            continue
        change = row.get("change_type") or "unchanged"
        if change == "unchanged":
            continue
        direction = "bullish" if change in {"new", "add"} else "bearish" if change in {"trim", "exit"} else "neutral"
        fund = row.get("fund") or row.get("fund_id")
        claim = f"{fund} {change} {ticker} in {row.get('quarter') or 'latest quarter'}"
        if row.get("change_shares_pct") is not None:
            claim += f" ({row['change_shares_pct']:+.1f}% shares)."
        out.append(
            insight_record(
                source="specialist_13f",
                as_of=row.get("filing_date"),
                scope="ticker",
                ref=ticker,
                title=f"Specialist 13F {change}: {fund}",
                claim=claim,
                direction=direction,
                evidence_ref=row.get("source_url"),
                event_type=f"13f_{change}",
                impact_axis="ownership",
                confidence="med" if row.get("fund_id") in {"baker-bros", "ra-capital", "orbimed", "perceptive-advisors"} else "low",
            )
        )
    return out


def from_tracked_funds_13f(our_tickers: set[str]) -> list[dict]:
    doc = load_json(TRACKED_FUNDS_RECORDS_PATH)
    if not isinstance(doc, dict):
        return []
    out: list[dict] = []
    for row in doc.get("records") or []:
        ticker = str(row.get("ticker") or "").upper()
        if ticker not in our_tickers:
            continue
        change = row.get("change_type") or "unchanged"
        if change == "unchanged":
            continue
        direction = "bullish" if change in {"new", "add"} else "bearish" if change in {"trim", "exit"} else "neutral"
        fund = row.get("fund") or row.get("fund_id")
        claim = f"{fund} {change} {ticker} in {row.get('quarter') or 'latest quarter'}"
        if row.get("change_shares_pct") is not None:
            claim += f" ({row['change_shares_pct']:+.1f}% shares)."
        out.append(
            insight_record(
                source="tracked_fund_13f",
                as_of=row.get("filing_date") or doc.get("generated_at"),
                scope="ticker",
                ref=ticker,
                title=f"Tracked fund 13F {change}: {fund}",
                claim=claim,
                direction=direction,
                evidence_ref=row.get("source_url") or relative_path(TRACKED_FUNDS_RECORDS_PATH),
                event_type=f"tracked_13f_{change}",
                impact_axis="ownership",
                confidence="med"
                if row.get("fund_id")
                in {"ruane-cunniff", "dodge-cox", "harris-associates", "first-eagle", "tweedy-browne"}
                else "low",
            )
        )
    return out


def from_reddit_mentions(our_tickers: set[str]) -> list[dict]:
    doc = load_json(REDDIT_MENTIONS_PATH)
    if not isinstance(doc, dict):
        return []
    sources = load_json(REDDIT_SOURCES_PATH) or {}
    settings = (sources.get("settings") if isinstance(sources, dict) else None) or {}
    min_score = int(settings.get("min_score_for_insight") or 25)
    min_mentions = int(settings.get("min_mentions_for_insight") or 3)
    out: list[dict] = []
    as_of = doc.get("as_of") or doc.get("generated_at")
    for row in doc.get("by_ticker") or []:
        ticker = str(row.get("ticker") or "").upper()
        if ticker not in our_tickers:
            continue
        mentions = int(row.get("mention_count") or 0)
        max_score = int(row.get("max_score") or 0)
        if mentions < min_mentions and max_score < min_score:
            continue
        top = (row.get("posts") or [{}])[0] if row.get("posts") else {}
        subs = ", ".join(row.get("subreddits") or []) or "reddit"
        claim = f"{ticker} mentioned {mentions}x on {subs} (max score {max_score})."
        if top.get("title"):
            claim += f" Top: {top.get('title')}"
        out.append(
            insight_record(
                source="reddit_mention",
                as_of=as_of,
                scope="ticker",
                ref=ticker,
                title=f"Reddit mentions: {ticker}",
                claim=claim,
                direction="neutral",
                evidence_ref=top.get("url") or relative_path(REDDIT_MENTIONS_PATH),
                event_type="reddit_mention",
                impact_axis="context",
                confidence="low",
                publisher="Reddit",
            )
        )
    return out


def from_earnings_calendar() -> list[dict]:
    docs: list[tuple[Path, dict]] = []
    global_doc = load_json(EARNINGS_CACHE)
    if isinstance(global_doc, dict):
        docs.append((EARNINGS_CACHE, global_doc))
    for path in sorted(ROOT.glob("*/research/evidence/earnings_calendar.json")):
        doc = load_json(path)
        if isinstance(doc, dict):
            docs.append((path, doc))

    best: dict[str, tuple[Path, dict, dict]] = {}
    for path, doc in docs:
        for event in doc.get("events") or []:
            ticker = str(event.get("ticker") or event.get("portfolio_ticker") or doc.get("ticker") or "").upper()
            if not valid_ticker(ticker):
                continue
            event_date = normalize_date(
                event.get("date") or event.get("earnings_date") or event.get("report_date")
            )
            reported = bool(event.get("reported") or event.get("actual_eps") is not None)
            key = f"{ticker}|{event_date or ''}|{'reported' if reported else 'upcoming'}"
            rank = (
                1 if path == EARNINGS_CACHE else 0,
                1 if event.get("verified") else 0,
                1 if reported else 0,
            )
            prev = best.get(key)
            if prev and prev[0] >= rank:
                continue
            best[key] = (rank, path, doc, event)

    out: list[dict] = []
    for _key, (_rank, path, doc, event) in best.items():
        ticker = str(event.get("ticker") or event.get("portfolio_ticker") or doc.get("ticker") or "").upper()
        event_date = normalize_date(
            event.get("date") or event.get("earnings_date") or event.get("report_date")
        )
        reported = bool(event.get("reported") or event.get("actual_eps") is not None)
        verified = bool(event.get("verified") or doc.get("verified_only"))
        out.append(
            insight_record(
                source="earnings",
                as_of=event_date or doc.get("as_of"),
                scope="ticker",
                ref=ticker,
                title=("Reported earnings" if reported else "Upcoming earnings"),
                claim=short_text(event.get("summary") or event.get("title") or f"{ticker} earnings event tracked."),
                direction="neutral",
                evidence_ref=relative_path(path),
                event_type="reported_earnings" if reported else "earnings_calendar",
                impact_axis="fundamentals",
                confidence="med" if verified else "low",
            )
        )
    return out


def theme_rankings(records: list[dict], quarter: str | None = None, our_tickers: set[str] | None = None) -> list[dict]:
    """Count distinct letters per theme (not raw paragraph hits)."""
    by_theme: dict[str, dict] = {}
    for r in records:
        if r.get("source") != "superinvestor_letter" or r.get("scope") != "theme":
            continue
        if quarter and r.get("quarter") != quarter:
            continue
        theme = r.get("ref") or "Other"
        fund = r.get("fund") or "Unknown"
        bucket = by_theme.setdefault(
            theme,
            {
                "theme": theme,
                "letter_count": 0,
                "fund_count": 0,
                "bullish": 0,
                "bearish": 0,
                "neutral": 0,
                "top_tickers": set(),
                "_funds": set(),
            },
        )
        if fund not in bucket["_funds"]:
            bucket["_funds"].add(fund)
            bucket["fund_count"] += 1
            bucket["letter_count"] += 1
            direction = r.get("direction", "neutral")
            bucket[direction] = bucket.get(direction, 0) + 1
        for tk in r.get("tickers") or []:
            if tk and re.match(r"^[A-Z0-9][A-Z0-9.\-]{0,11}$", str(tk).upper()):
                bucket["top_tickers"].add(str(tk).upper())
    out: list[dict] = []
    holdings = our_tickers or set()
    for bucket in by_theme.values():
        all_tickers = sorted(bucket["top_tickers"])
        ours = [t for t in all_tickers if t in holdings]
        top = (ours if (holdings and ours) else all_tickers)[:8]
        out.append(
            {
                "theme": bucket["theme"],
                "letter_count": bucket["letter_count"],
                "fund_count": bucket["fund_count"],
                "bullish": bucket["bullish"],
                "bearish": bucket["bearish"],
                "neutral": bucket["neutral"],
                "top_tickers": top,
            }
        )
    return sorted(out, key=lambda x: (-x["letter_count"], x["theme"]))


def theme_rankings_by_quarter(records: list[dict], our_tickers: set[str] | None = None) -> dict[str, list[dict]]:
    quarters = sorted({r.get("quarter") for r in records if r.get("quarter")})
    out = {"all": theme_rankings(records, our_tickers=our_tickers)}
    for q in quarters:
        out[q] = theme_rankings(records, quarter=q, our_tickers=our_tickers)
    return out


def _quarter_sort_key(qid: str) -> tuple[int, int]:
    m = re.match(r"^(20\d{2})Q([1-4])$", str(qid))
    if m:
        return (int(m.group(1)), int(m.group(2)))
    return (0, 0)


def build_insights_time_periods(letters: list[dict], theme_by_q: dict[str, list]) -> dict:
    """Indexed letter quarters — used by Insights 'Latest' (not PDF catalog alone)."""
    quarters: set[str] = set()
    for letter in letters:
        q = letter.get("quarter")
        if q and re.match(r"^20\d{2}Q[1-4]$", str(q)):
            quarters.add(str(q))
    for q in theme_by_q:
        if q != "all" and re.match(r"^20\d{2}Q[1-4]$", str(q)):
            quarters.add(str(q))
    sorted_q = sorted(quarters, key=_quarter_sort_key)
    return {
        "latest_indexed_quarter": sorted_q[-1] if sorted_q else None,
        "indexed_quarters": sorted_q,
    }


def theme_glossary() -> dict[str, list[str]]:
    try:
        import build_superinvestor_insights as si  # noqa: WPS433

        return dict(getattr(si, "THEME_KEYWORDS", {}) or {})
    except Exception:
        return {}


def compute_theme_qoq_shifts(current: list[dict], prior: list[dict]) -> list[dict]:
    prior_map = {r["theme"]: r for r in prior if r.get("theme")}
    seen: set[str] = set()
    shifts: list[dict] = []
    for row in current:
        theme = row.get("theme")
        if not theme:
            continue
        seen.add(str(theme))
        prev = prior_map.get(theme, {})
        shifts.append(
            {
                "theme": theme,
                "fund_count": row.get("fund_count") or row.get("letter_count") or 0,
                "delta_funds": (row.get("fund_count") or 0) - (prev.get("fund_count") or 0),
                "bullish": row.get("bullish") or 0,
                "delta_bullish": (row.get("bullish") or 0) - (prev.get("bullish") or 0),
                "bearish": row.get("bearish") or 0,
                "delta_bearish": (row.get("bearish") or 0) - (prev.get("bearish") or 0),
                "top_tickers": row.get("top_tickers") or [],
            }
        )
    for theme, prev in prior_map.items():
        if theme in seen:
            continue
        shifts.append(
            {
                "theme": theme,
                "fund_count": 0,
                "delta_funds": -(prev.get("fund_count") or 0),
                "bullish": 0,
                "delta_bullish": -(prev.get("bullish") or 0),
                "bearish": 0,
                "delta_bearish": -(prev.get("bearish") or 0),
                "top_tickers": [],
            }
        )
    return sorted(shifts, key=lambda x: (-abs(x["delta_funds"]), str(x["theme"])))


def theme_qoq_by_quarter(theme_by_q: dict[str, list[dict]]) -> dict[str, dict]:
    qids = sorted((q for q in theme_by_q if q not in ("all", "unknown")), key=_quarter_sort_key)
    out: dict[str, dict] = {}
    for i, qid in enumerate(qids):
        if i == 0:
            continue
        prior_qid = qids[i - 1]
        shifts = compute_theme_qoq_shifts(theme_by_q.get(qid) or [], theme_by_q.get(prior_qid) or [])
        out[qid] = {"prior_quarter": prior_qid, "shifts": shifts}
    return out


def fund_registry(letters: list[dict], our_tickers: set[str]) -> list[dict]:
    """One row per fund+quarter with overlap against our book."""
    by_key: dict[str, dict] = {}
    for letter in letters:
        fund = letter.get("fund") or "Unknown"
        fund_id = letter.get("fund_id") or fund
        quarter = letter.get("quarter") or "—"
        key = f"{fund_id}|{quarter}"
        letter_tickers = {str(t).upper() for t in (letter.get("tickers") or [])}
        overlap = sorted(letter_tickers & our_tickers)
        source_ref = source_document_ref(letter.get("source_document") or letter.get("source_file"))
        letter_ev = letter_evidence_fields(letter)
        row = by_key.setdefault(
            key,
            {
                "fund_id": fund_id,
                "fund": fund,
                "manager": letter.get("manager") or "",
                "quarter": quarter,
                "our_tickers": set(overlap),
                "tickers": set(letter_tickers),
                "themes": set(),
                "maps_to_persona": letter.get("maps_to_persona") or [],
                "lead_summary": letter.get("lead_summary") or "",
                "evidence_ref": letter_ev["evidence_ref"],
                "evidence_url": letter_ev["evidence_url"],
                "evidence_label": letter_ev["evidence_label"],
                "letter_date": letter.get("letter_date"),
            },
        )
        row["our_tickers"].update(overlap)
        row["tickers"].update(letter_tickers)
        for th in letter.get("themes") or []:
            if th.get("theme"):
                row["themes"].add(th["theme"])
        if not row["lead_summary"] and letter.get("lead_summary"):
            row["lead_summary"] = letter["lead_summary"]
    out = []
    for row in by_key.values():
        out.append(
            {
                "fund_id": row["fund_id"],
                "fund": row["fund"],
                "manager": row["manager"],
                "quarter": row["quarter"],
                "letter_date": row["letter_date"],
                "our_tickers": sorted(row["our_tickers"]),
                "our_ticker_count": len(row["our_tickers"]),
                "tickers": sorted(row["tickers"])[:20],
                "themes": sorted(row["themes"]),
                "maps_to_persona": row["maps_to_persona"],
                "lead_summary": (row["lead_summary"] or "")[:280],
                "evidence_ref": row["evidence_ref"],
                "evidence_url": row["evidence_url"],
                "evidence_label": row["evidence_label"],
            }
        )
    return sorted(out, key=lambda x: (-x["our_ticker_count"], x["fund"]))


def letter_index(letters: list[dict], our_tickers: set[str]) -> list[dict]:
    rows: list[dict] = []
    for letter in letters:
        tickers = unique_tickers([str(t).upper() for t in (letter.get("tickers") or [])])
        overlap = sorted(set(tickers) & our_tickers)
        positions = letter.get("positions") or []
        adds = unique_tickers(
            [
                p["ticker"]
                for p in positions
                if p.get("action") in {"add", "new", "buy"} and p.get("ticker")
            ]
        )
        # trim only — exits stay in exits so Trim/Exit UI concat cannot double-count
        trims = unique_tickers(
            [p["ticker"] for p in positions if p.get("action") == "trim" and p.get("ticker")]
        )
        shorts = unique_tickers(
            [p["ticker"] for p in positions if p.get("action") == "short" and p.get("ticker")]
        )
        exits = unique_tickers(
            [p["ticker"] for p in positions if p.get("action") == "exit" and p.get("ticker")]
        )
        letter_ev = letter_evidence_fields(letter)
        rows.append(
            {
                "fund_id": letter.get("fund_id"),
                "fund": letter.get("fund"),
                "manager": letter.get("manager") or "",
                "quarter": letter.get("quarter"),
                "letter_date": letter.get("letter_date"),
                "document_label": letter_document_label(letter),
                "themes": [t.get("theme") for t in (letter.get("themes") or []) if t.get("theme")],
                "tickers": tickers[:20],
                "our_overlap": overlap,
                "adds": adds[:8],
                "trims": trims[:8],
                "exits": exits[:8],
                "shorts": shorts[:8],
                "lead_summary": (letter.get("lead_summary") or "")[:320],
                "maps_to_persona": letter.get("maps_to_persona") or [],
                "source_file": letter.get("source_file"),
                "source_document": letter_ev["source_document"],
                "evidence_url": letter_ev["evidence_url"],
                "evidence_label": letter_ev["evidence_label"],
                "canonical_document_id": letter.get("canonical_document_id"),
                "duplicate_count": int(letter.get("duplicate_count") or 0),
            }
        )
    return sorted(rows, key=lambda x: (x.get("letter_date") or "", x.get("fund") or ""), reverse=True)


def dedupe_canonical_letters(letters: list[dict]) -> tuple[list[dict], int]:
    """Final safety net: one rendered/aggregated row per canonical document."""
    output: list[dict] = []
    seen: set[str] = set()
    suppressed = 0
    for letter in letters:
        key = str(
            letter.get("canonical_document_id")
            or letter.get("content_hash")
            or letter.get("source_file")
            or ""
        )
        if key and key in seen:
            suppressed += 1
            continue
        if key:
            seen.add(key)
        output.append(letter)
    return output, suppressed


def security_names() -> dict[str, str]:
    data = load_json(SECURITY_MASTER_PATH)
    if not isinstance(data, dict):
        return {}
    return {str(k).upper(): str((v or {}).get("name") or k) for k, v in data.items()}


BUY_ACTIONS = {"new", "add", "buy"}
SELL_ACTIONS = {"trim", "exit"}
SHORT_ACTIONS = {"short"}
ACTIONABLE = BUY_ACTIONS | SELL_ACTIONS | SHORT_ACTIONS


def _consensus_bucket(ticker: str, names: dict[str, str], our_tickers: set[str]) -> dict:
    return {
        "ticker": ticker,
        "name": names.get(ticker, ticker),
        "in_book": ticker in our_tickers,
        "buy_funds": set(),
        "sell_funds": set(),
        "short_funds": set(),
        "neutral_funds": set(),
        "mentioned_funds": set(),
        "all_funds": set(),
    }


def _finalize_consensus_row(b: dict) -> dict:
    buy_names = sorted(b["buy_funds"])
    sell_names = sorted(b["sell_funds"])
    short_names = sorted(b["short_funds"])
    mentioned_names = sorted(b.get("mentioned_funds") or [])
    buys, sells, shorts = len(buy_names), len(sell_names), len(short_names)
    # fund_count / lean: actionable votes only (discussed is mentioned, not a vote)
    fund_count = len(b["all_funds"])
    if buys > sells + shorts:
        sentiment = "accumulating"
    elif sells + shorts > buys:
        sentiment = "reducing"
    elif buys or sells or shorts:
        sentiment = "mixed"
    else:
        sentiment = "mentioned" if mentioned_names else "discussed"
    return {
        "ticker": b["ticker"],
        "name": b["name"],
        "in_book": b["in_book"],
        "fund_count": fund_count,
        "mentioned_count": len(mentioned_names),
        "buy_funds": buys,
        "sell_funds": sells,
        "short_funds": shorts,
        "net": buys - sells - shorts,
        "sentiment": sentiment,
        "funds": sorted(b["all_funds"]),
        "mentioned_funds": mentioned_names,
        "buy_fund_names": buy_names,
        "sell_fund_names": sell_names,
        "short_fund_names": short_names,
    }


def _collapse_consensus_rows(rows: list[dict]) -> list[dict]:
    """Collapse identical commentary across any funds into one row."""
    if not rows:
        return []
    groups: dict[tuple, dict] = {}
    order: list[tuple] = []
    for row in rows:
        commentary = normalize_commentary(row.get("commentary"))
        fam = row.get("family_id") or family_id_for_fund(row.get("fund_id"))
        ch = commentary_hash(row.get("commentary"))
        if ch:
            # Universal text collapse when snippet is long enough
            key = (
                row.get("ticker"),
                row.get("quarter"),
                row.get("letter_date") or "",
                ch,
            )
        else:
            key = (
                row.get("ticker"),
                row.get("quarter"),
                row.get("letter_date") or "",
                fam or row.get("fund_id") or row.get("fund"),
                commentary or row.get("fund_id"),
            )
        if key not in groups:
            keep = dict(row)
            keep["sibling_funds"] = []
            if fam:
                keep["family_id"] = fam
                keep["family"] = family_display(fam) or fam
            groups[key] = keep
            order.append(key)
            continue
        keep = groups[key]
        label = row.get("fund") or row.get("fund_id")
        primary = keep.get("fund") or keep.get("fund_id")
        sibs = keep.setdefault("sibling_funds", [])
        if label and label != primary and label not in sibs:
            sibs.append(label)
        if len(row.get("commentary") or "") > len(keep.get("commentary") or ""):
            keep["commentary"] = row.get("commentary")
            keep["evidence_url"] = row.get("evidence_url") or keep.get("evidence_url")
            keep["evidence_label"] = row.get("evidence_label") or keep.get("evidence_label")
        if not keep.get("family_id") and fam:
            keep["family_id"] = fam
            keep["family"] = family_display(fam) or fam

    out: list[dict] = []
    for key in order:
        row = groups[key]
        sibs = list(row.get("sibling_funds") or [])
        if sibs:
            row["fund"] = collapse_display_label(
                row.get("fund"),
                row.get("fund_id"),
                len(sibs),
                family_id=row.get("family_id"),
            )
            row["sibling_funds"] = sibs
        out.append(row)
    return out


def _consensus_row_map(store: dict[str, dict]) -> dict[str, dict]:
    return {b["ticker"]: _finalize_consensus_row(b) for b in store.values()}


def _compute_qoq_shifts(curr: dict[str, dict], prev: dict[str, dict]) -> list[dict]:
    """Quarter-over-quarter fund positioning shifts between two quarter stores."""
    curr_map = _consensus_row_map(curr)
    prev_map = _consensus_row_map(prev)
    shifts: list[dict] = []
    for ticker in sorted(set(curr_map) | set(prev_map)):
        c = curr_map.get(ticker)
        p = prev_map.get(ticker)
        c_funds = set(c["funds"]) if c else set()
        p_funds = set(p["funds"]) if p else set()
        new_funds = sorted(c_funds - p_funds)
        dropped_funds = sorted(p_funds - c_funds)
        c_fc = c["fund_count"] if c else 0
        p_fc = p["fund_count"] if p else 0
        c_net = c["net"] if c else 0
        p_net = p["net"] if p else 0
        delta_funds = c_fc - p_fc
        delta_net = c_net - p_net
        c_sent = c["sentiment"] if c else None
        p_sent = p["sentiment"] if p else None
        lean_flip = bool(c_sent and p_sent and c_sent != p_sent)
        if not (delta_funds or delta_net or new_funds or dropped_funds or lean_flip):
            continue
        ref = c or p
        shifts.append(
            {
                "ticker": ticker,
                "name": ref["name"],
                "in_book": ref["in_book"],
                "fund_count": c_fc,
                "prior_fund_count": p_fc,
                "delta_funds": delta_funds,
                "net": c_net,
                "prior_net": p_net,
                "delta_net": delta_net,
                "sentiment": c_sent or "mentioned",
                "prior_sentiment": p_sent,
                "lean_flip": lean_flip,
                "new_funds": new_funds[:12],
                "dropped_funds": dropped_funds[:12],
            }
        )
    return sorted(
        shifts,
        key=lambda r: (-abs(r["delta_net"]), -abs(r["delta_funds"]), r["ticker"]),
    )[:60]


def build_consensus(letters: list[dict], our_tickers: set[str], names: dict[str, str]) -> dict:
    """Dataroma-style cross-fund aggregation over Tier A/B letter positions."""
    quarters: set[str] = set()
    by_q: dict[str, dict[str, dict]] = {}
    all_q: dict[str, dict] = {}
    activity_by_q: dict[str, list[dict]] = {}
    by_ticker: dict[str, list[dict]] = {}
    all_vote_keys: set[str] = set()

    for letter in letters:
        q = letter.get("quarter") or "unknown"
        quarters.add(q)
        fund = letter.get("fund") or "Unknown"
        fund_id = letter.get("fund_id") or fund
        fam_id = family_id_for_fund(fund_id, family_id=letter.get("family_id"))
        letter_date = letter.get("letter_date")
        letter_ev = letter_evidence_fields(letter)
        for pos in letter.get("positions") or []:
            tk = str(pos.get("ticker") or "").upper()
            if not tk or not valid_ticker(tk):
                continue
            action = pos.get("action") or "discussed"
            commentary = short_text(pos.get("commentary") or pos.get("thesis"), 280)
            vote_key = consensus_vote_key(
                fund_id,
                fund,
                family_id=fam_id,
                commentary=commentary,
                action=action,
            )
            mention_key = family_display(fam_id) if fam_id else (fund or fund_id)
            for store in (by_q.setdefault(q, {}), all_q):
                b = store.get(tk) or _consensus_bucket(tk, names, our_tickers)
                store[tk] = b
                if vote_key:
                    b["all_funds"].add(vote_key)
                    all_vote_keys.add(vote_key)
                    if action in BUY_ACTIONS:
                        b["buy_funds"].add(vote_key)
                    elif action in SELL_ACTIONS:
                        b["sell_funds"].add(vote_key)
                    elif action in SHORT_ACTIONS:
                        b["short_funds"].add(vote_key)
                else:
                    b["mentioned_funds"].add(mention_key)
            row = {
                "ticker": tk,
                "name": names.get(tk, tk),
                "fund": fund,
                "fund_id": fund_id,
                "family_id": fam_id,
                "family": family_display(fam_id) if fam_id else None,
                "quarter": q,
                "letter_date": letter_date,
                "action": action,
                "direction": pos.get("direction") or "neutral",
                "conviction": pos.get("conviction") or "low",
                "tier": pos.get("tier"),
                "in_book": tk in our_tickers,
                "commentary": commentary,
                "evidence_url": letter_ev["evidence_url"],
                "evidence_label": letter_ev["evidence_label"],
            }
            by_ticker.setdefault(tk, []).append(row)
            if action in ACTIONABLE:
                activity_by_q.setdefault(q, []).append(row)

    def section(store: dict[str, dict], q: str) -> dict:
        rows = [_finalize_consensus_row(b) for b in store.values()]
        most = sorted(
            rows,
            key=lambda r: (-r["fund_count"], -r.get("mentioned_count", 0), -abs(r["net"]), r["ticker"]),
        )
        changes = sorted([r for r in rows if r["net"] != 0], key=lambda r: (-abs(r["net"]), -r["fund_count"]))
        activity = sorted(
            activity_by_q.get(q, []) if q != "all" else [r for rs in activity_by_q.values() for r in rs],
            key=lambda r: (r.get("letter_date") or "", r.get("conviction") or ""),
            reverse=True,
        )
        return {
            "letter_count": sum(1 for letter in letters if (q == "all" or letter.get("quarter") == q)),
            "most_discussed": most[:80],
            "biggest_changes": changes[:40],
            "activity": _collapse_consensus_rows(activity)[:20],
        }

    out_by_q = {q: section(store, q) for q, store in by_q.items()}
    out_by_q["all"] = section(all_q, "all")

    def quarter_sort_key(qid: str) -> tuple:
        m = re.match(r"^(20\d{2})Q([1-4])$", str(qid))
        if m:
            return (int(m.group(1)), int(m.group(2)))
        return (0, 0)

    sorted_qids = sorted((q for q in by_q if q != "unknown"), key=quarter_sort_key)
    qoq_by_quarter: dict[str, dict] = {}
    for i, qid in enumerate(sorted_qids):
        if i == 0:
            continue
        prior_qid = sorted_qids[i - 1]
        shifts = _compute_qoq_shifts(by_q.get(qid, {}), by_q.get(prior_qid, {}))
        qoq_by_quarter[qid] = {"prior_quarter": prior_qid, "shifts": shifts}
        if qid in out_by_q:
            out_by_q[qid]["qoq_shifts"] = shifts
            out_by_q[qid]["prior_quarter"] = prior_qid

    for tk, rows in by_ticker.items():
        rows.sort(key=lambda r: (r.get("letter_date") or ""), reverse=True)
        by_ticker[tk] = _collapse_consensus_rows(rows)[:8]

    as_of = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    proposals = propose_fund_families(letters, as_of=as_of)
    write_family_proposals(proposals, as_of=as_of)

    return {
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "quarters": sorted(quarters),
        "summary": {
            "tickers_covered": len(all_q),
            "fund_count": len(all_vote_keys),
            "book_tickers_discussed": sorted(t for t in all_q if t in our_tickers),
            "family_proposals": len(proposals),
        },
        "by_quarter": out_by_q,
        "by_ticker": by_ticker,
        "qoq_by_quarter": qoq_by_quarter,
    }


def fund_profiles(letters: list[dict], our_tickers: set[str]) -> dict[str, dict]:
    by_fund: dict[str, dict] = {}
    for letter in letters:
        fund_id = letter.get("fund_id") or slugify(letter.get("fund", "unknown"))
        profile = by_fund.setdefault(
            fund_id,
            {
                "fund_id": fund_id,
                "fund": letter.get("fund"),
                "manager": letter.get("manager") or "",
                "maps_to_persona": letter.get("maps_to_persona") or [],
                "our_tickers": set(),
                "letters": [],
            },
        )
        if letter.get("manager") and not profile["manager"]:
            profile["manager"] = letter["manager"]
        if letter.get("maps_to_persona"):
            profile["maps_to_persona"] = letter["maps_to_persona"]
        tickers = {str(t).upper() for t in (letter.get("tickers") or [])}
        letter_ev = letter_evidence_fields(letter)
        profile["our_tickers"].update(tickers & our_tickers)
        profile["letters"].append(
            {
                "quarter": letter.get("quarter"),
                "letter_date": letter.get("letter_date"),
                "lead_summary": short_text(letter.get("lead_summary"), 320),
                "themes": [
                    {"theme": theme.get("theme"), "stance": theme.get("stance")}
                    for theme in (letter.get("themes") or [])[:8]
                    if isinstance(theme, dict) and theme.get("theme")
                ],
                "positions": [
                    {
                        "ticker": pos.get("ticker"),
                        "action": pos.get("action"),
                        "commentary": short_text(pos.get("commentary") or pos.get("thesis"), 280),
                    }
                    for pos in (letter.get("positions") or [])[:10]
                    if isinstance(pos, dict) and pos.get("ticker")
                ],
                "risks": [short_text(value, 240) for value in (letter.get("risks") or [])[:5]],
                "catalysts": [short_text(value, 240) for value in (letter.get("catalysts") or [])[:5]],
                "evidence_url": letter_ev["evidence_url"],
                "evidence_label": letter_ev["evidence_label"],
            }
        )
    for profile in by_fund.values():
        profile["our_tickers"] = sorted(profile["our_tickers"])
        profile["letters"] = sorted(
            profile["letters"],
            key=lambda row: (row.get("letter_date") or "", row.get("quarter") or ""),
            reverse=True,
        )
        quarters = {row.get("quarter") for row in profile["letters"] if row.get("quarter")}
        # Extra letters beyond one-per-quarter are near-dups / monthly copies
        profile["duplicate_count"] = max(0, len(profile["letters"]) - max(len(quarters), 1))
        profile["letter_count"] = len(profile["letters"])
        profile["latest_quarter"] = profile["letters"][0].get("quarter") if profile["letters"] else None
    return by_fund


def slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower()).strip("-")
    return s or "unknown-fund"


def load_registry() -> dict:
    reg_path = ROOT / "_system" / "portfolio" / "registry.json"
    if not reg_path.exists():
        return {"holdings": {}, "watchlist": {}}
    reg = load_json(reg_path)
    if not isinstance(reg, dict):
        return {"holdings": {}, "watchlist": {}}
    return reg


def portfolio_tickers(include_watchlist: bool = True) -> set[str]:
    reg = load_registry()
    tickers = {str(k).upper() for k in (reg.get("holdings") or {})}
    if include_watchlist:
        tickers.update(str(k).upper() for k in (reg.get("watchlist") or {}))
    return tickers


def portfolio_company_hints(include_watchlist: bool = True) -> dict[str, set[str]]:
    reg = load_registry()
    rows = dict(reg.get("holdings") or {})
    if include_watchlist:
        rows.update(reg.get("watchlist") or {})
    hints: dict[str, set[str]] = {}
    for ticker, meta in rows.items():
        company = str((meta or {}).get("company") or ticker)
        tokens = {
            token.lower()
            for token in re.findall(r"[A-Za-z][A-Za-z0-9&]{2,}", company)
            if token.lower() not in COMPANY_STOPWORDS and len(token) >= 4
        }
        hints[str(ticker).upper()] = tokens
    return hints


def portfolio_identity_meta(include_watchlist: bool = True) -> dict[str, dict]:
    """Book ticker -> company/market/exchange for cross-exchange identity filters."""
    reg = load_registry()
    rows = dict(reg.get("holdings") or {})
    if include_watchlist:
        rows.update(reg.get("watchlist") or {})
    out: dict[str, dict] = {}
    for ticker, meta in rows.items():
        out[str(ticker).upper()] = {
            "company": (meta or {}).get("company"),
            "market": (meta or {}).get("market"),
            "exchange": (meta or {}).get("exchange"),
        }
    return out


def record_identity_ok(record: dict, identity_meta: dict[str, dict]) -> bool:
    ticker = str(record.get("ref") or record.get("ticker") or "").upper()
    meta = identity_meta.get(ticker) or {}
    text = " ".join(
        str(record.get(key) or "")
        for key in ("title", "claim", "summary", "commentary", "thesis")
    ).strip()
    if not text:
        return True
    return identity_match_ok(
        text,
        ticker,
        company=str(meta.get("company") or "") or None,
        market=str(meta.get("market") or "") or None,
        exchange=str(meta.get("exchange") or "") or None,
    )


def our_holdings_tickers() -> set[str]:
    return portfolio_tickers(include_watchlist=False)


def is_letter_boilerplate(text: str) -> bool:
    lower = text.lower()
    return any(phrase in lower for phrase in LETTER_BOILERPLATE_PHRASES)


def contains_ticker_token(text: str, ticker: str) -> bool:
    if not text or not ticker:
        return False
    tk = str(ticker).upper()
    pattern = rf"(?<![A-Z0-9.\-]){re.escape(tk)}(?![A-Z0-9.\-])"
    flags = 0 if len(tk.replace(".", "").replace("-", "")) <= 2 else re.IGNORECASE
    return bool(re.search(pattern, text, flags))


def has_company_hint(text: str, ticker: str, company_hints: dict[str, set[str]]) -> bool:
    lower = text.lower()
    return any(hint in lower for hint in company_hints.get(str(ticker).upper(), set()))


def strong_letter_ticker_evidence(
    record: dict,
    company_hints: dict[str, set[str]],
    identity_meta: dict[str, dict] | None = None,
) -> bool:
    ticker = str(record.get("ref") or "").upper()
    text = " ".join(
        str(record.get(key) or "")
        for key in ("title", "claim", "commentary", "thesis")
    ).strip()
    if not text:
        return record.get("action") in {"add", "trim"}
    if is_letter_boilerplate(text):
        return False
    if identity_meta is not None and not record_identity_ok(record, identity_meta):
        return False
    if record.get("action") in {"add", "trim"}:
        return True
    return contains_ticker_token(text, ticker) or has_company_hint(text, ticker, company_hints)


def front_record_allowed(
    record: dict,
    front_tickers: set[str],
    company_hints: dict[str, set[str]],
    identity_meta: dict[str, dict] | None = None,
) -> bool:
    scope = record.get("scope")
    if scope == "portfolio":
        return True
    if scope != "ticker":
        return False
    ticker = str(record.get("ref") or "").upper()
    if ticker not in front_tickers:
        return False
    if identity_meta is not None and not record_identity_ok(record, identity_meta):
        return False
    if record.get("source") == "superinvestor_letter":
        return strong_letter_ticker_evidence(record, company_hints, identity_meta)
    return True


def ticker_insights(
    records: list[dict],
    front_tickers: set[str],
    company_hints: dict[str, set[str]],
    identity_meta: dict[str, dict] | None = None,
) -> dict[str, list[dict]]:
    by_ticker: dict[str, list[dict]] = {}
    for r in records:
        if not front_record_allowed(r, front_tickers, company_hints, identity_meta):
            continue
        tk = str(r.get("ref", "")).upper()
        if not tk or not re.match(r"^[A-Z0-9][A-Z0-9.\-]{0,11}$", tk):
            continue
        by_ticker.setdefault(tk, []).append(r)
    def record_rank(record: dict) -> tuple:
        observed = (
            record.get("observed_at")
            or record.get("published_at")
            or record.get("letter_date")
            or record.get("quarter")
            or ""
        )
        confidence = record.get("confidence")
        confidence_rank = {"high": 3, "med": 2, "medium": 2, "low": 1}.get(
            str(confidence or "").lower(),
            float(confidence) if isinstance(confidence, (int, float)) else 0,
        )
        return (str(observed), confidence_rank, str(record.get("id") or ""))

    return {
        ticker: sorted(rows, key=record_rank, reverse=True)[:35]
        for ticker, rows in by_ticker.items()
    }


def ticker_discussants(
    letters: list[dict],
    our_tickers: set[str],
    company_hints: dict[str, set[str]],
    identity_meta: dict[str, dict] | None = None,
) -> dict[str, list[dict]]:
    """Per-ticker summary of which funds discuss it (letters only)."""
    by_ticker: dict[str, dict[str, dict]] = {}
    for letter in letters:
        fund = letter.get("fund") or "Unknown"
        fund_id = letter.get("fund_id") or fund
        fam_id = family_id_for_fund(fund_id, family_id=letter.get("family_id"))
        letter_ev = letter_evidence_fields(letter)
        for pos in letter.get("positions") or []:
            tk = str(pos.get("ticker", "")).upper()
            if not tk or tk not in our_tickers or not valid_ticker(tk):
                continue
            position_record = {
                "source": "superinvestor_letter",
                "scope": "ticker",
                "ref": tk,
                "action": pos.get("action", "discussed"),
                "claim": pos.get("commentary") or pos.get("thesis") or "",
                "commentary": pos.get("commentary") or "",
                "thesis": pos.get("thesis") or "",
            }
            if not strong_letter_ticker_evidence(position_record, company_hints, identity_meta):
                continue
            commentary = pos.get("commentary") or pos.get("thesis") or ""
            ch = commentary_hash(commentary)
            # Collapse siblings / identical snippets into one discussant slot
            bucket_key = ch or fam_id or fund_id
            bucket = by_ticker.setdefault(tk, {})
            entry = bucket.setdefault(
                bucket_key,
                {
                    "fund": fund,
                    "fund_id": fund_id,
                    "family_id": fam_id,
                    "sibling_funds": [],
                    "quarter": letter.get("quarter"),
                    "letter_date": letter.get("letter_date"),
                    "action": pos.get("action", "discussed"),
                    "commentary": commentary,
                    "source_file": letter.get("source_file"),
                    "source_document": letter_ev["source_document"],
                    "evidence_url": letter_ev["evidence_url"],
                    "evidence_label": letter_ev["evidence_label"],
                    "in_our_book": tk in our_tickers,
                },
            )
            if fund_id != entry.get("fund_id"):
                label = fund
                if label and label != entry.get("fund") and label not in entry["sibling_funds"]:
                    entry["sibling_funds"].append(label)
            if commentary and len(commentary) > len(entry.get("commentary") or ""):
                entry["commentary"] = commentary
                entry["action"] = pos.get("action", entry["action"])
    out: dict[str, list[dict]] = {}
    for tk, funds in by_ticker.items():
        rows = []
        for entry in funds.values():
            sibs = entry.get("sibling_funds") or []
            if sibs:
                entry["fund"] = collapse_display_label(
                    entry.get("fund"),
                    entry.get("fund_id"),
                    len(sibs),
                    family_id=entry.get("family_id"),
                )
            rows.append(entry)
        rows = sorted(rows, key=lambda x: (x.get("letter_date") or ""), reverse=True)
        out[tk] = rows[:12]
    return out


def confidence_weight(confidence: str | None) -> float:
    return {"high": 1.0, "med": 0.75, "medium": 0.75, "low": 0.45}.get(str(confidence or "").lower(), 0.6)


def freshness_days(as_of: str | None) -> int | None:
    d = parse_date(as_of)
    if not d:
        return None
    return (today_utc() - d).days


def freshness_weight(days: int | None) -> float:
    if days is None:
        return 0.5
    if days < 0:
        return 0.85
    if days <= 7:
        return 1.0
    if days <= 30:
        return 0.84
    if days <= 90:
        return 0.62
    if days <= 365:
        return 0.38
    return 0.2


def event_relevance(
    ticker: str | None,
    scope: str | None,
    holdings_tickers: set[str],
    front_tickers: set[str],
) -> float:
    if ticker and ticker in holdings_tickers:
        return 1.0
    if ticker and ticker in front_tickers:
        return 0.82
    if scope == "portfolio":
        return 0.72
    return 0.45


def event_materiality(record: dict) -> float:
    source = record.get("source")
    base = SOURCE_META.get(source, {}).get("materiality", 0.55)
    event_type = record.get("event_type") or ""
    if event_type == "inflection":
        # Second-derivative moves outrank routine records of the same source class.
        base += 0.1
    if event_type in {"filing_metric", "reported_earnings"}:
        base += 0.08
    if event_type == "form4_transaction" and record.get("direction") == "bullish":
        base += 0.06
    if source == "news" and record.get("impact_axis") in {"risk", "fundamentals"}:
        base += 0.06
    return min(base, 1.0)


def source_quality(record: dict) -> float:
    return SOURCE_META.get(record.get("source"), {}).get("quality", 0.55)


def model_impact_weight(record: dict) -> float:
    text = " ".join(
        str(record.get(key) or "")
        for key in ("title", "claim", "summary", "event_type", "impact_axis")
    ).lower()
    weight = 1.0
    if any(term in text for term in MODEL_IMPACT_TERMS):
        weight += 0.12
    if record.get("impact_axis") in {"fundamentals", "risk", "catalyst", "capital_allocation"}:
        weight += 0.08
    if record.get("in_base_irr"):
        weight -= 0.18
    return max(0.65, min(weight, 1.25))


def event_score(
    record: dict,
    ticker: str | None,
    holdings_tickers: set[str],
    front_tickers: set[str],
) -> int:
    days = freshness_days(record.get("as_of"))
    score = (
        100
        * source_quality(record)
        * event_materiality(record)
        * confidence_weight(record.get("confidence"))
        * freshness_weight(days)
        * event_relevance(ticker, record.get("scope"), holdings_tickers, front_tickers)
        * model_impact_weight(record)
    )
    return max(1, round(score))


def event_title(record: dict) -> str:
    if record.get("title"):
        return short_text(record.get("title"), 120)
    source_label = SOURCE_META.get(record.get("source"), {}).get("label", record.get("source") or "Insight")
    ref = record.get("ref")
    if ref:
        return short_text(f"{source_label}: {ref}", 120)
    return short_text(source_label, 120)


def event_id(record: dict, ticker: str | None) -> str:
    raw = "|".join(
        [
            str(record.get("source") or ""),
            str(record.get("event_type") or ""),
            str(ticker or record.get("ref") or ""),
            str(record.get("as_of") or ""),
            str(record.get("claim") or ""),
            str(record.get("evidence_ref") or ""),
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def event_dedupe_key(event: dict) -> str:
    title = str(event.get("title") or event.get("claim") or event.get("summary") or "")
    norm = re.sub(r"\s+", " ", title.strip().lower())
    # Strip volatile punctuation / wire suffixes so 13F headline variants collapse
    norm = re.sub(r"[^\w\s]", "", norm)
    norm = re.sub(r"\b(update|breaking|exclusive|sources?)\b", "", norm).strip()
    return "|".join(
        [
            str(event.get("ticker") or ""),
            str(event.get("event_type") or ""),
            str(event.get("observed_at") or "")[:10],
            norm[:160],
        ]
    )


def dedupe_events(events: list[dict]) -> list[dict]:
    """Collapse duplicate ranked events that differ only by evidence path."""
    best: dict[str, dict] = {}
    for event in events:
        key = event_dedupe_key(event)
        prev = best.get(key)
        if not prev or (event.get("score") or 0) > (prev.get("score") or 0):
            best[key] = event
    return list(best.values())


def events_from_records(
    records: list[dict],
    front_tickers: set[str],
    holdings_tickers: set[str],
    company_hints: dict[str, set[str]],
    identity_meta: dict[str, dict] | None = None,
) -> list[dict]:
    events: list[dict] = []
    for record in records:
        if not front_record_allowed(record, front_tickers, company_hints, identity_meta):
            continue
        source = record.get("source")
        scope = record.get("scope")
        if source == "superinvestor_letter" and scope == "theme":
            continue
        ticker = str(record.get("ref") or "").upper() if scope == "ticker" else None
        if ticker and not valid_ticker(ticker):
            ticker = None
        if not ticker and scope != "portfolio":
            continue
        days = freshness_days(record.get("as_of"))
        axis = record.get("impact_axis") or SOURCE_META.get(source, {}).get("axis") or "context"
        observed_at = normalize_date(record.get("as_of"))
        event_kind = "scheduled" if days is not None and days < 0 else "observed"
        structured_source = source in {
            "filing",
            "earnings",
            "insider",
            "kpi_trend",
            "specialist_13f",
            "tracked_fund_13f",
            "superinvestor_letter",
        }
        entity_text = " ".join(
            str(record.get(key) or "") for key in ("title", "claim", "summary", "commentary")
        )
        entity_verified = bool(
            not ticker
            or structured_source
            or contains_ticker_token(entity_text, ticker)
            or has_company_hint(entity_text, ticker, company_hints)
        )
        in_holdings = bool(ticker and ticker in holdings_tickers)
        in_watchlist = bool(ticker and ticker in front_tickers and ticker not in holdings_tickers)
        event = {
            "id": event_id(record, ticker),
            "ticker": ticker,
            "in_our_book": in_holdings,
            "in_holdings": in_holdings,
            "in_watchlist": in_watchlist,
            "portfolio_scope": "holdings" if in_holdings else ("watchlist" if in_watchlist else "portfolio"),
            "source": source,
            "source_label": SOURCE_META.get(source, {}).get("label", source or "Insight"),
            "source_name": record.get("publisher") or record.get("fund") or SOURCE_META.get(source, {}).get("label"),
            "event_type": record.get("event_type") or source or "insight",
            "impact_axis": axis,
            "observed_at": observed_at,
            "published_at": observed_at if event_kind == "observed" else normalize_date(record.get("published_at")),
            "effective_at": observed_at if event_kind == "scheduled" else normalize_date(record.get("effective_at")),
            "event_kind": event_kind,
            "freshness_days": days,
            "title": event_title(record),
            "summary": short_text(record.get("claim"), 320),
            "direction": record.get("direction") or "neutral",
            "confidence": record.get("confidence") or "med",
            "portfolio_relevance": event_relevance(ticker, scope, holdings_tickers, front_tickers),
            "score": event_score(record, ticker, holdings_tickers, front_tickers),
            "entity_verified": entity_verified,
            "evidence_ref": record.get("evidence_ref"),
            "evidence_url": record.get("evidence_url") or evidence_url(record.get("evidence_ref")),
            "evidence_label": record.get("evidence_label") or evidence_label(record.get("evidence_ref")),
            "evidence_document_id": record.get("evidence_document_id") or evidence_document_id(record.get("evidence_ref")),
            "source_filing_ref": record.get("source_filing_ref"),
            "extract_ref": record.get("extract_ref"),
            "extract_url": record.get("extract_url") or evidence_url(record.get("extract_ref")),
            "extract_label": record.get("extract_label") or "extract",
            "verification": record.get("verification"),
            "needs_review": bool(record.get("needs_review")),
            "inventory_ref": record.get("inventory_ref"),
            "source_path": record.get("source_path"),
            "match_tier": record.get("match_tier"),
            "metric_name": record.get("metric_name"),
            "change_pct": record.get("change_pct"),
            "prior_value": record.get("prior_value"),
            "current_value": record.get("current_value"),
            "trend_signal_tier": record.get("trend_signal_tier"),
            "position_action": record.get("position_action") or record.get("action"),
            "in_base_irr": record.get("in_base_irr"),
            "quarter": record.get("quarter"),
        }
        # Preserve activist-parity Form 4 / ICS materiality into the event queue.
        if record.get("materiality") is not None:
            event["materiality"] = record.get("materiality")
        if record.get("materiality_components"):
            event["materiality_components"] = record.get("materiality_components")
        if record.get("tier"):
            event["tier"] = record.get("tier")
        if record.get("ics") is not None:
            event["ics"] = record.get("ics")
        if record.get("value_usd") is not None:
            event["value_usd"] = record.get("value_usd")
        if record.get("action"):
            event["action"] = record.get("action")
        if record.get("band"):
            event["band"] = record.get("band")
        events.append(event)
    return dedupe_events(events)


def _retained_event_history(events: list[dict], max_events: int = 1800) -> list[dict]:
    """Retain a useful current feed plus representative older history and upcoming events."""
    scheduled = [e for e in events if e.get("event_kind") == "scheduled"]
    eligible = [e for e in events if e.get("event_kind") != "scheduled" and e.get("feed_eligible")]
    # Noise excluded from default Insights feed (triage queue / archive retain full set)

    def decision_rank(event: dict) -> tuple:
        return (
            int(event.get("decision_priority") or event.get("materiality") or 0),
            event.get("observed_at") or "",
        )

    chosen: list[dict] = []
    seen: set[str] = set()

    def add(rows: list[dict], limit: int) -> None:
        for event in sorted(rows, key=decision_rank, reverse=True)[:limit]:
            event_id = str(event.get("id") or "")
            if event_id and event_id in seen:
                continue
            if event_id:
                seen.add(event_id)
            chosen.append(event)

    add(scheduled, 150)
    add(eligible, 1000)

    by_year: dict[str, list[dict]] = {}
    for event in events:
        year = str(event.get("observed_at") or "unknown")[:4]
        by_year.setdefault(year, []).append(event)
    for year in sorted(by_year, reverse=True):
        add(by_year[year], 35)

    # Noise stays out of the default Insights feed (Pipeline/archive keep full triage)
    retained = chosen[:max_events]
    retained.sort(
        key=lambda e: (
            e.get("observed_at") or "",
            int(e.get("decision_priority") or e.get("materiality") or 0),
        ),
        reverse=True,
    )
    return retained


def finalize_events(events: list[dict], scan_date: str) -> tuple[list[dict], dict]:
    triaged, _ = triage_events(events)
    write_triage_queue(triaged, scan_date)
    feed = _retained_event_history(triaged)
    dates = sorted(e.get("observed_at") for e in feed if e.get("observed_at"))
    summary = {
        "signal": sum(1 for e in feed if e.get("tier") == "signal" and e.get("feed_eligible")),
        "context": sum(1 for e in feed if e.get("tier") == "context" and e.get("feed_eligible")),
        "noise": sum(1 for e in feed if e.get("tier") == "noise" or not e.get("feed_eligible")),
        "human_review": sum(1 for e in feed if e.get("triage_verdict") == "human_review"),
        "scheduled": sum(1 for e in feed if e.get("event_kind") == "scheduled"),
        "missing_evidence": sum(1 for e in feed if e.get("evidence_status") == "missing"),
        "raw_event_count": len(events),
        "triaged_event_count": len(triaged),
        "retained_event_count": len(feed),
        "history_start": dates[0] if dates else None,
        "history_end": dates[-1] if dates else None,
    }
    return feed, summary


def events_by_ticker(events: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for event in events:
        ticker = event.get("ticker")
        if not ticker:
            continue
        out.setdefault(ticker, []).append(event)
    for ticker, rows in out.items():
        rows.sort(key=lambda e: (e.get("score") or 0, e.get("observed_at") or ""), reverse=True)
        out[ticker] = rows[:25]
    return out


def source_counts(records: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        source = record.get("source") or "unknown"
        counts[source] = counts.get(source, 0) + 1
    return counts


def newest_as_of(values) -> str | None:
    dates = [normalize_date(v) for v in values if normalize_date(v)]
    return max(dates) if dates else None


def latest_filing_fact_files() -> list[Path]:
    latest: list[Path] = []
    for ticker_dir in ROOT.iterdir():
        if not ticker_dir.is_dir() or ticker_dir.name.startswith((".", "_")):
            continue
        files = sorted((ticker_dir / "research" / "evidence").glob("filing_facts_*.json"), reverse=True)
        if files:
            latest.append(files[0])
    return latest


def third_party_inventory_count() -> int:
    count = 0
    for ticker_dir in ROOT.iterdir():
        if ticker_dir.is_dir() and not ticker_dir.name.startswith((".", "_")):
            if list(ticker_dir.glob("third-party-analyses/source_inventory_*.json")):
                count += 1
    return count


def build_source_health(
    records: list[dict],
    letters: list[dict],
    news_doc: dict | None,
    archive_meta: dict | None = None,
) -> dict:
    counts = source_counts(records)
    insider_manifest = load_json(INSIDER_MANIFEST)
    earnings_doc = load_json(EARNINGS_CACHE)
    terminalvalue_doc = load_json(TERMINALVALUE_SOURCES)
    source_universe_doc = load_json(SOURCE_UNIVERSE_PATH)
    reddit_doc = load_json(REDDIT_MENTIONS_PATH)
    tracked_funds_doc = load_json(TRACKED_FUNDS_RECORDS_PATH)
    sumzero_doc = load_json(SUMZERO_INDEX)
    registry_doc = load_json(DOCUMENT_REGISTRY_PATH)
    drive_audit_doc = load_json(DRIVE_AUDIT_PATH)
    sumzero_summary = (sumzero_doc or {}).get("summary") if isinstance(sumzero_doc, dict) else {}
    sumzero_archive = (sumzero_doc or {}).get("archive") if isinstance(sumzero_doc, dict) else {}
    registry_summary = (registry_doc or {}).get("summary") if isinstance(registry_doc, dict) else {}
    drive_audit_summary = (drive_audit_doc or {}).get("summary") if isinstance(drive_audit_doc, dict) else {}
    filing_files = latest_filing_fact_files()
    kpi_trends_doc = load_json(KPI_TRENDS_PATH)
    if not isinstance(kpi_trends_doc, dict):
        kpi_trends_doc = None
    insider_tickers = (insider_manifest or {}).get("tickers") if isinstance(insider_manifest, dict) else {}
    insider_errors = [
        meta.get("error")
        for meta in (insider_tickers or {}).values()
        if isinstance(meta, dict)
        and meta.get("error")
        and str(meta.get("error")).lower()
        not in {"no transactions in window", "offline", "cached"}
    ]
    insider_cached = any(
        isinstance(meta, dict) and str(meta.get("error") or "").lower() in {"offline", "cached"}
        for meta in (insider_tickers or {}).values()
    )
    if insider_errors:
        insider_status = "degraded"
    elif insider_tickers:
        insider_status = "cached" if insider_cached else "ok"
    else:
        insider_status = "missing"
    return {
        "superinvestor_letters": {
            "status": "ok" if letters else "empty",
            "records": counts.get("superinvestor_letter", 0),
            "items": len(letters),
            "as_of": newest_as_of([l.get("letter_date") for l in letters]),
            "path": relative_path(LETTERS_INSIGHTS),
        },
        "podcasts": (
            lambda _pod: {
                "status": (
                    "ok"
                    if (_pod.get("episodes") or [])
                    else (
                        "missing"
                        if not PODCASTS_INSIGHTS.exists()
                        and not PODCASTS_INSIGHTS_INDEX_MIRROR.exists()
                        and not PODCASTS_INSIGHTS_MIRROR.exists()
                        else "empty"
                    )
                ),
                "records": counts.get("podcast_episode", 0),
                "items": len(_pod.get("episodes") or []),
                "episode_count": _pod.get("episode_count") or len(_pod.get("episodes") or []),
                "transcript_count": _pod.get("transcript_count"),
                "whisper_pending": _pod.get("whisper_pending"),
                "as_of": newest_as_of([e.get("published") for e in (_pod.get("episodes") or [])]),
                "notes": (
                    f"episodes={_pod.get('episode_count') or len(_pod.get('episodes') or [])}"
                    f" transcripts={_pod.get('transcript_count') or 0}"
                    f" whisper_pending={_pod.get('whisper_pending') or 0}"
                ),
                "path": (
                    relative_path(PODCASTS_INSIGHTS)
                    if PODCASTS_INSIGHTS.exists()
                    else (
                        relative_path(PODCASTS_INSIGHTS_INDEX_MIRROR)
                        if PODCASTS_INSIGHTS_INDEX_MIRROR.exists()
                        else relative_path(PODCASTS_INSIGHTS_MIRROR)
                    )
                ),
            }
        )(load_podcast_insights_doc()),
        "portfolio_news": {
            "status": "ok" if news_doc else "missing",
            "records": counts.get("news", 0),
            "items": len((news_doc or {}).get("items") or (news_doc or {}).get("news") or []),
            "as_of": normalize_date((news_doc or {}).get("build_time") or (news_doc or {}).get("generated_at")),
            "path": relative_path(NEWS_PATH),
        },
        "insider_transactions": {
            "status": insider_status,
            "records": counts.get("insider", 0),
            "items": len(insider_tickers or {}),
            "as_of": newest_as_of([(m or {}).get("as_of") for m in (insider_tickers or {}).values() if isinstance(m, dict)]),
            "warnings": len(insider_errors),
            "path": relative_path(INSIDER_MANIFEST),
        },
        "filing_facts": {
            "status": "ok" if filing_files else "missing",
            "records": counts.get("filing", 0),
            "items": len(filing_files),
            "as_of": newest_as_of([p.stem.replace("filing_facts_", "") for p in filing_files]),
            "path": "*/research/evidence/filing_facts_*.json",
        },
        "kpi_trends": {
            "status": "ok" if kpi_trends_doc else "missing",
            "records": counts.get("kpi_trend", 0),
            "items": (kpi_trends_doc or {}).get("inflection_count", 0),
            "as_of": normalize_date((kpi_trends_doc or {}).get("generated_at")),
            "path": relative_path(KPI_TRENDS_PATH),
            "notes": "Second-derivative KPI signals (YoY basis) from SEC XBRL fundamentals, equity models and news flow.",
        },
        "fundamental_series": {
            "status": "ok" if ((kpi_trends_doc or {}).get("coverage") or {}).get("fundamentals_tickers") else "missing",
            "records": 0,
            "items": ((kpi_trends_doc or {}).get("coverage") or {}).get("fundamentals_tickers", 0),
            "as_of": normalize_date((kpi_trends_doc or {}).get("generated_at")),
            "path": "_system/reference/market-data/fundamentals/",
            "notes": "SEC XBRL companyfacts quarterly series (build_fundamental_series.py).",
        },
        "earnings_calendar": {
            "status": (earnings_doc or {}).get("access_status") or ("ok" if earnings_doc else "missing"),
            "records": counts.get("earnings", 0),
            "items": len((earnings_doc or {}).get("events") or []),
            "as_of": normalize_date((earnings_doc or {}).get("as_of")),
            "path": relative_path(EARNINGS_CACHE),
        },
        "theme_panels": {
            "status": "ok" if THEMES_DIR.exists() else "missing",
            "records": counts.get("theme", 0),
            "items": len(list(THEMES_DIR.glob("*.csv"))) if THEMES_DIR.exists() else 0,
            "path": relative_path(THEMES_DIR),
        },
        "third_party_inventories": {
            "status": "ok" if third_party_inventory_count() else "missing",
            "records": counts.get("third_party", 0),
            "items": third_party_inventory_count(),
            "path": "*/third-party-analyses/source_inventory_*.json",
        },
        "sumzero_ideas": {
            "status": (
                "missing"
                if not sumzero_doc or (isinstance(sumzero_doc, dict) and sumzero_doc.get("status") == "missing")
                else ("empty" if not (sumzero_summary or {}).get("matched_documents") else "ok")
            ),
            "records": counts.get("sumzero_research", 0),
            "items": (sumzero_summary or {}).get("documents", 0),
            "matches": (sumzero_summary or {}).get("matched_documents", 0),
            "matched_tickers": (sumzero_summary or {}).get("matched_ticker_count", 0),
            "as_of": normalize_date((sumzero_doc or {}).get("generated_at")) if isinstance(sumzero_doc, dict) else None,
            "archive_latest_modified": (sumzero_archive or {}).get("latest_modified"),
            "path": relative_path(SUMZERO_INDEX),
            "notes": "Local SumZero Ideas archive index; raw documents stay out of git.",
        },
        "pdf_store": {
            "status": (
                "missing"
                if not registry_summary
                else (
                    "degraded"
                    if (registry_summary.get("pending_upload_count") or 0)
                    or (drive_audit_summary.get("duplicate_sha_count") or 0)
                    else "ok"
                )
            ),
            "records": registry_summary.get("document_count", 0),
            "items": registry_summary.get("uploaded_count", 0),
            "pending_uploads": registry_summary.get("pending_upload_count", 0),
            "drive_pdfs": drive_audit_summary.get("drive_pdf_count"),
            "orphans": drive_audit_summary.get("orphan_drive_pdf_count"),
            "duplicate_sha_groups": drive_audit_summary.get("duplicate_sha_count"),
            "as_of": normalize_date((registry_doc or {}).get("generated_at")) if isinstance(registry_doc, dict) else None,
            "path": relative_path(DOCUMENT_REGISTRY_PATH),
            "notes": "Google Drive canonical PDF store; orphan count is unmanaged legacy PDFs retained under canonical folders.",
        },
        "terminalvalue_candidates": {
            "status": "ok" if terminalvalue_doc else "missing",
            "records": 0,
            "items": len((terminalvalue_doc or {}).get("selected_tools") or []),
            "as_of": (terminalvalue_doc or {}).get("reviewed_at"),
            "path": relative_path(TERMINALVALUE_SOURCES),
            "notes": "Provider candidates for fundamentals, filings, transcripts, ownership, news, macro and valuation feeds.",
        },
        "reddit_mentions": {
            "status": (
                (reddit_doc or {}).get("status")
                if isinstance(reddit_doc, dict) and reddit_doc.get("status")
                else ("ok" if reddit_doc else "missing")
            ),
            "records": counts.get("reddit_mention", 0),
            "items": (reddit_doc or {}).get("mention_total", 0) if isinstance(reddit_doc, dict) else 0,
            "as_of": normalize_date((reddit_doc or {}).get("as_of") or (reddit_doc or {}).get("generated_at"))
            if isinstance(reddit_doc, dict)
            else None,
            "path": relative_path(REDDIT_MENTIONS_PATH),
            "notes": "Context-tier Reddit ticker mention scan (make reddit-ingest). Not for base IRR.",
        },
        "tracked_funds_13f": {
            "status": (
                (tracked_funds_doc or {}).get("status")
                if isinstance(tracked_funds_doc, dict) and tracked_funds_doc.get("status")
                else ("ok" if tracked_funds_doc and (tracked_funds_doc or {}).get("records") else "missing")
            ),
            "records": counts.get("tracked_fund_13f", 0),
            "items": (tracked_funds_doc or {}).get("record_count", 0) if isinstance(tracked_funds_doc, dict) else 0,
            "as_of": normalize_date((tracked_funds_doc or {}).get("generated_at"))
            if isinstance(tracked_funds_doc, dict)
            else None,
            "path": relative_path(TRACKED_FUNDS_RECORDS_PATH),
            "notes": "Curated great-fund / value-shop 13F portfolio overlay (make tracked-funds-13f-ingest).",
        },
        "source_universe": {
            "status": "ok" if source_universe_doc else "missing",
            "records": 0,
            "items": len((source_universe_doc or {}).get("sources") or []) if isinstance(source_universe_doc, dict) else 0,
            "as_of": ((source_universe_doc or {}).get("meta") or {}).get("updated_at")
            if isinstance(source_universe_doc, dict)
            else None,
            "path": relative_path(SOURCE_UNIVERSE_PATH),
            "notes": "Canonical registry of live + evaluation data sources we pull from.",
        },
        "research_archive": {
            "status": "ok" if archive_meta else "missing",
            "records": (archive_meta or {}).get("record_count", 0),
            "items": (archive_meta or {}).get("archived_ticker_count", 0),
            "as_of": (archive_meta or {}).get("generated_at"),
            "path": relative_path(ARCHIVE_OUTPUT),
            "notes": "Full raw insight records are kept out of the front dashboard payload.",
        },
    }


def build_record_archive(
    records: list[dict],
    front_tickers: set[str],
    company_hints: dict[str, set[str]],
    identity_meta: dict[str, dict] | None = None,
) -> dict:
    archived_tickers = {
        str(r.get("ref") or "").upper()
        for r in records
        if r.get("scope") == "ticker"
        and valid_ticker(str(r.get("ref") or "").upper())
        and not front_record_allowed(r, front_tickers, company_hints, identity_meta)
    }
    front_records = [
        r for r in records if front_record_allowed(r, front_tickers, company_hints, identity_meta)
    ]
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "record_count": len(records),
        "front_record_count": len(front_records),
        "archived_record_count": len(records) - len(front_records),
        "front_ticker_count": len(front_tickers),
        "archived_ticker_count": len(archived_tickers),
        "by_source": source_counts(records),
        "archived_tickers": sorted(archived_tickers),
        "records": records,
    }


def write_record_archive(archive_doc: dict) -> dict:
    ARCHIVE_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = ARCHIVE_OUTPUT.with_suffix(ARCHIVE_OUTPUT.suffix + ".tmp")
    backup_output = ARCHIVE_OUTPUT.with_suffix(ARCHIVE_OUTPUT.suffix + ".swap-backup")
    with temporary_output.open("w", encoding="utf-8") as handle:
        json.dump(archive_doc, handle, separators=(",", ":"))
        handle.write("\n")
    if backup_output.exists():
        backup_output.unlink()
    if ARCHIVE_OUTPUT.exists():
        ARCHIVE_OUTPUT.rename(backup_output)
    try:
        temporary_output.rename(ARCHIVE_OUTPUT)
    except OSError:
        if backup_output.exists() and not ARCHIVE_OUTPUT.exists():
            backup_output.rename(ARCHIVE_OUTPUT)
        raise
    if backup_output.exists():
        backup_output.unlink()
    return {
        "generated_at": archive_doc.get("generated_at"),
        "record_count": archive_doc.get("record_count"),
        "front_record_count": archive_doc.get("front_record_count"),
        "archived_record_count": archive_doc.get("archived_record_count"),
        "front_ticker_count": archive_doc.get("front_ticker_count"),
        "archived_ticker_count": archive_doc.get("archived_ticker_count"),
        "path": relative_path(ARCHIVE_OUTPUT),
    }


def build_provenance(
    records: list[dict],
    events: list[dict],
    letter_stats: dict | None = None,
    *,
    event_triage_summary: dict | None = None,
) -> dict:
    out = {
        "schema_version": 2,
        "pipeline": relative_path(Path(__file__).resolve()),
        "generated_by": "build_insights.py",
        "record_count": len(records),
        "event_count": len(events),
        "event_score": "event_materiality multiplicative model; see _system/data/event_triage_rules.json",
        "inputs": [
            relative_path(LETTERS_INSIGHTS),
            relative_path(NEWS_PATH),
            relative_path(INSIDER_MANIFEST),
            relative_path(EARNINGS_CACHE),
            relative_path(TERMINALVALUE_SOURCES),
            relative_path(SUMZERO_INDEX),
            relative_path(ARCHIVE_OUTPUT),
            "*/research/evidence/filing_facts_*.json",
            "*/third-party-analyses/source_inventory_*.json",
            relative_path(THEMES_DIR),
        ],
    }
    if letter_stats:
        out.update(letter_stats)
    if event_triage_summary:
        out["event_triage_summary"] = event_triage_summary
    return out


def main() -> int:
    records: list[dict] = []

    prior = load_prior_insights()
    letters_source_doc = load_json(LETTERS_INSIGHTS) or {"letters": []}
    vault_count = count_vault_letters()
    preserve, preserve_reason = should_preserve_letter_corpus(prior, vault_count)
    classification_policy_version = int(letters_source_doc.get("classification_policy_version") or 0)
    intentional_reclassification = can_replace_preserved_letter_corpus(
        letters_source_doc, vault_count
    )
    if intentional_reclassification:
        preserve = False
        preserve_reason = "intentional classified-letter corpus rebuild"
    if preserve:
        print(f"PRESERVE letter corpus: {preserve_reason}", file=sys.stderr)
        records.extend(load_preserved_letter_records())
        if not records:
            print(
                "WARN: preserve mode but no archived superinvestor_letter records; "
                "letter insight records may be missing",
                file=sys.stderr,
            )
        letters: list[dict] = []
        fund_identity_audit = (prior or {}).get("fund_identity_audit") or {}
    else:
        letters_doc = letters_source_doc
        letters = [
            canonicalize_letter_fund(letter)
            for letter in (letters_doc.get("letters") or [])
            if is_letter_eligible_for_index(letter)
        ]
        letters, fund_identity_audit = consolidate_letter_funds_stable(letters)
        letters, downstream_duplicates_suppressed = dedupe_canonical_letters(letters)
        letters_doc = {**letters_doc, "letters": letters}
        records.extend(from_superinvestor_letters(letters_doc))

    podcasts_doc = load_podcast_insights_doc()
    records.extend(from_podcast_episodes(podcasts_doc))

    front_tickers = portfolio_tickers(include_watchlist=True)
    holdings_tickers = our_holdings_tickers()
    company_hints = portfolio_company_hints(include_watchlist=True)
    identity_meta = portfolio_identity_meta(include_watchlist=True)
    sumzero_doc = load_json(SUMZERO_INDEX)
    records.extend(from_sumzero_ideas(sumzero_doc if isinstance(sumzero_doc, dict) else None, front_tickers))
    records.extend(from_insider_transactions(front_tickers, holdings_tickers=holdings_tickers))
    records.extend(from_specialist_13f(front_tickers))
    records.extend(from_tracked_funds_13f(front_tickers))
    records.extend(from_reddit_mentions(front_tickers))
    records.extend(from_earnings_calendar())

    for p in ROOT.iterdir():
        if not p.is_dir() or p.name.startswith((".", "_")):
            continue
        val_path = p / "research" / "valuation.json"
        if val_path.exists():
            val = load_json(val_path)
            if isinstance(val, dict):
                records.extend(from_valuation_context(p.name, val))
        records.extend(from_filing_facts(p, p.name))
        records.extend(from_third_party(p, p.name))

    records.extend(from_theme_panel())
    kpi_trends_doc = load_json(KPI_TRENDS_PATH)
    if isinstance(kpi_trends_doc, dict):
        records.extend(from_kpi_trends(kpi_trends_doc))
    news_doc = load_json(NEWS_PATH)
    if isinstance(news_doc, dict):
        records.extend(from_news(news_doc))
    index_membership_path = ROOT / "dashboard" / "data" / "index_membership.json"
    if index_membership_path.exists():
        try:
            index_doc = json.loads(index_membership_path.read_text(encoding="utf-8"))
            records.extend(from_index_membership(index_doc))
        except (json.JSONDecodeError, OSError):
            pass
    terminalvalue_doc = load_json(TERMINALVALUE_SOURCES)

    raw_events = events_from_records(
        records, front_tickers, holdings_tickers, company_hints, identity_meta
    )
    scan_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    events, event_triage_summary = finalize_events(raw_events, scan_date)
    archive_meta = write_record_archive(
        build_record_archive(records, front_tickers, company_hints, identity_meta)
    )
    if preserve and prior:
        preserved_fields = preserved_letter_payload_fields(prior)
        letter_count_value = int(preserved_fields.get("letter_count") or prior_letter_count(prior))
        prior_prov = prior.get("provenance") or {}
        letter_stats = {
            key: prior_prov[key]
            for key in ("letters_with_positions_pct", "letters_with_actionable_pct")
            if key in prior_prov
        }
    else:
        preserved_fields = {}
        letter_count_value = len(letters)
        letter_count = len(letters) or 1
        with_positions = sum(1 for letter in letters if letter.get("positions"))
        actionable = sum(
            1
            for letter in letters
            if any(
                p.get("action") in {"add", "trim", "new", "exit", "short", "buy"}
                for p in (letter.get("positions") or [])
            )
        )
        letter_stats = {
            "letters_with_positions_pct": round(with_positions / letter_count, 4),
            "letters_with_actionable_pct": round(actionable / letter_count, 4),
        }
    source_health = build_source_health(
        records,
        letters,
        news_doc if isinstance(news_doc, dict) else None,
        archive_meta,
    )
    if preserve and prior:
        si_health = source_health.get("superinvestor_letters") or {}
        si_health = {
            **si_health,
            "status": "preserved",
            "items": letter_count_value,
            "notes": (
                f"Committed dashboard corpus preserved ({preserve_reason}); "
                f"vault had {vault_count} letters in {relative_path(LETTERS_INSIGHTS)}"
            ),
        }
        source_health["superinvestor_letters"] = si_health
    theme_by_q = theme_rankings_by_quarter(records, front_tickers)
    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "classification_policy_version": classification_policy_version,
        "record_count": len(records),
        "front_record_count": archive_meta.get("front_record_count"),
        "archived_record_count": archive_meta.get("archived_record_count"),
        "event_count": len(events),
        "letter_count": letter_count_value,
        "podcast_count": len(podcasts_doc.get("episodes") or []),
        "source_health": source_health,
        "data_source_candidates": terminalvalue_doc or {},
        "provenance": build_provenance(
            records, events, letter_stats, event_triage_summary=event_triage_summary
        ),
        "record_archive": archive_meta,
        "events": events,
        "events_by_ticker": events_by_ticker(events),
        "theme_rankings": theme_rankings(records, our_tickers=front_tickers),
        "theme_rankings_by_quarter": theme_by_q,
        "theme_qoq_by_quarter": theme_qoq_by_quarter(theme_by_q),
        "theme_glossary": theme_glossary(),
        "time_periods": build_insights_time_periods(letters, theme_by_q),
        "letter_index": letter_index(letters, front_tickers),
        "podcast_index": podcast_index_rows(podcasts_doc),
        "podcast_by_show": podcast_by_show(podcasts_doc),
        "consensus": build_consensus(letters, front_tickers, security_names()),
        "fund_registry": fund_registry(letters, front_tickers),
        "fund_profiles": fund_profiles(letters, front_tickers),
        "fund_identity_audit": fund_identity_audit,
        "document_dedup_audit": {
            **(letters_source_doc.get("document_dedup_audit") or {}),
            "downstream_duplicates_suppressed": (
                downstream_duplicates_suppressed if not preserve else 0
            ),
        },
        "ticker_discussants": ticker_discussants(
            letters, front_tickers, company_hints, identity_meta
        ),
        "by_ticker": ticker_insights(
            records, front_tickers, company_hints, identity_meta
        ),
    }
    if preserved_fields:
        payload.update(preserved_fields)
        payload["letter_count"] = letter_count_value

    # Post-hoc attribution guard. `should_preserve_letter_corpus` has to decide
    # before ticker_discussants exists, so it cannot see a corpus that grew
    # while its attribution collapsed -- the exact 2026-08-11 case, 18,889
    # letters yielding 130 discussants against a prior 648. Re-check once the
    # real number is known and keep the richer map, saying so loudly. This
    # never blocks an intentional reclassification: that path sets
    # `preserve = False` via can_replace_preserved_letter_corpus and is
    # exempted here for the same reason.
    if not preserve and not intentional_reclassification:
        prior_disc = prior_discussant_count(prior)
        new_disc = len(payload.get("ticker_discussants") or {})
        if prior_disc > 0 and new_disc < int(prior_disc * DISCUSSANT_REGRESSION_RATIO):
            payload["ticker_discussants"] = (prior or {}).get("ticker_discussants") or {}
            payload["ticker_discussants_preserved"] = {
                "reason": "rebuild attribution regressed",
                "rebuilt_count": new_disc,
                "preserved_count": prior_disc,
                "vault_letters": vault_count,
                "prior_letters": prior_letter_count(prior),
            }
            print(
                f"PRESERVE ticker_discussants: rebuild yielded {new_disc} vs prior "
                f"{prior_disc} (vault {vault_count} letters); keeping the prior map. "
                "A larger corpus that attributes less is a regression, not an update.",
                file=sys.stderr,
            )

    # Same shape of guard, for the podcast catalog.
    #
    # The catalog is derived from research-vault/podcasts, but it is not owned by
    # the podcast workflow: every lane that runs this script regenerates it from
    # whatever the vault holds at that moment. podcast-refresh.yml checks for a
    # shrinking catalog before it commits; nothing else did. On 2026-08-20 the
    # nightly intake-full rebuilt while the vault was momentarily behind and
    # silently replaced a 3,711-episode catalog with 3,601, walking `newest` back
    # from 2026-08-19 to 2026-08-03. Nothing reported it, because from that
    # lane's point of view the rebuild succeeded.
    #
    # Putting the check here means every writer hits it rather than only the one
    # lane that remembered. A vault that is legitimately smaller still wins after
    # the ratio, so a real pruning is not blocked forever.
    prior_podcasts = list((prior or {}).get("podcast_index") or [])
    new_podcasts = list(payload.get("podcast_index") or [])
    if prior_podcasts and len(new_podcasts) < int(len(prior_podcasts) * PODCAST_REGRESSION_RATIO):
        payload["podcast_index"] = prior_podcasts
        payload["podcast_by_show"] = (prior or {}).get("podcast_by_show") or {}
        payload["podcast_index_preserved"] = {
            "reason": "rebuild produced a smaller catalog than the committed one",
            "rebuilt_count": len(new_podcasts),
            "preserved_count": len(prior_podcasts),
        }
        print(
            f"PRESERVE podcast_index: rebuild yielded {len(new_podcasts)} episodes vs prior "
            f"{len(prior_podcasts)}; keeping the committed catalog. The corpus this lane saw is "
            "behind the published one -- check that research-vault/podcasts was cloned and is current.",
            file=sys.stderr,
        )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    serialized_payload = json.dumps(payload, separators=(",", ":")) + "\n"
    _atomic_write(OUTPUT, serialized_payload)
    print(
        f"Wrote {OUTPUT} ({len(records)} insight records, {len(events)} events, "
        f"{letter_count_value} letters"
        f"{'; preserved committed corpus' if preserve else ''})"
    )
    return 0


def _atomic_write(path: Path, text: str, retries: int = 6) -> None:
    """Write via a temp file + os.replace, retrying transient Windows/OneDrive
    file locks (Errno 13/22) that intermittently hold synced files."""
    import os
    import time

    tmp = path.with_suffix(path.suffix + ".tmp")
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, path)
            return
        except OSError as err:
            last_err = err
            time.sleep(1.0 + attempt)
    raise OSError(f"Could not write {path} after {retries} attempts: {last_err}")


if __name__ == "__main__":
    raise SystemExit(main())
