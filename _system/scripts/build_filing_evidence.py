#!/usr/bin/env python3
"""Build per-ticker filing evidence from all documents in each ticker folder.

Outputs:
  {TICKER}/research/evidence/document_inventory.json
  {TICKER}/research/evidence/filing_digest_{date}.md

Tier 1 (full extract): latest annual, latest quarterly, latest 10-K, latest 10-Q, proxy/DEF 14A
Tier 2 (partial): prior 2 periodicals, earnings releases, 8-K
Tier 3 (inventory + keyword scan): all other PDFs/HTML in INDEX

Usage:
  python _system/scripts/build_filing_evidence.py
  python _system/scripts/build_filing_evidence.py FRMO ICE
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKIP_DIRS = {"_system", "dashboard", ".git", ".github", ".cursor", "research"}
TODAY = date.today().isoformat()

# Higher = more important for full read
TYPE_SCORE = {
    "10-k": 100,
    "10-q": 95,
    "20-f": 100,
    "annual": 98,
    "quarterly": 92,
    "proxy": 88,
    "def 14a": 88,
    "8-k": 75,
    "earnings": 80,
    "supplemental": 70,
    "presentation": 65,
    "otcqx": 90,
    "shareholder": 85,
    "md&a": 70,
}

SKIP_PATH = re.compile(
    r"(?:^|/)(?:4_\d{8}|SC\s*13|DOWNLOAD_MANIFEST|_download_log|\.cursor)",
    re.I,
)

KEYWORD_LINES = re.compile(
    r"(related.?part(?:y|ies)|lease|compensation|executive|director|"
    r"revenue|net income|operating income|total assets|stockholders.?"
    r"equity|book value|segment|investment [a-z]|fair value|"
    r"mineral|royalt|distribution|trustee|hash|bitcoin|"
    r"guidance|outlook|risk factor)",
    re.I,
)


def classify_path(rel: str) -> tuple[int, str]:
    low = rel.lower().replace("\\", "/")
    if SKIP_PATH.search(low):
        return 0, "skip"
    best = 10
    label = "other"
    for key, score in TYPE_SCORE.items():
        if key.replace(" ", "") in low.replace(" ", "").replace("_", "") or key in low:
            if score > best:
                best = score
                label = key
    if "10-k" in low or "10_k" in low:
        return 100, "10-K"
    if "10-q" in low or "10_q" in low:
        return 95, "10-Q"
    if "annual_report" in low or "annual-report" in low or "_annual_" in low:
        return 98, "annual"
    if "quarterly_report" in low or "quarterly" in low:
        return 92, "quarterly"
    if "def_14a" in low or "def 14a" in low or "proxy" in low:
        return 88, "proxy"
    if "8-k" in low or "8_k" in low:
        return 75, "8-K"
    if "earnings" in low or "earning" in low:
        return 80, "earnings"
    return best, label


def parse_date_from_name(name: str) -> str:
    m = re.search(r"(20\d{2})[-_]?(0[1-9]|1[0-2])[-_]?(0[1-9]|[12]\d|3[01])", name)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r"(20\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])", name)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return ""


def list_docs(ticker_dir: Path) -> list[dict]:
    rows: list[dict] = []
    idx = ticker_dir / "INDEX.csv"
    if idx.exists():
        with idx.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                p = ticker_dir / row["path"]
                if p.is_file() and p.suffix.lower() in {".pdf", ".htm", ".html"}:
                    score, kind = classify_path(row["path"])
                    rows.append(
                        {
                            "path": row["path"].replace("\\", "/"),
                            "filename": row["filename"],
                            "bytes": int(row.get("bytes") or 0),
                            "score": score,
                            "kind": kind,
                            "file_date": parse_date_from_name(row["filename"]),
                        }
                    )
        return rows
    for f in sorted(ticker_dir.rglob("*")):
        if not f.is_file():
            continue
        rel = str(f.relative_to(ticker_dir)).replace("\\", "/")
        if rel.split("/")[0] in SKIP_DIRS:
            continue
        if f.suffix.lower() not in {".pdf", ".htm", ".html"}:
            continue
        score, kind = classify_path(rel)
        rows.append(
            {
                "path": rel,
                "filename": f.name,
                "bytes": f.stat().st_size,
                "score": score,
                "kind": kind,
                "file_date": parse_date_from_name(f.name),
            }
        )
    return rows


def extract_html(path: Path, max_chars: int = 120_000) -> str:
    text = path.read_text(encoding="utf-8", errors="ignore")
    if "<ix:nonFraction" in text or "xmlns:ix=" in text:
        snippets = []
        for m in re.finditer(
            r'name="([^"]+)"[^>]*>([^<]*)</ix:nonFraction>', text
        ):
            name, val = m.group(1), m.group(2).strip()
            if any(
                k in name
                for k in (
                    "Revenue", "Operating", "NetIncome", "Earnings", "Assets",
                    "Liabilities", "Equity", "Debt", "Cash", "EPS", "Income",
                )
            ):
                if "Member" not in name and "Axis" not in name:
                    snippets.append(f"{name.split(':')[-1]}: {val}")
        ix_block = "\n".join(snippets[:400])
        clean = re.sub(r"<[^>]+>", " ", text)
        clean = re.sub(r"\s+", " ", clean)
        return (ix_block + "\n\n" + clean[:max_chars])[:max_chars]
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = re.sub(r"\s+", " ", clean)
    return clean[:max_chars]


def extract_pdf(path: Path, max_pages: int) -> str:
    from pypdf import PdfReader

    reader = PdfReader(path)
    pages = reader.pages[:max_pages]
    return "\n".join((p.extract_text() or "") for p in pages)


def keyword_snippets(text: str, limit: int = 40) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        s = line.strip()
        if len(s) < 12 or len(s) > 220:
            continue
        if not KEYWORD_LINES.search(s):
            continue
        key = s[:100].lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s[:220])
        if len(out) >= limit:
            break
    return out


def process_doc(ticker_dir: Path, doc: dict, tier: str) -> dict:
    path = ticker_dir / doc["path"]
    result = {**doc, "tier": tier, "chars": 0, "snippets": [], "error": None}
    try:
        if path.suffix.lower() == ".pdf":
            pages = 120 if tier == "full" else (15 if tier == "partial" else 3)
            text = extract_pdf(path, pages)
        else:
            cap = 120_000 if tier == "full" else (30_000 if tier == "partial" else 8_000)
            text = extract_html(path, cap)
        result["chars"] = len(text)
        result["snippets"] = keyword_snippets(text, 50 if tier == "full" else 20)
        if tier == "full":
            cache = ticker_dir / "research" / "evidence" / "_text"
            cache.mkdir(parents=True, exist_ok=True)
            safe = re.sub(r"[^\w.-]", "_", doc["filename"])[:80]
            (cache / f"{safe}.txt").write_text(text[:200_000], encoding="utf-8")
    except Exception as e:
        result["error"] = str(e)
    return result


def build_ticker(ticker: str) -> int:
    ticker_dir = ROOT / ticker
    if not ticker_dir.is_dir():
        print(f"SKIP {ticker}: no folder")
        return 0

    docs = list_docs(ticker_dir)
    docs.sort(key=lambda d: (d["score"], d["file_date"], d["filename"]), reverse=True)

    # Tier assignment
    kind_latest: dict[str, dict] = {}
    for d in docs:
        if d["score"] <= 0:
            d["tier"] = "inventory"
            continue
        k = d["kind"]
        if k not in kind_latest or (d["file_date"], d["filename"]) > (
            kind_latest[k]["file_date"],
            kind_latest[k]["filename"],
        ):
            kind_latest[k] = d

    full_kinds = {"10-K", "10-Q", "annual", "quarterly", "proxy", "otcqx", "10-k", "10-q"}
    full_count = 0
    partial_count = 0
    for d in docs:
        if d.get("tier") == "inventory":
            continue
        if d["kind"] in full_kinds and d is kind_latest.get(d["kind"]):
            d["tier"] = "full"
            full_count += 1
        elif d["score"] >= 70 and full_count + partial_count < 12:
            d["tier"] = "partial"
            partial_count += 1
        elif d["score"] >= 50:
            d["tier"] = "scan"
        else:
            d["tier"] = "inventory"

    evidence_dir = ticker_dir / "research" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    processed = []
    for d in docs:
        tier = d.get("tier", "inventory")
        if tier == "inventory":
            processed.append({**d, "tier": "inventory", "chars": 0, "snippets": [], "error": None})
        else:
            processed.append(process_doc(ticker_dir, d, tier))

    inv_path = evidence_dir / "document_inventory.json"
    inv_path.write_text(
        json.dumps(
            {"ticker": ticker, "as_of": TODAY, "document_count": len(processed), "documents": processed},
            indent=2,
        ),
        encoding="utf-8",
    )

    lines = [
        f"# Filing digest — {ticker}",
        f"",
        f"**Generated:** {TODAY}  ",
        f"**Agent:** Marvin (`build_filing_evidence.py`)  ",
        f"**Inventory:** `{ticker}/research/evidence/document_inventory.json`  ",
        f"",
        f"Documents in folder: **{len(processed)}** (all listed below; Tier 1–3 extracted or keyword-scanned).",
        f"",
        f"## Document inventory",
        f"",
        f"| Tier | Kind | File date | Path | Chars |",
        f"|------|------|-----------|------|-------|",
    ]
    for p in sorted(processed, key=lambda x: (-x["score"], x["path"])):
        err = f" ERR:{p['error'][:30]}" if p.get("error") else ""
        lines.append(
            f"| {p.get('tier','?')} | {p['kind']} | {p.get('file_date') or '—'} | `{p['path']}` | {p.get('chars',0)}{err} |"
        )

    for tier_name in ("full", "partial"):
        tier_docs = [p for p in processed if p.get("tier") == tier_name]
        if not tier_docs:
            continue
        lines.append(f"")
        lines.append(f"## Tier: {tier_name} — extracts")
        for p in tier_docs:
            lines.append(f"")
            lines.append(f"### `{p['path']}`")
            if p.get("error"):
                lines.append(f"Extract error: {p['error']}")
                continue
            if p.get("snippets"):
                lines.append("**Keyword snippets (related party, financials, segments):**")
                for s in p["snippets"][:35]:
                    lines.append(f"- {s}")
            else:
                lines.append("- *(no keyword hits; see cached full text in `research/evidence/_text/` if tier=full)*")

    digest_path = evidence_dir / f"filing_digest_{TODAY}.md"
    digest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    try:
        import sys

        scripts = Path(__file__).resolve().parent
        if str(scripts) not in sys.path:
            sys.path.insert(0, str(scripts))
        from filing_facts import write_filing_facts_json

        ff = write_filing_facts_json(ticker_dir, TODAY)
        if ff:
            lines.append("")
            lines.append(f"**Filing facts:** `{ff.relative_to(ticker_dir).as_posix()}`")
    except Exception as e:
        print(f"WARN {ticker}: filing_facts — {e}")

    print(
        f"OK {ticker}: docs={len(processed)} full={sum(1 for p in processed if p.get('tier') == 'full')} "
        f"partial={sum(1 for p in processed if p.get('tier') == 'partial')}"
    )
    return len(processed)


def tickers_from_holdings() -> list[str]:
    path = ROOT / "_system" / "portfolio" / "holdings.md"
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("|") and not line.startswith("| Ticker") and not line.startswith("|--"):
            parts = [c.strip() for c in line.split("|") if c.strip()]
            if parts and parts[0] not in ("Ticker", "--------"):
                out.append(parts[0])
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("tickers", nargs="*", help="Optional ticker list")
    args = parser.parse_args()
    tickers = args.tickers or tickers_from_holdings()
    total = 0
    for t in tickers:
        total += build_ticker(t)
    print(f"Done. {len(tickers)} tickers, {total} documents inventoried.")


if __name__ == "__main__":
    main()
