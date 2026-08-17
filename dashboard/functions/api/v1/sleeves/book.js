import { failure, json, requestId, requireDatabase } from "../../../_lib/http.js";
import { privateJson, requirePortfolioViewer } from "../../../_lib/auth.js";
import { loadBook } from "../../../_lib/sleeves.js";

export async function onRequestGet(context) {
  const id = requestId(context.request);
  const viewer = await requirePortfolioViewer(context);
  if (!viewer) return privateJson({ error: "Unauthorized.", request_id: id }, 401);
  const owner = new URL(context.request.url).searchParams.get("owner") || "drew";
  if (!["drew", "michael"].includes(owner)) {
    return json({ error: "owner must be drew or michael", request_id: id }, 400);
  }
  try {
    const db = requireDatabase(context.env);
    const book = await loadBook(db, owner);
    return json({ ...book, request_id: id }, 200, { "cache-control": "no-store" });
  } catch (error) {
    return failure(error, id);
  }
}
