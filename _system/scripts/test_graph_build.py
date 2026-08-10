from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_memory_triage
import graph_build

REPO_ROOT = Path(__file__).resolve().parents[2]


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def db_rows(db_path: Path, sql: str, args: tuple = ()) -> list:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(sql, args).fetchall()
    finally:
        conn.close()


def meta_value(db_path: Path, key: str) -> str:
    rows = db_rows(db_path, "SELECT value FROM meta WHERE key = ?", (key,))
    return rows[0]["value"] if rows else ""


def make_fixture(root: Path) -> None:
    """A minimal synthetic repo exercising every projection source."""
    guarded_slug = graph_build.correction_slug(
        "2026-01-05", "Guarded fixture error with executable assert.")
    write_json(root / "_system" / "graph" / "graph_sources.json", {
        "lanes": [{"name": "valuation",
                   "subject_regex": "^chore\\(valuation\\)",
                   "freshness_hours": 48}],
        "guards": {guarded_slug: [{
            "id": "demo-guard", "label": "demo guard",
            "script": "_system/scripts/scan_demo.py", "function": None,
            "enforced_by": ["_system/scripts/scan_demo.py"]}]},
        "falsifier_enforcement": {"typed_coverage_threshold": 0.8,
                                  "enforcement_enabled": False},
    })
    write_json(root / "_system" / "portfolio" / "registry.json", {
        "meta": {}, "watchlist": {},
        "holdings": {"TST": {
            "company": "Test Co", "market": "US", "onboarded": "2026-01-01",
            "classification": {"archetype": "compounder", "stance": "watch",
                               "investment_sleeve": "tech"}}},
    })
    write_json(root / "TST" / "research" / "valuation_contract.json", {
        "status": "decision_grade", "ticker": "TST", "as_of": "2026-01-01",
        "evidence": {"blockers": [
            "A complete economic ownership map has not been supplied.",
            "Market price per share is missing or non-positive."]},
        "economic_ownership_map": [{
            "component_id": "core", "label": "Core engine",
            "method": "owner_earnings_reinvestment_dcf",
            "category": "operating_business", "treatment": "additive",
            "valuation_status": "bounded_estimate",
            "falsifier": "Primary evidence shows worse than low case."}],
        "monitoring": {"falsifiers": [
            "Primary evidence shows worse than low case.",
            "Extra monitoring falsifier."]},
    })
    write_json(root / "TST" / "research" / "falsifier_specs.json", {
        "specs": [
            {"component_id": "core", "metric": "owner_cash_m", "comparator": "<",
             "threshold": 100, "unit": "USD millions", "due": "2026-06-30",
             "source_hint": "companyfacts", "derived_from": "prose",
             "untestable": False, "rationale": "typed"},
            {"component_id": "core", "metric": "vibes", "comparator": None,
             "threshold": None, "unit": None, "due": None, "source_hint": None,
             "derived_from": None, "untestable": True, "rationale": "prose"}],
    })
    write_json(root / "TST" / "research" / "valuation_fact_ledger.json", {
        "schema_version": "1.0", "ticker": "TST", "facts": [
            {"field_id": "cash_m", "value": 1.0, "unit": "USD millions",
             "locked": True, "confidence": "high",
             "source": {"ref": "TST/research/evidence/sec_companyfacts.json",
                        "locator": "us-gaap:Cash", "as_of": "2025-12-31"}},
            {"field_id": "unlocked_m", "locked": False}],
    })
    write_json(root / "TST" / "research" / "evidence" / "sec_companyfacts.json", {})
    write_json(root / "_system" / "data" / "runs" /
               "power_zone_security_run_2026-01-02_tst.json", {
                   "schema_version": "1.0", "as_of": "2026-01-02",
                   "scope": "targeted", "dry_run": False, "ticker_count": 1,
                   "stages": {"contracts": {"written": [
                       {"ticker": "TST", "status": "decision_grade"}]}}})
    write_json(root / "_system" / "data" / "contract_backfill_queue.json", {
        "updated": "2026-01-02", "wave_size": 1, "total_pending": 1,
        "tickers": ["TST"], "dispatch_attempts": {"TST": 1},
        "stall_breaker": {"active": False}, "reason": "fixture"})
    write_text(root / "_system" / "research" / "falsifier_outcomes.jsonl",
               json.dumps({"ticker": "TST", "component_id": "core",
                           "metric": "owner_cash_m", "result": "hit",
                           "resolved_at": "2026-07-01",
                           "method_id": "owner_earnings_reinvestment_dcf",
                           "power_zone": "quality_reinvestment"}) + "\n")
    write_text(root / "_system" / "memory" / "MEMORY.md", "\n".join([
        "# Memory", "",
        "## Approved beliefs — Test Lens", "",
        "- Old rule about testing. — `_system/memory/daily/2026-01-02.md`"
        " `[superseded 2026-01-03]`",
        "- New rule about testing better. —"
        " `_system/memory/daily/2026-01-02.md` `[active 2026-01-03 · agent]`",
        "",
        "## Approved beliefs — company-specific", "",
        "| Ticker | Belief | Source | Approved | Status |",
        "|--------|--------|--------|----------|--------|",
        "| TST | TST test fact row. | `TST/research/valuation_contract.json` |"
        " 2026-01-03 | `active 2026-01-03 · agent` |", ""]))
    write_text(root / "_system" / "memory" / "daily" / "2026-01-02.md", "\n".join([
        "# Daily log — 2026-01-02", "",
        "### [PROPOSED COMPANY]", "",
        "- TST: fixture proposal that was promoted.", "",
        "### [PROPOSED MUNGER]", "",
        "- Always test the graph builder twice.", ""]))
    items = build_memory_triage.parse_file(
        root / "_system" / "memory" / "daily" / "2026-01-02.md")
    promoted = next(i for i in items if i["lens"] == "COMPANY")
    write_json(root / "_system" / "memory" / "triage_ledger.json", {
        "version": 1, "updated": "2026-01-03", "cadence": "monthly",
        "decisions": {build_memory_triage.fingerprint(promoted): {
            "decision": "promoted", "date": "2026-01-03", "by": "human",
            "lens": "COMPANY",
            "excerpt": "TST: fixture proposal that was promoted.",
            "memory_anchor": '"New rule about testing"'}}})
    write_text(root / "_system" / "memory" / "corrections.md", "\n".join([
        "# Corrections Log", "",
        "| Date | Ticker | Error | Correction | Source |",
        "|------|--------|-------|------------|--------|",
        "| 2026-01-05 | TST | Guarded fixture error with executable assert. |"
        " Fixed in code. | `_system/scripts/scan_demo.py` |",
        "| 2026-01-06 | — | Prose-only fixture error. |"
        " Read the docs first. | chat |",
        "| 2026-01-07 | — | Merged-cells fixture error row. |"
        " `_system/scripts/scan_demo.py` |",
        "| 2026-01-08 | AAA/BBB | Two-ticker fixture error. |"
        " Split the cell. | chat |", ""]))
    write_text(root / "_system" / "scripts" / "scan_demo.py", "print('ok')\n")
    write_text(root / ".github" / "workflows" / "quality.yml", "\n".join([
        "name: Fixture Quality", "on: push", "jobs:", "  q:",
        "    runs-on: ubuntu-latest", "    steps:",
        "      - run: python _system/scripts/scan_demo.py", ""]))
    write_json(root / "_system" / "research" /
               "extreme_irr_adjudication_2026-01-01.json",
               {"as_of": "2026-01-01", "revision": 1,
                "adjudication_rule": "rule text", "authority": "advisory"})
    write_json(root / "_system" / "research" /
               "extreme_irr_adjudication_2026-01-02.json",
               {"as_of": "2026-01-02", "revision": 2,
                "adjudication_rule": "rule text", "authority": "advisory"})
    write_json(root / "_system" / "research" / "committee_calibration.json",
               {"status": "insufficient_outcomes", "completed_outcomes": 0})
    git = ["git", "-C", str(root)]
    subprocess.run(git + ["init", "-q"], check=True)
    env_id = ["-c", "user.email=fixture@test", "-c", "user.name=fixture"]
    subprocess.run(git + env_id + ["commit", "-q", "--allow-empty",
                                   "-m", "unrelated commit"], check=True)
    subprocess.run(git + env_id + ["commit", "-q", "--allow-empty",
                                   "-m", "chore(valuation): fixture commit"],
                   check=True)


class FixtureGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name)
        make_fixture(cls.root)
        cls.db = cls.root / "_system" / "graph" / "graph.db"
        cls.builder = graph_build.build(cls.root, cls.db)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def node(self, node_id: str):
        rows = db_rows(self.db, "SELECT * FROM nodes WHERE id = ?", (node_id,))
        self.assertTrue(rows, f"missing node {node_id}")
        return rows[0]

    def edge(self, src: str, dst: str, etype: str):
        rows = db_rows(self.db, "SELECT * FROM edges WHERE src=? AND dst=? AND type=?",
                       (src, dst, etype))
        self.assertTrue(rows, f"missing edge {src} -{etype}-> {dst}")
        return rows[0]

    def test_work_plane(self):
        lane = self.node("lane:valuation")
        data = json.loads(lane["data_json"])
        self.assertEqual(data["commit_count_in_window"], 1)
        self.assertTrue(data["last_commit_iso"])
        commits = db_rows(self.db, "SELECT * FROM nodes WHERE type='Commit'")
        self.assertEqual(len(commits), 1)  # the unrelated commit matches no lane
        run_id = "run:power_zone_security_run_2026-01-02_tst"
        self.node(run_id)
        self.edge("contract:TST", run_id, "PRODUCED_BY")
        self.node("wave:contract_backfill")
        self.edge("wave:contract_backfill", "ticker:TST", "ABOUT")

    def test_ticker_in_run_wave_and_registry_carries_registry_fields(self):
        # TST appears in a run receipt, the wave, AND the registry. The old
        # first-write-wins node() plus runs/wave-before-tickers ordering left
        # ticker:TST as a bare stub (data_json={}), discarding the registry's
        # company/archetype/sleeve/stance — the 464-of-836 empty-Ticker defect.
        node = self.node("ticker:TST")
        self.assertEqual(node["label"], "Test Co")
        self.assertEqual(node["status"], "watch")
        data = json.loads(node["data_json"])
        self.assertEqual(data.get("archetype"), "compounder")
        self.assertEqual(data.get("sleeve"), "tech")
        self.assertEqual(data.get("market"), "US")
        self.assertEqual(data.get("registry_section"), "holdings")

    def test_node_merge_never_overwrites_non_empty_with_empty(self):
        builder = graph_build.GraphBuilder(self.root)
        builder.node("ticker:X", "knowledge", "Ticker", ticker="X",
                     label="X Corp", status="watch",
                     data={"archetype": "compounder", "sleeve": None})
        # A later bare stub (empty label/status/data) must not blank anything.
        builder.node("ticker:X", "knowledge", "Ticker", ticker="X", label="")
        node = builder.nodes["ticker:X"]
        self.assertEqual(node["label"], "X Corp")
        self.assertEqual(node["status"], "watch")
        self.assertEqual(node["data"]["archetype"], "compounder")
        # And non-empty incoming values fill previously-empty slots.
        builder.node("ticker:X", "knowledge", "Ticker", ticker="X",
                     data={"sleeve": "tech", "archetype": "other"})
        self.assertEqual(node["data"]["sleeve"], "tech")
        self.assertEqual(node["data"]["archetype"], "compounder")  # first non-empty wins

    def test_multi_ticker_correction_cell_splits_into_about_edges(self):
        slug = graph_build.correction_slug("2026-01-08",
                                           "Two-ticker fixture error.")
        node_id = f"correction:{slug}"
        node = self.node(node_id)
        self.assertIsNone(node["ticker"])  # no single ticker owns the row
        self.edge(node_id, "ticker:AAA", "ABOUT")
        self.edge(node_id, "ticker:BBB", "ABOUT")
        self.assertEqual(json.loads(node["data_json"])["tickers"], ["AAA", "BBB"])
        # The old behavior minted a bogus combined ticker node.
        self.assertFalse(db_rows(self.db, "SELECT * FROM nodes WHERE id=?",
                                 ("ticker:AAA/BBB",)))

    def test_evidence_blockers_project_blocks_edges(self):
        blockers = db_rows(self.db, "SELECT * FROM nodes WHERE type='Blocker'"
                                    " ORDER BY id")
        self.assertEqual(len(blockers), 2)
        for row in blockers:
            self.assertEqual(row["ticker"], "TST")
            self.edge(row["id"], "contract:TST", "BLOCKS")
        # Stable readable id: ticker + slug of text (+ short digest).
        self.assertEqual(len(db_rows(
            self.db, "SELECT id FROM nodes WHERE id LIKE"
            " 'blocker:TST:market-price-per-share-is-missing%'")), 1)

    def test_contract_components_facts_falsifiers(self):
        self.assertEqual(self.node("contract:TST")["status"], "decision_grade")
        self.edge("contract:TST", "ticker:TST", "ABOUT")
        comp = "component:TST:core"
        self.node(comp)
        prose = db_rows(self.db,
                        "SELECT * FROM nodes WHERE type='Falsifier' AND status='prose'")
        self.assertEqual(len(prose), 2)  # component text deduped with monitoring copy
        typed = self.node("falsifier:TST:spec:core:owner-cash-m")
        self.assertEqual(typed["status"], "typed")
        self.edge(comp, typed["id"], "ASSERTS")
        untestable = self.node("falsifier:TST:spec:core:vibes")
        self.assertEqual(untestable["status"], "untestable")
        fact = self.node("fact:TST:cash_m")
        self.assertEqual(fact["status"], "locked")
        edge = self.edge("fact:TST:cash_m",
                         "source:TST/research/evidence/sec_companyfacts.json",
                         "SUPPORTED_BY")
        self.assertIn("us-gaap:Cash", edge["data_json"])
        source = self.node("source:TST/research/evidence/sec_companyfacts.json")
        self.assertEqual(source["status"], "present")
        self.assertFalse(db_rows(self.db, "SELECT * FROM nodes WHERE id=?",
                                 ("fact:TST:unlocked_m",)))

    def test_outcome_resolution_and_scoring(self):
        outcomes = db_rows(self.db, "SELECT * FROM nodes WHERE type='Outcome'")
        self.assertEqual(len(outcomes), 1)
        outcome_id = outcomes[0]["id"]
        self.edge("falsifier:TST:spec:core:owner-cash-m", outcome_id, "RESOLVED_BY")
        self.edge(outcome_id,
                  "bucket:owner_earnings_reinvestment_dcf:quality_reinvestment",
                  "SCORES")

    def test_beliefs_and_supersede(self):
        beliefs = db_rows(self.db, "SELECT * FROM nodes WHERE type='Belief'")
        self.assertEqual(len(beliefs), 3)
        old = self.node("belief:old-rule-about-testing")
        self.assertEqual(old["status"], "superseded")
        new = self.node("belief:new-rule-about-testing-better")
        self.assertEqual(json.loads(new["data_json"])["agent_approved"], True)
        self.edge(new["id"], old["id"], "SUPERSEDES")
        self.edge(new["id"], "source:_system/memory/daily/2026-01-02.md",
                  "SUPPORTED_BY")
        row = self.node("belief:tst-test-fact-row")
        self.assertEqual(row["ticker"], "TST")
        self.edge(row["id"], "ticker:TST", "ABOUT")

    def test_proposals_decided_and_undecided(self):
        decided = db_rows(self.db,
                          "SELECT * FROM nodes WHERE type='Proposal' AND status='promoted'")
        self.assertEqual(len(decided), 1)
        self.edge(decided[0]["id"], "decision:promoted", "DECIDED_AS")
        self.edge("belief:new-rule-about-testing-better", decided[0]["id"],
                  "DISTILLED_FROM")
        undecided = db_rows(self.db,
                            "SELECT * FROM nodes WHERE type='Proposal' AND status='undecided'")
        self.assertEqual(len(undecided), 1)
        self.assertIn("Always test the graph builder",
                      json.loads(undecided[0]["data_json"])["excerpt"])

    def test_corrections_guards_validators_ci(self):
        corrections = db_rows(self.db, "SELECT * FROM nodes WHERE type='Correction'")
        self.assertEqual(len(corrections), 4)  # incl. merged row + 2-ticker row
        guarded_slug = graph_build.correction_slug(
            "2026-01-05", "Guarded fixture error with executable assert.")
        guarded = self.node(f"correction:{guarded_slug}")
        self.assertEqual(guarded["status"], "guarded")
        self.edge(guarded["id"], "guard:demo-guard", "GUARDED_BY")
        self.edge("guard:demo-guard", "validator:scan_demo.py", "ENFORCED_BY")
        self.edge("validator:scan_demo.py", "ci:quality.yml", "INVOKED_BY")
        self.assertEqual(self.node("ci:quality.yml")["label"], "Fixture Quality")
        prose_slug = graph_build.correction_slug(
            "2026-01-06", "Prose-only fixture error.")
        self.assertEqual(self.node(f"correction:{prose_slug}")["status"],
                         "unguarded")
        merged_slug = graph_build.correction_slug(
            "2026-01-07", "Merged-cells fixture error row.")
        self.node(f"correction:{merged_slug}")
        self.assertFalse([w for w in self.builder.warnings
                          if "guard registry" in w])

    def test_evaluations_supersede_chain(self):
        self.node("eval:committee_calibration")
        self.edge("eval:extreme_irr_adjudication_2026-01-02",
                  "eval:extreme_irr_adjudication_2026-01-01", "SUPERSEDES")

    def test_fixture_determinism(self):
        db2 = self.root / "_system" / "graph" / "graph2.db"
        builder2 = graph_build.build(self.root, db2)
        self.assertEqual(len(self.builder.nodes), len(builder2.nodes))
        self.assertEqual(len(self.builder.edges), len(builder2.edges))
        self.assertEqual(meta_value(self.db, "content_hash"),
                         meta_value(db2, "content_hash"))


class RealRepoSmokeTests(unittest.TestCase):
    """One real build (plus a second for the determinism proof)."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.db1 = Path(cls._tmp.name) / "real1.db"
        cls.db2 = Path(cls._tmp.name) / "real2.db"
        started = time.time()
        cls.builder1 = graph_build.build(REPO_ROOT, cls.db1)
        cls.first_build_seconds = time.time() - started
        cls.builder2 = graph_build.build(REPO_ROOT, cls.db2)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def count(self, ntype: str) -> int:
        return db_rows(self.db1, "SELECT COUNT(*) AS n FROM nodes WHERE type=?",
                       (ntype,))[0]["n"]

    def test_node_count_floors(self):
        self.assertGreaterEqual(self.count("Ticker"), 800)
        self.assertGreaterEqual(self.count("Correction"), 13)
        self.assertGreaterEqual(self.count("Validator"), 25)
        # The 642-contract evidence_blocked book must be traversable.
        self.assertGreaterEqual(self.count("Blocker"), 600)
        blocks = db_rows(self.db1,
                         "SELECT COUNT(*) AS n FROM edges WHERE type='BLOCKS'")
        self.assertGreaterEqual(blocks[0]["n"], 600)

    def test_no_bogus_multi_ticker_nodes(self):
        rows = db_rows(self.db1,
                       "SELECT id FROM nodes WHERE type='Ticker' AND id LIKE '%/%'")
        self.assertEqual([r["id"] for r in rows], [])

    def test_registry_tickers_carry_registry_data(self):
        # Regression for the first-write-wins defect: registry-listed tickers
        # that also appear in runs/wave must keep company/archetype/sleeve.
        empty = db_rows(self.db1,
                        "SELECT COUNT(*) AS n FROM nodes"
                        " WHERE type='Ticker' AND data_json='{}'")
        rich = db_rows(self.db1,
                       "SELECT COUNT(*) AS n FROM nodes"
                       " WHERE type='Ticker' AND data_json LIKE '%registry_section%'")
        self.assertGreaterEqual(rich[0]["n"], 800)
        self.assertLessEqual(empty[0]["n"], 25)

    def test_build_time_budget(self):
        self.assertLess(self.first_build_seconds, 90.0)

    def test_guard_registry_keys_all_match_correction_rows(self):
        self.assertFalse([w for w in self.builder1.warnings
                          if "guard registry" in w],
                         "graph_sources.json guards must key on real row slugs")

    def test_every_guarded_correction_reaches_a_guard(self):
        guards = json.loads((REPO_ROOT / "_system" / "graph" /
                             "graph_sources.json").read_text(encoding="utf-8"))["guards"]
        for slug in guards:
            rows = db_rows(self.db1,
                           "SELECT * FROM edges WHERE src=? AND type='GUARDED_BY'",
                           (f"correction:{slug}",))
            self.assertTrue(rows, f"no GUARDED_BY edge for {slug}")

    def test_real_determinism(self):
        self.assertEqual(len(self.builder1.nodes), len(self.builder2.nodes))
        self.assertEqual(len(self.builder1.edges), len(self.builder2.edges))
        hash1 = meta_value(self.db1, "content_hash")
        hash2 = meta_value(self.db2, "content_hash")
        self.assertTrue(hash1)
        self.assertEqual(hash1, hash2)
        summary1 = self.builder1.summary()
        summary2 = self.builder2.summary()
        self.assertEqual(summary1, summary2)

    def test_graph_db_is_gitignored(self):
        gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("_system/graph/graph.db", gitignore)


if __name__ == "__main__":
    unittest.main()
