"""Invariants for the Research Watchdog.

Two of these are regression guards for bugs that were live in the data when the
watchdog was written, and both would fail silently rather than loudly:

  * `etf_ls_universe.json` is ls-algo's whole trading list (924 symbols,
    underlyings included), not a list of levered products. Excluding on it drops
    APLD, AXP, BRK B and SMR - real research names holding real capital - the
    moment a systematic strategy starts trading them.
  * `classify_position` tests universe membership BEFORE the owner checks, so
    recomputing a stored bucket moves those same names out of Michael's book.
    The watchdog must read book membership, never recompute it.
"""
from __future__ import annotations

import inspect
import json
import re
import tempfile
import unittest
from pathlib import Path

import research_watchdog as w


def _row(symbol, name, bucket, mv, sec_type="STK"):
    return {
        "symbol": symbol, "localSymbol": symbol, "name": name, "secType": sec_type,
        "marketValue": mv, "classification": {"ticker": symbol, "bucket": bucket},
    }


class GatewaySafety(unittest.TestCase):
    """CLAUDE.md rules 9 and 10: this repo never polls the Gateway."""

    def test_watchdog_never_touches_the_gateway(self):
        src = inspect.getsource(w)
        for forbidden in (
            r"\bimport\s+ib_insync\b", r"\bfrom\s+ib_insync\b",
            r"\bimport\s+ibapi\b", r"\bfrom\s+ibapi\b",
            r"\.reqGlobalCancel\s*\(", r"\.reqAutoOpenOrders\s*\(",
            r"\.reqMktData\s*\(", r"\.connect\s*\(", r"\bsocket\.",
        ):
            self.assertIsNone(
                re.search(forbidden, src),
                f"research_watchdog.py must not contain {forbidden!r}; broker truth "
                f"reaches this repo through committed files and Flex over HTTPS only.",
            )

    def test_the_only_subprocess_is_the_pr_lookup(self):
        calls = re.findall(r"subprocess\.\w+\(\s*\[([^\]]*)\]", inspect.getsource(w))
        self.assertEqual(len(calls), 1, "exactly one subprocess call expected")
        self.assertIn('"gh"', calls[0])


class WrapperDetection(unittest.TestCase):
    def test_levered_and_derivative_income_wrappers_are_detected(self):
        mapped = w.levered_wrapper_symbols()
        for symbol, name in [
            ("APLZ", "TRDR 2X SH APLD DLY ETF"),
            ("BRKU", "DIREXION DAILY BRKB BULL 2X"),
            ("BRKC", "YIELDMAX BO INCOME STRAY ETF"),
            ("SMZ", "TRADR 2X SHORT SMR DAILY ETF"),
            ("ECHX", "LEVERAGE SHARES 2X ECHO ETF"),
            ("TTDU", "T-REX 2XL TTD DAILY TAR ETF"),
            ("INTW", "GRANITE 2X LONG INTC ETF"),
        ]:
            self.assertTrue(w.is_wrapper(symbol, name, mapped), f"{symbol} is a wrapper")

    def test_plain_stocks_are_not_wrappers(self):
        mapped = w.levered_wrapper_symbols()
        for symbol, name in [
            ("APLD", "APPLIED DIGITAL CORP"),
            ("AXP", "AMERICAN EXPRESS CO"),
            ("BRK B", "BERKSHIRE HATHAWAY INC-CL B"),
            ("SMR", "NUSCALE POWER CORP"),
            ("GTX", "GARRETT MOTION INC"),
            ("JPM", "JPMORGAN CHASE & CO"),
        ]:
            self.assertFalse(w.is_wrapper(symbol, name, mapped), f"{symbol} is a plain stock")


class Scoping(unittest.TestCase):
    def _scope_over(self, rows):
        """Both scope paths must be redirected. The watchdog PREFERS
        research_scope.json, so patching only POSITIONS silently reads the real
        Flex scope off the developer's disk and the assertions below stop
        describing the fixture at all."""
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "positions.json"
            path.write_text(json.dumps(rows), encoding="utf-8")
            originals = (w.SCOPE_FILE, w.POSITIONS)
            w.SCOPE_FILE = Path(td) / "absent_research_scope.json"
            w.POSITIONS = path
            try:
                return w.build_scope()
            finally:
                w.SCOPE_FILE, w.POSITIONS = originals

    def test_a_held_name_stays_in_scope_even_when_ls_algo_trades_it(self):
        """The APLD regression. APLD, AXP, BRK B and SMR are all in
        etf_ls_universe.json, and all belong in the research book."""
        universe = set(json.loads(
            (w.ROOT / "_system/trading/sleeves/data/etf_ls_universe.json").read_text(encoding="utf-8")
        )["symbols"])
        rows = [
            _row("APLD", "APPLIED DIGITAL CORP", "michael", 654_150.0),
            _row("AXP", "AMERICAN EXPRESS CO", "michael", 125_942.0),
        ]
        for r in rows:
            self.assertIn(r["symbol"], universe, "guard is meaningless if the name left the universe")
        scope, meta = self._scope_over(rows)
        self.assertEqual({h.ticker for h in scope}, {"APLD", "AXP"})
        self.assertEqual(meta["excluded"]["levered_wrapper"], 0)

    def test_book_membership_is_read_not_recomputed(self):
        """A line ls-algo owns stays out even though it is an ordinary stock."""
        scope, meta = self._scope_over([
            _row("AAPL", "APPLE INC", "etf_ls", 12_000.0),
            _row("GTX", "GARRETT MOTION INC", "michael", 4_826_195.0),
        ])
        self.assertEqual([h.ticker for h in scope], ["GTX"])
        self.assertEqual(meta["excluded"]["other_book"], 1)

    def test_wrappers_michaels_book_wrongly_claims_are_dropped(self):
        scope, meta = self._scope_over([
            _row("APLZ", "TRDR 2X SH APLD DLY ETF", "michael", -177_749.0),
            _row("GTX", "GARRETT MOTION INC", "michael", 4_826_195.0),
        ])
        self.assertEqual([h.ticker for h in scope], ["GTX"])
        self.assertEqual(meta["excluded"]["levered_wrapper"], 1)

    def test_spx_and_options_never_enter_scope(self):
        scope, meta = self._scope_over([
            _row("SPXW  260813C07805000", "SPX OPT", "spx_0dte", -5000.0, sec_type="OPT"),
            _row("XSP   270129P00620000", "XSP OPT", "spx_0dte", -1000.0, sec_type="OPT"),
            _row("GTX", "GARRETT MOTION INC", "michael", 4_826_195.0),
        ])
        self.assertEqual([h.ticker for h in scope], ["GTX"])
        self.assertEqual(meta["excluded"]["spx_0dte"], 2)

    def test_foreign_symbols_resolve_to_their_suffixed_ticker_directory(self):
        scope, _ = self._scope_over([
            _row("FIHO12", "CONCENTRADORA FIBRA HOTELERA", "michael", 27_856.0),
            _row("JL80", "NORCONSULT AS", "michael", 3_976.0),
        ])
        self.assertEqual({h.ticker for h in scope}, {"FIHO12.MX", "JL80.DE"})

    def test_missing_sleeve_tags_is_reported_not_silently_absorbed(self):
        scope, meta = self._scope_over([_row("GTX", "GARRETT MOTION INC", "michael", 4_826_195.0)])
        if not meta["sleeve_tags_present"]:
            findings = w.detect_attribution_gap(scope, meta, w.date.today())
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].detector, "attribution_gap")


class Reporting(unittest.TestCase):
    def test_ranking_puts_capital_at_risk_ahead_of_a_bigger_pile(self):
        big_money = w.Finding("dive_quality", "GTX", "critical", "", "", 4_826_195.0, None)
        small_stale = w.Finding("pending_review", "PRVL.CVR", "medium", "", "", 1.0, 400)
        self.assertEqual([f.ticker for f in w.rank([small_stale, big_money])], ["GTX", "PRVL.CVR"])

    def test_the_report_is_capped_at_three(self):
        self.assertEqual(w.TOP_N, 3)

    def test_a_failing_detector_degrades_instead_of_killing_the_run(self):
        def explode(scope, today):
            raise RuntimeError("bit rot")

        original = dict(w.DETECTORS)
        w.DETECTORS.clear()
        w.DETECTORS["explode"] = explode
        try:
            self.assertEqual(w.main.__call__ and 0, 0)  # main is importable
            findings, degraded = [], {}
            for name, fn in w.DETECTORS.items():
                try:
                    findings.extend(fn([], w.date.today()))
                except Exception as exc:
                    degraded[name] = f"{type(exc).__name__}: {exc}"
            self.assertIn("explode", degraded)
            self.assertIn("bit rot", degraded["explode"])
        finally:
            w.DETECTORS.clear()
            w.DETECTORS.update(original)


class SystemicDetectors(unittest.TestCase):
    """A green lane is not evidence that its queue drained, and a watchdog that
    cannot see the current book must say so rather than rank a frozen one."""

    def _queue(self, payload):
        import contextlib
        @contextlib.contextmanager
        def swap():
            with tempfile.TemporaryDirectory() as td:
                path = Path(td) / "queue.json"
                path.write_text(json.dumps(payload), encoding="utf-8")
                original = w.DIVE_QUEUE
                w.DIVE_QUEUE = path
                try:
                    yield
                finally:
                    w.DIVE_QUEUE = original
        return swap()

    def test_a_queue_that_has_not_delivered_is_systemic(self):
        """The 2026-08-25 queue: 13 tickers set, none delivered, lane green."""
        with self._queue({"updated": "2026-01-01T00:00:00Z",
                          "tickers": ["SUM", "NAN", "FTC.L"]}):
            found = w.detect_stalled_dispatch_queue([], w.date(2026, 1, 20))
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].severity, "systemic")
        self.assertIn("3 of 3", found[0].detail)

    def test_a_queue_whose_dives_landed_is_silent(self):
        """Every queued ticker has a dive newer than the queue entry."""
        with self._queue({"updated": "2020-01-01T00:00:00Z", "tickers": ["APLD", "CSU"]}):
            self.assertEqual(w.detect_stalled_dispatch_queue([], w.date(2026, 1, 20)), [])

    def test_a_queue_set_today_is_not_yet_a_failure(self):
        """A queue needs time to drain before absence of delivery means anything."""
        today = w.date(2026, 1, 2)
        with self._queue({"updated": "2026-01-01T00:00:00Z", "tickers": ["SUM"]}):
            self.assertEqual(w.detect_stalled_dispatch_queue([], today), [])

    def test_an_empty_queue_is_silent(self):
        with self._queue({"updated": "2026-01-01T00:00:00Z", "tickers": []}):
            self.assertEqual(w.detect_stalled_dispatch_queue([], w.date(2026, 1, 20)), [])

    def test_a_stale_snapshot_is_systemic_and_carries_the_whole_book(self):
        findings = w.detect_stale_inputs(
            [w.Holding("GTX", "GTX", "GARRETT MOTION INC", "michael", 4_826_195.0, "michael")],
            w.date.today(),
        )
        # The real snapshot is months old in CI; if someone refreshes it this
        # test still holds, because a fresh snapshot must produce no finding.
        source = w.scope_source()
        snapshot = w.datetime.fromtimestamp(source.stat().st_mtime).date()
        if source == w.SCOPE_FILE:
            meta = w.load_json(source.parent / "research_scope_meta.json", {}) or {}
            if meta.get("session_date"):
                snapshot = w.date.fromisoformat(str(meta["session_date"]))
        if (w.date.today() - snapshot).days >= 14:
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].severity, "systemic")
            self.assertEqual(findings[0].capital, 4_826_195.0)
        else:
            self.assertEqual(findings, [])

    def test_systemic_outranks_a_larger_single_position(self):
        """A stalled repair loop must outrank the biggest individual gap, because
        nothing below it gets fixed until it is."""
        gtx = w.Finding("dive_quality", "GTX", "critical", "", "", 4_826_195.0, None)
        loop = w.Finding("stalled_queue", "-", "systemic", "", "", 11_845_627.0, 6)
        self.assertEqual([f.detector for f in w.rank([gtx, loop])],
                         ["stalled_queue", "dive_quality"])


class LaneDeclaration(unittest.TestCase):
    def test_the_watchdog_lane_is_declared_so_the_supervisor_can_see_it_fail(self):
        config = json.loads((w.ROOT / "_system/graph/graph_sources.json").read_text(encoding="utf-8"))
        lane = next((l for l in config["lanes"] if l["name"] == "research-watchdog"), None)
        self.assertIsNotNone(lane, "an undeclared workflow is invisible to the supervisor")
        self.assertEqual(lane["workflow_file"], "research-watchdog.yml")
        self.assertTrue((w.ROOT / ".github/workflows" / lane["workflow_file"]).exists())

    def test_the_lane_is_carried_by_its_receipt_because_it_commits_nothing(self):
        """This is a no-op lane by design: the ranked report names held positions
        and their market values, and this repository is public, so the workflow
        publishes nothing. graph_build takes max(last_commit, last_success), and
        test_p3_fresh_workflow_receipt_heals_noop_lane pins that a fresh receipt
        alone keeps such a lane healthy - so the schedule is what must exist."""
        workflow = (w.ROOT / ".github/workflows/research-watchdog.yml").read_text(encoding="utf-8")
        self.assertIn("schedule:", workflow, "no schedule means no receipt means a dead lane")
        self.assertNotIn("uses: ./.github/actions/commit-main", workflow,
                         "this lane must not commit; the report names held positions")
        self.assertNotIn("contents: write", workflow,
                         "read-only token: nothing from this lane should reach the repo")
        # test_llm_workflow_governance.test_actions_surface_has_no_manual_run_choices
        # bans a manual run surface outside a four-file allowlist. Caught in CI
        # on the first push of this lane; repository_dispatch is the way in.
        self.assertNotRegex(workflow, r"(?m)^\s{2}workflow_dispatch:\s*$",
                            "governance bans a manual run surface on new lanes")
        self.assertIn("repository_dispatch:", workflow)

    def test_the_report_and_its_json_are_gitignored(self):
        """The belt to the workflow's braces. WATCHDOG.md carries lines like
        '$4,826,195 held with no deep dive on GTX' and this repo is public."""
        ignored = (w.ROOT / ".gitignore").read_text(encoding="utf-8")
        for path in ("_system/data/research_watchdog.json", "_system/reviews/WATCHDOG.md"):
            self.assertIn(path, ignored, f"{path} names positions and must not be committed")

    def test_the_receipt_carries_no_ticker_and_no_dollar_figure(self):
        meta = {"in_scope": 51, "snapshot_date": "2026-08-13", "owners": {"michael": 51},
                "scope_source": "flex", "sleeve_tags_present": False, "excluded": {}}
        ranked = [w.Finding("dive_quality", "GTX", "critical",
                            "No deep dive on GTX", "$4,826,195 held", 4_826_195.0, None)]
        receipt = json.dumps(w.build_receipt(meta, ranked, {}, w.date.today()))
        self.assertNotIn("GTX", receipt)
        self.assertNotIn("4826195", receipt.replace(",", ""))
        self.assertNotIn("4,826,195", receipt)


if __name__ == "__main__":
    unittest.main()
