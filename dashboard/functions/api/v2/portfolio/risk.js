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
      return { conid: row.conid, symbol: row.symbol, market_value: (number(row.market_value_decimal) || 0) * factor, factor };
    });
    const gross = positions.reduce((sum, row) => sum + Math.abs(row.market_value), 0);
    const net = positions.reduce((sum, row) => sum + row.market_value, 0);
    const concentration = [...positions].sort((a, b) => Math.abs(b.market_value) - Math.abs(a.market_value)).slice(0, 20).map((row) => ({ ...row, gross_weight: gross ? Math.abs(row.market_value) / gross : null }));
    const strategyResult = await requireDatabase(context.env).prepare(`SELECT s.payload_json FROM portfolio_strategy_snapshots s
      JOIN portfolio_source_runs r USING(source_run_id)
      WHERE r.complete=1 AND r.as_of=(SELECT MAX(r2.as_of) FROM portfolio_source_runs r2 WHERE r2.source=r.source AND r2.complete=1)`).all();
    const allowed = new Map(positions.map((row) => [Number(row.conid), row.factor]));
    const linear = { beta_exposure: 0, delta_exposure: 0, delta: 0, gamma: 0, vega: 0 };
    let atomicRows = 0; let linkedRows = 0;
    for (const stored of strategyResult.results || []) {
      const payload = JSON.parse(stored.payload_json);
      for (const row of payload.rows || []) {
        atomicRows += 1;
        if (!row.conid || !allowed.has(Number(row.conid))) continue;
        linkedRows += 1;
        const factor = allowed.get(Number(row.conid));
        for (const key of Object.keys(linear)) linear[key] += (number(row.metrics?.[key]) || 0) * factor;
      }
    }
    return json({
      schema_version: "portfolio_risk.v1", scope: owner, gross_exposure: gross, net_exposure: net,
      concentration, linear_sensitivities: linear,
      coverage: { broker_positions: positions.length, producer_atomic_rows: atomicRows, linked_atomic_rows: linkedRows },
      nonlinear: { supported: owner === "all", value: null, null_reason: "scenario vectors have not been published at this scope" },
      request_id: id,
    }, 200, { "cache-control": "private, no-store" });
  } catch (error) { return failure(error, id); }
}
