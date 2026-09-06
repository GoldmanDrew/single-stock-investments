#!/usr/bin/env python3
"""Run the YouTube research lane end to end, on this host rather than in CI.

The lane was written for `youtube-refresh.yml`, which pins itself to a
`self-hosted, linux, youtube-egress` runner so caption traffic leaves from a
stable residential IP instead of a hosted datacenter one. That runner was never
registered: `GET /actions/runners` returns zero, so every scheduled run has sat
`queued` until the next night's run displaced it. The lane has therefore never
executed in CI at all, while reading as "not failed" the whole time -- a queued
job shows no red X anywhere.

Registering that runner was considered and rejected on 2026-09-06. This
repository is **public**, and a self-hosted runner on a public repository lets
any fork pull request execute code on the host. The host in question is the
operator's workstation: it holds `_secrets/`, a research-vault push token, and
sits on the same network as the trading systems. The egress IP the label exists
to provide is this machine's already, so running the lane directly gives up
nothing and removes the exposure entirely.

**Runs from its own worktree, not the primary checkout.** Concurrent agents
share the main working tree here, and a lane that stages files into a shared
index eventually has them swept into somebody else's commit. `git worktree`
gives a separate index and HEAD while sharing the 21 GB object store, so
isolation costs ~1 GB of sparse checkout rather than a 14 GB second clone.
The worktree pulls `main` at the start of every run: the NY4 hub is a file copy
with no `.git`, and the silent drift that produced is not worth repeating.

**Whisper is opt-in and off by default.** The CI job routes caption-less videos
through local Whisper at `--batch 4`. On this box that would be a third
competitor for memory alongside the podcast Whisper backfill and the analysis
batch, which already leave under 1 GB free; the analyser's own logs show it
waiting on a 600 MB floor. Videos without captions are queued and left queued
until someone asks for them.

    python _system/scripts/youtube_lane.py            # discover -> captions -> publish
    python _system/scripts/youtube_lane.py --hours 2  # longer caption window
    python _system/scripts/youtube_lane.py --whisper 4 --no-push
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

# A video title carries whatever the uploader typed, and cp1252 is what Python
# picks for a redirected stdout on Windows. A U+2060 in a podcast title killed
# an analysis run on 2026-08-29 -- the line reporting success was the crash.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from vault_git import clear_stale_git_state, run_git, vault_lock  # noqa: E402
from vault_paths import videos_root  # noqa: E402

# Written by publish_video_dashboard.py and read by the dashboard. Listed
# explicitly rather than added with `git add -A`: this worktree tracks main, and
# a broad add here would commit whatever else a pull happened to leave behind.
MAIN_PATHS = (
    "dashboard/data/insights/manifest.json",
    "dashboard/data/insights/videos.json",
    "_system/reference/video/insights_index_mirror.json",
)


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(message: str) -> None:
    print(f"[{stamp()}] {message}", flush=True)


def load_env_file(path: Path) -> int:
    """Read `export KEY='value'` lines into os.environ. Returns keys set.

    The secrets files use shell syntax because they are also `source`d by hand;
    quoting is single because Google key material is base64-ish and contains
    characters bash would otherwise expand.
    """
    if not path.is_file():
        return 0
    pattern = re.compile(r"^\s*(?:export\s+)?([A-Z0-9_]+)\s*=\s*(.*?)\s*$")
    count = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = pattern.match(line)
        if not match:
            continue
        key, raw = match.group(1), match.group(2)
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "'\"":
            raw = raw[1:-1]
        os.environ[key] = raw
        count += 1
    return count


def step(name: str, args: list[str], *, required: bool, timeout: float | None = None) -> bool:
    """Run one stage. A non-required stage that fails does not end the run.

    `timeout` exists for the caption stage and is not a safety net there, it is
    the actual bound. `fetch_video_transcript --daemon --hours N` checks its
    deadline *between* passes, and a single pass walks the whole pending
    backlog waiting for a pacing slot -- 153 items at 20/hour is about seven
    and a half hours. Left to run, it would be killed by the task's execution
    limit and score/build/publish/commit would never happen, stranding fetched
    captions uncommitted in the vault until the next day's run.
    """
    log(f"-> {name}")
    try:
        proc = subprocess.run([sys.executable, "-u", *args], cwd=ROOT, timeout=timeout)
    except subprocess.TimeoutExpired:
        # Nothing is lost: the backlog is persisted per item, and a fetch cut
        # short counts as transient, which this lane deliberately never charges
        # against an item's retry budget.
        log(f"{name} hit its {timeout:.0f}s budget; moving on")
        return True
    if proc.returncode == 0:
        return True
    level = "FAILED" if required else "failed (continuing)"
    log(f"{name} {level}: exit {proc.returncode}")
    return False


def self_update() -> None:
    """Pull main into this worktree so the lane runs current code.

    autoStash because the worktree carries `_secrets/` and whatever a previous
    run left behind; a plain rebase refuses outright when anything is unstaged,
    which is how the podcast analysis batch once analysed two episodes and
    pushed neither.

    The three published paths are reset first, and that is not tidiness. They
    are derived output -- `publish_video_dashboard.py` rebuilds them from the
    vault every run -- and the daily data pipeline rewrites the same
    `videos.json` on main (HEAD's copy was regenerated at 08:36Z on
    2026-09-06). Carrying a local edit to a file the upstream also edits is how
    an autostash pop turns into a conflict, and a conflict here would strand
    the worktree rather than merely skip an update. Discarding costs nothing:
    the corpus they are derived from is committed in the vault.
    """
    for rel in MAIN_PATHS:
        if (ROOT / rel).is_file():
            run_git(ROOT, "checkout", "--", rel, check=False, timeout=120)
    try:
        run_git(ROOT, "-c", "rebase.autoStash=true", "pull", "--rebase",
                "origin", "main", timeout=900)
        log("worktree updated from origin/main")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        # Running slightly stale beats not running. Say so rather than dying.
        log(f"self-update skipped: {type(exc).__name__} {str(exc)[:160]}")
        run_git(ROOT, "rebase", "--abort", check=False, timeout=120)


def push_vault(message: str) -> bool:
    """Commit the videos/ subtree of the shared vault.

    The Whisper backfill and the analysis batch commit to this same clone every
    few minutes. Two git processes in one repository collide on .git/index.lock,
    and that collision wedged the vault for fourteen hours on 2026-08-31, so the
    same advisory lock those two take is taken here.
    """
    repo = videos_root().parent
    try:
        with vault_lock(repo, owner="youtube_lane", log=lambda m: log(m.strip())):
            clear_stale_git_state(repo, log=lambda m: log(m.strip()))
            run_git(repo, "add", "-A", "videos", timeout=300)
            staged = run_git(repo, "diff", "--cached", "--quiet", check=False, timeout=120)
            if staged.returncode == 0:
                log("vault: nothing to commit")
                return False
            run_git(repo, "commit", "-m", message, timeout=300)
            run_git(repo, "-c", "rebase.autoStash=true", "pull", "--rebase",
                    "origin", "main", timeout=900)
            run_git(repo, "push", "origin", "main", timeout=600)
            log("vault: pushed")
            return True
    except TimeoutError as exc:
        log(f"vault lock: {exc}; skipping this push")
        return False
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        log(f"vault push failed: {str(exc)[:200]}")
        run_git(repo, "rebase", "--abort", check=False, timeout=120)
        clear_stale_git_state(repo, log=lambda m: log(m.strip()))
        return False


def push_main(message: str) -> bool:
    """Commit the published video shard to this repository's main."""
    try:
        present = [p for p in MAIN_PATHS if (ROOT / p).is_file()]
        if not present:
            log("main: no published shard to commit")
            return False
        run_git(ROOT, "add", "--sparse", *present, timeout=300)
        staged = run_git(ROOT, "diff", "--cached", "--quiet", check=False, timeout=120)
        if staged.returncode == 0:
            log("main: nothing to commit")
            return False
        run_git(ROOT, "commit", "-m", message, timeout=300)
        run_git(ROOT, "-c", "rebase.autoStash=true", "pull", "--rebase",
                "origin", "main", timeout=900)
        run_git(ROOT, "push", "origin", "main", timeout=600)
        log("main: pushed")
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        log(f"main push failed: {str(exc)[:200]}")
        run_git(ROOT, "rebase", "--abort", check=False, timeout=120)
        return False


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--hours", type=float, default=1.0,
                   help="Caption daemon window. Pacing is 150s between fetches "
                        "and 20/hour, so this is mostly a wait (default %(default)s).")
    p.add_argument("--whisper", type=int, default=0,
                   help="Videos to route through local Whisper. 0 queues them "
                        "and transcribes none, which is the default because "
                        "this host is already memory-bound.")
    p.add_argument("--no-push", action="store_true", help="Run, commit nothing.")
    p.add_argument("--no-update", action="store_true", help="Skip the worktree pull.")
    args = p.parse_args()

    scripts = ROOT / "_system" / "scripts"
    keys = load_env_file(ROOT / "_secrets" / "youtube.env")
    if not os.environ.get("YOUTUBE_API_KEY"):
        log("YOUTUBE_API_KEY is not set; discovery cannot run")
        return 2
    log(f"loaded {keys} key(s) from _secrets/youtube.env")
    log(f"vault -> {videos_root()}")

    if not args.no_update:
        self_update()

    # Discovery is cheap (playlistItems at 1 unit per 50 videos against a
    # 10,000/day free tier) but it is also the only stage that can add work.
    # If it fails there is nothing new to fetch, so the rest still runs against
    # whatever the backlog already holds.
    step("discover", [str(scripts / "discover_videos.py")], required=False)
    # --hours is passed as well as enforced: the daemon uses it to stop cleanly
    # at a pass boundary when it can, and the wall-clock budget catches the case
    # where a single pass outlives the window. A small margin so the clean exit
    # wins whenever it is available.
    step("captions", [str(scripts / "fetch_video_transcript.py"),
                      "--daemon", "--hours", str(args.hours)],
         required=False, timeout=args.hours * 3600 + 300)

    whisper_args = [str(scripts / "video_whisper_backfill.py")]
    whisper_args += ["--queue-only"] if args.whisper <= 0 else ["--batch", str(args.whisper)]
    step("whisper", whisper_args, required=False)

    # Relevance is decided on the transcript, never on metadata, so scoring has
    # to follow the fetch rather than gate it.
    step("score", [str(scripts / "score_video_relevance.py")], required=False)
    if not step("build", [str(scripts / "build_video_insights.py")], required=True):
        return 1

    if not args.no_push:
        push_vault(f"chore(videos): transcript refresh {stamp()}")

    # The shard is what the dashboard actually reads. A stage that writes must
    # name its reader, so publishing runs even under --no-push: skipping it
    # there would make a dry run silently stop one stage short of the thing
    # most likely to break, which is the whole reason to have a dry run.
    # Ordered after the vault commit so a failed publish cannot leave the
    # corpus uncommitted.
    published = step("publish", [str(scripts / "publish_video_dashboard.py")], required=True)
    if args.no_push:
        log("--no-push: ran the chain, committed nothing")
        return 0 if published else 1
    if published:
        push_main(f"chore(videos): publish admitted research {stamp()}")
    return 0 if published else 1


if __name__ == "__main__":
    raise SystemExit(main())
