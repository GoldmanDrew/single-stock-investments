from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import scan_fact_ledger_currency as scanner

COMPANYFACTS_REF = "TEST/research/evidence/sec_companyfacts.json"
LOCATOR = "us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents; accession 0001-26-1; form 20-F"
FX = {"from_currency": "EUR", "to_currency": "USD", "rate_per_usd": 0.85106,
      "rate_as_of": "2025-12-31", "evidence_ref": "_system/reference/market-data/fx_rates.json",
      "source_value": 12916.0, "source_unit": "EUR millions"}


def ledger(value: float, fx: dict | None = None) -> dict:
    row = {"field_id": "cash_m", "value": value, "unit": "USD millions", "locked": True,
           "source": {"ref": COMPANYFACTS_REF, "locator": LOCATOR, "as_of": "2025-12-31"}}
    if fx:
        row["fx_conversion"] = fx
    return {"schema_version": "1.0", "ticker": "TEST", "facts": [row]}


def model(value: float, fx: dict | None = None) -> dict:
    node = {"id": "cash", "label": "Cash", "kind": "fact", "value": value, "unit": "USD millions",
            "locked": True, "source": {"ref": COMPANYFACTS_REF, "locator": LOCATOR, "as_of": "2025-12-31"}}
    if fx:
        node["fx_conversion"] = fx
    return {
        "ticker": "TEST",
        "scenarios": {"kept": True},
        "component_valuation_results": {"additive_components": [{
            "id": "operating_business_and_net_assets",
            "calculation_proof": {"method_id": "owner_earnings_reinvestment_dcf", "inputs": [node]},
        }]},
    }


class CurrencyScanTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        research = self.root / "TEST" / "research"
        (research / "evidence").mkdir(parents=True)
        (research / "evidence" / "sec_companyfacts.json").write_text(json.dumps({
            "facts": {"us-gaap": {"CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents": {
                "units": {"EUR": [{"val": 12916000000}]}}}}
        }), encoding="utf-8")
        self.research = research
        patcher = mock.patch.object(scanner, "ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)

    def write(self, ledger_payload: dict | None, model_payload: dict | None) -> None:
        if ledger_payload is not None:
            (self.research / "valuation_fact_ledger.json").write_text(
                json.dumps(ledger_payload), encoding="utf-8")
        if model_payload is not None:
            (self.research / "valuation.json").write_text(json.dumps(model_payload), encoding="utf-8")

    def test_raw_foreign_value_in_ledger_is_a_mismatch(self):
        self.write(ledger(12916.0), None)
        mismatches, _, _, checked = scanner.scan_ledgers()
        self.assertEqual(checked, 1)
        self.assertEqual([row[1] for row in mismatches], ["ledger cash_m"])
        self.assertEqual(scanner.scan(), 1)

    def test_corrected_ledger_with_stale_proof_input_still_fails(self):
        # The ASML case: the ledger was re-locked in USD but valuation.json kept
        # the raw EUR figure. A ledger-only scan reports green on the file that
        # is actually wrong, so the proof surface must be scanned too.
        self.write(ledger(15176.36829365732, FX), model(12916.0))
        ledger_mismatches, _, _, _ = scanner.scan_ledgers()
        self.assertEqual(ledger_mismatches, [])
        proof_mismatches, _, _, proof_checked = scanner.scan_proofs()
        self.assertEqual(proof_checked, 1)
        self.assertEqual([row[1] for row in proof_mismatches],
                         ["proof owner_earnings_reinvestment_dcf.cash"])
        self.assertEqual(scanner.scan(), 1)

    def test_converted_value_with_fx_provenance_passes_both_surfaces(self):
        self.write(ledger(15176.36829365732, FX), model(15176.36829365732, FX))
        self.assertEqual(scanner.scan_ledgers()[0], [])
        self.assertEqual(scanner.scan_proofs()[0], [])
        self.assertEqual(scanner.scan(), 0)

    def test_converted_value_without_fx_provenance_is_not_self_evident(self):
        # Same number as the passing case, but nothing on the row says it was
        # converted, so it is indistinguishable from the stale-EUR corruption.
        self.write(ledger(15176.36829365732, FX), model(15176.36829365732))
        self.assertEqual(scanner.scan(), 1)

    def test_mismatched_fx_direction_is_a_mismatch(self):
        bad = dict(FX, from_currency="DKK")
        self.write(ledger(15176.36829365732, bad), model(15176.36829365732, bad))
        self.assertEqual(len(scanner.scan_ledgers()[0]), 1)
        self.assertEqual(len(scanner.scan_proofs()[0]), 1)

    def test_unresolvable_locator_is_unverifiable_not_a_mismatch(self):
        payload = model(12916.0)
        proof = payload["component_valuation_results"]["additive_components"][0]["calculation_proof"]
        proof["inputs"][0]["source"]["locator"] = "us-gaap:RenamedTag; accession 0001-26-1; form 20-F"
        self.write(ledger(15176.36829365732, FX), payload)
        mismatches, unverifiable, _, checked = scanner.scan_proofs()
        self.assertEqual((mismatches, checked), ([], 0))
        self.assertEqual(len(unverifiable), 1)
        self.assertEqual(scanner.scan(), 0)

    def test_non_monetary_input_is_skipped(self):
        payload = model(385.417665)
        proof = payload["component_valuation_results"]["additive_components"][0]["calculation_proof"]
        proof["inputs"][0]["unit"] = "million shares"
        self.write(ledger(15176.36829365732, FX), payload)
        self.assertEqual(scanner.scan_proofs(), ([], [], [], 0))

    def test_non_companyfacts_monetary_row_is_recorded_as_skipped(self):
        """A PDF/HTM locator exposes no unit key, so the row cannot be checked. It has
        to be counted, or '0 mismatches' reads as 'everything checked'."""
        payload = model(12916.0)
        proof = payload["component_valuation_results"]["additive_components"][0]["calculation_proof"]
        proof["inputs"][0]["source"]["ref"] = "TEST/research/evidence/annual_report_fy2024.pdf"
        ledger_payload = ledger(12916.0)
        ledger_payload["facts"][0]["source"]["ref"] = "TEST/research/evidence/filing_facts_2026-07-28.json"
        self.write(ledger_payload, payload)

        l_mismatches, _, l_skipped, l_checked = scanner.scan_ledgers()
        p_mismatches, _, p_skipped, p_checked = scanner.scan_proofs()
        self.assertEqual((l_mismatches, l_checked), ([], 0))
        self.assertEqual((p_mismatches, p_checked), ([], 0))
        self.assertEqual(l_skipped, [("TEST", "ledger cash_m", "filing_facts_*.json")])
        self.assertEqual(
            p_skipped,
            [("TEST", "proof owner_earnings_reinvestment_dcf.cash", "annual_report_fy2024.pdf")])

    def test_skipped_rows_are_printed_in_the_summary(self):
        payload = model(12916.0)
        proof = payload["component_valuation_results"]["additive_components"][0]["calculation_proof"]
        proof["inputs"][0]["source"]["ref"] = "TEST/research/evidence/annual_report_fy2024.pdf"
        self.write(ledger(15176.36829365732, FX), payload)
        with mock.patch("builtins.print") as printed:
            code = scanner.scan()
        output = "\n".join(str(call.args[0]) for call in printed.call_args_list)
        self.assertEqual(code, 0)
        self.assertIn("SKIPPED 1 monetary row(s)", output)
        self.assertIn("SKIPPED-SOURCE annual_report_fy2024.pdf: 1", output)
        self.assertIn("1 skipped for lack of a source unit key", output)
        self.assertTrue(output.isascii(), "output must stay ASCII for the cp1252 console")

    def test_fail_on_skipped_turns_the_coverage_gap_into_a_non_zero_exit(self):
        payload = model(12916.0)
        proof = payload["component_valuation_results"]["additive_components"][0]["calculation_proof"]
        proof["inputs"][0]["source"]["ref"] = "TEST/research/evidence/annual_report_fy2024.pdf"
        self.write(ledger(15176.36829365732, FX), payload)
        self.assertEqual(scanner.scan(), 0)
        self.assertEqual(scanner.scan(fail_on_skipped=True), 1)

    def test_non_monetary_row_is_not_counted_as_skipped(self):
        payload = model(385.417665)
        proof = payload["component_valuation_results"]["additive_components"][0]["calculation_proof"]
        proof["inputs"][0]["unit"] = "million shares"
        proof["inputs"][0]["source"]["ref"] = "TEST/research/evidence/annual_report_fy2024.pdf"
        self.write(ledger(15176.36829365732, FX), payload)
        self.assertEqual(scanner.scan_proofs(), ([], [], [], 0))

    def test_proofs_are_found_at_any_depth(self):
        payload = model(12916.0)
        payload["valuation_overlay"] = {"nested": [{"wrapper": payload["component_valuation_results"]}]}
        self.write(ledger(15176.36829365732, FX), payload)
        mismatches, _, _, checked = scanner.scan_proofs()
        self.assertEqual(checked, 2)
        self.assertEqual(len(mismatches), 2)


if __name__ == "__main__":
    unittest.main()
