#!/usr/bin/env python3
"""Discover YouTube videos from the channel registry. Metadata never admits a video.

The video analogue of discover_podcasts.py, with one deliberate difference that
is the whole point of the design.

**Podcasts must judge relevance from metadata; video must not.** On the podcast
side, deciding before transcription is forced: Whisper costs ~30 minutes of CPU
per episode, so `select_relevant` reads titles and show notes and commits. That
works there because podcast titles are descriptive and the 16-show registry is
curated.

YouTube titles are SEO artifacts. A ticker in a YouTube title is *anti*-correlated
with substance -- "$NVDA TO $500" is the house style of exactly the channels we
do not want. Porting the podcast title heuristic would import its worst case as
the common case. And we do not have to: captions are already published for most
videos and cost one cheap HTTP fetch, so relevance can be decided on what was
actually *said*.

So this module resolves entities and records what it found, then marks every
video `pending_transcript`. It admits nothing. The admission decision belongs to
the transcript gate, and the only rejections made here are mechanical ones that
no transcript could rescue -- a Short, a missing id, a video already in the
podcast corpus.

Precision comes from the registry, not from this file. Filtering is the backstop.

    python _system/scripts/discover_videos.py
    python _system/scripts/discover_videos.py --channel UCq4ajL72ndl4yPxyzSMLeMg
    python _system/scripts/discover_videos.py --no-dedupe --no-write
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

# Video and channel titles carry whatever the uploader typed. A U+2060 WORD
# JOINER in a podcast title killed an entire analysis run on 2026-08-29 because
# Python picks cp1252 for a redirected stdout on Windows -- the line that
# *reports* success is the line that crashes. Same idiom as the podcast scripts.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from resolve_podcast_entities import PodcastEntityResolver  # noqa: E402
from vault_paths import podcasts_root, videos_root  # noqa: E402

VIDEO_CFG = ROOT / "_system" / "reference" / "video"
CHANNEL_REG = VIDEO_CFG / "channel_registry.json"

ATOM = {
    "a": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}

# Retail-pump title grammar. Not used to reject on a curated channel -- the
# registry already did that work -- but recorded, so that when the open-search
# lane lands there is a calibrated pattern set rather than a guess.
SLOP_PATTERNS = [
    re.compile(r"\bprice\s+(target|prediction)\b", re.I),
    re.compile(r"\b(must|should)\s+(buy|sell)\b", re.I),
    re.compile(r"\bstocks?\s+to\s+buy\s+(now|today)\b", re.I),
    re.compile(r"\b(before|by)\s+it'?s\s+too\s+late\b", re.I),
    re.compile(r"\b\d+\s*%\s*(gain|return)s?\s+(guaranteed|incoming)\b", re.I),
    re.compile(r"[\U0001F680\U0001F4C8\U0001F911]"),  # rocket / chart-up / money-face
]


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def user_agent() -> str:
    return load_json(CHANNEL_REG).get("user_agent") or "SSI-VideoAgent/1.0 (+research)"


def http_get(url: str, timeout: int = 45) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": user_agent()})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def normalize_title(text: str) -> str:
    """Fold a title for duplicate comparison across podcast and video versions.

    The same episode is titled 'Foo Bar | EP 12' on the feed and 'Foo Bar - EP.
    12' on YouTube, so punctuation and case cannot participate. Episode-number
    noise is stripped for the same reason.
    """
    t = (text or "").lower()
    t = re.sub(r"\[(.*?)\]|\((.*?)\)", " ", t)
    t = re.sub(r"\bep\.?\s*\d+\b|\bepisode\s*\d+\b|\b#\d+\b", " ", t)
    return re.sub(r"[^a-z0-9]+", "", t)


def parse_channel_feed(xml_bytes: bytes, channel: dict) -> list[dict]:
    """Atom -> video records. The feed holds at most 15 entries and has no duration."""
    doc = ET.fromstring(xml_bytes)
    out: list[dict] = []
    for e in doc.findall("a:entry", ATOM):
        vid = e.findtext("yt:videoId", default="", namespaces=ATOM).strip()
        if not vid:
            continue
        group = e.find("media:group", ATOM)
        desc = ""
        views = None
        if group is not None:
            desc = (group.findtext("media:description", default="", namespaces=ATOM) or "").strip()
            stats = group.find("media:community/media:statistics", ATOM)
            if stats is not None:
                try:
                    views = int(stats.get("views") or 0)
                except ValueError:
                    views = None
        out.append({
            "video_id": vid,
            "url": "https://www.youtube.com/watch?v=" + vid,
            "channel_id": channel.get("channel_id"),
            "channel_title": channel.get("title"),
            "tier": channel.get("tier"),
            "trust": channel.get("trust"),
            "title": (e.findtext("a:title", default="", namespaces=ATOM) or "").strip(),
            "description": desc,
            "published": (e.findtext("a:published", default="", namespaces=ATOM) or "").strip(),
            "views": views,
            "discovery": "channel_rss",
        })
    return out


def build_podcast_title_index() -> dict:
    """Normalized episode titles already in the podcast corpus, by show and overall.

    Costs ~3.4s over 3,750 meta files, which is cheap next to one feed fetch and
    avoids a cache that could go stale against a corpus that is still growing.
    """
    by_show: dict[str, dict] = {}
    everything: dict[str, str] = {}
    root = podcasts_root()
    if not root.is_dir():
        return {"by_show": by_show, "all": everything}
    for meta in root.rglob("*.meta.json"):
        try:
            doc = json.loads(meta.read_text(encoding="utf-8", errors="replace"))
        except (json.JSONDecodeError, OSError):
            continue
        title = doc.get("title")
        if not title:
            continue
        key = normalize_title(title)
        if not key:
            continue
        episode_id = doc.get("episode_id") or meta.stem
        everything[key] = episode_id
        by_show.setdefault(doc.get("show_id") or "?", {})[key] = episode_id
    return {"by_show": by_show, "all": everything}


def screen(video: dict, channel: dict, index: dict) -> dict:
    """Mechanical rejects and advisory flags. Never an admission.

    Only failures a transcript could not overturn are rejections: a Short has no
    substance to find, and a video already transcribed as a podcast episode is
    work we have done. Everything else is recorded and deferred.
    """
    rejects: list[str] = []
    flags: list[str] = []

    if not video.get("video_id"):
        rejects.append("no_video_id")

    # Registry says this channel mirrors a show we already ingest; check the
    # specific show first, then the whole corpus -- a guest re-uploads other
    # people's episodes too, and those are just as duplicated.
    dupe_show = channel.get("dedupe_against_show_id")
    key = normalize_title(video.get("title") or "")
    hit = None
    if key:
        if dupe_show:
            hit = (index.get("by_show", {}).get(dupe_show) or {}).get(key)
        if not hit:
            hit = index.get("all", {}).get(key)
    if hit:
        rejects.append("duplicate_of_podcast_episode")
        video["duplicate_of_episode_id"] = hit

    title = video.get("title") or ""
    for pat in SLOP_PATTERNS:
        if pat.search(title):
            flags.append("slop_title")
            break

    # No duration in the Atom feed. Shorts are still detectable by convention:
    # they are almost always titled with the #shorts tag.
    if re.search(r"#shorts?\b", title, re.I):
        rejects.append("short_form")

    video["reject_reasons"] = rejects
    video["flags"] = flags
    # The load-bearing line: metadata defers, it does not admit.
    video["gate"] = "rejected_metadata" if rejects else "pending_transcript"
    return video


def discover(*, only_channel: str | None = None, dedupe: bool = True,
             write: bool = True) -> dict:
    doc = load_json(CHANNEL_REG)
    channels = [c for c in (doc.get("channels") or []) if c.get("ingest")]
    if only_channel:
        channels = [c for c in channels if c.get("channel_id") == only_channel]
    if not channels:
        return {"error": "no ingesting channels matched", "videos": []}

    resolver = PodcastEntityResolver()
    index = build_podcast_title_index() if dedupe else {"by_show": {}, "all": {}}
    print("podcast title index: {0} episodes".format(len(index.get("all", {}))), flush=True)

    videos: list[dict] = []
    stats: list[dict] = []
    errors: list[dict] = []

    for ch in channels:
        try:
            raw = http_get(ch["rss_url"])
            found = parse_channel_feed(raw, ch)
        except Exception as exc:  # noqa: BLE001 - feed and network shapes vary
            errors.append({"channel_id": ch.get("channel_id"), "error": type(exc).__name__ + ": " + str(exc)})
            print("ERR  {0}: {1}".format(ch.get("title"), type(exc).__name__), flush=True)
            continue

        for v in found:
            # Advisory only. Recorded so the transcript gate can be calibrated
            # later against what metadata would have guessed -- and so the two
            # can be compared on the labelled sample.
            v["resolve_preview"] = resolver.resolve_episode(
                title=v.get("title") or "",
                description=v.get("description") or "",
                show_title=ch.get("title") or "",
                host_guest_ids=list(ch.get("guest_ids") or []),
            )
            screen(v, ch, index)

        pending = sum(1 for v in found if v["gate"] == "pending_transcript")
        dupes = sum(1 for v in found if "duplicate_of_podcast_episode" in v["reject_reasons"])
        stats.append({
            "channel_id": ch.get("channel_id"),
            "title": ch.get("title"),
            "tier": ch.get("tier"),
            "trust": ch.get("trust"),
            "found": len(found),
            "pending_transcript": pending,
            "duplicates": dupes,
        })
        print("ok   {0:32s} found={1:<3} pending={2:<3} dupes={3}".format(
            (ch.get("title") or "")[:30], len(found), pending, dupes), flush=True)
        videos.extend(found)
        time.sleep(float(ch.get("rate_limit_seconds") or 1.0))

    # One video can appear on two registered channels (a guest re-upload).
    seen: set[str] = set()
    deduped: list[dict] = []
    for v in videos:
        if v["video_id"] in seen:
            continue
        seen.add(v["video_id"])
        deduped.append(v)

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "channel_count": len(channels),
        "video_count": len(deduped),
        "pending_transcript": sum(1 for v in deduped if v["gate"] == "pending_transcript"),
        "rejected_metadata": sum(1 for v in deduped if v["gate"] == "rejected_metadata"),
        "note": "gate=pending_transcript means undecided. Relevance is decided on the "
                "transcript, never on this record.",
        "channel_stats": stats,
        "errors": errors,
        "videos": deduped,
    }
    if write:
        out_dir = videos_root(create=True)
        (out_dir / "discovery_latest.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("\nwrote {0}".format(out_dir / "discovery_latest.json"), flush=True)
    return payload


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--channel", default=None, help="Limit to one channel_id")
    p.add_argument("--no-dedupe", action="store_true",
                   help="Skip the podcast-corpus duplicate index (faster, noisier)")
    p.add_argument("--no-write", action="store_true", help="Do not write discovery_latest.json")
    args = p.parse_args()

    payload = discover(only_channel=args.channel, dedupe=not args.no_dedupe,
                       write=not args.no_write)
    print("\n{0} videos: {1} pending transcript, {2} rejected on metadata".format(
        payload.get("video_count", 0), payload.get("pending_transcript", 0),
        payload.get("rejected_metadata", 0)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
