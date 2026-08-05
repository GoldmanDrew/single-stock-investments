"""Tests for Phase 2 (build_ssi_claims) of the SSI pipeline."""
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

CURRENT_10K = """Assets: 1,000,000
Revenues: 500,000
AllowanceForCreditLoss: 66,000
CashAndCashEquivalentsAtCarryingValue: 120,000
GoodwillImpairmentLoss: 30,000
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


def _ticker_with_pack(tmp_path: Path) -> Path:
    ticker_dir = tmp_path / "TEST"
    text_dir = ticker_dir / "research" / "evidence" / "_text"
    text_dir.mkdir(parents=True)
    (text_dir / "10-K_20260313_rpt20251231_acc1.htm.txt").write_text(CURRENT_10K, encoding="utf-8")
    (text_dir / "10-K_20250314_rpt20241231_acc2.htm.txt").write_text(PRIOR_10K, encoding="utf-8")
    pack_mod.write_evidence_pack(ticker_dir, "2026-08-05")
    return ticker_dir


def test_claims_route_to_furnace_taxonomy(tmp_path):
    ticker_dir = _ticker_with_pack(tmp_path)
    result = claims_mod.build_claims(ticker_dir, "2026-08-05")
    assert result is not None
    taxonomies = {c["taxonomy"] for c in result["claims"]}
    assert "earnings_quality" in taxonomies      # AllowanceForCreditLoss
    assert "liquidity_oxygen" in taxonomies      # Cash...
    assert "operating_failure" in taxonomies     # GoodwillImpairmentLoss + narrative


def test_allowance_jump_is_severity_4(tmp_path):
    ticker_dir = _ticker_with_pack(tmp_path)
    result = claims_mod.build_claims(ticker_dir, "2026-08-05")
    allowance = next(
        c for c in result["claims"]
        if c["evidence_ref"].get("tag") == "AllowanceForCreditLoss"
    )
    assert allowance["severity"] == 4
    assert allowance["magnitude_pct"] == 50.0
    assert allowance["direction"] == "up"


def test_going_concern_narrative_is_severity_5(tmp_path):
    ticker_dir = _ticker_with_pack(tmp_path)
    result = claims_mod.build_claims(ticker_dir, "2026-08-05")
    critical = [c for c in result["claims"] if c["severity"] == 5]
    assert critical, "expected a severity-5 claim from the going-concern diff"
    assert any("going concern" in c["statement"] for c in critical)
    # Claims are sorted most-severe first.
    assert result["claims"][0]["severity"] == 5


def test_every_claim_has_resolvable_evidence_ref(tmp_path):
    ticker_dir = _ticker_with_pack(tmp_path)
    result = claims_mod.build_claims(ticker_dir, "2026-08-05")
    pack = json.loads(
        (ticker_dir / "research" / "evidence" / "ssi_evidence_pack_2026-08-05.json")
        .read_text(encoding="utf-8")
    )
    sha_by_path = {f["path"]: f["sha256"] for f in pack["filings"]}
    for claim in result["claims"]:
        ref = claim["evidence_ref"]
        assert ref["pack_hash"] == pack["pack_hash"]
        assert ref["source_path"] in sha_by_path
        assert ref["source_sha256"] == sha_by_path[ref["source_path"]]
        assert claim["falsifier"]


def test_new_tag_claims_get_medium_confidence(tmp_path):
    ticker_dir = _ticker_with_pack(tmp_path)
    result = claims_mod.build_claims(ticker_dir, "2026-08-05")
    goodwill = next(
        c for c in result["claims"]
        if c["evidence_ref"].get("tag") == "GoodwillImpairmentLoss"
    )
    assert goodwill["direction"] == "new"
    assert goodwill["confidence"] == "medium"


def test_management_ledger_resolves_promises(tmp_path):
    ticker_dir = _ticker_with_pack(tmp_path)
    evidence_dir = ticker_dir / "research" / "evidence"
    (evidence_dir / "management_facts_2026-08-01.json").write_text(json.dumps({
        "ticker": "TEST",
        "claims": [
            {"metric": "revenues", "value": 450_000, "statement": "FY25 revenue above 450k", "date": "2025-05-01"},
            {"metric": "revenues", "value": 600_000, "statement": "FY25 revenue above 600k", "date": "2025-05-01"},
            {"metric": "nps_score", "value": 70, "statement": "NPS above 70"},
        ],
    }), encoding="utf-8")
    (evidence_dir / "filing_facts_2026-08-05.json").write_text(json.dumps({
        "ticker": "TEST",
        "metrics": {"revenues": {"current": 500_000, "prior": 400_000, "tag": "Revenues"}},
    }), encoding="utf-8")
    result = claims_mod.build_claims(ticker_dir, "2026-08-05")
    ledger = result["management_ledger"]
    assert ledger["promise_count"] == 3
    assert ledger["resolved_count"] == 2
    assert ledger["hit_rate"] == 0.5
    statuses = {r["promise"]: r["status"] for r in ledger["rows"]}
    assert statuses["FY25 revenue above 450k"] == "met"
    assert statuses["FY25 revenue above 600k"] == "missed"
    assert statuses["NPS above 70"] == "unresolvable_metric"


def test_spawner_scores_and_abstentions(tmp_path):
    ticker_dir = _ticker_with_pack(tmp_path)
    evidence_dir = ticker_dir / "research" / "evidence"
    (evidence_dir / "filing_facts_2026-08-05.json").write_text(json.dumps({
        "ticker": "TEST",
        "metrics": {
            "shares_outstanding": {"current": 46.4, "prior": 50.7, "tag": "WeightedAverageNumberOfDilutedSharesOutstanding"},
            "capital_expenditures": {"current": 10.0, "prior": 9.0, "tag": "PaymentsToAcquirePropertyPlantAndEquipment"},
            "operating_cash_flow": {"current": 100.0, "prior": 90.0, "tag": "NetCashProvidedByUsedInOperatingActivities"},
        },
    }), encoding="utf-8")
    result = claims_mod.build_claims(ticker_dir, "2026-08-05")
    spawner = result["spawner"]
    assert spawner["components"]["buyback_trajectory"]["read"] == "shrinking"
    assert spawner["components"]["capex_intensity"]["read"] == "capital_light"
    # Segment-dependent scores abstain instead of fabricating.
    assert any(a.startswith("small_bet_discipline") for a in spawner["abstentions"])
    assert any(a.startswith("kill_discipline") for a in spawner["abstentions"])


def test_intra_filing_claims_capped_at_medium_confidence(tmp_path):
    ticker_dir = tmp_path / "SOLO"
    text_dir = ticker_dir / "research" / "evidence" / "_text"
    text_dir.mkdir(parents=True)
    (text_dir / "10-K_20260313_rpt20251231_acc1.htm.txt").write_text(CURRENT_10K.replace(
        "GoodwillImpairmentLoss: 30,000\n", "GoodwillImpairmentLoss: 30,000\nGoodwillImpairmentLoss: 10,000\n"
    ), encoding="utf-8")
    pack_mod.write_evidence_pack(ticker_dir, "2026-08-05")
    result = claims_mod.build_claims(ticker_dir, "2026-08-05")
    assert result is not None and result["claims"]
    for claim in result["claims"]:
        if "intra_filing_pairing" in claim.get("flags", []):
            assert claim["confidence"] in ("medium", "low")


def test_no_pack_returns_none(tmp_path):
    ticker_dir = tmp_path / "EMPTY"
    (ticker_dir / "research" / "evidence").mkdir(parents=True)
    assert claims_mod.build_claims(ticker_dir, "2026-08-05") is None


def test_dropped_modalities_are_reported(tmp_path):
    ticker_dir = _ticker_with_pack(tmp_path)
    result = claims_mod.build_claims(ticker_dir, "2026-08-05")
    assert "market_mechanics" in result["dropped_modalities"]
    assert "unrouted_delta_rows" in result["dropped_modalities"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
