# Publish workspace to GitHub (run after: gh auth login)
$ErrorActionPreference = "Stop"
$Root = "C:\Users\werdn\Documents\Investing\Single Stock Investments"
Set-Location $Root

gh auth status | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Not logged in. Run: gh auth login --web"
    exit 1
}

$RepoName = "single-stock-investments"
$DashboardRepo = "single-stock-dashboard"
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
Write-Host "Private repo: https://github.com/$User/$RepoName"

# Sync static dashboard to public Pages repo (private repos cannot use GitHub Pages on free plan)
$tmp = Join-Path $env:TEMP "single-stock-dashboard"
if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
New-Item -ItemType Directory -Force -Path "$tmp\data" | Out-Null
Copy-Item "$Root\dashboard\index.html" "$tmp\index.html"
Copy-Item "$Root\dashboard\data\dashboard_data.json" "$tmp\data\dashboard_data.json"
Set-Location $tmp
if (-not (Test-Path ".git")) { git init; git branch -M main }
git add .
if (-not (git diff --staged --quiet)) {
    git commit -m "chore: refresh dashboard data"
}
if (-not (git remote get-url origin 2>$null)) {
    gh repo create "$User/$DashboardRepo" --public --source=. --remote=origin --description "Public portfolio dashboard for single-stock holdings"
    gh api "repos/$User/$DashboardRepo/pages" -X POST -f build_type=legacy -f "source[branch]=main" -f "source[path]=/" | Out-Null
}
git push -u origin main
Write-Host "Dashboard: https://$($User.ToLower()).github.io/$DashboardRepo/"
