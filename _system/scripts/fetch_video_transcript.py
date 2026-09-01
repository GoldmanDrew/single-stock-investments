#!/usr/bin/env python3
"""Fetch published captions for discovered videos. Captions only -- never audio.

Phase 2 of the video lane. The podcast pipeline tries a published transcript
first and falls back to Whisper on the audio; this one has no fallback and that
is deliberate. Audio download was ruled out, so a video without captions is
dropped rather than transcribed. That single constraint removes the ToS
question, removes the 30-minutes-of-CPU-per-item cost that has the podcast
analysis queue 29 days deep, and keeps this job cheap enough to run beside the
Whisper backfill without competing with it.

**No audio path exists here, and a test enforces that.** `yt-dlp` is installed on
this box and would happily fetch a stream; the guard is that no call site may
exist, in the same spirit as the `reqGlobalCancel` ban in the trading code.

Three mechanical gates, applied before a video is admitted to the corpus. None
of them is a *relevance* judgement -- that is the transcript gate, and it comes
next:

  * **Duration.** Under the floor it is a clip or a trailer.
  * **Length.** A transcript too short to contain an argument.
  * **Coverage.** chars-per-minute below the floor means the caption track does
    not actually cover the video -- a partial track, a music segment, or an
    intro-only caption. This is the video analogue of the podcast corpus finding
    that 97% of what looked like transcripts were MP3s wearing a .txt extension:
    the file existed and was the wrong thing, and only reading the content said so.

The 25,000-byte podcast floor deliberately does NOT transfer. A 10-minute Sohn
pitch measured 10,359 characters on 2026-09-01 -- a genuine single-name pitch
that the podcast threshold would have thrown away. Podcast episodes run 45-90
minutes; conference pitches are short and dense.

    python _system/scripts/fetch_video_transcript.py --limit 10
    python _system/scripts/fetch_video_transcript.py --video QoDbkHOsslg
    python _system/scripts/fetch_video_transcript.py --report
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

# Video titles carry whatever the uploader typed. A U+2060 WORD JOINER in a
# podcast title killed an analysis run on 2026-08-29 because Python picks cp1252
# for a redirected stdout on Windows: the line reporting success was the crash.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import caption_rate_limit as rate  # noqa: E402
import youtube_api  # noqa: E402
from vault_paths import videos_root  # noqa: E402

BACKLOG_NAME = "caption_backlog.json"

# Deliberately permissive. An 8-minute floor was tried first and dropped "Ryan
# Packard pitches AppLovin at Sohn 2026" at 7:28 -- a genuine single-name pitch,
# the exact thing this lane exists to collect. The junk it was aimed at (RV
# Capital's "Holiday 2021" cards, marketing shorts) is not distinguishable from a
# short pitch by *duration*; it is distinguishable by content, and content is the
# relevance gate's job. So this floor only removes what no transcript could
# rescue, and the corpus carries a few Christmas greetings until Phase 3 runs.
MIN_DURATION_SECONDS = int(os.environ.get("VIDEO_MIN_DURATION", "300"))
# ~5 minutes of ordinary speech. Not the podcast 25,000 -- see the module
# docstring -- and not 6,000 either: at a normal 800 chars/minute that would
# reimpose a 7.5-minute floor through the back door and lose the same pitches.
MIN_TRANSCRIPT_CHARS = int(os.environ.get("VIDEO_MIN_CHARS", "4000"))
# Ordinary speech runs 700-1,000 chars/minute. Below 350 the track is not
# covering the video, whatever its length says.
MIN_CHARS_PER_MINUTE = int(os.environ.get("VIDEO_MIN_CPM", "350"))
# Give up on an item after this many distinct failures rather than retrying it
# forever; one dead video must not consume the run. Mirrors the whisper backlog.
MAX_ATTEMPTS = 4

# Failures that say nothing about the video, only about the moment. YouTube
# rate-limits caption fetches by IP and returns IpBlocked for every subsequent
# request regardless of which video it names, so counting these against an
# item's retry budget buries good videos for an environmental reason.
#
# The podcast lane learned this exact lesson the expensive way: DNS failures
# resolve in milliseconds, so a brief outage burned each item's whole retry
# budget in under a second and marked 696 perfectly good episodes permanently
# failed on 2026-08-20. Same failure mode, same fix -- attempts are not
# incremented, and the run stops rather than marching through the backlog
# converting a rate limit into hundreds of parked items.
TRANSIENT_ERROR_MARKERS = (
    "IpBlocked",
    "RequestBlocked",
    "TooManyRequests",
    "YouTubeRequestFailed",
    "URLError",
    "TimeoutError",
    "RemoteDisconnected",
    "ConnectionResetError",
)

# The mirror image of the transient set: conditions that will never resolve by
# waiting. An age-restricted video needs an authenticated session this lane does
# not have and will not grow, so retrying it four times is four wasted slots out
# of a deliberately small hourly budget.
PERMANENT_ERROR_MARKERS = (
    "AgeRestricted",
    "VideoUnavailable",
    "VideoUnplayable",
    "NotTranslatable",
    "InvalidVideoId",
)

PREFERRED_LANGS = ["en", "en-US", "en-GB"]


def is_transient(status: str) -> bool:
    return any(marker in (status or "") for marker in TRANSIENT_ERROR_MARKERS)


def is_permanent(status: str) -> bool:
    return any(marker in (status or "") for marker in PERMANENT_ERROR_MARKERS)


def _dt_now() -> datetime:
    return datetime.now(timezone.utc)


def now_stamp() -> str:
    return _dt_now().strftime("%Y-%m-%dT%H:%M:%SZ")


def slugify(text: str, limit: int = 48) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return (slug[:limit].rstrip("-")) or "video"


def video_paths(video_id: str, title: str, published: str | None) -> tuple[Path, Path]:
    """<videos>/library/<year>/<slug>-<video_id>.txt and .meta.json.

    The video id is the unique key and always present; the slug is there so the
    directory can be read by a human, exactly as the podcast corpus does.
    """
    year = (published or "")[:4]
    if not re.match(r"^\d{4}$", year):
        year = datetime.now(timezone.utc).strftime("%Y")
    out = videos_root(create=True) / "library" / year
    out.mkdir(parents=True, exist_ok=True)
    stem = slugify(title) + "-" + video_id
    return out / (stem + ".txt"), out / (stem + ".meta.json")


def backlog_path() -> Path:
    return videos_root(create=True) / BACKLOG_NAME


def load_backlog() -> dict:
    path = backlog_path()
    if not path.exists():
        return {"items": {}}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {"items": {}}
    except json.JSONDecodeError:
        return {"items": {}}


def save_backlog(doc: dict) -> None:
    doc["updated_at"] = now_stamp()
    items = doc.get("items") or {}
    doc["pending_count"] = sum(1 for v in items.values() if v.get("status") == "pending")
    tmp = backlog_path().with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(backlog_path())


def fetch_captions(video_id: str) -> dict:
    """Published captions only. Manual preferred over auto-generated.

    Returns {status, text, language, is_generated, track_count}. `status` is
    'ok', 'no_captions', or 'error:<Type>'.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return {"status": "error:MissingDependency",
                "detail": "pip install youtube-transcript-api"}

    api = YouTubeTranscriptApi()
    try:
        listing = list(api.list(video_id))
    except Exception as exc:  # noqa: BLE001 - library raises many shapes
        name = type(exc).__name__
        if "NoTranscript" in name or "TranscriptsDisabled" in name:
            return {"status": "no_captions", "detail": name}
        return {"status": "error:" + name, "detail": str(exc)[:200]}

    if not listing:
        return {"status": "no_captions", "detail": "empty track list"}

    # A human-written track is materially better for quote verification, which
    # the analysis stage depends on -- auto captions have no punctuation to
    # anchor a quote against.
    manual = [t for t in listing if not t.is_generated]
    ordered = manual + [t for t in listing if t.is_generated]
    english = [t for t in ordered if (t.language_code or "").lower().startswith("en")]
    chosen = english or ordered

    try:
        fetched = api.fetch(video_id, languages=[t.language_code for t in chosen])
    except Exception as exc:  # noqa: BLE001
        return {"status": "error:" + type(exc).__name__, "detail": str(exc)[:200]}

    text = " ".join((s.text or "").strip() for s in fetched)
    text = re.sub(r"\s+", " ", text).strip()
    return {
        "status": "ok" if text else "no_captions",
        "text": text,
        "language": getattr(fetched, "language_code", None),
        "is_generated": bool(getattr(fetched, "is_generated", True)),
        "track_count": len(listing),
        "manual_available": bool(manual),
    }


def quality_gate(text: str, duration_seconds: int | None) -> list[str]:
    """Mechanical rejects only. Relevance is decided later, on this same text."""
    reasons: list[str] = []
    chars = len(text or "")
    if duration_seconds is not None and duration_seconds < MIN_DURATION_SECONDS:
        reasons.append("too_short_duration_{0}s".format(duration_seconds))
    if chars < MIN_TRANSCRIPT_CHARS:
        reasons.append("transcript_too_short_{0}c".format(chars))
    if duration_seconds and duration_seconds >= 60:
        cpm = chars / (duration_seconds / 60.0)
        if cpm < MIN_CHARS_PER_MINUTE:
            # The track exists but does not cover the video.
            reasons.append("caption_coverage_{0:.0f}cpm".format(cpm))
    return reasons


def load_pending(limit: int | None, only_video: str | None) -> list[dict]:
    disc = videos_root() / "discovery_latest.json"
    if not disc.exists():
        raise SystemExit("no discovery_latest.json -- run discover_videos.py first")
    doc = json.loads(disc.read_text(encoding="utf-8"))
    rows = [v for v in doc.get("videos") or [] if v.get("gate") == "pending_transcript"]
    if only_video:
        rows = [v for v in rows if v.get("video_id") == only_video]
    return rows[:limit] if limit else rows


def run(*, limit: int | None = None, only_video: str | None = None,
        refetch: bool = False, sleep_seconds: float = 1.0,
        wait_for_slot: bool = False) -> dict:
    rows = load_pending(limit, only_video)
    if not rows:
        return {"considered": 0, "note": "nothing pending"}

    backlog = load_backlog()
    items = backlog.setdefault("items", {})

    # One API call per 50 videos buys the duration that RSS does not carry.
    meta_by_id: dict[str, dict] = {}
    try:
        meta_by_id = youtube_api.videos([r["video_id"] for r in rows])
    except youtube_api.YouTubeAPIError as exc:
        print("api unavailable ({0}); proceeding without duration".format(exc), flush=True)

    stats = {"considered": len(rows), "fetched": 0, "no_captions": 0,
             "rejected_quality": 0, "skipped_existing": 0, "errors": 0, "parked": 0}

    for row in rows:
        vid = row["video_id"]
        state = items.setdefault(vid, {"attempts": 0, "status": "pending"})
        if state.get("status") == "parked":
            stats["parked"] += 1
            continue

        txt_path, meta_path = video_paths(vid, row.get("title") or "", row.get("published"))
        # Both files, not just one. A run killed between the two writes leaves a
        # meta with no transcript; requiring both makes that state self-healing
        # rather than a permanent skip over a video we never actually stored.
        if txt_path.exists() and meta_path.exists() and not refetch:
            stats["skipped_existing"] += 1
            state["status"] = "done"
            continue

        api_item = meta_by_id.get(vid) or {}
        duration = youtube_api.parse_duration(
            (api_item.get("contentDetails") or {}).get("duration"))

        # Cheapest possible reject: a short video never needs a caption fetch.
        if duration is not None and duration < MIN_DURATION_SECONDS:
            state.update({"status": "rejected", "reasons": ["too_short_duration"],
                          "checked_at": now_stamp()})
            stats["rejected_quality"] += 1
            print("skip  {0} {1}s  {2}".format(vid, duration, (row.get("title") or "")[:44]),
                  flush=True)
            continue

        # Pacing is checked immediately before the network call, never at the
        # top of the loop: skips and duration rejects cost nothing and must not
        # consume a slot. In batch mode an exhausted budget ends the run; in
        # daemon mode it waits, which is the whole point of running a daemon.
        decision = rate.check()
        while not decision["allowed"]:
            if not wait_for_slot:
                stats["stopped_on"] = "rate_budget:" + decision["reason"]
                print("hold  {0}  {1}, {2}s -- {3} left for the next run".format(
                    vid, decision["reason"], decision["wait_seconds"],
                    len(rows) - rows.index(row)), flush=True)
                save_backlog(backlog)
                return stats
            nap = min(decision["wait_seconds"], 300)
            print("wait  {0}s ({1})".format(nap, decision["reason"]), flush=True)
            time.sleep(nap)
            decision = rate.check()

        rate.record_fetch()
        result = fetch_captions(vid)
        state["last_attempt_at"] = now_stamp()
        if not is_transient(result.get("status", "")):
            # A transient failure is not this video's fault; see
            # TRANSIENT_ERROR_MARKERS. Only real failures spend retry budget.
            state["attempts"] = int(state.get("attempts", 0)) + 1

        if result["status"] == "no_captions":
            # The request itself succeeded, so the IP is evidently not blocked;
            # that is as much evidence of health as a transcript would be.
            rate.record_success()
            # No fallback by design: audio transcription is not part of this lane.
            state.update({"status": "no_captions", "detail": result.get("detail")})
            stats["no_captions"] += 1
            print("none  {0}  {1}".format(vid, (row.get("title") or "")[:50]), flush=True)
            time.sleep(sleep_seconds)
            continue

        if result["status"].startswith("error"):
            state["last_error"] = result["status"]
            stats["errors"] += 1
            if is_transient(result["status"]):
                # Persist the backoff before doing anything else: a restart must
                # not read as "we waited". Then stop -- once the IP is limited
                # every remaining item fails identically, and continuing would
                # convert one rate limit into a backlog of false failures.
                blocked = rate.record_block()
                state["status"] = "pending"
                stats["aborted_on"] = result["status"]
                print("stop  {0}  {1} -- backing off until {2}, {3} left".format(
                    vid, result["status"], blocked.get("blocked_until"),
                    len(rows) - rows.index(row) - 1), flush=True)
                break
            if is_permanent(result["status"]):
                state["status"] = "parked"
            else:
                state["status"] = ("parked" if state["attempts"] >= MAX_ATTEMPTS
                                   else "pending")
            print("err   {0}  {1}  ({2})".format(vid, result["status"],
                                                 state["status"]), flush=True)
            time.sleep(sleep_seconds)
            continue

        rate.record_success()
        text = result.get("text") or ""
        reasons = quality_gate(text, duration)
        if reasons:
            state.update({"status": "rejected", "reasons": reasons, "checked_at": now_stamp()})
            stats["rejected_quality"] += 1
            print("drop  {0}  {1}  {2}".format(vid, ",".join(reasons),
                                               (row.get("title") or "")[:36]), flush=True)
            time.sleep(sleep_seconds)
            continue

        snippet = api_item.get("snippet") or {}
        meta = {
            "video_id": vid,
            "url": row.get("url"),
            "title": row.get("title"),
            "channel_id": row.get("channel_id"),
            "channel_title": row.get("channel_title"),
            "tier": row.get("tier"),
            "trust": row.get("trust"),
            "published": row.get("published"),
            "description": snippet.get("description") or row.get("description"),
            "duration_seconds": duration,
            "views": row.get("views"),
            "caption_language": result.get("language"),
            "caption_is_generated": result.get("is_generated"),
            "caption_manual_available": result.get("manual_available"),
            "caption_track_count": result.get("track_count"),
            "transcript_chars": len(text),
            "chars_per_minute": round(len(text) / (duration / 60.0), 1) if duration else None,
            "transcript_source": "youtube_captions",
            "transcript_path": str(txt_path),
            "resolve_preview": row.get("resolve_preview"),
            # Set by the Phase 3 transcript gate, which has not run yet.
            "relevance": None,
            "gate": "transcript_fetched",
            "fetched_at": now_stamp(),
        }
        # Meta first, transcript second. The invariant worth holding is "every
        # transcript has a meta describing it". The reverse orphan is harmless:
        # the skip check requires both, so the next run simply retries it.
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")
        txt_path.write_text(text + "\n", encoding="utf-8")
        state.update({"status": "done", "chars": len(text)})
        stats["fetched"] += 1
        kind = "auto" if result.get("is_generated") else "MANUAL"
        print("ok    {0}  {1:>6}c  {2:>4}s  {3:6s} {4}".format(
            vid, len(text), duration or 0, kind, (row.get("title") or "")[:38]), flush=True)
        time.sleep(sleep_seconds)

    save_backlog(backlog)
    return stats


def daemon(*, max_hours: float | None = None, sleep_seconds: float = 1.0) -> dict:
    """Drain the backlog across as many passes as the pacing budget allows.

    A single pass ends when it hits a block, because every further item would
    fail identically. The daemon exists so that ending a pass is not the same as
    giving up: it waits out the persisted backoff and starts another. This is the
    whisper backfill's `--until-empty` shape, with the budget rather than the CPU
    as the thing being yielded to.
    """
    started = _dt_now()
    totals = {"passes": 0, "fetched": 0, "no_captions": 0, "rejected_quality": 0,
              "errors": 0, "blocks": 0}
    while True:
        if max_hours is not None:
            elapsed = (_dt_now() - started).total_seconds() / 3600.0
            if elapsed >= max_hours:
                totals["stopped"] = "max_hours"
                return totals

        stats = run(sleep_seconds=sleep_seconds, wait_for_slot=True)
        totals["passes"] += 1
        for key in ("fetched", "no_captions", "rejected_quality", "errors"):
            totals[key] += int(stats.get(key) or 0)
        if stats.get("aborted_on"):
            totals["blocks"] += 1

        remaining = sum(1 for v in (load_backlog().get("items") or {}).values()
                        if v.get("status") == "pending")
        print("[pass {0}] fetched={1} remaining_pending={2}".format(
            totals["passes"], stats.get("fetched"), remaining), flush=True)
        if remaining == 0 and not stats.get("aborted_on"):
            totals["stopped"] = "backlog_empty"
            return totals

        # The next pass will block on the pacing check anyway; sleeping here
        # keeps the log from filling with wait lines.
        decision = rate.check()
        if not decision["allowed"]:
            nap = min(decision["wait_seconds"], 900)
            print("idle  {0}s ({1})".format(nap, decision["reason"]), flush=True)
            time.sleep(nap)


def report() -> int:
    backlog = load_backlog()
    items = backlog.get("items") or {}
    by_status: dict[str, int] = {}
    for state in items.values():
        by_status[state.get("status", "?")] = by_status.get(state.get("status", "?"), 0) + 1
    lib = videos_root() / "library"
    txts = list(lib.rglob("*.txt")) if lib.is_dir() else []
    chars = sum(p.stat().st_size for p in txts)
    print(json.dumps({
        "backlog_items": len(items),
        "by_status": by_status,
        "transcripts_on_disk": len(txts),
        "total_chars": chars,
        "quota_spent_today": youtube_api.spent_today(),
    }, indent=2))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--limit", type=int, default=None, help="Only process this many videos")
    p.add_argument("--video", default=None, help="Only this video id")
    p.add_argument("--refetch", action="store_true", help="Re-fetch even if a transcript exists")
    p.add_argument("--sleep", type=float, default=1.0, help="Seconds between caption fetches")
    p.add_argument("--report", action="store_true", help="Summarise corpus and backlog")
    p.add_argument("--daemon", action="store_true",
                   help="Wait for a pacing slot instead of stopping. Safe to leave running.")
    p.add_argument("--rate-status", action="store_true", help="Show pacing state and exit")
    p.add_argument("--hours", type=float, default=None,
                   help="With --daemon, stop after this many hours")
    args = p.parse_args()

    if args.rate_status:
        print(json.dumps(rate.status(), indent=2))
        return 0
    if args.report:
        return report()

    if args.daemon:
        stats = daemon(max_hours=args.hours, sleep_seconds=args.sleep)
    else:
        stats = run(limit=args.limit, only_video=args.video, refetch=args.refetch,
                    sleep_seconds=args.sleep, wait_for_slot=False)
    print("\n" + json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
