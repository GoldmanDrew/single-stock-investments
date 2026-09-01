#!/usr/bin/env python3
"""Minimal YouTube Data API v3 client with quota accounting, and no search.list.

The free tier is 10,000 units/day. The cost table is what shapes this module:

    search.list          100 units   ->  100 calls/day. Never used here.
    playlistItems.list     1 unit    ->  50 videos per unit
    videos.list            1 unit    ->  50 videos per unit
    channels.list          1 unit

`search.list` is not merely avoided, it raises. A single accidental search loop
would burn the day's quota in 100 iterations and the failure would look like an
outage rather than a bug. Everything discovery needs is reachable without it:
each channel's uploads playlist id is `UU` + the channel id minus its `UC`
prefix, which the registry already stores, so full history costs one unit per 50
videos. Backfilling all seven ingesting channels is tens of units, not thousands.

Quota is counted locally and written to the vault, because the API does not tell
you what you have spent -- it only starts failing. A ledger that says "you spent
420 units today" is the difference between a diagnosis and a mystery.

Key resolution: $YOUTUBE_API_KEY, else `_secrets/youtube.env` (gitignored).
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from vault_paths import videos_root  # noqa: E402

API_BASE = "https://www.googleapis.com/youtube/v3/"
SECRETS_ENV = ROOT / "_secrets" / "youtube.env"

# Documented unit costs. Anything absent here is refused rather than guessed.
UNIT_COST = {
    "videos": 1,
    "playlistItems": 1,
    "channels": 1,
    "playlists": 1,
}
FREE_TIER_DAILY_UNITS = 10_000
# Refuse to start a call that would cross this. Leaves headroom for a manual
# check after an automated job has run.
DEFAULT_BUDGET = int(os.environ.get("YOUTUBE_DAILY_UNIT_BUDGET", "8000"))

MAX_IDS_PER_CALL = 50


class YouTubeAPIError(RuntimeError):
    """The API refused the call, or we refused to make it."""


class QuotaExceeded(YouTubeAPIError):
    """The local ledger says today's budget is spent."""


def _read_key_from_secrets() -> str:
    """Parse `export YOUTUBE_API_KEY='...'` out of the gitignored env file."""
    if not SECRETS_ENV.exists():
        return ""
    for line in SECRETS_ENV.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*(?:export\s+)?YOUTUBE_API_KEY\s*=\s*(.+?)\s*$", line)
        if m:
            return m.group(1).strip().strip("'\"")
    return ""


def api_key() -> str:
    key = (os.environ.get("YOUTUBE_API_KEY") or "").strip() or _read_key_from_secrets()
    if not key:
        raise YouTubeAPIError(
            "No API key. Set $YOUTUBE_API_KEY or create _secrets/youtube.env "
            "(source _secrets/youtube.env)."
        )
    return key


def _ledger_path() -> Path:
    return videos_root(create=True) / "api_quota_ledger.json"


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def load_ledger() -> dict:
    path = _ledger_path()
    if not path.exists():
        return {"days": {}}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {"days": {}}
    except json.JSONDecodeError:
        return {"days": {}}


def spent_today() -> int:
    return int((load_ledger().get("days") or {}).get(_today(), {}).get("units", 0))


def _record(endpoint: str, units: int) -> None:
    doc = load_ledger()
    days = doc.setdefault("days", {})
    day = days.setdefault(_today(), {"units": 0, "calls": {}})
    day["units"] = int(day.get("units", 0)) + units
    day["calls"][endpoint] = int(day.get("calls", {}).get(endpoint, 0)) + 1
    doc["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    doc["free_tier_daily_units"] = FREE_TIER_DAILY_UNITS
    # Keep the ledger small: 60 days is plenty to spot a runaway job.
    if len(days) > 60:
        for key in sorted(days)[:-60]:
            days.pop(key, None)
    _ledger_path().write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def call(endpoint: str, params: dict, *, budget: int = DEFAULT_BUDGET) -> dict:
    """One API call, quota-accounted. Refuses search.list and unknown endpoints."""
    if endpoint == "search":
        raise YouTubeAPIError(
            "search.list costs 100 units and is not used. Use playlistItems.list "
            "against the channel's uploads playlist (registry: uploads_playlist_id)."
        )
    if endpoint not in UNIT_COST:
        raise YouTubeAPIError("unknown endpoint " + endpoint + "; add its documented unit cost first")

    cost = UNIT_COST[endpoint]
    if spent_today() + cost > budget:
        raise QuotaExceeded(
            "local ledger says {0} units spent today; budget {1}".format(spent_today(), budget)
        )

    query = dict(params)
    query["key"] = api_key()
    url = API_BASE + endpoint + "?" + urllib.parse.urlencode(query)
    try:
        with urllib.request.urlopen(url, timeout=45) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:400]
        except Exception:  # noqa: BLE001
            pass
        # Count it anyway: a rejected call still bills against quota upstream.
        _record(endpoint, cost)
        raise YouTubeAPIError("HTTP {0} on {1}: {2}".format(exc.code, endpoint, detail)) from exc
    _record(endpoint, cost)
    return body


def videos(video_ids: list[str], *, part: str = "snippet,contentDetails,statistics") -> dict:
    """id -> video resource. 1 unit per 50 ids."""
    out: dict[str, dict] = {}
    ids = [v for v in video_ids if v]
    for i in range(0, len(ids), MAX_IDS_PER_CALL):
        chunk = ids[i:i + MAX_IDS_PER_CALL]
        body = call("videos", {"part": part, "id": ",".join(chunk), "maxResults": MAX_IDS_PER_CALL})
        for item in body.get("items") or []:
            out[item["id"]] = item
    return out


def playlist_items(playlist_id: str, *, max_videos: int | None = None) -> list[dict]:
    """Every video in a playlist. 1 unit per 50 -- this is how history is read."""
    collected: list[dict] = []
    page_token = None
    while True:
        params = {
            "part": "snippet,contentDetails",
            "playlistId": playlist_id,
            "maxResults": MAX_IDS_PER_CALL,
        }
        if page_token:
            params["pageToken"] = page_token
        body = call("playlistItems", params)
        for item in body.get("items") or []:
            vid = (item.get("contentDetails") or {}).get("videoId")
            if not vid:
                continue
            snip = item.get("snippet") or {}
            collected.append({
                "video_id": vid,
                "title": (snip.get("title") or "").strip(),
                "description": (snip.get("description") or "").strip(),
                "published": (item.get("contentDetails") or {}).get("videoPublishedAt")
                or snip.get("publishedAt"),
                "channel_id": snip.get("channelId"),
            })
            if max_videos and len(collected) >= max_videos:
                return collected
        page_token = body.get("nextPageToken")
        if not page_token:
            return collected


ISO_DURATION_RE = re.compile(
    r"^P(?:(?P<days>\d+)D)?T(?:(?P<h>\d+)H)?(?:(?P<m>\d+)M)?(?:(?P<s>\d+)S)?$"
)


def parse_duration(iso: str | None) -> int | None:
    """PT10M12S -> 612 seconds. Duration is only available from the API, not RSS."""
    if not iso:
        return None
    m = ISO_DURATION_RE.match(iso.strip())
    if not m:
        return None
    days = int(m.group("days") or 0)
    return (
        days * 86400
        + int(m.group("h") or 0) * 3600
        + int(m.group("m") or 0) * 60
        + int(m.group("s") or 0)
    )


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--quota", action="store_true", help="Show the local quota ledger")
    p.add_argument("--video", action="append", default=[], help="Look up a video id")
    args = p.parse_args()

    if args.quota:
        doc = load_ledger()
        print(json.dumps({"today": _today(), "spent_today": spent_today(),
                          "budget": DEFAULT_BUDGET,
                          "free_tier": FREE_TIER_DAILY_UNITS,
                          "days": doc.get("days", {})}, indent=2))
        return 0
    if args.video:
        got = videos(args.video)
        for vid, item in got.items():
            cd = item.get("contentDetails") or {}
            print(vid, parse_duration(cd.get("duration")), "s |",
                  (item.get("snippet") or {}).get("title", "")[:60])
        return 0
    p.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
