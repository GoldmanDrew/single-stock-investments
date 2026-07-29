CREATE TABLE IF NOT EXISTS ohlcv_observations (
  ticker TEXT NOT NULL,
  observed_on TEXT NOT NULL,
  adjusted_open REAL,
  adjusted_high REAL,
  adjusted_low REAL,
  adjusted_close REAL NOT NULL,
  volume REAL,
  source TEXT NOT NULL,
  imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (ticker, observed_on),
  FOREIGN KEY (ticker) REFERENCES securities(ticker) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS capitulation_snapshots (
  ticker TEXT NOT NULL,
  as_of_date TEXT NOT NULL,
  model_version TEXT NOT NULL,
  state TEXT NOT NULL,
  pressure_score REAL,
  panic_score REAL,
  exhaustion_score REAL,
  confidence_score REAL,
  price_dislocation_score REAL,
  selling_climax_score REAL,
  volatility_stress_score REAL,
  relative_path_stress_score REAL,
  data_grade TEXT,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (ticker, as_of_date, model_version),
  FOREIGN KEY (ticker) REFERENCES securities(ticker) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS market_context_snapshots (
  context_key TEXT NOT NULL,
  as_of_date TEXT NOT NULL,
  model_version TEXT NOT NULL,
  state TEXT,
  panic_score REAL,
  source TEXT,
  source_url TEXT,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (context_key, as_of_date, model_version)
);

CREATE INDEX IF NOT EXISTS idx_ohlcv_observations_ticker_date
  ON ohlcv_observations(ticker, observed_on DESC);
CREATE INDEX IF NOT EXISTS idx_capitulation_snapshots_state
  ON capitulation_snapshots(as_of_date DESC, state, panic_score DESC);
CREATE INDEX IF NOT EXISTS idx_capitulation_snapshots_ticker
  ON capitulation_snapshots(ticker, as_of_date DESC);
