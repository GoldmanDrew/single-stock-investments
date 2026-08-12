from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import graph_build
import graph_invariants
import record_committee_outcome
import resolve_falsifiers
import test_graph_build


def write_json(root: Path, relative: str, value: dict) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return path


class EpistemicLoopIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_resolved_forecast_traverses_outcome_graph_and_calibration(self):
        test_graph_build.make_fixture(self.root)
        write_json(self.root, "TST/research/falsifier_specs.json", {
            "schema_version": "2.0",
            "ticker": "TST",
            "specs": [{
                "spec_id": "tst-core-owner-cash-2026q2",
                "spec_revision": 1,
                "authored_at": "2026-05-01T12:00:00Z",
                "analysis_run_id": "fixture-run-1",
                "author": "fixture-agent",
                "model_id": "fixture-model",
                "prompt_version": "fixture-prompt-v1",
                "contract_hash": "a" * 64,
                "method_id": "owner_earnings_reinvestment_dcf",
                "power_zone": "quality_reinvestment",
                "component_id": "core",
                "metric": "owner_cash_m",
                "comparator": "lt",
                "threshold": 100.0,
                "unit": "USD millions",
                "measurement_period_end": "2026-06-30",
                "observable_after": "2026-08-01",
                "resolution_deadline": "2026-08-15",
                "source_hint": "owner_cash_m",
                "probability_fires": 0.25,
                "severity": 4,
                "derived_from": "Primary evidence shows worse than low case.",
                "untestable": False,
                "rationale": "Owner cash below 100 breaks the low case.",
                "supersedes_spec_id": None,
            }],
        })
        write_json(self.root, "TST/research/valuation_fact_ledger.json", {
            "facts": [{
                "field_id": "owner_cash_m",
                "value": 80.0,
                "unit": "USD millions",
                "locked": True,
                "source": {
                    "ref": "TST/research/evidence/sec_companyfacts.json",
                    "as_of": "2026-06-30",
                    "filed": "2026-08-05",
                },
            }],
        })

        resolved = resolve_falsifiers.run(
            self.root, date(2026, 8, 10), apply=True)
        self.assertEqual(resolved["counts"]["hit"], 1)
        row = resolved["new_rows"][0]
        self.assertEqual(row["spec_id"], "tst-core-owner-cash-2026q2")
        self.assertEqual(row["verdict"], "hit")
        self.assertEqual(row["resolved_as_of"], "2026-06-30")

        results, exit_code, _ = graph_invariants.run(
            self.root,
            self.root / "_system/graph/graph.db",
            self.root / "_system/graph",
            date(2026, 8, 10),
        )
        by_id = {result.id: result for result in results}
        self.assertEqual(by_id["E2"].count, 0)
        self.assertEqual(by_id["E3"].count, 0)
        self.assertEqual(exit_code, 0)

        graph_build.build(self.root, self.root / "_system/graph/graph.db")
        import sqlite3
        conn = sqlite3.connect(self.root / "_system/graph/graph.db")
        try:
            self.assertGreaterEqual(conn.execute(
                "SELECT count(*) FROM edges WHERE type='RESOLVED_BY'"
            ).fetchone()[0], 1)
            self.assertGreaterEqual(conn.execute(
                "SELECT count(*) FROM edges WHERE type='SCORES'"
            ).fetchone()[0], 1)
        finally:
            conn.close()

    def test_authoritative_owner_decision_enters_committee_outcome_loop(self):
        research = self.root / "TST/research"
        write_json(self.root, "TST/research/committee_2026-01-01.json", {
            "ticker": "TST",
            "final_state": "committee_complete_decision_pending",
            "review": {"as_of": "2026-01-01"},
            "evidence_packet": {"packet_hash": "b" * 64},
            "round_two": {"votes": [{
                "persona": "munger_quality",
                "vote": "approve",
                "expected_return_range_pct": [5.0, 15.0],
            }]},
            "human_decision": {
                "status": "pending", "decision": None, "sizing": None,
                "top_dissent_response": None, "decided_at": None,
            },
        })
        write_json(self.root, "TST/research/human_decision.json", {
            "schema_version": "1.0",
            "ticker": "TST",
            "status": "decided",
            "decision": "approve",
            "stance": "approve",
            "sizing": "2%",
            "owner": "owner",
            "committee_source": "committee_2026-01-01.json",
            "committee_packet_hash": "b" * 64,
            "top_dissent_response": "Reviewed and accepted the risk.",
            "attestation": "I reviewed the frozen evidence, committee synthesis, and strongest dissent.",
            "expires_at": None,
            "decided_at": "2026-01-01T12:00:00+00:00",
        })
        write_json(self.root, "TST/research/valuation.json", {
            "inputs": {"price": 100.0},
            "component_valuation_results": {
                "total_equity_value_per_share": {"low": 90, "base": 120, "high": 150},
                "additive_components": [],
            },
            "economic_value_analysis": {"status": "complete"},
            "universal_valuation_contract": {
                "status": "decision_grade",
                "method_route": {"profile_id": "quality_reinvestment"},
            },
        })

        with patch.object(record_committee_outcome, "ROOT", self.root), \
             patch.object(record_committee_outcome, "LEDGER",
                          self.root / "_system/research/committee_outcomes.jsonl"), \
             patch.object(record_committee_outcome, "CALIBRATION",
                          self.root / "_system/research/committee_calibration.json"), \
             patch.object(record_committee_outcome, "compute_period_total_return",
                          return_value={
                              "horizon_days": 181,
                              "return_status": "complete",
                              "total_return_pct": 12.0,
                              "return_evidence_ref": "fixture",
                              "return_contract": "split-and-dividend-aware",
                          }), \
             patch.object(record_committee_outcome, "write_valuation_workbench"):
            record = record_committee_outcome.record(
                "TST", committee_date="2026-01-01",
                measurement_date="2026-07-01", horizon_months=6,
                error_attribution=[], write=True)

        self.assertEqual(record["owner_decision"], "approve")
        self.assertEqual(record["decision_date"], "2026-01-01T12:00:00+00:00")
        calibration = json.loads((
            self.root / "_system/research/committee_calibration.json"
        ).read_text(encoding="utf-8"))
        self.assertEqual(calibration["completed_outcomes"], 1)
        self.assertEqual(calibration["methods"]["munger_quality"]["completed_outcomes"], 1)


if __name__ == "__main__":
    unittest.main()
