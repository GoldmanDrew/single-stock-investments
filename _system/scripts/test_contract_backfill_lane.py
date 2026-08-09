import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import build_contract_backfill_queue as queue
import build_deep_dive_dispatch_matrix as matrix
import llm_call_gate
import marvin_pick_ticker as pick


class ContractBackfillLaneTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "_system" / "data").mkdir(parents=True)
        (self.root / "_system" / "portfolio").mkdir(parents=True)
        holdings = {
            "AAA": {"stance": "hold"},
            "BBB": {"stance": "watch"},
            "CCC": {"stance": "core"},
        }
        (self.root / "_system" / "portfolio" / "registry.json").write_text(
            json.dumps({"holdings": holdings}), encoding="utf-8"
        )
        # Almost-there: mapped + blocked
        self._write_contract("AAA", evidence_blocked=True, mapped=True)
        # Unmapped blocked
        self._write_contract("BBB", evidence_blocked=True, mapped=False)
        # Decision grade — should not queue
        self._write_contract("CCC", evidence_blocked=False, mapped=True)

        patches = [
            patch.object(queue, "ROOT", self.root),
            patch.object(queue, "QUEUE", self.root / "_system" / "data" / "contract_backfill_queue.json"),
            patch.object(queue, "REGISTRY", self.root / "_system" / "portfolio" / "registry.json"),
            patch.object(pick, "ROOT", self.root),
            patch.object(matrix, "ROOT", self.root),
            patch.object(matrix, "DEFAULT_QUEUE", self.root / "_system" / "data" / "deep_dive_dispatch_queue.json"),
            patch.object(matrix, "BACKFILL_QUEUE", self.root / "_system" / "data" / "contract_backfill_queue.json"),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        self.addCleanup(self.tmp.cleanup)

    def _write_contract(self, ticker: str, *, evidence_blocked: bool, mapped: bool):
        research = self.root / ticker / "research"
        research.mkdir(parents=True, exist_ok=True)
        contract = {
            "status": "evidence_blocked" if evidence_blocked else "decision_grade",
            "component_coverage": {
                "all_material_components_identified": mapped,
                "additive_component_count": 3 if mapped else 0,
            },
            "evidence": {"blockers": ["needs proof"]},
        }
        (research / "valuation_contract.json").write_text(json.dumps(contract), encoding="utf-8")

    def test_queue_puts_almost_there_first_and_authorizes(self):
        payload = queue.build_queue(wave_size=10, authorize_packets=True)
        self.assertEqual(payload["almost_there"], ["AAA"])
        self.assertEqual(payload["tickers"][0], "AAA")
        self.assertIn("BBB", payload["tickers"])
        self.assertNotIn("CCC", payload["tickers"])
        auth = json.loads((self.root / "AAA" / "research" / "authorized_evidence.json").read_text(encoding="utf-8"))
        self.assertEqual(auth["purpose"], "contract_backfill")
        self.assertEqual(auth["cohort"], "almost_there")

    def test_fresh_build_does_not_rotate(self):
        payload = queue.build_queue(wave_size=10, authorize_packets=True)
        self.assertFalse(payload["stall_breaker"]["rotated"])
        self.assertEqual(payload["tickers"], ["AAA", "BBB"])
        self.assertEqual(payload["dispatch_attempts"], {"AAA": 1, "BBB": 1})

    def test_stalled_wave_rotates_to_back(self):
        # First real dispatch: wave of 1 takes the almost-there ticker.
        first = queue.build_queue(wave_size=1, authorize_packets=True)
        self.assertEqual(first["tickers"], ["AAA"])
        # No contract changed (the batch job failed); identical rebuild must rotate.
        second = queue.build_queue(wave_size=1, authorize_packets=True)
        self.assertTrue(second["stall_breaker"]["rotated"])
        self.assertEqual(second["stall_breaker"]["stalled_wave"], ["AAA"])
        self.assertEqual(second["tickers"], ["BBB"])
        self.assertEqual(second["dispatch_attempts"], {"AAA": 1, "BBB": 1})
        # Third rebuild with still no progress rotates back and bumps attempts.
        third = queue.build_queue(wave_size=1, authorize_packets=True)
        self.assertEqual(third["tickers"], ["AAA"])
        self.assertEqual(third["dispatch_attempts"], {"AAA": 2, "BBB": 1})

    def test_stall_with_all_pending_in_wave_rotates_by_one(self):
        first = queue.build_queue(wave_size=10, authorize_packets=True)
        self.assertEqual(first["tickers"], ["AAA", "BBB"])
        second = queue.build_queue(wave_size=10, authorize_packets=True)
        self.assertTrue(second["stall_breaker"]["rotated"])
        self.assertEqual(second["tickers"], ["BBB", "AAA"])
        self.assertNotEqual(second["tickers"], first["tickers"])

    def test_progress_suppresses_rotation(self):
        queue.build_queue(wave_size=10, authorize_packets=True)
        # AAA graduated: the rebuilt wave already differs, so no rotation.
        self._write_contract("AAA", evidence_blocked=False, mapped=True)
        payload = queue.build_queue(wave_size=10, authorize_packets=True)
        self.assertFalse(payload["stall_breaker"]["rotated"])
        self.assertEqual(payload["tickers"], ["BBB"])
        self.assertNotIn("AAA", payload["dispatch_attempts"])

    def test_dry_run_wave_is_not_treated_as_dispatched(self):
        # authorized_packets == 0 (dry run / --no-authorize) never counts as a
        # dispatched wave, so an identical rebuild passes through unchanged.
        queue.build_queue(wave_size=10, authorize_packets=False)
        payload = queue.build_queue(wave_size=10, authorize_packets=True)
        self.assertFalse(payload["stall_breaker"]["rotated"])
        self.assertEqual(payload["tickers"], ["AAA", "BBB"])

    def test_terminal_single_ticker_stall_reports_honestly(self):
        # Only one pending ticker: rotation is impossible, so the breaker must
        # not claim one, the wave stays unchanged (no push fires), and
        # attempts must not phantom-increment on the no-op rebuilds.
        self._write_contract("BBB", evidence_blocked=False, mapped=True)
        first = queue.build_queue(wave_size=1, authorize_packets=True)
        self.assertEqual(first["tickers"], ["AAA"])
        second = queue.build_queue(wave_size=1, authorize_packets=True)
        self.assertFalse(second["stall_breaker"]["rotated"])
        self.assertEqual(second["tickers"], ["AAA"])
        self.assertEqual(second["dispatch_attempts"], {"AAA": 1})

    def test_exhausted_tickers_park_behind_fresh_work(self):
        # After MAX_DISPATCH_ATTEMPTS failed dispatches a ticker parks at the
        # back of the order (visible in stall_breaker.parked) so fresh work
        # drains first, even though almost-there normally sorts ahead.
        for _ in range(5):
            payload = queue.build_queue(wave_size=1, authorize_packets=True)
        self.assertEqual(payload["dispatch_attempts"]["AAA"], queue.MAX_DISPATCH_ATTEMPTS)
        sixth = queue.build_queue(wave_size=1, authorize_packets=True)
        self.assertEqual(sixth["stall_breaker"]["parked"], ["AAA"])
        self.assertEqual(sixth["tickers"], ["BBB"])

    def test_dry_run_does_not_overwrite_dispatch_baseline(self):
        queue.build_queue(wave_size=1, authorize_packets=True)
        # A manual dry-run between scheduled runs must not clobber the
        # dispatched-wave record that arms the stall breaker.
        queue.build_queue(wave_size=1, authorize_packets=False, persist=False)
        on_disk = json.loads(
            (self.root / "_system" / "data" / "contract_backfill_queue.json").read_text(encoding="utf-8")
        )
        self.assertEqual(on_disk["authorized_packets"], 1)
        second = queue.build_queue(wave_size=1, authorize_packets=True)
        self.assertTrue(second["stall_breaker"]["rotated"])

    def test_matrix_prefers_backfill_queue_reason(self):
        queue.build_queue(wave_size=10, authorize_packets=False)
        jobs = matrix.resolve_jobs(
            queue_path=matrix.DEFAULT_QUEUE,
            use_queue=True,
            cli_csv=None,
            reason_override=None,
        )
        self.assertTrue(jobs)
        self.assertEqual(jobs[0]["reason"], "contract_backfill")
        self.assertEqual(jobs[0]["consumer"], "marvin_contract_backfill")

    def test_policy_admits_contract_backfill_consumer(self):
        policy = json.loads(
            (Path(__file__).resolve().parents[2] / "_system" / "config" / "llm_usage_policy.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertIn("contract_backfill", policy["consumers"]["marvin_research"]["allowed_reasons"])
        self.assertEqual(policy["consumers"]["marvin_contract_backfill"]["daily_repo_limit"], 12)
        model = llm_call_gate.resolve_model(policy, "marvin_contract_backfill", reason="contract_backfill")
        self.assertEqual(model, policy["model_ladder"]["default_model"])

    def test_pick_uses_contract_backfill_when_queue_ready(self):
        queue.build_queue(wave_size=10, authorize_packets=True)
        # Stub research_candidate to accept the first backfill ticker.
        def fake_candidate(ticker, reason, *, force=False):
            if reason == "contract_backfill" and ticker == "AAA":
                return {"ticker": ticker, "reason": reason, "skip": False}
            return None

        with patch.object(pick, "research_candidate", side_effect=fake_candidate), patch.object(
            pick, "evidence_recovery_candidates", return_value=[]
        ), patch.object(pick, "onboard_pending_holdings", return_value=[]), patch.object(
            pick, "holdings_tickers", return_value=["AAA", "BBB", "CCC"]
        ), patch.object(pick, "_activity_snapshot", return_value={"deep_dive_at": object(), "trigger_at": None, "reason": None}):
            result = pick.pick_ticker()
        self.assertEqual(result["ticker"], "AAA")
        self.assertEqual(result["reason"], "contract_backfill")


if __name__ == "__main__":
    unittest.main()
