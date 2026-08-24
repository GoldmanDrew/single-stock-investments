import assert from "node:assert/strict";
import test from "node:test";

import {
  LOOKUP_KINDS,
  normalizeMatches,
  validateContractLookup,
} from "../functions/_lib/contracts.js";
import {
  exchangeToday,
  validateOptionIdentity,
  validateOrderRequest,
} from "../functions/_lib/order-requests.js";

// A Monday well clear of any boundary, so "today" is unambiguous in both zones.
const MIDDAY_ET = new Date("2026-08-24T16:00:00Z");

test("a lookup is a question, never a conId", () => {
  const lookup = validateContractLookup({ symbol: "msft" }, "drew");
  assert.equal(lookup.symbol, "MSFT");
  assert.equal(lookup.sec_type, "STK");
  assert.equal(lookup.owner, "drew");
  assert.ok(!("conid" in lookup), "the browser never states a contract id");
});

test("owner comes from the verified login, not the body", () => {
  assert.throws(() => validateContractLookup({ symbol: "MSFT" }, null), /not mapped to a portfolio owner/);
});

test("ETF is refused as a security type wherever it appears", () => {
  // IBKR files ETFs as STK. A ticket carrying "ETF" fingerprints an instrument
  // that does not exist, so the qualified contract and the approved string
  // would describe different things.
  assert.throws(() => validateContractLookup({ symbol: "SPY", sec_type: "ETF" }, "drew"), /STK or OPT/);
  assert.throws(() => validateOrderRequest({
    conid: 756733, action: "BUY", quantity: "10", limit_price: "500", symbol: "SPY", sec_type: "ETF",
  }, "drew"), /STK or OPT/);
});

test("a single option contract needs all three coordinates", () => {
  assert.throws(() => validateContractLookup({
    kind: "option_contract", sec_type: "OPT", symbol: "XSP", expiry: "20270129", right: "P",
  }, "drew"), /expiry, strike and right/);
  const complete = validateContractLookup({
    kind: "option_contract", sec_type: "OPT", symbol: "XSP",
    expiry: "20270129", strike: "540", right: "p",
  }, "drew");
  assert.equal(complete.right, "P");
  assert.equal(complete.strike, "540");
});

test("chain lookups are option-only and kinds are closed", () => {
  assert.throws(() => validateContractLookup({ kind: "option_chain", sec_type: "STK", symbol: "XSP" }, "drew"), /require sec_type OPT/);
  assert.throws(() => validateContractLookup({ kind: "everything", symbol: "XSP" }, "drew"), /Unsupported lookup kind/);
  assert.deepEqual([...LOOKUP_KINDS].sort(), ["contract", "option_chain", "option_contract"]);
});

test("normalizeMatches drops anything without a real conId and never invents a multiplier", () => {
  const matches = normalizeMatches([
    { conId: 907480285, symbol: "XSP", localSymbol: "XSP   270129P00540000", secType: "OPT", strike: 540, right: "P" },
    { conId: 0, symbol: "BAD" },
    { symbol: "ALSO BAD" },
  ]);
  assert.equal(matches.length, 1);
  assert.equal(matches[0].conid, 907480285);
  // Padding collapsed so the fingerprint and the picker agree on the string.
  assert.equal(matches[0].local_symbol, "XSP 270129P00540000");
  assert.equal(matches[0].multiplier_decimal, null, "an absent multiplier stays absent");
});

test("same-day expiry is refused outright", () => {
  const today = exchangeToday(MIDDAY_ET);
  assert.throws(() => validateOptionIdentity({
    expiry: today, strike: "540", right: "P", quantity: "1",
  }, "OPT", MIDDAY_ET), /0DTE belongs to the SPX strategy/);
});

test("an already-expired option is refused with a different reason", () => {
  assert.throws(() => validateOptionIdentity({
    expiry: "20200101", strike: "540", right: "P", quantity: "1",
  }, "OPT", MIDDAY_ET), /already expired/);
});

test("option quantity must be whole contracts", () => {
  assert.throws(() => validateOptionIdentity({
    expiry: "20270129", strike: "540", right: "P", quantity: "1.5",
  }, "OPT", MIDDAY_ET), /whole number of contracts/);
});

test("options may not be routed outside regular hours", () => {
  assert.throws(() => validateOptionIdentity({
    expiry: "20270129", strike: "540", right: "P", quantity: "1", outside_rth: true,
  }, "OPT", MIDDAY_ET), /outside regular trading hours/);
});

test("option fields are refused on a stock ticket", () => {
  assert.throws(() => validateOptionIdentity({ expiry: "20270129" }, "STK", MIDDAY_ET), /only applies to an option/);
  const stock = validateOptionIdentity({}, "STK", MIDDAY_ET);
  assert.equal(stock.expiry, null);
  assert.equal(stock.strike, null);
});

test("a complete option ticket carries its identity through", () => {
  const ticket = validateOrderRequest({
    conid: 907480285, action: "BUY", quantity: "2", limit_price: "5.15",
    symbol: "XSP", sec_type: "OPT", expiry: "20270129", strike: "540", right: "p",
    multiplier: "100", trading_class: "xsp", local_symbol: "XSP   270129P00540000",
    mode: "paper",
  }, "drew");
  assert.equal(ticket.sec_type, "OPT");
  assert.equal(ticket.right, "P");
  assert.equal(ticket.trading_class, "XSP");
  assert.equal(ticket.local_symbol, "XSP 270129P00540000");
  assert.equal(ticket.owner, "drew");
});

test("exchangeToday reads the New York calendar, not the worker's UTC date", () => {
  // 01:30 UTC on the 25th is still the evening of the 24th in New York. Using
  // the UTC date here would call a next-session expiry "today" and refuse it.
  assert.equal(exchangeToday(new Date("2026-08-25T01:30:00Z")), "20260824");
  assert.equal(exchangeToday(new Date("2026-08-24T16:00:00Z")), "20260824");
});
