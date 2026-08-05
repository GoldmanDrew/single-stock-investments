"""Tests for Phase 1 (build_ssi_evidence_pack) of the SSI pipeline."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_ssi_evidence_pack as pack_mod  # noqa: E402


def _write_filing(text_dir: Path, name: str, body: str) -> Path:
    text_dir.mkdir(parents=True, exist_ok=True)
    path = text_dir / name
    path.write_text(body, encoding="utf-8")
    return path


def _ticker(tmp_path: Path, name: str = "TEST") -> Path:
    ticker_dir = tmp_path / name
    (ticker_dir / "research" / "evidence").mkdir(parents=True)
    return ticker_dir


CURRENT_10K = """Assets: 1,000,000
Assets: 900,000
Revenues: 500,000
Revenues: 400,000
AllowanceForCreditLoss: 66,000
AllowanceForCreditLoss: 44,000
CashAndCashEquivalentsAtCarryingValue: 120,000
CashAndCashEquivalentsAtCarryingValue: 150,000
Risk Factors
We may face substantial doubt about our ability to continue as a going concern.
Regulatory scrutiny of partner banks has increased.
"""

PRIOR_10K = """Assets: 900,000
Assets: 850,000
Revenues: 400,000
Revenues: 350,000
AllowanceForCreditLoss: 44,000
AllowanceForCreditLoss: 40,000
CashAndCashEquivalentsAtCarryingValue: 150,000
CashAndCashEquivalentsAtCarryingValue: 140,000
Risk Factors
Regulatory scrutiny of partner banks has increased.
"""


def _standard_pair(ticker_dir: Path) -> None:
    text_dir = ticker_dir / "research" / "evidence" / "_text"
    _write_filing(text_dir, "10-K_20260313_rpt20251231_acc0001_26_1.htm.txt", CURRENT_10K)
    _write_filing(text_dir, "10-K_20250314_rpt20241231_acc0001_25_1.htm.txt", PRIOR_10K)


def test_discovery_parses_metadata_and_hashes(tmp_path):
    ticker_dir = _ticker(tmp_path)
    _standard_pair(ticker_dir)
    filings = pack_mod.discover_filings(ticker_dir)
    assert len(filings) == 2
    current = max(filings, key=lambda f: f.period_end)
    assert current.form == "10-K"
    assert current.form_class == "annual"
    assert current.file_date == "2026-03-13"
    assert current.period_end == "2025-12-31"
    assert current.accession == "0001-26-1"
    assert len(current.sha256) == 64


def test_comparability_gate_accepts_yoy_annual(tmp_path):
    ticker_dir = _ticker(tmp_path)
    _standard_pair(ticker_dir)
    filings = pack_mod.discover_filings(ticker_dir)
    current = max(filings, key=lambda f: f.period_end)
    gate = pack_mod.comparability_gate(current, filings)
    assert gate["match"] is not None
    assert gate["match"].period_end == "2024-12-31"
    assert gate["rejections"] == []


def test_comparability_gate_rejects_sequential_quarter(tmp_path):
    ticker_dir = _ticker(tmp_path)
    text_dir = ticker_dir / "research" / "evidence" / "_text"
    _write_filing(text_dir, "10-Q_20260511_rpt20260331_acc1.htm.txt", "Assets: 100\n")
    _write_filing(text_dir, "10-Q_20260210_rpt20251231_acc2.htm.txt", "Assets: 90\n")
    filings = pack_mod.discover_filings(ticker_dir)
    current = max(filings, key=lambda f: f.period_end)
    gate = pack_mod.comparability_gate(current, filings)
    assert gate["match"] is None
    assert any("too_recent" in r["reason"] for r in gate["rejections"])


def test_comparability_gate_rejects_stale_and_cross_class(tmp_path):
    ticker_dir = _ticker(tmp_path)
    text_dir = ticker_dir / "research" / "evidence" / "_text"
    _write_filing(text_dir, "10-K_20260313_rpt20251231_acc1.htm.txt", "Assets: 100\n")
    _write_filing(text_dir, "10-K_20240315_rpt20231231_acc2.htm.txt", "Assets: 80\n")  # 2y stale
    _write_filing(text_dir, "10-Q_20250511_rpt20250331_acc3.htm.txt", "Assets: 95\n")
    filings = pack_mod.discover_filings(ticker_dir)
    current = max(filings, key=lambda f: f.period_end or "")
    gate = pack_mod.comparability_gate(current, filings)
    assert gate["match"] is None
    reasons = {r["reason"].split(":")[0] for r in gate["rejections"]}
    assert "too_stale" in reasons
    assert "form_class_mismatch" in reasons


def test_fact_delta_engine_flags_and_floors(tmp_path):
    ticker_dir = _ticker(tmp_path)
    _standard_pair(ticker_dir)
    filings = pack_mod.discover_filings(ticker_dir)
    current = max(filings, key=lambda f: f.period_end)
    prior = min(filings, key=lambda f: f.period_end)
    deltas = pack_mod.fact_delta_engine(current, prior)
    by_tag = {row["tag"]: row for row in deltas["rows"]}
    # Allowance 44k → 66k = +50% → extreme_move
    assert by_tag["AllowanceForCreditLoss"]["pct"] == 50.0
    assert "extreme_move" in by_tag["AllowanceForCreditLoss"]["flags"]
    # Cash 150k → 120k = -20% material, no flag
    assert by_tag["CashAndCashEquivalentsAtCarryingValue"]["pct"] == -20.0
    # Locators present
    assert by_tag["Revenues"]["line_current"] >= 1
    assert by_tag["Revenues"]["line_prior"] >= 1


def test_fact_delta_engine_sub_floor_dropped_but_counted(tmp_path):
    ticker_dir = _ticker(tmp_path)
    text_dir = ticker_dir / "research" / "evidence" / "_text"
    a = _write_filing(text_dir, "10-K_20260313_rpt20251231_acc1.htm.txt", "Assets: 102\n")
    b = _write_filing(text_dir, "10-K_20250314_rpt20241231_acc2.htm.txt", "Assets: 100\n")
    filings = pack_mod.discover_filings(ticker_dir)
    current = next(f for f in filings if f.path == a)
    prior = next(f for f in filings if f.path == b)
    deltas = pack_mod.fact_delta_engine(current, prior)
    assert deltas["rows"] == []
    assert deltas["dropped_sub_floor"] == 1


def test_revenue_definition_bank_style(tmp_path):
    ticker_dir = _ticker(tmp_path)
    text_dir = ticker_dir / "research" / "evidence" / "_text"
    body = (
        "InterestIncomeExpenseNet: 375,500\n"
        "NoninterestIncome: 469,500\n"
        "Revenues: 375,500\n"
    )
    path = _write_filing(text_dir, "10-K_20260313_rpt20251231_acc1.htm.txt", body)
    filing = pack_mod.discover_filings(ticker_dir)[0]
    result = pack_mod.revenue_definition_check(filing)
    assert result["definition"] == "bank_style"
    assert result["operating_revenue"] == 845_000
    assert "bank_style_revenue" in result["flags"]
    assert "reported_revenue_below_operating_revenue" in result["flags"]
    assert "noninterest_income_exceeds_nii" in result["flags"]


def test_section_diff_detects_added_going_concern(tmp_path):
    ticker_dir = _ticker(tmp_path)
    _standard_pair(ticker_dir)
    filings = pack_mod.discover_filings(ticker_dir)
    current = max(filings, key=lambda f: f.period_end)
    prior = min(filings, key=lambda f: f.period_end)
    diff = pack_mod.section_diff_engine(current, prior)
    assert diff["narrative_available"]
    risk = diff["sections"]["risk_factors"]
    assert any("going concern" in kw for kw in risk["severity_keywords_added"])
    assert risk["added_count"] == 1


def test_pack_hash_stable_and_sensitive(tmp_path):
    ticker_dir = _ticker(tmp_path)
    _standard_pair(ticker_dir)
    pack1 = pack_mod.build_evidence_pack(ticker_dir, "2026-08-05")
    pack2 = pack_mod.build_evidence_pack(ticker_dir, "2026-08-05")
    assert pack1["pack_hash"] == pack2["pack_hash"]
    # Any source change must change the hash.
    text_dir = ticker_dir / "research" / "evidence" / "_text"
    _write_filing(text_dir, "10-K_20260313_rpt20251231_acc0001_26_1.htm.txt", CURRENT_10K + "Assets: 1\n")
    pack3 = pack_mod.build_evidence_pack(ticker_dir, "2026-08-05")
    assert pack3["pack_hash"] != pack1["pack_hash"]


def test_write_evidence_pack_roundtrip(tmp_path):
    ticker_dir = _ticker(tmp_path)
    _standard_pair(ticker_dir)
    out = pack_mod.write_evidence_pack(ticker_dir, "2026-08-05")
    assert out is not None and out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["ticker"] == "TEST"
    assert data["comparisons"][0]["gate"]["matched"]
    assert data["pack_hash"]


def test_intra_filing_fallback_when_no_prior_on_disk(tmp_path):
    ticker_dir = _ticker(tmp_path)
    text_dir = ticker_dir / "research" / "evidence" / "_text"
    _write_filing(text_dir, "10-K_20260313_rpt20251231_acc1.htm.txt", CURRENT_10K)
    pack = pack_mod.build_evidence_pack(ticker_dir, "2026-08-05")
    comp = pack["comparisons"][0]
    assert comp["gate"]["matched"] is None
    deltas = comp["fact_deltas"]
    assert deltas["mode"] == "intra_filing"
    by_tag = {row["tag"]: row for row in deltas["rows"]}
    # 66k vs 44k prior-period pair inside the same filing.
    assert by_tag["AllowanceForCreditLoss"]["pct"] == 50.0
    assert "intra_filing_pairing" in by_tag["AllowanceForCreditLoss"]["flags"]
    assert any(note.endswith("intra_filing_fallback") for note in pack["coverage_notes"])


def test_unparsed_filenames_are_noted(tmp_path):
    ticker_dir = _ticker(tmp_path)
    text_dir = ticker_dir / "research" / "evidence" / "_text"
    _write_filing(text_dir, "20251113_j.pdf.txt", "some japanese filing text\n")
    pack = pack_mod.build_evidence_pack(ticker_dir, "2026-08-05")
    assert "unparsed_filename:20251113_j.pdf.txt" in pack["coverage_notes"]
    assert "no_text_extracts" not in pack["coverage_notes"]


def test_no_text_extracts_is_noted_not_fatal(tmp_path):
    ticker_dir = _ticker(tmp_path)
    pack = pack_mod.build_evidence_pack(ticker_dir, "2026-08-05")
    assert "no_text_extracts" in pack["coverage_notes"]
    assert pack["pack_hash"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
