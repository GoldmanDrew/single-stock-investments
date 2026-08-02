[CmdletBinding()]
param(
    [string]$IngestCredentialPath = (Join-Path $env:USERPROFILE ".magis-market-risk\market-risk-ingest-token.dpapi"),
    [string]$IngestUrl = $env:MARKET_RISK_INGEST_URL,
    [string]$IngestToken = $env:MARKET_RISK_INGEST_TOKEN,
    [switch]$NoPublish
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$builder = Join-Path $PSScriptRoot "build_market_risk_components.py"

if (-not $NoPublish) {
    if (-not $IngestUrl) {
        $urlPath = Join-Path $env:USERPROFILE ".magis-market-risk\ingest-url.txt"
        if (Test-Path -LiteralPath $urlPath -PathType Leaf) {
            $IngestUrl = (Get-Content -LiteralPath $urlPath -Raw).Trim()
        }
    }
    if (-not $IngestToken -and (Test-Path -LiteralPath $IngestCredentialPath -PathType Leaf)) {
        $secure = ConvertTo-SecureString (Get-Content -LiteralPath $IngestCredentialPath -Raw)
        $credential = [System.Net.NetworkCredential]::new("market-risk", $secure)
        $IngestToken = $credential.Password
    }
    if (-not $IngestUrl -or -not $IngestToken) {
        throw "The protected market-risk ingest URL and signing credential are required."
    }
    $env:MARKET_RISK_INGEST_URL = $IngestUrl
    $env:MARKET_RISK_INGEST_TOKEN = $IngestToken
}

try {
    Push-Location $repoRoot
    try {
        $localOutput = Join-Path $env:USERPROFILE ".magis-market-risk\market-risk-components-latest.json"
        $arguments = @($builder, "--output", $localOutput)
        if (-not $NoPublish) { $arguments += "--publish" }
        & python @arguments
        exit $LASTEXITCODE
    }
    finally { Pop-Location }
}
finally {
    Remove-Item Env:MARKET_RISK_INGEST_URL -ErrorAction SilentlyContinue
    Remove-Item Env:MARKET_RISK_INGEST_TOKEN -ErrorAction SilentlyContinue
}
