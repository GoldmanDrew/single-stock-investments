import { failure, json, requestId, requireDatabase } from "../../_lib/http.js";

export async function onRequestGet(context) {
  const id = requestId(context.request);
  try {
    const db = requireDatabase(context.env);
    const [valuation, tasks, pipeline] = await db.batch([
      db.prepare(`
        SELECT
          COUNT(*) AS ticker_count,
          SUM(CASE WHEN decision_status = 'decision_grade' THEN 1 ELSE 0 END) AS decision_grade_count,
          SUM(CASE WHEN decision_status = 'evidence_blocked' THEN 1 ELSE 0 END) AS evidence_blocked_count,
          SUM(CASE WHEN provisional = 1 THEN 1 ELSE 0 END) AS provisional_count,
          SUM(critical_gap_count) AS critical_gap_count
        FROM valuation_current
      `),
      db.prepare(`
        SELECT
          SUM(CASE WHEN status IN ('pending_collection', 'retry_pending', 'retry_scheduled') THEN 1 ELSE 0 END) AS actionable_count,
          SUM(CASE WHEN status = 'unavailable' THEN 1 ELSE 0 END) AS unavailable_count,
          SUM(CASE
            WHEN status IN ('pending_collection', 'retry_pending', 'retry_scheduled')
              AND (next_attempt_at IS NULL OR next_attempt_at <= CURRENT_TIMESTAMP)
            THEN 1 ELSE 0 END
          ) AS due_count
        FROM evidence_tasks
      `),
      db.prepare(`
        SELECT run_id, generated_at, source_sha256, status, ticker_count, imported_at
        FROM pipeline_runs
        ORDER BY generated_at DESC
        LIMIT 1
      `),
    ]);
    return json({
      valuation: valuation.results?.[0] ?? {},
      evidence_tasks: tasks.results?.[0] ?? {},
      latest_pipeline: pipeline.results?.[0] ?? null,
      request_id: id,
    });
  } catch (error) {
    return failure(error, id);
  }
}
