import { boundedLimit, failure, json, requestId, requireDatabase } from "../../../_lib/http.js";

export async function onRequestGet(context) {
  const id = requestId(context.request);
  try {
    const db = requireDatabase(context.env);
    const url = new URL(context.request.url);
    const limit = boundedLimit(url.searchParams.get("limit"), 50, 250);
    const openOnly = url.searchParams.get("open") !== "false";
    const result = await db.prepare(`
      SELECT alert_id, scope, symbol, opened_at, updated_at, closed_at,
             state, severity, model_version, reason_codes_json, payload_json
      FROM market_risk_alerts
      WHERE (? = 0 OR closed_at IS NULL)
      ORDER BY
        CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
        updated_at DESC
      LIMIT ?
    `).bind(openOnly ? 1 : 0, limit).all();
    const items = (result.results || []).map((row) => {
      let reasons = [];
      let payload = {};
      try { reasons = JSON.parse(row.reason_codes_json || "[]"); } catch (_) { reasons = []; }
      try { payload = JSON.parse(row.payload_json || "{}"); } catch (_) { payload = {}; }
      return { ...row, reason_codes: reasons, payload };
    });
    return json({ items, count: items.length, open_only: openOnly, request_id: id });
  } catch (error) {
    return failure(error, id);
  }
}
