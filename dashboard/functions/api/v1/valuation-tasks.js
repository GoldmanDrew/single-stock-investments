import {
  boundedLimit,
  failure,
  json,
  requestId,
  requireDatabase,
} from "../../_lib/http.js";

const ALLOWED_STATUSES = new Set([
  "pending_collection",
  "retry_pending",
  "retry_scheduled",
  "evidence_ready",
  "unavailable",
  "closed",
]);

export async function onRequestGet(context) {
  const id = requestId(context.request);
  try {
    const db = requireDatabase(context.env);
    const url = new URL(context.request.url);
    const limit = boundedLimit(url.searchParams.get("limit"));
    const filters = [];
    const bindings = [];

    const status = url.searchParams.get("status");
    if (status && ALLOWED_STATUSES.has(status)) {
      filters.push("t.status = ?");
      bindings.push(status);
    } else {
      filters.push("t.status IN ('pending_collection', 'retry_pending', 'retry_scheduled')");
    }
    if (url.searchParams.get("due") !== "false") {
      filters.push("(t.next_attempt_at IS NULL OR t.next_attempt_at <= CURRENT_TIMESTAMP)");
    }
    const ticker = url.searchParams.get("ticker")?.trim().toUpperCase();
    if (ticker) {
      filters.push("t.ticker = ?");
      bindings.push(ticker);
    }
    const collector = url.searchParams.get("collector")?.trim();
    if (collector) {
      filters.push("t.collector = ?");
      bindings.push(collector);
    }

    const result = await db.prepare(`
      SELECT
        t.ticker, s.company, t.task_id, t.priority, t.field_id, t.method_id,
        t.question, t.evidence_required, t.acceptance_test, t.collector,
        t.status, t.attempts, t.max_attempts, t.last_attempt_at,
        t.next_attempt_at, t.last_error, t.updated_at
      FROM evidence_tasks t
      JOIN securities s ON s.ticker = t.ticker
      WHERE ${filters.join(" AND ")}
      ORDER BY
        CASE t.priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 ELSE 2 END,
        COALESCE(t.next_attempt_at, ''),
        t.attempts,
        t.ticker,
        t.task_id
      LIMIT ?
    `).bind(...bindings, limit).all();

    return json({
      items: result.results ?? [],
      count: result.results?.length ?? 0,
      request_id: id,
    });
  } catch (error) {
    return failure(error, id);
  }
}
