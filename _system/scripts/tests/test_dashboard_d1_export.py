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
        migrations_dir = ROOT / "dashboard" / "cloudflare" / "migrations"
        migration = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(migrations_dir.glob("*.sql"))
        )
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
            criticality = connection.execute(
                """
                SELECT direction, criticality_score, quality_state
                FROM criticality_snapshots
                WHERE symbol = 'SPY'
                ORDER BY as_of DESC
                LIMIT 1
                """
            ).fetchone()
            self.assertIsNotNone(criticality)
            self.assertIn(
                criticality[0],
                {"positive_bubble", "negative_bubble", "none"},
            )
            self.assertGreaterEqual(criticality[1], 0)
            self.assertLessEqual(criticality[1], 100)
            self.assertIn(criticality[2], {"ready", "limited"})

    def test_operational_return_uses_only_publishable_canonical_forward_return(self):
        rows = [
            {
                "ticker": "CANON",
                "company": "Canonical",
                "classification": {},
                "valuation_tier": {"tier": 1, "tier_id": "tier_1"},
                "valuation_decision": {
                    "status": "decision_grade",
                    "model_level": "stock_specific",
                    "return_publishable": True,
                    "forward_return_at_price_pct": {"base": 12.5},
                },
            },
            {
                "ticker": "LEGACY",
                "company": "Legacy",
                "classification": {},
                "valuation_decision": {
                    "status": "decision_grade",
                    "model_level": "stock_specific",
                    "return_publishable": True,
                    "annualized_return_at_price_pct": {"base": 88.0},
                },
            },
            {
                "ticker": "SCREEN",
                "company": "Screen",
                "classification": {},
                "valuation_decision": {
                    "status": "decision_grade",
                    "model_level": "screening_grade",
                    "return_publishable": True,
                    "forward_return_at_price_pct": {"base": 33.0},
                },
            },
        ]
        core = {
            "generated_at": "2026-08-28T12:00:00Z",
            "summary": {"holdings": 3},
            "valuation_queue": {"items": []},
            "tickers": rows,
        }
        migration = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted((ROOT / "dashboard" / "cloudflare" / "migrations").glob("*.sql"))
        )
        with tempfile.TemporaryDirectory(dir=ROOT) as temp_dir:
            temp = Path(temp_dir)
            core_path = temp / "core.json"
            seed_path = temp / "seed.sql"
            core_path.write_text(json.dumps(core), encoding="utf-8")
            exporter.export(core_path, seed_path)
            connection = sqlite3.connect(":memory:")
            connection.executescript(migration)
            connection.executescript(seed_path.read_text(encoding="utf-8"))
            observed = dict(connection.execute(
                "SELECT ticker, annualized_return_base_pct FROM valuation_current"
            ).fetchall())
            self.assertEqual(observed["CANON"], 12.5)
            self.assertIsNone(observed["LEGACY"])
            self.assertIsNone(observed["SCREEN"])
            payload = json.loads(connection.execute(
                "SELECT payload_json FROM valuation_current WHERE ticker = 'CANON'"
            ).fetchone()[0])
            self.assertEqual(payload["model_level"], "stock_specific")
            self.assertEqual(payload["valuation_tier"]["tier_id"], "tier_1")


if __name__ == "__main__":
    unittest.main()
