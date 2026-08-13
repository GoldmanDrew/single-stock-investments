import { failure, json, requestId, requireDatabase } from "../../_lib/http.js";
import { loadBook, verifySleeveHmac } from "../../_lib/sleeves.js";

const MAX_BODY_BYTES = 512_000;

export async function onRequestPost(context) {
  const id = requestId(context.request);
  try {
    const body = await context.request.arrayBuffer();
    if (body.byteLength > MAX_BODY_BYTES) {
      return json({ error: "Payload too large.", request_id: id }, 413);
    }
    const authorization = await verifySleeveHmac(context.request, context.env, body);
    if (!authorization) {
      return json({ error: "Unauthorized or expired signature.", request_id: id }, 401, {
        "cache-control": "no-store",
      });
    }
    let payload;
    try {
      payload = JSON.parse(new TextDecoder().decode(body));
    } catch (_) {
      return json({ error: "Invalid JSON.", request_id: id }, 400);
    }
    const db = requireDatabase(context.env);
    const nonceInsert = await db.prepare(
      "INSERT OR IGNORE INTO sleeve_ingest_nonces (nonce) VALUES (?)",
    ).bind(authorization.nonce).run();
    if (Number(nonceInsert.meta?.changes || 0) !== 1) {
      return json({ error: "Replay rejected.", request_id: id }, 409, { "cache-control": "no-store" });
    }
    await db.prepare(
      "DELETE FROM sleeve_ingest_nonces WHERE received_at < datetime('now', '-1 day')",
    ).run();

    const statements = [];
    const fill = payload.fill;
    if (fill && fill.fill_id) {
      statements.push(db.prepare(`
        INSERT OR REPLACE INTO sleeve_orders (
          proposal_id, owner, ticker, side, qty, limit_price, status, dry_run, ib_order_id, submitted_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'filled', ?, ?, ?)
      `).bind(
        fill.proposal_id, fill.owner, fill.ticker, fill.side, fill.qty, fill.price,
        fill.dry_run ? 1 : 0, fill.ib_order_id || null, fill.filled_at,
      ));
      statements.push(db.prepare(`
        INSERT OR REPLACE INTO sleeve_fills (
          fill_id, proposal_id, owner, ticker, qty, price, commission, filled_at, source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
      `).bind(
        fill.fill_id, fill.proposal_id, fill.owner, fill.ticker, fill.qty, fill.price,
        fill.commission || 0, fill.filled_at, fill.source || "ib",
      ));
      const signed = fill.side === "BUY" ? -Math.abs(fill.qty * fill.price) : Math.abs(fill.qty * fill.price);
      statements.push(db.prepare(`
        INSERT INTO sleeve_cashflows (owner, date, ticker, amount, kind)
        VALUES (?, ?, ?, ?, ?)
      `).bind(fill.owner, String(fill.filled_at).slice(0, 10), fill.ticker, signed, fill.side === "BUY" ? "buy" : "sell"));
    }

    const book = payload.book;
    if (book && book.owner && Array.isArray(book.positions)) {
      const asOf = book.as_of || new Date().toISOString();
      statements.push(db.prepare(`
        INSERT INTO sleeve_config (owner, equity_usd, extra_margin_usd, as_of, payload_json, updated_at)
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(owner) DO UPDATE SET
          equity_usd = excluded.equity_usd,
          extra_margin_usd = excluded.extra_margin_usd,
          as_of = excluded.as_of,
          payload_json = excluded.payload_json,
          updated_at = CURRENT_TIMESTAMP
      `).bind(
        book.owner,
        book.header?.equity_usd ?? null,
        book.header?.extra_margin_usd ?? 0,
        asOf,
        JSON.stringify(book.header || {}),
      ));
      statements.push(db.prepare("DELETE FROM sleeve_positions WHERE owner = ?").bind(book.owner));
      for (const pos of book.positions) {
        statements.push(db.prepare(`
          INSERT INTO sleeve_positions (
            owner, ticker, qty, mark, market_value, sec_type, classifier_reason, synced_at
          ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        `).bind(
          book.owner, pos.ticker, pos.qty, pos.mark, pos.market_value,
          pos.secType || "STK", pos.classifier_reason || "residual", asOf,
        ));
      }
    }

    for (const row of payload.audit || []) {
      statements.push(db.prepare(`
        INSERT INTO sleeve_classifier_audit (as_of, ticker, bucket, reason, owner)
        VALUES (?, ?, ?, ?, ?)
      `).bind(
        row.as_of || new Date().toISOString(),
        row.ticker || "",
        row.bucket || "ignored",
        row.reason || "",
        row.owner || null,
      ));
    }

    if (statements.length) await db.batch(statements);
    const owner = book?.owner || fill?.owner || "drew";
    const next = await loadBook(db, owner);
    return json({ ok: true, book: next, request_id: id }, 200, { "cache-control": "no-store" });
  } catch (error) {
    return failure(error, id);
  }
}
