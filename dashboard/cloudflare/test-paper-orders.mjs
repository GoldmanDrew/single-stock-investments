import assert from "node:assert/strict";
import test from "node:test";

import {
  portfolioOrderOwner,
  requirePaperOrderRequest,
  validatePaperOrder,
} from "../functions/_lib/paper-orders.js";
import { onRequestGet, onRequestPost } from "../functions/api/v2/portfolio/paper-orders.js";
import { onRequestDelete } from "../functions/api/v2/portfolio/paper-orders/[id].js";

const validOrder = {
  client_request_id: "8bdc7ac6-47d8-4cab-a420-bc48258fb74f",
  symbol: "MSFT",
  sec_type: "STK",
  conid: 272093,
  side: "BUY",
  quantity: "10",
  limit_price: "415.25",
  order_type: "LMT",
  tif: "DAY",
  rationale: "Paper entry after committee review.",
};

class FakeStatement {
  constructor(database, sql) {
    this.database = database;
    this.sql = sql.replace(/\s+/g, " ").trim();
    this.args = [];
  }

  bind(...args) {
    this.args = args;
    return this;
  }

  async all() {
    if (this.sql.includes("FROM portfolio_paper_orders") && this.sql.includes("WHERE owner=?")) {
      const rows = [...this.database.orders.values()].filter((row) => row.owner === this.args[0]);
      return { results: rows.sort((a, b) => b.created_at.localeCompare(a.created_at)) };
    }
    throw new Error(`Unsupported fake all: ${this.sql}`);
  }

  async first() {
    if (this.sql.includes("FROM portfolio_paper_orders") && this.sql.includes("paper_order_id=? AND owner=?")) {
      const row = this.database.orders.get(this.args[0]);
      return row?.owner === this.args[1] ? { ...row } : null;
    }
    throw new Error(`Unsupported fake first: ${this.sql}`);
  }

  async run() {
    if (this.sql.startsWith("INSERT OR IGNORE INTO portfolio_paper_orders")) {
      const [paper_order_id, owner, actor_email, actor_subject, symbol, sec_type, conid, side,
        quantity_decimal, limit_price_decimal, order_type, tif, currency, rationale, mode,
        transmitted, status, created_at, updated_at] = this.args;
      if (this.database.orders.has(paper_order_id)) return { meta: { changes: 0 } };
      this.database.orders.set(paper_order_id, {
        paper_order_id, owner, actor_email, actor_subject, symbol, sec_type, conid, side,
        quantity_decimal, limit_price_decimal, order_type, tif, currency, rationale, mode,
        transmitted, status, created_at, updated_at,
      });
      return { meta: { changes: 1 } };
    }
    if (this.sql.startsWith("INSERT OR IGNORE INTO portfolio_paper_order_events")) {
      const [event_id, paper_order_id, owner, actor_email, event_type, payload_json, created_at] = this.args;
      if (this.database.events.has(event_id)) return { meta: { changes: 0 } };
      this.database.events.set(event_id, { event_id, paper_order_id, owner, actor_email, event_type, payload_json, created_at });
      return { meta: { changes: 1 } };
    }
    if (this.sql.startsWith("UPDATE portfolio_paper_orders")) {
      const [updated_at, paperOrderId, owner] = this.args;
      const row = this.database.orders.get(paperOrderId);
      if (!row || row.owner !== owner || row.status !== "paper_queued") return { meta: { changes: 0 } };
      this.database.orders.set(paperOrderId, { ...row, status: "paper_cancelled", updated_at });
      return { meta: { changes: 1 } };
    }
    throw new Error(`Unsupported fake run: ${this.sql}`);
  }
}

class FakeDatabase {
  constructor() {
    this.orders = new Map();
    this.events = new Map();
  }

  prepare(sql) {
    return new FakeStatement(this, sql);
  }

  async batch(statements) {
    const results = [];
    for (const statement of statements) results.push(await statement.run());
    return results;
  }
}

function developmentEnv(owner, database) {
  return { PORTFOLIO_AUTH_MODE: "development", PORTFOLIO_DEVELOPMENT_OWNER: owner, DB: database };
}

function paperRequest(method, path, body) {
  return new Request(`http://localhost${path}`, {
    method,
    headers: {
      "content-type": "application/json",
      "origin": "http://localhost",
      "sec-fetch-site": "same-origin",
      "x-paper-order-mode": "paper",
    },
    body: body == null ? undefined : JSON.stringify(body),
  });
}

test("maps verified Access emails to exactly one order owner", () => {
  const env = {
    PORTFOLIO_DREW_ACCESS_EMAILS: "Drew@example.com, drew.alt@example.com",
    PORTFOLIO_MICHAEL_ACCESS_EMAILS: "michael@example.com",
  };
  assert.equal(portfolioOrderOwner({ email: "drew@example.com" }, env), "drew");
  assert.equal(portfolioOrderOwner({ email: "MICHAEL@example.com" }, env), "michael");
  assert.equal(portfolioOrderOwner({ email: "viewer@example.com" }, env), null);
  assert.equal(portfolioOrderOwner({ service_token: "collector" }, env), null);
});

test("fails closed when an Access email is assigned to both owners", () => {
  const env = {
    PORTFOLIO_DREW_ACCESS_EMAILS: "same@example.com",
    PORTFOLIO_MICHAEL_ACCESS_EMAILS: "same@example.com",
  };
  assert.throws(() => portfolioOrderOwner({ email: "same@example.com" }, env), /more than one owner/);
});

test("development login remains read-only unless a separate owner is configured", () => {
  assert.equal(portfolioOrderOwner({ email: "local-development" }, {}), null);
  assert.equal(portfolioOrderOwner({ email: "local-development" }, { PORTFOLIO_DEVELOPMENT_OWNER: "drew" }), "drew");
});

test("Access service tokens cannot inherit a human order role", () => {
  const viewer = { email: "drew@example.com", service_token: "dashboard-collector" };
  assert.equal(portfolioOrderOwner(viewer, { PORTFOLIO_DREW_ACCESS_EMAILS: "drew@example.com" }), null);
});

test("normalizes a valid paper limit ticket and derives its owner", () => {
  assert.deepEqual(validatePaperOrder(validOrder, "drew"), {
    client_request_id: validOrder.client_request_id,
    owner: "drew",
    symbol: "MSFT",
    sec_type: "STK",
    conid: 272093,
    side: "BUY",
    quantity_decimal: "10",
    limit_price_decimal: "415.25",
    order_type: "LMT",
    tif: "DAY",
    currency: "USD",
    rationale: validOrder.rationale,
  });
});

test("rejects cross-owner, live-mode, and transmitted ticket injection", () => {
  assert.throws(() => validatePaperOrder({ ...validOrder, owner: "michael" }, "drew"), /only queue orders for the drew/);
  assert.throws(() => validatePaperOrder({ ...validOrder, mode: "live" }, "drew"), /paper-only/);
  assert.throws(() => validatePaperOrder({ ...validOrder, transmitted: true }, "drew"), /cannot be transmitted/);
});

test("requires exact contract identity and valid positive paper order values", () => {
  assert.throws(() => validatePaperOrder({ ...validOrder, conid: "" }, "drew"), /contract ID is required/);
  assert.throws(() => validatePaperOrder({ ...validOrder, quantity: "0" }, "drew"), /outside the supported range/);
  assert.throws(() => validatePaperOrder({ ...validOrder, limit_price: "market" }, "drew"), /positive number/);
  assert.throws(() => validatePaperOrder({ ...validOrder, sec_type: "OPT", quantity: "1.5" }, "drew"), /whole number/);
  assert.throws(() => validatePaperOrder({ ...validOrder, tif: "GTC" }, "drew"), /DAY orders only/);
});

test("requires a same-origin JSON request with an explicit paper header", () => {
  const request = new Request("https://dashboard.example/api/v2/portfolio/paper-orders", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "origin": "https://dashboard.example",
      "sec-fetch-site": "same-origin",
      "x-paper-order-mode": "paper",
    },
    body: "{}",
  });
  assert.doesNotThrow(() => requirePaperOrderRequest(request));
  assert.throws(() => requirePaperOrderRequest(new Request(request.url, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "origin": "https://attacker.example",
      "x-paper-order-mode": "paper",
    },
    body: "{}",
  })), /must come from this dashboard/);
});

test("endpoint derives Drew and Michael owners and lists only the logged-in owner's tickets", async () => {
  const database = new FakeDatabase();
  const drewResponse = await onRequestPost({
    request: paperRequest("POST", "/api/v2/portfolio/paper-orders", validOrder),
    env: developmentEnv("drew", database),
  });
  assert.equal(drewResponse.status, 201);
  assert.equal((await drewResponse.json()).order.owner, "drew");

  const michaelOrder = { ...validOrder, client_request_id: "8d924dfc-1e4f-4ac8-9f89-2749cfdd4625", symbol: "JPM", conid: 8719 };
  const michaelResponse = await onRequestPost({
    request: paperRequest("POST", "/api/v2/portfolio/paper-orders", michaelOrder),
    env: developmentEnv("michael", database),
  });
  assert.equal(michaelResponse.status, 201);
  assert.equal((await michaelResponse.json()).order.owner, "michael");

  const drewList = await onRequestGet({ request: new Request("http://localhost/api/v2/portfolio/paper-orders"), env: developmentEnv("drew", database) });
  const drewPayload = await drewList.json();
  assert.deepEqual(drewPayload.orders.map((row) => row.owner), ["drew"]);
  assert.equal(drewPayload.viewer.order_owner, "drew");
});

test("endpoint rejects owner injection and keeps the other owner's order undiscoverable", async () => {
  const database = new FakeDatabase();
  const injected = await onRequestPost({
    request: paperRequest("POST", "/api/v2/portfolio/paper-orders", { ...validOrder, owner: "michael" }),
    env: developmentEnv("drew", database),
  });
  assert.equal(injected.status, 403);
  assert.equal(database.orders.size, 0);

  await onRequestPost({
    request: paperRequest("POST", "/api/v2/portfolio/paper-orders", validOrder),
    env: developmentEnv("drew", database),
  });
  const crossOwnerCancel = await onRequestDelete({
    request: paperRequest("DELETE", `/api/v2/portfolio/paper-orders/${validOrder.client_request_id}`, {}),
    env: developmentEnv("michael", database),
    params: { id: validOrder.client_request_id },
  });
  assert.equal(crossOwnerCancel.status, 404);
  assert.equal(database.orders.get(validOrder.client_request_id).status, "paper_queued");
});

test("paper ticket creation is idempotent and cancellation writes only paper state", async () => {
  const database = new FakeDatabase();
  const context = () => ({
    request: paperRequest("POST", "/api/v2/portfolio/paper-orders", validOrder),
    env: developmentEnv("drew", database),
  });
  assert.equal((await onRequestPost(context())).status, 201);
  assert.equal((await onRequestPost(context())).status, 200);
  assert.equal(database.orders.size, 1);

  const conflict = await onRequestPost({
    request: paperRequest("POST", "/api/v2/portfolio/paper-orders", { ...validOrder, limit_price: "416" }),
    env: developmentEnv("drew", database),
  });
  assert.equal(conflict.status, 409);

  const cancelled = await onRequestDelete({
    request: paperRequest("DELETE", `/api/v2/portfolio/paper-orders/${validOrder.client_request_id}`, {}),
    env: developmentEnv("drew", database),
    params: { id: validOrder.client_request_id },
  });
  assert.equal(cancelled.status, 200);
  const payload = await cancelled.json();
  assert.equal(payload.order.status, "paper_cancelled");
  assert.equal(payload.order.transmitted, 0);
  assert.equal(database.events.get(`paper-cancelled:${validOrder.client_request_id}`).event_type, "paper_cancelled");
});
