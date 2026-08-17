import { failure, json, requestId, requireDatabase } from "../../../_lib/http.js";
import { requirePortfolioViewer } from "../../../_lib/auth.js";

export async function onRequestGet(context) {
  const id = requestId(context.request);
  try {
    const viewer = await requirePortfolioViewer(context);
    if (!viewer) return json({ error: "Authentication required.", request_id: id }, 401, { "cache-control": "no-store" });
    const result = await requireDatabase(context.env).prepare(`SELECT r.as_of,v.tag,v.value_decimal,v.currency,v.source
      FROM portfolio_source_runs r JOIN portfolio_account_values v USING(source_run_id)
      WHERE r.source='ibkr' AND r.complete=1 AND v.tag IN ('InitMarginReq','MaintMarginReq','AvailableFunds','ExcessLiquidity','BuyingPower','Cushion')
      ORDER BY r.as_of,v.tag`).all();
    return json({ schema_version: "portfolio_margin.v1", value_kind: "broker_reported", rows: result.results || [], request_id: id }, 200, { "cache-control": "private, no-store" });
  } catch (error) { return failure(error, id); }
}
