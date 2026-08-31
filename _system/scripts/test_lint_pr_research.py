#!/usr/bin/env python3
"""Unit tests for PR research lint scoping helpers."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import lint_pr_research as lpr


class LintPrResearchScopeTests(unittest.TestCase):
    def test_tickers_from_paths_ignores_system(self):
        paths = [
            "AES/research/valuation.json",
            "_system/data/contract_backfill_queue.json",
            "8697.T/research/committee_work/2026-07-21/chair_synthesis.json",
        ]
        self.assertEqual(lpr.tickers_from_paths(paths), ["8697.T", "AES"])

    def test_committee_only_allows_workbench(self):
        paths = [
            "8697.T/research/committee_work/2026-07-21/chair_synthesis.json",
            "8697.T/research/valuation_workbench.json",
        ]
        self.assertEqual(lpr.research_diff_kind("8697.T", paths, "origin/main"), "committee_only")

    def test_authorized_evidence_is_mechanical(self):
        paths = ["ALS.TO/research/authorized_evidence.json"]
        self.assertEqual(lpr.research_diff_kind("ALS.TO", paths, "origin/main"), "mechanical_only")

    def test_lenses_only_is_derived(self):
        paths = ["AAL/research/lenses.json"]
        self.assertEqual(lpr.research_diff_kind("AAL", paths, "origin/main"), "derived_only")

    def test_lenses_plus_narrative_is_not_derived(self):
        paths = [
            "AAL/research/lenses.json",
            "AAL/research/deep_dive_2026-08-04.md",
        ]
        self.assertEqual(lpr.research_diff_kind("AAL", paths, "origin/main"), "mixed")

    def test_git_diff_names_never_uses_two_dot_base_tip(self):
        """Shallow CI used to fall back to `git diff base`, poisoning PRs."""
        calls: list[list[str]] = []

        def fake_run(cmd, cwd=None, capture_output=None, text=None):  # noqa: ARG001
            calls.append(list(cmd))
            if cmd[:3] == ["git", "diff", "--name-only"] and "...HEAD" in cmd[-1]:
                return mock.Mock(returncode=1, stdout="", stderr="fatal: no merge base")
            if cmd[:2] == ["git", "merge-base"]:
                return mock.Mock(returncode=1, stdout="", stderr="fatal: Not a valid object")
            raise AssertionError(f"unexpected command: {cmd}")

        with mock.patch.object(lpr.subprocess, "run", side_effect=fake_run):
            with self.assertRaises(SystemExit) as ctx:
                lpr.git_diff_names("origin/main")
        self.assertEqual(ctx.exception.code, 2)
        # Must never call two-dot `git diff --name-only origin/main`.
        for cmd in calls:
            if cmd[:3] == ["git", "diff", "--name-only"]:
                self.assertTrue(any("..." in part for part in cmd), cmd)

    def test_name_only_file_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "files.txt"
            path.write_text("AES/research/deep_dive_2026-07-21.md\nALS.TO/research/authorized_evidence.json\n", encoding="utf-8")
            names = lpr.read_name_only_file(path)
            self.assertEqual(names[0], "AES/research/deep_dive_2026-07-21.md")
            self.assertEqual(lpr.tickers_from_paths(names), ["AES", "ALS.TO"])


if __name__ == "__main__":
    unittest.main()
