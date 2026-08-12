#!/usr/bin/env python3
"""Extract the Section 382 facts that XBRL cannot express, with citations.

The NOL screener models the 382 limit from market cap alone, which assumes a
clean slate. Three facts decide whether that assumption holds, none of them
tagged in XBRL:

  1. PRIOR OWNERSHIP CHANGE. Loss companies routinely disclose that a change
     already happened -- "as a result of ownership changes in 2019 and 2022,
     $X of our NOLs are subject to an annual limitation". If so the headline
     carryforward is already impaired BEFORE an acquirer arrives, and the
     screener's estimate is too high. This is the single largest modelled
     error and the reason this script exists.
  2. SECTION 382(l)(5)/(l)(6). The bankruptcy exceptions; (l)(5) can remove
     the limitation entirely, which moves a row the other way.
  3. NOL RIGHTS PLAN. A 382 poison pill, typically triggering near 4.9%,
     makes an acquisition impossible without board cooperation -- a hard
     blocker on the whole thesis regardless of the arithmetic. These live in
     8-K / DEF 14A / the charter as often as the 10-K, so both are searched.

DESIGN: retrieval is deterministic, classification is the judgment call.
Regex finds candidate passages for pennies; what needs judgment is telling a
PROSPECTIVE risk factor from a HISTORICAL event. Vanda's 10-K says its
attributes "would be subject to limitation ... should an ownership change ...
occur" -- boilerplate present in nearly every loss company's filing and
meaning nothing has happened. Reading that as an impairment would be worse
than not looking. So every hit is classified, and anything the rules cannot
separate is emitted as `needs_review` rather than guessed: an unresolved fact
is cheap, a confidently wrong one silently corrupts the valuation.

Output carries a verbatim quote, the accession number and a resolvable URL per
fact, so a wrong extraction is auditable rather than invisible.

Usage:
  python _system/scripts/extract_nol_382_facts.py --from-screener
  python _system/scripts/extract_nol_382_facts.py --tickers SIRI NWL REI VNDA
  python _system/scripts/extract_nol_382_facts.py --tickers SIRI --write

ASCII-only output: this runs on a cp1252 console.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCREENER = ROOT / "dashboard" / "data" / "nol_screener.json"
OUTPUT = ROOT / "dashboard" / "data" / "nol_382_facts.json"

SEC_UA = "Marvin Research marvin@single-stock-investments.local"
SEC_THROTTLE_S = 0.15
CONTEXT_BEFORE = 320
CONTEXT_AFTER = 520
# Forms searched, newest first. 10-K carries the tax footnote; DEF 14A and 8-K
# carry rights plans, which a 10-K may never mention.
FORMS = ("10-K", "DEF 14A", "8-K")
MAX_FILINGS_PER_FORM = {"10-K": 1, "DEF 14A": 1, "8-K": 6}

# --------------------------------------------------------------------------
# classification vocabulary
#
# A hit is only useful once you know whether it describes something that
# HAPPENED or something that MIGHT. These two lists are deliberately narrow;
# anything matching both, or neither, is escalated rather than resolved.
# --------------------------------------------------------------------------
HISTORICAL_MARKERS = (
    r"\bwe (?:have )?experienced\b",
    r"\bwe (?:have )?underwent\b",
    r"\bunderwent an ownership change\b",
    r"\bownership change (?:occurred|has occurred)\b",
    r"\bas a result of (?:the|an|our|prior) ownership change",
    r"\bwe determined that an ownership change\b",
    r"\bhave been subject to (?:an )?annual limitation",
    r"\bare subject to (?:an )?annual limitation",
    r"\bresulted in an ownership change\b",
    r"\btriggered an ownership change\b",
    # "the pre-ownership change period" presupposes a change already happened;
    # REI's 10-K uses exactly this and matched no other historical marker, so
    # it escalated to needs_review rather than being missed outright.
    r"\bpre-ownership change\b",
    r"\bpost-ownership change\b",
    r"\bprior ownership change\b",
)
PROSPECTIVE_MARKERS = (
    r"\bwould be subject\b",
    r"\bcould be subject\b",
    r"\bmay be subject\b",
    r"\bshould an ownership change\b",
    r"\bif we experience\b",
    r"\bif an ownership change\b",
    r"\bin the event (?:of|that)\b",
    r"\bmay be limited\b",
    r"\bcould be limited\b",
    r"\bmay become subject\b",
)

PATTERNS = {
    "ownership_change": r"ownership change",
    "bankruptcy_382": r"382\s*\(\s*l\s*\)\s*\(\s*[56]\s*\)|section\s*382\(l\)\(5\)|bankruptcy exception",
    # A 382 pill is rarely called a "rights plan" in the filing. TETRA's is a
    # "Tax Plan" that "deters any person or group from becoming ... a
    # 5-percent stockholder for purposes of Section 382" -- a hard blocker on
    # any acquisition, and invisible to a Rights-Agreement-only pattern. The
    # house styles are Tax Benefit Preservation Plan, Tax Asset Protection
    # Plan, NOL Rights Plan and plain Tax Plan; match the function, not a name.
    "rights_plan": (
        r"[Tt]ax (?:[Bb]enefit [Pp]reservation|[Aa]sset [Pp]rotection|[Bb]enefits? [Pp]reservation)"
        r"\s*(?:Plan|Agreement)"
        r"|(?:NOL|[Ss]ection\s*382|[Tt]ax [Bb]enefit)[^.]{0,80}?[Rr]ights\s*(?:Agreement|Plan)"
        r"|[Rr]ights\s*(?:Agreement|Plan)[^.]{0,80}?(?:NOL|net operating loss|[Ss]ection\s*382)"
        r"|[Tt]ax Plan[^.]{0,120}?(?:[Ss]ection\s*382|ownership change|5-percent stockholder)"
        r"|(?:[Ss]ection\s*382|ownership change)[^.]{0,120}?[Tt]ax Plan"
    ),
}
# Dollar amounts and years inside an ownership-change passage.
AMOUNT_RE = re.compile(r"\$\s?([\d,]+(?:\.\d+)?)\s*(billion|million|thousand)?", re.I)
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
TRIGGER_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")


def http_get(url: str, raw: bool = False):
    req = urllib.request.Request(url, headers={"User-Agent": SEC_UA})
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            body = resp.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None if raw else {"__error__": f"{type(exc).__name__}: {str(exc)[:120]}"}
    time.sleep(SEC_THROTTLE_S)
    if raw:
        return body
    try:
        return json.loads(body.decode())
    except json.JSONDecodeError:
        return {"__error__": "unparseable json"}


def strip_html(html: str) -> str:
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&#\d+;|&[a-zA-Z]+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def recent_filings(cik: str) -> list[dict]:
    """Newest filings per form, from the submissions API."""
    doc = http_get(f"https://data.sec.gov/submissions/CIK{cik}.json")
    if not doc or doc.get("__error__"):
        return []
    recent = (doc.get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    out: list[dict] = []
    seen: dict[str, int] = {}
    for i, form in enumerate(forms):
        if form not in FORMS:
            continue
        if seen.get(form, 0) >= MAX_FILINGS_PER_FORM.get(form, 1):
            continue
        seen[form] = seen.get(form, 0) + 1
        accession = (recent.get("accessionNumber") or [None] * len(forms))[i]
        primary = (recent.get("primaryDocument") or [None] * len(forms))[i]
        if not accession or not primary:
            continue
        out.append(
            {
                "form": form,
                "accession": accession,
                "filed": (recent.get("filingDate") or [None] * len(forms))[i],
                "url": (
                    f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                    f"{accession.replace('-', '')}/{primary}"
                ),
            }
        )
    return out


def classify_tense(passage: str) -> tuple[str, list[str]]:
    """HISTORICAL / PROSPECTIVE / AMBIGUOUS, plus the markers that decided it."""
    lowered = passage.lower()
    hist = [p for p in HISTORICAL_MARKERS if re.search(p, lowered)]
    pros = [p for p in PROSPECTIVE_MARKERS if re.search(p, lowered)]
    if hist and not pros:
        return "historical", hist
    if pros and not hist:
        return "prospective", pros
    if hist and pros:
        return "ambiguous", hist + pros
    return "ambiguous", []


def change_years(passage: str) -> list[str]:
    """Years plausibly naming WHEN a change happened.

    A naive year scan over this language is mostly noise: every such passage
    cites the "Internal Revenue Code of 1986", and filings restate their own
    period end, so Vanda's real answer (2014) arrived buried in
    ['1986', '2014', '2017', '2025', '2026']. Keep only years sitting close to
    the phrase itself, drop the statutory reference, and drop anything at or
    beyond the current year, which is the filing's own dateline rather than a
    past event.
    """
    now = datetime.now(timezone.utc).year
    out: set[str] = set()
    for anchor in re.finditer(r"ownership change", passage, re.I):
        window = passage[max(0, anchor.start() - 140) : anchor.end() + 200]
        window = re.sub(r"Internal Revenue Code of \d{4}", " ", window, flags=re.I)
        for match in YEAR_RE.finditer(window):
            year = int(match.group(0))
            if 1990 <= year < now:
                out.add(str(year))
    return sorted(out)


def parse_amount(passage: str) -> float | None:
    match = AMOUNT_RE.search(passage)
    if not match:
        return None
    try:
        value = float(match.group(1).replace(",", ""))
    except ValueError:
        return None
    scale = {"billion": 1e9, "million": 1e6, "thousand": 1e3}.get(
        (match.group(2) or "").lower(), 1.0
    )
    return value * scale


def scan_filing(text: str, filing: dict) -> list[dict]:
    facts: list[dict] = []
    for kind, pattern in PATTERNS.items():
        for match in re.finditer(pattern, text, re.I):
            start = max(0, match.start() - CONTEXT_BEFORE)
            passage = text[start : match.end() + CONTEXT_AFTER].strip()
            tense, markers = classify_tense(passage)
            fact = {
                "kind": kind,
                "tense": tense,
                "markers": markers[:4],
                "quote": passage[:900],
                "form": filing["form"],
                "accession": filing["accession"],
                "filed": filing["filed"],
                "url": filing["url"],
            }
            if kind == "ownership_change":
                fact["limited_amount_usd"] = parse_amount(passage) if tense == "historical" else None
                fact["years_mentioned"] = change_years(passage)
            if kind == "rights_plan":
                triggers = [float(t) for t in TRIGGER_RE.findall(passage)]
                # A 382 pill sits near 4.9%; anything above ~10% is some other
                # percentage that happens to share the sentence.
                fact["trigger_pct"] = next((t for t in triggers if t <= 10.0), None)
            facts.append(fact)
            if len(facts) >= 40:
                return facts
    return facts


def summarize(ticker: str, facts: list[dict]) -> dict:
    """Collapse raw hits into the fields the 382 model would consume.

    `prior_ownership_change` is only asserted on a HISTORICAL hit. Prospective
    boilerplate appears in nearly every loss company's risk factors and means
    nothing happened; treating it as an event would impair every row on the
    screen. Ambiguous hits set needs_review instead of deciding.
    """
    owner = [f for f in facts if f["kind"] == "ownership_change"]
    historical = [f for f in owner if f["tense"] == "historical"]
    ambiguous = [f for f in owner if f["tense"] == "ambiguous"]
    pill = [f for f in facts if f["kind"] == "rights_plan"]
    bankruptcy = [f for f in facts if f["kind"] == "bankruptcy_382"]

    amounts = [f.get("limited_amount_usd") for f in historical if f.get("limited_amount_usd")]
    years = sorted({y for f in historical for y in f.get("years_mentioned") or []})
    triggers = [f.get("trigger_pct") for f in pill if f.get("trigger_pct")]

    return {
        "ticker": ticker,
        "prior_ownership_change": {
            "occurred": bool(historical),
            "years": years,
            "limited_amount_usd": max(amounts) if amounts else None,
            "evidence": historical[0] if historical else None,
            "hit_counts": {
                "historical": len(historical),
                "prospective": len(owner) - len(historical) - len(ambiguous),
                "ambiguous": len(ambiguous),
            },
        },
        "nol_rights_plan": {
            "present": bool(pill),
            "trigger_pct": min(triggers) if triggers else None,
            "evidence": pill[0] if pill else None,
        },
        "bankruptcy_382_exception": {
            "mentioned": bool(bankruptcy),
            "evidence": bankruptcy[0] if bankruptcy else None,
        },
        # An ambiguous ownership-change hit is the case worth a human or an LLM;
        # everything else here is settled by the rules.
        "needs_review": bool(ambiguous) and not historical,
        "reviewed_forms": sorted({f["form"] for f in facts}),
    }


def extract_for(ticker: str, cik: str) -> dict:
    filings = recent_filings(cik)
    if not filings:
        return {"ticker": ticker, "cik": cik, "error": "no filings retrieved"}
    facts: list[dict] = []
    for filing in filings:
        body = http_get(filing["url"], raw=True)
        if not body:
            continue
        facts.extend(scan_filing(strip_html(body.decode("utf-8", "replace")), filing))
    result = summarize(ticker, facts)
    result["cik"] = cik
    result["filings_scanned"] = [
        {k: f[k] for k in ("form", "accession", "filed", "url")} for f in filings
    ]
    return result


def screener_targets() -> list[tuple[str, str]]:
    """Rows worth the fetch: anything not structurally blocked, with a CIK.

    Deliberately not all 89. A row already blocked because its own auditor
    fully reserves the asset does not become investable if a filing says the
    NOL is unimpaired, so spending SEC round-trips on it buys nothing.
    """
    doc = json.loads(SCREENER.read_text(encoding="utf-8"))
    out = []
    for row in doc.get("rows") or []:
        if not row.get("cik"):
            continue
        if row.get("usability") in ("material_after_382", "immaterial_after_382"):
            out.append((row["ticker"], row["cik"]))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", nargs="*", help="explicit tickers (needs --cik-from-screener)")
    parser.add_argument("--from-screener", action="store_true",
                        help="every non-blocked screener row carrying a CIK")
    parser.add_argument("--write", action="store_true", help=f"write {OUTPUT.name}")
    args = parser.parse_args()

    if args.from_screener or not args.tickers:
        targets = screener_targets()
    else:
        doc = json.loads(SCREENER.read_text(encoding="utf-8"))
        by_ticker = {r["ticker"]: r for r in doc.get("rows") or []}
        wanted = {t.upper() for t in args.tickers}
        targets = [(t, by_ticker[t]["cik"]) for t in wanted
                   if t in by_ticker and by_ticker[t].get("cik")]
        missing = wanted - {t for t, _ in targets}
        if missing:
            print(f"no CIK in screener for: {', '.join(sorted(missing))}", file=sys.stderr)

    results = []
    for ticker, cik in targets:
        print(f"  scanning {ticker} (CIK {cik}) ...", flush=True)
        results.append(extract_for(ticker, cik))

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "SEC EDGAR submissions + primary documents",
        "method": (
            "Deterministic regex retrieval over the latest 10-K / DEF 14A / recent 8-Ks, "
            "then tense classification. Prospective risk-factor boilerplate is NOT an "
            "ownership change; ambiguous hits set needs_review rather than being resolved."
        ),
        "not_extractable": [
            "NUBIG / NUBIL -- requires asset-level tax basis versus fair value, which is "
            "not disclosed in any filing. Flag candidates qualitatively; never model a number.",
        ],
        "research_only": True,
        "rows": results,
    }
    if args.write:
        OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {OUTPUT} ({len(results)} rows)")
    else:
        for r in results:
            oc = r.get("prior_ownership_change") or {}
            print(f"  {r['ticker']:6s} prior_change={oc.get('occurred')} "
                  f"years={oc.get('years')} pill={(r.get('nol_rights_plan') or {}).get('present')} "
                  f"needs_review={r.get('needs_review')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
