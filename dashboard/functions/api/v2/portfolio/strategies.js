import { failure, json, requestId, requireDatabase } from "../../../_lib/http.js";
import { requirePortfolioViewer } from "../../../_lib/auth.js";

const PRODUCERS = new Set(["spx_0dte", "ls_risk", "ls_bucket5_live", "ls_bucket5_product"]);

export async function onRequestGet(context) {
  const id = requestId(context.request);
  try {
    const viewer = await requirePortfolioViewer(context);
    if (!viewer) return json({ error: "Authentication required.", request_id: id }, 401, { "cache-control": "no-store" });
    const producer = new URL(context.request.url).searchParams.get("producer") || "ls_risk";
    if (!PRODUCERS.has(producer)) return json({ error: "Invalid producer.", request_id: id }, 400, { "cache-control": "no-store" });
    const row = await requireDatabase(context.env).prepare(`SELECT s.payload_json,r.as_of,r.complete,r.source_run_id
      FROM portfolio_strategy_snapshots s JOIN portfolio_source_runs r USING(source_run_id)
      WHERE s.producer=? ORDER BY r.as_of DESC LIMIT 1`).bind(producer).first();
    if (!row) return json({ schema_version: "strategy_read_model.v1", status: "unknown", producer, rows: [], request_id: id }, 200, { "cache-control": "private, no-store" });
    return json({ ...JSON.parse(row.payload_json), status: row.complete ? "complete" : "incomplete", request_id: id }, 200, { "cache-control": "private, no-store" });
  } catch (error) { return failure(error, id); }
}
