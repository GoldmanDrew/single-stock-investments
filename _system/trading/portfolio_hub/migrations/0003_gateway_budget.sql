-- Durable Gateway connection budget.
--
-- The budget was correct and completely volatile: `ConnectionBudget` kept its
-- attempts in a list on the instance, keyed to `time.monotonic`, so every
-- process restart reset the hourly cap, the daily cap and the circuit breaker
-- at once. Combined with a `Restart=` line whose start-limit keys were sitting
-- in the wrong systemd section and being ignored, the three brakes that exist
-- specifically to stop a reconnect storm could all be cleared by the very event
-- a reconnect storm consists of.
--
-- That is the collector's failure wearing a different coat: each part
-- defensible, the composition not. So the ledger holds the count.

-- One row per connection *attempt*, charged before the socket is opened.
-- Attempts, not sessions: concurrency was what the old rule measured and it
-- stayed at one the whole time the collector was doing damage.
CREATE TABLE IF NOT EXISTS gateway_connection_attempts (
  attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
  attempted_at REAL NOT NULL,        -- unix epoch seconds; wall clock, so it survives a restart
  attempted_at_iso TEXT NOT NULL,    -- the same instant, for receipts a human reads
  purpose TEXT                       -- which ticket caused it, when the caller knows
);

CREATE INDEX IF NOT EXISTS idx_gateway_attempts_at
  ON gateway_connection_attempts(attempted_at);

-- The breaker is a single row. It must survive a restart for the same reason
-- the counts must: a wedged Gateway that trips the breaker and then kills the
-- process would otherwise come back re-armed and try again immediately.
CREATE TABLE IF NOT EXISTS gateway_breaker_state (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  consecutive_failures INTEGER NOT NULL DEFAULT 0,
  tripped_until REAL,                -- unix epoch seconds, or NULL when closed
  updated_at TEXT NOT NULL
);

INSERT OR IGNORE INTO gateway_breaker_state(id, consecutive_failures, tripped_until, updated_at)
VALUES (1, 0, NULL, '1970-01-01T00:00:00Z');
