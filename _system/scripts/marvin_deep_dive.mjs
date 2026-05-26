#!/usr/bin/env node
/**
 * Run Marvin company deep dive via Cursor Cloud Agent.
 * Opens a PR with research outputs — human review before merge.
 *
 * Env:
 *   CURSOR_API_KEY  — required (repo secret)
 *   TICKER          — required (e.g. 8697.T)
 *   GITHUB_REPOSITORY — owner/repo (set automatically in Actions)
 */
import { readFileSync } from "node:fs";
import { Agent, CursorAgentError } from "@cursor/sdk";

const ticker = process.env.TICKER?.trim();
const apiKey = process.env.CURSOR_API_KEY?.trim();
const repo = process.env.GITHUB_REPOSITORY?.trim();
const pickReason = process.env.PICK_REASON?.trim() || "scheduled";
const date = new Date().toISOString().slice(0, 10);

if (!apiKey) {
  console.error("CURSOR_API_KEY is required.");
  process.exit(1);
}
if (!ticker) {
  console.error("TICKER is required.");
  process.exit(1);
}
if (!repo) {
  console.error("GITHUB_REPOSITORY is required (owner/repo).");
  process.exit(1);
}

const prefix = readFileSync("_system/prompts/_prefix.md", "utf8");
let template = readFileSync("_system/prompts/company-deep-dive.md", "utf8");
template = template.replaceAll("{{TICKER}}", ticker).replaceAll("{{date}}", date);

const prompt = `${prefix}

${template}

Additional instructions for this cloud run:
- Pick reason: ${pickReason} — if "new_documents", this is a **refresh** after daily download sync; read any files newer than the prior deep_dive_*.md. If "new_valuation_news", read dashboard/data/portfolio_news.json and {ticker}/research/news/news_index.json for refresh-eligible headlines since the last deep dive; focus the write-up on **what changed for cash flows / valuation**, not a full re-read of unchanged primary docs unless needed.
- Apply approved beliefs from _system/memory/MEMORY.md (Munger, Pabrai, Stahl sections).
- Apply lenses from _system/reference/investment-wisdom/INDEX.md for this ticker.
- Read `_system/frameworks/decision_stack.md` only (not mental_models + lawrence_irr separately).
- Follow `_system/prompts/deep_dive_template.md` — five sections: Executive summary, Business & moat, Payoff & return, Risks & inversion, Classification.
- Update ${ticker}/research/valuation.json; run \`python _system/scripts/marvin_valuation.py --ticker ${ticker} --write\`.
- Run \`python _system/scripts/sync_classification.py --fix --ticker ${ticker}\` then build_dashboard_data.py.
- Use stance from valuation.json stance_proposal unless override documented in [HUMAN REVIEW].
- End reports with Classification table, [HUMAN REVIEW], and [PROPOSED COMPANY] bullets only.
`;

const repoUrl = `https://github.com/${repo}`;

try {
  console.log(`Starting Marvin deep dive for ${ticker} on ${repoUrl}...`);
  const result = await Agent.prompt(prompt, {
    apiKey,
    model: { id: "composer-2" },
    cloud: {
      repos: [{ url: repoUrl }],
      autoCreatePR: true,
      skipReviewerRequest: true,
    },
  });

  console.log("Status:", result.status);
  console.log("Agent ID:", result.agentId);
  if (result.prUrl) console.log("PR:", result.prUrl);
  if (result.result) console.log("Summary:", result.result.slice(0, 500));

  if (result.status === "error") {
    console.error("Agent run failed.");
    process.exit(2);
  }
} catch (err) {
  if (err instanceof CursorAgentError) {
    console.error("Startup failed:", err.message, "retryable=", err.isRetryable);
    process.exit(1);
  }
  throw err;
}
