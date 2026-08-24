// Hub-facing: record what the bridge decided about one ticket.
//
// The hub owns every transition except two. A human approves (via
// order-intents/<id>/approve) and a human cancels; everything else -- drafting,
// the priced preview, submitting, the broker's own status -- is published here
// by the process that actually did it.
//
// This route is trusted with a lot, so it is deliberately narrow about one
// thing: it cannot write `approved`. If a compromised hub token could stamp a
// ticket approved, the human confirmation step would be decorative. Approval
// has to arrive from a browser session that passed Access, and the hub then
// re-verifies it against the HMAC token it never published.

import { failure, json, requestId, requireDatabase } from "../../../../../_lib/http.js";
import { reserveNonce, verifyPortfolioHmac } from "../../../../../_lib/portfolio.js";

// Everything the hub is allowed to say a ticket has become. `requested` is the
// browser's word and `approved` is the human's; neither is the hub's to write.
const HUB_STATES = new Set([
  "drafting", "previewed", "submitting", "acknowledged",
  "filled", "cancelled", "rejected", "expired",
]);

// Terminal from the edge's point of view. A late duplicate status must not
// resurrect a finished ticket -- IBKR can report on a permId long after the fact.
const TERMINAL_STATES = new Set(["filled", "cancelled", "rejected", "expired"]);

const TEXT_FIELDS = [
  "intent_uuid", "contract_fingerprint", "approval_expires_at", "reject_reason",
  "broker_status", "order_ref", "preview_as_of",
  "expiry", "right_code", "trading_class", "exchange", "local_symbol",
  "strike_decimal", "multiplier_decimal", "currency",
];
const INTEGER_FIELDS = ["client_id", "order_id", "perm_id"];

const MAX_BODY_BYTES = 262_144;
const noStore = () => ({ "cache-control": "no-store" });

export async function onRequestPost(context) {
  const id = requestId(context.request);
  try {
    const bytes = await context.request.arrayBuffer();
    if (bytes.byteLength > MAX_BODY_BYTES) {
      return json({ error: "Payload too large.", request_id: id }, 413, noStore());
    }
    const authorization = await verifyPortfolioHmac(context.request, context.env, bytes);
    if (!authorization) return json({ error: "Unauthorized or expired signature.", request_id: id }, 401, noStore());
    const db = requireDatabase(context.env);
    if (!await reserveNonce(db, authorization.nonce)) {
      return json({ error: "Replay rejected.", request_id: id }, 409, noStore());
    }

    let payload;
    try { payload = JSON.parse(new TextDecoder().decode(bytes) || "{}"); }
    catch (_) { return json({ error: "Invalid JSON.", request_id: id }, 400, noStore()); }

    const accountAlias = String(payload?.account_alias || "").trim();
    const key = String(payload?.request_id || "").trim();
    if (!accountAlias || !key) {
      return json({ error: "account_alias and request_id are required.", request_id: id }, 422, noStore());
    }
    const state = String(payload?.state || "").trim();
    if (!HUB_STATES.has(state)) {
      // Naming the rejected value matters: the hub logs this back into its own
      // loop, and "unsupported state" alone would not say which one.
      return json({ error: `The hub cannot publish state '${state}'.`, request_id: id }, 422, noStore());
    }

    const current = await db.prepare(
      "SELECT state FROM portfolio_order_requests WHERE request_id=? AND account_alias=?",
    ).bind(key, accountAlias).first();
    if (!current) return json({ error: "Unknown order request.", request_id: id }, 404, noStore());
    if (TERMINAL_STATES.has(current.state)) {
      return json({
        schema_version: "portfolio_order_requests.v1",
        request_id_published: key, state: current.state, ignored: true,
        note: "Ticket is already terminal; late status discarded.",
        request_id: id,
      }, 200, noStore());
    }

    const assignments = ["state=?", "updated_at=?"];
    const values = [state, new Date().toISOString()];
    for (const field of TEXT_FIELDS) {
      if (payload[field] === undefined) continue;
      assignments.push(`${field}=?`);
      values.push(payload[field] === null ? null : String(payload[field]).slice(0, 512));
    }
    for (const field of INTEGER_FIELDS) {
      if (payload[field] === undefined) continue;
      const parsed = Number(payload[field]);
      assignments.push(`${field}=?`);
      values.push(Number.isInteger(parsed) ? parsed : null);
    }
    if (payload.preview !== undefined) {
      assignments.push("preview_json=?", "preview_as_of=?");
      values.push(payload.preview === null ? null : JSON.stringify(payload.preview));
      values.push(new Date().toISOString());
    }
    // Releasing the lease on every publish keeps a crashed bridge from holding a
    // ticket it already finished with.
    assignments.push("claimed_at=?", "claimed_by=?");
    values.push(null, null);

    const result = await db.prepare(
      `UPDATE portfolio_order_requests SET ${assignments.join(",")} WHERE request_id=? AND account_alias=?`,
    ).bind(...values, key, accountAlias).run();

    if (!result.meta?.changes) {
      return json({ error: "Order request was not updated.", request_id: id }, 409, noStore());
    }
    return json({
      schema_version: "portfolio_order_requests.v1",
      request_id_published: key, state, request_id: id,
    }, 200, noStore());
  } catch (error) {
    return failure(error, id);
  }
}
