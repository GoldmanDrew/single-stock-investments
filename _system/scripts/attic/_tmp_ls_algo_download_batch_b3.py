#!/usr/bin/env python3
"""LS-algo download batch 3: tickers with registry CIK but empty sec-edgar."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "_system" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from portfolio_registry import load_registry  # noqa: E402

PY = sys.executable
REPORT = ROOT / "_system" / "data" / "ls_algo_download_batch_2026-07-28_b6.json"
BATCH_SIZE = 80
# Known empty/non-issuer + ETF / product wrappers (skip SEC equity pack)
SKIP = {
    "QNT", "SKHY", "SPY", "DIA", "GLD", "IBIT", "ETHA", "ARKK", "ASHR",
    "SOXX", "SPHB", "STLR", "TLT", "URA", "XBI", "XLE", "XLF", "XLK", "XOP",
    "QQQ", "SLV", "SVIX", "USO", "SPCX", "XRPZ", "SOEZ", "THYP", "XNDU",
    "CHNL", "COPX", "CRDD", "DRNZ", "EWJ", "EWW", "EWY", "FXI", "GDX",
    "GDXJ", "IWM", "KWEB",
}


def sec_file_count(ticker: str) -> int:
    sec = ROOT / ticker / "investor-documents" / "sec-edgar"
    if not sec.is_dir():
        return 0
    return sum(1 for p in sec.rglob("*") if p.is_file())


def select_batch(limit: int) -> list[str]:
    registry = load_registry()
    need: list[str] = []
    for ticker, holding in sorted((registry.get("holdings") or {}).items()):
        sleeve = holding.get("investment_sleeve") or (holding.get("classification") or {}).get(
            "investment_sleeve"
        )
        if sleeve != "ls_algo_underlying":
            continue
        if ticker in SKIP:
            continue
        cik = (holding.get("download") or {}).get("cik")
        if not cik:
            continue
        if sec_file_count(ticker) == 0:
            need.append(ticker)
        if len(need) >= limit:
            break
    return need


def run(cmd: list[str], label: str, timeout: int = 900) -> int:
    print(f"\n=== {label} ===", flush=True)
    try:
        return subprocess.run(cmd, cwd=ROOT, timeout=timeout).returncode
    except subprocess.TimeoutExpired:
        print(f"! timeout {label}", flush=True)
        return 124


def main() -> int:
    tickers = select_batch(BATCH_SIZE)
    started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"Batch size {len(tickers)}: {', '.join(tickers)}", flush=True)
    rows: list[dict] = []
    for ticker in tickers:
        t0 = time.time()
        before = sec_file_count(ticker)
        row = {
            "ticker": ticker,
            "sec_before": before,
            "download_rc": None,
            "index_rc": None,
            "evidence_rc": None,
            "automation_rc": None,
            "sec_after": None,
            "elapsed_sec": None,
        }
        row["download_rc"] = run(
            [PY, str(SCRIPTS / "download_us_investor_docs.py"), "--ticker", ticker],
            f"download {ticker}",
        )
        row["index_rc"] = run(
            [PY, str(SCRIPTS / "build_folder_indexes.py"), "--ticker", ticker],
            f"index {ticker}",
            timeout=300,
        )
        row["evidence_rc"] = run(
            [PY, str(SCRIPTS / "build_filing_evidence.py"), ticker],
            f"filing evidence {ticker}",
            timeout=600,
        )
        row["automation_rc"] = run(
            [
                PY,
                str(SCRIPTS / "automate_valuation_readiness.py"),
                "--tickers",
                ticker,
                "--date",
                "2026-07-28",
                "--full-rerun",
            ],
            f"valuation readiness {ticker}",
            timeout=600,
        )
        row["sec_after"] = sec_file_count(ticker)
        row["elapsed_sec"] = round(time.time() - t0, 1)
        rows.append(row)
        print(
            f"DONE {ticker}: sec {row['sec_before']}->{row['sec_after']} "
            f"rc=({row['download_rc']},{row['index_rc']},{row['evidence_rc']},{row['automation_rc']}) "
            f"{row['elapsed_sec']}s",
            flush=True,
        )

    subprocess.run([PY, str(SCRIPTS / "build_evidence_recovery_queue.py")], cwd=ROOT, check=False)
    # Also index+evidence COST from smoke test if present
    if sec_file_count("COST") > 0:
        run([PY, str(SCRIPTS / "build_folder_indexes.py"), "--ticker", "COST"], "index COST", 300)
        run([PY, str(SCRIPTS / "build_filing_evidence.py"), "COST"], "filing evidence COST", 600)

    got = [r for r in rows if (r.get("sec_after") or 0) > 0]
    empty = [r for r in rows if (r.get("sec_after") or 0) == 0]
    report = {
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "batch": tickers,
        "summary": {
            "attempted": len(rows),
            "downloaded_with_files": len(got),
            "failed_or_empty": len(empty),
            "empty_tickers": [r["ticker"] for r in empty],
        },
        "rows": rows,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("\n=== BATCH SUMMARY ===", flush=True)
    print(json.dumps(report["summary"], indent=2), flush=True)
    print(f"Report: {REPORT}", flush=True)
    return 1 if empty else 0


if __name__ == "__main__":
    raise SystemExit(main())
