#!/usr/bin/env python3
"""Apply company-name repair to transcripts already on disk.

New transcripts are repaired at write time by fetch_one, but the corpus already
holds transcripts produced before that existed -- including 361 written with the
`base` model, which mangles names considerably worse than the current default.
Those are the ones entity resolution has been silently missing.

Idempotent: running twice changes nothing the second time, because a repaired
transcript already contains the canonical spelling. Safe to re-run after adding
names to the security master.

    python _system/scripts/repair_transcript_names_backfill.py --dry-run
    python _system/scripts/repair_transcript_names_backfill.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from transcript_names import expected_names, repair  # noqa: E402
from vault_paths import podcasts_root  # noqa: E402


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def run(*, dry_run: bool = False, limit: int | None = None) -> dict:
    root = podcasts_root(create=True)
    changed = 0
    scanned = 0
    total_fixes = 0
    by_name: dict[str, int] = {}
    examples: list[str] = []

    for meta_path in sorted((root / "episodes").rglob("*.meta.json")):
        txt_path = meta_path.with_name(meta_path.name.replace(".meta.json", ".txt"))
        if not txt_path.exists():
            continue
        meta = load_json(meta_path) or {}
        # Only speech transcripts. A scraped show-notes page has no mangled
        # names to repair and every "fix" there would be noise.
        if meta.get("transcript_source") != "whisper":
            continue
        scanned += 1
        if limit is not None and changed >= limit:
            break

        text = txt_path.read_text(encoding="utf-8", errors="ignore")
        # Title only -- see repair_transcript_names in fetch_podcast_transcript.
        expected = expected_names(meta.get("title") or "")
        fixed, counts = repair(text, expected)
        if not counts or fixed == text:
            continue

        changed += 1
        total_fixes += sum(counts.values())
        for name, n in counts.items():
            by_name[name] = by_name.get(name, 0) + n
        if len(examples) < 12:
            examples.append(f"{(meta.get('title') or '')[:48]} -> {counts}")

        if dry_run:
            continue
        txt_path.write_text(fixed, encoding="utf-8")
        prior = meta.get("name_repairs") or {}
        merged = dict(prior)
        for name, n in counts.items():
            merged[name] = merged.get(name, 0) + n
        meta["name_repairs"] = merged
        meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    return {
        "scanned": scanned,
        "changed": changed,
        "total_fixes": total_fixes,
        "by_name": dict(sorted(by_name.items(), key=lambda kv: -kv[1])[:20]),
        "examples": examples,
        "dry_run": dry_run,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run", action="store_true", help="Report without writing.")
    p.add_argument("--limit", type=int, default=None, help="Stop after this many changed files.")
    args = p.parse_args()
    print(json.dumps(run(dry_run=args.dry_run, limit=args.limit), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
