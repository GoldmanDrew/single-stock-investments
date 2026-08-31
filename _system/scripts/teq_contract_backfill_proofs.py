#!/usr/bin/env python3
"""Build TEQ.ST's filing-reconciled, stock-specific valuation model.

The operating proof is an enterprise free-cash-flow DCF. The equity bridge
then deducts every financing claim exactly once. Future acquisitions receive
neither a cash cost nor a speculative benefit in the valuation; completed
acquisitions are already present in the reported trailing cash flow and balance
sheet. This prevents acquisition spend, debt capacity, and market price from
being added to intrinsic value as if they were separate assets.
"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VAL_PATH = ROOT / "TEQ.ST" / "research" / "valuation.json"
AUTH_PATH = ROOT / "TEQ.ST" / "research" / "authorized_evidence.json"
LEDGER_PATH = ROOT / "TEQ.ST" / "research" / "valuation_fact_ledger.json"

Q2_2026 = (
    "TEQ.ST/official-reports/interim-reports/2026/"
    "2026-07-18 - Interim Report April - June 2026 - Teqnion AB.pdf"
)
ANNUAL_2025 = (
    "TEQ.ST/official-reports/annual-reports/"
    "2026-03-21 - Årsredovisning 2025.pdf"
)
RECONCILIATION = "TEQ.ST/research/evidence_reconciliation_2026-08-31.json"
AS_OF = "2026-06-30"

OPERATING_CASH_FLOW_M = 213.5
CAPEX_M = 8.6
CASH_NET_FINANCE_M = 31.7
SHARES_M = 17.165756
CASH_M = 171.5
BANK_DEBT_M = 552.5
LEASE_NON_CURRENT_M = 109.1
LEASE_CURRENT_M = 54.4
OTHER_FINANCIAL_NON_CURRENT_M = 132.3
OTHER_FINANCIAL_CURRENT_M = 50.5
NON_CONTROLLING_INTEREST_M = 1.4


def _source(locator: str) -> dict:
    return {"ref": Q2_2026, "locator": locator, "as_of": AS_OF}


def _fact(node_id: str, label: str, value: float, unit: str, locator: str) -> dict:
    return {
        "id": node_id,
        "label": label,
        "kind": "fact",
        "value": value,
        "unit": unit,
        "source": _source(locator),
        "locked": True,
    }


def _judgment(
    node_id: str,
    label: str,
    values: dict,
    unit: str,
    rationale: str,
    low: float,
    high: float,
) -> dict:
    return {
        "id": node_id,
        "label": label,
        "kind": "judgment",
        "values": values,
        "unit": unit,
        "rationale": rationale,
        "allowed_range": {"min": low, "max": high},
    }


def operating_enterprise_proof() -> dict:
    calculations = [
        {
            "id": "fcfe_ex_acquisitions_m",
            "label": "R12 free cash flow excluding acquisitions",
            "op": "subtract",
            "args": ["operating_cash_flow_m", "maintenance_capex_m"],
            "unit": "SEK_m",
        },
        {
            "id": "after_tax_factor",
            "label": "One minus normalized cash tax rate",
            "op": "subtract",
            "args": [1, "cash_tax_rate"],
            "unit": "ratio",
        },
        {
            "id": "after_tax_net_finance_m",
            "label": "After-tax net financing cost added back",
            "op": "multiply",
            "args": ["cash_net_finance_m", "after_tax_factor"],
            "unit": "SEK_m",
        },
        {
            "id": "reported_fcff_m",
            "label": "R12 enterprise free cash flow before acquisitions",
            "op": "add",
            "args": ["fcfe_ex_acquisitions_m", "after_tax_net_finance_m"],
            "unit": "SEK_m",
        },
        {
            "id": "normalized_fcff_m",
            "label": "Scenario-normalized starting enterprise cash flow",
            "op": "multiply",
            "args": ["reported_fcff_m", "normalization_factor"],
            "unit": "SEK_m",
        },
        {
            "id": "normalized_fcff_per_share",
            "label": "Starting enterprise cash flow per share",
            "op": "divide",
            "args": ["normalized_fcff_m", "shares_m"],
            "unit": "SEK_per_share",
        },
        {
            "id": "growth_factor_y1_5",
            "label": "Growth factor in years 1–5",
            "op": "add",
            "args": [1, "growth_y1_5"],
            "unit": "ratio",
        },
        {
            "id": "growth_factor_y6_7",
            "label": "Growth factor in years 6–7",
            "op": "add",
            "args": [1, "growth_y6_7"],
            "unit": "ratio",
        },
    ]
    prior = "normalized_fcff_per_share"
    for year in range(1, 8):
        node_id = f"fcff_per_share_y{year}"
        calculations.append(
            {
                "id": node_id,
                "label": f"Enterprise cash flow per share in year {year}",
                "op": "multiply",
                "args": [prior, "growth_factor_y1_5" if year <= 5 else "growth_factor_y6_7"],
                "unit": "SEK_per_share",
            }
        )
        prior = node_id
    cash_flow_args: list[str | int] = []
    for year in range(1, 7):
        cash_flow_args.extend([f"fcff_per_share_y{year}", year])
    calculations.extend(
        [
            {
                "id": "explicit_cash_flow_pv",
                "label": "Present value of years 1–6 enterprise cash flow",
                "op": "present_value",
                "args": [*cash_flow_args, "discount_rate"],
                "unit": "SEK_per_share",
            },
            {
                "id": "terminal_enterprise_value",
                "label": "Year-7 terminal enterprise value",
                "op": "multiply",
                "args": ["fcff_per_share_y7", "exit_fcff_multiple"],
                "unit": "SEK_per_share",
            },
            {
                "id": "terminal_enterprise_value_pv",
                "label": "Present value of terminal enterprise value",
                "op": "discount",
                "args": ["terminal_enterprise_value", "discount_rate", 7],
                "unit": "SEK_per_share",
            },
            {
                "id": "enterprise_value_per_share",
                "label": "Operating enterprise value per share",
                "op": "add",
                "args": ["explicit_cash_flow_pv", "terminal_enterprise_value_pv"],
                "unit": "SEK_per_share",
            },
        ]
    )
    return {
        "schema_version": "1.0",
        "method_id": "owner_earnings_reinvestment_dcf",
        "method_version": "1.0",
        "output_unit": "SEK_per_share",
        "inputs": [
            _fact(
                "operating_cash_flow_m",
                "R12 cash flow from operating activities",
                OPERATING_CASH_FLOW_M,
                "SEK_m",
                "page 18: R12 cash flow from operating activities 213.5 MSEK",
            ),
            _fact(
                "maintenance_capex_m",
                "R12 net capital expenditure",
                CAPEX_M,
                "SEK_m",
                "page 18: R12 net capital expenditure 8.6 MSEK",
            ),
            _fact(
                "cash_net_finance_m",
                "R12 cash interest and other financial items, net",
                CASH_NET_FINANCE_M,
                "SEK_m",
                "page 18: R12 interest and other financial items, net -31.7 MSEK",
            ),
            _fact(
                "shares_m",
                "Diluted shares outstanding",
                SHARES_M,
                "million_shares",
                "page 17: Q2/YTD average shares after dilution and period-end shares 17,165,756",
            ),
        ],
        "assumptions": [
            _judgment(
                "cash_tax_rate",
                "Normalized cash tax rate",
                {"low": 0.28, "base": 0.25, "high": 0.22},
                "ratio",
                "Bounded around H1 2026 tax expense/profit before tax (26.2%) and the Swedish/UK operating mix.",
                0.18,
                0.35,
            ),
            _judgment(
                "normalization_factor",
                "Starting cash-flow normalization",
                {"low": 0.85, "base": 0.95, "high": 1.0},
                "ratio",
                "R12 cash conversion is filing-derived but follows a record margin period; no case starts above reported R12 cash flow.",
                0.70,
                1.05,
            ),
            _judgment(
                "growth_y1_5",
                "Existing-portfolio cash-flow growth in years 1–5",
                {"low": -0.02, "base": 0.05, "high": 0.08},
                "ratio",
                "Cases reflect organic/margin outcomes in the owned portfolio only. Future acquisition benefits and purchase prices are both excluded.",
                -0.10,
                0.15,
            ),
            _judgment(
                "growth_y6_7",
                "Existing-portfolio cash-flow growth in years 6–7",
                {"low": 0.0, "base": 0.03, "high": 0.04},
                "ratio",
                "Growth fades toward mature industrial nominal growth.",
                -0.05,
                0.08,
            ),
            _judgment(
                "discount_rate",
                "Required return on enterprise cash flow",
                {"low": 0.13, "base": 0.105, "high": 0.09},
                "ratio",
                "Scenario rates reflect First North liquidity, decentralized operating risk, cyclicality, and leverage.",
                0.08,
                0.16,
            ),
            _judgment(
                "exit_fcff_multiple",
                "Year-7 enterprise free-cash-flow multiple",
                {"low": 9.0, "base": 14.0, "high": 16.0},
                "multiple",
                "Terminal multiples are below or near the current enterprise/owner-cash cross-check and require the portfolio economics to persist.",
                6.0,
                20.0,
            ),
        ],
        "calculations": calculations,
        "outputs": {
            "low": "enterprise_value_per_share",
            "base": "enterprise_value_per_share",
            "high": "enterprise_value_per_share",
        },
    }


def financing_claims_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "SEK_per_share",
        "inputs": [
            _fact("bank_debt_m", "Bank debt", BANK_DEBT_M, "SEK_m", "page 16: non-current liabilities to credit institutions 552.5 MSEK"),
            _fact("lease_non_current_m", "Non-current lease liabilities", LEASE_NON_CURRENT_M, "SEK_m", "page 16: non-current lease liabilities 109.1 MSEK"),
            _fact("lease_current_m", "Current lease liabilities", LEASE_CURRENT_M, "SEK_m", "page 16: current lease liabilities 54.4 MSEK"),
            _fact("other_financial_non_current_m", "Other non-current financial liabilities", OTHER_FINANCIAL_NON_CURRENT_M, "SEK_m", "pages 16 and 21: other non-current financial liabilities 132.3 MSEK; acquisition payments carried at fair value"),
            _fact("other_financial_current_m", "Other current financial liabilities", OTHER_FINANCIAL_CURRENT_M, "SEK_m", "pages 16 and 21: other current financial liabilities 50.5 MSEK; acquisition payments carried at fair value"),
            _fact("cash_m", "Cash and cash equivalents", CASH_M, "SEK_m", "page 16: cash and cash equivalents 171.5 MSEK"),
            _fact("non_controlling_interest_m", "Non-controlling interest", NON_CONTROLLING_INTEREST_M, "SEK_m", "pages 16–17: non-controlling interests 1.4 MSEK"),
            _fact("shares_m", "Diluted shares outstanding", SHARES_M, "million_shares", "page 17: Q2/YTD average shares after dilution and period-end shares 17,165,756"),
        ],
        "assumptions": [],
        "calculations": [
            {
                "id": "gross_financing_claims_m",
                "label": "Bank, lease, and acquisition-payment claims",
                "op": "sum",
                "args": [
                    "bank_debt_m",
                    "lease_non_current_m",
                    "lease_current_m",
                    "other_financial_non_current_m",
                    "other_financial_current_m",
                    "non_controlling_interest_m",
                ],
                "unit": "SEK_m",
            },
            {
                "id": "net_financing_claims_m",
                "label": "Financing claims net of cash",
                "op": "subtract",
                "args": ["gross_financing_claims_m", "cash_m"],
                "unit": "SEK_m",
            },
            {
                "id": "net_financing_claims_per_share",
                "label": "Net financing claims per share",
                "op": "divide",
                "args": ["net_financing_claims_m", "shares_m"],
                "unit": "SEK_per_share",
            },
            {
                "id": "equity_bridge_per_share",
                "label": "Equity bridge deduction per share",
                "op": "negative",
                "args": ["net_financing_claims_per_share"],
                "unit": "SEK_per_share",
            },
        ],
        "outputs": {
            "low": "equity_bridge_per_share",
            "base": "equity_bridge_per_share",
            "high": "equity_bridge_per_share",
        },
    }


PROOFS = {
    "operating_enterprise": operating_enterprise_proof(),
    "financing_claims": financing_claims_proof(),
}


def _component(component_id: str, proof: dict, evaluation: dict) -> dict:
    operating = component_id == "operating_enterprise"
    outputs = evaluation["outputs"]
    return {
        "id": component_id,
        "label": (
            "Owned operating-company portfolio enterprise value"
            if operating
            else "Cash less bank, lease, acquisition-payment, and minority claims"
        ),
        "category": "operating_business" if operating else "liability_or_reserve",
        "overlap_key": "owned_operating_portfolio" if operating else "net_financing_claims",
        "treatment": "additive",
        "included_in_component_id": None,
        "method": proof["method_id"],
        "valuation_status": "bounded_estimate" if operating else "calculated",
        "calculation_proof": deepcopy(proof),
        "evidence_tier": "primary_derived",
        "evidence": (
            f"{Q2_2026}, pages 15–18 and 24; independently reconciled in {RECONCILIATION}."
            if operating
            else f"{Q2_2026}, pages 16–17 and 21; independently reconciled in {RECONCILIATION}."
        ),
        "cross_check": (
            "R12 enterprise cash flow reconciles from CFO less capex plus after-tax cash financing cost; acquisition cash outlays and benefits from future deals are excluded together."
            if operating
            else "All bank debt, leases, fair-valued acquisition-payment liabilities, cash, and minority interest are included once; unused credit is not an asset."
        ),
        "assumption_summary": (
            "Low/base/high vary starting normalization, existing-portfolio growth, discount rate, and year-7 exit multiple."
            if operating
            else "The latest reported balances are deducted at 100% of carrying value in every case."
        ),
        "falsifier": (
            "R12 cash flow falls below 85% of the 2026-Q2 run rate without a temporary working-capital explanation, organic decline persists, or EBITA margin falls below 9%."
            if operating
            else "Net debt/EBITDA approaches the 2.5x guardrail, acquisition-payment liabilities rise faster than acquired cash earnings, or material dilution is issued below intrinsic value."
        ),
        "scenario_assumptions": None,
        "low_per_share": round(outputs["low"], 2),
        "base_per_share": round(outputs["base"], 2),
        "high_per_share": round(outputs["high"], 2),
    }


def close_authorized_evidence() -> None:
    auth = json.loads(AUTH_PATH.read_text(encoding="utf-8"))
    auth["authorized_at"] = "2026-08-31T16:00:00Z"
    auth["cohort"] = "stock_specific"
    auth["contract_status"] = "decision_grade"
    auth["component_coverage"] = {
        "all_material_components_identified": True,
        "material_component_count": 2,
        "additive_component_count": 2,
        "embedded_component_count": 0,
        "unvalued_component_count": 0,
        "double_counting_flags": [],
    }
    auth["blockers"] = []
    auth["instruction"] = (
        "Primary filing reconciliation complete. Preserve the enterprise/equity basis, "
        "keep future acquisition costs and benefits paired, and require independent "
        "committee review before any human capital decision."
    )
    AUTH_PATH.write_text(json.dumps(auth, indent=2) + "\n", encoding="utf-8")


def write_fact_ledger() -> None:
    """Keep routed-method and falsifier fields current in their durable ledger."""
    rows = [
        ("normalized_owner_earnings_m", 204.9, "SEK millions", "page 18: R12 operating cash flow 213.5 less net capex 8.6 MSEK"),
        ("fcf_ex_acquisitions_m", 204.9, "SEK millions", "page 18: R12 free cash flow excluding acquisitions 204.9 MSEK"),
        ("operating_cash_flow_m", OPERATING_CASH_FLOW_M, "SEK millions", "page 18: R12 cash flow from operating activities 213.5 MSEK"),
        ("cash_m", CASH_M, "SEK millions", "page 16: cash and cash equivalents 171.5 MSEK"),
        ("debt_m", 898.8, "SEK millions", "pages 16 and 21: bank, lease, and other financial liabilities total 898.8 MSEK"),
        ("shares_outstanding", int(SHARES_M * 1_000_000), "shares", "page 17: Q2/YTD diluted and period-end shares 17,165,756"),
        ("net_debt_to_ebitda", 1.7, "times", "page 8: net debt/EBITDA 1.7x at 2026-Q2"),
    ]
    facts = []
    for field_id, value, unit, locator in rows:
        facts.append(
            {
                "field_id": field_id,
                "value": value,
                "unit": unit,
                "source": {
                    "ref": Q2_2026,
                    "locator": locator,
                    "as_of": AS_OF,
                    "filed": "2026-07-18",
                    "fiscal_period": "Q2",
                },
                "confidence": "high",
                "locked": True,
            }
        )
    ledger = {
        "schema_version": "1.0",
        "ticker": "TEQ.ST",
        "as_of": "2026-08-31",
        "facts": facts,
        "source_count": 1,
        "generated_at": "2026-08-31T16:00:00Z",
    }
    LEDGER_PATH.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    import sys

    sys.path.insert(0, str(ROOT / "_system" / "scripts"))
    from calculation_proof import evaluate_calculation_proof

    data = json.loads(VAL_PATH.read_text(encoding="utf-8-sig"))
    data["as_of"] = "2026-08-31"
    data["method"] = "issuer_specific_filing_reconciled"
    data["inputs"].update(
        {
            "fcf_per_share": round((OPERATING_CASH_FLOW_M - CAPEX_M) / SHARES_M, 4),
            "fcf_source": f"R12 operating cash flow {OPERATING_CASH_FLOW_M} MSEK less capex {CAPEX_M} MSEK ({Q2_2026}, page 18)",
            "shares_millions": round(SHARES_M, 6),
            "shares_outstanding": int(SHARES_M * 1_000_000),
            "shares_source": f"Q2/YTD diluted and period-end shares 17,165,756 ({Q2_2026}, page 17)",
            "cash_m": CASH_M,
            "total_debt_m": round(
                BANK_DEBT_M
                + LEASE_NON_CURRENT_M
                + LEASE_CURRENT_M
                + OTHER_FINANCIAL_NON_CURRENT_M
                + OTHER_FINANCIAL_CURRENT_M,
                1,
            ),
            "normalization_note": (
                "R12 owner cash is converted to enterprise cash by adding back after-tax cash financing cost. "
                "Cases never capitalize future acquisition benefits without their purchase cost."
            ),
        }
    )
    data["valuation_methodology"] = {
        "primary_method": "owner_earnings_reinvestment_dcf",
        "method_version": "1.0",
        "automation": "issuer_specific_filing_reconciled_model",
        "model_level": "stock_specific",
        "output_basis": "present_value_today",
        "required_return_pct": 10.5,
        "horizon_years": 7,
        "component_methods": ["owner_earnings_reinvestment_dcf", "net_asset_value"],
        "non_double_counting_rule": (
            "Value the current operating portfolio once on enterprise cash flow; then deduct all financing claims once. "
            "Assign zero to future acquisitions unless both future benefits and funding are modeled together."
        ),
    }

    components = []
    component_outputs = []
    for component_id, proof in PROOFS.items():
        evaluation = evaluate_calculation_proof(proof)
        if evaluation["status"] != "valid":
            raise SystemError(
                f"{component_id} proof invalid: {evaluation['checks']['errors']}"
            )
        components.append(_component(component_id, proof, evaluation))
        component_outputs.append(evaluation["outputs"])
        print(f"{component_id}: {evaluation['outputs']}")
    total_equity_value = {
        case: round(sum(output[case] for output in component_outputs), 4)
        for case in ("low", "base", "high")
    }
    data["component_valuation_results"] = {
        "status": "compiled",
        "all_material_components_identified": True,
        "additive_components": components,
        "embedded_components": [],
        "total_equity_value_per_share": total_equity_value,
    }

    analysis = data.get("economic_value_analysis") or {}
    analysis.update(
        {
            "filing_digest": RECONCILIATION,
            "evidence_citations": [Q2_2026, ANNUAL_2025, RECONCILIATION],
            "last_verified": {
                "deep_dive": "2026-08-31",
                "human_approved": None,
                "valuation_as_of": "2026-08-31",
            },
            "thesis": (
                "Teqnion is a decentralized industrial serial acquirer whose owned portfolio produced "
                "257.3 MSEK of R12 EBITA and 204.9 MSEK of R12 free cash flow excluding acquisition payments at 2026-Q2. "
                "The valuation gives no separate credit for unannounced acquisitions."
            ),
            "why_market_wrong": (
                "The market may extrapolate the record 13.5% R12 EBITA margin and continued M&A. "
                "At 186 SEK, the quote is above the filing-reconciled 140.38 SEK base value and only below the 220.87 SEK high case."
            ),
            "key_assumptions": [
                {"input": "R12 free cash flow excluding acquisitions", "value": "204.9 MSEK", "source": f"{Q2_2026}, page 18"},
                {"input": "Base existing-portfolio growth", "value": "5% years 1–5; 3% years 6–7", "source": "Scenario judgment; future M&A excluded"},
                {"input": "Base discount rate / exit multiple", "value": "10.5% / 14x year-7 FCFF", "source": "Stock-specific risk bounds"},
                {"input": "Net financing claims", "value": "728.7 MSEK", "source": f"{Q2_2026}, pages 16–17 and 21"},
            ],
            "scenarios": {
                "low": {"value_per_share": 38.97, "operating_case": "85% cash normalization, -2% then 0% growth, 13% discount rate, 9x exit"},
                "base": {"value_per_share": 140.38, "operating_case": "95% cash normalization, 5% then 3% growth, 10.5% discount rate, 14x exit"},
                "high": {"value_per_share": 220.87, "operating_case": "100% cash normalization, 8% then 4% growth, 9% discount rate, 16x exit"},
            },
            "open_questions": [
                "Independent committee review remains required before any capital decision.",
                "Track organic sales, EBITA margin, cash conversion, net debt/EBITDA, and acquisition-payment liabilities each quarter.",
            ],
        }
    )
    data["economic_value_analysis"] = analysis
    data["human_review"] = {"live_price_confirmed": False}

    VAL_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    close_authorized_evidence()
    write_fact_ledger()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
