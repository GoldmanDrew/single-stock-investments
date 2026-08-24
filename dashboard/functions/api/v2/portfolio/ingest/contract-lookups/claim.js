// Hub-facing: hand the bridge the contract questions still waiting on an answer.
//
// Same pull-only shape as the order channel, and the same reason: the browser
// asked, but only the machine holding the Gateway credentials may answer.
//
// The batch is small on purpose. reqContractDetails and reqSecDefOptParams are
// paced by IBKR, and a chain request for a liquid name can return hundreds of
// strikes, so taking a handful per tick keeps the bridge inside its pacing
// budget instead of discovering the limit during a live session.

import { failure, json, requestId, requireDatabase } from "../../../../../_lib/http.js";
import { reserveNonce, verifyPortfolioHmac } from "../../../../../_lib/portfolio.js";

const CLAIMABLE_STATES = ["requested", "resolving"];
const LEASE_SECONDS = 60;
const BATCH = 5;

const MAX_BODY_BYTES = 16_384;
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
    if (!accountAlias) return json({ error: "account_alias is required.", request_id: id }, 422, noStore());
    const claimant = String(payload?.claimed_by || "portfolio-hub-bridge").trim().slice(0, 64);

    const now = new Date();
    const stamp = now.toISOString();
    const leaseFloor = new Date(now.getTime() - LEASE_SECONDS * 1000).toISOString();
    const placeholders = CLAIMABLE_STATES.map(() => "?").join(",");

    // Lease in SQL for the same reason as the order channel: read-then-write
    // would let two bridges resolve the same chain twice against IBKR's pacing.
    // Re-claiming here is harmless -- a lookup transmits nothing.
    const claimable = await db.prepare(`SELECT lookup_id FROM portfolio_contract_lookups
      WHERE account_alias=? AND state IN (${placeholders})
        AND (claimed_at IS NULL OR claimed_at < ?)
      ORDER BY created_at LIMIT ?`).bind(accountAlias, ...CLAIMABLE_STATES, leaseFloor, BATCH).all();
    const ids = (claimable.results || []).map((row) => row.lookup_id);
    if (!ids.length) {
      return json({
        schema_version: "portfolio_contract_lookups.v1",
        account_alias: accountAlias, lookups: [], request_id: id,
      }, 200, noStore());
    }

    const idPlaceholders = ids.map(() => "?").join(",");
    await db.prepare(`UPDATE portfolio_contract_lookups
      SET state='resolving', claimed_at=?, claimed_by=?, updated_at=?
      WHERE lookup_id IN (${idPlaceholders})`).bind(stamp, claimant, stamp, ...ids).run();

    const rows = await db.prepare(`SELECT lookup_id,account_alias,owner,kind,symbol,sec_type,
        currency,exchange,expiry,strike_decimal,right_code,state,created_at
      FROM portfolio_contract_lookups WHERE lookup_id IN (${idPlaceholders})
      ORDER BY created_at`).bind(...ids).all();

    return json({
      schema_version: "portfolio_contract_lookups.v1",
      account_alias: accountAlias,
      lease_seconds: LEASE_SECONDS,
      lookups: rows.results || [],
      request_id: id,
    }, 200, noStore());
  } catch (error) {
    return failure(error, id);
  }
}
