export function parsePayload(row) {
  if (!row) return null;
  let payload = {};
  try {
    payload = JSON.parse(row.payload_json || "{}");
  } catch (_) {
    payload = {};
  }
  return {
    ...payload,
    symbol: row.symbol,
    scope: row.scope,
    as_of: row.as_of,
    model_version: row.model_version,
    direction: row.direction ?? payload.direction,
    score: row.criticality_score ?? payload.score,
    confidence: payload.confidence || {
      positive: row.positive_confidence,
      negative: row.negative_confidence,
      qualified: row.qualified_confidence,
    },
    critical_time: payload.critical_time || {
      unit: "trading_days_after_as_of",
      p10: row.tc_p10_days,
      median: row.tc_median_days,
      p90: row.tc_p90_days,
    },
    fit_count: row.fit_count ?? payload.fit_count,
    qualified_count: row.qualified_count ?? payload.qualified_count,
    source: row.source ?? payload.source,
    entitlement_mode: row.entitlement_mode ?? payload.entitlement_mode,
    quality_state: row.quality_state ?? payload.quality_state,
  };
}

export function parseFlow(row) {
  if (!row) return null;
  let payload = {};
  try {
    payload = JSON.parse(row.payload_json || "{}");
  } catch (_) {
    payload = {};
  }
  return {
    ...payload,
    symbol: row.symbol,
    scope: row.scope,
    as_of: row.as_of,
    model_version: row.model_version,
    state: row.state,
    scores: payload.scores || {
      pressure: row.pressure_score,
      panic: row.panic_score,
      exhaustion: row.exhaustion_score,
      liquidity: row.liquidity_score,
      breadth: row.breadth_score,
    },
    source: row.source ?? payload.source,
    entitlement_mode: row.entitlement_mode ?? payload.entitlement_mode,
    quality_state: row.quality_state ?? payload.quality_state,
  };
}

export function parseComponent(row) {
  if (!row) return null;
  let payload = {};
  try {
    payload = JSON.parse(row.payload_json || "{}");
  } catch (_) {
    payload = {};
  }
  return {
    ...payload,
    component: row.component,
    symbol: row.symbol,
    scope: row.scope,
    as_of: row.as_of,
    cadence: row.cadence,
    source: row.source,
    model_version: row.model_version,
    entitlement_mode: row.entitlement_mode,
    quality_state: row.quality_state,
    score: row.score ?? payload.score ?? null,
    value: row.value ?? payload.value ?? null,
    unit: row.unit ?? payload.unit ?? null,
  };
}

export const LATEST_CRITICALITY_SQL = `
  SELECT *
  FROM (
    SELECT c.*,
      ROW_NUMBER() OVER (
        PARTITION BY c.scope, c.symbol, c.horizon
        ORDER BY c.as_of DESC, c.created_at DESC
      ) AS row_number
    FROM criticality_snapshots c
  )
  WHERE row_number = 1
  ORDER BY
    CASE scope WHEN 'market' THEN 0 WHEN 'sector' THEN 1 ELSE 2 END,
    symbol
`;

export const LATEST_FLOW_SQL = `
  SELECT *
  FROM (
    SELECT f.*,
      ROW_NUMBER() OVER (
        PARTITION BY f.scope, f.symbol
        ORDER BY f.as_of DESC, f.created_at DESC
      ) AS row_number
    FROM flow_stress_snapshots f
  )
  WHERE row_number = 1
`;

export const LATEST_COMPONENTS_SQL = `
  SELECT *
  FROM (
    SELECT c.*,
      ROW_NUMBER() OVER (
        PARTITION BY c.component, c.scope, c.symbol
        ORDER BY c.as_of DESC, c.created_at DESC
      ) AS row_number
    FROM market_risk_component_snapshots c
  )
  WHERE row_number = 1
  ORDER BY component, scope, symbol
`;
