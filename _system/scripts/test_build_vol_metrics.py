#!/usr/bin/env python3
"""Tests for build_vol_metrics.py (stdlib only, ASCII output)."""
from __future__ import annotations

import json
import math
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_vol_metrics as bvm  # noqa: E402


def trading_dates(count: int, start: date = date(2020, 1, 1)) -> list:
    """Weekday-only date strings; enough for a deterministic fixture."""
    out = []
    cursor = start
    while len(out) < count:
        if cursor.weekday() < 5:
            out.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return out


def synthetic_level(index: int, base: float, amplitude: float, period: float) -> float:
    """Deterministic, non-degenerate, no RNG."""
    return base + amplitude * math.sin(index / period) + 0.01 * (index % 7)


def make_fetcher(dates: list, *, vix1d_from: int = 0, failing: set | None = None):
    failing = failing or set()
    specs = {
        "^VIX": (16.0, 5.0, 37.0),
        "^VIX9D": (14.5, 5.5, 29.0),
        "^VIX3M": (19.0, 4.0, 41.0),
        "^VIX6M": (21.0, 3.5, 53.0),
        "^VIX1D": (10.0, 4.5, 23.0),
        "^VVIX": (95.0, 15.0, 31.0),
        "^SKEW": (130.0, 10.0, 47.0),
        "^MOVE": (75.0, 12.0, 43.0),
        "^GSPC": (5000.0, 300.0, 61.0),
    }

    def fetcher(symbol: str) -> dict:
        if symbol in failing:
            raise RuntimeError(f"synthetic fetch failure for {symbol}")
        base, amplitude, period = specs[symbol]
        first = vix1d_from if symbol == "^VIX1D" else 0
        return {
            day: synthetic_level(index, base, amplitude, period)
            for index, day in enumerate(dates)
            if index >= first
        }

    return fetcher


class ZScoreMathTests(unittest.TestCase):
    def test_hand_computed_zscore_on_1_to_30(self):
        # 1..30: mean = 15.5; sample variance = n(n^2-1)/12/(n-1) = 30*899/12/29 = 77.5
        window = [float(value) for value in range(1, 31)]
        expected = (30.0 - 15.5) / math.sqrt(77.5)
        self.assertAlmostEqual(bvm.trailing_zscore(window), expected, places=12)
        self.assertAlmostEqual(expected, 1.6470893, places=6)

    def test_hand_computed_zscore_small_window(self):
        # [2,4,4,4,5,5,7,9]: mean 5, sum sq dev 32, sample sd = sqrt(32/7)
        window = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]
        expected = (9.0 - 5.0) / math.sqrt(32.0 / 7.0)
        self.assertAlmostEqual(
            bvm.trailing_zscore(window, min_observations=5), expected, places=12
        )
        self.assertAlmostEqual(expected, 1.8708287, places=6)

    def test_window_includes_nulls_without_breaking(self):
        window = [None] * 5 + [float(value) for value in range(1, 31)]
        expected = (30.0 - 15.5) / math.sqrt(77.5)
        self.assertAlmostEqual(bvm.trailing_zscore(window), expected, places=12)

    def test_percentile_rank(self):
        window = [float(value) for value in range(1, 31)]
        self.assertAlmostEqual(bvm.trailing_percentile(window), 100.0, places=12)
        window[-1] = 15.5
        # 15 values are <= 15.5 (1..15) plus itself = 16 of 30
        self.assertAlmostEqual(bvm.trailing_percentile(window), 100.0 * 16 / 30, places=12)


class GuardTests(unittest.TestCase):
    def test_insufficient_window_yields_null_not_zero(self):
        window = [float(value) for value in range(1, 30)]  # 29 observations
        self.assertIsNone(bvm.trailing_zscore(window))
        self.assertIsNone(bvm.trailing_percentile(window))
        self.assertEqual(len(window), 29)

    def test_exactly_thirty_observations_is_enough(self):
        window = [float(value) for value in range(1, 31)]
        self.assertIsNotNone(bvm.trailing_zscore(window))

    def test_zero_stdev_yields_null_not_zero(self):
        window = [7.0] * 40
        result = bvm.trailing_zscore(window)
        self.assertIsNone(result)
        self.assertNotEqual(result, 0.0)

    def test_missing_current_value_yields_null(self):
        window = [float(value) for value in range(1, 31)] + [None]
        self.assertIsNone(bvm.trailing_zscore(window))
        self.assertIsNone(bvm.trailing_percentile(window))

    def test_rolling_series_nulls_are_none_not_zero(self):
        series = [float(value) for value in range(1, 41)]
        rolled = bvm.rolling_zscores(series, window=252)
        self.assertTrue(all(item is None for item in rolled[:29]))
        self.assertIsNotNone(rolled[29])

    def test_completed_session_cutoff_excludes_an_open_us_session(self):
        now = datetime(2026, 8, 12, 19, 50, tzinfo=timezone.utc)  # 15:50 New York
        self.assertEqual(bvm.completed_session_cutoff(now), "2026-08-11")

    def test_completed_session_cutoff_includes_a_finished_us_session(self):
        now = datetime(2026, 8, 12, 23, 0, tzinfo=timezone.utc)  # 19:00 New York
        self.assertEqual(bvm.completed_session_cutoff(now), "2026-08-12")

    def test_completed_session_cutoff_rolls_weekend_to_friday(self):
        now = datetime(2026, 8, 16, 16, 0, tzinfo=timezone.utc)  # Sunday
        self.assertEqual(bvm.completed_session_cutoff(now), "2026-08-14")


class TrailingPropertyTests(unittest.TestCase):
    def test_zscores_do_not_change_when_later_rows_are_appended(self):
        series = [synthetic_level(index, 16.0, 5.0, 37.0) for index in range(400)]
        short = bvm.rolling_zscores(series[:250], window=252)
        long = bvm.rolling_zscores(series, window=252)
        self.assertEqual(short, long[:250])
        short_pct = bvm.rolling_percentiles(series[:250], window=252)
        long_pct = bvm.rolling_percentiles(series, window=252)
        self.assertEqual(short_pct, long_pct[:250])

    def test_row_zscores_stable_across_history_growth(self):
        dates = trading_dates(400)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            short_rows = bvm.build(
                output_dir=out,
                fetcher=make_fetcher(dates[:300]),
                dry_run=True,
                components_path=out / "missing.json",
            )["rows"]
            long_rows = bvm.build(
                output_dir=out,
                fetcher=make_fetcher(dates),
                dry_run=True,
                components_path=out / "missing.json",
            )["rows"]
        long_by_date = {row["date"]: row for row in long_rows}
        for row in short_rows:
            counterpart = long_by_date[row["date"]]
            for key in bvm.METRIC_KEYS:
                for suffix in ("_z1y", "_z5y", "_pct1y"):
                    field = key + suffix
                    self.assertEqual(
                        row[field], counterpart[field], f"{field} changed on {row['date']}"
                    )


class RealizedVolTests(unittest.TestCase):
    def test_alternating_log_returns(self):
        step = 0.01
        closes = [100.0 * (math.exp(step) if index % 2 else 1.0) for index in range(21)]
        series = bvm.realized_vol_series(closes, window=20)
        self.assertTrue(all(item is None for item in series[:20]))
        # 20 returns: ten +step and ten -step -> mean 0, sample sd = step*sqrt(20/19)
        expected = step * math.sqrt(20.0 / 19.0) * math.sqrt(252) * 100.0
        self.assertAlmostEqual(series[20], expected, places=8)
        self.assertAlmostEqual(expected, 16.2869014, places=6)

    def test_constant_series_is_zero_vol(self):
        closes = [100.0] * 30
        series = bvm.realized_vol_series(closes, window=20)
        self.assertAlmostEqual(series[29], 0.0, places=12)

    def test_short_series_is_null(self):
        series = bvm.realized_vol_series([100.0] * 15, window=20)
        self.assertTrue(all(item is None for item in series))

    def test_iv_rv_spread_matches_vix_minus_rv(self):
        dates = trading_dates(120)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            rows = bvm.build(
                output_dir=out,
                fetcher=make_fetcher(dates),
                dry_run=True,
                components_path=out / "missing.json",
            )["rows"]
        row = rows[-1]
        self.assertAlmostEqual(
            row["iv_rv_spread"], round(row["vix"] - row["spx_rv20"], 4), places=6
        )
        self.assertAlmostEqual(row["slope_vix_3m"], row["vix"] / row["vix3m"], places=5)


class SourceHealingTests(unittest.TestCase):
    def test_short_yahoo_tail_repairs_a_truncated_long_range(self):
        long_range = {"2026-07-17": 70.88}
        recent_tail = {
            "2026-07-17": 70.88,
            "2026-07-20": 72.10,
            "2026-08-11": 77.92,
        }
        with mock.patch.object(
            bvm, "_fetch_yahoo_close_series", side_effect=[long_range, recent_tail]
        ), mock.patch.object(
            bvm, "fetch_cnbc_move_latest", return_value={"2026-08-11": 77.92}
        ), mock.patch.object(
            bvm, "read_move_repair_series", return_value={}
        ):
            actual = bvm.fetch_close_series("^MOVE")
        self.assertEqual(actual, recent_tail)

    def test_cboe_source_recovers_when_both_yahoo_windows_fail(self):
        official = {"2026-08-10": 15.46, "2026-08-11": 15.28}
        with mock.patch.object(
            bvm, "_fetch_yahoo_close_series", side_effect=RuntimeError("Yahoo unavailable")
        ), mock.patch.object(
            bvm, "fetch_cboe_close_series", return_value=official
        ):
            actual = bvm.fetch_close_series("^VIX")
        self.assertEqual(actual, official)

    def test_cboe_csv_parser_accepts_ohlc_and_single_value_files(self):
        samples = {
            "^VIX": b"DATE,OPEN,HIGH,LOW,CLOSE\n08/11/2026,15.42,15.61,15.23,15.28\n",
            "^VVIX": "DATE,VVIX\n08/11/2026,90.90\n",
        }
        for symbol, payload in samples.items():
            with self.subTest(symbol=symbol), mock.patch.object(
                bvm, "_request", return_value=payload
            ):
                actual = bvm.fetch_cboe_close_series(symbol)
            self.assertEqual(actual["2026-08-11"], 15.28 if symbol == "^VIX" else 90.90)

    def test_partial_recovery_merges_with_committed_history(self):
        prior_row = {"date": "2026-08-10"}
        prior_row.update({key: 10.0 for key in bvm.FETCH_KEYS})
        prior = [prior_row]

        def latest_only(_symbol):
            return {"2026-08-11": 11.0}

        series_map, stale, failed = bvm.collect_series(latest_only, prior)
        self.assertEqual(series_map["move"], {"2026-08-10": 10.0, "2026-08-11": 11.0})
        self.assertEqual(stale, {})
        self.assertEqual(failed, {})

    def test_move_repair_file_is_an_auditable_date_value_overlay(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "move.csv"
            path.write_text(
                "date,close,source_url,retrieved_at\n"
                "2026-07-20,72.66,https://example.test,2026-08-12\n",
                encoding="utf-8",
            )
            actual = bvm.read_move_repair_series(path)
        self.assertEqual(actual, {"2026-07-20": 72.66})


class PreserveOnFetchFailureTests(unittest.TestCase):
    def test_failed_symbol_preserves_prior_rows_and_marks_stale(self):
        dates = trading_dates(300)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            components = out / "missing.json"
            first = bvm.build(
                output_dir=out, fetcher=make_fetcher(dates), components_path=components
            )
            self.assertEqual(first["latest"]["quality_state"], "ready")
            baseline = {row["date"]: row["vvix"] for row in first["rows"]}

            second = bvm.build(
                output_dir=out,
                fetcher=make_fetcher(dates, failing={"^VVIX"}),
                components_path=components,
            )

        latest = second["latest"]
        self.assertEqual(latest["quality_state"], "stale")
        self.assertIn("^VVIX", latest["coverage"]["symbols_stale"])
        self.assertNotIn("^VVIX", latest["coverage"]["symbols_ok"])
        self.assertIn("^VIX", latest["coverage"]["symbols_ok"])
        detail = latest["coverage"]["stale_detail"]["^VVIX"]
        self.assertEqual(detail["fetch_status"], "preserved_after_fetch_failure")
        self.assertEqual(detail["preserved_rows"], len(dates))

        for row in second["rows"]:
            self.assertEqual(row["quality_state"], "stale")
            self.assertEqual(row["stale_metrics"], ["vvix"])
            self.assertEqual(row["fetch_status"], "preserved_after_fetch_failure")
            self.assertEqual(row["vvix"], baseline[row["date"]])
        # the preserved column still produces the same z-scores it did when fresh
        self.assertEqual(
            second["rows"][-1]["vvix_z1y"], first["rows"][-1]["vvix_z1y"]
        )
        # an unaffected metric is untouched
        self.assertEqual(second["rows"][-1]["vix_z1y"], first["rows"][-1]["vix_z1y"])

    def test_failure_without_prior_history_is_null_not_invented(self):
        dates = trading_dates(120)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            result = bvm.build(
                output_dir=out,
                fetcher=make_fetcher(dates, failing={"^MOVE"}),
                components_path=out / "missing.json",
            )
        latest = result["latest"]
        self.assertEqual(latest["quality_state"], "stale")
        self.assertIn("^MOVE", latest["coverage"]["symbols_stale"])
        self.assertEqual(
            latest["coverage"]["unavailable_detail"]["^MOVE"]["fetch_status"],
            "failed_no_prior_history",
        )
        self.assertIsNone(latest["metrics"]["move"]["value"])
        self.assertIsNone(latest["metrics"]["move"]["z1y"])
        self.assertIsNotNone(latest["metrics"]["vix"]["value"])


class ShortHistoryTests(unittest.TestCase):
    def test_vix1d_short_history_does_not_corrupt_other_metrics(self):
        dates = trading_dates(400)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            components = out / "missing.json"
            with_vix1d = bvm.build(
                output_dir=out,
                fetcher=make_fetcher(dates, vix1d_from=350),
                dry_run=True,
                components_path=components,
            )["rows"]
            without_vix1d = bvm.build(
                output_dir=out,
                fetcher=make_fetcher(dates, failing={"^VIX1D"}),
                dry_run=True,
                components_path=components,
            )["rows"]

        self.assertEqual(len(with_vix1d), len(dates))
        # vix1d absent before its launch index, present after
        self.assertIsNone(with_vix1d[349]["vix1d"])
        self.assertIsNone(with_vix1d[349]["vix1d_z1y"])
        self.assertIsNotNone(with_vix1d[350]["vix1d"])
        self.assertIsNone(with_vix1d[350]["vix1d_z1y"])  # only 1 observation
        self.assertIsNotNone(with_vix1d[-1]["vix1d_z1y"])  # 50 observations
        # every other metric is bit-identical to the run where vix1d never existed
        for left, right in zip(with_vix1d, without_vix1d):
            for key in bvm.METRIC_KEYS:
                if key == "vix1d":
                    continue
                for suffix in ("", "_z1y", "_z5y", "_pct1y"):
                    field = key + suffix
                    self.assertEqual(left[field], right[field], f"{field} on {left['date']}")


class Spx0dteTests(unittest.TestCase):
    def _write_components(self, path: Path, latest: dict) -> None:
        path.write_text(
            json.dumps(
                {
                    "components": [
                        {"component": "credit_stress", "latest": {"skew_z": 99.0}},
                        {
                            "component": "options_stress",
                            "as_of": "2026-07-31T16:00:00",
                            "source": "spx-0dte:signals.csv",
                            "latest": latest,
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )

    def test_block_is_retired_and_never_reads_the_component_file(self):
        # options_stress is now built FROM this file (chain snapshot + the
        # z-scores in `metrics`). Carrying it back in would put this module's
        # own output in its input and make one number look like two agreeing
        # sources. Even with a perfectly good component file on disk, the block
        # must stay null.
        dates = trading_dates(60)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            components = out / "market_risk_components.json"
            self._write_components(
                components,
                {
                    "straddle_residual_z": 0.47063142437591776,
                    "skew_z": -0.2331,
                    "term_ratio_z": -0.6294797687861272,
                    "realized_vs_implied_z": -0.008802851827395975,
                },
            )
            result = bvm.build(
                output_dir=out,
                fetcher=make_fetcher(dates),
                dry_run=True,
                components_path=components,
            )
        block = result["latest"]["spx_0dte"]
        self.assertFalse(block["available"])
        self.assertEqual(block["status"], "retired:options_stress_now_derives_from_this_file")
        self.assertIsNone(block["source"])
        self.assertIsNone(block["source_as_of"])
        for key in bvm.SPX_0DTE_KEYS:
            self.assertIsNone(block[key])

    def test_the_replacement_zscores_are_carried_natively(self):
        # What the retired block used to mirror is available first-hand, so
        # nothing was lost in the retirement.
        dates = trading_dates(60)
        with tempfile.TemporaryDirectory() as tmp:
            result = bvm.build(
                output_dir=Path(tmp), fetcher=make_fetcher(dates), dry_run=True,
            )
        metrics = result["latest"]["metrics"]
        for name in ("skew", "slope_vix_3m", "iv_rv_spread"):
            self.assertIn(name, metrics)
            self.assertIn("z1y", metrics[name])


class OutputTests(unittest.TestCase):
    def test_jsonl_idempotency_identical_bytes(self):
        dates = trading_dates(300)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            components = out / "missing.json"
            bvm.build(output_dir=out, fetcher=make_fetcher(dates), components_path=components)
            first_bytes = (out / bvm.HISTORY_NAME).read_bytes()
            bvm.build(output_dir=out, fetcher=make_fetcher(dates), components_path=components)
            second_bytes = (out / bvm.HISTORY_NAME).read_bytes()
        self.assertEqual(first_bytes, second_bytes)

    def test_no_duplicate_dates_and_ascending(self):
        dates = trading_dates(200)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            bvm.build(
                output_dir=out,
                fetcher=make_fetcher(dates),
                components_path=out / "missing.json",
            )
            lines = (out / bvm.HISTORY_NAME).read_text(encoding="utf-8").splitlines()
        parsed = [json.loads(line)["date"] for line in lines]
        self.assertEqual(len(parsed), len(set(parsed)))
        self.assertEqual(parsed, sorted(parsed))
        self.assertEqual(parsed, dates)

    def test_dry_run_writes_nothing(self):
        dates = trading_dates(60)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            bvm.build(
                output_dir=out,
                fetcher=make_fetcher(dates),
                dry_run=True,
                components_path=out / "missing.json",
            )
            self.assertFalse((out / bvm.HISTORY_NAME).exists())
            self.assertFalse((out / bvm.LATEST_NAME).exists())

    def test_latest_payload_shape(self):
        dates = trading_dates(300)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            bvm.build(
                output_dir=out,
                fetcher=make_fetcher(dates),
                components_path=out / "missing.json",
            )
            payload = json.loads((out / bvm.LATEST_NAME).read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["model_version"], "vol-metrics-v2")
        self.assertTrue(payload["research_only"])
        self.assertEqual(payload["as_of"], dates[-1])
        self.assertIn(payload["regime"]["term_state"], {"contango", "flat", "backwardation"})
        for key in bvm.METRIC_KEYS:
            self.assertIn(key, payload["metrics"])
            self.assertEqual(
                sorted(payload["metrics"][key]),
                [
                    "last_pct1y",
                    "last_value",
                    "last_value_date",
                    "last_z1y",
                    "last_z5y",
                    "pct1y",
                    "value",
                    "z1y",
                    "z5y",
                ],
            )
        self.assertEqual(payload["quality_state"], "ready")
        self.assertEqual(payload["coverage"]["metrics_lagging"], {})

    def test_lagging_metric_is_named_not_forward_filled(self):
        dates = trading_dates(300)

        base = make_fetcher(dates)

        def lagging_fetcher(symbol: str) -> dict:
            series = base(symbol)
            if symbol == "^SKEW":
                for day in dates[-3:]:
                    series.pop(day, None)
            return series

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            result = bvm.build(
                output_dir=out,
                fetcher=lagging_fetcher,
                dry_run=True,
                components_path=out / "missing.json",
            )
        entry = result["latest"]["metrics"]["skew"]
        self.assertIsNone(entry["value"])
        self.assertIsNone(entry["z1y"])
        self.assertIsNotNone(entry["last_value"])
        self.assertEqual(entry["last_value_date"], dates[-4])
        self.assertIsNotNone(entry["last_z1y"])
        lag = result["latest"]["coverage"]["metrics_lagging"]["skew"]
        self.assertEqual(lag["last_value_date"], dates[-4])
        self.assertEqual(lag["sessions_behind"], 3)
        # a fresh metric is not listed as lagging
        self.assertNotIn("vix", result["latest"]["coverage"]["metrics_lagging"])

    def test_term_state_thresholds(self):
        self.assertEqual(bvm.term_state(0.90), "contango")
        self.assertEqual(bvm.term_state(0.979), "contango")
        self.assertEqual(bvm.term_state(0.99), "flat")
        self.assertEqual(bvm.term_state(1.02), "flat")
        self.assertEqual(bvm.term_state(1.05), "backwardation")
        self.assertEqual(bvm.term_state(None), "unknown")


class InteriorGapDetectionTests(unittest.TestCase):
    """A metric that stops printing for weeks and then resumes reads as
    perfectly fresh under a last-print check (observed 2026-08-10: the whole
    term-structure complex was null 2026-07-20..2026-08-07 while
    metrics_lagging named only move and skew)."""

    def _rows(self, gap_dates):
        rows = []
        for i in range(40):
            date = f"2026-06-{i + 1:02d}" if i < 30 else f"2026-07-{i - 29:02d}"
            rows.append({"date": date, "vix": 15.0 + i,
                         "vix3m": None if date in gap_dates else 18.0 + i})
        return rows

    def test_interior_gap_is_reported_though_latest_prints(self):
        rows = self._rows({"2026-07-02", "2026-07-03", "2026-07-04"})
        latest = bvm.build_latest(rows, {}, {}, {}, "2026-08-10T00:00:00+00:00")
        coverage = latest["coverage"]
        # Latest row prints, so a last-print check sees nothing wrong.
        self.assertNotIn("vix3m", coverage["metrics_lagging"])
        gap = coverage["metrics_with_gaps"]["vix3m"]
        self.assertEqual(gap["sessions_missing"], 3)
        self.assertEqual(gap["first_missing"], "2026-07-02")
        self.assertFalse(gap["window_fully_missing"])
        self.assertIn("vix3m", coverage["metrics_gap_stale"])
        self.assertEqual(latest["quality_state"], "stale")

    def test_metric_dead_for_the_whole_window_is_not_filtered_out(self):
        rows = self._rows(set())
        # Null the metric across the entire detection window, so the "gap"
        # is really a dead feed - the case an upper-bound guard would hide.
        for row in rows[-bvm.GAP_WINDOW_SESSIONS:]:
            row["vix3m"] = None
        latest = bvm.build_latest(rows, {}, {}, {}, "2026-08-10T00:00:00+00:00")
        gap = latest["coverage"]["metrics_with_gaps"]["vix3m"]
        self.assertTrue(gap["window_fully_missing"])
        self.assertEqual(gap["sessions_missing"], bvm.GAP_WINDOW_SESSIONS)

    def test_fully_covered_metric_reports_no_gap(self):
        rows = self._rows(set())
        latest = bvm.build_latest(rows, {}, {}, {}, "2026-08-10T00:00:00+00:00")
        self.assertNotIn("vix3m", latest["coverage"]["metrics_with_gaps"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
