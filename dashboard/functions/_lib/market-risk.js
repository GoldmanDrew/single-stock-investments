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
  SELECT c.*
  FROM market_risk_latest_refs latest
  JOIN criticality_snapshots c
    ON c.scope = latest.scope
   AND c.symbol = latest.symbol
   AND c.horizon = latest.qualifier
   AND c.as_of = latest.as_of
   AND c.model_version = latest.model_version
  WHERE latest.series = 'criticality'
  ORDER BY
    CASE c.scope WHEN 'market' THEN 0 WHEN 'sector' THEN 1 ELSE 2 END,
    c.symbol
`;

export const LATEST_FLOW_SQL = `
  SELECT f.*
  FROM market_risk_latest_refs latest
  JOIN flow_stress_snapshots f
    ON f.scope = latest.scope
   AND f.symbol = latest.symbol
   AND f.as_of = latest.as_of
   AND f.model_version = latest.model_version
  WHERE latest.series = 'flow'
`;

export const LATEST_COMPONENTS_SQL = `
  SELECT c.*
  FROM market_risk_latest_refs latest
  JOIN market_risk_component_snapshots c
    ON c.component = latest.qualifier
   AND c.scope = latest.scope
   AND c.symbol = latest.symbol
   AND c.as_of = latest.as_of
   AND c.source = latest.source
   AND c.model_version = latest.model_version
  WHERE latest.series = 'component'
  ORDER BY c.component, c.scope, c.symbol
`;
