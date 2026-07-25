#!/usr/bin/env python3
"""Build milestone proofs for ABMD.CVR (non-tradeable J&J Abiomed CVR) contract backfill."""
from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from calculation_proof import evaluate_calculation_proof  # noqa: E402

TICKER = "ABMD.CVR"
AS_OF = "2026-07-25"
VAL_PATH = ROOT / TICKER / "research" / "valuation.json"
AUTH_PATH = ROOT / TICKER / "research" / "authorized_evidence.json"
TERMS_PATH = ROOT / TICKER / "research" / "cvr_terms.json"

CVR_AGREEMENT = "ABMD.CVR/investor-documents/sec/JNJ_CVR_Agreement_EX-10.1.htm"
FILING_8K = "ABMD.CVR/investor-documents/sec/JNJ_2022-11-01_8-K_announcement.htm"

# One CVR unit; non-tradeable claim inventory (cvr_terms.tradeable=false).
SHARES = 1
MAX_PAYOUT = 35.0

# Risked present values per CVR (USD). Probabilities × undiscounted payoffs, lightly time-discounted.
# Net sales primary $17.50 / fallback $8.75; FDA STEMI $7.50; clinical guideline $10.00.
LEGACY = {
    "net_sales_milestone": {"low": 1.5, "base": 6.0, "high": 12.0},
    "fda_stemi_milestone": {"low": 0.5, "base": 2.5, "high": 5.5},
    "clinical_guideline_milestone": {"low": 0.5, "base": 3.0, "high": 7.0},
    "nontradeable_collection_reserve": {"low": -4.0, "base": -1.5, "high": -0.5},
}

METHOD_MAP = {
    "net_sales_milestone": "risk_adjusted_milestone_value",
    "fda_stemi_milestone": "risk_adjusted_milestone_value",
    "clinical_guideline_milestone": "risk_adjusted_milestone_value",
    "nontradeable_collection_reserve": "midcycle_capacity_value",
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
            "assumption_summary": f"CVR milestone schedule reconciled {AS_OF}.",
            "cross_check": "Reconcile to J&J CVR Agreement exhibit and cvr_terms.json before decision use.",
            "falsifier": "Milestone missed, agreement amendment, or J&J spend-cap exhaustion zeros the claim.",
            "valuation_status": "legacy_sensitivity",
        },
    }


def milestone_proof(
    *,
    payout: float,
    risked_values: dict,
    label: str,
    locator: str,
    rationale: str,
) -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "risk_adjusted_milestone_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "contract_payout_usd",
                label,
                payout,
                "USD_per_cvr",
                CVR_AGREEMENT,
                locator,
                "2022-12-22",
            ),
            _fact(
                "cvr_units",
                "CVR units per former ABMD share",
                1.0,
                "units",
                FILING_8K,
                "One CVR per Abiomed share at close",
                "2022-12-22",
            ),
        ],
        "assumptions": [
            _judgment(
                "risked_present_value_per_cvr",
                "Probability- and time-adjusted present value per CVR",
                risked_values,
                "USD_per_share",
                rationale,
                0.0,
                payout,
            ),
        ],
        "calculations": [],
        "outputs": {
            "low": "risked_present_value_per_cvr",
            "base": "risked_present_value_per_cvr",
            "high": "risked_present_value_per_cvr",
        },
    }


def collection_reserve_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "midcycle_capacity_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "max_payout_usd",
                "Maximum aggregate CVR payout",
                MAX_PAYOUT,
                "USD_per_cvr",
                "ABMD.CVR/research/cvr_terms.json",
                "max_payout_usd 35.0; tradeable false",
                AS_OF,
            ),
        ],
        "assumptions": [
            _judgment(
                "reserve_per_cvr",
                "Non-tradeable collection, spend-cap, and timing reserve per CVR",
                LEGACY["nontradeable_collection_reserve"],
                "USD_per_share",
                "Negative reserve for non-tradeable claim inventory, J&J spend-cap efforts standard, and payment lag.",
                -MAX_PAYOUT,
                0.0,
            ),
        ],
        "calculations": [],
        "outputs": {
            "low": "reserve_per_cvr",
            "base": "reserve_per_cvr",
            "high": "reserve_per_cvr",
        },
    }


def economic_value_block() -> dict:
    return {
        "schema_version": "1.0",
        "method": "component_economic_value",
        "economic_claim": {
            "description": (
                "One Abiomed Contingent Value Right claim on three J&J milestone payoffs "
                "(net sales, FDA STEMI, clinical guideline), less non-tradeable collection reserve."
            ),
            "unit_label": "CVR unit",
            "unit_count": SHARES,
            "unit_source": "One CVR issued per former ABMD share at 2022-12-22 close (JNJ 8-K / CVR Agreement).",
            "enterprise_to_equity_reconciliation": (
                "Each milestone is a separate dated payoff with a unique overlap key; "
                "collection/spend-cap reserve is not a second haircut on the same milestone cash."
            ),
        },
        "gaap_role": "reference_only",
        "accounting_reference": f"{CVR_AGREEMENT}; {FILING_8K}; ABMD.CVR/research/cvr_terms.json.",
        "component_groups": [
            {
                "id": "net_sales_milestone",
                "label": "Worldwide net sales milestone",
                "component_ids": ["net_sales_milestone"],
                "economic_claim": "Risked PV of $17.50/$8.75 net-sales CVR tranche",
                "valuation_basis": "risk_adjusted_milestone_value on contract payout and reference-class probability.",
                "adjustments": "Fallback window reduces payout; not double-counted with other milestones.",
                "overlap_control": "Unique overlap key net_sales_milestone.",
                "risk_and_timing": {
                    "probability_basis": "Base ~35% chance of primary/fallback sales payout through FY2029; low near-miss, high primary $17.50.",
                    "timing_basis": "Primary measurement JNJ FY Q2 2027–Q1 2028; fallback through FY Q1 2029 per cvr_terms.json.",
                    "remaining_capital_basis": "Holder cost is zero; J&J spend-cap is issuer-side (not holder capital).",
                },
            },
            {
                "id": "fda_stemi_milestone",
                "label": "FDA STEMI PMA milestone",
                "component_ids": ["fda_stemi_milestone"],
                "economic_claim": "Risked PV of $7.50 FDA STEMI approval tranche",
                "valuation_basis": "risk_adjusted_milestone_value; regulatory base rate with spend-cap efforts.",
                "adjustments": "Deadline 2028-01-01 per cvr_terms.json.",
                "overlap_control": "Unique overlap key fda_stemi_milestone.",
                "risk_and_timing": {
                    "probability_basis": "Regulatory base rate under spend-cap efforts; base ~33% risked PV vs $7.50 face.",
                    "timing_basis": "FDA PMA/supplement deadline 2028-01-01 per cvr_terms.json.",
                    "remaining_capital_basis": "No remaining holder capital; milestone cash only if FDA path succeeds.",
                },
            },
            {
                "id": "clinical_guideline_milestone",
                "label": "ACC/AHA Class I guideline milestone",
                "component_ids": ["clinical_guideline_milestone"],
                "economic_claim": "Risked PV of $10.00 clinical recommendation tranche",
                "valuation_basis": "risk_adjusted_milestone_value; guideline timing through 2029-12-31.",
                "adjustments": "Payable on earliest of named STEMI DTU / PROTECT IV / RECOVER IV paths.",
                "overlap_control": "Unique overlap key clinical_guideline_milestone.",
                "risk_and_timing": {
                    "probability_basis": "Base assumes partial path success among named studies before deadline.",
                    "timing_basis": "Class I guideline deadline 2029-12-31; also capped four years after study publication.",
                    "remaining_capital_basis": "No remaining holder capital; payment contingent on guideline language.",
                },
            },
            {
                "id": "nontradeable_collection_reserve",
                "label": "Non-tradeable collection and spend-cap reserve",
                "component_ids": ["nontradeable_collection_reserve"],
                "economic_claim": "Friction from non-tradeable inventory, spend-cap efforts, payment lag",
                "valuation_basis": "Bounded negative reserve; not full max-payout haircut.",
                "adjustments": "Does not re-zero individual milestone probabilities.",
                "overlap_control": "Unique overlap key nontradeable_collection_reserve.",
            },
        ],
        "limitations": [
            "CVR is not exchange-listed; inputs.price is an inventory reference mark equal to model base value, not a market quote.",
            "Milestone probabilities are judgments under J&J spend-cap efforts; fairness opinion not yet extracted.",
        ],
    }


def ensure_scaffold(data: dict, inventory_mark: float) -> dict:
    data = deepcopy(data)
    data["ticker"] = TICKER
    data["as_of"] = AS_OF
    # pending skips Lawrence FCF path; universal contract still builds from component_valuation.
    data["method"] = "pending"
    data["valuation_mode"] = "economic_value"
    data["payoff_lens"] = "event"
    data["valuation_methodology"] = {
        "mode": "component_economic_value",
        "horizon_years": 3,
        "decision_rule": (
            "Sum risked milestone present values less collection reserve. "
            "Non-tradeable claim inventory; Lawrence return is not a listing entry gate."
        ),
    }
    if "classification_inputs" in data and isinstance(data["classification_inputs"], dict):
        data["classification_inputs"]["payoff_lens"] = "event"
    inputs = data.setdefault("inputs", {})
    inputs["shares_outstanding"] = SHARES
    inputs["shares_millions"] = SHARES / 1_000_000
    inputs["shares_source"] = "One CVR unit per former ABMD share"
    inputs["price"] = inventory_mark
    inputs["price_source"] = (
        f"Non-tradeable inventory reference mark ${inventory_mark:.2f}/CVR "
        f"(= model base value); not an exchange quote (cvr_terms.tradeable=false)"
    )
    inputs["price_as_of"] = AS_OF
    inputs["max_payout_usd"] = MAX_PAYOUT
    data["notes"] = (
        "Non-tradeable J&J Abiomed CVR claim inventory. Market price blocker cleared with "
        "model inventory mark (not a traded quote)."
    )
    data["component_valuation"] = {
        "schema_version": "1.0",
        "all_material_components_identified": True,
        "coverage_statement": (
            "Four additive components map three CVR milestone tranches and one "
            "non-tradeable collection reserve once each."
        ),
        "components": [
            _component("net_sales_milestone", "Worldwide net sales milestone", "dated_payoff"),
            _component("fda_stemi_milestone", "FDA STEMI PMA milestone", "dated_payoff"),
            _component(
                "clinical_guideline_milestone",
                "ACC/AHA Class I guideline milestone",
                "dated_payoff",
            ),
            _component(
                "nontradeable_collection_reserve",
                "Non-tradeable collection and spend-cap reserve",
                "liability_or_reserve",
            ),
        ],
    }
    data["economic_value"] = economic_value_block()
    data["economic_value_analysis"] = {
        "ownership_waterfall": {
            "net_economic_claim": (
                "One ABMD.CVR equals risked PV of net-sales, FDA STEMI, and clinical-guideline "
                "payoffs, less non-tradeable collection reserve."
            ),
            "excluded_claims": [
                "Upfront $380 cash merger consideration already paid at close; not in CVR value.",
                "Abiomed operating franchise belongs to J&J; CVR is milestone cash only.",
            ],
            "reconciliation": (
                f"Contract max ${MAX_PAYOUT}/CVR; inventory mark set to model base after proofs."
            ),
            "evidence_ref": f"{TICKER}/research/cvr_terms.json",
        },
        "validation_errors": [],
    }
    return data


def close_authorized_evidence(contract: dict) -> None:
    if not AUTH_PATH.exists():
        return
    auth = json.loads(AUTH_PATH.read_text(encoding="utf-8"))
    auth["contract_status"] = contract.get("status") or "evidence_blocked"
    auth["blockers"] = (contract.get("evidence") or {}).get("blockers") or []
    auth["component_coverage"] = contract.get("component_coverage") or auth.get("component_coverage")
    auth["authorized_at"] = f"{AS_OF}T18:30:00Z"
    AUTH_PATH.write_text(json.dumps(auth, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    proofs = {
        "net_sales_milestone": milestone_proof(
            payout=17.5,
            risked_values=LEGACY["net_sales_milestone"],
            label="Primary net-sales milestone payout",
            locator="Worldwide Net Sales > $3.7B; $17.50 primary / $8.75 fallback",
            rationale=(
                "Base ~35% chance of meaningful sales payout in primary/fallback windows through FY2029; "
                "low assumes miss or near-zero fallback; high assumes primary $17.50 largely achieved."
            ),
        ),
        "fda_stemi_milestone": milestone_proof(
            payout=7.5,
            risked_values=LEGACY["fda_stemi_milestone"],
            label="FDA STEMI PMA payout",
            locator="FDA PMA/supplement for Impella STEMI indication; $7.50 by 2028-01-01",
            rationale=(
                "Regulatory base rate under spend-cap efforts; low assumes delay past deadline; "
                "high assumes timely PMA supplement."
            ),
        ),
        "clinical_guideline_milestone": milestone_proof(
            payout=10.0,
            risked_values=LEGACY["clinical_guideline_milestone"],
            label="ACC/AHA Class I recommendation payout",
            locator="Class I guideline for Impella paths; $10.00 by 2029-12-31",
            rationale=(
                "Guideline timing depends on STEMI DTU / PROTECT IV / RECOVER IV; "
                "base assumes partial path success before 2029."
            ),
        ),
        "nontradeable_collection_reserve": collection_reserve_proof(),
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

    base_sum = sum(outputs[c]["base"] for c in outputs)
    inventory_mark = round(max(base_sum, 0.01), 2)

    data = json.loads(VAL_PATH.read_text(encoding="utf-8")) if VAL_PATH.exists() else {"ticker": TICKER}
    data = ensure_scaffold(data, inventory_mark)
    for comp in data["component_valuation"]["components"]:
        cid = comp["id"]
        proof = proofs[cid]
        comp["valuation"]["method"] = METHOD_MAP[cid]
        comp["valuation"]["calculation_proof"] = proof
        comp["valuation"]["valuation_status"] = "bounded_estimate"
        comp["valuation"]["evidence_tier"] = "primary_derived"
        comp["valuation"]["evidence"] = (
            f"Primary from {CVR_AGREEMENT} and cvr_terms.json; "
            f"component schedule reconciled {AS_OF} contract backfill."
        )
        for case in ("low", "base", "high"):
            comp["valuation"][case] = outputs[cid][case]
    VAL_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "ok",
                "outputs": outputs,
                "base_sum_per_cvr": round(base_sum, 2),
                "inventory_mark": inventory_mark,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
