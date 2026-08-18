import { agentUrl, shortRepo, truncate, VERDICT, VERDICT_LABEL } from "./inbox_format.mjs";

const slackBotToken = process.env.SLACK_BOT_TOKEN;
const slackWebhookUrl = process.env.SLACK_WEBHOOK_URL;

export function slackChannelId(config = {}) {
  return process.env.SLACK_CHANNEL_ID || config.slack?.channel_id || "";
}

function mentionPrefix(kind, config = {}) {
  const ping = ["HUMAN_NEEDED", "AGENT_FAILED", "FIX_CI_RED"].includes(kind);
  if (!ping || !config.slack?.mention) return "";
  return `${config.slack.mention} `;
}

function colorFor(kind) {
  if (kind === VERDICT.FIX_CI_GREEN) return "#2eb67d";
  if (kind === VERDICT.WORKING) return "#439fe0";
  if (kind === VERDICT.REVIEW_PR) return "#2eb67d";
  if (kind === VERDICT.HUMAN_NEEDED || kind === VERDICT.AGENT_FAILED || kind === VERDICT.FIX_CI_RED) return "#e01e5a";
  return "#ecb22e";
}

export function buildDecisionBlocks({ kind, repo, workflow, diagnosis, next, links = [] }) {
  const title = `${VERDICT_LABEL[kind] || kind} · ${shortRepo(repo)}`.slice(0, 150);
  const text = [`*${workflow || "CI"}*`, diagnosis, next ? `*Next:* ${next}` : ""].filter(Boolean).join("\n");
  const blocks = [
    { type: "header", text: { type: "plain_text", text: title } },
    { type: "section", text: { type: "mrkdwn", text: truncate(text, 2800) } },
  ];
  const buttons = links
    .filter((link) => link.url)
    .slice(0, 5)
    .map((link) => ({
      type: "button",
      text: { type: "plain_text", text: link.label.slice(0, 75) },
      url: link.url,
    }));
  if (buttons.length) {
    blocks.push({ type: "actions", elements: buttons });
  }
  blocks.push({
    type: "context",
    elements: [
      {
        type: "mrkdwn",
        text: "Reply `@Cursor` in this thread to add follow-up. Open in Cursor to inspect the agent.",
      },
    ],
  });
  return blocks;
}

export function decisionLinks({ runUrl, prUrl, agentId }) {
  return [
    runUrl ? { label: "Failed run", url: runUrl } : null,
    prUrl ? { label: "Open PR", url: prUrl } : null,
    agentId ? { label: "Open in Cursor", url: agentUrl(agentId) } : null,
  ].filter(Boolean);
}

async function slackApi(method, payload) {
  const res = await fetch(`https://slack.com/api/${method}`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${slackBotToken}`,
      "content-type": "application/json; charset=utf-8",
    },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!data.ok) {
    throw new Error(`Slack ${method} failed: ${data.error || res.status}`);
  }
  return data;
}

async function joinChannel(channel) {
  try {
    await slackApi("conversations.join", { channel });
  } catch (err) {
    if (!/already_in_channel|method_not_supported_for_channel_type|missing_scope/.test(err.message)) {
      console.warn(err.message);
    }
  }
}

export async function postDecision({
  config = {},
  kind,
  repo,
  workflow,
  diagnosis,
  next,
  runUrl,
  prUrl,
  agentId,
  threadTs,
  updateTs,
  channel,
}) {
  if (config.slack?.enabled === false) {
    console.log("Slack notification skipped; Slack is disabled.");
    return null;
  }
  const channelId = channel || slackChannelId(config);
  const links = decisionLinks({ runUrl, prUrl, agentId });
  const blocks = buildDecisionBlocks({ kind, repo, workflow, diagnosis, next, links });
  const title = `${mentionPrefix(kind, config)}${VERDICT_LABEL[kind] || kind} · ${shortRepo(repo)}: ${workflow || "CI"}`;
  const fallbackText = [title, diagnosis, next ? `Next: ${next}` : "", ...links.map((link) => `${link.label}: ${link.url}`)]
    .filter(Boolean)
    .join("\n");

  if (slackBotToken && channelId) {
    try {
      await joinChannel(channelId);
      if (updateTs) {
        const updated = await slackApi("chat.update", {
          channel: channelId,
          ts: updateTs,
          text: fallbackText,
          blocks,
        });
        return { channel: updated.channel || channelId, ts: updated.ts || updateTs, threadTs: threadTs || updated.ts };
      }
      const posted = await slackApi("chat.postMessage", {
        channel: channelId,
        text: fallbackText,
        blocks,
        unfurl_links: false,
        unfurl_media: false,
        ...(threadTs ? { thread_ts: threadTs } : {}),
      });
      return {
        channel: posted.channel || channelId,
        ts: posted.ts,
        threadTs: threadTs || posted.ts,
      };
    } catch (err) {
      console.warn(`Slack bot post failed (${err.message}); trying webhook fallback.`);
    }
  }

  if (!slackWebhookUrl) {
    console.log("Slack notification skipped; SLACK_BOT_TOKEN/SLACK_CHANNEL_ID and SLACK_WEBHOOK_URL are not configured.");
    return null;
  }

  const payload = {
    text: fallbackText,
    blocks,
    attachments: [
      {
        color: colorFor(kind),
        text: truncate(fallbackText, 3000),
        mrkdwn_in: ["text"],
      },
    ],
  };
  const res = await fetch(slackWebhookUrl, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    console.warn(`Slack webhook failed: ${res.status} ${await res.text()}`);
    return null;
  }
  return { channel: channelId, ts: "", threadTs: "" };
}
