#!/usr/bin/env python3
"""Build filing-backed calculation proofs for the TBBK universal contract.

The Bancorp is a sponsor bank managed against a $10 billion asset cap (FRB
Reg II, Durbin).  That cap is the organizing economic fact: retained capital
cannot be deployed into the balance sheet, so the company distributes close to
100% of net income and per-share growth arrives through fee income operating
leverage plus share count reduction rather than through balance sheet
reinvestment.

The generic first-pass compiler in ``automate_valuation_readiness.py`` models
TBBK as a single reinvestment compounder.  That misstates the economics twice:
it takes 100% of owner earnings as distributable while simultaneously growing
those earnings at ``reinvestment * incremental_roic`` (the "growth without its
capital cost" failure mode named on the method card), and it treats operating
cash flow less capital expenditure as owner cash for a bank whose operating
cash flow swings with provisions and working capital.

This script supersedes that first pass with a segment partition.  Segment net
income sums exactly to consolidated net income, so every material economic
claim is valued once and only once:

  fintech_solutions_franchise      fee platform, growing, higher terminal
  credit_solutions_lending_book    REBL + institutional + commercial, cyclical
  corporate_and_securities         residual treasury and corporate result
  fintech_credit_enhancement_reserve   counterparty tail risk, negative

Buybacks are deliberately not modelled as a value driver here.  Distributable
cash is valued in full and divided by today's share count, so returning that
cash through repurchase rather than dividend is value neutral at fair value.
The earnings-per-share consequence of the repurchase programme is mapped
separately in ``build_tbbk_buyback_model.py``.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from calculation_proof import evaluate_calculation_proof  # noqa: E402

TICKER = "TBBK"
AS_OF = "2026-08-06"
YEARS = 7

K10 = "TBBK/investor-documents/sec-edgar/10-K_20260225_rpt20251231_acc0001295401_26_000002.htm"
Q10 = "TBBK/investor-documents/sec-edgar/10-Q_20260506_rpt20260331_acc0001295401_26_000004.htm"
DECK = "TBBK/investor-documents/ir-tbbk/tbbk-investor-presentation-q2-2026.pdf"

SHARES_M = 41.634439  # dei:EntityCommonStockSharesOutstanding, 10-Q cover 2026-04-27

# Half-year 2026 segment net income, doubled to an annual run rate.  Source:
# Q2 2026 deck page 21, "Six Months Ended Jun 30, 2026" segment table.
# 71.322 + 29.275 + 6.994 + 8.077 + 5.057 = 120.725 = consolidated H1 2026.
FINTECH_H1_M = 71.322
REBL_H1_M = 29.275
INSTITUTIONAL_H1_M = 6.994
COMMERCIAL_H1_M = 8.077
CORPORATE_H1_M = 5.057
CREDIT_BOOK_H1_M = REBL_H1_M + INSTITUTIONAL_H1_M + COMMERCIAL_H1_M

# Fintech net charge-offs, 2026 year to date (Q2 2026 deck page 12 footnote).
# Fully offset today by contractual credit enhancement income from the fintech
# partner; the reserve prices the possibility that the offset fails.
FINTECH_YTD_CHARGE_OFFS_M = 55.0


def _fact(node_id: str, label: str, value: float, unit: str, ref: str, locator: str, as_of: str) -> dict:
    return {
        "id": node_id,
        "label": label,
        "kind": "fact",
        "value": value,
        "unit": unit,
        "source": {"ref": ref, "locator": locator, "as_of": as_of},
        "locked": True,
    }


def _judgment(node_id: str, label: str, values: dict, unit: str, rationale: str, lo: float, hi: float) -> dict:
    return {
        "id": node_id,
        "label": label,
        "kind": "judgment",
        "values": values,
        "unit": unit,
        "rationale": rationale,
        "allowed_range": {"min": lo, "max": hi},
    }


def _shares_fact() -> dict:
    return _fact(
        "shares_m", "Common shares outstanding", SHARES_M, "million_shares", Q10,
        "dei:EntityCommonStockSharesOutstanding 41,634,439; Form 10-Q cover page", "2026-04-27",
    )


def _distributable_stream_calcs(base_node: str) -> list[dict]:
    """Grow a distributable owner-earnings base and discount it to today.

    The cap on balance sheet growth means essentially all segment net income is
    distributable, so distributable cash equals owner earnings in each year and
    no separate reinvestment charge is deducted.  Growth is therefore an
    explicit judgment about fee income and credit spread, never a free
    by-product of retained capital.
    """
    calcs: list[dict] = [{"id": "growth_factor", "op": "add", "args": [1, "growth_rate"], "unit": "ratio"}]
    prior = base_node
    for year in range(1, YEARS + 1):
        node = f"owner_earnings_y{year}"
        calcs.append({"id": node, "op": "multiply", "args": [prior, "growth_factor"], "unit": "USD_m"})
        prior = node
    cash_args: list = []
    for year in range(1, YEARS + 1):
        cash_args.extend([f"owner_earnings_y{year}", year])
    cash_args.append("discount_rate")
    calcs.extend([
        {"id": "cash_pv_m", "op": "present_value", "args": cash_args, "unit": "USD_m"},
        {"id": "terminal_value_m", "op": "multiply", "args": [f"owner_earnings_y{YEARS}", "terminal_multiple"], "unit": "USD_m"},
        {"id": "terminal_pv_m", "op": "discount", "args": ["terminal_value_m", "discount_rate", YEARS], "unit": "USD_m"},
        {"id": "equity_value_m", "op": "add", "args": ["cash_pv_m", "terminal_pv_m"], "unit": "USD_m"},
        {"id": "value_per_share", "op": "divide", "args": ["equity_value_m", "shares_m"], "unit": "USD_per_share"},
    ])
    return calcs


def fintech_franchise_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "owner_earnings_reinvestment_dcf",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact("fintech_h1_2026_net_income_m", "Fintech Solutions segment net income, six months ended 2026-06-30",
                  FINTECH_H1_M, "USD_m", DECK,
                  "Segment results table, six months ended Jun 30 2026: Fintech net income $71,322 thousand", "2026-06-30"),
            _fact("fintech_fy2025_net_income_m", "Fintech Solutions segment net income FY2025",
                  115.835, "USD_m", DECK,
                  "Segment results table, year ended Dec 31 2025: Fintech net income $115,835 thousand", "2025-12-31"),
            _fact("fintech_fee_revenue_adjusted_fy2025_m", "Fintech fee revenue excluding credit enhancement, FY2025",
                  141.261, "USD_m", DECK,
                  "Non-GAAP reconciliation: FTS fee revenue, adjusted $141,261 thousand FY2025", "2025-12-31"),
            _fact("gross_dollar_volume_fy2025_m", "Prepaid, debit and credit card gross dollar volume FY2025",
                  178211.647, "USD_m", DECK,
                  "Non-GAAP reconciliation: GDV $178,211,647 thousand FY2025", "2025-12-31"),
            _shares_fact(),
        ],
        "assumptions": [
            _judgment("annualization", "Half-year to annual run-rate factor", {"low": 2.0, "base": 2.0, "high": 2.0},
                      "ratio",
                      "The two 2026 half-years are of comparable seasonality; Q1 2026 diluted EPS $1.41 and Q2 2026 "
                      "$1.45 differ by 3%, so doubling the half is a fair annualisation.", 2.0, 2.0),
            _judgment("growth_rate", "Fintech owner-earnings growth, years 1 to 7",
                      {"low": 0.03, "base": 0.09, "high": 0.15}, "ratio",
                      "Adjusted fintech fee revenue compounded 14.4% a year from $82.3m in 2021 to $141.3m in 2025 and "
                      "GDV compounded 14.3% over the same span, with positive operating leverage in every year "
                      "(expense per $1,000 of GDV fell from $0.67 to $0.45). The base case fades that to 9% because "
                      "the $10bn asset cap limits deposit-funded spread growth. The low case assumes partner attrition "
                      "and interchange compression; the high case assumes Apex 2030 embedded finance delivers.",
                      -0.10, 0.25),
            _judgment("discount_rate", "Cost of equity", {"low": 0.12, "base": 0.105, "high": 0.095}, "ratio",
                      "Small-cap bank cost of equity with a premium for fintech partner concentration and sponsor-bank "
                      "regulatory risk.", 0.06, 0.20),
            _judgment("terminal_multiple", "Terminal multiple on year-7 owner earnings",
                      {"low": 10.0, "base": 14.0, "high": 17.0}, "multiple",
                      "A fee-based payments franchise supports a higher exit multiple than a balance sheet lender. "
                      "TBBK trades at 13.6x trailing earnings today; the base case assumes the fee mix earns a modest "
                      "premium to that, the low case a discount to bank-like economics.", 6.0, 22.0),
        ],
        "calculations": [
            {"id": "owner_earnings_base_m", "op": "multiply",
             "args": ["fintech_h1_2026_net_income_m", "annualization"], "unit": "USD_m"},
            *_distributable_stream_calcs("owner_earnings_base_m"),
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def credit_book_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "capital_structure_and_excess_return",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact("rebl_h1_2026_net_income_m", "Real estate bridge lending net income, six months ended 2026-06-30",
                  REBL_H1_M, "USD_m", DECK,
                  "Segment results table, six months ended Jun 30 2026: REBL net income $29,275 thousand", "2026-06-30"),
            _fact("institutional_h1_2026_net_income_m", "Institutional banking net income, six months ended 2026-06-30",
                  INSTITUTIONAL_H1_M, "USD_m", DECK,
                  "Segment results table, six months ended Jun 30 2026: Institutional Banking net income $6,994 thousand",
                  "2026-06-30"),
            _fact("commercial_h1_2026_net_income_m", "Commercial lending net income, six months ended 2026-06-30",
                  COMMERCIAL_H1_M, "USD_m", DECK,
                  "Segment results table, six months ended Jun 30 2026: Commercial net income $8,077 thousand", "2026-06-30"),
            _fact("stockholders_equity_fy2025_m", "Total shareholders' equity at 2025-12-31", 689.796, "USD_m", K10,
                  "us-gaap:StockholdersEquity $689,796 thousand", "2025-12-31"),
            _fact("total_assets_fy2025_m", "Total assets at 2025-12-31", 9352.425, "USD_m", K10,
                  "us-gaap:Assets $9,352,425 thousand", "2025-12-31"),
            _shares_fact(),
        ],
        "assumptions": [
            _judgment("annualization", "Half-year to annual run-rate factor", {"low": 2.0, "base": 2.0, "high": 2.0},
                      "ratio", "Consistent with the fintech component annualisation.", 2.0, 2.0),
            _judgment("growth_rate", "Credit Solutions owner-earnings growth, years 1 to 7",
                      {"low": -0.06, "base": 0.0, "high": 0.04}, "ratio",
                      "Credit Solutions loans were flat at $6.2bn through 2024 and 2025 and fell to $5.8bn by Q2 2026 "
                      "while management shifts the balance sheet toward a fintech-dominated mix inside the $10bn cap. "
                      "The base case therefore holds this book flat rather than growing it. The low case prices "
                      "multifamily bridge runoff plus credit normalisation from the 2025 leasing charge-offs.",
                      -0.15, 0.10),
            _judgment("discount_rate", "Cost of equity for the lending book",
                      {"low": 0.12, "base": 0.11, "high": 0.10}, "ratio",
                      "Balance sheet credit risk carries a higher required return than the fee franchise.", 0.06, 0.20),
            _judgment("terminal_multiple", "Terminal multiple on year-7 owner earnings",
                      {"low": 7.0, "base": 9.0, "high": 11.0}, "multiple",
                      "Bank-like exit economics for a spread lending book: below the KBW regional bank median in the "
                      "low case, at it in the base case.", 4.0, 14.0),
        ],
        "calculations": [
            {"id": "credit_h1_subtotal_a_m", "op": "add",
             "args": ["rebl_h1_2026_net_income_m", "institutional_h1_2026_net_income_m"], "unit": "USD_m"},
            {"id": "credit_h1_total_m", "op": "add",
             "args": ["credit_h1_subtotal_a_m", "commercial_h1_2026_net_income_m"], "unit": "USD_m"},
            {"id": "owner_earnings_base_m", "op": "multiply",
             "args": ["credit_h1_total_m", "annualization"], "unit": "USD_m"},
            *_distributable_stream_calcs("owner_earnings_base_m"),
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def corporate_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "capital_structure_and_excess_return",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact("corporate_h1_2026_net_income_m", "Corporate segment net income, six months ended 2026-06-30",
                  CORPORATE_H1_M, "USD_m", DECK,
                  "Segment results table, six months ended Jun 30 2026: Corporate net income $5,057 thousand", "2026-06-30"),
            _fact("corporate_fy2025_net_income_m", "Corporate segment net income FY2025", 22.854, "USD_m", DECK,
                  "Segment results table, year ended Dec 31 2025: Corporate net income $22,854 thousand", "2025-12-31"),
            _fact("securities_fair_value_q2_2026_m", "Securities portfolio fair value at 2026-06-30", 1615.0, "USD_m", DECK,
                  "Securities portfolio page: fair value $1,615 million at Jun-26, 4.3 year modified duration", "2026-06-30"),
            _shares_fact(),
        ],
        "assumptions": [
            _judgment("annualization", "Half-year to annual run-rate factor", {"low": 2.0, "base": 2.0, "high": 2.0},
                      "ratio", "Consistent with the other components.", 2.0, 2.0),
            _judgment("growth_rate", "Corporate and securities owner-earnings growth, years 1 to 7",
                      {"low": -0.05, "base": 0.0, "high": 0.03}, "ratio",
                      "The corporate result more than halved from $22.9m in FY2025 to a $10.1m run rate in 2026 as "
                      "interest allocation shifted toward the fintech segment. The base case holds the reduced level "
                      "flat; roughly $160m of securities principal rolls off annually for three years, so reinvestment "
                      "yield is the swing factor rather than volume.", -0.12, 0.08),
            _judgment("discount_rate", "Cost of equity", {"low": 0.12, "base": 0.11, "high": 0.10}, "ratio",
                      "Same required return as the lending book.", 0.06, 0.20),
            _judgment("terminal_multiple", "Terminal multiple on year-7 owner earnings",
                      {"low": 6.0, "base": 8.0, "high": 10.0}, "multiple",
                      "Residual treasury earnings deserve the lowest exit multiple in the map.", 3.0, 12.0),
        ],
        "calculations": [
            {"id": "owner_earnings_base_m", "op": "multiply",
             "args": ["corporate_h1_2026_net_income_m", "annualization"], "unit": "USD_m"},
            *_distributable_stream_calcs("owner_earnings_base_m"),
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def credit_enhancement_reserve_proof() -> dict:
    """Price the possibility that the fintech credit enhancement stops working.

    Fintech loan losses do not touch net income today because an equal amount
    is recognised in non-interest income under a contractual credit
    enhancement from the fintech partner.  In FY2025 that offset was $169.3m,
    against $151.1m of fintech net charge-offs, on average fintech balances of
    $607m.  The offset is only as good as the counterparty behind it, and the
    balances it covers have roughly doubled again in 2026.  This component
    charges the expected cost of that offset failing; it does not overlap the
    other three, whose owner earnings are already reported net of the offset.
    """
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact("fintech_charge_offs_ytd_2026_m", "Fintech net charge-offs, 2026 year to date",
                  FINTECH_YTD_CHARGE_OFFS_M, "USD_m", DECK,
                  "Credit Solutions page footnote: fintech net charge-offs of $55.0mm Q2 YTD 2026, fully offset by "
                  "credit enhancement income", "2026-06-30"),
            _fact("credit_enhancement_income_fy2025_m", "Fintech loan credit enhancement income FY2025",
                  169.294, "USD_m", DECK,
                  "Non-GAAP reconciliation: fintech loan credit enhancement $169,294 thousand FY2025", "2025-12-31"),
            _fact("average_fintech_balances_ytd_2026_m", "Average fintech loan balances, 2026 year to date",
                  1254.0, "USD_m", DECK,
                  "Credit Solutions page footnote: average fintech balances $1,254mm Q2 YTD 2026", "2026-06-30"),
            _shares_fact(),
        ],
        "assumptions": [
            _judgment("annualization", "Half-year to annual run-rate factor", {"low": 2.0, "base": 2.0, "high": 2.0},
                      "ratio", "Consistent with the other components.", 2.0, 2.0),
            _judgment("enhancement_failure_probability",
                      "Probability the credit enhancement fails to absorb one year of fintech losses",
                      {"low": 0.60, "base": 0.25, "high": 0.05}, "ratio",
                      "The enhancement is an unsecured contractual claim on fintech partners whose own credit standing "
                      "is not disclosed. Covered balances grew from $138m average in 2024 to $1,254m in 2026, so the "
                      "concentration is rising faster than the bank's equity. The base case prices a one-in-four chance "
                      "of a single unabsorbed year over the seven-year horizon.", 0.0, 1.0),
        ],
        "calculations": [
            {"id": "annual_fintech_losses_m", "op": "multiply",
             "args": ["fintech_charge_offs_ytd_2026_m", "annualization"], "unit": "USD_m"},
            {"id": "expected_unabsorbed_loss_m", "op": "multiply",
             "args": ["annual_fintech_losses_m", "enhancement_failure_probability"], "unit": "USD_m"},
            {"id": "reserve_m", "op": "negative", "args": ["expected_unabsorbed_loss_m"], "unit": "USD_m"},
            {"id": "value_per_share", "op": "divide", "args": ["reserve_m", "shares_m"], "unit": "USD_per_share"},
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


COMPONENTS = [
    {
        "id": "fintech_solutions_franchise",
        "label": "Fintech Solutions sponsorship, payments and sponsored lending franchise",
        "category": "operating_business",
        "treatment": "additive",
        "overlap_key": "segment_fintech",
        "method": "owner_earnings_reinvestment_dcf",
        "evidence_tier": "primary_derived",
        "evidence": "Segment net income partitioned from the audited consolidated result; fee revenue, GDV and "
                    "operating leverage from the non-GAAP reconciliation in the Q2 2026 deck.",
        "proof": fintech_franchise_proof,
        "falsifier": "Adjusted fintech fee revenue growth falls below 5% for two consecutive quarters, or a top-five "
                     "partner programme terminates.",
    },
    {
        "id": "credit_solutions_lending_book",
        "label": "Credit Solutions lending book: real estate bridge, institutional and commercial",
        "category": "financial_asset",
        "treatment": "additive",
        "overlap_key": "segment_credit_solutions",
        "method": "capital_structure_and_excess_return",
        "evidence_tier": "primary_derived",
        "evidence": "Segment net income partitioned from the audited consolidated result; loan balances and yields "
                    "from the Q2 2026 deck; equity and assets from the FY2025 10-K.",
        "proof": credit_book_proof,
        "falsifier": "Charge-offs excluding fintech exceed 0.35% of loans, or Credit Solutions balances fall below "
                     "$5.0bn.",
    },
    {
        "id": "corporate_and_securities",
        "label": "Corporate result and securities portfolio",
        "category": "financial_asset",
        "treatment": "additive",
        "overlap_key": "segment_corporate",
        "method": "capital_structure_and_excess_return",
        "evidence_tier": "primary_derived",
        "evidence": "Residual corporate segment net income; securities fair value and duration from the Q2 2026 deck.",
        "proof": corporate_proof,
        "falsifier": "Corporate segment net income turns negative for a full year.",
    },
    {
        "id": "fintech_credit_enhancement_reserve",
        "label": "Reserve against failure of the fintech loan credit enhancement",
        "category": "liability_or_reserve",
        "treatment": "additive",
        "overlap_key": "fintech_enhancement_counterparty",
        "method": "net_asset_value",
        "evidence_tier": "primary_derived",
        "evidence": "Credit enhancement income, fintech charge-offs and average covered balances disclosed in the "
                    "Q2 2026 deck non-GAAP reconciliation and Credit Solutions footnote.",
        "proof": credit_enhancement_reserve_proof,
        "falsifier": "The company discloses the identity and credit standing of the enhancement counterparties, or "
                     "collateralises the receivable.",
    },
]


def build() -> dict:
    components = []
    errors = []
    for spec in COMPONENTS:
        proof = spec["proof"]()
        evaluation = evaluate_calculation_proof(proof)
        if evaluation["status"] != "valid":
            errors.extend(f"{spec['id']}: {message}" for message in evaluation["checks"]["errors"])
        components.append({
            "id": spec["id"],
            "label": spec["label"],
            "category": spec["category"],
            "treatment": spec["treatment"],
            "overlap_key": spec["overlap_key"],
            "method": spec["method"],
            "evidence_tier": spec["evidence_tier"],
            "evidence": spec["evidence"],
            "falsifier": spec["falsifier"],
            "valuation_status": "calculated",
            "calculation_proof": proof,
            "_outputs": evaluation["outputs"],
        })
    return {"components": components, "errors": errors}


def main() -> int:
    result = build()
    if result["errors"]:
        for message in result["errors"]:
            print(f"ERROR {message}")
        return 1

    valuation_path = ROOT / TICKER / "research" / "valuation.json"
    valuation = json.loads(valuation_path.read_text(encoding="utf-8"))

    totals = {case: 0.0 for case in ("low", "base", "high")}
    for component in result["components"]:
        for case in totals:
            totals[case] += component["_outputs"][case]
        print(f"{component['id']:38s} {component['_outputs']}")
    print(f"{'TOTAL':38s} {{k: round(v, 2) for k, v in totals.items()}}".replace(
        "{k: round(v, 2) for k, v in totals.items()}",
        json.dumps({k: round(v, 2) for k, v in totals.items()}),
    ))

    for component in result["components"]:
        component.pop("_outputs", None)

    valuation["component_valuation_results"] = {
        "all_material_components_identified": True,
        "additive_components": result["components"],
        "embedded_components": [],
        "partition_note": (
            "Components partition consolidated net income by reportable segment. H1 2026 segment net income of "
            "$71.322m fintech, $29.275m REBL, $6.994m institutional, $8.077m commercial and $5.057m corporate sums "
            "to the reported $120.725m consolidated result, so no economic claim is valued twice or omitted. The "
            "credit enhancement reserve prices a counterparty exposure that the segment results net to zero and "
            "therefore do not capture."
        ),
        "source": "_system/scripts/build_tbbk_contract_proofs.py",
        "as_of": AS_OF,
    }
    valuation["valuation_methodology"] = {
        **(valuation.get("valuation_methodology") or {}),
        "horizon_years": YEARS,
        "automation": "issuer_specific_approved_proof",
        "capital_return_treatment": (
            "Distributable cash is valued in full and divided by the current share count. Returning it through "
            "repurchase rather than dividend is value neutral at fair value, so buybacks are not counted as a "
            "separate source of value. Their earnings-per-share effect is mapped in "
            "TBBK/research/buyback_eps_model.json."
        ),
        "asset_cap_note": (
            "Total assets were $9.352bn at 2025-12-31 against the $10bn FRB Reg II threshold, leaving roughly 7% of "
            "headroom. Balance sheet growth is therefore not available as a value driver and no reinvestment charge "
            "is deducted from distributable cash."
        ),
    }
    valuation["as_of"] = AS_OF
    valuation_path.write_text(json.dumps(valuation, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nWrote {valuation_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
