# Magis CI Autofix

This package triages failed GitHub Actions runs and notifies by default. It dispatches a Cursor Cloud Agent only for a repeated, narrow code/test/schema failure with actionable logs and a new stable signature.

Slack is a **decision inbox**, not a log pipe. Channel messages are short verdict cards (human needed, working, review PR, fix-PR CI). Logs stay on GitHub. Cursor native announcements should not share this webhook.

## Secrets

Set these repository or organization secrets:

- `CURSOR_API_KEY`: Cursor Cloud Agent API key.
- `SLACK_BOT_TOKEN`: Slack bot token with `chat:write`, `chat:write.public`, and `channels:join`. This is required for threading and message updates.
- `SLACK_CHANNEL_ID`: Public channel ID (`C…`) for the Magis CI Autofix inbox.
- `SLACK_WEBHOOK_URL`: Incoming webhook fallback if the bot token is missing. Fallback cards are compact but cannot thread or update.

If Slack secrets are missing, Autofix still triages and can still dispatch Cursor. Follow-up issues remain the ledger.

## Slack setup

1. Create a Slack app at <https://api.slack.com/apps> (or reuse the Magis bot).
2. Add bot scopes: `chat:write`, `chat:write.public`, `channels:join`, `channels:read`.
3. Install the app to the Magis workspace and invite it to the Autofix channel.
4. Copy the bot token (`xoxb-…`) and the channel ID.
5. Invite the **Cursor** Slack app to the same channel. In Cursor dashboard Cloud Agents, turn on **Display agent summary** and **Team follow-ups**.
6. Do **not** point Cursor product announcement webhooks at this channel. Magis owns the parent card; humans reply `@Cursor` in the thread to follow up.
7. Set org secrets:

```powershell
gh secret set SLACK_BOT_TOKEN --org magis-capital-partners --visibility all
gh secret set SLACK_CHANNEL_ID --org magis-capital-partners --visibility all
gh secret set CURSOR_API_KEY --org magis-capital-partners --visibility all
```

Keep `SLACK_WEBHOOK_URL` only as a fallback. If it currently mixes other Magis jobs into the Autofix channel, point those jobs at a different webhook.

## What Slack posts

Posted:

- Human needed (secrets, permissions, GitHub billing/runners, failure surface too broad)
- Working (Cursor agent launched; Open in Cursor button)
- Review PR / no PR (agent finished)
- Fix PR CI green or red
- Autofix failed or still running after 6 hours

Muted:

- Transients, unclassified, no-logs, fork PRs, first-time (not yet repeated) failures

Each incident is one thread. The parent card is updated to the latest verdict so the channel list stays scannable.

## Current repo

This repo has a local `.github/workflows/ci-autofix.yml` that:

- triages failed watched workflows and launches Cursor without waiting for the agent to finish
- every 15 minutes, sweeps open `ci-autofix` / `followup` issues, checks the Cursor run + fix-PR checks, and updates the Slack thread

Manual follow-up sweep:

```powershell
cd C:\Users\drewg\Projects\dashboards\single-stock-investments
$env:GITHUB_REPOSITORY = "magis-capital-partners/single-stock-investments"
node _system/ci_autofix/followup.mjs
```

Org-wide sweep (poller):

```powershell
$env:CI_AUTOFIX_ORG = "magis-capital-partners"
node _system/ci_autofix/followup.mjs
```

## Org-wide rollout

After fixing GitHub CLI auth, run:

```powershell
gh auth login -h github.com
powershell -ExecutionPolicy Bypass -File _system/ci_autofix/install_org_repos.ps1 -Org magis-capital-partners
```

Use `-DryRun` first to inspect local branches without pushing:

```powershell
powershell -ExecutionPolicy Bypass -File _system/ci_autofix/install_org_repos.ps1 -Org magis-capital-partners -DryRun
```

The installer opens one draft PR per non-archived repo. It copies this package into each repo instead of depending on cross-repo private workflow access.

## External poller

The GitHub Actions workflow cannot run if GitHub refuses to start jobs because of billing, spending-limit, or runner capacity issues. Use the external poller on a machine or VM you control to catch those failures **and** close the Slack loop:

```powershell
$env:SLACK_BOT_TOKEN = "xoxb-..."
$env:SLACK_CHANNEL_ID = "C..."
$env:SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/..."
$env:CURSOR_API_KEY = "cursor-api-key"
gh auth login -h github.com
powershell -ExecutionPolicy Bypass -File _system/ci_autofix/poll_org_failures.ps1 -Org magis-capital-partners -LookbackHours 24
```

For continuous monitoring, run that command every 10-15 minutes from Windows Task Scheduler, cron, launchd, or a small VM scheduler. The poller stores handled run IDs in:

```text
%USERPROFILE%\.magis-ci-autofix-state.json
```

## Classification

Notify-only by default:

- GitHub Actions billing/spending/runner startup failures
- missing secrets or invalid credentials
- permission failures
- fork PR failures
- no usable logs

Cursor admission requires all of the following:

- test, code, or schema classification with actionable logs;
- the same stable failure signature at least twice;
- no more than two failed jobs;
- no prior dispatch for the signature in the cooldown window;
- the shared daily budget has capacity.

Build, lint, generated drift, workflow, platform, authentication, permission, transient, broad, and unclassified failures are notify-only unless a human uses the audited manual force override. Every admitted attempt is written to the shared ledger. Cursor is launched through the Cloud Agents API and does not block the GitHub Actions job until the agent finishes.

## Tests

```powershell
cd _system/ci_autofix
npm test
```
