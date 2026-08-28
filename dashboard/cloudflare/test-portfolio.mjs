import assert from "node:assert/strict";
import test from "node:test";

import { validateAccountSnapshot, validateFlexEod, validateStrategySnapshot, verifyPortfolioHmac } from "../functions/_lib/portfolio.js";

function accountSnapshot() {
  return {
    schema_version: "account_snapshot.v1", source_run_id: "run-1", account_alias: "paper-primary",
    as_of: "2026-08-17T14:00:00Z", complete: true, base_currency: "USD", account_values: [],
    positions: [{ conid: 101, symbol: "TEST", sec_type: "STK", currency: "USD", native_currency: "USD", base_currency: "USD", quantity: "10", quantity_unit: "shares" }],
  };
}

test("canonical position identity requires conId and decimal quantity", () => {
  assert.equal(validateAccountSnapshot(accountSnapshot()).positions[0].conid, 101);
  const bad = accountSnapshot();
  bad.positions[0].quantity = "ten";
  assert.throws(() => validateAccountSnapshot(bad), /canonical position/);
});

test("non-base positions require explicit native/base conversion lineage", () => {
  const payload = accountSnapshot();
  payload.positions[0] = {
    ...payload.positions[0], symbol: "3905", currency: "JPY", native_currency: "JPY", mark: "1859",
    market_value: "34982.2902", market_value_native: "5577000", market_value_base: "34982.2902",
    fx_rate_to_base: "0.00627206118", fx_as_of: payload.as_of, fx_source: "ibkr_portfolio_translation",
  };
  assert.equal(validateAccountSnapshot(payload).positions[0].market_value_native, "5577000");
  delete payload.positions[0].fx_source;
  assert.throws(() => validateAccountSnapshot(payload), /native\/base FX/);
});

function untranslatedJpyPosition(overrides = {}) {
  // IBKR implies the rate from marketValue/marketPrice. Without a TSE market-data
  // permission the mark comes back 0, so the ratio is indeterminate.
  return {
    conid: 101, symbol: "3905", sec_type: "STK", currency: "JPY", native_currency: "JPY",
    base_currency: "USD", quantity: "100", quantity_unit: "shares", mark: "0",
    market_value: "0", market_value_native: "0", market_value_base: "0",
    fx_rate_to_base: null, fx_as_of: null, fx_source: "fx_unavailable",
    quality: "estimated", ...overrides,
  };
}

test("an underivable FX rate degrades its own row instead of failing the snapshot", () => {
  // Regression: this rejected the whole envelope, so one unquotable JPY position
  // took the entire account offline rather than showing as incomplete.
  const payload = accountSnapshot();
  payload.positions[0] = untranslatedJpyPosition();
  assert.equal(validateAccountSnapshot(payload).positions[0].fx_source, "fx_unavailable");

  const flat = accountSnapshot();
  flat.positions[0] = untranslatedJpyPosition({ quantity: "0", quality: "live" });
  assert.equal(validateAccountSnapshot(flat).positions.length, 1);
});

test("an untranslated position carrying value cannot claim live quality", () => {
  const payload = accountSnapshot();
  payload.positions[0] = untranslatedJpyPosition({
    market_value: "34982.2902", market_value_native: "5577000",
    market_value_base: "34982.2902", quality: "live",
  });
  assert.throws(() => validateAccountSnapshot(payload), /estimated or unknown/);
});

test("FX provenance must be a recognised source with a usable rate", () => {
  const unknown = accountSnapshot();
  unknown.positions[0] = untranslatedJpyPosition({ fx_source: "guessed" });
  assert.throws(() => validateAccountSnapshot(unknown), /native\/base FX/);

  const rateless = accountSnapshot();
  rateless.positions[0] = untranslatedJpyPosition({
    fx_source: "ibkr_portfolio_translation", fx_rate_to_base: null,
  });
  assert.throws(() => validateAccountSnapshot(rateless), /without a usable rate/);
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

test("a snapshot is dated so a stopped feed cannot read as a live one", async () => {
  const { snapshotAge, STALE_AFTER_SECONDS } = await import("../functions/_lib/portfolio.js");
  const now = Date.parse("2026-08-25T16:00:00Z");

  const fresh = snapshotAge({ as_of: "2026-08-25T15:59:00Z" }, now);
  assert.equal(fresh.stale, false);
  assert.equal(fresh.age_seconds, 60);

  // The collector was disabled 2026-08-25; this query keeps returning the same
  // run indefinitely, so age is the only thing separating it from live data.
  const old = snapshotAge({ as_of: "2026-08-22T15:00:00Z" }, now);
  assert.equal(old.stale, true);
  assert.ok(old.age_seconds > STALE_AFTER_SECONDS);

  // An unparseable stamp is unknown, never assumed fresh.
  assert.deepEqual(snapshotAge({ as_of: "" }, now), { age_seconds: null, stale: null });
});
