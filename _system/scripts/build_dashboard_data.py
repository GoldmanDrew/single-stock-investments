#!/usr/bin/env python3
"""Build portfolio dashboard JSON from ticker folders and _system/portfolio/holdings.md."""
from __future__ import annotations

import csv
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "dashboard" / "data"
OUTPUT = DATA_DIR / "dashboard_data.json"

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
}


def list_tickers() -> list[str]:
    skip = {"_system", "dashboard", ".git", ".github", ".cursor"}
    tickers = []
    for p in ROOT.iterdir():
        if p.is_dir() and p.name not in skip and not p.name.startswith("."):
            tickers.append(p.name)
    return sorted(tickers)


def parse_holdings() -> dict[str, dict]:
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


def has_download_script(ticker_dir: Path) -> tuple[bool, str | None]:
    patterns = [
        ticker_dir / "_scripts" / "download_and_organize.ps1",
        ticker_dir / "investor-documents" / "download_*_investor_docs.py",
    ]
    ps1 = ticker_dir / "_scripts" / "download_and_organize.ps1"
    if ps1.exists():
        return True, str(ps1.relative_to(ROOT))
    for py in (ticker_dir / "investor-documents").glob("download_*_investor_docs.py"):
        return True, str(py.relative_to(ROOT))
    for py in ticker_dir.rglob("download_*.py"):
        if "_system" not in py.parts:
            return True, str(py.relative_to(ROOT))
    return False, None


def count_pdfs(ticker_dir: Path) -> int:
    return sum(1 for _ in ticker_dir.rglob("*.pdf"))


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


def thesis_status(ticker_dir: Path) -> str:
    thesis = ticker_dir / "research" / "thesis.md"
    if not thesis.exists():
        return "unclear"
    text = thesis.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"\*\*Status:\*\*\s*(\w+)", text)
    return m.group(1).lower() if m else "unclear"


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
        })
    return out


def recent_developments(ticker_dir: Path, ticker: str) -> list[dict]:
    devs: list[dict] = []

    manifest = ticker_dir / "investor-documents" / "DOWNLOAD_MANIFEST.json"
    if manifest.exists():
        try:
            rows = json.loads(manifest.read_text(encoding="utf-8"))
            rows = sorted(rows, key=lambda r: r.get("filingDate", ""), reverse=True)
            for row in rows[:5]:
                if row.get("form", "").startswith("8-K"):
                    devs.append({
                        "date": row.get("filingDate"),
                        "type": "8-K",
                        "label": f"{row.get('form')} filed {row.get('filingDate')}",
                        "source": "SEC",
                    })
        except json.JSONDecodeError:
            pass

    research = ticker_dir / "research" / "reports"
    if research.exists():
        for f in sorted(research.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:3]:
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
    if row["readme"]: score += 20
    if row["download_script"]: score += 20
    if row["research_dir"]: score += 15
    if row["pdf_count"] >= 10: score += 15
    if row["last_download"]: score += 15
    if row["index_file"]: score += 15
    return min(score, 100)


def has_index(ticker_dir: Path) -> bool:
    return (ticker_dir / "INDEX.csv").exists() or (ticker_dir / "document-index.csv").exists()


def build_ticker_row(ticker: str, holdings: dict[str, dict]) -> dict:
    ticker_dir = ROOT / ticker
    meta = {**TICKER_META.get(ticker, {}), **holdings.get(ticker, {})}
    dl_script, dl_path = has_download_script(ticker_dir)
    row = {
        "ticker": ticker,
        "company": meta.get("company", ticker),
        "market": meta.get("market", "—"),
        "exchange": meta.get("exchange", "—"),
        "folder": f"{ticker}/",
        "readme": (ticker_dir / "README.md").exists(),
        "download_script": dl_script,
        "download_script_path": dl_path,
        "pdf_count": count_pdfs(ticker_dir),
        "sec_filings": count_sec_filings(ticker_dir),
        "research_dir": (ticker_dir / "research").exists(),
        "index_file": has_index(ticker_dir),
        "last_download": last_download(ticker_dir),
        "last_research": last_research(ticker_dir),
        "thesis_status": thesis_status(ticker_dir),
        "recent_files": recent_files(ticker_dir),
        "developments": recent_developments(ticker_dir, ticker),
    }
    row["completeness"] = completeness_score(row)
    return row


def build() -> dict:
    holdings = parse_holdings()
    tickers = list_tickers()
    rows = [build_ticker_row(t, holdings) for t in tickers]

    total_pdfs = sum(r["pdf_count"] for r in rows)
    with_research = sum(1 for r in rows if r["research_dir"])
    with_readme = sum(1 for r in rows if r["readme"])
    avg_complete = round(sum(r["completeness"] for r in rows) / len(rows)) if rows else 0

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "workspace": str(ROOT),
        "summary": {
            "ticker_count": len(rows),
            "total_pdfs": total_pdfs,
            "with_readme": with_readme,
            "with_research": with_research,
            "avg_completeness": avg_complete,
            "markets": sorted({r["market"] for r in rows}),
        },
        "tickers": rows,
    }


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = build()
    OUTPUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {OUTPUT} ({payload['summary']['ticker_count']} tickers)")


if __name__ == "__main__":
    main()
