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

from analyze_podcast_episode import analyze, build_aliases  # noqa: E402
from llm_local import LocalLLMUnavailable  # noqa: E402
from vault_paths import podcasts_root  # noqa: E402

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
# Outside podcasts/ so `git add -A podcasts` never stages it; the first run
# committed the lock and then recorded its own deletion.
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
    book = build_aliases(limit_in_book=True)

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
        subprocess.run(["git", "add", "-A", "podcasts"], cwd=repo, check=True,
                       capture_output=True, timeout=300)
        staged = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo,
                                capture_output=True, timeout=120)
        if staged.returncode == 0:
            return False
        subprocess.run(["git", "commit", "-m", message], cwd=repo, check=True,
                       capture_output=True, timeout=300)
        # autoStash: this vault always carries unrelated work in progress from
        # other lanes -- .gitignore edits, a letter mid-move, an untracked
        # AGENTS.md. A plain `pull --rebase` refuses outright ("cannot pull with
        # rebase: You have unstaged changes"), which is how the first batch run
        # analysed two episodes and pushed neither. Stash them, rebase, put them
        # back; never commit another lane's files.
        subprocess.run(["git", "-c", "rebase.autoStash=true", "pull", "--rebase",
                        "origin", "main"], cwd=repo, check=True,
                       capture_output=True, timeout=900)
        subprocess.run(["git", "push", "origin", "main"], cwd=repo, check=True,
                       capture_output=True, timeout=600)
        return True
    except subprocess.CalledProcessError as exc:
        err = (exc.stderr or b"").decode("utf-8", "replace")[:200]
        print(f"[{_stamp()}] vault push failed: {err}", flush=True)
        # Never leave a half-finished rebase: the queue file then fails to parse
        # and the next run dies on it.
        subprocess.run(["git", "rebase", "--abort"], cwd=repo, capture_output=True)
        return False
    except (subprocess.TimeoutExpired, OSError) as exc:
        print(f"[{_stamp()}] vault push error: {exc}", flush=True)
        return False


def run(*, limit: int | None, model: str | None, push: bool,
        push_minutes: int, hours: float | None) -> dict:
    root = podcasts_root(create=True)
    lock = root / LOCK_NAME
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
                         push_minutes=args.push_every_minutes, hours=args.hours), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
