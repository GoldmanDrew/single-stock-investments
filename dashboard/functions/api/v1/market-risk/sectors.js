import { failure, json, requestId, requireDatabase } from "../../../_lib/http.js";
import {
  LATEST_CRITICALITY_SQL,
  LATEST_FLOW_SQL,
  parseFlow,
  parsePayload,
} from "../../../_lib/market-risk.js";

export async function onRequestGet(context) {
  const id = requestId(context.request);
  try {
    const db = requireDatabase(context.env);
    const [criticalityResult, flowResult] = await db.batch([
      db.prepare(LATEST_CRITICALITY_SQL),
      db.prepare(LATEST_FLOW_SQL),
    ]);
    const flowBySymbol = Object.fromEntries(
      (flowResult.results || []).map((row) => [row.symbol, parseFlow(row)]),
    );
    const items = (criticalityResult.results || [])
      .map(parsePayload)
      .filter((item) => item.scope === "sector")
      .map((item) => ({ ...item, flow: flowBySymbol[item.symbol] || null }));
    return json({ items, count: items.length, research_only: true, request_id: id });
  } catch (error) {
    return failure(error, id);
  }
}
