#!/usr/bin/env python3
"""Tests for suppressing no-op Data Pipeline dashboard deploys."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))
from workflow_run_deploy_gate import should_deploy


def _job(name: str, *, conclusion: str = "success", steps: list[dict] | None = None) -> dict:
    return {
        "name": name,
        "conclusion": conclusion,
        "steps": steps or [],
    }


class WorkflowRunDeployGateTests(unittest.TestCase):
    def test_no_import_drive_run_does_not_deploy(self) -> None:
        jobs = [
            _job("decide"),
            _job(
                "drive",
                steps=[
                    {"name": "Import Drive intake PDFs", "conclusion": "success"},
                    {"name": "Commit imported documents", "conclusion": "skipped"},
                    {"name": "Commit updated intake report", "conclusion": "success"},
                ],
            ),
            _job("downloads", conclusion="skipped"),
            _job("pipeline-summary"),
        ]
        self.assertFalse(should_deploy("Data Pipeline", jobs))

    def test_imported_drive_documents_do_deploy(self) -> None:
        jobs = [
            _job("decide"),
            _job(
                "drive",
                steps=[
                    {"name": "Rebuild insights (only when files imported)", "conclusion": "success"},
                    {"name": "Commit imported documents", "conclusion": "success"},
                ],
            ),
            _job("pipeline-summary"),
        ]
        self.assertTrue(should_deploy("Data Pipeline", jobs))

    def test_other_data_pipeline_lane_preserves_deploy(self) -> None:
        jobs = [
            _job("decide"),
            _job("downloads", steps=[{"name": "Commit downloaded filings", "conclusion": "success"}]),
            _job("drive", conclusion="skipped"),
            _job("pipeline-summary"),
        ]
        self.assertTrue(should_deploy("Data Pipeline", jobs))

    def test_other_upstream_workflow_preserves_deploy(self) -> None:
        self.assertTrue(should_deploy("Darwin Portfolio Refresh", [_job("build")]))

    def test_unknown_data_pipeline_shape_fails_open(self) -> None:
        self.assertTrue(should_deploy("Data Pipeline", [_job("decide"), _job("pipeline-summary")]))


class WorkflowWiringTests(unittest.TestCase):
    def test_data_pipeline_persists_changed_warning_state(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "data-pipeline.yml").read_text(encoding="utf-8")
        drive_block = workflow.split("\n  drive:\n", 1)[1].split("\n  news:\n", 1)[0]
        intake_full_block = workflow.split("\n  intake-full:\n", 1)[1].split("\n  technicals:\n", 1)[0]
        self.assertIn("id: google_creds", drive_block)
        self.assertNotIn("id: google_creds", intake_full_block)
        self.assertIn("Commit updated intake report", workflow)
        self.assertIn("steps.import.outputs.report_changed == 'true'", workflow)
        self.assertIn("GITHUB_STEP_SUMMARY", workflow)
        self.assertIn("::error::Drive Intake cannot run", workflow)
        self.assertIn("steps.rebuild.conclusion == 'success'", workflow)
        self.assertGreaterEqual(workflow.count("always() &&"), 3)

    def test_dashboard_uses_upstream_change_gate(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "dashboard-pages.yml").read_text(encoding="utf-8")
        self.assertIn("upstream-change-gate:", workflow)
        self.assertIn("workflow_run_deploy_gate.py", workflow)
        self.assertIn("needs.upstream-change-gate.outputs.should_deploy == 'true'", workflow)

    def test_drive_intake_tests_are_wired_into_ci(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "ci-bootstrap-smoke.yml").read_text(encoding="utf-8")
        self.assertIn("drive-intake:", workflow)
        self.assertIn("_system.scripts.test_import_drive_intake", workflow)
        self.assertIn("_system.scripts.test_materialize_drive_credentials", workflow)
        self.assertIn("_system.scripts.test_workflow_run_deploy_gate", workflow)


if __name__ == "__main__":
    unittest.main()
