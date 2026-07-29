CREATE TABLE IF NOT EXISTS market_structure_snapshots (
  ticker TEXT NOT NULL,
  as_of_date TEXT NOT NULL,
  float_shares REAL,
  shares_outstanding REAL,
  float_percent_outstanding REAL,
  short_interest_shares REAL,
  short_percent_float REAL,
  short_change_pct REAL,
  days_to_cover REAL,
  source TEXT,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (ticker, as_of_date),
  FOREIGN KEY (ticker) REFERENCES securities(ticker) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_market_structure_short_float
  ON market_structure_snapshots(as_of_date DESC, short_percent_float DESC);
CREATE INDEX IF NOT EXISTS idx_market_structure_ticker
  ON market_structure_snapshots(ticker, as_of_date DESC);
