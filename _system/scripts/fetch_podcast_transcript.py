#!/usr/bin/env python3
"""Fetch published transcripts or Whisper-transcribe audio into research-vault/podcasts."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from vault_paths import podcasts_root  # noqa: E402

PODCASTS_CFG = ROOT / "_system" / "reference" / "podcasts"
SHOW_REG = PODCASTS_CFG / "show_registry.json"


def load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def user_agent() -> str:
    doc = load_json(SHOW_REG) or {}
    return doc.get("user_agent") or "SSI-PodcastAgent/1.0 (+research)"


def http_get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": user_agent()})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def year_from_published(published: str | None) -> str:
    if published and re.match(r"^\d{4}", published):
        return published[:4]
    return datetime.now(timezone.utc).strftime("%Y")


def episode_paths(episode_id: str, published: str | None) -> tuple[Path, Path]:
    root = podcasts_root(create=True)
    year = year_from_published(published)
    ep_dir = root / "episodes" / year
    ep_dir.mkdir(parents=True, exist_ok=True)
    return ep_dir / f"{episode_id}.txt", ep_dir / f"{episode_id}.meta.json"


def strip_html(text: str) -> str:
    text = unescape(text or "")
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</p>", "\n\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def try_published_transcript(episode: dict, show: dict | None) -> str | None:
    """Heuristic: follow episode link and look for transcript-sized text blocks."""
    link = episode.get("link")
    if not link:
        return None
    prefer = [p.lower() for p in ((show or {}).get("prefer_transcript_urls") or ["transcript"])]
    try:
        html = http_get(link, timeout=45).decode("utf-8", errors="ignore")
    except Exception:
        return None
    lower = html.lower()
    if not any(p in lower for p in prefer):
        # Still accept very long article bodies as transcript-like
        text = strip_html(html)
        return text if len(text) >= 4000 else None
    # Prefer elements labeled transcript
    m = re.search(
        r'(?is)(?:id|class)=["\'][^"\']*transcript[^"\']*["\'][^>]*>(.*?)</(?:div|section|article)>',
        html,
    )
    if m:
        text = strip_html(m.group(1))
        if len(text) >= 500:
            return text
    text = strip_html(html)
    return text if len(text) >= 2500 else None


def download_audio(audio_url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = http_get(audio_url, timeout=180)
    dest.write_bytes(data)
    return dest


def whisper_transcribe(audio_path: Path) -> str | None:
    """Transcribe with faster-whisper (preferred) or openai-whisper CLI."""
    # Prefer faster-whisper (CPU int8) — openai-whisper base on long episodes is too slow.
    try:
        from faster_whisper import WhisperModel  # type: ignore

        model = WhisperModel("base", device="cpu", compute_type="int8")
        segments, _info = model.transcribe(str(audio_path), language="en")
        parts = [seg.text.strip() for seg in segments if seg.text]
        text = "\n".join(parts).strip()
        if text:
            return text
    except Exception:
        pass
    try:
        out_dir = audio_path.parent
        subprocess.run(
            [
                sys.executable,
                "-m",
                "whisper",
                str(audio_path),
                "--model",
                "base",
                "--language",
                "en",
                "--output_format",
                "txt",
                "--output_dir",
                str(out_dir),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=3600,
        )
        txt = out_dir / f"{audio_path.stem}.txt"
        if txt.exists():
            return txt.read_text(encoding="utf-8", errors="ignore").strip()
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return None


WHISPER_BACKLOG_NAME = "whisper_backlog.json"


def whisper_backlog_path() -> Path:
    return podcasts_root(create=True) / WHISPER_BACKLOG_NAME


def load_whisper_backlog() -> dict:
    doc = load_json(whisper_backlog_path()) or {}
    if not isinstance(doc, dict):
        doc = {}
    doc.setdefault("items", [])
    return doc


def save_whisper_backlog(doc: dict) -> None:
    doc["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    doc["pending_count"] = sum(1 for i in (doc.get("items") or []) if i.get("status") == "pending")
    whisper_backlog_path().write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def whisper_pending_count() -> int:
    doc = load_whisper_backlog()
    return int(
        doc.get("pending_count")
        or sum(1 for i in (doc.get("items") or []) if i.get("status") == "pending")
    )


def upsert_whisper_backlog_item(episode: dict, *, status: str = "pending") -> None:
    if not episode.get("audio_url") or not episode.get("episode_id"):
        return
    doc = load_whisper_backlog()
    items = list(doc.get("items") or [])
    eid = episode["episode_id"]
    existing = next((i for i in items if i.get("episode_id") == eid), None)
    row = {
        "episode_id": eid,
        "show_id": episode.get("show_id"),
        "title": episode.get("title"),
        "published": episode.get("published"),
        "audio_url": episode.get("audio_url"),
        "link": episode.get("link"),
        "status": status,
        "attempts": int((existing or {}).get("attempts") or 0),
    }
    if existing:
        for i, it in enumerate(items):
            if it.get("episode_id") == eid:
                # Keep attempts; refresh metadata
                row["attempts"] = int(it.get("attempts") or 0)
                if it.get("status") == "done":
                    row["status"] = "done"
                items[i] = row
                break
    else:
        items.append(row)
    doc["items"] = items
    doc["pending_count"] = sum(1 for i in items if i.get("status") == "pending")
    save_whisper_backlog(doc)


def delete_audio_cache(episode_id: str) -> None:
    cache = podcasts_root(create=True) / "audio-cache"
    if not cache.is_dir():
        return
    for p in cache.glob(f"{episode_id}.*"):
        try:
            p.unlink()
        except OSError:
            pass


def fetch_one(episode: dict, show_by_id: dict[str, dict], *, allow_whisper: bool = True) -> dict:
    eid = episode["episode_id"]
    txt_path, meta_path = episode_paths(eid, episode.get("published"))
    show = show_by_id.get(episode.get("show_id") or "", {})
    status = "skipped"
    source = None
    text = None

    if txt_path.exists() and meta_path.exists():
        meta = load_json(meta_path) or {}
        return {"episode_id": eid, "status": "exists", "path": str(txt_path), "meta": meta}

    # Meta-only stubs from a prior --no-whisper pass should still retry Whisper.
    prior = load_json(meta_path) if meta_path.exists() else None
    if prior and not txt_path.exists():
        episode = {**prior, **episode}

    text = try_published_transcript(episode, show)
    if text:
        source = "published_html"
        status = "fetched_published"
    elif allow_whisper and episode.get("audio_url"):
        cache = podcasts_root(create=True) / "audio-cache"
        ext = ".mp3"
        url = episode["audio_url"]
        if ".m4a" in url:
            ext = ".m4a"
        audio_path = cache / f"{eid}{ext}"
        try:
            if not audio_path.exists():
                download_audio(url, audio_path)
            text = whisper_transcribe(audio_path)
            if text:
                source = "whisper"
                status = "transcribed"
            else:
                status = "whisper_unavailable"
        except Exception as exc:
            status = f"audio_error:{exc}"
        finally:
            if text:
                delete_audio_cache(eid)
    else:
        status = "no_transcript_source"
        if episode.get("audio_url") and not allow_whisper:
            upsert_whisper_backlog_item(episode, status="pending")

    # Always write meta; write transcript when available
    meta = {
        **episode,
        "transcript_source": source,
        "transcript_status": status,
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "transcript_path": str(txt_path.relative_to(podcasts_root())) if text else None,
        "sha1_audio": hashlib.sha1((episode.get("audio_url") or "").encode()).hexdigest()
        if episode.get("audio_url")
        else None,
    }
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    if text:
        txt_path.write_text(text + "\n", encoding="utf-8")
        # Mark backlog done if present
        doc = load_whisper_backlog()
        changed = False
        for it in doc.get("items") or []:
            if it.get("episode_id") == eid and it.get("status") != "done":
                it["status"] = "done"
                changed = True
        if changed:
            doc["pending_count"] = sum(1 for i in (doc.get("items") or []) if i.get("status") == "pending")
            save_whisper_backlog(doc)
    return {"episode_id": eid, "status": status, "path": str(txt_path) if text else None, "meta": meta}


def episode_fetch_priority(episode: dict, show: dict | None) -> str:
    """Classify fetch priority for Whisper budgeting.

    - high: officer / company alias / non-host PZ guest in title/desc
    - host: host-only show episode (try published; Whisper only if recent slot)
    - skip: no signal
    """
    prev = episode.get("resolve_preview") or {}
    title_guests = prev.get("title_guests") or [
        g for g in (prev.get("guests") or []) if g.get("matched_alias") != "show_host"
    ]
    if prev.get("has_officer_hit") or prev.get("near_universe_any") or prev.get("tickers"):
        return "high"
    if title_guests:
        return "high"
    if (prev.get("guests") or []) or (show or {}).get("host_guest_ids"):
        return "host"
    return "skip"


def fetch_from_discovery(
    discovery_path: Path | None = None,
    *,
    allow_whisper: bool = True,
    limit: int | None = None,
    host_whisper_per_show: int = 8,
    backfill: bool = False,
) -> dict:
    root = podcasts_root(create=True)
    discovery_path = discovery_path or (root / "discovery_latest.json")
    doc = load_json(discovery_path) or {}
    episodes = doc.get("episodes") or []
    shows = {s.get("show_id"): s for s in ((load_json(SHOW_REG) or {}).get("shows") or [])}

    # Newest first for host Whisper budget
    episodes = sorted(episodes, key=lambda e: e.get("published") or "", reverse=True)
    host_whisper_used: dict[str, int] = {}
    selected: list[tuple[dict, bool]] = []
    for ep in episodes:
        show = shows.get(ep.get("show_id") or "", {})
        pri = episode_fetch_priority(ep, show)
        if pri == "skip" and not backfill:
            continue
        whisper_ok = allow_whisper
        if backfill:
            # Backfill: attempt published for all; Whisper only if allow_whisper (ignore host budget)
            whisper_ok = allow_whisper
        elif pri == "host":
            sid = ep.get("show_id") or ""
            used = host_whisper_used.get(sid, 0)
            # Always attempt published; Whisper only within per-show budget
            whisper_ok = allow_whisper and used < host_whisper_per_show
            if whisper_ok:
                host_whisper_used[sid] = used + 1
        selected.append((ep, whisper_ok))

    if limit is not None:
        selected = selected[:limit]

    results = []
    for ep, whisper_ok in selected:
        results.append(fetch_one(ep, shows, allow_whisper=whisper_ok))
        # Queue remaining audio for Whisper when published-only backfill
        if backfill and not whisper_ok and ep.get("audio_url"):
            txt_path, _meta = episode_paths(ep["episode_id"], ep.get("published"))
            if not txt_path.exists():
                upsert_whisper_backlog_item(ep, status="pending")

    summary = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "count": len(results),
        "selected_from_discovery": len(selected),
        "backfill": backfill,
        "by_status": {},
        "results": results,
        "whisper_pending": (load_whisper_backlog().get("pending_count") or 0),
    }
    for r in results:
        summary["by_status"][r["status"]] = summary["by_status"].get(r["status"], 0) + 1
    summary["whisper_pending"] = whisper_pending_count()
    (root / "fetch_latest.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def drain_whisper_backlog(*, batch: int = 20) -> dict:
    """Whisper pending backlog items newest-first; delete audio after success."""
    root = podcasts_root(create=True)
    doc = load_whisper_backlog()
    items = [i for i in (doc.get("items") or []) if i.get("status") == "pending" and i.get("audio_url")]
    items.sort(key=lambda e: e.get("published") or "", reverse=True)
    batch_items = items[: max(0, batch)]
    shows = {s.get("show_id"): s for s in ((load_json(SHOW_REG) or {}).get("shows") or [])}
    results = []
    for it in batch_items:
        # bump attempts
        for row in doc.get("items") or []:
            if row.get("episode_id") == it.get("episode_id"):
                row["attempts"] = int(row.get("attempts") or 0) + 1
                break
        save_whisper_backlog(doc)
        ep = {
            "episode_id": it["episode_id"],
            "show_id": it.get("show_id"),
            "title": it.get("title"),
            "published": it.get("published"),
            "audio_url": it.get("audio_url"),
            "link": it.get("link"),
        }
        result = fetch_one(ep, shows, allow_whisper=True)
        results.append(result)
        # refresh doc after fetch_one may have marked done
        doc = load_whisper_backlog()
        if result.get("status") not in ("transcribed", "fetched_published", "exists"):
            for row in doc.get("items") or []:
                if row.get("episode_id") == it.get("episode_id"):
                    if int(row.get("attempts") or 0) >= 3:
                        row["status"] = "failed"
                    break
            doc["pending_count"] = sum(1 for i in (doc.get("items") or []) if i.get("status") == "pending")
            save_whisper_backlog(doc)

    summary = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "batch": batch,
        "attempted": len(results),
        "by_status": {},
        "whisper_pending": (load_whisper_backlog().get("pending_count") or 0),
        "results": results,
    }
    for r in results:
        summary["by_status"][r["status"]] = summary["by_status"].get(r["status"], 0) + 1
    (root / "whisper_batch_latest.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--discovery", type=Path, default=None)
    p.add_argument("--no-whisper", action="store_true")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--host-whisper-per-show", type=int, default=8)
    p.add_argument(
        "--backfill",
        action="store_true",
        help="Fetch every discovered watchlist episode (ignore skip priority / host Whisper budget)",
    )
    p.add_argument(
        "--whisper-batch",
        type=int,
        default=None,
        metavar="N",
        help="Drain N pending items from whisper_backlog.json (newest first)",
    )
    args = p.parse_args()
    if args.whisper_batch is not None:
        summary = drain_whisper_backlog(batch=args.whisper_batch)
        print(json.dumps({k: summary.get(k) for k in ("attempted", "by_status", "whisper_pending")}, indent=2))
        return 0
    summary = fetch_from_discovery(
        args.discovery,
        allow_whisper=not args.no_whisper,
        limit=args.limit,
        host_whisper_per_show=args.host_whisper_per_show,
        backfill=args.backfill,
    )
    print(json.dumps(summary.get("by_status") or {}, indent=2))
    if summary.get("whisper_pending"):
        print(f"whisper_pending={summary['whisper_pending']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())