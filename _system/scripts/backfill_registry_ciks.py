#!/usr/bin/env python3
"""Backfill missing download.cik values in registry.json from the SEC ticker-CIK map.

Recycled ticker symbols are a known identity trap: a symbol can map to a
DIFFERENT company in the SEC file. So a CIK is applied ONLY when the SEC
company title confidently matches the registry company name; everything else
is written to a held-for-review list.

  python3 _system/scripts/backfill_registry_ciks.py            # dry-run (default)
  python3 _system/scripts/backfill_registry_ciks.py --apply    # snapshot registry, then write

Writes (on --apply):
  _system/portfolio/registry.json                      (cik added to confident matches)
  _system/data/registry_backup_{date}.json             (pre-apply snapshot)
Always writes:
  _system/data/cik_backfill_review_{date}.json         (held-for-review rows)
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from portfolio_registry import REGISTRY_PATH, load_registry, save_registry  # noqa: E402

SEC_CIK_MAP_PATH = ROOT / "_system" / "reference" / "market-data" / "fundamentals" / "_sec_ticker_cik_map.json"
COMPANY_TICKERS_CACHE = ROOT / "_system" / "data" / "sec_company_tickers_cache.json"
COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_UA = "MarvinPortfolioDocs (contact@example.com)"
DATA_DIR = ROOT / "_system" / "data"

# Corporate suffixes stripped before comparison. Conservative: substantive words
# like "group", "holdings", "trust" are kept.
SUFFIX_WORDS = {
    "inc", "incorporated", "corp", "corporation", "co", "company", "ltd",
    "limited", "plc", "lp", "llp", "llc", "sa", "nv", "ag", "se", "ab",
    "the", "cos", "companies",
}
CLASS_RE = re.compile(r"\bclass\s+[a-c]\b(\s+common\s+(stock|shares))?", re.IGNORECASE)
COMMON_STOCK_RE = re.compile(r"\b(common|ordinary)\s+(stock|shares)\b", re.IGNORECASE)


def ascii_safe(s: str) -> str:
    """Windows console is cp1252; console output must stay ASCII."""
    return s.encode("ascii", "replace").decode("ascii")


def normalize_name(name: str) -> str:
    s = name.lower()
    s = s.replace("&", " and ")
    s = s.replace("'", "")
    # SEC titles carry state-of-incorporation tags like "/DE/", "/TX", "/NEW/"
    s = re.sub(r"/[a-z ]*/?", " ", s)
    s = CLASS_RE.sub(" ", s)
    s = COMMON_STOCK_RE.sub(" ", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    tokens = [t for t in s.split() if t not in SUFFIX_WORDS]
    return " ".join(tokens)


def confident_match(registry_name: str, sec_title: str) -> bool:
    a = normalize_name(registry_name)
    b = normalize_name(sec_title)
    if not a or not b:
        return False
    if a == b:
        return True
    # Allow one name to be a word-boundary prefix of the other (e.g.
    # "otc markets" vs "otc markets group"), never a mid-word match.
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if len(shorter) >= 6 and longer.startswith(shorter + " "):
        return True
    return False


def load_sec_map() -> dict[str, str]:
    if not SEC_CIK_MAP_PATH.exists():
        raise SystemExit(f"Missing SEC map: {SEC_CIK_MAP_PATH}")
    return json.loads(SEC_CIK_MAP_PATH.read_text(encoding="utf-8"))


def load_company_titles() -> dict[str, dict]:
    """Return ticker -> {cik, title} from SEC company_tickers.json (cached)."""
    if COMPANY_TICKERS_CACHE.exists():
        payload = json.loads(COMPANY_TICKERS_CACHE.read_text(encoding="utf-8"))
    else:
        req = urllib.request.Request(COMPANY_TICKERS_URL, headers={"User-Agent": SEC_UA})
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        COMPANY_TICKERS_CACHE.parent.mkdir(parents=True, exist_ok=True)
        COMPANY_TICKERS_CACHE.write_text(json.dumps(payload), encoding="utf-8")
    out: dict[str, dict] = {}
    for row in payload.values():
        if not isinstance(row, dict):
            continue
        t = str(row.get("ticker") or "").upper()
        if t and row.get("cik_str"):
            out[t] = {"cik": str(int(row["cik_str"])), "title": str(row.get("title") or "")}
    return out


def sec_lookup(ticker: str, table: dict) -> object | None:
    return table.get(ticker.upper()) or table.get(ticker.upper().replace(".", "-"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write CIKs to registry.json (default: dry-run)")
    args = parser.parse_args()

    today = date.today().isoformat()
    registry = load_registry()
    holdings = registry.get("holdings") or {}
    sec_map = load_sec_map()
    titles = load_company_titles()

    applied: list[dict] = []
    review: list[dict] = []
    unresolved = 0

    for ticker, holding in sorted(holdings.items()):
        dl = holding.get("download") or {}
        if dl.get("type") != "us_shared" or dl.get("cik"):
            continue
        mapped = sec_lookup(ticker, sec_map)
        if not mapped:
            unresolved += 1
            continue
        cik = str(int(str(mapped).lstrip("0") or "0"))
        registry_name = str(holding.get("company") or "")
        title_row = sec_lookup(ticker, titles)
        sec_title = title_row["title"] if isinstance(title_row, dict) else ""
        title_cik = title_row["cik"] if isinstance(title_row, dict) else None
        row = {
            "ticker": ticker,
            "registry_company": registry_name,
            "sec_title": sec_title,
            "cik": cik,
        }
        if title_cik is not None and title_cik != cik:
            row["reason"] = f"cik mismatch: map={cik} company_tickers={title_cik}"
            review.append(row)
            continue
        if not sec_title:
            row["reason"] = "no SEC title available for ticker"
            review.append(row)
            continue
        if confident_match(registry_name, sec_title):
            applied.append(row)
        else:
            row["reason"] = "name mismatch"
            review.append(row)

    review_path = DATA_DIR / f"cik_backfill_review_{today}.json"
    review_path.parent.mkdir(parents=True, exist_ok=True)
    review_path.write_text(json.dumps(review, indent=2) + "\n", encoding="utf-8")

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"[{mode}] confident matches: {len(applied)}")
    print(f"[{mode}] held for review:   {len(review)} -> {review_path.relative_to(ROOT)}")
    print(f"[{mode}] not in SEC map:    {unresolved}")
    for row in applied:
        print(ascii_safe(f"  MATCH {row['ticker']}: cik={row['cik']} '{row['registry_company']}' == '{row['sec_title']}'"))
    for row in review:
        print(ascii_safe(f"  HOLD  {row['ticker']}: {row['reason']} '{row['registry_company']}' vs '{row['sec_title']}'"))

    if not args.apply:
        print("Dry-run only. Re-run with --apply to write registry.json.")
        return
    if applied:
        backup_path = DATA_DIR / f"registry_backup_{today}.json"
        shutil.copy2(REGISTRY_PATH, backup_path)
        print(f"Registry snapshot -> {backup_path.relative_to(ROOT)}")
        for row in applied:
            holdings[row["ticker"]]["download"]["cik"] = row["cik"]
        save_registry(registry)
        print(f"Applied {len(applied)} CIK(s) to {REGISTRY_PATH.relative_to(ROOT)}")
        print("Remember to run sync_portfolio_from_registry.py to regenerate us_ticker_config.json.")
    else:
        print("Nothing to apply.")


if __name__ == "__main__":
    main()
