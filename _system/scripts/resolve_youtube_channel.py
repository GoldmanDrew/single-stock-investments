#!/usr/bin/env python3
"""Resolve a YouTube handle/URL to a channel ID, and prove the feed is the right one.

Registry maintenance tool. Two jobs, and the second is the one that matters.

**Resolve.** A handle (`@AcquiredFM`) is not a channel ID. The ID is what the RSS
feed needs and is only obtainable from the channel page, so this fetches it and
extracts `channelId`. Handles are guessable and frequently wrong: of 20
candidates tried by hand on 2026-09-01, 9 returned HTTP 404 on the obvious
spelling.

**Verify.** Name matching is how the wrong channel gets into a registry. Three
candidates resolved to a real channel that was not the intended one. Searching
"The Synopsis" returned a channel whose entire public output is one 2022 video
titled "Best Action Movies 2022"; "Ben Graham Centre" surfaced three lookalikes,
none of them Ivey's. Both would have looked correct in a registry diff -- right
name, valid ID, feed answers 200. So resolution is not finished until the *feed
contents* have been read: this reports entry count, last publish date and the
feed's own title, and flags a channel whose feed title does not resemble the
label we filed it under.

A feed that answers 200 with a plausible name is not evidence. The column is.

    python _system/scripts/resolve_youtube_channel.py @AcquiredFM @GuySpier
    python _system/scripts/resolve_youtube_channel.py --verify
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

# Channel and video titles carry whatever the uploader typed -- smart quotes and
# en dashes are routine, and a U+2060 WORD JOINER in a podcast title killed a
# whole analysis run on 2026-08-29 because Python picks cp1252 for a redirected
# stdout on Windows. The line that *reports* success is the line that crashes.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

VIDEO_CFG = ROOT / "_system" / "reference" / "video"
CHANNEL_REG = VIDEO_CFG / "channel_registry.json"

FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
ATOM = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}

CHANNEL_ID_RE = re.compile(r'"(?:channelId|externalId)":"(UC[\w-]{22})"')
OG_TITLE_RE = re.compile(r'<meta property="og:title" content="([^"]*)"')
BARE_ID_RE = re.compile(r"^(UC[\w-]{22})$")

# A channel with no upload in this long is not worth a daily poll.
DORMANT_DAYS = 365


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def user_agent() -> str:
    doc = load_json(CHANNEL_REG)
    return doc.get("user_agent") or "SSI-VideoAgent/1.0 (+research)"


def http_get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": user_agent()})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _normalize(text: str) -> str:
    """Fold to comparable form: lowercase alphanumerics only.

    'Capital Allocators with Ted Seides' vs 'Capital Allocators' must compare as
    related; 'The Synopsis' vs 'Best Action Movies 2022' must not.
    """
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def titles_agree(expected: str, actual: str) -> bool:
    a, b = _normalize(expected), _normalize(actual)
    if not a or not b:
        return False
    return a in b or b in a


def resolve_handle(handle: str) -> dict:
    """Return {channel_id, ...} for a handle, bare ID, or channel URL."""
    handle = (handle or "").strip()
    bare = BARE_ID_RE.match(handle)
    if bare:
        return {"channel_id": bare.group(1), "resolved_from": "bare_id", "tried": []}

    if handle.startswith("http"):
        forms = [handle]
    else:
        stem = handle.lstrip("@")
        # /@handle is current; /c/ and /user/ are legacy forms still serving many
        # older channels, which is where several of these actually resolved.
        forms = [
            "https://www.youtube.com/@" + stem,
            "https://www.youtube.com/c/" + stem,
            "https://www.youtube.com/user/" + stem,
        ]

    tried: list[dict] = []
    for url in forms:
        try:
            html = http_get(url).decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            tried.append({"url": url, "error": "HTTP " + str(exc.code)})
            time.sleep(0.5)
            continue
        except Exception as exc:  # noqa: BLE001 - network failure shapes vary
            tried.append({"url": url, "error": type(exc).__name__})
            time.sleep(0.5)
            continue
        cid = CHANNEL_ID_RE.search(html)
        if cid:
            og = OG_TITLE_RE.search(html)
            return {
                "channel_id": cid.group(1),
                "page_title": og.group(1) if og else "",
                "resolved_from": url,
                "tried": tried,
            }
        tried.append({"url": url, "error": "no channelId in page"})
        time.sleep(0.5)
    return {"channel_id": None, "tried": tried}


def probe_feed(channel_id: str) -> dict:
    """Read the channel's Atom feed and report what is actually in it.

    The feed carries at most 15 entries and YouTube does not paginate it. That
    cap is why history needs the Data API's uploads playlist; for discovering
    *new* uploads this is sufficient and costs no API quota.
    """
    try:
        raw = http_get(FEED_URL.format(cid=channel_id))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": type(exc).__name__ + ": " + str(exc)}
    try:
        doc = ET.fromstring(raw)
    except ET.ParseError as exc:
        return {"ok": False, "error": "ParseError: " + str(exc)}

    entries = doc.findall("a:entry", ATOM)
    feed_title = (doc.findtext("a:title", default="", namespaces=ATOM) or "").strip()
    days = sorted(
        d for d in
        ((e.findtext("a:published", default="", namespaces=ATOM) or "")[:10] for e in entries)
        if d
    )
    return {
        "ok": True,
        "feed_title": feed_title,
        "entry_count": len(entries),
        "first_published": days[0] if days else None,
        "last_published": days[-1] if days else None,
        "recent_titles": [
            (e.findtext("a:title", default="", namespaces=ATOM) or "")[:80] for e in entries[:3]
        ],
    }


def days_since(day: str | None) -> int | None:
    if not day:
        return None
    try:
        then = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - then).days


def assess(expected_title: str, channel_id: str) -> dict:
    """Resolve + probe + judge. `warnings` is the reason not to trust a row."""
    feed = probe_feed(channel_id)
    out = {"channel_id": channel_id, "expected_title": expected_title}
    out.update(feed)
    warnings: list[str] = []
    if not feed.get("ok"):
        warnings.append("feed_unreachable")
    else:
        if not titles_agree(expected_title, feed.get("feed_title") or ""):
            # The "Best Action Movies 2022" case: right name, wrong channel.
            warnings.append("feed_title_mismatch")
        if (feed.get("entry_count") or 0) <= 1:
            warnings.append("feed_nearly_empty")
        stale = days_since(feed.get("last_published"))
        if stale is not None and stale > DORMANT_DAYS:
            warnings.append("dormant_" + str(stale) + "d")
    out["warnings"] = warnings
    out["trusted"] = not warnings
    return out


def verify_registry() -> int:
    doc = load_json(CHANNEL_REG)
    channels = doc.get("channels") or []
    if not channels:
        print("no channels in " + str(CHANNEL_REG))
        return 1
    flagged = 0
    for ch in channels:
        res = assess(ch.get("title") or "", ch.get("channel_id") or "")
        if not res["trusted"]:
            flagged += 1
        mark = "OK  " if res["trusted"] else "WARN"
        print("{0} {1:32s} {2:>3} entries  last={3:10s} {4}".format(
            mark,
            (ch.get("title") or "")[:30],
            str(res.get("entry_count", "-")),
            res.get("last_published") or "-",
            ",".join(res["warnings"]),
        ))
        time.sleep(0.3)
    print("\n{0} channels, {1} flagged".format(len(channels), flagged))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("handles", nargs="*", help="@handle, channel URL, or bare UC... id")
    p.add_argument("--verify", action="store_true",
                   help="Re-probe every channel already in channel_registry.json")
    p.add_argument("--expect", default="",
                   help="Expected channel title, for mismatch detection")
    p.add_argument("--json", action="store_true", help="Emit the full result objects")
    args = p.parse_args()

    if args.verify:
        return verify_registry()
    if not args.handles:
        p.error("give at least one handle, or --verify")

    results = []
    for h in args.handles:
        res = resolve_handle(h)
        if not res.get("channel_id"):
            print("MISS " + h + "  (tried " + str(len(res["tried"])) + " forms)")
            results.append(dict({"input": h}, **res))
            continue
        expected = args.expect or res.get("page_title") or h.lstrip("@")
        checked = assess(expected, res["channel_id"])
        merged = dict({"input": h}, **res)
        merged.update(checked)
        results.append(merged)
        mark = "OK  " if checked["trusted"] else "WARN"
        print("{0} {1:26s} {2}  {3}".format(
            mark, h, res["channel_id"], (checked.get("feed_title") or "")[:34]))
        for w in checked["warnings"]:
            print("       ! " + w)
        for t in checked.get("recent_titles", [])[:2]:
            print("       - " + t)
        time.sleep(0.4)

    if args.json:
        print("\n" + json.dumps(results, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
