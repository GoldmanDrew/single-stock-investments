#!/usr/bin/env bash
# Publish broker truth from IBKR Flex. Opens NO IB connection of any kind.
#
# This replaces the collector that was masked on 2026-08-25 for reconnect-
# storming the Gateway (CLAUDE.md rule 9). It reads XML that ls-algo already
# fetches once a day for its own accounting, so it adds zero IBKR requests --
# not fewer, zero -- and it exits when it is done. There is no loop here, and
# there must never be one.
set -uo pipefail

REPO=/home/spx/single-stock-investments
PY=/home/spx/portfolio-hub-venv/bin/python
DB=/home/spx/portfolio-hub/portfolio.db
RUNS=/home/spx/ls-algo/data/runs
ACCOUNT=${IBKR_ACCOUNT_ALIAS:-U805366}
STALE_HOURS=${STALE_HOURS:-30}

log() { printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

# Newest run directory that actually contains a positions file. "Newest
# directory" alone is not enough: the directory is created before the Flex
# statement finishes generating, and IBKR can take minutes to build one.
POSITIONS=""
for d in $(ls -1 "$RUNS" 2>/dev/null | grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' | sort -r | head -5); do
  if [ -s "$RUNS/$d/ibkr_flex/flex_positions.xml" ]; then
    POSITIONS="$RUNS/$d/ibkr_flex/flex_positions.xml"
    break
  fi
done

if [ -z "$POSITIONS" ]; then
  log "no flex_positions.xml in the last 5 run directories; nothing to publish"
  exit 0
fi
log "using $POSITIONS"

set -a; . /home/spx/.config/portfolio-hub/secrets.env; set +a
cd "$REPO" || exit 1

# The CLI refuses a file older than --stale-hours itself. Republishing a frozen
# book as current is the failure this guard exists for; it is not an
# optimisation.
"$PY" -m _system.trading.portfolio_hub --db "$DB" flex-publish \
  --positions "$POSITIONS" \
  --account "$ACCOUNT" \
  --url "$PORTFOLIO_INGEST_URL" \
  --stale-hours "$STALE_HOURS"
rc=$?
log "flex-publish exit=$rc"
exit $rc
