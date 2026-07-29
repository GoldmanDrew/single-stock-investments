PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS pipeline_runs (
  run_id TEXT PRIMARY KEY,
  generated_at TEXT NOT NULL,
  source_sha256 TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('complete', 'partial', 'failed')),
  ticker_count INTEGER NOT NULL DEFAULT 0,
  summary_json TEXT NOT NULL,
  imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS securities (
  ticker TEXT PRIMARY KEY,
  company TEXT NOT NULL,
  market TEXT,
  exchange_code TEXT,
  investment_sleeve TEXT,
  stance TEXT,
  archetype TEXT,
  last_research_at TEXT,
  latest_run_id TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (latest_run_id) REFERENCES pipeline_runs(run_id)
    DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS valuation_current (
  ticker TEXT PRIMARY KEY,
  decision_status TEXT NOT NULL,
  provisional INTEGER NOT NULL DEFAULT 1 CHECK (provisional IN (0, 1)),
  method_profile TEXT,
  primary_power_zone TEXT,
  price_per_share REAL,
  value_low REAL,
  value_base REAL,
  value_high REAL,
  annualized_return_base_pct REAL,
  open_gap_count INTEGER NOT NULL DEFAULT 0,
  critical_gap_count INTEGER NOT NULL DEFAULT 0,
  next_gap_id TEXT,
  next_gap_question TEXT,
  source_as_of TEXT,
  latest_run_id TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (ticker) REFERENCES securities(ticker) ON DELETE CASCADE,
  FOREIGN KEY (latest_run_id) REFERENCES pipeline_runs(run_id)
    DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS evidence_tasks (
  ticker TEXT NOT NULL,
  task_id TEXT NOT NULL,
  priority TEXT NOT NULL,
  field_id TEXT,
  method_id TEXT,
  question TEXT,
  evidence_required TEXT,
  acceptance_test TEXT,
  collector TEXT,
  status TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 5,
  last_attempt_at TEXT,
  next_attempt_at TEXT,
  last_error TEXT,
  evidence_refs_json TEXT NOT NULL DEFAULT '[]',
  latest_run_id TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (ticker, task_id),
  FOREIGN KEY (ticker) REFERENCES securities(ticker) ON DELETE CASCADE,
  FOREIGN KEY (latest_run_id) REFERENCES pipeline_runs(run_id)
    DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS task_attempts (
  attempt_id TEXT PRIMARY KEY,
  ticker TEXT NOT NULL,
  task_id TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  collector TEXT,
  error TEXT,
  evidence_refs_json TEXT NOT NULL DEFAULT '[]',
  run_id TEXT,
  FOREIGN KEY (ticker, task_id) REFERENCES evidence_tasks(ticker, task_id) ON DELETE CASCADE,
  FOREIGN KEY (run_id) REFERENCES pipeline_runs(run_id)
);

CREATE TABLE IF NOT EXISTS source_documents (
  document_id TEXT PRIMARY KEY,
  ticker TEXT NOT NULL,
  source_type TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  source_locator TEXT,
  as_of_date TEXT,
  content_sha256 TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (ticker, source_ref, content_sha256),
  FOREIGN KEY (ticker) REFERENCES securities(ticker) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS facts (
  fact_id TEXT PRIMARY KEY,
  ticker TEXT NOT NULL,
  field_id TEXT NOT NULL,
  value_number REAL,
  value_text TEXT,
  unit TEXT,
  currency TEXT,
  as_of_date TEXT,
  confidence TEXT,
  locked INTEGER NOT NULL DEFAULT 1 CHECK (locked IN (0, 1)),
  source_document_id TEXT,
  source_locator TEXT,
  derivation_json TEXT,
  method_version TEXT,
  run_id TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (ticker) REFERENCES securities(ticker) ON DELETE CASCADE,
  FOREIGN KEY (source_document_id) REFERENCES source_documents(document_id),
  FOREIGN KEY (run_id) REFERENCES pipeline_runs(run_id)
);

CREATE TABLE IF NOT EXISTS valuation_runs (
  valuation_run_id TEXT PRIMARY KEY,
  ticker TEXT NOT NULL,
  method_id TEXT NOT NULL,
  method_version TEXT NOT NULL,
  power_zone_profile TEXT,
  as_of_date TEXT,
  status TEXT NOT NULL,
  input_hash TEXT NOT NULL,
  proof_hash TEXT,
  value_low REAL,
  value_base REAL,
  value_high REAL,
  output_unit TEXT,
  run_id TEXT,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (ticker) REFERENCES securities(ticker) ON DELETE CASCADE,
  FOREIGN KEY (run_id) REFERENCES pipeline_runs(run_id)
);

CREATE TABLE IF NOT EXISTS valuation_components (
  valuation_run_id TEXT NOT NULL,
  component_id TEXT NOT NULL,
  label TEXT,
  category TEXT,
  treatment TEXT NOT NULL,
  method_id TEXT,
  method_version TEXT,
  value_low REAL,
  value_base REAL,
  value_high REAL,
  overlap_key TEXT,
  proof_hash TEXT,
  payload_json TEXT NOT NULL,
  PRIMARY KEY (valuation_run_id, component_id),
  FOREIGN KEY (valuation_run_id) REFERENCES valuation_runs(valuation_run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_securities_market ON securities(market, ticker);
CREATE INDEX IF NOT EXISTS idx_securities_sleeve ON securities(investment_sleeve, ticker);
CREATE INDEX IF NOT EXISTS idx_valuation_status ON valuation_current(decision_status, critical_gap_count DESC, ticker);
CREATE INDEX IF NOT EXISTS idx_valuation_method ON valuation_current(method_profile, decision_status, ticker);
CREATE INDEX IF NOT EXISTS idx_tasks_status_retry ON evidence_tasks(status, next_attempt_at, priority, ticker);
CREATE INDEX IF NOT EXISTS idx_facts_lookup ON facts(ticker, field_id, as_of_date DESC);
CREATE INDEX IF NOT EXISTS idx_documents_ticker ON source_documents(ticker, as_of_date DESC);
CREATE INDEX IF NOT EXISTS idx_valuation_runs_ticker ON valuation_runs(ticker, created_at DESC);
