from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from _system.scripts.validate_dashboard_data import (
    repository_file_exists,
    resolve_payload_path,
)


class RepositoryFileExistsTests(unittest.TestCase):
    def run_git(self, root: Path, *args: str) -> None:
        subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def test_tracked_sparse_file_counts_as_existing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.run_git(root, "init")
            self.run_git(root, "config", "user.name", "CI Test")
            self.run_git(root, "config", "user.email", "ci@example.test")
            report = root / "ABC" / "third-party-analyses" / "activist_reports" / "report.htm"
            report.parent.mkdir(parents=True)
            report.write_text("report", encoding="utf-8")
            self.run_git(root, "add", ".")
            self.run_git(root, "commit", "-m", "fixture")
            report.unlink()

            self.assertFalse(repository_file_exists(root, report.relative_to(root).as_posix()))

            self.run_git(root, "config", "core.sparseCheckout", "true")
            self.assertTrue(repository_file_exists(root, report.relative_to(root).as_posix()))

    def test_untracked_sparse_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.run_git(root, "init")
            self.run_git(root, "config", "core.sparseCheckout", "true")
            self.assertFalse(repository_file_exists(root, "ABC/missing-report.htm"))


class ResolvePayloadPathTests(unittest.TestCase):
    def test_deploy_only_falls_back_to_core_when_monolith_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            monolith = root / "dashboard_data.json"
            core = root / "core.json"
            core.write_text("{}", encoding="utf-8")
            self.assertEqual(
                resolve_payload_path(monolith=monolith, core=core, deploy_only=True),
                core,
            )

    def test_full_checkout_still_requires_monolith(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            monolith = root / "dashboard_data.json"
            core = root / "core.json"
            core.write_text("{}", encoding="utf-8")
            self.assertIsNone(
                resolve_payload_path(monolith=monolith, core=core, deploy_only=False)
            )

    def test_monolith_wins_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            monolith = root / "dashboard_data.json"
            core = root / "core.json"
            monolith.write_text("{}", encoding="utf-8")
            core.write_text("{}", encoding="utf-8")
            self.assertEqual(
                resolve_payload_path(monolith=monolith, core=core, deploy_only=True),
                monolith,
            )


if __name__ == "__main__":
    unittest.main()
