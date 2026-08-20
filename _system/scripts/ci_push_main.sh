#!/usr/bin/env bash
# Rebase onto latest main and push (retries on transient rejections).
#
# Conflicts in derived artifacts are resolved by regeneration. Since the
# dashboard payload was sharded (core.json + per-ticker/per-section shards),
# giant-JSON collisions are rare; the resolver is a small classifier plus a
# builder table instead of bespoke per-artifact recovery functions.
set -euo pipefail
MAX_ATTEMPTS="${CI_PUSH_MAX_ATTEMPTS:-5}"
PYTHON="${PYTHON:-python3}"

git config user.name "${GIT_AUTHOR_NAME:-github-actions[bot]}"
git config user.email "${GIT_AUTHOR_EMAIL:-41898282+github-actions[bot]@users.noreply.github.com}"

rebase_in_progress() { [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]; }
conflicted_files() { git diff --name-only --diff-filter=U; }

# Derived artifacts that a builder can recreate from inputs after a rebase.
is_regenerable_artifact() {
  case "$1" in
    dashboard/data/*.json) return 0 ;;
    */INDEX.csv) return 0 ;;
    _system/portfolio/holdings.md|_system/portfolio/classification.json|_system/portfolio/us_ticker_config.json) return 0 ;;
    _system/reference/data-sources/insights_record_archive.json) return 0 ;;
    _system/reference/market-data/returns/*.csv) return 0 ;;
    _system/portfolio/research_events.jsonl) return 0 ;;
    _system/reference/market-data/external/sync_report.json) return 0 ;;
    *) return 1 ;;
  esac
}

# During rebase onto origin/main, --ours is upstream (main). Prefer main for
# Marvin-owned ticker research when refresh jobs race deep-dive merges.
is_prefer_upstream_on_rebase() {
  case "$1" in
    */research/*|*/third-party-analyses/*) return 0 ;;
    _system/memory/daily/*|_system/research/milly_log.md) return 0 ;;
    # Triage queues are rebuilt by whichever lane runs next, and two lanes on the
    # same day both create _system/reviews/pending/<name>_<date>.md, which lands
    # as an add/add conflict. They were classified as neither regenerable nor
    # prefer-upstream, so a single triage collision aborted the entire push --
    # podcast run 32332841926 lost its catalog commit that way after a
    # successful 72-minute refresh. This matches the intent already stated
    # below, where regenerate_conflicted_artifacts() restores this directory to
    # keep it out of intake commits; that cleanup just never ran, because these
    # files were what made the conflict unresolvable in the first place.
    _system/reviews/pending/*) return 0 ;;
    _system/data/transcript_sync_summary.json) return 0 ;;
    _system/lenses/universe_percentiles.json) return 0 ;;
    _system/reference/investment-wisdom/*/extract_refresh_status.json) return 0 ;;
    _system/reference/market-data/themes/*|_system/reference/market-data/peers/*|_system/reference/market-data/commodities/*|_system/reference/market-data/insider/*) return 0 ;;
    *) return 1 ;;
  esac
}

is_resolvable_rebase_conflict() {
  local file any=0
  while IFS= read -r file; do
    [ -n "$file" ] || continue
    any=1
    if ! is_regenerable_artifact "$file" && ! is_prefer_upstream_on_rebase "$file"; then
      echo "Non-resolvable rebase conflict in: $file"
      return 1
    fi
  done <<< "$(conflicted_files)"
  [ "$any" -eq 1 ]
}

# Builder keys per artifact class. Dashboard assembly runs last so it sees the
# other regenerated inputs. Keys map to run_builder cases below.
builders_for() {
  case "$1" in
    dashboard/data/insights.json|_system/reference/data-sources/insights_record_archive.json) echo insights ;;
    dashboard/data/activist_feed.json) echo activist ;;
    dashboard/data/*.json) echo dashboard ;;
    */INDEX.csv) echo indexes ;;
    _system/portfolio/holdings.md|_system/portfolio/classification.json|_system/portfolio/us_ticker_config.json) echo portfolio ;;
    _system/reference/market-data/returns/*.csv) echo returns ;;
    _system/portfolio/research_events.jsonl) echo research_events ;;
    _system/reference/market-data/external/sync_report.json) echo external_sync ;;
  esac
}

run_builder() {
  case "$1" in
    returns) "$PYTHON" _system/scripts/download_ira_research.py --tier A &&
      git add _system/reference/market-data/returns/ ;;
    indexes) "$PYTHON" _system/scripts/build_folder_indexes.py &&
      git add -- ':(glob)*/INDEX.csv' ;;
    portfolio) "$PYTHON" _system/scripts/sync_portfolio_from_registry.py &&
      git add _system/portfolio/holdings.md _system/portfolio/classification.json _system/portfolio/us_ticker_config.json ;;
    research_events) (cd _system/scripts && "$PYTHON" -c "from darwin.research_events import rebuild_events_log; rebuild_events_log()") &&
      git add _system/portfolio/research_events.jsonl ;;
    external_sync) (cd _system/scripts && "$PYTHON" -m darwin.import_external_data) || true
      git add _system/reference/market-data/external/sync_report.json 2>/dev/null || true ;;
    insights) "$PYTHON" _system/scripts/build_insights.py &&
      git add dashboard/data/insights.json _system/reference/data-sources/insights_record_archive.json ;;
    activist) { [ ! -f _system/scripts/clean_activist_indexes.py ] || "$PYTHON" _system/scripts/clean_activist_indexes.py; } &&
      "$PYTHON" _system/scripts/build_activist_feed.py &&
      git add dashboard/data/activist_feed.json ;;
    dashboard) "$PYTHON" _system/scripts/build_dashboard_data.py &&
      git add dashboard/data/ ;;
  esac
}

regenerate_conflicted_artifacts() {
  local conflicted file key needed=" "
  conflicted=$(conflicted_files)
  while IFS= read -r file; do
    [ -n "$file" ] || continue
    is_regenerable_artifact "$file" || continue
    rm -f "$file" 2>/dev/null || true
    key=$(builders_for "$file")
    case "$needed" in *" $key "*) ;; *) needed="$needed$key " ;; esac
  done <<< "$conflicted"

  for key in returns indexes portfolio research_events external_sync insights activist dashboard; do
    case "$needed" in
      *" $key "*)
        echo "Regenerating '$key' artifacts to resolve rebase conflicts..."
        if ! run_builder "$key"; then
          echo "::error::Builder '$key' failed while resolving a rebase conflict."
          return 1
        fi
        ;;
    esac
  done

  # Builders may refresh triage queues; keep them out of intake commits.
  [ ! -d _system/reviews/pending ] || git restore --worktree _system/reviews/pending/ 2>/dev/null || true

  # Stage regenerated conflict paths; drop any a builder no longer emits.
  while IFS= read -r file; do
    [ -n "$file" ] || continue
    is_regenerable_artifact "$file" || continue
    if [ -f "$file" ]; then git add -f "$file"; else git rm -f --cached "$file" 2>/dev/null || true; fi
  done <<< "$conflicted"
}

resolve_prefer_upstream_conflicts() {
  local file
  while IFS= read -r file; do
    [ -n "$file" ] || continue
    is_prefer_upstream_on_rebase "$file" || continue
    echo "Preferring origin/main for rebase conflict: $file"
    git checkout --ours -- "$file" 2>/dev/null || true
    if [ -f "$file" ]; then git add -- "$file"; else git rm -f -- "$file" 2>/dev/null || true; fi
  done <<< "$(conflicted_files)"
}

continue_rebase_after_resolution() {
  # Regeneration can reproduce origin/main byte-for-byte; skip the now-empty
  # commit instead of treating it as a failed resolution.
  if git diff --cached --quiet; then
    echo "Resolved rebase commit is empty after regeneration; skipping it."
    GIT_EDITOR=true git rebase --skip
  else
    GIT_EDITOR=true git rebase --continue
  fi
}

stage_remaining_regenerable_conflicts() {
  # Safety net: builders (or test doubles) may rewrite a conflicted path
  # without staging it. Stage regenerable paths so the rebase can continue.
  local file
  while IFS= read -r file; do
    [ -n "$file" ] || continue
    is_regenerable_artifact "$file" || continue
    if [ -f "$file" ]; then git add -f -- "$file"; else git rm -f --cached -- "$file" 2>/dev/null || true; fi
  done <<< "$(conflicted_files)"
}

try_resolve_rebase_conflicts() {
  rebase_in_progress || return 1
  is_resolvable_rebase_conflict || return 1
  resolve_prefer_upstream_conflicts
  if ! regenerate_conflicted_artifacts; then
    echo "::error::Artifact regeneration failed; rebase remains open."
    return 1
  fi
  stage_remaining_regenerable_conflicts
  if [ -n "$(conflicted_files)" ]; then
    echo "::error::Conflicted paths remain unmerged after regeneration:"
    conflicted_files
    return 1
  fi
  if ! continue_rebase_after_resolution; then
    # A non-zero continue that lands on another regenerable conflict is
    # progress on a multi-commit rebase, not a failure.
    if rebase_in_progress && is_resolvable_rebase_conflict; then
      echo "Advanced to another regenerable rebase conflict; resolving the next commit."
      return 0
    fi
    echo "::error::git rebase --continue failed after conflict resolution."
    conflicted_files || true
    return 1
  fi
  rebase_in_progress || return 0
  is_resolvable_rebase_conflict
}

_check_file_sizes_for_paths() {
  local limit=$((100 * 1024 * 1024)) warn=$((50 * 1024 * 1024)) failed=0 file size
  while IFS= read -r file; do
    [ -n "$file" ] && [ -f "$file" ] || continue
    size=$(stat -c%s "$file" 2>/dev/null || stat -f%z "$file")
    if [ "$size" -gt "$limit" ]; then
      echo "::error::File $file is $((size / 1024 / 1024))MB; exceeds GitHub 100MB limit."
      failed=1
    elif [ "$size" -gt "$warn" ]; then
      echo "::warning::File $file is $((size / 1024 / 1024))MB; above GitHub 50MB recommendation."
    fi
  done
  [ "$failed" -eq 0 ]
}

check_github_file_sizes() {
  _check_file_sizes_for_paths < <(git diff --cached --name-only --diff-filter=ACM)
}

check_push_file_sizes() {
  _check_file_sizes_for_paths < <(git diff --name-only origin/main...HEAD)
}

sync_self_from_origin_main() {
  [ "${CI_PUSH_SKIP_SELF_REFRESH:-0}" = "1" ] && return 0
  git rev-parse --git-dir >/dev/null 2>&1 || return 0
  git fetch origin main >/dev/null 2>&1 || return 0
  git cat-file -e "origin/main:_system/scripts/ci_push_main.sh" 2>/dev/null || return 0
  local dest="_system/scripts/ci_push_main.sh" tmp
  tmp=$(mktemp)
  git show "origin/main:_system/scripts/ci_push_main.sh" > "$tmp"
  if cmp -s "$tmp" "$dest"; then rm -f "$tmp"; return 0; fi
  echo "Syncing ci_push_main.sh from origin/main (conflict resolver update)."
  cp "$tmp" "$dest" && chmod +x "$dest" && rm -f "$tmp"
  # Reload functions only; the sourcing guard prevents zero-arg re-entry.
  # shellcheck disable=SC1091
  CI_PUSH_SOURCING=1 source "$dest"
}

ensure_main_rebase_history() {
  # Depth-1 sparse checkouts often cannot compute origin/main...HEAD merge-base
  # once main advances. Deepen (or unshallow) before rebase/push.
  if [ "$(git rev-parse --is-shallow-repository 2>/dev/null || echo false)" = "true" ]; then
    echo "Deepening shallow clone for rebase onto origin/main..."
    git fetch --deepen=200 origin main 2>/dev/null \
      || git fetch --unshallow origin 2>/dev/null \
      || git fetch origin main
  else
    git fetch origin main
  fi
}

clean_worktree_for_rebase() {
  # Rebuild steps may dirty files outside the staged commit set; rebase refuses
  # to start with unstaged changes. --keep-index preserves the commit payload.
  git update-index -q --refresh || true
  if ! git diff --quiet || [ -n "$(git ls-files --others --exclude-standard | head -n 1)" ]; then
    echo "Stashing unstaged/untracked worktree dirt before rebase..."
    git stash push -u --keep-index -m "ci_push_main-pre-rebase" || true
  fi
}

ci_push_main() {
  local msg="${1:?commit message required}"
  sync_self_from_origin_main
  # A self-refresh updates this tracked helper in the worktree. Stage it so a
  # later rebase always starts from a clean tree.
  git diff --quiet -- _system/scripts/ci_push_main.sh || git add _system/scripts/ci_push_main.sh
  if git diff --staged --quiet; then
    echo "No staged changes to commit."
    exit 0
  fi
  if ! check_github_file_sizes; then
    echo "::error::Aborting commit: staged files exceed GitHub size limits."
    exit 1
  fi
  # Drop unstaged noise so the post-commit rebase can start cleanly.
  clean_worktree_for_rebase
  git commit -m "$msg"

  local attempt=1
  while [ "$attempt" -le "$MAX_ATTEMPTS" ]; do
    ensure_main_rebase_history
    clean_worktree_for_rebase
    if ! git rebase origin/main; then
      while rebase_in_progress && try_resolve_rebase_conflicts; do
        echo "Resolved regenerable rebase conflicts; continuing rebase (attempt $attempt/$MAX_ATTEMPTS)."
      done
      if rebase_in_progress; then
        echo "::error::Rebase onto origin/main failed (attempt $attempt/$MAX_ATTEMPTS)."
        git rebase --abort 2>/dev/null || true
        exit 1
      fi
      echo "Rebase conflicts resolved via artifact regeneration (attempt $attempt/$MAX_ATTEMPTS)."
    fi
    if ! check_push_file_sizes; then
      echo "::error::Aborting push: commits ahead of origin/main exceed GitHub size limits."
      exit 1
    fi
    if git push origin HEAD:main; then
      echo "Pushed to main (attempt $attempt)."
      exit 0
    fi
    echo "Push rejected (attempt $attempt/$MAX_ATTEMPTS); retrying after fetch/rebase..."
    sleep $((attempt * 4))
    attempt=$((attempt + 1))
  done

  echo "::error::Failed to push to main after $MAX_ATTEMPTS attempts."
  exit 1
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]] && [[ "${CI_PUSH_SOURCING:-0}" != "1" ]]; then
  ci_push_main "$@"
fi
