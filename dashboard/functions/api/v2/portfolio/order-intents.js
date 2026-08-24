// Order command channel, edge half.
//
// GET  - the owner's recent tickets, for rendering the order desk.
// POST - record a *request* for an order. This never reaches IBKR. The hub on
//        the Ubuntu box polls, previews against the live book, and is the only
//        process that can transmit.
//
// The signed hub-facing routes (claim / publish preview / report status) live in
// ingest.js alongside the other HMAC endpoints, so this file has no path that a
// browser session could use to move a ticket toward the broker.

import { failure, json, requestId, requireDatabase } from "../../../_lib/http.js";
import { requirePortfolioViewer } from "../../../_lib/auth.js";
import { portfolioOrderOwner } from "../../../_lib/paper-orders.js";
import { validateOrderRequest } from "../../../_lib/order-requests.js";

const PUBLIC_COLUMNS = `request_id,owner,strategy,conid,symbol,sec_type,action,quantity_decimal,
  limit_price_decimal,currency,tif,outside_rth,mode,rationale,state,intent_uuid,contract_fingerprint,
  preview_json,preview_as_of,approval_expires_at,reject_reason,approved_at,approved_by,
  broker_status,order_ref,client_id,order_id,perm_id,created_at,updated_at,
  expiry,strike_decimal,right_code,multiplier_decimal,trading_class,exchange,local_symbol`;

const privateHeaders = () => ({ "cache-control": "private, no-store" });

function uuid() {
  return crypto.randomUUID();
}

export async function onRequestGet(context) {
  const id = requestId(context.request);
  try {
    const viewer = await requirePortfolioViewer(context);
    if (!viewer) return json({ error: "Authentication required.", request_id: id }, 401, privateHeaders());
    const owner = portfolioOrderOwner(viewer, context.env);
    const db = requireDatabase(context.env);
    const rows = owner
      ? await db.prepare(`SELECT ${PUBLIC_COLUMNS} FROM portfolio_order_requests
          WHERE owner=? ORDER BY created_at DESC LIMIT 100`).bind(owner).all()
      : { results: [] };
    return json({
      schema_version: "portfolio_order_requests.v1",
      command_plane: "python_private_only",
      viewer: { email: viewer?.email || null, order_owner: owner, can_request_orders: Boolean(owner) },
      // Live transmission also requires the hub's own interlock; the edge never
      // knows or controls that, and must not imply otherwise in the UI.
      requests: rows.results || [],
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
    const body = await context.request.json().catch(() => null);
    if (!body) return json({ error: "A JSON body is required.", request_id: id }, 400, privateHeaders());

    let ticket;
    try {
      ticket = validateOrderRequest(body, owner);
    } catch (error) {
      return json({ error: error.message, request_id: id }, 400, privateHeaders());
    }

    const db = requireDatabase(context.env);
    const run = await db.prepare(`SELECT account_alias FROM portfolio_source_runs
      WHERE source='ibkr' AND complete=1 ORDER BY as_of DESC LIMIT 1`).first();
    if (!run) {
      // Without a complete snapshot there is no book to price or size against.
      return json({ error: "No complete broker snapshot; order entry is closed.", request_id: id }, 409, privateHeaders());
    }

    const now = new Date().toISOString();
    const requestKey = uuid();
    // The option identity rides with the request so the ticket can be *read*.
    // It is not the source of truth for what gets sent: the hub re-qualifies the
    // conId at preview and builds the fingerprint from what IBKR returns, so a
    // browser that lied about the strike would produce a fingerprint that does
    // not match what it displayed, and the approval would not bind.
    await db.prepare(`INSERT INTO portfolio_order_requests
      (request_id,account_alias,owner,strategy,conid,symbol,sec_type,action,quantity_decimal,
       limit_price_decimal,currency,tif,outside_rth,mode,rationale,expiry,strike_decimal,right_code,
       multiplier_decimal,trading_class,exchange,local_symbol,state,created_at,updated_at)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'requested',?,?)`).bind(
      requestKey, run.account_alias, ticket.owner, ticket.strategy, ticket.conid, ticket.symbol,
      ticket.sec_type, ticket.action, ticket.quantity, ticket.limit_price, ticket.currency,
      ticket.tif, ticket.outside_rth ? 1 : 0, ticket.mode, ticket.rationale,
      ticket.expiry, ticket.strike, ticket.right, ticket.multiplier,
      ticket.trading_class, ticket.exchange, ticket.local_symbol, now, now,
    ).run();

    return json({
      schema_version: "portfolio_order_requests.v1",
      request_id_created: requestKey,
      state: "requested",
      transmitted: false,
      note: "Recorded for the private hub. Nothing has been sent to the broker.",
      request_id: id,
    }, 201, privateHeaders());
  } catch (error) {
    return failure(error, id);
  }
}
