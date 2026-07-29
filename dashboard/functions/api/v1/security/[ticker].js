import { failure, json, requestId, requireDatabase } from "../../../_lib/http.js";

export async function onRequestGet(context) {
  const id = requestId(context.request);
  try {
    const db = requireDatabase(context.env);
    const ticker = String(context.params.ticker ?? "").trim().toUpperCase();
    if (!/^[A-Z0-9._-]{1,24}$/.test(ticker)) {
      return json({ error: "Invalid ticker.", request_id: id }, 400);
    }
    const [security, tasks, valuations] = await db.batch([
      db.prepare(`
        SELECT s.*, v.*
        FROM securities s
        JOIN valuation_current v ON v.ticker = s.ticker
        WHERE s.ticker = ?
      `).bind(ticker),
      db.prepare(`
        SELECT task_id, priority, field_id, method_id, question, evidence_required,
          acceptance_test, collector, status, attempts, max_attempts,
          last_attempt_at, next_attempt_at, last_error, evidence_refs_json, updated_at
        FROM evidence_tasks
        WHERE ticker = ?
        ORDER BY
          CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 ELSE 2 END,
          COALESCE(next_attempt_at, ''),
          task_id
      `).bind(ticker),
      db.prepare(`
        SELECT valuation_run_id, method_id, method_version, power_zone_profile,
          as_of_date, status, value_low, value_base, value_high, output_unit,
          proof_hash, created_at
        FROM valuation_runs
        WHERE ticker = ?
        ORDER BY created_at DESC
        LIMIT 20
      `).bind(ticker),
    ]);
    const record = security.results?.[0];
    if (!record) {
      return json({ error: "Ticker not found.", request_id: id }, 404);
    }
    return json({
      security: record,
      evidence_tasks: tasks.results ?? [],
      valuation_runs: valuations.results ?? [],
      request_id: id,
    });
  } catch (error) {
    return failure(error, id);
  }
}
