#!/usr/bin/env python3
"""Rebuild manifest.csv for _system/reference/investment-wisdom/."""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WISDOM = ROOT / "_system" / "reference" / "investment-wisdom"
OUT = WISDOM / "manifest.csv"

THEMES = {
    "munger": "mental_models",
    "pabrai": "dhando_letters",
    "stahl": "croupier_diversification",
    "horizon-kinetics": "equity_yield_curve",
    "tci": "operating_mechanics",
}


def main() -> None:
    rows: list[dict[str, str | int]] = []
    for sub in sorted(WISDOM.iterdir()):
        if not sub.is_dir() or sub.name.startswith("."):
            continue
        genius = sub.name
        patterns = ("*.pdf",) if genius not in ("horizon-kinetics", "tci") else ("*.pdf", "*.txt")
        for pattern in patterns:
            for doc in sorted(sub.glob(pattern)):
                if doc.name.upper() == "README.MD":
                    continue
                stat = doc.stat()
                rows.append(
                    {
                        "genius": genius,
                        "filename": doc.name,
                        "path": str(doc.relative_to(ROOT)).replace("\\", "/"),
                        "size_bytes": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d"),
                        "theme_bucket": THEMES.get(genius, genius),
                    }
                )

    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["genius", "filename", "path", "size_bytes", "modified", "theme_bucket"],
        )
        w.writeheader()
        w.writerows(rows)

    print(f"Wrote {len(rows)} entries to {OUT}")


if __name__ == "__main__":
    main()
