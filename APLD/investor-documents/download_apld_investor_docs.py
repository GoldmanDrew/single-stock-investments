"""
Download Applied Digital (APLD, CIK 0001144879) SEC filings and IR PDFs.
SEC requires a descriptive User-Agent; replace CONTACT below if you use this script regularly.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request

SEC_UA = "APLDInvestorDocs (contact@example.com)"  # SEC fair-access: identify your traffic
IR_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) APLDInvestorDocs/1.0"
COMPANY_EDGAR_CIK_PATH = "1144879"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK0001144879.json"
SLEEP_SEC = 0.12
# Ignore very old filings that can appear when taking “last N” from the full history.
MIN_FILING_DATE = "2020-01-01"

ROOT = os.path.dirname(os.path.abspath(__file__))
SEC_DIR = os.path.join(ROOT, "sec-edgar")
IR_DIR = os.path.join(ROOT, "ir-applieddigital")

# (form, max_count) — most recent first in SEC JSON
FORM_LIMITS = [
    ("10-K", 5),
    ("10-K/A", 3),
    ("10-Q", 14),
    ("DEF 14A", 4),
    ("PRE 14A", 3),
    ("S-3", 3),
    ("S-3ASR", 3),
    ("424B5", 4),
    ("S-1", 2),
    ("S-1/A", 2),
    ("8-K", 15),
]


def sec_url(accession: str, primary: str) -> str:
    nodash = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{COMPANY_EDGAR_CIK_PATH}/{nodash}/{primary}"


def download(url: str, dest: str, ua: str) -> bool:
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
    except Exception as e:
        print(f"FAIL {url}\n  -> {e}")
        return False
    with open(dest, "wb") as f:
        f.write(data)
    print(f"OK {len(data):,} bytes -> {dest}")
    return True


def main() -> None:
    os.makedirs(SEC_DIR, exist_ok=True)
    os.makedirs(IR_DIR, exist_ok=True)

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

    # IR: investor deck(s) linked from presentations page
    pres_url = "https://ir.applieddigital.com/news-events/presentations"
    req = urllib.request.Request(pres_url, headers={"User-Agent": IR_UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        html = r.read().decode("utf-8", errors="ignore")

    pdfs = set(re.findall(r"https://ir\.applieddigital\.com/_assets/[^\"']+\.pdf", html))

    for u in sorted(pdfs):
        name = u.rsplit("/", 1)[-1]
        dest = os.path.join(IR_DIR, name)
        time.sleep(SLEEP_SEC)
        download(u, dest, IR_UA)

    man_path = os.path.join(ROOT, "DOWNLOAD_MANIFEST.json")
    with open(man_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"Wrote manifest: {man_path}")


if __name__ == "__main__":
    main()
