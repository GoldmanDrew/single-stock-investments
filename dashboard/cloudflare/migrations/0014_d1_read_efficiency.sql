-- Bound the rows read by the dashboard's hot paths.
--
-- D1 bills rows scanned, not rows returned. The portfolio and market-risk
-- routes historically asked for one current row by ranking the complete
-- history table, which exhausted the free-tier read allowance after the
-- high-frequency feeds became active.

CREATE INDEX IF NOT EXISTS idx_portfolio_source_latest
  ON portfolio_source_runs(source, complete, as_of DESC, received_at DESC);
CREATE INDEX IF NOT EXISTS idx_portfolio_account_value_tag_run
  ON portfolio_account_values(tag, source_run_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_breaks_run_status
  ON portfolio_reconciliation_breaks(source_run_id, status, severity);
CREATE INDEX IF NOT EXISTS idx_portfolio_strategy_producer
  ON portfolio_strategy_snapshots(producer, source_run_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_order_events_created
  ON portfolio_order_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_market_risk_alert_scope_open
  ON market_risk_alerts(scope, symbol, closed_at, opened_at DESC);

-- One pointer per logical risk series lets current-state routes read only the
-- handful of rows they return while the bounded history tables remain
-- available to /history. qualifier is horizon for criticality, component for
-- components, and the empty string for flow.
CREATE TABLE IF NOT EXISTS market_risk_latest_refs (
  series TEXT NOT NULL CHECK (series IN ('criticality', 'flow', 'component')),
  scope TEXT NOT NULL,
  symbol TEXT NOT NULL,
  qualifier TEXT NOT NULL DEFAULT '',
  as_of TEXT NOT NULL,
  model_version TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (series, scope, symbol, qualifier)
);

INSERT INTO market_risk_latest_refs
  (series, scope, symbol, qualifier, as_of, model_version, source)
SELECT 'criticality', scope, symbol, horizon, as_of, model_version, ''
FROM (
  SELECT scope, symbol, horizon, as_of, model_version,
         ROW_NUMBER() OVER (
           PARTITION BY scope, symbol, horizon
           ORDER BY as_of DESC, created_at DESC, model_version DESC
         ) AS row_number
  FROM criticality_snapshots
)
WHERE row_number = 1
ON CONFLICT (series, scope, symbol, qualifier) DO UPDATE SET
  as_of=excluded.as_of,
  model_version=excluded.model_version,
  source=excluded.source;

INSERT INTO market_risk_latest_refs
  (series, scope, symbol, qualifier, as_of, model_version, source)
SELECT 'flow', scope, symbol, '', as_of, model_version, ''
FROM (
  SELECT scope, symbol, as_of, model_version,
         ROW_NUMBER() OVER (
           PARTITION BY scope, symbol
           ORDER BY as_of DESC, created_at DESC, model_version DESC
         ) AS row_number
  FROM flow_stress_snapshots
)
WHERE row_number = 1
ON CONFLICT (series, scope, symbol, qualifier) DO UPDATE SET
  as_of=excluded.as_of,
  model_version=excluded.model_version,
  source=excluded.source;

INSERT INTO market_risk_latest_refs
  (series, scope, symbol, qualifier, as_of, model_version, source)
SELECT 'component', scope, symbol, component, as_of, model_version, source
FROM (
  SELECT component, scope, symbol, as_of, model_version, source,
         ROW_NUMBER() OVER (
           PARTITION BY component, scope, symbol
           ORDER BY as_of DESC, created_at DESC, model_version DESC, source DESC
         ) AS row_number
  FROM market_risk_component_snapshots
)
WHERE row_number = 1
ON CONFLICT (series, scope, symbol, qualifier) DO UPDATE SET
  as_of=excluded.as_of,
  model_version=excluded.model_version,
  source=excluded.source;

CREATE TRIGGER IF NOT EXISTS trg_criticality_latest_ref
AFTER INSERT ON criticality_snapshots
BEGIN
  INSERT INTO market_risk_latest_refs
    (series, scope, symbol, qualifier, as_of, model_version, source)
  VALUES ('criticality', NEW.scope, NEW.symbol, NEW.horizon, NEW.as_of, NEW.model_version, '')
  ON CONFLICT (series, scope, symbol, qualifier) DO UPDATE SET
    as_of=excluded.as_of,
    model_version=excluded.model_version,
    source=excluded.source
  WHERE excluded.as_of >= market_risk_latest_refs.as_of;
END;

CREATE TRIGGER IF NOT EXISTS trg_flow_latest_ref
AFTER INSERT ON flow_stress_snapshots
BEGIN
  INSERT INTO market_risk_latest_refs
    (series, scope, symbol, qualifier, as_of, model_version, source)
  VALUES ('flow', NEW.scope, NEW.symbol, '', NEW.as_of, NEW.model_version, '')
  ON CONFLICT (series, scope, symbol, qualifier) DO UPDATE SET
    as_of=excluded.as_of,
    model_version=excluded.model_version,
    source=excluded.source
  WHERE excluded.as_of >= market_risk_latest_refs.as_of;
END;

CREATE TRIGGER IF NOT EXISTS trg_component_latest_ref
AFTER INSERT ON market_risk_component_snapshots
BEGIN
  INSERT INTO market_risk_latest_refs
    (series, scope, symbol, qualifier, as_of, model_version, source)
  VALUES ('component', NEW.scope, NEW.symbol, NEW.component, NEW.as_of, NEW.model_version, NEW.source)
  ON CONFLICT (series, scope, symbol, qualifier) DO UPDATE SET
    as_of=excluded.as_of,
    model_version=excluded.model_version,
    source=excluded.source
  WHERE excluded.as_of >= market_risk_latest_refs.as_of;
END;

PRAGMA optimize;
