// The human approval step.
//
// This records that a person confirmed one exact contract inside the hub's
// approval window. It does not authorise transmission by itself: the hub
// re-checks its own HMAC token, the fingerprint, the clock, the live interlock
// and the kill switch before anything reaches IBKR. Approving here is necessary,
// never sufficient.

import { failure, json, requestId, requireDatabase } from "../../../../../_lib/http.js";
import { requirePortfolioViewer } from "../../../../../_lib/auth.js";
import { portfolioOrderOwner } from "../../../../../_lib/paper-orders.js";
import { validateApproval } from "../../../../../_lib/order-requests.js";

const privateHeaders = () => ({ "cache-control": "private, no-store" });

export async function onRequestPost(context) {
  const id = requestId(context.request);
  try {
    const viewer = await requirePortfolioViewer(context);
    if (!viewer) return json({ error: "Authentication required.", request_id: id }, 401, privateHeaders());
    const owner = portfolioOrderOwner(viewer, context.env);
    if (!owner) return json({ error: "This login is not mapped to a portfolio owner.", request_id: id }, 403, privateHeaders());

    const body = await context.request.json().catch(() => null);
    const key = context.params.request;
    const db = requireDatabase(context.env);
    const row = await db.prepare(
      "SELECT * FROM portfolio_order_requests WHERE request_id=? AND owner=?",
    ).bind(key, owner).first();

    let approval;
    try {
      approval = validateApproval(row, body, viewer.email);
    } catch (error) {
      return json({ error: error.message, request_id: id }, 409, privateHeaders());
    }

    const now = new Date().toISOString();
    // Guard the transition in SQL as well as in code: two tabs approving the same
    // previewed ticket must produce one approval, not two.
    const result = await db.prepare(`UPDATE portfolio_order_requests
      SET state='approved', approved_at=?, approved_by=?, approved_fingerprint=?, updated_at=?
      WHERE request_id=? AND owner=? AND state='previewed'`).bind(
      now, approval.approved_by, approval.approved_fingerprint, now, key, owner,
    ).run();

    if (!result.meta?.changes) {
      return json({ error: "The order was no longer awaiting approval.", request_id: id }, 409, privateHeaders());
    }
    return json({
      schema_version: "portfolio_order_requests.v1",
      request_id_approved: key,
      state: "approved",
      transmitted: false,
      note: "Approval recorded. The private hub still re-verifies its own token, the live interlock and the kill switch before transmitting.",
      request_id: id,
    }, 200, privateHeaders());
  } catch (error) {
    return failure(error, id);
  }
}
