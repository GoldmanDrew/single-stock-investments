#!/usr/bin/env python3
"""Lint deep dives for decision-stack report structure and prose rules.

Usage:
  python _system/scripts/lint_deep_dive.py              # all tickers, latest dive each
  python _system/scripts/lint_deep_dive.py ICE        # latest ICE dive
  python _system/scripts/lint_deep_dive.py --all ICE    # all ICE dives
  python _system/scripts/lint_deep_dive.py ICE --legacy # skip 2026 prose sections
  python _system/scripts/lint_deep_dive.py ICE --strict # prose warnings fail too
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

REQUIRED_SECTIONS = [
    (r"## What this business is", "What this business is"),
    (r"## Why the market might be wrong", "Why the market might be wrong"),
    (r"## Executive summary", "Executive summary"),
    (r"## (Business & moat|Business overview)", "Business & moat (or legacy Business overview)"),
    (r"## (Payoff & return|Lawrence IRR)", "Payoff & return (or legacy Lawrence IRR)"),
    (r"## (Risks & inversion|Risks)", "Risks & inversion"),
    (r"## Valuation & IRR \(assumption ledger\)", "Valuation & IRR (assumption ledger)"),
    (r"## Classification", "Classification"),
    (r"## \[HUMAN REVIEW\]", "[HUMAN REVIEW]"),
]

ASSUMPTION_LEDGER = re.compile(r"### Assumption ledger \(base case\)", re.IGNORECASE)
VALUATION_SECTION = re.compile(r"## Valuation & IRR \(assumption ledger\)", re.IGNORECASE)

FORBIDDEN = [
    (r"\*\*Thesis status:\*\*", "Legacy thesis status — use Classification table"),
    (r"## Thesis status", "Legacy Thesis status section"),
]

EXEC_SUMMARY_LABEL_OPEN = re.compile(
    r"^\s*\*\*(Archetype|Stahl|Munger|Pabrai|Lawrence|Dhando|Moat)\b",
    re.IGNORECASE | re.MULTILINE,
)

TIER2_HEADER = re.compile(r"### Tier 2 prompts", re.IGNORECASE)
MENTAL_MODELS = re.compile(r"### Mental models\b", re.IGNORECASE)
MENTAL_MODELS_LEGACY = re.compile(r"### Mental models in plain English", re.IGNORECASE)
RETURN_MATH = re.compile(r"#### Return math in plain English", re.IGNORECASE)
IRR_ARITHMETIC = re.compile(r"#### IRR arithmetic \(show your work\)", re.IGNORECASE)
UPSIDE_DOWN = re.compile(r"\*\*Upside / downside from price:\*\*", re.IGNORECASE)
PRIMARY_RISK = re.compile(r"\*\*Primary risk:\*\*", re.IGNORECASE)
HOLDING_CO = re.compile(r"\*\*Archetype\*\*.*holding_co", re.IGNORECASE)
LOOKTHROUGH_OR_SOTP = re.compile(
    r"#### (Look-through snapshot|Sum-of-parts or NAV)", re.IGNORECASE
)
CATALYST_PATH = re.compile(r"#### Catalyst path", re.IGNORECASE)

EM_DASH = "\u2014"  # —
EXEC_SUMMARY_MAX_WORDS = 220
EM_DASH_MAX = 1

AI_HYPERSCALERS = frozenset({"GOOGL", "AMZN", "META", "MSFT"})
SEGMENT_MAP = re.compile(r"#### Segment map\b", re.IGNORECASE)
SEGMENT_BUILD = re.compile(r"### Segment cash-flow build\b", re.IGNORECASE)
AI_INFRA = re.compile(r"#### AI infrastructure\b", re.IGNORECASE)


def ticker_from_dive_path(path: Path) -> str | None:
    parts = path.parts
    for i, p in enumerate(parts):
        if p == "research" and i > 0:
            return parts[i - 1]
    return None


def load_valuation(ticker: str) -> dict:
    val_path = ROOT / ticker / "research" / "valuation.json"
    if not val_path.exists():
        return {}
    return json.loads(val_path.read_text(encoding="utf-8"))


def registry_flags(ticker: str) -> dict:
    reg = ROOT / "_system" / "portfolio" / "registry.json"
    if not reg.exists():
        return {}
    data = json.loads(reg.read_text(encoding="utf-8"))
    holding = (data.get("holdings") or {}).get(ticker) or {}
    return holding.get("valuation_flags") or {}


def latest_dive(ticker_dir: Path) -> Path | None:
    dives = sorted(ticker_dir.glob("deep_dive_*.md"))
    return dives[-1] if dives else None


def body_before_classification(text: str) -> str:
    idx = text.find("## Classification")
    return text[:idx] if idx >= 0 else text


def extract_executive_summary(text: str) -> str | None:
    m = re.search(
        r"## Executive summary\s*\n+(.*?)(?=\n## |\Z)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    return m.group(1).strip() if m else None


def word_count(s: str) -> int:
    return len(re.findall(r"\b[\w']+\b", s))


def lint_file(path: Path, *, legacy: bool, strict: bool) -> tuple[list[str], list[str]]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    errors: list[str] = []
    warnings: list[str] = []
    rel = path.relative_to(ROOT)

    for pattern, name in REQUIRED_SECTIONS:
        if legacy and name in (
            "What this business is",
            "Why the market might be wrong",
        ):
            continue
        if not re.search(pattern, text, re.IGNORECASE):
            errors.append(f"{rel}: missing section — {name}")

    for pattern, msg in FORBIDDEN:
        if re.search(pattern, text):
            errors.append(f"{rel}: {msg}")

    if "## Classification" in text and "Implied 10yr IRR" not in text:
        errors.append(f"{rel}: Classification table missing Implied 10yr IRR (decision stack)")

    if legacy:
        return errors, warnings

    body = body_before_classification(text)

    if TIER2_HEADER.search(text) and (MENTAL_MODELS.search(text) or MENTAL_MODELS_LEGACY.search(text)):
        warnings.append(
            f"{rel}: has both Tier 2 prompts and Mental models — consolidate per deep_dive_structure.md"
        )
    if not (MENTAL_MODELS.search(text) or MENTAL_MODELS_LEGACY.search(text)):
        errors.append(f"{rel}: missing ### Mental models (deep_dive_structure.md)")

    if not VALUATION_SECTION.search(text):
        errors.append(
            f"{rel}: missing ## Valuation & IRR (assumption ledger) — must be at end (irr_assumption_ledger.md)"
        )
    if not ASSUMPTION_LEDGER.search(text):
        errors.append(
            f"{rel}: missing ### Assumption ledger (base case) (irr_assumption_ledger.md)"
        )
    if not IRR_ARITHMETIC.search(text):
        errors.append(
            f"{rel}: missing #### IRR arithmetic (show your work) (lawrence_irr.md § F)"
        )
    elif RETURN_MATH.search(text):
        warnings.append(
            f"{rel}: legacy #### Return math in plain English — rename to #### IRR arithmetic (show your work)"
        )
    elif IRR_ARITHMETIC.search(text) and VALUATION_SECTION.search(text):
        irr_pos = IRR_ARITHMETIC.search(text).start()
        val_pos = VALUATION_SECTION.search(text).start()
        if irr_pos < val_pos:
            errors.append(
                f"{rel}: IRR arithmetic must be inside ## Valuation & IRR section at end of report"
            )
        biz_end = text.find("## Valuation & IRR")
        if biz_end > 0 and IRR_ARITHMETIC.search(text[:biz_end]):
            warnings.append(
                f"{rel}: IRR arithmetic still in overview — run refresh_deep_dive_v2.py"
            )
    if not UPSIDE_DOWN.search(text):
        errors.append(f"{rel}: missing **Upside / downside from price:** (Hohn essentials)")
    if not PRIMARY_RISK.search(text):
        errors.append(f"{rel}: missing **Primary risk:** in Risks section (Hohn essentials)")

    if HOLDING_CO.search(text):
        if not LOOKTHROUGH_OR_SOTP.search(text):
            errors.append(
                f"{rel}: holding_co — missing #### Look-through snapshot or #### Sum-of-parts or NAV"
            )
        if not CATALYST_PATH.search(text):
            (errors if strict else warnings).append(
                f"{rel}: holding_co — missing #### Catalyst path (dated events)"
            )

    em_count = body.count(EM_DASH)
    if em_count > EM_DASH_MAX:
        msg = f"{rel}: {em_count} em dashes in body (max {EM_DASH_MAX}); use periods or parentheses"
        (errors if strict else warnings).append(msg)

    exec_sum = extract_executive_summary(text)
    if exec_sum:
        if EXEC_SUMMARY_LABEL_OPEN.search(exec_sum):
            msg = f"{rel}: executive summary opens with framework label — lead with the business"
            (errors if strict else warnings).append(msg)
        wc = word_count(exec_sum)
        if wc > EXEC_SUMMARY_MAX_WORDS:
            msg = f"{rel}: executive summary is {wc} words (target ≤{EXEC_SUMMARY_MAX_WORDS})"
            (errors if strict else warnings).append(msg)

    ticker = ticker_from_dive_path(path)
    if ticker and not legacy:
        val = load_valuation(ticker)
        overlay = val.get("valuation_overlay")
        if overlay == "segment_cashflow":
            if not SEGMENT_MAP.search(text):
                errors.append(
                    f"{rel}: valuation_overlay segment_cashflow — missing #### Segment map"
                )
            if not SEGMENT_BUILD.search(text):
                errors.append(
                    f"{rel}: valuation_overlay segment_cashflow — missing ### Segment cash-flow build"
                )
        flags = registry_flags(ticker) if ticker else {}
        need_ai = (
            val.get("ai_overlay") is not None
            or flags.get("ai_hyperscaler")
            or ticker in AI_HYPERSCALERS
        )
        if need_ai and not AI_INFRA.search(text):
            msg = (
                f"{rel}: AI hyperscaler or ai_overlay — missing "
                "#### AI infrastructure — model coverage (ai_infrastructure_valuation.md)"
            )
            (errors if strict else warnings).append(msg)

    return errors, warnings


def main() -> None:
    parser = argparse.ArgumentParser(description="Lint deep dive structure and prose")
    parser.add_argument("ticker", nargs="?", help="Ticker to lint")
    parser.add_argument("--all", action="store_true", help="Lint all dives for ticker")
    parser.add_argument(
        "--legacy",
        action="store_true",
        help="Skip What/Why sections and prose checks (pre-refresh dives)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat prose warnings as errors",
    )
    parser.add_argument(
        "--milly",
        action="store_true",
        help="Also run lint_adversarial.py on same ticker(s)",
    )
    args = parser.parse_args()

    paths: list[Path] = []
    if args.ticker:
        research = ROOT / args.ticker / "research"
        if args.all:
            paths = sorted(research.glob("deep_dive_*.md"))
        else:
            d = latest_dive(research)
            if d:
                paths = [d]
    else:
        for td in sorted(ROOT.iterdir()):
            if td.is_dir() and (td / "research").is_dir():
                d = latest_dive(td / "research")
                if d:
                    paths.append(d)

    if not paths:
        print("No deep dives found.")
        sys.exit(0)

    all_errors: list[str] = []
    all_warnings: list[str] = []
    for p in paths:
        errs, warns = lint_file(p, legacy=args.legacy, strict=args.strict)
        all_errors.extend(errs)
        all_warnings.extend(warns)

    for w in all_warnings:
        print(f"WARN: {w}")
    if all_errors:
        for e in all_errors:
            print(f"LINT: {e}")
        sys.exit(1)

    if args.milly:
        import subprocess

        py = sys.executable
        adv_script = Path(__file__).resolve().parent / "lint_adversarial.py"
        cmd = [py, str(adv_script)]
        if args.ticker:
            cmd.append(args.ticker)
        if args.strict:
            cmd.append("--strict")
        print("--- Milly / adversarial lint ---")
        r = subprocess.run(cmd, cwd=ROOT)
        if r.returncode != 0:
            sys.exit(r.returncode)

    suffix = ""
    if args.legacy:
        suffix = " (legacy mode)"
    elif all_warnings:
        suffix = f" ({len(all_warnings)} warning(s))"
    print(f"OK: {len(paths)} deep dive(s){suffix}")


if __name__ == "__main__":
    main()
