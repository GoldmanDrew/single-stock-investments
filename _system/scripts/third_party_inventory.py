"""Collect all third-party sources for a ticker (HK, Substacks, PDFs, shorts, pending)."""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))
from vault_paths import wisdom_root  # noqa: E402

THIRD_PARTY_MD = ROOT / "_system" / "frameworks" / "third_party_sources.md"
HK_INDEX = wisdom_root() / "hk_ticker_index.json"

# Human bulk-approved: promote inventory context rows to approved for synthesis blend
BULK_CONTEXT_APPROVED_TICKERS = frozenset(
    {"TEQ.ST", "TPL", "FRMO", "CMSG", "MSB", "ICE", "SJT", "KEWL"}
)


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _parse_md_table_paths(text: str) -> list[dict]:
    rows: list[dict] = []
    for line in text.splitlines():
        if not line.strip().startswith("|") or "---" in line:
            continue
        cols = [c.strip() for c in line.split("|")[1:-1]]
        if len(cols) < 2:
            continue
        row_text = " ".join(cols)
        path_m = re.search(r"`([^`]+\.(?:pdf|md|htm|html|txt))`", row_text, re.I)
        url_m = re.search(r"https?://[^\s`|)]+", row_text)
        title = cols[0] if cols else "reference"
        if path_m:
            rows.append(
                {
                    "source_id": "reference",
                    "title": title[:120],
                    "path": path_m.group(1),
                    "status": "context",
                    "use": cols[-1][:200] if cols else "",
                }
            )
        elif url_m:
            rows.append(
                {
                    "source_id": "reference",
                    "title": title[:120],
                    "path": url_m.group(0),
                    "status": "context",
                    "use": cols[-1][:200] if cols else "",
                }
            )
    return rows


def _approved_registry(ticker: str) -> list[dict]:
    if not THIRD_PARTY_MD.exists():
        return []
    text = THIRD_PARTY_MD.read_text(encoding="utf-8", errors="ignore")
    rows: list[dict] = []
    in_reg = False
    for line in text.splitlines():
        if line.startswith("## Approved registry"):
            in_reg = True
            continue
        if in_reg and line.startswith("## "):
            break
        if not in_reg or not line.strip().startswith("|"):
            continue
        if "---" in line or "ID |" in line:
            continue
        cols = [c.strip().strip("`") for c in line.split("|")[1:-1]]
        if len(cols) < 5:
            continue
        tickers_col = cols[2]
        if ticker.upper() not in tickers_col.upper() and tickers_col not in ("…", "..."):
            continue
        path = cols[3]
        if path == "approved_substacks.md":
            # Publisher-level approval; URLs live in references.md
            continue
        rows.append(
            {
                "source_id": cols[0],
                "title": cols[1],
                "path": path,
                "status": "approved",
                "use": cols[4][:200],
            }
        )
    return rows


def _research_notes(ticker: str) -> list[dict]:
    notes_dir = ROOT / ticker / "investor-documents" / "research-notes"
    if not notes_dir.is_dir():
        return []
    approved_text = THIRD_PARTY_MD.read_text(encoding="utf-8", errors="ignore") if THIRD_PARTY_MD.exists() else ""
    out: list[dict] = []
    for f in sorted(notes_dir.iterdir()):
        if f.suffix.lower() not in (".pdf", ".md", ".htm", ".html"):
            continue
        rel = _rel(f)
        status = "approved" if f.name in approved_text else "pending"
        out.append(
            {
                "source_id": "research_note",
                "title": f.name,
                "path": rel,
                "status": status,
                "use": "investor-documents/research-notes",
            }
        )
    return out


def _activist_reports(ticker: str) -> list[dict]:
    index_path = ROOT / ticker / "third-party-analyses" / "activist_reports_index.json"
    if index_path.exists():
        data = json.loads(index_path.read_text(encoding="utf-8"))
        out: list[dict] = []
        for report in data.get("reports") or []:
            path = report.get("local_pdf") or report.get("local_file")
            if not path:
                continue
            side = report.get("side") or "long"
            source_id = "activist_long" if side == "long" else "activist_short"
            out.append(
                {
                    "source_id": source_id,
                    "title": report.get("title") or report.get("firm_name") or report.get("firm_id"),
                    "path": path,
                    "status": "context",
                    "use": f"activist/{side} — {report.get('source', 'scan')}",
                }
            )
        if out:
            return out
    base = ROOT / ticker / "third-party-analyses" / "activist_reports"
    if not base.is_dir():
        return []
    out = []
    for side in ("long", "short"):
        side_dir = base / side
        if not side_dir.is_dir():
            continue
        source_id = "activist_long" if side == "long" else "activist_short"
        for f in sorted(side_dir.glob("*.pdf")):
            out.append(
                {
                    "source_id": source_id,
                    "title": f.stem,
                    "path": _rel(f),
                    "status": "context",
                    "use": f"activist/{side} scan",
                }
            )
    return out


def _short_reports(ticker: str) -> list[dict]:
    sr = ROOT / ticker / "third-party-analyses" / "short_reports"
    if not sr.is_dir():
        return []
    return [
        {
            "source_id": "short_report",
            "title": f.stem,
            "path": _rel(f),
            "status": "context",
            "use": "activist/short scan",
        }
        for f in sorted(sr.glob("*.md"))
    ]


def _vic_sources(ticker: str) -> list[dict]:
    vic_dir = ROOT / ticker / "third-party-analyses" / "vic"
    if not vic_dir.is_dir():
        return []
    out: list[dict] = []
    stems = sorted({f.stem for f in [*vic_dir.glob("*.md"), *vic_dir.glob("*.pdf")]})
    for stem in stems:
        md = vic_dir / f"{stem}.md"
        pdf = vic_dir / f"{stem}.pdf"
        f = pdf if pdf.exists() else md
        title = f.stem
        if md.exists():
            text = md.read_text(encoding="utf-8", errors="ignore")
            for line in text.splitlines():
                if line.startswith("# "):
                    title = line[2:].strip()
                    break
        out.append(
            {
                "source_id": "vic",
                "title": title[:120],
                "path": _rel(f),
                "status": "pending",
                "use": "VIC local single-page intake; human approval required",
            }
        )
    return out


def _hk_sources(ticker: str) -> list[dict]:
    tp = ROOT / ticker / "third-party-analyses"
    scans = sorted(tp.glob("hk_scan_*.json")) if tp.is_dir() else []
    if scans:
        data = json.loads(scans[-1].read_text(encoding="utf-8"))
        return [
            {
                "source_id": "hk",
                "title": s.get("topic", "")[:120],
                "path": s.get("path", ""),
                "status": "context",
                "use": s.get("use", "Horizon Kinetics / Stahl"),
            }
            for s in data.get("sources", [])
        ]
    if HK_INDEX.exists():
        idx = json.loads(HK_INDEX.read_text(encoding="utf-8"))
        entry = idx.get("tickers", {}).get(ticker.upper())
        if entry:
            out = []
            for c in entry.get("curated", []) + entry.get("stahl_pdfs", []):
                out.append(
                    {
                        "source_id": "hk",
                        "title": c.get("topic", ""),
                        "path": c.get("path", ""),
                        "status": "context",
                        "use": c.get("use", ""),
                    }
                )
            return out
    return []


def _dedupe(sources: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for s in sources:
        key = (s.get("path") or s.get("title", "")).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def collect_third_party_sources(ticker: str) -> dict:
    ticker = ticker.upper()
    sources: list[dict] = []
    sources.extend(_approved_registry(ticker))
    sources.extend(_vic_sources(ticker))
    ref = ROOT / ticker / "third-party-analyses" / "references.md"
    if ref.exists():
        sources.extend(_parse_md_table_paths(ref.read_text(encoding="utf-8", errors="ignore")))
    sources.extend(_research_notes(ticker))
    sources.extend(_activist_reports(ticker))
    sources.extend(_short_reports(ticker))
    sources.extend(_hk_sources(ticker))
    sources = _dedupe(sources)

    if ticker in BULK_CONTEXT_APPROVED_TICKERS:
        for s in sources:
            if s.get("status") == "context":
                s["status"] = "approved"

    pending = [s for s in sources if s.get("status") == "pending"]
    approved = [s for s in sources if s.get("status") == "approved"]
    context = [s for s in sources if s.get("status") == "context"]

    hk_indexed = False
    if HK_INDEX.exists():
        hk_indexed = ticker in json.loads(HK_INDEX.read_text(encoding="utf-8")).get("tickers", {})

    return {
        "ticker": ticker,
        "scan_date": date.today().isoformat(),
        "source_count": len(sources),
        "approved_count": len(approved),
        "pending_count": len(pending),
        "context_count": len(context),
        "sources": sources,
        "hk_indexed": hk_indexed,
    }


def write_inventory(ticker: str, out_date: str | None = None) -> tuple[Path, Path]:
    out_date = out_date or date.today().isoformat()
    result = collect_third_party_sources(ticker)
    tp = ROOT / ticker / "third-party-analyses"
    tp.mkdir(parents=True, exist_ok=True)
    json_path = tp / f"source_inventory_{out_date}.json"
    md_path = tp / f"source_inventory_{out_date}.md"
    json_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    lines = [
        f"# {ticker} — Third-party source inventory",
        "",
        f"**Date:** {out_date}",
        f"**Sources:** {result['source_count']} total "
        f"({result['approved_count']} approved, {result['pending_count']} pending, "
        f"{result['context_count']} context)",
        "",
        "| ID | Title | Path | Status | Use |",
        "|----|-------|------|--------|-----|",
    ]
    for s in result["sources"]:
        lines.append(
            f"| {s.get('source_id', '')} | {s.get('title', '')[:60]} | `{s.get('path', '')}` | "
            f"{s.get('status', '')} | {s.get('use', '')[:80]} |"
        )
    if not result["sources"]:
        lines.append("| (none) | — | — | — | Primary filings only |")
    lines.append("")
    lines.append(
        f"Cross-check required: `{ticker}/research/cross_check_third_party_{out_date}.md`"
    )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def load_latest_inventory(ticker: str) -> dict | None:
    tp = ROOT / ticker / "third-party-analyses"
    inv = sorted(tp.glob("source_inventory_*.json")) if tp.is_dir() else []
    if not inv:
        return None
    return json.loads(inv[-1].read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rebuild a ticker's third-party source inventory.")
    parser.add_argument("ticker", help="Existing repo ticker folder")
    parser.add_argument("--date", dest="out_date", help="Inventory date (YYYY-MM-DD)")
    args = parser.parse_args(argv)
    ticker = str(args.ticker).strip()
    if not ticker or not (ROOT / ticker).is_dir():
        parser.error(f"unknown ticker folder: {ticker or '(empty)'}")
    json_path, md_path = write_inventory(ticker, args.out_date)
    print(json_path.relative_to(ROOT))
    print(md_path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
