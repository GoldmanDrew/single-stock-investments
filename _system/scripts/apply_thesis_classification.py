#!/usr/bin/env python3
"""Apply classification.json to {TICKER}/research/thesis.md files."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLASS_PATH = ROOT / "_system" / "portfolio" / "classification.json"
DATE = "2026-05-21"


def classification_table(row: dict) -> str:
    cycle = row.get("cycle", "—")
    implied_irr = row.get("implied_irr", "pending")
    irr_method = row.get("irr_method", "pending")
    lawrence_bucket = row.get("lawrence_bucket", "—")
    return f"""## Classification

| Field | Value |
|-------|-------|
| **Archetype** (Stahl) | {row['archetype']} |
| **Moat** (Munger) | {row['moat']} |
| **Dhando** (Pabrai) | {row['dhando']} |
| **Stance** | {row['stance']} |
| **Cycle** | {cycle} |
| **Implied 10yr IRR** (Lawrence) | {implied_irr} |
| **IRR method** | {irr_method} |
| **Lawrence bucket** | {lawrence_bucket} |
"""


def strip_old_status(text: str) -> str:
    text = re.sub(r"\*\*Status:\*\*[^\n]*\n", "", text)
    text = re.sub(
        r"\n## Thesis status\s*\n\s*\n.+?(?=\n## |\Z)",
        "\n",
        text,
        flags=re.DOTALL,
    )
    text = re.sub(
        r"\n## Classification\s*\n\s*\n\| Field \| Value \|\s*\n\|[-| ]+\|\s*\n(?:\|[^\n]+\|\s*\n)+",
        "\n",
        text,
    )
    return text


def apply_ticker(ticker: str, row: dict) -> bool:
    thesis_path = ROOT / ticker / "research" / "thesis.md"
    if not thesis_path.exists():
        return False
    text = thesis_path.read_text(encoding="utf-8")
    text = strip_old_status(text)

    title_m = re.match(r"(# .+?\n\n)", text)
    if not title_m:
        return False
    rest = text[len(title_m.group(1)) :]

    rest = re.sub(r"\*\*Last updated:\*\*[^\n]*\n", "", rest)
    rest = re.sub(r"\*\*Archetype lenses:\*\*[^\n]*\n", "", rest)

    new_header = (
        f"{title_m.group(1)}"
        f"**Last updated:** {DATE}\n\n"
        f"{classification_table(row)}\n"
    )
    thesis_path.write_text(new_header + rest.lstrip(), encoding="utf-8")
    return True


def main() -> None:
    data = json.loads(CLASS_PATH.read_text(encoding="utf-8"))
    ok = 0
    for ticker, row in sorted(data.items()):
        if apply_ticker(ticker, row):
            ok += 1
            print(f"Updated {ticker}/research/thesis.md")
        else:
            print(f"SKIP {ticker} (no thesis.md)")
    print(f"Done: {ok}/{len(data)} tickers")


if __name__ == "__main__":
    main()
