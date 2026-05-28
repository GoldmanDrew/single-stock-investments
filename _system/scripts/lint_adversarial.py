#!/usr/bin/env python3
"""Milly-oriented cross-artifact lint: dive + valuation.json + adversarial + filing_facts.

Usage:
  python _system/scripts/lint_adversarial.py              # all holdings, latest dive
  python _system/scripts/lint_adversarial.py QDEL
  python _system/scripts/lint_adversarial.py QDEL --consistency-only
  python _system/scripts/lint_adversarial.py QDEL --strict   # warnings fail
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

IRR_PCT = re.compile(r"\*\*(\d{1,2}(?:\.\d)?)\s*%\*\*")
RETURNS_BLEND = re.compile(
    r"\*\*Returns statement(?: \(blended\))?:\*\*[^\n]*?\*\*(\d{1,2}(?:\.\d)?)\s*%\*\*",
    re.I,
)
EXEC_IRR = re.compile(
    r"(?:blended|floor|base|IRR)[^\n]{0,80}?\*\*(\d{1,2}(?:\.\d)?)\s*%\*\*",
    re.I,
)
CLASS_IRR = re.compile(
    r"\|\s*\*\*Implied 10yr IRR\*\*[^\|]*\|\s*([^\|]+)\|",
    re.I,
)
VAL_BRIDGE_BASE = re.compile(
    r"\|\s*Base\s*\|[^\n]*\|\s*\*\*(\d{1,2}(?:\.\d)?)\s*%\*\*",
    re.I,
)
ADVERSARIAL_LINK = re.compile(r"\*\*Adversarial(?: review)?:\*\*", re.I)
ADVERSARIAL_STATUS = re.compile(
    r"\*\*Adversarial:\*\*\s*(pass|blocked|pending|partial)",
    re.I,
)
LOOKTHROUGH_HDR = re.compile(r"#### Look-through snapshot\s*\n+(?=####|\n---|\n## )", re.I)


def subsection_empty(text: str, header: str) -> bool:
    m = re.search(
        rf"#### {header}\s*\n+(.*?)(?=\n#### |\n## |\n---)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if not m:
        return False
    body = m.group(1).strip()
    if not body:
        return True
    return not re.search(r"^\s*[-*]|\|", body, re.MULTILINE)
YAML_BLOCK = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL | re.MULTILINE)

HOLDING_CO = re.compile(r"holding_co", re.I)
AI_HYPERSCALERS = frozenset({"GOOGL", "AMZN", "META", "MSFT"})
AI_INFRA = re.compile(r"#### AI infrastructure\b", re.I)
TOLERANCE = 0.25  # percentage points


def registry_flags(ticker: str) -> dict:
    reg = ROOT / "_system" / "portfolio" / "registry.json"
    if not reg.exists():
        return {}
    data = json.loads(reg.read_text(encoding="utf-8"))
    return ((data.get("holdings") or {}).get(ticker) or {}).get("valuation_flags") or {}


def tickers_from_registry() -> list[str]:
    reg = ROOT / "_system" / "portfolio" / "registry.json"
    if reg.exists():
        data = json.loads(reg.read_text(encoding="utf-8"))
        holdings = data.get("holdings") or {}
        if isinstance(holdings, dict):
            return sorted(holdings.keys())
    path = ROOT / "_system" / "portfolio" / "holdings.md"
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("|") and not line.startswith("| Ticker") and not line.startswith("|--"):
            parts = [c.strip() for c in line.split("|") if c.strip()]
            if parts and parts[0] not in ("Ticker", "--------"):
                out.append(parts[0])
    return out


def latest_dive(research: Path) -> Path | None:
    dives = sorted(research.glob("deep_dive_*.md"))
    return dives[-1] if dives else None


def latest_adversarial(research: Path) -> Path | None:
    adv = sorted(research.glob("adversarial_*.md"))
    return adv[-1] if adv else None


def dive_date_from_path(p: Path) -> str:
    m = re.search(r"(\d{4}-\d{2}-\d{2})", p.name)
    return m.group(1) if m else ""


def expected_base_irr(val: dict) -> float | None:
    if not val:
        return None
    ir = val.get("implied_return") or {}
    if isinstance(ir.get("base_pct"), (int, float)):
        return float(ir["base_pct"])
    og = val.get("optionality_gate") or {}
    if isinstance(og.get("primary_return_pct"), (int, float)):
        return float(og["primary_return_pct"])
    bb = (val.get("estimates") or {}).get("blended_best") or {}
    if isinstance(bb.get("return_pct"), (int, float)):
        return float(bb["return_pct"])
    res = (val.get("results") or {}).get("base") or {}
    if isinstance(res.get("return_pct"), (int, float)):
        return float(res["return_pct"])
    return None


def extract_pct_from_class_row(row: str) -> float | None:
    m = re.search(r"(\d{1,2}(?:\.\d)?)\s*%", row)
    return float(m.group(1)) if m else None


def collect_dive_irrs(text: str) -> dict[str, float | None]:
    exec_sum = ""
    m = re.search(r"## Executive summary\s*\n+(.*?)(?=\n## )", text, re.DOTALL | re.I)
    if m:
        exec_sum = m.group(1)
    exec_irrs = [float(x) for x in IRR_PCT.findall(exec_sum)]
    ret_m = RETURNS_BLEND.search(text)
    ret_pct = float(ret_m.group(1)) if ret_m else None
    if ret_pct is None:
        m2 = re.search(
            r"\*\*Returns statement:\*\*[^\n]*?\*\*~?(\d{1,2}(?:\.\d)?)\s*%\*\*",
            text,
            re.I,
        )
        ret_pct = float(m2.group(1)) if m2 else None
    class_m = CLASS_IRR.search(text)
    class_pct = extract_pct_from_class_row(class_m.group(1)) if class_m else None
    bridge_m = VAL_BRIDGE_BASE.search(text)
    bridge_pct = float(bridge_m.group(1)) if bridge_m else None
    # Prefer blended/base in exec (often multiple; take most cited base ~12-22)
    exec_base = exec_irrs[0] if exec_irrs else None
    return {
        "executive_summary_first_pct": exec_base,
        "returns_statement": ret_pct,
        "classification": class_pct,
        "valuation_bridge_base": bridge_pct,
    }


def sotp_sum_check(val: dict) -> tuple[bool, str]:
    scenarios = val.get("scenarios") or {}
    base = scenarios.get("base") or {}
    build = base.get("sotp_build") or {}
    if not build:
        return True, ""
    payoff = base.get("payoff")
    if payoff is None:
        return True, ""
    payoff_f = float(payoff)
    y5_nav = build.get("year5_economic_nav_per_share")
    if isinstance(y5_nav, (int, float)) and abs(float(y5_nav) - payoff_f) <= 0.06:
        return True, ""
    book = build.get("book_per_share")
    inc = build.get("incremental_uplifts_sum")
    if isinstance(book, (int, float)) and isinstance(inc, (int, float)):
        if abs(float(book) + float(inc) - payoff_f) <= 0.06:
            return True, ""
    return True, ""  # holdco SOTP uses incremental uplifts; skip naive line sum


def parse_adversarial_yaml(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="ignore")
    m = YAML_BLOCK.match(text)
    if not m:
        return {}
    out: dict = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k, v = k.strip(), v.strip()
        if v.lower() in ("true", "false"):
            out[k] = v.lower() == "true"
        elif v.startswith("[") and v.endswith("]"):
            out[k] = [x.strip().strip('"') for x in v[1:-1].split(",") if x.strip()]
        else:
            try:
                out[k] = float(v) if "." in v else int(v)
            except ValueError:
                out[k] = v.strip('"')
    return out


def lint_ticker(
    ticker: str,
    *,
    consistency_only: bool,
    strict: bool,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    rel_base = f"{ticker}/research"

    research = ROOT / ticker / "research"
    dive = latest_dive(research)
    if not dive:
        errors.append(f"{rel_base}: no deep_dive_*.md")
        return errors, warnings

    rel_dive = dive.relative_to(ROOT)
    text = dive.read_text(encoding="utf-8", errors="ignore")
    dive_date = dive_date_from_path(dive)

    val_path = research / "valuation.json"
    val = {}
    if val_path.exists():
        val = json.loads(val_path.read_text(encoding="utf-8"))
    else:
        errors.append(f"{rel_dive}: missing valuation.json")

    expected = expected_base_irr(val)
    found = collect_dive_irrs(text)

    if expected is not None:
        ret_line = ""
        m_ret = re.search(r"\*\*Returns statement[^*]*\*\*[^\n]+", text, re.I)
        if m_ret:
            ret_line = m_ret.group(0).lower()
        blended_returns = "blended" in ret_line
        for label, pct in found.items():
            if pct is None:
                continue
            if abs(pct - expected) > TOLERANCE:
                if label == "executive_summary_first_pct":
                    sev = warnings
                elif label == "returns_statement" and blended_returns:
                    sev = warnings
                elif label in ("returns_statement", "classification"):
                    sev = errors
                else:
                    sev = warnings
                sev.append(
                    f"{rel_dive}: {label} {pct}% vs valuation.json base {expected}% "
                    f"(tol {TOLERANCE}pp)"
                )
        if found["returns_statement"] is None:
            warnings.append(f"{rel_dive}: missing parseable Returns statement IRR")
        if found["classification"] is None:
            warnings.append(f"{rel_dive}: missing Implied 10yr IRR in Classification")

    ok, msg = sotp_sum_check(val)
    if not ok:
        errors.append(f"{rel_dive}: {msg}")

    ai = val.get("ai_overlay") or {}
    need_ai = bool(ai) or registry_flags(ticker).get("ai_hyperscaler") or ticker in AI_HYPERSCALERS
    if need_ai and not val.get("overlay_results"):
        warnings.append(f"{rel_dive}: missing overlay_results — run marvin_valuation.py --write")
    if need_ai:
        if not AI_INFRA.search(text):
            (errors if strict else warnings).append(
                f"{rel_dive}: missing #### AI infrastructure — model coverage"
            )
        gaps = ai.get("not_in_model_requires_refresh") or []
        if gaps:
            human = "## [HUMAN REVIEW]" in text
            for gap in gaps[:3]:
                snippet = str(gap)[:60]
                if snippet.lower() not in text.lower() and not human:
                    warnings.append(
                        f"{rel_dive}: ai_overlay gap not in dive or [HUMAN REVIEW]: {snippet}…"
                    )
                    break
        stress = ai.get("capex_stress_2026") or ai.get("capex_stress") or {}
        guide = stress.get("capex_bn")
        if guide and not stress.get("implied_fcf_per_share") and "capex" not in text.lower():
            warnings.append(f"{rel_dive}: ai_overlay has capex_stress but dive omits capex trough")

    if HOLDING_CO.search(text):
        if LOOKTHROUGH_HDR.search(text):
            errors.append(
                f"{rel_dive}: empty #### Look-through snapshot (holding_co)"
            )
        if subsection_empty(text, "Catalyst path"):
            (errors if strict else warnings).append(
                f"{rel_dive}: empty #### Catalyst path (holding_co)"
            )

    facts_glob = list((research / "evidence").glob("filing_facts_*.json"))
    if not facts_glob:
        warnings.append(f"{rel_base}/evidence: no filing_facts_*.json — run build_filing_evidence.py")

    adv = latest_adversarial(research)
    if consistency_only:
        if adv and dive_date and dive_date not in adv.name:
            warnings.append(
                f"{rel_base}: adversarial {adv.name} may not match dive date {dive_date}"
            )
    else:
        if not adv:
            if ADVERSARIAL_LINK.search(text[:2500]) or ADVERSARIAL_STATUS.search(text[:2500]):
                errors.append(f"{rel_base}: dive header cites adversarial but file missing")
            else:
                warnings.append(f"{rel_base}: missing adversarial_*.md — run Milly standard pass")
        elif dive_date and dive_date not in adv.name:
            warnings.append(
                f"{rel_base}: adversarial date {adv.name} != dive {dive_date}"
            )
        if not ADVERSARIAL_LINK.search(text[:2000]):
            warnings.append(f"{rel_dive}: header missing **Adversarial review:** link")
        if adv:
            yml = parse_adversarial_yaml(adv)
            if yml.get("block_final") is True:
                errors.append(
                    f"{adv.relative_to(ROOT)}: block_final=true — resolve before final dive"
                )
            if yml and not yml.get("block_final") and yml.get("consistency") == "fail":
                errors.append(f"{adv.relative_to(ROOT)}: consistency=fail in YAML frontmatter")

    return errors, warnings


def main() -> None:
    parser = argparse.ArgumentParser(description="Lint dive vs valuation + Milly artifacts")
    parser.add_argument("ticker", nargs="?", help="Single ticker")
    parser.add_argument(
        "--consistency-only",
        action="store_true",
        help="Skip adversarial-file-required; re-pass after Marvin fixes",
    )
    parser.add_argument("--strict", action="store_true", help="Warnings are errors")
    args = parser.parse_args()

    tickers = [args.ticker] if args.ticker else tickers_from_registry()
    all_errors: list[str] = []
    all_warnings: list[str] = []

    for t in tickers:
        errs, warns = lint_ticker(
            t, consistency_only=args.consistency_only, strict=args.strict
        )
        all_errors.extend(errs)
        all_warnings.extend(warns)

    for w in all_warnings:
        print(f"WARN: {w}")
    if all_errors:
        for e in all_errors:
            print(f"LINT: {e}")
        sys.exit(1)

    n = len(tickers)
    suffix = ""
    if all_warnings:
        suffix = f" ({len(all_warnings)} warning(s))"
    print(f"OK: {n} ticker(s) adversarial lint{suffix}")


if __name__ == "__main__":
    main()
