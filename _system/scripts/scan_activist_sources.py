#!/usr/bin/env python3
"""Orchestrate activist source scanning for portfolio tickers.

Usage:
  python scan_activist_sources.py
  python scan_activist_sources.py --ticker APLD
  python scan_activist_sources.py --dry-run
  python scan_activist_sources.py --sec-only
"""
from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

from activist_common import (
    activist_index_path,
    activist_reports_dir,
    load_global_scan,
    load_ticker_index,
    now_iso,
    portfolio_tickers,
    save_global_scan,
    save_ticker_index,
    upsert_report,
    write_json,
)
from activist_date_parse import parse_local_report_metadata
from sec_filer_parse import is_sec_filing_relpath
from build_activist_feed import build_feed
from extract_activist_text import extract_ticker_activist_text
from milly_activist_reconcile import reconcile_ticker
from activist_triage import triage_portfolio
from activist_short_md import collect_short_markdown_reports
from press_activist_digest import scan_press_wires
from sec_filer_discovery import OUTPUT_PATH as DISCOVERY_OUTPUT
from sec_filer_discovery import discover as discover_filers
from sec_activist_scan import scan_portfolio_sec
from site_activist_scan import scan_publisher_sites
from third_party_inventory import write_inventory
from verify_activist_reports import verify_ticker

ROOT = Path(__file__).resolve().parents[2]
REVIEW_DIR = ROOT / "_system" / "research"
PENDING_DIR = ROOT / "_system" / "reviews" / "pending"


def collect_local_reports(ticker: str) -> list[dict]:
    out: list[dict] = []
    for side in ("long", "short"):
        base = activist_reports_dir(ticker, side)
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.name.startswith("."):
                continue
            rel_path = str(path.relative_to(ROOT)).replace("\\", "/")
            if is_sec_filing_relpath(rel_path):
                continue
            if path.suffix.lower() not in {".pdf", ".html", ".htm"}:
                continue
            meta = parse_local_report_metadata(path, side)
            meta["local_file"] = str(path.relative_to(ROOT)).replace("\\", "/")
            if meta.get("local_pdf"):
                meta["local_pdf"] = meta["local_file"]
            out.append(
                {
                    "ticker": ticker,
                    **meta,
                    "source": "local",
                    "status": "cached",
                }
            )
    return out


def write_review_queue(all_hits: list[dict], scan_date: str) -> Path | None:
    """Legacy queue — kept for compatibility; triage queue is authoritative."""
    return None


def collect_human_review_rows(tickers: list[str]) -> list[dict]:
    rows: list[dict] = []
    for ticker in tickers:
        index = load_ticker_index(ticker)
        for report in index.get("reports") or []:
            if report.get("triage_verdict") == "human_review":
                rows.append({**report, "ticker": ticker})
    return rows


def write_portfolio_scan_md(all_hits: list[dict], scan_date: str, tickers: list[str]) -> Path:
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    out = REVIEW_DIR / f"activist_scan_{scan_date}.md"
    by_ticker: dict[str, list[dict]] = {t: [] for t in tickers}
    for hit in all_hits:
        t = hit.get("ticker")
        if t in by_ticker:
            by_ticker[t].append(hit)
    lines = [
        f"# Portfolio activist scan",
        "",
        f"**Date:** {scan_date}",
        f"**Registry:** `_system/frameworks/activist_firm_registry.json`",
        "",
        "| Ticker | Long | Short | Latest | Notes |",
        "|--------|------|-------|--------|-------|",
    ]
    for ticker in tickers:
        index = load_ticker_index(ticker)
        reports = [r for r in (index.get("reports") or []) if r.get("include_in_feed", True)]
        long_n = sum(1 for r in reports if r.get("side") == "long")
        short_n = sum(1 for r in reports if r.get("side") == "short")
        latest = max((r.get("report_date") or "" for r in reports), default="")
        note = f"{len(reports)} indexed" if reports else "no hits"
        lines.append(f"| {ticker} | {long_n} | {short_n} | {latest or '—'} | {note} |")
    lines.extend(
        [
            "",
            "Run: `python _system/scripts/scan_activist_sources.py`",
            "Drive drop: `Admin/Activist/Long/{TICKER}/` or `Admin/Activist/Short/{TICKER}/`",
            "",
        ]
    )
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan activist long/short sources for portfolio tickers.")
    parser.add_argument("--ticker", action="append", help="Restrict to ticker (repeatable)")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--sec-only", action="store_true")
    parser.add_argument("--site-only", action="store_true")
    parser.add_argument("--wire-only", action="store_true", help="Only run press/letter digest ingest")
    parser.add_argument("--skip-feed", action="store_true")
    parser.add_argument("--skip-wire", action="store_true", help="Skip press/letter digest lane")
    parser.add_argument("--skip-site", action="store_true", help="Skip publisher site scrape")
    parser.add_argument("--include-passive", action="store_true", help="Index passive SC 13G filings")
    parser.add_argument("--reindex-local", action="store_true", help="Re-parse local SEC files without re-download")
    parser.add_argument("--reconcile", action="store_true", help="Run Milly activist mechanical reconcile after scan")
    parser.add_argument(
        "--backfill-days",
        type=int,
        default=None,
        help="Limit press-wire seeds to this many trailing days (default: all seeds)",
    )
    parser.add_argument(
        "--fetch-sec",
        action="store_true",
        help="Fetch SEC metadata during triage when local file missing",
    )
    parser.add_argument(
        "--discover-filers",
        action="store_true",
        help="Also run filer-driven discovery (what registry firms filed, anywhere)",
    )
    parser.add_argument(
        "--discover-min-date",
        default=None,
        help="Earliest filing date for filer-driven discovery (default: last 18 months)",
    )
    args = parser.parse_args()

    tickers = [t.upper() for t in args.ticker] if args.ticker else portfolio_tickers()
    all_hits: list[dict] = []
    run_sec = not args.site_only and not args.wire_only
    run_site = not args.sec_only and not args.wire_only and not args.skip_site
    run_wire = not args.sec_only and not args.site_only and not args.skip_wire

    if run_sec:
        sec = scan_portfolio_sec(
            tickers,
            dry_run=args.dry_run,
            include_passive=args.include_passive,
            reindex_local=args.reindex_local,
        )
        all_hits.extend(sec.get("hits") or [])

    if run_site:
        site = scan_publisher_sites(tickers, dry_run=args.dry_run)
        all_hits.extend(site.get("hits") or [])

    if args.discover_filers:
        # Filer-driven, deliberately separate from the issuer-driven lanes: it
        # surfaces campaigns at companies we do not hold, so its rows never
        # enter a ticker index. They land in activist_filer_discovery.json for
        # review.
        min_date = args.discover_min_date or (
            date.fromisoformat(args.date) - timedelta(days=548)
        ).isoformat()
        try:
            found = discover_filers(min_date=min_date, write_registry_ciks=not args.dry_run)
            if not args.dry_run:
                write_json(DISCOVERY_OUTPUT, found)
            print(
                f"filer discovery: {found['row_count']} filings from "
                f"{found['resolved_firm_count']}/{found['firm_count']} firms "
                f"({found['off_book_count']} outside the book)"
            )
        except Exception as exc:  # never let discovery break the main scan
            print(f"filer discovery skipped: {type(exc).__name__}: {exc}")

    if run_wire:
        wire = scan_press_wires(
            tickers,
            dry_run=args.dry_run,
            backfill_days=args.backfill_days,
            scan_date=args.date,
        )
        all_hits.extend(wire.get("hits") or [])

    for ticker in tickers:
        local = collect_local_reports(ticker)
        short_md = collect_short_markdown_reports(ticker)
        if not args.dry_run:
            index = load_ticker_index(ticker)
            changed = False
            for hit in local + short_md:
                entry = {k: v for k, v in hit.items() if k != "ticker"}
                entry.setdefault("status", "cached")
                entry.setdefault("tier", "context")
                if upsert_report(index, entry):
                    changed = True
            if changed:
                save_ticker_index(ticker, index)
        all_hits.extend(local)
        all_hits.extend(short_md)
        if not args.dry_run:
            extract_ticker_activist_text(ticker)
            verify_ticker(ticker)
            write_inventory(ticker)

    payload = {
        "generated_at": now_iso(),
        "scan_date": args.date,
        "dry_run": args.dry_run,
        "ticker_count": len(tickers),
        "hit_count": len(all_hits),
        "hits": all_hits,
    }
    if not args.dry_run:
        save_global_scan(payload)

    write_portfolio_scan_md(all_hits, args.date, tickers)

    if not args.dry_run:
        from cleanup_activist_false_positives import cleanup_ticker

        for ticker in tickers:
            index_path = activist_index_path(ticker)
            if index_path.exists():
                cleanup_ticker(ticker, apply=True)

        triage_summary = triage_portfolio(
            tickers=tickers,
            apply=True,
            fetch_sec=args.fetch_sec,
            scan_date=args.date,
        )
        print(
            f"Triage: {triage_summary.get('total_reports', 0)} reports "
            f"({triage_summary.get('counts', {})})"
        )
        if triage_summary.get("human_count"):
            print(f"  Human queue: {triage_summary.get('queue_path')}")

    write_review_queue(all_hits, args.date)

    if not args.skip_feed and not args.dry_run:
        build_feed()

    if args.reconcile and not args.dry_run:
        for ticker in tickers:
            index = load_ticker_index(ticker)
            pending = [
                r
                for r in (index.get("reports") or [])
                if r.get("include_in_feed", True)
                and (
                    r.get("triage_verdict") == "human_review"
                    or r.get("status") in ("new", "cached")
                    or (r.get("status") == "triaged_auto" and not r.get("milly_verdict"))
                )
            ]
            if pending:
                reconcile_ticker(ticker, args.date, write=True)

    print(f"Activist scan complete: {len(tickers)} tickers, {len(all_hits)} hits")
    for ticker in tickers:
        idx = activist_index_path(ticker)
        if idx.exists():
            count = len(load_ticker_index(ticker).get("reports") or [])
            print(f"  {ticker}: {count} indexed -> {idx.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
