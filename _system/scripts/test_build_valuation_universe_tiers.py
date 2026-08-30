import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import build_valuation_universe_tiers as tiers


class ValuationUniverseTierTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        policy = json.loads((tiers.ROOT / tiers.POLICY_REL).read_text(encoding="utf-8"))
        self.write(tiers.POLICY_REL, policy)
        self.write("_system/portfolio/registry.json", {"holdings": {}, "watchlist": {}})

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, relative: str | Path, payload) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(payload, str):
            path.write_text(payload, encoding="utf-8")
        else:
            path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def build(self):
        return tiers.build("2026-08-30", self.root)

    def test_registry_holdings_are_tier_3_research_members_not_positions(self):
        self.write("_system/portfolio/registry.json", {
            "holdings": {"REG": {"company": "Registry Only"}, "ZERO": {"company": "Zero Position"}},
            "watchlist": {},
        })
        self.write("_system/portfolio/paper/taxable.json", {
            "account_id": "taxable",
            "positions": [{"ticker": "ZERO", "shares": 0, "weight_pct": 0}],
        })

        payload = self.build()

        self.assertEqual(payload["assignments"]["REG"]["tier"], 3)
        self.assertEqual(payload["assignments"]["ZERO"]["tier"], 3)
        self.assertEqual(
            {row["code"] for row in payload["assignments"]["REG"]["assignment_reasons"]},
            {"research_universe_member"},
        )
        self.assertEqual(payload["validation"]["status"], "pass")

    def test_tier_1_sources_cover_positions_committees_triggers_decisions_and_approved_targets(self):
        self.write("_system/portfolio/registry.json", {
            "holdings": {ticker: {} for ticker in ("POS", "IC", "TRIG", "DEC", "EXP", "APP")},
            "watchlist": {},
        })
        self.write("_system/portfolio/paper/roth.json", {
            "account_id": "roth",
            "positions": [{"ticker": "POS", "shares": 2}],
        })
        self.write("IC/research/valuation_workbench.json", {
            "ticker": "IC",
            "committee": {
                "status": "independent_review_open",
                "stage": "round_one_open",
                "manifest_ref": "IC/research/committee_work/2026-08-30/manifest.json",
            },
        })
        self.write("TRIG/research/committee_trigger.json", {
            "ticker": "TRIG", "status": "open", "reason": "material thesis change",
        })
        self.write("DEC/research/human_decision.json", {
            "ticker": "DEC", "status": "decided", "decision": "hold", "expires_at": "2026-12-01",
        })
        self.write("EXP/research/human_decision.json", {
            "ticker": "EXP", "status": "decided", "decision": "watch", "expires_at": "2026-08-01",
        })
        self.write("_system/portfolio/taxable_target_weights.json", {
            "status": "approved", "weights": [{"ticker": "APP", "weight_pct": 4}],
        })

        payload = self.build()

        for ticker in ("POS", "IC", "TRIG", "DEC", "EXP", "APP"):
            with self.subTest(ticker=ticker):
                self.assertEqual(payload["assignments"][ticker]["tier"], 1)
        self.assertIn("expired_human_decision", {
            row["code"] for row in payload["assignments"]["EXP"]["assignment_reasons"]
        })
        self.assertTrue(payload["assignments"]["IC"]["workflow_policy"]["committee_auto_start"])

    def test_tier_2_sources_cover_followups_watchlist_stances_and_proposed_targets(self):
        self.write("_system/portfolio/registry.json", {
            "holdings": {"WATCH": {}, "HOLD": {}, "PROP": {}, "FUP": {}, "COHORT": {}},
            "watchlist": {"WATCH": {"reason": "curated"}},
        })
        self.write("_system/reference/valuation_followups.json", {
            "tickers": {"FUP": {"evidence_gaps": []}},
            "validation_cohort": [{"ticker": "COHORT"}],
        })
        self.write("_system/portfolio/classification.json", {"HOLD": {"stance": "hold"}})
        self.write("_system/portfolio/ira_target_weights.json", {
            "status": "proposed", "weights": [{"ticker": "PROP", "weight_pct": 5}],
        })

        payload = self.build()

        for ticker in ("WATCH", "HOLD", "PROP", "FUP", "COHORT"):
            with self.subTest(ticker=ticker):
                self.assertEqual(payload["assignments"][ticker]["tier"], 2)
                self.assertFalse(payload["assignments"][ticker]["workflow_policy"]["committee_auto_start"])

    def test_latest_active_raw_committee_manifest_is_tier_1(self):
        self.write("_system/portfolio/registry.json", {"holdings": {"RAW": {}}, "watchlist": {}})
        self.write("RAW/research/committee_work/2026-08-30/manifest.json", {
            "ticker": "RAW", "as_of": "2026-08-30", "stage": "chair_pending",
        })

        payload = self.build()

        self.assertEqual(payload["assignments"]["RAW"]["tier"], 1)
        self.assertIn("active_committee_manifest", {
            row["code"] for row in payload["assignments"]["RAW"]["assignment_reasons"]
        })

    def test_decision_grade_or_screening_model_alone_does_not_promote(self):
        self.write("_system/portfolio/registry.json", {"holdings": {"MODEL": {}}, "watchlist": {}})
        self.write("MODEL/research/valuation_workbench.json", {
            "ticker": "MODEL",
            "decision": {
                "status": "decision_grade",
                "model_level": "screening_grade",
                "forward_return_at_price_pct": {"base": 99},
            },
            "committee": {"status": "not_started"},
        })

        payload = self.build()

        self.assertEqual(payload["assignments"]["MODEL"]["tier"], 3)
        self.assertEqual(
            {row["code"] for row in payload["assignments"]["MODEL"]["assignment_reasons"]},
            {"research_universe_member"},
        )

    def test_owner_override_wins_both_upward_and_downward_and_keeps_audit_reasons(self):
        policy_path = self.root / tiers.POLICY_REL
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        policy["overrides"] = {
            "UP": {"tier": 1, "reason": "Owner requests full underwriting", "review_by": "2026-08-20"},
            "DOWN": {"tier": 3, "reason": "Position is a temporary data test", "review_by": "2026-12-01"},
        }
        self.write(tiers.POLICY_REL, policy)
        self.write("_system/portfolio/registry.json", {"holdings": {"UP": {}, "DOWN": {}}, "watchlist": {}})
        self.write("_system/portfolio/paper/taxable.json", {
            "positions": [{"ticker": "DOWN", "shares": 1}],
        })

        payload = self.build()

        up = payload["assignments"]["UP"]
        down = payload["assignments"]["DOWN"]
        self.assertEqual((up["automatic_tier"], up["tier"]), (3, 1))
        self.assertEqual((down["automatic_tier"], down["tier"]), (1, 3))
        self.assertEqual(up["assignment_source"], "owner_override")
        self.assertTrue(up["review_overdue"])
        self.assertIn("positive_paper_position", {row["code"] for row in down["assignment_reasons"]})
        self.assertIn("owner_override", {row["code"] for row in down["assignment_reasons"]})

    def test_every_tier_preserves_human_only_capital_authority(self):
        self.write("_system/portfolio/registry.json", {
            "holdings": {"ONE": {}, "TWO": {}, "THREE": {}},
            "watchlist": {"TWO": {}},
        })
        self.write("_system/portfolio/paper/taxable.json", {
            "positions": [{"ticker": "ONE", "notional_usd": 10}],
        })

        payload = self.build()

        for ticker in ("ONE", "TWO", "THREE"):
            workflow = payload["assignments"][ticker]["workflow_policy"]
            self.assertEqual(workflow["capital_authority"], "human_decision_only")
            self.assertFalse(workflow["automated_screen_can_authorize_capital"])
            self.assertFalse(workflow["generic_screen_can_authorize_capital"])
        self.assertTrue(payload["validation"]["checks"]["human_only_capital_authority"])

    def test_output_is_deterministic_and_summary_reconciles(self):
        self.write("_system/portfolio/registry.json", {
            "holdings": {"ZED": {}, "ALPHA": {}}, "watchlist": {"ZED": {}},
        })

        first = self.build()
        second = self.build()

        self.assertEqual(tiers.render(first), tiers.render(second))
        self.assertEqual(list(first["assignments"]), ["ALPHA", "ZED"])
        self.assertEqual(sum(first["summary"]["tier_counts"].values()), first["summary"]["security_count"])

    def test_invalid_override_is_rejected(self):
        policy_path = self.root / tiers.POLICY_REL
        policy = copy.deepcopy(json.loads(policy_path.read_text(encoding="utf-8")))
        policy["overrides"] = {"BAD": {"tier": 4, "reason": ""}}
        self.write(tiers.POLICY_REL, policy)

        with self.assertRaisesRegex(ValueError, "Invalid valuation universe policy"):
            self.build()


if __name__ == "__main__":
    unittest.main()
