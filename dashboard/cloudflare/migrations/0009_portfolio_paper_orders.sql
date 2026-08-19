CREATE TABLE IF NOT EXISTS portfolio_paper_orders (
  paper_order_id TEXT PRIMARY KEY,
  owner TEXT NOT NULL CHECK (owner IN ('drew', 'michael')),
  actor_email TEXT NOT NULL,
  actor_subject TEXT,
  symbol TEXT NOT NULL,
  sec_type TEXT NOT NULL CHECK (sec_type IN ('STK', 'ETF', 'OPT', 'WAR')),
  conid INTEGER,
  side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
  quantity_decimal TEXT NOT NULL,
  limit_price_decimal TEXT NOT NULL,
  order_type TEXT NOT NULL CHECK (order_type = 'LMT'),
  tif TEXT NOT NULL CHECK (tif = 'DAY'),
  currency TEXT NOT NULL CHECK (currency = 'USD'),
  rationale TEXT NOT NULL DEFAULT '',
  mode TEXT NOT NULL CHECK (mode = 'paper'),
  transmitted INTEGER NOT NULL CHECK (transmitted = 0),
  status TEXT NOT NULL CHECK (status IN ('paper_queued', 'paper_cancelled')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_portfolio_paper_orders_owner_created
  ON portfolio_paper_orders(owner, created_at DESC);

CREATE TABLE IF NOT EXISTS portfolio_paper_order_events (
  event_id TEXT PRIMARY KEY,
  paper_order_id TEXT NOT NULL REFERENCES portfolio_paper_orders(paper_order_id),
  owner TEXT NOT NULL CHECK (owner IN ('drew', 'michael')),
  actor_email TEXT NOT NULL,
  event_type TEXT NOT NULL CHECK (event_type IN ('paper_queued', 'paper_cancelled')),
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_portfolio_paper_order_events_order_created
  ON portfolio_paper_order_events(paper_order_id, created_at);
