from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from unittest import mock
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


def write_spx_tab(ssi_root: Path) -> None:
    """The two committed SPX-tab artifacts the risk builder reads, trimmed to
    the fields it uses. Values are lifted from a real 2026-08-21 session."""
    write_json(ssi_root / "dashboard/data/spx_surface_latest.json", {
        "as_of": "2026-08-21",
        "fetch_status": "ok",
        "quality_state": "ok",
        "spot": {"close": 7641.1602, "value": 7641.1602, "iv30_feed": 12.723},
        "tenors": [
            {"dte": 7, "atm_iv": 0.128503, "rr_25d": -0.0319, "bf_25d": 0.000847},
            {"dte": 31, "atm_iv": 0.129211, "rr_25d": -0.0431, "bf_25d": 0.002439},
            {"dte": 91, "atm_iv": 0.148957, "rr_25d": -0.0533, "bf_25d": 0.002993},
        ],
        "dealer_gamma_proxy": {
            "call_gamma_notional": 245438063038.12,
            "put_gamma_notional": 292958073947.38,
            "value": -47520010909.26,
            "contracts_used": 25777,
            "method": "proxy",
            "units": "USD delta change per 1% move in spot",
            "sign_convention": "ASSUMPTION, not an observation.",
            "oi_caveat": "Start-of-day open interest.",
        },
    })
    write_json(ssi_root / "dashboard/data/vol_metrics_latest.json", {
        "as_of": "2026-08-20",
        "quality_state": "ready",
        "coverage": {"rows": 2542},
        "metrics": {
            "vix": {"value": 16.01, "z1y": -0.6462, "pct1y": 25.79, "last_value_date": "2026-08-20"},
            "skew": {"value": 143.23, "z1y": -0.3207, "pct1y": 40.96},
            "slope_vix_3m": {"value": 0.839979, "z1y": -0.6165, "pct1y": 30.92},
            "iv_rv_spread": {"value": 2.8675, "z1y": -0.7531, "pct1y": 27.31},
        },
        "regime": {
            "term_state": "contango", "spx_rv20": 13.1425,
            "iv_rv_spread": 2.8675, "vvix_vix_ratio": 5.612742,
        },
    })


class MarketRiskComponentsTests(unittest.TestCase):
    def test_publish_only_reuses_validated_output_without_rebuilding(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "snapshot.json"
            payload = {
                "generated_at": "2026-08-31T23:00:00Z",
                "source": "test",
                "components": [{"component_id": "x"}],
                "coverage": {"total": 1},
            }
            write_json(output, payload)
            with mock.patch.object(builder, "build", side_effect=AssertionError("rebuilt")), \
                 mock.patch.object(builder, "publish", return_value={"accepted": True}) as publish, \
                 mock.patch.dict("os.environ", {
                     "MARKET_RISK_INGEST_URL": "https://example.test/ingest",
                     "MARKET_RISK_INGEST_TOKEN": "secret",
                 }), \
                 mock.patch.object(sys, "argv", [
                     "build_market_risk_components.py",
                     "--output", str(output),
                     "--publish-only",
                 ]):
                self.assertEqual(builder.main(), 0)
            publish.assert_called_once_with(
                "https://example.test/ingest", "secret", payload
            )

    def test_build_keeps_sources_separate_and_marks_known_gaps(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            etf = base / "etf"
            ls_algo = base / "ls"
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
            write_spx_tab(base / "ssi")
            payload = builder.build(etf, ls_algo, base / "ssi")
            names = {row["component"] for row in payload["components"]}
            self.assertIn("letf_rebalance_close", names)
            self.assertIn("volatility_borrow", names)
            self.assertIn("vix_regime", names)
            self.assertIn("dealer_gamma", names)
            self.assertTrue(any(row["symbol"] == "XLK" and row["scope"] == "sector" for row in payload["components"]))

            # The SPX marks now come off this repo's own SPX tab. Nothing in the
            # payload may cite the spx-0dte trading repository any more.
            self.assertNotIn("spx-0dte", payload["sources"])
            self.assertFalse([row for row in payload["components"]
                              if "spx-0dte" in str(row.get("source") or "")])

            gamma = next(row for row in payload["components"] if row["component"] == "dealer_gamma")
            self.assertNotEqual(gamma["quality_state"], "unavailable")
            self.assertEqual(gamma["net_gamma_notional"], -47520010909.26)
            # Short gamma is the stress reading; long gamma dampens and scores 0.
            self.assertGreater(gamma["score"], 0)

            vix = next(row for row in payload["components"] if row["component"] == "vix_regime")
            self.assertEqual(vix["close"], 16.01)
            self.assertEqual(vix["z1y"], -0.6462)

            stress = next(row for row in payload["components"] if row["component"] == "options_stress")
            self.assertEqual(stress["spx_eod_mark"], 7641.1602)
            self.assertEqual(stress["latest"]["skew_z"], -0.3207)
            self.assertEqual(stress["latest"]["realized_vs_implied_z"], -0.7531)
            self.assertEqual(stress["atm_iv_30d"], 0.129211)
            # Retired with the intraday feed: null, never a look-alike.
            self.assertIsNone(stress["latest"]["straddle_residual_z"])

    def test_an_unhealthy_spx_snapshot_is_refused_rather_than_read(self):
        # A dark feed still writes a well-formed file. Health is read off the
        # payload, so a failed fetch must not reach the component stack.
        with tempfile.TemporaryDirectory() as directory:
            ssi = Path(directory) / "ssi"
            write_spx_tab(ssi)
            surface = json.loads((ssi / "dashboard/data/spx_surface_latest.json").read_text())
            surface["fetch_status"] = "error"
            write_json(ssi / "dashboard/data/spx_surface_latest.json", surface)
            metrics = json.loads((ssi / "dashboard/data/vol_metrics_latest.json").read_text())
            metrics["quality_state"] = "stale"
            write_json(ssi / "dashboard/data/vol_metrics_latest.json", metrics)

            rows = {row["component"]: row for row in builder.build_spx(ssi)}
            self.assertEqual(rows, {})
            payload = builder.build(Path(directory) / "etf", Path(directory) / "ls", ssi)
            for name in ("options_stress", "vix_regime", "dealer_gamma"):
                row = next(item for item in payload["components"] if item["component"] == name)
                self.assertEqual(row["quality_state"], "unavailable")

    def test_business_age_ignores_weekends(self):
        self.assertEqual(builder.business_age("2026-07-31", today=builder.date(2026, 8, 2)), 0)


if __name__ == "__main__":
    unittest.main()
