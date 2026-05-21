# Move existing PDFs into organized folders (idempotent)
$ErrorActionPreference = 'Continue'
$Base = Split-Path $PSScriptRoot -Parent
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

$UrlFile = Join-Path $Base '_pdf_urls.txt'
$urlByFile = @{}
if (Test-Path $UrlFile) {
    Get-Content $UrlFile | ForEach-Object {
        if ($_ -match '^https?://') {
            $fn = ([IO.Path]::GetFileName(($_ -split '\?')[0])).ToLower()
            if (-not $urlByFile.ContainsKey($fn)) { $urlByFile[$fn] = $_ }
        }
    }
}

$moved = 0
Get-ChildItem $Base -Recurse -File -Filter *.pdf | Where-Object {
    $_.FullName -notmatch '\\_scripts\\'
} | ForEach-Object {
    $fn = $_.Name.ToLower()
    $url = $urlByFile[$fn]
    if ($url -and $url -notmatch 'jpx\.co\.jp/(english|corporate)/') { $url = $null }
    if (-not $url) {
        $n = $_.Name
        if ($n -match '^E_ER_|^ER_JPX|^ER_') {
            $url = 'https://www.jpx.co.jp/english/corporate/investor-relations/ir-library/financial-info/' + $n
        } elseif ($n -match '^E_EM_|^EM_JPX|^EM_') {
            $url = 'https://www.jpx.co.jp/english/corporate/investor-relations/ir-library/financial-info/' + $n
        } elseif ($n -match 'InvestorDay|IR_Day|JPX_IR_Day|Investor_Day') {
            $url = 'https://www.jpx.co.jp/english/corporate/investor-relations/ir-library/events/tvdivq0000009f1z-att/' + $n
        } elseif ($n -match 'mtmp|itmp|IT_Master|mplan|itplan|Medium_Term|sjcobq|b5b4pj00000') {
            $url = 'https://www.jpx.co.jp/english/corporate/investor-relations/management/mid-business-plan/' + $n
        } elseif ($n -match 'JPXReport|jpx_AR|jpxreport|annual_|2015_jpxreport') {
            $url = 'https://www.jpx.co.jp/english/corporate/investor-relations/ir-library/integrated-report/' + $n
        } elseif ($n -match 'Annual_Securities|ConsolidatedFinancial') {
            $url = 'https://www.jpx.co.jp/english/corporate/investor-relations/ir-library/securities-reports/' + $n
        } elseif ($n -match 'Extraordinary|^\d{8}') {
            $url = 'https://www.jpx.co.jp/english/corporate/investor-relations/ir-library/others/' + $n
        } elseif ($n -match 'transcript') {
            $url = 'https://www.jpx.co.jp/english/corporate/investor-relations/ir-library/events/' + $n
        } elseif ($n -match 'QA_|_QA|FAQ') {
            $url = 'https://www.jpx.co.jp/english/corporate/investor-relations/ir-library/events/' + $n
        } elseif ($_.DirectoryName -match 'Annual_Securities|securities-reports') {
            $url = 'https://www.jpx.co.jp/corporate/investor-relations/ir-library/securities-reports/' + $n
        } elseif ($n -match '^view\d|^View\d|yuho|h2[0-9]_') {
            $url = 'https://www.jpx.co.jp/corporate/investor-relations/ir-library/securities-reports/' + $n
        } else {
            $url = 'https://www.jpx.co.jp/english/corporate/investor-relations/ir-library/events/' + $n
        }
    }
    $destDir = Join-Path $Base (Get-DestFolder $url)
    New-Item -ItemType Directory -Force -Path $destDir | Out-Null
    $dest = Join-Path $destDir $_.Name
    if ($_.FullName -eq $dest) { return }
    if (Test-Path $dest) {
        if ((Get-Item $dest).Length -ge $_.Length) { Remove-Item $_.FullName -Force; return }
        Remove-Item $dest -Force
    }
    Move-Item $_.FullName $dest -Force
    $moved++
}

# Remove empty legacy dirs
@('01_Official\Annual_Securities_Reports', '02_Quarterly\Explanatory_Materials', '02_Quarterly\Earnings_Releases',
  '03_Events\IR_Events', '03_Events\Investor_Day', '05_Strategy\Mid_Term_Business_Plan') | ForEach-Object {
    $p = Join-Path $Base $_
    if ((Test-Path $p) -and -not (Get-ChildItem $p -Recurse -File -ErrorAction SilentlyContinue)) {
        Remove-Item $p -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "Moved $moved files"
