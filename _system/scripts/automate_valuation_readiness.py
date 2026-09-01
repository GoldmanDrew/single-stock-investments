#!/usr/bin/env python3
"""Resumable proof-first onboarding and valuation readiness automation.

The pipeline is deliberately fail closed: downloading a document never marks a
task ready.  A task is ready only when a field in the source-locked fact ledger
satisfies it, and a valuation is decision-grade only after the universal
contract validates its deterministic calculation proof.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
import subprocess
import sys
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

from power_zone_router import build_route
from calculation_proof import evaluate_calculation_proof
from marvin_valuation import compute_component_valuation
from economic_value_framework import build_economic_value_analysis

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "_system" / "scripts"
REGISTRY = ROOT / "_system" / "portfolio" / "registry.json"
OVERRIDES = ROOT / "_system" / "reference" / "security_identity_overrides.json"
METHODS = ROOT / "_system" / "reference" / "valuation_method_registry.json"
FX_RATES = ROOT / "_system" / "reference" / "market-data" / "fx_rates.json"


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {} if default is None else default


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def resolve_identity(
    ticker: str,
    entry: dict,
    overrides: dict,
    as_of: str,
    route: dict | None = None,
) -> dict:
    reviewed = (overrides.get("tickers") or {}).get(ticker, {})
    company = str(entry.get("company") or ticker)
    text = company.lower()
    security_type = reviewed.get("security_type")
    if not security_type:
        security_type = "exchange_traded_fund" if any(x in text for x in (" etf", " fund", " trust")) else "operating_company"
    archetype = reviewed.get("archetype") or ("holding_company" if security_type == "exchange_traded_fund" else "compounder")
    route = route or {}
    route_methods = route.get("primary_methods") or []
    route_has_signal = bool(route_methods) and (
        float(route.get("score") or 0) > 0
        or str(route.get("status") or "") not in {"", "default_needs_review"}
    )
    fallback_profile = "catalyst_asset_value" if security_type == "exchange_traded_fund" else "quality_reinvestment"
    fallback_method = "net_asset_value" if security_type == "exchange_traded_fund" else "owner_earnings_reinvestment_dcf"
    profile = reviewed.get("valuation_profile") or (
        route.get("profile_id") if route_has_signal else fallback_profile
    )
    method = reviewed.get("primary_method") or (
        route_methods[0] if route_has_signal else fallback_method
    )
    if reviewed.get("primary_method"):
        method_source = "reviewed_override"
    elif route_has_signal:
        method_source = "power_zone_route"
    else:
        method_source = "deterministic_fallback_pending_route_evidence"
    return {
        "schema_version": "1.0", "ticker": ticker, "as_of": as_of,
        "issuer_name": reviewed.get("issuer_name") or company,
        "security_type": security_type, "market": entry.get("market"),
        "cik": (entry.get("download") or {}).get("cik"),
        "archetype": archetype, "valuation_profile": profile,
        "primary_method": method,
        "method_source": method_source,
        "route_status": route.get("status"),
        "route_score": route.get("score"),
        "route_input_hash": route.get("input_hash"),
        "status": "reviewed_override" if reviewed else "rule_resolved",
        "reason": reviewed.get("reason") or "Resolved from registry metadata and deterministic name/type rules.",
        "reviewed_at": reviewed.get("reviewed_at"),
    }


def latest_filing_facts(ticker: str) -> tuple[Path | None, dict]:
    files = sorted((ROOT / ticker / "research" / "evidence").glob("filing_facts_*.json"), reverse=True)
    for path in files:
        payload = read_json(path)
        if payload.get("metrics"):
            return path, payload
    return None, {}


def fetch_companyfacts(ticker: str, cik: str | None) -> dict:
    if not cik:
        return {"returncode": 0, "stdout": "No CIK; companyfacts not applicable.", "stderr": ""}
    target = ROOT / ticker / "research" / "evidence" / "sec_companyfacts.json"
    try:
        req = urllib.request.Request(
            f"https://data.sec.gov/api/xbrl/companyfacts/CIK{str(cik).zfill(10)}.json",
            headers={"User-Agent": "ProofFirstValuationAutomation research@example.com"},
        )
        with urllib.request.urlopen(req, timeout=120) as response:
            payload = response.read()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        return {"returncode": 0, "stdout": f"Saved {target.relative_to(ROOT)}", "stderr": ""}
    except Exception as exc:
        return {"returncode": 1, "stdout": "", "stderr": f"{type(exc).__name__}: {exc}"}


def _latest_companyfact(payload: dict, namespace: str, tags: list[str], annual: bool) -> tuple[str, dict] | None:
    namespace_facts = (payload.get("facts") or {}).get(namespace) or {}
    candidates = []
    for priority, tag in enumerate(tags):
        record = namespace_facts.get(tag) or {}
        for unit, rows in (record.get("units") or {}).items():
            for row in rows:
                form = str(row.get("form") or "")
                if annual and form not in {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}:
                    continue
                if row.get("val") is None or not row.get("end"):
                    continue
                candidates.append((
                    str(row.get("end")),
                    str(row.get("filed") or ""),
                    -priority,
                    tag,
                    unit,
                    row,
                ))
    if not candidates:
        return None
    # Sort only on comparable keys; the raw row dict is not orderable.
    # The tag list is ordered by semantic preference.  When two concepts have
    # the same observation date (common for cash), prefer the first tag rather
    # than a lexicographically later aggregate such as cash plus restricted
    # clearing balances.
    _end, _filed, _priority, tag, unit, row = max(
        candidates, key=lambda item: (item[0], item[1], item[2], item[3], item[4])
    )
    return tag, {**row, "unit": unit}


def _latest_across_companyfacts(
    payload: dict, specs: list[tuple[str, list[str]]], annual: bool
) -> tuple[str, str, dict] | None:
    candidates = []
    for namespace, tags in specs:
        selected = _latest_companyfact(payload, namespace, tags, annual)
        if selected:
            tag, row = selected
            candidates.append((str(row.get("end") or ""), str(row.get("filed") or ""), namespace, tag, row))
    if not candidates:
        return None
    _end, _filed, namespace, tag, row = max(candidates, key=lambda item: (item[0], item[1]))
    return namespace, tag, row


# A foreign private issuer filing under IFRS has no ``dei`` share tag in its
# companyfacts payload: the DEI cover element is only produced by the domestic
# forms. Its issuer-wide count lives in the IFRS taxonomy instead, so both the
# point-in-time and the weighted lists carry an ifrs-full equivalent. Without
# these, an IFRS filer dead-ends on shares_outstanding forever (NVO, 2026-08-09).
ENTITY_SHARE_SPECS = [
    ("dei", ["EntityCommonStockSharesOutstanding"]),
    ("ifrs-full", ["NumberOfSharesOutstanding"]),
]
WEIGHTED_SHARE_SPECS = [
    ("us-gaap", [
        "WeightedAverageNumberOfDilutedSharesOutstanding",
        "WeightedAverageNumberOfSharesOutstandingBasic",
    ]),
    # IAS 33 elements: WeightedAverageShares is basic, AdjustedWeightedAverageShares
    # is diluted. (``WeightedAverageNumberOfSharesOutstanding`` is a us-gaap-shaped
    # name that does not exist in ifrs-full and never matched anything.)
    ("ifrs-full", [
        "AdjustedWeightedAverageShares",
        "WeightedAverageShares",
    ]),
]


def _select_share_companyfact(payload: dict) -> tuple[str, dict] | None:
    """Choose the freshest issuer-wide share denominator.

    SEC ``dei:EntityCommonStockSharesOutstanding`` occasionally contains an
    old class-member or spin-formation artifact. Current diluted/basic weighted
    shares are a safer fallback than accepting that stale value merely because
    it is the only DEI row.
    """
    entity = _latest_across_companyfacts(payload, ENTITY_SHARE_SPECS, annual=False)
    weighted = _latest_across_companyfacts(payload, WEIGHTED_SHARE_SPECS, annual=False)
    candidates = [row for row in (entity, weighted) if row]
    if not candidates:
        return None
    selected = max(candidates, key=lambda item: (str(item[2].get("end") or ""), str(item[2].get("filed") or "")))
    if entity and weighted:
        entity_value = float(entity[2]["val"])
        weighted_value = float(weighted[2]["val"])
        ratio = entity_value / weighted_value if weighted_value > 0 else 0
        try:
            date_gap_days = abs(
                (date.fromisoformat(str(entity[2]["end"])[:10])
                 - date.fromisoformat(str(weighted[2]["end"])[:10])).days
            )
        except (TypeError, ValueError):
            date_gap_days = 10_000
        # A current cover count normally reconciles closely to weighted shares.
        # Large divergence signals a class-member/context artifact; use the
        # issuer-wide weighted denominator until class counts can be reconciled.
        if date_gap_days <= 550 and (ratio < 0.5 or ratio > 1.5):
            selected = weighted
    namespace, tag, row = selected
    return tag, {**row, "namespace": namespace}


COVER_SHARE_DIRECTIVE = re.compile(r"Indicate the number of outstanding shares", re.I)
COVER_SHARE_TERMINATOR = re.compile(r"Indicate by check mark", re.I)
# Only comma-grouped counts of a million or more: enough to skip nominal values
# ("DKK 0.10 each"), item numbers and years without guessing at bare integers.
COVER_SHARE_COUNT = re.compile(r"\b\d{1,3}(?:,\d{3}){2,}\b")
COVER_FILING_DATE = re.compile(r"_(\d{8})")


def _cover_page_share_count(ticker: str) -> dict | None:
    """Share count summed over the classes on the latest 20-F/40-F cover page.

    Last resort for a foreign private issuer whose companyfacts payload carries
    no share concept at all. Item 'Indicate the number of outstanding shares of
    each of the issuer's classes of capital or common stock' is a required cover
    item, so the classes are enumerated there even when the taxonomy is silent.
    Returns a locked-fact row, or None when the cover cannot be read
    unambiguously - a wrong denominator is worse than a blocked one.
    """
    docs = ROOT / ticker / "investor-documents" / "sec-edgar"
    filings = [p for p in docs.glob("*.htm*") if p.name.split("_")[0] in {"20-F", "40-F"}]
    if not filings:
        return None
    def filed_on(path: Path) -> str:
        match = COVER_FILING_DATE.search(path.name)
        return match.group(1) if match else ""
    filing = max(filings, key=lambda p: (filed_on(p), p.name))
    extract = ROOT / ticker / "research" / "evidence" / "_text" / f"{filing.name}.txt"
    try:
        text = extract.read_text(encoding="utf-8", errors="replace") if extract.is_file() else re.sub(
            r"<[^>]+>", " ", filing.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None
    start = COVER_SHARE_DIRECTIVE.search(text)
    if not start:
        return None
    tail = text[start.end():start.end() + 1500]
    stop = COVER_SHARE_TERMINATOR.search(tail)
    window = tail[:stop.start()] if stop else tail
    counts = [int(raw.replace(",", "")) for raw in COVER_SHARE_COUNT.findall(window)]
    if not counts:
        return None
    line = text.count("\n", 0, start.start()) + 1
    classes = " + ".join(f"{value:,}" for value in counts)
    period_end = ""
    period = re.search(r"_rpt(\d{8})", filing.name)
    if period:
        stamp = period.group(1)
        period_end = f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:]}"
    return {
        "field_id": "shares_outstanding", "value": float(sum(counts)), "unit": "shares",
        "locked": True, "confidence": "medium",
        "source": {
            "ref": str(filing.relative_to(ROOT)).replace("\\", "/"),
            "locator": (f"{filing.name.split('_')[0]} cover page, 'Indicate the number of outstanding "
                        f"shares of each of the issuer's classes'; classes {classes}; "
                        f"text extract line {line}"),
            "as_of": period_end or None,
            "content_sha256": sha256(filing),
        },
    }


_ISO_CURRENCY = re.compile(r"^[A-Z]{3}$")


def _companyfacts_currency(unit_key: str) -> str | None:
    """ISO currency of a companyfacts unit key ("DKK", "USD", "EUR/shares")."""
    base = str(unit_key).split("/", 1)[0].strip()
    return base if _ISO_CURRENCY.match(base) else None


def _usd_conversion(
    ticker: str, field_id: str, unit_key: str, fact_end: str, fx_payload: dict
) -> tuple[float, dict | None] | None:
    """Divisor and provenance that turn a companyfacts value into USD.

    The ledger's monetary interface is USD millions, so the recorded unit is
    only honest when the source unit key is USD or an explicit, evidenced FX
    conversion is applied. Returns ``(divisor, fx_conversion_or_None)``, or
    ``None`` when the fact must NOT be locked: the unit key is not a monetary
    ISO code, or the source currency is non-USD and no FX rate row (rate,
    date, source) within 45 days of the fact's period end exists in
    ``FX_RATES``. Locking anyway is exactly the NVO DKK-labeled-as-USD
    corruption (2026-08-09).
    """
    currency = _companyfacts_currency(unit_key)
    if currency == "USD":
        return 1.0, None
    if currency is None:
        print(f"REFUSED to lock {ticker} {field_id}: companyfacts unit key "
              f"'{unit_key}' is not a monetary ISO currency code.")
        return None
    fx_ref = str(FX_RATES.relative_to(ROOT)).replace("\\", "/")
    candidates = []
    for row in (fx_payload.get("rates") or {}).get(currency) or []:
        rate, rate_as_of = row.get("rate_per_usd"), str(row.get("as_of") or "")
        if not isinstance(rate, (int, float)) or rate <= 0 or not row.get("source"):
            continue
        try:
            gap_days = abs((date.fromisoformat(rate_as_of[:10])
                            - date.fromisoformat(str(fact_end)[:10])).days)
        except (TypeError, ValueError):
            continue
        if gap_days <= 45:
            candidates.append((gap_days, rate_as_of, float(rate), str(row["source"])))
    if not candidates:
        print(f"REFUSED to lock {ticker} {field_id}: source reports in {currency} "
              f"but {fx_ref} has no {currency} rate row (rate_per_usd, as_of, source) "
              f"within 45 days of {fact_end}. Add an evidenced rate or the fact stays unlocked.")
        return None
    _gap, rate_as_of, rate, rate_source = min(candidates, key=lambda item: (item[0], item[1]))
    return rate, {"from_currency": currency, "to_currency": "USD", "rate_per_usd": rate,
                  "rate_as_of": rate_as_of, "evidence_ref": fx_ref, "rate_source": rate_source}


def build_fact_ledger(ticker: str, as_of: str) -> dict:
    path, filing = latest_filing_facts(ticker)
    facts = []
    metric_map = {
        "operating_cash_flow": ("operating_cash_flow_m", "USD millions"),
        "capital_expenditures": ("capital_expenditures_m", "USD millions"),
        "cash": ("cash_m", "USD millions"),
        "long_term_debt": ("debt_m", "USD millions"),
        "shares_outstanding": ("shares_outstanding", "shares"),
        "revenues": ("revenue_m", "USD millions"),
        "operating_income": ("operating_income_m", "USD millions"),
        "net_income": ("net_income_m", "USD millions"),
        "stockholders_equity": ("stockholders_equity_m", "USD millions"),
    }
    source_ref = str(path.relative_to(ROOT)).replace("\\", "/") if path else None
    source_as_of = (filing.get("filing_meta") or {}).get("period_end") or filing.get("as_of") or as_of
    for metric, (field_id, unit) in metric_map.items():
        row = (filing.get("metrics") or {}).get(metric) or {}
        value = row.get("current")
        if value is None or not source_ref:
            continue
        facts.append({
            "field_id": field_id, "value": value, "unit": unit,
            "source": {"ref": source_ref, "locator": f"IX fact {row.get('tag') or metric}; extracted line {row.get('current_line', 'n/a')}", "as_of": source_as_of,
                       "content_sha256": sha256(ROOT / source_ref)},
            "confidence": row.get("parser_confidence") or "medium", "locked": True,
        })
    companyfacts_path = ROOT / ticker / "research" / "evidence" / "sec_companyfacts.json"
    companyfacts = read_json(companyfacts_path)
    companyfact_specs = {
        "operating_cash_flow_m": ([
            ("us-gaap", ["NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"]),
            ("ifrs-full", ["CashFlowsFromUsedInOperatingActivities"]),
        ], True, 1 / 1_000_000, "USD millions"),
        "capital_expenditures_m": ([
            ("us-gaap", ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsForAdditionsToPropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"]),
            ("ifrs-full", ["PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"]),
        ], True, 1 / 1_000_000, "USD millions"),
        "cash_m": ([
            ("us-gaap", ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"]),
            ("ifrs-full", ["CashAndCashEquivalents"]),
        ], False, 1 / 1_000_000, "USD millions"),
        "debt_m": ([
            ("us-gaap", [
                "DebtInstrumentCarryingAmount",
                "LongTermDebt",
                "LongTermDebtAndFinanceLeaseObligations",
                "LongTermDebtAndCapitalLeaseObligations",
                "LongTermDebtNoncurrent",
            ]),
            ("ifrs-full", ["LongtermBorrowings"]),
        ], False, 1 / 1_000_000, "USD millions"),
    }
    by_id = {row["field_id"]: row for row in facts}
    companyfact_rows = {}
    fx_payload = read_json(FX_RATES)
    for field_id, (specs, annual, scale, unit) in companyfact_specs.items():
        selected = _latest_across_companyfacts(companyfacts, specs, annual)
        if not selected:
            continue
        namespace, tag, row = selected
        conversion = _usd_conversion(ticker, field_id, str(row.get("unit") or ""),
                                     str(row.get("end") or as_of), fx_payload)
        if conversion is None:
            continue
        divisor, fx = conversion
        companyfact_rows[field_id] = {
            "field_id": field_id, "value": float(row["val"]) * scale / divisor, "unit": unit, "locked": True, "confidence": "high",
            "source": {"ref": str(companyfacts_path.relative_to(ROOT)).replace("\\", "/"),
                       "locator": f"{namespace}:{tag}; accession {row.get('accn')}; form {row.get('form')}",
                       "as_of": row.get("end"), "content_sha256": sha256(companyfacts_path)},
        }
        if fx:
            companyfact_rows[field_id]["fx_conversion"] = {
                **fx, "source_value": float(row["val"]) * scale,
                "source_unit": f"{fx['from_currency']} millions",
            }
    debt_row = companyfact_rows.get("debt_m")
    if debt_row:
        debt_tag = str(debt_row["source"].get("locator") or "").split(":", 1)[-1].split(";", 1)[0]
        if debt_tag in {
            "LongTermDebtAndCapitalLeaseObligations",
            "LongTermDebtAndFinanceLeaseObligations",
            "LongTermDebtNoncurrent",
            "LongTermDebt",
        }:
            current = _latest_across_companyfacts(companyfacts, [("us-gaap", ["DebtCurrent"])], False)
            if current:
                _, cur_tag, cur_row = current
                conversion = _usd_conversion(
                    ticker, "debt_m", str(cur_row.get("unit") or ""),
                    str(cur_row.get("end") or as_of), fx_payload,
                )
                if conversion is not None:
                    divisor, _fx = conversion
                    current_m = float(cur_row["val"]) * (1 / 1_000_000) / divisor
                    debt_row["value"] = float(debt_row["value"]) + current_m
                    debt_row["source"]["locator"] = (
                        f"{debt_row['source']['locator']} + us-gaap:{cur_tag}; "
                        f"accession {cur_row.get('accn')}; form {cur_row.get('form')}"
                    )
                    debt_row["derived_from"] = ["long_term_debt_m", "debt_current_m"]
                    debt_row["formula"] = "long_term_debt_m + debt_current_m"
    selected_shares = _select_share_companyfact(companyfacts)
    if selected_shares:
        tag, row = selected_shares
        namespace = row["namespace"]
        companyfact_rows["shares_outstanding"] = {
            "field_id": "shares_outstanding", "value": float(row["val"]), "unit": "shares",
            "locked": True, "confidence": "high",
            "source": {"ref": str(companyfacts_path.relative_to(ROOT)).replace("\\", "/"),
                       "locator": f"{namespace}:{tag}; accession {row.get('accn')}; form {row.get('form')}",
                       "as_of": row.get("end"), "content_sha256": sha256(companyfacts_path)},
        }
    if companyfact_rows:
        by_id = companyfact_rows
    if "shares_outstanding" not in by_id:
        cover_shares = _cover_page_share_count(ticker)
        if cover_shares:
            by_id["shares_outstanding"] = cover_shares
    facts = list(by_id.values())
    ocf, capex = by_id.get("operating_cash_flow_m"), by_id.get("capital_expenditures_m")
    if ocf and capex:
        derived = {
            "field_id": "normalized_owner_earnings_m", "value": float(ocf["value"]) - abs(float(capex["value"])), "unit": "USD millions",
            "source": ocf["source"], "derived_from": ["operating_cash_flow_m", "capital_expenditures_m"],
            "formula": "operating_cash_flow_m - abs(capital_expenditures_m)", "confidence": "medium", "locked": True,
        }
        if ocf.get("fx_conversion"):
            derived["fx_conversion"] = {k: v for k, v in ocf["fx_conversion"].items()
                                        if k not in ("source_value", "source_unit")}
        facts.append(derived)
    facts = _merge_curated_facts(ticker, facts)
    return {"schema_version": "1.0", "ticker": ticker, "as_of": as_of, "facts": facts,
            "source_count": len({row["source"]["ref"] for row in facts}), "generated_at": now()}


CURATED_FACT_FIELDS = ("field_id", "value", "unit", "source")


def _merge_curated_facts(ticker: str, facts: list[dict]) -> list[dict]:
    """Overlay hand-curated primary-source facts onto the extracted ledger.

    XBRL companyfacts and the prose parser only reach concepts a machine can
    tag. Several approved methods require inputs that exist only as prospectus
    or reserve-report tables -- `economic_ownership_map`, `asset_quantity`,
    `unit_value`, `senior_claims`, `tax_and_realization_costs`. Without an
    overlay those method inputs can never be satisfied, so the evidence task
    queue stays `pending_collection` forever and the ticker never compiles.

    A curated row is held to the same bar as an extracted one: it must name a
    primary source ref that exists on disk, a locator, and an as-of date, and
    it is content-hashed like any other. Rows failing that stay unlocked so
    `validate_method_inputs` still rejects them.
    """
    path = ROOT / ticker / "research" / "curated_facts.json"
    payload = read_json(path)
    rows = payload.get("facts") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return facts
    by_id = {row.get("field_id"): row for row in facts}
    for row in rows:
        if not isinstance(row, dict) or any(row.get(key) is None for key in CURATED_FACT_FIELDS):
            continue
        source = dict(row.get("source") or {})
        ref = str(source.get("ref") or "")
        complete = bool(ref and source.get("locator") and source.get("as_of"))
        content_hash = sha256(ROOT / ref) if ref and (ROOT / ref).is_file() else None
        if content_hash:
            source["content_sha256"] = content_hash
        by_id[row["field_id"]] = {
            "field_id": row["field_id"], "value": row["value"], "unit": row["unit"],
            "source": source, "confidence": row.get("confidence") or "medium",
            "locked": bool(complete and content_hash),
            "origin": "curated_primary_source",
            "rationale": row.get("rationale"),
        }
    return list(by_id.values())


FIELD_REQUIREMENTS = {
    "royalty_distribution_curve": [
        "contractual_royalty_tiers", "production_by_period", "realized_pricing_or_contractual_index",
        "bonus_thresholds", "trust_expenses_and_taxes", "reserve_life", "units_outstanding", "discount_rate",
    ],
    "owner_earnings_reinvestment_dcf": ["normalized_owner_earnings_m", "shares_outstanding", "cash_m", "debt_m"],
    "net_asset_value": [
        "asset_quantity", "unit_value", "ownership_claim", "senior_claims",
        "tax_and_realization_costs", "shares_outstanding",
    ],
    "component_owner_cash_and_unit_nav": [
        "economic_ownership_map", "normalized_owner_cash", "asset_quantity", "unit_value",
        "senior_claims", "tax_and_realization_costs", "shares_outstanding",
    ],
    "midcycle_capacity_value": ["capacity", "utilization", "revenue_per_unit", "normalized_margin", "maintenance_capital_m", "tax_rate", "debt_m", "shares_outstanding"],
    "capital_structure_and_excess_return": [
        "tangible_equity_m", "normalized_roe", "cost_of_equity", "excess_return_duration",
        "stress_losses_m", "senior_claims_m", "shares_outstanding",
    ],
    "probability_weighted_catalyst_nav": [
        "event_tree", "outcome_probabilities", "outcome_payoffs", "remaining_costs",
        "outcome_timing", "discount_rates", "shares_outstanding",
    ],
    "risk_adjusted_milestone_value": [
        "asset_milestones", "base_rate_success_probabilities", "success_values",
        "milestone_timing", "remaining_costs", "cash_runway", "dilution", "shares_outstanding",
    ],
    "owner_cash_or_dividend_discount": [
        "sustainable_distribution", "sustainable_growth", "required_return",
        "maintenance_funding", "dilution_per_share", "shares_outstanding",
    ],
}

METHOD_INPUT_SCHEMAS = {
    "royalty_distribution_curve": {
        "contractual_royalty_tiers": {"type": "number", "min": 0, "unit": "ratio"},
        "production_by_period": {"type": "number", "min_exclusive": 0, "unit": "production units"},
        "realized_pricing_or_contractual_index": {"type": "number", "min": 0, "unit": "USD per production unit"},
        "bonus_thresholds": {"type": "number", "min": 0, "unit": "USD millions"},
        "trust_expenses_and_taxes": {"type": "number", "min": 0, "unit": "USD millions"},
        "reserve_life": {"type": "number", "min_exclusive": 0, "unit": "years"},
        "units_outstanding": {"type": "number", "min_exclusive": 0, "unit": "million units"},
        "discount_rate": {"type": "number", "min": 0, "max_exclusive": 1, "unit": "ratio"},
    },
    "net_asset_value": {
        "asset_quantity": {"type": "number", "min": 0, "unit": "asset units"},
        "unit_value": {"type": "number", "min": 0, "unit": "USD millions per asset unit"},
        "ownership_claim": {"type": "number", "min": 0, "max": 1, "unit": "ratio"},
        "senior_claims": {"type": "number", "min": 0, "unit": "USD millions"},
        "tax_and_realization_costs": {"type": "number", "min": 0, "unit": "USD millions"},
        "shares_outstanding": {"type": "number", "min_exclusive": 0, "unit": "shares"},
    },
    "owner_earnings_reinvestment_dcf": {
        "normalized_owner_earnings_m": {"type": "number", "min_exclusive": 0, "unit": "USD millions"},
        "shares_outstanding": {"type": "number", "min_exclusive": 0, "unit": "shares"},
        "cash_m": {"type": "number", "min": 0, "unit": "USD millions"},
        "debt_m": {"type": "number", "min": 0, "unit": "USD millions"},
    },
    "midcycle_capacity_value": {
        "capacity": {"type": "number", "min_exclusive": 0, "unit": "capacity units"},
        "utilization": {"type": "number", "min": 0, "max": 1, "unit": "ratio"},
        "revenue_per_unit": {"type": "number", "min": 0, "unit": "USD millions per capacity unit"},
        "normalized_margin": {"type": "number", "min": 0, "max": 1, "unit": "ratio"},
        "maintenance_capital_m": {"type": "number", "min": 0, "unit": "USD millions"},
        "tax_rate": {"type": "number", "min": 0, "max_exclusive": 1, "unit": "ratio"},
        "debt_m": {"type": "number", "min": 0, "unit": "USD millions"},
        "shares_outstanding": {"type": "number", "min_exclusive": 0, "unit": "shares"},
    },
    "capital_structure_and_excess_return": {
        "tangible_equity_m": {"type": "number", "min": 0, "unit": "USD millions"},
        "normalized_roe": {"type": "number", "min": 0, "unit": "ratio"},
        "cost_of_equity": {"type": "number", "min": 0, "max_exclusive": 1, "unit": "ratio"},
        "excess_return_duration": {"type": "number", "min": 0, "unit": "years"},
        "stress_losses_m": {"type": "number", "min": 0, "unit": "USD millions"},
        "senior_claims_m": {"type": "number", "min": 0, "unit": "USD millions"},
        "shares_outstanding": {"type": "number", "min_exclusive": 0, "unit": "shares"},
    },
    "probability_weighted_catalyst_nav": {
        "event_tree": {"type": "number", "min": 0, "unit": "event count"},
        "outcome_probabilities": {"type": "number", "min": 0, "max": 1, "unit": "ratio"},
        "outcome_payoffs": {"type": "number", "unit": "USD millions"},
        "remaining_costs": {"type": "number", "min": 0, "unit": "USD millions"},
        "outcome_timing": {"type": "number", "min": 0, "unit": "years"},
        "discount_rates": {"type": "number", "min": 0, "max_exclusive": 1, "unit": "ratio"},
        "shares_outstanding": {"type": "number", "min_exclusive": 0, "unit": "shares"},
    },
    "risk_adjusted_milestone_value": {
        "asset_milestones": {"type": "number", "min_exclusive": 0, "unit": "milestone count"},
        "base_rate_success_probabilities": {"type": "number", "min": 0, "max": 1, "unit": "ratio"},
        "success_values": {"type": "number", "min": 0, "unit": "USD millions"},
        "milestone_timing": {"type": "number", "min": 0, "unit": "years"},
        "remaining_costs": {"type": "number", "min": 0, "unit": "USD millions"},
        "cash_runway": {"type": "number", "unit": "USD millions"},
        "dilution": {"type": "number", "min": 0, "unit": "USD millions"},
        "shares_outstanding": {"type": "number", "min_exclusive": 0, "unit": "shares"},
    },
    "owner_cash_or_dividend_discount": {
        "sustainable_distribution": {"type": "number", "min": 0, "unit": "USD millions"},
        "sustainable_growth": {"type": "number", "min": -1, "max_exclusive": 1, "unit": "ratio"},
        "required_return": {"type": "number", "min_exclusive": 0, "max_exclusive": 1, "unit": "ratio"},
        "maintenance_funding": {"type": "number", "min": 0, "unit": "USD millions"},
        "dilution_per_share": {"type": "number", "min": 0, "unit": "USD per share"},
        "shares_outstanding": {"type": "number", "min_exclusive": 0, "unit": "shares"},
    },
    "component_owner_cash_and_unit_nav": {
        "economic_ownership_map": {"type": "object"},
        "normalized_owner_cash": {"type": "number", "min": 0, "unit": "USD millions"},
        "asset_quantity": {"type": "number", "min": 0, "unit": "asset units"},
        "unit_value": {"type": "number", "min": 0, "unit": "USD millions per asset unit"},
        "senior_claims": {"type": "number", "min": 0, "unit": "USD millions"},
        "tax_and_realization_costs": {"type": "number", "min": 0, "unit": "USD millions"},
        "shares_outstanding": {"type": "number", "min_exclusive": 0, "unit": "shares"},
    },
}


def validate_method_inputs(method_id: str, ledger: dict) -> list[str]:
    """Validate the normalized, source-locked interface consumed by a compiler."""
    facts = {row.get("field_id"): row for row in ledger.get("facts") or [] if row.get("locked") is True}
    errors = []
    for field_id, spec in METHOD_INPUT_SCHEMAS.get(method_id, {}).items():
        row = facts.get(field_id)
        if not row:
            errors.append(f"{field_id}: missing locked fact")
            continue
        value = row.get("value")
        if spec["type"] == "object":
            if not isinstance(value, (dict, list)) or not value:
                errors.append(f"{field_id}: expected a non-empty object or list")
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            errors.append(f"{field_id}: expected a finite number")
            continue
        number = float(value)
        if not math.isfinite(number):
            errors.append(f"{field_id}: expected a finite number")
        if spec.get("min") is not None and number < float(spec["min"]):
            errors.append(f"{field_id}: must be >= {spec['min']}")
        if spec.get("min_exclusive") is not None and number <= float(spec["min_exclusive"]):
            errors.append(f"{field_id}: must be > {spec['min_exclusive']}")
        if spec.get("max") is not None and number > float(spec["max"]):
            errors.append(f"{field_id}: must be <= {spec['max']}")
        if spec.get("max_exclusive") is not None and number >= float(spec["max_exclusive"]):
            errors.append(f"{field_id}: must be < {spec['max_exclusive']}")
    if method_id == "owner_cash_or_dividend_discount":
        growth = facts.get("sustainable_growth", {}).get("value")
        required = facts.get("required_return", {}).get("value")
        if isinstance(growth, (int, float)) and isinstance(required, (int, float)) and required <= growth:
            errors.append("required_return: must exceed sustainable_growth")
    return errors


def collector_for_field(field: str) -> str:
    value = field.lower()
    if any(token in value for token in ("contract", "royalty", "claim", "senior", "tax", "milestone", "event_tree")):
        return "primary_contracts_and_filings"
    if any(token in value for token in ("price", "unit_value", "capacity", "utilization", "margin", "discount_rate", "required_return")):
        return "market_and_filing_facts"
    if any(token in value for token in ("probabilit", "success_value", "failure")):
        return "primary_evidence_then_reference_class"
    return "primary_documents_then_fact_ledger"


def _model_evidence_refs(model: dict | None) -> list[str]:
    refs = set()
    for component in (((model or {}).get("component_valuation_results") or {}).get("additive_components") or []):
        for row in (component.get("calculation_proof") or {}).get("inputs") or []:
            ref = (row.get("source") or {}).get("ref")
            if ref:
                refs.add(str(ref))
    return sorted(refs)


def evidence_plan(
    ticker: str,
    identity: dict,
    ledger: dict,
    as_of: str,
    model_ready: bool = False,
    model: dict | None = None,
) -> dict:
    method = identity["primary_method"]
    available = {row["field_id"]: row for row in ledger.get("facts") or [] if row.get("locked")}
    method_input_errors = validate_method_inputs(method, ledger)
    invalid_fields = {error.split(":", 1)[0] for error in method_input_errors}
    revalidated_proof = (
        model_ready
        and ((model or {}).get("valuation_methodology") or {}).get("automation")
        == "revalidated_existing_approved_proofs"
    )
    model_refs = _model_evidence_refs(model)
    previous = read_json(ROOT / ticker / "research" / "evidence_task_queue.json")
    prior = {row.get("id"): row for row in previous.get("tasks") or []}
    tasks = []
    if identity.get("method_source") == "deterministic_fallback_pending_route_evidence":
        old = prior.get("valuation_route_classification_required", {})
        tasks.append({
            "id": "valuation_route_classification_required",
            "priority": "critical",
            "field_id": "valuation_route",
            "method_id": method,
            "question": "Supply enough source-backed classification to select a non-default Power Zone valuation route.",
            "evidence_required": "security archetype, economic ownership map, investment sleeve, and material component categories",
            "acceptance_test": "The canonical Power Zone router has a positive score and no default_needs_review status.",
            "collector": "primary_documents_then_classification",
            "status": "pending_collection",
            "attempts": int(old.get("attempts") or 0),
            "max_attempts": int(old.get("max_attempts") or 5),
            "last_attempt_at": old.get("last_attempt_at"),
            "next_attempt_at": old.get("next_attempt_at"),
            "last_error": old.get("last_error"),
            "evidence_refs": old.get("evidence_refs") or [],
        })
    for field in FIELD_REQUIREMENTS.get(method, []):
        task_id = f"method_input:{method}:{field}"
        old = prior.get(task_id, {})
        fact = available.get(field)
        usable = revalidated_proof or (bool(fact) and field not in invalid_fields)
        input_schema = METHOD_INPUT_SCHEMAS.get(method, {}).get(field) or {}
        tasks.append({
            "id": task_id, "priority": "critical", "field_id": field, "method_id": method,
            "question": f"Supply a primary-source value for {field.replace('_', ' ')}.",
            "evidence_required": field,
            "input_schema": input_schema,
            "acceptance_test": "A locked fact-ledger row has a primary source ref, locator, as-of date, and a value that passes the method input schema.",
            "collector": collector_for_field(field), "status": "evidence_ready" if usable else "pending_collection",
            "attempts": int(old.get("attempts") or 0), "last_attempt_at": old.get("last_attempt_at"),
            "max_attempts": int(old.get("max_attempts") or 5),
            "next_attempt_at": old.get("next_attempt_at"),
            "last_error": None if usable else next(
                (error for error in method_input_errors if error.startswith(f"{field}:")),
                old.get("last_error"),
            ),
            "satisfied_by": "issuer_specific_approved_proof" if revalidated_proof else "normalized_fact_ledger",
            "evidence_refs": model_refs if revalidated_proof else ([fact["source"]["ref"]] if usable else []),
        })
    field_tasks = [row for row in tasks if str(row.get("id") or "").startswith("method_input:")]
    all_fields_ready = bool(field_tasks) and all(row["status"] == "evidence_ready" for row in field_tasks)
    route_ready = not any(row["id"] == "valuation_route_classification_required" for row in tasks)
    all_inputs_ready = (all_fields_ready or revalidated_proof) and route_ready
    model_task = prior.get("complete_component_model_required") or {}
    tasks.append({
        "id": "complete_component_model_required", "priority": "critical", "field_id": "component_model", "method_id": method,
        "question": "Build a complete primary-sourced component valuation.",
        "evidence_required": "; ".join(FIELD_REQUIREMENTS.get(method, [])),
        "acceptance_test": "Every material economic claim is valued exactly once with a valid deterministic proof.",
        "collector": f"compile_{method}", "status": "evidence_ready" if all_inputs_ready and model_ready else "pending_collection",
        "attempts": int(model_task.get("attempts") or 0),
        "max_attempts": int(model_task.get("max_attempts") or 5),
        "last_attempt_at": model_task.get("last_attempt_at"),
        "next_attempt_at": model_task.get("next_attempt_at"),
        "last_error": None if all_inputs_ready and model_ready else (
            "; ".join(method_input_errors) or model_task.get("last_error")
            or "The selected method compiler has not produced a valid proof."
        ),
        "evidence_refs": (
            model_refs
            if all_inputs_ready and model_ready and revalidated_proof
            else sorted({row["source"]["ref"] for row in available.values()})
            if all_inputs_ready and model_ready
            else []
        ),
    })
    return {"schema_version": "2.0", "ticker": ticker, "updated_at": now(), "method_id": method,
            "ready_count": sum(t["status"] == "evidence_ready" for t in tasks), "task_count": len(tasks), "tasks": tasks}


def _proof_fact(field: dict, node_id: str, label: str, unit: str, scale: float = 1.0) -> dict:
    source = {k: v for k, v in field["source"].items() if k in {"ref", "locator", "as_of"}}
    node = {"id": node_id, "label": label, "kind": "fact", "value": float(field["value"]) * scale,
            "unit": unit, "source": source, "locked": True}
    fx = field.get("fx_conversion")
    if isinstance(fx, dict) and fx:
        # Carry the ledger's conversion evidence into the proof. Without it a
        # converted value and a raw foreign-currency value both read as plain
        # "USD millions" sourced to a EUR/DKK concept, so a stale proof input is
        # indistinguishable from a correct one by inspection (ASML, 2026-08-09).
        converted = dict(fx)
        if scale != 1.0 and isinstance(converted.get("source_value"), (int, float)):
            converted["source_value"] = float(converted["source_value"]) * scale
        node["fx_conversion"] = converted
    return node


def _shares_scale(facts: dict) -> float:
    shares = float(facts["shares_outstanding"]["value"])
    return 1.0 if shares < 100_000 else 1 / 1_000_000


def _judgment(node_id: str, label: str, values: tuple[float, float, float], unit: str,
              rationale: str, minimum: float, maximum: float) -> dict:
    return {
        "id": node_id, "label": label, "kind": "judgment",
        "values": dict(zip(("low", "base", "high"), values)), "unit": unit,
        "rationale": rationale, "allowed_range": {"min": minimum, "max": maximum},
    }


def _compiled_model(ticker: str, as_of: str, identity: dict, method_id: str,
                    components: list[dict], facts: dict, methodology: dict | None = None) -> dict:
    return {
        "ticker": ticker,
        "as_of": as_of,
        "schema_version": "3.0",
        "method": "proof_first_automated",
        "classification_inputs": {
            "archetype": identity.get("archetype"),
            "valuation_profile": identity.get("valuation_profile"),
            "method_source": identity.get("method_source"),
        },
        "inputs": {
            "shares_outstanding": facts.get("shares_outstanding", {}).get("value"),
        },
        "valuation_methodology": {
            "primary_method": method_id,
            "method_version": "1.0",
            "automation": "source_locked_method_dispatch",
            **(methodology or {}),
        },
        "component_valuation_results": {
            "status": "compiled",
            "all_material_components_identified": True,
            "additive_components": components,
            "embedded_components": [],
        },
        "economic_value_analysis": {"status": "compiled", "validation_errors": []},
    }


def merge_compiled_model(prior: dict, model: dict) -> dict:
    """Overlay the compiled model onto the prior valuation instead of replacing it.

    `_compiled_model` emits nine keys. A hand-built valuation.json routinely
    carries far more -- the authored `component_valuation` schedule, scenarios,
    human_review, catalyst_paths, lens_consensus, change_log. Writing the model
    straight over the file silently discarded all of it, and because the model's
    `component_valuation_results` has no totals, no market price and no upside,
    the dashboard's component panel went null even though the contract was
    complete.

    Keys the compiler owns still win; everything else survives. When the model
    came from revalidating this issuer's own approved proofs, the authored
    schedule is by definition still in agreement with it, so the richer
    `compute_component_valuation` results are regenerated to restore the
    summary fields the presentation layer reads.
    """
    if not isinstance(prior, dict) or not prior:
        return model
    merged = copy.deepcopy(prior)
    merged.update(model)
    automation = (model.get("valuation_methodology") or {}).get("automation")
    schedule = merged.get("component_valuation")
    if automation != "revalidated_existing_approved_proofs" or not isinstance(schedule, dict):
        return merged
    if not schedule.get("components"):
        return merged
    try:
        results = compute_component_valuation(merged)
    except (ValueError, TypeError, KeyError):
        return merged
    if not results:
        return merged
    prior_results = prior.get("component_valuation_results") or {}
    for key in ("partition_note", "coverage_statement", "source"):
        if prior_results.get(key) is not None:
            results.setdefault(key, prior_results[key])
    results["as_of"] = model.get("as_of") or results.get("as_of")
    merged["component_valuation_results"] = results
    # `_compiled_model` writes a two-key economic_value_analysis stub. Where the
    # issuer has an authored `economic_value` specification, rebuild the real
    # analysis from it rather than letting the stub stand -- otherwise the
    # economic_claim gate reports blocked forever on a file that has the answer.
    if isinstance(merged.get("economic_value"), dict) and merged["economic_value"]:
        try:
            build_economic_value_analysis(merged)
        except (ValueError, TypeError, KeyError):
            pass
    return merged


def _component(component_id: str, label: str, category: str, method_id: str, proof: dict,
               evidence: str) -> dict:
    return {
        "id": component_id,
        "label": label,
        "category": category,
        "overlap_key": component_id,
        "treatment": "additive",
        "method": method_id,
        "valuation_status": "bounded_estimate",
        "calculation_proof": proof,
        "evidence_tier": "primary_derived",
        "evidence": evidence,
        "falsifier": "A locked method input changes or fails its source acceptance test.",
    }


def compile_owner_earnings(ticker: str, as_of: str, identity: dict, ledger: dict) -> dict | None:
    if identity.get("primary_method") != "owner_earnings_reinvestment_dcf":
        return None
    if validate_method_inputs("owner_earnings_reinvestment_dcf", ledger):
        return None
    facts = {row["field_id"]: row for row in ledger.get("facts") or [] if row.get("locked") is True}
    shares = float(facts["shares_outstanding"]["value"])
    shares_m_scale = 1.0 if shares < 100_000 else 1 / 1_000_000
    inputs = [
        _proof_fact(facts["normalized_owner_earnings_m"], "owner_earnings", "Normalized owner earnings", "USD millions"),
        _proof_fact(facts["cash_m"], "cash", "Cash", "USD millions"),
        _proof_fact(facts["debt_m"], "debt", "Debt", "USD millions"),
        _proof_fact(facts["shares_outstanding"], "shares_m", "Diluted shares", "million shares", shares_m_scale),
    ]
    assumptions = [
        {"id": "reinvestment", "label": "Reinvestment rate", "kind": "judgment", "values": {"low": .20, "base": .35, "high": .50}, "unit": "ratio", "rationale": "Versioned initial bounds; refresh from the issuer reinvestment ledger.", "allowed_range": {"min": 0, "max": .75}},
        {"id": "incremental_roic", "label": "Incremental after-tax ROIC", "kind": "judgment", "values": {"low": .12, "base": .18, "high": .25}, "unit": "ratio", "rationale": "Conservative bounded starting cases pending a longer primary-source capital bridge.", "allowed_range": {"min": 0, "max": .50}},
        {"id": "discount_rate", "label": "Discount rate", "kind": "judgment", "values": {"low": .12, "base": .10, "high": .09}, "unit": "ratio", "rationale": "Approved risk bounds for the automated first pass.", "allowed_range": {"min": .07, "max": .15}},
        {"id": "terminal_multiple", "label": "Terminal owner-earnings multiple", "kind": "judgment", "values": {"low": 12, "base": 18, "high": 24}, "unit": "multiple", "rationale": "Bounded terminal economics; high case remains below a perpetual high-growth assumption.", "allowed_range": {"min": 8, "max": 30}},
    ]
    calculations = [
        {"id": "growth", "label": "Growth from reinvestment", "op": "multiply", "args": ["reinvestment", "incremental_roic"], "unit": "ratio"},
        {"id": "growth_factor", "op": "add", "args": [1, "growth"], "unit": "ratio"},
        {"id": "distribution_rate", "op": "subtract", "args": [1, "reinvestment"], "unit": "ratio"},
    ]
    cash_nodes = []
    prior = "owner_earnings"
    for year in range(1, 8):
        earn = f"owner_earnings_y{year}"
        cash = f"owner_cash_y{year}"
        calculations.extend([
            {"id": earn, "op": "multiply", "args": [prior, "growth_factor"], "unit": "USD millions"},
            # Growth here is bought with reinvestment, so only the unretained
            # share is distributable. Discounting the full owner-earnings figure
            # is the method card's "growth without capital cost" failure mode.
            {"id": cash, "op": "multiply", "args": [earn, "distribution_rate"], "unit": "USD millions"},
        ])
        cash_nodes.extend([cash, year])
        prior = earn
    calculations.extend([
        {"id": "cash_pv", "op": "present_value", "args": [*cash_nodes, "discount_rate"], "unit": "USD millions"},
        {"id": "terminal_value", "op": "multiply", "args": [prior, "terminal_multiple"], "unit": "USD millions"},
        {"id": "terminal_pv", "op": "discount", "args": ["terminal_value", "discount_rate", 7], "unit": "USD millions"},
        {"id": "enterprise_value", "op": "add", "args": ["cash_pv", "terminal_pv"], "unit": "USD millions"},
        {"id": "plus_cash", "op": "add", "args": ["enterprise_value", "cash"], "unit": "USD millions"},
        {"id": "equity_value", "op": "subtract", "args": ["plus_cash", "debt"], "unit": "USD millions"},
        {"id": "value_per_share", "op": "divide", "args": ["equity_value", "shares_m"], "unit": "USD per share"},
    ])
    proof = {"schema_version": "1.0", "method_id": "owner_earnings_reinvestment_dcf", "method_version": "1.0",
             "output_unit": "USD per share", "inputs": inputs, "assumptions": assumptions,
             "calculations": calculations, "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"}}
    return {
        "ticker": ticker, "as_of": as_of, "schema_version": "3.0", "method": "proof_first_automated",
        "classification_inputs": {"archetype": identity["archetype"]},
        "inputs": {"shares_outstanding": shares, "cash_m": facts["cash_m"]["value"], "total_debt_m": facts["debt_m"]["value"]},
        "valuation_methodology": {"horizon_years": 7, "automation": "source_locked_first_pass"},
        "component_valuation_results": {"status": "compiled", "all_material_components_identified": True,
            "additive_components": [{"id": "operating_business_and_net_assets", "label": "Operating business and net financial assets",
                "category": "operating_business", "overlap_key": "entire_security", "treatment": "additive", "method": "owner_earnings_reinvestment_dcf",
                "valuation_status": "bounded_estimate", "calculation_proof": proof, "evidence_tier": "primary_derived",
                "evidence": "Source-locked filing facts plus explicitly bounded versioned judgments.",
                "falsifier": "Owner earnings, incremental returns, or reinvestment runway fall below the low-case bridge."}],
            "embedded_components": []},
        "economic_value_analysis": {"status": "compiled", "validation_errors": []},
    }


def compile_royalty_distribution(ticker: str, as_of: str, identity: dict, ledger: dict) -> dict | None:
    method_id = "royalty_distribution_curve"
    if identity.get("primary_method") != method_id or validate_method_inputs(method_id, ledger):
        return None
    facts = {row["field_id"]: row for row in ledger["facts"] if row.get("locked") is True}
    inputs = [
        _proof_fact(facts["production_by_period"], "production", "Evidenced production", "production units"),
        _proof_fact(facts["realized_pricing_or_contractual_index"], "price", "Realized or indexed price", "USD millions per production unit"),
        _proof_fact(facts["contractual_royalty_tiers"], "royalty_rate", "Effective contractual royalty rate", "ratio"),
        _proof_fact(facts["bonus_thresholds"], "bonus", "Contractual bonus distributions", "USD millions"),
        _proof_fact(facts["trust_expenses_and_taxes"], "costs", "Trust expenses and taxes", "USD millions"),
        _proof_fact(facts["reserve_life"], "reserve_life", "Remaining reserve life", "years"),
        _proof_fact(facts["units_outstanding"], "units", "Units outstanding", "million units"),
        _proof_fact(facts["discount_rate"], "discount_rate", "Required return", "ratio"),
    ]
    calculations = [
        {"id": "gross_value", "op": "multiply", "args": ["production", "price"], "unit": "USD millions"},
        {"id": "ordinary_royalty", "op": "multiply", "args": ["gross_value", "royalty_rate"], "unit": "USD millions"},
        {"id": "gross_distribution", "op": "add", "args": ["ordinary_royalty", "bonus"], "unit": "USD millions"},
        {"id": "net_distribution", "op": "subtract", "args": ["gross_distribution", "costs"], "unit": "USD millions"},
        {"id": "present_distribution", "op": "discount", "args": ["net_distribution", "discount_rate", "reserve_life"], "unit": "USD millions"},
        {"id": "value_per_unit", "op": "divide", "args": ["present_distribution", "units"], "unit": "USD per unit"},
    ]
    proof = {
        "schema_version": "1.0", "method_id": method_id, "method_version": "1.0",
        "output_unit": "USD per unit", "inputs": inputs, "assumptions": [],
        "calculations": calculations,
        "outputs": {"low": "value_per_unit", "base": "value_per_unit", "high": "value_per_unit"},
    }
    return _compiled_model(
        ticker, as_of, identity, method_id,
        [_component("finite_royalty_claim", "Finite royalty claim", "royalty_claim", method_id, proof,
                    "Contract-normalized royalty economics, production, pricing, costs, reserve life, and units.")],
        facts,
    )


def _nav_proof(facts: dict, *, method_id: str = "net_asset_value",
               quantity_field: str = "asset_quantity", value_field: str = "unit_value",
               ownership_field: str | None = "ownership_claim") -> dict:
    inputs = [
        _proof_fact(facts[quantity_field], "asset_quantity", "Asset quantity", "asset units"),
        _proof_fact(facts[value_field], "unit_value", "Unit value", "USD millions per asset unit"),
        _proof_fact(facts["senior_claims"], "senior_claims", "Senior claims", "USD millions"),
        _proof_fact(facts["tax_and_realization_costs"], "realization_costs", "Tax and realization costs", "USD millions"),
        _proof_fact(facts["shares_outstanding"], "shares_m", "Diluted shares", "million shares", _shares_scale(facts)),
    ]
    calculations = [
        {"id": "gross_assets", "op": "multiply", "args": ["asset_quantity", "unit_value"], "unit": "USD millions"},
    ]
    gross_node = "gross_assets"
    if ownership_field:
        inputs.append(_proof_fact(facts[ownership_field], "ownership", "Economic ownership", "ratio"))
        calculations.append({"id": "owned_assets", "op": "multiply", "args": ["gross_assets", "ownership"], "unit": "USD millions"})
        gross_node = "owned_assets"
    calculations.extend([
        {"id": "after_claims", "op": "subtract", "args": [gross_node, "senior_claims"], "unit": "USD millions"},
        {"id": "equity_value", "op": "subtract", "args": ["after_claims", "realization_costs"], "unit": "USD millions"},
        {"id": "value_per_share", "op": "divide", "args": ["equity_value", "shares_m"], "unit": "USD per share"},
    ])
    return {
        "schema_version": "1.0", "method_id": method_id, "method_version": "1.0",
        "output_unit": "USD per share", "inputs": inputs, "assumptions": [],
        "calculations": calculations,
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def compile_net_asset_value(ticker: str, as_of: str, identity: dict, ledger: dict) -> dict | None:
    method_id = "net_asset_value"
    if identity.get("primary_method") != method_id or validate_method_inputs(method_id, ledger):
        return None
    facts = {row["field_id"]: row for row in ledger["facts"] if row.get("locked") is True}
    proof = _nav_proof(facts)
    return _compiled_model(
        ticker, as_of, identity, method_id,
        [_component("reconciled_net_assets", "Reconciled net assets", "net_assets", method_id, proof,
                    "Locked quantities and unit values less senior claims and realization friction.")],
        facts,
    )


def compile_midcycle_capacity(ticker: str, as_of: str, identity: dict, ledger: dict) -> dict | None:
    method_id = "midcycle_capacity_value"
    if identity.get("primary_method") != method_id or validate_method_inputs(method_id, ledger):
        return None
    facts = {row["field_id"]: row for row in ledger["facts"] if row.get("locked") is True}
    inputs = [
        _proof_fact(facts["capacity"], "capacity", "Evidenced capacity", "capacity units"),
        _proof_fact(facts["utilization"], "utilization", "Normalized utilization", "ratio"),
        _proof_fact(facts["revenue_per_unit"], "revenue_per_unit", "Revenue per utilized unit", "USD millions per capacity unit"),
        _proof_fact(facts["normalized_margin"], "margin", "Normalized cash margin", "ratio"),
        _proof_fact(facts["maintenance_capital_m"], "maintenance_capital", "Maintenance capital", "USD millions"),
        _proof_fact(facts["tax_rate"], "tax_rate", "Cash tax rate", "ratio"),
        _proof_fact(facts["debt_m"], "debt", "Net debt and senior claims", "USD millions"),
        _proof_fact(facts["shares_outstanding"], "shares_m", "Diluted shares", "million shares", _shares_scale(facts)),
    ]
    assumptions = [
        _judgment("midcycle_multiple", "Midcycle owner-cash multiple", (5.0, 7.0, 9.0), "multiple",
                  "Versioned capital-cycle bounds; not a peak-margin multiple.", 3.0, 12.0),
    ]
    calculations = [
        {"id": "utilized_capacity", "op": "multiply", "args": ["capacity", "utilization"], "unit": "capacity units"},
        {"id": "normalized_revenue", "op": "multiply", "args": ["utilized_capacity", "revenue_per_unit"], "unit": "USD millions"},
        {"id": "gross_cash", "op": "multiply", "args": ["normalized_revenue", "margin"], "unit": "USD millions"},
        {"id": "pre_tax_cash", "op": "subtract", "args": ["gross_cash", "maintenance_capital"], "unit": "USD millions"},
        {"id": "one_minus_tax", "op": "subtract", "args": [1, "tax_rate"], "unit": "ratio"},
        {"id": "after_tax_cash", "op": "multiply", "args": ["pre_tax_cash", "one_minus_tax"], "unit": "USD millions"},
        {"id": "enterprise_value", "op": "multiply", "args": ["after_tax_cash", "midcycle_multiple"], "unit": "USD millions"},
        {"id": "equity_value", "op": "subtract", "args": ["enterprise_value", "debt"], "unit": "USD millions"},
        {"id": "value_per_share", "op": "divide", "args": ["equity_value", "shares_m"], "unit": "USD per share"},
    ]
    proof = {
        "schema_version": "1.0", "method_id": method_id, "method_version": "1.0",
        "output_unit": "USD per share", "inputs": inputs, "assumptions": assumptions,
        "calculations": calculations,
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }
    return _compiled_model(
        ticker, as_of, identity, method_id,
        [_component("normalized_capacity", "Normalized capacity economics", "operating_business", method_id, proof,
                    "Source-locked capacity, utilization, unit revenue, margin, maintenance capital, tax, and leverage.")],
        facts,
    )


def compile_capital_structure(ticker: str, as_of: str, identity: dict, ledger: dict) -> dict | None:
    method_id = "capital_structure_and_excess_return"
    if identity.get("primary_method") != method_id or validate_method_inputs(method_id, ledger):
        return None
    facts = {row["field_id"]: row for row in ledger["facts"] if row.get("locked") is True}
    inputs = [
        _proof_fact(facts["tangible_equity_m"], "tangible_equity", "Tangible equity", "USD millions"),
        _proof_fact(facts["normalized_roe"], "normalized_roe", "Normalized return on equity", "ratio"),
        _proof_fact(facts["cost_of_equity"], "cost_of_equity", "Cost of equity", "ratio"),
        _proof_fact(facts["excess_return_duration"], "duration", "Excess-return duration", "years"),
        _proof_fact(facts["stress_losses_m"], "stress_losses", "Stress losses", "USD millions"),
        _proof_fact(facts["senior_claims_m"], "senior_claims", "Senior claims", "USD millions"),
        _proof_fact(facts["shares_outstanding"], "shares_m", "Diluted shares", "million shares", _shares_scale(facts)),
    ]
    calculations = [
        {"id": "roe_spread_raw", "op": "subtract", "args": ["normalized_roe", "cost_of_equity"], "unit": "ratio"},
        {"id": "roe_spread", "op": "maximum", "args": ["roe_spread_raw", 0], "unit": "ratio"},
        {"id": "annual_excess_return", "op": "multiply", "args": ["tangible_equity", "roe_spread"], "unit": "USD millions"},
        {"id": "franchise_value", "op": "multiply", "args": ["annual_excess_return", "duration"], "unit": "USD millions"},
        {"id": "gross_value", "op": "add", "args": ["tangible_equity", "franchise_value"], "unit": "USD millions"},
        {"id": "after_losses", "op": "subtract", "args": ["gross_value", "stress_losses"], "unit": "USD millions"},
        {"id": "equity_value", "op": "subtract", "args": ["after_losses", "senior_claims"], "unit": "USD millions"},
        {"id": "value_per_share", "op": "divide", "args": ["equity_value", "shares_m"], "unit": "USD per share"},
    ]
    proof = {
        "schema_version": "1.0", "method_id": method_id, "method_version": "1.0",
        "output_unit": "USD per share", "inputs": inputs, "assumptions": [],
        "calculations": calculations,
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }
    return _compiled_model(
        ticker, as_of, identity, method_id,
        [_component("tangible_capital_and_franchise", "Tangible capital & finite excess returns", "financial_franchise",
                    method_id, proof, "Locked tangible capital, normalized return, duration, stress loss, and claim waterfall.")],
        facts,
    )


def compile_catalyst_nav(ticker: str, as_of: str, identity: dict, ledger: dict) -> dict | None:
    method_id = "probability_weighted_catalyst_nav"
    if identity.get("primary_method") != method_id or validate_method_inputs(method_id, ledger):
        return None
    facts = {row["field_id"]: row for row in ledger["facts"] if row.get("locked") is True}
    inputs = [
        _proof_fact(facts["event_tree"], "event_count", "Exhaustive mutually exclusive outcomes", "event count"),
        _proof_fact(facts["outcome_probabilities"], "probability", "Aggregate evidenced probability", "ratio"),
        _proof_fact(facts["outcome_payoffs"], "payoff", "Outcome payoff", "USD millions"),
        _proof_fact(facts["remaining_costs"], "remaining_costs", "Remaining realization costs", "USD millions"),
        _proof_fact(facts["outcome_timing"], "timing", "Outcome timing", "years"),
        _proof_fact(facts["discount_rates"], "discount_rate", "Outcome discount rate", "ratio"),
        _proof_fact(facts["shares_outstanding"], "shares_m", "Diluted shares", "million shares", _shares_scale(facts)),
    ]
    calculations = [
        {"id": "net_payoff", "op": "subtract", "args": ["payoff", "remaining_costs"], "unit": "USD millions"},
        {"id": "weighted_payoff", "op": "multiply", "args": ["net_payoff", "probability"], "unit": "USD millions"},
        {"id": "present_value", "op": "discount", "args": ["weighted_payoff", "discount_rate", "timing"], "unit": "USD millions"},
        {"id": "value_per_share", "op": "divide", "args": ["present_value", "shares_m"], "unit": "USD per share"},
    ]
    proof = {
        "schema_version": "1.0", "method_id": method_id, "method_version": "1.0",
        "output_unit": "USD per share", "inputs": inputs, "assumptions": [],
        "calculations": calculations,
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }
    return _compiled_model(
        ticker, as_of, identity, method_id,
        [_component("catalyst_event_tree", "Catalyst event tree", "catalyst", method_id, proof,
                    "Normalized exhaustive event tree with sourced probability, payoff, cost, timing, and discount rate.")],
        facts,
    )


def compile_milestone_value(ticker: str, as_of: str, identity: dict, ledger: dict) -> dict | None:
    method_id = "risk_adjusted_milestone_value"
    if identity.get("primary_method") != method_id or validate_method_inputs(method_id, ledger):
        return None
    facts = {row["field_id"]: row for row in ledger["facts"] if row.get("locked") is True}
    inputs = [
        _proof_fact(facts["asset_milestones"], "milestone_count", "Material asset milestones", "milestone count"),
        _proof_fact(facts["base_rate_success_probabilities"], "success_probability", "Reference-class success probability", "ratio"),
        _proof_fact(facts["success_values"], "success_value", "Success-state value", "USD millions"),
        _proof_fact(facts["milestone_timing"], "timing", "Milestone timing", "years"),
        _proof_fact(facts["remaining_costs"], "remaining_costs", "Remaining costs", "USD millions"),
        _proof_fact(facts["cash_runway"], "cash_runway", "Net cash runway", "USD millions"),
        _proof_fact(facts["dilution"], "dilution", "Expected dilution burden", "USD millions"),
        _proof_fact(facts["shares_outstanding"], "shares_m", "Diluted shares", "million shares", _shares_scale(facts)),
    ]
    assumptions = [
        _judgment("discount_rate", "Milestone discount rate", (.14, .11, .09), "ratio",
                  "Versioned reference-class risk bounds used after the probability haircut.", .07, .20),
    ]
    calculations = [
        {"id": "discounted_success_value", "op": "discount", "args": ["success_value", "discount_rate", "timing"], "unit": "USD millions"},
        {"id": "risk_adjusted_asset", "op": "multiply", "args": ["discounted_success_value", "success_probability"], "unit": "USD millions"},
        {"id": "after_costs", "op": "subtract", "args": ["risk_adjusted_asset", "remaining_costs"], "unit": "USD millions"},
        {"id": "plus_cash", "op": "add", "args": ["after_costs", "cash_runway"], "unit": "USD millions"},
        {"id": "equity_value", "op": "subtract", "args": ["plus_cash", "dilution"], "unit": "USD millions"},
        {"id": "value_per_share", "op": "divide", "args": ["equity_value", "shares_m"], "unit": "USD per share"},
    ]
    proof = {
        "schema_version": "1.0", "method_id": method_id, "method_version": "1.0",
        "output_unit": "USD per share", "inputs": inputs, "assumptions": assumptions,
        "calculations": calculations,
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }
    return _compiled_model(
        ticker, as_of, identity, method_id,
        [_component("risk_adjusted_milestones", "Risk-adjusted milestones", "binary_option", method_id, proof,
                    "Reference-class success rates, outcome values, timing, cost, cash runway, and dilution.")],
        facts,
    )


def _owner_cash_proof(facts: dict, *, cash_field: str = "sustainable_distribution",
                      use_source_rates: bool = True) -> dict:
    inputs = [
        _proof_fact(facts[cash_field], "distribution", "Sustainable owner cash", "USD millions"),
        _proof_fact(facts["shares_outstanding"], "shares_m", "Diluted shares", "million shares", _shares_scale(facts)),
    ]
    assumptions = []
    if use_source_rates:
        inputs.extend([
            _proof_fact(facts["sustainable_growth"], "growth", "Sustainable growth", "ratio"),
            _proof_fact(facts["required_return"], "required_return", "Required return", "ratio"),
            _proof_fact(facts["maintenance_funding"], "maintenance_funding", "Required maintenance funding", "USD millions"),
            _proof_fact(facts["dilution_per_share"], "dilution_per_share", "Expected dilution per share", "USD per share"),
        ])
    else:
        assumptions.extend([
            _judgment("growth", "Sustainable owner-cash growth", (0.0, .02, .035), "ratio",
                      "Versioned finite-growth bounds for a source-locked normalized owner-cash base.", -.05, .05),
            _judgment("required_return", "Required owner-cash return", (.13, .11, .095), "ratio",
                      "Versioned predictable-cash-flow risk bounds.", .08, .16),
        ])
        inputs.extend([
            {"id": "maintenance_funding", "label": "Maintenance funding", "kind": "estimate",
             "value": 0.0, "unit": "USD millions"},
            {"id": "dilution_per_share", "label": "Dilution per share", "kind": "estimate",
             "value": 0.0, "unit": "USD per share"},
        ])
    calculations = [
        {"id": "one_plus_growth", "op": "add", "args": [1, "growth"], "unit": "ratio"},
        {"id": "next_distribution", "op": "multiply", "args": ["distribution", "one_plus_growth"], "unit": "USD millions"},
        {"id": "spread", "op": "subtract", "args": ["required_return", "growth"], "unit": "ratio"},
        {"id": "gross_value", "op": "divide", "args": ["next_distribution", "spread"], "unit": "USD millions"},
        {"id": "after_funding", "op": "subtract", "args": ["gross_value", "maintenance_funding"], "unit": "USD millions"},
        {"id": "before_dilution_per_share", "op": "divide", "args": ["after_funding", "shares_m"], "unit": "USD per share"},
        {"id": "value_per_share", "op": "subtract", "args": ["before_dilution_per_share", "dilution_per_share"], "unit": "USD per share"},
    ]
    return {
        "schema_version": "1.0", "method_id": "owner_cash_or_dividend_discount", "method_version": "1.0",
        "output_unit": "USD per share", "inputs": inputs, "assumptions": assumptions,
        "calculations": calculations,
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def compile_owner_cash(ticker: str, as_of: str, identity: dict, ledger: dict) -> dict | None:
    method_id = "owner_cash_or_dividend_discount"
    if identity.get("primary_method") != method_id or validate_method_inputs(method_id, ledger):
        return None
    facts = {row["field_id"]: row for row in ledger["facts"] if row.get("locked") is True}
    proof = _owner_cash_proof(facts)
    return _compiled_model(
        ticker, as_of, identity, method_id,
        [_component("predictable_owner_cash", "Predictable owner cash", "operating_business", method_id, proof,
                    "Sourced sustainable distribution, growth, required return, maintenance funding, and dilution.")],
        facts,
    )


def compile_component_owner_cash_and_nav(ticker: str, as_of: str, identity: dict,
                                         ledger: dict) -> dict | None:
    route_method = "component_owner_cash_and_unit_nav"
    if identity.get("primary_method") != route_method or validate_method_inputs(route_method, ledger):
        return None
    facts = {row["field_id"]: row for row in ledger["facts"] if row.get("locked") is True}
    owner_cash = _owner_cash_proof(facts, cash_field="normalized_owner_cash", use_source_rates=False)
    nav = _nav_proof(facts, ownership_field=None)
    components = [
        _component("owner_cash_component", "Operating owner cash", "operating_business",
                   "owner_cash_or_dividend_discount", owner_cash,
                   "Source-locked normalized owner cash with versioned predictable-cash-flow bounds."),
        _component("unit_nav_component", "Owned unit NAV", "net_assets", "net_asset_value", nav,
                   "Source-locked asset quantity and unit value less claims and realization costs."),
    ]
    model = _compiled_model(
        ticker, as_of, identity, route_method, components, facts,
        {"component_methods": ["owner_cash_or_dividend_discount", "net_asset_value"]},
    )
    model["classification_inputs"]["economic_ownership_map"] = facts["economic_ownership_map"]["value"]
    return model


METHOD_COMPILERS = {
    "royalty_distribution_curve": compile_royalty_distribution,
    "net_asset_value": compile_net_asset_value,
    "owner_earnings_reinvestment_dcf": compile_owner_earnings,
    "midcycle_capacity_value": compile_midcycle_capacity,
    "capital_structure_and_excess_return": compile_capital_structure,
    "probability_weighted_catalyst_nav": compile_catalyst_nav,
    "risk_adjusted_milestone_value": compile_milestone_value,
    "owner_cash_or_dividend_discount": compile_owner_cash,
    "component_owner_cash_and_unit_nav": compile_component_owner_cash_and_nav,
}


def compile_existing_approved_proofs(ticker: str, as_of: str, identity: dict) -> dict | None:
    """Reuse a complete proof-first component schedule after deterministic validation.

    Existing issuer-specific proof graphs often carry richer component economics
    than the normalized first-pass compiler. Revalidating them avoids discarding
    primary evidence while still refusing legacy ranges or non-approved methods.
    """
    prior = read_json(ROOT / ticker / "research" / "valuation.json")
    if prior.get("method") == "proof_first_automated":
        # Recompile automated graphs from the current fact ledger. Reusing them
        # would pin corrected SEC facts behind an otherwise valid old proof.
        return None
    component_results = prior.get("component_valuation_results") or {}
    components = component_results.get("additive_components") or []
    if not components or component_results.get("all_material_components_identified") is not True:
        return None
    approved = {
        row.get("method_id")
        for row in (read_json(METHODS).get("method_cards") or [])
        if row.get("status") == "approved"
    }
    compiled = []
    proof_methods = set()
    overlap_keys = set()
    for source_component in components:
        proof = source_component.get("calculation_proof")
        if not isinstance(proof, dict):
            return None
        evaluated = evaluate_calculation_proof(proof)
        method_id = evaluated.get("method_id")
        if evaluated.get("status") != "valid" or method_id not in approved:
            return None
        overlap_key = str(source_component.get("overlap_key") or source_component.get("id") or "")
        if not overlap_key or overlap_key in overlap_keys:
            return None
        overlap_keys.add(overlap_key)
        proof_methods.add(method_id)
        row = copy.deepcopy(source_component)
        row["method"] = method_id
        row["valuation_status"] = row.get("valuation_status") or "bounded_estimate"
        compiled.append(row)
    routed_method = str(identity.get("primary_method") or "")
    owner_earnings_family = {
        "owner_earnings_reinvestment_dcf", "reinvestment_return_dcf",
        "reinvestment_return_driver_dcf", "normalized_owner_earnings", "normalized_earnings",
    }
    owner_cash_family = {
        "owner_cash_or_dividend_discount", "owner_cash_dcf",
        "normalized_owner_cash_capitalization", "royalty_distribution_curve",
        "infrastructure_owner_cash_dcf", "capital_free_revenue_driver_dcf",
        "capital_free_produced_water_driver_dcf",
    }
    nav_family = {
        "net_asset_value", "unit_nav", "liquidation_nav", "portfolio_discounted_unit_nav",
        "segmented_comparable_land_nav_with_realization_discount", "risked_comparable_option_nav",
        "milestone_nav",
    }
    route_supported = routed_method in proof_methods
    if routed_method == "owner_earnings_reinvestment_dcf":
        route_supported = bool(proof_methods.intersection(owner_earnings_family))
    elif routed_method == "owner_cash_or_dividend_discount":
        route_supported = bool(proof_methods.intersection(owner_cash_family))
    elif routed_method == "component_owner_cash_and_unit_nav":
        route_supported = bool(
            proof_methods.intersection(owner_cash_family | owner_earnings_family)
            and proof_methods.intersection(nav_family)
        )
    if not route_supported:
        return None
    model = _compiled_model(
        ticker, as_of, identity, routed_method, compiled, {},
        {
            "primary_method": routed_method,
            "method_version": "1.0",
            "automation": "revalidated_existing_approved_proofs",
            "component_methods": sorted(proof_methods),
        },
    )
    model["inputs"] = copy.deepcopy(prior.get("inputs") or {})
    # These proofs were authored for this issuer and merely revalidated here, so
    # the routed method stays the recorded method. Stamping "proof_first_automated"
    # would make the NEXT run's guard above discard them and recompile from the
    # normalized ledger, silently replacing issuer-specific economics with a
    # first-pass model on the second run.
    model["method"] = routed_method
    return model


def compile_valuation(ticker: str, as_of: str, identity: dict, ledger: dict) -> dict | None:
    """Dispatch only to the compiler selected by the canonical Power Zone route."""
    existing = compile_existing_approved_proofs(ticker, as_of, identity)
    if existing:
        return existing
    compiler = METHOD_COMPILERS.get(str(identity.get("primary_method") or ""))
    return compiler(ticker, as_of, identity, ledger) if compiler else None


def run_command(args: list[str]) -> dict:
    proc = subprocess.run([sys.executable, *args], cwd=ROOT, text=True, capture_output=True)
    return {"returncode": proc.returncode, "stdout": proc.stdout[-4000:], "stderr": proc.stderr[-4000:]}


def run_ticker(ticker: str, as_of: str, collect: bool, full_rerun: bool) -> dict:
    research = ROOT / ticker / "research"
    state_path = research / "valuation_automation_state.json"
    state = read_json(state_path, {"schema_version": "1.0", "ticker": ticker, "stages": {}})
    registry_payload = read_json(REGISTRY)
    registry = registry_payload.get("holdings") or registry_payload.get("tickers") or registry_payload
    overrides = read_json(OVERRIDES)
    route = build_route(ticker, as_of)
    write_json(research / "valuation_route.json", route)
    identity = resolve_identity(ticker, registry.get(ticker, {}), overrides, as_of, route)
    write_json(research / "security_identity.json", identity)
    state["stages"]["identity"] = {"status": "complete", "at": now()}
    collection_results = []
    if collect:
        collection_results.append(fetch_companyfacts(ticker, identity.get("cik")))
        collection_results.append(run_command([str(SCRIPTS / "download_us_investor_docs.py"), "--ticker", ticker]))
        collection_results.append(run_command([str(SCRIPTS / "build_filing_evidence.py"), ticker]))
    state["stages"]["collection"] = {"status": "complete" if not any(r["returncode"] for r in collection_results) else "partial", "at": now(), "results": collection_results}
    ledger = build_fact_ledger(ticker, as_of)
    write_json(research / "valuation_fact_ledger.json", ledger)
    prior_valuation = read_json(research / "valuation.json")
    prior_inputs = prior_valuation.get("inputs") if isinstance(prior_valuation.get("inputs"), dict) else {}
    model = compile_valuation(ticker, as_of, identity, ledger)
    if model:
        # Preserve live market marks fetched into inputs.price.
        merged_inputs = dict(prior_inputs)
        merged_inputs.update(model.get("inputs") or {})
        for key in ("price", "price_as_of", "price_source"):
            if prior_inputs.get(key) not in (None, ""):
                merged_inputs[key] = prior_inputs[key]
        model["inputs"] = merged_inputs
        write_json(research / "valuation.json", merge_compiled_model(prior_valuation, model))
    else:
        if prior_valuation.get("method") == "proof_first_automated":
            (research / "valuation.json").unlink(missing_ok=True)
    plan = evidence_plan(ticker, identity, ledger, as_of, model_ready=bool(model), model=model)
    write_json(research / "evidence_task_queue.json", plan)
    state["stages"]["model_compile"] = {
        "status": "complete" if model else "evidence_blocked",
        "at": now(),
        "method_id": identity["primary_method"],
        "input_errors": [] if model else validate_method_inputs(identity["primary_method"], ledger),
    }
    decision = run_command([str(SCRIPTS / "run_security_decision_pipeline.py"), "--tickers", ticker, "--date", as_of, "--skip-dashboard"])
    contract = read_json(research / "valuation_contract.json")
    state.update({"updated_at": now(), "full_rerun": full_rerun, "status": "decision_grade" if contract.get("status") == "decision_grade" else "evidence_blocked"})
    state["stages"]["decision_contract"] = {"status": "complete" if decision["returncode"] == 0 else "failed", "at": now(), "result": decision}

    # SSI Perplexity-grade chain (Phases 1-4): deterministic, additive-only
    # artifacts; safe to run on every readiness pass. Requires _text extracts
    # (created by build_filing_evidence above when --collect ran).
    ssi_results = []
    for script in ("build_ssi_evidence_pack.py", "build_ssi_claims.py",
                   "verify_ssi_claims.py", "build_ssi_report.py"):
        ssi_results.append(run_command([str(SCRIPTS / script), ticker, "--date", as_of]))
        if ssi_results[-1]["returncode"]:
            break
    state["stages"]["ssi_report"] = {
        "status": "complete" if not any(r["returncode"] for r in ssi_results) else "partial",
        "at": now(),
        "results": ssi_results,
    }
    write_json(state_path, state)
    return {"ticker": ticker, "status": state["status"], "method": identity["primary_method"], "ready": plan["ready_count"], "tasks": plan["task_count"]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", nargs="+", type=str.upper, required=True)
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--collect", action="store_true", help="Download/refresh primary filings before compiling.")
    parser.add_argument("--full-rerun", action="store_true", help="Re-run every idempotent stage, even after prior success.")
    args = parser.parse_args()
    results = [run_ticker(t, args.date, args.collect, args.full_rerun) for t in args.tickers]
    print(json.dumps({"results": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
