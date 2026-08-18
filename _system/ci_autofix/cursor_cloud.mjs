const API = "https://api.cursor.com";

function apiKey() {
  const key = process.env.CURSOR_API_KEY;
  if (!key) throw new Error("CURSOR_API_KEY is required.");
  return key;
}

export async function cursorApi(path, { method = "GET", body, authMode = "bearer" } = {}) {
  const key = apiKey();
  const authorization = authMode === "basic"
    ? `Basic ${Buffer.from(`${key}:`).toString("base64")}`
    : `Bearer ${key}`;
  const res = await fetch(`${API}${path}`, {
    method,
    headers: {
      Authorization: authorization,
      Accept: "application/json",
      ...(body ? { "content-type": "application/json" } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { raw: text };
  }
  if (res.status === 401 && authMode === "bearer") {
    return cursorApi(path, { method, body, authMode: "basic" });
  }
  if (!res.ok) {
    throw new Error(`Cursor API ${res.status} ${method} ${path}: ${text.slice(0, 2000)}`);
  }
  return data;
}

export async function launchCloudAgent({ prompt, repoUrl, startingRef, model, name, envVars }) {
  const payload = {
    prompt: { text: prompt },
    name: String(name || "CI Autofix").slice(0, 100),
    repos: [
      {
        url: repoUrl,
        ...(startingRef ? { startingRef } : {}),
      },
    ],
    autoCreatePR: true,
    skipReviewerRequest: true,
  };
  if (model) payload.model = { id: model };
  if (envVars && Object.keys(envVars).length) payload.envVars = envVars;

  const data = await cursorApi("/v1/agents", { method: "POST", body: payload });
  const agent = data.agent || data;
  const run = data.run || {};
  if (!agent?.id) {
    throw new Error(`Cursor create did not return an agent id: ${JSON.stringify(data).slice(0, 1000)}`);
  }
  return {
    agentId: agent.id,
    runId: run.id || agent.latestRunId || "",
    url: agent.url || `https://cursor.com/agents/${agent.id}`,
    status: run.status || agent.status || "CREATING",
  };
}

export async function getCloudAgent(agentId) {
  return cursorApi(`/v1/agents/${encodeURIComponent(agentId)}`);
}

export async function getCloudRun(agentId, runId) {
  if (!runId) {
    const agent = await getCloudAgent(agentId);
    runId = agent.latestRunId;
  }
  if (!runId) return null;
  return cursorApi(`/v1/agents/${encodeURIComponent(agentId)}/runs/${encodeURIComponent(runId)}`);
}
