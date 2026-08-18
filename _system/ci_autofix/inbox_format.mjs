export const FOLLOWUP_MARKER = "CI-AUTOFIX-FOLLOWUP";

export const VERDICT = {
  HUMAN_NEEDED: "HUMAN_NEEDED",
  WORKING: "WORKING",
  REVIEW_PR: "REVIEW_PR",
  NO_PR: "NO_PR",
  AGENT_FAILED: "AGENT_FAILED",
  FIX_CI_GREEN: "FIX_CI_GREEN",
  FIX_CI_RED: "FIX_CI_RED",
  STALE: "STALE",
};

export const VERDICT_LABEL = {
  HUMAN_NEEDED: "Human needed",
  WORKING: "Working",
  REVIEW_PR: "Review PR",
  NO_PR: "No PR",
  AGENT_FAILED: "Autofix failed",
  FIX_CI_GREEN: "Fix PR CI green",
  FIX_CI_RED: "Fix PR CI red",
  STALE: "Still running",
};

export const HUMAN_NEEDED_CATEGORIES = new Set(["credentials", "permissions", "platform"]);

export function truncate(value, max) {
  const text = String(value || "");
  if (text.length <= max) return text;
  return `${text.slice(0, Math.floor(max * 0.65))}\n\n... [truncated ${text.length - max} chars] ...\n\n${text.slice(-Math.floor(max * 0.35))}`;
}

export function shortRepo(repo) {
  return String(repo || "").split("/")[1] || repo || "unknown";
}

export function agentUrl(agentId) {
  if (!agentId) return "";
  return `https://cursor.com/agents/${agentId}`;
}

export function prNumberFromUrl(prUrl) {
  const match = String(prUrl || "").match(/\/pull\/(\d+)/);
  return match ? Number(match[1]) : null;
}

export function isHumanNeeded(classification = {}) {
  if (HUMAN_NEEDED_CATEGORIES.has(classification.category)) return true;
  const reason = String(classification.reason || "");
  if (/too broad|change surface too broad/i.test(reason)) return true;
  if (/cursor_api_key|not configured/i.test(reason)) return true;
  return false;
}

export function shouldPostSlack(kind, classification, config = {}) {
  if (config.slack?.enabled === false) return false;
  if (kind === "working" || kind === "complete" || kind === "fix_pr_ci" || kind === "stale" || kind === "agent_failed") {
    return true;
  }
  if (kind === "human_needed") {
    return config.slack?.notify_human_needed !== false && isHumanNeeded(classification);
  }
  return false;
}

export function oneLineDiagnosis(failedLog, fallback) {
  const lines = String(failedLog || "").split(/\r?\n/);
  for (const raw of lines) {
    const line = raw
      .replace(/^\d{4}-\d{2}-\d{2}T[\d:.]+Z\s*/, "")
      .replace(/^##\[error\]\s*/i, "")
      .replace(/\s+/g, " ")
      .trim();
    if (line.length < 16 || line.length > 220) continue;
    if (/error|failed|exception|traceback|assert|denied|forbidden/i.test(line)) {
      return line;
    }
  }
  return fallback || "See the failed run for details.";
}

export function parseAgentBrief(text) {
  const source = String(text || "");
  const grab = (label) => {
    const match = source.match(new RegExp(`^${label}:\\s*(.+)$`, "im"));
    return match ? match[1].trim() : "";
  };
  return {
    diagnosis: grab("DIAGNOSIS"),
    files: grab("FILES"),
    risk: grab("RISK"),
    merge: grab("MERGE\\?"),
    commands: grab("COMMANDS"),
    next: grab("NEXT"),
    raw: source,
  };
}

export function briefToDiagnosis(brief, fallback) {
  if (brief?.diagnosis) return brief.diagnosis;
  const raw = String(brief?.raw || "").trim();
  if (!raw) return fallback;
  return raw.split(/\r?\n/).map((line) => line.trim()).find(Boolean) || fallback;
}

export function encodeFollowup(record) {
  return `<!-- ${FOLLOWUP_MARKER}\n${JSON.stringify(record, null, 2)}\n-->`;
}

export function parseFollowup(body) {
  const match = String(body || "").match(new RegExp(`<!--\\s*${FOLLOWUP_MARKER}\\s*([\\s\\S]*?)-->`));
  if (!match) return null;
  try {
    return JSON.parse(match[1]);
  } catch {
    return null;
  }
}

export function replaceFollowup(body, record) {
  const encoded = encodeFollowup(record);
  const source = String(body || "");
  if (new RegExp(`<!--\\s*${FOLLOWUP_MARKER}\\s*[\\s\\S]*?-->`).test(source)) {
    return source.replace(new RegExp(`<!--\\s*${FOLLOWUP_MARKER}\\s*[\\s\\S]*?-->`), encoded);
  }
  return `${encoded}\n\n${source}`.trim();
}

export function followupIssueBody(record, human) {
  return [
    encodeFollowup(record),
    "",
    "## Magis CI Autofix follow-up",
    "",
    human,
    "",
    "This issue is a machine ledger for Slack inbox updates. Close it only if you want the poller to stop watching this incident.",
  ].join("\n");
}

export function firstPrUrl(git) {
  const branches = git?.branches || [];
  for (const branch of branches) {
    if (branch?.prUrl) return branch.prUrl;
  }
  return "";
}

export function runIsTerminal(status) {
  return ["FINISHED", "ERROR", "CANCELLED", "EXPIRED", "finished", "error", "cancelled", "expired"].includes(String(status || ""));
}

export function runIsFailure(status) {
  return ["ERROR", "CANCELLED", "EXPIRED", "error", "cancelled", "expired"].includes(String(status || ""));
}

export function summarizeCheckRuns(checkRuns = []) {
  const failed = checkRuns.filter((run) =>
    ["failure", "timed_out", "cancelled", "startup_failure", "action_required"].includes(run.conclusion)
  );
  const pending = checkRuns.filter((run) =>
    ["queued", "in_progress", "waiting", "pending", "requested"].includes(run.status)
  );
  if (failed.length) {
    return {
      state: "red",
      detail: failed.slice(0, 4).map((run) => run.name).join(", ") || "a check failed",
    };
  }
  if (!checkRuns.length || pending.length) {
    return { state: "pending", detail: pending.length ? `${pending.length} checks still running` : "checks not posted yet" };
  }
  return { state: "green", detail: `${checkRuns.length} checks passed` };
}
