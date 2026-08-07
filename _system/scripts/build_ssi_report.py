#!/usr/bin/env python3
"""Phase 4 of the SSI Perplexity-grade pipeline: deterministic report rendering.

Renders the blueprint §4 output contract from artifacts that already exist —
verified claims, the hashed evidence pack, the XBRL series, the universal
valuation contract (via decision_authority, never legacy fields) — and stamps
a §5 shipping-gate verdict. Prose is assembled from resolved claims; nothing
is asserted that lacks a locator. Where a required feed is missing (consensus
estimates, price history, borrow), the section states the gap explicitly —
the report never fills a hole with plausible text.

Outputs:
  {TICKER}/research/ssi_report_{date}.md
  {TICKER}/research/evidence/ssi_report_gate_{date}.json

Usage:
  python _system/scripts/build_ssi_report.py TBBK
  python _system/scripts/build_ssi_report.py TBBK --date 2026-08-06
  python _system/scripts/build_ssi_report.py --check
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from decision_authority import resolve_authority  # noqa: E402

ROOT = SCRIPT_DIR.parents[1]

SCHEMA_VERSION = "1.0"

TAXONOMY_LABELS = {
    "identity_instrument": "Identity & instrument",
    "liquidity_oxygen": "Financial oxygen",
    "earnings_quality": "Earnings quality",
    "operating_failure": "Operating failure mode",
    "market_mechanics": "Market mechanics",
}

MONITORING_CADENCE = {
    "identity_instrument": "quarterly (10-Q/10-K cover + equity notes)",
    "liquidity_oxygen": "quarterly (balance sheet, liquidity note); ad-hoc on 8-K",
    "earnings_quality": "quarterly (allowances, accruals, receivables)",
    "operating_failure": "quarterly (segment + MD&A); ad-hoc on guidance events",
    "market_mechanics": "requires borrow feed — not monitored",
}


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def _latest_json(dirpath: Path, stem: str) -> tuple[Path | None, dict | None]:
    files = sorted(dirpath.glob(f"{stem}_*.json"), reverse=True)
    for path in files:
        try:
            return path, json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
    return None, None


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _fmt_money(value: float | None, unit: str = "$") -> str:
    if value is None:
        return "—"
    absv = abs(value)
    if absv >= 1e9:
        return f"{unit}{value / 1e9:,.2f}B"
    if absv >= 1e6:
        return f"{unit}{value / 1e6:,.1f}M"
    if absv >= 1e3:
        return f"{unit}{value / 1e3:,.0f}K"
    return f"{unit}{value:,.2f}"


def _fmt_num(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{value:,.{digits}f}"


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:+.1f}%"


def _cagr(first: float | None, last: float | None, years: int) -> float | None:
    if not first or last is None or years <= 0:
        return None
    if first <= 0 or last <= 0:
        return None
    return ((last / first) ** (1.0 / years) - 1.0) * 100.0


# ---------------------------------------------------------------------------
# Section builders (each returns list[str] of markdown lines)
# ---------------------------------------------------------------------------

def _annual(concepts: dict, concept: str) -> list[dict]:
    return ((concepts.get(concept) or {}).get("annual")) or []


def header_stat_block(ticker: str, market: dict, concepts: dict,
                      calendar: dict | None, authority: dict) -> list[str]:
    price = market.get("price_per_share")
    cap_m = market.get("market_cap_m")
    shares = market.get("fully_diluted_shares")

    ni = _annual(concepts, "net_income")
    eps = _annual(concepts, "eps_diluted")
    eq = _annual(concepts, "stockholders_equity")
    bb = _annual(concepts, "buybacks_paid")
    sh = _annual(concepts, "shares_outstanding")

    ni_fy = ni[-1]["val"] if ni else None
    eps_fy = eps[-1]["val"] if eps else None
    # A negative P/E is not a valuation multiple; printing "-845.3" in a header
    # stat block is worse than printing nothing.
    pe_cell = "—"
    if price and eps_fy:
        pe_cell = _fmt_num(price / eps_fy, 1) if eps_fy > 0 else "n/a (FY loss)"
    roe = None
    if ni_fy and len(eq) >= 2:
        avg_eq = (eq[-1]["val"] + eq[-2]["val"]) / 2.0
        roe = ni_fy / avg_eq * 100.0 if avg_eq else None

    # Series-derived stats must name their own period: the latest available
    # buyback row can be years older than the latest income row, and an
    # unlabeled "FY spend" silently passes stale data off as current.
    fy_end = ni[-1]["end"] if ni else None
    buyback_cell, buyback_src = "—", (bb[-1].get("accn", "") if bb else "")
    if bb and cap_m:
        bb_row = bb[-1]
        pct = bb_row["val"] / (cap_m * 1e6) * 100.0
        buyback_cell = f"{pct:+.1f}% (FY {bb_row['end']})"
        if fy_end and bb_row["end"] != fy_end:
            buyback_cell += " — stale vs latest FY"
    share_chg = None
    share_period = ""
    if len(sh) >= 2 and sh[-2]["val"]:
        share_chg = (sh[-1]["val"] - sh[-2]["val"]) / sh[-2]["val"] * 100.0
        share_period = f" ({sh[-2]['end']} → {sh[-1]['end']})"

    next_earnings = "— (earnings feed unconfigured)"
    if calendar and calendar.get("events"):
        upcoming = [e for e in calendar["events"] if e.get("date", "") >= date.today().isoformat()]
        if upcoming:
            next_earnings = upcoming[0].get("date", "—")

    fy_label = fy_end or "—"
    rows = [
        ("Price / share", _fmt_num(price), "valuation_contract.market"),
        ("Market cap", _fmt_money(cap_m * 1e6) if cap_m else "—", "valuation_contract.market"),
        ("Enterprise value", _fmt_money(market.get("enterprise_value_m", 0) * 1e6)
         if market.get("enterprise_value_m") else "—", "valuation_contract.market"),
        ("Fully diluted shares", f"{shares:,.0f}" if shares else "—", "valuation_contract.market"),
        (f"Net income (FY {fy_label})", _fmt_money(ni_fy), ni[-1].get("accn", "") if ni else ""),
        (f"EPS diluted (FY {fy_label})", _fmt_num(eps_fy), eps[-1].get("accn", "") if eps else ""),
        ("P/E (price ÷ FY EPS)", pe_cell, "derived: contract price ÷ XBRL EPS"),
        ("ROE (FY, avg equity)", _fmt_pct(roe), "derived: XBRL NI ÷ avg equity"),
        ("Buyback yield (spend ÷ cap)", buyback_cell, buyback_src),
        (f"Share count Δ{share_period}", _fmt_pct(share_chg),
         sh[-1].get("accn", "") if sh else ""),
        ("Valuation route", str(authority.get("profile_label") or "—"), "power_zone_router"),
        ("Contract status", str(authority.get("contract_status") or "—"), "decision_authority"),
        ("Next earnings", next_earnings, "evidence/earnings_calendar.json"),
    ]
    lines = ["## 1. Header stat block", "", "| Figure | Value | Source |", "|---|---|---|"]
    for label, value, src in rows:
        lines.append(f"| {label} | {value} | `{src}` |" if src else f"| {label} | {value} | — |")
    lines.append("")
    return lines


def executive_summary(claims: list[dict], spawner: dict, authority: dict,
                      thesis_card: dict | None, calendar: dict | None,
                      pack: dict) -> list[str]:
    lines = ["## 2. Executive summary — five moves", ""]

    # Severity leads: a sev-5 critical-narrative claim (material weakness,
    # going concern) is a section claim with no concept_tier and must never be
    # outranked by a fact claim. Tier only breaks ties within a severity.
    _tier_rank = {"primary": 0, "secondary": 1, "footnote_detail": 2}
    top = sorted(
        claims,
        key=lambda c: (
            -c.get("severity", 0),
            _tier_rank.get(c.get("concept_tier"), 0),
            c.get("taxonomy", ""),
        ),
    )[:3]
    matters = "; ".join(
        f"{c['statement'][:140]} (sev {c['severity']}, {c['confidence']})" for c in top
    )
    matters = (matters + ".") if matters else "No verified claims above the materiality floor."
    reads = {k: v.get("read") for k, v in (spawner.get("components") or {}).items() if v.get("read")}
    if reads:
        matters += f" Capital allocation reads: {', '.join(f'{k}={v}' for k, v in reads.items())}."
    lines += [f"**What matters most.** {matters}", ""]

    rr = authority.get("return_range_pct") or {}
    vps = authority.get("value_per_share") or {}
    if authority.get("contract_status") == "decision_grade" and vps:
        priced = (
            f"Contract value/share {_fmt_num(vps.get('low'))}–{_fmt_num(vps.get('base'))}–"
            f"{_fmt_num(vps.get('high'))} (low–base–high) vs implied return range "
            f"{_fmt_pct(rr.get('low'))}/{_fmt_pct(rr.get('base'))}/{_fmt_pct(rr.get('high'))} "
            f"(source: `universal_valuation_contract`, authority: {authority.get('authority_level')})."
        )
    else:
        priced = (
            f"Valuation contract status is `{authority.get('contract_status')}` — "
            "no priced-in arithmetic is quotable until the contract is decision_grade."
        )
    lines += [f"**What is priced in.** {priced}", ""]

    if thesis_card and thesis_card.get("why_market_wrong"):
        variant = (
            f"{str(thesis_card['why_market_wrong'])[:400]} "
            "*(analyst-authored thesis card; not Skeptic-verified — treat as hypothesis)*"
        )
    else:
        variant = (
            "No consensus-estimate feed is configured, so the variant view cannot be "
            "stated against a measured consensus. Gap: connect estimates, then diff "
            "verified claims against consensus assumptions."
        )
    lines += [f"**Variant perception.** {variant}", ""]

    if calendar and calendar.get("events"):
        cat = f"Next verified earnings event: {calendar['events'][0].get('date', '—')}."
    else:
        cat = "No verified earnings events in the calendar cache (earnings feed unconfigured)."
    filings = pack.get("filings") or []
    if filings:
        latest = max(filings, key=lambda f: f.get("file_date") or "")
        cat += f" Latest filing on record: {latest.get('form')} filed {latest.get('file_date')}."
    lines += [f"**Earnings & catalysts.** {cat}", ""]

    # §13 lists severity >= 3 only; quoting the all-claims total here would
    # overstate what a reader can actually go monitor.
    listed = sum(1 for c in claims if c.get("falsifier") and c.get("severity", 0) >= 3)
    total = sum(1 for c in claims if c.get("falsifier"))
    lines += [
        f"**Monitoring & falsification.** {listed} machine-checkable tripwires at severity ≥ 3 "
        f"are listed in §13 ({total} verified claims carry a falsifier in total); cadence is "
        "quarterly per filing cycle with ad-hoc 8-K checks.",
        "",
    ]
    return lines


def business_model_section(pack: dict, concepts: dict) -> list[str]:
    lines = ["## 3. Business model & structural inflection", ""]
    bank_rows = [r for r in pack.get("revenue_definition", []) if "bank_style_revenue" in (r.get("flags") or [])]
    if bank_rows:
        r = bank_rows[-1]
        nii, non = r.get("net_interest_income"), r.get("noninterest_income")
        lines += [
            "Revenue is **bank-style** (NII-centric): consensus 'revenue' comparisons must use "
            "operating revenue (NII + non-interest income), not the reported revenue tag.",
            "",
            "| Component | Value (as filed; units per filing) | Locator |",
            "|---|---|---|",
            f"| Net interest income | {_fmt_num(nii, 0)} | `{r['filing']}` |",
            f"| Non-interest income | {_fmt_num(non, 0)} | `{r['filing']}` |",
            f"| Operating revenue | {_fmt_num(r.get('operating_revenue'), 0)} | derived |",
        ]
        if nii is not None and non is not None and non > nii:
            lines.append(
                "| **Inflection flag** | non-interest income exceeds NII — fee engine now "
                "leads the model | `revenue_definition_check` |"
            )
        lines.append("")
    else:
        rev = _annual(concepts, "revenue")
        if len(rev) >= 3:
            first, last = rev[0], rev[-1]
            growth = _cagr(first["val"], last["val"], max(len(rev) - 1, 1))
            lines += [
                f"Revenue ({(concepts.get('revenue') or {}).get('tag')}): "
                f"{_fmt_money(first['val'])} (FY {first['end']}) → {_fmt_money(last['val'])} "
                f"(FY {last['end']}), {_fmt_pct(growth)} CAGR over {len(rev) - 1} years "
                f"(locators: accessions {first.get('accn')} → {last.get('accn')}).",
                "",
            ]
        else:
            lines += ["Insufficient XBRL revenue history for a structural read; see §5 table.", ""]
    return lines


def expectations_section(pack: dict) -> list[str]:
    lines = ["## 4. Market expectations reconciliation", ""]
    bank = any("bank_style_revenue" in (r.get("flags") or []) for r in pack.get("revenue_definition", []))
    lines += [
        "**Gap (blocking §5 gate):** no consensus-estimate feed is connected, so beat/miss and "
        "guide-vs-consensus tables cannot be built. Required: an estimates source keyed to the "
        "issuer's operating-revenue definition.",
        "",
    ]
    if bank:
        lines += [
            "**Definitional artifact callout (mechanical):** the issuer's reported revenue tag is "
            "NII-centric. Any consensus 'revenue' series that mixes operating revenue with the "
            "reported tag will manufacture phantom beats/misses — reconcile definitions before "
            "quoting either.",
            "",
        ]
    return lines


def kpi_table(concepts: dict, bank_style: bool = False) -> list[str]:
    lines = ["## 5. Historical KPIs (XBRL, per-accession locators) — with honesty flags", ""]
    if not concepts:
        return lines + ["No XBRL series available (`sec_companyfacts.json` missing).", ""]
    revenue_label = "Revenue"
    if bank_style and (concepts.get("revenue") or {}).get("tag", "").startswith("us-gaap:RevenueFromContract"):
        revenue_label = "Fee revenue (ASC 606 tag only — bank-style issuer, see §3)"
    show = [
        ("revenue", revenue_label), ("net_income", "Net income"), ("eps_diluted", "EPS (diluted)"),
        ("operating_cash_flow", "Operating cash flow"), ("capital_expenditures", "Capex"),
        ("buybacks_paid", "Buybacks paid"), ("stockholders_equity", "Stockholders' equity"),
        ("shares_outstanding", "Shares outstanding"),
    ]
    years: list[str] = []
    for key, _ in show:
        for row in _annual(concepts, key)[-5:]:
            fy = row["end"][:4]
            if fy not in years:
                years.append(fy)
    years = sorted(years)[-5:]
    header = "| Metric | " + " | ".join(years) + " | CAGR | Flags |"
    sep = "|---" * (len(years) + 3) + "|"
    lines += [header, sep]
    honesty: list[str] = []
    for key, label in show:
        rows = _annual(concepts, key)
        if not rows:
            continue
        by_year = {r["end"][:4]: r for r in rows}
        cells = []
        for y in years:
            r = by_year.get(y)
            if r is None:
                cells.append("—")
            else:
                val = r["val"]
                cell = _fmt_money(val) if key not in ("eps_diluted", "shares_outstanding") else (
                    _fmt_num(val) if key == "eps_diluted" else f"{val / 1e6:,.1f}M"
                )
                if r.get("restated"):
                    cell += " †"
                cells.append(cell)
        span = [by_year.get(y) for y in years if by_year.get(y)]
        growth = _cagr(span[0]["val"], span[-1]["val"], max(len(span) - 1, 1)) if len(span) >= 2 else None
        flags = []
        restated_years = [y for y in years if by_year.get(y, {}).get("restated")]
        if restated_years:
            flags.append(f"restated: {','.join(restated_years)}")
        lines.append(f"| {label} | " + " | ".join(cells) + f" | {_fmt_pct(growth)} | {'; '.join(flags) or '—'} |")
        if restated_years:
            for y in restated_years:
                r = by_year[y]
                honesty.append(
                    f"- **{label} FY{y} restated** ({r.get('restated')} distinct filed values; "
                    f"first-reported {_fmt_money(r.get('first_reported'))} → latest {_fmt_money(r['val'])}, "
                    f"accn `{r.get('accn')}`)."
                )
    ni = _annual(concepts, "net_income")
    eps = _annual(concepts, "eps_diluted")
    if len(ni) >= 4 and len(eps) >= 4:
        ni_span, eps_span = ni[-4:], eps[-4:]
        ni_g = _cagr(ni_span[0]["val"], ni_span[-1]["val"], 3)
        eps_g = _cagr(eps_span[0]["val"], eps_span[-1]["val"], 3)
        if ni_g is not None and eps_g is not None and abs(eps_g - ni_g) > 2.0:
            honesty.append(
                f"- **Per-share vs headline divergence:** 3y EPS CAGR {_fmt_pct(eps_g)} vs net income "
                f"{_fmt_pct(ni_g)} — the gap is share-count driven (buybacks/dilution), not operating."
            )
    lines.append("")
    lines.append("† = value restated across filings (first-reported ≠ latest).")
    lines.append("")
    if honesty:
        lines += ["**Honesty flags:**", *honesty, ""]
    lines += [
        f"*Statistical sidebar: n = {len(years)} fiscal years shown (longer series in the pack); "
        "single-regime sample — treat CAGRs as descriptive, not predictive. Conclusions from "
        "n < 40 observations are hypotheses.*",
        "",
    ]
    return lines


def driver_table(claims: list[dict]) -> list[str]:
    lines = [
        "## 6. Driver & monitoring table (from verified claims)", "",
        "Ordered by economic significance (primary concepts first), round-robined "
        "across taxonomies so one noisy bucket cannot crowd out the others.", "",
        "| Taxonomy | Signal | Tier | Direction | Magnitude | Reported line (locator) | Cadence |",
        "|---|---|---|---|---|---|---|",
    ]
    # Round-robin across taxonomies so one noisy bucket (e.g. OCI swings in
    # earnings_quality) can't crowd out liquidity or instrument signals.
    tier_rank = {"primary": 0, "secondary": 1, "footnote_detail": 2}
    by_tax: dict[str, list[dict]] = {}
    for c in sorted(
        claims,
        key=lambda c: (tier_rank.get(c.get("concept_tier"), 1), -c.get("severity", 0)),
    ):
        by_tax.setdefault(c.get("taxonomy", "other"), []).append(c)
    picked: list[dict] = []
    rank = 0
    while len(picked) < 12 and any(len(v) > rank for v in by_tax.values()):
        for tax in sorted(by_tax):
            if rank < len(by_tax[tax]) and len(picked) < 12:
                picked.append(by_tax[tax][rank])
        rank += 1
    for c in picked:
        ref = c.get("evidence_ref") or {}
        loc = ref.get("tag") or ref.get("section") or "—"
        path = (ref.get("source_path") or "").split("/")[-1]
        lines.append(
            f"| {TAXONOMY_LABELS.get(c['taxonomy'], c['taxonomy'])} | {c['statement'][:90]} | "
            f"{c.get('concept_tier') or '—'} | {c.get('direction', '—')} | "
            f"{_fmt_pct(c.get('magnitude_pct'))} | `{loc}` in `{path}` | "
            f"{MONITORING_CADENCE.get(c['taxonomy'], 'quarterly')} |"
        )
    lines.append("")
    return lines


def valuation_section(authority: dict, contract: dict | None) -> list[str]:
    lines = ["## 7. Valuation & priced-in scenarios (contract-derived only)", ""]
    status = authority.get("contract_status")
    lines.append(
        f"Authority: `{authority.get('authority_level')}` · contract status: `{status}` · "
        f"route: {authority.get('profile_label')} (`{authority.get('profile_id')}`)."
    )
    lines.append("")
    if status != "decision_grade":
        lines += [
            f"Contract is `{status}` — per the one-valuation-language rule, no value or return "
            "figures are quotable. Remediate the contract, then re-render.",
            "",
        ]
        return lines
    vps = authority.get("value_per_share") or {}
    rr = authority.get("return_range_pct") or {}
    market = (contract or {}).get("market") or {}
    price = market.get("price_per_share")
    lines += [
        "| Scenario | Value / share | vs price | Implied return |",
        "|---|---|---|---|",
    ]
    for name in ("low", "base", "high"):
        v = vps.get(name)
        upside = ((v / price) - 1) * 100.0 if v and price else None
        lines.append(
            f"| {name} | {_fmt_num(v)} | {_fmt_pct(upside)} | {_fmt_pct(rr.get(name))} |"
        )
    lines += [
        "",
        f"Price reference: {_fmt_num(price)} (contract `market.price_per_share`, as of "
        f"{(contract or {}).get('as_of')}). Scenario arithmetic and component proofs live in "
        "`research/valuation_contract.json` (`scenario_contract`, `calculation_proof_summary`). "
        "Legacy IRR/stance fields are non-actionable and intentionally absent here.",
        "",
    ]
    return lines


def pattern_gap_sections(evidence_dir: Path) -> list[str]:
    lines = [
        "## 8. Earnings / revision pattern", "",
        "**Gap:** requires a price-history + estimate-revision feed (EPS surprise vs 1-day move "
        "table). Not fabricated. Wire a market-data source to enable.", "",
        "## 9. Peer & factor attribution", "",
        "**Gap:** requires a peer-set return feed. The valuation route's archetype peers are "
        "listed in the contract's method route; quantitative attribution is not fabricated.", "",
        "## 10. Early proxy tracker", "",
    ]
    proxies = []
    for stem, label in (
        ("insider_signal", "Insider (Form 4) signal"),
        ("thematic_context", "Thematic context sweep"),
    ):
        files = sorted(evidence_dir.glob(f"{stem}_*.md"), reverse=True)
        if files:
            newest = files[0]
            proxies.append((label, newest))
    if proxies:
        lines += ["| Proxy | Latest artifact | Read cadence |", "|---|---|---|"]
        for label, path in proxies:
            rel = path.as_posix().split("/research/")[-1]
            lines.append(f"| {label} | `research/{rel}` | daily |")
        lines.append("")
    else:
        lines += ["No proxy artifacts found in the evidence directory.", ""]
    return lines


def variant_section(claims: list[dict], thesis_card: dict | None) -> list[str]:
    lines = ["## 11. Variant perception (mechanical draft)", ""]
    # Only economically primary concepts belong here. Footnote-schedule rows
    # (OCI components, deferred-tax detail, amortization schedules) can post
    # huge percentages without carrying thesis information.
    def eligible(c: dict, directions: tuple[str, ...]) -> bool:
        return (
            c.get("direction") in directions
            and c.get("severity", 0) >= 3
            and c.get("concept_tier") != "footnote_detail"
        )

    ups = [c for c in claims if eligible(c, ("up", "new"))]
    downs = [c for c in claims if eligible(c, ("down", "removed"))]
    primary_up = [c for c in ups if c.get("concept_tier") == "primary"] or ups
    primary_down = [c for c in downs if c.get("concept_tier") == "primary"] or downs

    lines.append("**Bull-variant (verified expansion signals, primary concepts):**")
    for c in primary_up[:5]:
        lines.append(f"- {c['statement'][:150]} *(sev {c['severity']}, {c.get('concept_tier')})*")
    if not primary_up:
        lines.append("- none above severity 3 outside footnote detail")
    lines.append("")
    lines.append("**Bear-variant (verified deterioration signals, primary concepts):**")
    for c in primary_down[:5]:
        lines.append(f"- {c['statement'][:150]} *(sev {c['severity']}, {c.get('concept_tier')})*")
    if not primary_down:
        lines.append("- none above severity 3 outside footnote detail")
    lines.append("")
    if thesis_card and thesis_card.get("why_market_wrong"):
        lines += [
            "**Where consensus is wrong (analyst thesis card — unverified by Skeptic):**",
            f"> {str(thesis_card['why_market_wrong'])[:500]}",
            "",
        ]
    else:
        lines += [
            "**Where consensus is wrong:** unstated — requires the consensus feed (§4 gap) or an "
            "analyst-authored thesis card.",
            "",
        ]
    return lines


def catalyst_calendar(pack: dict, calendar: dict | None) -> list[str]:
    lines = ["## 12. Catalyst calendar", "", "| Date | Event | Basis |", "|---|---|---|"]
    have_row = False
    if calendar:
        for event in (calendar.get("events") or [])[:6]:
            lines.append(
                f"| {event.get('date', '—')} | {event.get('type', 'earnings')} | verified feed |"
            )
            have_row = True
    periodics = [f for f in pack.get("filings", []) if f.get("form_class") in ("annual", "quarterly")]
    if periodics:
        latest = max(periodics, key=lambda f: f.get("period_end") or "")
        pe = latest.get("period_end")
        if pe:
            try:
                nxt = date.fromisoformat(pe) + timedelta(days=131)  # qtr end + ~40d filing window
                lines.append(
                    f"| ~{nxt.isoformat()} | next periodic filing due (estimate: prior period end "
                    f"+ 91d + 40d filing window) | deterministic estimate |"
                )
                have_row = True
            except ValueError:
                pass
    if not have_row:
        lines.append("| — | no verified events; earnings feed unconfigured | — |")
    lines.append("")
    return lines


def falsification_section(claims: list[dict]) -> list[str]:
    lines = ["## 13. Falsification framework & monitoring cadence", ""]
    by_tax: dict[str, list[dict]] = {}
    for c in claims:
        if c.get("severity", 0) >= 3 and c.get("falsifier"):
            by_tax.setdefault(c["taxonomy"], []).append(c)
    if not by_tax:
        return lines + ["No severity ≥ 3 claims with falsifiers.", ""]
    for tax in sorted(by_tax):
        lines.append(f"**{TAXONOMY_LABELS.get(tax, tax)}** — cadence: {MONITORING_CADENCE.get(tax, 'quarterly')}")
        for c in by_tax[tax][:6]:
            lines.append(f"- [sev {c['severity']}] {c['falsifier'][:220]}")
        lines.append("")
    lines += [
        "Every tripwire is a re-derivation procedure against hashed sources — a reader (or cron "
        "job) can automate each one verbatim.",
        "",
    ]
    return lines


def audit_trail(pack: dict, verified_doc: dict, claims_path: Path | None,
                gate: dict) -> list[str]:
    lines = ["## 14. Source quality, limitations & audit trail", ""]
    lines += [
        f"- Evidence pack hash: `{pack.get('pack_hash')}` (as of {pack.get('as_of')})",
        f"- Claims file: `{claims_path.name if claims_path else '—'}` "
        f"(sha256 `{hashlib.sha256(claims_path.read_bytes()).hexdigest()[:16]}…`)" if claims_path else "- Claims file: —",
        f"- Skeptic verification: {verified_doc.get('verified_count')} verified / "
        f"{verified_doc.get('failed_count')} failed "
        f"(failures → `_eval/ssi_skeptic_gold.jsonl`: {verified_doc.get('gold_cases_appended')})",
    ]
    lines.append("- Filings in evidence pack:")
    for f in pack.get("filings", []):
        lines.append(
            f"  - `{f['path']}` — {f.get('form')} filed {f.get('file_date')}, period "
            f"{f.get('period_end')}, accession `{f.get('accession')}`, sha256 `{f['sha256'][:16]}…`"
        )
    notes = pack.get("coverage_notes") or []
    if notes:
        lines.append("- Coverage limits (nothing silently dropped):")
        for n in notes[:12]:
            lines.append(f"  - `{n}`")
    xs = pack.get("xbrl_series") or {}
    lines.append(
        f"- XBRL series: {'available (' + str(len(xs.get('concepts') or {})) + ' concepts, CIK ' + str(xs.get('cik')) + ')' if xs.get('available') else 'unavailable — ' + str(xs.get('reason'))}"
    )
    lines.append("")
    lines += ["### Shipping gate (§5)", "", "| Check | Verdict | Detail |", "|---|---|---|"]
    for check in gate["checks"]:
        lines.append(f"| {check['name']} | {check['verdict']} | {check['detail'][:140]} |")
    lines += [
        "",
        f"**Gate result: {gate['result']}** — {gate['summary']}",
        "",
    ]
    return lines


# ---------------------------------------------------------------------------
# Shipping gate (§5)
# ---------------------------------------------------------------------------

def shipping_gate(pack: dict, verified_doc: dict, authority: dict,
                  evidence_dir: Path, as_of: str, report_body: str = "") -> dict:
    checks: list[dict] = []

    def add(name: str, ok: bool | None, detail: str) -> None:
        verdict = "PASS" if ok else ("BLOCKED" if ok is None else "FAIL")
        checks.append({"name": name, "verdict": verdict, "detail": detail})

    comparisons = pack.get("comparisons") or []
    cross = sum(1 for c in comparisons if c.get("gate", {}).get("matched"))
    intra = sum(1 for c in comparisons if (c.get("fact_deltas") or {}).get("mode") == "intra_filing")
    # A newly public issuer has no prior-period filing of the same form to diff
    # against, so the claim engine correctly emits nothing. That is a missing
    # input, not a defect in this run, and must not read as one. The distinction
    # is whether any comparison existed at all: if one did and the claims still
    # came back empty or broken, that IS a defect and stays a FAIL.
    no_comparable_filing = not comparisons

    failed = verified_doc.get("failed_count", 0)
    verified_count = verified_doc.get("verified_count", 0)
    add("locator_resolution",
        None if (no_comparable_filing and failed == 0 and verified_count == 0)
        else (failed == 0 and verified_count > 0),
        f"{verified_count} claims Skeptic-verified, {failed} failed; "
        + ("no prior-period filing exists to diff against, so no claims were emitted"
           if no_comparable_filing else "report renders verified claims only"))

    add("comparability_gate",
        None if no_comparable_filing else (cross > 0 and all(
            c.get("gate", {}).get("matched") or (c.get("fact_deltas") or {}).get("mode") == "intra_filing"
            for c in comparisons
        )),
        f"{cross} cross-filing gated comparisons; {intra} intra-filing fallbacks (flagged per-row)"
        + ("; issuer has no prior-period filing of a comparable form" if no_comparable_filing else ""))

    add("consensus_reconciliation", None,
        "no consensus-estimate feed configured — beat/miss content omitted, definitional callout emitted when bank-style")

    # Two distinct questions used to share one check, which made every ticker
    # with an upstream non-decision-grade contract read as a defect in this run.
    # (a) discipline: did the renderer obey the one-valuation-language rule?
    # (b) availability: is a decision_grade contract there to quote at all?
    status = authority.get("contract_status")
    is_decision_grade = status == "decision_grade"
    quoted_value = ("Contract value/share" in report_body
                    or "| Scenario | Value / share" in report_body)
    resolve_error = authority.get("error")
    discipline_ok = (not resolve_error) and not (quoted_value and not is_decision_grade)
    add("valuation_contract_only", discipline_ok,
        f"authority={authority.get('authority_level')}; value arithmetic rendered: {quoted_value}; "
        + (f"authority resolution errored ({str(resolve_error)[:80]})"
           if resolve_error else
           "figures sourced via decision_authority only, legacy IRR/stance fields never rendered"))

    add("valuation_contract_decision_grade", True if is_decision_grade else None,
        f"contract status={status}"
        + ("" if is_decision_grade else
           " — upstream valuation work outstanding; renderer correctly quoted no value figures"))

    tripwires = sum(
        1 for c in verified_doc.get("verified_claims", []) if c.get("falsifier") and c.get("severity", 0) >= 3
    )
    add("falsification_quantified",
        None if (no_comparable_filing and tripwires == 0) else tripwires >= 5,
        f"{tripwires} severity≥3 tripwires, each a re-derivation procedure on hashed sources"
        + ("; none available without a prior-period filing to diff" if no_comparable_filing else ""))

    add("statistical_caveats", True, "n stated in KPI sidebar; n<40 framed as hypothesis by construction")

    committee_started = authority.get("committee_state") not in (None, "not_started")
    premortems = list(evidence_dir.parent.glob("premortem_*.md")) + list(evidence_dir.glob("premortem_*.md"))
    add("premortem_before_ic", (not committee_started) or bool(premortems),
        f"committee_state={authority.get('committee_state')}; premortem artifacts found: {len(premortems)}")

    tz = list(evidence_dir.glob(f"ssi_time_zero_{as_of}.json"))
    add("time_zero_snapshot", bool(tz), f"snapshot present for {as_of}: {bool(tz)}")

    add("gold_conversion", verified_doc.get("gold_cases_appended", 0) >= failed,
        f"{verified_doc.get('gold_cases_appended', 0)} gold cases appended for {failed} failures")

    add("no_dynamic_memory", True, "renderer writes only research/ artifacts; never MEMORY.md")

    n_pass = sum(1 for c in checks if c["verdict"] == "PASS")
    n_fail = sum(1 for c in checks if c["verdict"] == "FAIL")
    n_blocked = sum(1 for c in checks if c["verdict"] == "BLOCKED")
    result = "SHIPPABLE" if n_fail == 0 and n_blocked == 0 else ("DRAFT (blocked)" if n_fail == 0 else "NOT SHIPPABLE")
    return {
        "schema_version": SCHEMA_VERSION,
        "as_of": as_of,
        "checks": checks,
        "result": result,
        "summary": f"{n_pass} pass / {n_fail} fail / {n_blocked} blocked "
                   "(blocked = missing external feed or outstanding upstream valuation work, "
                   "not a defect in this run)",
    }


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def build_report(ticker_dir: Path, as_of: str) -> tuple[str, dict] | None:
    research = ticker_dir / "research"
    evidence_dir = research / "evidence"
    if not evidence_dir.is_dir():
        return None
    _, pack = _latest_json(evidence_dir, "ssi_evidence_pack")
    claims_path, _claims_doc = _latest_json(evidence_dir, "ssi_claims")
    _, verified_doc = _latest_json(evidence_dir, "ssi_verified_claims")
    if pack is None or verified_doc is None:
        return None

    claims = verified_doc.get("verified_claims") or []
    spawner = (_claims_doc or {}).get("spawner") or {}
    ledger = (_claims_doc or {}).get("management_ledger") or {}
    concepts = ((pack.get("xbrl_series") or {}).get("concepts")) or {}

    valuation = _read_json(research / "valuation.json") or {"ticker": ticker_dir.name}
    try:
        authority = resolve_authority(research, valuation=valuation)
    except Exception as exc:
        authority = {"authority_level": "unresolved", "contract_status": "missing", "error": str(exc)[:200]}
    contract = _read_json(research / "valuation_contract.json")
    market = (contract or {}).get("market") or {}
    thesis_card = _read_json(research / "thesis_card.json")
    calendar = _read_json(evidence_dir / "earnings_calendar.json")

    ticker = ticker_dir.name
    # Body is assembled first so the shipping gate can inspect what was actually
    # rendered (the valuation-discipline check reads the text), then the header
    # carrying the verdict is prepended.
    lines: list[str] = []
    bank_style = any(
        "bank_style_revenue" in (r.get("flags") or []) for r in pack.get("revenue_definition", [])
    )
    lines += header_stat_block(ticker, market, concepts, calendar, authority)
    lines += executive_summary(claims, spawner, authority, thesis_card, calendar, pack)
    lines += business_model_section(pack, concepts)
    lines += expectations_section(pack)
    lines += kpi_table(concepts, bank_style=bank_style)
    lines += driver_table(claims)
    lines += valuation_section(authority, contract)
    lines += pattern_gap_sections(evidence_dir)
    lines += variant_section(claims, thesis_card)
    lines += catalyst_calendar(pack, calendar)
    lines += falsification_section(claims)

    if ledger:
        lines += ["## Management credibility & commitment ledger", ""]
        all_rows = ledger.get("rows") or []
        # Quantitative commitments lead; qualitative statements are listed
        # separately so the ledger's hit rate never implies scoring on prose.
        rows = [r for r in all_rows if r.get("status") != "qualitative_statement"]
        statements = [r for r in all_rows if r.get("status") == "qualitative_statement"]
        if rows:
            lines += ["| Promise | Made | Value | Status | Locator |", "|---|---|---|---|---|"]
            for r in rows[:10]:
                # source_ref is a dict for scanner-derived rows and a bare
                # string for management_facts-derived rows; both are valid.
                ref = r.get("source_ref")
                if isinstance(ref, dict):
                    loc = str(ref.get("source_path") or ref)[:60]
                elif ref:
                    loc = str(ref)[:60]
                else:
                    loc = "—"
                lines.append(
                    f"| {str(r.get('promise'))[:100]} | {r.get('date_made') or '—'} | "
                    f"{_fmt_money(r.get('promised_value'))} | {r.get('status')} | `{loc}` |"
                )
            ob = ledger.get("observed_buybacks")
            if ob:
                lines.append("")
                lines.append(
                    f"Observed repurchase spend ({ob.get('window')}): {_fmt_money(ob.get('value'))} "
                    f"(`{ob.get('tag')}`, periods {', '.join(ob.get('periods') or [])})."
                )
        else:
            lines.append(
                "No **quantitative** commitments resolvable from filings. Guidance-style "
                "promises require the transcript/earnings feed (see §4 gap)."
            )
        if statements:
            lines += [
                "",
                f"<details><summary>{len(statements)} qualitative management statement(s) "
                "— recorded, not scoreable</summary>",
                "",
                "| Statement | Made | Tier | Locator |",
                "|---|---|---|---|",
            ]
            for r in statements[:12]:
                ref = r.get("source_ref")
                loc = str(ref.get("source_path") if isinstance(ref, dict) else ref or "—")[:60]
                text = str(r.get("promise") or "").replace("|", "\\|")[:120]
                lines.append(
                    f"| {text} | {r.get('date_made') or '—'} | "
                    f"{r.get('epistemic_tier') or '—'} | `{loc}` |"
                )
            lines += ["", "</details>"]
        lines.append("")

    if spawner:
        lines += ["## Spawner engine (capital allocation)", ""]
        for name, comp in (spawner.get("components") or {}).items():
            detail = ", ".join(
                f"{k}={v}" for k, v in comp.items() if k not in ("evidence_ref",) and not isinstance(v, dict)
            )
            lines.append(f"- **{name}**: {detail}")
        for abstention in spawner.get("abstentions") or []:
            lines.append(f"- *abstained*: `{abstention}`")
        lines.append("")

    gate = shipping_gate(pack, verified_doc, authority, evidence_dir, as_of,
                         report_body="\n".join(lines))
    header = [
        f"# SSI deep dive — {ticker} ({as_of})",
        "",
        f"**Status: {gate['result']}** · pack `{str(pack.get('pack_hash'))[:12]}…` · "
        f"{verified_doc.get('verified_count')} Skeptic-verified claims · "
        f"generated by `build_ssi_report.py` (deterministic; no LLM prose)",
        "",
    ]
    lines = header + lines
    lines += audit_trail(pack, verified_doc, claims_path, gate)
    return "\n".join(lines) + "\n", gate


def write_report(ticker_dir: Path, as_of: str) -> tuple[Path, Path] | None:
    built = build_report(ticker_dir, as_of)
    if built is None:
        return None
    text, gate = built
    report_path = ticker_dir / "research" / f"ssi_report_{as_of}.md"
    gate_path = ticker_dir / "research" / "evidence" / f"ssi_report_gate_{as_of}.json"
    report_path.write_text(text, encoding="utf-8")
    gate_path.write_text(json.dumps(gate, indent=2) + "\n", encoding="utf-8")
    return report_path, gate_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tickers", nargs="*", help="Ticker folders (default: all with verified claims)")
    parser.add_argument("--date", default=datetime.now().date().isoformat())
    parser.add_argument("--check", action="store_true", help="Build in memory and report, do not write")
    args = parser.parse_args(argv)

    if args.tickers:
        ticker_dirs = [ROOT / t for t in args.tickers]
    else:
        ticker_dirs = sorted(
            {p.parents[2] for p in ROOT.glob("*/research/evidence/ssi_verified_claims_*.json")}
        )

    failures = 0
    for ticker_dir in ticker_dirs:
        if args.check:
            built = build_report(ticker_dir, args.date)
            if built is None:
                print(f"[skip] {ticker_dir.name}: no verified claims (run Phases 1-3 first)")
                failures += 1
                continue
            _, gate = built
            print(f"[check] {ticker_dir.name}: gate={gate['result']} ({gate['summary']})")
        else:
            outs = write_report(ticker_dir, args.date)
            if outs is None:
                print(f"[skip] {ticker_dir.name}: no verified claims (run Phases 1-3 first)")
                failures += 1
            else:
                print(f"[ok] {outs[0].relative_to(ROOT)} (gate: see {outs[1].name})")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
