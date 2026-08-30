from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import refresh_valuation_dashboard_rows as refresh


class RefreshValuationDashboardRowsTests(unittest.TestCase):
    def test_served_core_and_detail_shards_receive_current_tier_and_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            (data_dir / "tickers").mkdir()
            core = {"summary": {}, "tickers": [{"ticker": "AAA"}, {"ticker": "BBB"}]}
            (data_dir / "core.json").write_text(json.dumps(core), encoding="utf-8")
            for ticker in ("AAA", "BBB"):
                (data_dir / "tickers" / f"{ticker}.json").write_text(
                    json.dumps({"ticker": ticker, "company": ticker}), encoding="utf-8"
                )

            def attach(row, *, include_detail):
                row["valuation_tier"] = {"tier": 1, "tier_id": "tier_1"}
                row["valuation_decision"] = {
                    "status": "decision_grade",
                    "model_level": "stock_specific",
                    "return_publishable": False,
                    "universe_tier": row["valuation_tier"],
                }
                if include_detail:
                    row["valuation_workbench"] = {"schema_version": "3.0"}
                return True

            with (
                patch.object(refresh, "_attach_current_valuation", side_effect=attach),
                patch.object(refresh, "valuation_queue_summary", return_value={"counts": {"tickers": 0, "evidence_blocked": 0, "critical_gaps": 0}, "items": []}),
                patch.object(refresh, "load_valuation_universe_tiers", return_value={"as_of": "2026-08-30"}),
                patch.object(refresh, "load_power_zones", return_value={"by_ticker": {}}),
            ):
                result = refresh.refresh_served_data(data_dir, ("AAA",))

            self.assertEqual(result, {"core_rows": 1, "ticker_shards": 1})
            current_core = json.loads((data_dir / "core.json").read_text(encoding="utf-8"))
            aaa = next(row for row in current_core["tickers"] if row["ticker"] == "AAA")
            bbb = next(row for row in current_core["tickers"] if row["ticker"] == "BBB")
            self.assertEqual(aaa["valuation_tier"]["tier"], 1)
            self.assertNotIn("valuation_tier", bbb)
            self.assertEqual(current_core["summary"]["valuation_tier_counts"], {"tier_1": 1})
            self.assertEqual(current_core["summary"]["valuation_model_level_counts"], {"stock_specific": 1, "unmodeled": 1})
            detail = json.loads((data_dir / "tickers/AAA.json").read_text(encoding="utf-8"))
            self.assertEqual(detail["valuation_workbench"]["schema_version"], "3.0")
            untouched = json.loads((data_dir / "tickers/BBB.json").read_text(encoding="utf-8"))
            self.assertNotIn("valuation_workbench", untouched)


if __name__ == "__main__":
    unittest.main()
