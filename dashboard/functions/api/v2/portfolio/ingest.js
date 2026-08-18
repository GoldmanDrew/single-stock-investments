import { failure, json, requestId, requireDatabase } from "../../../_lib/http.js";
import { reserveNonce, storeAccountSnapshot, storeAllocationProjection, storeFlexEod, storeStrategySnapshot, validateAccountSnapshot, validateAllocationProjection, validateFlexEod, validateStrategySnapshot, verifyPortfolioHmac } from "../../../_lib/portfolio.js";

const MAX_BODY_BYTES = 8_000_000;

export async function onRequestPost(context) {
  const id = requestId(context.request);
  try {
    const bytes = await context.request.arrayBuffer();
    if (bytes.byteLength > MAX_BODY_BYTES) return json({ error: "Payload too large.", request_id: id }, 413, { "cache-control": "no-store" });
    const authorization = await verifyPortfolioHmac(context.request, context.env, bytes);
    if (!authorization) return json({ error: "Unauthorized or expired signature.", request_id: id }, 401, { "cache-control": "no-store" });
    const db = requireDatabase(context.env);
    if (!await reserveNonce(db, authorization.nonce)) return json({ error: "Replay rejected.", request_id: id }, 409, { "cache-control": "no-store" });
    let payload;
    try { payload = JSON.parse(new TextDecoder().decode(bytes)); }
    catch (_) { return json({ error: "Invalid JSON.", request_id: id }, 400, { "cache-control": "no-store" }); }
    let stored;
    if (payload.schema_version === "account_snapshot.v1") stored = await storeAccountSnapshot(context.env, validateAccountSnapshot(payload), bytes);
    else if (payload.schema_version === "strategy_snapshot.v1") stored = await storeStrategySnapshot(context.env, validateStrategySnapshot(payload), bytes);
    else if (payload.schema_version === "allocation_projection.v1") stored = await storeAllocationProjection(context.env, validateAllocationProjection(payload), bytes);
    else if (payload.schema_version === "flex_eod.v1") stored = await storeFlexEod(context.env, validateFlexEod(payload), bytes);
    else return json({ error: "Unsupported schema_version.", request_id: id }, 422, { "cache-control": "no-store" });
    return json({ ok: true, source_run_id: payload.source_run_id, ...stored, request_id: id }, stored.duplicate ? 200 : 201, { "cache-control": "no-store" });
  } catch (error) {
    if (error instanceof TypeError) return json({ error: error.message, request_id: id }, 422, { "cache-control": "no-store" });
    return failure(error, id);
  }
}
