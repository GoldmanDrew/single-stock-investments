PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
  version TEXT PRIMARY KEY,
  applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_runs (
  source_run_id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  as_of TEXT NOT NULL,
  complete INTEGER NOT NULL CHECK (complete IN (0, 1)),
  content_sha256 TEXT NOT NULL,
  received_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS account_snapshots (
  snapshot_id TEXT PRIMARY KEY,
  source_run_id TEXT NOT NULL REFERENCES source_runs(source_run_id),
  account_alias TEXT NOT NULL,
  gateway_session_id TEXT,
  base_currency TEXT NOT NULL,
  as_of TEXT NOT NULL,
  complete INTEGER NOT NULL CHECK (complete IN (0, 1)),
  completeness_json TEXT NOT NULL DEFAULT '{}',
  UNIQUE(account_alias, source_run_id)
);

CREATE TABLE IF NOT EXISTS account_values (
  snapshot_id TEXT NOT NULL REFERENCES account_snapshots(snapshot_id) ON DELETE CASCADE,
  tag TEXT NOT NULL,
  currency TEXT NOT NULL,
  segment TEXT NOT NULL DEFAULT '',
  model_code TEXT NOT NULL DEFAULT '',
  value_decimal TEXT NOT NULL,
  source TEXT NOT NULL,
  as_of TEXT NOT NULL,
  PRIMARY KEY(snapshot_id, tag, currency, segment, model_code)
);

CREATE TABLE IF NOT EXISTS position_snapshot_rows (
  snapshot_id TEXT NOT NULL REFERENCES account_snapshots(snapshot_id) ON DELETE CASCADE,
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
  PRIMARY KEY(snapshot_id, account_alias, conid, model_code)
);

CREATE INDEX IF NOT EXISTS idx_positions_latest
  ON position_snapshot_rows(account_alias, conid, model_code, as_of DESC);

CREATE TABLE IF NOT EXISTS broker_order_snapshot_rows (
  snapshot_id TEXT NOT NULL REFERENCES account_snapshots(snapshot_id) ON DELETE CASCADE,
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
  PRIMARY KEY(snapshot_id, client_id, order_id)
);

CREATE TABLE IF NOT EXISTS allocation_lots (
  allocation_id TEXT PRIMARY KEY,
  account_alias TEXT NOT NULL,
  conid INTEGER NOT NULL,
  model_code TEXT NOT NULL DEFAULT '',
  owner TEXT NOT NULL CHECK (owner IN ('drew', 'michael', 'unallocated')),
  strategy TEXT NOT NULL,
  bucket TEXT,
  quantity_decimal TEXT NOT NULL,
  effective_at TEXT NOT NULL,
  ended_at TEXT,
  confidence TEXT NOT NULL CHECK (confidence IN ('authoritative', 'explicit_override', 'legacy_inferred', 'unallocated')),
  source_event_id TEXT,
  note TEXT,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_allocations_active
  ON allocation_lots(account_alias, conid, model_code, effective_at, ended_at);

CREATE TABLE IF NOT EXISTS cash_allocation_events (
  event_id TEXT PRIMARY KEY,
  account_alias TEXT NOT NULL,
  owner TEXT NOT NULL CHECK (owner IN ('drew', 'michael', 'unallocated')),
  strategy TEXT NOT NULL,
  currency TEXT NOT NULL,
  amount_decimal TEXT NOT NULL,
  event_type TEXT NOT NULL,
  effective_at TEXT NOT NULL,
  source TEXT NOT NULL,
  source_event_id TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS broker_events (
  event_key TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  account_alias TEXT NOT NULL,
  gateway_session_id TEXT,
  receive_seq INTEGER,
  source_client_id INTEGER,
  source_timestamp TEXT,
  received_at TEXT NOT NULL,
  payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS strategy_snapshots (
  source_run_id TEXT PRIMARY KEY REFERENCES source_runs(source_run_id),
  producer TEXT NOT NULL,
  as_of TEXT NOT NULL,
  complete INTEGER NOT NULL,
  payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS flex_session_versions (
  source_run_id TEXT PRIMARY KEY REFERENCES source_runs(source_run_id),
  account_alias TEXT NOT NULL,
  session_date TEXT NOT NULL,
  is_primary INTEGER NOT NULL CHECK (is_primary IN (0, 1)),
  restates_source_run_id TEXT,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_flex_primary_session
  ON flex_session_versions(account_alias, session_date) WHERE is_primary=1;

CREATE TABLE IF NOT EXISTS reconciliation_breaks (
  break_id TEXT PRIMARY KEY,
  snapshot_id TEXT NOT NULL REFERENCES account_snapshots(snapshot_id),
  account_alias TEXT NOT NULL,
  conid INTEGER,
  model_code TEXT,
  break_type TEXT NOT NULL,
  expected_decimal TEXT,
  actual_decimal TEXT,
  severity TEXT NOT NULL,
  details_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  created_at TEXT NOT NULL,
  resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS outbox (
  outbox_id TEXT PRIMARY KEY,
  topic TEXT NOT NULL,
  business_key TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  delivered_at TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  UNIQUE(topic, business_key)
);

CREATE TABLE IF NOT EXISTS order_intents (
  intent_uuid TEXT PRIMARY KEY,
  account_alias TEXT NOT NULL,
  conid INTEGER NOT NULL,
  contract_fingerprint TEXT NOT NULL,
  action TEXT NOT NULL CHECK (action IN ('BUY', 'SELL')),
  quantity_decimal TEXT NOT NULL,
  limit_price_decimal TEXT NOT NULL,
  tif TEXT NOT NULL,
  outside_rth INTEGER NOT NULL,
  reduce_only INTEGER NOT NULL,
  owner TEXT NOT NULL,
  strategy TEXT NOT NULL,
  mode TEXT NOT NULL CHECK (mode IN ('dry_run', 'paper', 'live')),
  state TEXT NOT NULL,
  approval_hash TEXT,
  approval_expires_at TEXT,
  gateway_session_id TEXT,
  client_id INTEGER,
  order_id INTEGER,
  perm_id INTEGER,
  order_ref TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS order_events (
  event_id TEXT PRIMARY KEY,
  intent_uuid TEXT NOT NULL REFERENCES order_intents(intent_uuid),
  prior_state TEXT,
  next_state TEXT NOT NULL,
  event_type TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS executions (
  account_alias TEXT NOT NULL,
  exec_id TEXT NOT NULL,
  intent_uuid TEXT,
  perm_id INTEGER,
  conid INTEGER NOT NULL,
  quantity_decimal TEXT NOT NULL,
  price_decimal TEXT NOT NULL,
  side TEXT NOT NULL,
  executed_at TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  PRIMARY KEY(account_alias, exec_id)
);

CREATE TABLE IF NOT EXISTS commissions (
  account_alias TEXT NOT NULL,
  exec_id TEXT NOT NULL,
  commission_decimal TEXT NOT NULL,
  currency TEXT NOT NULL,
  realized_pnl_decimal TEXT,
  payload_json TEXT NOT NULL,
  PRIMARY KEY(account_alias, exec_id),
  FOREIGN KEY(account_alias, exec_id) REFERENCES executions(account_alias, exec_id)
);
