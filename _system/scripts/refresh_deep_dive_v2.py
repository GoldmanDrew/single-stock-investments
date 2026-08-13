#!/usr/bin/env python3
"""Restructure deep dives: overview first, Valuation & IRR (assumption ledger) at end.

Usage:
  python _system/scripts/refresh_deep_dive_v2.py FRMO
  python _system/scripts/refresh_deep_dive_v2.py --all
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))
from vault_paths import wisdom_root  # noqa: E402
from decision_authority import resolve_authority  # noqa: E402

APPROVED_THIRD_PARTY = ROOT / "_system" / "frameworks" / "third_party_sources.md"
HK_INDEX = wisdom_root() / "hk_ticker_index.json"
VALUATION_BRIDGE_START = re.compile(r"#### Valuation bridge", re.IGNORECASE)
HOLDING_CO_KEEP = re.compile(
    r"#### (Look-through snapshot|Sum-of-parts or NAV|Catalyst path)",
    re.IGNORECASE,
)
VALUATION_SECTION = re.compile(r"^## Valuation & IRR", re.IGNORECASE | re.MULTILINE)
SECTION_RE = re.compile(r"^(## .+)$", re.MULTILINE)


def latest_dive(research: Path) -> Path | None:
    dives = sorted(research.glob("deep_dive_*.md"))
    return dives[-1] if dives else None


def split_sections(text: str) -> dict[str, str]:
    parts: dict[str, str] = {}
    matches = list(SECTION_RE.finditer(text))
    for i, m in enumerate(matches):
        title = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        parts[title] = normalize_section_body(text[start:end])
    return parts


def normalize_section_body(body: str) -> str:
    """Strip spurious horizontal rules left by prior refresh passes."""
    if not body.strip():
        return ""
    lines = [ln for ln in body.splitlines() if ln.strip() != "---"]
    return "\n".join(lines).strip()


def extract_irr_block(body: str) -> tuple[str, str | None]:
    """Return (body_without_valuation_math, preserved_tail_from_valuation_bridge_onward)."""
    m = VALUATION_BRIDGE_START.search(body)
    if not m:
        return body, None
    tail = body[m.start() :]
    # Keep holdco tables in Business overview; only preserve math for end section
    keep_parts = []
    for hm in HOLDING_CO_KEEP.finditer(tail):
        keep_parts.append((hm.start(), hm.end(), hm.group(0)))
    preserved = tail.strip()
    head = body[: m.start()].rstrip()
    if keep_parts:
        blocks = []
        for start, end, _ in keep_parts:
            blocks.append(tail[start:end].strip())
        head = head + "\n\n" + "\n\n".join(blocks)
    return head, preserved


def strip_valuation_from_business(body: str) -> str:
    """Remove valuation bridge, IRR, returns statement from Business & moat."""
    body, _ = extract_irr_block(body)
    body = re.sub(
        r"\*\*Returns statement:\*\*.*?(?=\n### |\n#### |\Z)",
        "",
        body,
        flags=re.DOTALL | re.IGNORECASE,
    )
    body = re.sub(
        r"\*\*Upside / downside from price:\*\*.*?(?=\n### |\n#### |\Z)",
        "",
        body,
        flags=re.DOTALL | re.IGNORECASE,
    )
    return body.rstrip()


def load_valuation(ticker: str) -> dict | None:
    p = ROOT / ticker / "research" / "valuation.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def filing_digest_path(ticker: str) -> str | None:
    ev = ROOT / ticker / "research" / "evidence"
    if not ev.exists():
        return None
    digs = sorted(ev.glob("filing_digest_*.md"))
    if not digs:
        return None
    return str(digs[-1].relative_to(ROOT)).replace("\\", "/")


def scan_pending_third_party(ticker: str) -> list[dict]:
    notes = ROOT / ticker / "investor-documents" / "research-notes"
    if not notes.exists():
        return []
    approved_text = APPROVED_THIRD_PARTY.read_text(encoding="utf-8", errors="ignore")
    pending = []
    for f in sorted(notes.iterdir()):
        if f.suffix.lower() not in (".pdf", ".md", ".htm", ".html"):
            continue
        rel = str(f.relative_to(ROOT)).replace("\\", "/")
        if f.name in approved_text and "pending" not in approved_text.split(f.name)[0][-80:]:
            if "approved" in approved_text.lower() and f.name in approved_text:
                pass
        status = "approved" if f.name in approved_text and "McIntyre" in f.name else "pending"
        if rel not in approved_text and status == "pending":
            pending.append({"path": rel, "name": f.name})
    return pending


def is_hk_indexed(ticker: str) -> bool:
    if not HK_INDEX.exists():
        return False
    data = json.loads(HK_INDEX.read_text(encoding="utf-8"))
    return ticker.upper() in data.get("tickers", {})


def inject_hk_primary_sources(body: str, ticker: str) -> str:
    if not is_hk_indexed(ticker):
        return body
    import sys

    scripts = Path(__file__).resolve().parent
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from scan_hk_sources import HK_SCAN_BEGIN, HK_SCAN_END, hk_block_markdown, load_latest_scan

    result = load_latest_scan(ticker)
    if not result:
        return body
    block = hk_block_markdown(result)
    if not block:
        return body
    if HK_SCAN_BEGIN in body and HK_SCAN_END in body:
        pre = body[: body.index(HK_SCAN_BEGIN)]
        post = body[body.index(HK_SCAN_END) + len(HK_SCAN_END) :]
        return pre + block + post
    return body.rstrip() + "\n\n" + block + "\n"


def write_pending_md(ticker: str, items: list[dict]) -> None:
    tp = ROOT / ticker / "third-party-analyses"
    tp.mkdir(parents=True, exist_ok=True)
    out = tp / "pending.md"
    lines = [
        f"# {ticker} — Pending third-party sources",
        "",
        f"**Updated:** {date.today().isoformat()}",
        "",
        "Approve in `_system/frameworks/third_party_sources.md` before using in base IRR.",
        "",
        "| File | Status |",
        "|------|--------|",
    ]
    for it in items:
        lines.append(f"| `{it['path']}` | **PENDING APPROVAL** |")
    if not items:
        lines.append("| (none) | — |")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


from lawrence_horizon import (  # noqa: E402
    IMPLIED_IRR_LABEL,
    LAWRENCE_HORIZON_YEARS,
    RETURN_LABEL,
    SYNTHESIS_LABEL,
)

METHOD_LABELS = {
    "full": f"{LAWRENCE_HORIZON_YEARS}-year cash flow",
    "yield_curve": "Dated payoff",
    "scenario": "Scenarios",
    "pending": "Pending",
}


def method_label(method: str) -> str:
    return METHOD_LABELS.get(method, method)


def stance_proposal_block(val: dict) -> str:
    ticker = str(val.get("ticker") or "").upper()
    research = ROOT / ticker / "research" if ticker else ROOT
    authority = resolve_authority(research, val)
    if authority.get("authority_level") != "legacy_reference":
        base_pct = (authority.get("return_range_pct") or {}).get("base")
        recommendation = authority.get("decision") or "pending owner/committee review"
        lines = [
            "### Decision authority",
            "",
            f"**Status:** {authority.get('status')}  ",
            f"**Authority:** {authority.get('authority_level')}  ",
            f"**Power Zone:** {authority.get('profile_label') or authority.get('profile_id') or 'routing pending'}  ",
            f"**Contract base return:** {str(base_pct) + '%' if base_pct is not None else 'not decision-grade'}  ",
            f"**Recommendation/decision:** {recommendation}",
            "",
            "Legacy Marvin/Lawrence returns are migration references only and do not set the stance.",
            "",
        ]
        return "\n".join(lines)
    base_pct = val.get("implied_return", {}).get("base_pct") or (val.get("results") or {}).get("base", {}).get(
        "return_pct", "?"
    )
    proposal = val.get("stance_proposal") or {}
    suggested = proposal.get("suggested", "pending")
    approved = val.get("approved_stance") or proposal.get("approved_stance")
    stance = approved or suggested
    lines = [
        "### Stance proposal",
        "",
        f"Base **{base_pct}%** per year → **{stance}**"
        + (
            f" (model suggested **{suggested}**; human approved **{approved}**)"
            if approved and approved != suggested
            else ""
        )
        + ".",
    ]
    override = proposal.get("override_reason")
    if override:
        lines.append(f"**Override:** {override}")
    entry = (val.get("human_review") or {}).get("entry_band_15pct")
    if entry:
        lines.append(f"**Entry band (~15% base):** {entry}")
    lines.append("")
    return "\n".join(lines)


def primary_irr_pct(val: dict) -> float | int | str | None:
    from optionality_evidence_common import synthesis_in_dive

    ir = val.get("implied_return") or {}
    if synthesis_in_dive(val):
        syn = ir.get("synthesis_pct") if ir.get("synthesis_pct") is not None else ir.get("base_pct")
        if syn is not None:
            return syn
    ticker = str(val.get("ticker") or "").upper()
    method = val.get("method") or val.get("irr_method")
    legacy_pct = val.get("implied_return", {}).get("base_pct") or (val.get("results") or {}).get("base", {}).get(
        "return_pct"
    )
    if method in ("yield_curve", "full", "scenario") and legacy_pct is not None:
        return legacy_pct
    authority = resolve_authority(ROOT / ticker / "research", val) if ticker else {}
    contract_base = (authority.get("return_range_pct") or {}).get("base")
    if contract_base is not None:
        return contract_base
    return ir.get("base_pct") or (val.get("results") or {}).get("base", {}).get("return_pct")


def format_headline_pct(base_pct: float | int | str) -> str:
    if isinstance(base_pct, float):
        if base_pct == int(base_pct):
            return str(int(base_pct))
        return f"{base_pct:.2f}".rstrip("0").rstrip(".")
    return str(base_pct)


def growth_rates_for_irr(val: dict) -> tuple[float, float, float | int]:
    """Return (g1, g2, exit_multiple) for IRR arithmetic from scenarios.base."""
    base = val.get("scenarios", {}).get("base", {})
    g1 = base.get("growth_y1_5", 0.05)
    g2 = base.get("growth_y6_10", 0.03)
    ex = base.get("exit_pfcf_y10") or base.get("exit_multiple", 10)
    return g1, g2, ex


def patch_classification_stance(text: str, val: dict) -> str:
    ticker = str(val.get("ticker") or "").upper()
    authority = resolve_authority(ROOT / ticker / "research", val) if ticker else {}
    approved = authority.get("stance") if authority.get("actionable") else None
    if approved:
        text = re.sub(
            r"(\|\s*\*\*Stance\*\*[^|]*\|\s*)([^|]+)(\|)",
            lambda m: f"{m.group(1)}{approved}     {m.group(3)}",
            text,
            count=1,
        )
    text = re.sub(
        r"\*\*Implied \d+yr IRR\*\*",
        f"**{IMPLIED_IRR_LABEL}**",
        text,
        count=1,
    )
    from optionality_evidence_common import synthesis_in_dive

    ir = val.get("implied_return") or {}
    contract_base = (authority.get("return_range_pct") or {}).get("base")
    if synthesis_in_dive(val):
        syn = ir.get("synthesis_pct") if ir.get("synthesis_pct") is not None else ir.get("base_pct")
        display = f"{syn}% (total synthesis)" if syn is not None else None
    else:
        display = (
            f"{contract_base}% (contract base)"
            if contract_base is not None
            else (ir.get("display") if authority.get("authority_level") == "legacy_reference" else None)
        )
    if display:
        text = re.sub(
            rf"(\|\s*\*\*{re.escape(IMPLIED_IRR_LABEL)}\*\*[^|]*\|\s*)([^\|]+)(\|)",
            lambda m: f"{m.group(1)}{display}     {m.group(3)}",
            text,
            count=1,
        )
    return text


def patch_exec_summary_irr(body: str, val: dict) -> str:
    base_pct = primary_irr_pct(val)
    if base_pct is None:
        return body
    pct = format_headline_pct(base_pct)
    body = re.sub(
        rf"\*\*(?:Lawrence consolidated base|falsifier-adjusted) \d+-year annual return is [\d.-]+%\*\*",
        f"**Base {LAWRENCE_HORIZON_YEARS}-year annual return is {pct}%**",
        body,
    )
    body = re.sub(
        rf"(?:Lawrence base|Falsifier-adjusted) \d+-year annual return is \*\*[\d.-]+%\*\*",
        f"Base {LAWRENCE_HORIZON_YEARS}-year annual return is **{pct}%**",
        body,
    )
    body = re.sub(
        rf"Base \d+-year annual return is \*\*[\d.-]+%\*\*",
        f"Base {LAWRENCE_HORIZON_YEARS}-year annual return is **{pct}%**",
        body,
        count=1,
    )
    body = re.sub(
        r"implies about [\d.-]+% annualized return",
        f"implies about **{pct}%** per year (total synthesis headline)",
        body,
        count=1,
    )
    body = re.sub(
        r"about [\d.-]+% annualized return",
        f"about **{pct}%** per year (total synthesis headline)",
        body,
        count=1,
    )
    body = re.sub(
        r"base expected annual return[^.]{0,120}\*\*[\d.-]+%\*\*",
        lambda m: re.sub(r"\*\*[\d.-]+%\*\*", f"**{pct}%**", m.group(0), count=1),
        body,
        count=1,
        flags=re.IGNORECASE,
    )
    body = re.sub(
        r"we expect about \*\*[\d.]+% per year\*\*",
        f"we expect about **{pct}% per year**",
        body,
        count=1,
        flags=re.IGNORECASE,
    )
    body = re.sub(
        r"We expect \*\*[\d.-]+%\*\* per year on the Lawrence[^.]+\.",
        f"We expect **{pct}%** per year (total synthesis at today's price).",
        body,
        count=1,
    )
    body = re.sub(
        r"equity-yield-curve base is \*\*[\d.-]+%\*\*",
        f"total synthesis headline is **{pct}%**",
        body,
        count=1,
    )
    body = re.sub(
        r"base equity-yield-curve return is \*\*[\d.-]+%\*\*",
        f"total synthesis headline is **{pct}%**",
        body,
        count=1,
    )
    return patch_horizon_year_prose(body)


def patch_horizon_year_prose(body: str) -> str:
    """Normalize legacy ten-year horizon wording to Lawrence horizon constant."""
    n = LAWRENCE_HORIZON_YEARS
    body = re.sub(r"\bover ten years\b", f"over {n} years", body, flags=re.I)
    body = re.sub(r"\bfor ten years\b", f"for {n} years", body, flags=re.I)
    body = re.sub(r"\bper year over ten years\b", f"per year over {n} years", body, flags=re.I)
    body = re.sub(r"\bTen-year owner-cash\b", f"{n}-year owner-cash", body, flags=re.I)
    body = re.sub(r"\bten-year owner-cash\b", f"{n}-year owner-cash", body, flags=re.I)
    return body


def blended_estimate_section(val: dict) -> str | None:
    """JSON-driven blended estimate; replaces regex patches when estimates exist."""
    import sys

    scripts = Path(__file__).resolve().parent
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from valuation_synthesis import blended_estimate_markdown, has_blended_estimates

    if not has_blended_estimates(val):
        return None
    body = blended_estimate_markdown(val)
    return body.strip() if body else None


def patch_blended_estimate_irr(body: str, val: dict) -> str:
    base_pct = primary_irr_pct(val)
    if base_pct is None:
        return body
    pct = format_headline_pct(base_pct)
    # 4-column (owner cash + return): CMSG-style
    body = re.sub(
        r"(\|\s*\*\*Blended best estimate\*\*\s*\|\s*[^|]+\|\s*)\*\*[^*|~]+?\*\*(\s*\|)",
        lambda m: f"{m.group(1)}**{pct}%** (total synthesis){m.group(2)}",
        body,
        count=1,
    )
    # 3-column (return anchor only): FRMO-style
    body = re.sub(
        r"(\|\s*\*\*Blended best estimate\*\*\s*\|\s*)\*\*[\d.-]+%\*\*[^|]*(\|)",
        lambda m: f"{m.group(1)}**{pct}%** (total synthesis)     {m.group(2)}",
        body,
        count=1,
    )
    body = re.sub(
        r"\*\*Returns statement \(blend\):\*\* We expect about \*\*[\d.]+%\*\*",
        f"**Returns statement (blend):** We expect about **{pct}%**",
        body,
        count=1,
    )
    body = re.sub(
        r"numeric anchor unchanged \(\*\*[\d.-]+%\*\*",
        f"headline is total synthesis (**{pct}%**",
        body,
        count=1,
    )
    return body


def patch_payoff_returns_statement(body: str, val: dict) -> str:
    """Early payoff returns lines before synthesis block."""
    base_pct = primary_irr_pct(val)
    if base_pct is None:
        return body
    pct = format_headline_pct(base_pct)
    body = re.sub(
        r"\*\*Returns statement:\*\* At [^.]+\*\*[\d.-]+%\*\* per year",
        f"**Returns statement:** At today's price, we expect about **{pct}%** per year",
        body,
        count=1,
    )
    return body


def patch_payoff_expected_return(body: str, val: dict) -> str:
    base_pct = primary_irr_pct(val)
    if base_pct is None:
        return body

    def repl_base(m: re.Match) -> str:
        return f"{m.group(1)}**{base_pct}%**{m.group(2)}"

    def repl_base_plain(m: re.Match) -> str:
        return f"{m.group(1)}{base_pct}%{m.group(2)}"

    body = re.sub(r"(\|\s*Base\s*\|\s*)\*\*[\d.-]+%\*\*(\s*\|)", repl_base, body, count=1)
    body = re.sub(r"(\|\s*Base\s*\|\s*)[\d.-]+%(?:\s*\([^)]*\))?(\s*\|)", repl_base_plain, body, count=1)
    return body


def bridge_key_plain(sc: dict) -> str:
    if "growth_y1_5" in sc:
        g1 = sc.get("growth_y1_5", 0) * 100
        g2 = sc.get("growth_y6_10", 0) * 100
        ex = sc.get("exit_pfcf_y10", sc.get("exit_multiple", "?"))
        return (
            f"Cash flow grows {g1:.0f}% then {g2:.0f}%; "
            f"sell at {ex:.0f} times year-10 cash flow"
        )
    return (sc.get("notes") or "")[:70]


def bridge_bar(pct: float | None, *, stance_gate: bool = True) -> str:
    if pct is None:
        return "info"
    if not stance_gate:
        return "overlay"
    if pct >= 15:
        return "pass"
    if pct >= 10:
        return "marginal"
    return "fail"


def bridge_table(val: dict) -> str:
    method = val.get("method", "full")
    results = val.get("results", {})
    scenarios = val.get("scenarios", {})
    rows = []
    for case in ("bear", "base", "bull"):
        sc = scenarios.get(case, {})
        res = (val.get("results_lawrence_legacy") or results).get(case, {})
        pct = res.get("return_pct", "—")
        bar = bridge_bar(pct if isinstance(pct, (int, float)) else None)
        suffix = " (Lawrence legacy)" if val.get("results_growth_theory") else ""
        notes = sc.get("notes", "")[:60]
        if method == "yield_curve" and "payoff" in sc:
            key = (
                f"Payoff ${sc['payoff']} in {sc['years']} years "
                f"vs price ${sc.get('price', val.get('inputs', {}).get('price', '?'))}"
            )
        elif "growth_y1_5" in sc:
            key = bridge_key_plain(sc)
        else:
            key = notes or case
        rows.append(
            f"| {case.capitalize()}{suffix} | {method_label(method)} | {key} | "
            f"**{pct}%** per year | {bar} |"
        )

    for ov in val.get("overlay_results") or []:
        case = ov.get("case", "Overlay")
        m = ov.get("method", "overlay")
        key = ov.get("key_inputs", "")[:70]
        if ov.get("display"):
            ret_cell = f"**{ov['display']}**"
        elif ov.get("return_pct") is not None:
            ret_cell = f"**{format_overlay_return_pct(ov['return_pct'])}** p.a."
        else:
            ret_cell = "—"
        bar = bridge_bar(ov.get("return_pct"), stance_gate=ov.get("stance_gate", False))
        rows.append(f"| {case} | {m} | {key} | {ret_cell} | {bar} |")
    return "\n".join(rows)


def assumption_ledger(val: dict) -> str:
    method = val.get("method", "full")
    inputs = val.get("inputs", {})
    rows = [
        "| # | Assumption | Value | Source or judgment |",
        "|---|------------|-------|-------------------|",
    ]
    n = 1
    price = inputs.get("price", "?")
    src = inputs.get("price_source", "market")
    rows.append(f"| {n} | Price today | **${price}** | {src} |")
    n += 1

    if method == "proof_first_automated":
        comps = (val.get("component_valuation_results") or {}).get("additive_components") or []
        proof = comps[0].get("calculation_proof") if comps else {}
        for inp in proof.get("inputs") or []:
            label = inp.get("label") or inp.get("id", "")
            value = inp.get("value")
            unit = inp.get("unit") or ""
            loc = (inp.get("source") or {}).get("locator") or (inp.get("source") or {}).get("ref", "filing")
            if value is None:
                continue
            if unit == "USD millions":
                cell = f"**${value:,.0f}M**"
            elif unit == "million shares":
                cell = f"**{value:.1f}M**"
            elif unit == "shares":
                cell = f"**{value:,.0f}**"
            else:
                cell = f"**{value}**"
            rows.append(f"| {n} | {label} | {cell} | {loc} |")
            n += 1
        for ass in proof.get("assumptions") or []:
            label = ass.get("label") or ass.get("id", "")
            base = (ass.get("values") or {}).get("base")
            if base is None:
                continue
            unit = ass.get("unit") or ""
            rationale = ass.get("rationale") or "[Assumption]"
            if unit == "ratio":
                cell = f"**{base * 100:.1f}%**"
            elif unit == "multiple":
                cell = f"**{base} times**"
            else:
                cell = f"**{base}**"
            rows.append(f"| {n} | {label} | {cell} | {rationale} |")
            n += 1
        horizon = (val.get("valuation_methodology") or {}).get("horizon_years", LAWRENCE_HORIZON_YEARS)
        rows.append(
            f"| {n} | Time horizon | **{horizon} years** | "
            f"{horizon}-year owner-cash model in calculation proof |"
        )
        return "\n".join(rows)

    if method == "yield_curve":
        base = val.get("scenarios", {}).get("base", {})
        payoff = base.get("payoff")
        years = base.get("years")
        book = inputs.get("book_per_share")
        if book:
            rows.append(f"| {n} | GAAP book per share | **${book}** | Filing equity ÷ shares |")
            n += 1
        if payoff is not None:
            rows.append(
                f"| {n} | Payoff price (Year {years}) | **${payoff}** | Sum of parts / catalyst path in IRR steps |"
            )
            n += 1
        if years:
            rows.append(
                f"| {n} | Horizon (years) | **{years}** | Model choice in valuation.json (not company guidance) |"
            )
            n += 1
        sotp = base.get("sotp_build", {})
        for line in sotp.get("lines", []):
            if line.get("id") == "book":
                continue
            uplift = line.get("uplift_per_share", 0)
            if uplift:
                rows.append(
                    f"| {n} | {line.get('label', line.get('id'))} uplift | **+${uplift}/sh** | {line.get('math', '[Assumption]')} |"
                )
                n += 1
        return "\n".join(rows)

    if method in ("full", "scenario"):
        book = inputs.get("book_per_share")
        if book and val.get("valuation_mode") == "optionality":
            caveat = inputs.get("book_per_share_caveat", "GAAP book; not fair-value floor")
            rows.append(f"| {n} | GAAP book per share | **${book}** | {caveat} |")
            n += 1
        fcf = inputs.get("fcf_per_share") or inputs.get("per_share")
        fcf_src = inputs.get("fcf_source") or inputs.get("per_share_source", "normalization")
        if fcf is not None:
            rows.append(
                f"| {n} | Starting free cash flow per share | **${fcf}** | {fcf_src} |"
            )
            n += 1
        arch = (val.get("classification_inputs") or {}).get("archetype")
        cycle = (val.get("classification_inputs") or {}).get("cycle")
        norm = inputs.get("normalization_note")
        if arch == "croupier" and (cycle or norm):
            rows.append(
                f"| {n} | Cycle adjustment (starting cash) | **{cycle or 'see note'}** | {norm or '[Assumption]'} |"
            )
            n += 1
        ge = val.get("growth_explanation") or {}
        theory_label = ge.get("theory_label")
        base = val.get("scenarios", {}).get("base", {})
        if base.get("growth_y1_5") is not None:
            g1 = base.get("growth_y1_5")
            src = base.get("notes") or (f"Growth theory: {theory_label}" if theory_label else "[Assumption]")
            rows.append(
                f"| {n} | Growth in years 1 through 5 | **{g1*100:.1f}%** per year | {src} |"
            )
            n += 1
            g2 = base.get("growth_y6_10")
            if g2 is not None:
                rows.append(
                    f"| {n} | Growth in years 6 through {LAWRENCE_HORIZON_YEARS} | **{g2*100:.1f}%** per year | Scenario base |"
                )
                n += 1
        ex = base.get("exit_pfcf_y10") or base.get("exit_multiple")
        if ex is not None:
            rows.append(
                f"| {n} | Selling multiple in year 10 | **{ex} times cash flow** | Scenario base |"
            )
            n += 1
        rows.append(
            f"| {n} | Time horizon | **{LAWRENCE_HORIZON_YEARS} years** | "
            f"{LAWRENCE_HORIZON_YEARS}-year owner-cash model |"
        )
        n += 1
        ai = val.get("ai_overlay") or {}
        bull = ai.get("ai_inflection_bull") or {}
        if bull.get("fcf_per_share_y0") is not None:
            rows.append(
                f"| {n} | AI inflection FCF₀ (sensitivity) | **${bull['fcf_per_share_y0']}/sh** | {bull.get('fcf_y0_note', '[Assumption]')} |"
            )
            n += 1
            if bull.get("computed_return_pct") is not None:
                rows.append(
                    f"| {n} | AI inflection implied return | **{bull['computed_return_pct']}%** | `marvin_valuation.py` overlay |"
                )
                n += 1
        stress = ai.get("capex_stress_2026") or {}
        if stress.get("implied_fcf_per_share") is not None:
            rows.append(
                f"| {n} | Capex stress Y0 FCF | **${stress['implied_fcf_per_share']}/sh** | {stress.get('capex_source', 'mgmt guide')} |"
            )
            n += 1
        blend = val.get("estimates", {}).get("blended_best")
        if blend:
            rows.append(
                f"| {n} | Blended owner cash | **${blend.get('per_share')}** | {blend.get('weights', 'external_view_blend')} |"
            )
    return "\n".join(rows)


def format_overlay_return_pct(pct: float | int | None) -> str:
    if pct is None:
        return "n/a"
    if isinstance(pct, (int, float)) and abs(pct) < 0.05:
        return f"~{pct:.2f}%"
    return f"{pct}%"


def growth_explanation_stress_block(val: dict) -> str:
    """Render Popper/Deutsch growth stress test from valuation.json growth_explanation."""
    ge = val.get("growth_explanation") or {}
    if not ge.get("theory_label"):
        return ""
    fa = ge.get("falsifier_adjusted") or {}
    base = val.get("scenarios", {}).get("base", {})
    g1 = fa.get("y1_5") if fa.get("y1_5") is not None else base.get("growth_y1_5")
    g2 = fa.get("y6_10") if fa.get("y6_10") is not None else base.get("growth_y6_10")
    if g1 is None:
        return ""
    g1_pct = g1 * 100
    g2_pct = (g2 or 0) * 100
    status = ge.get("status", "partial")
    lines = [
        "### Growth explanation stress test (Popper / Deutsch)",
        "",
        "| Field | Value |",
        "|-------|-------|",
        f"| Growth assumption under test | Years 1–5: **{g1_pct:.1f}%**; years 6–{LAWRENCE_HORIZON_YEARS}: **{g2_pct:.1f}%** (falsifier-adjusted base) |",
        f"| Theory name | {ge.get('theory_label', '')} |",
        f"| Status | **{status}** |",
        "",
    ]
    if ge.get("problem_situation"):
        lines += [f"**Problem situation:** {ge['problem_situation']}", ""]
    mechs = ge.get("mechanisms") or []
    if mechs:
        lines += [
            "#### Explanatory theory (why this growth rate)",
            "",
            "| # | Mechanism | Causal chain (plain English) | Filing / evidence | Hard to vary? |",
            "|---|-----------|------------------------------|-------------------|---------------|",
        ]
        for i, m in enumerate(mechs, 1):
            lines.append(
                f"| {i} | {m.get('id', '')} | {m.get('chain', '')[:120]} | `{m.get('evidence', '')[:60]}` | {m.get('hard_to_vary', '')} |"
            )
        lines.append("")
    preds = ge.get("risky_predictions") or []
    if preds:
        lines += [
            "#### Risky predictions (Popper)",
            "",
            "| # | Prediction | By when | If false → |",
            "|---|------------|---------|------------|",
        ]
        for i, p in enumerate(preds, 1):
            lines.append(f"| {i} | {p.get('text', '')[:100]} | {p.get('by', '')} | {p.get('falsifier_action', '')[:80]} |")
        lines.append("")
    fals = ge.get("falsifiers") or []
    if fals:
        lines += [
            "#### Falsifiers (what would refute the theory)",
            "",
            "| # | Observation | Effect on growth assumption |",
            "|---|-------------|----------------------------|",
        ]
        for i, f in enumerate(fals, 1):
            lines.append(f"| {i} | {f.get('observation', '')[:100]} | {f.get('action', '')[:80]} |")
        lines.append("")
    banned = ge.get("ad_hoc_rescue_banned") or []
    if banned:
        lines += ["#### Ad hoc rescue watch (Popper)", ""]
        for b in banned:
            lines.append(f"- {b}")
        lines.append("")
    dc = ge.get("deutsch_checks") or {}
    if dc:
        def yn(v: object) -> str:
            return "yes" if v is True else ("no" if v is False else str(v))
        lines += [
            "#### Deutsch checks",
            "",
            "| Check | Pass? |",
            "|-------|-------|",
            f"| Hard to vary | {yn(dc.get('hard_to_vary'))} |",
            f"| Reach | {yn(dc.get('reach'))} |",
            f"| Falsifiable | {yn(dc.get('falsifiable'))} |",
            f"| Not instrumentalist | {yn(dc.get('not_instrumentalist'))} |",
            "",
        ]
    excluded = ge.get("excluded_from_base") or []
    if excluded:
        lines += ["**Excluded from base growth:**"]
        for ex in excluded:
            item = str(ex.get("item", "")).replace("\u2014", ":")
            treat = str(ex.get("treatment", "")).replace("\u2014", ":")
            lines.append(f"- {item}: {treat}")
        lines.append("")
    return "\n".join(lines)


def extract_preserved_block(preserved: str | None, heading: str) -> str | None:
    """Keep narrative blocks (segment build, segment IRR steps) across refresh."""
    if not preserved:
        return None
    pat = re.compile(rf"({re.escape(heading)}.*?)(?=\n#### |\n### |\n\*\*Upside / downside|\n## |\Z)", re.DOTALL | re.IGNORECASE)
    m = pat.search(preserved)
    if m and len(m.group(1).strip()) > 80:
        return m.group(1).strip()
    return None


def segment_build_section(val: dict, preserved: str | None) -> str:
    """Render ### Segment cash-flow build from valuation.json or preserved markdown."""
    kept = extract_preserved_block(preserved, "### Segment cash-flow build")
    if kept:
        return kept
    build = val.get("segment_build") or {}
    if not build.get("segments"):
        return ""
    recon = build.get("reconciliation") or {}
    disc = recon.get("explicit_discount_rate_pct") or (build.get("discount_rate_explicit", 0.1) * 100)
    sum_pv = recon.get("sum_pv_per_share_at_explicit_discount") or recon.get("sum_pv_per_share_at_10pct")
    implied = recon.get("implied_business_return_pct")
    ai = (val.get("ai_overlay") or {}).get("ai_inflection_bull") or {}
    ai_irr = ai.get("computed_return_pct")
    lawrence = recon.get("lawrence_base_irr_pct") or (val.get("results") or {}).get("base", {}).get("return_pct")

    lines = [
        "### Segment cash-flow build (Speedwell / Hohn overlay)",
        "",
        "| # | Segment / option | Owner cash Y0 ($/sh) | Growth Y1–5 / Y6–10 | Exit × Y10 | PV @ {:.0f}% ($/sh) | Source |".format(disc),
        "|---|------------------|----------------------|---------------------|------------|-----------------|--------|",
    ]
    n = 1
    for seg in build.get("segments", []):
        g1 = seg.get("growth_y1_5", 0) * 100
        g2 = seg.get("growth_y6_10", 0) * 100
        ex = seg.get("exit_pfcf_y10", "?")
        pv = seg.get("pv_per_share_at_10pct") or seg.get("pv_per_share_at_explicit_discount")
        pv_s = f"~${pv:.0f}" if pv is not None else "—"
        f0 = seg.get("owner_cash_y0_per_share")
        f0_s = f"${f0:.2f}" if f0 is not None else "—"
        lines.append(
            f"| {n} | {seg.get('label', seg.get('id', 'Segment'))} | {f0_s} | "
            f"{g1:.0f}% / {g2:.0f}% | {ex}× | {pv_s} | {seg.get('owner_cash_y0_source', seg.get('notes', ''))[:40]} |"
        )
        n += 1
    for opt in build.get("options", []):
        drag = opt.get("annual_drag_per_share")
        pv = opt.get("pv_drag_per_share_at_10pct")
        drag_s = f"(${drag:.2f})/yr drag" if drag is not None else "—"
        pv_s = f"~(${abs(pv):.0f})" if pv is not None and pv < 0 else (f"~${pv:.0f}" if pv is not None else "—")
        lines.append(
            f"| {n} | {opt.get('label', opt.get('id', 'Option'))} | {drag_s} | — | $0 | {pv_s} | {opt.get('notes', '')[:40]} |"
        )
        n += 1
    corp = build.get("corporate_drag") or {}
    if corp.get("alphabet_level_drag_per_share") is not None:
        drag = corp["alphabet_level_drag_per_share"]
        pv = corp.get("pv_drag_per_share_at_10pct")
        pv_s = f"~(${abs(pv):.0f})" if pv is not None and pv < 0 else "—"
        lines.append(
            f"| {n} | Alphabet-level | (${drag:.2f})/yr drag | — | $0 | {pv_s} | {corp.get('notes', '')[:40]} |"
        )

    footer = f"**Sum PV/sh @ {disc:.0f}%:** **${sum_pv}**" if sum_pv is not None else ""
    if ai_irr is not None:
        footer += f" · **AI inflection (normalized ${ai.get('fcf_per_share_y0', '?')} FCF₀):** **{ai_irr}%** {RETURN_LABEL}"
    if lawrence is not None:
        footer += f" · **Lawrence base:** **{lawrence}%**"
    lines += ["", footer, ""]

    seg_irr = extract_preserved_block(preserved, "#### Segment IRR arithmetic")
    if seg_irr:
        lines.append(seg_irr)
    elif sum_pv is not None:
        price = (val.get("inputs") or {}).get("price", "?")
        imp_disp = format_overlay_return_pct(implied) if implied is not None else "—"
        lines += [
            "#### Segment IRR arithmetic (show your work)",
            "",
            f"**Step 1–5:** Segment owner-cash from `valuation.json`; drags burdened; sum PV @ {disc:.0f}% = **${sum_pv}/sh** vs P₀ **${price}** → implied segment return **{imp_disp}** (`overlay_results`).",
            "",
        ]
    return "\n".join(lines)


SEGMENT_MAP_HEADING = "#### Segment map (filings)"
AI_INFRA_HEADING = "#### AI infrastructure — what the valuation captures vs gaps"
THEMATIC_CONTEXT_HEADING = "#### Thematic context"
INSIDER_CONVICTION_HEADING = "#### Insider conviction"


def extract_thematic_narrative(source: str | None) -> str | None:
    """Keep Marvin narrative prose between heading and table/disclaimer on refresh."""
    if not source:
        return None
    pat = re.compile(
        rf"{re.escape(THEMATIC_CONTEXT_HEADING)}\s*\n+(.*?)(?=\n> |\n\| Indicator|\n\|[- ]|#### |### |\n## |\Z)",
        re.DOTALL | re.IGNORECASE,
    )
    m = pat.search(source)
    if m and len(m.group(1).strip()) > 40:
        text = m.group(1).strip()
        if text.startswith("> "):
            return None
        return text
    return None


def extract_insider_narrative(source: str | None) -> str | None:
    """Keep Marvin narrative prose between heading and disclaimer/table on refresh."""
    if not source:
        return None
    pat = re.compile(
        rf"{re.escape(INSIDER_CONVICTION_HEADING)}\s*\n+(.*?)(?=\n> |\n\| Insider|\n\|[- ]|#### |### |\n## |\Z)",
        re.DOTALL | re.IGNORECASE,
    )
    m = pat.search(source)
    if m and len(m.group(1).strip()) > 40:
        text = m.group(1).strip()
        if text.startswith("> "):
            return None
        return text
    return None


def insider_conviction_business_block(val: dict, body: str | None) -> str:
    """Business-section insider conviction from valuation.json insider_signal."""
    sig = val.get("insider_signal") or {}
    if not sig or sig.get("ics") is None:
        return ""
    narrative = extract_insider_narrative(body)
    tilt = (sig.get("scenario_confidence") or {}).get("tilted") or {}
    priors = (sig.get("scenario_confidence") or {}).get("priors") or {}
    lines = [INSIDER_CONVICTION_HEADING, ""]
    if narrative:
        lines.append(narrative)
        lines.append("")
    lines.append(f"> {sig.get('disclaimer', 'Context only. Not in Lawrence base IRR.')}")
    lines += [
        "",
        f"**Insider Conviction Score (ICS):** {sig.get('ics')} ({sig.get('band')}) · "
        f"**Bull case support:** {sig.get('bull_case_support', 'none')} · "
        f"**In base IRR:** {'yes [HUMAN REVIEW]' if sig.get('in_base_irr') else 'no (context)'}",
        "",
        "| Scenario | Prior weight | Tilted weight |",
        "|----------|--------------|---------------|",
    ]
    for key in ("bear", "base", "bull"):
        p = priors.get(key)
        t = tilt.get(key)
        ps = f"{100 * float(p):.0f}%" if isinstance(p, (int, float)) else "n/a"
        ts = f"{100 * float(t):.0f}%" if isinstance(t, (int, float)) else "n/a"
        lines.append(f"| {key.title()} | {ps} | {ts} |")
    lines += [
        "",
        "| Insider | Date | Shares | Price | Value |",
        "|---------|------|--------|-------|-------|",
    ]
    for row in sig.get("top_buys") or []:
        lines.append(
            f"| {row.get('insider', '')} | {row.get('date', '')} | "
            f"{row.get('shares', '')} | ${row.get('price', '')} | ${row.get('value_usd', '')} |"
        )
    hooks = sig.get("narrative_hooks") or []
    if hooks:
        lines += ["", "**Hooks:** " + "; ".join(hooks)]
    lines.append("")
    return "\n".join(lines)


def thematic_context_business_block(val: dict, body: str | None) -> str:
    """Business-section thematic context table from valuation.json context_overlay."""
    overlay = val.get("context_overlay") or {}
    themes = overlay.get("themes") or []
    if not themes:
        return ""
    narrative = extract_thematic_narrative(body)
    lines = [THEMATIC_CONTEXT_HEADING, ""]
    if narrative:
        lines.append(narrative)
        lines.append("")
    lines.append(f"> {overlay.get('disclaimer', 'Context only. Not in Lawrence base IRR.')}")
    lines += [
        "",
        "| Indicator | Latest | As of | YoY | Direction | In base IRR? |",
        "|-----------|--------|-------|-----|-----------|--------------|",
    ]
    for theme in themes:
        for ind in theme.get("indicators") or []:
            yoy = f"{ind['yoy_pct']:+.1f}%" if isinstance(ind.get("yoy_pct"), (int, float)) else "n/a"
            latest = ind.get("latest")
            latest_s = f"{latest}" if latest is not None else "n/a"
            if ind.get("stale"):
                latest_s += " (stale)"
            base = "yes [HUMAN REVIEW]" if ind.get("in_base_irr") else "no (context)"
            lines.append(
                f"| {ind.get('label', ind.get('id', ''))} | {latest_s} | "
                f"{ind.get('as_of') or 'n/a'} | {yoy} | {ind.get('direction', 'flat')} | {base} |"
            )
    peer = overlay.get("peer_context")
    if peer:
        lines += [
            "",
            f"**Peer cluster:** `{peer.get('cluster_id')}` ({', '.join(peer.get('tickers') or [])}) — context only.",
        ]
    lines.append("")
    return "\n".join(lines)


CRYPTO_CONTEXT_HEADING = "#### Bitcoin economics — model coverage"
STABLECOIN_CONTEXT_HEADING = "#### Stablecoin economics — model coverage"


def crypto_context_business_block(val: dict) -> str:
    overlay = val.get("btc_overlay") or {}
    themes = overlay.get("themes") or []
    if not themes:
        return ""
    exposure = overlay.get("crypto_exposure", "treasury")
    heading = (
        STABLECOIN_CONTEXT_HEADING if exposure == "stablecoin" else CRYPTO_CONTEXT_HEADING
    )
    lines = [heading, ""]
    lines.append(f"> {overlay.get('disclaimer', 'Context only. Not in Lawrence base IRR.')}")
    lines += [
        "",
        f"**Exposure type:** {exposure}",
        "",
        "| Indicator | Latest | As of | YoY | Direction | In base IRR? |",
        "|-----------|--------|-------|-----|-----------|--------------|",
    ]
    for theme in themes:
        for ind in theme.get("indicators") or []:
            yoy = f"{ind['yoy_pct']:+.1f}%" if isinstance(ind.get("yoy_pct"), (int, float)) else "n/a"
            latest = ind.get("latest")
            latest_s = f"{latest}" if latest is not None else "fetch failed"
            if ind.get("stale") and latest is None:
                latest_s = "fetch failed (stale)"
            lines.append(
                f"| {ind.get('label', ind.get('id', ''))} | {latest_s} | "
                f"{ind.get('as_of') or 'n/a'} | {yoy} | {ind.get('direction', 'flat')} | no (context) |"
            )
    lines.append("")
    return "\n".join(lines)


def segment_map_business_block(val: dict, preserved: str | None) -> str:
    """Business-section segment table from valuation.json (hyperscalers)."""
    kept = extract_preserved_block(preserved, SEGMENT_MAP_HEADING)
    if kept:
        return kept
    build = val.get("segment_build") or {}
    segments = build.get("segments") or []
    if not segments:
        return ""
    lines = [
        SEGMENT_MAP_HEADING,
        "",
        f"Segment economics as of **{build.get('as_of', val.get('as_of', '—'))}** — see `valuation.json` → `segment_build`:",
        "",
        "| Segment / option | Owner cash Y0 ($/sh) | Growth Y1–5 / Y6–10 | Base-case treatment |",
        "|------------------|----------------------|---------------------|---------------------|",
    ]
    for seg in segments:
        y0 = seg.get("owner_cash_y0_per_share")
        y0_s = f"**${y0:.2f}**" if y0 is not None else "—"
        g1 = seg.get("growth_y1_5", 0) * 100
        g2 = seg.get("growth_y6_10", 0) * 100
        notes = (seg.get("notes") or seg.get("owner_cash_y0_source") or "")[:80]
        lines.append(
            f"| **{seg.get('label', seg.get('id', 'Segment'))}** | {y0_s} | "
            f"**{g1:.0f}%** / **{g2:.0f}%** | {notes} |"
        )
    for opt in build.get("options") or []:
        drag = opt.get("annual_drag_per_share")
        drag_s = f"(${abs(drag):.2f})/yr drag" if drag else "$0"
        lines.append(
            f"| **{opt.get('label', opt.get('id', 'Option'))}** | {drag_s} | — | "
            f"{(opt.get('notes') or 'Option; $0 terminal in base')[:80]} |"
        )
    corp = build.get("corporate_drag") or {}
    if corp.get("alphabet_level_drag_per_share") is not None:
        drag = corp["alphabet_level_drag_per_share"]
        lines.append(
            f"| **Corporate / Alphabet-level** | (${drag:.2f})/yr drag | — | "
            f"{(corp.get('notes') or '')[:80]} |"
        )
    recon = build.get("reconciliation") or {}
    if recon.get("sum_pv_per_share_at_explicit_discount") is not None:
        lines += [
            "",
            f"**Segment sum PV:** **${recon['sum_pv_per_share_at_explicit_discount']}/sh** "
            f"@ {recon.get('explicit_discount_rate_pct', 10):.0f}% · implied return "
            f"**{format_overlay_return_pct(recon.get('implied_business_return_pct'))}** "
            f"(`overlay_results`).",
        ]
    return "\n".join(lines)


def ai_infrastructure_business_block(val: dict, ticker: str, preserved: str | None) -> str:
    """Business-section AI coverage table from ai_overlay."""
    kept = extract_preserved_block(preserved, AI_INFRA_HEADING)
    if kept:
        return kept
    ai = val.get("ai_overlay") or {}
    if not ai:
        return ""
    in_model = ai.get("in_model") or {}
    gaps = ai.get("not_in_model_requires_refresh") or []
    stress = ai.get("capex_stress_2026") or {}
    bull = ai.get("ai_inflection_bull") or {}
    base_pct = (val.get("results") or {}).get("base", {}).get("return_pct")
    fcf = (val.get("inputs") or {}).get("fcf_per_share")
    lines = [
        AI_INFRA_HEADING,
        "",
        f"**Status:** {ai.get('status', 'partial')}. Lawrence base IRR **{base_pct}%** uses "
        f"**FY owner cash ${fcf}/sh** unless noted — AI themes below are **partially** in scenarios.",
        "",
        "| Theme | In filings / overlay | In current math |",
        "|-------|----------------------|-----------------|",
    ]
    for k, v in in_model.items():
        lines.append(f"| **{k.replace('_', ' ').title()}** | {v} | See scenarios / segment build |")
    for gap in gaps[:6]:
        lines.append(f"| **Gap** | {gap} | **Not modeled** |")
    if stress.get("implied_fcf_per_share") is not None:
        lines.append(
            f"| **Capex stress (2026)** | OCF ~${stress.get('ocf_bn_assumption')}B, "
            f"capex ~${stress.get('capex_bn')}B | Implied **${stress['implied_fcf_per_share']}/sh** FCF — "
            "illustrative, not stance gate |"
        )
    lines.append("")
    if bull.get("computed_return_pct") is not None:
        y0 = bull.get("fcf_per_share_y0", "?")
        lines.append(
            f"**Bull AI path** (`ai_overlay.ai_inflection_bull`): sensitivity "
            f"**{bull['computed_return_pct']}%** per year at **${y0}** normalized FCF/sh — "
            "**not** the stance gate."
        )
    lines.append("")
    lines.append(
        f"**[HUMAN REVIEW]:** Refresh after next 10-K/10-Q; run "
        f"`python _system/scripts/marvin_valuation.py --ticker {ticker} --write`."
    )
    return "\n".join(lines)


def inject_before_marker(body: str, marker: str, block: str) -> str:
    if not block.strip():
        return body
    if marker in body:
        return body.replace(marker, block.strip() + "\n\n" + marker, 1)
    return body.rstrip() + "\n\n" + block.strip() + "\n"


def section_body_empty(body: str, heading: str) -> bool:
    """True if heading exists but has no content before the next #### or ##."""
    pat = re.compile(
        rf"{re.escape(heading)}\s*\n+(?=####|\n---|\n## |\*\*Disruption|\Z)",
        re.IGNORECASE,
    )
    if pat.search(body):
        return True
    # Heading followed only by horizontal rule before next section
    pat2 = re.compile(
        rf"{re.escape(heading)}\s*\n+---\s*\n+(?=## |\Z)",
        re.IGNORECASE,
    )
    if pat2.search(body):
        return True
    # normalize_section_body strips trailing ---; heading may sit at EOF with no body
    pat3 = re.compile(rf"{re.escape(heading)}\s*\Z", re.IGNORECASE)
    return bool(pat3.search(body))


def replace_h4_section(body: str, heading: str, new_block: str) -> str:
    """Replace a #### section through the next ####, ##, **Disruption, or EOF."""
    if not new_block.strip():
        return body
    esc = re.escape(heading)
    pat = re.compile(
        rf"({esc}\s*\n)(.*?)(?=\n#### |\n## |\n\*\*Disruption|\Z)",
        re.IGNORECASE | re.DOTALL,
    )
    if pat.search(body):
        return pat.sub(lambda m: new_block.rstrip() + "\n\n", body, count=1)
    return body


def option_scan_block(val: dict) -> str:
    rows = val.get("option_scan") or []
    if not rows:
        return ""
    lines = [
        "#### Option scan",
        "",
        "| # | Question | Answer | Treatment | Evidence |",
        "|---|----------|--------|-----------|----------|",
    ]
    for r in rows:
        qn = r.get("q", "")
        q = (r.get("question") or "")[:70]
        lines.append(
            f"| {qn} | {q} | {r.get('answer', '')} | {r.get('treatment', '')} | "
            f"{(r.get('evidence') or '')[:80]} |"
        )
    return "\n".join(lines)


def look_through_block(val: dict, ticker: str) -> str:
    base = (val.get("scenarios") or {}).get("base", {})
    sotp = base.get("sotp_build") or {}
    lines_data = sotp.get("lines") or []
    nav = val.get("nav_overlay") or {}
    inputs = val.get("inputs") or {}
    if not lines_data and not nav:
        return ""
    lines = [
        "#### Look-through snapshot",
        "",
        "| Piece | Carrying / GAAP | Economic value (if different) | Driver |",
        "|-------|-----------------|-------------------------------|--------|",
    ]
    for row in lines_data:
        if row.get("id") == "book":
            gaap = row.get("gaap_per_share")
            lines.append(
                f"| {row.get('label', 'Book')} | **${gaap}/sh** | Anchor | Filing equity ÷ shares |"
            )
        elif row.get("uplift_per_share"):
            uplift = row.get("uplift_per_share")
            lines.append(
                f"| {row.get('label', row.get('id', ''))} | In book or $0 | **+${uplift}/sh** uplift | "
                f"{(row.get('math') or '[Assumption]')[:60]} |"
            )
    if nav.get("overlay_nav_per_share"):
        lines.append(
            f"| NAV overlay (fair value) | GAAP **${nav.get('gaap_book_per_share', inputs.get('book_per_share', '?'))}/sh** | "
            f"**~${nav['overlay_nav_per_share']}/sh** | {nav.get('notes', 'nav_overlay')[:60]} |"
        )
    lines.append("")
    return "\n".join(lines)


def sotp_nav_block(val: dict) -> str:
    base = (val.get("scenarios") or {}).get("base", {})
    sotp = base.get("sotp_build") or {}
    lines_data = sotp.get("lines") or []
    payoff = base.get("payoff") or sotp.get("year5_economic_nav_per_share")
    if not lines_data or payoff is None:
        return ""
    anchor = next((l.get("gaap_per_share") for l in lines_data if l.get("id") == "book"), None)
    lines = [
        "#### Sum-of-parts or NAV",
        "",
        f"**Base case Year-{base.get('years', sotp.get('years', 5))} economic NAV = ${payoff}/sh**. "
        "See Valuation & IRR assumption ledger.",
        "",
        "| Piece | $/sh (today) | + Incremental uplift | In book? |",
        "|-------|--------------|----------------------|----------|",
    ]
    running = anchor or 0
    for row in lines_data:
        if row.get("id") == "book":
            lines.append(f"| {row.get('label', 'Anchor')} | **${row.get('gaap_per_share')}** | n/a | Yes |")
            continue
        uplift = row.get("uplift_per_share") or 0
        if uplift:
            lines.append(
                f"| {row.get('label', row.get('id', ''))} | (in anchor) | **+${uplift}** | Partial |"
            )
            running += uplift
    lines += [
        "",
        f"**Sum check:** **${_round_payoff(running)}** ≈ **${payoff}** payoff (`valuation.json` → `scenarios.base.sotp_build`).",
        "",
    ]
    return "\n".join(lines)


def _round_payoff(x: float) -> str:
    return f"{x:.2f}".rstrip("0").rstrip(".")


def catalyst_path_block(val: dict) -> str:
    paths = val.get("catalyst_paths") or []
    if not paths:
        base = (val.get("scenarios") or {}).get("base", {})
        if base.get("notes"):
            paths = [{"event": "Base catalyst", "timing": f"{base.get('years', '?')} years", "impact": base["notes"]}]
        else:
            return ""
    lines = ["#### Catalyst path", ""]
    for p in paths:
        lines.append(f"- **{p.get('event', 'Event')}** ({p.get('timing', 'timing TBD')}): {p.get('impact', '')}")
    lines.append("")
    return "\n".join(lines)


def optionality_overlay_block(val: dict) -> str:
    arch = (val.get("classification_inputs") or {}).get("archetype", "")
    mode = val.get("valuation_mode", "")
    nav = val.get("nav_overlay") or {}
    gate = val.get("optionality_gate") or {}
    if arch not in ("optionality", "holding_co") and mode != "optionality":
        return ""
    base_pct = primary_irr_pct(val)
    lines = [
        "### Optionality overlay",
        "",
        f"**Primary metric (stance gate):** Lawrence base **{base_pct}%** per year. "
        f"Overlay framework: **{gate.get('framework', 'optionality')}** · floor_pass **{gate.get('floor_pass', 'n/a')}**.",
        "",
    ]
    if nav.get("overlay_nav_per_share"):
        lines.append(
            f"**NAV overlay:** economic **~${nav['overlay_nav_per_share']}/sh** vs GAAP book "
            f"**${nav.get('gaap_book_per_share', '?')}/sh** — not used as silent Lawrence FCF."
        )
        lines.append("")
    bull = (val.get("results") or {}).get("bull", {}).get("return_pct")
    if bull is not None:
        lines.append(f"**Bull sensitivity:** **{bull}%** per year (`scenarios.bull`).")
        lines.append("")
    return "\n".join(lines)


def inject_optionality_sections(body: str, val: dict, ticker: str) -> str:
    """Fill option scan / look-through / SOTP / catalyst blocks from valuation.json."""
    import sys

    _scripts = Path(__file__).resolve().parent
    if str(_scripts) not in sys.path:
        sys.path.insert(0, str(_scripts))
    from optionality_evidence_common import has_evidence_refresh_config

    force_sotp = has_evidence_refresh_config(val)
    if not re.search(r"#### Option scan\b", body, re.I):
        block = option_scan_block(val)
        if block:
            if "#### Thesis pillars" in body:
                body = inject_before_marker(body, "#### Thesis pillars", block)
            elif "#### Operating snapshot" in body:
                body = inject_before_marker(body, "#### Operating snapshot", block)
            else:
                body = body.rstrip() + "\n\n" + block
    elif section_body_empty(body, "#### Option scan"):
        body = re.sub(
            r"#### Option scan\s*\n+(?=####|\n---|\n## |\*\*Disruption|\Z)",
            option_scan_block(val) + "\n\n",
            body,
            count=1,
            flags=re.I,
        )

    for heading, builder in (
        ("#### Look-through snapshot", lambda: look_through_block(val, ticker)),
        ("#### Sum-of-parts or NAV", lambda: sotp_nav_block(val)),
        ("#### Catalyst path", lambda: catalyst_path_block(val)),
    ):
        block = builder()
        if not block:
            continue
        if force_sotp and heading.lower() in body.lower():
            body = replace_h4_section(body, heading, block)
            continue
        if heading.lower() not in body.lower():
            if "#### Look-through snapshot" in body or "#### Sum-of-parts" in body:
                body = body.rstrip() + "\n\n" + block
            elif "**Disruption" in body:
                body = inject_before_marker(body, "**Disruption", block)
            else:
                body = body.rstrip() + "\n\n" + block
        elif section_body_empty(body, heading):
            for pat in (
                rf"{re.escape(heading)}\s*\n+(?:---\s*\n+)?(?=## |\Z)",
                rf"{re.escape(heading)}\s*\n+(?=####|\n---|\n## |\*\*Disruption|\Z)",
                rf"{re.escape(heading)}\s*\Z",
            ):
                body, n = re.subn(pat, block + "\n", body, count=1, flags=re.I)
                if n:
                    break
    return body


def yield_curve_sotp_irr(val: dict, ticker: str) -> str:
    """Detailed yield_curve IRR when sotp_build lines exist."""
    method = val.get("method", "")
    if method != "yield_curve":
        return ""
    base = (val.get("scenarios") or {}).get("base", {})
    sotp = base.get("sotp_build") or {}
    lines_data = sotp.get("lines") or []
    if len(lines_data) < 2:
        return ""
    inputs = val.get("inputs") or {}
    price = inputs.get("price", 0)
    payoff = base.get("payoff", 0)
    years = base.get("years", 5)
    base_pct = primary_irr_pct(val)
    book = inputs.get("book_per_share") or next(
        (l.get("gaap_per_share") for l in lines_data if l.get("id") == "book"), None
    )

    out = [
        "#### IRR arithmetic (show your work)",
        "",
        f"**Base case** (dated payoff / sum-of-parts; `irr_method`: yield_curve). "
        f"Payoff **${payoff}** and horizon **{years} years** are model assumptions in `valuation.json`.",
        "",
        "**Step 1: Price today**",
        f"- **${price}** ({inputs.get('price_source', 'market')})",
        "",
    ]
    if book:
        if price < book:
            disc = (book - price) / book * 100
            out += [
                "**Step 2: Filing anchor (book)**",
                f"- Book **${book}/sh** · Price **{disc:.0f}%** below book",
                "",
            ]
        else:
            prem = (price - book) / book * 100 if book else 0
            out += [
                "**Step 2: Filing anchor (book)**",
                f"- Book **${book}/sh** · Price **{prem:.0f}%** above book (option priced in)",
                "",
            ]
    out += [
        "**Step 3: Build payoff by adding incremental lines**",
        "",
        "```",
        f"  {book or price}  anchor (GAAP book or price)",
    ]
    running = book or price
    for row in lines_data:
        if row.get("id") == "book":
            continue
        uplift = row.get("uplift_per_share") or 0
        if uplift:
            out.append(f"+ {uplift:>5}  {row.get('label', row.get('id', ''))[:50]}")
            running += uplift
    out += [
        "───────",
        f"  {payoff}  = base-case payoff per share",
        "```",
        "",
        f"Same build in `{ticker}/research/valuation.json` → `scenarios.base.sotp_build`.",
        "",
        f"**Step 4: Horizon: {years} years** (model choice; not company guidance)",
        "",
        "**Step 5: Total return**",
        f"- ${payoff} ÷ ${price} − 1 = **{(payoff / price - 1) * 100:.1f}%** total" if price else "",
        "",
        "**Step 6: Annualized return**",
        f"- (${payoff} ÷ ${price})^(1/{years}) − 1 = **{base_pct}%** per year"
        if price and payoff and base_pct is not None
        else "",
    ]
    bear = (val.get("scenarios") or {}).get("bear", {})
    bull = (val.get("scenarios") or {}).get("bull", {})
    if bear.get("payoff") and bear.get("return_pct") is not None:
        out.append(
            f"\n**Bear (payoff ${bear['payoff']}):** **{bear['return_pct']}%**/year — {bear.get('notes', '')[:80]}"
        )
    if bull.get("payoff") and bull.get("return_pct") is not None:
        out.append(
            f"**Bull (payoff ${bull['payoff']}):** **{bull['return_pct']}%**/year — {bull.get('notes', '')[:80]}"
        )
    return "\n".join(out)


def enrich_business_moat(body: str, val: dict, ticker: str, preserved: str | None) -> str:
    body = strip_valuation_from_business(body)
    body = inject_optionality_sections(body, val, ticker)
    if not re.search(r"#### Segment map\b", body, re.I) and val.get("segment_build", {}).get("segments"):
        seg = segment_map_business_block(val, preserved)
        if "#### Thesis pillars" in body:
            body = inject_before_marker(body, "#### Thesis pillars", seg)
        else:
            body = inject_before_marker(body, "**Disruption", seg) if "**Disruption" in body else body.rstrip() + "\n\n" + seg
    if not re.search(r"#### AI infrastructure\b", body, re.I) and val.get("ai_overlay"):
        ai = ai_infrastructure_business_block(val, ticker, preserved)
        if "#### Thesis pillars" in body:
            body = inject_before_marker(body, "#### Thesis pillars", ai)
        elif "**Disruption" in body:
            body = inject_before_marker(body, "**Disruption", ai)
        else:
            body = body.rstrip() + "\n\n" + ai
    if val.get("context_overlay", {}).get("themes"):
        thematic = thematic_context_business_block(val, body)
        if thematic and not re.search(r"#### Thematic context\b", body, re.I):
            if "#### Thesis pillars" in body:
                body = inject_before_marker(body, "#### Thesis pillars", thematic)
            elif "**Disruption" in body:
                body = inject_before_marker(body, "**Disruption", thematic)
            else:
                body = body.rstrip() + "\n\n" + thematic
        elif thematic and re.search(r"#### Thematic context\b", body, re.I):
            body = re.sub(
                r"#### Thematic context.*?(?=\n#### |\n### |\n\*\*Upside / downside|\n## |\Z)",
                thematic.rstrip() + "\n",
                body,
                count=1,
                flags=re.DOTALL | re.IGNORECASE,
            )
    if val.get("btc_overlay", {}).get("themes"):
        crypto = crypto_context_business_block(val)
        crypto_pat = r"#### (?:Bitcoin|Stablecoin) economics — model coverage"
        if crypto and not re.search(crypto_pat, body, re.I):
            if "#### Thesis pillars" in body:
                body = inject_before_marker(body, "#### Thesis pillars", crypto)
            elif "**Disruption" in body:
                body = inject_before_marker(body, "**Disruption", crypto)
            else:
                body = body.rstrip() + "\n\n" + crypto
        elif crypto and re.search(crypto_pat, body, re.I):
            body = re.sub(
                crypto_pat + r".*?(?=\n#### |\n### |\n\*\*Upside / downside|\n## |\Z)",
                crypto.rstrip() + "\n",
                body,
                count=1,
                flags=re.DOTALL | re.IGNORECASE,
            )
    if val.get("insider_signal", {}).get("ics") is not None:
        insider = insider_conviction_business_block(val, body)
        if insider and not re.search(r"#### Insider conviction\b", body, re.I):
            if "#### Thesis pillars" in body:
                body = inject_before_marker(body, "#### Thesis pillars", insider)
            elif "**Disruption" in body:
                body = inject_before_marker(body, "**Disruption", insider)
            else:
                body = body.rstrip() + "\n\n" + insider
        elif insider and re.search(r"#### Insider conviction\b", body, re.I):
            body = re.sub(
                r"#### Insider conviction.*?(?=\n#### |\n### |\n\*\*Upside / downside|\n## |\Z)",
                insider.rstrip() + "\n",
                body,
                count=1,
                flags=re.DOTALL | re.IGNORECASE,
            )
    bull = (val.get("ai_overlay") or {}).get("ai_inflection_bull") or {}
    ai_irr = bull.get("computed_return_pct")
    if ai_irr is not None:
        body = body.replace(
            "**Bull AI path** in `valuation.json` → `ai_overlay.ai_inflection_bull` is a **placeholder** "
            "($8/sh normalized FCF, higher growth) for sensitivity only — **not computed IRR yet**; "
            "needs a filing-backed bridge from Cloud OI, depreciation on new capex, and TPU revenue if disclosed.",
            f"**Bull AI path** (`ai_overlay.ai_inflection_bull`): sensitivity **{ai_irr}%** {RETURN_LABEL} at normalized "
            f"${bull.get('fcf_per_share_y0', 8)}/sh FCF₀ — "
            "**not** the stance gate; needs filing-backed bridge from Cloud OI, capex normalization, and TPU revenue if disclosed.",
        )
    return body


def _contract_valuation_block(authority: dict) -> str:
    if authority.get("authority_level") == "legacy_reference":
        return ""
    values = authority.get("value_per_share") or {}
    returns = authority.get("return_range_pct") or {}
    route = authority.get("profile_label") or authority.get("profile_id") or "routing pending"
    return "\n".join([
        "",
        "#### Contract valuation arithmetic (show your work)",
        "",
        f"**Power Zone:** {route}",
        f"**Contract status:** {authority.get('contract_status')}",
        f"**Low/base/high value per share:** {values.get('low')} / {values.get('base')} / {values.get('high')}",
        f"**Low/base/high annualized return at price:** {returns.get('low')}% / {returns.get('base')}% / {returns.get('high')}%",
        "",
        "The component ownership map, causal assumptions, evidence tiers, overlap controls, and falsifiers are recorded in `valuation_contract.json`. Legacy Marvin/Lawrence scenario arithmetic is retained only as a migration cross-check.",
    ])


def irr_arithmetic(val: dict, ticker: str, preserved: str | None) -> str:
    base_pct = primary_irr_pct(val)
    authority = resolve_authority(ROOT / ticker / "research", val)
    contract_suffix = _contract_valuation_block(authority)
    sotp_irr = yield_curve_sotp_irr(val, ticker)
    if sotp_irr:
        return sotp_irr + contract_suffix

    if preserved and "#### IRR arithmetic" in preserved:
        m = re.search(
            r"#### IRR arithmetic \(show your work\)(.*?)(?=\n\*\*Upside / downside|\n## |\n#### Contract valuation|\Z)",
            preserved,
            re.DOTALL | re.IGNORECASE,
        )
        if m and len(m.group(1).strip()) > 200:
            body = m.group(1).strip()
            stale = re.search(
                r"falsifier-adjusted|Popper|Deutsch|Theory-implied",
                body,
                re.I,
            )
            pct_in_body = re.findall(r"\*\*(-?\d+\.?\d*)%?\*\*/yr", body)
            pct_mismatch = base_pct is not None and pct_in_body and not any(
                abs(float(p) - float(base_pct)) < 0.15 for p in pct_in_body
            )
            if (
                not stale
                and not re.search(r"P₀|FCF₀|Cash₀/sh|g1=|exit=\d", body)
                and not pct_mismatch
            ):
                return "#### IRR arithmetic (show your work)\n\n" + body + contract_suffix

    method = val.get("method", "full")
    inputs = val.get("inputs", {})
    price = inputs.get("price", 0)
    base_pct = primary_irr_pct(val)
    lines = ["#### IRR arithmetic (show your work)", ""]

    if method == "yield_curve":
        base = val.get("scenarios", {}).get("base", {})
        payoff = base.get("payoff", 0)
        years = base.get("years", 5)
        book = inputs.get("book_per_share")
        lines += [
            f"**Base case** (`irr_method`: {method}). See assumption ledger and `sotp_build` in valuation.json.",
            "",
            "**Step 1: Price today**",
            f"- **${price}** ({inputs.get('price_source', 'market')})",
            "",
        ]
        if book:
            disc = (book - price) / book * 100 if book else 0
            lines += [
                "**Step 2: Filing anchor (book)**",
                f"- Book **${book}/sh** · Price is **{disc:.0f}%** below book" if price < book else f"- Book **${book}/sh**",
                "",
            ]
        lines += [
            "**Step 3: Payoff (sum of parts)**",
            f"- Build incremental lines in assumption ledger; payoff **${payoff}** must equal running sum.",
            "",
            f"**Step 4: Horizon: {years} years**",
            "- Model choice in valuation.json; not company guidance.",
            "",
            "**Step 5: Total return**",
            f"- ${payoff} ÷ ${price} − 1 = **{(payoff/price - 1)*100:.1f}%** total" if price else "",
            "",
            "**Step 6: Annualized IRR**",
            f"- (${payoff} ÷ ${price})^(1/{years}) − 1 = **{base_pct}%**/yr"
            if price and payoff and base_pct
            else "",
        ]
        return "\n".join(lines) + contract_suffix

    if method in ("full", "scenario"):
        fcf = inputs.get("fcf_per_share") or inputs.get("per_share")
        g1, g2, ex = growth_rates_for_irr(val)
        scenario_base = (val.get("scenarios") or {}).get("base", {}).get("return_pct")
        synthesis_pct = (val.get("implied_return") or {}).get("synthesis_pct")
        lines += [
            "How we calculated the annual return (base case). Verify with "
            f"`python _system/scripts/marvin_valuation.py --ticker {ticker}`",
            "",
            f"1. **Price today:** **${price}**",
            f"2. **Starting free cash flow per share:** **${fcf}** "
            f"({inputs.get('per_share_source', inputs.get('fcf_source', ''))})",
            f"3. **Growth in years 1–5:** **{g1*100:.1f}%** per year · **years 6–{LAWRENCE_HORIZON_YEARS}:** **{g2*100:.1f}%** per year",
            f"4. **Selling multiple in year 10:** **{ex} times** year-10 cash flow",
        ]
        if scenario_base is not None:
            lines.append(
                f"5. **Lawrence scenario return at today's price:** **{scenario_base}%** per year over "
                f"{LAWRENCE_HORIZON_YEARS} years (`scenarios.base`)"
            )
        if synthesis_pct is not None and synthesis_pct != scenario_base:
            lines.append(
                f"6. **Total synthesis return:** **{synthesis_pct}%** per year (weighted blend in `valuation.json` → `synthesis`)"
            )
        elif base_pct is not None:
            lines.append(
                f"5. **Annual return at today's price:** **{base_pct}%** per year over {LAWRENCE_HORIZON_YEARS} years "
                "(`implied_return.base_pct` in `valuation.json`)"
            )
        return "\n".join(lines) + contract_suffix

    lines.append("IRR pending. See [HUMAN REVIEW].")
    return "\n".join(lines) + contract_suffix


def book_estimate_section(ticker: str) -> str:
    """Render ### Current book value estimate from book_estimate.json."""
    be_path = ROOT / ticker / "research" / "book_estimate.json"
    if not be_path.exists():
        return ""
    be = json.loads(be_path.read_text(encoding="utf-8"))
    anchor = be.get("filing_anchor") or {}
    summary = be.get("summary") or {}
    comp = be.get("price_comparison") or {}
    lines = [
        "### Current book value estimate (mark-to-market)",
        "",
        f"**Filed book:** **${anchor.get('filed_book_per_share', '?')}/sh** "
        f"(period end **{anchor.get('period_end', '?')}**, `{anchor.get('source', '')}`).",
        "",
        "| Line | Filing ($M) | Current ($M) | Δ ($M) | Δ $/sh | Source |",
        "|------|-------------|--------------|--------|--------|--------|",
    ]
    for row in be.get("lines") or []:
        lines.append(
            f"| {row.get('label', row.get('id', ''))[:40]} | "
            f"{row.get('filing_value_m', '—')} | {row.get('current_value_m', '—')} | "
            f"{row.get('delta_m', '—')} | "
            f"{(row.get('delta_m', 0) / anchor.get('shares', 1) * 1e6) if row.get('delta_m') and anchor.get('shares') else '—'} | "
            f"{(row.get('price_source', '') or row.get('source', ''))[:30]} |"
        )
    lines += [
        "",
        f"**Current best estimate:** **${summary.get('current_book_per_share', '?')}/sh** "
        f"(Δ **${summary.get('delta_per_share', '?')}/sh**, **{summary.get('delta_pct_of_filed_book', '?')}%** vs filed).",
        "",
        f"**Price comparison:** market **${comp.get('market_price', '?')}** · "
        f"discount to filed book **{comp.get('discount_to_filed_book_pct', '?')}%** · "
        f"discount to current estimate **{comp.get('discount_to_current_estimate_pct', '?')}%**.",
        "",
    ]
    flags = be.get("staleness_flags") or []
    if flags:
        lines.append("**Staleness / gaps:** " + "; ".join(flags[:5]))
        lines.append("")
    return "\n".join(lines)


def build_valuation_section(ticker: str, val: dict, preserved_val: str | None) -> str:
    import sys

    scripts = Path(__file__).resolve().parent
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from optionality_evidence_common import synthesis_in_dive
    from valuation_synthesis import synthesis_markdown

    inputs = val.get("inputs", {})
    price = inputs.get("price", "?")
    src = inputs.get("price_source", "")
    method = val.get("method", "full")
    base_pct = primary_irr_pct(val) or "?"
    seg_body = segment_build_section(val, preserved_val)
    irr_body = irr_arithmetic(val, ticker, preserved_val)
    upside = ""
    if preserved_val:
        um = re.search(r"\*\*Upside / downside from price:\*\*.*", preserved_val)
        if um:
            upside = um.group(0)
    if not upside:
        upside = f"**Upside / downside from price:** Base IRR **{base_pct}%** at **${price}**; see bear/bull in `valuation.json` scenarios."

    ret = ""
    headline = primary_irr_pct(val) or base_pct
    fcf = inputs.get("fcf_per_share") or inputs.get("per_share")
    if fcf:
        ret = (
            f"**Returns statement:** We expect **{headline}%** per year over {LAWRENCE_HORIZON_YEARS} years "
            f"at **~${price}** on **${fcf}/sh** starting owner cash."
        )
    else:
        ret = f"**Returns statement:** We expect **{headline}%** per year at **${price}**."

    parts = [
        "## Valuation & IRR (assumption ledger)",
        "",
        f"**Price today:** **${price}** ({src})  ",
        f"**Method:** {method_label(method)} (`{method}`) · **Base annual return:** **{base_pct}%** per year · `{ticker}/research/valuation.json`",
        "",
        "### Assumption ledger (base case)",
        "",
        assumption_ledger(val),
    ]
    if seg_body:
        parts += ["", seg_body]
    parts += [
        "",
        irr_body,
        "",
    ]
    if synthesis_in_dive(val):
        syn_body = synthesis_markdown(val)
        if syn_body:
            parts += [syn_body, ""]
    be_body = book_estimate_section(ticker)
    if be_body and "### Current book value estimate" not in (preserved_val or ""):
        parts += [be_body, ""]
    parts += [upside, ""]
    if not synthesis_in_dive(val):
        parts.append(ret)
    return "\n\n".join(parts)


def refresh_ticker(ticker: str, out_date: str) -> Path | None:
    research = ROOT / ticker / "research"
    if not research.is_dir():
        print(f"SKIP {ticker}: no research/")
        return None
    src = latest_dive(research)
    if not src:
        print(f"SKIP {ticker}: no deep dive")
        return None
    val = load_valuation(ticker)
    if not val:
        print(f"SKIP {ticker}: no valuation.json")
        return None

    text = src.read_text(encoding="utf-8", errors="ignore")
    sections = split_sections(text)
    preserved_val = sections.get("## Valuation & IRR (assumption ledger)") or None
    if not preserved_val and VALUATION_SECTION.search(text):
        preserved_val = text[VALUATION_SECTION.search(text).start() :]
    biz = sections.get("## Business & moat", "")
    _, biz_irr = extract_irr_block(biz)
    if biz_irr:
        preserved_val = (preserved_val or "") + "\n\n" + biz_irr

    # Header through risks
    overview_keys = [
        "## What this business is",
        "## Why the market might be wrong",
        "## Executive summary",
        "## Primary sources reviewed",
        "## Business & moat",
        "## Approved Substack context",
        "## Blended estimate (best judgment)",
        "## Blended estimate (best judgment)".replace("(best judgment)", ""),  # noqa — fallback
        "## Payoff & return",
        "## Risks & inversion",
    ]
    out_parts: list[str] = []
    title_m = re.match(r"^#\s+.+", text)
    header = text[: text.find("---", 0)].strip() if "---" in text[:800] else title_m.group(0) if title_m else f"# {ticker}: Company Deep Dive"
    if "**Date:**" not in header:
        header = f"# {ticker}: Company Deep Dive\n\n**Date:** {out_date}\n**Agent:** Marvin"
    else:
        header = re.sub(r"\*\*Date:\*\*\s*\S+", f"**Date:** {out_date}", header, count=1)
    digest = filing_digest_path(ticker)
    if digest and "**Filing evidence:**" not in header:
        header += f"\n**Filing evidence:** `{digest}`"
    if "**Third party:**" not in header:
        header += f"\n**Third party:** `{ticker}/third-party-analyses/references.md` · `pending.md`"
    out_parts.append(header)
    out_parts.append("\n---\n")

    for key in overview_keys:
        if key not in sections:
            continue
        body = sections[key]
        if key == "## Business & moat":
            body = enrich_business_moat(body, val, ticker, preserved_val)
        if key == "## Executive summary":
            body = patch_exec_summary_irr(body, val)
        if key in ("## Blended estimate (best judgment)", "## Blended estimate"):
            rendered = blended_estimate_section(val)
            if rendered:
                lines = rendered.splitlines()
                body = "\n".join(lines[1:]).strip() if lines and lines[0].startswith("## ") else rendered
            else:
                body = patch_blended_estimate_irr(body, val)
        if key == "## Primary sources reviewed":
            body = inject_hk_primary_sources(body, ticker)
        if key == "## Payoff & return":
            body = re.sub(
                r"#### Valuation bridge.*?#### ",
                "#### ",
                body,
                flags=re.DOTALL,
            )
            overlay = optionality_overlay_block(val)
            if overlay and "### Optionality overlay" not in body:
                body = body.rstrip() + "\n\n" + overlay
            body = patch_payoff_expected_return(body, val)
            body = patch_payoff_returns_statement(body, val)
            body = re.sub(
                r"### Stance proposal.*?(?=\n---|\n## |\Z)",
                stance_proposal_block(val) + "\n**Scenarios and every IRR assumption:** see **## Valuation & IRR (assumption ledger)** and `valuation.json`.\n",
                body,
                flags=re.DOTALL,
            )
        out_parts.append(key)
        out_parts.append(body)
        out_parts.append("\n---\n")

    out_parts.append(build_valuation_section(ticker, val, preserved_val or text))
    out_parts.append("\n---\n")

    for key in ("## Classification", "## Terms (optional)", "## [HUMAN REVIEW]", "## [PROPOSED MEMORY]"):
        if key in sections:
            out_parts.append(key)
            block = patch_classification_stance(sections[key], val) if key == "## Classification" else sections[key]
            out_parts.append(block)
            out_parts.append("\n")

    pending = scan_pending_third_party(ticker)
    write_pending_md(ticker, pending)

    out_path = research / f"deep_dive_{out_date}.md"
    final_text = patch_horizon_year_prose("\n".join(out_parts).strip() + "\n")
    out_path.write_text(final_text, encoding="utf-8")
    print(f"OK {ticker} -> {out_path.relative_to(ROOT)}")
    return out_path


def tickers_from_registry() -> list[str]:
    reg = ROOT / "_system" / "portfolio" / "registry.json"
    if reg.exists():
        data = json.loads(reg.read_text(encoding="utf-8"))
        holdings = data.get("holdings", {})
        if isinstance(holdings, dict):
            return sorted(holdings.keys())
        return [h["ticker"] for h in holdings]
    return [
        d.name
        for d in sorted(ROOT.iterdir())
        if d.is_dir() and (d / "research").is_dir() and not d.name.startswith(("_", "."))
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker", nargs="?", help="Ticker symbol")
    parser.add_argument("--all", action="store_true", help="Refresh all holdings")
    parser.add_argument("--date", default=date.today().isoformat(), help="Output date YYYY-MM-DD")
    args = parser.parse_args()
    if args.all:
        for t in tickers_from_registry():
            refresh_ticker(t, args.date)
    elif args.ticker:
        refresh_ticker(args.ticker.upper(), args.date)
    else:
        parser.error("Provide TICKER or --all")


if __name__ == "__main__":
    main()
