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
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APPROVED_THIRD_PARTY = ROOT / "_system" / "frameworks" / "third_party_sources.md"
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
        parts[title] = text[start:end].strip()
    return parts


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
        res = results.get(case, {})
        pct = res.get("return_pct", "—")
        bar = bridge_bar(pct if isinstance(pct, (int, float)) else None)
        notes = sc.get("notes", "")[:60]
        if method == "yield_curve" and "payoff" in sc:
            key = f"Payoff ${sc['payoff']} / {sc['years']}yr @ ${sc.get('price', val.get('inputs', {}).get('price', '?'))}"
        elif "growth_y1_5" in sc:
            key = f"g1={sc['growth_y1_5']*100:.0f}% g2={sc.get('growth_y6_10',0)*100:.0f}% exit={sc.get('exit_pfcf_y10', sc.get('exit_multiple','?'))}×"
        else:
            key = notes or case
        rows.append(f"| {case.capitalize()} | {method} | {key} | **{pct}%** p.a. | {bar} |")

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
    rows.append(f"| {n} | Price today (P₀) | **${price}** | {src} |")
    n += 1

    if method == "yield_curve" or val.get("valuation_mode") == "optionality":
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
        fcf = inputs.get("fcf_per_share") or inputs.get("per_share")
        fcf_src = inputs.get("fcf_source") or inputs.get("per_share_source", "normalization")
        if fcf is not None:
            rows.append(f"| {n} | Owner cash / FCF₀ per share | **${fcf}** | {fcf_src} |")
            n += 1
        base = val.get("scenarios", {}).get("base", {})
        g1 = base.get("growth_y1_5")
        g2 = base.get("growth_y6_10")
        ex = base.get("exit_pfcf_y10") or base.get("exit_multiple")
        if g1 is not None:
            rows.append(f"| {n} | Growth years 1–5 | **{g1*100:.1f}%/yr** | {base.get('notes', '[Assumption]')} |")
            n += 1
        if g2 is not None:
            rows.append(f"| {n} | Growth years 6–10 | **{g2*100:.1f}%/yr** | Scenario base |")
            n += 1
        if ex is not None:
            rows.append(f"| {n} | Exit multiple year 10 | **{ex}×** | Scenario base |")
            n += 1
        rows.append(f"| {n} | Horizon | **10 years** | Lawrence full / scenario method |")
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
        recon = (val.get("segment_build") or {}).get("reconciliation") or {}
        if recon.get("sum_pv_per_share_at_explicit_discount") is not None:
            rows.append(
                f"| {n} | Segment sum PV | **${recon['sum_pv_per_share_at_explicit_discount']}/sh** | @ {recon.get('explicit_discount_rate_pct', 10)}% discount |"
            )
            n += 1
        if recon.get("implied_business_return_pct") is not None:
            rows.append(
                f"| {n} | Segment implied return | **{format_overlay_return_pct(recon['implied_business_return_pct'])}** | reverse DCF (segment PV = P₀) |"
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
        return "—"
    if isinstance(pct, (int, float)) and abs(pct) < 0.05:
        return f"~{pct:.2f}%"
    return f"{pct}%"


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
        footer += f" · **AI inflection (normalized ${ai.get('fcf_per_share_y0', '?')} FCF₀):** **{ai_irr}%** 10yr IRR"
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


def irr_arithmetic(val: dict, ticker: str, preserved: str | None) -> str:
    if preserved and "#### IRR arithmetic" in preserved:
        m = re.search(
            r"#### IRR arithmetic \(show your work\)(.*?)(?=\n\*\*Upside / downside|\n## |\Z)",
            preserved,
            re.DOTALL | re.IGNORECASE,
        )
        if m and len(m.group(1).strip()) > 200:
            return "#### IRR arithmetic (show your work)\n\n" + m.group(1).strip()

    method = val.get("method", "full")
    inputs = val.get("inputs", {})
    price = inputs.get("price", 0)
    base_pct = val.get("implied_return", {}).get("base_pct") or val.get("results", {}).get("base", {}).get("return_pct")
    lines = ["#### IRR arithmetic (show your work)", ""]

    if method == "yield_curve" or val.get("valuation_mode") == "optionality":
        base = val.get("scenarios", {}).get("base", {})
        payoff = base.get("payoff", 0)
        years = base.get("years", 5)
        book = inputs.get("book_per_share")
        lines += [
            f"**Base case** (`irr_method`: {method}). See assumption ledger and `sotp_build` in valuation.json.",
            "",
            "**Step 1 — Price today**",
            f"- **${price}** ({inputs.get('price_source', 'market')})",
            "",
        ]
        if book:
            disc = (book - price) / book * 100 if book else 0
            lines += [
                "**Step 2 — Filing anchor (book)**",
                f"- Book **${book}/sh** · Price is **{disc:.0f}%** below book" if price < book else f"- Book **${book}/sh**",
                "",
            ]
        lines += [
            "**Step 3 — Payoff (sum of parts)**",
            f"- Build incremental lines in assumption ledger; payoff **${payoff}** must equal running sum.",
            "",
            f"**Step 4 — Horizon: {years} years**",
            "- Model choice in valuation.json; not company guidance.",
            "",
            "**Step 5 — Total return**",
            f"- ${payoff} ÷ ${price} − 1 = **{(payoff/price - 1)*100:.1f}%** total" if price else "",
            "",
            "**Step 6 — Annualized IRR**",
            f"- (${payoff} ÷ ${price})^(1/{years}) − 1 = **{base_pct}%**/yr"
            if price and payoff and base_pct
            else "",
        ]
        return "\n".join(lines)

    if method in ("full", "scenario"):
        fcf = inputs.get("fcf_per_share") or inputs.get("per_share")
        base = val.get("scenarios", {}).get("base", {})
        g1 = base.get("growth_y1_5", 0.05)
        g2 = base.get("growth_y6_10", 0.03)
        ex = base.get("exit_pfcf_y10") or base.get("exit_multiple", 10)
        lines += [
            f"**Base case** — verify: `python _system/scripts/marvin_valuation.py --ticker {ticker}`",
            "",
            f"- P₀ = **${price}**",
            f"- Cash₀/sh = **${fcf}** ({inputs.get('per_share_source', inputs.get('fcf_source', ''))})",
            f"- Growth Y1–5 = **{g1*100:.1f}%/yr** · Y6–10 = **{g2*100:.1f}%/yr**",
            f"- Exit year 10 = **{ex}×**",
            f"- IRR = **{base_pct}%**/yr (10-year owner-cash stream in valuation.json)",
        ]
        return "\n".join(lines)

    lines.append("IRR pending — see [HUMAN REVIEW].")
    return "\n".join(lines)


def build_valuation_section(ticker: str, val: dict, preserved_val: str | None) -> str:
    inputs = val.get("inputs", {})
    price = inputs.get("price", "?")
    src = inputs.get("price_source", "")
    method = val.get("method", "full")
    base_pct = val.get("implied_return", {}).get("base_pct") or val.get("results", {}).get("base", {}).get("return_pct", "?")
    seg_body = segment_build_section(val, preserved_val)
    irr_body = irr_arithmetic(val, ticker, preserved_val)
    upside = ""
    if preserved_val:
        um = re.search(r"\*\*Upside / downside from price:\*\*.*", preserved_val)
        if um:
            upside = um.group(0)
    if not upside:
        upside = f"**Upside / downside from price:** Base IRR **{base_pct}%** at **${price}**; see bear/bull in bridge."

    ret = ""
    if preserved_val:
        rm = re.search(r"\*\*Returns statement:\*\*.*", preserved_val)
        if rm:
            ret = rm.group(0)
    if not ret:
        ret = f"**Returns statement:** We expect **{base_pct}%** per year (base case) at **${price}**."

    return "\n\n".join(
        [
            "## Valuation & IRR (assumption ledger)",
            "",
            f"**Price today:** **${price}** ({src})  ",
            f"**Method:** `{method}` · **Base IRR:** **{base_pct}%** · `{ticker}/research/valuation.json`",
            "",
            "### Valuation bridge",
            "",
            "| Case | Method | Key inputs | Implied return | vs ~15% bar |",
            "|------|--------|------------|----------------|-------------|",
            bridge_table(val),
            "",
            "### Assumption ledger (base case)",
            "",
            assumption_ledger(val),
            "",
            seg_body,
            "",
            irr_body,
            "",
            upside,
            "",
            ret,
        ]
    )


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
            body = strip_valuation_from_business(body)
            ai_irr = ((val.get("ai_overlay") or {}).get("ai_inflection_bull") or {}).get("computed_return_pct")
            if ai_irr is not None:
                body = body.replace(
                    "**Bull AI path** in `valuation.json` → `ai_overlay.ai_inflection_bull` is a **placeholder** "
                    "($8/sh normalized FCF, higher growth) for sensitivity only — **not computed IRR yet**; "
                    "needs a filing-backed bridge from Cloud OI, depreciation on new capex, and TPU revenue if disclosed.",
                    f"**Bull AI path** (`ai_overlay.ai_inflection_bull`): sensitivity **{ai_irr}%** 10yr IRR at normalized "
                    f"${(val.get('ai_overlay') or {}).get('ai_inflection_bull', {}).get('fcf_per_share_y0', 8)}/sh FCF₀ — "
                    "**not** the stance gate; needs filing-backed bridge from Cloud OI, capex normalization, and TPU revenue if disclosed.",
                )
        if key == "## Payoff & return":
            body = re.sub(
                r"#### Valuation bridge.*?#### ",
                "#### ",
                body,
                flags=re.DOTALL,
            )
            if "Valuation & IRR" not in body:
                body = re.sub(
                    r"(### Stance proposal.*?)$",
                    r"\1\n\n**Scenarios and every IRR assumption:** see **## Valuation & IRR (assumption ledger)** and `valuation.json`.\n",
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
            out_parts.append(sections[key])
            out_parts.append("\n")

    pending = scan_pending_third_party(ticker)
    write_pending_md(ticker, pending)

    out_path = research / f"deep_dive_{out_date}.md"
    out_path.write_text("\n".join(out_parts).strip() + "\n", encoding="utf-8")
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
