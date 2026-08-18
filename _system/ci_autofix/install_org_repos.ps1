param(
    [string]$Org = "magis-capital-partners",
    [string]$BranchName = "codex/ci-autofix",
    [string]$WorkDir = "$env:TEMP\magis-ci-autofix-rollout",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Require-Command($Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name is required but was not found on PATH."
    }
}

Require-Command git
Require-Command gh
Require-Command robocopy

function Get-WorkflowNamesForAutofix($RepoPath) {
    $workflowDir = Join-Path $RepoPath ".github\workflows"
    if (-not (Test-Path $workflowDir)) {
        return @()
    }

    $names = @()
    foreach ($file in Get-ChildItem -Path $workflowDir -Filter *.yml) {
        foreach ($line in Get-Content $file.FullName) {
            if ($line -match '^\s*name:\s*["'']?(.+?)["'']?\s*$') {
                $name = $matches[1].Trim()
                if ($name -and $name -ne "CI Autofix") {
                    $names += $name
                }
                break
            }
        }
    }

    return ($names | Sort-Object -Unique)
}

function Format-WorkflowRunList($WorkflowNames) {
    if ($WorkflowNames.Count -eq 0) {
        throw "No source workflows found in .github/workflows. CI Autofix requires at least one workflow_run target."
    }

    $lines = $WorkflowNames | ForEach-Object { "      - `"$_`"" }
    return ($lines -join "`n")
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SourceCiDir = Resolve-Path $ScriptDir
$SourceRepoRoot = Resolve-Path (Join-Path $ScriptDir "..\..")
$SourceGate = Join-Path $SourceRepoRoot "_system\scripts\llm_call_gate.py"
$SourcePolicy = Join-Path $SourceRepoRoot "_system\config\llm_usage_policy.json"

gh auth status | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "GitHub CLI auth is not valid. Run: gh auth login -h github.com"
}

New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null

$reposJson = gh repo list $Org --limit 500 --json nameWithOwner,isArchived,defaultBranchRef
$repos = @($reposJson | ConvertFrom-Json) | ForEach-Object { $_ } | Where-Object { -not $_.isArchived }

foreach ($repo in $repos) {
    $full = $repo.nameWithOwner
    $name = ($full -split "/")[1]
    $target = Join-Path $WorkDir $name
    Write-Host ""
    Write-Host "=== $full ==="

    if (Test-Path $target) {
        git -C $target fetch origin | Out-Host
        git -C $target checkout $repo.defaultBranchRef.name | Out-Host
        git -C $target pull --ff-only | Out-Host
    } else {
        gh repo clone $full $target | Out-Host
    }

    git -C $target checkout -B $BranchName | Out-Host

    New-Item -ItemType Directory -Force -Path (Join-Path $target ".github\workflows") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $target "_system\scripts") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $target "_system\config") | Out-Null
    robocopy $SourceCiDir (Join-Path $target "_system\ci_autofix") /MIR /XD node_modules rollout /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
    if ($LASTEXITCODE -gt 7) { throw "robocopy failed for $full with exit code $LASTEXITCODE" }
    Copy-Item -Force $SourceGate (Join-Path $target "_system\scripts\llm_call_gate.py")
    Copy-Item -Force $SourcePolicy (Join-Path $target "_system\config\llm_usage_policy.json")

    $workflowNames = Get-WorkflowNamesForAutofix $target
    $workflowRunList = Format-WorkflowRunList $workflowNames

    $workflow = @"
name: CI Autofix

on:
  workflow_run:
    workflows:
$workflowRunList
    types: [completed]
    branches: [main]
  schedule:
    - cron: "*/15 * * * *"
  workflow_dispatch:
    inputs:
      run_id:
        description: "Workflow run ID to investigate"
        required: true
      force_agent:
        description: "Force Cursor agent even if classifier would normally notify only"
        required: false
        default: "false"

permissions:
  actions: read
  contents: write
  issues: write
  pull-requests: write
  checks: read

concurrency:
  group: ci-autofix-`${{ github.event.workflow_run.id || github.event.inputs.run_id || github.event_name }}
  cancel-in-progress: false

jobs:
  triage-and-dispatch:
    if: >
      github.event_name == 'workflow_dispatch' ||
      (
        github.event.workflow_run.conclusion == 'failure' &&
        github.event.workflow_run.name != 'CI Autofix'
      )
    runs-on: ubuntu-latest
    timeout-minutes: 15

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: npm
          cache-dependency-path: _system/ci_autofix/package-lock.json

      - name: Restore CI Autofix call ledger
        uses: actions/cache@v4
        with:
          path: .llm-state/ci_autofix
          key: llm-ci-autofix-`${{ github.repository_id }}-`${{ github.run_id }}
          restore-keys: |
            llm-ci-autofix-`${{ github.repository_id }}-

      - name: Install CI Autofix dependencies
        working-directory: _system/ci_autofix
        run: npm ci

      - name: Triage failure and dispatch Cursor if appropriate
        env:
          GH_TOKEN: `${{ github.token }}
          GITHUB_TOKEN: `${{ github.token }}
          CURSOR_API_KEY: `${{ secrets.CURSOR_API_KEY }}
          SLACK_WEBHOOK_URL: `${{ secrets.SLACK_WEBHOOK_URL }}
          SLACK_BOT_TOKEN: `${{ secrets.SLACK_BOT_TOKEN }}
          SLACK_CHANNEL_ID: `${{ secrets.SLACK_CHANNEL_ID }}
          CI_AUTOFIX_RUN_ID: `${{ github.event.inputs.run_id || github.event.workflow_run.id }}
          CI_AUTOFIX_FORCE_AGENT: `${{ github.event.inputs.force_agent || 'false' }}
          LLM_LEDGER_PATH: .llm-state/ci_autofix/ledger.jsonl
        run: node _system/ci_autofix/ci_autofix.mjs

      - name: Upload CI token audit
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: llm-audit-ci-`${{ github.run_id }}
          path: .llm-state/ci_autofix/ledger.jsonl
          if-no-files-found: ignore

  followup:
    if: github.event_name == 'schedule'
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: npm
          cache-dependency-path: _system/ci_autofix/package-lock.json

      - name: Install CI Autofix dependencies
        working-directory: _system/ci_autofix
        run: npm ci

      - name: Close the Slack inbox loop
        env:
          GH_TOKEN: `${{ github.token }}
          GITHUB_TOKEN: `${{ github.token }}
          CURSOR_API_KEY: `${{ secrets.CURSOR_API_KEY }}
          SLACK_WEBHOOK_URL: `${{ secrets.SLACK_WEBHOOK_URL }}
          SLACK_BOT_TOKEN: `${{ secrets.SLACK_BOT_TOKEN }}
          SLACK_CHANNEL_ID: `${{ secrets.SLACK_CHANNEL_ID }}
        run: node _system/ci_autofix/followup.mjs
"@

    $config = @"
enabled: true

cursor:
  enabled: true
  model: composer-2.5
  max_log_chars: 45000
  max_agent_attempts_per_sha: 1
  minimum_repeat_count: 2
  maximum_failed_jobs: 2
  skip_fork_prs: true
  skip_workflows:
    - CI Autofix

github:
  create_issue_for_notify_only: true
  issue_labels:
    - ci-autofix
    - needs-attention
  pr_labels:
    - ci-autofix
    - agent-generated
    - needs-human-review

slack:
  enabled: true
  mention: ""
  notify_human_needed: true
  mute_notify_only: true

classify:
  notify_only:
    - platform
    - credentials
    - permissions
    - human_required
  transient_retry_first: true
  default_action: notify_only
"@

    Set-Content -Path (Join-Path $target ".github\workflows\ci-autofix.yml") -Value $workflow -Encoding UTF8
    Set-Content -Path (Join-Path $target ".github\ci-autofix.yml") -Value $config -Encoding UTF8

    git -C $target add .github/workflows/ci-autofix.yml .github/ci-autofix.yml _system/ci_autofix _system/scripts/llm_call_gate.py _system/config/llm_usage_policy.json | Out-Host
    if (git -C $target diff --staged --quiet) {
        Write-Host "No changes."
        continue
    }

    git -C $target commit -m "chore: add CI autofix workflow" | Out-Host
    if ($DryRun) {
        Write-Host "Dry run: not pushing $full"
        continue
    }

    git -C $target push -u origin $BranchName --force-with-lease | Out-Host
    gh pr create `
        --repo $full `
        --base $repo.defaultBranchRef.name `
        --head $BranchName `
        --title "chore: add CI autofix workflow" `
        --body "Adds CI failure triage, Slack notification, and Cursor Cloud Agent dispatch through the central Magis CI Autofix workflow." `
        --draft | Out-Host
}
