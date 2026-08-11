from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_evidence_integrity as cei  # noqa: E402

TODAY = date(2026, 8, 11)


def write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def proof(kind: str = "fact", sourced: bool = True) -> dict:
    node = {"id": "x", "kind": kind, "value": 1.0, "unit": "USD_m"}
    if sourced:
        node["source"] = {"ref": "a.htm", "locator": "p1", "as_of": "2026-01-01"}
    return {"traces": {"base": [node]}}


def healthy(research: Path) -> None:
    """A ticker that should produce no findings at all."""
    write(research / "valuation_contract.json", {
        "status": "decision_grade",
        "economic_ownership_map": [
            {"method": "owner_cash_or_dividend_discount", "calculation_proof": proof()},
            {"method": "net_asset_value", "calculation_proof": proof()},
        ],
    })
    write(research / "security_identity.json",
          {"primary_method": "component_owner_cash_and_unit_nav"})
    write(research / "valuation_route.json",
          {"primary_methods": ["component_owner_cash_and_unit_nav"]})
    write(research / "valuation_automation_state.json",
          {"stages": {"model_compile": {"status": "complete"}}})
    write(research / "evidence_task_queue.json",
          {"updated_at": "2026-08-11T00:00:00Z", "tasks": []})
    write(research / "valuation_fact_ledger.json", {"facts": [
        {"field_id": f, "locked": True} for f in
        cei.REQUIRED_INPUTS["component_owner_cash_and_unit_nav"]]})
    write(research / "valuation.json", {"component_valuation_results": {
        "additive_components": [{"id": "a"}],
        "total_equity_value_per_share": {"low": 1, "base": 2, "high": 3}}})
    write(research / "falsifier_specs.json", {"specs": [
        {"untestable": False, "threshold": 1.0, "metric": "m"}]})


class RouteSatisfiedTests(unittest.TestCase):
    def test_pairing_requires_both_legs(self):
        both = {"owner_cash_or_dividend_discount", "net_asset_value"}
        self.assertTrue(cei.route_satisfied("component_owner_cash_and_unit_nav", both))

    def test_pairing_rejects_owner_cash_alone(self):
        # The WHK regression: owner-cash leg only, NAV leg missing.
        self.assertFalse(cei.route_satisfied(
            "component_owner_cash_and_unit_nav", {"owner_cash_or_dividend_discount"}))

    def test_pairing_rejects_nav_alone(self):
        self.assertFalse(cei.route_satisfied(
            "component_owner_cash_and_unit_nav", {"net_asset_value"}))

    def test_plain_method_needs_exact_match(self):
        self.assertTrue(cei.route_satisfied("net_asset_value", {"net_asset_value"}))
        self.assertFalse(cei.route_satisfied(
            "owner_earnings_reinvestment_dcf", {"owner_cash_or_dividend_discount"}))


class SourcedFactTests(unittest.TestCase):
    def test_counts_only_sourced_facts(self):
        contract = {"economic_ownership_map": [
            {"calculation_proof": proof("fact", sourced=True)},
            {"calculation_proof": proof("fact", sourced=False)},
            {"calculation_proof": proof("judgment", sourced=True)},
        ]}
        self.assertEqual(cei.sourced_fact_nodes(contract), 1)

    def test_empty_contract_is_zero(self):
        self.assertEqual(cei.sourced_fact_nodes({}), 0)


class AgeDaysTests(unittest.TestCase):
    def test_reads_iso_timestamp_and_date(self):
        self.assertEqual(cei.age_days("2026-08-04T10:00:00Z", TODAY), 7)
        self.assertEqual(cei.age_days("2026-08-04", TODAY), 7)

    def test_unparseable_stamp_is_none_not_fresh(self):
        # A stamp that cannot be read must never be treated as fresh.
        self.assertIsNone(cei.age_days("whenever", TODAY))
        self.assertIsNone(cei.age_days(None, TODAY))


class ScanTickerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.research = Path(self.tmp.name) / "T" / "research"
        healthy(self.research)
        self.addCleanup(self.tmp.cleanup)

    def scan(self, wave=frozenset()):
        return cei.scan_ticker("T", self.research, set(wave), TODAY)

    def test_healthy_ticker_has_no_findings(self):
        self.assertEqual(self.scan(), {})

    def test_v1_status_disagreement(self):
        write(self.research / "valuation_automation_state.json",
              {"stages": {"model_compile": {"status": "evidence_blocked",
                                            "input_errors": ["a", "b"]}}})
        self.assertIn("V1", self.scan())

    def test_v2_ignores_input_classification(self):
        # 187 decision-grade contracts have facts: [] and are not defective.
        contract = json.loads(
            (self.research / "valuation_contract.json").read_text(encoding="utf-8"))
        contract["input_classification"] = {"facts": [], "judgments": [{"a": 1}]}
        write(self.research / "valuation_contract.json", contract)
        self.assertNotIn("V2", self.scan())

    def test_v2_fires_when_no_proof_carries_a_source(self):
        contract = json.loads(
            (self.research / "valuation_contract.json").read_text(encoding="utf-8"))
        for comp in contract["economic_ownership_map"]:
            comp["calculation_proof"] = proof("fact", sourced=False)
        write(self.research / "valuation_contract.json", contract)
        self.assertIn("V2", self.scan())

    def test_v3_untouched_queue_on_stale_stamp(self):
        write(self.research / "evidence_task_queue.json", {
            "updated_at": "2026-07-01T00:00:00Z",
            "tasks": [{"status": "pending_collection", "attempts": 0}]})
        self.assertIn("V3", self.scan())

    def test_v3_fresh_queue_is_not_a_finding(self):
        write(self.research / "evidence_task_queue.json", {
            "updated_at": "2026-08-11T00:00:00Z",
            "tasks": [{"status": "pending_collection", "attempts": 0}]})
        self.assertNotIn("V3", self.scan())

    def test_v3_attempted_task_is_not_a_finding(self):
        write(self.research / "evidence_task_queue.json", {
            "updated_at": "2026-07-01T00:00:00Z",
            "tasks": [{"status": "pending_collection", "attempts": 2}]})
        self.assertNotIn("V3", self.scan())

    def test_v3_marks_trapped_only_when_outside_the_wave(self):
        write(self.research / "evidence_task_queue.json", {
            "updated_at": "2026-07-01T00:00:00Z",
            "tasks": [{"status": "pending_collection", "attempts": 0}]})
        self.assertIn("TRAPPED", self.scan()["V3"])
        self.assertNotIn("TRAPPED", self.scan(wave={"T"})["V3"])

    def test_v4_unsatisfied_route(self):
        contract = json.loads(
            (self.research / "valuation_contract.json").read_text(encoding="utf-8"))
        contract["economic_ownership_map"] = [
            {"method": "owner_cash_or_dividend_discount", "calculation_proof": proof()}]
        write(self.research / "valuation_contract.json", contract)
        self.assertIn("V4", self.scan())

    def test_v5_missing_totals(self):
        write(self.research / "valuation.json", {"component_valuation_results": {
            "status": "compiled", "additive_components": [{"id": "a"}]}})
        self.assertIn("V5", self.scan())

    def test_v6_no_typed_falsifier(self):
        write(self.research / "falsifier_specs.json",
              {"specs": [{"untestable": True, "threshold": None}]})
        self.assertIn("V6", self.scan())

    def test_v7_only_applies_to_decision_grade(self):
        write(self.research / "valuation_fact_ledger.json", {"facts": []})
        self.assertIn("V7", self.scan())
        contract = json.loads(
            (self.research / "valuation_contract.json").read_text(encoding="utf-8"))
        contract["status"] = "evidence_blocked"
        write(self.research / "valuation_contract.json", contract)
        # 641 evidence_blocked tickers missing inputs are the backlog, not defects.
        self.assertNotIn("V7", cei.scan_ticker("T", self.research, set(), TODAY))

    def test_missing_contract_yields_nothing(self):
        (self.research / "valuation_contract.json").unlink()
        self.assertEqual(self.scan(), {})


class TruncatedFilingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.research = Path(self.tmp.name) / "T" / "research"
        healthy(self.research)
        self.evidence = self.research / "evidence"
        self.addCleanup(self.tmp.cleanup)

    def inventory(self, coverage):
        write(self.evidence / "document_inventory.json",
              {"documents": [{"tier": "full", "coverage": coverage}]})

    def test_measured_truncation_fires(self):
        self.inventory({"truncated": True, "coverage_pct": 23.4,
                        "sections_missing": ["liquidity_and_capital_resources"]})
        detail = cei.truncated_filings(self.research)
        self.assertIn("23.4%", detail)
        self.assertIn("liquidity_and_capital_resources", detail)

    def test_measured_complete_does_not_fire(self):
        self.inventory({"truncated": False, "coverage_pct": 100.0, "sections_missing": []})
        self.assertIsNone(cei.truncated_filings(self.research))

    def test_legacy_cache_at_cap_without_marker_fires(self):
        cache = self.evidence / "_text"
        cache.mkdir(parents=True, exist_ok=True)
        (cache / "big.txt").write_text("x" * cei.LEGACY_CHAR_CAP, encoding="utf-8")
        self.assertIn("legacy", cei.truncated_filings(self.research))

    def test_legacy_cache_with_marker_does_not_fire(self):
        # Already measured and marked -> known, not silent.
        cache = self.evidence / "_text"
        cache.mkdir(parents=True, exist_ok=True)
        (cache / "big.txt").write_text(
            "x" * cei.LEGACY_CHAR_CAP + "\n" + cei.TRUNCATION_MARKER + " kept ...]",
            encoding="utf-8")
        self.assertIsNone(cei.truncated_filings(self.research))

    def test_small_cache_files_are_ignored(self):
        cache = self.evidence / "_text"
        cache.mkdir(parents=True, exist_ok=True)
        (cache / "small.txt").write_text("short", encoding="utf-8")
        self.assertIsNone(cei.truncated_filings(self.research))

    def test_no_evidence_dir_is_not_a_finding(self):
        self.assertIsNone(cei.truncated_filings(Path(self.tmp.name) / "nope" / "research"))

    def test_measured_metadata_wins_over_legacy_heuristic(self):
        # A re-extracted ticker keeps a big cache file; metadata says complete.
        cache = self.evidence / "_text"
        cache.mkdir(parents=True, exist_ok=True)
        (cache / "big.txt").write_text("x" * 400_000, encoding="utf-8")
        self.inventory({"truncated": False, "coverage_pct": 100.0, "sections_missing": []})
        self.assertIsNone(cei.truncated_filings(self.research))


class WorklistTests(unittest.TestCase):
    def test_orders_by_breakage_then_trapped_then_held(self):
        report = {
            "per_ticker": {
                "ONE": {"V6": "x"},
                "TRAP": {"V6": "x", "V3": "... [TRAPPED: ...]"},
                "HELD": {"V6": "x"},
            },
            "findings": {"V6": [{"ticker": "HELD", "held": True}]},
        }
        order = [r["ticker"] for r in cei.worklist(report, 10)]
        self.assertEqual(order[0], "HELD")        # holdings weigh most
        self.assertEqual(order[1], "TRAP")        # then the trap
        self.assertEqual(order[2], "ONE")


if __name__ == "__main__":
    unittest.main()
