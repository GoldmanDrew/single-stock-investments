"""Tests for the error-driven gold set and the blueprint calibration bars.

Three defects these pin, all found on 2026-08-07:

  * Infrastructure failures (source drift, pack mismatch) were logged as
    "pending" and swamped the queue -- 258 of 261 cases from one NVDA run.
    They are unadjudicable as generator/skeptic errors and must not touch
    locator accuracy.
  * Every re-run of Phase 3 re-appended the same failures, so the log held
    129 unique cases across 516 lines.
  * locator_accuracy returned exactly 1.000 "MEETS BAR" on zero adjudications,
    and severity5_recall returned 100% on a single event. Neither is a
    measurement.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import calibrate_ssi as cal  # noqa: E402
import verify_ssi_claims as verify  # noqa: E402


# ---------------------------------------------------------------------------
# Gold set: infrastructure classification and re-run dedupe
# ---------------------------------------------------------------------------

def _failure(claim_id: str, reason: str) -> dict:
    return {"claim_id": claim_id, "failure_reason": reason, "source": "filing_sentinel",
            "taxonomy": "earnings_quality", "statement": "x moved", "evidence_ref": {}}


def _rows(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


@pytest.mark.parametrize("reason", sorted(verify.INFRASTRUCTURE_REASONS))
def test_infrastructure_failures_are_not_left_pending(tmp_path, reason):
    gold = tmp_path / "gold.jsonl"
    verify.append_gold_cases("NVDA", "2026-08-06", [_failure("c1", reason)], gold)
    row = _rows(gold)[0]
    assert row["adjudication"] == "infrastructure"
    assert row["adjudicable"] is False


def test_real_failures_still_await_a_human(tmp_path):
    gold = tmp_path / "gold.jsonl"
    verify.append_gold_cases(
        "ABX", "2026-08-06", [_failure("c2", "severity_keyword_not_rederived")], gold)
    row = _rows(gold)[0]
    assert row["adjudication"] == "pending"
    assert row["adjudicable"] is True


def test_rerunning_does_not_duplicate_cases(tmp_path):
    gold = tmp_path / "gold.jsonl"
    failures = [_failure("c1", "source_drift"), _failure("c2", "source_drift")]
    assert verify.append_gold_cases("NVDA", "2026-08-06", failures, gold) == 2
    # Same failures, same date: a re-run must add nothing.
    assert verify.append_gold_cases("NVDA", "2026-08-06", failures, gold) == 0
    assert len(_rows(gold)) == 2


def test_same_claim_on_a_new_date_is_a_new_case(tmp_path):
    gold = tmp_path / "gold.jsonl"
    verify.append_gold_cases("NVDA", "2026-08-06", [_failure("c1", "source_drift")], gold)
    verify.append_gold_cases("NVDA", "2026-08-07", [_failure("c1", "source_drift")], gold)
    assert len(_rows(gold)) == 2


# ---------------------------------------------------------------------------
# Supersession
# ---------------------------------------------------------------------------

def test_supersede_keeps_only_the_latest_verdict():
    rows = [
        {"issuer": "NVDA", "claim_id": "c1", "as_of": "d", "adjudication": "pending"},
        {"issuer": "NVDA", "claim_id": "c1", "as_of": "d", "adjudication": "infrastructure"},
    ]
    latest = cal.latest_adjudications(rows)
    assert len(latest) == 1
    assert latest[0]["adjudication"] == "infrastructure"


def test_supersede_keeps_distinct_cases_apart():
    rows = [
        {"issuer": "NVDA", "claim_id": "c1", "as_of": "d", "adjudication": "pending"},
        {"issuer": "ABX", "claim_id": "c1", "as_of": "d", "adjudication": "pending"},
        {"issuer": "NVDA", "claim_id": "c2", "as_of": "d", "adjudication": "pending"},
    ]
    assert len(cal.latest_adjudications(rows)) == 3


def test_unkeyed_rows_are_never_dropped():
    rows = [{"issuer": "X", "adjudication": "pending"},
            {"issuer": "X", "adjudication": "pending"}]
    assert len(cal.latest_adjudications(rows)) == 2


# ---------------------------------------------------------------------------
# Bars: honest rather than vacuous
# ---------------------------------------------------------------------------

def test_locator_accuracy_is_unmeasured_without_adjudications():
    value, detail = cal.locator_accuracy(
        [{"adjudication": "pending", "claim_id": "c1"}], emitted_claims=1000)
    assert value is None, "1.000 on zero adjudications is not a measurement"
    assert "unmeasured" in detail


def test_infrastructure_cases_do_not_make_accuracy_measurable():
    rows = [{"adjudication": "infrastructure", "claim_id": f"c{i}"} for i in range(258)]
    value, detail = cal.locator_accuracy(rows, emitted_claims=53_000)
    assert value is None
    assert "258 infrastructure case(s) excluded" in detail


def test_locator_accuracy_counts_only_generator_errors():
    rows = [
        {"adjudication": "generator_error", "claim_id": "c1"},
        {"adjudication": "skeptic_error", "claim_id": "c2"},
        {"adjudication": "infrastructure", "claim_id": "c3"},
    ]
    value, _ = cal.locator_accuracy(rows, emitted_claims=100)
    assert value == pytest.approx(1.0 - 1 / 100)


def test_severity5_recall_needs_a_real_sample():
    value, detail = cal.severity5_recall([{"caught": True}])
    assert value is None, "1/1 is not evidence of 100% recall"
    assert "floor" in detail


def test_severity5_recall_measures_at_the_floor():
    rows = [{"caught": True}] * 4 + [{"caught": False}]
    value, _ = cal.severity5_recall(rows)
    assert value == pytest.approx(0.8)


def test_enforce_does_not_fail_on_insufficient_data():
    """A bar that cannot be measured must not fail CI -- only a measurable bar
    that is actually unmet should."""
    assert cal.severity5_recall([{"caught": True}])[0] is None
    assert cal.locator_accuracy([], emitted_claims=0)[0] is None


# ---------------------------------------------------------------------------
# Adjudication CLI
# ---------------------------------------------------------------------------

import ssi_adjudicate as adj  # noqa: E402


def test_alert_sampling_interleaves_issuers(tmp_path, monkeypatch):
    """A precision number measured on one noisy ticker says nothing about the
    detector, so the real sampler must round-robin across issuers."""
    for issuer in ("AAA", "BBB", "CCC"):
        ev = tmp_path / issuer / "research" / "evidence"
        ev.mkdir(parents=True)
        (ev / "ssi_verified_claims_2026-08-07.json").write_text(json.dumps({
            "as_of": "2026-08-07",
            "verified_claims": [
                {"claim_id": f"{issuer}-{n}", "severity": 4 + (n % 2),
                 "taxonomy": "earnings_quality", "statement": "x", "evidence_ref": {}}
                for n in range(3)
            ],
        }), encoding="utf-8")
    monkeypatch.setattr(adj, "ROOT", tmp_path)

    queue = adj._emitted_alerts()
    assert len(queue) == 9
    assert len({r["issuer"] for r in queue[:3]}) == 3, "first page must span issuers"


def test_alert_sampling_skips_low_severity(tmp_path, monkeypatch):
    ev = tmp_path / "AAA" / "research" / "evidence"
    ev.mkdir(parents=True)
    (ev / "ssi_verified_claims_2026-08-07.json").write_text(json.dumps({
        "as_of": "2026-08-07",
        "verified_claims": [
            {"claim_id": "keep", "severity": 4, "statement": "x", "evidence_ref": {}},
            {"claim_id": "drop", "severity": 3, "statement": "x", "evidence_ref": {}},
        ],
    }), encoding="utf-8")
    monkeypatch.setattr(adj, "ROOT", tmp_path)
    assert [r["claim_id"] for r in adj._emitted_alerts()] == ["keep"]


def test_gold_set_appends_a_superseding_row(tmp_path, monkeypatch):
    gold = tmp_path / "gold.jsonl"
    verify.append_gold_cases(
        "ABX", "2026-08-06", [_failure("c9", "severity_keyword_not_rederived")], gold)
    monkeypatch.setattr(adj, "GOLD", gold)

    args = adj.argparse.Namespace(set=("c9", "generator_error"), note="bad locator",
                                  date="2026-08-07", limit=10, issuer="")
    assert adj.cmd_gold(args) == 0
    rows = _rows(gold)
    assert len(rows) == 2, "original case is kept; the verdict is appended"
    assert rows[-1]["adjudication"] == "generator_error"
    assert rows[-1]["supersedes"]["prior_adjudication"] == "pending"
    # and the collapse resolves to the new verdict
    assert cal.latest_adjudications(rows)[0]["adjudication"] == "generator_error"


def test_gold_set_rejects_an_unknown_verdict(tmp_path, monkeypatch):
    gold = tmp_path / "gold.jsonl"
    verify.append_gold_cases("ABX", "2026-08-06", [_failure("c9", "x")], gold)
    monkeypatch.setattr(adj, "GOLD", gold)
    args = adj.argparse.Namespace(set=("c9", "looks_wrong"), note="", date="2026-08-07",
                                  limit=10, issuer="")
    assert adj.cmd_gold(args) == 2
    assert len(_rows(gold)) == 1, "nothing appended on a bad verdict"
