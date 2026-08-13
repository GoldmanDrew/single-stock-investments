PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sleeve_ingest_nonces (
  nonce TEXT PRIMARY KEY,
  received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sleeve_config (
  owner TEXT PRIMARY KEY CHECK (owner IN ('drew', 'michael')),
  equity_usd REAL,
  extra_margin_usd REAL NOT NULL DEFAULT 0,
  as_of TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sleeve_ideas (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  owner TEXT NOT NULL CHECK (owner IN ('drew', 'michael')),
  ticker TEXT NOT NULL,
  side TEXT,
  status TEXT,
  cluster TEXT,
  conviction INTEGER,
  plc_score INTEGER,
  plc_thesis TEXT,
  holding_period_years REAL,
  entry_price REAL,
  shares REAL,
  cost_usd REAL,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (owner, ticker)
);

CREATE TABLE IF NOT EXISTS sleeve_notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  owner TEXT NOT NULL CHECK (owner IN ('drew', 'michael')),
  ticker TEXT NOT NULL,
  note_date TEXT NOT NULL,
  body TEXT NOT NULL,
  entry_price REAL,
  shares REAL,
  cost_usd REAL,
  conviction INTEGER,
  plc_score INTEGER,
  plc_thesis TEXT,
  holding_period_years REAL,
  cluster TEXT,
  author TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sleeve_orders (
  proposal_id TEXT PRIMARY KEY,
  owner TEXT NOT NULL CHECK (owner IN ('drew', 'michael')),
  ticker TEXT NOT NULL,
  side TEXT NOT NULL,
  qty REAL NOT NULL,
  limit_price REAL NOT NULL,
  status TEXT NOT NULL,
  dry_run INTEGER NOT NULL DEFAULT 1,
  ib_order_id TEXT,
  submitted_at TEXT
);

CREATE TABLE IF NOT EXISTS sleeve_fills (
  fill_id TEXT PRIMARY KEY,
  proposal_id TEXT,
  owner TEXT NOT NULL CHECK (owner IN ('drew', 'michael')),
  ticker TEXT NOT NULL,
  qty REAL NOT NULL,
  price REAL NOT NULL,
  commission REAL,
  filled_at TEXT NOT NULL,
  source TEXT NOT NULL,
  FOREIGN KEY (proposal_id) REFERENCES sleeve_orders(proposal_id)
);

CREATE TABLE IF NOT EXISTS sleeve_positions (
  owner TEXT NOT NULL CHECK (owner IN ('drew', 'michael')),
  ticker TEXT NOT NULL,
  qty REAL NOT NULL,
  mark REAL,
  market_value REAL,
  sec_type TEXT,
  classifier_reason TEXT,
  synced_at TEXT NOT NULL,
  PRIMARY KEY (owner, ticker)
);

CREATE TABLE IF NOT EXISTS sleeve_marks (
  owner TEXT NOT NULL CHECK (owner IN ('drew', 'michael')),
  as_of TEXT NOT NULL,
  ticker TEXT NOT NULL,
  last REAL,
  source TEXT,
  PRIMARY KEY (owner, as_of, ticker)
);

CREATE TABLE IF NOT EXISTS sleeve_cashflows (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  owner TEXT NOT NULL CHECK (owner IN ('drew', 'michael')),
  date TEXT NOT NULL,
  ticker TEXT,
  amount REAL NOT NULL,
  kind TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sleeve_classifier_audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  as_of TEXT NOT NULL,
  ticker TEXT NOT NULL,
  bucket TEXT NOT NULL,
  reason TEXT,
  owner TEXT
);

INSERT OR IGNORE INTO sleeve_config (owner, equity_usd, extra_margin_usd, as_of, payload_json)
VALUES
  ('drew', 100000, 100000, '2026-08-13', '{"blurb":"Drew sleeve starts at $100k plus extra margin."}'),
  ('michael', NULL, 0, '2026-08-13', '{"blurb":"Long-term residual book; SPX 0DTE and systematic LETFs excluded; blacklist families included."}');
