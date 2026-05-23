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
- Use Classification table (archetype, moat, dhando, stance, cycle) per _system/frameworks/classification.md — not legacy thesis status.
- Do NOT edit _system/memory/MEMORY.md — use [PROPOSED COMPANY] in daily log only.
- Write ${ticker}/research/deep_dive_${date}.md (new dated file; keep prior dives for history).
- Update ${ticker}/research/thesis.md Classification + one-line thesis if primary docs support changes.
- Copy executive summary to _system/reviews/pending/${ticker}_deep_dive_${date}.md
- Run: python _system/scripts/build_dashboard_data.py
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
