import { failure, json, requestId, requireDatabase } from "../../../_lib/http.js";
import { requirePortfolioViewer } from "../../../_lib/auth.js";

export async function onRequestGet(context) {
  const id = requestId(context.request);
  try {
    const viewer = await requirePortfolioViewer(context);
    if (!viewer) return json({ error: "Authentication required.", request_id: id }, 401, { "cache-control": "no-store" });
    const db = requireDatabase(context.env);
    const [broker, strategies, breaks] = await db.batch([
      db.prepare("SELECT source_run_id,as_of,complete,received_at FROM portfolio_source_runs WHERE source='ibkr' ORDER BY as_of DESC LIMIT 1"),
      db.prepare("SELECT source,MAX(as_of) AS as_of,MAX(received_at) AS received_at FROM portfolio_source_runs WHERE source!='ibkr' GROUP BY source"),
      db.prepare("SELECT severity,COUNT(*) AS count FROM portfolio_reconciliation_breaks WHERE status='open' GROUP BY severity"),
    ]);
    return json({ schema_version: "portfolio_health.v1", broker: broker.results?.[0] || null, strategies: strategies.results || [], open_breaks: breaks.results || [], generated_at: new Date().toISOString(), request_id: id }, 200, { "cache-control": "private, no-store" });
  } catch (error) { return failure(error, id); }
}
