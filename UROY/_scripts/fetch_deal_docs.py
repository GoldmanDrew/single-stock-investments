#!/usr/bin/env python3
"""Fetch UROY New URC deal circular + related 6-K exhibits from SEC."""
from __future__ import annotations

import json
import re
import time
import urllib.request
from pathlib import Path

UA = "Marvin Research single-stock-investments contact portfolio@local research bot"
ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "investor-documents" / "sec-edgar"
DEST.mkdir(parents=True, exist_ok=True)
LOG = ROOT / "_download_log.txt"


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def save(name: str, data: bytes) -> Path:
    path = DEST / name
    path.write_bytes(data)
    print(f"OK {name} {len(data):,} bytes")
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} OK {name} {len(data)} bytes\n")
    return path


def main() -> None:
    # Recent filings list
    subs = json.loads(get("https://data.sec.gov/submissions/CIK0001711570.json").decode())
    recent = subs["filings"]["recent"]
    rows = []
    for i, form in enumerate(recent["form"][:40]):
        rows.append(
            {
                "date": recent["filingDate"][i],
                "form": form,
                "accession": recent["accessionNumber"][i],
                "primary": recent["primaryDocument"][i],
            }
        )
        print(f"{rows[-1]['date']} {form} {rows[-1]['accession']} {rows[-1]['primary']}")
    (ROOT / "research" / "sec_recent_filings.json").parent.mkdir(parents=True, exist_ok=True)
    (ROOT / "research" / "sec_recent_filings.json").write_text(
        json.dumps(rows, indent=2) + "\n", encoding="utf-8"
    )

    # June 22 2026 6-K index + exhibits
    acc = "0001493152-26-029646"
    acc_nodash = acc.replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/1711570/{acc_nodash}"
    index_html = get(f"{base}/{acc}-index.htm").decode("utf-8", errors="replace")
    save("6K_20260622_index.htm", index_html.encode("utf-8"))

    # Parse exhibit links from index
    links = re.findall(r'href="([^"]+)"', index_html, flags=re.I)
    docs = sorted({u.split("/")[-1] for u in links if u.lower().endswith((".htm", ".html", ".pdf", ".txt"))})
    print("index docs:", docs)

    wanted = []
    for d in docs:
        low = d.lower()
        if any(x in low for x in ("ex99", "ex-99", "exhibit", "form6", "circular", "proxy")):
            wanted.append(d)
        if low.endswith(".pdf"):
            wanted.append(d)
    wanted = sorted(set(wanted) | {d for d in docs if "99" in d.lower()})
    if not wanted:
        # fallback common names
        wanted = [
            "ex99-1.htm",
            "ex99-1.pdf",
            "ex99_1.htm",
            "exhibit99_1.htm",
            "ex991.htm",
            "ex99-4.htm",
            "ex99-4.pdf",
            "form6-k.htm",
        ]

    for name in wanted:
        out = f"6K_20260622_{name}"
        if (DEST / out).exists() and (DEST / out).stat().st_size > 1000:
            print(f"skip existing {out}")
            continue
        try:
            data = get(f"{base}/{name}")
            # skip SEC block pages
            if b"Undeclared Automated Tool" in data[:2000]:
                print(f"BLOCKED {name}")
                continue
            save(out, data)
            time.sleep(0.35)
        except Exception as exc:
            print(f"FAIL {name}: {exc}")

    # April 16 2026 6-K (deal announcement)
    acc2 = "0001493152-26-017113"
    acc2_nodash = acc2.replace("-", "")
    base2 = f"https://www.sec.gov/Archives/edgar/data/1711570/{acc2_nodash}"
    try:
        idx2 = get(f"{base2}/{acc2}-index.htm").decode("utf-8", errors="replace")
        save("6K_20260416_index.htm", idx2.encode("utf-8"))
        links2 = re.findall(r'href="([^"]+)"', idx2, flags=re.I)
        docs2 = sorted({u.split("/")[-1] for u in links2 if u.lower().endswith((".htm", ".html", ".pdf", ".txt"))})
        print("apr index docs:", docs2)
        for name in docs2:
            out = f"6K_20260416_{name}"
            if (DEST / out).exists() and (DEST / out).stat().st_size > 500:
                continue
            try:
                data = get(f"{base2}/{name}")
                if b"Undeclared Automated Tool" in data[:2000]:
                    print(f"BLOCKED {name}")
                    continue
                save(out, data)
                time.sleep(0.35)
            except Exception as exc:
                print(f"FAIL apr {name}: {exc}")
    except Exception as exc:
        print(f"FAIL april index: {exc}")


if __name__ == "__main__":
    main()
