from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

import build_review_queue_rollup as rollup


US_CONFIG = {
    "ADI": {"cik": "0000006281", "ir_roots": []},
    "AMD": {"cik": "2488", "ir_roots": []},
    "SHDW": {"cik": None, "ir_roots": []},
    "MISM": {"cik": "0000000042", "ir_roots": []},
}

# A classification a human actually decided: no field left on the onboarding default.
# Every non-sleeve key in DEFAULT_CLASSIFICATION must appear, moi_bucket and
# payoff_lens included - they were the two the old hand-listed tuple never tested.
CONFIRMED_CLASSIFICATION = {
    "archetype": "compounder", "moat": "widening", "dhando": "partial",
    "stance": "core", "cycle": "mid", "moi_bucket": "3-5x", "payoff_lens": "convex",
    "investment_sleeve": "exchanges_markets",
}

# Tickers the deep-dive index would report. The checklist's deep-dive line is only
# waived when a dive actually exists, so every fixture meant to close carries one.
DIVES = frozenset({"ICE", "0388X.HK", "ADI", "AMD", "NOSLV", "NOIR", "LASR",
                   "NOCIK", "SHDW", "MISM", "0388.HK"})

HOLDINGS = {
    # Everything a machine can check is genuinely checkable: real name, CIK agreeing
    # with us_ticker_config, an IR root, and a classification off every default.
    "ICE": {
        "company": "Intercontinental Exchange", "market": "US",
        "download": {"type": "us_shared", "cik": "0001571949", "ir_roots": ["https://ir.theice.com"]},
        "classification": dict(CONFIRMED_CLASSIFICATION),
    },
    "0388X.HK": {
        "company": "Hong Kong Exchanges and Clearing Ltd", "market": "EU",
        "download": {"type": "hk_archive", "ir_roots": ["https://www.hkexgroup.com/ir"]},
        "classification": dict(CONFIRMED_CLASSIFICATION),
    },
    # The 584-checklist case: every classification field is still the onboarding
    # default. All five values are truthy, so a truthiness test closes it.
    "ADI": {
        "company": "Analog Devices", "market": "US",
        "download": {"type": "us_shared", "cik": "0000006281", "ir_roots": ["https://investor.analog.com"]},
        "classification": {"archetype": "unknown", "moat": "unproven", "dhando": "pending",
                           "stance": "watch", "cycle": "-", "investment_sleeve": "ls_algo_underlying"},
    },
    # Unpadded CIK in the registry, padded in us_ticker_config: same company.
    # Partly classified: archetype/moat/dhando decided, stance/cycle still default.
    "AMD": {
        "company": "Advanced Micro Devices", "market": "US",
        "download": {"type": "us_shared", "cik": "2488", "ir_roots": ["https://ir.amd.com"]},
        "classification": {"archetype": "compounder", "moat": "narrow", "dhando": "none",
                           "stance": "watch", "cycle": "-", "moi_bucket": "2-3x",
                           "payoff_lens": "linear", "investment_sleeve": "technology_ai"},
    },
    # Confirmed classification but the no-sleeve sentinel, which is not a sleeve.
    "NOSLV": {
        "company": "No Sleeve Corp", "market": "US",
        "download": {"type": "us_shared", "cik": "0000111222", "ir_roots": ["https://ir.nosleeve.com"]},
        "classification": dict(CONFIRMED_CLASSIFICATION, investment_sleeve="-"),
    },
    # Confirmed classification and sleeve, but no IR URL to verify.
    "NOIR": {
        "company": "No Ir Corp", "market": "US",
        "download": {"type": "us_shared", "cik": "0000333444", "ir_roots": []},
        "classification": dict(CONFIRMED_CLASSIFICATION),
    },
    # Company name never resolved past the raw symbol.
    "LASR": {
        "company": "LASR", "market": "US",
        "download": {"type": "us_shared", "cik": "0001124796", "ir_roots": []},
        "classification": {"archetype": "unknown", "moat": "unproven", "dhando": "pending",
                           "stance": "watch", "cycle": "-", "investment_sleeve": "ls_algo_underlying"},
    },
    "NOCIK": {
        "company": "No Cik Corp", "market": "US",
        "download": {"type": "us_shared", "cik": None, "ir_roots": []},
        "classification": {"archetype": "unknown", "moat": "unproven", "dhando": "pending",
                           "stance": "watch", "cycle": "-", "investment_sleeve": "ls_algo_underlying"},
    },
    # us_ticker_config.json shadows the registry: a null there beats a good registry value.
    "SHDW": {
        "company": "Shadowed Inc", "market": "US",
        "download": {"type": "us_shared", "cik": "0000123456", "ir_roots": []},
        "classification": {"archetype": "unknown", "moat": "unproven", "dhando": "pending",
                           "stance": "watch", "cycle": "-", "investment_sleeve": "ls_algo_underlying"},
    },
    "MISM": {
        "company": "Mismatch Ltd", "market": "US",
        "download": {"type": "us_shared", "cik": "0000999999", "ir_roots": []},
        "classification": {"archetype": "unknown", "moat": "unproven", "dhando": "pending",
                           "stance": "watch", "cycle": "-", "investment_sleeve": "ls_algo_underlying"},
    },
    "0388.HK": {
        "company": "Hong Kong Exchanges and Clearing Ltd", "market": "EU",
        "download": {"type": "hk_archive"},
        "classification": {"archetype": "compounder", "moat": "wide", "dhando": "none",
                           "stance": "watch", "cycle": "-", "moi_bucket": "2-3x",
                           "payoff_lens": "linear", "investment_sleeve": "exchanges"},
    },
}


class ClassifyTests(unittest.TestCase):
    def assert_type(self, name, type_id):
        qt, _ = rollup.classify(name)
        self.assertIsNotNone(qt, name)
        self.assertEqual(qt.id, type_id, name)

    def test_every_observed_pattern_classifies(self):
        cases = {
            "ADI_onboard_2026-07-10.md": "onboard_checklist",
            "0388.HK_onboard_2026-06-11.md": "onboard_checklist",
            "batch_onboard_2026-06-03.md": "batch_onboard_receipt",
            "otc_sleeve_onboard_2026-07-17.md": "sleeve_onboard_proposal",
            "fund_nav_discounts_onboard_2026-07-20.md": "sleeve_onboard_proposal",
            "batch_deep_dive_dispatch_2026-06-03.md": "dispatch_receipt",
            "vicki_ir_harvest_dispatch_2026-07-02.md": "dispatch_receipt",
            "world_model_review_TPL_2026-07-23.md": "world_model_review",
            "AAPL_cross_check_HK_2026-06-01.md": "cross_check",
            "3905.T_deep_dive_2026-05-21.md": "deep_dive",
            "news_2026-06-15.md": "portfolio_news",
            "darwin_regime_brief_2026-08-07.md": "darwin_regime_brief",
            "transcript_coverage_2026-08-06.md": "transcript_coverage",
            "ls_algo_ic_queue_2026-08-09.md": "ls_algo_ic_queue",
            "fund_family_proposals_2026-08-09.md": "fund_family_proposals",
            "event_triage_2026-08-09.md": "event_triage",
            "filing_insights_2026-08-02.md": "filing_insights",
            "activist_triage_2026-08-02.md": "activist_triage",
            "activist_press_digest_2026-08-02.md": "activist_press_digest",
            "memory_digest_2026-08-02.md": "memory_digest",
            "cvr_discovery_2026-07-23.md": "cvr_discovery",
            "deep_dive_depth_scorecard_2026-06-04.csv": "depth_scorecard",
            "dashboard_plan.md": "plan_proposal",
            "sp500_completion_plan_2026-06-20.md": "plan_proposal",
            "option_treatment_rules_upgrade_2026-07-05.md": "plan_proposal",
            "royalty_king_hk_screen_2026-06-02.md": "one_off_note",
            "setup_status.md": "standing_doc",
        }
        for name, type_id in cases.items():
            self.assert_type(name, type_id)

    def test_batch_onboard_is_not_a_ticker_checklist(self):
        qt, groups = rollup.classify("batch_onboard_2026-06-03.md")
        self.assertEqual(qt.id, "batch_onboard_receipt")
        self.assertIsNone(groups.get("ticker"))


class OnboardCheckTests(unittest.TestCase):
    def checks(self, ticker):
        return rollup.onboard_checks(ticker, HOLDINGS, US_CONFIG, DIVES)

    def test_clean_us_ticker_closes(self):
        passed, blockers = self.checks("ICE")
        self.assertEqual(blockers, [])
        self.assertIn("cik_present_and_unshadowed", passed)
        self.assertIn("classification_confirmed", passed)
        self.assertIn("ir_roots_well_formed", passed)
        self.assertIn("sleeve_assigned", passed)

    def test_placeholder_only_classification_does_not_close(self):
        """The checklist asks a human to confirm the defaults. Defaults are not a confirmation."""
        passed, blockers = self.checks("ADI")
        self.assertIn("classification_unconfirmed:archetype,moat,dhando,stance,cycle,moi_bucket,payoff_lens", blockers)
        self.assertNotIn("classification_confirmed", passed)

    def test_every_registry_default_reads_as_unconfirmed(self):
        for field, default in rollup.DEFAULT_CLASSIFICATION.items():
            if field in rollup.CLASSIFICATION_FIELDS:
                self.assertFalse(rollup._is_confirmed(field, default), f"{field}={default!r}")

    def test_classification_fields_cover_every_non_sleeve_default(self):
        """A key present in DEFAULT_CLASSIFICATION but absent here is never tested,
        so a checklist closes with that field still at its onboarding default."""
        expected = {k for k in rollup.DEFAULT_CLASSIFICATION if k != rollup.SLEEVE_FIELD}
        self.assertEqual(set(rollup.CLASSIFICATION_FIELDS), expected)
        self.assertIn("moi_bucket", rollup.CLASSIFICATION_FIELDS)
        self.assertIn("payoff_lens", rollup.CLASSIFICATION_FIELDS)

    def test_moi_bucket_and_payoff_lens_at_default_block_the_close(self):
        holdings = dict(HOLDINGS)
        holdings["MOIP"] = dict(
            HOLDINGS["ICE"],
            classification=dict(CONFIRMED_CLASSIFICATION, moi_bucket="pending", payoff_lens="pending"),
        )
        _, blockers = rollup.onboard_checks("MOIP", holdings, US_CONFIG, DIVES | {"MOIP"})
        self.assertEqual(blockers, ["classification_unconfirmed:moi_bucket,payoff_lens"])

    def test_partially_confirmed_classification_names_only_the_stragglers(self):
        _, blockers = self.checks("AMD")
        self.assertIn("classification_unconfirmed:stance,cycle", blockers)

    def test_unpadded_registry_cik_matches_padded_config(self):
        passed, blockers = self.checks("AMD")
        self.assertNotIn("cik_missing_in_registry", blockers)
        self.assertNotIn("cik_mismatch_registry_vs_us_ticker_config", blockers)
        self.assertIn("cik_present_and_unshadowed", passed)
        self.assertIn("ir_roots_well_formed", passed)

    def test_no_sleeve_sentinel_is_not_an_assignment(self):
        passed, blockers = self.checks("NOSLV")
        self.assertEqual(blockers, ["sleeve_unassigned"])
        self.assertNotIn("sleeve_assigned", passed)

    def test_sentinel_sleeve_falls_through_to_the_entry_level_sleeve(self):
        """'-' is truthy, so `classification.get(...) or entry.get(...)` short-circuited
        on the sentinel and never read the real entry-level sleeve."""
        holdings = dict(HOLDINGS)
        holdings["FALLB"] = dict(
            HOLDINGS["ICE"],
            classification=dict(CONFIRMED_CLASSIFICATION, investment_sleeve="-"),
            investment_sleeve="sp500_liquidity",
        )
        passed, blockers = rollup.onboard_checks("FALLB", holdings, US_CONFIG, DIVES | {"FALLB"})
        self.assertEqual(blockers, [])
        self.assertIn("sleeve_assigned", passed)

    def test_both_sleeve_sources_placeholder_still_blocks(self):
        holdings = dict(HOLDINGS)
        holdings["NOSL2"] = dict(
            HOLDINGS["ICE"],
            classification=dict(CONFIRMED_CLASSIFICATION, investment_sleeve="-"),
            investment_sleeve="unassigned",
        )
        _, blockers = rollup.onboard_checks("NOSL2", holdings, US_CONFIG, DIVES | {"NOSL2"})
        self.assertEqual(blockers, ["sleeve_unassigned"])

    def test_deep_dive_line_blocks_until_a_dive_exists(self):
        """The waiver used to be unconditional; ~797 of 802 open checklists had no dive
        anywhere, so the item was discharged by argument rather than by an artifact."""
        passed, blockers = rollup.onboard_checks("ICE", HOLDINGS, US_CONFIG, frozenset())
        self.assertEqual(blockers, ["deep_dive_absent"])
        self.assertNotIn("deep_dive_artifact_present", passed)

    def test_deep_dive_line_is_waived_once_the_artifact_exists(self):
        passed, blockers = rollup.onboard_checks("ICE", HOLDINGS, US_CONFIG, frozenset({"ICE"}))
        self.assertEqual(blockers, [])
        self.assertIn("deep_dive_artifact_present", passed)

    def test_empty_ir_roots_is_a_blocker_not_a_pass(self):
        passed, blockers = self.checks("NOIR")
        self.assertEqual(blockers, ["ir_roots_missing"])
        self.assertNotIn("no_ir_root_asserted", passed)

    def test_non_us_closes_on_download_route(self):
        passed, blockers = self.checks("0388X.HK")
        self.assertEqual(blockers, [])
        self.assertIn("non_us_download_route_set", passed)

    def test_non_us_placeholder_classification_still_blocks(self):
        _, blockers = self.checks("0388.HK")
        self.assertIn("classification_unconfirmed:stance,cycle", blockers)

    def test_placeholder_company_name_blocks(self):
        _, blockers = self.checks("LASR")
        self.assertIn("company_name_placeholder", blockers)

    def test_missing_cik_blocks(self):
        _, blockers = self.checks("NOCIK")
        self.assertIn("cik_missing_in_registry", blockers)

    def test_null_cik_in_us_ticker_config_blocks_despite_good_registry(self):
        _, blockers = self.checks("SHDW")
        self.assertIn("cik_null_in_us_ticker_config", blockers)

    def test_cik_mismatch_blocks(self):
        _, blockers = self.checks("MISM")
        self.assertIn("cik_mismatch_registry_vs_us_ticker_config", blockers)

    def test_unknown_ticker_blocks(self):
        _, blockers = self.checks("ZZZZ")
        self.assertEqual(blockers, ["missing_registry_entry"])


class ExpiryTests(unittest.TestCase):
    def items(self, type_id, dates, today=date(2026, 8, 9)):
        rows = []
        for d in dates:
            rows.append({
                "file": f"{type_id}_{d}.md", "type": type_id,
                "disposition": rollup.TYPES_BY_ID[type_id].disposition,
                "ticker": None, "date": d,
                "age_days": rollup._age_days(d, today),
                "checks_passed": [], "blockers": [],
            })
        return rows

    def test_keeps_latest_and_expires_old(self):
        dates = ["2026-08-09", "2026-08-08", "2026-06-01", "2026-05-20"]
        rows = self.items("transcript_coverage", dates)
        rollup.mark_expiry(rows)
        self.assertEqual([r.get("expired", False) for r in rows], [False, False, True, True])

    def test_newest_never_expires_even_when_ancient(self):
        rows = self.items("darwin_regime_brief", ["2026-01-01"])
        rollup.mark_expiry(rows)
        self.assertFalse(rows[0].get("expired"))

    def test_human_verdict_types_never_expire(self):
        rows = self.items("deep_dive", ["2026-05-21", "2026-05-22"])
        rollup.mark_expiry(rows)
        self.assertFalse(any(r.get("expired") for r in rows))

    def test_within_cutoff_survives(self):
        rows = self.items("event_triage", ["2026-08-09", "2026-08-01", "2026-07-25"])
        rollup.mark_expiry(rows)
        self.assertFalse(any(r.get("expired") for r in rows))


class BlockerGroupTests(unittest.TestCase):
    def items(self):
        rows = []
        for ticker in ("ADI", "NOIR", "NOSLV", "LASR", "NOCIK"):
            passed, blockers = rollup.onboard_checks(ticker, HOLDINGS, US_CONFIG, DIVES)
            rows.append({
                "file": f"{ticker}_onboard_2026-07-18.md", "type": "onboard_checklist",
                "ticker": ticker, "checks_passed": passed, "blockers": blockers,
            })
        return rows

    def test_groups_collapse_the_field_detail_suffix(self):
        groups = {g["blocker"]: g for g in rollup._blocker_groups(self.items())}
        self.assertEqual(groups["classification_unconfirmed"]["count"], 3)
        self.assertEqual(groups["classification_unconfirmed"]["tickers"], ["ADI", "LASR", "NOCIK"])
        self.assertIn("archetype,moat,dhando,stance,cycle,moi_bucket,payoff_lens",
                      groups["classification_unconfirmed"]["detail_counts"])

    def test_every_group_carries_a_fix(self):
        for group in rollup._blocker_groups(self.items()):
            self.assertIn(group["blocker"], rollup.BLOCKER_FIXES, group["blocker"])
            self.assertTrue(group["fix"])

    def test_census_counts_classes_not_field_combinations(self):
        census = rollup._blocker_census(self.items())
        self.assertEqual(census["classification_unconfirmed"], 3)
        self.assertEqual(census["ir_roots_missing"], 3)


class DeepDiveIndexTests(unittest.TestCase):
    """The dive is written to the ticker tree and queued under a different filename,
    so both shapes have to count or the waiver never fires for a ticker that has one."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        pending = self.tmp / "reviews" / "pending"
        approved = self.tmp / "reviews" / "approved"
        expired = self.tmp / "reviews" / "expired" / "deep_dive"
        closed = self.tmp / "reviews" / "auto_closed"
        for folder in (pending, approved, expired, closed):
            folder.mkdir(parents=True)
        (self.tmp / "ICE" / "research").mkdir(parents=True)
        (self.tmp / "ICE" / "research" / "deep_dive_2026-05-21.md").write_text("x", encoding="utf-8")
        (self.tmp / "NODIV" / "research").mkdir(parents=True)
        (self.tmp / "NODIV" / "research" / "valuation.json").write_text("{}", encoding="utf-8")
        (pending / "3905.T_deep_dive_2026-05-21.md").write_text("x", encoding="utf-8")
        (approved / "AMZN_deep_dive_2026-06-02.md").write_text("x", encoding="utf-8")
        (expired / "OLD_deep_dive_2026-01-02.md").write_text("x", encoding="utf-8")
        (pending / "ADI_onboard_2026-07-18.md").write_text("x", encoding="utf-8")

        self._saved = (rollup.ROOT, rollup.PENDING, rollup.APPROVED,
                       rollup.EXPIRED, rollup.AUTO_CLOSED)
        rollup.ROOT = self.tmp
        rollup.PENDING, rollup.APPROVED = pending, approved
        rollup.EXPIRED, rollup.AUTO_CLOSED = self.tmp / "reviews" / "expired", closed
        self.addCleanup(self.restore)

    def restore(self):
        (rollup.ROOT, rollup.PENDING, rollup.APPROVED,
         rollup.EXPIRED, rollup.AUTO_CLOSED) = self._saved
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_finds_both_ticker_tree_and_review_artifacts(self):
        index = rollup.deep_dive_index()
        self.assertEqual(index, frozenset({"ICE", "3905.T", "AMZN", "OLD"}))

    def test_a_ticker_with_no_dive_is_absent(self):
        self.assertNotIn("NODIV", rollup.deep_dive_index())


class ReverifyClosedTests(unittest.TestCase):
    """A closure is only as good as the check behind it, so tightening the gate has
    to re-test what the looser gate closed rather than grandfather it."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.pending = self.tmp / "pending"
        self.closed = self.tmp / "auto_closed"
        self.pending.mkdir()
        self.closed.mkdir()
        us_config = self.tmp / "us_ticker_config.json"
        us_config.write_text(json.dumps(US_CONFIG), encoding="utf-8")

        self._saved = (rollup.PENDING, rollup.AUTO_CLOSED, rollup.AUTOCLOSE_LEDGER,
                       rollup.US_CONFIG_PATH, rollup.load_registry, rollup.deep_dive_index)
        rollup.PENDING = self.pending
        rollup.AUTO_CLOSED = self.closed
        rollup.AUTOCLOSE_LEDGER = self.closed / "_autoclose_ledger.json"
        rollup.US_CONFIG_PATH = us_config
        rollup.load_registry = lambda: {"holdings": HOLDINGS}
        # Pinned so the re-verify tests never depend on which dives happen to exist
        # in the working tree.
        rollup.deep_dive_index = lambda: DIVES
        self.addCleanup(self.restore)

    def restore(self):
        (rollup.PENDING, rollup.AUTO_CLOSED, rollup.AUTOCLOSE_LEDGER,
         rollup.US_CONFIG_PATH, rollup.load_registry, rollup.deep_dive_index) = self._saved
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_closed(self, *names):
        for name in names:
            (self.closed / name).write_text("# onboard\n", encoding="utf-8")

    def test_placeholder_closure_is_reopened_and_clean_one_stays(self):
        self.write_closed("ADI_onboard_2026-07-18.md", "ICE_onboard_2026-07-10.md")
        reopened, still_closed = rollup.reverify_auto_closed("2026-08-09T00:00:00Z")
        self.assertEqual((reopened, still_closed), (1, 1))
        self.assertTrue((self.pending / "ADI_onboard_2026-07-18.md").exists())
        self.assertTrue((self.closed / "ICE_onboard_2026-07-10.md").exists())

    def test_reopen_appends_to_the_ledger_instead_of_rewriting_it(self):
        rollup.AUTOCLOSE_LEDGER.write_text(
            json.dumps([{"action": "auto_closed", "file": "ADI_onboard_2026-07-18.md"}]),
            encoding="utf-8")
        self.write_closed("ADI_onboard_2026-07-18.md")
        rollup.reverify_auto_closed("2026-08-09T00:00:00Z")
        ledger = json.loads(rollup.AUTOCLOSE_LEDGER.read_text(encoding="utf-8"))
        self.assertEqual(len(ledger), 2)
        self.assertEqual(ledger[0]["action"], "auto_closed")
        self.assertEqual(ledger[1]["action"], "reopened")
        self.assertIn("classification_unconfirmed:archetype,moat,dhando,stance,cycle,moi_bucket,payoff_lens",
                      ledger[1]["blockers"])

    def test_non_onboard_files_are_left_alone(self):
        self.write_closed("AMZN_deep_dive_2026-05-21.md")
        reopened, still_closed = rollup.reverify_auto_closed("2026-08-09T00:00:00Z")
        self.assertEqual((reopened, still_closed), (0, 0))
        self.assertTrue((self.closed / "AMZN_deep_dive_2026-05-21.md").exists())

    def test_rerun_is_idempotent(self):
        self.write_closed("ADI_onboard_2026-07-18.md")
        rollup.reverify_auto_closed("2026-08-09T00:00:00Z")
        again = rollup.reverify_auto_closed("2026-08-09T00:00:00Z")
        self.assertEqual(again, (0, 0))


if __name__ == "__main__":
    unittest.main()
