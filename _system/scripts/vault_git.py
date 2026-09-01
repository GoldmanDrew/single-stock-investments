#!/usr/bin/env python3
"""One repository, two writers: the git coordination the vault always needed.

The Whisper backfill and the local-model analyser both commit to
`research-vault` -- the daemon every 15 minutes, the analyser every 20 -- and
until now neither knew the other existed. Two `git` processes in one working
tree collide on `.git/index.lock`, and on 2026-08-31 that turned a brief DNS
outage into a wedged repository:

  * a `git pull --rebase` hung for 27 minutes, past its own 900-second timeout;
  * `subprocess.run(timeout=)` killed the direct child but not the
    `git-remote-https` grandchildren it had spawned, so they kept running;
  * they left a stale `index.lock` and a half-written `.git/rebase-merge/`
    holding nothing but an `autostash`;
  * that autostash contained another lane's uncommitted work, stashed and never
    restored, invisible to `git status`;
  * every subsequent push from either job failed for 14 hours, stranding 20
    commits, while both jobs logged ordinary-looking progress.

Three defences, in the order they matter:

1. `vault_lock()` -- only one process touches vault git at a time.
2. `run_git()` -- a timeout kills the whole process tree, not just the child.
3. `clear_stale_git_state()` -- an abandoned rebase is detected and unwound,
   and its autostash is restored rather than silently abandoned.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

LOCK_NAME = ".vault-git.lock"
# A vault push is fetch + rebase + push. Ninety seconds is a normal slow one;
# past ten minutes the holder is not working, it is stuck.
LOCK_STALE_SECONDS = 600
LOCK_POLL_SECONDS = 2
DEFAULT_ACQUIRE_TIMEOUT = 900
# How long to keep draining a killed command's pipes before abandoning them.
POST_KILL_DRAIN_SECONDS = 5


def _lock_path(repo: Path) -> Path:
    return repo / ".git" / LOCK_NAME


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        import psutil  # noqa: WPS433

        return psutil.pid_exists(pid)
    except ImportError:
        pass
    if hasattr(os, "kill"):
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            pass
    return True  # unknowable: treat as held and let staleness expire it


def _read_lock(path: Path) -> tuple[int, float] | None:
    try:
        pid_text, stamp_text = path.read_text(encoding="utf-8").split()[:2]
        return int(pid_text), float(stamp_text)
    except (OSError, ValueError):
        return None


@contextmanager
def vault_lock(repo: Path, *, owner: str, timeout: int = DEFAULT_ACQUIRE_TIMEOUT,
               log=print):
    """Hold the vault's git lock for the duration of the block.

    Advisory and cooperative -- it guards the two jobs in this repo against each
    other, not against a human running git by hand. Breaking a lock requires
    both that its holder is gone and that it is old, because a live holder doing
    slow network work must not be interrupted just for being slow.
    """
    path = _lock_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + timeout
    announced = False

    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()} {time.time()} {owner}\n".encode("utf-8"))
            os.close(fd)
            break
        except FileExistsError:
            held = _read_lock(path)
            if held is None:
                # Unreadable: a writer died mid-write. Age it out by mtime.
                try:
                    age = time.time() - path.stat().st_mtime
                except OSError:
                    continue
                if age > LOCK_STALE_SECONDS:
                    path.unlink(missing_ok=True)
                    continue
            else:
                pid, stamp = held
                age = time.time() - stamp
                if not _pid_alive(pid) and age > LOCK_STALE_SECONDS:
                    log(f"  vault lock: holder {pid} gone and {age:.0f}s old; breaking")
                    path.unlink(missing_ok=True)
                    continue
                if not announced:
                    log(f"  vault lock held by {pid} ({age:.0f}s); waiting")
                    announced = True
            if time.time() >= deadline:
                raise TimeoutError(f"vault git lock not acquired within {timeout}s")
            time.sleep(LOCK_POLL_SECONDS)

    try:
        yield
    finally:
        held = _read_lock(path)
        # Only release a lock that is still ours; a broken-and-retaken lock
        # belongs to someone else now.
        if held is None or held[0] == os.getpid():
            path.unlink(missing_ok=True)


def _kill_tree(proc: subprocess.Popen) -> None:
    """Kill the process and everything it spawned.

    `git fetch` runs `git-remote-https`, which is what actually holds the
    socket. Killing only the parent leaves that child alive holding
    `index.lock`, which is how a timed-out pull wedged the repository for
    fourteen hours.
    """
    try:
        import psutil  # noqa: WPS433
    except ImportError:
        proc.kill()
        return
    try:
        parent = psutil.Process(proc.pid)
        victims = parent.children(recursive=True) + [parent]
    except psutil.Error:
        proc.kill()
        return
    for p in victims:
        try:
            p.kill()
        except psutil.Error:
            pass
    psutil.wait_procs(victims, timeout=10)


def run_git(repo: Path, *args, check: bool = True, timeout: int = 300):
    """`git` with a timeout that is actually enforced.

    Output goes to temporary files rather than pipes, and that choice is the
    whole fix. With pipes, the timeout path has to call `communicate()` to
    collect output, and `communicate()` waits for EOF -- which never arrives
    while any grandchild still holds the inherited write end. `git fetch` spawns
    `git-remote-https`; when `sh`-style intermediaries exit, such a grandchild is
    reparented away and a recursive kill from the original pid no longer finds
    it. Measured on a hook that backgrounds a 60-second child: `subprocess.run`
    with a 6-second timeout returned after 91.5 seconds, and killing the tree
    first still returned after 60 -- both simply waited the grandchild out. At
    the 900-second timeout the vault push used, that is how one `git pull
    --rebase` hung for 27 minutes and stranded 20 commits for 14 hours.

    Files have no EOF to wait for. `proc.wait()` returns as soon as the direct
    child is gone, whatever its descendants are still doing, and the output is
    read afterwards.
    """
    import tempfile  # noqa: WPS433

    with tempfile.TemporaryFile() as out_f, tempfile.TemporaryFile() as err_f:
        proc = subprocess.Popen(["git", *args], cwd=repo, stdout=out_f, stderr=err_f)

        def _read() -> tuple[str, str]:
            for handle in (out_f, err_f):
                try:
                    handle.seek(0)
                except OSError:
                    pass
            return (out_f.read().decode("utf-8", "replace"),
                    err_f.read().decode("utf-8", "replace"))

        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            try:
                proc.wait(timeout=POST_KILL_DRAIN_SECONDS)
            except subprocess.TimeoutExpired:
                pass
            out, err = _read()
            raise subprocess.TimeoutExpired(["git", *args], timeout,
                                            output=out, stderr=err)
        out, err = _read()

    result = subprocess.CompletedProcess(["git", *args], proc.returncode, out, err)
    if check and proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, ["git", *args], out, err)
    return result


def _git_running_in(repo: Path) -> bool:
    try:
        import psutil  # noqa: WPS433
    except ImportError:
        return True  # cannot tell; assume yes and leave the lock alone
    target = str(repo.resolve()).lower()
    for proc in psutil.process_iter(["name", "cwd"]):
        try:
            if (proc.info.get("name") or "").lower().startswith("git"):
                cwd = (proc.info.get("cwd") or "").lower()
                if cwd.startswith(target):
                    return True
        except psutil.Error:
            continue
    return False


def clear_stale_git_state(repo: Path, *, log=print) -> list[str]:
    """Unwind a rebase that died, and restore what it stashed.

    Returns a list of what it repaired, empty when the repository was clean.
    Only ever runs while holding `vault_lock`, and only when no git process is
    live in the repository -- otherwise a slow-but-healthy operation would be
    torn out from under itself.
    """
    repaired: list[str] = []
    git_dir = repo / ".git"
    if _git_running_in(repo):
        return repaired

    rebase_dirs = [git_dir / "rebase-merge", git_dir / "rebase-apply"]
    for rebase_dir in rebase_dirs:
        if not rebase_dir.is_dir():
            continue
        autostash = (rebase_dir / "autostash")
        stash_sha = autostash.read_text(encoding="utf-8").strip() if autostash.is_file() else ""
        # `rebase --abort` needs head-name to work. A rebase that died before
        # writing it cannot be aborted and must be removed by hand -- which is
        # exactly the state the 2026-08-31 wedge left behind.
        if (rebase_dir / "head-name").is_file():
            run_git(repo, "rebase", "--abort", check=False, timeout=120)
            repaired.append("aborted an unfinished rebase")
        if rebase_dir.is_dir():
            import shutil  # noqa: WPS433

            shutil.rmtree(rebase_dir, ignore_errors=True)
            repaired.append(f"removed {rebase_dir.name}")
        if stash_sha:
            # The autostash holds another lane's uncommitted work. Losing it is
            # worse than any push failure, so restore it before anything else
            # touches the tree.
            applied = run_git(repo, "stash", "apply", stash_sha, check=False, timeout=120)
            repaired.append("restored the autostash" if applied.returncode == 0
                            else f"COULD NOT restore autostash {stash_sha[:12]}")

    index_lock = git_dir / "index.lock"
    if index_lock.is_file():
        index_lock.unlink(missing_ok=True)
        repaired.append("removed a stale index.lock")

    for line in repaired:
        log(f"  vault repair: {line}")
    return repaired
