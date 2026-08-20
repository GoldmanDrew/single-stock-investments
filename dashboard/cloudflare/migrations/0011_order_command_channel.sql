-- Order command channel.
--
-- The browser never commands the hub. It writes a *request* here and reads the
-- hub's answer back; the hub on the Ubuntu box polls this table, makes every
-- decision locally, and is the only process that can transmit to IBKR. That
-- keeps /api/v2/portfolio/orders.js's stated boundary intact
-- (command_plane = python_private_only) while still letting a human drive.
--
-- Nothing in this table is an instruction. A row is a request with a state; the
-- hub decides whether it becomes an order.

CREATE TABLE IF NOT EXISTS portfolio_order_requests (
  request_id TEXT PRIMARY KEY,
  account_alias TEXT NOT NULL,
  owner TEXT NOT NULL,                  -- fixed by the Access login, never client-supplied
  strategy TEXT NOT NULL,
  conid INTEGER NOT NULL,
  symbol TEXT NOT NULL,
  sec_type TEXT NOT NULL,
  action TEXT NOT NULL,                 -- BUY | SELL
  quantity_decimal TEXT NOT NULL,
  limit_price_decimal TEXT NOT NULL,
  currency TEXT,
  tif TEXT NOT NULL DEFAULT 'DAY',
  outside_rth INTEGER NOT NULL DEFAULT 0,
  mode TEXT NOT NULL DEFAULT 'dry_run', -- dry_run | paper | live
  rationale TEXT,

  -- Lifecycle as seen from the edge. The authoritative state machine lives in
  -- the hub ledger; this mirrors just enough for the UI to render a ticket.
  state TEXT NOT NULL DEFAULT 'requested',
  intent_uuid TEXT,                     -- assigned by the hub once it drafts
  contract_fingerprint TEXT,            -- echoed back for the human to confirm

  -- Hub-published preview: live NBBO, real whatIf margin, and the approval clock.
  preview_json TEXT,
  preview_as_of TEXT,
  approval_expires_at TEXT,
  reject_reason TEXT,

  -- Human approval. The HMAC token never leaves the hub; this only records that
  -- a human confirmed the exact contract inside the window.
  approved_at TEXT,
  approved_by TEXT,
  approved_fingerprint TEXT,

  broker_status TEXT,
  order_ref TEXT,
  client_id INTEGER,
  order_id INTEGER,
  perm_id INTEGER,

  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

-- The hub polls for work by state; the UI reads one owner's recent tickets.
CREATE INDEX IF NOT EXISTS idx_order_requests_state ON portfolio_order_requests(state, created_at);
CREATE INDEX IF NOT EXISTS idx_order_requests_owner ON portfolio_order_requests(owner, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_order_requests_intent ON portfolio_order_requests(intent_uuid)
  WHERE intent_uuid IS NOT NULL;
