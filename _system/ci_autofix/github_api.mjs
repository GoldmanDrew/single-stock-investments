const token = process.env.GH_TOKEN || process.env.GITHUB_TOKEN;

export function repoParts(fullName = process.env.GITHUB_REPOSITORY) {
  if (!fullName || !fullName.includes("/")) {
    throw new Error("GITHUB_REPOSITORY is required.");
  }
  const [owner, name] = fullName.split("/");
  return { owner, name, repo: fullName };
}

export async function github(path, options = {}) {
  if (!token) throw new Error("GITHUB_TOKEN/GH_TOKEN is required.");
  const res = await fetch(`https://api.github.com${path}`, {
    ...options,
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${token}`,
      "X-GitHub-Api-Version": "2022-11-28",
      ...(options.headers || {}),
    },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`GitHub API ${res.status} ${path}: ${body}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

export async function ensureLabels(repoFullName, labels = []) {
  const { owner, name } = repoParts(repoFullName);
  for (const label of labels) {
    try {
      await github(`/repos/${owner}/${name}/labels/${encodeURIComponent(label)}`);
    } catch {
      try {
        await github(`/repos/${owner}/${name}/labels`, {
          method: "POST",
          body: JSON.stringify({
            name: label,
            color: label === "needs-attention" ? "d93f0b" : label === "followup" ? "0e8a16" : "5319e7",
          }),
        });
      } catch {
        // Non-fatal. The issue can still be created without labels in some permission configurations.
      }
    }
  }
}

export async function createIssue({ repo: repoFullName, title, body, labels }) {
  const { owner, name } = repoParts(repoFullName);
  try {
    await ensureLabels(repoFullName, labels);
    const issue = await github(`/repos/${owner}/${name}/issues`, {
      method: "POST",
      body: JSON.stringify({ title, body, labels }),
    });
    console.log(`Created issue: ${issue.html_url}`);
    return issue;
  } catch (err) {
    console.warn(`Could not create issue: ${err.message}`);
    return null;
  }
}

export async function updateIssue({ repo: repoFullName, number, body, state }) {
  const { owner, name } = repoParts(repoFullName);
  return github(`/repos/${owner}/${name}/issues/${number}`, {
    method: "PATCH",
    body: JSON.stringify({
      ...(body ? { body } : {}),
      ...(state ? { state } : {}),
    }),
  });
}

export async function searchIssues(query) {
  const data = await github(`/search/issues?q=${encodeURIComponent(query)}&per_page=50`);
  return data.items || [];
}

export async function listRepoIssues({ repo: repoFullName, labels, state = "open" }) {
  const { owner, name } = repoParts(repoFullName);
  const params = new URLSearchParams({
    state,
    labels: labels.join(","),
    per_page: "50",
  });
  return github(`/repos/${owner}/${name}/issues?${params}`);
}

export async function addIssueLabels({ repo: repoFullName, number, labels }) {
  const { owner, name } = repoParts(repoFullName);
  await ensureLabels(repoFullName, labels);
  try {
    await github(`/repos/${owner}/${name}/issues/${number}/labels`, {
      method: "POST",
      body: JSON.stringify({ labels }),
    });
  } catch (err) {
    console.warn(`Could not label ${repoFullName}#${number}: ${err.message}`);
  }
}

export async function getPull({ repo: repoFullName, number }) {
  const { owner, name } = repoParts(repoFullName);
  return github(`/repos/${owner}/${name}/pulls/${number}`);
}

export async function getCheckRuns({ repo: repoFullName, sha }) {
  const { owner, name } = repoParts(repoFullName);
  const data = await github(`/repos/${owner}/${name}/commits/${sha}/check-runs?per_page=100`);
  return data.check_runs || [];
}

export function repoFromIssue(issue, fallback) {
  if (issue.repository?.full_name) return issue.repository.full_name;
  const match = String(issue.repository_url || issue.html_url || "").match(/github\.com\/repos\/([^/]+\/[^/]+)/)
    || String(issue.html_url || "").match(/github\.com\/([^/]+\/[^/]+)\//);
  if (match) return match[1];
  return fallback;
}
