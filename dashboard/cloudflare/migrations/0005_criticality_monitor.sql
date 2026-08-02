CREATE TABLE IF NOT EXISTS criticality_snapshots (
  scope TEXT NOT NULL CHECK (scope IN ('market', 'sector', 'security')),
  symbol TEXT NOT NULL,
  as_of TEXT NOT NULL,
  horizon TEXT NOT NULL DEFAULT 'multi',
  model_version TEXT NOT NULL,
  direction TEXT NOT NULL CHECK (
    direction IN ('positive_bubble', 'negative_bubble', 'none')
  ),
  criticality_score REAL NOT NULL,
  positive_confidence REAL NOT NULL,
  negative_confidence REAL NOT NULL,
  qualified_confidence REAL NOT NULL,
  tc_p10_days REAL,
  tc_median_days REAL,
  tc_p90_days REAL,
  fit_count INTEGER NOT NULL,
  qualified_count INTEGER NOT NULL,
  source TEXT,
  entitlement_mode TEXT,
  quality_state TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (scope, symbol, as_of, horizon, model_version)
);

CREATE TABLE IF NOT EXISTS flow_stress_snapshots (
  scope TEXT NOT NULL CHECK (scope IN ('market', 'sector', 'security')),
  symbol TEXT NOT NULL,
  as_of TEXT NOT NULL,
  model_version TEXT NOT NULL,
  state TEXT NOT NULL,
  pressure_score REAL,
  panic_score REAL,
  exhaustion_score REAL,
  liquidity_score REAL,
  breadth_score REAL,
  vol_target_pressure_low REAL,
  vol_target_pressure_high REAL,
  source TEXT,
  entitlement_mode TEXT,
  quality_state TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (scope, symbol, as_of, model_version)
);

CREATE TABLE IF NOT EXISTS market_risk_alerts (
  alert_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL CHECK (scope IN ('market', 'sector', 'security')),
  symbol TEXT NOT NULL,
  opened_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  closed_at TEXT,
  state TEXT NOT NULL,
  severity TEXT NOT NULL,
  model_version TEXT NOT NULL,
  reason_codes_json TEXT NOT NULL,
  payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS market_risk_ingest_runs (
  request_id TEXT PRIMARY KEY,
  received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  generated_at TEXT,
  source TEXT,
  criticality_count INTEGER NOT NULL DEFAULT 0,
  flow_count INTEGER NOT NULL DEFAULT 0,
  symbols_json TEXT NOT NULL,
  status TEXT NOT NULL,
  latency_ms REAL,
  payload_bytes INTEGER
);

CREATE TABLE IF NOT EXISTS market_risk_ingest_nonces (
  nonce TEXT PRIMARY KEY,
  received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_criticality_latest
  ON criticality_snapshots(scope, symbol, as_of DESC);
CREATE INDEX IF NOT EXISTS idx_criticality_direction
  ON criticality_snapshots(as_of DESC, direction, criticality_score DESC);
CREATE INDEX IF NOT EXISTS idx_flow_stress_latest
  ON flow_stress_snapshots(scope, symbol, as_of DESC);
CREATE INDEX IF NOT EXISTS idx_market_risk_alerts_open
  ON market_risk_alerts(closed_at, severity, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_market_risk_ingest_received
  ON market_risk_ingest_runs(received_at DESC);
CREATE INDEX IF NOT EXISTS idx_market_risk_nonce_received
  ON market_risk_ingest_nonces(received_at DESC);
