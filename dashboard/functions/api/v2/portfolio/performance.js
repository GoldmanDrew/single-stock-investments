import { failure, json, requestId, requireDatabase } from "../../../_lib/http.js";
import { requirePortfolioViewer } from "../../../_lib/auth.js";
import { ownerScope } from "../../../_lib/portfolio.js";

export async function onRequestGet(context) {
  const id = requestId(context.request);
  try {
    const viewer = await requirePortfolioViewer(context);
    if (!viewer) return json({ error: "Authentication required.", request_id: id }, 401, { "cache-control": "no-store" });
    const owner = ownerScope(context.request.url);
    const db = requireDatabase(context.env);
    const result = await db.prepare(`SELECT r.as_of,v.value_decimal AS nav_decimal,v.currency
      FROM portfolio_source_runs r JOIN portfolio_account_values v USING(source_run_id)
      WHERE r.source='ibkr' AND r.complete=1 AND v.tag='NetLiquidation'
      ORDER BY r.as_of`).all();
    const flex = await db.prepare("SELECT session_date,is_primary,restates_source_run_id FROM portfolio_flex_sessions ORDER BY session_date,source_run_id").all();
    const nav = result.results || [];
    let peak = null; let maxDrawdown = 0;
    const series = nav.map((row) => {
      const value = Number(row.nav_decimal);
      peak = peak == null ? value : Math.max(peak, value);
      const drawdown = peak > 0 ? value / peak - 1 : null;
      if (drawdown != null) maxDrawdown = Math.min(maxDrawdown, drawdown);
      return { ...row, drawdown };
    });
    return json({
      schema_version: "portfolio_performance.v1", scope: owner,
      nav_series: owner === "all" ? series : [], max_drawdown: owner === "all" && series.length ? maxDrawdown : null,
      twr: null,
      null_reason: owner === "all" ? "external cash-flow coverage is not complete" : "owner NAV requires complete allocation and cash history",
      pnl_series: { intraday: "ibkr_pnl", completed_session: "flex_immutable", restatements: "separate" },
      completed_sessions: flex.results || [],
      benchmark: {
        symbol: "SPY",
        series: [],
        null_reason: "benchmark series is withheld until a complete cash-flow-aware NAV history exists",
      },
      lineage: {
        nav: { source: "IBKR account summary", tag: "NetLiquidation", value_kind: "broker_reported" },
        sessions: { source: "IBKR Flex EOD", value_kind: "completed_session" },
        twr: { source: null, null_reason: owner === "all" ? "external cash-flow coverage is not complete" : "owner NAV requires complete allocation and cash history" },
        benchmark: { source: null, symbol: "SPY", null_reason: "benchmark series has not been published" },
      },
      request_id: id,
    }, 200, { "cache-control": "private, no-store" });
  } catch (error) { return failure(error, id); }
}
