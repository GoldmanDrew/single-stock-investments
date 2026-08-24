// End-to-end test of the command channel against real SQL.
//
// These routes are almost entirely SQL -- an atomic lease, a guarded UPDATE, an
// upsert -- so testing them against a mock database would test the mock. This
// runs the migrations into an in-memory SQLite and drives the real handlers
// through a D1-shaped adapter, which is close enough that a broken ALTER or a
// bad ON CONFLICT fails here rather than on deploy.

import assert from "node:assert/strict";
import test from "node:test";
import { DatabaseSync } from "node:sqlite";
import { readFileSync, readdirSync } from "node:fs";
import { createHmac, randomUUID } from "node:crypto";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { onRequestPost as claimOrders } from "../functions/api/v2/portfolio/ingest/order-requests/claim.js";
import { onRequestPost as publishOrder } from "../functions/api/v2/portfolio/ingest/order-requests/publish.js";
import { onRequestPost as claimLookups } from "../functions/api/v2/portfolio/ingest/contract-lookups/claim.js";
import { onRequestPost as publishLookup } from "../functions/api/v2/portfolio/ingest/contract-lookups/publish.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const TOKEN = "x".repeat(48);

// --- a D1-shaped adapter over node:sqlite ---------------------------------

function d1(database) {
  const prepare = (sql) => {
    const statement = { sql, binds: [] };
    statement.bind = (...values) => ({ ...statement, binds: values, bind: statement.bind, run, all, first });
    async function run() {
      const result = database.prepare(sql).run(...normalize(this?.binds ?? statement.binds));
      return { meta: { changes: Number(result.changes || 0) } };
    }
    async function all() {
      return { results: database.prepare(sql).all(...normalize(this?.binds ?? statement.binds)) };
    }
    async function first() {
      return database.prepare(sql).get(...normalize(this?.binds ?? statement.binds)) ?? null;
    }
    return { ...statement, run, all, first };
  };
  return { prepare, batch: async (statements) => Promise.all(statements.map((s) => s.run())) };
}

// SQLite rejects booleans and undefined; D1 coerces them.
const normalize = (binds) => binds.map((value) => {
  if (value === undefined) return null;
  if (typeof value === "boolean") return value ? 1 : 0;
  return value;
});

function freshDatabase() {
  const database = new DatabaseSync(":memory:");
  const dir = join(HERE, "migrations");
  for (const file of readdirSync(dir).filter((name) => name.endsWith(".sql")).sort()) {
    const sql = readFileSync(join(dir, file), "utf8");
    for (const statement of splitStatements(sql)) {
      try { database.exec(statement); }
      catch (error) {
        // Earlier migrations reference tables this test does not need; only a
        // failure inside the migration under test should fail the run.
        if (file.startsWith("0012") ) throw new Error(`0012 failed on: ${statement.slice(0, 90)} -- ${error.message}`);
      }
    }
  }
  return database;
}

function splitStatements(sql) {
  // Strip comments before splitting. A `--` comment may legitimately contain a
  // semicolon, and splitting first cuts the enclosing CREATE TABLE in half --
  // which is exactly how this harness first failed, and a real hazard for any
  // migration runner that splits naively.
  //
  // `[^\n]*` rather than `.*`: these files are checked out with CRLF endings on
  // Windows, and `.` does not match `\r`, so a `.*$` strip silently does nothing
  // and every semicolon in a comment comes back.
  return sql
    .replace(/--[^\n]*/g, "")
    .split(";").map((part) => part.trim()).filter(Boolean);
}

async function signedRequest(url, payload) {
  const body = JSON.stringify(payload);
  const timestamp = String(Math.floor(Date.now() / 1000));
  const nonce = randomUUID().replace(/-/g, "");
  const signature = createHmac("sha256", TOKEN).update(`${timestamp}\n${nonce}\n${body}`).digest("hex");
  return new Request(url, {
    method: "POST", body,
    headers: {
      "content-type": "application/json",
      "x-portfolio-timestamp": timestamp,
      "x-portfolio-nonce": nonce,
      "x-portfolio-signature": signature,
    },
  });
}

async function call(handler, path, payload, database) {
  const request = await signedRequest(`https://dash.example${path}`, payload);
  const response = await handler({ request, env: { DB: d1(database), PORTFOLIO_INGEST_TOKEN: TOKEN } });
  return { status: response.status, body: await response.json() };
}

function seedRequest(database, overrides = {}) {
  const row = {
    request_id: randomUUID(), account_alias: "U805366", owner: "drew", strategy: "single_stock",
    conid: 907480285, symbol: "XSP", sec_type: "OPT", action: "BUY", quantity_decimal: "2",
    limit_price_decimal: "5.15", tif: "DAY", outside_rth: 0, mode: "paper", state: "requested",
    created_at: new Date().toISOString(), updated_at: new Date().toISOString(), ...overrides,
  };
  const columns = Object.keys(row);
  database.prepare(`INSERT INTO portfolio_order_requests (${columns.join(",")})
    VALUES (${columns.map(() => "?").join(",")})`).run(...Object.values(row));
  return row.request_id;
}

// --- the migration itself --------------------------------------------------

test("migration 0012 applies and adds every column the routes write", () => {
  const database = freshDatabase();
  const columns = new Set(database.prepare("PRAGMA table_info(portfolio_order_requests)").all().map((row) => row.name));
  for (const column of ["claimed_at", "claimed_by", "expiry", "strike_decimal", "right_code",
    "multiplier_decimal", "trading_class", "exchange", "local_symbol"]) {
    assert.ok(columns.has(column), `0012 must add ${column}`);
  }
  const tables = new Set(database.prepare("SELECT name FROM sqlite_master WHERE type='table'").all().map((row) => row.name));
  assert.ok(tables.has("portfolio_contract_lookups"));
  assert.ok(tables.has("portfolio_contracts"));
});

// --- order claim / publish -------------------------------------------------

test("the route command_poller has always called now answers", async () => {
  const database = freshDatabase();
  const key = seedRequest(database);
  const { status, body } = await call(claimOrders, "/api/v2/portfolio/ingest/order-requests/claim",
    { account_alias: "U805366" }, database);
  assert.equal(status, 200);
  assert.equal(body.requests.length, 1);
  assert.equal(body.requests[0].request_id, key);
});

test("an unsigned claim is refused", async () => {
  const database = freshDatabase();
  seedRequest(database);
  const request = new Request("https://dash.example/x", { method: "POST", body: "{}" });
  const response = await claimOrders({ request, env: { DB: d1(database), PORTFOLIO_INGEST_TOKEN: TOKEN } });
  assert.equal(response.status, 401);
});

test("a second bridge cannot claim a ticket the first one holds", async () => {
  const database = freshDatabase();
  seedRequest(database);
  const first = await call(claimOrders, "/c", { account_alias: "U805366", claimed_by: "bridge-a" }, database);
  const second = await call(claimOrders, "/c", { account_alias: "U805366", claimed_by: "bridge-b" }, database);
  assert.equal(first.body.requests.length, 1);
  assert.equal(second.body.requests.length, 0, "the lease must be exclusive while it is live");
});

test("the hub cannot publish 'approved' -- only a human can", async () => {
  const database = freshDatabase();
  const key = seedRequest(database, { state: "previewed" });
  const { status, body } = await call(publishOrder, "/p",
    { account_alias: "U805366", request_id: key, state: "approved" }, database);
  assert.equal(status, 422);
  assert.match(body.error, /cannot publish state 'approved'/);
  const row = database.prepare("SELECT state FROM portfolio_order_requests WHERE request_id=?").get(key);
  assert.equal(row.state, "previewed", "a refused publish must not move the ticket");
});

test("publishing a preview stores the fingerprint and releases the lease", async () => {
  const database = freshDatabase();
  const key = seedRequest(database);
  await call(claimOrders, "/c", { account_alias: "U805366" }, database);
  const { status } = await call(publishOrder, "/p", {
    account_alias: "U805366", request_id: key, state: "previewed",
    contract_fingerprint: "XSP 270129P00540000 | OPT | 540 P | 20270129 | 100x | SMART/USD | conId 907480285",
    local_symbol: "XSP 270129P00540000", expiry: "20270129", strike_decimal: "540", right_code: "P",
    preview: { quote: { bid: "5.10", ask: "5.20" } },
  }, database);
  assert.equal(status, 200);
  const row = database.prepare("SELECT * FROM portfolio_order_requests WHERE request_id=?").get(key);
  assert.equal(row.state, "previewed");
  assert.match(row.contract_fingerprint, /540 P/);
  assert.equal(row.right_code, "P");
  assert.equal(row.claimed_at, null, "publishing releases the lease");
  assert.ok(JSON.parse(row.preview_json).quote.ask);
});

test("a late broker status cannot resurrect a filled ticket", async () => {
  const database = freshDatabase();
  const key = seedRequest(database, { state: "filled" });
  const { status, body } = await call(publishOrder, "/p",
    { account_alias: "U805366", request_id: key, state: "acknowledged" }, database);
  assert.equal(status, 200);
  assert.equal(body.ignored, true);
  const row = database.prepare("SELECT state FROM portfolio_order_requests WHERE request_id=?").get(key);
  assert.equal(row.state, "filled");
});

test("a replayed signature is rejected", async () => {
  const database = freshDatabase();
  seedRequest(database);
  const request = await signedRequest("https://dash.example/c", { account_alias: "U805366" });
  const env = { DB: d1(database), PORTFOLIO_INGEST_TOKEN: TOKEN };
  const first = await claimOrders({ request: request.clone(), env });
  const second = await claimOrders({ request, env });
  assert.equal(first.status, 200);
  assert.equal(second.status, 409);
});

// --- contract lookups ------------------------------------------------------

function seedLookup(database, overrides = {}) {
  const row = {
    lookup_id: randomUUID(), account_alias: "U805366", owner: "drew", kind: "contract",
    symbol: "MSFT", sec_type: "STK", state: "requested",
    created_at: new Date().toISOString(), updated_at: new Date().toISOString(), ...overrides,
  };
  const columns = Object.keys(row);
  database.prepare(`INSERT INTO portfolio_contract_lookups (${columns.join(",")})
    VALUES (${columns.map(() => "?").join(",")})`).run(...Object.values(row));
  return row.lookup_id;
}

test("a resolved lookup seeds the contract cache", async () => {
  const database = freshDatabase();
  const key = seedLookup(database);
  const { status, body } = await call(publishLookup, "/lp", {
    account_alias: "U805366", lookup_id: key, state: "resolved",
    matches: [{ conId: 272093, symbol: "MSFT", secType: "STK", currency: "USD", localSymbol: "MSFT" }],
  }, database);
  assert.equal(status, 200);
  assert.equal(body.cached, 1);
  const cached = database.prepare("SELECT * FROM portfolio_contracts WHERE conid=?").get(272093);
  assert.equal(cached.symbol, "MSFT");
  assert.equal(cached.source, "lookup");
});

test("resolving the same contract twice updates rather than duplicates", async () => {
  const database = freshDatabase();
  for (const description of ["Microsoft", "Microsoft Corp"]) {
    const key = seedLookup(database);
    await call(publishLookup, "/lp", {
      account_alias: "U805366", lookup_id: key, state: "resolved",
      matches: [{ conId: 272093, symbol: "MSFT", secType: "STK", longName: description }],
    }, database);
  }
  const rows = database.prepare("SELECT * FROM portfolio_contracts WHERE conid=?").all(272093);
  assert.equal(rows.length, 1, "conid is the primary key; a re-resolve is an upsert");
  assert.equal(rows[0].description, "Microsoft Corp");
});

test("a 'resolved' lookup with no matches is refused as a disguised failure", async () => {
  const database = freshDatabase();
  const key = seedLookup(database);
  const { status, body } = await call(publishLookup, "/lp",
    { account_alias: "U805366", lookup_id: key, state: "resolved", matches: [] }, database);
  assert.equal(status, 422);
  assert.match(body.error, /at least one match/);
});

test("claiming a lookup marks it resolving so a second bridge skips it", async () => {
  const database = freshDatabase();
  seedLookup(database);
  const first = await call(claimLookups, "/lc", { account_alias: "U805366", claimed_by: "bridge-a" }, database);
  const second = await call(claimLookups, "/lc", { account_alias: "U805366", claimed_by: "bridge-b" }, database);
  assert.equal(first.body.lookups.length, 1);
  assert.equal(first.body.lookups[0].state, "resolving");
  assert.equal(second.body.lookups.length, 0);
});

test("a failed lookup records why and stores no matches", async () => {
  const database = freshDatabase();
  const key = seedLookup(database, { symbol: "ZZZZ" });
  await call(publishLookup, "/lp",
    { account_alias: "U805366", lookup_id: key, state: "failed", error: "IBKR returned no contract for ZZZZ." }, database);
  const row = database.prepare("SELECT * FROM portfolio_contract_lookups WHERE lookup_id=?").get(key);
  assert.equal(row.state, "failed");
  assert.equal(row.matches_json, null);
  assert.match(row.error, /ZZZZ/);
});

test("seeding the cache from a big book writes every holding, not the first 400", async () => {
  const { normalizeMatches, rememberContracts } = await import("../functions/_lib/contracts.js");
  const database = freshDatabase();
  const positions = Array.from({ length: 900 }, (_, index) => ({
    conid: 100000 + index, symbol: `SYM${index}`, sec_type: "STK", currency: "USD",
  }));
  // The default bound is a picker concern; forgetting 500 holdings would make the
  // symbol box quietly incomplete, which is far harder to notice than a slow one.
  const written = await rememberContracts(d1(database), normalizeMatches(positions, positions.length), "position");
  assert.equal(written, 900);
  const count = database.prepare("SELECT COUNT(*) AS n FROM portfolio_contracts").get();
  assert.equal(count.n, 900);
});

test("the default bound still applies to hub-published matches", async () => {
  const { normalizeMatches } = await import("../functions/_lib/contracts.js");
  const raw = Array.from({ length: 900 }, (_, index) => ({ conId: 200000 + index, symbol: "X", secType: "OPT" }));
  assert.equal(normalizeMatches(raw).length, 400, "a picker must stay bounded by default");
});
