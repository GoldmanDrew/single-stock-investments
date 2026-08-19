import { failure, json, requestId, requireDatabase } from "../../../../_lib/http.js";
import { requirePortfolioViewer } from "../../../../_lib/auth.js";
import { portfolioOrderOwner, requirePaperOrderRequest } from "../../../../_lib/paper-orders.js";

const PUBLIC_COLUMNS = `paper_order_id,owner,symbol,sec_type,conid,side,quantity_decimal,
  limit_price_decimal,order_type,tif,currency,rationale,mode,transmitted,status,created_at,updated_at`;

function privateHeaders() {
  return { "cache-control": "private, no-store" };
}

export async function onRequestDelete(context) {
  const requestIdValue = requestId(context.request);
  try {
    const viewer = await requirePortfolioViewer(context);
    if (!viewer) return json({ error: "Authentication required.", request_id: requestIdValue }, 401, privateHeaders());
    const owner = portfolioOrderOwner(viewer, context.env);
    if (!owner) return json({ error: "This login is not assigned to a portfolio order role.", request_id: requestIdValue }, 403, privateHeaders());
    try {
      requirePaperOrderRequest(context.request);
    } catch (error) {
      return json({ error: error.message, request_id: requestIdValue }, 403, privateHeaders());
    }

    const orderId = String(context.params?.id || "").trim();
    const db = requireDatabase(context.env);
    const existing = await db.prepare(`SELECT ${PUBLIC_COLUMNS} FROM portfolio_paper_orders
      WHERE paper_order_id=? AND owner=?`).bind(orderId, owner).first();
    if (!existing) return json({ error: "Paper order not found.", request_id: requestIdValue }, 404, privateHeaders());
    if (existing.status === "paper_cancelled") {
      return json({ schema_version: "portfolio_paper_order.v1", order: existing, request_id: requestIdValue }, 200, privateHeaders());
    }

    const now = new Date().toISOString();
    const eventId = `paper-cancelled:${orderId}`;
    await db.batch([
      db.prepare(`UPDATE portfolio_paper_orders SET status='paper_cancelled',updated_at=?
        WHERE paper_order_id=? AND owner=? AND status='paper_queued'`).bind(now, orderId, owner),
      db.prepare(`INSERT OR IGNORE INTO portfolio_paper_order_events
        (event_id,paper_order_id,owner,actor_email,event_type,payload_json,created_at)
        VALUES (?,?,?,?,?,?,?)`).bind(
        eventId, orderId, owner, viewer.email, "paper_cancelled",
        JSON.stringify({ mode: "paper", transmitted: false }), now,
      ),
    ]);
    const stored = await db.prepare(`SELECT ${PUBLIC_COLUMNS} FROM portfolio_paper_orders
      WHERE paper_order_id=? AND owner=?`).bind(orderId, owner).first();
    return json({
      schema_version: "portfolio_paper_order.v1",
      mode: "paper",
      transmitted: false,
      order: stored,
      request_id: requestIdValue,
    }, 200, privateHeaders());
  } catch (error) {
    return failure(error, requestIdValue);
  }
}
