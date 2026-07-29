CREATE TABLE IF NOT EXISTS price_observations (
  ticker TEXT NOT NULL,
  observed_on TEXT NOT NULL,
  adjusted_close REAL NOT NULL,
  volume REAL,
  source TEXT NOT NULL,
  imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (ticker, observed_on),
  FOREIGN KEY (ticker) REFERENCES securities(ticker) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS technical_snapshots (
  ticker TEXT NOT NULL,
  as_of_date TEXT NOT NULL,
  model_version TEXT NOT NULL,
  benchmark TEXT,
  data_quality TEXT NOT NULL,
  trend_z REAL,
  stretch_z REAL,
  relative_strength_z REAL,
  volume_surprise_z REAL,
  volatility_regime_z REAL,
  drawdown_z REAL,
  trend_regime TEXT,
  stretch_regime TEXT,
  setup_regime TEXT,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (ticker, as_of_date, model_version),
  FOREIGN KEY (ticker) REFERENCES securities(ticker) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_price_observations_ticker_date
  ON price_observations(ticker, observed_on DESC);
CREATE INDEX IF NOT EXISTS idx_technical_snapshots_setup
  ON technical_snapshots(as_of_date DESC, setup_regime, trend_z DESC);
CREATE INDEX IF NOT EXISTS idx_technical_snapshots_ticker
  ON technical_snapshots(ticker, as_of_date DESC);
