param(
    [string]$Org = "magis-capital-partners",
    [int]$LookbackHours = 24,
    [int]$MaxRunsPerRepo = 20,
    [string]$StatePath = "$env:USERPROFILE\.magis-ci-autofix-state.json",
    [string]$LogPath = "$env:USERPROFILE\.magis-ci-autofix-poller.log",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Require-Command($Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name is required but was not found on PATH."
    }
}

function Load-State($Path) {
    if (-not (Test-Path $Path)) {
        return @{ handled = @{} }
    }
    $raw = Get-Content -Raw $Path
    if (-not $raw.Trim()) {
        return @{ handled = @{} }
    }
    $obj = $raw | ConvertFrom-Json
    $handled = @{}
    if ($obj.handled) {
        foreach ($prop in $obj.handled.PSObject.Properties) {
            $handled[$prop.Name] = $prop.Value
        }
    }
    return @{ handled = $handled }
}

function Save-State($Path, $State) {
    $parent = Split-Path -Parent $Path
    if ($parent) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    $State | ConvertTo-Json -Depth 8 | Set-Content -Path $Path -Encoding UTF8
}

Require-Command gh
Require-Command node

$logParent = Split-Path -Parent $LogPath
if ($logParent) {
    New-Item -ItemType Directory -Force -Path $logParent | Out-Null
}
Start-Transcript -Path $LogPath -Append | Out-Null

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..\..")
$AgentScript = Join-Path $RepoRoot "_system\ci_autofix\ci_autofix.mjs"

if (-not (Test-Path $AgentScript)) {
    throw "Cannot find $AgentScript"
}

$token = $env:GH_TOKEN
if (-not $token) {
    gh auth status | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "GitHub CLI auth is not valid. Run: gh auth login -h github.com, or set GH_TOKEN."
    }
    $token = (gh auth token).Trim()
}
if (-not $token) {
    throw "No GitHub token found. Set GH_TOKEN or run gh auth login."
}

if (-not $env:SLACK_WEBHOOK_URL) {
    Write-Warning "SLACK_WEBHOOK_URL is not set; Slack notifications will be skipped."
}
if (-not $env:CURSOR_API_KEY) {
    Write-Warning "CURSOR_API_KEY is not set; Cursor dispatch will be skipped."
}

$state = Load-State $StatePath
$cutoff = (Get-Date).ToUniversalTime().AddHours(-1 * $LookbackHours)
$reposJson = gh repo list $Org --limit 500 --json nameWithOwner,isArchived
$repos = @($reposJson | ConvertFrom-Json) | ForEach-Object { $_ } | Where-Object { -not $_.isArchived }

foreach ($repo in $repos) {
    $full = $repo.nameWithOwner
    Write-Host "Scanning $full"
    $runsJson = gh run list --repo $full --limit $MaxRunsPerRepo --json databaseId,conclusion,workflowName,createdAt,status,url
    $runs = @($runsJson | ConvertFrom-Json) | ForEach-Object { $_ }
    foreach ($run in $runs) {
        if ($run.conclusion -ne "failure") { continue }
        $created = [DateTime]::Parse($run.createdAt).ToUniversalTime()
        if ($created -lt $cutoff) { continue }

        $key = "$full#$($run.databaseId)"
        if ($state.handled.ContainsKey($key)) {
            continue
        }

        Write-Host "  failed: $($run.workflowName) $($run.databaseId)"
        if ($DryRun) {
            $state.handled[$key] = @{
                dry_run = $true
                seen_at = (Get-Date).ToUniversalTime().ToString("o")
                url = $run.url
            }
            continue
        }

        $env:GITHUB_REPOSITORY = $full
        $env:GH_TOKEN = $token
        $env:GITHUB_TOKEN = $token
        $env:CI_AUTOFIX_RUN_ID = [string]$run.databaseId
        if (-not $env:CI_AUTOFIX_FORCE_AGENT) {
            $env:CI_AUTOFIX_FORCE_AGENT = "false"
        }

        Push-Location $RepoRoot
        try {
            & node $AgentScript
            if ($LASTEXITCODE -ne 0) {
                throw "ci_autofix.mjs exited with code $LASTEXITCODE"
            }
            $state.handled[$key] = @{
                success = $true
                handled_at = (Get-Date).ToUniversalTime().ToString("o")
                url = $run.url
            }
        } catch {
            $state.handled[$key] = @{
                success = $false
                handled_at = (Get-Date).ToUniversalTime().ToString("o")
                url = $run.url
                error = $_.Exception.Message
            }
            Write-Warning "Failed to handle $key`: $($_.Exception.Message)"
        } finally {
            Pop-Location
            Save-State $StatePath $state
        }
    }
}

Save-State $StatePath $state

Write-Host "Refreshing Cursor / Slack follow-ups"
Push-Location $RepoRoot
try {
    $env:CI_AUTOFIX_ORG = $Org
    $env:GH_TOKEN = $token
    $env:GITHUB_TOKEN = $token
    & node (Join-Path $ScriptDir "followup.mjs")
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "followup.mjs exited with code $LASTEXITCODE"
    }
} catch {
    Write-Warning "Follow-up sweep failed: $($_.Exception.Message)"
} finally {
    Pop-Location
}

Save-State $StatePath $state
Stop-Transcript | Out-Null
