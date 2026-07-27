#!/usr/bin/env python3
from __future__ import annotations

import time
import urllib.request
from pathlib import Path

UA = "Marvin Research single-stock-investments contact portfolio@local research bot"
DEST = Path(__file__).resolve().parents[1] / "investor-documents" / "sec-edgar"
DEST.mkdir(parents=True, exist_ok=True)

FILINGS = [
    ("0001493152-26-033941", "20260720"),  # shareholder approval
    ("0001493152-26-030304", "20260626"),
    ("0001493152-26-019420", "20260429"),  # may have MD&A / financials
]


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def main() -> None:
    for accession, tag in FILINGS:
        nodash = accession.replace("-", "")
        base = f"https://www.sec.gov/Archives/edgar/data/1711570/{nodash}"
        index_name = f"{accession}-index.htm"
        try:
            idx = get(f"{base}/{index_name}")
            (DEST / f"6K_{tag}_index.htm").write_bytes(idx)
            print(f"OK index {tag} {len(idx)}")
        except Exception as exc:
            print(f"FAIL index {tag}: {exc}")
            continue
        import re

        html = idx.decode("utf-8", errors="replace")
        docs = sorted(
            {
                u.split("/")[-1]
                for u in re.findall(r'href="([^"]+)"', html, flags=re.I)
                if u.lower().endswith((".htm", ".html", ".pdf", ".txt"))
            }
        )
        print(f"  docs: {docs}")
        for name in docs:
            if name in {"index.htm", "companysearch.html"}:
                continue
            out = DEST / f"6K_{tag}_{name}"
            if out.exists() and out.stat().st_size > 500:
                print(f"  skip {out.name}")
                continue
            try:
                data = get(f"{base}/{name}")
                if b"Undeclared Automated" in data[:1500]:
                    print(f"  BLOCKED {name}")
                    continue
                out.write_bytes(data)
                print(f"  OK {out.name} {len(data)}")
                time.sleep(0.4)
            except Exception as exc:
                print(f"  FAIL {name}: {exc}")


if __name__ == "__main__":
    main()
