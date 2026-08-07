#!/usr/bin/env python3
"""Phase 2 of the SSI Perplexity-grade pipeline: specialist synthesis & claim resolution.

Consumes the Phase 1 evidence pack (`ssi_evidence_pack_{date}.json`) and emits
structured atomic claims — never prose. Three specialist passes, all
deterministic:

  Filing Sentinel   — classifies material deltas and section-diff signals
                      against the five-part furnace taxonomy
                      (_system/frameworks/short_alpha_filing_furnace.md):
                      identity_instrument, liquidity_oxygen, earnings_quality,
                      operating_failure, market_mechanics.
  Management Ledger — quantitative promises vs realized outcomes; consumes
                      management_facts_*.json claims when present and resolves
                      realized values from filing facts.
  Spawner Engine    — capital-allocation discipline scored from cited facts
                      (buyback trajectory, capex vs operating cash flow),
                      abstaining with a reason when inputs are missing.

Every claim carries: statement, direction, magnitude, severity (1–5),
confidence, a falsifier, and an evidence_ref that resolves to
{pack_hash, source sha256, source path, tag, line}. Claims without a
resolvable evidence_ref are not emitted.

Output: {TICKER}/research/evidence/ssi_claims_{date}.json

Usage:
  python _system/scripts/build_ssi_claims.py TBBK ABX
  python _system/scripts/build_ssi_claims.py ABX --date 2026-08-05
  python _system/scripts/build_ssi_claims.py ABX --check
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

ROOT = SCRIPT_DIR.parents[1]

SCHEMA_VERSION = "1.0"

# ---------------------------------------------------------------------------
# Furnace taxonomy routing: first matching rule wins (ordered most- to
# least-specific). Tags that match no rule are counted, not silently dropped.
# ---------------------------------------------------------------------------
TAXONOMY_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("operating_failure", re.compile(
        r"Impairment|GoodwillImpairment|RestructuringCharges|AssetRetirement"
        r"|DisposalGroup|DiscontinuedOperation", re.I)),
    ("earnings_quality", re.compile(
        r"AllowanceFor(?:Credit|Loan|Doubtful)|ProvisionFor(?:Credit|Loan|Doubtful)"
        r"|DeferredRevenue|ContractWithCustomerLiability|AccountsReceivable"
        r"|InventoryNet|CapitalizedContractCost|UnbilledReceivables", re.I)),
    ("liquidity_oxygen", re.compile(
        r"Cash(?:And|Cash)|Debt|Borrowings|LineOfCredit|InterestExpense"
        r"|OperatingLeaseLiability|FinanceLeaseLiability|LettersOfCredit"
        r"|CommercialPaper|NotesPayable", re.I)),
    ("identity_instrument", re.compile(
        r"SharesOutstanding|SharesIssued|StockIssuedDuringPeriod|Warrant"
        r"|Convertible|PreferredStock|TreasuryStock|StockRepurchase", re.I)),
    # --- Extended coverage (after the core rules, so their routing is
    # unchanged). The ABX pilot dropped 126/157 delta rows as unrouted;
    # these map the common US-GAAP surface into the same five buckets. ---
    ("identity_instrument", re.compile(
        r"RepurchaseOf(?:Common)?Stock|Dividends|CommonStock|ShareBasedCompensation"
        r"|SaleOfStock|EquityIssuance|EmployeeStockPurchase|NoncontrollingInterest", re.I)),
    ("earnings_quality", re.compile(
        r"Amortization|Depreciation|Goodwill|IntangibleAsset|IncomeTax|DeferredTax"
        r"|OtherComprehensiveIncome|UnrealizedGain|UnrealizedLoss|EquityMethod"
        r"|FairValue|AccruedLiabilities|PrepaidExpense|Provision|Reserve"
        r"|ContractAsset|BadDebt|Writedown|WriteOff", re.I)),
    ("liquidity_oxygen", re.compile(
        r"NetCashProvidedByUsedIn|PaymentsOf|PaymentsFor|PaymentsTo|ProceedsFrom"
        r"|RestrictedCash|MarketableSecurities|ShortTermInvestments|AvailableForSale"
        r"|HeldToMaturity|WorkingCapital|Deposits|FederalFunds|InterestBearing"
        r"|FinanceReceivable|LoansAndLeasesReceivable|SecuredBorrowing", re.I)),
    ("operating_failure", re.compile(
        r"Revenue|Sales|CostOf|GrossProfit|OperatingIncome|OperatingExpense"
        r"|SellingGeneralAndAdministrative|ResearchAndDevelopment|GeneralAndAdministrative"
        r"|NetIncomeLoss|ProfitLoss|EarningsPerShare|ComprehensiveIncome"
        r"|NumberOfEmployees|LeaseCost|ProductWarranty|Inventory|Production"
        r"|Segment|Backlog|Utilization", re.I)),
)

# ---------------------------------------------------------------------------
# Economic-significance tiering. A +1,900% swing in
# DeferredStateAndLocalIncomeTaxExpenseBenefit is a footnote artifact, not a
# thesis signal; without this, high-percentage footnote rows dominate severity
# ranking and crowd real economics out of the report.
# ---------------------------------------------------------------------------
PRIMARY_CONCEPTS = re.compile(
    r"^(?:Revenues?|RevenueFromContract\w*|SalesRevenue\w*|OperatingIncomeLoss"
    r"|NetIncomeLoss\w*|ProfitLoss|EarningsPerShare(?:Basic|Diluted)"
    r"|GrossProfit|CostOfRevenue|CostOfGoodsAndServicesSold"
    r"|Assets|Liabilities|StockholdersEquity\w*"
    r"|CashAndCashEquivalentsAtCarryingValue"
    r"|NetCashProvidedByUsedIn(?:Operating|Investing|Financing)Activities\w*"
    r"|LongTermDebt\w*|DebtInstrumentCarryingAmount|ShortTermBorrowings"
    r"|Deposits|InterestIncomeExpenseNet|NoninterestIncome"
    r"|LoansAndLeasesReceivableNetReportedAmount|FinancingReceivable\w*"
    r"|AllowanceForCreditLoss\w*|ProvisionForLoanLeaseAndOtherLosses"
    r"|GoodwillImpairmentLoss|ImpairmentOfLongLivedAssets\w*"
    r"|PaymentsForRepurchaseOfCommonStock|CommonStockSharesOutstanding"
    r"|WeightedAverageNumberOf\w*SharesOutstanding\w*"
    r"|PaymentsToAcquirePropertyPlantAndEquipment)$",
    re.I,
)

# Footnote/schedule detail: real disclosures, but movements in them are not
# thesis-level signals on their own.
FOOTNOTE_DETAIL = re.compile(
    r"OtherComprehensiveIncome|AccumulatedOtherComprehensive"
    r"|Deferred(?:Federal|State|Foreign)\w*IncomeTax"
    r"|FairValueDisclosure|FiniteLivedIntangibleAssets(?:Amortization|Accumulated|Acquired)"
    r"|AmortizationExpenseAfterYear|ExpectedAmortization"
    r"|ShareBasedCompensationArrangement|SharebasedCompensationArrangement"
    r"|AntidilutiveSecurities|UnrecognizedTaxBenefits\w*Detail"
    r"|ScheduleOf|TableTextBlock|PolicyTextBlock"
    r"|DebtInstrumentBasisSpreadOnVariableRate|DebtInstrumentInterestRate\w*",
    re.I,
)

# Maturity/obligation schedule buckets. These are footnote detail, but they must
# be tested BEFORE PRIMARY_CONCEPTS: `LongTermDebt\w*` there otherwise captures
# LongTermDebtMaturitiesRepaymentsOfPrincipalInYearTwo and friends and ranks a
# single roll-forward bucket as primary economics. The buckets are volatile by
# construction — debt rolling from "year two" into "next twelve months" produces
# a -100%/+100% pair every year with no change in total obligation — so a move in
# one bucket is not a thesis signal. Aggregate debt tags stay primary.
MATURITY_SCHEDULE = re.compile(
    r"MaturitiesRepaymentsOfPrincipal"
    r"|LongTermDebtMaturities"
    r"|(?:DebtInstrument|LineOfCredit)\w*(?:MaturityDate|PeriodicPayment)"
    r"|LesseeOperatingLeaseLiabilityPaymentsDue"
    r"|FinanceLeaseLiabilityPaymentsDue"
    r"|LesseeOperatingLeaseLiabilityUndiscountedExcessAmount"
    r"|OperatingLeasesFutureMinimumPaymentsDue"
    r"|ContractualObligation"
    r"|(?:InYear(?:Two|Three|Four|Five)|InNextTwelveMonths|InRemainderOfFiscalYear"
    r"|AfterYearFive|YearFiveAndThereafter|Thereafter)$",
    re.I,
)

# Max severity a footnote-detail row may reach, regardless of percentage move.
FOOTNOTE_SEVERITY_CAP = 2


def tag_tier(tag: str) -> str:
    """'primary' | 'footnote_detail' | 'secondary'."""
    if MATURITY_SCHEDULE.search(tag):
        return "footnote_detail"
    if PRIMARY_CONCEPTS.match(tag):
        return "primary"
    if FOOTNOTE_DETAIL.search(tag):
        return "footnote_detail"
    return "secondary"


SECTION_TAXONOMY = {
    "risk_factors": "operating_failure",
    "mdna": "earnings_quality",
    "liquidity_covenants": "liquidity_oxygen",
    "accounting_policies": "earnings_quality",
    "controls": "earnings_quality",
    "related_party": "identity_instrument",
}

# Severity-5 narrative triggers (must match SEVERITY_KEYWORDS in Phase 1).
CRITICAL_NARRATIVE = re.compile(
    r"going\s+concern|substantial\s+doubt|material\s+weakness|covenant\s+(?:breach|violation|waiver)"
    r"|default|restatement|delisting", re.I)

# Ledger: promise metrics we can resolve deterministically from fact deltas.
LEDGER_RESOLVABLE = {
    "revenues", "revenue", "net_income", "eps_basic", "operating_income",
    "shares_outstanding", "operating_cash_flow", "capital_expenditures",
}


def claim_id(ticker: str, taxonomy: str, tag: str, filing_path: str) -> str:
    blob = f"{ticker}|{taxonomy}|{tag}|{filing_path}"
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def _route_taxonomy(tag: str) -> str | None:
    for taxonomy, pattern in TAXONOMY_RULES:
        if pattern.search(tag):
            return taxonomy
    return None


def _severity_for_delta(taxonomy: str, row: dict) -> int:
    pct = row.get("pct")
    flags = row.get("flags", [])
    severity = 2
    if "extreme_move" in flags or "sign_flip" in flags:
        severity = 3
    if pct is not None and abs(pct) >= 100.0:
        severity = 4
    if taxonomy == "earnings_quality" and pct is not None and pct >= 30.0 \
            and re.search(r"AllowanceFor|ProvisionFor", row["tag"], re.I):
        severity = max(severity, 4)
    if taxonomy == "liquidity_oxygen" and "gone_tag" in flags \
            and re.search(r"Cash(?:And|Cash)", row["tag"], re.I):
        severity = max(severity, 4)
    # A footnote-schedule row cannot outrank real economics on percentage alone.
    if tag_tier(row["tag"]) == "footnote_detail":
        severity = min(severity, FOOTNOTE_SEVERITY_CAP)
    # A pair spanning >50x is a scope mismatch, not a move; it must not headline.
    if "implausible_ratio" in flags:
        severity = min(severity, FOOTNOTE_SEVERITY_CAP)
    return severity


def _confidence_for_row(row: dict) -> str:
    flags = set(row.get("flags", []))
    if flags & {"occurrence_mismatch", "implausible_ratio"} \
            or flags >= {"intra_filing_pairing", "ambiguous_occurrences"}:
        return "low"
    if flags & {"new_tag", "gone_tag", "intra_filing_pairing"}:
        return "medium"
    return "high"


def _direction(row: dict) -> str:
    if row.get("current") is None:
        return "removed"
    if row.get("prior") is None:
        return "new"
    return "up" if row["current"] > row["prior"] else "down"


def _fmt(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.4g}"


# ---------------------------------------------------------------------------
# Filing Sentinel
# ---------------------------------------------------------------------------

def sentinel_claims(pack: dict) -> tuple[list[dict], dict]:
    ticker = pack["ticker"]
    sha_by_path = {f["path"]: f["sha256"] for f in pack["filings"]}
    claims: list[dict] = []
    unrouted = 0

    for comparison in pack.get("comparisons", []):
        deltas = comparison.get("fact_deltas")
        if not deltas:
            continue
        filing_path = deltas["current_filing"]
        prior_path = deltas["prior_filing"]
        intra = deltas.get("mode") == "intra_filing"
        basis = (
            "vs prior period within the same filing (intra-filing pairing)"
            if intra else "vs comparable prior filing"
        )
        for row in deltas["rows"]:
            taxonomy = _route_taxonomy(row["tag"])
            if taxonomy is None:
                unrouted += 1
                continue
            severity = _severity_for_delta(taxonomy, row)
            direction = _direction(row)
            pct = row.get("pct")
            magnitude = f"{pct:+.1f}%" if pct is not None else direction
            statement = (
                f"{row['tag']} moved {_fmt(row.get('prior'))} → {_fmt(row.get('current'))}"
                f" ({magnitude}) {basis}"
            )
            if intra:
                falsifier = (
                    f"Re-extract both occurrences of {row['tag']} from {filing_path}; "
                    f"claim fails if the current/prior document-order pairing is wrong"
                )
            else:
                falsifier = (
                    f"Re-extract {row['tag']} from {filing_path} and {prior_path}; "
                    f"claim fails if either value or the comparability pairing differs"
                )
            claims.append({
                "claim_id": claim_id(ticker, taxonomy, row["tag"], filing_path),
                "source": "filing_sentinel",
                "taxonomy": taxonomy,
                "statement": statement,
                "direction": direction,
                "magnitude_pct": pct,
                "severity": severity,
                "concept_tier": tag_tier(row["tag"]),
                "confidence": _confidence_for_row(row),
                "falsifier": falsifier,
                "evidence_ref": {
                    "pack_hash": pack["pack_hash"],
                    "source_path": filing_path,
                    "source_sha256": sha_by_path.get(filing_path),
                    "prior_path": prior_path,
                    "prior_sha256": sha_by_path.get(prior_path),
                    "tag": row["tag"],
                    "line_current": row.get("line_current"),
                    "line_prior": row.get("line_prior"),
                },
                "flags": row.get("flags", []),
            })

        section_diff = comparison.get("section_diff") or {}
        for section, diff in (section_diff.get("sections") or {}).items():
            for keyword in diff.get("severity_keywords_added", []):
                taxonomy = SECTION_TAXONOMY.get(section, "operating_failure")
                added_line = next(
                    (
                        line
                        for line in diff.get("severity_lines_added", [])
                        if keyword in line.lower()
                    ),
                    None,
                )
                claims.append({
                    "claim_id": claim_id(ticker, taxonomy, f"{section}:{keyword}", filing_path),
                    "source": "filing_sentinel",
                    "taxonomy": taxonomy,
                    "statement": f"New '{keyword}' language added to {section} vs comparable prior filing",
                    "direction": "new",
                    "magnitude_pct": None,
                    "severity": 5,
                    "confidence": "high" if added_line else "medium",
                    "falsifier": (
                        f"Re-diff section '{section}' between {filing_path} and {prior_path}; "
                        f"claim fails if '{keyword}' appears in the prior period too"
                    ),
                    "evidence_ref": {
                        "pack_hash": pack["pack_hash"],
                        "source_path": filing_path,
                        "source_sha256": sha_by_path.get(filing_path),
                        "prior_path": prior_path,
                        "prior_sha256": sha_by_path.get(prior_path),
                        "section": section,
                        "snippet": (added_line or "")[:240],
                    },
                    "flags": ["critical_narrative"],
                })

    for rev in pack.get("revenue_definition", []):
        if "bank_style_revenue" not in rev.get("flags", []):
            continue
        filing_path = rev["filing"]
        claims.append({
            "claim_id": claim_id(ticker, "earnings_quality", "revenue_definition", filing_path),
            "source": "filing_sentinel",
            "taxonomy": "earnings_quality",
            "statement": (
                f"Bank-style revenue definition: operating revenue "
                f"{_fmt(rev.get('operating_revenue'))} (NII {_fmt(rev.get('net_interest_income'))} "
                f"+ non-interest {_fmt(rev.get('noninterest_income'))}) — consensus 'revenue' "
                f"comparisons must reconcile definitions first"
            ),
            "direction": "flag",
            "magnitude_pct": None,
            "severity": 3,
            "confidence": "high",
            "falsifier": (
                f"Recompute NII + non-interest income from {filing_path}; claim fails if the "
                f"reported revenue tag already equals operating revenue"
            ),
            "evidence_ref": {
                "pack_hash": pack["pack_hash"],
                "source_path": filing_path,
                "source_sha256": sha_by_path.get(filing_path),
                "lines": rev.get("evidence_lines", {}),
            },
            "flags": rev.get("flags", []),
        })

    return claims, {"unrouted_delta_rows": unrouted}


# ---------------------------------------------------------------------------
# Management Credibility & Commitment Ledger
# ---------------------------------------------------------------------------

def _latest_json(evidence_dir: Path, stem: str) -> dict | None:
    files = sorted(evidence_dir.glob(f"{stem}_*.json"), reverse=True)
    for path in files:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
    return None


def _latest_filing_facts(evidence_dir: Path) -> dict:
    facts = _latest_json(evidence_dir, "filing_facts") or {}
    return facts.get("metrics") or {}


BUYBACK_AUTH = re.compile(
    r"(?:board|directors)[^.\n]{0,120}?authoriz\w+[^.\n]{0,160}?"
    r"\$\s?([\d,][\d,.]*)\s*(million|billion)?[^.\n]{0,120}?(?:repurchas|buy\s?-?\s?back)"
    r"|authoriz\w+[^.\n]{0,160}?(?:repurchas|buy\s?-?\s?back)[^.\n]{0,160}?"
    r"\$\s?([\d,][\d,.]*)\s*(million|billion)?",
    re.I,
)


QUANT_IN_TEXT = re.compile(
    r"\$\s?([\d,][\d,.]*)\s*(million|billion|bn|m\b)?|([\d,][\d,.]*)\s*(?:%|percent)",
    re.I,
)


def _quantitative_value(text: str) -> float | None:
    """First dollar or percent figure in a statement, or None when the
    statement carries no number (i.e. it is not a scoreable commitment)."""
    match = QUANT_IN_TEXT.search(text)
    if not match:
        return None
    raw = match.group(1) or match.group(3)
    if not raw:
        return None
    try:
        value = float(raw.replace(",", ""))
    except ValueError:
        return None
    scale = (match.group(2) or "").lower()
    if scale in ("million", "m"):
        value *= 1e6
    elif scale in ("billion", "bn"):
        value *= 1e9
    return value


# XBRL context/metadata rows survive text extraction and can contain both a
# dollar figure and the word "repurchase" (from a tag name), producing a
# citation that points at machine metadata instead of a board resolution.
NON_PROSE = re.compile(r"https?://|fasb\.org|us-gaap/|\bxbrl\b|#[A-Za-z]+Current\b", re.I)


def _looks_like_prose(line: str) -> bool:
    """True when a line reads as filing narrative rather than XBRL metadata."""
    if NON_PROSE.search(line):
        return False
    letters = sum(1 for ch in line if ch.isalpha())
    if letters < 40 or letters / max(len(line), 1) < 0.55:
        return False
    # A board resolution is a sentence: it needs lowercase words, not just
    # identifiers and numbers.
    words = [w for w in re.split(r"\s+", line) if w.isalpha()]
    return len(words) >= 8


def _auth_usd(match: re.Match) -> float | None:
    raw = match.group(1) or match.group(3)
    scale = (match.group(2) or match.group(4) or "").lower()
    if raw is None:
        return None
    try:
        value = float(raw.replace(",", ""))
    except ValueError:
        return None
    if scale == "million":
        value *= 1e6
    elif scale == "billion":
        value *= 1e9
    return value


def buyback_authorization_promises(pack: dict, evidence_dir: Path) -> list[dict]:
    """Deterministic scan of periodic-filing narrative for board buyback
    authorizations — each hit becomes a Management Ledger promise row with a
    path+line locator. Duplicate dollar amounts across filings keep the
    earliest sighting (the original promise date)."""
    base = evidence_dir.parents[1].parent  # rel paths in the pack are ROOT-relative
    seen: dict[float, dict] = {}
    for filing in pack.get("filings", []):
        if filing.get("form_class") not in ("annual", "quarterly"):
            continue
        path = base / filing["path"]
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if not _looks_like_prose(line):
                continue
            for match in BUYBACK_AUTH.finditer(line):
                usd = _auth_usd(match)
                if usd is None or usd < 1e5:
                    continue
                row = {
                    "promise": line.strip()[:240],
                    "metric": "buyback_authorization",
                    "promised_value": usd,
                    "date_made": filing.get("file_date"),
                    "due": None,
                    "source_ref": {
                        "source_path": filing["path"],
                        "source_sha256": filing.get("sha256"),
                        "line": line_no,
                    },
                    "realized_value": None,
                    "delta": None,
                    "status": "open_authorization",
                }
                prior = seen.get(usd)
                if prior is None or (row["date_made"] or "") < (prior["date_made"] or ""):
                    seen[usd] = row
    return [seen[k] for k in sorted(seen)]


def management_ledger(pack: dict, evidence_dir: Path, as_of: str) -> dict:
    """Promise rows in, resolution status out. Promises come from
    management_facts_*.json (schema: {claims: [{metric, value, due, ...}]})
    plus deterministic buyback-authorization sightings in filing narrative;
    realized values resolve from the latest filing_facts metrics."""
    mgmt = _latest_json(evidence_dir, "management_facts") or {}
    promises = mgmt.get("claims") or []
    metrics = _latest_filing_facts(evidence_dir)

    rows: list[dict] = []
    unresolvable = 0
    for promise in promises:
        # build_management_evidence.py emits {id, excerpt, source, file_date};
        # older/hand-authored files use {metric, value, statement, due}. Accept
        # both rather than silently rendering blank rows.
        metric = str(promise.get("metric") or promise.get("id") or "").lower()
        text = (
            promise.get("statement")
            or promise.get("claim")
            or promise.get("excerpt")
            or metric
        )
        value = promise.get("value")
        if value is None:
            value = _quantitative_value(str(promise.get("excerpt") or ""))
        row = {
            "promise": text,
            "metric": metric,
            "promised_value": value,
            "date_made": promise.get("date") or promise.get("file_date") or promise.get("as_of"),
            "due": promise.get("due"),
            "source_ref": promise.get("source") or promise.get("evidence_ref"),
            "realized_value": None,
            "delta": None,
            "status": "pending",
            "epistemic_tier": promise.get("epistemic_tier"),
        }
        if value is None:
            # A commitment ledger scores *quantitative* promises. Qualitative
            # management statements are recorded but never counted as promises
            # awaiting resolution — that would inflate the ledger with rows
            # nothing can ever resolve.
            row["status"] = "qualitative_statement"
            rows.append(row)
            continue
        if metric in LEDGER_RESOLVABLE and metric in metrics:
            realized = metrics[metric].get("current")
            row["realized_value"] = realized
            promised = promise.get("value")
            if isinstance(promised, (int, float)) and isinstance(realized, (int, float)):
                row["delta"] = realized - promised
                row["status"] = "met" if realized >= promised else "missed"
            else:
                row["status"] = "unresolved_types"
        elif metric and metric not in LEDGER_RESOLVABLE:
            row["status"] = "unresolvable_metric"
            unresolvable += 1
        rows.append(row)

    rows.extend(buyback_authorization_promises(pack, evidence_dir))

    # Context for open buyback authorizations: actual repurchase spend from
    # the XBRL series (TTM if quarterly data exists, else latest fiscal year).
    observed_buybacks = None
    concepts = ((pack.get("xbrl_series") or {}).get("concepts")) or {}
    bb = concepts.get("buybacks_paid") or {}
    quarterly = bb.get("quarterly") or []
    # 10-Q cash-flow frames are often YTD, so the deduped quarterly series can
    # be sparse (e.g. Q1-only). Only call four quarters a TTM when they are
    # actually contiguous (~a year end-to-end); otherwise use the annual row.
    contiguous = False
    if len(quarterly) >= 4:
        tail = quarterly[-4:]
        try:
            span = (
                _dt.date.fromisoformat(tail[-1]["end"])
                - _dt.date.fromisoformat(tail[0]["end"])
            ).days
            contiguous = span <= 300
        except ValueError:
            contiguous = False
    if contiguous:
        observed_buybacks = {
            "window": "ttm",
            "value": sum(r["val"] for r in tail),
            "periods": [r["end"] for r in tail],
            "tag": bb.get("tag"),
        }
    elif bb.get("annual"):
        last = bb["annual"][-1]
        observed_buybacks = {
            "window": "latest_fy",
            "value": last["val"],
            "periods": [last["end"]],
            "tag": bb.get("tag"),
            "accn": last.get("accn"),
        }

    scored = [r for r in rows if r["status"] in ("met", "missed")]
    quantitative = [r for r in rows if r["status"] != "qualitative_statement"]
    return {
        "as_of": as_of,
        "pack_hash": pack["pack_hash"],
        "promise_count": len(quantitative),
        "statement_count": len(rows) - len(quantitative),
        "resolved_count": len(scored),
        "hit_rate": (
            round(sum(1 for r in scored if r["status"] == "met") / len(scored), 3)
            if scored else None
        ),
        "unresolvable_count": unresolvable,
        "observed_buybacks": observed_buybacks,
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# Spawner Engine (capital allocation)
# ---------------------------------------------------------------------------

def _series_read(change_pct: float) -> str:
    if change_pct < -0.5:
        return "shrinking"
    if change_pct > 0.5:
        return "diluting"
    return "flat"


def _xbrl_spawner_components(concepts: dict) -> tuple[dict, list[str]]:
    """Multi-year capital-allocation components from the pack's XBRL series."""
    components: dict = {}
    abstentions: list[str] = []

    def annual(concept: str) -> list[dict]:
        return (concepts.get(concept) or {}).get("annual") or []

    shares = annual("shares_outstanding")
    if len(shares) >= 2:
        last, prev, first = shares[-1], shares[-2], shares[0]
        change_1y = ((last["val"] - prev["val"]) / prev["val"] * 100.0) if prev["val"] else None
        span = max(len(shares) - 1, 1)
        total = ((last["val"] / first["val"]) ** (1.0 / span) - 1) * 100.0 if first["val"] else None
        components["buyback_trajectory"] = {
            "share_count_change_1y_pct": round(change_1y, 2) if change_1y is not None else None,
            "share_count_cagr_pct": round(total, 2) if total is not None else None,
            "years_observed": len(shares),
            "read": _series_read(change_1y if change_1y is not None else 0.0),
            "evidence_ref": {
                "tag": (concepts.get("shares_outstanding") or {}).get("tag"),
                "first": {"end": first.get("end"), "accn": first.get("accn")},
                "last": {"end": last.get("end"), "accn": last.get("accn")},
            },
        }
    else:
        abstentions.append("buyback_trajectory:missing_share_count_pair")

    capex, ocf = annual("capital_expenditures"), annual("operating_cash_flow")
    ocf_by_end = {r["end"]: r["val"] for r in ocf}
    ratios = [
        (r["end"], abs(r["val"]) / abs(ocf_by_end[r["end"]]))
        for r in capex
        if r["end"] in ocf_by_end and ocf_by_end[r["end"]]
    ]
    if ratios:
        latest_end, latest_ratio = ratios[-1]
        med = sorted(v for _, v in ratios)[len(ratios) // 2]
        components["capex_intensity"] = {
            "capex_to_ocf": round(latest_ratio, 3),
            "capex_to_ocf_median": round(med, 3),
            "years_observed": len(ratios),
            "period_end": latest_end,
            "read": (
                "reinvesting_heavily" if latest_ratio > 0.6
                else ("balanced" if latest_ratio > 0.25 else "capital_light")
            ),
            "negative_ocf_years": sum(1 for r in ocf if r["val"] < 0),
            "evidence_ref": {
                "capex_tag": (concepts.get("capital_expenditures") or {}).get("tag"),
                "ocf_tag": (concepts.get("operating_cash_flow") or {}).get("tag"),
            },
        }
    else:
        abstentions.append("capex_intensity:missing_capex_or_ocf")

    buybacks, dividends, net_income = (
        annual("buybacks_paid"), annual("dividends_paid"), annual("net_income"),
    )
    if buybacks or dividends:
        recent_bb = [r["val"] for r in buybacks[-3:]]
        recent_dv = [r["val"] for r in dividends[-3:]]
        ni_by_end = {r["end"]: r["val"] for r in net_income}
        payout = None
        if buybacks and buybacks[-1]["end"] in ni_by_end and ni_by_end[buybacks[-1]["end"]]:
            total_returned = buybacks[-1]["val"] + (
                dividends[-1]["val"] if dividends and dividends[-1]["end"] == buybacks[-1]["end"] else 0
            )
            payout = round(total_returned / ni_by_end[buybacks[-1]["end"]], 3)
        components["shareholder_returns"] = {
            "buybacks_3y": recent_bb,
            "dividends_3y": recent_dv,
            "total_payout_ratio_latest": payout,
            "evidence_ref": {
                "buybacks_tag": (concepts.get("buybacks_paid") or {}).get("tag"),
                "dividends_tag": (concepts.get("dividends_paid") or {}).get("tag"),
            },
        }

    return components, abstentions


def spawner_scores(pack: dict, evidence_dir: Path) -> dict:
    block: dict = {"pack_hash": pack["pack_hash"], "components": {}, "abstentions": []}

    concepts = ((pack.get("xbrl_series") or {}).get("concepts")) or {}
    if concepts:
        block["basis"] = "xbrl_series"
        block["components"], block["abstentions"] = _xbrl_spawner_components(concepts)
    else:
        # Fallback: single-filing pair from filing_facts (pre-XBRL behavior).
        block["basis"] = "filing_facts"
        metrics = _latest_filing_facts(evidence_dir)

        def pair(key: str) -> tuple[float | None, float | None]:
            entry = metrics.get(key) or {}
            return entry.get("current"), entry.get("prior")

        shares_cur, shares_pri = pair("shares_outstanding")
        capex_cur, _ = pair("capital_expenditures")
        ocf_cur, _ = pair("operating_cash_flow")

        if shares_cur and shares_pri:
            change_pct = (shares_cur - shares_pri) / shares_pri * 100.0
            block["components"]["buyback_trajectory"] = {
                "share_count_change_pct": round(change_pct, 2),
                "read": _series_read(change_pct),
                "evidence_ref": {"metric": "shares_outstanding", "tag": metrics["shares_outstanding"].get("tag")},
            }
        else:
            block["abstentions"].append("buyback_trajectory:missing_share_count_pair")

        if capex_cur is not None and ocf_cur:
            ratio = abs(capex_cur) / abs(ocf_cur)
            block["components"]["capex_intensity"] = {
                "capex_to_ocf": round(ratio, 3),
                "read": "reinvesting_heavily" if ratio > 0.6 else ("balanced" if ratio > 0.25 else "capital_light"),
                "evidence_ref": {
                    "capex_tag": metrics["capital_expenditures"].get("tag"),
                    "ocf_tag": metrics["operating_cash_flow"].get("tag"),
                },
            }
        else:
            block["abstentions"].append("capex_intensity:missing_capex_or_ocf")

    # Small-bet / kill discipline need segment-level history — abstain rather
    # than fabricate a score from insufficient inputs.
    block["abstentions"].append("small_bet_discipline:requires_segment_history")
    block["abstentions"].append("kill_discipline:requires_segment_history")
    return block


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def _latest_pack(evidence_dir: Path) -> dict | None:
    return _latest_json(evidence_dir, "ssi_evidence_pack")


def build_claims(ticker_dir: Path, as_of: str) -> dict | None:
    evidence_dir = ticker_dir / "research" / "evidence"
    if not evidence_dir.is_dir():
        return None
    pack = _latest_pack(evidence_dir)
    if pack is None:
        return None

    claims, sentinel_meta = sentinel_claims(pack)
    claims.sort(key=lambda c: (-c["severity"], c["taxonomy"], c["claim_id"]))
    ledger = management_ledger(pack, evidence_dir, as_of)
    spawner = spawner_scores(pack, evidence_dir)

    severity_hist = {str(n): sum(1 for c in claims if c["severity"] == n) for n in range(1, 6)}
    tier_hist = {
        tier: sum(1 for c in claims if c.get("concept_tier") == tier)
        for tier in ("primary", "secondary", "footnote_detail")
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "ticker": pack["ticker"],
        "as_of": as_of,
        "pack_hash": pack["pack_hash"],
        "pack_as_of": pack.get("as_of"),
        "claims": claims,
        "claim_count": len(claims),
        "severity_histogram": severity_hist,
        "concept_tier_histogram": tier_hist,
        "management_ledger": ledger,
        "spawner": spawner,
        "dropped_modalities": {
            **sentinel_meta,
            "market_mechanics": "requires borrow/days-to-cover feed (see refresh_short_alpha_borrow.py)",
        },
    }


def write_claims(ticker_dir: Path, as_of: str) -> Path | None:
    result = build_claims(ticker_dir, as_of)
    if result is None:
        return None
    out = ticker_dir / "research" / "evidence" / f"ssi_claims_{as_of}.json"
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tickers", nargs="*", help="Ticker folders (default: all with an evidence pack)")
    parser.add_argument("--date", default=datetime.now().date().isoformat())
    parser.add_argument("--check", action="store_true", help="Build in memory and report, do not write")
    args = parser.parse_args(argv)

    if args.tickers:
        ticker_dirs = [ROOT / t for t in args.tickers]
    else:
        ticker_dirs = sorted(
            {p.parents[2] for p in ROOT.glob("*/research/evidence/ssi_evidence_pack_*.json")}
        )

    failures = 0
    for ticker_dir in ticker_dirs:
        if args.check:
            result = build_claims(ticker_dir, args.date)
            if result is None:
                print(f"[skip] {ticker_dir.name}: no evidence pack (run build_ssi_evidence_pack.py first)")
                failures += 1
                continue
            sev5 = result["severity_histogram"]["5"]
            print(
                f"[check] {ticker_dir.name}: {result['claim_count']} claims "
                f"(sev5: {sev5}), ledger {result['management_ledger']['promise_count']} promises"
            )
        else:
            out = write_claims(ticker_dir, args.date)
            if out is None:
                print(f"[skip] {ticker_dir.name}: no evidence pack (run build_ssi_evidence_pack.py first)")
                failures += 1
            else:
                print(f"[ok] {out.relative_to(ROOT)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
