#!/usr/bin/env bash
# Checkout repo with CI profile-specific sparse paths.
#
# GitHub Actions cannot use ./.github/actions/* before actions/checkout runs.
# Every job must bootstrap with public actions, then call this script:
#   1. jlumbroso/free-disk-space@main (optional; heavy profiles only)
#   2. actions/checkout@v4 (sparse: ci_checkout_workspace.sh, ci_resolve_checkout_ref.sh, ci_sparse_checkout_paths.py)
#   3. bash _system/scripts/ci_checkout_workspace.sh <profile> [ref] [depth]
#
# Local actions (commit-main, marvin-agent, publish-dashboard, etc.) are safe
# after step 3 because .github/ is included in every profile.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
source "$SCRIPT_DIR/ci_resolve_checkout_ref.sh"

PROFILE="${1:?profile required: full|history|news|marvin-pick|marvin-forecast|minimal|marvin-agent|darwin|dashboard|pages}"
REF_INPUT="${2:-}"
FETCH_DEPTH="${3:-}"

if [ -z "$FETCH_DEPTH" ]; then
  if [ "$PROFILE" = "history" ]; then
    FETCH_DEPTH=0
  else
    FETCH_DEPTH=1
  fi
fi

REF=$(resolve_checkout_ref "$REF_INPUT")

if [ -n "${GITHUB_WORKSPACE:-}" ]; then
  git config --global --add safe.directory "$GITHUB_WORKSPACE"
fi

fetch_ref() {
  if [ "$FETCH_DEPTH" = "0" ]; then
    git fetch origin "$REF"
  else
    git fetch --depth="$FETCH_DEPTH" origin "$REF"
  fi
}

checkout_ref() {
  git checkout -B "$REF" "origin/$REF" 2>/dev/null || git checkout FETCH_HEAD
}

apply_sparse_paths() {
  local paths_file
  paths_file=$(mktemp)
  {
    echo "_system"
    echo ".github"
    echo "dashboard"
    python3 "$SCRIPT_DIR/ci_sparse_checkout_paths.py" "$PROFILE"
  } >"$paths_file"
  local count
  count=$(grep -c . "$paths_file" || true)
  echo "Sparse profile=$PROFILE path_count=$count (batched set --stdin)"
  git sparse-checkout init --no-cone
  git sparse-checkout set --stdin <"$paths_file"
  rm -f "$paths_file"
}

case "$PROFILE" in
  full|history)
    git sparse-checkout disable 2>/dev/null || true
    fetch_ref
    checkout_ref
    ;;
  minimal|marvin-agent)
    git sparse-checkout init --no-cone
    # Makefile is required for letter-date-check / document-sync make targets.
    git sparse-checkout set _system .github Makefile
    git fetch --depth="$FETCH_DEPTH" --filter=blob:none origin "$REF"
    checkout_ref
    ;;
  pages)
    git sparse-checkout init --no-cone
    git sparse-checkout set _system .github dashboard Makefile
    git fetch --depth="$FETCH_DEPTH" --filter=blob:none origin "$REF"
    checkout_ref
    ;;
  news|marvin-pick|marvin-forecast|darwin|dashboard)
    git sparse-checkout init --no-cone
    # Seed with base dirs so fetch can resolve scripts before path list runs.
    git sparse-checkout set _system .github dashboard Makefile
    git fetch --depth="$FETCH_DEPTH" --filter=blob:none origin "$REF"
    checkout_ref
    apply_sparse_paths
    git read-tree -mu HEAD
    ;;
  *)
    echo "Unknown checkout profile: $PROFILE" >&2
    exit 1
    ;;
esac

echo "Checkout workspace profile=$PROFILE ref=$REF depth=$FETCH_DEPTH"
