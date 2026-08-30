-- Contract v3 separates intrinsic value today from dated forward returns and
-- records underwriting maturity explicitly.  annualized_return_base_pct is
-- retained as a compatibility alias; exporters populate it only from the
-- canonical forward return.
ALTER TABLE valuation_current ADD COLUMN model_level TEXT;
ALTER TABLE valuation_current ADD COLUMN output_basis TEXT;
ALTER TABLE valuation_current ADD COLUMN present_value_base REAL;
ALTER TABLE valuation_current ADD COLUMN margin_of_safety_base_pct REAL;
ALTER TABLE valuation_current ADD COLUMN forward_return_base_pct REAL;
ALTER TABLE valuation_current ADD COLUMN required_return_pct REAL;
ALTER TABLE valuation_current ADD COLUMN return_publishable INTEGER NOT NULL DEFAULT 0
  CHECK (return_publishable IN (0, 1));
ALTER TABLE valuation_current ADD COLUMN valuation_tier INTEGER
  CHECK (valuation_tier IS NULL OR valuation_tier IN (1, 2, 3));
ALTER TABLE valuation_current ADD COLUMN model_as_of TEXT;
ALTER TABLE valuation_current ADD COLUMN latest_fact_as_of TEXT;
ALTER TABLE valuation_current ADD COLUMN price_as_of TEXT;

CREATE INDEX IF NOT EXISTS idx_valuation_model_level
  ON valuation_current(model_level, decision_status, ticker);
CREATE INDEX IF NOT EXISTS idx_valuation_tier
  ON valuation_current(valuation_tier, model_level, ticker);
