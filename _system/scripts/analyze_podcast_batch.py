#!/usr/bin/env python3
"""Run the local-model analysis across the transcript corpus, safely and resumably.

Companion to analyze_podcast_episode.py, which handles one episode. This handles
the other 460 and the things that only matter at that scale: not losing work, not
redoing it, not starving the machine, and not being the reason a trading
workstation swaps.

**Resumable by content, not by name.** Each result records the SHA-1 of the
transcript it was derived from. An episode is skipped only when that hash still
matches, so re-transcribing an episode -- which this corpus does, as Whisper
drains and name repair rewrites -- correctly invalidates the old analysis
instead of silently keeping a summary of text that no longer exists.

**Checkpointed to the vault.** An unpushed result is an unbacked-up one. The
whisper daemon learned this the expensive way: transcripts sat locally for five
hours because its push interval was evaluated per chunk rather than per episode.
Here the interval is checked after every episode.

**Yields rather than competes.** Two things run on this box already -- the
whisper backfill on 12 CPU threads and llama-server holding the model. Available
memory was 1.4 GB when this was written, with commit charge at 84 of 99 GB. So
the loop checks free memory before each episode and waits rather than pushing the
machine into swap, and the process asks for BELOW_NORMAL priority. Inference
itself runs on the GPU, so the cost here is mostly waiting on HTTP; the guard is
for the case where that assumption stops holding.

**Single instance.** Two analysers over one corpus would duplicate work and race
each other's vault pushes, which is exactly what two whisper daemons did on
2026-08-25 -- a third of a night's transcription discarded.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

# Episode titles come from RSS feeds and carry whatever the publisher typed --
# en dashes, smart quotes, and on 2026-08-29 a U+2060 WORD JOINER that killed a
# run outright. Python picks cp1252 for a redirected stdout on Windows, so the
# progress line that *reports* a finished episode was the thing that crashed:
# 730 episodes still to do, the process gone, and the last log line a normal
# success. Same idiom as build_memory_digest.py.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from analyze_podcast_episode import analyze, build_aliases, scan_aliases  # noqa: E402
from llm_local import LocalLLMUnavailable  # noqa: E402
from vault_paths import podcasts_root  # noqa: E402
from vault_git import clear_stale_git_state, run_git, vault_lock  # noqa: E402

# Only episodes with genuine speech. Below this it is show notes or a scraped
# page, and there is nothing to extract a claim from.
MIN_TRANSCRIPT_BYTES = 25000
# Pause below this. Not a hard OOM limit -- a floor that keeps the box
# responsive. 600 rather than something larger because the model is already
# resident in llama-server and inference runs on the GPU: this process is a thin
# HTTP client needing ~150 MB, so a high floor would block on a machine that is
# merely well-used rather than actually short.
MIN_AVAILABLE_MB = int(os.environ.get("ANALYZE_MIN_AVAIL_MB", "600"))
MEMORY_WAIT_SECONDS = 120
DEFAULT_PUSH_MINUTES = 20
# The Whisper backfill owns this box for weeks at a time and is the job that
# actually feeds the dashboard. Running both at once cost it 5.5x: transcription
# ran at 3.0 episodes/hour up to the 16:44Z checkpoint on 2026-08-26 and 0.55/hour
# across the next five and a half hours, llama-server having started at 17:17Z.
# Sequentially the two take 4 days and 17 days; concurrently the pair takes 91.
WHISPER_PROCESS_HINT = "whisper_backfill_daemon.py"
# Cores. Whisper transcribes on 12 threads, so "working" is unambiguous and a
# low bar separates it from a daemon sitting in its between-batch sleep.
WHISPER_BUSY_CORES = float(os.environ.get("ANALYZE_WHISPER_BUSY_CORES", "0.5"))
WHISPER_SAMPLE_SECONDS = 3.0
WHISPER_POLL_SECONDS = 60
# Headroom Whisper needs to load distil-large-v3 and hold its audio buffers.
# Below this the box is paging and Whisper is the job that suffers for it, so
# the analyser stands down even though nothing is using the CPU.
WHISPER_MEMORY_FLOOR_MB = int(os.environ.get("ANALYZE_WHISPER_FLOOR_MB", "2500"))
DEFAULT_MAX_WAIT_MINUTES = 30
# Outside podcasts/ so `git add -A podcasts` never stages it; the first run
# committed the lock and then recorded its own deletion. It went on doing that:
# the lock was still being created inside podcasts/ and was a tracked file in
# the vault until 2026-08-26. `podcasts_root().parent` is what the comment
# always meant.
LOCK_NAME = ".analyze_podcast_batch.lock"

_stop = False


def _install_stop_handlers() -> None:
    def handler(signum, _frame):
        global _stop
        _stop = True
        print(f"[{_stamp()}] stop requested (signal {signum}); "
              "finishing this episode then pushing", flush=True)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, handler)
        except (ValueError, OSError):
            pass


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def deprioritise() -> str:
    """Same fix as the whisper daemon: os.nice does not exist on Windows, and
    ctypes truncates the process pseudo-handle unless restype is declared."""
    if hasattr(os, "nice"):
        try:
            os.nice(10)
            return "nice+10"
        except OSError:
            return "unchanged"
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        kernel32.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        if kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), 0x00004000):
            return "below-normal"
    except Exception:
        pass
    return "unchanged"


def available_mb() -> int | None:
    """Physical memory a new allocation could claim, or None if unknowable."""
    if hasattr(os, "sysconf") and "SC_AVPHYS_PAGES" in os.sysconf_names:
        return int(os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / 1048576)
    try:
        class _Stat(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        stat = _Stat()
        stat.dwLength = ctypes.sizeof(_Stat)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return int(stat.ullAvailPhys / 1048576)
    except Exception:
        pass
    return None


def wait_for_memory() -> None:
    while not _stop:
        free = available_mb()
        if free is None or free >= MIN_AVAILABLE_MB:
            return
        print(f"[{_stamp()}] only {free} MB available (floor {MIN_AVAILABLE_MB}); "
              f"waiting {MEMORY_WAIT_SECONDS}s", flush=True)
        time.sleep(MEMORY_WAIT_SECONDS)


def whisper_cores(sample_seconds: float = WHISPER_SAMPLE_SECONDS) -> float | None:
    """Cores the Whisper backfill is using right now, or None if unknowable.

    Measured rather than inferred. "Is the daemon running" is the wrong
    question -- it runs `--until-empty` for weeks, so it is always running and a
    gate on that would starve this batch permanently. What matters is whether it
    is transcribing at this moment or sitting in its between-batch sleep, and
    CPU time is the direct evidence of that.
    """
    try:
        import psutil  # noqa: WPS433
    except ImportError:
        return None
    try:
        procs = []
        for proc in psutil.process_iter(["pid", "cmdline"]):
            cmdline = " ".join(proc.info.get("cmdline") or [])
            if WHISPER_PROCESS_HINT in cmdline:
                procs.append(proc)
        if not procs:
            return 0.0
        first = [(p, p.cpu_times()) for p in procs]
        time.sleep(sample_seconds)
        used = 0.0
        for proc, before in first:
            try:
                after = proc.cpu_times()
            except psutil.Error:
                continue
            used += (after.user - before.user) + (after.system - before.system)
        return used / sample_seconds
    except Exception:
        return None


def whisper_present() -> bool:
    """Whether a Whisper backfill process exists at all."""
    try:
        import psutil  # noqa: WPS433
    except ImportError:
        return False
    for proc in psutil.process_iter(["cmdline"]):
        try:
            if WHISPER_PROCESS_HINT in " ".join(proc.info.get("cmdline") or []):
                return True
        except psutil.Error:
            continue
    return False


def wait_for_whisper(max_wait_minutes: int) -> None:
    """Yield the box to the transcription backfill, but never indefinitely.

    A pure gate would never release: the backlog is 1,206 episodes and drains
    over weeks. So this waits out the busy stretches and, once the wait budget
    is spent, takes one episode anyway before yielding again -- whisper keeps
    the box most of the time and this batch still finishes.
    """
    deadline = time.time() + max_wait_minutes * 60
    announced = False
    while not _stop:
        cores = whisper_cores()
        free = available_mb()
        # CPU alone reads a starving Whisper as an idle one. On 2026-09-01 the
        # box was at 1.3 GB free of 32 GB with 21 GB paged out; Whisper spent
        # its time blocked on page-ins rather than on the CPU, this gate saw
        # "idle", and the analyser took the machine -- transcription halved to
        # 1.5 episodes/hour while the analyser sped up. Yield on either signal:
        # a Whisper that cannot get memory needs the memory, not the courtesy.
        starved = (free is not None and free < WHISPER_MEMORY_FLOOR_MB
                   and whisper_present())
        if not starved and (cores is None or cores < WHISPER_BUSY_CORES):
            if announced:
                print(f"[{_stamp()}] whisper idle; resuming", flush=True)
            return
        why = (f"{free} MB free, below the {WHISPER_MEMORY_FLOOR_MB} MB floor"
               if starved else f"{cores:.1f} cores busy")
        if time.time() >= deadline:
            print(f"[{_stamp()}] waited {max_wait_minutes}m for whisper "
                  f"({why}); taking one episode anyway", flush=True)
            return
        if not announced:
            print(f"[{_stamp()}] whisper busy ({why}); "
                  f"yielding, up to {max_wait_minutes}m", flush=True)
            announced = True
        time.sleep(WHISPER_POLL_SECONDS)


def sha1_text(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def load_meta(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def unique_text_bytes(rows: list[tuple[Path, Path, dict]]) -> dict[Path, int]:
    """Bytes of text unique to each episode, after per-show boilerplate.

    File size alone is not evidence of speech. Three shows in this corpus store
    the same scraped episode-listing page once per episode -- Yet Another Value
    Podcast is 426 files of ~108 KB that share a 107,526-character body, and
    holds zero real transcripts. By raw size all 426 look like rich material;
    559 of the 1,156 size-passing candidates come from three such shows.

    Sending those to the model would burn roughly half the batch producing
    confident claims about a navigation menu. Sentence-shingle document
    frequency separates them cleanly: shingles appearing in more than a third of
    a show's episodes are chrome, and what remains is what the episode actually
    said. Measured on YAVP, that collapses 43.0 MB to 0.31 MB.
    """
    by_show: dict[str, list[tuple[Path, str]]] = {}
    for txt, _, meta in rows:
        show = meta.get("show_id") or meta.get("show_title") or "?"
        try:
            by_show.setdefault(show, []).append(
                (txt, txt.read_text(encoding="utf-8", errors="ignore")))
        except OSError:
            continue

    unique: dict[Path, int] = {}
    for _show, files in by_show.items():
        if len(files) < 3:
            for path, text in files:
                unique[path] = len(text)
            continue
        shingles = [
            {s for s in (x.strip() for x in re.split(r"(?<=[.!?])\s+|\n{2,}", text)) if len(s) >= 30}
            for _p, text in files
        ]
        freq: dict[str, int] = {}
        for shs in shingles:
            for s in shs:
                freq[s] = freq.get(s, 0) + 1
        cutoff = max(2, int(len(files) * 0.33))
        boiler = {s for s, n in freq.items() if n >= cutoff}
        for (path, _text), shs in zip(files, shingles):
            unique[path] = sum(len(s) for s in shs - boiler)
    return unique


def candidates(root: Path) -> list[tuple[Path, Path, dict]]:
    """Episodes that actually contain speech, newest first."""
    sized = []
    for meta_path in (root / "episodes").rglob("*.meta.json"):
        txt = meta_path.with_name(meta_path.name.replace(".meta.json", ".txt"))
        if not txt.exists() or txt.stat().st_size < MIN_TRANSCRIPT_BYTES:
            continue
        sized.append((txt, meta_path, load_meta(meta_path)))

    unique = unique_text_bytes(sized)
    out = [row for row in sized if unique.get(row[0], 0) >= MIN_TRANSCRIPT_BYTES]

    # Value-first, then newest. 343 of the 591 survivors are a16z -- venture
    # conversations about companies that are mostly private, so they cost a full
    # analysis and yield no ticker. The first two episodes the batch picked by
    # date alone were Whatnot and Stripe: 324s and 438s spent, zero tickers
    # between them. Ranking by in-book mentions puts the ownable episodes first,
    # so a run stopped early has done the work that mattered.
    # Scanned against running text, so short names are excluded here.
    book = scan_aliases(build_aliases(limit_in_book=True))

    def book_hits(path: Path) -> int:
        try:
            low = path.read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:
            return 0
        return sum(1 for alias in book if alias in low)

    scored = [(book_hits(row[0]), row) for row in out]
    # Descending by in-book mentions; ties broken newest-first.
    scored.sort(key=lambda pair: (-pair[0], _neg_date(pair[1][2].get("published") or "")))
    return [row for _hits, row in scored]


def _neg_date(published: str) -> str:
    """Descending dates inside an ascending sort, without a second pass."""
    return "".join(chr(0x7E - ord(c)) if 0x20 <= ord(c) <= 0x7E else c for c in published)


def needs_analysis(meta: dict, digest: str) -> bool:
    prior = meta.get("llm_analysis")
    if not isinstance(prior, dict):
        return True
    # Re-analyse when the transcript itself changed -- a re-transcription or a
    # name repair means the old claims were drawn from text that is gone.
    return prior.get("transcript_sha1") != digest


def vault_push(message: str) -> bool:
    repo = podcasts_root().parent
    try:
        # The Whisper daemon commits to this same tree every 15 minutes. Two
        # git processes in one repository collide on .git/index.lock, and that
        # collision is what a DNS outage needed to wedge the vault for fourteen
        # hours on 2026-08-31. One writer at a time.
        with vault_lock(repo, owner="analyze_podcast_batch",
                        log=lambda m: print(f"[{_stamp()}]{m}", flush=True)):
            clear_stale_git_state(repo, log=lambda m: print(f"[{_stamp()}]{m}", flush=True))
            return _push_locked(repo, message)
    except TimeoutError as exc:
        print(f"[{_stamp()}] vault lock: {exc}; skipping this push", flush=True)
        return False


def _push_locked(repo: Path, message: str) -> bool:
    try:
        run_git(repo, "add", "-A", "podcasts", timeout=300)
        staged = run_git(repo, "diff", "--cached", "--quiet", check=False, timeout=120)
        if staged.returncode == 0:
            return False
        run_git(repo, "commit", "-m", message, timeout=300)
        # autoStash: this vault always carries unrelated work in progress from
        # other lanes -- .gitignore edits, a letter mid-move, an untracked
        # AGENTS.md. A plain `pull --rebase` refuses outright ("cannot pull with
        # rebase: You have unstaged changes"), which is how the first batch run
        # analysed two episodes and pushed neither. Stash them, rebase, put them
        # back; never commit another lane's files.
        run_git(repo, "-c", "rebase.autoStash=true", "pull", "--rebase",
                "origin", "main", timeout=900)
        run_git(repo, "push", "origin", "main", timeout=600)
        return True
    except subprocess.CalledProcessError as exc:
        err = str(exc.stderr or "")[:300]
        print(f"[{_stamp()}] vault push failed: {err}", flush=True)
        # Never leave a half-finished rebase: the queue file then fails to parse
        # and the next run dies on it.
        run_git(repo, "rebase", "--abort", check=False, timeout=120)
        clear_stale_git_state(repo, log=lambda m: print(f"[{_stamp()}]{m}", flush=True))
        return False
    except (subprocess.TimeoutExpired, OSError) as exc:
        print(f"[{_stamp()}] vault push error: {exc}", flush=True)
        # A timeout now means run_git killed the whole git process tree, so the
        # repository is ours to clean rather than something's to finish.
        clear_stale_git_state(repo, log=lambda m: print(f"[{_stamp()}]{m}", flush=True))
        return False


def run(*, limit: int | None, model: str | None, push: bool,
        push_minutes: int, hours: float | None,
        max_wait_minutes: int | None) -> dict:
    root = podcasts_root(create=True)
    lock = root.parent / LOCK_NAME
    if lock.exists():
        age = time.time() - lock.stat().st_mtime
        if age < 3600:
            print(f"another batch holds {lock} (age {age:.0f}s); exiting")
            return {"skipped": "locked"}
        print(f"stale lock ({age:.0f}s old); taking it")
    lock.write_text(f"{os.getpid()} {_stamp()}\n", encoding="utf-8")

    print(f"[{_stamp()}] priority -> {deprioritise()}", flush=True)
    aliases = build_aliases()
    deadline = datetime.now(timezone.utc) + timedelta(hours=hours) if hours else None

    done = failed = skipped = 0
    since_push = 0
    last_push = datetime.now(timezone.utc)
    try:
        rows = candidates(root)
        print(f"[{_stamp()}] {len(rows)} episodes with a real transcript", flush=True)
        for txt, meta_path, meta in rows:
            if _stop or (limit is not None and done >= limit):
                break
            if deadline and datetime.now(timezone.utc) >= deadline:
                print(f"[{_stamp()}] deadline reached", flush=True)
                break

            digest = sha1_text(txt)
            if not needs_analysis(meta, digest):
                skipped += 1
                continue

            wait_for_memory()
            if max_wait_minutes is not None:
                wait_for_whisper(max_wait_minutes)
            if _stop:
                break

            title = meta.get("title") or txt.stem
            started = time.time()
            try:
                result = analyze(txt.read_text(encoding="utf-8", errors="ignore"),
                                 title=title,
                                 show=meta.get("show_title") or meta.get("show_id") or "",
                                 model=model, aliases=aliases)
            except LocalLLMUnavailable as exc:
                print(f"[{_stamp()}] LLM unavailable: {exc}", flush=True)
                break
            except Exception as exc:  # one bad episode must not end the run
                failed += 1
                print(f"[{_stamp()}] FAILED {title[:48]}: {type(exc).__name__} {exc}", flush=True)
                continue

            result["transcript_sha1"] = digest
            result["analyzed_at"] = _stamp()
            meta["llm_analysis"] = result
            meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
                                 encoding="utf-8")

            done += 1
            since_push += 1
            elapsed = time.time() - started
            print(f"[{_stamp()}] {done:4d} {elapsed:5.0f}s  claims={len(result.get('claims') or []):2d} "
                  f"verified={result.get('quote_verified_rate')} "
                  f"tickers={','.join((result.get('tickers') or [])[:4]) or '-'}  {title[:44]}",
                  flush=True)

            due = (datetime.now(timezone.utc) - last_push).total_seconds() >= push_minutes * 60
            if push and (due or since_push >= 10):
                if vault_push(f"chore(podcasts): local-model analysis {_stamp()}"):
                    print(f"[{_stamp()}] pushed vault ({since_push} episodes)", flush=True)
                last_push = datetime.now(timezone.utc)
                since_push = 0
    finally:
        if push and since_push:
            vault_push(f"chore(podcasts): local-model analysis {_stamp()}")
        try:
            lock.unlink()
        except OSError:
            pass

    return {"analyzed": done, "failed": failed, "already_current": skipped}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--limit", type=int, default=None, help="Stop after N episodes.")
    p.add_argument("--hours", type=float, default=None, help="Stop cleanly after N hours.")
    p.add_argument("--model", default=None, help="Model identifier on the local server.")
    p.add_argument("--no-push", action="store_true", help="Do not commit/push the vault.")
    p.add_argument("--push-every-minutes", type=int, default=DEFAULT_PUSH_MINUTES)
    p.add_argument("--status", action="store_true", help="Report coverage and exit.")
    p.add_argument("--share-with-whisper", action="store_true",
                   help="Run alongside the Whisper backfill instead of yielding to it. "
                        "Measured cost of doing so: transcription drops ~5.5x.")
    p.add_argument("--max-wait-minutes", type=int, default=DEFAULT_MAX_WAIT_MINUTES,
                   help="Longest to wait for whisper to go idle before taking an "
                        "episode anyway (default %(default)s).")
    args = p.parse_args()

    root = podcasts_root(create=True)
    if args.status:
        rows = candidates(root)
        current = sum(1 for txt, _, meta in rows if not needs_analysis(meta, sha1_text(txt)))
        print(json.dumps({"with_transcript": len(rows), "analyzed": current,
                          "remaining": len(rows) - current}, indent=2))
        return 0

    _install_stop_handlers()
    print(json.dumps(run(limit=args.limit, model=args.model, push=not args.no_push,
                         push_minutes=args.push_every_minutes, hours=args.hours,
                         max_wait_minutes=None if args.share_with_whisper
                         else args.max_wait_minutes), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
