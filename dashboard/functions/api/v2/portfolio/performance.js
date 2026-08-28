import { failure, json, requestId, requireDatabase } from "../../../_lib/http.js";
import { requirePortfolioViewer } from "../../../_lib/auth.js";
import { ownerScope } from "../../../_lib/portfolio.js";
import { ROLLING_WINDOWS, dailyCloses, rollingStats } from "../../../_lib/performance.js";

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
    const daily = dailyCloses(series);
    const windows = ROLLING_WINDOWS.map((window) => rollingStats(daily, window));
    return json({
      schema_version: "portfolio_performance.v1", scope: owner,
      nav_series: owner === "all" ? series : [], max_drawdown: owner === "all" && series.length ? maxDrawdown : null,
      twr: null,
      // Rolling performance. Every window is returned whether or not it has the
      // history to be computed, each carrying its own reason -- a window that is
      // simply missing reads as an oversight, while one that says "needs 359 more
      // days" tells you when to look again.
      rolling: owner === "all" ? windows : ROLLING_WINDOWS.map((window) => ({
        label: window.label, years: window.years, available: false,
        null_reason: "owner NAV requires complete allocation and cash history",
      })),
      nav_daily_observations: daily.length,
      nav_first_at: daily.length ? daily[0].date : null,
      nav_last_at: daily.length ? daily[daily.length - 1].date : null,
      null_reason: owner === "all" ? "external cash-flow coverage is not complete" : "owner NAV requires complete allocation and cash history",
      pnl_series: { intraday: "ibkr_pnl", completed_session: "flex_immutable", restatements: "separate" },
      completed_sessions: flex.results || [],
      // No benchmark. Comparing this book to an index was never the question
      // being asked of it, and a withheld SPY series occupied the panel that
      // rolling own-performance should have.
      lineage: {
        nav: { source: "IBKR account summary", tag: "NetLiquidation", value_kind: "broker_reported" },
        sessions: { source: "IBKR Flex EOD", value_kind: "completed_session" },
        twr: { source: null, null_reason: owner === "all" ? "external cash-flow coverage is not complete" : "owner NAV requires complete allocation and cash history" },
        rolling: {
          source: "IBKR account summary",
          tag: "NetLiquidation",
          value_kind: "broker_reported",
          basis: "last complete observation per calendar day",
          note: "NAV is broker-reported and not cash-flow adjusted, so these are NAV growth rates, not investor returns.",
        },
      },
      request_id: id,
    }, 200, { "cache-control": "private, no-store" });
  } catch (error) { return failure(error, id); }
}
