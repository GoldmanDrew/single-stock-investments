# Publish workspace to GitHub (run after: gh auth login)
$ErrorActionPreference = "Stop"
$Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
if (-not (Test-Path $Root)) { $Root = "C:\Users\werdn\Documents\Investing\Single Stock Investments" }

Set-Location $Root

gh auth status | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Not logged in. Run: gh auth login --web"
    exit 1
}

$RepoName = "single-stock-investments"
$User = (gh api user -q .login)

if (-not (git remote get-url origin 2>$null)) {
    gh repo create "$User/$RepoName" --private --source=. --remote=origin --description "Marvin single-stock research workspace with portfolio dashboard"
}

python _system/scripts/build_dashboard_data.py
git add -A
if (-not (git diff --staged --quiet)) {
    git commit -m "chore: refresh dashboard data"
}

git push -u origin main
Write-Host "Repo: https://github.com/$User/$RepoName"
Write-Host "Enable GitHub Pages: Settings -> Pages -> GitHub Actions (workflow dashboard-deploy.yml)"
