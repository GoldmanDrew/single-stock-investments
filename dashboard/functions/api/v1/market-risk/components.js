import { failure, json, requestId, requireDatabase } from "../../../_lib/http.js";
import {
  LATEST_COMPONENTS_SQL,
  parseComponent,
} from "../../../_lib/market-risk.js";

export async function onRequestGet(context) {
  const id = requestId(context.request);
  try {
    const url = new URL(context.request.url);
    const component = String(url.searchParams.get("component") || "").trim();
    const scope = String(url.searchParams.get("scope") || "").trim();
    const db = requireDatabase(context.env);
    const result = await db.prepare(LATEST_COMPONENTS_SQL).all();
    const items = (result.results || []).map(parseComponent).filter((item) => (
      (!component || item.component === component) && (!scope || item.scope === scope)
    ));
    return json({
      schema_version: 1,
      research_only: true,
      generated_at: items.map((item) => item.as_of).filter(Boolean).sort().at(-1) || null,
      items,
      request_id: id,
    }, 200, { "cache-control": "public, max-age=15, stale-while-revalidate=30" });
  } catch (error) {
    return failure(error, id);
  }
}
