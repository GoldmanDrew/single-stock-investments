CREATE TABLE IF NOT EXISTS portfolio_ingest_nonces (
  nonce TEXT PRIMARY KEY,
  received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS portfolio_source_runs (
  source_run_id TEXT PRIMARY KEY,
  schema_version TEXT NOT NULL,
  source TEXT NOT NULL,
  account_alias TEXT,
  as_of TEXT NOT NULL,
  complete INTEGER NOT NULL CHECK (complete IN (0, 1)),
  completeness_json TEXT NOT NULL DEFAULT '{}',
  content_sha256 TEXT NOT NULL,
  object_key TEXT NOT NULL,
  received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS portfolio_account_values (
  source_run_id TEXT NOT NULL REFERENCES portfolio_source_runs(source_run_id) ON DELETE CASCADE,
  tag TEXT NOT NULL,
  currency TEXT NOT NULL DEFAULT '',
  segment TEXT NOT NULL DEFAULT '',
  model_code TEXT NOT NULL DEFAULT '',
  value_decimal TEXT NOT NULL,
  source TEXT NOT NULL,
  as_of TEXT NOT NULL,
  PRIMARY KEY(source_run_id, tag, currency, segment, model_code)
);

CREATE TABLE IF NOT EXISTS portfolio_positions (
  source_run_id TEXT NOT NULL REFERENCES portfolio_source_runs(source_run_id) ON DELETE CASCADE,
  account_alias TEXT NOT NULL,
  conid INTEGER NOT NULL,
  model_code TEXT NOT NULL DEFAULT '',
  symbol TEXT NOT NULL,
  local_symbol TEXT,
  description TEXT,
  sec_type TEXT NOT NULL,
  currency TEXT NOT NULL,
  exchange_name TEXT,
  expiry TEXT,
  strike_decimal TEXT,
  right_code TEXT,
  multiplier_decimal TEXT,
  quantity_decimal TEXT NOT NULL,
  average_cost_decimal TEXT,
  mark_decimal TEXT,
  market_value_decimal TEXT,
  unrealized_pnl_decimal TEXT,
  realized_pnl_decimal TEXT,
  daily_pnl_decimal TEXT,
  source TEXT NOT NULL,
  quality TEXT NOT NULL,
  as_of TEXT NOT NULL,
  PRIMARY KEY(source_run_id, account_alias, conid, model_code)
);

CREATE INDEX IF NOT EXISTS idx_portfolio_positions_latest
  ON portfolio_positions(account_alias, as_of DESC, symbol);

CREATE TABLE IF NOT EXISTS portfolio_broker_orders (
  source_run_id TEXT NOT NULL REFERENCES portfolio_source_runs(source_run_id) ON DELETE CASCADE,
  account_alias TEXT NOT NULL,
  client_id INTEGER,
  order_id INTEGER NOT NULL,
  perm_id INTEGER,
  conid INTEGER,
  symbol TEXT,
  action TEXT,
  order_type TEXT,
  total_quantity_decimal TEXT,
  limit_price_decimal TEXT,
  tif TEXT,
  status TEXT,
  order_ref TEXT,
  ownership TEXT NOT NULL,
  parent_id INTEGER,
  oca_group TEXT,
  as_of TEXT NOT NULL,
  PRIMARY KEY(source_run_id, client_id, order_id)
);

CREATE TABLE IF NOT EXISTS portfolio_allocations (
  allocation_id TEXT PRIMARY KEY,
  account_alias TEXT NOT NULL,
  conid INTEGER NOT NULL,
  model_code TEXT NOT NULL DEFAULT '',
  owner TEXT NOT NULL CHECK (owner IN ('drew', 'michael', 'unallocated')),
  strategy TEXT NOT NULL,
  bucket TEXT,
  quantity_decimal TEXT NOT NULL,
  confidence TEXT NOT NULL,
  effective_at TEXT NOT NULL,
  ended_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_portfolio_allocations_active
  ON portfolio_allocations(account_alias, conid, model_code, effective_at, ended_at);

CREATE TABLE IF NOT EXISTS portfolio_cash_events (
  event_id TEXT PRIMARY KEY,
  account_alias TEXT NOT NULL,
  owner TEXT NOT NULL CHECK (owner IN ('drew', 'michael', 'unallocated')),
  strategy TEXT NOT NULL,
  currency TEXT NOT NULL,
  amount_decimal TEXT NOT NULL,
  event_type TEXT NOT NULL,
  effective_at TEXT NOT NULL,
  source TEXT NOT NULL,
  source_event_id TEXT
);

CREATE TABLE IF NOT EXISTS portfolio_reconciliation_breaks (
  break_id TEXT PRIMARY KEY,
  source_run_id TEXT NOT NULL REFERENCES portfolio_source_runs(source_run_id),
  account_alias TEXT NOT NULL,
  conid INTEGER,
  model_code TEXT,
  break_type TEXT NOT NULL,
  expected_decimal TEXT,
  actual_decimal TEXT,
  severity TEXT NOT NULL,
  status TEXT NOT NULL,
  details_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS portfolio_strategy_snapshots (
  source_run_id TEXT PRIMARY KEY REFERENCES portfolio_source_runs(source_run_id),
  producer TEXT NOT NULL,
  payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS portfolio_allocation_projections (
  projection_id TEXT PRIMARY KEY,
  source_run_id TEXT NOT NULL REFERENCES portfolio_source_runs(source_run_id),
  account_alias TEXT NOT NULL,
  as_of TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  object_key TEXT NOT NULL,
  received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS portfolio_flex_sessions (
  source_run_id TEXT PRIMARY KEY REFERENCES portfolio_source_runs(source_run_id),
  account_alias TEXT NOT NULL,
  session_date TEXT NOT NULL,
  is_primary INTEGER NOT NULL CHECK (is_primary IN (0, 1)),
  restates_source_run_id TEXT,
  payload_json TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_portfolio_flex_primary
  ON portfolio_flex_sessions(account_alias, session_date) WHERE is_primary=1;

CREATE TABLE IF NOT EXISTS portfolio_order_events (
  event_id TEXT PRIMARY KEY,
  intent_uuid TEXT NOT NULL,
  account_alias TEXT NOT NULL,
  conid INTEGER NOT NULL,
  order_ref TEXT NOT NULL,
  state TEXT NOT NULL,
  event_type TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_portfolio_orders_recent
  ON portfolio_order_events(account_alias, created_at DESC);
