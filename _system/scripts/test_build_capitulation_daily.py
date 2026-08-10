#!/usr/bin/env python3
"""Tests for the always-on daily capitulation model.

The central claim under test is that ``build_capitulation_daily`` did NOT fork
the intraday model's math: every score, confirmation and ladder threshold must
come from ``criticality.flow_stress``. So the assertions compare against the
IMPORTED function and the IMPORTED ``STATE_RANK``, never against a hardcoded
copy of a weight or a threshold.
"""
from __future__ import annotations

import json
import math
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_capitulation_daily as bcd  # noqa: E402
from criticality.flow_stress import (  # noqa: E402
    STATE_RANK,
    apply_state_hysteresis,
    calculate_flow_snapshot,
)


def bars(
    count: int = 200,
    *,
    selloff: bool = False,
    crash: int = 12,
    volume_multiple: float = 6.0,
    spread: float = 0.02,
    offset_days: int = 0,
) -> list[dict]:
    """Synthetic daily OHLCV bars; ``selloff`` tacks a violent decline on the end."""
    start = date(2025, 9, 1) + timedelta(days=offset_days)
    price = 100.0
    rows = []
    for index in range(count):
        panicking = selloff and index >= count - crash
        change = 0.0005 + math.sin(index / 7.0) * 0.002 + (-0.035 if panicking else 0.0)
        open_price = price
        price *= 1.0 + change
        width = 0.004 + (spread if panicking else 0.0)
        rows.append(
            {
                "date": (start + timedelta(days=index)).isoformat(),
                "open": open_price,
                "high": max(open_price, price) * (1 + width),
                "low": min(open_price, price) * (1 - width),
                "close": price,
                "volume": 1_000_000
                * (1 + 0.002 * index)
                * (volume_multiple if panicking else 1.0),
            }
        )
    return rows


class NoForkedMathTest(unittest.TestCase):
    """The daily model must be the intraday model, not a lookalike."""

    def test_scores_and_confirmations_match_flow_stress_exactly(self):
        for label, series in (
            ("calm", bars()),
            ("selloff", bars(selloff=True)),
            ("short_crash", bars(selloff=True, crash=3)),
        ):
            with self.subTest(series=label):
                snapshot = calculate_flow_snapshot(
                    "SPY",
                    series,
                    scope="market",
                    source=bcd.SOURCE,
                    entitlement_mode="eod",
                )
                row = bcd.calculate_symbol("SPY", series, None)["row"]
                self.assertEqual(row["pressure"], snapshot["scores"]["pressure"])
                self.assertEqual(row["panic"], snapshot["scores"]["panic"])
                self.assertEqual(row["exhaustion"], snapshot["scores"]["exhaustion"])
                self.assertEqual(row["confirmations"], snapshot["confirmation"])
                self.assertEqual(
                    row["confirmation_count"],
                    sum(bool(value) for value in snapshot["confirmation"].values()),
                )
                self.assertEqual(row["features"], snapshot["features"])
                self.assertEqual(row["as_of"], snapshot["as_of"])

    def test_state_ladder_reproduces_flow_stress(self):
        for label, series in (
            ("calm", bars()),
            ("selloff", bars(selloff=True)),
            ("short_crash", bars(selloff=True, crash=3)),
            ("one_day_gap", bars(selloff=True, crash=1, volume_multiple=12.0, spread=0.05)),
        ):
            with self.subTest(series=label):
                snapshot = calculate_flow_snapshot("SPY", series)
                row = bcd.calculate_symbol("SPY", series, None)["row"]
                self.assertEqual(row["raw_state"], snapshot["raw_state"])
                self.assertEqual(row["raw_state_rank"], STATE_RANK[snapshot["raw_state"]])
                self.assertEqual(row["state_rank"], STATE_RANK[row["state"]])

    def test_module_carries_no_copy_of_the_ladder_thresholds(self):
        source = (SCRIPTS / "build_capitulation_daily.py").read_text(encoding="utf-8")
        code = "\n".join(
            line for line in source.splitlines() if not line.lstrip().startswith("#")
        )
        code = code.split('"""', 2)[-1]  # drop the module docstring
        for state in STATE_RANK:
            if state in ("normal", "stress"):
                continue  # named in payload/gate wiring, not as a threshold
            self.assertNotIn(
                f'"{state}"',
                code,
                f"{state} is decided by flow_stress; do not re-derive it here",
            )
        self.assertIn("MEANINGFUL_MIN_RANK", code)

    def test_meaningful_gate_is_derived_from_the_imported_ladder(self):
        self.assertEqual(bcd.MEANINGFUL_MIN_RANK, STATE_RANK["stress"])


class ExhaustionMeaningTest(unittest.TestCase):
    """The single most important honesty property of the model."""

    def test_low_panic_makes_exhaustion_not_meaningful(self):
        meaningful, reason = bcd.exhaustion_meaning("normal", 34.6, -22.0, True)
        self.assertFalse(meaningful)
        self.assertIn("panic", reason)
        meaningful, reason = bcd.exhaustion_meaning("observe", 61.0, -30.0, True)
        self.assertFalse(meaningful)
        self.assertIn("stress threshold", reason)

    def test_high_panic_in_drawdown_is_meaningful(self):
        meaningful, reason = bcd.exhaustion_meaning("stress", 86.2, -18.0, True)
        self.assertTrue(meaningful)
        self.assertIn("cleared", reason)
        meaningful, _ = bcd.exhaustion_meaning("confirmed_exhaustion", 92.0, -25.0, True)
        self.assertTrue(meaningful)

    def test_high_panic_at_the_highs_is_not_capitulation(self):
        meaningful, reason = bcd.exhaustion_meaning("stress", 88.0, -1.2, False)
        self.assertFalse(meaningful)
        self.assertIn("no selloff to capitulate from", reason)

    def test_calm_tape_near_highs_never_publishes_meaningful_exhaustion(self):
        row = bcd.calculate_symbol("SPY", bars(), None)["row"]
        self.assertGreater(row["exhaustion"], 40.0)  # the nonsense reading today
        self.assertLess(STATE_RANK[row["raw_state"]], STATE_RANK["stress"])
        self.assertFalse(row["in_drawdown"])
        self.assertFalse(row["exhaustion_meaningful"])
        self.assertTrue(row["exhaustion_meaningful_reason"])

    def test_selloff_publishes_meaningful_exhaustion(self):
        row = bcd.calculate_symbol("SPY", bars(selloff=True), None)["row"]
        self.assertGreaterEqual(STATE_RANK[row["raw_state"]], STATE_RANK["stress"])
        self.assertTrue(row["in_drawdown"])
        self.assertTrue(row["exhaustion_meaningful"])


class DrawdownTest(unittest.TestCase):
    def _series(self, closes):
        start = date(2025, 1, 1)
        return [
            {
                "date": (start + timedelta(days=index)).isoformat(),
                "open": value,
                "high": value,
                "low": value,
                "close": value,
                "volume": 1_000.0,
            }
            for index, value in enumerate(closes)
        ]

    def test_drawdown_from_trailing_high(self):
        closes = [100.0, 110.0, 120.0, 200.0, 180.0, 160.0, 150.0]
        context = bcd.drawdown_context(self._series(closes))
        self.assertEqual(context["drawdown_pct"], -25.0)
        self.assertEqual(context["days_since_high"], 3)
        self.assertTrue(context["in_drawdown"])
        self.assertEqual(context["drawdown_window_sessions"], 7)

    def test_at_the_high_is_not_a_drawdown(self):
        context = bcd.drawdown_context(self._series([100.0, 110.0, 120.0]))
        self.assertEqual(context["drawdown_pct"], 0.0)
        self.assertEqual(context["days_since_high"], 0)
        self.assertFalse(context["in_drawdown"])

    def test_shallow_dip_is_below_the_threshold(self):
        context = bcd.drawdown_context(self._series([100.0, 100.0, 98.0]))
        self.assertEqual(context["drawdown_pct"], -2.0)
        self.assertFalse(context["in_drawdown"])

    def test_window_only_looks_back_the_configured_sessions(self):
        closes = [500.0] + [100.0] * 300
        context = bcd.drawdown_context(self._series(closes), window=10)
        self.assertEqual(context["drawdown_pct"], 0.0)
        self.assertEqual(context["drawdown_window_sessions"], 10)
        wide = bcd.drawdown_context(self._series(closes), window=400)
        self.assertEqual(wide["drawdown_pct"], -80.0)


class HysteresisTest(unittest.TestCase):
    def test_dwell_matches_flow_stress_and_persists_across_runs(self):
        first = bars(selloff=True)
        second = bars(selloff=True, offset_days=1)
        raw = calculate_flow_snapshot("SPY", first)["raw_state"]
        self.assertNotEqual(raw, "normal")

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            series = {0: first, 1: second}
            call = {"n": 0}

            def fetcher(symbol):
                index = min(call["n"], 1)
                return series[index]

            call["n"] = 0
            run_one = bcd.build(output_dir=out, fetcher=fetcher, symbols={"SPY"}, workers=1)
            expected_one, memory = apply_state_hysteresis(raw, None)
            self.assertEqual(run_one["payload"]["market"]["state"], expected_one)
            self.assertEqual(run_one["payload"]["market"]["raw_state"], raw)
            self.assertTrue((out / bcd.STATE_NAME).exists())
            stored = json.loads((out / bcd.STATE_NAME).read_text(encoding="utf-8"))
            self.assertEqual(stored["symbols"]["SPY"]["count"], memory["count"])
            self.assertEqual(stored["symbols"]["SPY"]["as_of"], first[-1]["date"])

            call["n"] = 1
            run_two = bcd.build(output_dir=out, fetcher=fetcher, symbols={"SPY"}, workers=1)
            expected_two, _ = apply_state_hysteresis(raw, memory)
            self.assertEqual(run_two["payload"]["market"]["state"], expected_two)
            self.assertEqual(expected_two, raw)  # second observation promotes

    def test_rerun_on_the_same_session_does_not_walk_the_ladder_twice(self):
        series = bars(selloff=True)
        raw = calculate_flow_snapshot("SPY", series)["raw_state"]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            first = bcd.build(
                output_dir=out, fetcher=lambda symbol: series, symbols={"SPY"}, workers=1
            )
            again = bcd.build(
                output_dir=out, fetcher=lambda symbol: series, symbols={"SPY"}, workers=1
            )
            self.assertEqual(
                first["payload"]["market"]["state"], again["payload"]["market"]["state"]
            )
            self.assertNotEqual(again["payload"]["market"]["state"], raw)


class FailurePolicyTest(unittest.TestCase):
    def test_fetch_failure_preserves_prior_row_and_marks_stale(self):
        series = bars(selloff=True)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            good = bcd.build(
                output_dir=out, fetcher=lambda symbol: series, symbols={"SPY"}, workers=1
            )
            prior = good["payload"]["market"]

            def broken(symbol):
                raise RuntimeError("yahoo 503")

            after = bcd.build(
                output_dir=out, fetcher=broken, symbols={"SPY"}, workers=1
            )
            market = after["payload"]["market"]
            self.assertEqual(market["panic"], prior["panic"])
            self.assertEqual(market["as_of"], prior["as_of"])
            self.assertEqual(market["quality_state"], "stale")
            self.assertEqual(market["fetch_status"], "preserved_after_fetch_failure")
            self.assertIn("yahoo 503", market["fetch_error"])
            self.assertEqual(after["payload"]["quality_state"], "stale")
            self.assertEqual(after["payload"]["coverage"]["symbols_failed"], 1)
            self.assertEqual(after["payload"]["coverage"]["symbols_ok"], 0)
            self.assertIn("SPY", after["payload"]["coverage"]["failures"])

    def test_total_failure_with_no_prior_still_writes_a_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)

            def broken(symbol):
                raise RuntimeError("no network")

            result = bcd.build(output_dir=out, fetcher=broken, symbols={"SPY"}, workers=1)
            self.assertEqual(result["payload"]["quality_state"], "unavailable")
            self.assertIsNone(result["payload"]["market"])
            self.assertTrue((out / bcd.OUTPUT_NAME).exists())


class HistoryTest(unittest.TestCase):
    def test_history_is_idempotent_by_date(self):
        series = bars(selloff=True)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            for _ in range(3):
                bcd.build(
                    output_dir=out, fetcher=lambda symbol: series, symbols={"SPY"}, workers=1
                )
            lines = [
                line
                for line in (out / bcd.HISTORY_NAME).read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(lines), 1)
            row = json.loads(lines[0])
            self.assertEqual(row["date"], series[-1]["date"])
            self.assertEqual(row["symbol"], "SPY")

            later = bars(selloff=True, offset_days=1)
            bcd.build(
                output_dir=out, fetcher=lambda symbol: later, symbols={"SPY"}, workers=1
            )
            dates = [
                json.loads(line)["date"]
                for line in (out / bcd.HISTORY_NAME).read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(dates, sorted(dates))
            self.assertEqual(len(dates), 2)

    def test_merge_history_upserts_rather_than_appends(self):
        prior = [{"date": "2026-08-05", "panic": 10.0}, {"date": "2026-08-06", "panic": 20.0}]
        merged = bcd.merge_history(prior, {"date": "2026-08-06", "panic": 99.0})
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[-1]["panic"], 99.0)


class PayloadShapeTest(unittest.TestCase):
    def test_dry_run_writes_nothing(self):
        series = bars()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            bcd.build(
                output_dir=out,
                fetcher=lambda symbol: series,
                symbols={"SPY"},
                workers=1,
                dry_run=True,
            )
            self.assertFalse((out / bcd.OUTPUT_NAME).exists())
            self.assertFalse((out / bcd.HISTORY_NAME).exists())
            self.assertFalse((out / bcd.STATE_NAME).exists())

    def test_sectors_sort_by_state_rank_then_panic(self):
        calm = bars()
        stressed = bars(selloff=True)
        loud = bars(selloff=True, crash=3)

        def fetcher(symbol):
            if symbol == "XLK":
                return loud
            if symbol == "XLE":
                return stressed
            return calm

        with tempfile.TemporaryDirectory() as tmp:
            result = bcd.build(
                output_dir=Path(tmp),
                fetcher=fetcher,
                symbols={"XLK", "XLE", "XLU", "SPY"},
                workers=1,
            )
            sectors = result["payload"]["sectors"]
            self.assertEqual([row["symbol"] for row in sectors], ["XLK", "XLE", "XLU"])
            keys = [(row["state_rank"], row["panic"]) for row in sectors]
            self.assertEqual(keys, sorted(keys, reverse=True))

    def test_payload_contract(self):
        series = bars()
        with tempfile.TemporaryDirectory() as tmp:
            result = bcd.build(
                output_dir=Path(tmp),
                fetcher=lambda symbol: series,
                symbols={"SPY", "XLK"},
                workers=1,
            )
            payload = result["payload"]
            for key in (
                "schema_version",
                "generated_at",
                "model_version",
                "research_only",
                "as_of",
                "cadence",
                "basis",
                "market",
                "symbols",
                "sectors",
                "coverage",
                "quality_state",
            ):
                self.assertIn(key, payload)
            self.assertEqual(payload["model_version"], "capitulation-daily-v1")
            self.assertEqual(payload["cadence"], "daily")
            self.assertTrue(payload["research_only"])
            self.assertIn("daily bars (Yahoo)", payload["basis"])
            market = payload["market"]
            for key in (
                "symbol",
                "state",
                "state_rank",
                "pressure",
                "panic",
                "exhaustion",
                "exhaustion_meaningful",
                "exhaustion_meaningful_reason",
                "confirmations",
                "confirmation_count",
                "drawdown_pct",
                "days_since_high",
                "in_drawdown",
            ):
                self.assertIn(key, market)
            self.assertEqual(market["symbol"], "SPY")
            self.assertEqual(len(market["confirmations"]), 5)
            # The intraday vol-target block depends on the minute annualization
            # constant and is deliberately absent rather than reinterpreted.
            self.assertNotIn("vol_target", market)

    def test_universe_matches_the_flow_monitor(self):
        expected = {
            "SPY", "QQQ", "IWM", "DIA", "EWJ", "VXX", "HYG", "LQD", "TLT", "UUP",
            "EFA", "EEM",
            "XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV",
            "XLY",
        }
        self.assertEqual(set(bcd.UNIVERSE), expected)
        self.assertEqual(len(bcd.SECTORS), 11)


if __name__ == "__main__":
    unittest.main()
