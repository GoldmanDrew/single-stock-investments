import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


exporter = load_module(
    "export_dashboard_d1_seed",
    ROOT / "_system" / "scripts" / "export_dashboard_d1_seed.py",
)


class DashboardD1ExportTests(unittest.TestCase):
    def test_export_is_idempotent_and_preserves_blocked_work(self):
        core = {
            "generated_at": "2026-07-29T12:00:00Z",
            "summary": {"holdings": 1},
            "valuation_queue": {
                "items": [{
                    "ticker": "TEST",
                    "next_gap_id": "revenue_required",
                    "next_gap_question": "Find audited revenue.",
                }],
            },
            "tickers": [{
                "ticker": "TEST",
                "company": "Test Company",
                "market": "US",
                "classification": {
                    "investment_sleeve": "Software & platforms",
                    "stance": "watch",
                    "archetype": "compounder",
                    "analysis_as_of": "2026-07-28",
                },
                "valuation_decision": {
                    "status": "evidence_blocked",
                    "provisional": True,
                    "open_gap_count": 1,
                    "critical_gap_count": 1,
                    "next_gap_id": "revenue_required",
                    "value_per_share": {},
                },
            }],
        }
        migration = (
            ROOT
            / "dashboard"
            / "cloudflare"
            / "migrations"
            / "0001_operational_schema.sql"
        ).read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory(dir=ROOT) as temp_dir:
            temp = Path(temp_dir)
            core_path = temp / "core.json"
            seed_path = temp / "seed.sql"
            core_path.write_text(json.dumps(core), encoding="utf-8")
            exporter.export(core_path, seed_path)
            seed = seed_path.read_text(encoding="utf-8")

            connection = sqlite3.connect(":memory:")
            connection.executescript(migration)
            connection.executescript(seed)
            connection.executescript(seed)

            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM securities").fetchone()[0],
                1,
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM evidence_tasks").fetchone()[0],
                1,
            )
            status = connection.execute(
                "SELECT decision_status FROM valuation_current WHERE ticker = 'TEST'"
            ).fetchone()[0]
            self.assertEqual(status, "evidence_blocked")


if __name__ == "__main__":
    unittest.main()
