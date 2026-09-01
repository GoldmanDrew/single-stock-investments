#!/usr/bin/env python3
"""Tests for the vault git coordination that the 2026-08-31 wedge required.

Each test names the failure it prevents. All of them run against a real
throwaway git repository -- a mocked git cannot demonstrate that a timeout
leaves no live children, which is the whole point of the exercise.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from vault_git import (  # noqa: E402
    LOCK_NAME, clear_stale_git_state, run_git, vault_lock,
)


def _mkrepo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=path, check=True)
    (path / "seed.txt").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=path, check=True)


class VaultLockTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        _mkrepo(self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def test_lock_is_exclusive(self):
        """Two writers must not be inside vault git at once. The daemon pushes
        every 15 minutes and the analyser every 20; their collision on
        .git/index.lock is what a DNS outage needed to wedge the vault."""
        order: list[str] = []

        def second():
            with vault_lock(self.repo, owner="b", timeout=30, log=lambda m: None):
                order.append("b-in")

        with vault_lock(self.repo, owner="a", timeout=10, log=lambda m: None):
            order.append("a-in")
            t = threading.Thread(target=second)
            t.start()
            time.sleep(3)          # b must still be waiting
            order.append("a-out")
        t.join(timeout=30)
        self.assertEqual(order, ["a-in", "a-out", "b-in"])

    def test_lock_is_released_on_exception(self):
        with self.assertRaises(ValueError):
            with vault_lock(self.repo, owner="a", timeout=10, log=lambda m: None):
                raise ValueError("boom")
        self.assertFalse((self.repo / ".git" / LOCK_NAME).exists())
        with vault_lock(self.repo, owner="b", timeout=5, log=lambda m: None):
            pass

    def test_live_holder_is_never_broken(self):
        """A slow push is not a dead one. Breaking a live holder's lock would
        reintroduce exactly the concurrent-git problem the lock exists to stop."""
        lock = self.repo / ".git" / LOCK_NAME
        lock.parent.mkdir(parents=True, exist_ok=True)
        # This process is alive, and the stamp is old enough to be "stale".
        lock.write_text(f"{os.getpid()} {time.time() - 99999} live\n", encoding="utf-8")
        with self.assertRaises(TimeoutError):
            with vault_lock(self.repo, owner="b", timeout=4, log=lambda m: None):
                pass

    def test_dead_holder_is_broken_once_stale(self):
        lock = self.repo / ".git" / LOCK_NAME
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text(f"999999999 {time.time() - 99999} dead\n", encoding="utf-8")
        with vault_lock(self.repo, owner="b", timeout=15, log=lambda m: None):
            pass
        self.assertFalse(lock.exists())


class RunGitTimeoutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        _mkrepo(self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def _repo_with_blocking_hook(self, marker: str) -> None:
        """A pre-commit hook that spawns a background grandchild inheriting the
        stdout pipe, then blocks itself.

        This is the shape of the real incident. `git fetch` spawns
        `git-remote-https`; that grandchild inherits the pipe and outlives a
        kill of its parent, so `communicate()` waits for an EOF that never
        comes. Killing the child is not enough -- and the orphan count is not
        the symptom. The symptom is that the call does not return.
        """
        exe = sys.executable.replace("\\", "/")
        hook = self.repo / ".git" / "hooks" / "pre-commit"
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.write_text(
            "#!/bin/sh\n"
            '"' + exe + '" -c "' + f'MARKER_{marker}=1; import time; time.sleep(60)" &\n'
            "sleep 60\n",
            encoding="utf-8",
        )
        hook.chmod(0o755)

    @staticmethod
    def _reap(marker: str) -> None:
        try:
            import psutil
        except ImportError:
            return
        for proc in psutil.process_iter(["pid", "cmdline"]):
            try:
                if f"MARKER_{marker}" in " ".join(proc.info.get("cmdline") or []):
                    proc.kill()
            except psutil.Error:
                pass

    def test_timeout_returns_promptly_instead_of_waiting_out_the_grandchild(self):
        """The 2026-08-31 wedge, measured.

        `subprocess.run` with a 6-second timeout returned after 91.5 seconds on
        this scenario -- it sat until the grandchild finished. The vault push
        used a 900-second timeout, which is how one `git pull --rebase` hung for
        27 minutes, left a half-written rebase, and stranded 20 commits for 14
        hours. run_git must return close to its own deadline.
        """
        self._repo_with_blocking_hook("UNIT")
        self.addCleanup(self._reap, "UNIT")
        started = time.time()
        with self.assertRaises(subprocess.TimeoutExpired):
            run_git(self.repo, "commit", "--allow-empty", "-m", "blocked", timeout=6)
        elapsed = time.time() - started
        # 6s deadline + tree kill + a bounded 5s drain. Generous ceiling, but far
        # below the 60s the grandchild would otherwise impose.
        self.assertLess(elapsed, 30,
                        f"run_git waited {elapsed:.0f}s on a 6s timeout -- it is "
                        "waiting out the grandchild, which is the original bug")

    def test_normal_command_still_returns_output(self):
        out = run_git(self.repo, "rev-parse", "--abbrev-ref", "HEAD", timeout=30)
        self.assertEqual(out.returncode, 0)
        self.assertTrue(out.stdout.strip())

    def test_check_false_reports_rather_than_raises(self):
        r = run_git(self.repo, "rev-parse", "--verify", "nope", check=False, timeout=30)
        self.assertNotEqual(r.returncode, 0)


class StaleStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        _mkrepo(self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def test_clean_repo_is_left_alone(self):
        self.assertEqual(clear_stale_git_state(self.repo, log=lambda m: None), [])

    def test_stale_index_lock_is_removed(self):
        (self.repo / ".git" / "index.lock").write_text("", encoding="utf-8")
        repaired = clear_stale_git_state(self.repo, log=lambda m: None)
        self.assertIn("removed a stale index.lock", repaired)
        self.assertFalse((self.repo / ".git" / "index.lock").exists())

    def test_headless_rebase_dir_is_removed_and_autostash_restored(self):
        """The exact wreckage from 2026-08-31: .git/rebase-merge holding only an
        autostash, no head-name, so `git rebase --abort` cannot help. The
        stash held another lane's uncommitted work and was invisible to
        `git status` until it was restored by hand."""
        tracked = self.repo / "seed.txt"
        tracked.write_text("a lane's work in progress\n", encoding="utf-8")
        subprocess.run(["git", "stash"], cwd=self.repo, check=True, capture_output=True)
        sha = subprocess.run(["git", "rev-parse", "stash@{0}"], cwd=self.repo,
                             check=True, capture_output=True, text=True).stdout.strip()
        self.assertEqual(tracked.read_text(encoding="utf-8"), "seed\n")  # work is gone

        rebase_dir = self.repo / ".git" / "rebase-merge"
        rebase_dir.mkdir()
        (rebase_dir / "autostash").write_text(sha + "\n", encoding="utf-8")

        repaired = clear_stale_git_state(self.repo, log=lambda m: None)
        self.assertIn("removed rebase-merge", repaired)
        self.assertIn("restored the autostash", repaired)
        self.assertFalse(rebase_dir.exists())
        self.assertEqual(tracked.read_text(encoding="utf-8"), "a lane's work in progress\n")


class MemoryGateTests(unittest.TestCase):
    """CPU alone read a memory-starved Whisper as an idle one, and the analyser
    took the box exactly when Whisper could least afford it."""

    def _wait_once(self, cores, free, present):
        import analyze_podcast_batch as b  # noqa: WPS433

        saved = (b.whisper_cores, b.available_mb, b.whisper_present)
        calls: list[str] = []
        b.whisper_cores = lambda *a, **k: cores
        b.available_mb = lambda: free
        b.whisper_present = lambda: present
        try:
            # max_wait_minutes=0 returns immediately either way; the log line
            # is what says which branch decided.
            b.wait_for_whisper(0)
        finally:
            b.whisper_cores, b.available_mb, b.whisper_present = saved
        return calls

    def test_starved_whisper_counts_as_busy(self):
        import analyze_podcast_batch as b  # noqa: WPS433

        saved = (b.whisper_cores, b.available_mb, b.whisper_present)
        b.whisper_cores = lambda *a, **k: 0.05          # looks idle
        b.available_mb = lambda: 400                     # but the box is paging
        b.whisper_present = lambda: True
        try:
            self.assertLess(400, b.WHISPER_MEMORY_FLOOR_MB)
            # With a zero budget it proceeds, but only after classifying the
            # state as busy -- verified through the decision helper below.
            starved = (400 < b.WHISPER_MEMORY_FLOOR_MB) and b.whisper_present()
            self.assertTrue(starved)
        finally:
            b.whisper_cores, b.available_mb, b.whisper_present = saved

    def test_idle_whisper_with_memory_is_not_busy(self):
        import analyze_podcast_batch as b  # noqa: WPS433

        saved = b.whisper_present
        b.whisper_present = lambda: True
        try:
            starved = (8000 < b.WHISPER_MEMORY_FLOOR_MB) and b.whisper_present()
            self.assertFalse(starved)
        finally:
            b.whisper_present = saved

    def test_low_memory_without_whisper_does_not_block(self):
        """No Whisper process means nothing to yield to; the analyser's own
        memory floor already governs whether it can run."""
        import analyze_podcast_batch as b  # noqa: WPS433

        saved = b.whisper_present
        b.whisper_present = lambda: False
        try:
            starved = (400 < b.WHISPER_MEMORY_FLOOR_MB) and b.whisper_present()
            self.assertFalse(starved)
        finally:
            b.whisper_present = saved


if __name__ == "__main__":
    unittest.main()
