<#
.SYNOPSIS
    Keep the Whisper backfill draining on this host until the backlog is empty.

.DESCRIPTION
    The daemon is deliberately quittable -- it stops on a deadline, after six
    barren rounds, or on any unhandled error -- because a process that must run
    for days will be killed at some point and the design prefers that to be
    survivable. That makes it correct but not persistent. This supervisor is the
    other half: it restarts the daemon until the work is actually finished.

    Single instance is the property that matters most here. On 2026-08-25 two
    daemons ran against the same backlog from different hosts and roughly a
    third of all transcription was thrown away -- both machines transcribing the
    same episode, each overwriting the other, and the vault push racing between
    them. A global mutex makes that impossible on this host; keeping only one
    host scheduled is the operator's half of the same rule.

    Restarts back off. A daemon that exits immediately is usually telling you
    the network is down or the vault is unreachable, and hammering it turns one
    outage into thousands of journal lines -- which is exactly how an earlier
    retry loop produced 6,785 restarts in a day.

.PARAMETER Model
    Whisper checkpoint. distil-large-v3 is the default: benchmarked on this box
    at 4.3x realtime, faster than `small` AND more accurate, and the only tested
    config that preserves negations rather than inverting them.

.PARAMETER Threads
    CPU threads for CTranslate2. Left at 12 of 16 so the machine stays usable.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File _system\scripts\whisper_supervisor.ps1
#>
[CmdletBinding()]
param(
    [string] $Model      = 'distil-large-v3',
    [int]    $Threads    = 12,
    # The daemon evaluates its push interval at chunk boundaries, not per
    # episode, so the chunk size -- not PushMins -- is what really governs how
    # often finished work reaches the vault. At 8 with the machine busy, three
    # completed transcripts sat unpushed for five hours. Three keeps a
    # checkpoint roughly hourly even when transcription is slow.
    [int]    $Chunk      = 3,
    [int]    $PushMins   = 15,
    [int]    $MinBackoff = 120,
    [int]    $MaxBackoff = 1800,
    [int]    $MaxLogMB   = 32
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $repo

$logDir = Join-Path $repo 'tmp'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir 'whisper_supervisor.log'

function Write-Log {
    param([string] $Message)
    $line = '[{0}] {1}' -f (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'), $Message
    Write-Host $line
    Add-Content -Path $log -Value $line -Encoding utf8
}

function Rotate-Log {
    # A multi-day run writes a lot. Keep one generation so a stalled loop cannot
    # fill the disk the transcripts are being written to.
    if ((Test-Path $log) -and ((Get-Item $log).Length -gt ($MaxLogMB * 1MB))) {
        Move-Item -Path $log -Destination "$log.1" -Force
    }
}

# --- single instance -------------------------------------------------------
# Global\ so it holds across sessions, not just this logon.
$mutex = New-Object System.Threading.Mutex($false, 'Global\ssi-whisper-backfill')
if (-not $mutex.WaitOne(0)) {
    Write-Log 'another supervisor already holds the lock; exiting'
    exit 0
}

$python = 'python'
$daemon = Join-Path $repo '_system\scripts\whisper_backfill_daemon.py'
$env:WHISPER_MODEL   = $Model
$env:WHISPER_THREADS = "$Threads"
$env:PYTHONUNBUFFERED = '1'

Write-Log ("supervisor start: model=$Model threads=$Threads chunk=$Chunk push=${PushMins}m repo=$repo")

$backoff = $MinBackoff
try {
    while ($true) {
        Rotate-Log

        # Ask the daemon itself whether there is anything left, rather than
        # parsing its output. It is the only thing that knows what `pending`
        # means after reconciliation against disk.
        $statusJson = & $python $daemon --status 2>&1 | Out-String
        try   { $pending = ([int](($statusJson | ConvertFrom-Json).pending)) }
        catch { $pending = -1 }

        if ($pending -eq 0) {
            Write-Log 'backlog empty; supervisor done'
            break
        }
        if ($pending -lt 0) {
            Write-Log "could not read backlog status; retrying in $backoff s"
            Start-Sleep -Seconds $backoff
            $backoff = [Math]::Min($backoff * 2, $MaxBackoff)
            continue
        }

        Write-Log "starting daemon ($pending pending)"
        $started = Get-Date
        # Not Tee-Object: on Windows PowerShell 5.1 its -FilePath has no
        # encoding parameter and writes UTF-16LE, which interleaves with the
        # UTF-8 lines Write-Log appends and leaves the log unreadable -- every
        # character separated by a NUL. Echo and append explicitly instead.
        & $python '-u' $daemon '--until-empty' '--chunk' "$Chunk" '--push-every-minutes' "$PushMins" 2>&1 |
            ForEach-Object {
                Write-Host $_
                Add-Content -Path $log -Value $_ -Encoding utf8
            }
        $code = $LASTEXITCODE
        $ran  = [int]((Get-Date) - $started).TotalSeconds
        Write-Log "daemon exited code=$code after ${ran}s"

        # A run that did real work resets the backoff; one that died immediately
        # is a signal, not a blip.
        if ($ran -ge 600) { $backoff = $MinBackoff }
        Write-Log "sleeping $backoff s before restart"
        Start-Sleep -Seconds $backoff
        if ($ran -lt 600) { $backoff = [Math]::Min($backoff * 2, $MaxBackoff) }
    }
}
finally {
    $mutex.ReleaseMutex()
    $mutex.Dispose()
    Write-Log 'supervisor exit'
}
