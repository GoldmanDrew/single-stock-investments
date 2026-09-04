#!/usr/bin/env python3
"""Unit tests for the YouTube channel registry and video discovery gate."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "_system" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from unittest import mock  # noqa: E402

import discover_videos  # noqa: E402
from discover_videos import (  # noqa: E402
    SLOP_PATTERNS, fetch_playlist, normalize_title, parse_channel_feed,
    playlist_sources, registry_sources, screen,
)
from resolve_youtube_channel import titles_agree  # noqa: E402

REG = ROOT / "_system" / "reference" / "video" / "channel_registry.json"

MINIMAL_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns:media="http://search.yahoo.com/mrss/"
      xmlns="http://www.w3.org/2005/Atom">
  <title>Test Channel</title>
  <entry>
    <id>yt:video:abc123XYZ_-</id>
    <yt:videoId>abc123XYZ_-</yt:videoId>
    <title>Larry Robbins pitches at Sohn 2026</title>
    <published>2026-05-27T12:00:00+00:00</published>
    <media:group>
      <media:description>A single-name pitch.</media:description>
      <media:community>
        <media:statistics views="4210"/>
      </media:community>
    </media:group>
  </entry>
</feed>"""


class RegistryIntegrityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.doc = json.loads(REG.read_text(encoding="utf-8"))
        self.channels = self.doc["channels"]

    def test_every_channel_has_required_fields(self):
        for ch in self.channels:
            for field in ("channel_id", "title", "tier", "trust", "ingest", "rss_url"):
                self.assertIn(field, ch, f"{ch.get('title')} missing {field}")
            self.assertRegex(ch["channel_id"], r"^UC[\w-]{22}$")
            self.assertIn(ch["tier"], {"duplicate", "guest", "native"})
            self.assertIn(ch["trust"], {"high", "broad"})

    def test_channel_ids_are_unique(self):
        ids = [c["channel_id"] for c in self.channels]
        self.assertEqual(len(ids), len(set(ids)))

    def test_rss_url_matches_channel_id(self):
        for ch in self.channels:
            self.assertTrue(ch["rss_url"].endswith(ch["channel_id"]), ch["title"])

    def test_uploads_playlist_derives_from_channel_id(self):
        # UU<id-without-UC> is the uploads playlist; the API backfill depends on it.
        for ch in self.channels:
            self.assertEqual(ch["uploads_playlist_id"], "UU" + ch["channel_id"][2:])

    def test_duplicate_tier_is_never_ingested(self):
        # A pure mirror of a show already in the podcast corpus must not be fetched.
        for ch in self.channels:
            if ch["tier"] == "duplicate":
                self.assertFalse(ch["ingest"], f"{ch['title']} would double-ingest")

    def test_guest_ids_exist_in_the_podcast_guest_registry(self):
        # The video lane must not grow a second relevance vocabulary.
        guests = json.loads(
            (ROOT / "_system" / "reference" / "podcasts" / "podcast_guest_registry.json")
            .read_text(encoding="utf-8"))
        known = {g["guest_id"] for g in guests["guests"]}
        for ch in self.channels:
            for gid in ch.get("guest_ids") or []:
                self.assertIn(gid, known, f"{ch['title']} references unknown guest {gid}")

    def test_dedupe_show_ids_exist_in_the_show_registry(self):
        shows = json.loads(
            (ROOT / "_system" / "reference" / "podcasts" / "show_registry.json")
            .read_text(encoding="utf-8"))
        known = {s["show_id"] for s in shows["shows"]}
        for ch in self.channels:
            sid = ch.get("dedupe_against_show_id")
            if sid:
                self.assertIn(sid, known, f"{ch['title']} references unknown show {sid}")

    def test_feed_evidence_is_recorded_not_assumed(self):
        # Every row must carry live probe results, so a dead channel is visible.
        for ch in self.channels:
            self.assertIn("feed_last_published", ch)
            self.assertIn("verified_at", ch)


class TitleNormalizationTests(unittest.TestCase):
    def test_punctuation_and_case_do_not_matter(self):
        self.assertEqual(
            normalize_title("Foo Bar | EP 12"), normalize_title("foo bar - ep. 12"))

    def test_episode_numbering_noise_is_stripped(self):
        self.assertEqual(normalize_title("Spotter [Business Breakdowns, EP. 78]"),
                         normalize_title("Spotter"))

    def test_distinct_titles_stay_distinct(self):
        self.assertNotEqual(normalize_title("The Synopsis"),
                            normalize_title("Best Action Movies 2022"))


class ChannelVerificationTests(unittest.TestCase):
    def test_related_names_agree(self):
        self.assertTrue(titles_agree("Capital Allocators",
                                     "Capital Allocators with Ted Seides"))

    def test_unrelated_names_disagree(self):
        self.assertFalse(titles_agree("Ben Graham Centre", "Benjamin Graham Value Insights"))


class FeedParsingTests(unittest.TestCase):
    def test_parses_entry_fields(self):
        rows = parse_channel_feed(MINIMAL_FEED, {"channel_id": "UC" + "x" * 22,
                                                 "title": "Test", "tier": "native",
                                                 "trust": "high"})
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["video_id"], "abc123XYZ_-")
        self.assertEqual(row["views"], 4210)
        self.assertEqual(row["url"], "https://www.youtube.com/watch?v=abc123XYZ_-")


class GateTests(unittest.TestCase):
    """The load-bearing contract: metadata defers, it never admits."""

    EMPTY = {"by_show": {}, "all": {}}

    def _video(self, title: str) -> dict:
        return {"video_id": "vid", "title": title, "description": ""}

    def test_a_clean_video_is_pending_not_admitted(self):
        v = screen(self._video("Sir Paul Marshall on market structure"), {}, self.EMPTY)
        self.assertEqual(v["gate"], "pending_transcript")

    def test_no_video_is_ever_admitted_on_metadata(self):
        for title in ["NVDA deep dive", "$NVDA TO $500", "Berkshire annual meeting"]:
            v = screen(self._video(title), {}, self.EMPTY)
            self.assertIn(v["gate"], {"pending_transcript", "rejected_metadata"})
            self.assertNotEqual(v["gate"], "admitted")

    def test_slop_title_flags_but_does_not_reject(self):
        # On a curated channel the registry is the precision mechanism; the
        # pattern is recorded for the future open-search lane, not enforced here.
        v = screen(self._video("NVDA PRICE PREDICTION - MUST BUY"), {}, self.EMPTY)
        self.assertIn("slop_title", v["flags"])
        self.assertEqual(v["gate"], "pending_transcript")

    def test_shorts_are_rejected(self):
        v = screen(self._video("Quick take on rates #shorts"), {}, self.EMPTY)
        self.assertEqual(v["gate"], "rejected_metadata")
        self.assertIn("short_form", v["reject_reasons"])

    def test_podcast_duplicate_is_rejected_via_show_index(self):
        index = {"by_show": {"chai_with_pabrai": {normalize_title("Chai with Pabrai EP 12"): "ep-12"}},
                 "all": {}}
        v = screen(self._video("Chai with Pabrai - Ep. 12"),
                   {"dedupe_against_show_id": "chai_with_pabrai"}, index)
        self.assertEqual(v["gate"], "rejected_metadata")
        self.assertEqual(v["duplicate_of_episode_id"], "ep-12")

    def test_reupload_of_another_show_is_caught_by_the_global_index(self):
        # A guest channel re-uploads other people's episodes too.
        index = {"by_show": {}, "all": {normalize_title("Spotter"): "spotter-123"}}
        v = screen(self._video("Spotter [Business Breakdowns, EP. 78]"), {}, index)
        self.assertIn("duplicate_of_podcast_episode", v["reject_reasons"])

    def test_unrelated_title_is_not_a_duplicate(self):
        index = {"by_show": {}, "all": {normalize_title("Spotter"): "spotter-123"}}
        v = screen(self._video("Larry Robbins pitches at Sohn"), {}, index)
        self.assertEqual(v["gate"], "pending_transcript")


class SlopPatternTests(unittest.TestCase):
    def test_patterns_match_pump_grammar(self):
        for title in ["NVDA Price Target 2027", "3 STOCKS TO BUY NOW",
                      "You MUST BUY this before it's too late"]:
            self.assertTrue(any(p.search(title) for p in SLOP_PATTERNS), title)

    def test_patterns_do_not_match_legitimate_titles(self):
        for title in ["Sir Paul Marshall: Why Markets Are Getting More Complex",
                      "Nintendo: The Switch 2 Edition w/ Ryan O'Connor",
                      "Tom Gayner VALUEx BRK 2026",
                      "The Nvidia of Physical AI: Inside Applied Intuition"]:
            self.assertFalse(any(p.search(title) for p in SLOP_PATTERNS), title)



class PlaylistRegistryTests(unittest.TestCase):
    """A channel can be off while a playlist inside it is on.

    Talks at Google and Columbia Business School were demoted to ingest=false on
    2026-09-01 on recorded evidence -- their last 15 uploads were Diary of a
    Wimpy Kid and MBA admissions webinars respectively. The fix is not to undo
    that demotion; it is to read the one playlist on each that carries the
    investing material.
    """

    def setUp(self) -> None:
        self.doc = json.loads(REG.read_text(encoding="utf-8"))
        self.channels = self.doc["channels"]
        self.by_title = {c["title"]: c for c in self.channels}

    def test_playlist_rows_are_well_formed(self):
        for ch in self.channels:
            for pl in ch.get("playlists") or []:
                for field in ("playlist_id", "title", "ingest", "trust",
                              "item_count", "verified_at", "notes"):
                    self.assertIn(field, pl, f"{ch['title']} playlist missing {field}")
                self.assertRegex(pl["playlist_id"], r"^PL[\w-]{16,}$")
                self.assertIn(pl["trust"], {"high", "broad"})
                self.assertGreater(pl["item_count"], 0)

    def test_playlist_ids_are_unique_across_the_registry(self):
        ids = [pl["playlist_id"] for c in self.channels for pl in c.get("playlists") or []]
        self.assertEqual(len(ids), len(set(ids)))

    def test_a_playlist_is_never_the_uploads_playlist(self):
        # UU<id> is the whole channel wearing a playlist costume. Ingesting it
        # would silently undo the demotion this mechanism exists to respect.
        for ch in self.channels:
            for pl in ch.get("playlists") or []:
                self.assertNotEqual(pl["playlist_id"], ch["uploads_playlist_id"])

    def test_the_demoted_channels_stay_demoted(self):
        for title in ("Talks at Google", "Columbia Business School"):
            self.assertFalse(
                self.by_title[title]["ingest"],
                f"{title} channel feed was re-enabled; the 2026-09-01 evidence "
                "says its uploads are not investing content",
            )

    def test_the_scoped_playlists_are_the_ones_enabled(self):
        on = {pl["title"] for c in self.channels
              for pl in c.get("playlists") or [] if pl["ingest"]}
        self.assertEqual(on, {"Investors at Google",
                              "Heilbrunn Center for Graham & Dodd Investing"})

    def test_heilbrunn_channel_has_nothing_to_ingest(self):
        # Checked live 2026-09-03: zero public playlists, one video from 2013.
        ch = self.by_title["HeilbrunnCenter"]
        self.assertFalse(ch["ingest"])
        self.assertEqual(ch.get("playlists"), [])


class PlaylistSourceTests(unittest.TestCase):
    CHANNEL = {
        "channel_id": "UCbmNph6atAoGfqLoCL_duAg",
        "title": "Talks at Google",
        "tier": "native",
        "trust": "broad",
        "ingest": False,
        "rate_limit_seconds": 1.0,
        "playlists": [
            {"playlist_id": "PLaaaaaaaaaaaaaaaaaaa", "title": "On", "ingest": True,
             "trust": "high", "item_count": 3},
            {"playlist_id": "PLbbbbbbbbbbbbbbbbbbb", "title": "Off", "ingest": False,
             "trust": "broad", "item_count": 9},
        ],
    }

    def test_only_enabled_playlists_become_sources(self):
        got = playlist_sources(self.CHANNEL)
        self.assertEqual([s["playlist_title"] for s in got], ["On"])
        self.assertEqual(got[0]["source_kind"], "playlist")

    def test_playlist_trust_overrides_the_channel(self):
        # The reason to scope to a playlist is that it beats its own channel.
        self.assertEqual(playlist_sources(self.CHANNEL)[0]["trust"], "high")

    def test_a_playlist_without_an_id_is_skipped(self):
        ch = {**self.CHANNEL, "playlists": [{"title": "x", "ingest": True}]}
        self.assertEqual(playlist_sources(ch), [])

    def test_channel_with_no_playlists_yields_none(self):
        self.assertEqual(playlist_sources({"title": "x"}), [])

    def test_registry_sources_reads_a_playlist_off_a_disabled_channel(self):
        doc = {"channels": [self.CHANNEL]}
        got = registry_sources(doc)
        # The channel feed is off, so the playlist is the only source.
        self.assertEqual([s["source_kind"] for s in got], ["playlist"])

    def test_registry_sources_emits_both_kinds_when_both_are_on(self):
        doc = {"channels": [{**self.CHANNEL, "ingest": True, "rss_url": "u"}]}
        self.assertEqual([s["source_kind"] for s in registry_sources(doc)],
                         ["channel_rss", "playlist"])

    def test_only_channel_filter_applies_to_playlists_too(self):
        doc = {"channels": [self.CHANNEL]}
        self.assertEqual(registry_sources(doc, only_channel="UCother"), [])
        self.assertEqual(
            len(registry_sources(doc, only_channel=self.CHANNEL["channel_id"])), 1)


class PlaylistFetchTests(unittest.TestCase):
    SOURCE = {
        "channel_id": "UCbmNph6atAoGfqLoCL_duAg",
        "title": "Talks at Google",
        "tier": "native",
        "trust": "broad",
        "source_kind": "playlist",
        "playlist_id": "PLaaaaaaaaaaaaaaaaaaa",
        "playlist_title": "Investors at Google",
    }
    ITEMS = [{
        "video_id": "abc123XYZ_-",
        "title": "  Howard Marks on cycles  ",
        "description": " A talk. ",
        "published": "2026-05-27T12:00:00Z",
        "channel_id": "UCbmNph6atAoGfqLoCL_duAg",
    }]

    def test_record_shape_matches_the_rss_path(self):
        with mock.patch.object(discover_videos.youtube_api, "playlist_items",
                               return_value=self.ITEMS):
            got = fetch_playlist(self.SOURCE)
        rss = parse_channel_feed(MINIMAL_FEED, {
            "channel_id": "c", "title": "t", "tier": "native", "trust": "high"})
        # Every key the downstream gate and backlog read must exist in both.
        missing = set(rss[0]) - set(got[0])
        self.assertFalse(missing, f"playlist record is missing {missing}")

    def test_fields_are_carried_and_trimmed(self):
        with mock.patch.object(discover_videos.youtube_api, "playlist_items",
                               return_value=self.ITEMS):
            v = fetch_playlist(self.SOURCE)[0]
        self.assertEqual(v["video_id"], "abc123XYZ_-")
        self.assertEqual(v["title"], "Howard Marks on cycles")
        self.assertEqual(v["url"], "https://www.youtube.com/watch?v=abc123XYZ_-")
        self.assertEqual(v["discovery"], "playlist")
        self.assertEqual(v["playlist_title"], "Investors at Google")
        self.assertEqual(v["channel_title"], "Talks at Google")

    def test_items_without_an_id_are_dropped(self):
        with mock.patch.object(discover_videos.youtube_api, "playlist_items",
                               return_value=[{"video_id": "", "title": "x"}]):
            self.assertEqual(fetch_playlist(self.SOURCE), [])

    def test_a_playlist_video_is_still_never_admitted_on_metadata(self):
        # The whole design: the source decides precision, the transcript decides
        # admission. Scoping to a playlist must not become a back door.
        with mock.patch.object(discover_videos.youtube_api, "playlist_items",
                               return_value=self.ITEMS):
            v = fetch_playlist(self.SOURCE)[0]
        screen(v, self.SOURCE, {"by_show": {}, "all": {}})
        self.assertEqual(v["gate"], "pending_transcript")

if __name__ == "__main__":
    unittest.main(verbosity=2)
