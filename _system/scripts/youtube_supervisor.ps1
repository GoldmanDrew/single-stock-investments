<#
.SYNOPSIS
    Run the YouTube research lane once, from its own worktree, with a log.

.DESCRIPTION
    The thin half of the pair: youtube_lane.py holds the pipeline and the git
    work, this holds the things a scheduled task needs and a Python script
    should not own -- a single-instance guard, a rotating log, and a working
    directory that is the lane worktree rather than whatever the operator's
    shell was sitting in.

    Unlike whisper_supervisor.ps1 and analysis_supervisor.ps1 this does NOT
    loop. Those two drain a backlog of thousands against a CPU that is the only
    limit; this one is rate-limited to 20 caption fetches an hour and 120 a day
    by YouTube, so a run is mostly waiting and a second run in the same hour
    would fetch nothing. One run per day, exit, matches both the pacing and the
    `17 5 * * *` cron the CI workflow used before its runner turned out never to
    have existed.

    **-Worktree is not the primary checkout, and that is the point.** Concurrent
    agents share the main working tree, and a lane that stages files into a
    shared index eventually finds them in somebody else's commit. The worktree
    has its own index and HEAD while sharing the object store.

.PARAMETER Hours
    Caption daemon window. At 150s spacing this is mostly sleep; 1 hour is about
    20 fetches, which is the hourly cap anyway.

.PARAMETER Whisper
    Videos to route through local Whisper. 0 -- the default -- queues them and
    transcribes none, because this host already runs the podcast Whisper
    backfill and the analysis batch and sits under 1 GB free.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File _system\scripts\youtube_supervisor.ps1
#>
[CmdletBinding()]
param(
    [string] $Worktree = 'C:\Users\drewg\Projects\dashboards\ssi-youtube-lane',
    [double] $Hours    = 1.0,
    [int]    $Whisper  = 0,
    [int]    $MaxLogMB = 16,
    [switch] $NoPush
)

$ErrorActionPreference = 'Stop'

$logDir = Join-Path $Worktree 'tmp'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir 'youtube_lane.log'

function Write-Log {
    param([string] $Message)
    $line = '[{0}] {1}' -f (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'), $Message
    Write-Host $line
    Add-Content -Path $log -Value $line -Encoding utf8
}

if ((Test-Path $log) -and ((Get-Item $log).Length -gt ($MaxLogMB * 1MB))) {
    Move-Item -Path $log -Destination "$log.1" -Force
}

if (-not (Test-Path (Join-Path $Worktree '_system\scripts\youtube_lane.py'))) {
    Write-Log "lane worktree missing or incomplete at $Worktree; nothing to run"
    exit 1
}

# Global\ so it holds across sessions. A second run while one is in flight would
# duplicate fetches against a budget measured in tens per hour.
$mutex = New-Object System.Threading.Mutex($false, 'Global\ssi-youtube-lane')
if (-not $mutex.WaitOne(0)) {
    Write-Log 'another youtube lane run already holds the lock; exiting'
    exit 0
}

Set-Location $Worktree
$env:PYTHONUNBUFFERED = '1'

$laneArgs = @('-u', '_system\scripts\youtube_lane.py', '--hours', "$Hours", '--whisper', "$Whisper")
if ($NoPush) { $laneArgs += '--no-push' }

Write-Log "lane start: worktree=$Worktree hours=$Hours whisper=$Whisper"
$started = Get-Date
try {
    # Not Tee-Object: on Windows PowerShell 5.1 its -FilePath writes UTF-16LE,
    # which interleaves with the UTF-8 Write-Log appends and leaves the log
    # unreadable. Echo and append explicitly instead.
    & python $laneArgs 2>&1 | ForEach-Object {
        Write-Host $_
        Add-Content -Path $log -Value $_ -Encoding utf8
    }
    $code = $LASTEXITCODE
    $ran  = [int]((Get-Date) - $started).TotalSeconds
    Write-Log "lane exited code=$code after ${ran}s"
    exit $code
}
finally {
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
