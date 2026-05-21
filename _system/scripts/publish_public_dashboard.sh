#!/usr/bin/env bash
# Sync dashboard/index.html + dashboard_data.json to the public GitHub Pages repo.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DASHBOARD_REPO="${DASHBOARD_REPO:-GoldmanDrew/single-stock-dashboard}"
TOKEN="${GH_TOKEN:-${GITHUB_TOKEN:-}}"

if [[ -z "$TOKEN" ]]; then
  echo "ERROR: GH_TOKEN or GITHUB_TOKEN required to push public dashboard." >&2
  exit 1
fi

python "$ROOT/_system/scripts/build_dashboard_data.py"

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

git clone --depth 1 "https://x-access-token:${TOKEN}@github.com/${DASHBOARD_REPO}.git" "$WORKDIR/repo"
mkdir -p "$WORKDIR/repo/data"
cp "$ROOT/dashboard/index.html" "$WORKDIR/repo/index.html"
cp "$ROOT/dashboard/data/dashboard_data.json" "$WORKDIR/repo/data/dashboard_data.json"

cd "$WORKDIR/repo"
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add index.html data/dashboard_data.json

if git diff --staged --quiet; then
  echo "Public dashboard already up to date."
  exit 0
fi

git commit -m "chore: daily dashboard sync $(date -u +%Y-%m-%d)"
git push origin main
echo "Published https://$(echo "$DASHBOARD_REPO" | tr '[:upper:]' '[:lower:]' | cut -d/ -f1).github.io/$(echo "$DASHBOARD_REPO" | cut -d/ -f2)/"
