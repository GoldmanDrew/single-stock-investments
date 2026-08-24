-- Contract resolution, option tickets, and the lease the command channel was
-- missing.
--
-- Three things land together because none of them is useful alone: an option
-- ticket needs a conId no human can type, resolving that conId needs a request
-- the hub can pull, and pulling anything needs the claim/publish half of the
-- channel that command_poller.py has always called and that never existed.
--
-- The direction of trust is unchanged. Every table here is a *request* the
-- browser writes and an *answer* the hub writes back. Nothing in this file lets
-- an edge session reach IB Gateway.

-- 1. The claim lease -------------------------------------------------------
--
-- There is exactly one transmitter by design (client 91), so contention is not
-- expected; the lease exists so that a bridge which dies mid-draft releases its
-- work instead of stranding a ticket in `drafting` forever. Re-claiming is safe
-- because the hub ledger, not this table, is the serialisation point for
-- anything that transmits: GuardedOrderService.submit() refuses a second call
-- on an intent that is no longer Approved.
ALTER TABLE portfolio_order_requests ADD COLUMN claimed_at TEXT;
ALTER TABLE portfolio_order_requests ADD COLUMN claimed_by TEXT;

-- 2. Option contract identity ---------------------------------------------
--
-- `portfolio_order_requests` carried conid and sec_type only. That is enough to
-- place a stock order and not enough to *show a human what they are approving*:
-- a fingerprint of "272093|STK||SMART" names nothing a person can check. An
-- option ticket has to read "XSP 270129P00540000 - 100x - SMART/USD" before the
-- approval means anything, so the qualified contract's identity is stored
-- alongside the request and the fingerprint is built from it.
ALTER TABLE portfolio_order_requests ADD COLUMN expiry TEXT;          -- YYYYMMDD
ALTER TABLE portfolio_order_requests ADD COLUMN strike_decimal TEXT;
ALTER TABLE portfolio_order_requests ADD COLUMN right_code TEXT;      -- P | C
ALTER TABLE portfolio_order_requests ADD COLUMN multiplier_decimal TEXT;
ALTER TABLE portfolio_order_requests ADD COLUMN trading_class TEXT;
ALTER TABLE portfolio_order_requests ADD COLUMN exchange TEXT;
ALTER TABLE portfolio_order_requests ADD COLUMN local_symbol TEXT;

-- 3. Contract lookups ------------------------------------------------------
--
-- A conId is a broker fact. The browser may ask what a symbol resolves to; only
-- the hub may answer, because only the hub may talk to IBKR. Same pull-only
-- shape as the order channel: the row is a question with a state, and the hub
-- decides what the answer is.
--
-- Resolution costs no market-data line. reqContractDetails and
-- reqSecDefOptParams come from a different pool than reqMktData, so this path
-- cannot starve the SPX option NBBO stream the way a streaming subscription
-- could (CLAUDE.md rule 4).
CREATE TABLE IF NOT EXISTS portfolio_contract_lookups (
  lookup_id TEXT PRIMARY KEY,
  account_alias TEXT NOT NULL,
  owner TEXT NOT NULL,                  -- fixed by the Access login, never client-supplied
  kind TEXT NOT NULL,                   -- 'contract' | 'option_chain' | 'option_contract'
  symbol TEXT NOT NULL,
  sec_type TEXT NOT NULL,
  currency TEXT,
  exchange TEXT,
  expiry TEXT,
  strike_decimal TEXT,
  right_code TEXT,

  state TEXT NOT NULL DEFAULT 'requested',  -- requested | resolving | resolved | failed
  matches_json TEXT,                    -- hub-published, and the only source of conIds
  error TEXT,
  claimed_at TEXT,
  claimed_by TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_contract_lookups_state
  ON portfolio_contract_lookups(state, created_at);
CREATE INDEX IF NOT EXISTS idx_contract_lookups_owner
  ON portfolio_contract_lookups(owner, created_at DESC);

-- 4. The contract cache ----------------------------------------------------
--
-- Everything the hub has ever resolved or held, so the symbol box can offer a
-- conId without asking IBKR at all. This is what makes the field usable on a
-- weekend: `ibc.service` is a session service that is legitimately down outside
-- market days (CLAUDE.md rule 8), so a lookup that requires the Gateway returns
-- nothing then, while the cache still answers.
--
-- Deliberately never expired. A conId is stable for the life of the contract,
-- and an expired option that lingers here is harmless -- the hub re-qualifies
-- every contract at preview time regardless of what this table said.
CREATE TABLE IF NOT EXISTS portfolio_contracts (
  conid INTEGER PRIMARY KEY,
  symbol TEXT NOT NULL,
  local_symbol TEXT,
  sec_type TEXT NOT NULL,
  currency TEXT,
  exchange TEXT,
  primary_exchange TEXT,
  trading_class TEXT,
  expiry TEXT,
  strike_decimal TEXT,
  right_code TEXT,
  multiplier_decimal TEXT,
  description TEXT,
  source TEXT NOT NULL,                 -- 'position' | 'lookup'
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_portfolio_contracts_symbol
  ON portfolio_contracts(symbol, sec_type);
CREATE INDEX IF NOT EXISTS idx_portfolio_contracts_local
  ON portfolio_contracts(local_symbol);
