CREATE TABLE IF NOT EXISTS market_risk_component_snapshots (
  component TEXT NOT NULL,
  scope TEXT NOT NULL CHECK (scope IN ('market', 'sector', 'security')),
  symbol TEXT NOT NULL,
  as_of TEXT NOT NULL,
  cadence TEXT NOT NULL,
  source TEXT NOT NULL,
  model_version TEXT NOT NULL,
  entitlement_mode TEXT NOT NULL,
  quality_state TEXT NOT NULL,
  score REAL,
  value REAL,
  unit TEXT,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (component, scope, symbol, as_of, source, model_version)
);

CREATE INDEX IF NOT EXISTS idx_market_risk_components_latest
  ON market_risk_component_snapshots(component, scope, symbol, as_of DESC);
CREATE INDEX IF NOT EXISTS idx_market_risk_components_quality
  ON market_risk_component_snapshots(quality_state, as_of DESC);

ALTER TABLE market_risk_ingest_runs
  ADD COLUMN component_count INTEGER NOT NULL DEFAULT 0;
