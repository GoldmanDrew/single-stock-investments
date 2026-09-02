import { failure, json, requestId, requireDatabase } from "../../../_lib/http.js";
import { requirePortfolioViewer } from "../../../_lib/auth.js";

export async function onRequestGet(context) {
  const id = requestId(context.request);
  try {
    const viewer = await requirePortfolioViewer(context);
    if (!viewer) return json({ error: "Authentication required.", request_id: id }, 401, { "cache-control": "no-store" });
    const result = await requireDatabase(context.env).prepare(`WITH latest AS (
        SELECT source_run_id FROM portfolio_source_runs
        WHERE source='ibkr' AND complete=1 ORDER BY as_of DESC LIMIT 1
      )
      SELECT r.as_of,v.tag,v.value_decimal,v.currency,v.source
      FROM latest
      JOIN portfolio_source_runs r USING(source_run_id)
      JOIN portfolio_account_values v USING(source_run_id)
      WHERE v.tag IN ('InitMarginReq','MaintMarginReq','AvailableFunds','ExcessLiquidity','BuyingPower','Cushion')
      ORDER BY v.tag`).all();
    return json({ schema_version: "portfolio_margin.v1", value_kind: "broker_reported", rows: result.results || [], request_id: id }, 200, { "cache-control": "private, no-store" });
  } catch (error) { return failure(error, id); }
}
