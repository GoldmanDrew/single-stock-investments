#!/usr/bin/env python3
"""Replace legacy Thesis status footer in deep dives with Classification table."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLASS_PATH = ROOT / "_system" / "portfolio" / "classification.json"


def classification_block(row: dict) -> str:
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


def update_dive(path: Path, row: dict) -> None:
    text = path.read_text(encoding="utf-8")
    text = re.sub(
        r"\n## Classification\s*\n\s*\n\| Field \| Value \|\s*\n\|[-| ]+\|\s*\n(?:\|[^\n]+\|\s*\n)+",
        "\n",
        text,
    )
    text = re.sub(
        r"\n## Thesis status\s*\n\s*\n.+?(?=\n## (\[HUMAN REVIEW\]|Approved|\[PROPOSED))",
        "\n",
        text,
        flags=re.DOTALL,
    )
    block = classification_block(row) + "\n"
    if "## [HUMAN REVIEW]" in text:
        text = text.replace("## [HUMAN REVIEW]", block + "## [HUMAN REVIEW]", 1)
    elif "## Approved" in text:
        text = text.replace("## Approved", block + "## Approved", 1)
    elif "## [PROPOSED" in text:
        text = text.replace("## [PROPOSED", block + "## [PROPOSED", 1)
    else:
        text = text.rstrip() + "\n\n" + block
    path.write_text(text, encoding="utf-8")


def main() -> None:
    data = json.loads(CLASS_PATH.read_text(encoding="utf-8"))
    for ticker, row in sorted(data.items()):
        dives = list((ROOT / ticker / "research").glob("deep_dive_*.md"))
        for dive in dives:
            update_dive(dive, row)
            print(f"Updated {dive.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
