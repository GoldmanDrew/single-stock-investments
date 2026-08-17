#!/usr/bin/env node
/**
 * Run Marvin company deep dive via Cursor Cloud Agent.
 * Opens a PR with research outputs — human review before merge.
 *
 * Prompt source of truth: _system/prompts/cloud_marvin_runbook.md
 * Mechanical pipeline: _system/scripts/marvin_cloud_refresh.py
 *
 * Env:
 *   CURSOR_API_KEY  — required (repo secret)
 *   TICKER          — required (e.g. 8697.T)
 *   GITHUB_REPOSITORY — owner/repo (set automatically in Actions)
 *   CURSOR_STARTING_REF - optional explicit branch/ref for Cursor Cloud Agent
 *   PICK_REASON     — optional (new_documents, new_valuation_news, manual, …)
 *   HK_PDFS_ROOT    — optional; forwarded to cloud agent (default /opt/cursor/hk_pdfs)
 */
import { readFileSync } from "node:fs";
import { Agent, CursorAgentError } from "@cursor/sdk";

const ticker = process.env.TICKER?.trim();
const apiKey = process.env.CURSOR_API_KEY?.trim();
const repo = process.env.GITHUB_REPOSITORY?.trim();
const startingRef = process.env.CURSOR_STARTING_REF?.trim();
const pickReason = process.env.PICK_REASON?.trim() || "scheduled";
const evidenceHash = process.env.RESEARCH_EVIDENCE_HASH?.trim();
const evidenceManifest = process.env.RESEARCH_EVIDENCE_MANIFEST?.trim();
const evidenceManifestJson = process.env.RESEARCH_EVIDENCE_MANIFEST_JSON?.trim();
const hkPdfsRoot = process.env.HK_PDFS_ROOT?.trim() || "/opt/cursor/hk_pdfs";
// Model ladder (_system/config/llm_usage_policy.json): callers escalate
// judgment-heavy reasons via `llm_call_gate.py model`; cheap default otherwise.
const modelId = process.env.CURSOR_MODEL_ID?.trim() || "composer-2.5";
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
let runbook = readFileSync("_system/prompts/cloud_marvin_runbook.md", "utf8");
runbook = runbook
  .replaceAll("{{TICKER}}", ticker)
  .replaceAll("{{date}}", date)
  .replaceAll("{{PICK_REASON}}", pickReason);

const prompt = `${prefix}

${runbook}

---

**Cloud agent reminder:** You MUST finish by running:
\`python _system/scripts/marvin_cloud_refresh.py ${ticker} --date ${date}\`
after narrative + valuation.json updates. Do not hand-merge valuation sections; \`refresh_deep_dive_v2.py\` owns structure.

This run is authorized only for evidence packet \`${evidenceHash || "missing"}\`.
Materialize the exact JSON below at \`${evidenceManifest || "the generated manifest"}\`, read it first, and
restrict exploration to its changed evidence plus existing decision artifacts.
Routine routing, arithmetic, pricing, committee assembly, and dashboard work are
owned by deterministic scripts. Do not spend judgment time recreating them.

Before opening the PR, you MUST run the supplied refresh command with its cloud
environment intact and commit both \`${ticker}/research/research_agent_manifest.json\`
and \`${ticker}/research/agent_run_state.json\`. The state file must carry this exact
evidence hash. These two files are required provenance for automatic merge; do not
replace them with generated timestamps or a new fingerprint.

Evidence manifest:
\`\`\`json
${evidenceManifestJson || "{}"}
\`\`\`
`;

const repoUrl = `https://github.com/${repo}`;

try {
  console.log(`Starting Marvin deep dive for ${ticker} on ${repoUrl}...`);
  console.log(`Starting ref: ${startingRef || "(Cursor default branch)"}`);
  console.log(`HK_PDFS_ROOT (cloud): ${hkPdfsRoot}`);
  console.log(`Model: ${modelId}`);
  const repoSpec = startingRef ? { url: repoUrl, startingRef } : { url: repoUrl };
  const result = await Agent.prompt(prompt, {
    apiKey,
    model: { id: modelId },
    cloud: {
      repos: [repoSpec],
      autoCreatePR: true,
      skipReviewerRequest: true,
      envVars: {
        HK_PDFS_ROOT: hkPdfsRoot,
        RESEARCH_EVIDENCE_HASH: evidenceHash || "",
        RESEARCH_EVIDENCE_MANIFEST: evidenceManifest || "",
        // The manifest may contain a full frozen epistemic work packet and can
        // exceed Cursor's 4 KiB per-env-value limit. It is already embedded in
        // the prompt above and committed in the controller queue; the cloud
        // agent materializes it at RESEARCH_EVIDENCE_MANIFEST before refresh.
        RESEARCH_PICK_REASON: pickReason,
      },
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
