#!/usr/bin/env python3
"""Unit tests for podcast guest registry, entity resolve, and insights merge."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "_system" / "scripts"
import sys

sys.path.insert(0, str(SCRIPTS))

from resolve_podcast_entities import PodcastEntityResolver, resolve_text  # noqa: E402
from build_insights import from_podcast_episodes, load_podcast_insights_doc  # noqa: E402
from vault_paths import podcasts_root, PODCASTS_REF_PREFIX  # noqa: E402

POD = ROOT / "_system" / "reference" / "podcasts"
POWER_ZONES = ROOT / "_system" / "frameworks" / "power_zones.json"
PERSONAS = ROOT / "_system" / "lenses" / "personas.json"


class PodcastRegistryTests(unittest.TestCase):
    def test_guest_registry_covers_zones_and_map(self):
        guests = json.loads((POD / "podcast_guest_registry.json").read_text(encoding="utf-8"))
        by_id = {g["guest_id"]: g for g in guests["guests"]}
        zones = json.loads(POWER_ZONES.read_text(encoding="utf-8")).get("zones") or {}
        for zid in zones:
            self.assertIn(zid, by_id, f"missing zone guest {zid}")
            self.assertGreaterEqual(len(by_id[zid].get("search_queries") or []), 1)
        fmap = json.loads(PERSONAS.read_text(encoding="utf-8")).get("fund_persona_map") or {}
        # mapped names encoded as guest ids
        expected_map_ids = {
            "ackman",
            "loeb",
            "lone_pine",
            "tiger",
            "coatue",
            "valueact",
        }
        for gid in expected_map_ids:
            self.assertIn(gid, by_id)
        # Tier B locked list
        for gid in (
            "vinall",
            "einhorn",
            "spier",
            "li_lu",
            "watsa",
            "akre",
            "smith_fundsmith",
            "orbis",
            "nomad",
            "rochon",
            "begg",
            "bloomstran",
            "russo",
        ):
            self.assertEqual(by_id[gid]["tier"], "guest_only")
        self.assertGreaterEqual(len(by_id), 30)
        _ = fmap  # unused except documenting sync source

    def test_show_registry_includes_synopsis(self):
        shows = json.loads((POD / "show_registry.json").read_text(encoding="utf-8"))
        ids = {s["show_id"] for s in shows["shows"]}
        self.assertIn("the_synopsis", ids)
        self.assertGreaterEqual(len(ids), 16)


class PodcastResolveGoldTests(unittest.TestCase):
    def test_evolution_officer_true_positive(self):
        r = resolve_text(
            "Martin Carlesund, CEO of Evolution Gaming on live casino",
            "Chief Executive Officer of Evolution Gaming; NetEnt mentioned",
            "Martin Carlesund of Evolution Gaming. Not Evotec.",
        )
        self.assertTrue(r["has_officer_hit"])
        self.assertIn("EVO.ST", r["tickers"])
        self.assertTrue(any(c.get("company_key") == "evolution_gaming" for c in r["companies"]))
        self.assertNotIn("EVO", r["tickers"])

    def test_evotec_collision_guard(self):
        r = resolve_text(
            "Evotec SE pipeline update",
            "Discussion of Evotec clinical assets",
            "Evotec is a biotech company.",
        )
        # May or may not resolve Evotec via master; must not be evolution_gaming
        self.assertFalse(any(c.get("company_key") == "evolution_gaming" for c in r["companies"]))

    def test_macro_evolution_negative(self):
        r = resolve_text(
            "The evolution of markets and indexation",
            "A macro discussion of the evolution of markets",
        )
        self.assertEqual(r["tickers"], [])
        self.assertFalse(any(c.get("company_key") == "evolution_gaming" for c in r["companies"]))

    def test_pz_guest_pabrai_marks(self):
        r = resolve_text(
            "Howard Marks joins Mohnish Pabrai for chai",
            "Mohnish Pabrai hosts Howard Marks of Oaktree",
        )
        ids = {g["guest_id"] for g in r["guests"]}
        self.assertIn("pabrai", ids)
        self.assertIn("marks_credit_cycle", ids)

    def test_host_show_does_not_spam_from_show_title(self):
        r = PodcastEntityResolver().resolve_episode(
            title="Macro update with no named guest",
            description="Weekly markets roundup",
            show_title="Chai with Pabrai",
        )
        self.assertEqual(r["guests"], [])

    def test_host_guest_injection(self):
        r = PodcastEntityResolver().resolve_episode(
            title="Macro update with no named guest",
            description="Weekly markets roundup",
            show_title="Chai with Pabrai",
            host_guest_ids=["pabrai"],
        )
        self.assertEqual({g["guest_id"] for g in r["guests"]}, {"pabrai"})

    def test_ceo_of_junk_not_officer(self):
        r = resolve_text(
            "Outsmarting Uber",
            "Why Bolt wins in Europe — CEO of FROM nowhere",
        )
        self.assertNotIn("FROM", r["tickers"])
        self.assertFalse(r["has_officer_hit"])


class PodcastInsightsMergeTests(unittest.TestCase):
    def test_from_podcast_episodes_emits_records(self):
        doc = load_podcast_insights_doc()
        recs = from_podcast_episodes(doc)
        # Fixtures should produce at least officer/PZ records
        self.assertTrue(any(r.get("source") == "podcast_episode" for r in recs) or doc.get("episodes"))
        for r in recs:
            self.assertFalse(r.get("in_base_irr"))
            self.assertNotIn("highlights", r)

    def test_index_mirror_skips_fanout(self):
        from build_insights import from_podcast_episodes as fanout

        slim = {
            "schema_kind": "index_mirror",
            "episode_count": 1,
            "episodes": [
                {
                    "episode_id": "ep1",
                    "show_id": "s1",
                    "title": "t",
                    "tickers": ["HD"],
                    "positions": [{"ticker": "HD"}],
                    "themes": [{"theme": "AI", "stance": "neutral"}],
                }
            ],
        }
        self.assertEqual(fanout(slim), [])

    def test_podcast_by_show_is_thin(self):
        from build_insights import podcast_by_show

        doc = {
            "episodes": [
                {
                    "episode_id": "a",
                    "show_id": "s1",
                    "show_title": "Show One",
                    "title": "Ep A",
                    "published": "2026-01-01",
                    "tickers": ["HD"],
                },
                {
                    "episode_id": "b",
                    "show_id": "s1",
                    "show_title": "Show One",
                    "title": "Ep B",
                    "published": "2026-02-01",
                },
            ]
        }
        by = podcast_by_show(doc)
        self.assertEqual(by["s1"]["episode_count"], 2)
        self.assertEqual(by["s1"]["episode_ids"], ["a", "b"])
        self.assertNotIn("episodes", by["s1"])

    def test_slim_index_mirror_path(self):
        from build_podcast_insights import INDEX_MIRROR_PATH, index_row_from_episode

        self.assertTrue(str(INDEX_MIRROR_PATH).endswith("insights_index_mirror.json"))
        row = index_row_from_episode(
            {
                "episode_id": "x",
                "show_id": "s",
                "show_title": "Show",
                "title": "T",
                "guests": [{"display": "Guest"}],
                "highlights": [
                    {
                        "text": "A claim about HD and capital allocation over the cycle.",
                        "quote": "A claim about HD and capital allocation over the cycle.",
                    }
                ],
                "themes": [{"theme": "AI", "stance": "neutral"}],
                "tickers": ["HD"],
                "summary": "Guest discusses HD capital allocation.",
            }
        )
        self.assertEqual(row["highlight_count"], 1)
        self.assertEqual(len(row["highlight_previews"]), 1)
        self.assertEqual(row["themes"][0]["theme"], "AI")
        self.assertTrue(row["has_summary"])

    def test_podcasts_ref_prefix(self):
        self.assertEqual(PODCASTS_REF_PREFIX, "_system/reference/podcasts")
        root = podcasts_root(create=True)
        self.assertTrue(root.exists())


class PodcastAudioGuardTests(unittest.TestCase):
    def test_audio_cache_gitignored(self):
        gi = podcasts_root(create=True) / ".gitignore"
        self.assertTrue(gi.exists())
        text = gi.read_text(encoding="utf-8")
        self.assertIn("audio-cache/", text)
        self.assertIn("*.mp3", text)


class PodcastHarvestTests(unittest.TestCase):
    def test_select_relevant_keep_all_watchlist(self):
        from discover_podcasts import select_relevant
        from resolve_podcast_entities import PodcastEntityResolver

        resolver = PodcastEntityResolver()
        eps = [
            {
                "episode_id": "filler-1",
                "title": "Weekly mailbag with no tickers",
                "description": "Listener questions about markets in general",
                "show_title": "Acquired",
                "published": "2026-01-01",
            },
            {
                "episode_id": "signal-1",
                "title": "Martin Carlesund, CEO of Evolution Gaming",
                "description": "Live casino economics",
                "show_title": "Business Breakdowns",
                "published": "2026-02-01",
            },
        ]
        kept_all = select_relevant(eps, resolver, watchlist=True, keep_all_watchlist=True)
        self.assertEqual(len(kept_all), 2)
        kept_filt = select_relevant(eps, resolver, watchlist=True, keep_all_watchlist=False)
        self.assertGreaterEqual(len(kept_filt), 1)
        self.assertLessEqual(len(kept_filt), 2)

    def test_filter_garbled_and_summary(self):
        from summarize_podcast_episode import (
            extractive_summary,
            filter_highlights,
            is_garbled_highlight,
        )

        self.assertTrue(is_garbled_highlight("PK\x03\x04 binary junk here!!!!"))
        self.assertTrue(is_garbled_highlight("http://a.com/x " * 20))
        self.assertTrue(
            is_garbled_highlight(
                "Internet Service Terms Apple Podcasts web player & Privacy Cookie Warning Support"
            )
        )
        clean = {
            "text": "The company has a durable moat from network effects and high switching costs.",
            "quote": "The company has a durable moat from network effects and high switching costs.",
            "method": "extractive",
        }
        filtered = filter_highlights([clean, {"text": "\x00\x01\x02 garbage blob"}])
        self.assertEqual(len(filtered), 1)
        summary = extractive_summary("Unused.", [clean])
        self.assertIn("moat", summary.lower())

    def test_whisper_backlog_upsert(self):
        import tempfile
        from pathlib import Path
        from unittest import mock

        import fetch_podcast_transcript as ft

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with mock.patch.object(ft, "podcasts_root", return_value=root):
                ft.upsert_whisper_backlog_item(
                    {
                        "episode_id": "ep-1",
                        "show_id": "acquired",
                        "title": "T",
                        "published": "2026-01-01",
                        "audio_url": "https://example.com/a.mp3",
                    },
                    status="pending",
                )
                doc = ft.load_whisper_backlog()
                self.assertEqual(doc["pending_count"], 1)
                self.assertEqual(doc["items"][0]["episode_id"], "ep-1")
                self.assertEqual(ft.whisper_pending_count(), 1)

    def test_episode_detail_payload(self):
        from build_podcast_insights import episode_detail_payload

        ep = {
            "episode_id": "test-ep-abc",
            "show_id": "acquired",
            "show_title": "Acquired",
            "title": "Episode",
            "published": "2026-01-01",
            "summary": "A short summary of the episode thesis.",
            "highlights": [
                {
                    "text": "Capital allocation discipline drove returns over a decade.",
                    "quote": "Capital allocation discipline drove returns over a decade.",
                }
            ],
            "tickers": ["HD"],
            "positions": [{"ticker": "HD", "commentary": "Discussed"}],
            "guests": [{"guest_id": "pabrai", "display": "Mohnish Pabrai"}],
            "themes": [{"theme": "Capital Allocation", "stance": "neutral"}],
        }
        detail = episode_detail_payload(ep)
        self.assertEqual(detail["summary"], ep["summary"])
        self.assertEqual(len(detail["highlights"]), 1)
        self.assertEqual(detail["tickers"], ["HD"])
        self.assertTrue(detail["guests"][0]["display"])


class TickerAttributionTests(unittest.TestCase):
    """A claim filed under the wrong company is the one error quote
    verification cannot catch, because the quote is genuine."""

    ALIASES = {
        "costamare inc.": "CMRE",
        "costco": "COST",
        "costar group": "CSGP",
        "invesco": "IVZ",
        "constellation software": "CSU",
        "elevance health inc": "ELV",
        "alphabet inc.": "GOOGL",
        "google": "GOOGL",
        "apple inc.": "AAPL",
        "apple hospitality reit": "APLE",
        "visa inc.": "V",
        "ford motor company": "F",
        "amazon.com": "AMZN",
        # Rows that made the model's own abbreviations dangerous: each is a
        # real master entry whose name leads with a two- or three-letter symbol
        # the model writes into the company field.
        "bank of america": "BAC",
        "bac.wa": "BAC.WA",
        "general dynamics": "GD",
        "gd culture group ltd": "GDC",
        "texas instruments": "TXN",
        "3m company": "MMM",
        # Harvested rows: real companies nobody curated, and the trap for any
        # rule that resolves a fragment. "Benchmark" the venture firm has no
        # master row, so "benchmark electronics inc" is the only thing its name
        # leads -- uniquely, which is exactly why uniqueness cannot be the test.
        "benchmark electronics inc": "BHE",
        "alpha pro tech ltd": "APT",
    }

    # The curated book, ~830 of the master's 3,735 rows. The harvested tail
    # (CMRE, APLE, GDC, BAC.WA, BHE, APT) is deliberately absent.
    BOOK = frozenset({"COST", "CSGP", "IVZ", "CSU", "ELV", "GOOGL", "AAPL", "V",
                      "F", "AMZN", "BAC", "GD", "TXN", "MMM"})

    def _validated(self, company, ticker):
        from analyze_podcast_episode import validate_tickers  # noqa: WPS433

        claims = [{"company": company, "ticker": ticker, "claim": "x"}]
        validate_tickers(claims, dict(self.ALIASES), self.BOOK)
        return claims[0]

    def test_symbol_in_company_field_is_not_a_mismatch(self):
        """The model writes company=COST for Costco. Character matching sent
        that to "costamare inc." -> CMRE and rewrote four real Costco claims
        onto a Greek containership lessor."""
        self.assertEqual(self._validated("COST", "COST")["ticker"], "COST")

    def test_stub_never_captures_a_longer_name(self):
        for company in ("COST", "COSTA"):
            with self.subTest(company=company):
                self.assertNotEqual(self._validated(company, company)["ticker"], "CMRE")

    def test_ambiguous_leading_word_resolves_to_nothing(self):
        """Apple leads both "Apple Inc." and "Apple Hospitality REIT". A
        leading-word run is only an attribution when the master agrees on one
        answer -- otherwise a claim about Apple lands on a hotel REIT."""
        from analyze_podcast_episode import _match_alias  # noqa: WPS433

        self.assertIsNone(_match_alias("appl", dict(self.ALIASES), self.BOOK))
        # Apple itself is unambiguous: it matches "Apple Inc." exactly.
        self.assertEqual(self._validated("Apple", "AAPL")["ticker"], "AAPL")
        self.assertEqual(self._validated("Apple Hospitality REIT", "APLE")["ticker"], "APLE")

    def test_unambiguous_leading_word_resolves(self):
        """Ford is not "Ford Motor Company" exactly, but nothing else in the
        master leads with it."""
        self.assertEqual(self._validated("Ford", "F")["ticker"], "F")

    def test_short_names_survive(self):
        """The alias index used to drop everything under five characters, which
        deleted Visa and Ford from attribution entirely. That floor belongs to
        the substring scanners, not here."""
        self.assertEqual(self._validated("Visa", "V")["ticker"], "V")

    def test_self_naming_does_not_outrank_existence(self):
        """The model spelling company and ticker the same way is not evidence.
        "TSMC" is not a symbol -- the master carries TSM -- and "TI" is Telecom
        Italia, not Texas Instruments, which is TXN. Both walked through on 10
        and 7 claims because the self-naming case was tested before the master
        was consulted at all."""
        for symbol in ("TSMC", "TI"):
            with self.subTest(symbol=symbol):
                claim = self._validated(symbol, symbol)
                self.assertIsNone(claim["ticker"])
                self.assertEqual(claim["ticker_rejected"], symbol)

    def test_self_naming_still_holds_for_a_symbol_the_master_carries(self):
        for company, ticker in (("COST", "COST"), ("BAC", "BAC"), ("GD", "GD")):
            with self.subTest(company=company):
                self.assertEqual(self._validated(company, ticker)["ticker"], ticker)

    def test_short_symbol_never_leads_a_longer_name(self):
        """A leading-word run is not a licence for a stub. "BAC" leads
        "BAC.WA" and took a Bank of America claim to a Warsaw listing; "GD"
        leads "GD Culture Group Ltd" and took a General Dynamics claim to GDC.
        Equality needs no floor, but this branch does."""
        self.assertEqual(self._validated("BAC", "BAC")["ticker"], "BAC")
        self.assertEqual(self._validated("GD", "GD")["ticker"], "GD")

    def test_two_character_name_still_matches_exactly(self):
        """The prefix floor must not cost the exact path: 3M is two characters
        and matches "3M Company" outright."""
        self.assertEqual(self._validated("3M", "MMM")["ticker"], "MMM")

    def test_real_symbol_for_the_wrong_company_is_dropped(self):
        """IVZ is a perfectly real symbol. It is not Vanguard, which the master
        does not carry at all -- so the symbol is unverifiable and must go."""
        claim = self._validated("Vanguard", "IVZ")
        self.assertIsNone(claim["ticker"])
        self.assertEqual(claim["ticker_rejected"], "IVZ")

    def test_contradicted_symbol_is_corrected(self):
        claim = self._validated("Constellation Software", "CSCO")
        self.assertEqual(claim["ticker"], "CSU")
        self.assertEqual(claim["ticker_corrected_from"], "CSCO")

    def test_corporate_suffix_is_not_a_difference(self):
        self.assertEqual(self._validated("Elevance Health", "ELV")["ticker"], "ELV")
        self.assertEqual(self._validated("Alphabet", "GOOGL")["ticker"], "GOOGL")
        self.assertEqual(self._validated("Amazon", "AMZN")["ticker"], "AMZN")

    def test_match_does_not_depend_on_alias_insertion_order(self):
        """The Costco/Costamare bug was decided by which key the master happened
        to store first. Order must not be able to change an attribution."""
        from analyze_podcast_episode import validate_tickers  # noqa: WPS433

        forward = dict(self.ALIASES)
        reverse = dict(reversed(list(self.ALIASES.items())))
        for company, ticker in (("Costco", "COST"), ("COST", "COST"),
                                ("Vanguard", "IVZ"), ("Apple", "AAPL"), ("Ford", "F")):
            with self.subTest(company=company):
                a = [{"company": company, "ticker": ticker}]
                b = [{"company": company, "ticker": ticker}]
                validate_tickers(a, forward, self.BOOK)
                validate_tickers(b, reverse, self.BOOK)
                self.assertEqual(a[0]["ticker"], b[0]["ticker"])

    def test_resolve_fills_a_missing_symbol_without_guessing(self):
        from analyze_podcast_episode import resolve_tickers  # noqa: WPS433

        claims = [
            {"company": "Elevance Health", "ticker": None},
            {"company": "COST", "ticker": None},
            {"company": "Vanguard", "ticker": None},
        ]
        resolve_tickers(claims, dict(self.ALIASES), self.BOOK)
        self.assertEqual(claims[0]["ticker"], "ELV")
        self.assertIsNone(claims[1]["ticker"])
        self.assertIsNone(claims[2]["ticker"])

    def test_unique_leading_word_is_not_enough_on_its_own(self):
        """Fourth variant of the same bug. The ambiguity gate asks whether two
        master rows compete for the stub; it cannot ask whether the company the
        speaker meant is in the master at all. "Benchmark" -- the venture firm,
        which has no row -- uniquely leads "Benchmark Electronics Inc", so it
        won uncontested and carried a claim about a VC to a contract
        manufacturer. Oaktree -> OCSL, Sears -> SCC.T and Tencent -> TME are the
        same shape, 6 of 75 leading-word attributions in the live corpus."""
        claim = self._validated("Benchmark", "BHE")
        self.assertIsNone(claim["ticker"])
        self.assertEqual(claim["ticker_rejected"], "BHE")
        # ...while a leading-word run onto the book still resolves.
        self.assertEqual(self._validated("Ford", "F")["ticker"], "F")

    def test_self_naming_does_not_reach_the_harvested_tail(self):
        """Self-naming contains no evidence at all -- neither field is a company
        name -- so it may only land on a curated symbol. "APT" took a claim
        about Applied Technology to Alpha Pro Tech on nothing but the model
        spelling it the same way twice."""
        claim = self._validated("APT", "APT")
        self.assertIsNone(claim["ticker"])
        self.assertEqual(claim["ticker_rejected"], "APT")

    def test_every_attribution_records_the_rule_that_made_it(self):
        """Each of the four variants was found by auditing live output, never by
        a failing test. Recording the branch makes the fifth visible in the
        corpus without a hand audit."""
        for company, ticker, basis in (("Costco", "COST", "exact_name"),
                                       ("Elevance Health", "ELV", "same_name"),
                                       ("Ford", "F", "leading_word"),
                                       ("COST", "COST", "self_named")):
            with self.subTest(company=company):
                self.assertEqual(self._validated(company, ticker)["ticker_basis"], basis)

    def test_a_symbol_is_not_a_company_name(self):
        """274 master rows, every one a foreign listing, are named only by their
        own symbol: BA.L is called "ba.l". The model wrote company "BA" for
        Boeing, which reduces to the same single token, so it matched by
        *equality* -- the one path with no length floor -- and a Boeing claim
        landed on BAE Systems in London."""
        import whisper_vocab  # noqa: WPS433
        from analyze_podcast_episode import build_aliases  # noqa: WPS433

        rows = {"BA.L": {"name": "BA.L", "in_book": False},
                "IBM": {"name": "IBM", "in_book": True},
                "AAON": {"name": "AAON, Inc.", "in_book": True}}
        original = whisper_vocab._securities
        whisper_vocab._securities = lambda: rows
        try:
            aliases = build_aliases()
        finally:
            whisper_vocab._securities = original
        self.assertNotIn("ba.l", aliases)
        # The exchange suffix is the tell. A plain symbol that is also the
        # company's name is a name: IBM, RH and UBER are the three, and
        # dropping IBM on this rule cost 22 correct claims.
        self.assertEqual(aliases.get("ibm"), "IBM")
        self.assertEqual(aliases.get("aaon, inc."), "AAON")

    def test_scan_floor_excludes_short_names_from_window_matching(self):
        """Short names are unsafe to look for *inside* prose -- visa matches
        "visa requirements". The floor still applies there."""
        from analyze_podcast_episode import scan_aliases  # noqa: WPS433

        scan = scan_aliases(dict(self.ALIASES))
        self.assertNotIn("visa", scan)
        self.assertIn("costamare inc.", scan)


class AnalysisOverlayTests(unittest.TestCase):
    """The analysis reached the dashboard through nothing at all until it was
    folded into positions and themes here."""

    ANALYSIS = {
        "thesis": "Costco curation is the moat.",
        "themes": [{"theme": "Retail Moats", "stance": "bullish"}],
        "claims": [
            {"company": "Costco", "ticker": "COST", "stance": "bullish",
             "claim": "Costco sells fewer items on purpose.",
             "quote": "In Costco, you have very few things", "quote_verified": True},
            {"company": "Vanguard", "ticker": None, "stance": "neutral",
             "claim": "A claim whose symbol could not be corroborated."},
        ],
        "numbers": [{"what": "revenue", "value": "$440 million", "quote_verified": True}],
        "method": "local_llm", "quote_verified_rate": 1.0,
        "chunks_analyzed": 8, "chunks_total": 20,
    }

    def test_claim_upgrades_the_resolver_row_rather_than_duplicating_it(self):
        from build_podcast_insights import analysis_positions  # noqa: WPS433

        positions = [{"ticker": "COST", "action": "discussed",
                      "commentary": None, "tier": "resolver"}]
        analysis_positions(self.ANALYSIS, positions, {"COST"})
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0]["tier"], "llm_claim")
        self.assertEqual(positions[0]["stance"], "bullish")
        self.assertIn("fewer items", positions[0]["commentary"])

    def test_claim_without_a_ticker_creates_no_position(self):
        """The validator nulls a symbol it cannot corroborate. A fan-out row
        with no ticker has nothing to attach to."""
        from build_podcast_insights import analysis_positions  # noqa: WPS433

        positions: list = []
        analysis_positions(self.ANALYSIS, positions, set())
        self.assertEqual([p["ticker"] for p in positions], ["COST"])

    def test_model_themes_replace_keyword_themes(self):
        from build_podcast_insights import analysis_themes  # noqa: WPS433

        fallback = [{"theme": "Capital Allocation", "stance": "neutral"}]
        themes = analysis_themes(self.ANALYSIS, fallback)
        self.assertEqual(themes[0]["theme"], "Retail Moats")
        # Stance is translated into the vocabulary the fan-out already speaks.
        self.assertEqual(themes[0]["stance"], "constructive")
        self.assertEqual(analysis_themes({}, fallback), fallback)

    def test_index_row_carries_counts_not_claim_arrays(self):
        """podcast_index is one file the SPA loads at boot. Claims belong in the
        per-episode detail shard."""
        from build_podcast_insights import analysis_summary, index_row_from_episode  # noqa: WPS433

        row = index_row_from_episode({
            "episode_id": "e1", "title": "t", "tickers": ["COST"],
            "analysis": analysis_summary(self.ANALYSIS),
            "thesis": self.ANALYSIS["thesis"], "claims": self.ANALYSIS["claims"],
        })
        self.assertTrue(row["has_analysis"])
        self.assertEqual(row["claim_count"], 2)
        self.assertEqual(row["quote_verified_rate"], 1.0)
        self.assertIn("moat", row["thesis_preview"])
        self.assertNotIn("claims", row)

    def test_detail_payload_carries_claims_with_their_quotes(self):
        from build_podcast_insights import episode_detail_payload  # noqa: WPS433

        detail = episode_detail_payload({
            "episode_id": "e1", "title": "t",
            "thesis": self.ANALYSIS["thesis"], "claims": self.ANALYSIS["claims"],
            "numbers": self.ANALYSIS["numbers"],
        })
        self.assertEqual(len(detail["claims"]), 2)
        self.assertTrue(detail["claims"][0]["quote_verified"])
        self.assertEqual(detail["claims"][0]["ticker"], "COST")
        self.assertEqual(len(detail["numbers"]), 1)
        self.assertIn("moat", detail["thesis"])


if __name__ == "__main__":
    unittest.main()
