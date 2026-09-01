#!/usr/bin/env python3
"""Unit tests for the transcript relevance gate and the caption pacing budget."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "_system" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import caption_rate_limit as rl  # noqa: E402
import score_video_relevance as svr  # noqa: E402

AMBIG_CFG = ROOT / "_system" / "reference" / "video" / "ambiguous_aliases.json"


class WordBoundaryTests(unittest.TestCase):
    """The INTC bug: `alias in text` filed Intel against AI discussions."""

    def test_intel_does_not_match_inside_intelligent(self):
        pat = svr.pattern_for("intel")
        self.assertFalse(pat.search("an artificial intelligence system"))
        self.assertFalse(pat.search("the intelligent investor"))

    def test_intel_still_matches_the_company(self):
        self.assertTrue(svr.pattern_for("intel").search("like the intel or tsmc business"))

    def test_possessive_still_matches(self):
        self.assertTrue(svr.pattern_for("berkshire").search("berkshire's annual meeting"))

    def test_alias_at_end_of_sentence_matches(self):
        self.assertTrue(svr.pattern_for("markel").search("he runs Markel."))


class AmbiguousAliasTests(unittest.TestCase):
    def test_config_loads_and_is_non_empty(self):
        self.assertTrue(svr.AMBIGUOUS_ALIASES)
        self.assertTrue(svr.ACRONYM_STOP_TOKENS)

    def test_the_known_offenders_are_listed(self):
        # bullish -> BLSH matched "I'm very bullish on Israel";
        # recall -> REC.AX matched "you might recall that...".
        for word in ("bullish", "intel", "recall", "target", "compass"):
            self.assertIn(word, svr.AMBIGUOUS_ALIASES, word)

    def test_config_has_no_duplicates(self):
        doc = json.loads(AMBIG_CFG.read_text(encoding="utf-8"))
        for key in ("ambiguous", "acronym_stop_tokens"):
            self.assertEqual(len(doc[key]), len(set(doc[key])), key)

    def test_ambiguous_alias_alone_does_not_establish_a_ticker(self):
        aliases = {"bullish": "BLSH"}
        signals = svr.score_transcript("I am very bullish on Israel. " * 20, aliases, {})
        self.assertEqual(signals["sustained_tickers"], [])
        self.assertIn("BLSH", signals["ambiguous_alias_rejected"])

    def test_ambiguous_alias_counts_once_corroborated(self):
        # "alphabet" rides on "google"; that is the whole point of the rule.
        aliases = {"alphabet": "GOOGL", "google": "GOOGL"}
        text = ("google is a great business. " * 4) + ("alphabet trades cheaply. " * 4)
        signals = svr.score_transcript(text, aliases, {})
        self.assertEqual([r["ticker"] for r in signals["sustained_tickers"]], ["GOOGL"])


class CorporateSuffixTests(unittest.TestCase):
    def test_strips_a_simple_suffix(self):
        self.assertEqual(svr.strip_corporate_suffix("bwx technologies, inc."),
                         "bwx technologies")

    def test_strips_stacked_suffixes(self):
        self.assertEqual(svr.strip_corporate_suffix("datasection co., ltd."), "datasection")

    def test_leaves_a_clean_name_alone(self):
        self.assertEqual(svr.strip_corporate_suffix("carvana"), "carvana")

    def test_expansion_drops_cross_ticker_collisions(self):
        aliases = {"graham holdings co": "GHC", "graham corporation": "GHM",
                   "carvana co": "CVNA"}
        out = svr.expand_aliases(aliases, {})
        self.assertNotIn("graham", out)
        self.assertEqual(out.get("carvana"), "CVNA")

    def test_expansion_drops_person_name_collisions(self):
        # 'templeton' is Lauren Templeton in this corpus far more often than a ticker.
        out = svr.expand_aliases({"templeton emerging markets plc": "TEM"},
                                 {"templeton": "templeton_guest"})
        self.assertNotIn("templeton", out)


class ShortFormTests(unittest.TestCase):
    """First mention full, every mention after that abbreviated."""

    def test_leading_token_is_taken(self):
        self.assertEqual(svr.short_form("bwx technologies"), "bwx")

    def test_generic_leading_tokens_are_refused(self):
        for name in ("general motors", "american airlines", "first solar",
                     "national grid"):
            self.assertIsNone(svr.short_form(name), name)

    def test_single_token_alias_has_no_short_form(self):
        self.assertIsNone(svr.short_form("carvana"))

    def test_short_form_lifts_a_pitch_over_the_floor(self):
        # The real shape of the BWX pitch: full name twice, abbreviation throughout.
        text = ("bwx technologies is the subject. " * 2) + ("bwx makes naval reactors. " * 20)
        signals = svr.score_transcript(text, {"bwx technologies": "BWXT"}, {})
        self.assertEqual([r["ticker"] for r in signals["sustained_tickers"]], ["BWXT"])

    def test_short_form_cannot_introduce_an_unnamed_company(self):
        # Without the full name present, the abbreviation must contribute nothing.
        signals = svr.score_transcript("bwx bwx bwx bwx bwx bwx", {"bwx technologies": "BWXT"}, {})
        self.assertEqual(signals["sustained_tickers"], [])


class SpreadRequirementTests(unittest.TestCase):
    """The rule that silently rejected every short talk."""

    def test_video_chunk_window_is_smaller_than_the_podcast_one(self):
        # 12,000 made a 10,214-char pitch exactly one chunk, so "across >= 2
        # chunks" could never be satisfied.
        self.assertLess(svr.VIDEO_CHUNK_CHARS, 12000)

    def test_a_ten_minute_pitch_yields_more_than_one_chunk(self):
        self.assertGreater(len(svr.chunk_video("x" * 10214)), 1)

    def test_spread_never_demands_more_windows_than_exist(self):
        # A short transcript must be judged on recurrence, not on being short.
        text = "carvana is the whole subject here. " * 8
        signals = svr.score_transcript(text, {"carvana": "CVNA"}, {})
        self.assertEqual(len(signals["sustained_tickers"]), 1)

    def test_a_single_passing_mention_is_not_sustained(self):
        text = ("we talked about many things. " * 200) + "carvana came up once."
        signals = svr.score_transcript(text, {"carvana": "CVNA"}, {})
        self.assertEqual(signals["sustained_tickers"], [])
        self.assertEqual([r["ticker"] for r in signals["mentioned_only"]], ["CVNA"])


class DecisionTests(unittest.TestCase):
    def test_company_route_admits(self):
        self.assertTrue(svr.decide({"sustained_tickers": [{"ticker": "BWXT"}],
                                    "people": []})["admitted"])

    def test_people_route_admits(self):
        self.assertTrue(svr.decide({"sustained_tickers": [],
                                    "people": [{"guest_id": "pabrai"}]})["admitted"])

    def test_nothing_found_is_rejected(self):
        verdict = svr.decide({"sustained_tickers": [], "people": []})
        self.assertFalse(verdict["admitted"])
        self.assertEqual(verdict["gate"], "rejected_relevance")


class PacingBudgetTests(unittest.TestCase):
    """A rate limit must be prevented, not merely survived."""

    def test_spacing_floor_is_far_below_the_observed_trigger(self):
        # The block came at ~25 fetches spaced one second apart.
        self.assertGreaterEqual(rl.MIN_INTERVAL_SECONDS, 60)

    def test_hourly_cap_cannot_exceed_the_spacing_floor(self):
        # Otherwise the caps disagree and the looser one is decorative.
        max_possible = 3600 // rl.MIN_INTERVAL_SECONDS
        self.assertLessEqual(rl.MAX_PER_HOUR, max_possible)

    def test_backoff_doubles_and_is_capped(self):
        doc = {"fetches": [], "backoff_seconds": 0, "blocked_until": None}
        seen = []
        for _ in range(8):
            current = doc["backoff_seconds"]
            nxt = (rl.BACKOFF_START_SECONDS if current <= 0
                   else min(current * 2, rl.BACKOFF_CEILING_SECONDS))
            doc["backoff_seconds"] = nxt
            seen.append(nxt)
        self.assertEqual(seen[0], rl.BACKOFF_START_SECONDS)
        self.assertEqual(seen[-1], rl.BACKOFF_CEILING_SECONDS)
        self.assertEqual(sorted(seen), seen)

    def test_a_persisted_block_denies_immediately(self):
        from datetime import datetime, timedelta, timezone
        future = (datetime.now(timezone.utc) + timedelta(minutes=30)).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        decision = rl.check({"fetches": [], "backoff_seconds": 1800,
                             "blocked_until": future})
        self.assertFalse(decision["allowed"])
        self.assertTrue(decision["reason"].startswith("backoff_until_"))

    def test_hourly_cap_denies(self):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        decision = rl.check({"fetches": [now] * (rl.MAX_PER_HOUR + 1),
                             "backoff_seconds": 0, "blocked_until": None})
        self.assertFalse(decision["allowed"])
        self.assertIn("cap", decision["reason"])

    def test_empty_state_allows(self):
        decision = rl.check({"fetches": [], "backoff_seconds": 0, "blocked_until": None})
        self.assertTrue(decision["allowed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
