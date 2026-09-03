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
            changes_before_repeat = connection.total_changes
            connection.executescript(seed)

            self.assertEqual(connection.total_changes, changes_before_repeat)

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

            for static_only_table in (
                "price_observations",
                "ohlcv_observations",
                "technical_snapshots",
                "capitulation_snapshots",
                "market_context_snapshots",
                "market_structure_snapshots",
            ):
                self.assertNotIn(f"INSERT INTO {static_only_table}", seed)
                self.assertIsNone(
                    connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                        (static_only_table,),
                    ).fetchone()
                )

    def test_export_writes_contract_v3_fields_and_only_canonical_forward_return(self):
        core = {
            "generated_at": "2026-08-30T12:00:00Z",
            "summary": {"holdings": 1},
            "valuation_queue": {"items": []},
            "tickers": [{
                "ticker": "READY",
                "company": "Ready Company",
                "market": "US",
                "classification": {"stance": "watch", "analysis_as_of": "2026-08-30"},
                "valuation_tier": {"tier": 1, "tier_id": "tier_1"},
                "valuation_decision": {
                    "status": "decision_grade",
                    "provisional": False,
                    "model_level": "stock_specific",
                    "output_basis": "future_payoff",
                    "price_per_share": 80,
                    "value_per_share": {"low": 90, "base": 100, "high": 110},
                    "present_value_today_per_share": {"low": 90, "base": 100, "high": 110},
                    "margin_of_safety_pct": {"low": 11.11, "base": 20, "high": 27.27},
                    "forward_return_at_price_pct": {"low": 6, "base": 12, "high": 18},
                    "annualized_return_at_price_pct": {"low": 6, "base": 12, "high": 18},
                    "forward_return_status": "available",
                    "required_return_pct": 10,
                    "return_publishable": True,
                    "dates": {
                        "model_as_of": "2026-08-30",
                        "latest_fact_as_of": "2026-08-20",
                        "price_as_of": "2026-08-29",
                    },
                    "open_gap_count": 0,
                    "critical_gap_count": 0,
                },
            }],
        }
        migration = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted((ROOT / "dashboard/cloudflare/migrations").glob("*.sql"))
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
            row = connection.execute(
                """
                SELECT model_level, output_basis, present_value_base,
                       margin_of_safety_base_pct, forward_return_base_pct,
                       annualized_return_base_pct, required_return_pct,
                       return_publishable, valuation_tier, model_as_of,
                       latest_fact_as_of, price_as_of
                FROM valuation_current WHERE ticker = 'READY'
                """
            ).fetchone()
            self.assertEqual(
                row,
                (
                    "stock_specific", "future_payoff", 100.0, 20.0, 12.0,
                    12.0, 10.0, 1, 1, "2026-08-30", "2026-08-20", "2026-08-29",
                ),
            )


if __name__ == "__main__":
    unittest.main()
