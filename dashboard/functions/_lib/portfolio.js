import { requireDatabase } from "./http.js";
import { normalizeMatches, rememberContracts } from "./contracts.js";

const DECIMAL = /^-?[0-9]+(?:\.[0-9]+)?$/;
const OWNERS = new Set(["all", "drew", "michael", "unallocated"]);
// Every non-base position names how it was translated, and the set is closed so a
// new source cannot arrive unreviewed.
//
//   identity                   same-currency row, rate 1
//   ibkr_flex_rate             fxRateToBase, stated per row by Flex; preferred,
//                              and the only source once the collector is gone
//   ibkr_exchange_rate         the rate IBKR states for the currency (Gateway)
//   ibkr_portfolio_translation inferred from marketValue / (position x price),
//                              usable only when that ratio is not ~1
//   fx_unavailable             an honest failure: null rate, degraded quality
const FX_SOURCES = new Set([
  "identity", "ibkr_flex_rate", "ibkr_exchange_rate", "ibkr_portfolio_translation", "fx_unavailable",
]);
const DEGRADED_QUALITY = new Set(["estimated", "unknown"]);

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
      || !/^[A-Z]{3}$/.test(payload.base_currency || "")
      || !Array.isArray(payload.account_values) || !Array.isArray(payload.positions)) {
    throw new TypeError("Invalid account_snapshot.v1 envelope");
  }
  for (const row of payload.positions) {
    if (!Number.isInteger(row.conid) || row.conid <= 0 || !row.symbol || !row.sec_type
        || !row.currency || row.base_currency !== payload.base_currency
        || !["shares", "contracts", "units", "cash"].includes(row.quantity_unit)
        || !DECIMAL.test(String(row.quantity))
        || (row.account_alias && row.account_alias !== payload.account_alias)) {
      throw new TypeError("Invalid canonical position row");
    }
    const nativeCurrency = row.native_currency || row.currency;
    if (nativeCurrency !== payload.base_currency && row.market_value != null) {
      // A non-base row must still state both sides of the translation and name its
      // source, so nothing can be silently mixed into base totals.
      if (!DECIMAL.test(String(row.market_value_native)) || !DECIMAL.test(String(row.market_value_base))
          || !FX_SOURCES.has(row.fx_source)) {
        throw new TypeError("Non-base position is missing explicit native/base FX fields");
      }
      // The rate itself may be genuinely underivable: IBKR implies it from
      // marketValue/marketPrice, and a zero mark (no market-data permission on the
      // listing venue, a halted name) or a flat row makes that ratio indeterminate.
      // That is a property of one position, so it degrades that row's quality
      // instead of failing the envelope -- OPERATIONS.md requires an incomplete
      // account to stay visible, "never an empty account".
      if (row.fx_source !== "fx_unavailable"
          && (!DECIMAL.test(String(row.fx_rate_to_base)) || !row.fx_as_of)) {
        throw new TypeError("Non-base position declares an FX source without a usable rate");
      }
      // A flat row is zero on both sides, so there is no exposure to misstate and no
      // rate to miss; only a position carrying value has to admit it is estimated.
      const carriesValue = Number(row.market_value_native) !== 0 || Number(row.market_value_base) !== 0;
      if (row.fx_source === "fx_unavailable" && carriesValue && !DEGRADED_QUALITY.has(row.quality)) {
        throw new TypeError("Untranslated non-base position must be marked estimated or unknown");
      }
    }
  }
  for (const row of payload.open_orders || []) {
    if (!Number.isInteger(row.order_id) || (row.ownership && !["hub", "foreign", "legacy"].includes(row.ownership))) {
      throw new TypeError("Invalid broker open-order row");
    }
  }
  return payload;
}

const STRATEGY_PRODUCERS = new Set(["spx_0dte", "ls_risk", "ls_bucket5_live", "ls_bucket5_product"]);

export function validateStrategySnapshot(payload) {
  if (payload?.schema_version !== "strategy_snapshot.v1" || !payload.producer
      || !STRATEGY_PRODUCERS.has(payload.producer) || !payload.source_run_id || !payload.as_of
      || typeof payload.complete !== "boolean" || !Array.isArray(payload.rows)) {
    throw new TypeError("Invalid strategy_snapshot.v1 envelope");
  }
  for (const row of payload.rows) {
    if (!row?.row_id || !row.reconciliation_role || !row.exposure_basis) {
      throw new TypeError("Invalid strategy snapshot row");
    }
    if (payload.producer === "ls_bucket5_product" && (row.reconciliation_role !== "research_only" || row.conid)) {
      throw new TypeError("B5 product snapshot cannot broker-reconcile");
    }
    if (payload.producer === "ls_bucket5_live" && row.bucket !== "B5") {
      throw new TypeError("live B5 snapshot leaked a non-B5 row");
    }
  }
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
      (source_run_id,account_alias,conid,model_code,symbol,local_symbol,description,sec_type,currency,exchange_name,expiry,
       strike_decimal,right_code,multiplier_decimal,quantity_decimal,average_cost_decimal,mark_decimal,market_value_decimal,
       unrealized_pnl_decimal,realized_pnl_decimal,daily_pnl_decimal,source,quality,as_of,quantity_unit,base_currency,
       native_currency,fx_rate_to_base_decimal,fx_as_of,fx_source,average_cost_native_decimal,mark_native_decimal,
       market_value_native_decimal,market_value_base_decimal,unrealized_pnl_base_decimal,realized_pnl_base_decimal,daily_pnl_base_decimal)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`).bind(
      payload.source_run_id, payload.account_alias, row.conid, row.model_code || "", row.symbol, row.local_symbol || null,
      row.description || null, row.sec_type, row.currency, row.exchange || null, row.expiry || null, row.strike || null,
      row.right || null, row.multiplier || null, String(row.quantity), row.average_cost ?? null, row.mark ?? null,
      row.market_value ?? null, row.unrealized_pnl ?? null, row.realized_pnl ?? null, row.daily_pnl ?? null,
      row.source, row.quality || "unknown", row.as_of,
      row.quantity_unit, payload.base_currency, row.native_currency || row.currency, row.fx_rate_to_base ?? null,
      row.fx_as_of ?? null, row.fx_source ?? null, row.average_cost_native ?? row.average_cost ?? null,
      row.mark_native ?? row.mark ?? null, row.market_value_native ?? null, row.market_value_base ?? row.market_value ?? null,
      row.unrealized_pnl_base ?? row.unrealized_pnl ?? null, row.realized_pnl_base ?? row.realized_pnl ?? null,
      row.daily_pnl_base ?? row.daily_pnl ?? null,
    ));
  }
  for (const row of payload.open_orders || []) {
    statements.push(db.prepare(`INSERT INTO portfolio_broker_orders
      (source_run_id,account_alias,client_id,order_id,perm_id,conid,symbol,action,order_type,total_quantity_decimal,limit_price_decimal,tif,status,order_ref,ownership,parent_id,oca_group,as_of)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`).bind(
      payload.source_run_id, payload.account_alias, row.client_id ?? null, row.order_id, row.perm_id ?? null,
      row.conid ?? null, row.symbol || null, row.action || null, row.order_type || null, row.total_quantity ?? null,
      row.limit_price ?? null, row.tif || null, row.status || null, row.order_ref || null, row.ownership || "foreign",
      row.parent_id ?? null, row.oca_group || null, row.as_of || payload.as_of,
    ));
  }
  await db.batch(statements);
  // Every position seeds the contract cache. This is what makes the order
  // ticket's symbol box useful without asking IBKR anything: the account's own
  // holdings are the contracts most likely to be traded again, and remembering
  // them here means the box still answers on a weekend, when `ibc.service` is
  // legitimately down and no live lookup can resolve.
  await rememberContracts(db, normalizeMatches(payload.positions.map((row) => ({
    conid: row.conid, symbol: row.symbol, local_symbol: row.local_symbol,
    sec_type: row.sec_type, currency: row.currency, exchange: row.exchange,
    trading_class: row.trading_class, expiry: row.expiry, strike: row.strike,
    right: row.right, multiplier: row.multiplier, description: row.description,
  })), payload.positions.length), "position");
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
  const brokerCount = await db.prepare("SELECT COUNT(*) AS count FROM portfolio_positions WHERE source_run_id=?").bind(payload.source_run_id).first();
  if (Number(brokerCount?.count || 0) > 0 && payload.allocations.length === 0) {
    throw new TypeError("non-empty broker snapshot cannot publish an empty allocation projection");
  }
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
  const [values, rows, breaks, cash, openOrders, brokerPositions, allocationStatus] = await db.batch([
    db.prepare("SELECT * FROM portfolio_account_values WHERE source_run_id=? ORDER BY tag,currency").bind(run.source_run_id),
    db.prepare(`SELECT p.*, a.allocation_id, a.owner, a.strategy, a.bucket, a.quantity_decimal AS allocated_quantity_decimal, a.confidence
      FROM portfolio_positions p LEFT JOIN portfolio_allocations a
        ON a.account_alias=p.account_alias AND a.conid=p.conid AND a.model_code=p.model_code
        AND a.effective_at<=p.as_of AND (a.ended_at IS NULL OR a.ended_at>p.as_of)
        AND EXISTS (SELECT 1 FROM portfolio_allocation_projections ap
          WHERE ap.source_run_id=p.source_run_id AND ap.account_alias=p.account_alias)
      WHERE p.source_run_id=? AND (?='all' OR a.owner=?) ORDER BY p.symbol,p.conid,a.owner,a.strategy`).bind(run.source_run_id, owner, owner),
    db.prepare("SELECT * FROM portfolio_reconciliation_breaks WHERE source_run_id=? AND status='open' ORDER BY severity,created_at DESC").bind(run.source_run_id),
    db.prepare("SELECT * FROM portfolio_cash_events WHERE account_alias=? AND effective_at<=? AND (?='all' OR owner=?) ORDER BY effective_at,event_id").bind(run.account_alias, run.as_of, owner, owner),
    db.prepare("SELECT COUNT(*) AS count FROM portfolio_broker_orders WHERE source_run_id=?").bind(run.source_run_id),
    db.prepare("SELECT COUNT(*) AS count FROM portfolio_positions WHERE source_run_id=?").bind(run.source_run_id),
    db.prepare(`SELECT p.projection_id,p.as_of,COUNT(a.allocation_id) AS allocation_count
      FROM portfolio_allocation_projections p LEFT JOIN portfolio_allocations a ON a.account_alias=p.account_alias
      WHERE p.account_alias=? AND p.source_run_id=?
      GROUP BY p.projection_id,p.as_of ORDER BY p.as_of DESC LIMIT 1`).bind(run.account_alias, run.source_run_id),
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
  const brokerPositionCount = Number(brokerPositions.results?.[0]?.count || 0);
  const allocationRow = allocationStatus.results?.[0] || null;
  const allocationCount = Number(allocationRow?.allocation_count || 0);
  const allocationState = brokerPositionCount === 0 ? "not_applicable" : allocationCount > 0 ? "complete" : "upstream_absent";
  return {
    schema_version: "portfolio_read_model.v1",
    // "complete" describes the snapshot's contents, not its age. With the
    // collector disabled (2026-08-25) nothing writes new snapshots, so this
    // query keeps returning the same run forever and every figure on the page
    // would present as current. Age is stated so the page can say otherwise --
    // a feed that has stopped must not look identical to one that is live.
    status: "complete", scope: owner, snapshot: { ...run, ...snapshotAge(run) },
    account_values: values.results || [], positions, cash_events: cash.results || [],
    broker_position_count: brokerPositionCount, owner_position_count: positions.length,
    allocation_status: allocationState,
    allocation_reason: allocationState === "upstream_absent" ? "Broker positions exist, but no allocation projection has been published." : null,
    allocation_projection_as_of: allocationRow?.as_of || null,
    broker_open_order_count: Number(openOrders.results?.[0]?.count || 0), reconciliation_breaks: breaks.results || [],
  };
}

// Sources whose rate is inferred rather than stated by IBKR. Mirrors INFERRED_FX
// in portfolio-viz.js; both exist because the same rule has to hold whether a
// number is being rendered or being summed into an exposure total.
const INFERRED_FX_SOURCES = new Set(["ibkr_portfolio_translation"]);

/**
 * The position's market value in account base currency, or null when it cannot
 * honestly be stated in base.
 *
 * Never falls back across currencies. A foreign row without a usable rate means
 * "unknown in base", not "same as native" -- reading the native figure as base
 * is what put a JPY 4,842,000 position into a USD gross-exposure total at
 * $4,842,000 and gave it 30% of the book's concentration weight.
 *
 * An inferred rate within 0.01% of parity is treated as no rate at all: it means
 * the collector divided a figure by itself because IBKR returned marketValue in
 * the contract currency. A *stated* rate near parity is fine -- EUR and CHF
 * legitimately trade there.
 */
export function baseMarketValue(row, baseCurrency) {
  const native = row?.native_currency || row?.currency || baseCurrency;
  const value = Number(row?.market_value_base_decimal ?? row?.market_value_decimal);
  if (!Number.isFinite(value)) return null;
  if (native === baseCurrency) return value;
  if (!row?.fx_source || row.fx_source === "fx_unavailable") return null;
  if (INFERRED_FX_SOURCES.has(row.fx_source)) {
    const rate = Number(row.fx_rate_to_base_decimal);
    if (!Number.isFinite(rate) || Math.abs(rate - 1) < 0.0001) return null;
  }
  return Number.isFinite(Number(row?.market_value_base_decimal)) ? Number(row.market_value_base_decimal) : null;
}


// A snapshot older than this is presented as stale rather than as current. Two
// hours is generous for a 30-second publisher and short enough that a feed which
// died overnight is obvious the next morning.
const STALE_AFTER_SECONDS = 7200;

function snapshotAge(run, now = Date.now()) {
  const asOf = Date.parse(run?.as_of || "");
  if (!Number.isFinite(asOf)) return { age_seconds: null, stale: null };
  const age = Math.max(0, Math.round((now - asOf) / 1000));
  return { age_seconds: age, stale: age > STALE_AFTER_SECONDS };
}

export { snapshotAge, STALE_AFTER_SECONDS };
