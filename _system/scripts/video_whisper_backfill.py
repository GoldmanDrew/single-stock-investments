#!/usr/bin/env python3
"""Route videos without published captions through the local Whisper lane.

Audio is temporary working material: it is downloaded into videos/audio-cache,
transcribed locally, and deleted in a finally block. Only text and provenance
metadata enter the research vault.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from fetch_podcast_transcript import whisper_transcribe
from fetch_video_transcript import quality_gate, slugify
from vault_paths import videos_root


BACKLOG_NAME = "whisper_backlog.json"
MAX_ATTEMPTS = 3


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def backlog_path() -> Path:
    return videos_root(create=True) / BACKLOG_NAME


def load_backlog() -> dict:
    doc = load_json(backlog_path())
    doc.setdefault("items", [])
    return doc


def save_backlog(doc: dict) -> None:
    items = doc.get("items") or []
    doc["updated_at"] = now_stamp()
    doc["pending_count"] = sum(1 for row in items if row.get("status") == "pending")
    atomic_json(backlog_path(), doc)


def queue_no_caption_videos() -> dict:
    root = videos_root(create=True)
    captions = load_json(root / "caption_backlog.json")
    discovery = load_json(root / "discovery_latest.json")
    discovered = {
        row.get("video_id"): row
        for row in (discovery.get("videos") or [])
        if isinstance(row, dict) and row.get("video_id")
    }
    backlog = load_backlog()
    items = list(backlog.get("items") or [])
    known = {row.get("video_id") for row in items if row.get("video_id")}
    queued = 0
    for video_id, row in (captions.get("items") or {}).items():
        if not isinstance(row, dict) or row.get("status") != "no_captions" or video_id in known:
            continue
        detail = dict(discovered.get(video_id) or {})
        detail.update({
            key: value for key, value in row.items()
            if key not in {"status", "attempts"} and value not in (None, "")
        })
        items.append({
            **detail,
            "video_id": video_id,
            "url": row.get("url") or f"https://www.youtube.com/watch?v={video_id}",
            "status": "pending",
            "attempts": 0,
            "queued_at": now_stamp(),
        })
        known.add(video_id)
        queued += 1
    backlog["items"] = items
    save_backlog(backlog)
    return {"queued": queued, "pending": backlog.get("pending_count", 0)}


def _video_paths(item: dict) -> tuple[Path, Path]:
    year = str(item.get("published") or "")[:4]
    if not (len(year) == 4 and year.isdigit()):
        year = datetime.now(timezone.utc).strftime("%Y")
    library = videos_root(create=True) / "library" / year
    library.mkdir(parents=True, exist_ok=True)
    stem = slugify(str(item.get("title") or "video")) + "-" + str(item["video_id"])
    return library / (stem + ".txt"), library / (stem + ".meta.json")


def finalize_transcript(item: dict, text: str) -> dict:
    text = (text or "").strip()
    duration = item.get("duration_seconds")
    reasons = quality_gate(text, duration)
    if reasons:
        return {"status": "rejected_quality", "reasons": reasons}

    txt_path, meta_path = _video_paths(item)
    root = videos_root(create=True)
    try:
        transcript_path = txt_path.relative_to(root).as_posix()
    except ValueError:
        transcript_path = txt_path.name
    meta = {
        **{key: value for key, value in item.items()
           if key not in {"status", "attempts", "last_error", "queued_at"}},
        "video_id": item.get("video_id"),
        "url": item.get("url") or f"https://www.youtube.com/watch?v={item.get('video_id')}",
        "transcript_chars": len(text),
        "chars_per_minute": round(len(text) / (duration / 60.0), 1) if duration else None,
        "transcript_source": "local_whisper",
        "transcript_path": transcript_path,
        "relevance": None,
        "gate": "transcript_fetched",
        "fetched_at": now_stamp(),
    }
    txt_path.write_text(text + "\n", encoding="utf-8")
    atomic_json(meta_path, meta)
    return {"status": "transcribed", "text_path": str(txt_path), "meta_path": str(meta_path)}


def download_audio(item: dict, cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    video_id = str(item["video_id"])
    output = cache_dir / (video_id + ".%(ext)s")
    completed = subprocess.run(
        [
            sys.executable, "-m", "yt_dlp",
            "--no-playlist", "--quiet", "--no-warnings", "--print-json",
            "-f", "bestaudio[ext=m4a]/bestaudio",
            "-o", str(output),
            str(item.get("url") or f"https://www.youtube.com/watch?v={video_id}"),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=900,
    )
    # Caption backlog rows are intentionally sparse. yt-dlp gives the duration
    # and current public metadata while it downloads, so carry those forward
    # into the quality gate and provenance record without a second request.
    try:
        info = json.loads((completed.stdout or "").strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        info = {}
    field_map = {
        "duration": "duration_seconds",
        "title": "title",
        "channel_id": "channel_id",
        "channel": "channel_title",
        "view_count": "views",
        "description": "description",
    }
    for source, target in field_map.items():
        if info.get(source) not in (None, ""):
            item[target] = info[source]
    matches = [path for path in cache_dir.glob(video_id + ".*") if path.is_file()]
    if not matches:
        raise FileNotFoundError("yt-dlp completed without an audio file")
    return max(matches, key=lambda path: path.stat().st_size)


def _mark_caption_done(video_id: str) -> None:
    path = videos_root(create=True) / "caption_backlog.json"
    doc = load_json(path)
    row = (doc.get("items") or {}).get(video_id)
    if isinstance(row, dict):
        row["status"] = "done"
        row["transcript_source"] = "local_whisper"
        row["completed_at"] = now_stamp()
        doc["pending_count"] = sum(
            1 for value in (doc.get("items") or {}).values()
            if isinstance(value, dict) and value.get("status") == "pending"
        )
        atomic_json(path, doc)


def drain(*, batch: int = 4) -> dict:
    queue_no_caption_videos()
    doc = load_backlog()
    pending = [row for row in doc.get("items") or [] if row.get("status") == "pending"]
    results = []
    cache = videos_root(create=True) / "audio-cache"
    for item in pending[:max(0, batch)]:
        item["attempts"] = int(item.get("attempts") or 0) + 1
        item["last_attempt_at"] = now_stamp()
        save_backlog(doc)
        audio_path = None
        try:
            audio_path = download_audio(item, cache)
            text = whisper_transcribe(audio_path, {
                "title": item.get("title"),
                "show_id": item.get("channel_id"),
                "description": item.get("description"),
            })
            if not text:
                raise RuntimeError("Whisper returned no transcript")
            result = finalize_transcript(item, text)
            if result.get("status") == "transcribed":
                item["status"] = "done"
                item["completed_at"] = now_stamp()
                _mark_caption_done(str(item["video_id"]))
            else:
                item["status"] = "rejected"
                item["reasons"] = result.get("reasons") or []
            results.append({"video_id": item.get("video_id"), **result})
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            item["last_error"] = str(exc)[:300]
            if int(item.get("attempts") or 0) >= MAX_ATTEMPTS:
                item["status"] = "failed"
            results.append({"video_id": item.get("video_id"), "status": item["status"],
                            "error": item["last_error"]})
        finally:
            if audio_path and audio_path.exists():
                try:
                    audio_path.unlink()
                except OSError:
                    pass
            save_backlog(doc)
    if cache.is_dir() and not any(cache.iterdir()):
        cache.rmdir()
    return {
        "attempted": len(results),
        "pending": doc.get("pending_count", 0),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue-only", action="store_true")
    parser.add_argument("--batch", type=int, default=4)
    args = parser.parse_args()
    result = queue_no_caption_videos() if args.queue_only else drain(batch=args.batch)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
