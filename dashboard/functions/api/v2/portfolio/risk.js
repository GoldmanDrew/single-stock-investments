import { failure, json, requestId, requireDatabase } from "../../../_lib/http.js";
import { requirePortfolioViewer } from "../../../_lib/auth.js";
import { loadPortfolio, ownerScope } from "../../../_lib/portfolio.js";

function number(value) { const result = Number(value); return Number.isFinite(result) ? result : null; }

export async function onRequestGet(context) {
  const id = requestId(context.request);
  try {
    const viewer = await requirePortfolioViewer(context);
    if (!viewer) return json({ error: "Authentication required.", request_id: id }, 401, { "cache-control": "no-store" });
    const owner = ownerScope(context.request.url);
    const book = await loadPortfolio(context.env, owner);
    const positions = (book.positions || []).map((row) => {
      const brokerQty = number(row.quantity_decimal) || 0;
      const scopeQty = owner === "all" ? brokerQty : (row.allocations || []).reduce((sum, allocation) => sum + (number(allocation.quantity_decimal) || 0), 0);
      const factor = brokerQty ? scopeQty / brokerQty : 0;
      return {
        conid: row.conid,
        symbol: row.local_symbol || row.symbol,
        sec_type: row.sec_type,
        quantity: scopeQty,
        quantity_unit: ["OPT", "FOP"].includes(String(row.sec_type || "").toUpperCase()) ? "contracts" : "shares",
        market_value: (number(row.market_value_decimal) || 0) * factor,
        factor,
      };
    });
    const gross = positions.reduce((sum, row) => sum + Math.abs(row.market_value), 0);
    const net = positions.reduce((sum, row) => sum + row.market_value, 0);
    const concentration = [...positions].sort((a, b) => Math.abs(b.market_value) - Math.abs(a.market_value)).slice(0, 20).map((row) => ({ ...row, gross_weight: gross ? Math.abs(row.market_value) / gross : null }));
    const strategyResult = await requireDatabase(context.env).prepare(`SELECT s.payload_json FROM portfolio_strategy_snapshots s
      JOIN portfolio_source_runs r USING(source_run_id)
      WHERE r.complete=1 AND r.as_of=(SELECT MAX(r2.as_of) FROM portfolio_source_runs r2 WHERE r2.source=r.source AND r2.complete=1)`).all();
    const payloads = (strategyResult.results || []).map((stored) => JSON.parse(stored.payload_json));
    const allowed = new Map(positions.map((row) => [Number(row.conid), row.factor]));
    const linear = { beta_exposure: 0, delta_exposure: 0, delta: 0, gamma: 0, vega: 0 };
    let atomicRows = 0; let linkedRows = 0;
    for (const payload of payloads) {
      for (const row of payload.rows || []) {
        atomicRows += 1;
        if (!row.conid || !allowed.has(Number(row.conid))) continue;
        linkedRows += 1;
        const factor = allowed.get(Number(row.conid));
        for (const key of Object.keys(linear)) linear[key] += (number(row.metrics?.[key]) || 0) * factor;
      }
    }
    const lsPayload = payloads.find((payload) => payload.producer === "ls_risk");
    const slideRisk = lsPayload?.summary?.slide_risk || {};
    const scenarios = owner === "all" && slideRisk.available
      ? (slideRisk.indices || []).flatMap((index) => (index.shock_rows || []).map((shock) => {
        const horizon = (shock.horizons || []).find((item) => item.horizon_key === "T+0") || {};
        return {
          scenario_id: `${String(index.key || index.index || "market").toLowerCase()}:${shock.shock_pct}`,
          scenario: shock.label || `${index.index} shock`,
          strategy: "LS Algo",
          factor: index.index || index.key,
          shock_value: shock.shock_pct,
          shock_unit: "percent",
          horizon: "T+0",
          pnl_usd: horizon.total_pnl_usd ?? shock.pnl_usd ?? null,
          pnl_pct_nav: horizon.total_pnl_pct_nav ?? shock.pnl_pct_nav ?? null,
          margin_delta_usd: null,
          post_shock_excess_liquidity_usd: null,
          top_contributor: shock.top_loss?.underlying || null,
          model_version: slideRisk.model || null,
          value_kind: "producer_model_estimate",
        };
      })) : [];
    return json({
      schema_version: "portfolio_risk.v1", scope: owner, gross_exposure: gross, net_exposure: net,
      concentration, linear_sensitivities: linear,
      factors: owner === "all" ? payloads.flatMap((payload) => {
        return (payload.rows || []).filter((row) => row.metrics && (row.metrics.beta_exposure != null || row.metrics.delta_exposure != null)).map((row) => ({
          row_id: row.row_id, symbol: row.symbol, producer: payload.producer, bucket: row.bucket,
          reconciliation_role: row.reconciliation_role, exposure_basis: row.exposure_basis,
          beta_exposure: row.metrics.beta_exposure ?? null, delta_exposure: row.metrics.delta_exposure ?? null,
          supported_scopes: payload.supported_scopes || ["account"],
        }));
      }) : [],
      scenarios,
      coverage: { broker_positions: positions.length, producer_atomic_rows: atomicRows, linked_atomic_rows: linkedRows },
      nonlinear: {
        supported: scenarios.length > 0,
        value: scenarios.length || null,
        null_reason: scenarios.length ? null : owner === "all"
          ? "No producer scenario surface has been published at this scope."
          : "Nonlinear metrics are not pro-rated across owners.",
      },
      shock_coverage: {
        market_slide: scenarios.length ? "LS Algo producer model" : "unavailable",
        margin: "requires IBKR what-if or a published strategy margin model",
        correlation: lsPayload?.summary?.correlation_shock?.available
          ? "LS Algo producer model"
          : "correlation-lift surface is not yet present in the sanitized snapshot",
      },
      lineage: {
        exposures: { source: "IBKR positions", value_kind: "broker_reported", as_of: book?.snapshot?.as_of || null },
        factors: { source: "strategy_snapshot.v1", value_kind: "model_estimate" },
        scenarios: scenarios.length
          ? { source: "LS Algo slide_risk_panel", value_kind: "producer_model_estimate", supported_scopes: ["account", "strategy"] }
          : { source: null, null_reason: "scenario vectors have not been published" },
      },
      request_id: id,
    }, 200, { "cache-control": "private, no-store" });
  } catch (error) { return failure(error, id); }
}
