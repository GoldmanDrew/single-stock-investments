#!/usr/bin/env python3
"""Emit a compact per-ticker thesis_card.json for token-diet agent context.

The card carries the thesis one-liner, base IRR, key assumptions, open
questions, last-verified dates, and top evidence citations. Agents read the
card plus the latest filing digest instead of the full deep dive, which cuts
per-run context sharply; the deep dive remains the human-readable artifact.

Usage:
  python _system/scripts/build_thesis_card.py ICE
  python _system/scripts/build_thesis_card.py --all
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

MAX_ASSUMPTIONS = 8
MAX_OPEN_QUESTIONS = 6
MAX_CITATIONS = 5
DIVE_RE = re.compile(r"^deep_dive_(\d{4}-\d{2}-\d{2})\.md$")
DIGEST_RE = re.compile(r"^filing_digest_(\d{4}-\d{2}-\d{2})\.md$")


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}


def latest_dated(directory: Path, pattern: re.Pattern) -> tuple[str, Path] | None:
    best: tuple[str, Path] | None = None
    if not directory.is_dir():
        return None
    for path in directory.iterdir():
        match = pattern.match(path.name)
        if match and (best is None or match.group(1) > best[0]):
            best = (match.group(1), path)
    return best


def section_text(markdown: str, heading: str) -> str:
    """Return the body of a heading up to the next heading of same-or-higher level."""
    lines = markdown.splitlines()
    level = heading.split(" ", 1)[0].count("#")
    title = heading.split(" ", 1)[1].strip().lower()
    body: list[str] = []
    capture = False
    for line in lines:
        match = re.match(r"^(#+)\s+(.*)$", line)
        if match:
            if capture and len(match.group(1)) <= level:
                break
            if match.group(2).strip().lower().startswith(title) and len(match.group(1)) == level:
                capture = True
                continue
        elif capture:
            body.append(line)
    return "\n".join(body).strip()


def first_paragraph(text: str) -> str:
    for block in re.split(r"\n\s*\n", text):
        block = block.strip()
        if block and not block.startswith(("|", "```", "<!--")):
            return re.sub(r"\s+", " ", block)
    return ""


def parse_assumption_ledger(markdown: str) -> list[dict]:
    body = section_text(markdown, "### Assumption ledger (base case)")
    rows: list[dict] = []
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 2 or set(cells[0]) <= {"-", ":", " "}:
            continue
        if cells[0].lstrip("#").strip().isdigit() or cells[0] == "#":
            cells = cells[1:]  # drop a leading numbering column
        if not cells or cells[0].lower() in ("", "input", "assumption", "item", "row"):
            continue
        rows.append({"input": cells[0], "value": cells[1] if len(cells) > 1 else "", "source": cells[2] if len(cells) > 2 else ""})
        if len(rows) >= MAX_ASSUMPTIONS:
            break
    return rows


def parse_open_questions(markdown: str) -> list[str]:
    body = section_text(markdown, "## [HUMAN REVIEW]")
    questions: list[str] = []
    for line in body.splitlines():
        line = line.strip().lstrip("-*0123456789. ").strip()
        if line:
            questions.append(re.sub(r"\s+", " ", line))
        if len(questions) >= MAX_OPEN_QUESTIONS:
            break
    return questions


def parse_citations(markdown: str, ticker: str) -> list[str]:
    """Top distinct citations, preferring primary sources over research artifacts."""
    pattern = re.compile(
        rf"`?((?:{re.escape(ticker)}/|investor-documents/)[\w\-./ ]+?\.(?:pdf|htm|html|md|csv|txt))`?",
        re.IGNORECASE,
    )
    primary: list[str] = []
    secondary: list[str] = []
    for match in pattern.finditer(markdown):
        cite = match.group(1).strip()
        bucket = secondary if f"{ticker}/research/".lower() in cite.lower() else primary
        if cite not in primary and cite not in secondary:
            bucket.append(cite)
    return (primary + secondary)[:MAX_CITATIONS]


def build_card(ticker: str) -> dict | None:
    research = ROOT / ticker / "research"
    valuation = read_json(research / "valuation.json")
    dive = latest_dated(research, DIVE_RE)
    if not valuation and not dive:
        return None
    markdown = dive[1].read_text(encoding="utf-8", errors="replace") if dive else ""

    implied = valuation.get("implied_return") or {}
    results = valuation.get("results") or {}
    # Some valuations store human_review as a list of note strings (CEE, PSH, …).
    raw_human = valuation.get("human_review")
    if isinstance(raw_human, dict):
        human = raw_human
    elif isinstance(raw_human, list):
        human = {"notes": raw_human, "approved_date": None}
    else:
        human = {}
    classification = dict(valuation.get("classification_inputs") or {})
    if valuation.get("lawrence_bucket"):
        classification["lawrence_bucket"] = valuation["lawrence_bucket"]

    digest = latest_dated(research / "evidence", DIGEST_RE)
    scenarios = {
        name: (results.get(name) or {}).get("return_pct")
        for name in ("bear", "base", "bull")
        if isinstance(results.get(name), dict)
    }

    return {
        "schema_version": "1.0",
        "ticker": ticker,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "thesis": first_paragraph(section_text(markdown, "## What this business is")),
        "why_market_wrong": first_paragraph(section_text(markdown, "## Why the market might be wrong")),
        "stance": valuation.get("approved_stance") or (valuation.get("stance_proposal") or {}).get("stance"),
        "classification": classification,
        "base_irr_pct": implied.get("base_pct", (results.get("base") or {}).get("return_pct")),
        "irr_label": implied.get("label", ""),
        "scenarios": scenarios,
        "key_assumptions": parse_assumption_ledger(markdown),
        "open_questions": parse_open_questions(markdown),
        "last_verified": {
            "deep_dive": dive[0] if dive else None,
            "valuation_as_of": valuation.get("as_of"),
            "human_approved": human.get("approved_date"),
        },
        "evidence_citations": parse_citations(markdown, ticker),
        "filing_digest": digest[1].relative_to(ROOT).as_posix() if digest else None,
    }


def ticker_dirs() -> list[str]:
    return sorted(
        entry.name
        for entry in ROOT.iterdir()
        if entry.is_dir()
        and not entry.name.startswith((".", "_"))
        and entry.name not in ("dashboard", "docs", "tmp", "terminals")
        and (entry / "research").is_dir()
    )


def write_card(ticker: str) -> bool:
    card = build_card(ticker)
    if card is None:
        print(f"SKIP {ticker}: no valuation.json or deep dive")
        return False
    out = ROOT / ticker / "research" / "thesis_card.json"
    out.write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {out.relative_to(ROOT).as_posix()}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ticker", nargs="?", type=str.upper)
    parser.add_argument("--all", action="store_true", help="Build cards for every ticker folder")
    args = parser.parse_args()
    if args.all:
        for ticker in ticker_dirs():
            write_card(ticker)
        return 0
    if not args.ticker:
        parser.error("ticker or --all required")
    return 0 if write_card(args.ticker) else 1


if __name__ == "__main__":
    raise SystemExit(main())
