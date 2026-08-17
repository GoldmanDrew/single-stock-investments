import { failure, json, requestId, requireDatabase } from "../../../_lib/http.js";
import { requirePortfolioViewer } from "../../../_lib/auth.js";

export async function onRequestGet(context) {
  const id = requestId(context.request);
  try {
    const viewer = await requirePortfolioViewer(context);
    if (!viewer) return json({ error: "Authentication required.", request_id: id }, 401, { "cache-control": "no-store" });
    const db = requireDatabase(context.env);
    const [events, broker] = await db.batch([
      db.prepare("SELECT * FROM portfolio_order_events ORDER BY created_at DESC LIMIT 250"),
      db.prepare(`SELECT o.* FROM portfolio_broker_orders o JOIN portfolio_source_runs r USING(source_run_id)
        WHERE r.source='ibkr' AND r.complete=1 AND r.as_of=(SELECT MAX(as_of) FROM portfolio_source_runs WHERE source='ibkr' AND complete=1)
        ORDER BY o.symbol,o.order_id`),
    ]);
    return json({ schema_version: "order_events.v1", command_plane: "python_private_only", events: events.results || [], broker_open_orders: broker.results || [], request_id: id }, 200, { "cache-control": "private, no-store" });
  } catch (error) { return failure(error, id); }
}
