import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import process from "node:process";
import { loadConfig } from "./config.mjs";
import { launchCloudAgent } from "./cursor_cloud.mjs";
import {
  createIssue,
  github,
  repoParts,
} from "./github_api.mjs";
import {
  followupIssueBody,
  isHumanNeeded,
  oneLineDiagnosis,
  shouldPostSlack,
  truncate,
  VERDICT,
} from "./inbox_format.mjs";
import { postDecision } from "./slack_inbox.mjs";

const repo = process.env.GITHUB_REPOSITORY;
const token = process.env.GH_TOKEN || process.env.GITHUB_TOKEN;
const runId = process.env.CI_AUTOFIX_RUN_ID;
const cursorApiKey = process.env.CURSOR_API_KEY;
const forceAgent = String(process.env.CI_AUTOFIX_FORCE_AGENT || "false").toLowerCase() === "true";
const eventPath = process.env.GITHUB_EVENT_PATH;
const llmLedgerPath = process.env.LLM_LEDGER_PATH || ".llm-state/ci_autofix/ledger.jsonl";
const llmGateScript = process.env.LLM_GATE_SCRIPT || "_system/scripts/llm_call_gate.py";
const llmPolicyPath = process.env.LLM_POLICY_PATH || "_system/config/llm_usage_policy.json";
const config = loadConfig();

if (!repo) fail("GITHUB_REPOSITORY is required.");
if (!token) fail("GITHUB_TOKEN/GH_TOKEN is required.");
if (!runId) fail("CI_AUTOFIX_RUN_ID is required.");

const repoUrl = `https://github.com/${repo}`;

main().catch(async (err) => {
  console.error(err);
  await postDecision({
    config,
    kind: VERDICT.AGENT_FAILED,
    repo,
    workflow: "CI Autofix",
    diagnosis: err?.message || String(err),
    next: "Check the Autofix job logs. This crash happened before a repair agent finished.",
  });
  process.exit(1);
});

async function main() {
  if (config.enabled === false) {
    console.log("CI Autofix disabled by .github/ci-autofix.yml");
    return;
  }

  const run = await github(`/repos/${repoParts(repo).owner}/${repoParts(repo).name}/actions/runs/${runId}`);
  const jobs = await getJobs();
  const failedJobs = jobs.filter((job) => ["failure", "cancelled", "timed_out", "startup_failure"].includes(job.conclusion));
  const failedLog = getFailedLog();
  const event = readEvent();
  const skippedWorkflow = (config.cursor?.skip_workflows || []).includes(run.name);
  const forkPr = isForkPullRequest(run, event);
  let classification = classifyFailure({ run, failedJobs, failedLog, skippedWorkflow, forkPr });
  const signature = failureSignature(run, failedJobs, failedLog);
  classification = { ...classification, signature };
  if (classification.action === "cursor_agent" && !forceAgent) {
    const maxJobs = Number(config.cursor?.maximum_failed_jobs || 2);
    if (failedJobs.length > maxJobs) {
      classification = { ...classification, action: "notify_only", reason: `Change surface too broad: ${failedJobs.length} failed jobs exceeds ${maxJobs}.` };
    } else {
      const repeatCount = await repeatedFailureCount(run);
      const minimum = Number(config.cursor?.minimum_repeat_count || 2);
      if (repeatCount < minimum) {
        classification = { ...classification, action: "notify_only", reason: `Failure has reproduced ${repeatCount}/${minimum} required times on this SHA.` };
      } else if (await existingSignature(signature)) {
        classification = { ...classification, action: "notify_only", reason: `Failure signature ${signature} already has an issue or PR.` };
      }
    }
  }
  const runUrl = run.html_url || `${repoUrl}/actions/runs/${runId}`;
  const summary = makeSummary({ run, failedJobs, failedLog, classification, runUrl });
  const diagnosis = oneLineDiagnosis(failedLog, classification.reason);

  console.log(summary);

  const labels = config.github?.issue_labels || ["ci-autofix", "needs-attention"];
  const shouldNotifyOnly = classification.action === "notify_only" && config.github?.create_issue_for_notify_only !== false;
  if (shouldNotifyOnly) {
    await createIssue({
      repo,
      title: `[ci-autofix] ${repo}: ${run.name} failed (${classification.category})`,
      body: summary,
      labels,
    });
  }

  if (classification.action !== "cursor_agent" && !forceAgent) {
    if (shouldPostSlack("human_needed", classification, config)) {
      await postDecision({
        config,
        kind: VERDICT.HUMAN_NEEDED,
        repo,
        workflow: run.name,
        diagnosis,
        next: nextForHuman(classification),
        runUrl,
      });
    } else {
      console.log(`Slack muted for notify-only ${classification.category}: ${classification.reason}`);
    }
    console.log(`No Cursor dispatch: ${classification.reason}`);
    return;
  }

  const llmGate = reserveLlmCall(signature, classification.category, forceAgent);
  if (!llmGate.approved) {
    console.log(`No Cursor dispatch: shared LLM gate ${llmGate.gate_reason}`);
    if (isHumanNeeded({ ...classification, reason: llmGate.gate_reason || classification.reason })) {
      await postDecision({
        config,
        kind: VERDICT.HUMAN_NEEDED,
        repo,
        workflow: run.name,
        diagnosis: `${diagnosis} Cursor was not dispatched (${llmGate.gate_reason}).`,
        next: "Raise the LLM budget or wait for cooldown, then re-run Autofix.",
        runUrl,
      });
    }
    return;
  }

  if (!cursorApiKey) {
    const text = `${summary}\n\nCursor was not dispatched because CURSOR_API_KEY is not configured.`;
    await createIssue({
      repo,
      title: `[ci-autofix] ${repo}: Cursor not configured for ${run.name}`,
      body: text,
      labels,
    });
    await postDecision({
      config,
      kind: VERDICT.HUMAN_NEEDED,
      repo,
      workflow: run.name,
      diagnosis: "CURSOR_API_KEY is not configured, so Autofix cannot start a repair agent.",
      next: "Set the org secret, then re-run the failed workflow.",
      runUrl,
    });
    recordLlmCall(signature, classification.category, "failed");
    return;
  }

  const working = shouldPostSlack("working", classification, config)
    ? await postDecision({
      config,
      kind: VERDICT.WORKING,
      repo,
      workflow: run.name,
      diagnosis,
      next: "Wait for a draft PR in this thread, or open the agent in Cursor. Reply `@Cursor` here to add instructions once the agent exists.",
      runUrl,
    })
    : null;

  let launched;
  try {
    launched = await launchCloudAgent({
      prompt: buildCursorPrompt({ run, failedJobs, failedLog, classification, runUrl }),
      repoUrl,
      startingRef: run.head_branch || run.head_sha,
      model: config.cursor?.model || "composer-2.5",
      name: `CI Autofix: ${run.name}`,
      envVars: {
        CI_AUTOFIX_RUN_ID: String(runId),
        CI_AUTOFIX_RUN_URL: runUrl,
      },
    });
    recordLlmCall(signature, classification.category, "completed");
  } catch (err) {
    recordLlmCall(signature, classification.category, "failed");
    throw err;
  }

  if (working?.ts && launched.agentId) {
    await postDecision({
      config,
      kind: VERDICT.WORKING,
      repo,
      workflow: run.name,
      diagnosis,
      next: "Cursor agent is running. Wait for the PR in this thread, or Open in Cursor.",
      runUrl,
      agentId: launched.agentId,
      threadTs: working.threadTs,
      updateTs: working.ts,
      channel: working.channel,
    });
  }

  const followupRecord = {
    version: 1,
    repo,
    run_id: String(runId),
    run_url: runUrl,
    workflow: run.name,
    signature,
    category: classification.category,
    diagnosis,
    agent_id: launched.agentId,
    cursor_run_id: launched.runId || "",
    agent_url: launched.url,
    slack: {
      channel: working?.channel || "",
      thread_ts: working?.threadTs || working?.ts || "",
      parent_ts: working?.ts || "",
    },
    pr_url: "",
    stage: "working",
    announced: { working: true, complete: false, fix_ci: null, stale: false },
    launched_at: new Date().toISOString(),
  };

  await createIssue({
    repo,
    title: `[ci-autofix followup] ${repo}: ${run.name}`,
    body: followupIssueBody(
      followupRecord,
      [
        `Workflow: ${run.name}`,
        `Failed run: ${runUrl}`,
        `Agent: ${launched.url}`,
        `Signature: ${signature}`,
      ].join("\n")
    ),
    labels: ["ci-autofix", "followup"],
  });

  console.log(`Cursor Cloud Agent launched: ${launched.agentId} ${launched.url}`);
}

function getJobs() {
  const { owner, name } = repoParts(repo);
  return github(`/repos/${owner}/${name}/actions/runs/${runId}/jobs?per_page=100`).then((out) => out.jobs || []);
}

function getFailedLog() {
  try {
    const output = execFileSync("gh", ["run", "view", String(runId), "--repo", repo, "--log-failed"], {
      encoding: "utf8",
      maxBuffer: 12 * 1024 * 1024,
      env: { ...process.env, GH_TOKEN: token },
    });
    return truncate(output, config.cursor?.max_log_chars || 45000);
  } catch (err) {
    const fallback = [err?.stdout, err?.stderr, err?.message].filter(Boolean).join("\n");
    try {
      const view = execFileSync("gh", ["run", "view", String(runId), "--repo", repo], {
        encoding: "utf8",
        maxBuffer: 4 * 1024 * 1024,
        env: { ...process.env, GH_TOKEN: token },
      });
      return truncate(`${fallback}\n\n${view}`, config.cursor?.max_log_chars || 45000);
    } catch (viewErr) {
      const viewFallback = [viewErr?.stdout, viewErr?.stderr, viewErr?.message].filter(Boolean).join("\n");
      return truncate(`${fallback}\n\n${viewFallback}`, config.cursor?.max_log_chars || 45000);
    }
  }
}

function readEvent() {
  if (!eventPath || !existsSync(eventPath)) return null;
  try {
    return JSON.parse(readFileSync(eventPath, "utf8"));
  } catch {
    return null;
  }
}

function isForkPullRequest(run, event) {
  const payloadRun = event?.workflow_run || {};
  const headRepo = payloadRun.head_repository?.full_name || run.head_repository?.full_name;
  if (!headRepo) return false;
  return headRepo.toLowerCase() !== repo.toLowerCase();
}

function classifyFailure({ run, failedJobs, failedLog, skippedWorkflow, forkPr }) {
  const text = `${run.name}\n${run.conclusion}\n${failedJobs.map((j) => `${j.name} ${j.conclusion}`).join("\n")}\n${failedLog}`.toLowerCase();
  const notifyOnly = new Set(config.classify?.notify_only || ["platform", "credentials", "permissions", "human_required"]);

  const rules = [
    {
      category: "platform",
      reason: "GitHub Actions platform, billing, spending limit, or runner startup failure.",
      patterns: [
        /payments have failed/,
        /billing/,
        /spending limit/,
        /startup_failure/,
        /job was not started/,
        /hosted runner.*unavailable/,
        /no hosted parallelism/,
        /waiting for a runner/,
      ],
    },
    {
      category: "credentials",
      reason: "Missing or invalid secret/token/credential.",
      patterns: [
        /secret .* is not set/,
        /.+\ssecret is not set/,
        /cursor_api_key.*not set/,
        /could not resolve.*secret/,
        /bad credentials/,
        /invalid token/,
        /authentication failed/,
        /usage_limit_exceeded/,
        /usage-based pricing required/,
      ],
    },
    {
      category: "permissions",
      reason: "GitHub token, repository permission, or integration permission issue.",
      patterns: [
        /resource not accessible by integration/,
        /permission denied/,
        /403 forbidden/,
        /not permitted/,
        /insufficient permission/,
      ],
    },
    {
      category: "transient",
      reason: "Likely transient network, registry, API, or timeout failure.",
      patterns: [
        /econnreset/,
        /etimedout/,
        /http 50[234]/,
        /502 bad gateway/,
        /503 service unavailable/,
        /504 gateway timeout/,
        /connection timed out/,
        /rate limit exceeded/,
        /temporarily unavailable/,
      ],
    },
    {
      category: "test_failure",
      reason: "A deterministic test or assertion failed with actionable logs.",
      patterns: [/assertionerror/, /tests? failed/, /failed tests?/, /expected .* received/, /pytest.*failed/],
    },
    {
      category: "code_failure",
      reason: "A compiler, type checker, parser, or linter found a localized code defect.",
      patterns: [/syntaxerror/, /typeerror/, /type check/, /compilation failed/, /lint errors?/, /eslint/, /ruff.*failed/, /py_compile/],
    },
    {
      category: "schema_failure",
      reason: "A deterministic schema or contract validation failed.",
      patterns: [/schema validation/, /jsonschema/, /additional properties are not allowed/, /required property/],
    },
  ];

  if (skippedWorkflow) {
    return { category: "configuration", action: "notify_only", reason: "Workflow is excluded from CI Autofix." };
  }
  if (forkPr && config.cursor?.skip_fork_prs !== false) {
    return { category: "fork_pr", action: "notify_only", reason: "Fork pull request skipped to avoid privileged repair on untrusted code." };
  }

  for (const rule of rules) {
    if (rule.patterns.some((pattern) => pattern.test(text))) {
      const action = notifyOnly.has(rule.category) || (rule.category === "transient" && config.classify?.transient_retry_first !== false)
        ? "notify_only"
        : "cursor_agent";
      return { category: rule.category, action, reason: rule.reason };
    }
  }

  if (!failedLog.trim()) {
    return { category: "no_logs", action: "notify_only", reason: "No failed logs were available for agent context." };
  }

  return {
    category: "unclassified",
    action: config.classify?.default_action || "notify_only",
    reason: "Failure does not match the narrow test/code/schema allowlist.",
  };
}

function failureSignature(run, failedJobs, failedLog) {
  const normalizedLog = String(failedLog || "")
    .split("\n")
    .filter((line) => /error|failed|exception|traceback|assert/i.test(line))
    .slice(0, 80)
    .join("\n")
    .replace(/\b\d{4}-\d{2}-\d{2}[T ][\d:.+-]+Z?\b/g, "<time>")
    .replace(/\b[0-9a-f]{7,64}\b/gi, "<sha>");
  const value = JSON.stringify({
    workflow: run.workflow_id || run.name,
    sha: run.head_sha,
    jobs: failedJobs.map((job) => job.name).sort(),
    log: normalizedLog,
  });
  return createHash("sha256").update(value).digest("hex").slice(0, 24);
}

async function repeatedFailureCount(run) {
  if (!run.workflow_id || !run.head_sha) return 1;
  const { owner, name } = repoParts(repo);
  const data = await github(`/repos/${owner}/${name}/actions/workflows/${run.workflow_id}/runs?head_sha=${encodeURIComponent(run.head_sha)}&status=completed&per_page=20`);
  const separateRuns = (data.workflow_runs || []).filter((row) => ["failure", "timed_out"].includes(row.conclusion)).length;
  return Math.max(separateRuns, Number(run.run_attempt || 1));
}

async function existingSignature(signature) {
  const query = encodeURIComponent(`repo:${repo} \"CI-Autofix-Agent-Signature: ${signature}\"`);
  const data = await github(`/search/issues?q=${query}&per_page=1`);
  return Number(data.total_count || 0) > 0;
}

function reserveLlmCall(signature, reason, force) {
  const args = [
    llmGateScript, "evaluate",
    "--consumer", "ci_autofix", "--subject", signature,
    "--reason", reason, "--evidence-hash", signature,
    "--ledger", llmLedgerPath, "--policy", llmPolicyPath, "--reserve",
  ];
  if (force) args.push("--force");
  const output = execFileSync("python", args, { encoding: "utf8" });
  return JSON.parse(output);
}

function recordLlmCall(signature, reason, status) {
  execFileSync("python", [
    llmGateScript, "record",
    "--consumer", "ci_autofix", "--subject", signature,
    "--reason", reason, "--evidence-hash", signature,
    "--ledger", llmLedgerPath, "--policy", llmPolicyPath, "--status", status,
  ], { stdio: "inherit" });
}

function makeSummary({ run, failedJobs, failedLog, classification, runUrl }) {
  const steps = [];
  for (const job of failedJobs) {
    const failedSteps = (job.steps || [])
      .filter((step) => ["failure", "cancelled", "timed_out"].includes(step.conclusion))
      .map((step) => `  - ${step.name}: ${step.conclusion}`)
      .join("\n");
    steps.push(`- ${job.name}: ${job.conclusion}${failedSteps ? `\n${failedSteps}` : ""}`);
  }

  return [
    `## CI Autofix triage`,
    ``,
    `Repository: ${repo}`,
    `Workflow: ${run.name}`,
    `Run: ${runUrl}`,
    `Branch: ${run.head_branch || "unknown"}`,
    `SHA: ${run.head_sha || "unknown"}`,
    `Conclusion: ${run.conclusion}`,
    `Classification: ${classification.category}`,
    `Action: ${classification.action}`,
    `Reason: ${classification.reason}`,
    ``,
    `### Failed jobs`,
    steps.length ? steps.join("\n") : "No failed job details available.",
    ``,
    `### Log excerpt`,
    "```text",
    truncate(failedLog || "No failed log excerpt available.", 6000),
    "```",
  ].join("\n");
}

function nextForHuman(classification) {
  if (classification.category === "credentials") return "Fix the missing or invalid secret, then re-run the workflow.";
  if (classification.category === "permissions") return "Fix token or integration permissions, then re-run the workflow.";
  if (classification.category === "platform") return "This is a GitHub billing/runner issue, not a code bug. Restore Actions capacity.";
  if (/too broad/i.test(classification.reason || "")) return "The failure is too wide for Autofix. Inspect the run and split the fix.";
  return classification.reason || "Inspect the failed run. Autofix will not start an agent for this class of failure.";
}

function buildCursorPrompt({ run, failedJobs, failedLog, classification, runUrl }) {
  const repoNotes = config.repo_notes ? `\nRepository notes:\n${config.repo_notes}\n` : "";
  const failedJobText = failedJobs.map((job) => {
    const steps = (job.steps || [])
      .filter((step) => step.conclusion && step.conclusion !== "success")
      .map((step) => `  - ${step.name}: ${step.conclusion}`)
      .join("\n");
    return `- ${job.name}: ${job.conclusion}${steps ? `\n${steps}` : ""}`;
  }).join("\n");

  return `You are a senior software engineer fixing a failing GitHub Actions workflow.

Goal:
- Investigate the failed workflow.
- Make the smallest correct code/config/test fix.
- Run the relevant local verification commands if possible.
- Open a draft pull request with a clear title, diagnosis, fix summary, and verification notes.

Guardrails:
- Do not auto-merge.
- Do not make unrelated refactors.
- Do not commit secrets or credentials.
- If the issue is external platform/billing/secrets/permissions and no code fix is possible, open a PR only if you can improve diagnostics or guardrails. Otherwise report clearly.
- Label the PR with: ${(config.github?.pr_labels || ["ci-autofix", "agent-generated", "needs-human-review"]).join(", ")}

Repository: ${repoUrl}
Workflow: ${run.name}
Run URL: ${runUrl}
Branch: ${run.head_branch || "unknown"}
SHA: ${run.head_sha || "unknown"}
Classification: ${classification.category}
Classifier reason: ${classification.reason}
CI-Autofix-Signature: ${classification.signature}
${repoNotes}
Failed jobs:
${failedJobText || "No failed job details available."}

Failed log excerpt:
\`\`\`text
${truncate(failedLog, config.cursor?.max_log_chars || 45000)}
\`\`\`

Include this exact marker in the pull request body:
CI-Autofix-Agent-Signature: ${classification.signature}

Your LAST message must use this exact shape, one field per line:
DIAGNOSIS: <one sentence>
FILES: <comma-separated paths, or none>
RISK: low|medium|high — <why>
MERGE?: yes|no — <why>
COMMANDS: <what you ran>
NEXT: <what a human should do in Slack>
`;
}

function fail(message) {
  console.error(message);
  process.exit(1);
}
