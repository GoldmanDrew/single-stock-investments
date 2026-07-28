#!/usr/bin/env python3
"""One-shot podcast pipeline: discover -> fetch -> resolve/build -> summarize -> insights merge."""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "_system" / "scripts"


def run(cmd: list[str]) -> int:
    print("+", " ".join(cmd), flush=True)
    return subprocess.call(cmd, cwd=str(ROOT))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--date", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    p.add_argument("--no-search", action="store_true", help="Skip discovery 2B search")
    p.add_argument("--no-whisper", action="store_true")
    p.add_argument("--fetch-limit", type=int, default=None)
    p.add_argument("--skip-dashboard", action="store_true")
    p.add_argument(
        "--all-watchlist",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Discover every watchlist RSS episode (default on).",
    )
    p.add_argument(
        "--backfill",
        action="store_true",
        help="Full harvest: all-watchlist discover, published-first fetch, queue Whisper backlog.",
    )
    p.add_argument(
        "--whisper-batch",
        type=int,
        default=20,
        help="Drain N Whisper backlog items after fetch (default 20; 0 to skip).",
    )
    args = p.parse_args()

    py = sys.executable
    discover_cmd = [py, str(SCRIPTS / "discover_podcasts.py"), "--paginate-capped-feeds"]
    if args.no_search or args.backfill:
        discover_cmd.append("--no-search")
    if args.all_watchlist:
        discover_cmd.append("--all-watchlist")
    else:
        discover_cmd.append("--no-all-watchlist")
    rc = run(discover_cmd)
    if rc != 0:
        return rc

    fetch_cmd = [py, str(SCRIPTS / "fetch_podcast_transcript.py")]
    if args.backfill:
        fetch_cmd.append("--backfill")
        # Published pass first; Whisper drained via --whisper-batch
        fetch_cmd.append("--no-whisper")
    elif args.no_whisper:
        fetch_cmd.append("--no-whisper")
    if args.fetch_limit is not None:
        fetch_cmd.extend(["--limit", str(args.fetch_limit)])
    rc = run(fetch_cmd)
    if rc != 0:
        return rc

    if args.whisper_batch and args.whisper_batch > 0:
        rc = run(
            [
                py,
                str(SCRIPTS / "fetch_podcast_transcript.py"),
                "--whisper-batch",
                str(args.whisper_batch),
            ]
        )
        if rc != 0:
            return rc

    for script in (
        "build_officer_directory.py",
        "build_podcast_insights.py",
        "summarize_podcast_episode.py",  # writes highlights/summary to *.meta.json only
        "build_podcast_insights.py",  # rebuild vault catalog + detail shards from meta
    ):
        rc = run([py, str(SCRIPTS / script)])
        if rc != 0:
            return rc

    if not args.skip_dashboard:
        rc = run([py, str(SCRIPTS / "build_insights.py")])
        if rc != 0:
            return rc
        # Ensure podcasts shard + episode detail shards are current
        rc = run(
            [
                py,
                "-c",
                (
                    "from pathlib import Path; "
                    "import sys; "
                    f"sys.path.insert(0, r'{SCRIPTS}'); "
                    "from build_dashboard_shards import write_insights_shards; "
                    "from build_podcast_insights import emit_episode_detail_shards; "
                    f"root = Path(r'{ROOT}'); "
                    "ins = root / 'dashboard' / 'data' / 'insights.json'; "
                    "import json; "
                    "doc = json.loads(ins.read_text(encoding='utf-8')) if ins.exists() else {}; "
                    "write_insights_shards(doc, root / 'dashboard' / 'data'); "
                    "n = emit_episode_detail_shards(); "
                    "print(f'shards ok detail={n}')"
                ),
            ]
        )
        if rc != 0:
            return rc
    print(f"OK podcast_cloud_refresh date={args.date} backfill={args.backfill}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
