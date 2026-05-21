"""
Download QuidelOrtho (QDEL, CIK 0001906324) SEC filings and IR PDFs.
SEC requires a descriptive User-Agent; replace CONTACT below if you use this script regularly.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from datetime import datetime

SEC_UA = "QDELInvestorDocs (contact@example.com)"
IR_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) QDELInvestorDocs/1.0"
COMPANY_EDGAR_CIK_PATH = "1906324"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK0001906324.json"
SLEEP_SEC = 0.12
MIN_FILING_DATE = "2020-01-01"

ROOT = os.path.dirname(os.path.abspath(__file__))
TICKER_ROOT = os.path.dirname(ROOT)
SEC_DIR = os.path.join(ROOT, "sec-edgar")
IR_DIR = os.path.join(ROOT, "ir-quidelortho")
LOG_FILE = os.path.join(TICKER_ROOT, "_download_log.txt")

FORM_LIMITS = [
    ("10-K", 5),
    ("10-K/A", 3),
    ("10-Q", 14),
    ("DEF 14A", 4),
    ("PRE 14A", 3),
    ("S-3", 3),
    ("S-3ASR", 3),
    ("424B5", 4),
    ("8-K", 20),
]


def log(msg: str) -> None:
    line = f"{datetime.now().isoformat()} {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def sec_url(accession: str, primary: str) -> str:
    nodash = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{COMPANY_EDGAR_CIK_PATH}/{nodash}/{primary}"


def download(url: str, dest: str, ua: str) -> bool:
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        log(f"SKIP exists -> {dest}")
        return True
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
    except Exception as e:
        log(f"FAIL {url} -> {e}")
        return False
    with open(dest, "wb") as f:
        f.write(data)
    log(f"OK {len(data):,} bytes -> {dest}")
    return True


def fetch_ir_pdfs_from_q4_feeds() -> set[str]:
    """Harvest IR PDF URLs from QuidelOrtho Q4 Investor Relations feeds."""
    import urllib.parse

    root = "https://ir.quidelortho.com"
    feeds = [
        "/feed/FinancialReport.svc/GetFinancialReportList?LanguageId=1&PageSize=-1",
        "/feed/Event.svc/GetEventList?LanguageId=1&PageSize=-1",
    ]
    pdfs: set[str] = set()

    def add_url(u: str) -> None:
        if not u:
            return
        if u.startswith("/"):
            u = urllib.parse.urljoin(root, u)
        if u.lower().endswith(".pdf"):
            pdfs.add(u.replace("/files/files/", "/files/"))

    def walk(obj) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, str) and any(x in k.lower() for x in ("path", "url", "link", "document", "file")):
                    add_url(v)
                walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)
        elif isinstance(obj, str):
            for m in re.findall(r"https?://[^\s\"'<>]+\.pdf", obj, re.I):
                add_url(m)

    for feed in feeds:
        url = root + feed
        req = urllib.request.Request(url, headers={"User-Agent": IR_UA, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                walk(json.load(r))
        except Exception as e:
            log(f"FAIL Q4 feed {feed} -> {e}")
        time.sleep(SLEEP_SEC)
    return pdfs


def ir_dest_path(url: str) -> str:
    name = re.sub(r"[^\w.\-]", "_", url.rsplit("/", 1)[-1])
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return os.path.join(IR_DIR, name)


def main() -> None:
    os.makedirs(SEC_DIR, exist_ok=True)
    os.makedirs(IR_DIR, exist_ok=True)
    log("Starting QDEL download")

    req = urllib.request.Request(SUBMISSIONS_URL, headers={"User-Agent": SEC_UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        j = json.load(r)

    recent = j["filings"]["recent"]
    n = len(recent["form"])
    rows = []
    for i in range(n):
        rows.append(
            {
                "form": recent["form"][i],
                "filingDate": recent["filingDate"][i],
                "accession": recent["accessionNumber"][i],
                "primary": recent["primaryDocument"][i],
                "report": recent["reportDate"][i] or "",
            }
        )

    picked: list[dict] = []
    for form, limit in FORM_LIMITS:
        cnt = 0
        for row in rows:
            if row["form"] != form:
                continue
            if row["filingDate"] < MIN_FILING_DATE:
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
        dest = os.path.join(SEC_DIR, safe)
        url = sec_url(row["accession"], row["primary"])
        time.sleep(SLEEP_SEC)
        ok = download(url, dest, SEC_UA)
        manifest.append({**row, "url": url, "local": dest, "ok": ok})

    pdfs = fetch_ir_pdfs_from_q4_feeds()
    ir_ok = 0
    for u in sorted(pdfs):
        dest = ir_dest_path(u)
        time.sleep(SLEEP_SEC)
        if download(u, dest, IR_UA):
            ir_ok += 1

    man_path = os.path.join(ROOT, "DOWNLOAD_MANIFEST.json")
    with open(man_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    log(f"Wrote manifest: {man_path}")
    log(f"Done. SEC filings={len(manifest)} IR PDFs={len(pdfs)} IR downloaded/skipped={ir_ok}")


if __name__ == "__main__":
    main()
