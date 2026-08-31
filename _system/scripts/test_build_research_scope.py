"""Invariants for the Flex-sourced Research Watchdog scope.

The two that caught real bugs during development:

  * The rewind guard. `_external/ls-algo` on a developer machine is a stale
    clone of the runs directory that lives on NY4. Pointing the builder at it
    wrote a 2026-07-15 book over a 2026-08-13 one, and because the watchdog
    PREFERS research_scope.json, the stale book immediately became the scope.
    A rewound snapshot reads exactly like a current one.
  * Bucket carry-forward. Flex `OpenPosition` rows carry no `orderRef` and
    `model` is empty on all 536 rows of the real statement, so recomputing with
    `classify_position` sends every name in ls-algo's 924-symbol universe to
    `etf_ls` - including APLD, AXP, BRK B and SMR.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

import build_research_scope as b


def _flex(rows: str, to_date: str = "20260816") -> bytes:
    return (
        f'<FlexQueryResponse><FlexStatements><FlexStatement accountId="U805366" '
        f'toDate="{to_date}"><OpenPositions>{rows}</OpenPositions>'
        f"</FlexStatement></FlexStatements></FlexQueryResponse>"
    ).encode()


def _pos(symbol, *, conid, currency="USD", position="100", value="1000",
         fx="1", desc="", category="STK"):
    return (f'<OpenPosition conid="{conid}" symbol="{symbol}" assetCategory="{category}" '
            f'currency="{currency}" position="{position}" positionValue="{value}" '
            f'fxRateToBase="{fx}" description="{desc}" model="" />')


class FxIsStatedNotInferred(unittest.TestCase):
    def test_a_foreign_row_uses_the_rate_ibkr_states(self):
        """CAD 801,879.40 at 0.71217 is USD 571,074.45, and nothing is derived
        from marketValue / (position x price) - the calculation that returned
        ~1.0 for every foreign holding and published yen at dollar magnitudes."""
        with tempfile.TemporaryDirectory() as td:
            xml = Path(td) / "flex.xml"
            xml.write_bytes(_flex(_pos("CSU", conid=1, currency="CAD",
                                       position="300.1304", value="801879.4",
                                       fx="0.71217", desc="CONSTELLATION SOFTWARE INC")))
            rows, _ = b.build_rows(xml, "U805366")
        row = rows[0]
        self.assertEqual(row["currency"], "CAD")
        self.assertAlmostEqual(row["marketValueNative"], 801879.4, places=2)
        self.assertAlmostEqual(row["marketValue"], 571074.45, places=2)

    def test_a_row_with_no_usable_rate_is_left_unvalued_rather_than_guessed(self):
        with tempfile.TemporaryDirectory() as td:
            xml = Path(td) / "flex.xml"
            xml.write_bytes(_flex(_pos("XXX", conid=9, currency="JPY", value="1000000", fx="")))
            rows, meta = b.build_rows(xml, "U805366")
        self.assertIsNone(rows[0]["marketValue"])
        self.assertAlmostEqual(rows[0]["marketValueNative"], 1000000.0)
        self.assertIn("XXX", meta["unvalued_no_fx"])


class BucketCarryForward(unittest.TestCase):
    def test_a_known_symbol_keeps_its_book_even_when_ls_algo_trades_it(self):
        """APLD is in etf_ls_universe.json. Recomputing would move it out of the
        research book; carrying forward keeps it where the desk put it."""
        universe = set(json.loads(
            (b.ROOT / "_system/trading/sleeves/data/etf_ls_universe.json").read_text(encoding="utf-8")
        )["symbols"])
        self.assertIn("APLD", universe, "guard is vacuous if APLD left the universe")
        with tempfile.TemporaryDirectory() as td:
            xml = Path(td) / "flex.xml"
            xml.write_bytes(_flex(_pos("APLD", conid=2, value="654150",
                                       desc="APPLIED DIGITAL CORP")))
            rows, meta = b.build_rows(xml, "U805366")
        self.assertEqual(rows[0]["classification"]["bucket"], "michael")
        self.assertEqual(rows[0]["classification"]["reason"], "carried_forward")
        self.assertNotIn("APLD", meta["needs_review"])

    def test_an_unknown_wrapper_is_identified_from_the_instrument_and_needs_no_human(self):
        with tempfile.TemporaryDirectory() as td:
            xml = Path(td) / "flex.xml"
            xml.write_bytes(_flex(_pos("ZZZU", conid=3, desc="DIREXION DAILY ZZZ BULL 2X")))
            rows, meta = b.build_rows(xml, "U805366")
        self.assertEqual(rows[0]["classification"]["bucket"], "etf_ls")
        self.assertEqual(rows[0]["classification"]["reason"], "levered_wrapper")
        self.assertNotIn("ZZZU", meta["needs_review"])

    def test_an_unknown_plain_stock_is_flagged_rather_than_silently_booked(self):
        """It still lands in Michael's book - matching the residual rule - but the
        watchdog will start ranking it, and nothing has confirmed it belongs."""
        with tempfile.TemporaryDirectory() as td:
            xml = Path(td) / "flex.xml"
            xml.write_bytes(_flex(_pos("NEWCO", conid=4, value="50000", desc="NEWCO INDUSTRIES")))
            rows, meta = b.build_rows(xml, "U805366")
        self.assertEqual(rows[0]["classification"]["bucket"], "michael")
        self.assertEqual(rows[0]["classification"]["reason"], "residual_unreviewed")
        self.assertIn("NEWCO", meta["needs_review"])


class LotFolding(unittest.TestCase):
    def test_tax_lots_of_one_contract_fold_into_a_single_position(self):
        """Flex reports at lot level. Unfolded, one contract appears as many
        positions and its value is counted once per lot."""
        with tempfile.TemporaryDirectory() as td:
            xml = Path(td) / "flex.xml"
            xml.write_bytes(_flex(
                _pos("GTX", conid=5, position="100", value="1000", desc="GARRETT MOTION INC")
                + _pos("GTX", conid=5, position="50", value="500", desc="GARRETT MOTION INC")))
            rows, meta = b.build_rows(xml, "U805366")
        self.assertEqual(meta["lot_rows"], 2)
        self.assertEqual(meta["folded_rows"], 1)
        self.assertAlmostEqual(rows[0]["qty"], 150.0)
        self.assertAlmostEqual(rows[0]["marketValue"], 1500.0)


class RewindGuard(unittest.TestCase):
    """Refusing to move the book backwards is the point; a rewound snapshot
    reads exactly like a current one."""

    def _run(self, argv):
        import contextlib, io, sys
        buf = io.StringIO()
        original = sys.argv
        sys.argv = ["build_research_scope.py", *argv]
        try:
            with contextlib.redirect_stdout(buf):
                code = b.main()
        finally:
            sys.argv = original
        return code, buf.getvalue()

    def test_an_older_statement_is_refused_against_the_existing_scope(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "research_scope.json"
            (out.parent / "research_scope_meta.json").write_text(
                json.dumps({"session_date": "2026-08-13"}), encoding="utf-8")
            xml = Path(td) / "flex.xml"
            xml.write_bytes(_flex(_pos("GTX", conid=6), to_date="20260715"))
            code, output = self._run(["--flex", str(xml), "--out", str(out)])
        self.assertEqual(code, 1)
        self.assertIn("refusing to rewind", output)
        self.assertFalse(out.exists())

    def test_the_first_run_is_still_floored_by_the_fallback_snapshot(self):
        """The bug this caught: with no prior meta the guard had nothing to
        compare against, so a stale runs directory rewound scope on run one."""
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "research_scope.json"  # no prior meta at all
            xml = Path(td) / "flex.xml"
            stale = (date.today() - timedelta(days=90)).strftime("%Y%m%d")
            xml.write_bytes(_flex(_pos("GTX", conid=7), to_date=stale))
            code, output = self._run(["--flex", str(xml), "--out", str(out)])
        if b.watchdog.POSITIONS.exists():
            self.assertEqual(code, 1, "a 90-day-old statement must not become scope")
            self.assertIn("refusing to rewind", output)
            self.assertFalse(out.exists())

    def test_force_overrides_the_guard(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "research_scope.json"
            (out.parent / "research_scope_meta.json").write_text(
                json.dumps({"session_date": "2026-08-13"}), encoding="utf-8")
            xml = Path(td) / "flex.xml"
            xml.write_bytes(_flex(_pos("GTX", conid=8), to_date="20260715"))
            code, _ = self._run(["--flex", str(xml), "--out", str(out), "--force"])
        self.assertEqual(code, 0)


class NoGateway(unittest.TestCase):
    def test_the_scope_builder_never_touches_the_gateway(self):
        import inspect
        import re as _re
        src = inspect.getsource(b)
        for forbidden in (r"\bimport\s+ib_insync\b", r"\bimport\s+ibapi\b",
                          r"\.connect\s*\(", r"\.reqMktData\s*\(", r"\bsocket\.",
                          r"requests\.", r"urlopen"):
            self.assertIsNone(_re.search(forbidden, src),
                              f"must not contain {forbidden!r}: Flex is a file read, "
                              f"not a broker connection")


if __name__ == "__main__":
    unittest.main()
