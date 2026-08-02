import { failure, json, requestId, requireDatabase } from "../../../_lib/http.js";

export async function onRequestGet(context) {
  const id = requestId(context.request);
  try {
    const db = requireDatabase(context.env);
    const [latestIngest, snapshotCounts, alertCounts] = await db.batch([
      db.prepare(`
        SELECT request_id, received_at, generated_at, source, criticality_count,
               flow_count, symbols_json, status, latency_ms, payload_bytes
        FROM market_risk_ingest_runs
        ORDER BY received_at DESC
        LIMIT 1
      `),
      db.prepare(`
        SELECT
          (SELECT COUNT(*) FROM criticality_snapshots) AS criticality_count,
          (SELECT COUNT(*) FROM flow_stress_snapshots) AS flow_count,
          (SELECT MAX(as_of) FROM criticality_snapshots) AS latest_criticality_at,
          (SELECT MAX(as_of) FROM flow_stress_snapshots) AS latest_flow_at
      `),
      db.prepare(`
        SELECT
          SUM(CASE WHEN closed_at IS NULL THEN 1 ELSE 0 END) AS open_count,
          COUNT(*) AS total_count
        FROM market_risk_alerts
      `),
    ]);
    const ingest = latestIngest.results?.[0] || null;
    if (ingest?.symbols_json) {
      try { ingest.symbols = JSON.parse(ingest.symbols_json); } catch (_) { ingest.symbols = []; }
      delete ingest.symbols_json;
    }
    return json({
      status: ingest ? "operational" : "awaiting_live_ingest",
      latest_ingest: ingest,
      snapshots: snapshotCounts.results?.[0] || {},
      alerts: alertCounts.results?.[0] || {},
      research_only: true,
      request_id: id,
    }, 200, { "cache-control": "public, max-age=15, stale-while-revalidate=30" });
  } catch (error) {
    return failure(error, id);
  }
}
