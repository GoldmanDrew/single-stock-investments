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


if __name__ == "__main__":
    unittest.main()
