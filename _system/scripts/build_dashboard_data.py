#!/usr/bin/env python3
"""Build portfolio dashboard JSON from ticker folders and _system/portfolio/holdings.md."""
from __future__ import annotations

import csv
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))
from dated_md import dated_md_label, dated_md_sort_key, latest_dated_md  # noqa: E402
from document_date import catalog_sort_key, infer_document_period  # noqa: E402
from document_store import best_document_label, best_document_url, document_id_for_ref  # noqa: E402
from market_order import sort_market_filters, sort_markets  # noqa: E402
from insight_format import (  # noqa: E402
    OWNERSHIP_SOURCES,
    format_letter_position,
    is_letter_table_debris,
    is_portfolio_wide,
    split_insight_rows,
)
from listing_units import resolve_units  # noqa: E402
from valuation_synthesis import website_implied_irr  # noqa: E402
from calculation_proof import floor_equity_value_range  # noqa: E402
from decision_authority import contract_return_display, resolve_authority  # noqa: E402
from macro_regime_panel import (  # noqa: E402
    build_portfolio_macro_regime,
    regime_to_compat_macro_list,
)
from insider_materiality import SIGNAL_THRESHOLD as INSIDER_SIGNAL_THRESHOLD  # noqa: E402
from event_materiality import materiality_score as event_materiality_score  # noqa: E402
from ticker_identity import identity_match_ok  # noqa: E402

DATA_DIR = ROOT / "dashboard" / "data"
OUTPUT = DATA_DIR / "dashboard_data.json"
RESEARCH_MEMORY_PATH = DATA_DIR / "research_memory.json"
DOCUMENT_REGISTRY_PATH = DATA_DIR / "document_registry.json"
DOCUMENT_CATALOG_PATH = DATA_DIR / "document_catalog.json"
DRIVE_FOLDER_INDEX_PATH = ROOT / "_system" / "reference" / "document-store" / "drive_folder_index.json"
CLASS_PATH = ROOT / "_system" / "portfolio" / "classification.json"
REGISTRY_PATH = ROOT / "_system" / "portfolio" / "registry.json"
SLEEVES_PATH = ROOT / "_system" / "portfolio" / "investment_sleeves.json"
CVR_UNIVERSE_PATH = ROOT / "_system" / "reference" / "cvr" / "cvr_universe.json"
GITHUB_REPO = "GoldmanDrew/single-stock-investments"
UNIVERSE_INTAKE_WORKFLOW = "ls-algo-universe.yml"


def github_blob_url(rel_path: str) -> str:
    return f"https://github.com/{GITHUB_REPO}/blob/main/{rel_path.replace(chr(92), '/')}"


def github_tree_url(rel_path: str) -> str:
    return f"https://github.com/{GITHUB_REPO}/tree/main/{rel_path.replace(chr(92), '/').rstrip('/')}"


def github_raw_url(rel_path: str) -> str:
    return f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{rel_path.replace(chr(92), '/')}"


def source_document_ref(ref: str | None) -> str | None:
    if not ref:
        return None
    clean = str(ref).strip()
    if not clean:
        return None
    if clean.startswith(("http://", "https://")):
        return clean
    base = clean.split("#", 1)[0].replace("\\", "/")
    suffix = f"#{clean.split('#', 1)[1]}" if "#" in clean else ""
    path = ROOT / base
    candidates: list[Path] = []
    if base.endswith(".pdf.txt"):
        candidates.append(ROOT / base[: -len(".txt")])
    if path.suffix.lower() in {".txt", ".md"}:
        candidates.append(path.with_suffix(".pdf"))
    if path.suffix.lower() != ".json":
        candidates.append(path)
    for candidate in candidates:
        if candidate.exists():
            return str(candidate.relative_to(ROOT)).replace("\\", "/") + suffix
    return clean


DATED_MD_RE = re.compile(r"_(\d{4}-\d{2}-\d{2})\.md$")

# Listings whose quote units could not be resolved, reported at the end of the build.
# An unresolved listing still renders -- as a bare number, never with a guessed symbol.
UNRESOLVED_UNITS: dict[str, str] = {}


# Known metadata fallback when holdings.md is sparse
TICKER_META = {
    "8697.T": {"company": "Japan Exchange Group", "market": "JP", "exchange": "TSE"},
    "3905.T": {"company": "DataSection Co., Ltd.", "market": "JP", "exchange": "TSE"},
    "AMZN": {"company": "Amazon.com", "market": "US", "exchange": "NASDAQ"},
    "APLD": {"company": "Applied Digital", "market": "US", "exchange": "NASDAQ"},
    "BN": {"company": "Brookfield Corporation", "market": "US", "exchange": "NYSE"},
    "CPRT": {"company": "Copart", "market": "US", "exchange": "NASDAQ"},
    "CSGP": {"company": "CoStar Group", "market": "US", "exchange": "NASDAQ"},
    "CSU": {"company": "Constellation Software", "market": "CA", "exchange": "TSX"},
    "DHR": {"company": "Danaher Corporation", "market": "US", "exchange": "NYSE"},
    "FRMO": {"company": "FRMO Corporation", "market": "US", "exchange": "OTC"},
    "GOOGL": {"company": "Alphabet Inc.", "market": "US", "exchange": "NASDAQ"},
    "ICE": {"company": "Intercontinental Exchange", "market": "US", "exchange": "NYSE"},
    "KEWL": {"company": "Keweenaw Land Association", "market": "US", "exchange": "OTC Pink"},
    "OTCM": {"company": "OTC Markets Group", "market": "US", "exchange": "OTCQX"},
    "QDEL": {"company": "QuidelOrtho", "market": "US", "exchange": "NASDAQ"},
    "SPGI": {"company": "S&P Global", "market": "US", "exchange": "NYSE"},
    "TEQ.ST": {"company": "Teqnion AB", "market": "SE", "exchange": "Nasdaq First North"},
    "WBI": {"company": "WaterBridge Infrastructure", "market": "US", "exchange": "NYSE"},
    "SJT": {"company": "San Juan Basin Royalty Trust", "market": "US", "exchange": "NYSE"},
}


SKIP_TICKER_DIRS = {"_system", "dashboard", "docs", ".git", ".github", ".cursor", "_external"}


def list_tickers() -> list[str]:
    """Registry holdings are source of truth; folder scan is fallback only."""
    reg = load_registry()
    holdings = reg.get("holdings") or {}
    if holdings:
        return sorted(holdings.keys())
    tickers = []
    for p in ROOT.iterdir():
        if not p.is_dir():
            continue
        if p.name in SKIP_TICKER_DIRS or p.name.startswith(("_", ".")):
            continue
        tickers.append(p.name)
    return sorted(tickers)


def load_registry() -> dict:
    if not REGISTRY_PATH.exists():
        return {"holdings": {}, "watchlist": {}}
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def parse_holdings() -> dict[str, dict]:
    reg = load_registry()
    meta: dict[str, dict] = {}
    for ticker, h in (reg.get("holdings") or {}).items():
        meta[ticker] = {
            "company": h.get("company", ticker),
            "market": h.get("market", "—"),
            "exchange": h.get("exchange", "—"),
            "display_ticker": h.get("display_ticker"),
            "quote_ticker": h.get("quote_ticker"),
        }
    if meta:
        return meta
    holdings_path = ROOT / "_system" / "portfolio" / "holdings.md"
    meta: dict[str, dict] = {}
    if not holdings_path.exists():
        return meta
    in_holdings_table = False
    for line in holdings_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            break
        if line.startswith("| Ticker | Folder |"):
            in_holdings_table = True
            continue
        if not in_holdings_table or not line.startswith("|"):
            continue
        if line.startswith("|--------"):
            continue
        parts = [c.strip() for c in line.split("|")[1:-1]]
        if len(parts) >= 4 and parts[0] not in ("—", "-"):
            meta[parts[0]] = {
                "company": parts[2],
                "market": parts[3],
            }
    return meta


def onboard_status(ticker_dir: Path) -> dict | None:
    path = ticker_dir / ".onboard_status.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def reconcile_onboard_status(ticker_dir: Path, pdf_count: int) -> dict | None:
    """Heal stale failed onboard when primary PDFs exist (e.g. partial BSE after CDN 403)."""
    status = onboard_status(ticker_dir)
    if not status or status.get("phase") != "failed" or pdf_count < 1:
        return status
    healed = {
        "phase": "complete",
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "error": None,
        "download_detail": (
            f"partial IR reconciled ({pdf_count} PDFs on disk); prior: {status.get('error', '')}"
        ).strip(),
        "ir_gap": True,
        "deep_dive_pending": status.get("deep_dive_pending", True),
    }
    path = ticker_dir / ".onboard_status.json"
    path.write_text(json.dumps(healed, indent=2) + "\n", encoding="utf-8")
    return healed


def build_watchlist_rows(watchlist: dict) -> list[dict]:
    rows = []
    for ticker, w in sorted(watchlist.items()):
        rows.append(
            {
                "ticker": ticker,
                "company": w.get("company", ticker),
                "market": w.get("market", "—"),
                "notes": w.get("notes", ""),
                "added": w.get("added"),
                "status": "watchlist",
            }
        )
    return rows


def has_download_script(ticker_dir: Path) -> tuple[bool, str | None]:
    patterns = [
        ticker_dir / "_scripts" / "download_and_organize.ps1",
        ticker_dir / "investor-documents" / "download_*_investor_docs.py",
    ]
    # as_posix(), not str(): every other path emitted into the payload is
    # normalised to forward slashes, and this function was the one that was not.
    # A rebuild run on Windows wrote "AVGO\investor-documents\..." into all 833
    # shards, which is a dead link everywhere the dashboard renders it.
    ps1 = ticker_dir / "_scripts" / "download_and_organize.ps1"
    if ps1.exists():
        return True, ps1.relative_to(ROOT).as_posix()
    scripts_dir = ticker_dir / "_scripts"
    if scripts_dir.exists():
        for script in scripts_dir.glob("download*"):
            if script.is_file():
                return True, script.relative_to(ROOT).as_posix()
    for py in (ticker_dir / "investor-documents").glob("download_*_investor_docs.py"):
        return True, py.relative_to(ROOT).as_posix()
    for py in ticker_dir.rglob("download_*.py"):
        if "_system" not in py.parts:
            return True, py.relative_to(ROOT).as_posix()
    return False, None


def count_pdfs(ticker_dir: Path, registry_docs: list[dict] | None = None) -> int:
    local = sum(1 for _ in ticker_dir.rglob("*.pdf"))
    if local > 0:
        return local
    if not registry_docs:
        return 0
    prefix = f"{ticker_dir.name}/"
    return sum(
        1
        for doc in registry_docs
        if str(doc.get("local_pdf_path") or "").replace("\\", "/").startswith(prefix)
    )


# Infra fields that collapse to empty when ticker trees are absent (sparse CI).
_INFRA_PRESERVE_KEYS = (
    "pdf_count",
    "readme",
    "research_dir",
    "sec_filings",
    "completeness",
    "index_file",
    "download_script",
    "download_script_path",
    "last_download",
    "last_research",
    "recent_files",
)

# Valuation payloads require ticker research trees. Sparse pages/letter rebuilds
# must keep the prior VAL/IRR/range fields instead of publishing "missing".
_VALUATION_PRESERVE_KEYS = (
    "valuation_decision",
    "total_return_panel",
    "component_valuation",
    "valuation_workbench",
    "classification",
)


def load_prior_dashboard_rows() -> dict[str, dict]:
    prior = _load_json(OUTPUT) or {}
    rows = prior.get("tickers") or []
    return {str(r.get("ticker")): r for r in rows if r.get("ticker")}


def merge_sparse_payload(current: dict, prior: dict) -> dict:
    """Update present ticker rows without deleting absent rows in a sparse worktree."""
    current_rows = current.get("tickers") or []
    prior_rows = prior.get("tickers") or []
    if len(prior_rows) < 50 or len(current_rows) * 2 >= len(prior_rows):
        return current
    updates = {row.get("ticker"): row for row in current_rows if row.get("ticker")}
    merged = dict(prior)
    merged["generated_at"] = current.get("generated_at")
    merged_rows = [updates.pop(row.get("ticker"), row) for row in prior_rows]
    merged_rows.extend(updates.values())
    merged["tickers"] = merged_rows
    summary = dict(prior.get("summary") or {})
    summary["ticker_count"] = len(merged_rows)
    summary["total_pdfs"] = sum(int(row.get("pdf_count") or 0) for row in merged_rows)
    summary["with_readme"] = sum(bool(row.get("readme")) for row in merged_rows)
    summary["with_research"] = sum(bool(row.get("research_dir")) for row in merged_rows)
    summary["avg_completeness"] = round(sum(float(row.get("completeness") or 0) for row in merged_rows) / len(merged_rows)) if merged_rows else 0
    merged["summary"] = summary
    return merged


def ticker_dirs_present(tickers: list[str]) -> int:
    return sum(1 for t in tickers if (ROOT / t).is_dir())


def workspace_is_sparse(tickers: list[str]) -> bool:
    """True when most holding folders are missing (pages/darwin sparse checkout)."""
    if not tickers:
        return False
    present = ticker_dirs_present(tickers)
    floor = max(50, len(tickers) // 5)
    return present < floor


def _valuation_field_missing(key: str, value) -> bool:
    if value in (None, False, 0, "", [], {}):
        return True
    if key == "valuation_decision":
        return isinstance(value, dict) and value.get("status") in (None, "missing")
    if key == "total_return_panel":
        if not isinstance(value, dict):
            return True
        return value.get("status") == "missing" or value.get("error") == "no_valuation_json"
    return False


def preserve_infra_from_prior(rows: list[dict], prior_by_ticker: dict[str, dict]) -> int:
    """Fill infra/valuation fields hidden by sparse checkout from the prior dashboard."""
    restored = 0
    for row in rows:
        prior = prior_by_ticker.get(row["ticker"])
        if not prior:
            continue
        changed = False
        for key in _INFRA_PRESERVE_KEYS:
            current_value = row.get(key)
            prior_value = prior.get(key)
            missing_now = current_value in (None, False, 0, "", [], {})
            if key == "completeness":
                missing_now = float(current_value or 0) < float(prior_value or 0)
            if missing_now and prior_value not in (None, False, 0, "", [], {}):
                row[key] = prior[key]
                changed = True
        for key in _VALUATION_PRESERVE_KEYS:
            current_value = row.get(key)
            prior_value = prior.get(key)
            if _valuation_field_missing(key, current_value) and not _valuation_field_missing(
                key, prior_value
            ):
                row[key] = prior[key]
                changed = True
        restored += int(changed)
    return restored


# A sparse rebuild does not zero the infra columns, it THINS them, and the old
# guard only tripped at exactly zero. On 2026-08-11 a CI run without the ticker
# trees published total_pdfs=7 (from 8,614) and took readme 830->0,
# index_file 833->0, download_script 825->0, last_download 815->0 and
# sec_filings 555->0 with it. Every one of those passed `total_pdfs == 0`.
# Only research_dir and completeness survived, which is exactly what the old
# `with_research` half of the test looked at, so the guard read healthy while
# six of eight infra columns were gone. It reached origin/main and the
# validator caught one symptom afterwards -- by which point the artifact was
# already committed and the deploy silently skipped.
#
# Judge each preserved column on its own, by RATIO against the prior payload,
# and keep an absolute floor on total_pdfs that matches
# validate_dashboard_data.py. A cheap pre-write check must not be weaker than
# the expensive post-commit one.
_INFRA_COLLAPSE_RATIO = 0.25     # new < 25% of prior population = collapsed
_INFRA_PRIOR_MIN = 20            # prior must have had this many to judge at all
_TOTAL_PDFS_FLOOR = 100          # mirrors validate_dashboard_data.py


def refuse_infra_collapse(payload: dict, prior_by_ticker: dict[str, dict]) -> None:
    """Abort write when a sparse rebuild would publish thinned holdings infra."""
    summary = payload.get("summary") or {}
    rows = payload.get("tickers") or []
    ticker_count = int(summary.get("ticker_count") or len(rows))
    if ticker_count < 50 or len(prior_by_ticker) < 50:
        return

    def populated(records, key):
        return sum(1 for r in records if r.get(key))

    failures = []
    for key in _INFRA_PRESERVE_KEYS:
        prior_n = populated(prior_by_ticker.values(), key)
        now_n = populated(rows, key)
        if prior_n >= _INFRA_PRIOR_MIN and now_n < prior_n * _INFRA_COLLAPSE_RATIO:
            failures.append(f"{key} {prior_n}->{now_n}")

    total_pdfs = int(summary.get("total_pdfs") or 0)
    prior_pdfs = sum(int(r.get("pdf_count") or 0) for r in prior_by_ticker.values())
    if prior_pdfs >= _TOTAL_PDFS_FLOOR and total_pdfs < _TOTAL_PDFS_FLOOR:
        failures.append(f"total_pdfs {prior_pdfs}->{total_pdfs} (floor {_TOTAL_PDFS_FLOOR})")

    if failures:
        raise SystemExit(
            "Refusing to write dashboard_data.json: sparse/empty ticker checkout would "
            f"clobber infra stats over {ticker_count} tickers -- " + "; ".join(failures) + ". "
            "Rebuild with ticker trees present, or deploy committed dashboard/ as-is."
        )


def refuse_valuation_collapse(payload: dict, prior_by_ticker: dict[str, dict]) -> None:
    """Abort write when sparse rebuild would wipe VAL/IRR/range payloads."""
    rows = payload.get("tickers") or []
    if len(rows) < 50 or len(prior_by_ticker) < 50:
        return
    missing_now = sum(
        1
        for row in rows
        if _valuation_field_missing("valuation_decision", row.get("valuation_decision"))
    )
    prior_ok = sum(
        1
        for row in prior_by_ticker.values()
        if not _valuation_field_missing("valuation_decision", row.get("valuation_decision"))
    )
    # Collapse: most rows missing now while prior had broad valuation coverage.
    if prior_ok >= max(50, len(prior_by_ticker) // 2) and missing_now >= max(
        50, int(0.5 * len(rows))
    ):
        raise SystemExit(
            "Refusing to write dashboard_data.json: sparse/empty research checkout would "
            f"clobber valuation payloads (missing VAL now={missing_now}/{len(rows)}; "
            f"prior decision-ready≈{prior_ok}/{len(prior_by_ticker)}). "
            "Rebuild with ticker research trees present, or preserve prior valuation fields."
        )


def source_type_label(source_type: str | None) -> str:
    labels = {
        "superinvestor_letter": "Letters",
        "company_document": "Company",
        "third_party": "VIC / third party",
        "activist_long": "Activist (long)",
        "activist_short": "Activist (short)",
        "activist_report": "Activist",
        "sumzero_research": "SumZero",
        "research": "Research",
        "dropbox_ingestion": "Dropbox ingestion",
        "pdf": "Other PDFs",
    }
    return labels.get(source_type or "", str(source_type or "Other").replace("_", " ").title())


def catalog_ticker(doc: dict) -> str | None:
    folder = str(doc.get("drive_folder_path") or "")
    parts = [p for p in folder.split("/") if p]
    if len(parts) >= 2 and parts[0] == "Single Stocks":
        return parts[1]
    local = str(doc.get("local_pdf_path") or "")
    first = local.split("/", 1)[0]
    if first and (ROOT / first).is_dir() and first not in SKIP_TICKER_DIRS and not first.startswith((".", "_")):
        return first
    return None


def catalog_quarter(doc: dict) -> str | None:
    folder = str(doc.get("drive_folder_path") or "")
    parts = [p for p in folder.split("/") if p]
    if len(parts) >= 2 and parts[0] == "Letters":
        return parts[1]
    local = str(doc.get("local_pdf_path") or "")
    m = re.search(r"superinvestor-letters/(\d{4})Q([1-4])/", local)
    if m:
        return f"{m.group(1)} Q{m.group(2)}"
    return None


QUARTER_PATTERNS = [
    re.compile(r"(?<!\d)(20\d{2})\s*Q([1-4])(?!\d)", re.IGNORECASE),
    re.compile(r"(?<!\d)(20\d{2})\s*([1-4])Q(?:\s+Letters)?(?!\d)", re.IGNORECASE),
    re.compile(r"(?<!\d)(20\d{2})Q([1-4])(?!\d)", re.IGNORECASE),
]


def normalize_quarter_id(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    for pattern in QUARTER_PATTERNS:
        m = pattern.search(text)
        if m:
            return f"{m.group(1)}Q{m.group(2)}"
    return None


def quarter_label(quarter_id: str) -> str:
    m = re.match(r"^(20\d{2})Q([1-4])$", quarter_id)
    if not m:
        return quarter_id
    return f"Q{m.group(2)} {m.group(1)}"


def build_time_periods(rows: list[dict], folders: dict) -> dict:
    by_quarter: dict[str, dict] = {}

    def bucket(quarter_id: str) -> dict:
        year, q = int(quarter_id[:4]), int(quarter_id[-1])
        return by_quarter.setdefault(
            quarter_id,
            {
                "id": quarter_id,
                "label": quarter_label(quarter_id),
                "year": year,
                "quarter": q,
                "document_count": 0,
                "source_folder_count": 0,
                "source_folder_url": None,
            },
        )

    for row in rows:
        qid = row.get("document_quarter") or normalize_quarter_id(row.get("quarter"))
        if qid:
            bucket(qid)["document_count"] += 1

    for path, meta in (folders or {}).items():
        qid = normalize_quarter_id(path)
        if not qid:
            continue
        b = bucket(qid)
        b["source_folder_count"] += 1
        if not b.get("source_folder_url"):
            b["source_folder_url"] = (meta or {}).get("webViewLink")

    quarters = sorted(by_quarter.values(), key=lambda q: (q["year"], q["quarter"]), reverse=True)
    years = sorted({q["year"] for q in quarters}, reverse=True)
    latest_catalog = quarters[0]["id"] if quarters else None
    return {
        "latest_quarter": latest_catalog,
        "latest_catalog_quarter": latest_catalog,
        "years": years,
        "available_quarters": quarters,
    }


def load_drive_folder_index() -> dict:
    if not DRIVE_FOLDER_INDEX_PATH.exists():
        return {"folders": {}, "generated_at": None}
    try:
        return json.loads(DRIVE_FOLDER_INDEX_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"folders": {}, "generated_at": None}


def folder_url(folder_id: str | None) -> str | None:
    return f"https://drive.google.com/drive/folders/{folder_id}" if folder_id else None


def build_document_catalog(document_registry: dict | None) -> dict | None:
    if not isinstance(document_registry, dict):
        return None
    docs = document_registry.get("documents") or []
    folder_index = load_drive_folder_index()
    folders = folder_index.get("folders") or {}
    rows: list[dict] = []
    by_source: Counter[str] = Counter()
    by_ticker: Counter[str] = Counter()
    by_quarter: Counter[str] = Counter()
    for doc in docs:
        source_type = doc.get("source_type") or "pdf"
        ticker = catalog_ticker(doc)
        period = infer_document_period(doc)
        quarter = period.quarter_display or catalog_quarter(doc)
        folder_path = doc.get("drive_folder_path")
        row = {
            "document_id": doc.get("document_id"),
            "title": doc.get("title"),
            "ticker": ticker,
            "quarter": quarter,
            "document_date": period.document_date,
            "document_year": period.document_year,
            "document_quarter": period.document_quarter,
            "period_label": period.period_label,
            "period_source": period.period_source,
            "source_type": source_type,
            "source_label": source_type_label(source_type),
            "drive_folder_path": folder_path,
            "drive_folder_id": doc.get("drive_folder_id"),
            "drive_folder_url": folder_url(doc.get("drive_folder_id")),
            "drive_web_view_link": doc.get("drive_web_view_link"),
            "modified_at": doc.get("modified_at"),
            "size_bytes": doc.get("size_bytes"),
        }
        if folder_path and folder_path in folders:
            row["drive_folder_id"] = folders[folder_path].get("id") or row.get("drive_folder_id")
            row["drive_folder_url"] = folders[folder_path].get("webViewLink") or folder_url(row.get("drive_folder_id"))
        rows.append(row)
        by_source[source_type] += 1
        if ticker:
            by_ticker[ticker] += 1
        if quarter:
            by_quarter[quarter] += 1
        elif period.document_quarter:
            by_quarter[period.quarter_display or quarter_label(period.document_quarter)] += 1
    rows.sort(key=catalog_sort_key)
    catalog = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "registry_generated_at": document_registry.get("generated_at"),
        "folder_index_generated_at": folder_index.get("generated_at"),
        "time_periods": build_time_periods(rows, folders),
        "summary": {
            "document_count": len(rows),
            "uploaded_count": (document_registry.get("summary") or {}).get("uploaded_count", 0),
            "pending_upload_count": (document_registry.get("summary") or {}).get("pending_upload_count", 0),
            "by_source_type": dict(sorted(by_source.items())),
            "by_ticker": dict(sorted(by_ticker.items())),
            "by_quarter": dict(sorted(by_quarter.items(), reverse=True)),
        },
        "known_tickers": sorted(by_ticker.keys()),
        "documents": rows,
    }
    DOCUMENT_CATALOG_PATH.write_text(json.dumps(catalog, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return catalog


def attach_pdf_store_rows(rows: list[dict], catalog: dict | None) -> None:
    if not isinstance(catalog, dict):
        return
    folders = (load_drive_folder_index().get("folders") or {})
    by_ticker = ((catalog.get("summary") or {}).get("by_ticker") or {})
    for row in rows:
        ticker = row.get("ticker")
        ticker_folder = folders.get(f"Single Stocks/{ticker}") or {}
        row["pdf_store"] = {
            "count": int(by_ticker.get(ticker, 0) or 0),
            "drive_folder_path": f"Single Stocks/{ticker}",
            "drive_folder_id": ticker_folder.get("id"),
            "drive_folder_url": ticker_folder.get("webViewLink") or folder_url(ticker_folder.get("id")),
        }


def count_sec_filings(ticker_dir: Path) -> int:
    sec = ticker_dir / "investor-documents" / "sec-edgar"
    if sec.exists():
        return sum(1 for f in sec.iterdir() if f.is_file())
    return 0


def last_download(ticker_dir: Path) -> str | None:
    log = ticker_dir / "_download_log.txt"
    if not log.exists():
        return None
    lines = [ln.strip() for ln in log.read_text(encoding="utf-8", errors="ignore").splitlines() if ln.strip()]
    if not lines:
        return None
    last = lines[-1]
    m = re.match(r"(\d{4}-\d{2}-\d{2}T[\d:.+-]+)", last)
    if m:
        return m.group(1)[:10]
    return None


def last_research(ticker_dir: Path) -> str | None:
    research = ticker_dir / "research"
    if not research.exists():
        return None
    files = [f for f in research.rglob("*") if f.is_file()]
    if not files:
        return None
    latest = max(files, key=lambda f: f.stat().st_mtime)
    return datetime.fromtimestamp(latest.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%d")


def load_classification() -> dict[str, dict]:
    if not CLASS_PATH.exists():
        return {}
    return json.loads(CLASS_PATH.read_text(encoding="utf-8"))


def load_investment_sleeve_index() -> tuple[dict[str, str], dict[str, str]]:
    """Map ticker -> sleeve id and sleeve id -> display label."""
    if not SLEEVES_PATH.exists():
        return {}, {}
    try:
        doc = json.loads(SLEEVES_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}, {}
    ticker_to_sleeve: dict[str, str] = {}
    labels: dict[str, str] = {}
    for sleeve_id, meta in (doc.get("sleeves") or {}).items():
        labels[sleeve_id] = meta.get("label") or sleeve_id
        for ticker in meta.get("tickers") or []:
            ticker_to_sleeve[str(ticker).upper()] = sleeve_id
    return ticker_to_sleeve, labels


_INVESTMENT_SLEEVE_INDEX, _INVESTMENT_SLEEVE_LABELS = load_investment_sleeve_index()


def parse_classification_from_thesis(ticker_dir: Path) -> dict | None:
    thesis = ticker_dir / "research" / "thesis.md"
    if not thesis.exists():
        return None
    text = thesis.read_text(encoding="utf-8", errors="ignore")
    fields = {}
    for key, label in [
        ("archetype", r"Archetype"),
        ("moat", r"Moat"),
        ("dhando", r"Dhando"),
        ("stance", r"Stance"),
        ("cycle", r"Cycle"),
        ("implied_irr", r"Implied 7yr IRR"),
        ("irr_method", r"IRR method"),
        ("lawrence_bucket", r"Lawrence bucket"),
    ]:
        m = re.search(rf"\*\*{label}\*\*[^|]*\|\s*([^\|]+)", text)
        if m:
            fields[key] = m.group(1).strip()
    return fields if fields else None


def parse_irr_pct(implied: str | None) -> float | None:
    if not implied or implied in ("pending", "—", "-", None):
        return None
    m = re.match(r"(-?\d+(?:\.\d+)?)", str(implied).strip())
    return float(m.group(1)) if m else None


def load_valuation(ticker_dir: Path) -> dict | None:
    for name in ("valuation.json", "irr_model.json"):
        path = ticker_dir / "research" / name
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return None
    return None


_CVR_UNIVERSE_CACHE: dict | None = None


def load_cvr_universe() -> dict:
    global _CVR_UNIVERSE_CACHE
    if _CVR_UNIVERSE_CACHE is None:
        _CVR_UNIVERSE_CACHE = _load_json(CVR_UNIVERSE_PATH) or {}
    return _CVR_UNIVERSE_CACHE or {}


def cvr_universe_index() -> dict[str, dict]:
    """Map dashboard ticker -> universe row (pre_close or post_close)."""
    doc = load_cvr_universe()
    out: dict[str, dict] = {}
    for row in doc.get("pre_close_opportunities") or []:
        t = str(row.get("ticker") or "").strip()
        if t:
            out[t.upper()] = {**row, "stage": row.get("stage") or "pre_close"}
    for row in doc.get("post_close_universe") or []:
        t = str(row.get("ticker") or "").strip()
        if t:
            out[t.upper()] = {**row, "stage": row.get("stage") or "post_close"}
    return out


def _cvr_next_milestone(terms: dict) -> dict | None:
    milestones = terms.get("milestones") or []
    open_ms = [m for m in milestones if (m.get("status") or "open") == "open"]
    pool = open_ms or milestones
    if not pool:
        return None
    best = pool[0]
    # Prefer explicit ISO-ish deadline strings for sorting when present.
    def _key(m: dict) -> str:
        return str(
            m.get("deadline")
            or m.get("outside_date")
            or m.get("deadline_press")
            or m.get("deadline_primary")
            or "9999"
        )

    best = sorted(pool, key=_key)[0]
    return {
        "id": best.get("id"),
        "description": best.get("description"),
        "amount_usd": best.get("amount_usd")
        or best.get("amount_primary_usd")
        or best.get("max_payout_usd"),
        "deadline": best.get("deadline")
        or best.get("deadline_press")
        or best.get("deadline_primary")
        or best.get("outside_date"),
        "status": best.get("status") or "open",
    }


def cvr_summary(ticker: str, ticker_dir: Path) -> dict | None:
    """Compact CVR / contingent-consideration payload for dashboard filter + detail."""
    urow = cvr_universe_index().get(ticker.upper())
    terms_path = ticker_dir / "research" / "cvr_terms.json"
    terms = _load_json(terms_path) if terms_path.exists() else None
    if not urow and not terms:
        return None
    terms = terms or {}
    parent = terms.get("parent_deal") or {}
    stage = (urow or {}).get("stage") or terms.get("stage") or "unknown"
    max_payout = (
        (urow or {}).get("max_contingent_usd")
        or (urow or {}).get("max_payout_usd")
        or terms.get("max_payout_usd")
        or parent.get("contingent_cash_per_share")
    )
    tradeable = terms.get("tradeable")
    if tradeable is None:
        tradeable = bool((urow or {}).get("tradeable")) if "tradeable" in (urow or {}) else stage == "pre_close"
    sec_links = terms.get("sec_links") or []
    primary_sec = None
    for link in sec_links:
        if link.get("url"):
            primary_sec = {"label": link.get("label") or "SEC", "url": link.get("url")}
            break
    next_ms = _cvr_next_milestone(terms)
    display = {
        "pre_close": "Pre-close opportunity",
        "post_close": "Post-close claim",
        "resolved": "Resolved",
    }.get(str(stage), str(stage).replace("_", " "))
    return {
        "id": (urow or {}).get("id") or terms.get("cvr_id") or ticker,
        "stage": stage,
        "stage_label": display,
        "role": (urow or {}).get("role") or terms.get("sleeve_classification", {}).get("book_type"),
        "tradeable": bool(tradeable),
        "tradeable_vehicle": (urow or {}).get("tradeable_vehicle")
        or terms.get("tradeable_vehicle")
        or (ticker if stage == "pre_close" else None),
        "max_payout_usd": max_payout,
        "upfront_cash_usd": (urow or {}).get("upfront_cash_usd") or parent.get("upfront_cash_per_share"),
        "stated_max_usd": (urow or {}).get("stated_max_usd") or parent.get("total_stated_max_per_share"),
        "acquirer": (urow or {}).get("acquirer") or parent.get("acquirer") or parent.get("acquirer_ticker"),
        "outside_date": (urow or {}).get("outside_date") or terms.get("outside_date"),
        "expected_close": (urow or {}).get("expected_close") or parent.get("expected_close"),
        "catalyst": (urow or {}).get("catalyst"),
        "next_milestone": next_ms,
        "p_market": terms.get("p_market")
        if terms.get("p_market") is not None
        else ((terms.get("display") or {}).get("p_market") if isinstance(terms.get("display"), dict) else None),
        "p_marvin": terms.get("p_marvin")
        if terms.get("p_marvin") is not None
        else ((terms.get("display") or {}).get("p_marvin") if isinstance(terms.get("display"), dict) else None),
        "irr_at_buy": terms.get("irr_at_buy")
        if terms.get("irr_at_buy") is not None
        else ((terms.get("display") or {}).get("irr_at_buy") if isinstance(terms.get("display"), dict) else None),
        "primary_sec": primary_sec,
        "terms_path": str(terms_path.relative_to(ROOT)).replace("\\", "/") if terms_path.exists() else None,
        "as_of": terms.get("as_of") or terms.get("extraction_date") or (urow or {}).get("as_of"),
    }


def fund_nav_summary(ticker_dir: Path, holdings_meta: dict | None = None) -> dict | None:
    """Compact NAV-discount sleeve payload for dashboard chips/columns."""
    val = load_valuation(ticker_dir) or {}
    overlay = val.get("fund_nav_overlay") if isinstance(val, dict) else None
    cls = (holdings_meta or {}).get("classification") or {}
    instrument = (
        (val or {}).get("instrument_type")
        or cls.get("instrument_type")
        or (holdings_meta or {}).get("instrument_type")
    )
    edge = None
    if isinstance(overlay, dict):
        edge = overlay.get("edge")
    edge = edge or cls.get("fund_edge")
    if not overlay and not instrument and not edge:
        return None
    overlay = overlay or {}
    disc = overlay.get("discount_to_reported_nav_pct")
    disc_econ_local = overlay.get("discount_to_mtm_nav_local_only_pct")
    disc_econ_full = overlay.get("discount_to_mtm_nav_full_proxy_pct")
    # Prefer local-only MTM when present (ADR/GDR mapping can overstate full proxy).
    disc_econ = disc_econ_local if disc_econ_local is not None else disc_econ_full
    has_zero = bool(overlay.get("zero_marked_sleeves"))
    edge_key = str(edge or "classic")
    # Shadow / zero-marked sleeves: reported (GAAP) NAV is not the economic source of truth.
    show_both = bool(
        edge_key == "shadow"
        or has_zero
        or (
            disc is not None
            and disc_econ is not None
            and abs(float(disc_econ) - float(disc)) >= 5.0
        )
    )
    return {
        "instrument_type": instrument or "closed_end_fund",
        "edge": edge_key,
        "edge_label": {
            "classic": "Classic discount",
            "shadow": "Shadow NAV",
            "holdco": "Holdco look-through",
        }.get(edge_key, edge_key),
        "as_of": overlay.get("as_of") or val.get("as_of"),
        "currency": overlay.get("currency") or (val.get("inputs") or {}).get("currency"),
        "market_price": overlay.get("market_price"),
        "reported_nav": overlay.get("reported_nav"),
        "liquid_nav_per_share": overlay.get("liquid_nav_per_share"),
        "complete_nav_per_share_base": overlay.get("complete_nav_per_share_base"),
        "complete_nav_per_share_illustration_local": overlay.get(
            "complete_nav_per_share_illustration_local"
        ),
        "complete_nav_per_share_illustration_full_proxy": overlay.get(
            "complete_nav_per_share_illustration_full_proxy"
        ),
        "discount_to_reported_nav_pct": disc,
        "discount_to_liquid_nav_pct": overlay.get("discount_to_liquid_nav_pct"),
        "discount_to_complete_nav_pct": overlay.get("discount_to_complete_nav_pct"),
        "discount_to_mtm_nav_local_only_pct": disc_econ_local,
        "discount_to_mtm_nav_full_proxy_pct": disc_econ_full,
        "discount_to_economic_nav_pct": disc_econ,
        "show_reported_and_economic_discount": show_both,
        "has_zero_marked_sleeve": has_zero,
    }


def classification_for(ticker: str, ticker_dir: Path, portfolio: dict[str, dict]) -> dict:
    from_thesis = parse_classification_from_thesis(ticker_dir)
    from_json = portfolio.get(ticker, {})
    merged = {**from_json, **(from_thesis or {})}
    defaults = {
        "archetype": "unknown",
        "moat": "unproven",
        "dhando": "pending",
        "stance": "watch",
        "cycle": "—",
        "implied_irr": "pending",
        "irr_method": "pending",
        "lawrence_bucket": "—",
        "investment_sleeve": "—",
        "investment_sleeve_label": "—",
        "instrument_type": "—",
        "fund_edge": "—",
    }
    out = {k: merged.get(k, defaults[k]) for k in defaults}
    val = load_valuation(ticker_dir)
    if val:
        if not val.get("ticker"):
            val["ticker"] = ticker_dir.name
        authority = resolve_authority(ticker_dir / "research", val)
        irr_web = website_implied_irr(val)
        inputs = val.get("classification_inputs") or {}
        for key in ("archetype", "moat", "dhando", "cycle", "investment_sleeve", "payoff_lens"):
            if inputs.get(key) and inputs[key] not in ("-", "—", "pending"):
                out[key] = inputs[key]
        if val.get("instrument_type"):
            out["instrument_type"] = val["instrument_type"]
        fund_overlay = val.get("fund_nav_overlay") or {}
        if isinstance(fund_overlay, dict) and fund_overlay.get("edge"):
            out["fund_edge"] = fund_overlay["edge"]
        authority_display = contract_return_display(authority)
        if authority_display:
            out["implied_irr"] = authority_display
        elif authority.get("authority_level") == "legacy_reference" and irr_web.get("display"):
            out["implied_irr"] = irr_web["display"] + " [legacy]"
        method = authority.get("profile_id") or val.get("method", val.get("irr_method"))
        if method and out.get("irr_method") == "pending":
            out["irr_method"] = method
        bucket = val.get("lawrence_bucket")
        if bucket and out.get("lawrence_bucket") == "—":
            out["lawrence_bucket"] = bucket
        out["valuation_authority"] = authority.get("authority_level")
        out["valuation_status"] = authority.get("status")
        out["decision_actionable"] = bool(authority.get("actionable"))
        if authority.get("decision"):
            out["stance_proposed"] = authority["decision"]
        if authority.get("actionable") and authority.get("stance"):
            out["stance"] = authority["stance"]
        if val.get("as_of"):
            out["analysis_as_of"] = val["as_of"]
        contract_base = (authority.get("return_range_pct") or {}).get("base")
        if contract_base is not None:
            out["analysis_irr_pct"] = float(contract_base)
        elif authority.get("authority_level") == "legacy_reference" and irr_web.get("base_pct") is not None:
            out["analysis_irr_pct"] = float(irr_web["base_pct"])
        else:
            out["analysis_irr_pct"] = parse_irr_pct(out.get("implied_irr"))
        gate_pct = irr_web.get("lawrence_stance_gate_pct")
        if gate_pct is not None:
            out["filing_irr_ref"] = f"{gate_pct}% (stance gate)"
        elif irr_web.get("falsifier_adjusted_pct") is not None:
            out["filing_irr_ref"] = f"{irr_web['falsifier_adjusted_pct']}% (falsifier-adjusted)"
        if irr_web.get("synthesis_status") == "complete":
            out["irr_source"] = "total_synthesis"
    sleeve_id = _INVESTMENT_SLEEVE_INDEX.get(ticker.upper())
    if sleeve_id and out.get("investment_sleeve") in ("—", "-", "pending", None, ""):
        out["investment_sleeve"] = sleeve_id
    if out.get("investment_sleeve") and out["investment_sleeve"] not in ("—", "-", "pending"):
        out["investment_sleeve_label"] = _INVESTMENT_SLEEVE_LABELS.get(
            out["investment_sleeve"], out["investment_sleeve"]
        )
    return out


def valuation_human_review(ticker_dir: Path) -> dict | None:
    val = load_valuation(ticker_dir)
    if not val:
        return None
    authority = resolve_authority(ticker_dir / "research", val)
    if authority.get("authority_level") == "legacy_reference":
        return None
    return {
        "approved_stance": authority.get("stance") if authority.get("actionable") else None,
        "model_stance": authority.get("committee_recommendation"),
        "override_reason": None,
        "entry_band_15pct": None,
        "live_price_confirmed": None,
        "approved_date": None,
        "notes": f"Authority: {authority.get('authority_level')} / {authority.get('status')}",
        "authority_level": authority.get("authority_level"),
        "decision_actionable": authority.get("actionable"),
    }


def property_register_summary(ticker_dir: Path) -> dict | None:
    """Property inventory for the Valuation drawer (from properties.json + valuation summary)."""
    reg_path = ticker_dir / "research" / "properties.json"
    if not reg_path.exists():
        return None
    try:
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    val = load_valuation(ticker_dir) or {}
    summary = val.get("property_register") or {}
    props = []
    for row in reg.get("properties") or []:
        fv = row.get("estimated_fair_value_usd") or {}
        income = row.get("income") or {}
        units = row.get("units") or {}
        props.append({
            "id": row.get("id"),
            "name": row.get("name"),
            "type": row.get("type"),
            "location": row.get("location"),
            "status": row.get("status"),
            "nav_overlay_line": row.get("nav_overlay_line"),
            "carrying_value_usd": row.get("carrying_value_usd"),
            "fair_value_usd": {
                "low": fv.get("low") if isinstance(fv, dict) else None,
                "base": fv.get("base") if isinstance(fv, dict) else None,
                "high": fv.get("high") if isinstance(fv, dict) else None,
            },
            "annualized_cash_noi_usd": income.get("annualized_cash_noi_usd"),
            "annualized_cash_rent_usd": income.get("annualized_cash_rent_usd"),
            "units": {
                "acres": units.get("acres"),
                "sqft": units.get("sqft"),
                "acre_feet": units.get("acre_feet"),
                "nra": units.get("nra"),
            },
            "valuation_basis": row.get("valuation_basis"),
            "source": row.get("source"),
            "flags": row.get("flags") or [],
        })
    recon = summary.get("reconciliation") or {}
    return {
        "as_of": summary.get("as_of") or reg.get("as_of"),
        "source": summary.get("source") or reg.get("source"),
        "status": summary.get("status") or ("ok" if props else "missing"),
        "in_base_irr": bool(summary.get("in_base_irr", reg.get("in_base_irr", False))),
        "property_count": summary.get("property_count") or len(props),
        "total_fair_value_usd": summary.get("total_fair_value_usd"),
        "total_fair_value_m": summary.get("total_fair_value_m"),
        "types": summary.get("types") or {},
        "reconciliation_ok": recon.get("ok"),
        "unknown_targets": recon.get("unknown_targets") or [],
        "properties": props,
        "github_url": github_blob_url(reg_path.relative_to(ROOT).as_posix()) if reg_path.exists() else None,
        "updated_at": summary.get("updated_at"),
    }


def valuation_component_summary(ticker_dir: Path) -> dict | None:
    """Small, presentation-safe component valuation payload for the dashboard."""
    val = load_valuation(ticker_dir)
    if not val:
        return None
    result = val.get("component_valuation_results") or {}
    if not result:
        return None
    raw_total = result.get("total_equity_value_per_share") or {}
    total = floor_equity_value_range(raw_total, ndigits=4)
    price = result.get("market_price_per_share")
    upside = result.get("upside_downside_pct")
    if price is not None and any(
        isinstance(raw_total.get(k), (int, float)) and raw_total[k] < 0 for k in ("low", "base", "high")
    ):
        try:
            px = float(price)
            if px > 0:
                upside = {
                    key: round((float(total[key]) / px - 1) * 100, 1)
                    for key in ("low", "base", "high")
                    if total.get(key) is not None
                }
        except (TypeError, ValueError):
            pass
    components = []
    for row in [*(result.get("additive_components") or []), *(result.get("embedded_components") or [])]:
        components.append({
            "id": row.get("id"),
            "label": row.get("label"),
            "category": row.get("category"),
            "treatment": row.get("treatment"),
            "method": row.get("method"),
            "evidence_tier": row.get("evidence_tier"),
            "driver_model_type": row.get("driver_model_type"),
            "assumption_summary": row.get("assumption_summary"),
            "low_per_share": row.get("low_per_share"),
            "base_per_share": row.get("base_per_share"),
            "high_per_share": row.get("high_per_share"),
            "cross_check": row.get("cross_check"),
        })
    queue = val.get("component_review_queue") or {}
    economic = val.get("economic_value_analysis") or {}
    return {
        "status": result.get("status"),
        "all_material_components_identified": result.get("all_material_components_identified", False),
        "decision_rule": result.get("decision_rule"),
        "market_price_per_share": result.get("market_price_per_share"),
        "total_equity_value_per_share": total,
        "upside_downside_pct": _sane_upside_pct(upside),
        "material_component_count": result.get("material_component_count", 0),
        "additive_component_count": result.get("additive_component_count", 0),
        "embedded_component_count": result.get("embedded_component_count", 0),
        "components": components,
        "review_status": queue.get("status"),
        "review_open_count": len([x for x in queue.get("items", []) if x.get("status") == "open"]),
        "economic_value": {
            "status": economic.get("status"),
            "gaap_role": economic.get("gaap_role"),
            "accounting_reference": economic.get("accounting_reference"),
            "economic_claim": economic.get("economic_claim"),
            "valuation_proof": economic.get("valuation_proof") or [],
            "validation_errors": economic.get("validation_errors") or [],
            "complete_component_coverage": economic.get("complete_component_coverage"),
        } if economic else None,
    }


def investment_committee_summary(ticker_dir: Path) -> dict | None:
    """Latest committee result, reduced to decision-relevant presentation fields."""
    research = ticker_dir / "research"
    paths = sorted(research.glob("committee_????-??-??.json"))
    if not paths:
        return None
    try:
        record = json.loads(paths[-1].read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    synthesis = record.get("synthesis") or {}
    decision = record.get("human_decision") or {}
    return {
        "as_of": (record.get("review") or {}).get("as_of"),
        "state": record.get("final_state"),
        "vote_split": synthesis.get("vote_split") or {},
        "score_medians": synthesis.get("score_medians") or {},
        "strongest_dissent": synthesis.get("strongest_dissent"),
        "unresolved_items": synthesis.get("unresolved_items") or [],
        "owner_status": decision.get("status"),
        "owner_decision": decision.get("decision"),
        "selected_raters": [r.get("persona") for r in record.get("selected_raters", [])],
    }


def valuation_workbench_summary(ticker_dir: Path) -> dict | None:
    """Consolidated committee, evidence, method-fit, outcome, and attribution views."""
    path = ticker_dir / "research" / "valuation_workbench.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    decision = dict(data.get("decision") or {})
    if decision.get("value_per_share"):
        decision["value_per_share"] = floor_equity_value_range(decision["value_per_share"], ndigits=4)
    valuation = dict(data.get("valuation") or {})
    if valuation.get("value_per_share"):
        valuation["value_per_share"] = floor_equity_value_range(valuation["value_per_share"], ndigits=4)
    return {
        "as_of": data.get("as_of"),
        "decision": decision,
        "business": data.get("business") or {},
        "valuation": valuation,
        "optionality": data.get("optionality") or {},
        "committee": data.get("committee") or {},
        "evidence": data.get("evidence") or {},
        "method_fit": data.get("method_fit") or {},
        "outcomes": data.get("outcomes") or {},
        "attribution": data.get("attribution") or {},
        "github_url": github_blob_url(path.relative_to(ROOT).as_posix()),
    }


CLOSED_GAP_STATUSES = frozenset({"resolved", "accepted", "not_applicable", "met"})
ABSURD_UPSIDE_PCT = 50_000


def _sane_upside_pct(upside: dict | None) -> dict | None:
    """Drop multi-million % gaps caused by share-count unit bugs."""
    if not isinstance(upside, dict):
        return None
    values = [upside.get(k) for k in ("low", "base", "high") if upside.get(k) is not None]
    if not values:
        return None
    if any(abs(float(v)) > ABSURD_UPSIDE_PCT for v in values):
        return None
    return upside


def _extreme_return_validated(ticker_dir: Path) -> bool:
    """Read model_checks.extreme_return_validated from the ticker's contract.

    universal_valuation_contract sets this only when
    valuation_methodology.outlier_validation passed with at least one
    independent method and evidence refs, so it is the single definition of a
    corroborated outlier. Surfaced into the dashboard row so the validator can
    apply the IRR gate without needing the ticker tree.
    """
    path = ticker_dir / "research" / "valuation_contract.json"
    if not path.exists():
        return False
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, ValueError):
        return False
    return bool((contract.get("model_checks") or {}).get("extreme_return_validated"))


def valuation_decision_summary(
    ticker: str,
    ticker_dir: Path,
    workbench: dict | None = None,
    component: dict | None = None,
) -> dict:
    """Slim readiness payload for holdings-table badges and filters."""
    wb = workbench if workbench is not None else valuation_workbench_summary(ticker_dir)
    cv = component if component is not None else valuation_component_summary(ticker_dir)
    followups_path = ROOT / "_system" / "reference" / "valuation_followups.json"
    followups = {}
    if followups_path.exists():
        try:
            followups = json.loads(followups_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            followups = {}
    ticker_cfg = (followups.get("tickers") or {}).get(ticker) or (followups.get("tickers") or {}).get(ticker.upper()) or {}
    gaps = list(ticker_cfg.get("evidence_gaps") or [])
    open_gaps = [g for g in gaps if g.get("status") not in CLOSED_GAP_STATUSES]
    critical = [g for g in open_gaps if g.get("priority") == "critical"]
    decision = (wb or {}).get("decision") or {}
    evidence = (wb or {}).get("evidence") or {}
    method = (wb or {}).get("method_fit") or {}
    open_count = int(evidence.get("open_count") if evidence.get("open_count") is not None else len(open_gaps))
    critical_count = int(evidence.get("critical_count") if evidence.get("critical_count") is not None else len(critical))
    status = decision.get("status")
    if critical_count > 0 or open_count > 0:
        status = "evidence_blocked"
    elif status == "decision_grade":
        status = "decision_grade"
    elif wb:
        status = status or "evidence_blocked"
    elif cv:
        status = "provisional"
    else:
        # First-pass inventory without workbench
        phase2 = ticker_dir / "research"
        first_pass = list(phase2.glob("evidence_reconciliation_*_phase2_first_pass.json")) if phase2.exists() else []
        if first_pass or ticker_cfg.get("rollout_wave"):
            status = "provisional"
        else:
            status = "missing"
    next_gap = None
    for gap in critical + open_gaps:
        next_gap = gap.get("id")
        break
    if not next_gap and (evidence.get("gaps") or []):
        next_gap = (evidence["gaps"][0] or {}).get("id")
    diagnostic_returns = (
        decision.get("annualized_return_at_price_pct")
        or ((wb or {}).get("valuation") or {}).get("annualized_return_at_price_pct")
        or (((wb or {}).get("valuation") or {}).get("valuation") or {}).get("annualized_return_at_price_pct")
    )
    return {
        "status": status,
        "provisional": status in {"evidence_blocked", "provisional"},
        "open_gap_count": open_count,
        "critical_gap_count": critical_count,
        "method_profile": ticker_cfg.get("method_profile") or method.get("profile_id"),
        "primary_power_zone": decision.get("primary_power_zone") or method.get("label"),
        "value_per_share": decision.get("value_per_share") or (cv or {}).get("total_equity_value_per_share"),
        "upside_downside_pct": _sane_upside_pct(
            (cv or {}).get("upside_downside_pct") or decision.get("upside_downside_pct")
        ),
        # Keep diagnostic returns inside the workbench, but never publish an
        # unvalidated IRR into the front-page ranking or D1 valuation table.
        "annualized_return_at_price_pct": diagnostic_returns if status == "decision_grade" else None,
        # Whether an extreme IRR has been corroborated by outlier_validation.
        # Carried in the payload because validate_dashboard_data.py runs in the
        # sparse "pages" checkout, which has no ticker trees to read the
        # contract from -- reading it there silently treats every outlier as
        # uncorroborated and fails the deploy.
        "extreme_return_validated": _extreme_return_validated(ticker_dir),
        "horizon_years": (
            decision.get("horizon_years")
            or ((wb or {}).get("valuation") or {}).get("horizon_years")
            or (((wb or {}).get("valuation") or {}).get("valuation") or {}).get("horizon_years")
        ),
        "price_per_share": decision.get("price_per_share") or (cv or {}).get("market_price_per_share"),
        "next_action": decision.get("next_action"),
        "next_gap_id": next_gap,
        "rollout_wave": ticker_cfg.get("rollout_wave"),
        "in_validation_cohort": any(
            (row.get("ticker") or "").upper() == ticker.upper()
            for row in (followups.get("validation_cohort") or [])
        ) or ticker.upper() in {
            "TPL", "LB", "WBI", "AZLCZ", "MSB", "C", "NVR", "NUE", "BIIB",
        },
    }


def valuation_queue_summary(rows: list[dict]) -> dict:
    """Portfolio Valuation Queue built from followups + per-ticker decision summaries."""
    followups_path = ROOT / "_system" / "reference" / "valuation_followups.json"
    try:
        followups = json.loads(followups_path.read_text(encoding="utf-8")) if followups_path.exists() else {}
    except (json.JSONDecodeError, OSError):
        followups = {}
    by_ticker = {str(r.get("ticker") or "").upper(): r for r in rows}
    items = []
    for ticker, cfg in (followups.get("tickers") or {}).items():
        row = by_ticker.get(str(ticker).upper()) or {}
        decision = row.get("valuation_decision") or {}
        gaps = [g for g in (cfg.get("evidence_gaps") or []) if g.get("status") not in CLOSED_GAP_STATUSES]
        critical = [g for g in gaps if g.get("priority") == "critical"]
        next_gap = critical[0] if critical else (gaps[0] if gaps else {})
        progress_note = str(next_gap.get("progress_note") or "")
        progress_tier = "unknown"
        note_l = progress_note.lower()
        if note_l.startswith("partially_met") or "partially_met:" in note_l:
            progress_tier = "partially_met"
        elif note_l.startswith("not_met") or "not_met:" in note_l:
            progress_tier = "not_met"
        elif note_l.startswith("met") or note_l.startswith("resolved"):
            progress_tier = "met"
        items.append({
            "ticker": ticker,
            "company": row.get("company") or ticker,
            "method_profile": cfg.get("method_profile") or decision.get("method_profile"),
            "rollout_wave": cfg.get("rollout_wave") or decision.get("rollout_wave") or (
                "validation_cohort" if decision.get("in_validation_cohort") else "followups"
            ),
            "decision_status": decision.get("status") or ("evidence_blocked" if gaps else "missing"),
            "open_gap_count": decision.get("open_gap_count", len(gaps)),
            "critical_gap_count": decision.get("critical_gap_count", len(critical)),
            "next_gap_id": decision.get("next_gap_id") or next_gap.get("id"),
            "next_gap_question": next_gap.get("question"),
            "next_gap_progress_note": progress_note or None,
            "next_gap_progress_tier": progress_tier,
            "value_per_share": decision.get("value_per_share"),
            "primary_power_zone": decision.get("primary_power_zone"),
            "in_validation_cohort": bool(decision.get("in_validation_cohort")),
        })
    items.sort(key=lambda r: (
        0 if r.get("in_validation_cohort") else 1,
        -(r.get("critical_gap_count") or 0),
        str(r.get("ticker") or ""),
    ))
    waves = followups.get("expansion_waves") or {}
    return {
        "generated_from": "_system/reference/valuation_followups.json",
        "counts": {
            "tickers": len(items),
            "evidence_blocked": sum(1 for r in items if r.get("decision_status") == "evidence_blocked"),
            "decision_grade": sum(1 for r in items if r.get("decision_status") == "decision_grade"),
            "provisional": sum(1 for r in items if r.get("decision_status") == "provisional"),
            "open_gaps": sum(int(r.get("open_gap_count") or 0) for r in items),
            "critical_gaps": sum(int(r.get("critical_gap_count") or 0) for r in items),
        },
        "expansion_waves": waves,
        "items": items,
    }


def pricing_analysis_summary(ticker_dir: Path) -> dict | None:
    path = ticker_dir / "research" / "pricing_analysis.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    values = floor_equity_value_range(data.get("component_value_per_share") or {}, ndigits=4)
    return {
        "as_of": data.get("as_of"),
        "price": data.get("price"),
        "component_value_per_share": values,
        "upside_downside_pct": data.get("upside_downside_pct"),
        "current_supported_value": data.get("base_value_supported_by_current_or_contracted_assets"),
        "market_price_above_supported_value": data.get("market_price_above_current_or_contracted_value"),
        "implied_growth_pct": data.get("market_implied_constant_owner_cash_growth_pct"),
        "entry_prices": data.get("entry_prices_by_hurdle_and_case"),
        "entry_price_15pct_base": data.get("primary_entry_price_15pct_base"),
        "decision": data.get("decision"),
        "conclusion": data.get("pricing_conclusion"),
        "strongest_counter_explanation": data.get("strongest_counter_explanation"),
        "economic_claim_note": data.get("economic_claim_note"),
        "economic_value_bridge": data.get("economic_value_bridge"),
        "committee_routing": data.get("committee_routing"),
    }


def valuation_total_return_panel(ticker: str, ticker_dir: Path) -> dict | None:
    val = load_valuation(ticker_dir)
    if not val:
        return {
            "ticker": ticker,
            "status": "missing",
            "error": "no_valuation_json",
            "chart_github_url": None,
            "chart_raw_url": None,
            "panel_github_url": None,
        }
    panel = val.get("total_return_panel") or {}
    panel_path = ticker_dir / "research" / "total_return_panel.json"
    panel_file = None
    if panel_path.exists():
        try:
            panel_file = json.loads(panel_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            panel_file = None
    merged = {}
    if isinstance(panel_file, dict):
        merged.update(panel_file)
    if isinstance(panel, dict):
        merged.update(panel)
    if not merged:
        return {
            "ticker": ticker,
            "status": "missing",
            "error": "panel_not_built",
            "chart_github_url": None,
            "chart_raw_url": None,
            "panel_github_url": None,
        }
    chart_rel = merged.get("chart")
    panel_rel = merged.get("panel_json")
    merged["chart_github_url"] = (
        github_blob_url(chart_rel) if chart_rel else None
    )
    merged["chart_raw_url"] = (
        github_raw_url(chart_rel) if chart_rel else None
    )
    merged["panel_github_url"] = (
        github_blob_url(panel_rel) if panel_rel else None
    )
    merged["ticker"] = ticker
    return merged


def thesis_status(ticker_dir: Path) -> str:
    """Legacy alias — returns archetype for backward compatibility."""
    c = parse_classification_from_thesis(ticker_dir)
    if c and c.get("archetype"):
        return c["archetype"]
    thesis = ticker_dir / "research" / "thesis.md"
    if not thesis.exists():
        return "unknown"
    text = thesis.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"\*\*Status:\*\*\s*(\w+)", text)
    return m.group(1).lower() if m else "unknown"


def one_line_thesis(ticker_dir: Path) -> str | None:
    thesis = ticker_dir / "research" / "thesis.md"
    if not thesis.exists():
        return None
    text = thesis.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"## One-line thesis\s*\n\s*\n(.+?)(?:\n\n|\Z)", text, re.DOTALL)
    if not m:
        return None
    return re.sub(r"\*\*", "", m.group(1).strip())


STALE_THESIS_PHRASE = "pending marvin deep dive"
EXEC_SUMMARY_RE = re.compile(
    r"## Executive summary\s*\n+(?!\s*##)(.+?)(?:\n\n---|\n\n## )",
    re.DOTALL | re.IGNORECASE,
)


def display_one_line_thesis(ticker_dir: Path, deep_dive: dict | None) -> str | None:
    thesis = one_line_thesis(ticker_dir)
    if thesis and STALE_THESIS_PHRASE not in thesis.lower():
        return thesis
    summary = (deep_dive or {}).get("executive_summary")
    if summary:
        first = re.match(r"([^.!?]+[.!?])", summary.strip())
        return first.group(1).strip() if first else summary[:200]
    return thesis


def _research_links(ticker: str, ticker_dir: Path) -> dict:
    research = ticker_dir / "research"
    links = {
        "folder": github_tree_url(f"{ticker}/"),
        "readme": github_blob_url(f"{ticker}/README.md") if (ticker_dir / "README.md").exists() else None,
        "thesis": github_blob_url(f"{ticker}/research/thesis.md")
        if (research / "thesis.md").exists()
        else None,
        "valuation": github_blob_url(f"{ticker}/research/valuation.json")
        if (research / "valuation.json").exists()
        else None,
        "adversarial": None,
    }
    if research.is_dir():
        adv = latest_dated_md(research, "adversarial")
        if adv:
            rel = str(adv.relative_to(ROOT)).replace("\\", "/")
            links["adversarial"] = github_blob_url(rel)
    return links


def latest_ssi_report(ticker_dir: Path) -> dict | None:
    """Pointer block for the Perplexity-grade SSI report (Phase 4 renderer):
    path + date + shipping-gate verdict + verified-claim stats."""
    research = ticker_dir / "research"
    if not research.is_dir():
        return None
    path = latest_dated_md(research, "ssi_report")
    if not path:
        return None
    date_m = re.search(r"ssi_report_(\d{4}-\d{2}-\d{2})\.md$", path.name)
    report_date = date_m.group(1) if date_m else None
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    block: dict = {
        "date": report_date,
        "path": rel,
        "url": github_blob_url(rel),
    }
    if report_date:
        gate_path = research / "evidence" / f"ssi_report_gate_{report_date}.json"
        try:
            gate = json.loads(gate_path.read_text(encoding="utf-8"))
            block["gate_result"] = gate.get("result")
            block["gate_summary"] = gate.get("summary")
        except (OSError, json.JSONDecodeError):
            pass
        verified_path = research / "evidence" / f"ssi_verified_claims_{report_date}.json"
        try:
            verified = json.loads(verified_path.read_text(encoding="utf-8"))
            block["verified_claims"] = verified.get("verified_count")
            block["failed_claims"] = verified.get("failed_count")
            block["severity5"] = sum(
                1 for c in verified.get("verified_claims", []) if c.get("severity") == 5
            )
        except (OSError, json.JSONDecodeError):
            pass
    return block


def latest_deep_dive(ticker_dir: Path, classification: dict) -> dict | None:
    research = ticker_dir / "research"
    if not research.exists():
        return None
    path = latest_dated_md(research, "deep_dive")
    if not path:
        return None
    text = path.read_text(encoding="utf-8", errors="ignore")
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    date_m = re.search(r"deep_dive_(\d{4}-\d{2}-\d{2})\.md$", path.name)
    dive_date = date_m.group(1) if date_m else None

    summary = None
    sm = EXEC_SUMMARY_RE.search(text)
    if sm:
        summary = re.sub(r"\*\*", "", sm.group(1).strip())
        if len(summary) > 600:
            summary = summary[:597] + "..."

    dive_stance = classification.get("stance", "watch")
    sm_stance = re.search(r"\*\*Stance\*\*[^|]*\|\s*(\w+)", text)
    if sm_stance:
        dive_stance = sm_stance.group(1).strip()

    return {
        "path": rel,
        "date": dive_date,
        "stance": dive_stance,
        "executive_summary": summary,
        "github_url": f"https://github.com/GoldmanDrew/single-stock-investments/blob/main/{rel}",
    }


def recent_files(ticker_dir: Path, limit: int = 5) -> list[dict]:
    skip_dirs = {"research", ".git"}
    files = []
    for f in ticker_dir.rglob("*"):
        if not f.is_file():
            continue
        if any(part.startswith("_") and part != "_scripts" for part in f.relative_to(ticker_dir).parts):
            if f.suffix.lower() not in {".pdf", ".htm", ".html"}:
                continue
        rel = str(f.relative_to(ROOT)).replace("\\", "/")
        if rel.startswith("_system"):
            continue
        files.append(f)
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    out = []
    for f in files[:limit]:
        out.append({
            "path": str(f.relative_to(ROOT)).replace("\\", "/"),
            "name": f.name,
            "date": datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%d"),
            "type": f.suffix.lower().lstrip("."),
            "github_url": github_blob_url(str(f.relative_to(ROOT)).replace("\\", "/")),
        })
    return out


def recent_developments(ticker_dir: Path, ticker: str) -> list[dict]:
    devs: list[dict] = []

    manifest = ticker_dir / "investor-documents" / "DOWNLOAD_MANIFEST.json"
    manifest_rows: list[dict] = []
    if manifest.exists():
        try:
            raw_manifest = json.loads(manifest.read_text(encoding="utf-8"))
            if isinstance(raw_manifest, list):
                manifest_rows = [r for r in raw_manifest if isinstance(r, dict)]
            else:
                manifest_rows = []
            rows = sorted(manifest_rows, key=lambda r: r.get("filingDate", ""), reverse=True)
            for row in rows[:5]:
                if row.get("form", "").startswith("8-K") and not row.get("exhibit"):
                    devs.append({
                        "date": row.get("filingDate"),
                        "type": "8-K",
                        "label": f"{row.get('form')} filed {row.get('filingDate')}",
                        "source": "SEC",
                        "url": row.get("url"),
                    })
        except json.JSONDecodeError:
            pass

    research = ticker_dir / "research"
    dive_paths: list[Path] = []
    if research.exists():
        dive_paths = sorted(
            research.glob("deep_dive_*.md"), key=dated_md_sort_key, reverse=True
        )[:2]
        for f in dive_paths:
            rel = str(f.relative_to(ROOT)).replace("\\", "/")
            devs.append({
                "date": dated_md_label(f),
                "type": "deep_dive",
                "label": f"Deep dive — {f.stem.replace('deep_dive_', '')}",
                "source": "Marvin",
                "url": github_blob_url(rel),
            })
        reports = research / "reports"
        if reports.exists():
            for f in sorted(reports.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:3]:
                devs.append({
                    "date": datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%d"),
                    "type": "research",
                    "label": f.name.replace("_", " ").replace(".md", ""),
                    "source": "Marvin",
                })

    for rf in recent_files(ticker_dir, limit=3):
        if rf["type"] == "pdf" and not any(d.get("label", "").endswith(rf["name"]) for d in devs):
            devs.append({
                "date": rf["date"],
                "type": "document",
                "label": rf["name"],
                "source": "local",
            })

    devs.sort(key=lambda d: d.get("date") or "", reverse=True)
    return devs[:6]


def completeness_score(row: dict) -> int:
    score = 0
    if row["readme"]:
        score += 20
    if row["download_script"]:
        score += 20
    if row["research_dir"]:
        score += 15
    primary_docs = row["pdf_count"] + row.get("sec_filings", 0)
    if primary_docs >= 10:
        score += 15
    if row["last_download"]:
        score += 15
    if row["index_file"]:
        score += 15
    return min(score, 100)


def has_index(ticker_dir: Path) -> bool:
    return (ticker_dir / "INDEX.csv").exists() or (ticker_dir / "document-index.csv").exists()


def transcript_summary(ticker: str, ticker_dir: Path) -> dict:
    """Verified transcript + earnings fields for dashboard (no unverified projections)."""
    manifest_path = ticker_dir / "investor-documents" / "TRANSCRIPT_MANIFEST.json"
    entries: list[dict] = []
    if manifest_path.exists():
        try:
            entries = json.loads(manifest_path.read_text(encoding="utf-8")).get("entries") or []
        except json.JSONDecodeError:
            entries = []

    earnings_path = ticker_dir / "research" / "evidence" / "earnings_calendar.json"
    earnings_events: list[dict] = []
    if earnings_path.exists():
        try:
            earnings_events = json.loads(earnings_path.read_text(encoding="utf-8")).get("events") or []
        except json.JSONDecodeError:
            earnings_events = []

    tx_sorted = sorted(
        [e for e in entries if e.get("event_type") in ("earnings", "other")],
        key=lambda e: (e.get("call_date") or "", e.get("downloaded_at") or ""),
        reverse=True,
    )
    latest_tx = tx_sorted[0] if tx_sorted else None

    reported = [e for e in earnings_events if e.get("reported") and e.get("verified")]
    reported.sort(key=lambda e: e.get("date") or "", reverse=True)
    latest_er = reported[0] if reported else None

    gap = False
    if latest_er and latest_tx:
        gap = (
            latest_er.get("fiscal_period")
            and latest_tx.get("fiscal_period")
            and latest_er.get("fiscal_period") != latest_tx.get("fiscal_period")
            and (latest_er.get("date") or "") > (latest_tx.get("call_date") or "")
        )
    elif latest_er and not latest_tx:
        gap = True

    return {
        "transcript_count": len(entries),
        "latest_transcript_date": latest_tx.get("call_date") if latest_tx else None,
        "latest_transcript_path": latest_tx.get("canonical_path") if latest_tx else None,
        "latest_reported_earnings_date": latest_er.get("date") if latest_er else None,
        "latest_reported_fiscal_period": latest_er.get("fiscal_period") if latest_er else None,
        "earnings_verified": bool(latest_er),
        "transcript_gap": gap,
    }


def load_lenses(ticker_dir: Path) -> dict | None:
    path = ticker_dir / "research" / "lenses.json"
    return _load_json(path)


def load_dossier(ticker_dir: Path) -> dict | None:
    path = ticker_dir / "research" / "dossier.json"
    return _load_json(path)


DOSSIER_STALE_DAYS = 180
DOSSIER_DELTA_MIN_SCORE = 70
DOSSIER_TIMELINE_CAP = 30


def _timeline_dedupe_key(date: str, label: str) -> tuple[str, str]:
    words = re.sub(r"[^a-z0-9 ]", "", str(label or "").lower()).split()
    return (str(date or "")[:10], " ".join(words[:6]))


def build_dossier_view(dossier: dict | None, insight_events: list[dict]) -> dict | None:
    """Merge the agent-written dossier with recent high-score insight events.

    The agent refreshes dossier.json on deep-dive runs; between runs this keeps
    the timeline current by appending high-materiality events automatically.
    """
    timeline: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for entry in (dossier or {}).get("timeline") or []:
        date = str(entry.get("date") or "")[:10]
        label = str(entry.get("label") or "").strip()
        if not date or not label:
            continue
        key = _timeline_dedupe_key(date, label)
        if key in seen:
            continue
        seen.add(key)
        timeline.append(
            {
                "date": date,
                "type": entry.get("type") or "other",
                "label": label,
                "evidence_url": entry.get("evidence_url"),
                "source": "dossier",
            }
        )

    auto_added = 0
    for ev in insight_events or []:
        if insight_score(ev) < DOSSIER_DELTA_MIN_SCORE:
            continue
        date = insight_date(ev)[:10]
        label = insight_claim(ev)
        if not date or not label:
            continue
        key = _timeline_dedupe_key(date, label)
        if key in seen:
            continue
        seen.add(key)
        auto_added += 1
        timeline.append(
            {
                "date": date,
                "type": ev.get("event_type") or "insight",
                "label": label,
                "evidence_url": ev.get("evidence_url"),
                "source": "auto",
            }
        )

    industry = (dossier or {}).get("industry") or None
    if not timeline and not industry:
        return None

    timeline.sort(key=lambda e: e["date"], reverse=True)
    as_of = (dossier or {}).get("as_of")
    stale_days = days_since_iso(as_of)
    return {
        "as_of": as_of,
        "stale_days": stale_days,
        "stale": (stale_days is None or stale_days > DOSSIER_STALE_DAYS) if dossier else True,
        "has_agent_dossier": bool(dossier),
        "auto_added": auto_added,
        "timeline": timeline[:DOSSIER_TIMELINE_CAP],
        "industry": industry,
    }


_REGISTRY_IDENTITY_CACHE: dict[str, dict] | None = None


def _holding_identity(ticker: str) -> dict:
    global _REGISTRY_IDENTITY_CACHE
    if _REGISTRY_IDENTITY_CACHE is None:
        reg = _load_json(REGISTRY_PATH) or {}
        cache: dict[str, dict] = {}
        for bucket in ("holdings", "watchlist"):
            for key, meta in ((reg.get(bucket) or {}) or {}).items():
                cache[str(key).upper()] = {
                    "company": (meta or {}).get("company"),
                    "market": (meta or {}).get("market"),
                    "exchange": (meta or {}).get("exchange"),
                }
        _REGISTRY_IDENTITY_CACHE = cache
    return dict(_REGISTRY_IDENTITY_CACHE.get(str(ticker).upper()) or {})


def _insight_text(row: dict) -> str:
    return " ".join(
        str(row.get(key) or "")
        for key in ("title", "claim", "summary", "commentary", "thesis")
    ).strip()


def filter_identity_rows(ticker: str, rows: list[dict]) -> list[dict]:
    """Drop cross-exchange / wrong-issuer attachments for a book ticker."""
    ident = _holding_identity(ticker)
    out: list[dict] = []
    for row in rows or []:
        text = _insight_text(row)
        if text and not identity_match_ok(
            text,
            ticker,
            company=str(ident.get("company") or "") or None,
            market=str(ident.get("market") or "") or None,
            exchange=str(ident.get("exchange") or "") or None,
        ):
            continue
        out.append(row)
    return out


def load_insights_for_ticker(ticker: str, insights_doc: dict | None) -> list[dict]:
    if not insights_doc:
        return []
    by_ticker = insights_doc.get("by_ticker") or {}
    rows = by_ticker.get(ticker.upper()) or by_ticker.get(ticker) or []
    return filter_identity_rows(ticker, rows)


SOURCE_PRIORITY = {
    "filing": 0,
    "earnings": 1,
    "insider": 2,
    "superinvestor_letter": 3,
    "news": 4,
    "sumzero_research": 5,
    "third_party": 6,
    "macro": 7,
    "theme": 8,
}


def insight_evidence_url(evidence_ref: str | None) -> str | None:
    if not evidence_ref:
        return None
    ref = source_document_ref(evidence_ref)
    if not ref:
        return None
    return best_document_url(ref, GITHUB_REPO)


def load_letter_discussants(ticker: str, insights_doc: dict | None) -> list[dict]:
    if not insights_doc:
        return []
    by_ticker = insights_doc.get("ticker_discussants") or {}
    rows = filter_identity_rows(
        ticker, by_ticker.get(ticker.upper()) or by_ticker.get(ticker) or []
    )
    out: list[dict] = []
    for r in rows:
        row = dict(r)
        source_ref = row.get("source_document") or source_document_ref(row.get("source_file"))
        row["source_document"] = source_ref
        row["evidence_url"] = insight_evidence_url(source_ref) or row.get("evidence_url")
        row["evidence_label"] = row.get("evidence_label") or best_document_label(source_ref)
        row["evidence_document_id"] = row.get("evidence_document_id") or document_id_for_ref(source_ref)
        out.append(row)
    return out


def enrich_ticker_insights(raw: list[dict], limit: int = 12) -> list[dict]:
    out: list[dict] = []
    for r in raw:
        row = dict(r)
        row["evidence_url"] = insight_evidence_url(row.get("evidence_ref")) or row.get("evidence_url")
        if not row.get("evidence_label"):
            ref = source_document_ref(row.get("evidence_ref"))
            row["evidence_label"] = best_document_label(ref)
        row["evidence_document_id"] = row.get("evidence_document_id") or document_id_for_ref(row.get("evidence_ref"))
        out.append(row)
    out.sort(key=lambda x: x.get("as_of") or "", reverse=True)
    out.sort(key=lambda x: SOURCE_PRIORITY.get(x.get("source", ""), 9))
    out.sort(key=lambda x: int(x.get("score") or 0), reverse=True)
    return out[:limit]


def load_events_for_ticker(ticker: str, insights_doc: dict | None) -> list[dict]:
    if not insights_doc:
        return []
    by_ticker = insights_doc.get("events_by_ticker") or {}
    rows = filter_identity_rows(
        ticker, by_ticker.get(ticker.upper()) or by_ticker.get(ticker) or []
    )
    out: list[dict] = []
    for r in rows:
        row = dict(r)
        row["evidence_url"] = insight_evidence_url(row.get("evidence_ref")) or row.get("evidence_url")
        if not row.get("evidence_label"):
            ref = source_document_ref(row.get("evidence_ref"))
            row["evidence_label"] = best_document_label(ref)
        row["evidence_document_id"] = row.get("evidence_document_id") or document_id_for_ref(row.get("evidence_ref"))
        out.append(row)
    return out


def insight_date(row: dict) -> str:
    return str(row.get("observed_at") or row.get("as_of") or "")


def insight_score(row: dict) -> int:
    try:
        return int(row.get("score") or 0)
    except (TypeError, ValueError):
        return 0


def insight_claim(row: dict) -> str:
    return str(row.get("summary") or row.get("claim") or row.get("title") or "").strip()


def days_since_iso(value: str | None) -> int | None:
    if not value:
        return None
    try:
        d = datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    return (datetime.now(timezone.utc).date() - d).days


def best_insight(rows: list[dict], predicate) -> dict | None:
    matches = [r for r in rows if predicate(r)]
    if not matches:
        return None
    matches.sort(key=lambda r: (insight_score(r), insight_date(r)), reverse=True)
    return matches[0]


def latest_insight(rows: list[dict]) -> dict | None:
    dated = [r for r in rows if insight_date(r)]
    if not dated:
        return best_insight(rows, lambda _r: True)
    dated.sort(key=lambda r: (insight_date(r), insight_score(r)), reverse=True)
    return dated[0]


def compact_insight(row: dict | None) -> dict | None:
    if not row:
        return None
    source = row.get("source")
    label = row.get("source_label") or source or "Insight"
    item = {
        "id": row.get("id") or f"{source}:{row.get('event_type') or row.get('ref') or insight_date(row)}",
        "source": source,
        "source_label": row.get("source_label") or source or "Insight",
        "source_name": row.get("source_name") or row.get("fund") or row.get("publisher"),
        "event_type": row.get("event_type"),
        "impact_axis": row.get("impact_axis"),
        "date": insight_date(row) or None,
        "direction": row.get("direction") or "neutral",
        "confidence": row.get("confidence") or "med",
        "score": insight_score(row),
        "title": row.get("title") or str(label),
        "summary": insight_claim(row)[:320],
        "evidence_url": insight_evidence_url(row.get("evidence_ref")) or row.get("evidence_url"),
        "evidence_label": row.get("evidence_label") or best_document_label(row.get("evidence_ref")),
        "evidence_document_id": row.get("evidence_document_id") or document_id_for_ref(row.get("evidence_ref")),
        "match_tier": row.get("match_tier"),
        "inventory_ref": row.get("inventory_ref"),
    }
    if row.get("materiality") is not None:
        item["materiality"] = row.get("materiality")
    if row.get("tier"):
        item["tier"] = row.get("tier")
    if row.get("materiality_components"):
        item["materiality_components"] = row.get("materiality_components")
    if row.get("ics") is not None:
        item["ics"] = row.get("ics")
    return item


def row_freshness_days(row: dict) -> int | None:
    value = row.get("freshness_days")
    if isinstance(value, (int, float)):
        return int(value)
    return days_since_iso(insight_date(row))


def polish_compact_insight(item: dict | None, row: dict | None, ticker: str) -> dict | None:
    if not item or not row:
        return item
    source = row.get("source")
    if source == "superinvestor_letter":
        title, summary = format_letter_position(
            ticker=ticker,
            fund=row.get("fund") or item.get("source_name") or "Investor",
            action=row.get("action") or "discussed",
            quarter=row.get("quarter"),
            letter_date=insight_date(row),
            commentary=insight_claim(row),
        )
        item["title"] = title
        item["summary"] = summary
        item["source_label"] = "Letter"
    elif source == "insider":
        band = row.get("band") or insight_claim(row)
        item["title"] = f"Insider · {item.get('direction', 'neutral')}"
        if not item.get("summary") or item["summary"].startswith("Insider conviction"):
            item["summary"] = str(band)[:320]
    return item


def dedupe_insight_columns(latest: dict | None, bull: dict | None, bear: dict | None) -> tuple[dict | None, dict | None, dict | None]:
    if latest and bear and latest.get("id") == bear.get("id"):
        bear = None
    if latest and bull and latest.get("id") == bull.get("id"):
        bull = None
    if bear and bull and bear.get("id") == bull.get("id"):
        bull = None
    return latest, bull, bear


def dedupe_owner_insights(
    latest: dict | None,
    bull: dict | None,
    bear: dict | None,
    owner: dict | None,
) -> tuple[dict | None, dict | None, dict | None, dict | None]:
    """Remove duplicate cards across latest/bull/bear/owner columns."""
    latest, bull, bear = dedupe_insight_columns(latest, bull, bear)
    if not owner:
        return latest, bull, bear, owner
    owner_id = owner.get("id")
    owner_claim = re.sub(r"\s+", " ", str(owner.get("summary") or owner.get("claim") or "").lower()).strip()

    def _overlaps(card: dict | None) -> bool:
        if not card:
            return False
        if owner_id and card.get("id") == owner_id:
            return True
        other = re.sub(r"\s+", " ", str(card.get("summary") or card.get("claim") or "").lower()).strip()
        if owner_claim and other and (owner_claim in other or other in owner_claim):
            return len(owner_claim) >= 40 and len(other) >= 40
        return False

    if _overlaps(latest):
        latest = None
    if _overlaps(bull):
        bull = None
    if _overlaps(bear):
        bear = None
    return latest, bull, bear, owner


def letter_claim_quality(row: dict) -> int:
    commentary = str(row.get("commentary") or row.get("claim") or "")
    if is_letter_table_debris(commentary):
        return 0
    claim = insight_claim(row)
    if "letter references" in claim.lower() and "table" in claim.lower():
        return 0
    if len(claim) >= 80:
        return 2
    return 1


def best_owner_insight(rows: list[dict]) -> dict | None:
    candidates = [r for r in rows if r.get("source") in OWNERSHIP_SOURCES]
    if not candidates:
        return None
    action_rank = {"new": 5, "add": 4, "trim": 4, "short": 3, "hold": 2, "discussed": 1}

    def sort_key(row: dict) -> tuple:
        action = row.get("action") or "discussed"
        return (
            letter_claim_quality(row),
            action_rank.get(str(action), 1),
            insight_score(row),
            insight_date(row),
        )

    candidates.sort(key=sort_key, reverse=True)
    return candidates[0]


def insight_materiality(row: dict | None) -> int | None:
    """Best available materiality for Fresh risk / catalyst gating."""
    if not row:
        return None
    if row.get("materiality") is not None:
        try:
            return int(row["materiality"])
        except (TypeError, ValueError):
            pass
    # Compact cards may only carry score; prefer explicit materiality on raw rows.
    try:
        score, _ = event_materiality_score(row)
        return int(score)
    except Exception:
        raw = row.get("score")
        try:
            return int(raw) if raw is not None else None
        except (TypeError, ValueError):
            return None


def material_enough_for_fresh_status(row: dict | None) -> bool:
    """Fresh risk/catalyst only when materiality clears the activist-style signal bar."""
    if not row:
        return False
    mat = insight_materiality(row)
    if mat is None:
        # Ownership Form 4 without score: do not escalate to Fresh risk.
        if row.get("source") == "insider":
            return False
        return False
    threshold = INSIDER_SIGNAL_THRESHOLD
    return mat >= threshold


def build_essential_insights(
    ticker: str,
    events: list[dict],
    raw_insights: list[dict],
    discussants: list[dict],
) -> dict:
    all_rows = events if events else raw_insights
    source_rows = [*events, *raw_insights]
    specific_rows, portfolio_rows = split_insight_rows(all_rows)
    selection_rows = specific_rows if specific_rows else portfolio_rows

    latest_row = latest_insight(selection_rows)
    bull_row = best_insight(selection_rows, lambda r: r.get("direction") == "bullish")
    bear_row = best_insight(
        selection_rows,
        lambda r: r.get("direction") == "bearish" or r.get("impact_axis") == "risk",
    )
    owner_row = best_owner_insight(all_rows)
    if not owner_row:
        owner_row = best_owner_insight(specific_rows)

    latest = polish_compact_insight(compact_insight(latest_row), latest_row, ticker)
    bull = polish_compact_insight(compact_insight(bull_row), bull_row, ticker)
    bear = polish_compact_insight(compact_insight(bear_row), bear_row, ticker)
    latest, bull, bear = dedupe_insight_columns(latest, bull, bear)

    owner = polish_compact_insight(compact_insight(owner_row), owner_row, ticker)
    if not owner and discussants:
        action_rank = {"new": 5, "add": 4, "trim": 4, "short": 3, "hold": 2, "discussed": 1}

        def discussant_key(d: dict) -> tuple:
            fake_row = {
                "commentary": d.get("commentary") or "",
                "claim": d.get("commentary") or "",
                "action": d.get("action") or "discussed",
            }
            return (
                letter_claim_quality(fake_row),
                action_rank.get(str(d.get("action") or "discussed"), 1),
                d.get("letter_date") or "",
            )

        d0 = max(discussants, key=discussant_key)
        title, summary = format_letter_position(
            ticker=ticker,
            fund=d0.get("fund") or "Investor",
            action=d0.get("action") or "discussed",
            quarter=d0.get("quarter"),
            letter_date=d0.get("letter_date"),
            commentary=d0.get("commentary") or "",
        )
        owner = {
            "id": f"letter:{ticker}:{d0.get('fund')}",
            "source": "superinvestor_letter",
            "source_label": "Letter",
            "source_name": d0.get("fund"),
            "event_type": "letter_position",
            "impact_axis": "ownership",
            "date": d0.get("letter_date"),
            "direction": {"add": "bullish", "trim": "bearish", "new": "bullish", "short": "bearish"}.get(
                d0.get("action"), "neutral"
            ),
            "confidence": "med",
            "score": 0,
            "title": title,
            "summary": summary,
            "evidence_url": insight_evidence_url(d0.get("source_document") or d0.get("source_file")) or d0.get("evidence_url"),
            "evidence_label": d0.get("evidence_label") or best_document_label(d0.get("source_document") or d0.get("source_file")),
            "evidence_document_id": d0.get("evidence_document_id") or document_id_for_ref(d0.get("source_document") or d0.get("source_file")),
        }

    latest, bull, bear, owner = dedupe_owner_insights(latest, bull, bear, owner)

    bullets: list[dict] = []
    seen: set[str] = set()
    for item in (latest, bear, bull, owner):
        if not item or item["id"] in seen:
            continue
        seen.add(item["id"])
        bullets.append(item)
        if len(bullets) >= 3:
            break

    source_mix = sorted({r.get("source") for r in source_rows if r.get("source")})
    freshness_candidates: list[int] = []
    for r in specific_rows:
        days = row_freshness_days(r)
        if days is not None:
            freshness_candidates.append(days)
    for d in discussants:
        days = days_since_iso(d.get("letter_date"))
        if days is not None:
            freshness_candidates.append(days)
    freshness_days = min(freshness_candidates) if freshness_candidates else None

    fresh = freshness_days is not None and freshness_days <= 30
    macro_only = bool(portfolio_rows and not specific_rows and not discussants)
    if macro_only:
        latest = None
    ticker_specific = bool(specific_rows or discussants)
    bear_specific = bool(
        bear
        and not is_portfolio_wide({"source": bear.get("source")})
        and bear.get("impact_axis") in {"risk", "fundamentals", "ownership", "variant_view", None}
    )
    bull_specific = bool(
        bull
        and not is_portfolio_wide({"source": bull.get("source")})
        and bull.get("impact_axis") in {"catalyst", "fundamentals", "ownership", "capital_allocation", "variant_view", None}
    )
    primary = latest or owner or bull or bear
    primary_is_ownership = bool(primary and primary.get("source") in OWNERSHIP_SOURCES)

    # Resolve raw rows for materiality gate (compact cards may lack full score inputs).
    bear_raw = bear_row
    bull_raw = bull_row
    fresh_risk_ok = bear_specific and fresh and material_enough_for_fresh_status(bear_raw or bear)
    fresh_catalyst_ok = bull_specific and fresh and material_enough_for_fresh_status(bull_raw or bull)

    if not all_rows and not discussants:
        status = {"label": "No insight", "tone": "stale"}
    elif fresh_risk_ok:
        status = {"label": "Fresh risk", "tone": "risk"}
    elif fresh_catalyst_ok:
        status = {"label": "Fresh catalyst", "tone": "bullish"}
    elif primary_is_ownership and owner:
        status = {"label": "Owner signal", "tone": "ownership"}
    elif macro_only:
        status = {"label": "Macro only", "tone": "stale"}
    elif not ticker_specific:
        status = {"label": "No ticker signal", "tone": "stale"}
    elif owner:
        status = {"label": "Owner signal", "tone": "ownership"}
    elif freshness_days is not None and freshness_days > 120:
        status = {"label": "Stale", "tone": "stale"}
    else:
        status = {"label": "Covered", "tone": "neutral"}

    # Best insider materiality among ticker-specific rows for Scan columns.
    insider_materiality = None
    insider_tier = None
    insider_ics = None
    for r in specific_rows:
        if r.get("source") != "insider":
            continue
        mat = r.get("materiality")
        if mat is None:
            continue
        try:
            mat_i = int(mat)
        except (TypeError, ValueError):
            continue
        if insider_materiality is None or mat_i > insider_materiality:
            insider_materiality = mat_i
            insider_tier = r.get("tier")
            insider_ics = r.get("ics")

    return {
        "status": status,
        "latest": latest,
        "bull": bull,
        "bear": bear,
        "owner": owner,
        "bullets": bullets,
        "source_mix": source_mix,
        "freshness_days": freshness_days,
        "macro_only": macro_only,
        "ticker_specific": ticker_specific,
        "event_count": len(events),
        "record_count": len(raw_insights),
        "insider_materiality": insider_materiality,
        "insider_tier": insider_tier,
        "insider_ics": insider_ics,
        "needs_work": False,  # set from essential reasons below
    }


def collect_portfolio_macro_records(insights_doc: dict | None) -> list[dict]:
    if not insights_doc:
        return []
    seen: set[str] = set()
    out: list[dict] = []
    for rows in (insights_doc.get("by_ticker") or {}).values():
        for row in rows:
            if row.get("source") != "macro":
                continue
            # Dedupe by series/theme id when present, else claim.
            key = str(row.get("theme_id") or row.get("series_id") or row.get("claim") or row.get("id") or "")
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(row)
    out.sort(key=lambda r: (insight_date(r), insight_score(r)), reverse=True)
    return out


def build_portfolio_macro(insights_doc: dict | None) -> list[dict]:
    """Legacy compat list — prefer portfolio_macro_regime in the UI."""
    regime = build_portfolio_macro_regime()
    compat = regime_to_compat_macro_list(regime)
    if compat:
        return compat
    out: list[dict] = []
    for row in collect_portfolio_macro_records(insights_doc)[:8]:
        item = compact_insight(row)
        if not item:
            continue
        item["title"] = str(row.get("theme_id") or row.get("event_type") or "Macro")
        out.append(item)
    return out


def essential_needs_work_reasons(row: dict) -> list[str]:
    """Holdings-critical Attention gaps only (plan 1A)."""
    if not row.get("in_holdings"):
        return []
    essential = row.get("essential_insights") or {}
    reasons: list[str] = []
    if not essential.get("ticker_specific"):
        reasons.append("no ticker coverage")
    bullets = essential.get("bullets") or []
    primary = bullets[0] if bullets else None
    if primary and not primary.get("evidence_url"):
        reasons.append("missing evidence")
    valuation_days = days_since_iso((row.get("classification") or {}).get("analysis_as_of"))
    if valuation_days is None or valuation_days > 180:
        reasons.append("stale valuation")
    return reasons[:5]


def coverage_gap_reasons(row: dict) -> list[str]:
    """Completeness audit gaps — demoted from Needs Attention."""
    if not row.get("in_holdings"):
        return []
    essential = row.get("essential_insights") or {}
    reasons: list[str] = []
    freshness = essential.get("freshness_days")
    if isinstance(freshness, int) and freshness > 90:
        reasons.append("stale source")
    outside_research_sources = {"third_party", "sumzero_research"}
    if not (outside_research_sources & set(essential.get("source_mix") or [])):
        reasons.append("no third-party check")
    dossier = row.get("dossier")
    if not dossier or not dossier.get("has_agent_dossier"):
        reasons.append("no dossier")
    elif dossier.get("stale"):
        reasons.append("stale dossier")
    return reasons[:5]


def build_active_lenses(lenses_doc: dict | None) -> tuple[list[dict], int]:
    if not lenses_doc:
        return [], 0
    personas = lenses_doc.get("lenses") or []
    active: list[dict] = []
    silent = 0
    for p in personas:
        rel = float(p.get("relevance") or 0)
        verdict = p.get("verdict") or "silent"
        if rel <= 0 or verdict == "silent":
            silent += 1
            continue
        label = (p.get("label") or p.get("persona") or "").split("/")[0].strip()
        active.append(
            {
                "persona": p.get("persona"),
                "label": label or p.get("persona"),
                "verdict": verdict,
                "return_pct": p.get("return_pct"),
                "relevance": rel,
                "horizon_yrs": p.get("horizon_yrs"),
                "key_metrics": p.get("key_metrics") or [],
                "falsifier": p.get("falsifier"),
            }
        )
    active.sort(key=lambda x: (-x["relevance"], -(x.get("return_pct") or -999)))
    return active[:3], silent


def build_decision_summary(
    classification: dict,
    lenses_doc: dict | None,
    human_review: dict | None,
    valuation: dict | None,
) -> dict | None:
    lenses_doc = lenses_doc or {}
    blend = lenses_doc.get("valuation_blend") or {}
    consensus = lenses_doc.get("consensus") or {}
    actionable = bool(classification.get("decision_actionable"))
    if actionable:
        stance = classification.get("stance")
        stance_source = "human_decision"
    elif classification.get("stance_proposed"):
        stance = classification.get("stance_proposed")
        stance_source = classification.get("valuation_authority") or "investment_committee"
    else:
        stance = "pending"
        stance_source = classification.get("valuation_authority") or "valuation_contract"

    dissents = consensus.get("dissents") or []
    top_dissent = None
    if dissents:
        d0 = dissents[0]
        top_dissent = {
            "persona": d0.get("persona"),
            "label": (d0.get("label") or d0.get("persona") or "").split("/")[0],
            "verdict": d0.get("verdict"),
        }

    house = classification.get("analysis_irr_pct")
    blend_pct = blend.get("blended_return_pct")
    divergence = bool(consensus.get("lawrence_divergence"))
    if house is not None and blend_pct is not None and not divergence:
        divergence = abs(float(house) - float(blend_pct)) > 2.0

    lens_stance = consensus.get("stance")

    return {
        "stance": stance,
        "stance_source": stance_source,
        "lens_stance": lens_stance,
        "house_irr_pct": house,
        "lens_blend_pct": blend_pct,
        "lens_band_pct": blend.get("band_pct"),
        "agreement_pct": consensus.get("agreement_pct"),
        "top_dissent": top_dissent,
        "divergence": divergence,
        "as_of": lenses_doc.get("as_of") or classification.get("analysis_as_of"),
    }


def compact_research_memory(ticker: str, memory_doc: dict | None) -> dict | None:
    if not memory_doc:
        return None
    by_ticker = memory_doc.get("by_ticker") or {}
    mem = by_ticker.get(ticker.upper()) or by_ticker.get(ticker)
    if not mem:
        return None

    def _claims(key: str, limit: int) -> list[dict]:
        rows = []
        for claim in mem.get(key) or []:
            text = str(
                claim.get("claim")
                or claim.get("summary")
                or claim.get("title")
                or ""
            )
            wrapped = {"claim": text, "title": claim.get("title"), "summary": claim.get("summary")}
            if filter_identity_rows(ticker, [wrapped]):
                rows.append(claim)
            if len(rows) >= limit:
                break
        return rows

    return {
        "claim_count": mem.get("claim_count", 0),
        "evidence_count": mem.get("evidence_count", 0),
        "source_count": mem.get("source_count", 0),
        "source_mix": mem.get("source_mix") or [],
        "confirming_count": mem.get("confirming_count", 0),
        "disconfirming_count": mem.get("disconfirming_count", 0),
        "mixed_count": mem.get("mixed_count", 0),
        "neutral_count": mem.get("neutral_count", 0),
        "top_claims": _claims("top_claims", 4),
        "inflection_claims": _claims("inflection_claims", 3),
        "risk_claims": _claims("risk_claims", 3),
        "ownership_claims": _claims("ownership_claims", 3),
        "biotech": mem.get("biotech") or {},
    }


def build_ticker_row(
    ticker: str,
    holdings: dict[str, dict],
    portfolio_class: dict[str, dict],
    insights_doc: dict | None = None,
    memory_doc: dict | None = None,
    watchlist: dict | None = None,
    registry_docs: list[dict] | None = None,
) -> dict:
    ticker_dir = ROOT / ticker
    meta = {**TICKER_META.get(ticker, {}), **holdings.get(ticker, {})}
    dl_script, dl_path = has_download_script(ticker_dir)
    classification = classification_for(ticker, ticker_dir, portfolio_class)
    pdf_count = count_pdfs(ticker_dir, registry_docs)
    deep_dive = latest_deep_dive(ticker_dir, classification)
    display_ticker = meta.get("display_ticker") or ticker
    quote_ticker = meta.get("quote_ticker") or ticker
    units = resolve_units(ticker, meta.get("market"), meta.get("exchange"))
    if units["source"] == "unresolved":
        UNRESOLVED_UNITS[ticker] = units["reason"]
    row = {
        "ticker": ticker,
        "display_ticker": display_ticker,
        "quote_ticker": quote_ticker,
        "company": meta.get("company", ticker),
        "market": meta.get("market", "—"),
        "exchange": meta.get("exchange", "—"),
        # Quote units for every per-share figure in this payload. Resolved once here
        # so no renderer has to infer a currency from the ticker or assume USD.
        "units": units,
        "folder": f"{ticker}/",
        "readme": (ticker_dir / "README.md").exists(),
        "download_script": dl_script,
        "download_script_path": dl_path,
        "pdf_count": pdf_count,
        "sec_filings": count_sec_filings(ticker_dir),
        "research_dir": (ticker_dir / "research").exists(),
        "index_file": has_index(ticker_dir),
        "last_download": last_download(ticker_dir),
        "last_research": last_research(ticker_dir),
        "classification": classification,
        "thesis_status": classification["archetype"],
        "one_line_thesis": display_one_line_thesis(ticker_dir, deep_dive),
        "links": _research_links(ticker, ticker_dir),
        "deep_dive": deep_dive,
        "ssi_report": latest_ssi_report(ticker_dir),
        "human_review": valuation_human_review(ticker_dir),
        "pricing_analysis": pricing_analysis_summary(ticker_dir),
        "investment_committee": investment_committee_summary(ticker_dir),
        "valuation_workbench": valuation_workbench_summary(ticker_dir),
        "component_valuation": valuation_component_summary(ticker_dir),
        "properties": property_register_summary(ticker_dir),
        "total_return_panel": valuation_total_return_panel(ticker, ticker_dir),
        # filled below after workbench/component are known
        "valuation_decision": None,
        "recent_files": recent_files(ticker_dir),
        "developments": recent_developments(ticker_dir, ticker),
        "onboard": reconcile_onboard_status(ticker_dir, pdf_count),
        "transcripts": transcript_summary(ticker, ticker_dir),
        "in_holdings": ticker in holdings,
        "in_watchlist": bool((watchlist or {}).get(ticker)),
    }
    row["valuation_decision"] = valuation_decision_summary(
        ticker,
        ticker_dir,
        workbench=row.get("valuation_workbench"),
        component=row.get("component_valuation"),
    )
    row["completeness"] = completeness_score(row)
    lenses = load_lenses(ticker_dir)
    val = load_valuation(ticker_dir)
    if lenses:
        row["lenses"] = {
            "as_of": lenses.get("as_of"),
            "valuation_blend": lenses.get("valuation_blend"),
            "consensus": lenses.get("consensus"),
            "personas": lenses.get("lenses"),
        }
        active, silent_count = build_active_lenses(lenses)
        row["active_lenses"] = active
        row["silent_lens_count"] = silent_count
    row["decision_summary"] = build_decision_summary(
        classification, lenses, row.get("human_review"), val
    )
    full_insights = enrich_ticker_insights(load_insights_for_ticker(ticker, insights_doc), limit=200)
    display_insights = full_insights[:12]
    if not any(r.get("source") == "sumzero_research" for r in display_insights):
        sumzero_row = next((r for r in full_insights if r.get("source") == "sumzero_research"), None)
        if sumzero_row:
            display_insights = [*display_insights[:11], sumzero_row]
    row["insights"] = display_insights
    row["insight_events"] = load_events_for_ticker(ticker, insights_doc)
    row["letter_discussants"] = load_letter_discussants(ticker, insights_doc)
    row["essential_insights"] = build_essential_insights(
        ticker,
        row["insight_events"],
        full_insights,
        row["letter_discussants"],
    )
    row["dossier"] = build_dossier_view(load_dossier(ticker_dir), row["insight_events"])
    reasons = essential_needs_work_reasons(row)
    coverage = coverage_gap_reasons(row)
    row["essential_insights"]["needs_work_reasons"] = reasons
    row["essential_insights"]["coverage_gaps"] = coverage
    row["essential_insights"]["needs_work"] = bool(reasons)
    row["research_memory"] = compact_research_memory(ticker, memory_doc)
    row["activist"] = activist_summary_for_ticker(ticker)
    row["kpi_trends"] = kpi_trends_for_ticker(ticker)
    row["power_zones"] = power_zones_for_ticker(ticker)
    row["index_membership"] = index_membership_for_ticker(ticker)
    row["fund_nav"] = fund_nav_summary(ticker_dir, meta)
    if row["fund_nav"] and classification.get("instrument_type") in ("—", "-", None, ""):
        classification["instrument_type"] = row["fund_nav"].get("instrument_type") or "—"
    if row["fund_nav"] and classification.get("fund_edge") in ("—", "-", None, ""):
        classification["fund_edge"] = row["fund_nav"].get("edge") or "—"
    row["cvr"] = cvr_summary(ticker, ticker_dir)
    if row["cvr"] and classification.get("investment_sleeve") in ("—", "-", "pending", None, ""):
        classification["investment_sleeve"] = "cvr_contingent"
        classification["investment_sleeve_label"] = _INVESTMENT_SLEEVE_LABELS.get(
            "cvr_contingent", "CVRs"
        )
    return row


_INDEX_MEMBERSHIP_CACHE: dict | None = None


def load_index_membership() -> dict | None:
    global _INDEX_MEMBERSHIP_CACHE
    if _INDEX_MEMBERSHIP_CACHE is None:
        _INDEX_MEMBERSHIP_CACHE = _load_json(DATA_DIR / "index_membership.json") or {}
    return _INDEX_MEMBERSHIP_CACHE or None


def index_membership_for_ticker(ticker: str) -> dict | None:
    doc = load_index_membership()
    entry = ((doc or {}).get("by_ticker") or {}).get(ticker)
    if not entry:
        return None
    return {
        "badge_status": entry.get("badge_status"),
        "current_memberships": entry.get("current_memberships") or [],
        "priority_score": (entry.get("impact_proxy") or {}).get("priority_score"),
        "demand_shock_pct_of_adv": (entry.get("impact_proxy") or {}).get("demand_shock_pct_of_adv"),
        "inclusion_probability_band": (entry.get("prediction") or {}).get("inclusion_probability_band"),
        "next_calendar_event": (entry.get("prediction") or {}).get("next_calendar_event"),
        "confirmed_events": (entry.get("confirmed_events") or [])[:5],
        "scorecards": (entry.get("scorecards") or [])[:12],
        "inputs_missing": entry.get("inputs_missing") or [],
    }


_KPI_TRENDS_CACHE: dict | None = None


def load_kpi_trends() -> dict | None:
    global _KPI_TRENDS_CACHE
    if _KPI_TRENDS_CACHE is None:
        _KPI_TRENDS_CACHE = _load_json(DATA_DIR / "kpi_trends.json") or {}
    return _KPI_TRENDS_CACHE or None


def kpi_trends_for_ticker(ticker: str) -> dict | None:
    doc = load_kpi_trends()
    entry = ((doc or {}).get("by_ticker") or {}).get(ticker)
    if not entry:
        return None
    return {
        "summary": entry.get("summary"),
        "metrics": (entry.get("metrics") or [])[:8],
        "business_momentum": entry.get("business_momentum"),
        "leadership_risk": entry.get("leadership_risk"),
        "data_tier": entry.get("data_tier"),
        "has_trend_data": entry.get("data_tier") in ("sec_fundamentals", "equity_model"),
    }


_POWER_ZONES_CACHE: dict | None = None


def load_power_zones() -> dict | None:
    global _POWER_ZONES_CACHE
    if _POWER_ZONES_CACHE is None:
        _POWER_ZONES_CACHE = _load_json(DATA_DIR / "power_zones.json") or {}
    return _POWER_ZONES_CACHE or None


def power_zones_for_ticker(ticker: str) -> dict | None:
    doc = load_power_zones()
    return ((doc or {}).get("by_ticker") or {}).get(ticker)


def load_activist_feed() -> dict | None:
    path = DATA_DIR / "activist_feed.json"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    if "<<<<<<<" in text or ">>>>>>>" in text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def load_insights_document() -> dict | None:
    """Load the current sharded Insights contract, with legacy monolith fallback."""
    legacy = _load_json(DATA_DIR / "insights.json")
    if legacy:
        return legacy
    shard_dir = DATA_DIR / "insights"
    if not shard_dir.is_dir():
        return None
    merged: dict = {}
    for path in sorted(shard_dir.glob("*.json")):
        shard = _load_json(path)
        if isinstance(shard, dict):
            merged.update(shard)
    return merged or None


def activist_summary_for_ticker(ticker: str) -> dict:
    feed = load_activist_feed()
    by_ticker = (feed or {}).get("by_ticker") or {}
    summary = by_ticker.get(ticker) or by_ticker.get(ticker.upper()) or {}
    if summary:
        return summary
    return {
        "long_count": 0,
        "short_count": 0,
        "latest": None,
        "has_unreconciled": False,
    }


def build() -> dict:
    reg = load_registry()
    holdings = parse_holdings()
    portfolio_class = load_classification()
    tickers = list_tickers()
    insights_doc = load_insights_document()
    memory_doc = _load_json(RESEARCH_MEMORY_PATH)
    registry_doc = _load_json(DOCUMENT_REGISTRY_PATH) or {}
    registry_docs = list(registry_doc.get("documents") or [])
    rows = [
        build_ticker_row(
            t,
            holdings,
            portfolio_class,
            insights_doc,
            memory_doc,
            reg.get("watchlist") or {},
            registry_docs,
        )
        for t in tickers
    ]
    prior_by_ticker = load_prior_dashboard_rows()
    preserve_sparse_infra = (
        workspace_is_sparse(tickers)
        or os.environ.get("DASHBOARD_PRESERVE_DOCUMENT_REGISTRY") == "1"
    )
    if preserve_sparse_infra and prior_by_ticker:
        restored = preserve_infra_from_prior(rows, prior_by_ticker)
        if restored:
            print(
                f"WARN: sparse checkout ({ticker_dirs_present(tickers)}/{len(tickers)} "
                f"ticker dirs); preserved infra stats for {restored} tickers from prior "
                f"{OUTPUT.relative_to(ROOT)}"
            )
    watchlist = build_watchlist_rows(reg.get("watchlist") or {})
    portfolio_macro_regime = build_portfolio_macro_regime()
    portfolio_macro = build_portfolio_macro(insights_doc)

    total_pdfs = sum(r["pdf_count"] for r in rows)
    with_research = sum(1 for r in rows if r["research_dir"])
    with_readme = sum(1 for r in rows if r["readme"])
    avg_complete = round(sum(r["completeness"] for r in rows) / len(rows)) if rows else 0

    sleeve_filters = [{"id": "ALL", "label": "All sleeves"}]
    real_assets_union: set[str] = set()
    fund_nav_union: set[str] = set()
    cvr_union: set[str] = set()
    for sleeve_id in _INVESTMENT_SLEEVE_LABELS:
        if sleeve_id.startswith("real_assets"):
            real_assets_union.update(
                t
                for t, sid in _INVESTMENT_SLEEVE_INDEX.items()
                if sid == sleeve_id
            )
        if sleeve_id == "fund_nav_discounts":
            fund_nav_union.update(
                t
                for t, sid in _INVESTMENT_SLEEVE_INDEX.items()
                if sid == sleeve_id
            )
        if sleeve_id == "cvr_contingent":
            cvr_union.update(
                t
                for t, sid in _INVESTMENT_SLEEVE_INDEX.items()
                if sid == sleeve_id
            )
    # Also count rows that carry a cvr payload even if sleeve sync lagged.
    cvr_union.update(
        str(r.get("ticker") or "").upper()
        for r in rows
        if r.get("cvr")
    )
    if cvr_union:
        sleeve_filters.append(
            {
                "id": "cvr_all",
                "label": "CVRs",
                "count": sum(
                    1
                    for r in rows
                    if (r.get("classification") or {}).get("investment_sleeve")
                    == "cvr_contingent"
                    or r.get("cvr")
                    or str(r.get("ticker") or "").upper() in cvr_union
                ),
            }
        )
    if real_assets_union:
        sleeve_filters.append(
            {
                "id": "real_assets_all",
                "label": "All hard assets",
                "count": sum(
                    1
                    for r in rows
                    if r["ticker"] in real_assets_union
                ),
            }
        )
    if fund_nav_union:
        sleeve_filters.append(
            {
                "id": "fund_nav_all",
                "label": "NAV discounts",
                "count": sum(1 for r in rows if r["ticker"] in fund_nav_union),
            }
        )
    for sleeve_id, label in sorted(_INVESTMENT_SLEEVE_LABELS.items(), key=lambda x: x[1]):
        # Meta filters already cover these single sleeves near the top.
        if sleeve_id == "fund_nav_discounts" and fund_nav_union:
            continue
        if sleeve_id == "cvr_contingent" and cvr_union:
            continue
        count = sum(
            1
            for r in rows
            if (r.get("classification") or {}).get("investment_sleeve") == sleeve_id
        )
        sleeve_filters.append({"id": sleeve_id, "label": label, "count": count})

    valuation_queue = valuation_queue_summary(rows)
    with_property_register = sum(1 for r in rows if r.get("properties"))
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "workspace": str(ROOT),
        "summary": {
            "ticker_count": len(rows),
            "watchlist_count": len(watchlist),
            "total_pdfs": total_pdfs,
            "with_readme": with_readme,
            "with_research": with_research,
            "with_property_register": with_property_register,
            "avg_completeness": avg_complete,
            "markets": sort_markets({r["market"] for r in rows}),
            "market_filters": sort_market_filters({r["market"] for r in rows}),
            "sleeve_filters": sleeve_filters,
            "github_repo": GITHUB_REPO,
            "universe_intake_workflow": UNIVERSE_INTAKE_WORKFLOW,
            "universe_intake_dispatch_event": "sync-ls-algo-universe",
            "valuation_queue_tickers": (valuation_queue.get("counts") or {}).get("tickers"),
            "valuation_evidence_blocked": (valuation_queue.get("counts") or {}).get("evidence_blocked"),
            "valuation_critical_gaps": (valuation_queue.get("counts") or {}).get("critical_gaps"),
        },
        "watchlist": watchlist,
        "tickers": rows,
        "valuation_queue": valuation_queue,
        "portfolio_macro_regime": portfolio_macro_regime,
        "portfolio_macro": portfolio_macro,
    }


OAUTH_CONFIG = DATA_DIR / "oauth_config.json"


def write_oauth_config() -> None:
    """Merge OAuth client_id from env (CI) with committed config."""
    existing: dict = {}
    if OAUTH_CONFIG.exists():
        try:
            existing = json.loads(OAUTH_CONFIG.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
    client_id = os.environ.get("OAUTH_CLIENT_ID", "").strip() or existing.get("client_id", "")
    exchange_url = os.environ.get("OAUTH_PROXY_URL", "").strip() or existing.get("exchange_url", "")
    allowed_logins = existing.get("allowed_logins") or [
        "GoldmanDrew",
        "dgoldman",
        "mcricenti",
        "dylansapienza",
        "Dsap5131",
    ]
    # Normalize once so allowlist checks stay case-insensitive.
    allowed_logins = sorted({str(x).strip() for x in allowed_logins if str(x).strip()})
    payload = {
        "client_id": client_id,
        "exchange_url": exchange_url,
        "scopes": existing.get("scopes", "repo"),
        "allowed_logins": allowed_logins,
        "setup": existing.get(
            "setup",
            "Create a GitHub OAuth App; callback URL must match .../oauth/callback.html on Pages.",
        ),
    }
    OAUTH_CONFIG.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def load_darwin_portfolio() -> dict | None:
    return _load_json(DATA_DIR / "darwin_portfolio.json") or _load_json(
        DATA_DIR / "darwin_portfolio_roth.json"
    )


def load_darwin_serving() -> dict | None:
    return _load_json(DATA_DIR / "darwin_serving.json")


def load_darwin_bundle() -> dict:
    """Prefer L4 serving; fallback to per-account portfolio files."""
    serving = load_darwin_serving()
    if serving and serving.get("accounts"):
        bundle = {
            "serving": serving,
            "default_account": serving.get("default_account", "roth"),
        }
        for aid, row in serving["accounts"].items():
            if row.get("portfolio"):
                bundle[aid] = row["portfolio"]
            if row.get("paper"):
                bundle[f"paper_{aid}"] = {
                    "last_mark": row["paper"],
                    "inception_date": row.get("paper_inception"),
                }
        return bundle
    bundle: dict = {"default_account": "roth", "account_scope": "ira_only"}
    for aid in ("roth",):
        p = _load_json(DATA_DIR / f"darwin_portfolio_{aid}.json")
        if p:
            bundle[aid] = p
    roth = bundle.get("roth") or load_darwin_portfolio()
    if roth:
        bundle["roth"] = roth
    return bundle


def build_darwin_if_missing() -> dict | None:
    """Run Darwin pipeline when portfolio JSON absent (e.g. fresh clone)."""
    if (DATA_DIR / "darwin_serving.json").exists() or (DATA_DIR / "darwin_portfolio_roth.json").exists():
        return load_darwin_bundle()
    script = ROOT / "_system" / "scripts" / "build_darwin_portfolio.py"
    if not script.exists():
        return None
    import subprocess

    subprocess.run(
        [sys.executable, str(script), "--fast"],
        cwd=str(ROOT),
        check=False,
        timeout=600,
    )
    return load_darwin_bundle()


def build_nol_screener() -> dict | None:
    """Always rebuild NOL screener so SEC filings and prices stay fresh."""
    path = DATA_DIR / "nol_screener.json"
    script = ROOT / "_system" / "scripts" / "build_nol_screener.py"
    if not script.exists():
        return _load_json(path)
    import subprocess

    subprocess.run(
        [sys.executable, str(script), "--write"],
        cwd=str(ROOT),
        check=False,
        timeout=900,
    )
    return _load_json(path)


def build_advantaged_banks_screener() -> dict | None:
    """Rebuild advantaged-banks screener (seed + SEC deposit/ROE enrich)."""
    path = DATA_DIR / "advantaged_banks_screener.json"
    script = ROOT / "_system" / "scripts" / "build_advantaged_banks_screener.py"
    if not script.exists():
        return _load_json(path)
    import subprocess

    subprocess.run(
        [sys.executable, str(script), "--write"],
        cwd=str(ROOT),
        check=False,
        timeout=300,
    )
    return _load_json(path)


def build_equity_models() -> dict:
    """Run equity model ingest and return payload for dashboard merge."""
    script = ROOT / "_system" / "scripts" / "build_equity_model_dashboard.py"
    if script.exists():
        import subprocess

        subprocess.run([sys.executable, str(script)], cwd=str(ROOT), check=False)
    path = DATA_DIR / "equity_models.json"
    if not path.exists():
        return {"built_at": None, "ticker_count": 0, "tickers": {}, "summaries": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"built_at": None, "ticker_count": 0, "tickers": {}, "summaries": {}}


def merge_equity_model_rows(rows: list[dict], equity_payload: dict) -> None:
    summaries = equity_payload.get("summaries") or {}
    tickers = equity_payload.get("tickers") or {}
    for row in rows:
        ticker = row["ticker"]
        if ticker in summaries:
            row["equity_model"] = summaries[ticker]
        elif ticker in tickers:
            row["equity_model"] = {"ready": True, "as_of": tickers[ticker].get("as_of")}
        else:
            row["equity_model"] = {"ready": False}


def build_document_registry() -> dict | None:
    import subprocess

    if os.environ.get("DASHBOARD_PRESERVE_DOCUMENT_REGISTRY") == "1":
        return _load_json(DOCUMENT_REGISTRY_PATH)
    script = ROOT / "_system" / "scripts" / "build_document_registry.py"
    if script.exists():
        subprocess.run([sys.executable, str(script)], cwd=str(ROOT), check=False)
    return _load_json(DOCUMENT_REGISTRY_PATH)


def build_research_memory() -> dict | None:
    return _load_json(RESEARCH_MEMORY_PATH)


def build_short_alpha() -> dict | None:
    """Compile the separately loaded Short Alpha hypothesis ledger."""
    script = ROOT / "_system" / "scripts" / "build_short_alpha_dashboard.py"
    path = DATA_DIR / "short_alpha.json"
    if script.exists():
        import subprocess

        subprocess.run([sys.executable, str(script)], cwd=str(ROOT), check=True, timeout=60)
    return _load_json(path)


def build_learning_loop_summary() -> dict | None:
    return _load_json(ROOT / "_system" / "reviews" / "pending" /
                      "memory_triage_summary.json")


def load_prior_rows() -> dict[str, dict]:
    """Prior per-ticker rows for the anti-clobber guards and infra restore.

    dashboard_data.json is the historical source, but it is a 76MB monolith
    that duplicates artifacts already committed (core.json + the per-ticker
    shards) and is rewritten on every build, which is most of why .git is 19GB.
    It cannot simply be dropped: `prior_by_ticker` is what
    `refuse_infra_collapse` and `restore_infra_fields` compare against, and
    both return early when the prior has fewer than 50 rows -- so untracking
    the monolith without this fallback would silently DISABLE the guards in a
    fresh CI checkout, which is the opposite of the intent.

    Fall back to the committed shards, which carry the same rows: core.json for
    the summary fields, per-ticker shards for everything else.
    """
    payload = _load_json(OUTPUT) or {}
    rows = payload.get("tickers") or []
    if rows:
        return {str(r.get("ticker")): r for r in rows if r.get("ticker")}

    merged: dict[str, dict] = {}
    core = _load_json(DATA_DIR / "core.json") or {}
    for row in core.get("tickers") or []:
        if row.get("ticker"):
            merged[str(row["ticker"])] = dict(row)
    shard_dir = DATA_DIR / "tickers"
    if shard_dir.is_dir():
        for path in shard_dir.glob("*.json"):
            shard = _load_json(path) or {}
            ticker = str(shard.get("ticker") or "")
            if not ticker:
                continue
            # Shard wins on keys it carries (recent_files lives only there);
            # core fills the rest.
            merged.setdefault(ticker, {}).update(
                {k: v for k, v in shard.items() if v not in (None, "", [], {})}
            )
    if merged:
        print(
            f"prior rows reconstructed from committed shards ({len(merged)} tickers); "
            f"{OUTPUT.name} absent",
            file=sys.stderr,
        )
    return merged
def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    short_alpha = build_short_alpha()
    equity_payload = build_equity_models()
    prior_by_ticker = load_prior_rows()
    document_registry = build_document_registry()
    document_catalog = build_document_catalog(document_registry)
    insights_doc = load_insights_document()
    memory_doc = build_research_memory()
    learning_loop = build_learning_loop_summary()
    if memory_doc and learning_loop:
        memory_doc["learning_loop"] = learning_loop
        RESEARCH_MEMORY_PATH.write_text(
            json.dumps(memory_doc, separators=(",", ":")), encoding="utf-8")
    payload = build()
    if short_alpha:
        payload["short_alpha_ref"] = {
            "path": "dashboard/data/short_alpha.json",
            "generated_at": short_alpha.get("generated_at"),
            "summary": short_alpha.get("summary") or {},
        }
        payload["summary"]["short_alpha_count"] = (short_alpha.get("summary") or {}).get(
            "position_count", 0
        )
    refuse_infra_collapse(payload, prior_by_ticker)
    refuse_valuation_collapse(payload, prior_by_ticker)
    attach_pdf_store_rows(payload["tickers"], document_catalog)
    merge_equity_model_rows(payload["tickers"], equity_payload)
    model_ready = sum(1 for r in payload["tickers"] if (r.get("equity_model") or {}).get("ready"))
    payload["summary"]["equity_models_ready"] = model_ready
    payload["equity_models"] = equity_payload
    if insights_doc:
        payload["insights_ref"] = {
            "path": "dashboard/data/insights/manifest.json",
            "generated_at": insights_doc.get("generated_at"),
            "record_count": insights_doc.get("record_count"),
        }
    if memory_doc:
        payload["research_memory_ref"] = {
            "path": "dashboard/data/research_memory.json",
            "evidence_path": "dashboard/data/research_memory_evidence.json",
            "generated_at": memory_doc.get("generated_at"),
            "summary": memory_doc.get("summary"),
        }
    if learning_loop:
        payload["learning_loop"] = learning_loop
        payload["summary"]["learning_loop_pending_proposals"] = (
            (learning_loop.get("proposal_loop") or {}).get("undecided", 0))
        payload["summary"]["learning_loop_resolved_outcomes"] = (
            (learning_loop.get("forecast_loop") or {}).get("resolved", 0))
    if document_catalog:
        payload["document_catalog"] = {
            "generated_at": document_catalog.get("generated_at"),
            "registry_generated_at": document_catalog.get("registry_generated_at"),
            "folder_index_generated_at": document_catalog.get("folder_index_generated_at"),
            "time_periods": document_catalog.get("time_periods"),
            "summary": document_catalog.get("summary"),
            "known_tickers": document_catalog.get("known_tickers"),
            "documents": document_catalog.get("documents"),
        }
    persona_cal = _load_json(DATA_DIR / "persona_calibration.json")
    if persona_cal:
        payload["persona_calibration"] = persona_cal
    kpi_trends = load_kpi_trends()
    if kpi_trends:
        payload["kpi_trends"] = kpi_trends
        payload["summary"]["kpi_inflections"] = kpi_trends.get("inflection_count", 0)
    power_zones = load_power_zones()
    if power_zones:
        payload["power_zones"] = power_zones
    bundle = load_darwin_bundle() or build_darwin_if_missing() or {}
    serving = bundle.get("serving") or load_darwin_serving()
    if serving:
        payload["darwin_serving"] = serving
    if bundle.get("roth"):
        payload["darwin"] = bundle["roth"]
    if bundle:
        payload["darwin_accounts"] = bundle
    nol = build_nol_screener()
    if nol:
        payload["nol_screener"] = nol
        payload["summary"]["nol_screener_count"] = nol.get("row_count") or len(
            nol.get("rows") or []
        )
    banks = build_advantaged_banks_screener()
    if banks:
        payload["advantaged_banks_screener"] = banks
        payload["summary"]["advantaged_banks_count"] = banks.get("row_count") or len(
            banks.get("rows") or []
        )
    index_membership = load_index_membership()
    if index_membership:
        payload["index_membership_ref"] = {
            "path": "dashboard/data/index_membership.json",
            "generated": index_membership.get("generated"),
            "rules_as_of": index_membership.get("rules_as_of"),
        }
        payload["index_membership_summary"] = index_membership.get("portfolio_summary") or {}
        payload["index_membership_calendar"] = index_membership.get("calendar") or []
        payload["index_membership_caption"] = index_membership.get("caption")
        summary = index_membership.get("portfolio_summary") or {}
        payload["summary"]["index_inclusion_candidates"] = len(summary.get("inclusion_candidates") or [])
        payload["summary"]["index_deletion_risks"] = len(summary.get("deletion_risks") or [])
    activist_feed = load_activist_feed()
    if not activist_feed:
        try:
            from build_activist_feed import build_feed

            activist_feed = build_feed()
        except Exception:
            activist_feed = None
    if activist_feed:
        payload["activist_feed"] = activist_feed
        payload["summary"]["activist_hits"] = (activist_feed.get("summary") or {}).get("portfolio_hits", 0)
        payload["summary"]["activist_tickers_with_hits"] = (activist_feed.get("summary") or {}).get(
            "tickers_with_hits", 0
        )
    # Same prior, shard-reconstructed when the monolith is absent.
    payload = merge_sparse_payload(payload, {"tickers": list(prior_by_ticker.values())})
    OUTPUT.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    write_oauth_config()
    print(f"Wrote {OUTPUT} ({payload['summary']['ticker_count']} tickers)")
    if UNRESOLVED_UNITS:
        # Not fatal: these render as bare numbers, which is honest. It is still a
        # gap in _system/reference/listing_units_overrides.json worth closing.
        print(
            f"WARNING: {len(UNRESOLVED_UNITS)} listings have unresolved quote units; "
            "their figures render without a currency symbol.",
            file=sys.stderr,
        )
        for ticker, reason in sorted(UNRESOLVED_UNITS.items())[:20]:
            print(f"  {ticker}: {reason}", file=sys.stderr)
    from build_dashboard_shards import write_shards

    write_shards(payload, insights_doc, DATA_DIR)


if __name__ == "__main__":
    main()
