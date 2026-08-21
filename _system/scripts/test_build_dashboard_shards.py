from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_dashboard_shards as bds  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
INDEX_HTML = ROOT / "dashboard" / "index.html"


def _cv() -> dict:
    """A component_valuation shaped like the real payload."""
    return {
        "status": "provisional",
        "total_equity_value_per_share": {"low": 1, "base": 2, "high": 3},
        "upside_downside_pct": {"base": 0.25},
        "market_price_per_share": 1.75,
        "material_component_count": 2,
        # the detail-pane schedule -- the expensive half
        "economic_value": {"segments": [{"name": "x", "value": 1}] * 20},
        "components": [{"id": "a", "method": "net_asset_value"}] * 12,
        "decision_rule": "a long prose decision rule " * 8,
        "review_status": "committee_open",
        "review_open_count": 3,
    }


class SlimComponentValuationTests(unittest.TestCase):
    def test_detail_only_schedule_is_dropped(self):
        slim = bds._slim_component_valuation(_cv())
        for field in ("economic_value", "components", "decision_rule",
                      "review_status", "review_open_count"):
            self.assertNotIn(field, slim, f"{field} still ships in core.json")

    def test_table_keys_survive(self):
        """These four are what the holdings table reads before any ticker is
        opened. Dropping one renders the value-gap column blank."""
        slim = bds._slim_component_valuation(_cv())
        for field in ("status", "total_equity_value_per_share",
                      "upside_downside_pct", "market_price_per_share"):
            self.assertIn(field, slim, f"{field} is boot-critical and was dropped")

    def test_slim_actually_shrinks_the_row(self):
        full = _cv()
        slim = bds._slim_component_valuation(full)
        self.assertLess(len(json.dumps(slim)), len(json.dumps(full)) / 2)

    def test_every_component_valuation_sort_key_survives_the_slim(self):
        """The binding constraint, asserted against the SPA itself.

        index.html sorts the holdings table on `component_valuation.<field>`
        paths. Sorting happens before any shard loads, so a sort key whose field
        this function drops silently sorts every row as equal. Adding such a
        sort key must fail here rather than in the browser.
        """
        if not INDEX_HTML.exists():                      # pragma: no cover
            self.skipTest("dashboard/index.html not present")
        html = INDEX_HTML.read_text(encoding="utf-8", errors="ignore")
        referenced = set(re.findall(r"component_valuation\.([A-Za-z0-9_]+)", html))
        self.assertTrue(referenced, "expected index.html to sort on component_valuation")
        dropped = referenced & set(bds._COMPONENT_VALUATION_DETAIL_ONLY)
        self.assertEqual(
            dropped, set(),
            f"index.html sorts on component_valuation.{sorted(dropped)}"
            " but the core slim drops it -- the column would sort every row as equal",
        )


class SlimTickerRowTests(unittest.TestCase):
    def test_row_slim_applies_component_valuation(self):
        row = {"ticker": "T", "component_valuation": _cv()}
        slim = bds.slim_ticker_row(row)
        self.assertIn("component_valuation", slim)
        self.assertNotIn("economic_value", slim["component_valuation"])
        self.assertIn("upside_downside_pct", slim["component_valuation"])

    def test_row_without_component_valuation_is_untouched(self):
        slim = bds.slim_ticker_row({"ticker": "T"})
        self.assertNotIn("component_valuation", slim)


if __name__ == "__main__":
    unittest.main()
