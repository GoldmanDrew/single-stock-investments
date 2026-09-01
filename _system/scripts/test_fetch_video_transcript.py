#!/usr/bin/env python3
"""Unit tests for the caption fetch lane: no audio path, quota discipline, gates."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "_system" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import youtube_api  # noqa: E402
import fetch_video_transcript as fvt  # noqa: E402

FETCHER_SRC = (SCRIPTS / "fetch_video_transcript.py").read_text(encoding="utf-8")
API_SRC = (SCRIPTS / "youtube_api.py").read_text(encoding="utf-8")


class NoAudioPathTests(unittest.TestCase):
    """The video lane fetches captions and nothing else.

    yt-dlp is installed on this host. The guard against audio download is that
    no call site may exist -- same shape as the reqGlobalCancel ban in the
    trading code, where the test IS the enforcement mechanism.
    """

    FORBIDDEN = [
        "yt_dlp", "yt-dlp", "youtube_dl", "bestaudio", "--extract-audio",
        "ffmpeg", "WhisperModel", "faster_whisper", "whisper_transcribe",
    ]

    def test_fetcher_has_no_audio_download_call_site(self):
        for token in self.FORBIDDEN:
            # The docstring names yt-dlp to explain the ban; code must not.
            code = "\n".join(
                line for line in FETCHER_SRC.splitlines()
                if not line.strip().startswith("#")
            )
            body = code.split('"""', 2)[-1] if code.count('"""') >= 2 else code
            self.assertNotIn(token, body, "audio path leaked into the fetcher: " + token)

    def test_no_audio_url_field_is_persisted(self):
        self.assertNotIn("audio_url", FETCHER_SRC)


class QuotaDisciplineTests(unittest.TestCase):
    def test_search_endpoint_is_refused(self):
        # 100 units per call would burn the free tier in 100 iterations.
        with self.assertRaises(youtube_api.YouTubeAPIError) as ctx:
            youtube_api.call("search", {"q": "value investing"})
        self.assertIn("search.list", str(ctx.exception))

    def test_unknown_endpoint_is_refused_rather_than_guessed(self):
        with self.assertRaises(youtube_api.YouTubeAPIError):
            youtube_api.call("subscriptions", {})

    def test_documented_costs_are_one_unit(self):
        for endpoint in ("videos", "playlistItems", "channels"):
            self.assertEqual(youtube_api.UNIT_COST[endpoint], 1)

    def test_free_tier_constant_matches_google(self):
        self.assertEqual(youtube_api.FREE_TIER_DAILY_UNITS, 10_000)

    def test_budget_leaves_headroom_under_free_tier(self):
        self.assertLess(youtube_api.DEFAULT_BUDGET, youtube_api.FREE_TIER_DAILY_UNITS)

    def test_api_source_contains_no_search_call(self):
        self.assertNotIn('call("search"', API_SRC)


class DurationParsingTests(unittest.TestCase):
    def test_parses_minutes_and_seconds(self):
        self.assertEqual(youtube_api.parse_duration("PT10M12S"), 612)

    def test_parses_hours(self):
        self.assertEqual(youtube_api.parse_duration("PT1H30M5S"), 5405)

    def test_parses_seconds_only(self):
        self.assertEqual(youtube_api.parse_duration("PT45S"), 45)

    def test_missing_duration_is_none_not_zero(self):
        # None must not be confused with a zero-length video by the gate.
        self.assertIsNone(youtube_api.parse_duration(None))
        self.assertIsNone(youtube_api.parse_duration("garbage"))


class QualityGateTests(unittest.TestCase):
    def test_a_real_sohn_pitch_passes(self):
        # Measured 2026-09-01: 10,359 chars over 612s. The podcast 25,000-byte
        # floor would have rejected this; that is why it does not transfer.
        self.assertEqual(fvt.quality_gate("x" * 10359, 612), [])

    def test_short_clip_is_rejected_on_duration(self):
        reasons = fvt.quality_gate("x" * 9000, 200)
        self.assertTrue(any(r.startswith("too_short_duration") for r in reasons))

    def test_thin_transcript_is_rejected_on_length(self):
        reasons = fvt.quality_gate("x" * 500, 3600)
        self.assertTrue(any(r.startswith("transcript_too_short") for r in reasons))

    def test_partial_caption_track_is_caught_by_coverage(self):
        # 7,000 chars across a 60-minute video is ~117 cpm: the track exists and
        # does not cover the video. Length alone would have passed it.
        reasons = fvt.quality_gate("x" * 7000, 3600)
        self.assertTrue(any(r.startswith("caption_coverage") for r in reasons))
        self.assertFalse(any(r.startswith("transcript_too_short") for r in reasons))

    def test_normal_speech_density_passes_coverage(self):
        # 45 minutes at ~800 chars/min.
        self.assertEqual(fvt.quality_gate("x" * 36000, 2700), [])

    def test_unknown_duration_still_checks_length(self):
        self.assertEqual(fvt.quality_gate("x" * 30000, None), [])
        self.assertTrue(fvt.quality_gate("x" * 100, None))


class PathAndSlugTests(unittest.TestCase):
    def test_slug_is_filesystem_safe(self):
        slug = fvt.slugify("Mohnish Pabrai's Interview: Value & Risk / 2026")
        self.assertRegex(slug, r"^[a-z0-9-]+$")

    def test_slug_survives_a_title_that_is_all_punctuation(self):
        self.assertEqual(fvt.slugify("!!!???"), "video")

    def test_unicode_title_does_not_crash_the_slug(self):
        # The U+2060 class of failure, at the filename layer this time.
        self.assertRegex(fvt.slugify("Chris Voss on “No”⁠-Oriented"), r"^[a-z0-9-]+$")


class GateProgressionTests(unittest.TestCase):
    def test_fetched_meta_is_not_yet_relevance_judged(self):
        # Phase 2 ends at transcript_fetched; admission is Phase 3's decision.
        self.assertIn('"gate": "transcript_fetched"', FETCHER_SRC)
        self.assertIn('"relevance": None', FETCHER_SRC)


class CorpusShapeTests(unittest.TestCase):
    """Read whatever this lane has actually written, if anything."""

    def setUp(self) -> None:
        from vault_paths import videos_root
        self.lib = videos_root() / "library"
        if not self.lib.is_dir():
            self.skipTest("no video corpus on this host yet")
        self.metas = list(self.lib.rglob("*.meta.json"))
        if not self.metas:
            self.skipTest("no video meta files yet")

    def test_every_transcript_has_a_meta(self):
        # One direction only. Meta is written first, so a meta without a
        # transcript is an interrupted run that the next pass retries; a
        # transcript without a meta would be a corpus we cannot describe.
        metas = {p.with_suffix("").with_suffix("") for p in self.metas}
        for txt in self.lib.rglob("*.txt"):
            self.assertIn(txt.with_suffix(""), metas, "orphan transcript: " + txt.name)

    def test_no_meta_records_an_audio_source(self):
        for m in self.metas:
            doc = json.loads(m.read_text(encoding="utf-8"))
            self.assertEqual(doc.get("transcript_source"), "youtube_captions")
            self.assertNotIn("audio_url", doc)

    def test_every_stored_transcript_passes_its_own_gate(self):
        for m in self.metas:
            doc = json.loads(m.read_text(encoding="utf-8"))
            reasons = fvt.quality_gate(
                "x" * int(doc.get("transcript_chars") or 0), doc.get("duration_seconds"))
            self.assertEqual(reasons, [], m.name + " stored despite " + str(reasons))


class TransientFailureTests(unittest.TestCase):
    """A rate limit must not be recorded as a bad video.

    The podcast lane buried 696 good episodes on 2026-08-20 by charging a DNS
    outage to each item's retry budget. IpBlocked is the same shape: YouTube
    returns it for every request once the IP is limited, so it says nothing
    about the video named in the call.
    """

    def test_rate_limit_is_classified_transient(self):
        for status in ["error:IpBlocked", "error:RequestBlocked", "error:TooManyRequests"]:
            self.assertTrue(fvt.is_transient(status), status)

    def test_a_real_video_failure_is_not_transient(self):
        for status in ["error:NoTranscriptFound", "error:VideoUnavailable", "no_captions"]:
            self.assertFalse(fvt.is_transient(status), status)

    def test_run_aborts_rather_than_marching_through_the_backlog(self):
        # Continuing past a rate limit converts one environmental failure into
        # a backlog of false ones.
        self.assertIn("aborted_on", FETCHER_SRC)
        self.assertIn("break", FETCHER_SRC)

    def test_attempts_are_only_spent_on_real_failures(self):
        self.assertIn("if not is_transient(result.get(\"status\", \"\")):", FETCHER_SRC)


class ThresholdCalibrationTests(unittest.TestCase):
    def test_a_seven_minute_sohn_pitch_survives(self):
        # "Ryan Packard pitches AppLovin at Sohn 2026" is 448s. An 8-minute
        # floor dropped it; that is why the floor is 300s.
        self.assertEqual(fvt.quality_gate("x" * 6000, 448), [])

    def test_char_floor_does_not_reimpose_a_duration_floor(self):
        # At a normal 800 chars/min a 6,000-char floor would silently require
        # 7.5 minutes. 4,000 keeps the real floor at ~5 minutes.
        self.assertLessEqual(fvt.MIN_TRANSCRIPT_CHARS / 800.0 * 60, fvt.MIN_DURATION_SECONDS + 1)


class PermanentFailureTests(unittest.TestCase):
    """Some failures never resolve by waiting; retrying them wastes a paced slot."""

    def test_age_restriction_is_permanent(self):
        self.assertTrue(fvt.is_permanent("error:AgeRestricted"))

    def test_permanent_and_transient_are_disjoint(self):
        for marker in fvt.PERMANENT_ERROR_MARKERS:
            self.assertFalse(fvt.is_transient("error:" + marker), marker)
        for marker in fvt.TRANSIENT_ERROR_MARKERS:
            self.assertFalse(fvt.is_permanent("error:" + marker), marker)

    def test_a_missing_transcript_is_neither(self):
        self.assertFalse(fvt.is_permanent("no_captions"))
        self.assertFalse(fvt.is_transient("no_captions"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
