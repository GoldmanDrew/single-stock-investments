-- The row scans 0014 left behind.
--
-- 0014 fixed the current-state routes by materializing market_risk_latest_refs.
-- Two classes of full scan survived it, both for the same reason: the filtered
-- column is not the leading column of any existing index, so SQLite cannot seek
-- and reads the whole table. D1 bills rows scanned, not rows returned.
--
--   1. /api/v1/market-risk/history filters on symbol alone, but every index on
--      the snapshot tables leads with scope. Each request read all of
--      criticality_snapshots and flow_stress_snapshots to return 250 rows.
--   2. prune_cloudflare_d1.py deletes by time alone (WHERE <column> < cutoff).
--      Only criticality had a time-leading index, so the other tables were
--      rescanned once per 1,000-row batch, on every deployment.
--
-- Index construction reads each table once. Deploy applies these migrations
-- before retention so prune can seek on received_at / as_of instead of
-- full-scanning (the previous prune-first order exhausted free-tier reads).

-- 1. History route: seek to the symbol, then walk it in the order the route
-- already asks for, so the LIMIT bounds rows read instead of rows returned.
CREATE INDEX IF NOT EXISTS idx_criticality_symbol_history
  ON criticality_snapshots(symbol, as_of DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_flow_stress_symbol_history
  ON flow_stress_snapshots(symbol, as_of DESC, created_at DESC);

-- 2. Retention time policies in prune_cloudflare_d1.py.
-- criticality_snapshots is already served by idx_criticality_direction, whose
-- leading column is as_of; if that index is ever dropped, criticality needs an
-- as_of index added here or its retention silently returns to a full scan.
CREATE INDEX IF NOT EXISTS idx_flow_stress_as_of
  ON flow_stress_snapshots(as_of);
CREATE INDEX IF NOT EXISTS idx_market_risk_components_as_of
  ON market_risk_component_snapshots(as_of);
CREATE INDEX IF NOT EXISTS idx_sleeve_marks_as_of
  ON sleeve_marks(as_of);
CREATE INDEX IF NOT EXISTS idx_sleeve_classifier_audit_as_of
  ON sleeve_classifier_audit(as_of);
CREATE INDEX IF NOT EXISTS idx_sleeve_nonce_received
  ON sleeve_ingest_nonces(received_at);
CREATE INDEX IF NOT EXISTS idx_portfolio_nonce_received
  ON portfolio_ingest_nonces(received_at);

-- 3. Retention cascade. prune_portfolio_history deletes the referencing rows
-- before their source run. Three of the four reference tables already reach
-- source_run_id through a primary key or a leading index column; this one
-- reached it through a full scan per batch.
CREATE INDEX IF NOT EXISTS idx_portfolio_projections_run
  ON portfolio_allocation_projections(source_run_id);
