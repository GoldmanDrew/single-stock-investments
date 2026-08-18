import assert from "node:assert/strict";
import test from "node:test";

import { validateAccountSnapshot, validateFlexEod, validateStrategySnapshot, verifyPortfolioHmac } from "../functions/_lib/portfolio.js";

function accountSnapshot() {
  return {
    schema_version: "account_snapshot.v1", source_run_id: "run-1", account_alias: "paper-primary",
    as_of: "2026-08-17T14:00:00Z", complete: true, account_values: [],
    positions: [{ conid: 101, symbol: "TEST", sec_type: "STK", currency: "USD", quantity: "10" }],
  };
}

test("canonical position identity requires conId and decimal quantity", () => {
  assert.equal(validateAccountSnapshot(accountSnapshot()).positions[0].conid, 101);
  const bad = accountSnapshot();
  bad.positions[0].quantity = "ten";
  assert.throws(() => validateAccountSnapshot(bad), /canonical position/);
});

test("strategy envelope retains producer reconciliation metadata", () => {
  const payload = { schema_version: "strategy_snapshot.v1", producer: "ls_risk", source_run_id: "ls-1", as_of: "2026-08-17T14:00:00Z", complete: true, rows: [] };
  assert.equal(validateStrategySnapshot(payload).producer, "ls_risk");
});

test("Flex completed-session envelope requires an explicit session date", () => {
  const payload = { schema_version: "flex_eod.v1", source_run_id: "flex-1", account_alias: "paper-primary", session_date: "2026-08-16", as_of: "2026-08-17T08:00:00Z", positions: [], trades: [], cash_transactions: [], nav_rows: [] };
  assert.equal(validateFlexEod(payload).session_date, "2026-08-16");
  assert.throws(() => validateFlexEod({ ...payload, session_date: "today" }), /flex_eod/);
});

test("portfolio ingest signature is body-bound", async () => {
  const secret = "this-is-a-test-secret-that-is-long-enough";
  const timestamp = String(Math.floor(Date.now() / 1000));
  const nonce = "0123456789abcdef0123456789abcdef";
  const body = new TextEncoder().encode('{"ok":true}');
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const prefix = new TextEncoder().encode(`${timestamp}\n${nonce}\n`);
  const message = new Uint8Array(prefix.length + body.length); message.set(prefix); message.set(body, prefix.length);
  const signature = [...new Uint8Array(await crypto.subtle.sign("HMAC", key, message))].map((x) => x.toString(16).padStart(2, "0")).join("");
  const request = new Request("https://internal.example/api", { headers: { "x-portfolio-timestamp": timestamp, "x-portfolio-nonce": nonce, "x-portfolio-signature": signature } });
  assert.deepEqual(await verifyPortfolioHmac(request, { PORTFOLIO_INGEST_TOKEN: secret }, body), { timestamp, nonce });
  assert.equal(await verifyPortfolioHmac(request, { PORTFOLIO_INGEST_TOKEN: secret }, new TextEncoder().encode("changed")), false);
});

test("open orders are validated without mutating storage", () => {
  const payload = accountSnapshot();
  payload.open_orders = [{ order_id: 7, ownership: "foreign" }];
  assert.equal(validateAccountSnapshot(payload).open_orders[0].ownership, "foreign");
  const bad = accountSnapshot();
  bad.open_orders = [{ order_id: 7, ownership: "shared" }];
  assert.throws(() => validateAccountSnapshot(bad), /open-order/);
});

test("B5 product snapshots cannot broker-reconcile", () => {
  const payload = {
    schema_version: "strategy_snapshot.v1", producer: "ls_bucket5_product", source_run_id: "p1",
    as_of: "2026-08-17T14:00:00Z", complete: true,
    rows: [{ row_id: "r1", reconciliation_role: "research_only", exposure_basis: "research" }],
  };
  assert.equal(validateStrategySnapshot(payload).producer, "ls_bucket5_product");
  payload.rows[0].conid = 12;
  assert.throws(() => validateStrategySnapshot(payload), /cannot broker-reconcile/);
});
