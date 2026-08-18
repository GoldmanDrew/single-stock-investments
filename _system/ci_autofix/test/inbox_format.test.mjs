import assert from "node:assert/strict";
import test from "node:test";
import {
  briefToDiagnosis,
  encodeFollowup,
  isHumanNeeded,
  oneLineDiagnosis,
  parseAgentBrief,
  parseFollowup,
  prNumberFromUrl,
  replaceFollowup,
  runIsFailure,
  runIsTerminal,
  shouldPostSlack,
  summarizeCheckRuns,
  VERDICT,
} from "../inbox_format.mjs";
import { buildDecisionBlocks, decisionLinks } from "../slack_inbox.mjs";

test("mutes ordinary notify-only failures", () => {
  const config = { slack: { enabled: true, notify_human_needed: true } };
  assert.equal(shouldPostSlack("human_needed", { category: "transient", reason: "timeout" }, config), false);
  assert.equal(shouldPostSlack("human_needed", { category: "unclassified", reason: "no match" }, config), false);
  assert.equal(shouldPostSlack("human_needed", { category: "credentials", reason: "secret missing" }, config), true);
  assert.equal(isHumanNeeded({ reason: "Change surface too broad: 5 failed jobs exceeds 2." }), true);
});

test("posts working and completion kinds even when classification is quiet", () => {
  const config = { slack: { enabled: true } };
  assert.equal(shouldPostSlack("working", { category: "test_failure" }, config), true);
  assert.equal(shouldPostSlack("complete", { category: "test_failure" }, config), true);
  assert.equal(shouldPostSlack("fix_pr_ci", { category: "test_failure" }, config), true);
});

test("oneLineDiagnosis prefers a short error line over a stack dump", () => {
  const log = [
    "2026-08-18T12:00:00.000Z ##[error] AssertionError: expected 2 received 3",
    "a".repeat(4000),
  ].join("\n");
  assert.match(oneLineDiagnosis(log, "fallback"), /AssertionError/);
});

test("parseAgentBrief reads the Slack-shaped last message", () => {
  const brief = parseAgentBrief(`
DIAGNOSIS: Hash ledger drifted after the Darwin refresh.
FILES: DD/research/valuation.json, _system/scripts/foo.py
RISK: low — test-only fixture
MERGE?: yes — localized assertion fix
COMMANDS: pytest _system/scripts/test_foo.py
NEXT: Merge if the PR CI is green.
`);
  assert.equal(brief.diagnosis.startsWith("Hash ledger"), true);
  assert.equal(brief.merge.startsWith("yes"), true);
  assert.equal(briefToDiagnosis(brief, "fallback").includes("Hash ledger"), true);
});

test("follow-up marker round-trips", () => {
  const record = { version: 1, agent_id: "bc-1", stage: "working" };
  const parsed = parseFollowup(encodeFollowup(record));
  assert.equal(parsed.agent_id, "bc-1");
  const updated = replaceFollowup("hello\n" + encodeFollowup(record), { ...record, stage: "review_pr" });
  assert.equal(parseFollowup(updated).stage, "review_pr");
});

test("PR helpers and check summaries", () => {
  assert.equal(prNumberFromUrl("https://github.com/magis-capital-partners/single-stock-investments/pull/401"), 401);
  assert.equal(runIsTerminal("FINISHED"), true);
  assert.equal(runIsFailure("ERROR"), true);
  assert.equal(summarizeCheckRuns([{ name: "test", status: "completed", conclusion: "success" }]).state, "green");
  assert.equal(summarizeCheckRuns([{ name: "test", status: "completed", conclusion: "failure" }]).state, "red");
  assert.equal(summarizeCheckRuns([{ name: "test", status: "in_progress", conclusion: null }]).state, "pending");
});

test("decision cards stay compact and include action buttons", () => {
  const blocks = buildDecisionBlocks({
    kind: VERDICT.REVIEW_PR,
    repo: "magis-capital-partners/single-stock-investments",
    workflow: "Research quality",
    diagnosis: "Ledger hash drifted.",
    next: "Skim the draft PR.",
    links: decisionLinks({
      runUrl: "https://github.com/org/repo/actions/runs/1",
      prUrl: "https://github.com/org/repo/pull/2",
      agentId: "bc-abc",
    }),
  });
  const json = JSON.stringify(blocks);
  assert.equal(json.includes("Review PR"), true);
  assert.equal(json.includes("Open PR"), true);
  assert.equal(json.includes("Open in Cursor"), true);
  assert.equal(json.includes("Reply `@Cursor`"), true);
  assert.ok(json.length < 4000);
});
