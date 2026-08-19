#!/usr/bin/env python3
"""Resumable Whisper backfill for the podcast transcript corpus.

The weekly CI lane drains 20 items. The backlog is 1,515 pending, and it grows
as shows publish, so that cadence never converges -- roughly 78 weeks against a
moving target. Raising the CI batch does not help either: the job has a wall
clock and lands nothing when it overruns, which is exactly how run 32280009523
threw away two hours of work.

So this runs off CI, on the host that is already up for the trading hub, and is
built to be interrupted. Every design choice here follows from one fact: audio
transcription is slow, and any process that must run for days will be killed at
some point.

  * State lives in the vault's whisper_backlog.json, which drain_whisper_backlog
    already updates per item. Killing this process mid-episode loses that one
    episode, never the run.
  * Results are pushed to the vault on an interval. An unpushed transcript is
    an unbacked-up transcript, and a host rebuild would lose the lot.
  * Items that keep failing are parked rather than retried forever, so one dead
    audio URL cannot consume the whole budget.
  * It yields to the trading hub. This is background work; an order preview has
    a 10-second quote budget and must never queue behind a transcription.

Usage:
    python _system/scripts/whisper_backfill_daemon.py --until-empty
    python _system/scripts/whisper_backfill_daemon.py --hours 8 --chunk 25
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from vault_paths import podcasts_root  # noqa: E402

# An item that has failed this many times is almost always a dead audio URL or a
# format faster-whisper cannot open. Parking it keeps the queue moving.
MAX_ATTEMPTS = 4
DEFAULT_CHUNK = 25
# Offsite cadence. Transcripts are on local disk the moment they are written --
# atomic_write_text() fsyncs them -- so this interval bounds only what a *disk*
# or machine loss costs, not a process crash. Fifteen minutes is a handful of
# episodes; pushing much more often spends more time in git than in Whisper.
DEFAULT_PUSH_MINUTES = 15
# Also push once this many episodes have landed, so a fast stretch does not sit
# unbacked-up waiting for the clock.
PUSH_EVERY_ITEMS = 10

# Set by the signal handler so a stop request finishes the episode in flight and
# pushes, instead of losing it.
_stop_requested = False


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp() -> str:
    return _now().strftime("%Y-%m-%dT%H:%M:%SZ")


def backlog_path() -> Path:
    return podcasts_root(create=True) / "whisper_backlog.json"


def read_backlog() -> dict:
    path = backlog_path()
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"items": []}


def counts(doc: dict) -> dict[str, int]:
    tally: dict[str, int] = {}
    for item in doc.get("items") or []:
        status = str(item.get("status") or "unknown")
        if status == "pending" and int(item.get("attempts") or 0) >= MAX_ATTEMPTS:
            status = "parked"
        tally[status] = tally.get(status, 0) + 1
    return tally


def park_exhausted(doc: dict) -> int:
    """Mark repeatedly-failing items so they stop being selected."""
    parked = 0
    for item in doc.get("items") or []:
        if item.get("status") == "pending" and int(item.get("attempts") or 0) >= MAX_ATTEMPTS:
            item["status"] = "parked"
            item["parked_at"] = _stamp()
            parked += 1
    if parked:
        from fetch_podcast_transcript import atomic_write_text

        doc["updated_at"] = _stamp()
        # Same rule as everywhere else: this file is the resume index for the
        # whole backlog, so it is never left half-written.
        atomic_write_text(backlog_path(), json.dumps(doc, indent=2) + "\n")
    return parked


def vault_push(message: str) -> bool:
    """Commit and push the vault. A transcript only on this disk is not safe."""
    vault = podcasts_root(create=False)
    if vault is None:
        return False
    repo = vault.parent
    if not (repo / ".git").is_dir():
        return False
    try:
        subprocess.run(["git", "add", "-A", "podcasts"], cwd=repo, check=True,
                       capture_output=True, timeout=300)
        staged = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo,
                                capture_output=True, timeout=60)
        if staged.returncode == 0:
            return False  # nothing new
        subprocess.run(["git", "commit", "-m", message], cwd=repo, check=True,
                       capture_output=True, timeout=300)
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], cwd=repo,
                       check=True, capture_output=True, timeout=600)
        subprocess.run(["git", "push", "origin", "HEAD:main"], cwd=repo, check=True,
                       capture_output=True, timeout=600)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        # A failed push must not stop transcription; the next interval retries and
        # the work is still on disk.
        print(f"  vault push failed ({exc.__class__.__name__}); continuing", flush=True)
        return False


def install_stop_handlers() -> None:
    """Turn systemd stop / Ctrl-C into a clean finish rather than a lost episode."""
    import signal

    def handler(signum, _frame):
        global _stop_requested
        if _stop_requested:
            # Second signal: the operator means now.
            raise KeyboardInterrupt
        _stop_requested = True
        print(f"[{_stamp()}] stop requested (signal {signum}); "
              "finishing the current chunk and pushing before exit", flush=True)

    for name in ("SIGTERM", "SIGINT", "SIGHUP"):
        sig = getattr(signal, name, None)
        if sig is not None:
            try:
                signal.signal(sig, handler)
            except (ValueError, OSError):
                pass


def run(*, chunk: int, deadline: datetime | None, until_empty: bool, push: bool,
        push_minutes: int) -> int:
    from fetch_podcast_transcript import drain_whisper_backlog

    started = _now()
    last_push = started
    done_this_run = 0
    since_push = 0
    push_seconds = max(60, push_minutes * 60)

    parked = park_exhausted(read_backlog())
    if parked:
        print(f"parked {parked} items at >= {MAX_ATTEMPTS} attempts", flush=True)

    while True:
        doc = read_backlog()
        tally = counts(doc)
        pending = tally.get("pending", 0)
        elapsed = _now() - started
        print(
            f"[{_stamp()}] pending={pending} done={tally.get('done', 0)} "
            f"parked={tally.get('parked', 0)} transcribed_this_run={done_this_run} "
            f"elapsed={str(elapsed).split('.')[0]}",
            flush=True,
        )

        if pending == 0:
            print("backlog empty", flush=True)
            break
        if _stop_requested:
            print("stopping on request", flush=True)
            break
        if deadline and _now() >= deadline:
            print("time budget reached; stopping cleanly", flush=True)
            break
        if not until_empty and not deadline:
            break

        before = counts(read_backlog()).get("done", 0)
        try:
            drain_whisper_backlog(batch=chunk)
        except KeyboardInterrupt:
            print("interrupted; state is checkpointed in whisper_backlog.json", flush=True)
            break
        except Exception as exc:
            # One bad chunk should not end a multi-day run.
            print(f"  chunk failed: {exc.__class__.__name__}: {exc}", flush=True)
            time.sleep(30)
            continue
        landed = max(0, counts(read_backlog()).get("done", 0) - before)
        done_this_run += landed
        since_push += landed

        park_exhausted(read_backlog())

        # Push on whichever comes first: the clock, or enough finished episodes
        # to be worth protecting. Either way the local copy is already durable.
        due = (_now() - last_push).total_seconds() >= push_seconds or since_push >= PUSH_EVERY_ITEMS
        if push and due:
            if vault_push(f"chore(podcasts): whisper backfill {_stamp()}"):
                print(f"  pushed vault ({since_push} episodes)", flush=True)
            last_push = _now()
            since_push = 0

    if push and vault_push(f"chore(podcasts): whisper backfill {_stamp()}"):
        print("pushed vault (final)", flush=True)

    final = counts(read_backlog())
    print(json.dumps({"transcribed_this_run": done_this_run, **final}, indent=2), flush=True)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--chunk", type=int, default=DEFAULT_CHUNK,
                   help=f"Items per drain call (default {DEFAULT_CHUNK}). State is saved per item, "
                        "so this only controls reporting granularity.")
    p.add_argument("--hours", type=float, default=None, help="Stop cleanly after this many hours.")
    p.add_argument("--until-empty", action="store_true", help="Run until the backlog is drained.")
    p.add_argument("--no-push", action="store_true", help="Do not commit/push the vault.")
    p.add_argument("--status", action="store_true", help="Print backlog counts and exit.")
    p.add_argument("--push-every-minutes", type=int, default=DEFAULT_PUSH_MINUTES,
                   help=f"Offsite push cadence (default {DEFAULT_PUSH_MINUTES}). Bounds what a "
                        "disk or machine loss costs; local writes are already fsynced.")
    args = p.parse_args()

    if args.status:
        doc = read_backlog()
        print(json.dumps({"path": str(backlog_path()), **counts(doc)}, indent=2))
        return 0

    if not args.until_empty and args.hours is None:
        p.error("choose --until-empty or --hours (or --status)")

    deadline = _now() + timedelta(hours=args.hours) if args.hours else None
    # Background work. An order preview has a 10s quote budget and must never
    # wait behind a transcription on the same host.
    if hasattr(os, "nice"):
        try:
            os.nice(15)
        except OSError:
            pass
    install_stop_handlers()
    return run(chunk=args.chunk, deadline=deadline, until_empty=args.until_empty,
               push=not args.no_push, push_minutes=args.push_every_minutes)


if __name__ == "__main__":
    raise SystemExit(main())
