#!/usr/bin/env python3
"""Publish only the YouTube catalog shard without rebuilding unrelated feeds."""
from __future__ import annotations

import json
from pathlib import Path

from build_video_insights import INDEX_MIRROR_PATH, build_catalog
from vault_paths import videos_root

ROOT = Path(__file__).resolve().parents[2]
INSIGHTS_DIR = ROOT / "dashboard" / "data" / "insights"
MANIFEST_PATH = INSIGHTS_DIR / "manifest.json"
SHARD_PATH = INSIGHTS_DIR / "videos.json"


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_json(path: Path, value: dict, *, compact: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = (
        json.dumps(value, separators=(",", ":"), ensure_ascii=False)
        if compact
        else json.dumps(value, indent=2, ensure_ascii=False)
    ) + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def publish(root: Path | None = None) -> dict:
    catalog = build_catalog(root or videos_root(create=True))
    shard = {
        "generated_at": catalog.get("generated_at"),
        "video_index": catalog.get("video_index") or [],
        "video_by_channel": catalog.get("video_by_channel") or {},
        "video_status_counts": catalog.get("status_counts") or {},
        "video_newest_published": catalog.get("newest_published"),
    }
    write_json(SHARD_PATH, shard)
    write_json(INDEX_MIRROR_PATH, catalog, compact=False)

    manifest = load_json(MANIFEST_PATH)
    manifest["video_count"] = catalog.get("video_count", 0)
    manifest.setdefault("shards", {})["videos"] = "data/insights/videos.json"
    health = manifest.setdefault("source_health", {})
    health["videos"] = {
        "status": "ok" if catalog.get("video_count") else "empty",
        "items": catalog.get("video_count", 0),
        "as_of": catalog.get("newest_published"),
        "generated_at": catalog.get("generated_at"),
        "status_counts": catalog.get("status_counts") or {},
        "path": "_system/reference/video/insights_index_mirror.json",
    }
    write_json(MANIFEST_PATH, manifest)
    return catalog


def main() -> int:
    catalog = publish()
    print(
        f"video dashboard: {catalog.get('video_count', 0)} admitted, "
        f"newest={catalog.get('newest_published') or 'none'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
