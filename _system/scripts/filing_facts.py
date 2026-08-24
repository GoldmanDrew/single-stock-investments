"""Extract canonical filing metrics from cached full-tier _text extracts.

Used by build_filing_evidence.py → research/evidence/filing_facts_{date}.json
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

# IX line format from build_filing_evidence HTML extract: "Revenues: 619.8"
IX_LINE = re.compile(r"^([A-Za-z][A-Za-z0-9]*(?:\.[A-Za-z0-9]+)*):\s*([\d,.\-]+|&#8212;|\u2014|no)$")

CANONICAL = {
    "revenues": (
        "Revenues",
        "Revenue",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueNet",
    ),
    "operating_income": ("OperatingIncomeLoss",),
    "net_income": (
        "NetIncomeLoss",
        "NetIncomeLossAvailableToCommonStockholdersBasic",
        "ProfitLoss",
    ),
    "eps_basic": ("EarningsPerShareBasic",),
    "total_assets": ("Assets",),
    "stockholders_equity": (
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ),
    "long_term_debt": (
        "LongTermDebt",
        "LongTermDebtNoncurrent",
        "DebtInstrumentCarryingAmount",
    ),
    "cash": (
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ),
    "operating_cash_flow": (
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ),
    "capital_expenditures": (
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsForAdditionsToPropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
    ),
    "shares_outstanding": (
        "EntityCommonStockSharesOutstanding",
        "CommonStockSharesOutstanding",
        "WeightedAverageNumberOfDilutedSharesOutstanding",
        "WeightedAverageNumberOfSharesOutstandingBasic",
    ),
}

BALANCE_SHEET_METRICS = {"cash", "long_term_debt", "total_assets", "stockholders_equity"}
INCOME_METRICS = {
    "revenues", "revenue", "operating_income", "net_income", "eps_basic",
    "operating_cash_flow", "capital_expenditures", "shares_outstanding",
}

SEGMENT_CONTEXT_TAGS = {
    "NumberOfOperatingSegments",
    "SegmentReportingInformation",
    "NumberOfReportableSegments",
}

FOOTNOTE_CONTEXT_PREFIXES = (
    "DebtInstrument",
    "Derivative",
    "ShareBased",
    "OperatingLease",
    "FairValue",
    "Convertible",
)

FILING_NAME_RE = re.compile(
    r"^(?P<form>10-K|10-Q|20-F|40-F|8-K|S-1|DEF\s14A|Semi-Annual|Annual_Report|Quarterly|Interim)"
    r"_(?P<file_date>\d{8})"
    r"(?:_rpt(?P<period_end>\d{8}))?",
    re.I,
)


@dataclass(frozen=True)
class TaggedValue:
    line: int
    tag: str
    value: float


def _parse_num(raw: str) -> float | None:
    raw = raw.strip().replace(",", "")
    if raw in ("", "—", "-", "&#8212;", "no"):
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def parse_ix_fact_lines(text: str) -> dict[str, list[float]]:
    """Return tag → list of numeric values in document order (pairs often current/prior)."""
    _lines, indexed = parse_ix_fact_lines_indexed(text)
    return {tag: [item.value for item in items] for tag, items in indexed.items()}


def parse_ix_fact_lines_indexed(text: str) -> tuple[list[str], dict[str, list[TaggedValue]]]:
    lines = text.splitlines()
    out: dict[str, list[TaggedValue]] = {}
    for line_no, raw in enumerate(lines, start=1):
        line = raw.strip()
        match = IX_LINE.match(line)
        if not match:
            continue
        tag, val_s = match.group(1), match.group(2)
        val = _parse_num(val_s)
        if val is None:
            continue
        short = tag.split(":")[-1] if ":" in tag else tag
        out.setdefault(short, []).append(TaggedValue(line=line_no, tag=short, value=val))
    return lines, out


def _context_flags(lines: list[str], line_no: int, window: int = 8) -> set[str]:
    flags: set[str] = set()
    start = max(0, line_no - window - 1)
    for ctx_line in lines[start : line_no - 1]:
        ctx = ctx_line.strip()
        if not ctx or ":" not in ctx:
            continue
        tag = ctx.split(":", 1)[0].strip()
        if tag in SEGMENT_CONTEXT_TAGS:
            flags.add("segment_block")
        if any(tag.startswith(prefix) for prefix in FOOTNOTE_CONTEXT_PREFIXES):
            flags.add("footnote_block")
    return flags


def _score_candidate_pair(
    canon: str,
    current: float,
    prior: float,
    cur_line: int,
    pri_line: int,
    cur_flags: set[str],
    pri_flags: set[str],
) -> tuple[float, list[str]]:
    score = 100.0
    flags: list[str] = []

    if "segment_block" in cur_flags and canon in INCOME_METRICS and current == 0:
        score -= 85
        flags.append("segment_context")

    if "footnote_block" in pri_flags or "footnote_block" in cur_flags:
        if canon in BALANCE_SHEET_METRICS:
            score -= 70
            flags.append("footnote_pairing")

    if canon in BALANCE_SHEET_METRICS and max(abs(current), abs(prior)) < 10:
        score -= 60
        flags.append("immaterial_values")

    if canon == "long_term_debt" and max(abs(current), abs(prior)) < 1_000:
        score -= 80
        flags.append("non_statement_debt")

    if abs(prior) < 100 and abs(current) > 10_000:
        score -= 75
        flags.append("immaterial_prior")

    if canon in {"revenues", "revenue"} and current == 0 and abs(prior) > 1_000:
        score -= 90
        flags.append("segment_zero_revenue")

    if prior != 0:
        pct = abs((current - prior) / prior) * 100.0
        if pct > 500:
            score -= 50
            flags.append("extreme_pct")

    gap = abs(cur_line - pri_line)
    if gap <= 3:
        score += 15
    elif gap <= 10:
        score += 5
    elif gap > 50:
        score -= 20

    if prior != 0 and current != 0:
        ratio = max(abs(current), abs(prior)) / max(min(abs(current), abs(prior)), 1e-9)
        if ratio > 100:
            score -= 40
            flags.append("magnitude_mismatch")

    if canon in {"revenues", "revenue"}:
        score += min(abs(current) + abs(prior), 100_000) / 10_000

    return score, flags


def _confidence_from_score(score: float, flags: list[str]) -> str:
    if score >= 80 and not flags:
        return "high"
    if score >= 55 and "extreme_pct" not in flags:
        return "medium"
    return "low"


def select_best_pair(canon: str, tag: str, occurrences: list[TaggedValue], lines: list[str]) -> dict:
    if not occurrences:
        return {
            "current": None,
            "prior": None,
            "tag": tag,
            "all_values": [],
            "parser_confidence": "low",
            "parser_flags": ["missing_values"],
        }
    if len(occurrences) == 1:
        only = occurrences[0]
        return {
            "current": only.value,
            "prior": None,
            "tag": tag,
            "all_values": [only.value],
            "current_line": only.line,
            "parser_confidence": "medium",
            "parser_flags": ["single_value"],
            "extract_snippet": f"{tag}: {only.value}",
            "comparison": "single_period",
        }

    best: tuple[TaggedValue, TaggedValue, list[str], float] | None = None
    best_score = -999.0
    for idx in range(len(occurrences) - 1):
        current = occurrences[idx]
        prior = occurrences[idx + 1]
        cur_flags = _context_flags(lines, current.line)
        pri_flags = _context_flags(lines, prior.line)
        score, flags = _score_candidate_pair(
            canon,
            current.value,
            prior.value,
            current.line,
            prior.line,
            cur_flags,
            pri_flags,
        )
        if score > best_score:
            best_score = score
            best = (current, prior, flags, score)

    if best is None:
        return {
            "current": None,
            "prior": None,
            "tag": tag,
            "all_values": [item.value for item in occurrences[:6]],
            "parser_confidence": "low",
            "parser_flags": ["no_pair"],
        }

    current, prior, flags, score = best
    confidence = _confidence_from_score(score, flags)
    if score < 40 and canon == "long_term_debt":
        large = [item for item in occurrences if item.value >= 1_000]
        if large:
            only = large[0]
            return {
                "current": only.value,
                "prior": None,
                "tag": tag,
                "all_values": [item.value for item in occurrences[:6]],
                "current_line": only.line,
                "parser_confidence": "medium",
                "parser_flags": ["no_prior_period"],
                "comparison": "new_balance_sheet_item",
                "extract_snippet": f"{tag}: {only.value:,.4g}",
            }
    return {
        "current": current.value,
        "prior": prior.value,
        "tag": tag,
        "all_values": [item.value for item in occurrences[:6]],
        "current_line": current.line,
        "prior_line": prior.line,
        "parser_confidence": confidence,
        "parser_flags": flags,
        "pair_score": round(score, 1),
        "comparison": "YoY annual",
        "extract_snippet": f"{tag}: {current.value:,.4g}\n{tag}: {prior.value:,.4g}",
    }


def _first_pair(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"current": None, "prior": None}
    if len(values) == 1:
        return {"current": values[0], "prior": None}
    return {"current": values[0], "prior": values[1]}


def canonical_metrics(ix: dict[str, list[float]], lines: list[str] | None = None, indexed: dict[str, list[TaggedValue]] | None = None) -> dict:
    if lines is not None and indexed is not None:
        metrics: dict = {}
        for canon, tags in CANONICAL.items():
            for tag in tags:
                if tag in indexed:
                    metrics[canon] = select_best_pair(canon, tag, indexed[tag], lines)
                    break
        return metrics

    metrics = {}
    for canon, tags in CANONICAL.items():
        for tag in tags:
            if tag in ix:
                pair = _first_pair(ix[tag])
                metrics[canon] = {**pair, "tag": tag, "all_values": ix[tag][:6], "parser_confidence": "low", "parser_flags": ["legacy_pairing"]}
                break
    return metrics


def source_filing_ref_from_text_path(ticker: str, source_text: str | None) -> str | None:
    if not source_text:
        return None
    stem = Path(str(source_text).replace("\\", "/")).name
    if stem.endswith(".txt"):
        stem = stem[:-4]
    if not stem:
        return None
    return f"{ticker}/investor-documents/sec-edgar/{stem}"


def filing_metadata_from_text_path(source_text: str | None) -> dict:
    if not source_text:
        return {}
    stem = Path(str(source_text).replace("\\", "/")).name
    if stem.endswith(".txt"):
        stem = stem[:-4]
    match = FILING_NAME_RE.match(stem.replace(" ", "_"))
    if not match:
        form = stem.split("_", 1)[0].replace(" ", "-")
        return {"filing_form": form, "source_filename": stem}
    file_date = match.group("file_date")
    period_end = match.group("period_end")
    meta = {
        "filing_form": match.group("form").upper().replace(" ", "-"),
        "filing_date": f"{file_date[:4]}-{file_date[4:6]}-{file_date[6:8]}",
        "source_filename": stem,
    }
    if period_end:
        meta["period_end"] = f"{period_end[:4]}-{period_end[4:6]}-{period_end[6:8]}"
    return meta


def latest_full_text_path(evidence_dir: Path) -> Path | None:
    text_dir = evidence_dir / "_text"
    if not text_dir.is_dir():
        return None
    files = sorted(text_dir.glob("*.txt"), key=lambda p: p.name, reverse=True)
    prefs = (
        "exhibit99-2",
        "Annual_Report",
        "annual",
        "10-K",
        "10_K",
        "40-F",
        "Semi-Annual",
        "10-Q",
        "10_Q",
        "Quarterly",
        "Interim",
    )
    for pref in prefs:
        for f in files:
            if pref.lower() in f.name.lower() and "mgmt" not in f.parts and f.stat().st_size > 0:
                return f
    for f in files:
        if f.stat().st_size > 0:
            return f
    return None


def parse_otc_prose_metrics(text: str) -> dict:
    """Extract disclosure-form metrics from OTC / IR PDF text extracts."""
    metrics: dict = {}
    m = re.search(r"Total shares outstanding:\s*([\d,]+)", text, re.I)
    if m:
        metrics["shares_outstanding"] = {
            "current": int(m.group(1).replace(",", "")),
            "source": "otc_disclosure_form",
            "parser_confidence": "medium",
            "parser_flags": [],
        }
    m = re.search(r"over\s+([\d.]+)\s+million\s+acres", text, re.I)
    if m:
        metrics["mineral_acres_gross"] = {
            "current": f">{m.group(1)}M",
            "source": "otc_disclosure_form",
            "parser_confidence": "medium",
            "parser_flags": [],
        }
    m = re.search(r"agreement on\s+([\d,]+)\s+acres", text, re.I)
    if m:
        metrics["leased_acres"] = {
            "current": int(m.group(1).replace(",", "")),
            "source": "otc_disclosure_form",
            "parser_confidence": "medium",
            "parser_flags": [],
        }
    for label, key in (
        (r"Net income[^\d$]*\$?\s*([\d,]+)", "net_income"),
        (r"Mineral lease[^\d$]*\$?\s*([\d,]+)", "mineral_lease_income"),
        (r"book value[^\d$]*\$?\s*([\d,.]+)\s*per share", "book_value_per_share"),
        (r"Total stockholders[^\']*equity[^\d$]*\$?\s*([\d,]+)", "stockholders_equity"),
    ):
        m = re.search(label, text, re.I)
        if m and key not in metrics:
            raw = m.group(1).replace(",", "")
            try:
                val = float(raw)
            except ValueError:
                continue
            metrics[key] = {
                "current": val,
                "source": "otc_prose_regex",
                "parser_confidence": "medium",
                "parser_flags": [],
            }
    return metrics


COMPANYFACTS_FALLBACK = {
    "cash": (
        ("ifrs-full", "CashAndCashEquivalents"),
        ("us-gaap", "CashAndCashEquivalentsAtCarryingValue"),
    ),
    "stockholders_equity": (
        ("ifrs-full", "Equity"),
        ("us-gaap", "StockholdersEquity"),
    ),
    "net_income": (
        ("ifrs-full", "ProfitLoss"),
        ("us-gaap", "NetIncomeLoss"),
    ),
    "operating_cash_flow": (
        ("ifrs-full", "CashFlowsFromUsedInOperatingActivities"),
        ("us-gaap", "NetCashProvidedByUsedInOperatingActivities"),
    ),
    "revenues": (
        ("ifrs-full", "Revenue"),
        ("ifrs-full", "Revenues"),
        ("us-gaap", "Revenues"),
    ),
}


def metrics_from_companyfacts(evidence_dir: Path) -> dict:
    """Fallback when HTML extract has no inline XBRL (common for IFRS 40-F shells)."""
    path = evidence_dir / "sec_companyfacts.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    facts = payload.get("facts") or {}
    metrics: dict = {}
    for canon, specs in COMPANYFACTS_FALLBACK.items():
        for namespace, tag in specs:
            block = (facts.get(namespace) or {}).get(tag)
            if not block:
                continue
            units = block.get("units") or {}
            best_row = None
            best_end = ""
            for unit_key, rows in units.items():
                for row in rows:
                    end = str(row.get("end") or "")
                    if end >= best_end:
                        best_end = end
                        best_row = row
                        best_unit = unit_key
            if best_row is None:
                continue
            metrics[canon] = {
                "current": best_row.get("val"),
                "prior": None,
                "source": f"sec_companyfacts:{namespace}:{tag}",
                "unit": best_unit,
                "as_of": best_end,
                "parser_confidence": "high",
                "parser_flags": ["companyfacts_fallback"],
            }
            break
    return metrics


def build_filing_facts(ticker: str, evidence_dir: Path, source_path: Path | None) -> dict:
    if source_path is None or not source_path.exists():
        return {
            "ticker": ticker,
            "error": "no_full_tier_text_extract",
            "metrics": {},
        }
    text = source_path.read_text(encoding="utf-8", errors="ignore")[:250_000]
    lines, indexed = parse_ix_fact_lines_indexed(text)
    ix = {tag: [item.value for item in items] for tag, items in indexed.items()}
    metrics = canonical_metrics(ix, lines=lines, indexed=indexed)
    parser = "ix_facts"
    if not metrics:
        otc = parse_otc_prose_metrics(text)
        if otc:
            metrics = otc
            parser = "otc_prose"
    if not metrics:
        cf = metrics_from_companyfacts(evidence_dir)
        if cf:
            metrics = cf
            parser = "companyfacts_fallback"
    try:
        rel_src = source_path.relative_to(evidence_dir.parent)
    except ValueError:
        rel_src = source_path.name
    rel_src_s = str(rel_src).replace("\\", "/")
    filing_meta = filing_metadata_from_text_path(rel_src_s)
    source_filing = source_filing_ref_from_text_path(ticker, rel_src_s)
    out = {
        "ticker": ticker,
        "source_text": rel_src_s,
        "source_filing_ref": source_filing,
        "filing_meta": filing_meta,
        "metrics": metrics,
        "raw_tag_count": len(ix),
        "parser": parser,
    }
    return out


def write_filing_facts_json(ticker_dir: Path, as_of: str) -> Path | None:
    evidence_dir = ticker_dir / "research" / "evidence"
    src = latest_full_text_path(evidence_dir)
    facts = build_filing_facts(ticker_dir.name, evidence_dir, src)
    facts["as_of"] = as_of
    out = evidence_dir / f"filing_facts_{as_of}.json"
    if not evidence_dir.exists():
        return None
    evidence_dir.mkdir(parents=True, exist_ok=True)
    if not facts.get("metrics"):
        candidates = [out] if out.exists() else []
        candidates.extend(sorted(evidence_dir.glob("filing_facts_*.json"), reverse=True))
        for p in candidates:
            if not p.exists():
                continue
            try:
                old = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if old.get("metrics"):
                facts["metrics"] = old["metrics"]
                if p != out:
                    facts["metrics_preserved_from"] = p.name
                break
    out.write_text(json.dumps(facts, indent=2) + "\n", encoding="utf-8")
    return out
