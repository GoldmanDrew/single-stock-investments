"""Tests for Phase 3 (verify_ssi_claims) of the SSI pipeline."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_ssi_claims as claims_mod  # noqa: E402
import build_ssi_evidence_pack as pack_mod  # noqa: E402
import verify_ssi_claims as verify_mod  # noqa: E402

CURRENT_10K = """Assets: 1,000,000
Revenues: 500,000
AllowanceForCreditLoss: 66,000
CashAndCashEquivalentsAtCarryingValue: 120,000
Risk Factors
We may face substantial doubt about our ability to continue as a going concern.
"""

PRIOR_10K = """Assets: 900,000
Revenues: 400,000
AllowanceForCreditLoss: 44,000
CashAndCashEquivalentsAtCarryingValue: 150,000
Risk Factors
Ordinary regulatory language.
"""


def _pipeline_through_phase2(tmp_path: Path, name: str = "TEST") -> Path:
    ticker_dir = tmp_path / name
    text_dir = ticker_dir / "research" / "evidence" / "_text"
    text_dir.mkdir(parents=True)
    (text_dir / "10-K_20260313_rpt20251231_acc1.htm.txt").write_text(CURRENT_10K, encoding="utf-8")
    (text_dir / "10-K_20250314_rpt20241231_acc2.htm.txt").write_text(PRIOR_10K, encoding="utf-8")
    pack_mod.write_evidence_pack(ticker_dir, "2026-08-05")
    claims_mod.write_claims(ticker_dir, "2026-08-05")
    return ticker_dir


def test_clean_pipeline_verifies_all_claims(tmp_path):
    ticker_dir = _pipeline_through_phase2(tmp_path)
    result = verify_mod.verify_ticker(ticker_dir, "2026-08-05", gold_path=tmp_path / "gold.jsonl")
    assert result is not None
    assert result["pack_integrity"]["ok"]
    assert result["failed_count"] == 0
    assert result["verified_count"] > 0
    assert all(c["verification"] == "verified" for c in result["verified_claims"])
    assert not (tmp_path / "gold.jsonl").exists()  # no failures → no gold cases


def test_source_drift_fails_claims_and_writes_gold(tmp_path):
    ticker_dir = _pipeline_through_phase2(tmp_path)
    # Tamper with the current filing AFTER claims were built.
    target = next((ticker_dir / "research" / "evidence" / "_text").glob("10-K_20260313*"))
    target.write_text(CURRENT_10K + "TamperTag: 1\n", encoding="utf-8")
    gold = tmp_path / "gold.jsonl"
    result = verify_mod.verify_ticker(ticker_dir, "2026-08-05", gold_path=gold)
    assert not result["pack_integrity"]["ok"]
    assert target.name in result["pack_integrity"]["drifted_sources"][0]
    assert result["verified_count"] == 0
    assert result["failed_count"] > 0
    lines = gold.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == result["failed_count"]
    case = json.loads(lines[0])
    assert case["issuer"] == "TEST"
    assert case["adjudication"] == "pending"


def test_fabricated_locator_is_deleted_not_softened(tmp_path):
    ticker_dir = _pipeline_through_phase2(tmp_path)
    claims_path = next((ticker_dir / "research" / "evidence").glob("ssi_claims_*.json"))
    doc = json.loads(claims_path.read_text(encoding="utf-8"))
    fact = next(c for c in doc["claims"] if c["evidence_ref"].get("tag") == "AllowanceForCreditLoss")
    fact["evidence_ref"]["line_current"] = 2  # points at Revenues, not Allowance
    claims_path.write_text(json.dumps(doc), encoding="utf-8")
    result = verify_mod.verify_ticker(ticker_dir, "2026-08-05", gold_path=tmp_path / "gold.jsonl")
    failed_ids = {r for r in result["failure_reasons"]}
    assert any("current_tag_mismatch" in r for r in failed_ids)
    verified_tags = {c["evidence_ref"].get("tag") for c in result["verified_claims"]}
    assert "AllowanceForCreditLoss" not in verified_tags


def test_direction_mismatch_is_caught(tmp_path):
    ticker_dir = _pipeline_through_phase2(tmp_path)
    claims_path = next((ticker_dir / "research" / "evidence").glob("ssi_claims_*.json"))
    doc = json.loads(claims_path.read_text(encoding="utf-8"))
    fact = next(c for c in doc["claims"] if c["evidence_ref"].get("tag") == "AllowanceForCreditLoss")
    fact["direction"] = "down"  # raw values say up (44k → 66k)
    claims_path.write_text(json.dumps(doc), encoding="utf-8")
    result = verify_mod.verify_ticker(ticker_dir, "2026-08-05", gold_path=tmp_path / "gold.jsonl")
    assert any("direction_mismatch" in r for r in result["failure_reasons"])


def test_section_claim_verifies_blind(tmp_path):
    ticker_dir = _pipeline_through_phase2(tmp_path)
    result = verify_mod.verify_ticker(ticker_dir, "2026-08-05", gold_path=tmp_path / "gold.jsonl")
    section_claims = [
        c for c in result["verified_claims"] if c["evidence_ref"].get("section")
    ]
    assert section_claims, "going-concern section claim should verify"
    assert section_claims[0]["severity"] == 5


def test_routing_ineligible_without_contract(tmp_path):
    ticker_dir = _pipeline_through_phase2(tmp_path)
    result = verify_mod.verify_ticker(ticker_dir, "2026-08-05", gold_path=tmp_path / "gold.jsonl")
    routing = result["routing"]
    assert routing["committee_eligible"] is False
    assert "contract_status=missing" in routing["reason"]
    assert routing["high_severity_claim_ids"]  # sev-5 exists, contract is the blocker


def test_routing_eligible_with_decision_grade_contract(tmp_path):
    ticker_dir = _pipeline_through_phase2(tmp_path)
    research = ticker_dir / "research"
    (research / "valuation.json").write_text(json.dumps({"ticker": "TEST"}), encoding="utf-8")
    (research / "valuation_contract.json").write_text(json.dumps({
        "status": "decision_grade", "ticker": "TEST",
        "evidence": {"blockers": []},
    }), encoding="utf-8")
    result = verify_mod.verify_ticker(ticker_dir, "2026-08-05", gold_path=tmp_path / "gold.jsonl")
    routing = result["routing"]
    assert routing["contract_status"] == "decision_grade"
    assert routing["committee_eligible"] is True
    assert "dispatch" in routing["dispatch_note"].lower() or "committee" in routing["dispatch_note"].lower()


def test_time_zero_snapshot_contents(tmp_path):
    ticker_dir = _pipeline_through_phase2(tmp_path)
    outs = verify_mod.write_verification(ticker_dir, "2026-08-05")
    assert outs is not None
    verified_out, snapshot_out = outs
    snapshot = json.loads(snapshot_out.read_text(encoding="utf-8"))
    verified = json.loads(verified_out.read_text(encoding="utf-8"))
    assert snapshot["pack_hash"] == verified["pack_hash"]
    assert snapshot["verified_claim_ids"]
    assert set(snapshot["verified_claim_ids"]) == {
        c["claim_id"] for c in verified["verified_claims"]
    }
    assert len(snapshot["claims_file_sha256"]) == 64
    assert "price" in snapshot["unavailable_fields"]


def test_no_claims_returns_none(tmp_path):
    ticker_dir = tmp_path / "EMPTY"
    (ticker_dir / "research" / "evidence").mkdir(parents=True)
    assert verify_mod.verify_ticker(ticker_dir, "2026-08-05") is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
