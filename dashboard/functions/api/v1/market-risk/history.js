import {
  boundedLimit,
  failure,
  json,
  requestId,
  requireDatabase,
} from "../../../_lib/http.js";
import { parseFlow, parsePayload } from "../../../_lib/market-risk.js";

const SYMBOL_RE = /^[A-Z0-9.^_-]{1,16}$/;

export async function onRequestGet(context) {
  const id = requestId(context.request);
  try {
    const db = requireDatabase(context.env);
    const url = new URL(context.request.url);
    const symbol = String(url.searchParams.get("symbol") || "SPY").trim().toUpperCase();
    if (!SYMBOL_RE.test(symbol)) {
      return json({ error: "Invalid symbol.", request_id: id }, 400);
    }
    const limit = boundedLimit(url.searchParams.get("limit"), 90, 500);
    const [criticalityResult, flowResult] = await db.batch([
      db.prepare(`
        SELECT * FROM criticality_snapshots
        WHERE symbol = ?
        ORDER BY as_of DESC, created_at DESC
        LIMIT ?
      `).bind(symbol, limit),
      db.prepare(`
        SELECT * FROM flow_stress_snapshots
        WHERE symbol = ?
        ORDER BY as_of DESC, created_at DESC
        LIMIT ?
      `).bind(symbol, limit),
    ]);
    const criticality = (criticalityResult.results || []).map(parsePayload);
    const flow = (flowResult.results || []).map(parseFlow);
    return json({
      symbol,
      criticality,
      flow,
      count: { criticality: criticality.length, flow: flow.length },
      research_only: true,
      request_id: id,
    });
  } catch (error) {
    return failure(error, id);
  }
}
