import { failure, json, requestId, requireDatabase } from "../../../_lib/http.js";
import { requirePortfolioViewer } from "../../../_lib/auth.js";
import {
  portfolioOrderOwner,
  requirePaperOrderRequest,
  validatePaperOrder,
} from "../../../_lib/paper-orders.js";

const PUBLIC_COLUMNS = `paper_order_id,owner,symbol,sec_type,conid,side,quantity_decimal,
  limit_price_decimal,order_type,tif,currency,rationale,mode,transmitted,status,created_at,updated_at`;

function privateHeaders() {
  return { "cache-control": "private, no-store" };
}

function viewerPayload(viewer, owner) {
  return {
    email: viewer?.email || null,
    order_owner: owner,
    can_queue_paper_orders: Boolean(owner),
  };
}

function sameTicket(row, ticket) {
  return row
    && row.owner === ticket.owner
    && row.symbol === ticket.symbol
    && row.sec_type === ticket.sec_type
    && Number(row.conid) === Number(ticket.conid)
    && row.side === ticket.side
    && String(row.quantity_decimal) === ticket.quantity_decimal
    && String(row.limit_price_decimal) === ticket.limit_price_decimal
    && row.order_type === ticket.order_type
    && row.tif === ticket.tif
    && String(row.rationale || "") === ticket.rationale;
}

export async function onRequestGet(context) {
  const id = requestId(context.request);
  try {
    const viewer = await requirePortfolioViewer(context);
    if (!viewer) return json({ error: "Authentication required.", request_id: id }, 401, privateHeaders());
    const owner = portfolioOrderOwner(viewer, context.env);
    const db = requireDatabase(context.env);
    const rows = owner
      ? await db.prepare(`SELECT ${PUBLIC_COLUMNS} FROM portfolio_paper_orders
          WHERE owner=? ORDER BY created_at DESC LIMIT 250`).bind(owner).all()
      : { results: [] };
    return json({
      schema_version: "portfolio_paper_orders.v1",
      mode: "paper",
      transmitted: false,
      viewer: viewerPayload(viewer, owner),
      orders: rows.results || [],
      request_id: id,
    }, 200, privateHeaders());
  } catch (error) {
    return failure(error, id);
  }
}

export async function onRequestPost(context) {
  const id = requestId(context.request);
  try {
    const viewer = await requirePortfolioViewer(context);
    if (!viewer) return json({ error: "Authentication required.", request_id: id }, 401, privateHeaders());
    const owner = portfolioOrderOwner(viewer, context.env);
    if (!owner) return json({ error: "This login is not assigned to a portfolio order role.", request_id: id }, 403, privateHeaders());

    try {
      requirePaperOrderRequest(context.request);
    } catch (error) {
      return json({ error: error.message, request_id: id }, 403, privateHeaders());
    }

    let payload;
    try {
      payload = await context.request.json();
    } catch (_) {
      return json({ error: "Paper order body must be valid JSON.", request_id: id }, 400, privateHeaders());
    }
    if (payload?.owner != null && String(payload.owner).trim().toLowerCase() !== owner) {
      return json({ error: `This login can only queue orders for the ${owner} portfolio.`, request_id: id }, 403, privateHeaders());
    }

    let ticket;
    try {
      ticket = validatePaperOrder(payload, owner);
    } catch (error) {
      return json({ error: error.message, request_id: id }, 422, privateHeaders());
    }

    const db = requireDatabase(context.env);
    const now = new Date().toISOString();
    const eventId = `paper-queued:${ticket.client_request_id}`;
    const eventPayload = JSON.stringify({
      symbol: ticket.symbol,
      sec_type: ticket.sec_type,
      conid: ticket.conid,
      side: ticket.side,
      quantity_decimal: ticket.quantity_decimal,
      limit_price_decimal: ticket.limit_price_decimal,
      order_type: ticket.order_type,
      tif: ticket.tif,
      mode: "paper",
      transmitted: false,
    });
    const results = await db.batch([
      db.prepare(`INSERT OR IGNORE INTO portfolio_paper_orders
        (paper_order_id,owner,actor_email,actor_subject,symbol,sec_type,conid,side,quantity_decimal,
         limit_price_decimal,order_type,tif,currency,rationale,mode,transmitted,status,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`).bind(
        ticket.client_request_id, owner, viewer.email, viewer.subject || null, ticket.symbol, ticket.sec_type,
        ticket.conid, ticket.side, ticket.quantity_decimal, ticket.limit_price_decimal, ticket.order_type,
        ticket.tif, ticket.currency, ticket.rationale, "paper", 0, "paper_queued", now, now,
      ),
      db.prepare(`INSERT OR IGNORE INTO portfolio_paper_order_events
        (event_id,paper_order_id,owner,actor_email,event_type,payload_json,created_at)
        VALUES (?,?,?,?,?,?,?)`).bind(
        eventId, ticket.client_request_id, owner, viewer.email, "paper_queued", eventPayload, now,
      ),
    ]);
    const stored = await db.prepare(`SELECT ${PUBLIC_COLUMNS} FROM portfolio_paper_orders
      WHERE paper_order_id=? AND owner=?`).bind(ticket.client_request_id, owner).first();
    if (!stored) return json({ error: "Paper order ID conflicts with another ticket.", request_id: id }, 409, privateHeaders());
    if (!sameTicket(stored, ticket)) {
      return json({ error: "Paper order ID was already used for a different ticket.", request_id: id }, 409, privateHeaders());
    }
    const created = Number(results?.[0]?.meta?.changes || 0) > 0;
    return json({
      schema_version: "portfolio_paper_order.v1",
      mode: "paper",
      transmitted: false,
      viewer: viewerPayload(viewer, owner),
      order: stored,
      request_id: id,
    }, created ? 201 : 200, privateHeaders());
  } catch (error) {
    return failure(error, id);
  }
}
