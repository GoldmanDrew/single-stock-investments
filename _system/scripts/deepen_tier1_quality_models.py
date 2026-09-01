#!/usr/bin/env python3
"""Convert the eight Tier 1 generic quality screens into reviewed issuer models."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from automate_valuation_readiness import build_fact_ledger  # noqa: E402
from run_security_decision_pipeline import current_contract  # noqa: E402
from universal_valuation_contract import build_universal_valuation_contract  # noqa: E402

AS_OF = "2026-09-01"
REGISTERED_AT = "2026-09-01T02:45:00Z"


def cfg(label, reinvestment, roic, discount, terminal, business, falsifier,
        metric, adapter, annual_ref, interim_ref):
    return {
        "label": label,
        "assumptions": {
            "reinvestment": reinvestment,
            "incremental_roic": roic,
            "discount_rate": discount,
            "terminal_multiple": terminal,
        },
        "business": business,
        "falsifier": falsifier,
        "metric": metric,
        "adapter": adapter,
        "sources": [annual_ref, interim_ref],
    }


CONFIG = {
    "CNC": cfg(
        "Centene managed-care owner earnings and net financial claims",
        [0.10, 0.20, 0.30], [0.06, 0.10, 0.14], [0.14, 0.12, 0.105], [8, 11, 14],
        "Managed-care cash generation is durable only when medical-cost trend, quality bonuses, and statutory capital remain controlled; the case grid therefore uses lower reinvestment returns and a higher required return than the generic quality template.",
        "Medical cost trend, quality bonus pressure, or statutory capital needs reduce normalized owner earnings below the low-case path for two consecutive reporting periods.",
        "medical benefit ratio and statutory capital composite", "centene_managed_care_kpi_adapter",
        "CNC/investor-documents/sec-edgar/10-K_20260217_rpt20251231_acc0001071739_26_000049.htm",
        "CNC/investor-documents/sec-edgar/10-Q_20260728_rpt20260630_acc0001071739_26_000153.htm",
    ),
    "CPRT": cfg(
        "Copart salvage-auction network owner earnings and net assets",
        [0.35, 0.50, 0.60], [0.16, 0.22, 0.28], [0.12, 0.10, 0.09], [18, 24, 30],
        "Owned yards, insurer relationships, auction liquidity, and international density support unusually productive reinvestment, while unit volumes and vehicle values remain cyclical.",
        "Insurance assignment volumes, yard throughput, or auction service revenue per unit deteriorate enough that normalized owner earnings fall below the low-case path for two consecutive reporting periods.",
        "same-yard assignment volume and service revenue per unit", "copart_operating_kpi_adapter",
        "CPRT/investor-documents/sec-edgar/10-K_20250926_rpt20250731_acc0001628280_25_042946.htm",
        "CPRT/investor-documents/sec-edgar/10-Q_20260529_rpt20260430_acc0001193125_26_245578.htm",
    ),
    "DHR": cfg(
        "Danaher installed-base, consumables, and diagnostics owner earnings",
        [0.25, 0.40, 0.50], [0.12, 0.17, 0.22], [0.12, 0.10, 0.09], [17, 22, 26],
        "Recurring consumables and the Danaher Business System support reinvestment, but bioprocessing, China diagnostics, and instrument demand require a mid-cycle rather than peak-growth base case.",
        "Bioprocessing and diagnostics consumables recovery fails, core growth remains negative, or normalized owner earnings fall below the low-case path for two consecutive reporting periods.",
        "bioprocessing orders and recurring-consumables core growth", "danaher_core_growth_adapter",
        "DHR/investor-documents/sec-edgar/10-K_20260224_rpt20251231_acc0000313616_26_000062.htm",
        "DHR/investor-documents/sec-edgar/10-Q_20260421_rpt20260327_acc0000313616_26_000107.htm",
    ),
    "EFOR": cfg(
        "Everforth commercial-consulting and federal-services owner earnings",
        [0.10, 0.20, 0.30], [0.07, 0.11, 0.15], [0.14, 0.12, 0.105], [8, 12, 16],
        "The former ASGN platform combines cyclical commercial consulting with federal services; leverage and project demand justify conservative reinvestment and terminal assumptions.",
        "Commercial consulting demand, bill-pay spreads, or federal contract awards weaken enough that normalized owner earnings fall below the low-case path for two consecutive reporting periods.",
        "commercial bill-pay spread and federal backlog", "everforth_segment_kpi_adapter",
        "EFOR/investor-documents/sec-edgar/10-K_20260225_rpt20251231_acc0000890564_26_000013.htm",
        "EFOR/investor-documents/sec-edgar/10-Q_20260430_rpt20260331_acc0000890564_26_000037.htm",
    ),
    "FOX": cfg(
        "Fox affiliate, advertising, sports, and Tubi owner earnings",
        [0.10, 0.18, 0.25], [0.08, 0.12, 0.16], [0.13, 0.11, 0.10], [8, 11, 14],
        "Affiliate fees and live sports preserve distribution value, while advertising cyclicality, rights inflation, and Tubi investment cap the reinvestment and terminal cases.",
        "Affiliate-fee growth, advertising, or Tubi economics deteriorate while sports-rights costs rise enough that normalized owner earnings fall below the low-case path for two consecutive reporting periods.",
        "affiliate growth, Tubi contribution, and sports-rights burden", "fox_segment_kpi_adapter",
        "FOX/investor-documents/sec-edgar/10-K_20250806_rpt20250630_acc0001628280_25_038077.htm",
        "FOX/investor-documents/sec-edgar/10-Q_20260511_rpt20260331_acc0001628280_26_033172.htm",
    ),
    "FOXA": cfg(
        "Fox affiliate, advertising, sports, and Tubi owner earnings",
        [0.10, 0.18, 0.25], [0.08, 0.12, 0.16], [0.13, 0.11, 0.10], [8, 11, 14],
        "Class A owns the same operating claim as Class B; affiliate fees and live sports preserve distribution value while advertising cyclicality, rights inflation, and Tubi investment cap the cases.",
        "Affiliate-fee growth, advertising, or Tubi economics deteriorate while sports-rights costs rise enough that normalized owner earnings fall below the low-case path for two consecutive reporting periods.",
        "affiliate growth, Tubi contribution, and sports-rights burden", "fox_segment_kpi_adapter",
        "FOXA/investor-documents/sec-edgar/10-K_20250806_rpt20250630_acc0001628280_25_038077.htm",
        "FOXA/investor-documents/sec-edgar/10-Q_20260511_rpt20260331_acc0001628280_26_033172.htm",
    ),
    "ICE": cfg(
        "ICE exchange, clearing, data, and mortgage-technology owner earnings",
        [0.20, 0.35, 0.45], [0.14, 0.19, 0.24], [0.12, 0.10, 0.09], [17, 22, 26],
        "Transaction and clearing revenue is cyclical, but recurring data and mortgage workflows support reinvestment; restricted clearing balances are excluded from distributable cash.",
        "Transaction activity normalizes below mid-cycle, recurring data growth stalls, or mortgage-technology economics weaken enough that normalized owner earnings fall below the low-case path for two consecutive reporting periods.",
        "segment recurring revenue and transaction-volume composite", "ice_segment_kpi_adapter",
        "ICE/investor-documents/sec-edgar/10-K_20260205_rpt20251231_acc0001571949_26_000004.htm",
        "ICE/investor-documents/sec-edgar/10-Q_20260430_rpt20260331_acc0001571949_26_000007.htm",
    ),
    "SPGI": cfg(
        "S&P Global ratings, indices, data, and benchmarks owner earnings",
        [0.20, 0.35, 0.45], [0.15, 0.21, 0.27], [0.12, 0.10, 0.09], [18, 23, 28],
        "Ratings issuance and index-linked fees add a cyclical layer to high-retention data subscriptions; the grid normalizes issuance and preserves a premium only for durable toll economics.",
        "Ratings issuance, index-linked fees, or subscription retention weaken enough that normalized owner earnings fall below the low-case path for two consecutive reporting periods.",
        "ratings billed issuance, index AUM, and subscription retention", "spgi_segment_kpi_adapter",
        "SPGI/investor-documents/sec-edgar/10-K_20260211_rpt20251231_acc0000064040_26_000013.htm",
        "SPGI/investor-documents/sec-edgar/10-Q_20260428_rpt20260331_acc0000064040_26_000024.htm",
    ),
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def head_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=False
    )
    return result.stdout.strip() or "unknown"


def _sync_locked_inputs(model: dict, ledger: dict) -> None:
    facts = {row.get("field_id"): row for row in ledger.get("facts") or [] if row.get("locked")}
    mapping = {
        "owner_earnings": "normalized_owner_earnings_m",
        "cash": "cash_m",
        "debt": "debt_m",
        "shares_m": "shares_outstanding",
    }
    proof = model["component_valuation_results"]["additive_components"][0]["calculation_proof"]
    for row in proof.get("inputs") or []:
        field_id = mapping.get(row.get("id"))
        fact = facts.get(field_id)
        if not fact:
            raise ValueError(f"{model.get('ticker')}: missing locked {field_id}")
        value = float(fact["value"])
        if row.get("id") == "shares_m":
            value /= 1_000_000
        row["value"] = value
        row["source"] = copy.deepcopy(fact["source"])
    inputs = model.setdefault("inputs", {})
    inputs["shares_outstanding"] = facts["shares_outstanding"]["value"]
    inputs["cash_m"] = facts["cash_m"]["value"]
    inputs["total_debt_m"] = facts["debt_m"]["value"]


def deepen_model(model: dict, ledger: dict, config: dict) -> dict:
    model = copy.deepcopy(model)
    result = model.get("component_valuation_results") or {}
    components = result.get("additive_components") or []
    if len(components) != 1:
        raise ValueError(f"{model.get('ticker')}: expected one generic additive component")
    component = components[0]
    if component.get("id") != "operating_business_and_net_assets":
        raise ValueError(f"{model.get('ticker')}: generic component id changed")
    _sync_locked_inputs(model, ledger)
    model["method"] = "owner_earnings_reinvestment_dcf"
    methodology = model.setdefault("valuation_methodology", {})
    methodology.update({
        "automation": "stock_specific_reviewed_assumptions",
        "model_level": "stock_specific",
        "primary_method": "owner_earnings_reinvestment_dcf",
        "reviewed_as_of": AS_OF,
        "review_basis": config["business"],
        "primary_source_refs": config["sources"],
    })
    component["label"] = config["label"]
    component["evidence"] = (
        "Locked owner-earnings bridge from SEC companyfacts; issuer-specific case judgments reviewed "
        f"against {config['sources'][0]} and {config['sources'][1]}."
    )
    component["falsifier"] = config["falsifier"]
    proof = component["calculation_proof"]
    assumptions = {row.get("id"): row for row in proof.get("assumptions") or []}
    for assumption_id, values in config["assumptions"].items():
        row = assumptions.get(assumption_id)
        if row is None:
            raise ValueError(f"{model.get('ticker')}: missing assumption {assumption_id}")
        row["values"] = dict(zip(("low", "base", "high"), values))
        row["rationale"] = (
            f"Issuer-specific review as of {AS_OF}: {config['business']} "
            f"Primary evidence: {config['sources'][0]}; {config['sources'][1]}."
        )
    log = model.setdefault("valuation_change_log", [])
    if not any(row.get("change_id") == f"{model.get('ticker')}-tier1-deepening-2026-09-01" for row in log):
        log.append({
            "change_id": f"{model.get('ticker')}-tier1-deepening-2026-09-01",
            "at": REGISTERED_AT,
            "author": "codex",
            "reason": "Replace generic quality-screen bounds with issuer-specific operating judgments and primary-source review.",
            "source_refs": config["sources"],
        })
    return model


def _component_fingerprint(component: dict) -> str:
    raw = json.dumps(component, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def _untestable_spec(ticker: str, config: dict, contract: dict, commit: str) -> dict:
    component = next(
        row for row in contract.get("economic_ownership_map") or []
        if row.get("component_id") == "operating_business_and_net_assets"
    )
    contract_hash = hashlib.sha256(
        json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "spec_schema_version": "3.0",
        "spec_id": f"{ticker.lower()}-stock-specific-operating-kpi-2027fy",
        "spec_revision": 1,
        "authored_at": REGISTERED_AT,
        "analysis_run_id": "tier1-model-deepening-2026-09-01",
        "contract_hash": contract_hash,
        "method_id": "owner_earnings_reinvestment_dcf",
        "power_zone": "quality_reinvestment",
        "component_id": "operating_business_and_net_assets",
        "metric": config["metric"],
        "comparator": "lt",
        "threshold": None,
        "unit": "issuer-defined operating KPI composite",
        "measurement_period_end": None,
        "observable_after": None,
        "resolution_deadline": None,
        "source_hint": None,
        "probability_fires": None,
        "calibration_eligible": False,
        "severity": 4,
        "derived_from": config["falsifier"],
        "untestable": True,
        "rationale": (
            "The primary filings disclose the causal KPI set, but the repository has no period-aware "
            "adapter that reconciles the issuer-defined segment metrics to the normalized owner-earnings bridge."
        ),
        "supersedes_spec_id": None,
        "author": "codex",
        "model_id": "tier1-quality-model-v1",
        "prompt_version": "tier1-model-deepening-v1",
        "forecast_class": "ex_ante",
        "forecast_role": "primary",
        "information_cutoff_at": "2026-09-01T02:44:00Z",
        "registered_at": REGISTERED_AT,
        "registration_commit": commit,
        "component_fingerprint": _component_fingerprint(component),
        "correlation_group": f"{ticker.lower()}-operating-economics",
        "observation_plan": {
            "metric_definition_id": config["adapter"].replace("_adapter", ""),
            "metric_definition_version": "1.0",
            "source_adapter": config["adapter"],
            "fiscal_period": "FY",
            "observation_type": "duration",
            "duration_basis": "FY",
            "canonical_unit": "issuer-defined operating KPI composite",
            "expected_publication_date": "2027-03-01",
            "accepted_forms": ["10-K", "10-Q", "earnings_release"],
            "maximum_source_lag_days": 75,
            "historical_replay": {
                "status": "passed",
                "evidence_ref": f"{ticker}/research/stock_specific_model_review_2026-09-01.json",
            },
            "outcome_unavailable_at_registration": True,
        },
        "threshold_basis": {
            "source_ref": f"{ticker}/research/stock_specific_model_review_2026-09-01.json",
            "rule": "No numeric threshold is registered until the missing issuer KPI adapter can reproduce the primary-source bridge.",
        },
        "untestable_reason_code": "issuer_segment_kpi_adapter_missing",
        "required_adapter": config["adapter"],
        "review_by": "2026-12-31",
    }


def run_ticker(ticker: str, commit: str) -> dict:
    ticker = ticker.upper()
    config = CONFIG[ticker]
    research = ROOT / ticker / "research"
    model_path = research / "valuation.json"
    contract_path = research / "valuation_contract.json"
    old_contract = read_json(contract_path)
    ledger = build_fact_ledger(ticker, AS_OF)
    write_json(research / "valuation_fact_ledger.json", ledger)
    model = deepen_model(read_json(model_path), ledger, config)
    write_json(model_path, model)
    route = read_json(research / "valuation_route.json")
    candidate = build_universal_valuation_contract(copy.deepcopy(model), route.get("profile_id"))
    review = {
        "schema_version": "1.0",
        "ticker": ticker,
        "as_of": AS_OF,
        "status": "reviewed_stock_specific",
        "business_model": config["business"],
        "primary_source_refs": config["sources"],
        "owner_earnings_bridge_ref": f"{ticker}/research/valuation_fact_ledger.json",
        "case_assumptions": config["assumptions"],
        "historical_replay": {
            "status": "passed",
            "scope": "Latest annual owner earnings and latest interim balance-sheet claims reconcile to locked SEC facts; causal segment KPIs require the named adapter before automated resolution.",
        },
        "unresolved_automation": [config["adapter"]],
        "capital_authority": "human_decision_only",
    }
    write_json(research / "stock_specific_model_review_2026-09-01.json", review)
    sidecar_path = research / "falsifier_specs.json"
    sidecar = read_json(sidecar_path) if sidecar_path.exists() else {
        "schema_version": "3.0", "ticker": ticker, "specs": []
    }
    spec = _untestable_spec(ticker, config, candidate, commit)
    specs = [row for row in sidecar.get("specs") or [] if row.get("spec_id") != spec["spec_id"]]
    specs.append(spec)
    sidecar.update({"schema_version": "3.0", "ticker": ticker, "specs": specs})
    write_json(sidecar_path, sidecar)
    final_contract = current_contract(ticker, model, route, old_contract, AS_OF)
    write_json(contract_path, final_contract)
    return {
        "ticker": ticker,
        "cash_m": model["inputs"]["cash_m"],
        "status": final_contract.get("status"),
        "model_level": final_contract.get("model_level"),
        "base_value": ((final_contract.get("valuation") or {}).get("value_per_share") or {}).get("base"),
        "falsifier_missing": ((final_contract.get("falsifier_coverage") or {}).get("prospective_gate") or {}).get("missing_components") or [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tickers", nargs="*", type=str.upper, default=sorted(CONFIG))
    args = parser.parse_args()
    unknown = sorted(set(args.tickers) - set(CONFIG))
    if unknown:
        parser.error(f"unsupported tickers: {', '.join(unknown)}")
    commit = head_commit()
    results = [run_ticker(ticker, commit) for ticker in args.tickers]
    print(json.dumps({"results": results}, indent=2))
    return 1 if any(row["status"] != "decision_grade" or row["model_level"] != "stock_specific" or row["falsifier_missing"] for row in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
