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

from discover_videos import (  # noqa: E402
    SLOP_PATTERNS, normalize_title, parse_channel_feed, screen,
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
