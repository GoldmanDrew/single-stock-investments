# Download and organize JPX (8697.T) IR documents
$ErrorActionPreference = 'Continue'
$Base = Split-Path $PSScriptRoot -Parent
$UrlFile = Join-Path $Base '_pdf_urls.txt'
$LogFile = Join-Path $Base '_download_log.txt'

function Get-DestFolder([string]$Url) {
    $u = $Url.ToLower()
    if ($u -match '/management/mid-business-plan/') { return '04_Strategy\Mid_Term_Plans' }
    if ($u -match '/ir-library/others/') { return '01_Official\Extraordinary_Reports' }
    if ($u -match '/ir-library/integrated-report/') {
        if ($u -match 'introduction|messagesfrommanagement|creatingvalue|strategiesand|co-creation|foundations|corporatedata') {
            return '01_Official\Integrated_Reports\2025_Sections'
        }
        if ($u -match '/tvdivq0000008tvr-att/') { return '01_Official\Integrated_Reports\TSE_Group_Historical' }
        return '01_Official\Integrated_Reports'
    }
    if ($u -match '/ir-library/securities-reports/' -or ($u -match '/securities-reports/' -and $u -notmatch '/financial-info/')) {
        if ($u -match 'annual_securities_report|consolidatedfinancialstatements') {
            return '01_Official\Annual_Securities_Reports\English'
        }
        return '01_Official\Annual_Securities_Reports\Japanese'
    }
    if ($u -match '/ir-library/financial-info/') {
        $name = [IO.Path]::GetFileName(($Url -split '\?')[0]).ToUpper()
        if ($name -match '^E_ER_|^ER_JPX_|^ER_' -or $name -match 'FINANCIAL_RESULTS') { return '02_Quarterly\Earnings_Releases' }
        if ($name -match '^E_EM_|^EM_JPX_|^EM_' -or $name -match 'Q3FY2018') { return '02_Quarterly\Explanatory_Materials' }
        if ($u -match 'tvdivq0000008quw-att|h2[0-9]_') { return '02_Quarterly\TSE_Group_Archive' }
        return '02_Quarterly\Other'
    }
    if ($u -match '/ir-library/events/') {
        if ($u -match 'investorday|ir_day|jpx_ir_day') { return '03_Events\Investor_Day' }
        if ($u -match 'transcript') { return '03_Events\Transcripts' }
        if ($u -match 'qa_|_qa|faq_qa') { return '03_Events\Q_and_A' }
        if ($u -match '3rd_mtmp|mtmp|mtmp') { return '04_Strategy\Presentations' }
        if ($u -match 'e_em_|e_pm_|e_er_|pm_jpx|jpx_pm') { return '03_Events\Earnings_Presentations' }
        return '03_Events\Other'
    }
    return '99_Unsorted'
}

function Get-FileName([string]$Url) {
    $name = [IO.Path]::GetFileName(($Url -split '\?')[0])
    if ([string]::IsNullOrWhiteSpace($name)) { $name = 'document.pdf' }
    return $name
}

# Seed URLs from file + crawl key IR pages
$seedPages = @(
    'https://www.jpx.co.jp/english/corporate/investor-relations/ir-library/financial-info/index.html',
    'https://www.jpx.co.jp/english/corporate/investor-relations/ir-library/securities-reports/index.html',
    'https://www.jpx.co.jp/english/corporate/investor-relations/ir-library/integrated-report/index.html',
    'https://www.jpx.co.jp/english/corporate/investor-relations/ir-library/events/index.html',
    'https://www.jpx.co.jp/english/corporate/investor-relations/ir-library/others/index.html',
    'https://www.jpx.co.jp/english/corporate/investor-relations/management/mid-business-plan/index.html',
    'https://www.jpx.co.jp/corporate/investor-relations/ir-library/securities-reports/index.html'
)

$allUrls = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
if (Test-Path $UrlFile) {
    Get-Content $UrlFile | ForEach-Object {
        if ($_ -match '^https?://') { [void]$allUrls.Add($_.Trim()) }
    }
}

function Resolve-PdfUrl([string]$PageUrl, [string]$Href) {
    $href = $Href -replace '&amp;', '&'
    if ($href -match '^https?://') { return $href }
    $base = $PageUrl.Substring(0, $PageUrl.LastIndexOf('/') + 1)
    if ($href.StartsWith('/')) { return 'https://www.jpx.co.jp' + $href }
    return $base + $href.TrimStart('./')
}

foreach ($page in $seedPages) {
    try {
        $html = Invoke-WebRequest -Uri $page -UseBasicParsing -TimeoutSec 60
        $matches = [regex]::Matches($html.Content, 'href="([^"]+\.pdf[^"]*)"', 'IgnoreCase')
        foreach ($m in $matches) {
            $href = Resolve-PdfUrl $page $m.Groups[1].Value
            if ($href -match 'jpx\.co\.jp/(english|corporate)/') { [void]$allUrls.Add($href) }
        }
    } catch {
        Add-Content $LogFile "$(Get-Date -Format o) CRAWL_FAIL $page : $($_.Exception.Message)"
    }
}

# Drop malformed root-level links from prior crawls
$clean = $allUrls | Where-Object { $_ -match 'jpx\.co\.jp/(english|corporate)/' }
$allUrls = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$clean | ForEach-Object { [void]$allUrls.Add($_) }

$allUrls | Sort-Object | Set-Content (Join-Path $Base '_pdf_urls.txt') -Encoding UTF8
"$(Get-Date -Format o) Found $($allUrls.Count) PDF URLs" | Out-File $LogFile -Encoding UTF8

$client = New-Object System.Net.WebClient
$client.Headers.Add('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Research/1.0')

$ok = 0; $skip = 0; $fail = 0
foreach ($url in ($allUrls | Sort-Object)) {
    $folder = Get-DestFolder $url
    $destDir = Join-Path $Base $folder
    New-Item -ItemType Directory -Force -Path $destDir | Out-Null
    $fileName = Get-FileName $url
    $destPath = Join-Path $destDir $fileName

    if ((Test-Path $destPath) -and ((Get-Item $destPath).Length -gt 1024)) {
        $skip++
        continue
    }

    try {
        $client.DownloadFile($url, $destPath)
        if ((Get-Item $destPath).Length -lt 512) {
            Remove-Item $destPath -Force -ErrorAction SilentlyContinue
            throw 'File too small - likely error page'
        }
        $ok++
        Add-Content $LogFile "$(Get-Date -Format o) OK $fileName"
    } catch {
        $fail++
        Add-Content $LogFile "$(Get-Date -Format o) FAIL $url : $($_.Exception.Message)"
        Start-Sleep -Milliseconds 500
    }
    Start-Sleep -Milliseconds 150
}

$client.Dispose()
"$(Get-Date -Format o) Done. Downloaded=$ok Skipped=$skip Failed=$fail Total=$($allUrls.Count)" | Add-Content $LogFile
