"""The live-flow feed must survive its own weather, and its silence must be
countable.

Two halves of one outage (2026-08-03 12:15:40 -> 2026-08-10):

  * ``run_databento_flow_monitor`` died on an UNCAUGHT
    ``urllib.error.URLError: <urlopen error timed out>`` raised from the
    publish path. The first half of this suite proves a transient publish
    failure is now retried, then logged and survived, and that only a 401/403
    stops the monitor.
  * Nothing anywhere reported the resulting seven days of empty flow rails.
    The second half proves invariant P7 fires on a stale evidence file, skips
    cleanly (reported, not violated) on an absent one, and passes on a fresh
    one -- the branch split that keeps P7 usable in CI, where the evidence is
    machine-local and never present.
"""
from __future__ import annotations

import contextlib
import io
import json
import socket
import sys
import tempfile
import threading
import types
import unittest
import unittest.mock
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import graph_invariants                       # noqa: E402
import run_databento_flow_monitor as monitor  # noqa: E402
import test_graph_invariants as gi_tests      # noqa: E402


def http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://ingest.invalid", code,
                                  "planted", {}, None)


class RecordingSleeper:
    def __init__(self) -> None:
        self.delays: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


class PublishRetryTests(unittest.TestCase):
    """publish_with_retry: bounded exponential backoff, transient vs
    permanent, and never a stray non-ASCII byte on a cp1252 console."""

    def setUp(self):
        self.sleeper = RecordingSleeper()
        self.stdout = io.StringIO()

    def _run(self, publisher, **kwargs):
        with contextlib.redirect_stdout(self.stdout):
            return monitor.publish_with_retry(
                "https://ingest.invalid", "token", [{"symbol": "SPY"}], [],
                publisher=publisher, sleeper=self.sleeper,
                jitter=lambda: 0.0, **kwargs)

    def test_transient_timeout_is_retried_then_succeeds(self):
        # The exact exception that killed the process on 2026-08-03.
        calls = []

        def publisher(url, token, snapshots, components):
            calls.append(url)
            if len(calls) < 3:
                raise urllib.error.URLError(socket.timeout("timed out"))
            return {"accepted": {"flow": 23}}

        result, error = self._run(publisher)
        self.assertEqual(result, {"accepted": {"flow": 23}})
        self.assertIsNone(error)
        self.assertEqual(len(calls), 3)
        # 2s then 4s, jitter pinned to 0 for determinism.
        self.assertEqual(self.sleeper.delays, [2.0, 4.0])

    def test_all_attempts_fail_returns_error_and_does_not_raise(self):
        def publisher(url, token, snapshots, components):
            raise urllib.error.URLError(socket.timeout("timed out"))

        result, error = self._run(publisher)
        self.assertIsNone(result)
        self.assertEqual(error["attempts"], monitor.PUBLISH_ATTEMPTS)
        self.assertEqual(error["attempt"], monitor.PUBLISH_ATTEMPTS)
        self.assertEqual(error["error_class"], "URLError")
        # The last attempt must not sleep -- there is nothing left to retry.
        self.assertEqual(len(self.sleeper.delays),
                         monitor.PUBLISH_ATTEMPTS - 1)

    def test_every_attempt_logs_its_count_and_error_class(self):
        def publisher(url, token, snapshots, components):
            raise OSError("connection reset")

        self._run(publisher)
        lines = [json.loads(line) for line in
                 self.stdout.getvalue().splitlines() if line.strip()]
        attempts = [line for line in lines
                    if line["event"] == "publish_attempt_failed"]
        self.assertEqual(len(attempts), monitor.PUBLISH_ATTEMPTS)
        self.assertEqual([line["attempt"] for line in attempts],
                         list(range(1, monitor.PUBLISH_ATTEMPTS + 1)))
        for line in attempts:
            self.assertEqual(line["error_class"], "OSError")
        self.assertTrue(attempts[-1]["retrying"] is False)

    def test_log_output_is_ascii_only(self):
        def publisher(url, token, snapshots, components):
            raise urllib.error.URLError("timed out — dash and é")

        self._run(publisher)
        text = self.stdout.getvalue()
        self.assertTrue(text.strip())
        text.encode("ascii")   # raises UnicodeEncodeError if this regresses

    def test_auth_failures_raise_immediately_without_retrying(self):
        for code in monitor.AUTH_STATUS_CODES:
            with self.subTest(code=code):
                sleeper = RecordingSleeper()
                calls = []

                def publisher(url, token, snapshots, components):
                    calls.append(code)
                    raise http_error(code)

                with contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaises(monitor.PublishAuthError) as ctx:
                        monitor.publish_with_retry(
                            "https://ingest.invalid", "token", [], [],
                            publisher=publisher, sleeper=sleeper,
                            jitter=lambda: 0.0)
                self.assertEqual(ctx.exception.status, code)
                self.assertEqual(len(calls), 1, "a bad token must not retry")
                self.assertEqual(sleeper.delays, [])

    def test_non_auth_http_error_is_transient(self):
        calls = []

        def publisher(url, token, snapshots, components):
            calls.append(1)
            raise http_error(503)

        result, error = self._run(publisher)
        self.assertIsNone(result)
        self.assertEqual(len(calls), monitor.PUBLISH_ATTEMPTS)
        self.assertEqual(error["http_status"], 503)

    def test_backoff_is_bounded_and_exponential(self):
        def publisher(url, token, snapshots, components):
            raise urllib.error.URLError("down")

        self._run(publisher, attempts=4, base_delay=2.0)
        self.assertEqual(self.sleeper.delays, [2.0, 4.0, 8.0])


class PublishCycleTests(unittest.TestCase):
    """The contract the outage violated: LOG AND CONTINUE. A failed publish
    must never leave the streaming loop."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.state_path = Path(self._tmp.name) / "flow-state.json"

    def tearDown(self):
        self._tmp.cleanup()

    def _cycle(self, publisher, consecutive_failures=0):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            count = monitor.publish_cycle(
                ingest_url="https://ingest.invalid", ingest_token="token",
                snapshots=[{"symbol": "SPY"}], components=[],
                consecutive_failures=consecutive_failures,
                state_memory={"SPY": {"candidate": "calm", "count": 1}},
                state_path=self.state_path, publisher=publisher)
        lines = [json.loads(line) for line in stdout.getvalue().splitlines()
                 if line.strip()]
        return count, lines

    def test_failed_publish_counts_and_continues(self):
        count, lines = self._cycle(lambda *a: (None, {
            "error_class": "URLError", "error": "timed out", "attempts": 3}))
        self.assertEqual(count, 1)
        failed = [line for line in lines if line["event"] == "publish_failed"]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["action"], "continue_streaming")
        self.assertEqual(failed[0]["error_class"], "URLError")
        self.assertEqual(failed[0]["consecutive_failures"], 1)

    def test_heartbeat_carries_consecutive_failures(self):
        count, lines = self._cycle(
            lambda *a: (None, {"error_class": "URLError", "attempts": 3}),
            consecutive_failures=4)
        self.assertEqual(count, 5)
        beats = [line for line in lines if line["event"] == "heartbeat"]
        self.assertEqual(len(beats), 1)
        self.assertEqual(beats[0]["consecutive_failures"], 5)
        self.assertFalse(beats[0]["publish_ok"])

    def test_success_preserves_the_out_log_line_shape(self):
        # Something downstream parses this exact object, and P7 reads its
        # published_at as the live-feed stamp.
        count, lines = self._cycle(
            lambda *a: ({"accepted": {"flow": 23}}, None),
            consecutive_failures=7)
        self.assertEqual(count, 0, "a success resets the failure streak")
        published = [line for line in lines if "published_at" in line]
        self.assertEqual(len(published), 1)
        self.assertEqual(set(published[0]),
                         {"published_at", "symbols", "response"})
        self.assertEqual(published[0]["symbols"], 1)
        self.assertEqual(published[0]["response"], {"flow": 23})
        datetime.fromisoformat(published[0]["published_at"])

    def test_escalation_at_threshold_still_continues_streaming(self):
        below = monitor.PUBLISH_ESCALATION_AFTER - 2
        count, lines = self._cycle(
            lambda *a: (None, {"error_class": "URLError", "attempts": 3}),
            consecutive_failures=below)
        self.assertEqual(
            [line for line in lines
             if line["event"] == "publish_escalation"], [])
        count, lines = self._cycle(
            lambda *a: (None, {"error_class": "URLError", "attempts": 3}),
            consecutive_failures=monitor.PUBLISH_ESCALATION_AFTER - 1)
        escalations = [line for line in lines
                       if line["event"] == "publish_escalation"]
        self.assertEqual(len(escalations), 1)
        self.assertEqual(escalations[0]["consecutive_failures"],
                         monitor.PUBLISH_ESCALATION_AFTER)
        self.assertEqual(escalations[0]["action"], "continue_streaming")

    def test_auth_error_escapes_the_cycle(self):
        def publisher(*args, **kwargs):
            raise monitor.PublishAuthError(401, "bad token")

        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(monitor.PublishAuthError):
                monitor.publish_cycle(
                    ingest_url="u", ingest_token="t", snapshots=[],
                    components=[], consecutive_failures=0, state_memory={},
                    state_path=self.state_path, publisher=publisher)

    def test_state_write_failure_is_logged_not_fatal(self):
        blocked = Path(self._tmp.name) / "flow-state.json" / "nested.json"
        stdout = io.StringIO()
        (Path(self._tmp.name) / "flow-state.json").write_text("{}",
                                                              encoding="utf-8")
        with contextlib.redirect_stdout(stdout):
            ok = monitor.write_state(blocked, {"SPY": {}})
        self.assertFalse(ok)
        events = [json.loads(line)["event"]
                  for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertIn("state_write_failed", events)


class _StopTest(Exception):
    """Breaks out of the (deliberately infinite) reconnect loop."""


def fake_databento(live_factory) -> dict:
    """Stand-in ``databento`` / ``databento_dbn`` modules.

    Faked rather than skipped-if-missing: the reconnect claim has to hold on
    a CI runner that has never heard of Databento.
    """
    databento = types.ModuleType("databento")
    databento.Live = live_factory
    dbn = types.ModuleType("databento_dbn")
    dbn.SymbolMappingMsg = type("SymbolMappingMsg", (), {})
    dbn.SymbolMappingMsgV1 = type("SymbolMappingMsgV1", (), {})
    dbn.OHLCVMsg = type("OHLCVMsg", (), {})
    dbn.FIXED_PRICE_SCALE = 1_000_000_000
    return {"databento": databento, "databento_dbn": dbn}


class StreamReconnectTests(unittest.TestCase):
    """The second half of the same bug: if the Databento client raises
    mid-stream the process used to die with nothing to restart it."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.state_path = Path(self._tmp.name) / "flow-state.json"
        self.parked = threading.Event()

    def tearDown(self):
        self.parked.set()
        self._tmp.cleanup()

    def live_factory(self, flow_failure):
        parked = self.parked
        outer = self

        class FakeLive:
            def subscribe(self, *, dataset, schema, symbols, stype_in,
                          start=None):
                self.schema = schema

            def __iter__(self):
                if self.schema != "ohlcv-1m":
                    parked.wait(2.0)      # the liquidity thread, parked quietly
                    return iter(())
                outer.connects += 1
                raise flow_failure()

        return FakeLive

    def _run(self, flow_failure, delays_before_stop=3):
        self.connects = 0
        delays: list[float] = []

        def sleeper(seconds):
            if threading.current_thread() is not threading.main_thread():
                return
            delays.append(seconds)
            if len(delays) >= delays_before_stop:
                raise _StopTest()

        stdout = io.StringIO()
        modules = fake_databento(self.live_factory(flow_failure))
        with unittest.mock.patch.dict(sys.modules, modules):
            with unittest.mock.patch("time.sleep", sleeper):
                with contextlib.redirect_stdout(stdout):
                    outcome = self._invoke()
        events = []
        for line in stdout.getvalue().splitlines():
            try:
                parsed = json.loads(line)
            except ValueError:
                continue
            if isinstance(parsed, dict) and "event" in parsed:
                events.append(parsed)
        return outcome, delays, events

    def _invoke(self):
        try:
            return monitor.run(
                symbols=("SPY",), dataset="EQUS.MINI", publish_seconds=60.0,
                ingest_url="https://ingest.invalid", ingest_token="token",
                replay_start=0, stype_in="raw_symbol", default_scope="market",
                state_path=self.state_path, liquidity_schema="mbp-1")
        except _StopTest:
            return "stopped-by-test"

    def test_mid_stream_failure_reconnects_with_bounded_backoff(self):
        outcome, delays, events = self._run(
            lambda: ConnectionResetError("stream dropped"))
        self.assertEqual(outcome, "stopped-by-test")
        # It kept re-establishing the session instead of exiting.
        self.assertGreaterEqual(self.connects, 3)
        self.assertEqual(delays, [5.0, 10.0, 20.0])
        errors = [e for e in events if e["event"] == "stream_error"]
        self.assertGreaterEqual(len(errors), 3)
        self.assertEqual(errors[0]["error_class"], "ConnectionResetError")
        self.assertEqual(errors[0]["action"], "reconnect")
        self.assertTrue(any(e["event"] == "stream_reconnect" for e in events))
        self.assertTrue(any(e["event"] == "stream_connected" for e in events))

    def test_auth_failure_exits_instead_of_reconnecting_forever(self):
        # The broad reconnect handler must NOT swallow a rejected token:
        # retrying it would look alive while publishing nothing.
        outcome, delays, events = self._run(
            lambda: monitor.PublishAuthError(401, "bad token"))
        self.assertEqual(outcome, monitor.EXIT_AUTH_FAILURE)
        self.assertEqual(delays, [])
        self.assertEqual(self.connects, 1)
        auth = [e for e in events if e["event"] == "publish_auth_failed"]
        self.assertEqual(len(auth), 1)
        self.assertEqual(auth[0]["http_status"], 401)
        self.assertEqual(auth[0]["action"], "exit")
        self.assertEqual(auth[0]["exit_code"], monitor.EXIT_AUTH_FAILURE)


# --------------------------------------------------------------------------- #
# P7 -- live feed staleness
# --------------------------------------------------------------------------- #

def out_log_lines(stamp: datetime) -> str:
    """A realistic tail of databento-flow-monitor.out.log: several published
    lines, plus a trailing non-JSON line (the two log streams interleave), so
    the reader is proven to scan back to the last JSON object."""
    rows = []
    for offset in (2, 1, 0):
        rows.append(json.dumps({
            "published_at": (stamp - timedelta(minutes=offset)).isoformat(),
            "symbols": 23,
            "response": {"criticality": 0, "flow": 23, "components": 0}}))
    rows.append("Traceback (most recent call last):")
    return "\n".join(rows) + "\n"


class LiveFeedInvariantTests(unittest.TestCase):
    """P7 planted violations. Uses the graph_build fixture repo so the whole
    suite runs, not just the invariant under test."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        gi_tests.make_fixture(self.root)
        gi_tests.git_commit_all(self.root, "fixture files")
        self.evidence_dir = self.root / "logs"
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self._tmp.cleanup()

    def register(self, **overrides) -> None:
        feed = {
            "name": "flow_monitor",
            "description": "planted live feed",
            "evidence_path": "logs/flow.out.log",
            "stamp_field": "published_at",
            "max_age_hours": 24,
            "healer": "restart the scheduled task",
        }
        feed.update(overrides)
        config = gi_tests.load_config(self.root)
        config["live_feeds"] = {"flow_monitor": feed}
        gi_tests.save_config(self.root, config)

    def write_evidence(self, text: str, name: str = "flow.out.log") -> None:
        (self.evidence_dir / name).write_text(text, encoding="utf-8")

    def test_severity_is_report_not_hard(self):
        self.assertEqual(graph_invariants.BASE_SEVERITY["P7"], "report")

    def test_stale_evidence_fires(self):
        # The outage shape: the log exists and its last published_at is a
        # week old.
        self.register()
        self.write_evidence(out_log_lines(
            datetime.now(timezone.utc) - timedelta(days=7)))
        results, exit_code = gi_tests.run_invariants(self.root)
        self.assertEqual(results["P7"].count, 1)
        self.assertIn("flow_monitor: not published inside its window",
                      results["P7"].violations[0])
        self.assertIn("window 24h", results["P7"].violations[0])
        self.assertIn("restart the scheduled task", results["P7"].violations[0])
        # Report severity: loud, but it must not block a merge.
        self.assertEqual(exit_code, 0)
        md = (self.root / "_system" / "graph" / "INVARIANTS.md").read_text(
            encoding="utf-8")
        self.assertIn("not published inside its window", md)

    def test_absent_evidence_is_skipped_with_a_reason_not_violated(self):
        # The CI shape: the evidence is machine-local and simply is not there.
        self.register(evidence_path="logs/does-not-exist.out.log")
        results, exit_code = gi_tests.run_invariants(self.root)
        self.assertEqual(results["P7"].count, 0)
        self.assertEqual(results["P7"].violations, [])
        self.assertIn("SKIPPED", results["P7"].note)
        self.assertIn("evidence absent", results["P7"].note)
        self.assertIn("never a violation", results["P7"].note)
        self.assertEqual(exit_code, 0)
        md = (self.root / "_system" / "graph" / "INVARIANTS.md").read_text(
            encoding="utf-8")
        self.assertIn("SKIPPED", md)

    def test_fresh_evidence_passes(self):
        self.register()
        self.write_evidence(out_log_lines(datetime.now(timezone.utc)))
        results, exit_code = gi_tests.run_invariants(self.root)
        self.assertEqual(results["P7"].count, 0)
        self.assertIn("1/1 live feeds fresh", results["P7"].note)
        self.assertNotIn("SKIPPED", results["P7"].note)
        self.assertEqual(exit_code, 0)

    def test_unparseable_stamp_is_a_violation(self):
        # P6's rule, carried over: a stamp that cannot be parsed can never be
        # judged fresh. Distinct from an absent file, which is skipped.
        self.register()
        self.write_evidence(json.dumps({"published_at": "soon"}) + "\n")
        results, _ = gi_tests.run_invariants(self.root)
        self.assertEqual(results["P7"].count, 1)
        self.assertIn("can never be judged fresh",
                      results["P7"].violations[0])

    def test_present_but_carrying_no_stamp_field_is_a_violation(self):
        self.register()
        self.write_evidence("Traceback (most recent call last):\nboom\n")
        results, _ = gi_tests.run_invariants(self.root)
        self.assertEqual(results["P7"].count, 1)
        self.assertIn("can never be judged fresh",
                      results["P7"].violations[0])

    def test_registry_without_evidence_path_is_a_violation(self):
        self.register(evidence_path="")
        results, _ = gi_tests.run_invariants(self.root)
        self.assertEqual(results["P7"].count, 1)
        self.assertIn("no evidence_path registered",
                      results["P7"].violations[0])

    def test_empty_registry_is_zero_not_an_error(self):
        results, exit_code = gi_tests.run_invariants(self.root)
        self.assertEqual(results["P7"].count, 0)
        self.assertEqual(exit_code, 0)

    def test_violation_text_is_stable_so_a_waiver_can_target_it(self):
        self.register()
        self.write_evidence(out_log_lines(
            datetime.now(timezone.utc) - timedelta(days=7)))
        first, _ = gi_tests.run_invariants(self.root)
        self.write_evidence(out_log_lines(
            datetime.now(timezone.utc) - timedelta(days=9)))
        second, _ = gi_tests.run_invariants(self.root)
        self.assertEqual(first["P7"].violations, second["P7"].violations)


class LiveEvidencePathTests(unittest.TestCase):

    def test_home_rooted_path_expands_and_stays_absolute(self):
        path = graph_invariants._live_evidence_path(
            Path("/repo"), "~/.magis-market-risk/logs/x.out.log")
        self.assertTrue(path.is_absolute())
        self.assertNotIn("~", str(path))

    def test_relative_path_resolves_against_the_repo_root(self):
        path = graph_invariants._live_evidence_path(
            Path("/repo"), "dashboard/data/x.json")
        self.assertEqual(path, Path("/repo") / "dashboard/data/x.json")

    def test_blank_path_is_none(self):
        self.assertIsNone(
            graph_invariants._live_evidence_path(Path("/repo"), ""))
        self.assertIsNone(
            graph_invariants._live_evidence_path(Path("/repo"), None))

    def test_last_json_line_wins_over_earlier_ones(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "flow.out.log"
            path.write_text(out_log_lines(
                datetime(2026, 8, 3, 16, 14, tzinfo=timezone.utc)),
                encoding="utf-8")
            stamp = graph_invariants._live_stamp(path, "published_at")
            self.assertEqual(
                datetime.fromisoformat(str(stamp)),
                datetime(2026, 8, 3, 16, 14, tzinfo=timezone.utc))

    def test_single_json_document_also_works(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "feed.json"
            path.write_text(json.dumps(
                {"published_at": "2026-08-10T00:00:00+00:00"}, indent=2),
                encoding="utf-8")
            self.assertEqual(
                graph_invariants._live_stamp(path, "published_at"),
                "2026-08-10T00:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
