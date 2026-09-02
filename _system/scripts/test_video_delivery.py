from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))

import build_dashboard_shards as shards  # noqa: E402
import build_video_insights as video_insights  # noqa: E402
import video_whisper_backfill as whisper  # noqa: E402


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


class VideoWhisperFallbackTests(unittest.TestCase):
    def test_no_caption_items_are_queued_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_json(
                root / "caption_backlog.json",
                {
                    "items": {
                        "abc123": {
                            "status": "no_captions",
                            "title": "A single-stock pitch",
                            "published": "2026-09-01T12:00:00Z",
                            "url": "https://www.youtube.com/watch?v=abc123",
                        },
                        "already": {"status": "done"},
                    }
                },
            )
            with mock.patch.object(whisper, "videos_root", return_value=root):
                first = whisper.queue_no_caption_videos()
                second = whisper.queue_no_caption_videos()
                backlog = json.loads((root / "whisper_backlog.json").read_text(encoding="utf-8"))

            self.assertEqual(first["queued"], 1)
            self.assertEqual(second["queued"], 0)
            self.assertEqual(backlog["pending_count"], 1)
            self.assertEqual([row["video_id"] for row in backlog["items"]], ["abc123"])

    def test_sparse_caption_state_is_hydrated_from_discovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_json(root / "caption_backlog.json", {
                "items": {"abc123": {"status": "no_captions", "detail": "TranscriptsDisabled"}}
            })
            _write_json(root / "discovery_latest.json", {
                "videos": [{
                    "video_id": "abc123",
                    "title": "The real title",
                    "channel_id": "UC1",
                    "channel_title": "Research Channel",
                    "published": "2026-09-01T12:00:00Z",
                    "duration_seconds": 900,
                }]
            })
            with mock.patch.object(whisper, "videos_root", return_value=root):
                whisper.queue_no_caption_videos()
                row = json.loads(
                    (root / "whisper_backlog.json").read_text(encoding="utf-8")
                )["items"][0]

            self.assertEqual(row["title"], "The real title")
            self.assertEqual(row["channel_title"], "Research Channel")

    def test_finalized_whisper_transcript_enters_the_normal_relevance_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            item = {
                "video_id": "abc123",
                "title": "A durable compounder",
                "published": "2026-09-01T12:00:00Z",
                "channel_id": "UC1",
                "channel_title": "Research Channel",
                "url": "https://www.youtube.com/watch?v=abc123",
                "duration_seconds": 600,
            }
            with mock.patch.object(whisper, "videos_root", return_value=root):
                result = whisper.finalize_transcript(item, "company analysis " * 800)

            self.assertEqual(result["status"], "transcribed")
            meta = json.loads(Path(result["meta_path"]).read_text(encoding="utf-8"))
            self.assertEqual(meta["transcript_source"], "local_whisper")
            self.assertEqual(meta["gate"], "transcript_fetched")
            self.assertIsNone(meta["relevance"])
            self.assertFalse(Path(meta["transcript_path"]).is_absolute())


class VideoCatalogTests(unittest.TestCase):
    def _write_video(self, root: Path, video_id: str, gate: str, title: str) -> None:
        year = root / "library" / "2026"
        year.mkdir(parents=True, exist_ok=True)
        text_path = year / f"{title}-{video_id}.txt"
        text_path.write_text("Investment thesis and evidence. " * 40, encoding="utf-8")
        _write_json(
            year / f"{title}-{video_id}.meta.json",
            {
                "video_id": video_id,
                "title": title.replace("-", " ").title(),
                "channel_id": "UC1",
                "channel_title": "Research Channel",
                "published": "2026-09-01T12:00:00Z",
                "duration_seconds": 900,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "gate": gate,
                "relevance": {
                    "routes": ["sustained_company_1"],
                    "sustained_tickers": [{"ticker": "ABC", "mentions": 8}],
                    "people": [{"guest_id": "investor-one", "mentions": 3}],
                },
                "transcript_path": str(text_path),
                "transcript_source": "youtube_captions",
            },
        )

    def test_catalog_is_admitted_only_and_uses_stable_refs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_video(root, "keep", "admitted", "keep-video")
            self._write_video(root, "drop", "rejected_relevance", "drop-video")
            catalog = video_insights.build_catalog(root)

            self.assertEqual(catalog["video_count"], 1)
            self.assertEqual([row["video_id"] for row in catalog["video_index"]], ["keep"])
            row = catalog["video_index"][0]
            self.assertEqual(row["tickers"], ["ABC"])
            self.assertTrue(row["source_document"].startswith("_system/reference/video/"))
            self.assertNotIn(str(root), json.dumps(catalog))

    def test_video_catalog_has_its_own_lazy_dashboard_shard(self):
        self.assertEqual(shards.INSIGHTS_SHARDS["videos"], ("video_index", "video_by_channel"))


class VideoWorkflowContractTests(unittest.TestCase):
    def test_scheduled_lane_is_local_and_conflict_safe(self):
        workflow = ROOT / ".github" / "workflows" / "youtube-refresh.yml"
        text = workflow.read_text(encoding="utf-8")
        self.assertIn("schedule:", text)
        self.assertIn("self-hosted", text)
        self.assertIn("commit-vault", text)
        self.assertIn('git_add: "videos"', text)
        self.assertNotIn("CAPTION_MAX_PER_DAY: 480", text)

    def test_dashboard_routes_and_lazy_loads_the_video_lane(self):
        html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
        viz = (ROOT / "dashboard" / "insights-viz.js").read_text(encoding="utf-8")
        css = (ROOT / "dashboard" / "insights-events.css").read_text(encoding="utf-8")
        self.assertIn("letters|podcasts|videos|inflections", html)
        self.assertIn("videos: ['videos']", html)
        self.assertIn("renderVideoIndex", viz)
        self.assertIn("Transcript-gated video research", viz)
        self.assertIn(".video-screening-tape", css)


if __name__ == "__main__":
    unittest.main(verbosity=2)
