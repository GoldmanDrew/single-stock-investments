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
    const criticality = (criticalityResult.results || []).map(parsePayload);
    const flowBySymbol = Object.fromEntries(
      (flowResult.results || []).map((row) => [row.symbol, parseFlow(row)]),
    );
    const items = criticality.map((item) => ({
      ...item,
      flow: flowBySymbol[item.symbol] || null,
    }));
    return json({
      schema_version: 1,
      research_only: true,
      generated_at: items
        .map((item) => item.as_of)
        .filter(Boolean)
        .sort()
        .at(-1) || null,
      by_symbol: Object.fromEntries(items.map((item) => [item.symbol, item])),
      market: items.filter((item) => item.scope === "market"),
      sectors: items.filter((item) => item.scope === "sector"),
      request_id: id,
    });
  } catch (error) {
    return failure(error, id);
  }
}
