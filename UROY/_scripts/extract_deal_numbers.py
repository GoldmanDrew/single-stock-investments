#!/usr/bin/env python3
"""Mine deal filings for New URC pro forma economics."""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEC = ROOT / "investor-documents" / "sec-edgar"
OUT = ROOT / "research" / "evidence"


def to_text(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() == ".txt":
        return raw
    text = re.sub(r"<script.*?</script>", " ", raw, flags=re.I | re.S)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"[ \t]+", " ", text)


def snippets(text: str, patterns: list[str], limit: int = 40) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for pat in patterns:
        for m in re.finditer(pat, text, flags=re.I):
            s = " ".join(m.group(0).split())
            if s in seen:
                continue
            seen.add(s)
            found.append(s[:300])
            if len(found) >= limit:
                return found
    return found


PATTERNS = [
    r".{0,60}adjusted EBITDA.{0,140}",
    r".{0,60}EBITDA.{0,120}",
    r".{0,50}pro forma.{0,140}",
    r".{0,40}US\$\s?[0-9,\.]+\s*(?:million|billion).{0,100}",
    r".{0,50}\$\s?[0-9,\.]+\s*(?:million|billion).{0,100}",
    r".{0,50}shares outstanding.{0,120}",
    r".{0,40}deemed value.{0,100}",
    r".{0,40}Total debt.{0,120}",
    r".{0,40}net debt.{0,100}",
    r".{0,40}cash and cash equivalents.{0,100}",
    r".{0,50}ownership.{0,100}",
    r".{0,40}lock-?up.{0,120}",
    r".{0,40}PFIC.{0,100}",
    r".{0,50}interest coverage.{0,100}",
    r".{0,40}EV/EBITDA.{0,100}",
    r".{0,50}soda ash.{0,100}",
    r".{0,40}625\s*million.{0,80}",
    r".{0,40}330\s*million.{0,80}",
    r".{0,40}813\s*million.{0,80}",
    r".{0,40}3\.64.{0,80}",
    r".{0,40}74\s*million.{0,80}",
    r".{0,50}non-controlling.{0,100}",
    r".{0,40}92%.{0,80}",
]


def main() -> None:
    targets = [
        SEC / "6K_20260416_ex99-1.htm",
        SEC / "6K_20260429_ex99-1.htm",
        SEC / "6K_20260429_0001493152-26-019420.txt",
        SEC / "6K_20260626_ex99-1.htm",
        SEC / "6K_20260720_ex99-1.htm",
        SEC / "6K_20260429_ex99-2.htm",
        SEC / "6K_20260429_ex99-10.htm",
        SEC / "6K_20260429_ex99-3.htm",
    ]
    report: dict = {}
    for path in targets:
        if not path.exists():
            continue
        print(f"=== {path.name} size={path.stat().st_size} ===")
        text = to_text(path)
        # save cleaned text for large useful docs
        if path.stat().st_size < 2_500_000:
            (OUT / f"_{path.stem}_text.txt").write_text(text, encoding="utf-8")
        snips = snippets(text, PATTERNS, limit=50)
        report[path.name] = snips
        for s in snips[:25]:
            print("-", s)
        print()

    # Also search the giant txt for specific tables
    giant = SEC / "6K_20260429_0001493152-26-019420.txt"
    if giant.exists():
        text = giant.read_text(encoding="utf-8", errors="replace")
        keys = [
            "UNAUDITED PRO FORMA",
            "Pro Forma Combined",
            "Adjusted EBITDA",
            "Sweetwater",
            "Interest expense",
            "Cash and cash",
            "Long-term debt",
            "shares of common stock",
            "New URC",
        ]
        hits = {}
        for k in keys:
            idxs = [m.start() for m in re.finditer(re.escape(k), text, flags=re.I)]
            hits[k] = len(idxs)
            for i, idx in enumerate(idxs[:3]):
                chunk = " ".join(text[max(0, idx - 80) : idx + 400].split())
                print(f"GIANT[{k}#{i}]", chunk[:350])
                print()
        report["_giant_key_counts"] = hits

    (OUT / "deal_number_extract.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("wrote deal_number_extract.json")


if __name__ == "__main__":
    main()
