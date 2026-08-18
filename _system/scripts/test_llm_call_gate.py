from __future__ import annotations

import unittest
from datetime import datetime, timezone

from llm_call_gate import evaluate


POLICY = {
    "default": {"daily_repo_limit": 2, "per_subject_daily_limit": 1, "duplicate_evidence_block": True},
    "consumers": {"test": {"cooldown_hours": 0}},
}
AT = datetime(2026, 7, 18, 12, tzinfo=timezone.utc)


class LlmCallGateTests(unittest.TestCase):
    def test_completed_state_suppresses_same_evidence(self):
        result = evaluate(
            consumer="test", subject="AAA", reason="material", evidence_hash="a" * 64,
            policy_doc=POLICY, ledger=[], state={"evidence_hash": "a" * 64}, at=AT,
        )
        self.assertFalse(result["approved"])
        self.assertEqual(result["gate_reason"], "evidence_already_processed")

    def test_changed_evidence_is_admitted(self):
        result = evaluate(
            consumer="test", subject="AAA", reason="material", evidence_hash="b" * 64,
            policy_doc=POLICY, ledger=[], state={"evidence_hash": "a" * 64}, at=AT,
        )
        self.assertTrue(result["approved"])

    def test_new_evidence_bypasses_subject_cooldown(self):
        policy = {
            "default": {"daily_repo_limit": 4, "per_subject_daily_limit": 2},
            "consumers": {"test": {"cooldown_hours": 24}},
        }
        ledger = [{"timestamp": AT.isoformat(), "consumer": "test", "subject": "AAA", "evidence_hash": "a" * 64, "status": "reserved"}]
        result = evaluate(
            consumer="test", subject="AAA", reason="material", evidence_hash="b" * 64,
            policy_doc=policy, ledger=ledger, at=AT.replace(hour=13),
        )
        self.assertTrue(result["approved"])

    def test_daily_budget_counts_reservations_not_completion_events(self):
        ledger = [
            {"timestamp": AT.isoformat(), "consumer": "test", "subject": "AAA", "evidence_hash": "a" * 64, "status": "reserved"},
            {"timestamp": AT.isoformat(), "consumer": "test", "subject": "AAA", "evidence_hash": "a" * 64, "status": "completed"},
        ]
        result = evaluate(
            consumer="test", subject="BBB", reason="material", evidence_hash="b" * 64,
            policy_doc=POLICY, ledger=ledger, at=AT,
        )
        self.assertTrue(result["approved"])

    def test_duplicate_reservation_is_suppressed(self):
        ledger = [{"timestamp": AT.isoformat(), "consumer": "test", "subject": "AAA", "evidence_hash": "a" * 64, "status": "reserved"}]
        result = evaluate(
            consumer="test", subject="AAA", reason="material", evidence_hash="a" * 64,
            policy_doc=POLICY, ledger=ledger, at=AT,
        )
        self.assertFalse(result["approved"])
        self.assertEqual(result["gate_reason"], "duplicate_evidence_hash")

    def test_failed_startup_releases_its_reservation_for_retry(self):
        ledger = [
            {"timestamp": AT.isoformat(), "consumer": "test", "subject": "AAA", "evidence_hash": "a" * 64, "status": "reserved", "run_id": "10"},
            {"timestamp": AT.isoformat(), "consumer": "test", "subject": "AAA", "evidence_hash": "a" * 64, "status": "failed", "run_id": "10"},
        ]
        result = evaluate(
            consumer="test", subject="AAA", reason="material", evidence_hash="a" * 64,
            policy_doc=POLICY, ledger=ledger, at=AT,
        )
        self.assertTrue(result["approved"])

    def test_typed_reason_prefix_admits_only_matching_work(self):
        policy = {
            "default": {"daily_repo_limit": 4, "per_subject_daily_limit": 2},
            "consumers": {"forecast": {
                "allowed_reason_prefixes": ["epistemic_author_forecast:"],
            }},
        }
        good = evaluate(
            consumer="forecast", subject="AAA",
            reason="epistemic_author_forecast:w1:component",
            evidence_hash="a" * 64, policy_doc=policy, ledger=[], at=AT,
        )
        bad = evaluate(
            consumer="forecast", subject="AAA", reason="manual_material_change",
            evidence_hash="b" * 64, policy_doc=policy, ledger=[], at=AT,
        )
        self.assertTrue(good["approved"])
        self.assertEqual(bad["gate_reason"], "reason_not_allowed")


if __name__ == "__main__":
    unittest.main()
