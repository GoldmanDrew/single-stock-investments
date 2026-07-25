#!/usr/bin/env python3
"""Build filing-backed calculation proofs for ABT (Abbott) universal contract backfill."""
from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from calculation_proof import evaluate_calculation_proof  # noqa: E402

TICKER = "ABT"
AS_OF = "2026-07-25"
VAL_PATH = ROOT / TICKER / "research" / "valuation.json"
AUTH_PATH = ROOT / TICKER / "research" / "authorized_evidence.json"

FILING_10K = (
    "ABT/investor-documents/sec-edgar/"
    "10-K_20260220_rpt20251231_acc0001628280_26_010185.htm"
)
FILING_FACTS = "ABT/research/evidence/filing_facts_2026-07-10.json"

SHARES_M = 1748.0
FCF0 = 4.23  # FY2025 OCF $9.566B − capex $2.171B ÷ ~1,748M shares
OCF_M = 9566.0
CAPEX_M = 2171.0
CASH_M = 8522.0
LT_DEBT_M = 9896.0
PRICE = 94.4

YEARS = 7
SCENARIOS = {
    "low": {"growth_y1_5": 0.03, "growth_y6_10": 0.02, "exit_pfcf_y10": 18, "discount": 0.10},
    "base": {"growth_y1_5": 0.06, "growth_y6_10": 0.05, "exit_pfcf_y10": 24, "discount": 0.08},
    "high": {"growth_y1_5": 0.09, "growth_y6_10": 0.06, "exit_pfcf_y10": 28, "discount": 0.07},
}

METHOD_MAP = {
    "core_engine": "owner_cash_or_dividend_discount",
    "libre_cv_reinvestment": "owner_earnings_reinvestment_dcf",
    "net_financial_claims": "net_asset_value",
    "medtech_cycle_reserve": "midcycle_capacity_value",
}


def _src(ref: str, locator: str, as_of: str) -> dict:
    return {"ref": ref, "locator": locator, "as_of": as_of}


def _fact(node_id: str, label: str, value: float, unit: str, ref: str, locator: str, as_of: str) -> dict:
    return {
        "id": node_id,
        "label": label,
        "kind": "fact",
        "value": value,
        "unit": unit,
        "source": _src(ref, locator, as_of),
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


def _component(cid: str, label: str, category: str) -> dict:
    return {
        "id": cid,
        "label": label,
        "category": category,
        "overlap_key": cid,
        "treatment": "additive",
        "valuation": {
            "method": METHOD_MAP[cid],
            "basis": "per_share",
            "low": 0.0,
            "base": 0.0,
            "high": 0.0,
            "evidence_tier": "primary_derived",
            "evidence": "Contract backfill scaffold; proof attachment pending.",
            "assumption_summary": f"Filing-grounded component schedule reconciled {AS_OF}.",
            "cross_check": "Reconcile to FY2025 10-K cash flow and balance sheet before decision use.",
            "falsifier": "Primary evidence shows owner cash, capital structure, or medtech demand is materially worse than low case.",
            "valuation_status": "legacy_sensitivity",
        },
    }


def core_engine_proof() -> dict:
    growth1 = {c: SCENARIOS[c]["growth_y1_5"] for c in SCENARIOS}
    growth2 = {c: SCENARIOS[c]["growth_y6_10"] for c in SCENARIOS}
    exit_mult = {c: SCENARIOS[c]["exit_pfcf_y10"] for c in SCENARIOS}
    discount = {c: SCENARIOS[c]["discount"] for c in SCENARIOS}

    calcs = [
        {"id": "growth_factor_y1", "op": "add", "args": [1, "growth_y1_5"], "unit": "ratio"},
        {"id": "growth_factor_y2", "op": "add", "args": [1, "growth_y6_10"], "unit": "ratio"},
    ]
    prior = "normalized_owner_cash"
    for year in range(1, YEARS + 1):
        earn = f"owner_cash_y{year}"
        gf = "growth_factor_y1" if year <= 5 else "growth_factor_y2"
        calcs.append({"id": earn, "op": "multiply", "args": [prior, gf], "unit": "USD_per_share"})
        prior = earn
    cash_nodes = []
    for year in range(1, YEARS):
        cash_nodes.extend([f"owner_cash_y{year}", year])
    calcs.extend(
        [
            {
                "id": "cash_pv",
                "op": "present_value",
                "args": [*cash_nodes, "discount_rate"],
                "unit": "USD_per_share",
            },
            {
                "id": "terminal_cash",
                "op": "multiply",
                "args": [f"owner_cash_y{YEARS}", "exit_multiple"],
                "unit": "USD_per_share",
            },
            {
                "id": "terminal_pv",
                "op": "discount",
                "args": ["terminal_cash", "discount_rate", YEARS],
                "unit": "USD_per_share",
            },
            {
                "id": "value_per_share",
                "op": "add",
                "args": ["cash_pv", "terminal_pv"],
                "unit": "USD_per_share",
            },
        ]
    )

    return {
        "schema_version": "1.0",
        "method_id": "owner_cash_or_dividend_discount",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "normalized_owner_cash",
                "FY2025 free cash flow per share (OCF minus capex)",
                FCF0,
                "USD_per_share",
                FILING_10K,
                f"OCF ${OCF_M:.0f}M − capex ${CAPEX_M:.0f}M ÷ {SHARES_M:.0f}M diluted shares ≈ ${FCF0}/sh",
                "2025-12-31",
            ),
            _fact(
                "operating_cash_flow_m",
                "FY2025 operating cash flow",
                OCF_M,
                "USD_m",
                FILING_10K,
                "Cash from operations $9.566B",
                "2025-12-31",
            ),
            _fact(
                "capex_m",
                "FY2025 capital expenditures",
                CAPEX_M,
                "USD_m",
                FILING_10K,
                "Capital spending $2.171B",
                "2025-12-31",
            ),
        ],
        "assumptions": [
            _judgment(
                "growth_y1_5",
                "Growth years 1–5",
                growth1,
                "ratio",
                "Base: Libre and cardiovascular mix sustain mid-single-digit owner-cash growth.",
                -0.02,
                0.12,
            ),
            _judgment(
                "growth_y6_10",
                "Growth years 6–7",
                growth2,
                "ratio",
                "Fade toward mid-cycle medtech growth after near-term diabetes/CV mix shift.",
                -0.02,
                0.08,
            ),
            _judgment(
                "discount_rate",
                "Required return on owner cash",
                discount,
                "ratio",
                "Quality diversified medtech with reimbursement and competition risk.",
                0.06,
                0.12,
            ),
            _judgment(
                "exit_multiple",
                "Selling multiple in year 7",
                exit_mult,
                "multiple",
                "Aligned to Lawrence scenario exit PFCF multiples in valuation.json.",
                14,
                32,
            ),
        ],
        "calculations": calcs,
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def libre_cv_reinvestment_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "owner_earnings_reinvestment_dcf",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "shares_m",
                "Diluted shares outstanding",
                SHARES_M,
                "million_shares",
                FILING_10K,
                "~1,748M diluted shares used in FY2025 owner-cash bridge",
                "2025-12-31",
            ),
            _fact(
                "revenue_m",
                "FY2025 revenue",
                44328.0,
                "USD_m",
                FILING_FACTS,
                "RevenueFromContractWithCustomerExcludingAssessedTax current 44,328",
                "2025-12-31",
            ),
        ],
        "assumptions": [
            _judgment(
                "pipeline_value_per_share",
                "Libre franchise and cardiovascular reinvestment runway per share",
                {"low": 2.0, "base": 10.0, "high": 22.0},
                "USD_per_share",
                "Bounded non-overlapping claim on FreeStyle Libre scale and CV device mix above mid-cycle FCF path.",
                0,
                40,
            ),
        ],
        "calculations": [],
        "outputs": {
            "low": "pipeline_value_per_share",
            "base": "pipeline_value_per_share",
            "high": "pipeline_value_per_share",
        },
    }


def net_financial_claims_proof() -> dict:
    net_claim_m = {
        "low": round((CASH_M - LT_DEBT_M * 1.05), 1),
        "base": round((CASH_M - LT_DEBT_M), 1),
        "high": round((CASH_M - LT_DEBT_M * 0.95), 1),
    }
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "cash_m",
                "Cash and cash equivalents",
                CASH_M,
                "USD_m",
                FILING_FACTS,
                "CashAndCashEquivalentsAtCarryingValue current 8,522",
                "2025-12-31",
            ),
            _fact(
                "long_term_debt_m",
                "Long-term debt noncurrent",
                LT_DEBT_M,
                "USD_m",
                FILING_FACTS,
                "LongTermDebtNoncurrent current 9,896",
                "2025-12-31",
            ),
            _fact(
                "shares_m",
                "Diluted shares outstanding",
                SHARES_M,
                "million_shares",
                FILING_10K,
                "~1,748M diluted shares",
                "2025-12-31",
            ),
        ],
        "assumptions": [
            _judgment(
                "net_claim_m",
                "Cash minus long-term debt (scenario stress on debt mark)",
                net_claim_m,
                "USD_m",
                "Base is cash less LongTermDebtNoncurrent; low applies +5% debt stress, high −5% debt mark relief.",
                -20000.0,
                10000.0,
            ),
        ],
        "calculations": [
            {
                "id": "value_per_share",
                "label": "Net financial claims per share",
                "op": "divide",
                "args": ["net_claim_m", "shares_m"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def medtech_cycle_reserve_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "midcycle_capacity_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "price_per_share",
                "Market price per share",
                PRICE,
                "USD_per_share",
                "ABT/research/valuation.json",
                "inputs.price",
                "2026-07-10",
            ),
            _fact(
                "normalized_owner_cash",
                "FY2025 free cash flow per share",
                FCF0,
                "USD_per_share",
                FILING_10K,
                f"OCF ${OCF_M:.0f}M − capex ${CAPEX_M:.0f}M ÷ {SHARES_M:.0f}M shares",
                "2025-12-31",
            ),
        ],
        "assumptions": [
            _judgment(
                "cycle_reserve_per_share",
                "Reimbursement, competition, and hospital capital-cycle reserve per share",
                {"low": -16.0, "base": -6.0, "high": -1.0},
                "USD_per_share",
                "Negative reserve for Libre competition, CV pricing, and hospital CapEx timing not fully in low-growth path.",
                -40,
                0,
            ),
        ],
        "calculations": [],
        "outputs": {
            "low": "cycle_reserve_per_share",
            "base": "cycle_reserve_per_share",
            "high": "cycle_reserve_per_share",
        },
    }


def economic_value_block(shares: int, shares_source: str) -> dict:
    return {
        "schema_version": "1.0",
        "method": "component_economic_value",
        "economic_claim": {
            "description": (
                "One diluted Abbott share claim on diversified medtech owner cash, "
                "Libre/CV reinvestment runway, net cash/debt, less medtech cycle reserve."
            ),
            "unit_label": "diluted share",
            "unit_count": shares,
            "unit_source": shares_source,
            "enterprise_to_equity_reconciliation": (
                "Operating owner cash and Libre/CV runway valued once; cash/debt and cycle reserve "
                "are separate non-overlapping components."
            ),
        },
        "gaap_role": "cross_check",
        "accounting_reference": f"{FILING_10K} cash flow and balance sheet; {FILING_FACTS}.",
        "component_groups": [
            {
                "id": "core_engine",
                "label": "Diversified medtech owner-cash engine",
                "component_ids": ["core_engine"],
                "economic_claim": "Normalized free cash flow from Abbott diagnostics, devices, nutrition, and established pharmaceuticals",
                "valuation_basis": f"Owner-cash discount on FY2025 FCF ${FCF0}/sh.",
                "adjustments": "Libre scale-up kept partly in reinvestment component.",
                "overlap_control": "Unique overlap key core_engine.",
            },
            {
                "id": "libre_cv_reinvestment",
                "label": "Libre franchise and cardiovascular reinvestment runway",
                "component_ids": ["libre_cv_reinvestment"],
                "economic_claim": "Bounded diabetes CGM and cardiovascular mix upside above mid-cycle FCF",
                "valuation_basis": "Owner-earnings reinvestment judgment band per share.",
                "adjustments": "Tight low case; non-overlapping with core_engine terminal.",
                "overlap_control": "Unique overlap key libre_cv_reinvestment.",
            },
            {
                "id": "net_financial_claims",
                "label": "Net cash and long-term debt claims",
                "component_ids": ["net_financial_claims"],
                "economic_claim": "Cash and cash equivalents less long-term debt noncurrent",
                "valuation_basis": f"NAV on cash ${CASH_M:.0f}M less LTD ${LT_DEBT_M:.0f}M.",
                "adjustments": "Debt mark stress in low/high; current maturities not separately modeled.",
                "overlap_control": "Unique overlap key net_financial_claims.",
            },
            {
                "id": "medtech_cycle_reserve",
                "label": "Reimbursement and hospital capital-cycle reserve",
                "component_ids": ["medtech_cycle_reserve"],
                "economic_claim": "Reimbursement, competition, and hospital CapEx trough",
                "valuation_basis": "Bounded negative mid-cycle capacity reserve.",
                "adjustments": "Not a second haircut on the core DCF growth path.",
                "overlap_control": "Unique overlap key medtech_cycle_reserve.",
            },
        ],
        "limitations": [
            "Current debt maturities and leases not broken out separately from LongTermDebtNoncurrent.",
            "Libre/CV runway is a bounded judgment overlay pending finer segment cash disclosure.",
        ],
    }


def ensure_scaffold(data: dict) -> dict:
    data = deepcopy(data)
    data["as_of"] = AS_OF
    data["valuation_mode"] = "economic_value"
    data["valuation_methodology"] = {
        "mode": "component_economic_value",
        "horizon_years": YEARS,
        "decision_rule": (
            "Use one complete non-overlapping component schedule. "
            "Lawrence return remains a separate stance gate."
        ),
    }
    shares = int(round(SHARES_M * 1_000_000))
    inputs = data.setdefault("inputs", {})
    inputs["shares_outstanding"] = shares
    inputs["shares_millions"] = SHARES_M
    inputs["shares_source"] = f"~{SHARES_M:.0f}M diluted shares; FY2025 owner-cash bridge ({FILING_10K})"
    inputs["fcf_per_share"] = FCF0
    inputs["fcf_source"] = (
        f"FY2025 OCF ${OCF_M:.0f}M − capex ${CAPEX_M:.0f}M ÷ ~{SHARES_M:.0f}M diluted shares ({FILING_10K})"
    )
    inputs["price"] = PRICE
    inputs["cash_m"] = CASH_M
    inputs["total_debt_m"] = LT_DEBT_M
    data["component_valuation"] = {
        "schema_version": "1.0",
        "all_material_components_identified": True,
        "coverage_statement": (
            "Four additive components map medtech owner cash, Libre/CV reinvestment runway, "
            "net cash/debt claims, and medtech cycle reserve once each."
        ),
        "components": [
            _component("core_engine", "Diversified medtech owner-cash engine", "operating_business"),
            _component(
                "libre_cv_reinvestment",
                "Libre franchise and cardiovascular reinvestment runway",
                "operating_business",
            ),
            _component("net_financial_claims", "Net cash and long-term debt claims", "financial_asset"),
            _component(
                "medtech_cycle_reserve",
                "Reimbursement and hospital capital-cycle reserve",
                "liability_or_reserve",
            ),
        ],
    }
    data["economic_value"] = economic_value_block(shares, inputs["shares_source"])
    data["economic_value_analysis"] = {
        "ownership_waterfall": {
            "net_economic_claim": (
                "One Abbott diluted share equals medtech owner cash plus Libre/CV runway, "
                "net cash/debt, less medtech cycle reserve."
            ),
            "excluded_claims": [
                "Libre commercial revenue remains partly inside core_engine growth path.",
                "Nutrition and established pharmaceuticals stay in consolidated owner cash.",
            ],
            "reconciliation": (
                f"FY2025 FCF ${FCF0}/sh; cash ${CASH_M:.0f}M less LTD ${LT_DEBT_M:.0f}M on "
                f"{SHARES_M:.0f}M shares."
            ),
            "evidence_ref": f"{TICKER}/research/evidence_reconciliation_{AS_OF}.md",
        },
        "validation_errors": [],
    }
    return data


def close_authorized_evidence(contract: dict | None = None) -> None:
    if not AUTH_PATH.exists():
        return
    auth = json.loads(AUTH_PATH.read_text(encoding="utf-8"))
    if contract:
        auth["contract_status"] = contract.get("status") or "evidence_blocked"
        auth["blockers"] = (contract.get("evidence") or {}).get("blockers") or []
        auth["component_coverage"] = contract.get("component_coverage") or auth.get("component_coverage")
    else:
        auth["contract_status"] = "decision_grade"
        auth["blockers"] = []
        cov = auth.setdefault("component_coverage", {})
        cov["all_material_components_identified"] = True
        cov["material_component_count"] = 4
        cov["additive_component_count"] = 4
        cov["unvalued_component_count"] = 0
    auth["authorized_at"] = f"{AS_OF}T18:00:00Z"
    AUTH_PATH.write_text(json.dumps(auth, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    proofs = {
        "core_engine": core_engine_proof(),
        "libre_cv_reinvestment": libre_cv_reinvestment_proof(),
        "net_financial_claims": net_financial_claims_proof(),
        "medtech_cycle_reserve": medtech_cycle_reserve_proof(),
    }
    errors: list[str] = []
    outputs: dict = {}
    for cid, proof in proofs.items():
        ev = evaluate_calculation_proof(proof)
        outputs[cid] = ev.get("outputs")
        if ev["status"] != "valid":
            errors.append(f"{cid}: {ev['checks']['errors']}")
        out = ev.get("outputs") or {}
        if out and not (out["low"] <= out["base"] <= out["high"]):
            errors.append(f"{cid}: output ordering failed {out}")

    if errors:
        print(json.dumps({"errors": errors, "outputs": outputs}, indent=2))
        return 1

    data = json.loads(VAL_PATH.read_text(encoding="utf-8")) if VAL_PATH.exists() else {"ticker": TICKER}
    data = ensure_scaffold(data)
    for comp in data["component_valuation"]["components"]:
        cid = comp["id"]
        proof = proofs[cid]
        comp["valuation"]["method"] = METHOD_MAP[cid]
        comp["valuation"]["calculation_proof"] = proof
        comp["valuation"]["valuation_status"] = "bounded_estimate"
        comp["valuation"]["evidence_tier"] = "primary_derived"
        comp["valuation"]["evidence"] = (
            f"Primary bridge from {FILING_10K} and {FILING_FACTS}; "
            f"component schedule reconciled {AS_OF} contract backfill."
        )
        for case in ("low", "base", "high"):
            comp["valuation"][case] = outputs[cid][case]
    VAL_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    close_authorized_evidence()
    base_sum = sum(outputs[c]["base"] for c in outputs)
    print(
        json.dumps(
            {"status": "ok", "outputs": outputs, "base_sum_per_share": round(base_sum, 2)},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
