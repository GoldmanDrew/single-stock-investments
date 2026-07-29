import {
  boundedLimit,
  failure,
  json,
  requestId,
  requireDatabase,
} from "../../_lib/http.js";

const ALLOWED_STATUSES = new Set(["decision_grade", "evidence_blocked", "insufficient_data"]);

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
      filters.push("v.decision_status = ?");
      bindings.push(status);
    }
    const market = url.searchParams.get("market")?.trim().toUpperCase();
    if (market) {
      filters.push("s.market = ?");
      bindings.push(market);
    }
    const method = url.searchParams.get("method")?.trim();
    if (method) {
      filters.push("v.method_profile = ?");
      bindings.push(method);
    }
    const search = url.searchParams.get("q")?.trim();
    if (search) {
      filters.push("(s.ticker LIKE ? OR s.company LIKE ?)");
      const pattern = `%${search}%`;
      bindings.push(pattern, pattern);
    }
    const after = url.searchParams.get("after")?.trim().toUpperCase();
    if (after) {
      filters.push("s.ticker > ?");
      bindings.push(after);
    }

    const where = filters.length ? `WHERE ${filters.join(" AND ")}` : "";
    const statement = db.prepare(`
      SELECT
        s.ticker, s.company, s.market, s.exchange_code, s.investment_sleeve,
        s.stance, s.archetype, s.last_research_at,
        v.decision_status, v.provisional, v.method_profile, v.primary_power_zone,
        v.price_per_share, v.value_low, v.value_base, v.value_high,
        v.annualized_return_base_pct, v.open_gap_count, v.critical_gap_count,
        v.next_gap_id, v.next_gap_question, v.source_as_of, v.updated_at
      FROM securities s
      JOIN valuation_current v ON v.ticker = s.ticker
      ${where}
      ORDER BY s.ticker
      LIMIT ?
    `).bind(...bindings, limit);
    const result = await statement.all();
    const rows = result.results ?? [];
    return json({
      items: rows,
      count: rows.length,
      next_after: rows.length === limit ? rows.at(-1).ticker : null,
      request_id: id,
    });
  } catch (error) {
    return failure(error, id);
  }
}
