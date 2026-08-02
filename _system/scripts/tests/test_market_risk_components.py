from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_market_risk_components as builder


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


class MarketRiskComponentsTests(unittest.TestCase):
    def test_build_keeps_sources_separate_and_marks_known_gaps(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            etf = base / "etf"
            ls_algo = base / "ls"
            spx = base / "spx"
            write_json(etf / "data/letf_rebalance_flows_latest.json", {
                "latest_date": "2026-07-31", "method": "test",
                "by_underlying": {
                    "SPY": {"underlying": "SPY", "date": "2026-07-31", "net_moc_dollars": -100,
                            "gross_moc_dollars": 100, "net_moc_pct_auction_volume": -0.5,
                            "abs_net_moc_pctile_60d": 0.9},
                    "XLK": {"underlying": "XLK", "date": "2026-07-31", "net_moc_dollars": -40,
                            "gross_moc_dollars": 40, "net_moc_pct_auction_volume": -0.2,
                            "abs_net_moc_pctile_60d": 0.8},
                },
            })
            write_json(etf / "data/etf_holdings_latest.json", {
                "latest_date": "2026-07-31", "by_symbol": {"SPXL": [{
                    "as_of_date": "2026-07-31", "security_type": "SWAP", "source": "issuer",
                }]},
            })
            write_csv(ls_algo / "data/etf_screened_today.csv", [{
                "ETF": "SPXL", "Underlying": "SPY", "asof_date": "2026-07-31", "Delta": "3",
                "borrow_fee_annual": "0.01", "borrow_spiking": "False", "und_rv_20d_daily_annual": "0.2",
                "und_rv_20d_pctile": "0.7", "high_intraday_risk": "False", "purgatory": "False",
            }])
            write_csv(spx / "data/calendar/vix_daily.csv", [{
                "date": "2026-07-31", "open": "18", "high": "20", "low": "16",
                "close": "17", "prior_close": "18",
            }])
            payload = builder.build(etf, ls_algo, spx, base / "ssi")
            names = {row["component"] for row in payload["components"]}
            self.assertIn("letf_rebalance_close", names)
            self.assertIn("volatility_borrow", names)
            self.assertIn("vix_regime", names)
            self.assertIn("dealer_gamma", names)
            self.assertTrue(any(row["symbol"] == "XLK" and row["scope"] == "sector" for row in payload["components"]))
            gamma = next(row for row in payload["components"] if row["component"] == "dealer_gamma")
            self.assertEqual(gamma["quality_state"], "unavailable")

    def test_business_age_ignores_weekends(self):
        self.assertEqual(builder.business_age("2026-07-31", today=builder.date(2026, 8, 2)), 0)


if __name__ == "__main__":
    unittest.main()
