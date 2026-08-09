#!/usr/bin/env python3
"""Re-register LS-algo orphan folders + scaffold ETF stubs; tag sleeve."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "_system" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from portfolio_registry import load_registry, save_registry  # noqa: E402

PY = sys.executable
GAP = ROOT / "_system" / "data" / "ls_algo_underlying_gap.json"
SLEEVE = "ls_algo_underlying"
CIK_MAP = json.loads(
    (ROOT / "_system" / "reference" / "market-data" / "fundamentals" / "_sec_ticker_cik_map.json").read_text(
        encoding="utf-8"
    )
)
ETF_SKIP = {
    "ARKK", "ASHR", "CHNL", "COPX", "CRDD", "DRNZ", "EWJ", "EWW", "EWY", "FXI",
    "GDX", "GDXJ", "IWM", "KWEB", "DIA", "GLD", "IBIT", "ETHA", "SPY", "QNT",
    "SKHY", "SOXX", "SPHB", "STLR", "TLT", "URA", "XBI", "XLE", "XLF", "XLK",
    "XOP", "QQQ", "SLV", "SVIX", "USO", "SPCX", "XRPZ",
}


def tag_sleeve(ticker: str) -> None:
    registry = load_registry()
    holding = (registry.get("holdings") or {}).get(ticker)
    if holding is None:
        return
    classification = holding.setdefault("classification", {})
    classification["investment_sleeve"] = SLEEVE
    holding["investment_sleeve"] = SLEEVE
    dl = holding.setdefault("download", {})
    if not dl.get("cik"):
        cik = CIK_MAP.get(ticker.upper()) or CIK_MAP.get(ticker.upper().replace(".", "-"))
        if cik:
            dl["cik"] = str(cik).zfill(10)
            dl.setdefault("type", "us_shared")
    save_registry(registry)


def onboard(ticker: str, company: str, force: bool) -> int:
    cmd = [
        PY,
        str(SCRIPTS / "onboard_ticker.py"),
        "--ticker",
        ticker,
        "--company",
        company or ticker,
        "--market",
        "US",
        "--skip-download",
        "--skip-indexes",
        "--skip-dashboard",
        "--no-deep-dive",
    ]
    if force:
        cmd.append("--force")
    cik = CIK_MAP.get(ticker.upper()) or CIK_MAP.get(ticker.upper().replace(".", "-"))
    if cik and ticker not in ETF_SKIP:
        cmd.extend(["--cik", str(cik).zfill(10)])
    print(f"\n=== onboard {ticker} force={force} ===", flush=True)
    return subprocess.run(cmd, cwd=ROOT).returncode


def main() -> int:
    gap = json.loads(GAP.read_text(encoding="utf-8"))
    reg = load_registry()
    known = set(reg.get("holdings") or {}) | set(reg.get("watchlist") or {})
    pending = [c for c in gap.get("candidates") or [] if c.get("status") == "pending_onboard"]
    orphans = [c for c in pending if (ROOT / c["ticker"]).is_dir() and c["ticker"] not in known]
    missing = [c for c in pending if not (ROOT / c["ticker"]).is_dir()]

    ok: list[str] = []
    failed: list[tuple[str, int]] = []
    for row in orphans + missing:
        ticker = row["ticker"]
        force = (ROOT / ticker).is_dir()
        code = onboard(ticker, row.get("company") or ticker, force=force)
        if code == 0:
            tag_sleeve(ticker)
            ok.append(ticker)
        else:
            failed.append((ticker, code))

    subprocess.run([PY, str(SCRIPTS / "sync_portfolio_from_registry.py")], cwd=ROOT, check=False)
    subprocess.run([PY, str(SCRIPTS / "darwin" / "build_ls_algo_underlying_gap.py")], cwd=ROOT, check=False)
    print("\n=== REGISTER SUMMARY ===", flush=True)
    print(f"ok={len(ok)} failed={failed}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
