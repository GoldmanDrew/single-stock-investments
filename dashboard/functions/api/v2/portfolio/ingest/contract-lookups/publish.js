// Hub-facing: record what IBKR said a symbol resolves to.
//
// This is the only route in the system that writes a conId the browser will
// later use, which is why it is HMAC-signed and why every match is normalised
// before storage rather than trusted as sent.
//
// A resolved lookup also seeds the contract cache, so the second person to ask
// about the same contract gets an instant answer and IBKR is not asked twice.

import { failure, json, requestId, requireDatabase } from "../../../../../_lib/http.js";
import { reserveNonce, verifyPortfolioHmac } from "../../../../../_lib/portfolio.js";
import { normalizeMatches, rememberContracts } from "../../../../../_lib/contracts.js";

const PUBLISHABLE = new Set(["resolved", "failed"]);
const MAX_BODY_BYTES = 1_000_000;
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
    const key = String(payload?.lookup_id || "").trim();
    const state = String(payload?.state || "").trim();
    if (!accountAlias || !key) {
      return json({ error: "account_alias and lookup_id are required.", request_id: id }, 422, noStore());
    }
    if (!PUBLISHABLE.has(state)) {
      return json({ error: `The hub cannot publish state '${state}'.`, request_id: id }, 422, noStore());
    }

    const matches = state === "resolved" ? normalizeMatches(payload?.matches) : [];
    // A "resolved" lookup with nothing in it is a failure wearing a success
    // label, and the UI would render an empty picker with no explanation.
    if (state === "resolved" && !matches.length) {
      return json({ error: "A resolved lookup must carry at least one match.", request_id: id }, 422, noStore());
    }

    const result = await db.prepare(`UPDATE portfolio_contract_lookups
      SET state=?, matches_json=?, error=?, claimed_at=NULL, claimed_by=NULL, updated_at=?
      WHERE lookup_id=? AND account_alias=?`).bind(
      state,
      matches.length ? JSON.stringify(matches) : null,
      payload?.error == null ? null : String(payload.error).slice(0, 500),
      new Date().toISOString(), key, accountAlias,
    ).run();
    if (!result.meta?.changes) {
      return json({ error: "Unknown contract lookup.", request_id: id }, 404, noStore());
    }

    let cached = 0;
    if (matches.length) cached = await rememberContracts(db, matches, "lookup");

    return json({
      schema_version: "portfolio_contract_lookups.v1",
      lookup_id_published: key, state, matches: matches.length, cached, request_id: id,
    }, 200, noStore());
  } catch (error) {
    return failure(error, id);
  }
}
