import process from "node:process";
import { loadConfig } from "./config.mjs";
import { getCloudAgent, getCloudRun } from "./cursor_cloud.mjs";
import {
  addIssueLabels,
  getCheckRuns,
  getPull,
  listRepoIssues,
  repoFromIssue,
  searchIssues,
  updateIssue,
} from "./github_api.mjs";
import {
  briefToDiagnosis,
  firstPrUrl,
  followupIssueBody,
  parseAgentBrief,
  parseFollowup,
  prNumberFromUrl,
  replaceFollowup,
  runIsFailure,
  runIsTerminal,
  summarizeCheckRuns,
  VERDICT,
} from "./inbox_format.mjs";
import { postDecision } from "./slack_inbox.mjs";

const STALE_MS = 6 * 60 * 60 * 1000;

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

async function main() {
  const config = loadConfig();
  const issues = await loadFollowups();
  console.log(`Follow-up sweep: ${issues.length} open ledger issue(s)`);
  for (const issue of issues) {
    try {
      await processIssue(issue, config);
    } catch (err) {
      console.warn(`Follow-up failed for ${issue.html_url}: ${err.message}`);
    }
  }
}

async function loadFollowups() {
  const org = process.env.CI_AUTOFIX_ORG;
  if (org) {
    const items = await searchIssues(`org:${org} label:followup label:ci-autofix is:open is:issue`);
    return items.filter((issue) => !issue.pull_request);
  }
  const repo = process.env.GITHUB_REPOSITORY;
  if (!repo) throw new Error("GITHUB_REPOSITORY or CI_AUTOFIX_ORG is required.");
  const items = await listRepoIssues({ repo, labels: ["ci-autofix", "followup"], state: "open" });
  return items.filter((issue) => !issue.pull_request);
}

async function processIssue(issue, config) {
  const record = parseFollowup(issue.body);
  if (!record?.agent_id) {
    console.log(`Skipping ${issue.html_url}: no follow-up marker`);
    return;
  }
  const repo = record.repo || repoFromIssue(issue, process.env.GITHUB_REPOSITORY);
  const slack = record.slack || {};

  let agent;
  let run;
  try {
    agent = await getCloudAgent(record.agent_id);
    run = await getCloudRun(record.agent_id, record.cursor_run_id || agent.latestRunId);
  } catch (err) {
    console.warn(`Cursor lookup failed for ${record.agent_id}: ${err.message}`);
    if (!record.announced?.complete) {
      await announce(config, record, repo, slack, {
        kind: VERDICT.AGENT_FAILED,
        diagnosis: `Could not load Cursor agent ${record.agent_id}: ${err.message}`,
        next: "Open the failed GitHub run and retry Autofix if the agent is gone.",
      });
      record.announced = { ...record.announced, complete: true };
      record.stage = "agent_failed";
      await save(issue, repo, record, "closed");
    }
    return;
  }

  const status = run?.status || agent.status || "";
  const prUrl = firstPrUrl(run?.git) || record.pr_url || "";
  record.cursor_run_id = run?.id || record.cursor_run_id;
  record.pr_url = prUrl;
  record.agent_url = agent.url || record.agent_url;

  if (!runIsTerminal(status)) {
    const launchedAt = Date.parse(record.launched_at || issue.created_at || "") || 0;
    if (launchedAt && Date.now() - launchedAt > STALE_MS && !record.announced?.stale) {
      await announce(config, record, repo, slack, {
        kind: VERDICT.STALE,
        diagnosis: record.diagnosis || "Cursor agent is still running after 6 hours.",
        next: "Open in Cursor and check whether it is stuck. Reply `@Cursor` in this thread if you want to redirect it.",
        prUrl,
      });
      record.announced = { ...record.announced, stale: true };
      record.stage = "stale";
      await save(issue, repo, record, "open");
    } else {
      console.log(`${record.agent_id} still ${status || "running"}`);
    }
    return;
  }

  if (runIsFailure(status) && !record.announced?.complete) {
    const brief = parseAgentBrief(run.result || "");
    await announce(config, record, repo, slack, {
      kind: VERDICT.AGENT_FAILED,
      diagnosis: briefToDiagnosis(brief, run.result || `Cursor run ended with ${status}.`),
      next: "Inspect the agent in Cursor. If this is still a code failure, reply `@Cursor` with a tighter instruction.",
      prUrl,
    });
    record.announced = { ...record.announced, complete: true };
    record.stage = "agent_failed";
    await save(issue, repo, record, "closed");
    return;
  }

  if (!record.announced?.complete || (prUrl && record.stage === "no_pr")) {
    const brief = parseAgentBrief(run.result || "");
    const kind = prUrl ? VERDICT.REVIEW_PR : VERDICT.NO_PR;
    const diagnosis = briefToDiagnosis(brief, record.diagnosis || "Cursor finished.");
    const next = prUrl
      ? (brief.next || "Skim the draft PR. Merge only after you agree with the diagnosis. Reply `@Cursor` here if CI on the fix is still red.")
      : (brief.next || "The agent finished without a PR. Read the diagnosis and decide whether to follow up in this thread.");
    await announce(config, record, repo, slack, { kind, diagnosis, next, prUrl });
    record.announced = { ...record.announced, complete: true };
    record.stage = prUrl ? "review_pr" : "no_pr";
    if (prUrl) await labelFixPr(repo, prUrl, config);
    if (!prUrl) {
      await save(issue, repo, record, "closed");
      return;
    }
    await save(issue, repo, record, "open");
  }

  if (!prUrl) return;

  const number = prNumberFromUrl(prUrl);
  if (!number) return;
  const pull = await getPull({ repo, number });
  if (pull.merged || pull.state === "closed") {
    record.stage = "done";
    await save(issue, repo, record, "closed");
    return;
  }
  const checks = await getCheckRuns({ repo, sha: pull.head.sha });
  const summary = summarizeCheckRuns(checks);
  if (summary.state === "pending") {
    console.log(`${prUrl} CI pending: ${summary.detail}`);
    return;
  }
  if (summary.state === "green" && record.announced?.fix_ci !== "green") {
    await announce(config, record, repo, slack, {
      kind: VERDICT.FIX_CI_GREEN,
      diagnosis: `${summary.detail} on ${prUrl}`,
      next: "Review the PR and merge if the diagnosis is right.",
      prUrl,
    });
    record.announced = { ...record.announced, fix_ci: "green" };
    record.stage = "fix_ci_green";
    await save(issue, repo, record, "closed");
    return;
  }
  if (summary.state === "red" && record.announced?.fix_ci !== "red") {
    await announce(config, record, repo, slack, {
      kind: VERDICT.FIX_CI_RED,
      diagnosis: `Fix PR CI failed: ${summary.detail}`,
      next: `Reply \`@Cursor\` in this thread with the failing check, or Open in Cursor and send a follow-up.`,
      prUrl,
    });
    record.announced = { ...record.announced, fix_ci: "red" };
    record.stage = "fix_ci_red";
    await save(issue, repo, record, "open");
  }
}

async function labelFixPr(repo, prUrl, config) {
  const number = prNumberFromUrl(prUrl);
  if (!number) return;
  const labels = config.github?.pr_labels || ["ci-autofix", "agent-generated", "needs-human-review"];
  await addIssueLabels({ repo, number, labels });
}

async function announce(config, record, repo, slack, { kind, diagnosis, next, prUrl }) {
  await postDecision({
    config,
    kind,
    repo,
    workflow: record.workflow,
    diagnosis,
    next,
    runUrl: record.run_url,
    prUrl: prUrl || record.pr_url,
    agentId: record.agent_id,
    threadTs: slack.thread_ts,
    channel: slack.channel,
  });
  if (slack.parent_ts && kind !== VERDICT.WORKING) {
    await postDecision({
      config,
      kind,
      repo,
      workflow: record.workflow,
      diagnosis,
      next,
      runUrl: record.run_url,
      prUrl: prUrl || record.pr_url,
      agentId: record.agent_id,
      updateTs: slack.parent_ts,
      channel: slack.channel,
    });
  }
}

async function save(issue, repo, record, state) {
  const body = replaceFollowup(
    followupIssueBody(record, [
      `Workflow: ${record.workflow}`,
      `Failed run: ${record.run_url}`,
      `Agent: ${record.agent_url || record.agent_id}`,
      record.pr_url ? `PR: ${record.pr_url}` : "PR: none yet",
      record.signature ? `CI-Autofix-Agent-Signature: ${record.signature}` : "",
      `Stage: ${record.stage}`,
    ].join("\n")),
    record
  );
  await updateIssue({ repo, number: issue.number, body, state });
  console.log(`Updated ${repo}#${issue.number} stage=${record.stage} state=${state}`);
}
