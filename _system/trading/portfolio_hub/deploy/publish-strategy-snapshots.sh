#!/usr/bin/env bash
# Publish SPX 0DTE and ls-algo strategy snapshots to the dashboard.
#
# Both producers live on this box, so this reads two JSON files off local disk
# and POSTs to the HMAC ingest. It opens NO IB connection and is therefore
# outside the Gateway safety surface entirely -- see CLAUDE.md rule 0.
set -uo pipefail

REPO=/home/spx/single-stock-investments
PY=/home/spx/portfolio-hub-venv/bin/python
SPX_LIVE=/home/spx/spx-0dte/data/live
LS_LATEST=/home/spx/ls-algo/risk_dashboard/data/latest.json
OUT=/home/spx/portfolio-hub/strategy-snapshots
STALE_HOURS=${STALE_HOURS:-30}

log() { printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

# Newest session dir that actually has a live_status.json. The executor does not
# write one on a no-session day, so "newest dir" alone is not enough.
SPX_FILE=""
for d in $(ls -1 "$SPX_LIVE" 2>/dev/null | grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' | sort -r | head -5); do
  if [ -f "$SPX_LIVE/$d/live_status.json" ]; then SPX_FILE="$SPX_LIVE/$d/live_status.json"; break; fi
done

# Freshness is read off the FILE, not off the run succeeding. A producer that
# stops writing leaves a well-formed file behind, and publishing it forever would
# present a frozen book as current -- the exact failure that let the podcast
# catalog sit at 3,561 episodes while the page called it live.
fresh() {
  local path="$1" name="$2"
  [ -f "$path" ] || { log "SKIP $name: $path absent"; return 1; }
  local age=$(( ( $(date +%s) - $(stat -c %Y "$path") ) / 3600 ))
  if [ "$age" -gt "$STALE_HOURS" ]; then
    log "SKIP $name: ${age}h old (> ${STALE_HOURS}h). Producer has stopped writing; not republishing stale state."
    return 1
  fi
  log "ok   $name: ${age}h old  $path"
  return 0
}

ARGS=()
fresh "$SPX_FILE" spx_0dte  && ARGS+=(--spx "$SPX_FILE")
fresh "$LS_LATEST" ls_risk  && ARGS+=(--ls "$LS_LATEST")

if [ ${#ARGS[@]} -eq 0 ]; then
  log "no fresh producer artifacts; nothing to publish"
  exit 0
fi

set -a; . /home/spx/.config/portfolio-hub/secrets.env; set +a
mkdir -p "$OUT"
cd "$REPO" || exit 1
log "publishing: ${ARGS[*]}"
"$PY" -m _system.trading.portfolio_hub dual-publish "${ARGS[@]}" \
  --output-dir "$OUT" --url "$PORTFOLIO_INGEST_URL"
rc=$?
log "dual-publish exit=$rc"

# Keep the last 14 adapted bundles for forensics; they are small and R2 holds the
# authoritative copy anyway.
ls -1t "$OUT"/*.json 2>/dev/null | tail -n +29 | xargs -r rm -f
exit $rc
