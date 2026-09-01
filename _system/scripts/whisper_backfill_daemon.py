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
# Consecutive rounds that transcribe nothing before the loop gives up. Each
# barren round doubles the wait, so this rides out a short blip but refuses to
# grind through the backlog while the network is down.
BARREN_ROUNDS_BEFORE_STOP = 6
BARREN_BACKOFF_BASE = 30
BARREN_BACKOFF_CAP = 900

# Set by the signal handler so a stop request finishes the episode in flight and
# pushes, instead of losing it.
_stop_requested = False


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp() -> str:
    return _now().strftime("%Y-%m-%dT%H:%M:%SZ")


def backlog_path() -> Path:
    return podcasts_root(create=True) / "whisper_backlog.json"


class BacklogUnreadable(RuntimeError):
    """The queue file exists but cannot be parsed."""


def read_backlog() -> dict:
    """Read the queue, failing loudly rather than with a JSON traceback.

    A days-long run can find this file broken by something other than its own
    writes -- an abandoned git rebase leaves conflict markers in it, which is
    exactly how the 2026-08-20 run died. The message needs to say that, because
    a JSONDecodeError at line 17810 does not.
    """
    path = backlog_path()
    if not path.exists():
        return {"items": []}
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        if "<<<<<<<" in text or ">>>>>>>" in text:
            raise BacklogUnreadable(
                f"{path} contains git conflict markers, so a rebase was left unfinished. "
                "Run `git rebase --abort` in the vault, confirm the file parses, then restart."
            ) from exc
        raise BacklogUnreadable(f"{path} is not valid JSON: {exc}") from exc


def counts(doc: dict) -> dict[str, int]:
    tally: dict[str, int] = {}
    for item in doc.get("items") or []:
        status = str(item.get("status") or "unknown")
        if status == "pending" and int(item.get("attempts") or 0) >= MAX_ATTEMPTS:
            status = "parked"
        tally[status] = tally.get(status, 0) + 1
    return tally


def reconcile_with_disk(doc: dict) -> int:
    """Mark done any pending item whose transcript is already on disk.

    The backlog is the resume index, but the transcripts are the truth. The two
    drift apart whenever this file is merged textually instead of semantically --
    `_merge_backlog` unions the two sides on push, but a rebase done by hand
    takes one side wholesale and silently discards the other's done-markings.

    That happened on 2026-08-25 and the failure mode is expensive rather than
    loud: eight episodes sat `pending` with their transcripts already written, so
    every chunk re-downloaded and re-transcribed roughly fifty minutes of audio
    each, landed nothing new, and reported a barren round. Six barren rounds stop
    the daemon, and four attempts park the episode -- so left alone this parks
    work that was already finished.

    Cheap to check (a stat per pending item) and it runs before every round, so
    the drift can only cost one round rather than the run.
    """
    root = podcasts_root(create=True)
    episodes = root / "episodes"
    healed = 0
    for item in doc.get("items") or []:
        if item.get("status") != "pending":
            continue
        eid = item.get("episode_id")
        if not eid:
            continue
        published = str(item.get("published") or "")
        year = published[:4] if published[:4].isdigit() else None
        candidate = episodes / year / f"{eid}.txt" if year else None
        if candidate is None or not candidate.exists():
            matches = list(episodes.rglob(f"{eid}.txt"))
            candidate = matches[0] if matches else None
        if candidate is None or not candidate.exists():
            continue
        item["status"] = "done"
        item["reconciled_at"] = _stamp()
        healed += 1
    if healed:
        from fetch_podcast_transcript import atomic_write_text

        doc["updated_at"] = _stamp()
        atomic_write_text(backlog_path(), json.dumps(doc, indent=2) + "\n")
    return healed


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


def _git(repo: Path, *args, check: bool = True, timeout: int = 300):
    # run_git rather than subprocess.run: a timeout must kill git's children
    # too. `git fetch` spawns git-remote-https, which is what holds the socket
    # and .git/index.lock, and killing only the parent is how a 900-second
    # timeout produced a 27-minute hang and a wedged vault on 2026-08-31.
    from vault_git import run_git  # noqa: WPS433

    return run_git(repo, *args, check=check, timeout=timeout)


def _merge_backlog(base_text: str, other_text: str) -> str:
    """Union two backlog states. Progress wins on both sides.

    The daemon and CI both mark items in this file, so a textual merge collides
    every time they both do work. The semantics are simple though: an episode
    transcribed anywhere is transcribed, and attempts only ever go up.
    """
    base = json.loads(base_text)
    other = json.loads(other_text)
    rank = {"done": 3, "parked": 2, "pending": 1}
    merged: dict[str, dict] = {}
    for item in (base.get("items") or []) + (other.get("items") or []):
        key = item.get("episode_id")
        if not key:
            continue
        seen = merged.get(key)
        if seen is None:
            merged[key] = dict(item)
            continue
        if rank.get(item.get("status"), 0) > rank.get(seen.get("status"), 0):
            seen["status"] = item["status"]
        seen["attempts"] = max(int(seen.get("attempts") or 0), int(item.get("attempts") or 0))
    items = list(merged.values())
    return json.dumps({
        "items": items,
        "pending_count": sum(1 for i in items if i.get("status") == "pending"),
        "updated_at": _stamp(),
    }, indent=2) + "\n"


def _resolve_corpus_conflicts(repo: Path) -> bool:
    """Resolve a rebase conflict inside podcasts/ by keeping progress.

    During a rebase, stage 2 (--ours) is the upstream being rebased onto and
    stage 3 (--theirs) is the commit being replayed -- this run's work. Anything
    outside podcasts/ is not ours to decide, and returns False so the caller
    aborts rather than guessing.
    """
    conflicted = [line for line in _git(repo, "diff", "--name-only", "--diff-filter=U")
                  .stdout.splitlines() if line.strip()]
    if not conflicted:
        return False
    for path in conflicted:
        if not path.startswith("podcasts/"):
            print(f"  conflict outside the corpus ({path}); not resolving", flush=True)
            return False
        if path.endswith("whisper_backlog.json"):
            upstream = _git(repo, "show", f":2:{path}", check=False).stdout
            local = _git(repo, "show", f":3:{path}", check=False).stdout
            try:
                (repo / path).write_text(_merge_backlog(upstream, local), encoding="utf-8")
            except (json.JSONDecodeError, ValueError):
                return False
        else:
            # Transcripts, episode metadata and run summaries: this run just
            # wrote them, so the replayed side is the newer truth.
            _git(repo, "checkout", "--theirs", "--", path, check=False)
        _git(repo, "add", "--", path)
    return True


def vault_push(message: str) -> bool:
    """Commit and push the vault. A transcript only on this disk is not safe."""
    vault = podcasts_root(create=False)
    if vault is None:
        return False
    repo = vault.parent
    if not (repo / ".git").is_dir():
        return False
    # The local-model analyser commits to this same tree every 20 minutes.
    # One writer at a time; see vault_git for what their collisions cost.
    from vault_git import clear_stale_git_state, vault_lock  # noqa: WPS433

    try:
        with vault_lock(repo, owner="whisper_backfill_daemon", log=print):
            clear_stale_git_state(repo, log=print)
            return _push_vault_locked(repo, message)
    except TimeoutError as exc:
        print(f"  vault lock: {exc}; skipping this push", flush=True)
        return False


def _push_vault_locked(repo: Path, message: str) -> bool:
    try:
        subprocess.run(["git", "add", "-A", "podcasts"], cwd=repo, check=True,
                       capture_output=True, timeout=300)
        staged = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo,
                                capture_output=True, timeout=60)
        if staged.returncode == 0:
            return False  # nothing new
        subprocess.run(["git", "commit", "-m", message], cwd=repo, check=True,
                       capture_output=True, timeout=300)
        for attempt in range(1, 4):
            _git(repo, "fetch", "origin", "main", timeout=600)
            # autoStash because the vault is a shared tree: other lanes routinely
            # leave unstaged edits in it, and a plain rebase refuses to run with a
            # dirty worktree.
            rebase = _git(repo, "-c", "rebase.autoStash=true", "rebase", "origin/main",
                          check=False, timeout=600)
            while rebase.returncode != 0:
                # A conflict here is expected, not exceptional: CI writes the same
                # backlog and metadata this run does. Resolve by keeping progress
                # from both sides, and never leave the worktree mid-rebase -- an
                # abandoned rebase writes conflict markers into whisper_backlog.json,
                # and the next read of it fails to parse, taking the run down.
                if not _resolve_corpus_conflicts(repo):
                    _git(repo, "rebase", "--abort", check=False)
                    print("  vault rebase hit a conflict it should not resolve; aborted cleanly",
                          flush=True)
                    return False
                rebase = _git(repo, "-c", "core.editor=true", "rebase", "--continue",
                              check=False, timeout=600)
            if _git(repo, "push", "origin", "HEAD:main", check=False, timeout=600).returncode == 0:
                return True
            print(f"  vault push rejected (attempt {attempt}/3); refetching", flush=True)
        return False
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        # Transcription must survive a push failure -- the work is on disk and the
        # next interval retries -- but only from a clean tree.
        from vault_git import clear_stale_git_state  # noqa: WPS433

        _git(repo, "rebase", "--abort", check=False)
        clear_stale_git_state(repo, log=print)
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
    barren_rounds = 0
    push_seconds = max(60, push_minutes * 60)

    healed = reconcile_with_disk(read_backlog())
    if healed:
        print(f"reconciled {healed} pending items that were already transcribed", flush=True)
    parked = park_exhausted(read_backlog())
    if parked:
        print(f"parked {parked} items at >= {MAX_ATTEMPTS} attempts", flush=True)

    while True:
        reconcile_with_disk(read_backlog())
        doc = read_backlog()
        tally = counts(doc)
        pending = tally.get("pending", 0)
        elapsed = _now() - started
        # Print EVERY status. The first real run buried 696 episodes as
        # "failed" while this line showed only pending/done/parked, so the
        # damage was invisible for five hours.
        breakdown = " ".join(f"{name}={count}" for name, count in sorted(tally.items()))
        print(
            f"[{_stamp()}] {breakdown} transcribed_this_run={done_this_run} "
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
        before_failed = counts(read_backlog()).get("failed", 0)
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
        after = counts(read_backlog())
        landed = max(0, after.get("done", 0) - before)
        done_this_run += landed
        since_push += landed

        # A whole chunk that transcribed nothing is the signature of an
        # environment problem, not of bad episodes. Back off hard rather than
        # spinning: instant DNS failures let this loop chew through hundreds of
        # items a minute, which is exactly how one outage cost 696 of them.
        if landed == 0:
            barren_rounds += 1
            new_failures = after.get("failed", 0) - before_failed
            backoff = min(BARREN_BACKOFF_CAP, BARREN_BACKOFF_BASE * (2 ** (barren_rounds - 1)))
            print(
                f"  no episode landed this round (barren={barren_rounds}, "
                f"new permanent failures={new_failures}); sleeping {backoff}s",
                flush=True,
            )
            if barren_rounds >= BARREN_ROUNDS_BEFORE_STOP:
                print(
                    f"  {barren_rounds} barren rounds in a row -- stopping rather than "
                    "burning the queue. Check connectivity, then restart; nothing is lost.",
                    flush=True,
                )
                break
            time.sleep(backoff)
        else:
            barren_rounds = 0

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


def deprioritise() -> str:
    """Drop to the lowest useful scheduling priority, on either platform.

    os.nice does not exist on Windows, so the original `if hasattr(os, "nice")`
    guard silently did nothing there -- and this job now runs on a 16-core
    Windows workstation for days at a time, which is exactly where a greedy
    background process is felt. SetPriorityClass with BELOW_NORMAL keeps the
    machine responsive; IDLE would let it starve outright.
    """
    if hasattr(os, "nice"):
        try:
            os.nice(15)
            return "nice+15"
        except OSError:
            return "unchanged"
    try:
        import ctypes

        BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
        kernel32 = ctypes.windll.kernel32
        # GetCurrentProcess returns the pseudo-handle (HANDLE)-1. Without an
        # explicit restype ctypes truncates it to a 32-bit int and the call
        # fails with ERROR_INVALID_HANDLE while still looking like a normal
        # no-op -- which is how the original guard managed to do nothing twice.
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        kernel32.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        if kernel32.SetPriorityClass(kernel32.GetCurrentProcess(),
                                     BELOW_NORMAL_PRIORITY_CLASS):
            return "below-normal"
    except Exception:
        pass
    return "unchanged"


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
    deprioritise()
    install_stop_handlers()
    return run(chunk=args.chunk, deadline=deadline, until_empty=args.until_empty,
               push=not args.no_push, push_minutes=args.push_every_minutes)


if __name__ == "__main__":
    raise SystemExit(main())
