#!/usr/bin/env python3
"""Coverage and blocker report for the SSI Perplexity-grade pipeline.

Answers "what is stopping each ticker from producing a shippable report?" —
per ticker and in aggregate — so partial coverage becomes a work queue instead
of a silent degradation. Read-only: inspects artifacts on disk, runs the
comparability gate in memory, and never writes into ticker folders.

Stages checked per ticker:
  filings      raw SEC documents present
  extracts     >=2 full-tier `_text` extracts in the same form class
  gate         comparability gate finds a prior-year pair (else YoY diffs are
               intra-filing only)
  xbrl         research/evidence/sec_companyfacts.json present
  transcripts  earnings transcripts present (Management Ledger input)
  claims       Skeptic-verified claims file present
  report       ssi_report_*.md present, with its shipping-gate verdict

Usage:
  python _system/scripts/ssi_coverage_report.py
  python _system/scripts/ssi_coverage_report.py --holdings --md out.md
  python _system/scripts/ssi_coverage_report.py --json coverage.json --top-blockers
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

ROOT = SCRIPT_DIR.parents[1]

# Windows consoles default to cp1252 and raise on the em-dashes/arrows used in
# the remedy text; never let a report crash on its own formatting.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# blocker → the concrete action that clears it
REMEDIES = {
    "no_filings": "run download_us_investor_docs.py (needs a CIK in us_ticker_config.json / registry.json)",
    "no_extracts": "run build_filing_evidence.py TICKER",
    "single_period_only": "no prior-year filing on disk in the same form class — download more history, then re-run build_filing_evidence.py",
    "no_gated_comparison": "prior-year filing exists but is not full-tier or is outside the 300-430d window — check promote_comparables()",
    "no_xbrl": "fetch companyfacts: automate_valuation_readiness.py --collect (needs a non-null CIK)",
    "no_transcripts": "earnings/transcript feed unconfigured (earnings_calendar.json access_status) — blocks the Management Ledger",
    "no_claims": "run run_ssi_pipeline.py TICKER",
    "no_report": "run build_ssi_report.py TICKER",
}


def _has_files(path: Path) -> bool:
    return path.is_dir() and any(path.iterdir())


def _form_class(name: str) -> str:
    upper = name.upper()
    if upper.startswith(("10-K", "20-F", "40-F", "ANNUAL")):
        return "annual"
    if upper.startswith(("10-Q", "QUARTERLY", "INTERIM", "SEMI")):
        return "quarterly"
    return "other"


def assess(ticker: str, as_of: str, run_gate: bool = True) -> dict:
    ticker_dir = ROOT / ticker
    research = ticker_dir / "research"
    evidence = research / "evidence"
    text_dir = evidence / "_text"

    row: dict = {"ticker": ticker, "blockers": []}

    row["filings"] = _has_files(ticker_dir / "investor-documents" / "sec-edgar")
    extracts = sorted(text_dir.glob("*.txt")) if text_dir.is_dir() else []
    row["extract_count"] = len(extracts)
    by_class: dict[str, int] = {}
    for path in extracts:
        by_class[_form_class(path.name)] = by_class.get(_form_class(path.name), 0) + 1
    row["extracts_by_class"] = by_class
    row["has_pair"] = any(n >= 2 for cls, n in by_class.items() if cls != "other")

    row["xbrl"] = (evidence / "sec_companyfacts.json").exists()
    row["transcripts"] = _has_files(ticker_dir / "investor-documents" / "transcripts")

    gated = None
    if run_gate and extracts:
        try:
            from build_ssi_evidence_pack import build_evidence_pack

            pack = build_evidence_pack(ticker_dir, as_of)
            gated = sum(1 for c in pack.get("comparisons", []) if c.get("gate", {}).get("matched"))
        except Exception as exc:  # a broken ticker must not kill the sweep
            row["gate_error"] = str(exc)[:120]
    row["gated_comparisons"] = gated

    verified = sorted(evidence.glob("ssi_verified_claims_*.json"), reverse=True)
    row["claims"] = bool(verified)
    if verified:
        try:
            doc = json.loads(verified[0].read_text(encoding="utf-8"))
            row["verified_count"] = doc.get("verified_count")
            row["failed_count"] = doc.get("failed_count")
            row["severity5"] = sum(
                1 for c in doc.get("verified_claims", []) if c.get("severity") == 5
            )
        except (OSError, json.JSONDecodeError):
            pass

    reports = sorted(research.glob("ssi_report_*.md"), reverse=True) if research.is_dir() else []
    row["report"] = bool(reports)
    if reports:
        row["report_path"] = str(reports[0].relative_to(ROOT)).replace("\\", "/")
        stamp = reports[0].stem.replace("ssi_report_", "")
        gate_path = evidence / f"ssi_report_gate_{stamp}.json"
        try:
            gate = json.loads(gate_path.read_text(encoding="utf-8"))
            row["gate_result"] = gate.get("result")
            row["gate_fails"] = [c["name"] for c in gate["checks"] if c["verdict"] == "FAIL"]
        except (OSError, json.JSONDecodeError):
            pass

    # Ordered blockers: the first is the one to act on next.
    if not row["filings"]:
        row["blockers"].append("no_filings")
    elif not extracts:
        row["blockers"].append("no_extracts")
    elif not row["has_pair"]:
        row["blockers"].append("single_period_only")
    elif gated == 0:
        row["blockers"].append("no_gated_comparison")
    if not row["xbrl"]:
        row["blockers"].append("no_xbrl")
    if not row["transcripts"]:
        row["blockers"].append("no_transcripts")
    if extracts and not row["claims"]:
        row["blockers"].append("no_claims")
    if row["claims"] and not row["report"]:
        row["blockers"].append("no_report")
    return row


def _holdings() -> list[str]:
    path = ROOT / "_system" / "portfolio" / "holdings.md"
    out: list[str] = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("|") and not line.startswith("| Ticker") and not line.startswith("|--"):
            cells = [c.strip() for c in line.split("|") if c.strip()]
            if cells and cells[0] not in ("Ticker", "--------"):
                out.append(cells[0])
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tickers", nargs="*")
    parser.add_argument("--date", default=datetime.now().date().isoformat())
    parser.add_argument("--holdings", action="store_true")
    parser.add_argument("--no-gate", action="store_true", help="skip the in-memory gate run (much faster)")
    parser.add_argument("--json", dest="json_out")
    parser.add_argument("--md", dest="md_out")
    parser.add_argument("--top-blockers", action="store_true", help="print the per-blocker ticker lists")
    args = parser.parse_args(argv)

    if args.tickers:
        tickers = [t.strip() for t in args.tickers if t.strip()]
    elif args.holdings:
        tickers = _holdings()
    else:
        tickers = sorted(
            p.name for p in ROOT.iterdir()
            if p.is_dir() and not p.name.startswith((".", "_")) and p.name != "dashboard"
        )

    rows = [assess(t, args.date, run_gate=not args.no_gate) for t in tickers]

    counts: dict[str, int] = {}
    by_blocker: dict[str, list[str]] = {}
    for row in rows:
        for blocker in row["blockers"]:
            counts[blocker] = counts.get(blocker, 0) + 1
            by_blocker.setdefault(blocker, []).append(row["ticker"])

    ready = [r for r in rows if not r["blockers"]]
    with_gate = [r for r in rows if (r.get("gated_comparisons") or 0) > 0]
    with_report = [r for r in rows if r["report"]]
    shippable = [r for r in rows if r.get("gate_result") == "SHIPPABLE"]

    summary = {
        "as_of": args.date,
        "tickers": len(rows),
        "fully_unblocked": len(ready),
        "with_gated_comparison": len(with_gate),
        "with_xbrl": sum(1 for r in rows if r["xbrl"]),
        "with_transcripts": sum(1 for r in rows if r["transcripts"]),
        "with_verified_claims": sum(1 for r in rows if r["claims"]),
        "with_report": len(with_report),
        "shippable": len(shippable),
        "blocker_counts": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
    }

    print(f"SSI coverage — {len(rows)} tickers (as of {args.date})\n")
    for key in ("fully_unblocked", "with_gated_comparison", "with_xbrl", "with_transcripts",
                "with_verified_claims", "with_report", "shippable"):
        print(f"  {key:24s} {summary[key]:5d} / {len(rows)}")
    print("\nBlockers (most common first):")
    for blocker, n in summary["blocker_counts"].items():
        print(f"  {n:5d}  {blocker:22s} -> {REMEDIES.get(blocker, '')}")
    if args.top_blockers:
        print()
        for blocker in summary["blocker_counts"]:
            sample = by_blocker[blocker]
            print(f"  {blocker} ({len(sample)}): {', '.join(sample[:25])}"
                  + (" ..." if len(sample) > 25 else ""))

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps({**summary, "rows": rows}, indent=2) + "\n", encoding="utf-8")
        print(f"\nWrote {args.json_out}")

    if args.md_out:
        lines = [
            f"# SSI coverage — {args.date}", "",
            f"**Tickers assessed:** {len(rows)} · fully unblocked **{len(ready)}** · "
            f"with YoY gate **{len(with_gate)}** · with report **{len(with_report)}** · "
            f"shippable **{len(shippable)}**", "",
            "## Blockers", "", "| Count | Blocker | Remedy |", "|---|---|---|",
        ]
        for blocker, n in summary["blocker_counts"].items():
            lines.append(f"| {n} | `{blocker}` | {REMEDIES.get(blocker, '')} |")
        lines += ["", "## Per ticker", "",
                  "| Ticker | Extracts | Gate | XBRL | Transcripts | Verified | Sev-5 | Report gate | Next blocker |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for r in sorted(rows, key=lambda r: (len(r["blockers"]), r["ticker"])):
            lines.append(
                f"| {r['ticker']} | {r['extract_count']} | {r.get('gated_comparisons') if r.get('gated_comparisons') is not None else '—'} | "
                f"{'yes' if r['xbrl'] else 'no'} | {'yes' if r['transcripts'] else 'no'} | "
                f"{r.get('verified_count', '—')} | {r.get('severity5', '—')} | "
                f"{r.get('gate_result', '—')} | {r['blockers'][0] if r['blockers'] else 'none'} |"
            )
        Path(args.md_out).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"Wrote {args.md_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
