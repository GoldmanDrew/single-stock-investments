#!/usr/bin/env python3
"""One-shot podcast pipeline: discover → fetch → resolve/build → summarize → insights merge."""
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
    args = p.parse_args()

    py = sys.executable
    discover_cmd = [py, str(SCRIPTS / "discover_podcasts.py")]
    if args.no_search:
        discover_cmd.append("--no-search")
    rc = run(discover_cmd)
    if rc != 0:
        return rc

    fetch_cmd = [py, str(SCRIPTS / "fetch_podcast_transcript.py")]
    if args.no_whisper:
        fetch_cmd.append("--no-whisper")
    if args.fetch_limit is not None:
        fetch_cmd.extend(["--limit", str(args.fetch_limit)])
    rc = run(fetch_cmd)
    if rc != 0:
        return rc

    for script in (
        "build_officer_directory.py",
        "build_podcast_insights.py",
        "summarize_podcast_episode.py",  # writes highlights to *.meta.json only
        "build_podcast_insights.py",  # rebuild vault catalog + slim CI index from meta
    ):
        rc = run([py, str(SCRIPTS / script)])
        if rc != 0:
            return rc

    if not args.skip_dashboard:
        rc = run([py, str(SCRIPTS / "build_insights.py")])
        if rc != 0:
            return rc
    print(f"OK podcast_cloud_refresh date={args.date}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
