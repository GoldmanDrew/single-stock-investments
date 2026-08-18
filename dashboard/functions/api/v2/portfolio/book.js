import { failure, json, requestId } from "../../../_lib/http.js";
import { requirePortfolioViewer } from "../../../_lib/auth.js";
import { loadPortfolio, ownerScope } from "../../../_lib/portfolio.js";

export async function onRequestGet(context) {
  const id = requestId(context.request);
  try {
    const viewer = await requirePortfolioViewer(context);
    if (!viewer) return json({ error: "Authentication required.", request_id: id }, 401, { "cache-control": "no-store" });
    const book = await loadPortfolio(context.env, ownerScope(context.request.url));
    return json({ ...book, viewer: { email: viewer.email || null }, request_id: id }, 200, { "cache-control": "private, no-store" });
  } catch (error) {
    if (error instanceof TypeError) return json({ error: error.message, request_id: id }, 400, { "cache-control": "no-store" });
    return failure(error, id);
  }
}
