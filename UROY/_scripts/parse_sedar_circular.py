#!/usr/bin/env python3
"""Extract New URC economics from SEDAR circular text."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
text = (ROOT / "research" / "evidence" / "circular_sedar_text.md").read_text(encoding="utf-8", errors="replace")
print("chars", len(text))

# Key section dumps
keys = [
    "Unaudited Pro Forma",
    "PRO FORMA",
    "Adjusted EBITDA",
    "adjusted EBITDA",
    "Enterprise Value",
    "deemed value",
    "US$3.64",
    "625 million",
    "330 million",
    "813 million",
    "74 million",
    "ownership",
    "lock-up",
    "PFIC",
    "shares outstanding",
    "Fully diluted",
    "Interest expense",
    "Long-term debt",
    "Cash and cash equivalents",
    "non-controlling",
    "8% minority",
    "fairness opinion",
    "Paradigm",
    "EV/EBITDA",
    "net debt",
    "Subsequent Financing",
    "uranium inventory",
]


def dump(key: str, n: int = 4, width: int = 500) -> None:
    idxs = [m.start() for m in re.finditer(re.escape(key), text, flags=re.I)]
    print(f"\n### {key} ({len(idxs)} hits)")
    for i, idx in enumerate(idxs[:n]):
        chunk = " ".join(text[max(0, idx - 100) : idx + width].split())
        print(f"[{i}] {chunk}\n")


for k in keys:
    dump(k)

# Pull numeric tables around EBITDA
out = {}
for label, pat in [
    ("ebitda_lines", r".{0,40}(?:Adjusted )?EBITDA.{0,200}"),
    ("debt_lines", r".{0,40}(?:long[- ]term debt|total debt|net debt).{0,200}"),
    ("share_lines", r".{0,40}(?:shares outstanding|New URC Shares|pro forma shares).{0,200}"),
    ("multiple_lines", r".{0,40}(?:EV/EBITDA|x EBITDA|times EBITDA).{0,200}"),
]:
    rows = []
    for m in re.finditer(pat, text, flags=re.I):
        s = " ".join(m.group(0).split())
        if s not in rows:
            rows.append(s[:350])
        if len(rows) >= 30:
            break
    out[label] = rows

(ROOT / "research" / "evidence" / "circular_key_lines.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
print("\nwrote circular_key_lines.json")
for k, rows in out.items():
    print("\n==", k)
    for r in rows[:15]:
        print("-", r)
