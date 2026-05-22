#!/usr/bin/env python3
"""Download SEC filings and IR PDFs for US tickers (config: us_ticker_config.json)."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = Path(__file__).resolve().parent / "us_ticker_config.json"
SEC_UA = "MarvinPortfolioDocs (contact@example.com)"
IR_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MarvinPortfolioDocs/1.0"
SLEEP_SEC = 0.12
MIN_FILING_DATE = "2018-01-01"

FORM_LIMITS = [
    ("10-K", 5),
    ("10-K/A", 3),
    ("10-Q", 14),
    ("20-F", 3),
    ("40-F", 3),
    ("DEF 14A", 4),
    ("PRE 14A", 3),
    ("S-3", 3),
    ("S-3ASR", 3),
    ("424B5", 4),
    ("8-K", 25),
]

Q4_FEEDS = [
    "/feed/FinancialReport.svc/GetFinancialReportList?LanguageId=1&PageSize=-1",
    "/feed/Event.svc/GetEventList?LanguageId=1&PageSize=-1",
    "/feed/PressRelease.svc/GetPressReleaseList?LanguageId=1&PageSize=-1",
]

IR_PAGE_SUFFIXES = [
    "",
    "/financials/default.aspx",
    "/financials/annual-reports/default.aspx",
    "/events-and-presentations/presentations/default.aspx",
    "/news-events/presentations",
    "/news/default.aspx",
    "/home/default.aspx",
]


def log(log_file: Path, msg: str) -> None:
    line = f"{datetime.now().isoformat()} {msg}"
    print(line)
    with log_file.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def download(url: str, dest: Path, ua: str, log_file: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 0:
        log(log_file, f"SKIP exists -> {dest}")
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
    except Exception as e:
        log(log_file, f"FAIL {url} -> {e}")
        return False
    dest.write_bytes(data)
    log(log_file, f"OK {len(data):,} bytes -> {dest}")
    return True


def sec_url(cik_path: str, accession: str, primary: str) -> str:
    nodash = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{cik_path}/{nodash}/{primary}"


def download_8k_exhibits(
    cik_path: str,
    row: dict,
    sec_dir: Path,
    log_file: Path,
    patterns: tuple[str, ...] = ("ex99", "ex-99"),
) -> list[dict]:
    """Download EX-99.x press-release exhibits bundled with 8-K filings."""
    if not row["form"].startswith("8-K"):
        return []
    nodash = row["accession"].replace("-", "")
    index_url = f"https://www.sec.gov/Archives/edgar/data/{cik_path}/{nodash}/index.json"
    req = urllib.request.Request(index_url, headers={"User-Agent": SEC_UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            index = json.load(r)
    except Exception as e:
        log(log_file, f"EXHIBIT INDEX FAIL {row['accession']} -> {e}")
        return []

    out: list[dict] = []
    fd = row["filingDate"].replace("-", "")
    acc = row["accession"].replace("-", "_")
    for item in index.get("directory", {}).get("item", []):
        name = item.get("name", "")
        if not name or name == row["primary"]:
            continue
        lower = name.lower()
        if not any(p in lower for p in patterns):
            continue
        ext = os.path.splitext(name)[1] or ".htm"
        safe = f"8-K_{fd}_exhibit_{name.replace('/', '-').replace(' ', '_')}_acc{acc}{ext}"
        dest = sec_dir / safe
        url = sec_url(cik_path, row["accession"], name)
        time.sleep(SLEEP_SEC)
        ok = download(url, dest, SEC_UA, log_file)
        out.append(
            {
                **row,
                "exhibit": name,
                "url": url,
                "local": str(dest),
                "ok": ok,
            }
        )
    return out


def download_sec(cik: str, sec_dir: Path, log_file: Path, meta: dict | None = None) -> list[dict]:
    meta = meta or {}
    cik_path = str(int(cik))
    cik_padded = f"{int(cik):010d}"
    url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
    req = urllib.request.Request(url, headers={"User-Agent": SEC_UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        j = json.load(r)

    recent = j["filings"]["recent"]
    n = len(recent["form"])
    rows = [
        {
            "form": recent["form"][i],
            "filingDate": recent["filingDate"][i],
            "accession": recent["accessionNumber"][i],
            "primary": recent["primaryDocument"][i],
            "report": recent["reportDate"][i] or "",
        }
        for i in range(n)
    ]

    picked: list[dict] = []
    min_date = meta.get("min_filing_date", MIN_FILING_DATE)
    if meta.get("sec_any_recent"):
        limit = int(meta["sec_any_recent"])
        for row in rows:
            if row["filingDate"] < min_date:
                continue
            picked.append(row)
            if len(picked) >= limit:
                break
    else:
        for form, limit in FORM_LIMITS:
            cnt = 0
            for row in rows:
                if row["form"] != form or row["filingDate"] < min_date:
                    continue
                picked.append(row)
                cnt += 1
                if cnt >= limit:
                    break

    manifest = []
    for row in picked:
        fd = row["filingDate"].replace("-", "")
        rep = (row.get("report") or "").replace("-", "")
        acc = row["accession"].replace("-", "_")
        ext = os.path.splitext(row["primary"])[1] or ".htm"
        safe = f"{row['form'].replace('/', '-')}_{fd}_rpt{rep}_acc{acc}{ext}"
        dest = sec_dir / safe
        filing_url = sec_url(cik_path, row["accession"], row["primary"])
        time.sleep(SLEEP_SEC)
        ok = download(filing_url, dest, SEC_UA, log_file)
        manifest.append({**row, "url": filing_url, "local": str(dest), "ok": ok})
        if meta.get("download_8k_exhibits"):
            manifest.extend(download_8k_exhibits(cik_path, row, sec_dir, log_file))
    return manifest


def walk_json_for_pdfs(obj, pdfs: set[str]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str):
                if v.lower().endswith(".pdf") or "doc_downloads" in v.lower() or "doc_financials" in v.lower():
                    pdfs.add(v)
                for m in re.findall(r"https?://[^\s\"'<>]+\.pdf", v, re.I):
                    pdfs.add(m)
            walk_json_for_pdfs(v, pdfs)
    elif isinstance(obj, list):
        for item in obj:
            walk_json_for_pdfs(item, pdfs)


def normalize_pdf_url(u: str, base: str) -> str | None:
    if not u:
        return None
    u = u.replace("/files/files/", "/files/")
    if u.startswith("//"):
        u = "https:" + u
    if u.startswith("/"):
        u = urllib.parse.urljoin(base, u)
    if not u.lower().startswith("http"):
        return None
    if not u.lower().endswith(".pdf"):
        return None
    return u


def harvest_ir_pdfs(ir_roots: list[str], log_file: Path) -> set[str]:
    pdfs: set[str] = set()
    for root in ir_roots:
        root = root.rstrip("/")
        base_host = root

        for feed in Q4_FEEDS:
            feed_url = root + feed
            try:
                req = urllib.request.Request(feed_url, headers={"User-Agent": IR_UA, "Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=60) as r:
                    walk_json_for_pdfs(json.load(r), pdfs)
            except Exception:
                pass
            time.sleep(SLEEP_SEC)

        for suffix in IR_PAGE_SUFFIXES:
            page = root + suffix if suffix else root
            try:
                req = urllib.request.Request(page, headers={"User-Agent": IR_UA})
                with urllib.request.urlopen(req, timeout=60) as r:
                    html = r.read().decode("utf-8", errors="ignore")
            except Exception:
                continue
            for m in re.findall(r"https?://[^\s\"'<>]+\.pdf", html, re.I):
                if u := normalize_pdf_url(m, base_host):
                    pdfs.add(u)
            for m in re.findall(r'href=(["\'])(.*?)\1', html, re.I):
                if ".pdf" not in m[1].lower():
                    continue
                if u := normalize_pdf_url(m[1], base_host):
                    pdfs.add(u)
            time.sleep(SLEEP_SEC)

    return {u for u in pdfs if u.lower().endswith(".pdf")}


def ir_dest(ir_dir: Path, url: str) -> Path:
    name = re.sub(r"[^\w.\-]", "_", url.rsplit("/", 1)[-1])
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return ir_dir / name


def install_wrapper(ticker: str) -> Path:
    inv = ROOT / ticker / "investor-documents"
    inv.mkdir(parents=True, exist_ok=True)
    for sub in ("sec-edgar", f"ir-{ticker.lower()}", "research-notes"):
        (inv / sub).mkdir(parents=True, exist_ok=True)
    script = inv / f"download_{ticker.lower()}_investor_docs.py"
    if not script.exists():
        script.write_text(
            f'''#!/usr/bin/env python3
"""Download {ticker} investor documents via shared Marvin script."""
import subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
subprocess.check_call([
    sys.executable,
    str(ROOT / "_system" / "scripts" / "download_us_investor_docs.py"),
    "--ticker", "{ticker}",
])
''',
            encoding="utf-8",
        )
    return script


def run_ticker(ticker: str, config: dict) -> None:
    ticker = ticker.upper()
    if ticker not in config:
        raise SystemExit(f"Unknown ticker {ticker} in config")

    meta = config[ticker]
    ticker_root = ROOT / ticker
    inv = ticker_root / "investor-documents"
    sec_dir = inv / "sec-edgar"
    ir_dir = inv / f"ir-{ticker.lower()}"
    log_file = ticker_root / "_download_log.txt"

    install_wrapper(ticker)
    log(log_file, f"Starting download for {ticker}")

    manifest: list[dict] = []
    if meta.get("cik"):
        try:
            manifest = download_sec(str(meta["cik"]), sec_dir, log_file, meta)
            log(log_file, f"SEC filings downloaded: {len(manifest)}")
        except Exception as e:
            log(log_file, f"SEC FAIL -> {e}")

    pdfs = harvest_ir_pdfs(meta.get("ir_roots", []), log_file)
    log(log_file, f"IR PDF URLs found: {len(pdfs)}")
    ir_ok = 0
    for url in sorted(pdfs):
        dest = ir_dest(ir_dir, url)
        time.sleep(SLEEP_SEC)
        if download(url, dest, IR_UA, log_file):
            ir_ok += 1

    man_path = inv / "DOWNLOAD_MANIFEST.json"
    man_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log(log_file, f"Done {ticker}. SEC={len(manifest)} IR={ir_ok}/{len(pdfs)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    args = parser.parse_args()
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    run_ticker(args.ticker, config)


if __name__ == "__main__":
    main()
