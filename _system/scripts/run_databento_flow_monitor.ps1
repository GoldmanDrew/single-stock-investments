[CmdletBinding()]
param(
    [string]$CredentialPath = "C:\Users\drewg\.magis-market-risk\databento-api-key.dpapi",
    [string]$IngestCredentialPath = "C:\Users\drewg\.magis-market-risk\market-risk-ingest-token.dpapi",
    [string]$IngestUrl = $env:MARKET_RISK_INGEST_URL,
    [string]$IngestToken = $env:MARKET_RISK_INGEST_TOKEN,
    [string]$Dataset = "EQUS.MINI",
    [string]$Symbols = "SPY,QQQ,IWM,DIA,EWJ,VXX,HYG,LQD,TLT,UUP,EFA,EEM,XLB,XLC,XLE,XLF,XLI,XLK,XLP,XLRE,XLU,XLV,XLY",
    [string]$StypeIn = "raw_symbol",
    [ValidateSet("market", "sector", "security")]
    [string]$Scope = "market",
    [double]$PublishSeconds = 60
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$monitorScript = Join-Path $PSScriptRoot "run_databento_flow_monitor.py"

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
        python $monitorScript `
            --dataset $Dataset `
            --symbols $Symbols `
            --stype-in $StypeIn `
            --scope $Scope `
            --publish-seconds $PublishSeconds
        exit $LASTEXITCODE
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
