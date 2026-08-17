import { requireDatabase } from "./http.js";

const DECIMAL = /^-?[0-9]+(?:\.[0-9]+)?$/;
const OWNERS = new Set(["all", "drew", "michael", "unallocated"]);

function hex(bytes) {
  return [...bytes].map((value) => value.toString(16).padStart(2, "0")).join("");
}

export async function verifyPortfolioHmac(request, env, body) {
  const expected = String(env?.PORTFOLIO_INGEST_TOKEN || "");
  const timestamp = request.headers.get("x-portfolio-timestamp") || "";
  const nonce = request.headers.get("x-portfolio-nonce") || "";
  const supplied = (request.headers.get("x-portfolio-signature") || "").toLowerCase();
  const seconds = Number(timestamp);
  if (expected.length < 32 || !/^\d{10}$/.test(timestamp) || !/^[a-f0-9]{32}$/.test(nonce)
      || !/^[a-f0-9]{64}$/.test(supplied) || !Number.isFinite(seconds)
      || Math.abs(Date.now() / 1000 - seconds) > 300) return false;
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey("raw", encoder.encode(expected), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const prefix = encoder.encode(`${timestamp}\n${nonce}\n`);
  const message = new Uint8Array(prefix.byteLength + body.byteLength);
  message.set(prefix);
  message.set(new Uint8Array(body), prefix.byteLength);
  const computed = hex(new Uint8Array(await crypto.subtle.sign("HMAC", key, message)));
  const left = encoder.encode(computed);
  const right = encoder.encode(supplied);
  let difference = left.length ^ right.length;
  for (let i = 0; i < Math.min(left.length, right.length); i += 1) difference |= left[i] ^ right[i];
  return difference === 0 ? { timestamp, nonce } : false;
}

export function requirePrivateArchive(env) {
  if (!env?.PRIVATE_ARTIFACTS) throw new Error("Missing required R2 binding: PRIVATE_ARTIFACTS");
  return env.PRIVATE_ARTIFACTS;
}

export function validateAccountSnapshot(payload) {
  if (payload?.schema_version !== "account_snapshot.v1" || !payload.source_run_id
      || !payload.account_alias || !payload.as_of || typeof payload.complete !== "boolean"
      || !Array.isArray(payload.account_values) || !Array.isArray(payload.positions)) {
    throw new TypeError("Invalid account_snapshot.v1 envelope");
  }
  for (const row of payload.positions) {
    if (!Number.isInteger(row.conid) || row.conid <= 0 || !row.symbol || !row.sec_type
        || !row.currency || !DECIMAL.test(String(row.quantity))
        || (row.account_alias && row.account_alias !== payload.account_alias)) {
      throw new TypeError("Invalid canonical position row");
    }
  }
  for (const row of payload.open_orders || []) {
    if (!Number.isInteger(row.order_id) || (row.ownership && !["hub", "foreign", "legacy"].includes(row.ownership))) {
      throw new TypeError("Invalid broker open-order row");
    }
  }
  for (const row of payload.open_orders || []) statements.push(db.prepare(`INSERT INTO portfolio_broker_orders
    (source_run_id,account_alias,client_id,order_id,perm_id,conid,symbol,action,order_type,total_quantity_decimal,limit_price_decimal,tif,status,order_ref,ownership,parent_id,oca_group,as_of)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`).bind(payload.source_run_id, payload.account_alias, row.client_id ?? null, row.order_id, row.perm_id ?? null, row.conid ?? null, row.symbol || null, row.action || null, row.order_type || null, row.total_quantity ?? null, row.limit_price ?? null, row.tif || null, row.status || null, row.order_ref || null, row.ownership || "foreign", row.parent_id ?? null, row.oca_group || null, row.as_of || payload.as_of));
  return payload;
}

export function validateStrategySnapshot(payload) {
  if (payload?.schema_version !== "strategy_snapshot.v1" || !payload.producer
      || !payload.source_run_id || !payload.as_of || typeof payload.complete !== "boolean"
      || !Array.isArray(payload.rows)) throw new TypeError("Invalid strategy_snapshot.v1 envelope");
  return payload;
}

export function validateAllocationProjection(payload) {
  if (payload?.schema_version !== "allocation_projection.v1" || !payload.projection_id
      || !payload.source_run_id || !payload.account_alias || !payload.as_of
      || !Array.isArray(payload.allocations) || !Array.isArray(payload.cash_events) || !Array.isArray(payload.reconciliation_breaks)
      || !Array.isArray(payload.order_events)) throw new TypeError("Invalid allocation_projection.v1 envelope");
  return payload;
}

export function validateFlexEod(payload) {
  if (payload?.schema_version !== "flex_eod.v1" || !payload.source_run_id || !payload.account_alias
      || !/^\d{4}-\d{2}-\d{2}$/.test(payload.session_date || "") || !payload.as_of
      || !Array.isArray(payload.positions) || !Array.isArray(payload.trades)
      || !Array.isArray(payload.cash_transactions) || !Array.isArray(payload.nav_rows)) {
    throw new TypeError("Invalid flex_eod.v1 envelope");
  }
  return payload;
}

export async function sha256Hex(bytes) {
  return hex(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)));
}

export async function reserveNonce(db, nonce) {
  const result = await db.prepare("INSERT OR IGNORE INTO portfolio_ingest_nonces(nonce) VALUES (?)").bind(nonce).run();
  if (Number(result.meta?.changes || 0) !== 1) return false;
  await db.prepare("DELETE FROM portfolio_ingest_nonces WHERE received_at < datetime('now', '-1 day')").run();
  return true;
}

export async function storeAccountSnapshot(env, payload, bytes) {
  const db = requireDatabase(env);
  const archive = requirePrivateArchive(env);
  const digest = await sha256Hex(bytes);
  const objectKey = `portfolio/account/${payload.account_alias}/${payload.as_of.slice(0, 10)}/${payload.source_run_id}.json`;
  const existing = await db.prepare("SELECT content_sha256 FROM portfolio_source_runs WHERE source_run_id=?").bind(payload.source_run_id).first();
  if (existing) {
    if (existing.content_sha256 !== digest) throw new TypeError("source_run_id reused with different content");
    return { duplicate: true, object_key: objectKey };
  }
  await archive.put(objectKey, bytes, { httpMetadata: { contentType: "application/json" }, customMetadata: { schema: payload.schema_version, sha256: digest } });
  const statements = [
    db.prepare(`INSERT INTO portfolio_source_runs
      (source_run_id,schema_version,source,account_alias,as_of,complete,completeness_json,content_sha256,object_key)
      VALUES (?,?,?,?,?,?,?,?,?)`).bind(payload.source_run_id, payload.schema_version, "ibkr", payload.account_alias, payload.as_of, payload.complete ? 1 : 0, JSON.stringify(payload.completeness || {}), digest, objectKey),
  ];
  for (const row of payload.account_values) {
    if (!DECIMAL.test(String(row.value))) throw new TypeError(`Invalid account value ${row.tag}`);
    statements.push(db.prepare(`INSERT INTO portfolio_account_values
      (source_run_id,tag,currency,segment,model_code,value_decimal,source,as_of) VALUES (?,?,?,?,?,?,?,?)`)
      .bind(payload.source_run_id, row.tag, row.currency || "", row.segment || "", row.model_code || "", String(row.value), row.source, row.as_of));
  }
  for (const row of payload.positions) {
    statements.push(db.prepare(`INSERT INTO portfolio_positions
      (source_run_id,account_alias,conid,model_code,symbol,local_symbol,description,sec_type,currency,exchange_name,expiry,strike_decimal,right_code,multiplier_decimal,quantity_decimal,average_cost_decimal,mark_decimal,market_value_decimal,unrealized_pnl_decimal,realized_pnl_decimal,daily_pnl_decimal,source,quality,as_of)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`).bind(
      payload.source_run_id, payload.account_alias, row.conid, row.model_code || "", row.symbol, row.local_symbol || null,
      row.description || null, row.sec_type, row.currency, row.exchange || null, row.expiry || null, row.strike || null,
      row.right || null, row.multiplier || null, String(row.quantity), row.average_cost ?? null, row.mark ?? null,
      row.market_value ?? null, row.unrealized_pnl ?? null, row.realized_pnl ?? null, row.daily_pnl ?? null,
      row.source, row.quality || "unknown", row.as_of,
    ));
  }
  await db.batch(statements);
  return { duplicate: false, object_key: objectKey };
}

export async function storeStrategySnapshot(env, payload, bytes) {
  const db = requireDatabase(env);
  const archive = requirePrivateArchive(env);
  const digest = await sha256Hex(bytes);
  const objectKey = `portfolio/strategy/${payload.producer}/${payload.as_of.slice(0, 10)}/${payload.source_run_id}.json`;
  const existing = await db.prepare("SELECT content_sha256 FROM portfolio_source_runs WHERE source_run_id=?").bind(payload.source_run_id).first();
  if (existing) {
    if (existing.content_sha256 !== digest) throw new TypeError("source_run_id reused with different content");
    return { duplicate: true, object_key: objectKey };
  }
  await archive.put(objectKey, bytes, { httpMetadata: { contentType: "application/json" }, customMetadata: { schema: payload.schema_version, sha256: digest } });
  await db.batch([
    db.prepare(`INSERT INTO portfolio_source_runs
      (source_run_id,schema_version,source,account_alias,as_of,complete,completeness_json,content_sha256,object_key)
      VALUES (?,?,?,?,?,?,?,?,?)`).bind(payload.source_run_id, payload.schema_version, payload.producer, null, payload.as_of, payload.complete ? 1 : 0, '{}', digest, objectKey),
    db.prepare("INSERT INTO portfolio_strategy_snapshots(source_run_id,producer,payload_json) VALUES (?,?,?)")
      .bind(payload.source_run_id, payload.producer, JSON.stringify(payload)),
  ]);
  return { duplicate: false, object_key: objectKey };
}

export async function storeAllocationProjection(env, payload, bytes) {
  const db = requireDatabase(env);
  const archive = requirePrivateArchive(env);
  const digest = await sha256Hex(bytes);
  const objectKey = `portfolio/allocation/${payload.account_alias}/${payload.as_of.slice(0, 10)}/${payload.projection_id}.json`;
  const existing = await db.prepare("SELECT content_sha256 FROM portfolio_allocation_projections WHERE projection_id=?").bind(payload.projection_id).first();
  if (existing) {
    if (existing.content_sha256 !== digest) throw new TypeError("projection_id reused with different content");
    return { duplicate: true, object_key: objectKey };
  }
  const source = await db.prepare("SELECT account_alias FROM portfolio_source_runs WHERE source_run_id=? AND source='ibkr' AND complete=1").bind(payload.source_run_id).first();
  if (!source || source.account_alias !== payload.account_alias) throw new TypeError("projection does not reference a matching complete broker snapshot");
  await archive.put(objectKey, bytes, { httpMetadata: { contentType: "application/json" }, customMetadata: { schema: payload.schema_version, sha256: digest } });
  const statements = [
    db.prepare("DELETE FROM portfolio_allocations WHERE account_alias=?").bind(payload.account_alias),
    db.prepare("DELETE FROM portfolio_cash_events WHERE account_alias=?").bind(payload.account_alias),
    db.prepare("DELETE FROM portfolio_reconciliation_breaks WHERE source_run_id=?").bind(payload.source_run_id),
    db.prepare("INSERT INTO portfolio_allocation_projections VALUES (?,?,?,?,?,?,CURRENT_TIMESTAMP)").bind(payload.projection_id, payload.source_run_id, payload.account_alias, payload.as_of, digest, objectKey),
  ];
  for (const row of payload.allocations) statements.push(db.prepare(`INSERT INTO portfolio_allocations
    (allocation_id,account_alias,conid,model_code,owner,strategy,bucket,quantity_decimal,confidence,effective_at,ended_at)
    VALUES (?,?,?,?,?,?,?,?,?,?,?)`).bind(row.allocation_id, row.account_alias, row.conid, row.model_code || "", row.owner, row.strategy, row.bucket || null, row.quantity_decimal, row.confidence, row.effective_at, row.ended_at || null));
  for (const row of payload.cash_events) statements.push(db.prepare(`INSERT INTO portfolio_cash_events
    (event_id,account_alias,owner,strategy,currency,amount_decimal,event_type,effective_at,source,source_event_id)
    VALUES (?,?,?,?,?,?,?,?,?,?)`).bind(row.event_id, row.account_alias, row.owner, row.strategy, row.currency, row.amount_decimal, row.event_type, row.effective_at, row.source, row.source_event_id || null));
  for (const row of payload.reconciliation_breaks) statements.push(db.prepare(`INSERT INTO portfolio_reconciliation_breaks
    (break_id,source_run_id,account_alias,conid,model_code,break_type,expected_decimal,actual_decimal,severity,status,details_json,created_at,resolved_at)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)`).bind(row.break_id, payload.source_run_id, row.account_alias, row.conid ?? null, row.model_code || "", row.break_type, row.expected_decimal ?? null, row.actual_decimal ?? null, row.severity, row.status, JSON.stringify(row.details || {}), row.created_at, row.resolved_at || null));
  for (const row of payload.order_events) statements.push(db.prepare(`INSERT OR IGNORE INTO portfolio_order_events
    (event_id,intent_uuid,account_alias,conid,order_ref,state,event_type,payload_json,created_at) VALUES (?,?,?,?,?,?,?,?,?)`).bind(row.event_id, row.intent_uuid, row.account_alias, row.conid, row.order_ref, row.state, row.event_type, JSON.stringify(row.payload || {}), row.created_at));
  await db.batch(statements);
  return { duplicate: false, object_key: objectKey };
}

export async function storeFlexEod(env, payload, bytes) {
  const db = requireDatabase(env); const archive = requirePrivateArchive(env); const digest = await sha256Hex(bytes);
  const objectKey = `portfolio/flex/${payload.account_alias}/${payload.session_date}/${payload.source_run_id}.json`;
  const existing = await db.prepare("SELECT content_sha256 FROM portfolio_source_runs WHERE source_run_id=?").bind(payload.source_run_id).first();
  if (existing) {
    if (existing.content_sha256 !== digest) throw new TypeError("source_run_id reused with different content");
    return { duplicate: true, object_key: objectKey };
  }
  const primary = await db.prepare("SELECT source_run_id FROM portfolio_flex_sessions WHERE account_alias=? AND session_date=? AND is_primary=1").bind(payload.account_alias, payload.session_date).first();
  await archive.put(objectKey, bytes, { httpMetadata: { contentType: "application/json" }, customMetadata: { schema: payload.schema_version, sha256: digest } });
  await db.batch([
    db.prepare(`INSERT INTO portfolio_source_runs
      (source_run_id,schema_version,source,account_alias,as_of,complete,completeness_json,content_sha256,object_key)
      VALUES (?,?,?,?,?,1,'{}',?,?)`).bind(payload.source_run_id, payload.schema_version, "ibkr_flex", payload.account_alias, payload.as_of, digest, objectKey),
    db.prepare("INSERT INTO portfolio_flex_sessions VALUES (?,?,?,?,?,?)").bind(payload.source_run_id, payload.account_alias, payload.session_date, primary ? 0 : 1, primary?.source_run_id || null, JSON.stringify(payload)),
  ]);
  return { duplicate: false, restatement: Boolean(primary), restates_source_run_id: primary?.source_run_id || null, object_key: objectKey };
}

export function ownerScope(url) {
  const owner = new URL(url).searchParams.get("owner") || "all";
  if (!OWNERS.has(owner)) throw new TypeError("Invalid owner scope");
  return owner;
}

export async function loadPortfolio(env, owner = "all") {
  const db = requireDatabase(env);
  const run = await db.prepare(`SELECT * FROM portfolio_source_runs
    WHERE source='ibkr' AND complete=1 ORDER BY as_of DESC LIMIT 1`).first();
  if (!run) return { schema_version: "portfolio_read_model.v1", status: "unknown", reason: "no complete broker snapshot", scope: owner, account_values: [], positions: [], reconciliation_breaks: [] };
  const [values, rows, breaks, cash, openOrders] = await db.batch([
    db.prepare("SELECT * FROM portfolio_account_values WHERE source_run_id=? ORDER BY tag,currency").bind(run.source_run_id),
    db.prepare(`SELECT p.*, a.allocation_id, a.owner, a.strategy, a.bucket, a.quantity_decimal AS allocated_quantity_decimal, a.confidence
      FROM portfolio_positions p LEFT JOIN portfolio_allocations a
        ON a.account_alias=p.account_alias AND a.conid=p.conid AND a.model_code=p.model_code
        AND a.effective_at<=p.as_of AND (a.ended_at IS NULL OR a.ended_at>p.as_of)
      WHERE p.source_run_id=? AND (?='all' OR a.owner=?) ORDER BY p.symbol,p.conid,a.owner,a.strategy`).bind(run.source_run_id, owner, owner),
    db.prepare("SELECT * FROM portfolio_reconciliation_breaks WHERE source_run_id=? AND status='open' ORDER BY severity,created_at DESC").bind(run.source_run_id),
    db.prepare("SELECT * FROM portfolio_cash_events WHERE account_alias=? AND effective_at<=? AND (?='all' OR owner=?) ORDER BY effective_at,event_id").bind(run.account_alias, run.as_of, owner, owner),
    db.prepare("SELECT COUNT(*) AS count FROM portfolio_broker_orders WHERE source_run_id=?").bind(run.source_run_id),
  ]);
  const positions = [];
  const keyed = new Map();
  for (const row of rows.results || []) {
    const key = `${row.account_alias}:${row.conid}:${row.model_code}`;
    let position = keyed.get(key);
    if (!position) {
      position = { ...row, allocations: [] };
      delete position.allocation_id; delete position.owner; delete position.strategy; delete position.bucket;
      delete position.allocated_quantity_decimal; delete position.confidence;
      positions.push(position); keyed.set(key, position);
    }
    if (row.allocation_id) position.allocations.push({ allocation_id: row.allocation_id, owner: row.owner, strategy: row.strategy, bucket: row.bucket, quantity_decimal: row.allocated_quantity_decimal, confidence: row.confidence });
  }
  return { schema_version: "portfolio_read_model.v1", status: "complete", scope: owner, snapshot: run, account_values: values.results || [], positions, cash_events: cash.results || [], broker_open_order_count: Number(openOrders.results?.[0]?.count || 0), reconciliation_breaks: breaks.results || [] };
}
