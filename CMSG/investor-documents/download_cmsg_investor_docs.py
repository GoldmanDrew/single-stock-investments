#!/usr/bin/env python3
"""Download CMSG primary documents.

CMSG trades on OTCQX and is not SEC-registered (no CIK). Disclosures are filed on
OTC Markets and mirrored on https://consensusmining.com/. OTC file URLs require a
Referer from the issuer site.

Logging: appends to ``CMSG/_download_log.txt`` and refreshes ``DOWNLOAD_MANIFEST.json``.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
LOG = ROOT / "CMSG" / "_download_log.txt"
MANIFEST = Path(__file__).resolve().parent / "DOWNLOAD_MANIFEST.json"
DEST_OTC = Path(__file__).resolve().parent / "otcmarkets"
DEST_IR = Path(__file__).resolve().parent / "ir-consensusmining"

UA = "Mozilla/5.0 MarvinPortfolioDocs/1.0"
REF = "https://consensusmining.com/"
SLEEP_SEC = 0.15

# Canonical primary sources (URLs may need refresh when new annual is posted).
SOURCES: list[tuple[str, Path, str]] = [
    (
        "https://www.otcmarkets.com/file/company/financial-report/525398/content",
        DEST_OTC / "CMSG_OTCQX_Annual_Disclosure_2025-12-31.pdf",
        "OTCQX Annual Disclosure FY2025",
    ),
    (
        "https://consensusmining.com/app/uploads/2026/02/CMSG_2026_Proxy_Statement.pdf",
        DEST_IR / "CMSG_2026_Proxy_Statement.pdf",
        "Proxy Statement 2026",
    ),
    (
        "https://consensusmining.com/app/uploads/2025/09/CMSC_Q2_2025_Shareholder_Update.pdf",
        DEST_IR / "CMSC_Q2_2025_Shareholder_Update.pdf",
        "Q2 2025 shareholder update",
    ),
    (
        "https://consensusmining.com/app/uploads/2025/05/CMSC_Q1_2025_Shareholder_Update.pdf",
        DEST_IR / "CMSC_Q1_2025_Shareholder_Update.pdf",
        "Q1 2025 shareholder update",
    ),
    (
        "https://consensusmining.com/app/uploads/2025/04/67eee478976599a717f855d3_2024_Audited_Financial_Statements_CMSC.pdf",
        DEST_IR / "2024_Audited_Financial_Statements_CMSC.pdf",
        "Audited financials FY2024",
    ),
]


def log(msg: str) -> None:
    line = f"{datetime.now().isoformat()} {msg}"
    print(line)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def fetch(url: str, dest: Path, referer: str | None = REF) -> dict:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        log(f"SKIP exists -> {dest.name}")
        return {"url": url, "local": str(dest), "ok": True, "skipped": True}
    headers = {"User-Agent": UA}
    if referer:
        headers["Referer"] = referer
    req = Request(url, headers=headers)
    try:
        time.sleep(SLEEP_SEC)
        with urlopen(req, timeout=120) as resp:
            data = resp.read()
        dest.write_bytes(data)
        log(f"OK {len(data):,} bytes -> {dest}")
        return {"url": url, "local": str(dest), "ok": True, "bytes": len(data)}
    except Exception as e:
        log(f"FAIL {url} -> {e}")
        return {"url": url, "local": str(dest), "ok": False, "error": str(e)}


def main() -> int:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []
    for url, dest, label in SOURCES:
        manifest.append({"label": label, **fetch(url, dest)})
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    bad = sum(1 for m in manifest if not m.get("ok"))
    log(f"Done CMSG OTC/IR. ok={len(manifest)-bad} fail={bad}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
