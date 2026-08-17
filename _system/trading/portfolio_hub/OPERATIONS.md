# Portfolio hub operations

## Security boundary

- `dashboard/data/sleeves_*.json` is excluded from every Pages artifact and the browser has no static fallback.
- All `/api/v2/portfolio/*` reads validate the Cloudflare Access JWT at the origin and return `private, no-store`.
- Signed ingest uses a distinct `PORTFOLIO_INGEST_TOKEN`, timestamp, nonce, body HMAC, replay table, business ID, and immutable R2 copy.
- `PRIVATE_ARTIFACTS` is a private R2 binding. It is required; ingest fails if absent.
- Real account IDs live only in `IBKR_ACCOUNT_ID`. Public artifacts are scanned for broker-account patterns before deployment.
- Preview and `pages.dev` hostnames must be covered by Access or disabled. Verify unauthenticated requests to `/api/v2/portfolio/book` and the legacy sleeve endpoint return 401 before rollout.

## Data lifecycle

1. Collector opens a session epoch, pins the configured account, waits for complete account summary and position end markers, and publishes `account_snapshot.v1`. A missing permission or end marker produces `complete=false`, never an empty account.
2. The local ledger writes snapshots, events, allocations, cash, and outbox rows transactionally in SQLite/WAL.
3. Allocation reconciliation runs only against one complete snapshot watermark. Every broker quantity must equal Drew + Michael + Unallocated within decimal tolerance.
4. The publisher sends the account snapshot, `allocation_projection.v1`, and producer artifacts to the signed endpoint. D1 is the query projection; R2 and the local ledger are evidence.
5. Flex creates completed-session truth. Session P&L is immutable; later changes are separate restatements. Wall-clock date and legacy `pnl_today` aliases are not daily truth.

Telemetry is sampled/coalesced; broker executions, order transitions, commissions, cash flows, allocation overrides, and restatements are immutable business events. Do not archive every quote tick.

## Backup and recovery

- Run SQLite online backup at least daily and before migrations; encrypt backups at rest and retain 35 daily plus 12 monthly copies.
- Quarterly restore drill: restore to a temporary path, run migrations and integrity check, rebuild the latest read model, and compare source-run hashes.
- R2 retention follows the same minimum horizon; raw payload object keys are content-linked from D1.
- On corrupt/incomplete state, disable commands, preserve files, restore the ledger, replay broker/Flex events, then reconcile before re-enabling paper mode.

## Incident controls

The order kill switch rejects new intents without cancelling foreign orders. Disconnection, stale quote, unknown account, incomplete snapshot, unresolved ownership, price/tick violation, notional breach, or uncertain send fail closed. Alerts cover stale broker/producer feeds, incomplete snapshots, critical reconciliation breaks, unknown working orders, low excess liquidity, and undelivered outbox age.

## Cutover

Export local SleeveStore and hosted D1 v1 separately, back both up, map ticker rows to conIds, review conflicts, bootstrap opening allocations/cash with `legacy_inferred` labels, and suppress pre-cutover owner performance that cannot be reconstructed. Dual-run the private v2 read model before retiring the now-authenticated v1 schema. The old public gist is retired only after the private SPX monitor has dual-published and matched.
