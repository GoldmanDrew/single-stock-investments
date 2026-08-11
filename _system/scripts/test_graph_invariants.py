from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import graph_build
import graph_invariants
import test_graph_build

REPO_ROOT = Path(__file__).resolve().parents[2]
TODAY = date(2026, 8, 10)


def make_fixture(root: Path) -> None:
    """graph_build's fixture plus the calibration store its outcome scores
    into -- without it E3 (correctly) fires on the clean fixture."""
    test_graph_build.make_fixture(root)
    test_graph_build.write_json(
        root / "_system" / "research" / "falsifier_calibration.json",
        {"buckets": {"owner_earnings_reinvestment_dcf|quality_reinvestment":
                     {"hits": 1, "misses": 0}}})


def run_invariants(root: Path, today: date = TODAY):
    results, exit_code, _ = graph_invariants.run(
        root, root / "_system" / "graph" / "graph.db",
        root / "_system" / "graph", today)
    return {r.id: r for r in results}, exit_code


def load_config(root: Path) -> dict:
    path = root / "_system" / "graph" / "graph_sources.json"
    return json.loads(path.read_text(encoding="utf-8"))


def save_config(root: Path, config: dict) -> None:
    path = root / "_system" / "graph" / "graph_sources.json"
    path.write_text(json.dumps(config, indent=1), encoding="utf-8")


def fixture_unguarded_corrections(root: Path) -> int:
    """Expected P1 count, derived from the fixture files themselves (the
    graph_build fixture belongs to test_graph_build and grows rows; a
    hard-coded count here goes stale the moment it does). Independent
    re-parse, not a call into the code under test."""
    import re
    guards = set(load_config(root).get("guards", {}))
    text = (root / "_system" / "memory" / "corrections.md").read_text(
        encoding="utf-8")
    count = 0
    for raw in text.splitlines():
        if not raw.startswith("|"):
            continue
        cells = [c.strip() for c in raw.strip().strip("|").split("|")]
        if len(cells) < 4 or not re.match(r"^\d{4}-\d{2}-\d{2}$", cells[0]):
            continue
        if graph_build.correction_slug(cells[0], cells[2]) not in guards:
            count += 1
    return count


def git_commit_all(root: Path, message: str) -> None:
    git = ["git", "-C", str(root), "-c", "user.email=fixture@test",
           "-c", "user.name=fixture", "-c", "core.autocrlf=false"]
    subprocess.run(git[:3] + ["add", "-A"], check=True)
    subprocess.run(git + ["commit", "-q", "-m", message], check=True)


class CleanFixtureTests(unittest.TestCase):
    """The unmodified graph_build fixture: only the deliberately-planted
    report-severity debt fires, and no hard invariant does."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name)
        make_fixture(cls.root)
        git_commit_all(cls.root, "fixture files")
        cls.results, cls.exit_code = run_invariants(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_exit_zero(self):
        self.assertEqual(self.exit_code, 0)

    def test_p1_fires_on_prose_corrections(self):
        # Fixture rows without a guard entry -- P1 must see every one of
        # them (the fixture proves P1 CAN fire; severity stays report).
        expected = fixture_unguarded_corrections(self.root)
        self.assertGreaterEqual(expected, 2)
        self.assertEqual(self.results["P1"].count, expected)
        self.assertEqual(self.results["P1"].severity, "report")

    def test_hard_invariants_green(self):
        for inv_id in ("P2", "P3", "P4", "E2", "E3", "E4", "E5"):
            self.assertEqual(self.results[inv_id].count, 0, inv_id)
            self.assertEqual(self.results[inv_id].severity, "hard", inv_id)

    def test_e2_not_vacuous_with_typed_falsifiers(self):
        # 1 typed falsifier, due 2026-06-30, outcome resolved 2026-07-01.
        self.assertIn("1 typed, 1 matured", self.results["E2"].note)
        self.assertNotIn("vacuous", self.results["E2"].note)

    def test_e6_fires_on_undecided_proposal(self):
        self.assertEqual(self.results["E6"].count, 1)

    def test_reports_written(self):
        md = (self.root / "_system" / "graph" / "INVARIANTS.md").read_text(
            encoding="utf-8")
        payload = json.loads((self.root / "_system" / "graph" /
                              "invariants.json").read_text(encoding="utf-8"))
        for inv_id in graph_invariants.BASE_SEVERITY:
            self.assertIn(f"| {inv_id} |", md)
        self.assertEqual(len(payload["invariants"]),
                         len(graph_invariants.BASE_SEVERITY))
        self.assertEqual(payload["exit_code"], 0)


class PlantedViolationTests(unittest.TestCase):
    """Every invariant gets a planted violation proving it FIRES -- the
    no-vacuous-validators rule applied to the validator suite itself."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        make_fixture(self.root)
        git_commit_all(self.root, "fixture files")

    def tearDown(self):
        self._tmp.cleanup()

    def test_p1_new_unguarded_correction_raises_count(self):
        baseline = fixture_unguarded_corrections(self.root)
        path = self.root / "_system" / "memory" / "corrections.md"
        path.write_text(path.read_text(encoding="utf-8")
                        + "| 2026-02-01 | - | Another prose-only error. |"
                        " Just remember it. | chat |\n", encoding="utf-8")
        results, _ = run_invariants(self.root)
        self.assertEqual(results["P1"].count, baseline + 1)

    def test_p2_guard_with_unwired_enforcer_fires_and_exits_1(self):
        config = load_config(self.root)
        slug = graph_build.correction_slug(
            "2026-01-06", "Prose-only fixture error.")
        config["guards"][slug] = [{
            "id": "unwired-guard", "label": "guard no CI job invokes",
            "script": "_system/scripts/scan_orphan.py", "function": None,
            "enforced_by": ["_system/scripts/scan_orphan.py"]}]
        save_config(self.root, config)
        results, exit_code = run_invariants(self.root)
        self.assertEqual(results["P2"].count, 1)
        self.assertIn("unwired-guard", results["P2"].violations[0])
        self.assertEqual(exit_code, 1)

    def test_p6_stale_feed_fires_fresh_feed_passes(self):
        config = load_config(self.root)
        (self.root / "dashboard" / "data").mkdir(parents=True, exist_ok=True)
        stale = self.root / "dashboard" / "data" / "stale_feed.json"
        stale.write_text(json.dumps(
            {"generated_at": "2026-01-01T00:00:00+00:00"}), encoding="utf-8")
        fresh = self.root / "dashboard" / "data" / "fresh_feed.json"
        fresh.write_text(json.dumps(
            {"generated_at": datetime.now(timezone.utc).isoformat()}),
            encoding="utf-8")
        config["data_feeds"] = {
            "stale_feed": {"path": "dashboard/data/stale_feed.json",
                           "stamp_field": "generated_at",
                           "max_age_hours": 48, "healer": "run the builder"},
            "fresh_feed": {"path": "dashboard/data/fresh_feed.json",
                           "stamp_field": "generated_at",
                           "max_age_hours": 48, "healer": "run the builder"},
        }
        save_config(self.root, config)
        results, exit_code = run_invariants(self.root)
        self.assertEqual(results["P6"].count, 1)
        self.assertIn("stale_feed: stale (window 48h)",
                      results["P6"].violations[0])
        self.assertEqual(exit_code, 1)

    def test_p6_unparseable_stamp_and_missing_file_fire(self):
        config = load_config(self.root)
        (self.root / "dashboard" / "data").mkdir(parents=True, exist_ok=True)
        garbled = self.root / "dashboard" / "data" / "garbled_feed.json"
        garbled.write_text(json.dumps({"generated_at": "soon"}),
                           encoding="utf-8")
        config["data_feeds"] = {
            "garbled_feed": {"path": "dashboard/data/garbled_feed.json",
                             "stamp_field": "generated_at",
                             "max_age_hours": 48, "healer": "h"},
            "ghost_feed": {"path": "dashboard/data/ghost_feed.json",
                           "stamp_field": "generated_at",
                           "max_age_hours": 48, "healer": "h"},
        }
        save_config(self.root, config)
        results, _ = run_invariants(self.root)
        self.assertEqual(results["P6"].count, 2)
        joined = " | ".join(results["P6"].violations)
        self.assertIn("can never be judged fresh", joined)
        self.assertIn("file missing", joined)

    def test_p3_lane_with_no_commit_fires(self):
        config = load_config(self.root)
        config["lanes"].append({"name": "dead-lane",
                                "subject_regex": "^never-matches-anything",
                                "freshness_hours": 48})
        save_config(self.root, config)
        results, exit_code = run_invariants(self.root)
        self.assertEqual(results["P3"].count, 1)
        self.assertIn("dead-lane", results["P3"].violations[0])
        self.assertEqual(exit_code, 1)

    def test_p3_stale_lane_fires(self):
        git = ["git", "-C", str(self.root), "-c", "user.email=fixture@test",
               "-c", "user.name=fixture"]
        env = dict(os.environ, GIT_COMMITTER_DATE="2026-01-01T00:00:00Z")
        subprocess.run(git + ["commit", "-q", "--allow-empty",
                              "--date", "2026-01-01T00:00:00Z",
                              "-m", "chore(old-lane): ancient commit"],
                       check=True, env=env)
        config = load_config(self.root)
        config["lanes"].append({"name": "old-lane",
                                "subject_regex": "^chore\\(old-lane\\)",
                                "freshness_hours": 48})
        save_config(self.root, config)
        results, exit_code = run_invariants(self.root)
        self.assertEqual(results["P3"].count, 1)
        self.assertIn("old-lane", results["P3"].violations[0])
        self.assertEqual(exit_code, 1)

    def test_p3_lane_projection_prefers_origin_main_when_ref_exists(self):
        # PR-checkout shape: a lane's commits landed on main AFTER the PR
        # branch point, so they are absent from HEAD's history but present
        # on origin/main. Old behavior read only HEAD and fired P3
        # spuriously; run() must set GRAPH_LANE_REF=origin/main (and unset
        # it afterwards) so graph_build projects lanes from origin/main.
        config = load_config(self.root)
        config["lanes"].append({"name": "nightly",
                                "subject_regex": "^chore\\(nightly\\)",
                                "freshness_hours": 48})
        save_config(self.root, config)
        git = ["git", "-C", str(self.root), "-c", "user.email=fixture@test",
               "-c", "user.name=fixture"]
        tree = subprocess.run(git + ["rev-parse", "HEAD^{tree}"], check=True,
                              capture_output=True, text=True).stdout.strip()
        head = subprocess.run(git + ["rev-parse", "HEAD"], check=True,
                              capture_output=True, text=True).stdout.strip()
        fresh = subprocess.run(
            git + ["commit-tree", tree, "-p", head,
                   "-m", "chore(nightly): fresh main-only lane commit"],
            check=True, capture_output=True, text=True).stdout.strip()
        subprocess.run(git + ["update-ref", "refs/remotes/origin/main", fresh],
                       check=True)
        results, exit_code = run_invariants(self.root)
        self.assertEqual(results["P3"].count, 0,
                         results["P3"].violations)
        self.assertEqual(exit_code, 0)
        # The preference must not leak into later builds against other roots.
        self.assertNotIn(graph_invariants.LANE_REF_ENV, os.environ)

    def test_p4_receipt_in_pending_fires(self):
        test_graph_build.write_json(
            self.root / "_system" / "reviews" / "pending" /
            "power_zone_security_run_2026-01-03_stray.json",
            {"stages": {}, "scope": "targeted"})
        results, exit_code = run_invariants(self.root)
        self.assertEqual(results["P4"].count, 1)
        self.assertIn("pending", results["P4"].violations[0])
        self.assertEqual(exit_code, 1)

    def test_p4_receipt_shaped_payload_fires_without_run_filename(self):
        test_graph_build.write_json(
            self.root / "_system" / "data" / "stray_receipt.json",
            {"stages": {"contracts": {}}, "dry_run": False})
        results, exit_code = run_invariants(self.root)
        self.assertEqual(results["P4"].count, 1)
        self.assertEqual(exit_code, 1)

    def test_p5_fires_on_orphan_validator(self):
        test_graph_build.write_text(
            self.root / "_system" / "scripts" / "scan_orphan.py", "print(1)\n")
        results, _ = run_invariants(self.root)
        self.assertEqual(results["P5"].count, 1)
        self.assertIn("scan_orphan.py", results["P5"].violations[0])

    def test_e1_fires_on_decision_grade_component_without_typed(self):
        test_graph_build.write_json(
            self.root / "NTF" / "research" / "valuation_contract.json", {
                "status": "decision_grade", "ticker": "NTF",
                "as_of": "2026-01-01",
                "economic_ownership_map": [{
                    "component_id": "core", "label": "No typed falsifier",
                    "method": "net_asset_value",
                    "valuation_status": "bounded_estimate",
                    "falsifier": "Prose only."}]})
        results, _ = run_invariants(self.root)
        self.assertEqual(results["E1"].count, 1)
        self.assertIn("NTF:core", results["E1"].violations[0])
        self.assertIn("net_asset_value", results["E1"].violations[0])
        self.assertIn("typed coverage 1/2 (50.0%)", results["E1"].note)
        # Zero-coverage methods are aggregated so the note stays diffable.
        self.assertIn("1 methods 0/1", results["E1"].note)

    def test_e2_overdue_typed_falsifier_fires(self):
        specs = self.root / "TST" / "research" / "falsifier_specs.json"
        payload = json.loads(specs.read_text(encoding="utf-8"))
        payload["specs"].append(
            {"component_id": "core", "metric": "revenue_m", "comparator": "<",
             "threshold": 5, "unit": "USD millions", "due": "2026-05-01",
             "source_hint": None, "derived_from": None, "untestable": False,
             "rationale": "planted overdue"})
        specs.write_text(json.dumps(payload), encoding="utf-8")
        results, exit_code = run_invariants(self.root)
        self.assertEqual(results["E2"].count, 1)
        self.assertIn("revenue-m", results["E2"].violations[0])
        self.assertEqual(exit_code, 1)

    def test_e2_typed_without_due_fires(self):
        specs = self.root / "TST" / "research" / "falsifier_specs.json"
        payload = json.loads(specs.read_text(encoding="utf-8"))
        payload["specs"].append(
            {"component_id": "core", "metric": "dueless_m", "comparator": "<",
             "threshold": 5, "unit": "USD millions", "due": None,
             "source_hint": None, "derived_from": None, "untestable": False,
             "rationale": "planted dueless"})
        specs.write_text(json.dumps(payload), encoding="utf-8")
        results, exit_code = run_invariants(self.root)
        self.assertEqual(results["E2"].count, 1)
        self.assertIn("can never mature", results["E2"].violations[0])
        self.assertEqual(exit_code, 1)

    def test_e2_malformed_lexically_past_due_fires_instead_of_crashing(self):
        # '2026-06-31' sorts lexically before today, so the old code reached
        # date.fromisoformat and crashed the whole suite with an uncaught
        # ValueError -- no INVARIANTS.md written. It must instead be an E2
        # violation: an unparseable due can never mature.
        specs = self.root / "TST" / "research" / "falsifier_specs.json"
        payload = json.loads(specs.read_text(encoding="utf-8"))
        payload["specs"].append(
            {"component_id": "core", "metric": "bad_date_m", "comparator": "<",
             "threshold": 5, "unit": "USD millions", "due": "2026-06-31",
             "source_hint": None, "derived_from": None, "untestable": False,
             "rationale": "planted malformed due"})
        specs.write_text(json.dumps(payload), encoding="utf-8")
        results, exit_code = run_invariants(self.root)
        self.assertEqual(results["E2"].count, 1)
        self.assertIn("bad-date-m", results["E2"].violations[0])
        self.assertIn("unparseable due", results["E2"].violations[0])
        self.assertIn("can never mature", results["E2"].violations[0])
        self.assertEqual(exit_code, 1)
        md = (self.root / "_system" / "graph" / "INVARIANTS.md").read_text(
            encoding="utf-8")
        self.assertIn("unparseable due", md)

    def test_e2_lexically_future_garbage_due_fires(self):
        # '2026-Q3' and 'TBD' sort lexically after today's ISO date, so the
        # old string comparison silently treated them as not-yet-matured
        # forever. Both must be violations.
        specs = self.root / "TST" / "research" / "falsifier_specs.json"
        payload = json.loads(specs.read_text(encoding="utf-8"))
        for metric, due in (("quarterly_m", "2026-Q3"), ("someday_m", "TBD")):
            payload["specs"].append(
                {"component_id": "core", "metric": metric, "comparator": "<",
                 "threshold": 5, "unit": "USD millions", "due": due,
                 "source_hint": None, "derived_from": None,
                 "untestable": False, "rationale": "planted garbage due"})
        specs.write_text(json.dumps(payload), encoding="utf-8")
        results, exit_code = run_invariants(self.root)
        self.assertEqual(results["E2"].count, 2)
        joined = " ".join(results["E2"].violations)
        self.assertIn("2026-Q3", joined)
        self.assertIn("TBD", joined)
        self.assertEqual(joined.count("can never mature"), 2)
        self.assertEqual(exit_code, 1)

    def test_e2_vacuously_green_with_zero_typed_says_so(self):
        (self.root / "TST" / "research" / "falsifier_specs.json").unlink()
        results, exit_code = run_invariants(self.root)
        self.assertEqual(results["E2"].count, 0)
        self.assertEqual(results["E2"].note, "vacuously green (0 typed)")
        self.assertEqual(exit_code, 0)
        md = (self.root / "_system" / "graph" / "INVARIANTS.md").read_text(
            encoding="utf-8")
        self.assertIn("vacuously green (0 typed)", md)

    def test_e3_outcome_without_scores_edge_fires(self):
        path = self.root / "_system" / "research" / "falsifier_outcomes.jsonl"
        path.write_text(path.read_text(encoding="utf-8") + json.dumps(
            {"ticker": "TST", "component_id": "core", "metric": "owner_cash_m",
             "result": "miss", "resolved_at": "2026-07-02"}) + "\n",
            encoding="utf-8")
        results, exit_code = run_invariants(self.root)
        self.assertEqual(results["E3"].count, 1)
        self.assertIn("no SCORES edge", results["E3"].violations[0])
        self.assertEqual(exit_code, 1)

    def test_e3_missing_calibration_store_fires(self):
        # The fixture outcome scores a bucket, but the store that should
        # hold it is gone.
        (self.root / "_system" / "research" /
         "falsifier_calibration.json").unlink()
        results, exit_code = run_invariants(self.root)
        self.assertEqual(results["E3"].count, 1)
        self.assertIn("calibration store missing", results["E3"].violations[0])
        self.assertEqual(exit_code, 1)

    def test_e3_bucket_absent_from_store_fires(self):
        test_graph_build.write_json(
            self.root / "_system" / "research" / "falsifier_calibration.json",
            {"buckets": {"some_other_method|other_zone": {"hits": 9}}})
        results, exit_code = run_invariants(self.root)
        self.assertEqual(results["E3"].count, 1)
        self.assertIn("not in calibration store", results["E3"].violations[0])
        self.assertEqual(exit_code, 1)

    def test_e4_in_place_rewrite_fires(self):
        path = self.root / "_system" / "memory" / "MEMORY.md"
        path.write_text(path.read_text(encoding="utf-8").replace(
            "New rule about testing better.",
            "New rule about testing much better."), encoding="utf-8")
        results, exit_code = run_invariants(self.root)
        self.assertEqual(results["E4"].count, 1)
        self.assertIn("new rule about testing", results["E4"].violations[0])
        self.assertEqual(exit_code, 1)

    def test_e4_deleted_belief_fires(self):
        path = self.root / "_system" / "memory" / "MEMORY.md"
        kept = [line for line in
                path.read_text(encoding="utf-8").splitlines()
                if "Old rule about testing." not in line]
        path.write_text("\n".join(kept) + "\n", encoding="utf-8")
        results, exit_code = run_invariants(self.root)
        self.assertEqual(results["E4"].count, 1)
        self.assertIn("[superseded]", results["E4"].violations[0])
        self.assertEqual(exit_code, 1)

    def test_e4_committed_rewrite_fires_via_history_window(self):
        # The repro this closes: rewrite a promoted belief in place AND
        # commit it. HEAD then equals the working tree, so the old
        # HEAD-vs-worktree diff could never fire in CI. The bounded
        # historical baseline (oldest of the last 15 commits touching
        # MEMORY.md) must catch it.
        path = self.root / "_system" / "memory" / "MEMORY.md"
        path.write_text(path.read_text(encoding="utf-8").replace(
            "New rule about testing better.",
            "New rule about testing much better."), encoding="utf-8")
        git_commit_all(self.root, "rewrite belief in place")
        results, exit_code = run_invariants(self.root)
        self.assertEqual(results["E4"].count, 1)
        self.assertIn("new rule about testing", results["E4"].violations[0])
        self.assertIn("rewritten or deleted without supersede",
                      results["E4"].violations[0])
        self.assertEqual(exit_code, 1)

    def test_e4_committed_deletion_fires_via_history_window(self):
        path = self.root / "_system" / "memory" / "MEMORY.md"
        kept = [line for line in
                path.read_text(encoding="utf-8").splitlines()
                if "Old rule about testing." not in line]
        path.write_text("\n".join(kept) + "\n", encoding="utf-8")
        git_commit_all(self.root, "delete belief outright")
        results, exit_code = run_invariants(self.root)
        self.assertEqual(results["E4"].count, 1)
        self.assertIn("[superseded]", results["E4"].violations[0])
        self.assertEqual(exit_code, 1)

    def test_e4_committed_status_tag_change_is_not_a_violation(self):
        # Retirement is a status-tag change that keeps the text; committed,
        # it must pass both the HEAD diff and the historical baseline.
        path = self.root / "_system" / "memory" / "MEMORY.md"
        path.write_text(path.read_text(encoding="utf-8").replace(
            "`[active 2026-01-03 · agent]`", "`[superseded 2026-02-01]`"),
            encoding="utf-8")
        git_commit_all(self.root, "retire belief by status tag")
        results, exit_code = run_invariants(self.root)
        self.assertEqual(results["E4"].count, 0)
        self.assertEqual(exit_code, 0)

    def test_e4_status_tag_change_is_not_a_violation(self):
        path = self.root / "_system" / "memory" / "MEMORY.md"
        path.write_text(path.read_text(encoding="utf-8").replace(
            "`[active 2026-01-03 · agent]`", "`[superseded 2026-02-01]`"),
            encoding="utf-8")
        results, exit_code = run_invariants(self.root)
        self.assertEqual(results["E4"].count, 0)
        self.assertEqual(exit_code, 0)

    def test_e5_belief_citing_missing_source_fires(self):
        path = self.root / "_system" / "memory" / "MEMORY.md"
        path.write_text(path.read_text(encoding="utf-8")
                        + "- Planted belief citing a ghost. —"
                        " `_system/nonexistent/ghost.md` `[active 2026-01-04]`\n",
                        encoding="utf-8")
        results, exit_code = run_invariants(self.root)
        self.assertEqual(results["E5"].count, 1)
        self.assertIn("ghost.md", results["E5"].violations[0])
        self.assertEqual(exit_code, 1)

    def test_e5_waiver_suppresses_named_violation_only(self):
        path = self.root / "_system" / "memory" / "MEMORY.md"
        path.write_text(path.read_text(encoding="utf-8")
                        + "- Planted belief citing a ghost. —"
                        " `_system/nonexistent/ghost.md` `[active 2026-01-04]`\n",
                        encoding="utf-8")
        config = load_config(self.root)
        config["invariants"] = {"waivers": {"E5": [{
            "violation": "belief:planted-belief-citing-a-ghost ->"
                         " source:_system/nonexistent/ghost.md",
            "note": "2026-01-04: planted waiver"}]}}
        save_config(self.root, config)
        results, exit_code = run_invariants(self.root)
        self.assertEqual(results["E5"].count, 0)
        self.assertEqual(len(results["E5"].waived), 1)
        self.assertEqual(exit_code, 0)
        md = (self.root / "_system" / "graph" / "INVARIANTS.md").read_text(
            encoding="utf-8")
        self.assertIn("planted waiver", md)

    def test_stale_waiver_is_reported(self):
        config = load_config(self.root)
        config["invariants"] = {"waivers": {"E5": [{
            "violation": "belief:no-such -> source:nowhere",
            "note": "2026-01-04: stale"}]}}
        save_config(self.root, config)
        run_invariants(self.root)
        md = (self.root / "_system" / "graph" / "INVARIANTS.md").read_text(
            encoding="utf-8")
        self.assertIn("STALE waiver", md)

    def test_override_demotes_hard_to_report_with_todo(self):
        config = load_config(self.root)
        slug = graph_build.correction_slug(
            "2026-01-06", "Prose-only fixture error.")
        config["guards"][slug] = [{
            "id": "unwired-guard", "label": "guard no CI job invokes",
            "script": "_system/scripts/scan_orphan.py", "function": None,
            "enforced_by": ["_system/scripts/scan_orphan.py"]}]
        config["invariants"] = {"overrides": {"P2": {
            "severity": "report", "todo": "2026-01-06: wire it later"}}}
        save_config(self.root, config)
        results, exit_code = run_invariants(self.root)
        self.assertEqual(results["P2"].count, 1)
        self.assertEqual(results["P2"].severity, "report")
        self.assertEqual(exit_code, 0)
        md = (self.root / "_system" / "graph" / "INVARIANTS.md").read_text(
            encoding="utf-8")
        self.assertIn("demoted", md)
        self.assertIn("2026-01-06: wire it later", md)

    def test_override_without_todo_is_not_applied(self):
        config = load_config(self.root)
        slug = graph_build.correction_slug(
            "2026-01-06", "Prose-only fixture error.")
        config["guards"][slug] = [{
            "id": "unwired-guard", "label": "guard no CI job invokes",
            "script": "_system/scripts/scan_orphan.py", "function": None,
            "enforced_by": ["_system/scripts/scan_orphan.py"]}]
        config["invariants"] = {"overrides": {"P2": {"severity": "report"}}}
        save_config(self.root, config)
        results, exit_code = run_invariants(self.root)
        self.assertEqual(results["P2"].severity, "hard")
        self.assertEqual(exit_code, 1)

    def test_e6_delta_against_previous_committed_report(self):
        run_invariants(self.root)
        git_commit_all(self.root, "commit first invariants report")
        daily = self.root / "_system" / "memory" / "daily" / "2026-01-02.md"
        # A new [PROPOSED] heading block: bullets under an existing heading
        # merge into that block's single item and would not change the count.
        daily.write_text(daily.read_text(encoding="utf-8")
                         + "\n### [PROPOSED STAHL]\n\n"
                         "- A second undecided proposal bullet.\n",
                         encoding="utf-8")
        results, _ = run_invariants(self.root)
        self.assertEqual(results["E6"].count, 2)
        self.assertEqual(results["E6"].delta, "+1")
        self.assertEqual(results["P1"].delta, "0")


class RealRepoTests(unittest.TestCase):
    """The committed suite must exit 0 on the current repo (reports written
    to a tempdir so the committed INVARIANTS.md is not clobbered mid-test)."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        out = Path(cls._tmp.name)
        cls.results, cls.exit_code, cls.meta = graph_invariants.run(
            REPO_ROOT, out / "graph.db", out)
        cls.by_id = {r.id: r for r in cls.results}

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_exit_zero_on_current_repo(self):
        hard = [r.id for r in self.results
                if r.severity == "hard" and r.count]
        self.assertEqual(self.exit_code, 0,
                         f"hard invariants firing on the real repo: {hard}")

    def test_all_eleven_ran(self):
        self.assertEqual(sorted(self.by_id),
                         sorted(graph_invariants.BASE_SEVERITY))

    def test_p2_demotion_is_declared_not_silent(self):
        p2 = self.by_id["P2"]
        if p2.severity != p2.base_severity:
            self.assertIn("demoted", p2.note)
            self.assertIn("TODO", p2.note)

    def test_e2_never_plain_green_on_no_data(self):
        e2 = self.by_id["E2"]
        if not any("typed" in v for v in e2.violations):
            self.assertTrue("vacuously green (0 typed)" in e2.note
                            or "typed" in e2.note,
                            "E2 must name the typed population it judged")


def seed_lens_plane(root: Path) -> None:
    """Clean lens-plane layer on the graph_build fixture: canonical vocab and
    derived-artifact registries, canonical persona registries, and TST fully
    classified with a fresh lens plane (agreeing with the fixture registry's
    archetype=compounder so no surface conflicts)."""
    from persona_groups import INDEPENDENCE_GROUPS
    config = load_config(root)
    config["classification_vocab"] = {
        "sentinels": ["", "pending", "unknown", "-"],
        "fields": {
            "archetype": ["croupier", "compounder", "serial_acquirer",
                          "platform", "holding_co", "optionality",
                          "turnaround", "infrastructure"],
            "payoff_lens": ["operating", "asset", "event", "levered"],
            "moat": ["widening", "stable", "eroding", "unproven", "n/a"],
            "dhando": ["full", "partial", "none"],
        },
    }
    config["derived_artifacts"] = {
        "lenses": {"source": "research/valuation.json",
                   "derived": "research/lenses.json",
                   "missing_when": "decision_grade",
                   "healer": "persona_lens.py --all"},
        "valuation_route": {"source": "research/valuation.json",
                            "derived": "research/valuation_route.json",
                            "missing_when": "never",
                            "healer": "power_zone_router.py"},
    }
    save_config(root, config)
    persona_ids = sorted(INDEPENDENCE_GROUPS)
    test_graph_build.write_json(
        root / "_system" / "lenses" / "personas.json",
        {"personas": {pid: {} for pid in persona_ids}})
    test_graph_build.write_json(
        root / "_system" / "frameworks" / "power_zones.json",
        {"zones": {pid: {} for pid in persona_ids}})
    research = root / "TST" / "research"
    test_graph_build.write_json(research / "valuation.json", {
        "as_of": "2026-08-01",
        "payoff_lens": "asset",
        "classification_inputs": {"archetype": "compounder",
                                  "moat": "stable", "dhando": "partial"},
    })
    test_graph_build.write_json(research / "lenses.json", {
        "as_of": "2026-08-01",
        "consensus": {"stance": "watch"},
        "valuation_blend": {"contributors": [{"persona": "hk"},
                                             {"persona": "stahl"}]},
    })
    test_graph_build.write_json(research / "valuation_route.json",
                                {"as_of": "2026-08-01"})


class LensPlaneTests(unittest.TestCase):
    """L1-L6: clean seeded fixture is green with non-vacuous notes, and every
    invariant gets a planted violation proving it fires."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        make_fixture(self.root)
        seed_lens_plane(self.root)
        git_commit_all(self.root, "fixture files")

    def edit_json(self, rel: str, mutate) -> None:
        path = self.root / rel
        doc = json.loads(path.read_text(encoding="utf-8"))
        mutate(doc)
        test_graph_build.write_json(path, doc)

    def test_clean_lens_plane_green_and_not_vacuous(self):
        results, exit_code = run_invariants(self.root)
        self.assertEqual(exit_code, 0)
        for inv_id in ("L1", "L2", "L3", "L4", "L5", "L6"):
            self.assertEqual(results[inv_id].count, 0, inv_id)
            self.assertNotIn("vacuous", results[inv_id].note, inv_id)
        self.assertIn("1/1 tickers resolve", results["L1"].note)

    def test_l1_fires_when_no_surface_classifies(self):
        self.edit_json("TST/research/valuation.json", lambda doc: (
            doc.pop("payoff_lens"),
            doc.__setitem__("classification_inputs", {})))
        results, _ = run_invariants(self.root)
        self.assertEqual(results["L1"].count, 1)
        self.assertIn("TST", results["L1"].violations[0])

    def test_l1_resolves_through_classification_inputs(self):
        # The shadowed-classification heal: classification_inputs alone must
        # count as classified (the old persona reader looked top-level only).
        self.edit_json("TST/research/valuation.json", lambda doc: (
            doc.pop("payoff_lens"),
            doc["classification_inputs"].__setitem__("payoff_lens", "asset")))
        results, _ = run_invariants(self.root)
        self.assertEqual(results["L1"].count, 0)
        self.assertIn("classification_inputs 1", results["L1"].note)

    def test_l2_fires_on_conflicting_surfaces(self):
        self.edit_json("TST/research/valuation.json", lambda doc: (
            doc["classification_inputs"].__setitem__("payoff_lens",
                                                     "operating")))
        results, _ = run_invariants(self.root)
        self.assertEqual(results["L2"].count, 1)
        self.assertIn("payoff_lens", results["L2"].violations[0])

    def test_l2_registry_default_is_not_a_conflict(self):
        self.edit_json("_system/portfolio/registry.json", lambda doc: (
            doc["holdings"]["TST"]["classification"].__setitem__(
                "archetype", "unknown")))
        results, _ = run_invariants(self.root)
        self.assertEqual(results["L2"].count, 0)

    def test_l3_fires_on_stale_and_missing(self):
        self.edit_json("TST/research/lenses.json", lambda doc: (
            doc.__setitem__("as_of", "2026-07-01")))
        results, _ = run_invariants(self.root)
        self.assertEqual(results["L3"].count, 1)
        self.assertIn("lenses.json behind", results["L3"].violations[0])
        (self.root / "TST" / "research" / "lenses.json").unlink()
        results, _ = run_invariants(self.root)
        self.assertEqual(results["L3"].count, 1)
        self.assertIn("missing for a decision_grade",
                      results["L3"].violations[0])

    def test_l3_missing_route_is_not_judged(self):
        (self.root / "TST" / "research" / "valuation_route.json").unlink()
        results, _ = run_invariants(self.root)
        self.assertEqual(results["L3"].count, 0)

    def test_l3_undated_artifacts_are_violations_not_skips(self):
        # The P6 rule: what cannot be judged fresh must never read as fresh.
        self.edit_json("TST/research/lenses.json", lambda doc: (
            doc.pop("as_of"),))
        results, _ = run_invariants(self.root)
        self.assertEqual(results["L3"].count, 1)
        self.assertIn("can never be judged fresh", results["L3"].violations[0])
        self.edit_json("TST/research/valuation.json", lambda doc: (
            doc.pop("as_of"),))
        results, _ = run_invariants(self.root)
        self.assertIn("valuation.json has no as_of",
                      "\n".join(results["L3"].violations))

    def test_lens_scan_survives_malformed_shapes(self):
        # A string where a dict belongs degrades to unclassified, never a
        # crashed suite with no report written.
        self.edit_json("TST/research/valuation.json", lambda doc: (
            doc.pop("payoff_lens"),
            doc.__setitem__("classification_inputs", "not-a-dict")))
        results, exit_code = run_invariants(self.root)
        self.assertEqual(results["L1"].count, 1)

    def test_l4_fires_on_noncanon_and_narrower_lens(self):
        self.edit_json("_system/lenses/personas.json", lambda doc: (
            doc["personas"].__setitem__("stahl", {"criteria": [
                {"id": "a", "check": "archetype_any", "values": ["bank"]}]})))
        self.edit_json("_system/frameworks/power_zones.json", lambda doc: (
            doc["zones"].__setitem__("stahl", {"rules": {
                "archetype": ["croupier", "optionality"]}})))
        self.edit_json("TST/research/valuation.json", lambda doc: (
            doc["classification_inputs"].__setitem__("moat", "narrow")))
        results, _ = run_invariants(self.root)
        violations = "\n".join(results["L4"].violations)
        self.assertIn("'bank' not canonical", violations)
        self.assertIn("moat value 'narrow' not canonical", violations)
        self.assertIn("stahl archetype lens misses zone values"
                      " croupier, optionality", violations)

    def test_l5_fires_on_low_coverage_stance(self):
        self.edit_json("TST/research/lenses.json", lambda doc: (
            doc.__setitem__("valuation_blend",
                            {"contributors": [{"persona": "hk"}]})))
        results, _ = run_invariants(self.root)
        self.assertEqual(results["L5"].count, 1)
        self.assertIn("1 contributing persona", results["L5"].violations[0])

    def test_l6_fires_on_registry_gap_and_collided_committee(self):
        self.edit_json("_system/lenses/personas.json", lambda doc: (
            doc["personas"].__setitem__("new_guy", {})))
        test_graph_build.write_json(
            self.root / "TST" / "research" / "committee_work" / "2026-08-01"
            / "manifest.json",
            {"ticker": "TST", "stage": "round_one_open", "selected_raters": [
                {"persona": "hohn"}, {"persona": "buffett_weschler"},
                {"persona": "munger"}]})
        results, _ = run_invariants(self.root)
        violations = "\n".join(results["L6"].violations)
        self.assertIn("'new_guy' has no entry", violations)
        self.assertIn("collapse to 2 canonical group(s)", violations)

    def test_l6_unknown_rater_cannot_mint_a_group(self):
        # [hohn, typo_a, typo_b] must FAIL, not pass with 3 minted groups.
        test_graph_build.write_json(
            self.root / "TST" / "research" / "committee_work" / "2026-08-01"
            / "manifest.json",
            {"ticker": "TST", "stage": "round_one_open", "selected_raters": [
                {"persona": "hohn"}, {"persona": "typo_a"},
                {"persona": "typo_b"}]})
        results, _ = run_invariants(self.root)
        self.assertIn("outside the canonical registry",
                      "\n".join(results["L6"].violations))

    def test_l6_superseded_manifest_not_judged(self):
        test_graph_build.write_json(
            self.root / "TST" / "research" / "committee_work" / "2026-08-01"
            / "manifest.json",
            {"ticker": "TST", "stage": "superseded", "selected_raters": [
                {"persona": "hohn"}, {"persona": "buffett_weschler"},
                {"persona": "munger"}]})
        results, _ = run_invariants(self.root)
        self.assertEqual(results["L6"].count, 0)


class BaselineRatchetTests(unittest.TestCase):
    """The committed baseline gates report-severity counts: a rise fails the
    run even though nothing is hard severity; equal or falling counts pass."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        make_fixture(self.root)
        seed_lens_plane(self.root)
        git_commit_all(self.root, "fixture files")

    def write_baseline(self, counts: dict) -> None:
        test_graph_build.write_json(
            self.root / "_system" / "graph" / "invariants_baseline.json",
            {"as_of": "2026-08-11", "counts": counts})

    def plant_l1(self) -> None:
        path = self.root / "TST" / "research" / "valuation.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc.pop("payoff_lens")
        doc["classification_inputs"] = {}
        test_graph_build.write_json(path, doc)

    def test_regression_fails_run(self):
        self.write_baseline({"L1": 0})
        self.plant_l1()
        results, exit_code = run_invariants(self.root)
        self.assertEqual(results["L1"].count, 1)
        self.assertEqual(exit_code, 1)
        md = (self.root / "_system" / "graph" / "INVARIANTS.md").read_text(
            encoding="utf-8")
        self.assertIn("RATCHET REGRESSION", md)

    def test_count_at_or_below_baseline_passes(self):
        self.write_baseline({"L1": 1})
        self.plant_l1()
        _, exit_code = run_invariants(self.root)
        self.assertEqual(exit_code, 0)

    def test_unarmed_id_never_gates(self):
        self.write_baseline({"L5": 0})
        self.plant_l1()
        _, exit_code = run_invariants(self.root)
        self.assertEqual(exit_code, 0)

    def test_absent_baseline_disarms(self):
        self.plant_l1()
        results, exit_code = run_invariants(self.root)
        self.assertEqual(results["L1"].count, 1)
        self.assertEqual(exit_code, 0)
        md = (self.root / "_system" / "graph" / "INVARIANTS.md").read_text(
            encoding="utf-8")
        self.assertIn("Ratchet disarmed", md)


if __name__ == "__main__":
    unittest.main()
