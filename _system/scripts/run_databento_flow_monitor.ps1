[CmdletBinding()]
param(
    [string]$CredentialPath = "C:\Users\drewg\.magis-market-risk\databento-api-key.dpapi",
    [string]$IngestCredentialPath = "C:\Users\drewg\.magis-market-risk\market-risk-ingest-token.dpapi",
    [string]$IngestUrl = $env:MARKET_RISK_INGEST_URL,
    [string]$IngestToken = $env:MARKET_RISK_INGEST_TOKEN,
    [string]$Dataset = "EQUS.MINI",
    [string]$Symbols = "SPY,QQQ,IWM,DIA,EWJ,VXX,HYG,LQD,TLT,UUP,EFA,EEM,XLB,XLC,XLE,XLF,XLI,XLK,XLP,XLRE,XLU,XLV,XLY",
    [string]$StypeIn = "raw_symbol",
    [string]$LiquiditySchema = "mbp-1",
    [ValidateSet("market", "sector", "security")]
    [string]$Scope = "market",
    [double]$PublishSeconds = 60,
    # Supervision. The monitor died on an uncaught publish timeout on
    # 2026-08-03 and nothing restarted it, so the flow rails were empty for
    # seven days with no signal anywhere. This script is now the restarter.
    [int]$MaxRestartsPerHour = 6,
    [int]$RestartDelaySeconds = 15,
    [switch]$NoSupervise,
    # The scheduled-task action is a bare `powershell.exe -File <this>` with no
    # redirection, so until now everything this script and the monitor printed
    # went nowhere: the only lines ever in the out log came from someone
    # running it by hand. That matters beyond tidiness - the out log is the
    # evidence the P7 live-feed invariant reads, so an unredirected task made a
    # running feed indistinguishable from a dead one. The script now owns its
    # own log paths instead of depending on how it was invoked.
    [string]$LogDirectory = (Join-Path $HOME ".magis-market-risk\logs")
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$monitorScript = Join-Path $PSScriptRoot "run_databento_flow_monitor.py"

# Exit code the python monitor uses for a permanent auth failure (401/403 from
# the ingest). Restarting on that would burn the restart budget re-proving a
# rejected token is still rejected, so the supervisor stops instead.
$AuthFailureExitCode = 2

function Write-SupervisorEvent {
    param(
        [Parameter(Mandatory = $true)][string]$Event,
        [hashtable]$Fields
    )
    $payload = [ordered]@{
        event = "supervisor_$Event"
        at    = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    }
    if ($Fields) {
        foreach ($key in $Fields.Keys) { $payload[$key] = $Fields[$key] }
    }
    $line = ConvertTo-Json -InputObject $payload -Compress
    Write-Output $line
    if ($script:SupervisorOutLog) {
        # Append, never truncate: the log is an append-only evidence trail and
        # P7 reads its last stamped line.
        Add-Content -LiteralPath $script:SupervisorOutLog -Value $line -Encoding utf8
    }
}

if (-not (Test-Path -LiteralPath $LogDirectory)) {
    New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
}
$script:SupervisorOutLog = Join-Path $LogDirectory "databento-flow-monitor.out.log"
$script:SupervisorErrLog = Join-Path $LogDirectory "databento-flow-monitor.err.log"

if (-not (Test-Path -LiteralPath $CredentialPath -PathType Leaf)) {
    throw "Encrypted Databento credential not found at $CredentialPath"
}
if (-not $IngestUrl) {
    $ingestUrlPath = "C:\Users\drewg\.magis-market-risk\ingest-url.txt"
    if (Test-Path -LiteralPath $ingestUrlPath -PathType Leaf) {
        $IngestUrl = (Get-Content -LiteralPath $ingestUrlPath -Raw).Trim()
    }
}
if (-not $IngestUrl) {
    throw "Set MARKET_RISK_INGEST_URL, pass -IngestUrl, or create the protected local ingest-url.txt configuration."
}
if (-not $IngestToken -and (Test-Path -LiteralPath $IngestCredentialPath -PathType Leaf)) {
    $encryptedIngest = Get-Content -LiteralPath $IngestCredentialPath -Raw
    $secureIngest = ConvertTo-SecureString $encryptedIngest
    $ingestCredential = [System.Net.NetworkCredential]::new("market-risk", $secureIngest)
    $IngestToken = $ingestCredential.Password
}
if (-not $IngestToken) {
    throw "Encrypted market-risk signing credential not found; set MARKET_RISK_INGEST_TOKEN or pass -IngestToken."
}

$encrypted = Get-Content -LiteralPath $CredentialPath -Raw
$secure = ConvertTo-SecureString $encrypted
$credential = [System.Net.NetworkCredential]::new("databento", $secure)
$env:DATABENTO_API_KEY = $credential.Password
$env:MARKET_RISK_INGEST_URL = $IngestUrl
$env:MARKET_RISK_INGEST_TOKEN = $IngestToken

try {
    Push-Location $repoRoot
    try {
        # Rolling one-hour restart budget: a transient crash is restarted
        # promptly, a hard-broken build is not spun in a tight loop forever.
        $restartTimes = New-Object System.Collections.ArrayList
        $exitCode = 0
        $launches = 0

        while ($true) {
            $launches++
            Write-SupervisorEvent -Event "launch" -Fields @{
                launches            = $launches
                restarts_last_hour  = $restartTimes.Count
                max_restarts_hour   = $MaxRestartsPerHour
                script              = $monitorScript
            }

            # -u (unbuffered): stdout here is redirected to a file, so python
            # block-buffers it ~8KB at a time. That delays every heartbeat and
            # published_at line -- and the out log is precisely the evidence
            # the P7 live-feed invariant reads for freshness, so a buffered
            # log makes a healthy feed look stale and a dead one look recent.
            # Tee the child's stdout to the out log line by line (Add-Content
            # per line keeps it append-only and readable while running);
            # stderr goes to the err log. `2>&1` is deliberately NOT used on
            # this native call - under PS 5.1 it wraps each stderr line in an
            # ErrorRecord and sets $? to false even on a clean exit 0, which
            # would make every healthy shutdown look like a crash to the
            # supervisor below.
            python -u $monitorScript `
                --dataset $Dataset `
                --symbols $Symbols `
                --stype-in $StypeIn `
                --liquidity-schema $LiquiditySchema `
                --scope $Scope `
                --publish-seconds $PublishSeconds `
                2> $script:SupervisorErrLog |
                ForEach-Object {
                    Write-Output $_
                    Add-Content -LiteralPath $script:SupervisorOutLog -Value $_ -Encoding utf8
                }

            $exitCode = $LASTEXITCODE
            if ($null -eq $exitCode) { $exitCode = -1 }

            Write-SupervisorEvent -Event "child_exited" -Fields @{
                exit_code = $exitCode
                launches  = $launches
            }

            if ($NoSupervise) {
                Write-SupervisorEvent -Event "stop" -Fields @{
                    reason    = "supervision disabled (-NoSupervise)"
                    exit_code = $exitCode
                }
                break
            }

            if ($exitCode -eq $AuthFailureExitCode) {
                Write-SupervisorEvent -Event "stop" -Fields @{
                    reason      = "permanent auth failure reported by the monitor"
                    exit_code   = $exitCode
                    remediation = "re-mint the market-risk ingest signing token, then re-run the scheduled task"
                }
                break
            }

            # Prune the window, then decide whether the budget still allows a
            # restart. Counting BEFORE appending keeps the budget honest.
            $cutoff = (Get-Date).AddHours(-1)
            $kept = New-Object System.Collections.ArrayList
            foreach ($stamp in $restartTimes) {
                if ($stamp -gt $cutoff) { [void]$kept.Add($stamp) }
            }
            $restartTimes = $kept

            if ($restartTimes.Count -ge $MaxRestartsPerHour) {
                Write-SupervisorEvent -Event "restart_budget_exhausted" -Fields @{
                    reason             = "already restarted $($restartTimes.Count) times in the last hour; not restarting again"
                    exit_code          = $exitCode
                    max_restarts_hour  = $MaxRestartsPerHour
                    remediation        = "read databento-flow-monitor.err.log; the scheduled task will start a fresh supervisor on its next trigger"
                }
                break
            }

            [void]$restartTimes.Add((Get-Date))
            Write-SupervisorEvent -Event "restarting" -Fields @{
                exit_code          = $exitCode
                delay_seconds      = $RestartDelaySeconds
                restarts_last_hour = $restartTimes.Count
                max_restarts_hour  = $MaxRestartsPerHour
            }
            Start-Sleep -Seconds $RestartDelaySeconds
        }

        exit $exitCode
    }
    finally {
        Pop-Location
    }
}
finally {
    Remove-Item Env:DATABENTO_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:MARKET_RISK_INGEST_URL -ErrorAction SilentlyContinue
    Remove-Item Env:MARKET_RISK_INGEST_TOKEN -ErrorAction SilentlyContinue
}
