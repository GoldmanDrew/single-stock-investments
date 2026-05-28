#!/usr/bin/env python3
"""Build portfolio short-scan index from local short_reports/ + registry holdings.

Usage:
  python _system/scripts/short_scan_batch.py
  python _system/scripts/short_scan_batch.py --date 2026-05-28
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Pilot + manual notes until per-ticker web pass
KNOWN: dict[str, tuple[str, str]] = {
    "APLD": ("stale_hit", "Wolfpack / Bear Cave / Friendly Bear Jul 2023 — see short_reports/"),
    "QDEL": ("litigation", "2024 securities class actions; no Tier-1 forensic short"),
    "FRMO": ("no_hit", "No Muddy/Hindenburg; Jan 2026 non-reliance (disclosure, not short)"),
}


def tickers() -> list[str]:
    reg = ROOT / "_system" / "portfolio" / "registry.json"
    if reg.exists():
        data = json.loads(reg.read_text(encoding="utf-8"))
        h = data.get("holdings") or {}
        if isinstance(h, dict):
            return sorted(h.keys())
    return []


def local_short_status(ticker: str) -> str:
    sr = ROOT / ticker / "third-party-analyses" / "short_reports"
    if not sr.is_dir():
        return ""
    md = list(sr.glob("*.md"))
    return f"{len(md)} file(s) in short_reports/" if md else ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()

    out = ROOT / "_system" / "research" / f"short_scan_{args.date}.md"
    lines = [
        f"# Portfolio short activist scan",
        f"",
        f"**Date:** {args.date}  ",
        f"**Agent:** Milly (`short_scan_batch.py`)  ",
        f"**Registry:** `_system/frameworks/short_activist_registry.md`",
        f"",
        f"**Method:** Local `short_reports/` scan + known hits. Tier-1 web search: run per ticker in Milly pass.",
        f"",
        f"## Summary",
        f"",
        f"| Ticker | Status | Local cache | Notes |",
        f"|--------|--------|-------------|-------|",
    ]

    for t in tickers():
        if t in KNOWN:
            status, note = KNOWN[t]
        else:
            local = local_short_status(t)
            status = "no_local_hit" if not local else "local_cache"
            note = local or "Run Milly Tier-1 web scan per registry"
        lines.append(f"| {t} | {status} | {local_short_status(t) or '—'} | {note} |")

    lines.extend(
        [
            "",
            "## Maintenance",
            "",
            "- Re-run: `python _system/scripts/short_scan_batch.py`",
            "- Save hits: `{TICKER}/third-party-analyses/short_reports/{firm}_{date}.md`",
            "- Reconcile in `{TICKER}/research/adversarial_{date}.md`",
            "",
        ]
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {out.relative_to(ROOT)} ({len(tickers())} rows)")


if __name__ == "__main__":
    main()
