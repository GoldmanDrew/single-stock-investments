import json
import re
import unittest
from pathlib import Path

from summarize_llm_ledger import summarize


ROOT = Path(__file__).resolve().parents[2]


class WorkflowGovernanceTests(unittest.TestCase):
    def test_actions_surface_has_no_manual_run_choices(self):
        # Existing schedule+manual ops surfaces; everything else is schedule/push only.
        allow_manual = {"dashboard-pages.yml", "letter-backfill.yml", "podcast-refresh.yml"}
        for path in (ROOT / ".github" / "workflows").glob("*.yml"):
            if path.name in allow_manual:
                continue
            text = path.read_text(encoding="utf-8")
            self.assertNotRegex(text, r"(?m)^\s{2}workflow_dispatch:\s*$", path.name)

    def test_every_runner_job_has_a_hard_timeout(self):
        for path in (ROOT / ".github" / "workflows").glob("*.yml"):
            text = path.read_text(encoding="utf-8")
            jobs = text.split("\njobs:\n", 1)
            if len(jobs) != 2:
                continue
            blocks = re.split(r"(?m)(?=^  [A-Za-z0-9_-]+:\s*$)", jobs[1])
            for block in blocks:
                if re.search(r"(?m)^    runs-on:", block):
                    self.assertRegex(block, r"(?m)^    timeout-minutes: [1-9][0-9]*$", path.name)
                    timeout = int(re.search(r"(?m)^    timeout-minutes: ([0-9]+)$", block).group(1))
                    self.assertLessEqual(timeout, 300, path.name)

    def test_agent_parallelism_and_artifact_retention_are_bounded(self):
        for path in (ROOT / ".github" / "workflows").glob("*.yml"):
            text = path.read_text(encoding="utf-8")
            for value in re.findall(r"(?m)^\s+max-parallel:\s+([0-9]+)\s*$", text):
                self.assertLessEqual(int(value), 3, path.name)
            lines = text.splitlines()
            for index, line in enumerate(lines):
                if "actions/upload-artifact@" in line:
                    window = "\n".join(lines[index:index + 12])
                    self.assertRegex(window, r"(?m)^\s+retention-days:\s+[1-7]\s*$", path.name)

    def test_deprecated_wrapper_workflows_stay_removed(self):
        retired = {
            "activist-scan-sync.yml",
            "drive-intake-sync.yml",
            "portfolio-news.yml",
            "batch-onboard-pdfs.yml",
            "ci-autofix-reusable.yml",
        }
        active = {path.name for path in (ROOT / ".github" / "workflows").glob("*.yml")}
        self.assertTrue(retired.isdisjoint(active))
        # Workflow count is deliberately not capped: the boundary is whether a
        # workflow has a clear owner and a bounded execution contract. A raw
        # count made a legitimate new pipeline a permanent CI failure.

    def test_only_dispatcher_invokes_marvin_action(self):
        callers = []
        for path in (ROOT / ".github" / "workflows").glob("*.yml"):
            if "uses: ./.github/actions/marvin-agent" in path.read_text(encoding="utf-8"):
                callers.append(path.name)
        self.assertEqual(callers, ["research-agent-dispatch.yml"])

    def test_active_workflows_use_pinned_install_and_shared_gate(self):
        active = [
            ROOT / ".github" / "actions" / "marvin-agent" / "action.yml",
            ROOT / ".github" / "actions" / "vicki-agent" / "action.yml",
        ]
        for path in active:
            text = path.read_text(encoding="utf-8")
            self.assertIn("actions/llm-gate", text, path.name)
            self.assertIn("npm ci", text, path.name)
            self.assertNotIn("npm install --no-save", text, path.name)
        local_runner = (ROOT / "_system" / "scripts" / "run_deep_dive.py").read_text(encoding="utf-8")
        self.assertNotIn("npm install --no-save", local_runner)
        self.assertIn("npm\", \"ci", local_runner)

    def test_committee_does_not_duplicate_open_pr_tasks(self):
        workflow = (ROOT / ".github" / "workflows" / "investment-committee.yml").read_text(encoding="utf-8")
        self.assertIn("Exclude committee tasks with an open PR", workflow)
        self.assertIn('row["task_key"] not in open_titles', workflow)
        self.assertIn('action = "waiting"', workflow)

    def test_committee_workflow_is_human_review_only(self):
        workflow = (ROOT / ".github" / "workflows" / "investment-committee.yml").read_text(encoding="utf-8")
        self.assertIn("Queue bounded human committee review", workflow)
        self.assertNotIn("committee_task_runner.mjs", workflow)
        self.assertNotIn("CURSOR_API_KEY", workflow)

    def test_agent_pr_merge_continues_after_draft_promotion(self):
        workflow = (ROOT / ".github" / "workflows" / "marvin-pr-automerge.yml").read_text(encoding="utf-8")
        self.assertIn('echo "eligible=true"', workflow)
        self.assertIn("if: needs.resolve-pr.outputs.eligible == 'true'", workflow)
        self.assertNotIn("Stop after promoting draft", workflow)

    def test_agent_pr_merge_waits_for_research_quality_without_race(self):
        workflow = (ROOT / ".github" / "workflows" / "marvin-pr-automerge.yml").read_text(encoding="utf-8")
        self.assertIn("wait_for_workflow_run.py", workflow)
        # Must match research-quality.yml's `name:` exactly: workflow_run and
        # `gh run list --workflow` resolve by name string, so a rename that
        # misses this line silently disables the wait.
        quality = (ROOT / ".github" / "workflows" / "research-quality.yml").read_text(encoding="utf-8")
        name = re.search(r"^name:\s*(.+)$", quality, re.MULTILINE).group(1).strip()
        self.assertIn(f'workflows: ["{name}"]', workflow)
        self.assertNotIn("lewagon/wait-on-check-action", workflow)

    def test_agent_pr_merge_serializes_squash_on_main(self):
        workflow = (ROOT / ".github" / "workflows" / "marvin-pr-automerge.yml").read_text(encoding="utf-8")
        self.assertIn("group: agent-automerge-main", workflow)
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn("Squash merge and delete branch", workflow)

    def test_agent_pr_merge_accepts_committee_work_artifacts(self):
        workflow = (ROOT / ".github" / "workflows" / "marvin-pr-automerge.yml").read_text(encoding="utf-8")
        self.assertIn("validate_committee_pr_artifacts.py", workflow)
        self.assertIn("validate_research_pr_provenance.py", workflow)
        self.assertIn("committee_work", workflow)
        self.assertNotIn(
            "Cursor research PR must include research_agent_manifest.json.",
            workflow,
        )

    def test_research_quality_overlays_lint_scripts_from_base(self):
        workflow = (ROOT / ".github" / "workflows" / "research-quality.yml").read_text(encoding="utf-8")
        self.assertIn("Overlay lint scripts from base branch", workflow)
        self.assertIn("lint_pr_research.py", workflow)
        self.assertIn("lint_deep_dive.py", workflow)
        self.assertIn("--name-only-file", workflow)

    def test_contract_backfill_wave_is_throttled(self):
        continue_wf = (ROOT / ".github" / "workflows" / "contract-backfill-continue.yml").read_text(
            encoding="utf-8"
        )
        queue_wf = (ROOT / ".github" / "workflows" / "marvin-deep-dive.yml").read_text(encoding="utf-8")
        dispatch = (ROOT / ".github" / "workflows" / "research-agent-dispatch.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("--wave-size 5", continue_wf)
        self.assertIn("MAX_OPEN_CURSOR_PRS", continue_wf)
        # Pre-checkout gate must not rely on a local git remote.
        self.assertIn('gh pr list --repo "${{ github.repository }}"', continue_wf)
        self.assertIn('echo "max_parallel=1"', queue_wf)
        self.assertIn("cursor_pr_backlog_", dispatch)
        self.assertIn('.mergeable == "MERGEABLE"', dispatch)
        self.assertNotIn('.mergeable != "CONFLICTING"', dispatch)

    def test_power_zone_writer_uses_shared_lock_and_retry_push(self):
        workflow = (ROOT / ".github" / "workflows" / "power-zone-universe.yml").read_text(encoding="utf-8")
        self.assertIn("group: data-commit-main", workflow)
        self.assertIn('bash _system/scripts/ci_push_main.sh "chore(valuation): process Power Zone universe"', workflow)
        self.assertNotIn('git push origin "HEAD:${GITHUB_REF_NAME}"', workflow)

    def test_research_quality_checks_use_persistent_pr_head_ref(self):
        workflow = (ROOT / ".github" / "workflows" / "research-quality.yml").read_text(encoding="utf-8")
        persistent_ref = '"pull/${{ github.event.pull_request.number }}/head"'
        # Every PR-ref checkout must use the persistent pull/N/head ref, which
        # survives a force-push, rather than the branch name. Assert the
        # property, not a count: jobs get added.
        checkouts = re.findall(r"ci_checkout_workspace\.sh \w+ (.+)$", workflow, re.MULTILINE)
        pr_checkouts = [ref for ref in checkouts if "pull_request" in ref]
        self.assertTrue(pr_checkouts)
        for ref in pr_checkouts:
            # Every PR-ref checkout must use the persistent pull/N/head form
            # (survives force-push); other persistent-ref uses (e.g. a git
            # fetch deepening history) are fine and not counted.
            self.assertTrue(ref.startswith(persistent_ref), ref)
        self.assertNotIn("github.event.pull_request.head.ref", workflow)

    def test_model_ladder_defaults_cheap_and_escalates_frontier(self):
        import llm_call_gate

        policy = json.loads((ROOT / "_system" / "config" / "llm_usage_policy.json").read_text(encoding="utf-8"))
        ladder = policy["model_ladder"]
        self.assertEqual(ladder["default_model"], "composer-2.5")
        self.assertNotEqual(ladder["frontier_model"], ladder["default_model"])
        cheap = ladder["default_model"]
        frontier = ladder["frontier_model"]
        # Mechanical lanes stay on the cheap default.
        self.assertEqual(llm_call_gate.resolve_model(policy, "vicki_ir", reason="ir_gap"), cheap)
        self.assertEqual(llm_call_gate.resolve_model(policy, "ci_autofix"), cheap)
        self.assertEqual(llm_call_gate.resolve_model(policy, "marvin_research", reason="new_documents"), cheap)
        self.assertEqual(llm_call_gate.resolve_model(policy, "investment_committee", task_id="round1-munger"), cheap)
        # Judgment-heavy lanes escalate: brand-new deep dives and chair synthesis.
        self.assertEqual(llm_call_gate.resolve_model(policy, "marvin_research", reason="no_deep_dive"), frontier)
        self.assertEqual(llm_call_gate.resolve_model(policy, "marvin_research", reason="onboard_pending"), frontier)
        self.assertEqual(llm_call_gate.resolve_model(policy, "investment_committee", task_id="chair-synthesis"), frontier)

    def test_agent_runners_and_callers_wire_the_model_ladder(self):
        for name in ("marvin_deep_dive.mjs", "committee_task_runner.mjs", "vicki_ir_harvest.mjs"):
            text = (ROOT / "_system" / "scripts" / name).read_text(encoding="utf-8")
            self.assertIn("CURSOR_MODEL_ID", text, name)
            self.assertNotIn('model: { id: "composer-2.5" }', text, name)
        marvin_action = (ROOT / ".github" / "actions" / "marvin-agent" / "action.yml").read_text(encoding="utf-8")
        self.assertIn("llm_call_gate.py model", marvin_action)
        self.assertIn("CURSOR_MODEL_ID: ${{ steps.model.outputs.model }}", marvin_action)

    def test_marvin_does_not_forward_large_manifest_as_cloud_env(self):
        runner = (ROOT / "_system" / "scripts" / "marvin_deep_dive.mjs").read_text(
            encoding="utf-8"
        )
        self.assertIn('${evidenceManifestJson || "{}"}', runner)
        cloud_env = runner.split("envVars: {", 1)[1].split("},", 1)[0]
        self.assertNotIn("RESEARCH_EVIDENCE_MANIFEST_JSON", cloud_env)

    def test_policy_encodes_expected_call_budgets(self):
        policy = json.loads((ROOT / "_system" / "config" / "llm_usage_policy.json").read_text(encoding="utf-8"))
        self.assertEqual(policy["consumers"]["marvin_research"]["daily_repo_limit"], 4)
        self.assertIn("contract_backfill", policy["consumers"]["marvin_research"]["allowed_reasons"])
        self.assertEqual(policy["consumers"]["marvin_contract_backfill"]["daily_repo_limit"], 12)
        self.assertEqual(policy["consumers"]["investment_committee"]["baseline_calls_per_ticker"], 5)
        self.assertEqual(policy["consumers"]["investment_committee"]["maximum_calls_per_ticker"], 9)
        self.assertEqual(policy["consumers"]["ci_autofix"]["minimum_repeat_count"], 2)

    def test_legacy_static_rollout_fails_closed(self):
        rollout = (ROOT / "_system" / "ci_autofix" / "apply_rollout.sh").read_text(encoding="utf-8")
        self.assertIn("deprecated", rollout.lower())
        self.assertIn("exit 2", rollout)

    def test_ci_rollout_uses_current_repeat_and_signature_controls(self):
        installer = (ROOT / "_system" / "ci_autofix" / "install_org_repos.ps1").read_text(encoding="utf-8")
        self.assertIn("minimum_repeat_count: 2", installer)
        self.assertIn("maximum_failed_jobs: 2", installer)
        self.assertIn("default_action: notify_only", installer)
        implementation = (ROOT / "_system" / "ci_autofix" / "ci_autofix.mjs").read_text(encoding="utf-8")
        self.assertIn("CI-Autofix-Agent-Signature", implementation)

    def test_audit_summary_counts_calls_and_suppressions(self):
        result = summarize([
            {"consumer": "marvin_research", "status": "reserved"},
            {"consumer": "marvin_research", "status": "completed"},
            {"consumer": "vicki_ir", "status": "suppressed", "reason": "duplicate_evidence"},
        ])
        self.assertEqual(result["by_consumer"]["marvin_research"]["completed"], 1)
        self.assertEqual(result["suppression_reasons"]["duplicate_evidence"], 1)


if __name__ == "__main__":
    unittest.main()
