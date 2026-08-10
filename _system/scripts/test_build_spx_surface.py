#!/usr/bin/env python3
"""Tests for build_spx_surface.py -- stdlib unittest only."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_spx_surface as bss  # noqa: E402


def option_row(symbol, *, bid=10.0, ask=10.5, iv=0.20, delta=0.5, gamma=0.001, oi=100.0):
    return {
        "option": symbol,
        "bid": bid,
        "ask": ask,
        "iv": iv,
        "delta": delta,
        "gamma": gamma,
        "open_interest": oi,
        "volume": 0.0,
        "vega": 1.0,
        "theta": -1.0,
    }


def chain_payload(options, *, timestamp="2026-08-10 18:23:34", spot=100.0, close=100.0):
    return {
        "timestamp": timestamp,
        "symbol": "_SPX",
        "data": {
            "options": options,
            "symbol": "_SPX",
            "security_type": "index",
            "current_price": spot,
            "close": close,
            "iv30": 12.3,
        },
    }


class TestOsiParsing(unittest.TestCase):
    def test_parses_real_symbol(self):
        parsed = bss.parse_osi("SPX260821C00200000")
        self.assertEqual(parsed["root"], "SPX")
        self.assertEqual(parsed["expiry"], date(2026, 8, 21))
        self.assertEqual(parsed["right"], "C")
        self.assertAlmostEqual(parsed["strike"], 200.0)

    def test_parses_variable_length_root_and_put(self):
        parsed = bss.parse_osi("SPXW260911P07750000")
        self.assertEqual(parsed["root"], "SPXW")
        self.assertEqual(parsed["right"], "P")
        self.assertAlmostEqual(parsed["strike"], 7750.0)
        self.assertEqual(parsed["expiry"], date(2026, 9, 11))

    def test_strike_is_thousandths(self):
        # 8-digit strike field 00200000 -> 200.000, not 200000
        self.assertAlmostEqual(bss.parse_osi("SPX260821C00200000")["strike"], 200.0)
        self.assertAlmostEqual(bss.parse_osi("SPX260821C07750500")["strike"], 7750.5)

    def test_malformed_symbols_return_none(self):
        for bad in (
            "NOTANOPTION",
            "SPX26082C00200000",  # 5-digit date
            "SPX260821X00200000",  # bad right
            "SPX260821C0020000",  # 7-digit strike
            "SPX260231C00200000",  # Feb 31 -- not a real date
            "SPX260821C00000000",  # zero strike
            "",
            None,
            12345,
        ):
            self.assertIsNone(bss.parse_osi(bad), f"expected None for {bad!r}")

    def test_malformed_row_is_skipped_and_counted(self):
        rows, quality = bss.filter_rows(
            [option_row("SPX260821C07700000"), option_row("GARBAGE")]
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(quality["rows_rejected_by_reason"]["unparsed_symbol"], 1)


class TestQualityFilter(unittest.TestCase):
    def test_reject_reason_counts(self):
        options = [
            option_row("SPX260821C07700000"),  # good
            option_row("GARBAGE"),  # unparsed_symbol
            option_row("SPX260821C07710000", iv=None),  # missing greeks
            option_row("SPX260821C07720000", delta=None),  # missing greeks
            option_row("SPX260821C07730000", gamma=None),  # missing greeks
            option_row("SPX260821C07740000", bid=0.0),  # no_bid
            option_row("SPX260821C07750000", bid=-1.0),  # no_bid
            option_row("SPX260821C07760000", bid=10.0, ask=9.0),  # crossed
            option_row("SPX260821C07770000", bid=10.0, ask=10.0),  # locked
            option_row("SPX260821C07780000", iv=7.03),  # iv too high
            option_row("SPX260821C07790000", iv=0.0001),  # iv too low
        ]
        rows, quality = bss.filter_rows(options)
        self.assertEqual(len(rows), 1)
        self.assertEqual(quality["rows_total"], 11)
        self.assertEqual(quality["rows_used"], 1)
        self.assertEqual(quality["rows_rejected"], 10)
        self.assertEqual(
            quality["rows_rejected_by_reason"],
            {
                "unparsed_symbol": 1,
                "missing_or_nonfinite_greeks": 3,
                "no_bid": 2,
                "crossed_or_locked_quote": 2,
                "iv_out_of_bounds": 2,
            },
        )

    def test_iv_bounds_are_inclusive_at_the_edges(self):
        rows, _ = bss.filter_rows(
            [
                option_row("SPX260821C07700000", iv=bss.IV_MIN),
                option_row("SPX260821C07710000", iv=bss.IV_MAX),
            ]
        )
        self.assertEqual(len(rows), 2)

    def test_null_open_interest_is_coerced_not_rejected(self):
        rows, quality = bss.filter_rows([option_row("SPX260821C07700000", oi=None)])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["open_interest"], 0.0)
        self.assertEqual(quality["rows_open_interest_coerced_zero"], 1)
        self.assertEqual(quality["rows_rejected"], 0)


class TestTenorSelection(unittest.TestCase):
    def _chains(self, as_of, expiries):
        rows = []
        for expiry in expiries:
            rows.append(
                {
                    "symbol": f"SPX{expiry}C07700000",
                    "root": "SPX",
                    "expiry": date.fromisoformat(expiry),
                    "right": "C",
                    "strike": 7700.0,
                    "iv": 0.13,
                    "delta": 0.5,
                    "gamma": 0.001,
                    "open_interest": 10.0,
                }
            )
        return bss.group_chains(rows, as_of)

    def test_picks_nearest_dte(self):
        as_of = date(2026, 8, 10)
        chains = self._chains(as_of, ["2026-08-14", "2026-08-21", "2026-09-11"])
        # targets 7 -> 2026-08-17 absent; 8-14 is dte 4 (err 3), 8-21 is dte 11 (err 4)
        picked = bss.select_tenor(chains, 7)
        self.assertEqual(picked["expiry"], date(2026, 8, 14))
        self.assertEqual(picked["dte"], 4)
        # target 30 -> 2026-09-11 is dte 32 (err 2) vs 8-21 dte 11 (err 19)
        picked = bss.select_tenor(chains, 30)
        self.assertEqual(picked["expiry"], date(2026, 9, 11))
        self.assertEqual(picked["dte"], 32)

    def test_excludes_same_day_and_expired(self):
        as_of = date(2026, 8, 10)
        chains = self._chains(as_of, ["2026-08-01", "2026-08-10", "2026-08-12"])
        picked = bss.select_tenor(chains, 1)
        self.assertEqual(picked["expiry"], date(2026, 8, 12))

    def test_returns_none_when_nothing_eligible(self):
        as_of = date(2026, 8, 10)
        chains = self._chains(as_of, ["2026-08-01"])
        self.assertIsNone(bss.select_tenor(chains, 30))

    def test_am_and_pm_roots_are_separate_chains_tie_broken_by_size(self):
        as_of = date(2026, 8, 10)
        rows = [
            {"symbol": "a", "root": "SPX", "expiry": date(2026, 8, 21), "right": "C", "strike": 1.0},
            {"symbol": "b", "root": "SPXW", "expiry": date(2026, 8, 21), "right": "C", "strike": 1.0},
            {"symbol": "c", "root": "SPXW", "expiry": date(2026, 8, 21), "right": "P", "strike": 1.0},
        ]
        chains = bss.group_chains(rows, as_of)
        self.assertEqual(len(chains), 2)
        picked = bss.select_tenor(chains, 11)
        self.assertEqual(picked["root"], "SPXW")  # more rows wins the tie

    def test_actual_dte_is_reported_never_the_label(self):
        as_of = date(2026, 8, 10)
        chains = self._chains(as_of, ["2026-08-14"])
        tenor = bss.build_tenor("1m", 30, bss.select_tenor(chains, 30), 7700.0)
        self.assertEqual(tenor["tenor"], "1m")
        self.assertEqual(tenor["dte"], 4)
        self.assertEqual(tenor["dte_error_vs_target"], -26)
        self.assertEqual(tenor["expiry"], "2026-08-14")


class TestAtmInterpolation(unittest.TestCase):
    def _row(self, right, strike, iv, delta=0.5):
        return {
            "symbol": f"X{right}{strike}",
            "root": "SPX",
            "expiry": date(2026, 8, 21),
            "right": right,
            "strike": float(strike),
            "iv": iv,
            "delta": delta,
            "gamma": 0.001,
            "open_interest": 10.0,
        }

    def test_hand_computable_interpolation(self):
        # strikes 100 (iv .20) and 110 (iv .30); spot 102.5 -> 25% of the way
        # -> .20 + .25 * .10 = .225
        rows = [self._row("C", 100, 0.20), self._row("C", 110, 0.30)]
        value, detail = bss.interpolate_iv_at(rows, 102.5)
        self.assertAlmostEqual(value, 0.225, places=12)
        self.assertEqual(detail["strikes"], [100.0, 110.0])
        self.assertFalse(detail["extrapolated"])

    def test_calls_and_puts_averaged(self):
        # call leg interpolates to .225, put leg to .245 -> average .235
        rows = [
            self._row("C", 100, 0.20),
            self._row("C", 110, 0.30),
            self._row("P", 100, 0.22),
            self._row("P", 110, 0.32),
        ]
        result = bss.atm_iv(rows, 102.5)
        self.assertAlmostEqual(result["atm_iv_call"], 0.225, places=9)
        self.assertAlmostEqual(result["atm_iv_put"], 0.245, places=9)
        self.assertAlmostEqual(result["atm_iv"], 0.235, places=9)
        self.assertAlmostEqual(result["atm_call_put_gap"], -0.02, places=9)
        self.assertEqual(result["atm_reference"], "spot")

    def test_exact_strike_hit(self):
        rows = [self._row("C", 100, 0.20), self._row("C", 110, 0.30)]
        value, _ = bss.interpolate_iv_at(rows, 100.0)
        self.assertAlmostEqual(value, 0.20, places=12)

    def test_spot_outside_strike_range_flags_extrapolation(self):
        rows = [self._row("C", 100, 0.20), self._row("C", 110, 0.30)]
        value, detail = bss.interpolate_iv_at(rows, 200.0)
        self.assertAlmostEqual(value, 0.30, places=12)
        self.assertTrue(detail["extrapolated"])

    def test_empty_returns_none(self):
        value, detail = bss.interpolate_iv_at([], 100.0)
        self.assertIsNone(value)
        self.assertEqual(detail["n_strikes"], 0)


class TestDeltaSelection(unittest.TestCase):
    def _row(self, right, strike, delta, iv):
        return {
            "symbol": f"X{right}{strike}",
            "root": "SPX",
            "expiry": date(2026, 8, 21),
            "right": right,
            "strike": float(strike),
            "iv": iv,
            "delta": delta,
            "gamma": 0.001,
            "open_interest": 10.0,
        }

    def test_picks_nearest_absolute_delta(self):
        rows = [
            self._row("C", 110, 0.40, 0.18),
            self._row("C", 120, 0.27, 0.21),  # nearest to 0.25
            self._row("C", 130, 0.10, 0.24),
            self._row("P", 90, -0.24, 0.30),  # nearest to 0.25
            self._row("P", 80, -0.10, 0.34),
        ]
        call = bss.select_by_delta(rows, "C", 0.25)
        put = bss.select_by_delta(rows, "P", 0.25)
        self.assertAlmostEqual(call["strike"], 120.0)
        self.assertAlmostEqual(put["strike"], 90.0)

    def test_rr_and_bf_arithmetic(self):
        # atm from strikes 100/110 at spot 100 -> .20
        rows = [
            self._row("C", 100, 0.52, 0.20),
            self._row("C", 110, 0.27, 0.18),
            self._row("P", 100, -0.48, 0.20),
            self._row("P", 90, -0.26, 0.30),
        ]
        chain = {"expiry": date(2026, 8, 21), "root": "SPX", "dte": 11, "rows": rows}
        tenor = bss.build_tenor("1w", 7, chain, 100.0)
        self.assertAlmostEqual(tenor["atm_iv"], 0.20, places=9)
        # rr = iv(25d call) - iv(25d put) = .18 - .30 = -.12
        self.assertAlmostEqual(tenor["rr_25d"], -0.12, places=9)
        # bf = (.18 + .30)/2 - .20 = .04
        self.assertAlmostEqual(tenor["bf_25d"], 0.04, places=9)
        self.assertAlmostEqual(tenor["call_25d"]["delta"], 0.27)
        self.assertAlmostEqual(tenor["put_25d"]["delta"], -0.26)

    def test_no_candidates_returns_none(self):
        self.assertIsNone(bss.select_by_delta([], "C", 0.25))


class TestPutSkewSlope(unittest.TestCase):
    def _put(self, strike, iv):
        return {
            "symbol": f"P{strike}",
            "root": "SPX",
            "expiry": date(2026, 8, 21),
            "right": "P",
            "strike": float(strike),
            "iv": iv,
            "delta": -0.2,
            "gamma": 0.001,
            "open_interest": 1.0,
        }

    def test_perfect_line_recovers_slope(self):
        # spot 100; strikes 90/95/100 -> x = -10, -5, 0
        # iv = 0.20 - 0.004 * x  -> slope -0.004 per 1% moneyness
        rows = [self._put(90, 0.24), self._put(95, 0.22), self._put(100, 0.20)]
        fit = bss.fit_put_skew_slope(rows, 100.0)
        self.assertAlmostEqual(fit["put_skew_slope"], -0.004, places=9)
        self.assertAlmostEqual(fit["put_skew_r_squared"], 1.0, places=9)
        self.assertEqual(fit["put_skew_n_points"], 3)
        self.assertEqual(fit["put_skew_status"], "ok")
        self.assertIn("1% of moneyness", fit["put_skew_slope_units"])

    def test_band_excludes_out_of_range_strikes_and_calls(self):
        rows = [
            self._put(80, 0.40),  # 0.80 moneyness -- outside band
            self._put(105, 0.19),  # above spot -- outside band
            self._put(90, 0.24),
            self._put(95, 0.22),
            self._put(100, 0.20),
        ]
        call = dict(self._put(95, 0.99))
        call["right"] = "C"
        rows.append(call)
        fit = bss.fit_put_skew_slope(rows, 100.0)
        self.assertEqual(fit["put_skew_n_points"], 3)
        self.assertAlmostEqual(fit["put_skew_slope"], -0.004, places=9)

    def test_insufficient_points(self):
        fit = bss.fit_put_skew_slope([self._put(95, 0.22)], 100.0)
        self.assertIsNone(fit["put_skew_slope"])
        self.assertEqual(fit["put_skew_status"], "insufficient_points")


class TestDealerGammaProxy(unittest.TestCase):
    def test_two_row_hand_computation(self):
        spot = 100.0
        # spot^2 * 0.01 = 10000 * 0.01 = 100
        # call: .01 gamma * 50 oi * 100 mult * 100 = 5000, sign +1
        # put:  .02 gamma * 10 oi * 100 mult * 100 = 2000, sign -1
        # net = 5000 - 2000 = 3000
        rows = [
            {"right": "C", "gamma": 0.01, "open_interest": 50.0},
            {"right": "P", "gamma": 0.02, "open_interest": 10.0},
        ]
        result = bss.dealer_gamma_proxy(rows, spot)
        self.assertAlmostEqual(result["value"], 3000.0, places=6)
        self.assertAlmostEqual(result["call_gamma_notional"], 5000.0, places=6)
        self.assertAlmostEqual(result["put_gamma_notional"], 2000.0, places=6)
        self.assertEqual(result["contracts_used"], 2)

    def test_caveats_are_explicit_fields(self):
        result = bss.dealer_gamma_proxy([], 100.0)
        self.assertEqual(result["method"], "proxy")
        self.assertIn("ASSUMPTION", result["sign_convention"])
        self.assertIn("long", result["sign_convention"])
        self.assertIn("start-of-day", result["oi_caveat"])
        self.assertTrue(result["research_only"])

    def test_gamma_flip_is_omitted_not_fabricated(self):
        result = bss.dealer_gamma_proxy([], 100.0)
        self.assertNotIn("gamma_flip_estimate", result)
        self.assertEqual(result["gamma_flip_estimate_status"], "omitted")
        self.assertTrue(result["gamma_flip_omitted_reason"])

    def test_sign_convention_flips_with_right(self):
        rows = [{"right": "P", "gamma": 0.01, "open_interest": 50.0}]
        self.assertLess(bss.dealer_gamma_proxy(rows, 100.0)["value"], 0)


class TestSnapshotAndHistory(unittest.TestCase):
    def _fixture(self, timestamp="2026-08-10 18:23:34"):
        options = []
        # 4 expiries near the 4 tenor targets from a 2026-08-10 snapshot
        for expiry, base_iv in (
            ("260817", 0.13),
            ("260909", 0.14),
            ("261109", 0.16),
            ("270208", 0.18),
        ):
            for strike in range(88, 113, 2):
                money = strike / 100.0
                iv = base_iv + (1.0 - money) * 0.30
                # crude monotone deltas so the 25d picks are well defined
                call_delta = max(0.02, min(0.98, 0.5 - (strike - 100) * 0.03))
                put_delta = -(1.0 - call_delta)
                strike_field = f"{int(strike * 1000):08d}"
                options.append(
                    option_row(
                        f"SPXW{expiry}C{strike_field}",
                        iv=iv,
                        delta=call_delta,
                        gamma=0.01,
                        oi=100.0,
                        bid=1.0,
                        ask=1.2,
                    )
                )
                options.append(
                    option_row(
                        f"SPXW{expiry}P{strike_field}",
                        iv=iv,
                        delta=put_delta,
                        gamma=0.01,
                        oi=50.0,
                        bid=1.0,
                        ask=1.2,
                    )
                )
        options.append(option_row("MALFORMED"))
        options.append(option_row("SPXW260817C00090000", bid=0.0))
        return chain_payload(options, timestamp=timestamp, spot=100.0, close=99.0)

    def test_snapshot_shape(self):
        snapshot = bss.build_snapshot(self._fixture())
        self.assertEqual(snapshot["as_of"], "2026-08-10")
        self.assertEqual(snapshot["model_version"], "spx-surface-v1")
        self.assertTrue(snapshot["research_only"])
        self.assertEqual(snapshot["source"]["delayed_minutes"], 15)
        self.assertEqual(snapshot["source"]["snapshot_timestamp"], "2026-08-10 18:23:34")
        self.assertAlmostEqual(snapshot["spot"]["value"], 100.0)
        self.assertEqual(snapshot["spot"]["source_field"], "data.current_price")
        self.assertEqual([t["tenor"] for t in snapshot["tenors"]], ["1w", "1m", "3m", "6m"])
        for tenor in snapshot["tenors"]:
            self.assertIsNotNone(tenor["atm_iv"])
            self.assertIsNotNone(tenor["dte"])
            self.assertIsNotNone(tenor["expiry"])
        self.assertEqual(snapshot["quality_state"], "ok")
        self.assertEqual(snapshot["quality"]["rows_rejected_by_reason"]["unparsed_symbol"], 1)
        self.assertEqual(snapshot["quality"]["rows_rejected_by_reason"]["no_bid"], 1)

    def test_spot_falls_back_to_close(self):
        payload = self._fixture()
        payload["data"]["current_price"] = None
        snapshot = bss.build_snapshot(payload)
        self.assertAlmostEqual(snapshot["spot"]["value"], 99.0)
        self.assertEqual(snapshot["spot"]["source_field"], "data.close")

    def test_bad_spot_raises(self):
        payload = self._fixture()
        payload["data"]["current_price"] = None
        payload["data"]["close"] = 0
        with self.assertRaises(ValueError):
            bss.build_snapshot(payload)

    def test_same_day_run_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            fixture = out / "fixture.json"
            fixture.write_text(json.dumps(self._fixture()), encoding="utf-8")

            bss.build(output_dir=out, fixture=fixture)
            history = out / bss.HISTORY_NAME
            first = history.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(first), 1)

            self.assertAlmostEqual(json.loads(first[0])["spot"]["value"], 100.0)

            # second run, same date, different spot -> must overwrite the row
            moved = self._fixture()
            moved["data"]["current_price"] = 101.0
            fixture.write_text(json.dumps(moved), encoding="utf-8")
            bss.build(output_dir=out, fixture=fixture)
            second = history.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(second), 1, "same-day rerun must replace, not append")

            rows = bss.read_history(history)
            self.assertEqual([row["as_of"] for row in rows], ["2026-08-10"])
            self.assertAlmostEqual(rows[0]["spot"]["value"], 101.0)
            latest = json.loads((out / bss.LATEST_NAME).read_text(encoding="utf-8"))
            self.assertAlmostEqual(latest["spot"]["value"], 101.0)

    def test_distinct_dates_append_and_sort(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            for stamp in ("2026-08-11 18:00:00", "2026-08-10 18:00:00"):
                fixture = out / "fixture.json"
                fixture.write_text(
                    json.dumps(self._fixture(timestamp=stamp)), encoding="utf-8"
                )
                bss.build(output_dir=out, fixture=fixture)
            rows = bss.read_history(out / bss.HISTORY_NAME)
            self.assertEqual([row["as_of"] for row in rows], ["2026-08-10", "2026-08-11"])

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            fixture = out / "fixture.json"
            fixture.write_text(json.dumps(self._fixture()), encoding="utf-8")
            bss.build(output_dir=out, fixture=fixture, dry_run=True)
            self.assertFalse((out / bss.HISTORY_NAME).exists())
            self.assertFalse((out / bss.LATEST_NAME).exists())

    def test_corrupt_history_lines_are_dropped_not_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            history = out / bss.HISTORY_NAME
            history.write_text(
                '{"as_of":"2026-08-01"}\nnot json\n{"no_as_of":1}\n\n', encoding="utf-8"
            )
            rows = bss.read_history(history)
            self.assertEqual([row["as_of"] for row in rows], ["2026-08-01"])


class TestFetchFailurePreservation(unittest.TestCase):
    def test_prior_history_preserved_and_latest_stamped_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            history = out / bss.HISTORY_NAME
            latest = out / bss.LATEST_NAME
            good = {
                "schema_version": 1,
                "as_of": "2026-08-09",
                "quality_state": "ok",
                "spot": {"value": 7700.0},
                "tenors": [{"tenor": "1m", "atm_iv": 0.13}],
            }
            history.write_text(json.dumps(good) + "\n", encoding="utf-8")
            latest.write_text(json.dumps(good), encoding="utf-8")
            history_before = history.read_text(encoding="utf-8")

            def boom(*args, **kwargs):
                raise RuntimeError("CBOE fetch failed after 3 attempts: timed out")

            original = bss.fetch_chain
            bss.fetch_chain = boom
            try:
                payload = bss.build(output_dir=out)
            finally:
                bss.fetch_chain = original

            self.assertEqual(payload["quality_state"], "stale")
            self.assertEqual(payload["fetch_status"], "preserved_after_fetch_failure")
            self.assertIn("CBOE fetch failed", payload["fetch_error"])
            self.assertEqual(payload["as_of"], "2026-08-09")
            self.assertEqual(payload["spot"]["value"], 7700.0)
            # history untouched
            self.assertEqual(history.read_text(encoding="utf-8"), history_before)
            written = json.loads(latest.read_text(encoding="utf-8"))
            self.assertEqual(written["quality_state"], "stale")

    def test_fetch_failure_with_no_prior_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)

            def boom(*args, **kwargs):
                raise RuntimeError("dns failure")

            original = bss.fetch_chain
            bss.fetch_chain = boom
            try:
                payload = bss.build(output_dir=out)
            finally:
                bss.fetch_chain = original

            self.assertEqual(payload["quality_state"], "stale")
            self.assertIsNone(payload["as_of"])
            self.assertFalse((out / bss.HISTORY_NAME).exists())
            self.assertTrue((out / bss.LATEST_NAME).exists())

    def test_malformed_payload_takes_the_stale_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            fixture = out / "bad.json"
            fixture.write_text('{"data":{"options":[]}}', encoding="utf-8")
            payload = bss.build(output_dir=out, fixture=fixture)
            self.assertEqual(payload["quality_state"], "stale")
            self.assertFalse((out / bss.HISTORY_NAME).exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
