import assert from "node:assert/strict";
import test from "node:test";

import { ROLLING_WINDOWS, dailyCloses, rollingStats } from "../functions/_lib/performance.js";

const day = (date, value) => ({ as_of: `${date}T20:00:00Z`, nav_decimal: String(value) });

function syntheticDaily(days, startValue, dailyReturn) {
  const rows = [];
  let value = startValue;
  for (let index = 0; index < days; index += 1) {
    const stamp = new Date(Date.parse("2016-01-01T00:00:00Z") + index * 86_400_000).toISOString().slice(0, 10);
    rows.push({ date: stamp, value });
    value *= 1 + dailyReturn;
  }
  return rows;
}

// ------------------------------------------------------------ daily collapse

test("intraday ticks collapse to one close per calendar day", () => {
  // The collector writes every 30s. Treating those as daily returns would
  // measure the polling interval, not the book.
  const series = [
    day("2026-08-18", 100), { as_of: "2026-08-18T20:00:30Z", nav_decimal: "101" },
    day("2026-08-19", 102), { as_of: "2026-08-19T21:00:00Z", nav_decimal: "103" },
  ];
  const daily = dailyCloses(series);
  assert.equal(daily.length, 2);
  assert.deepEqual(daily.map((row) => row.value), [101, 103], "the last observation of each day is the close");
});

test("non-positive and unparseable NAV rows are dropped", () => {
  const daily = dailyCloses([
    day("2026-08-18", 100), day("2026-08-19", 0), day("2026-08-20", -5),
    { as_of: "garbage", nav_decimal: "120" }, { as_of: "2026-08-21T20:00:00Z", nav_decimal: "abc" },
  ]);
  assert.deepEqual(daily.map((row) => row.date), ["2026-08-18"]);
});

// ------------------------------------------------ the history that exists today

test("six days of history cannot produce any rolling window", () => {
  // The real state on 2026-08-25: NAV first recorded 2026-08-18.
  const series = ["2026-08-18", "2026-08-19", "2026-08-20", "2026-08-21", "2026-08-24", "2026-08-25"]
    .map((date, index) => day(date, 12_000_000 - index * 10_000));
  const daily = dailyCloses(series);
  for (const window of ROLLING_WINDOWS) {
    const stats = rollingStats(daily, window);
    assert.equal(stats.available, false, `${window.label} must not be computed from 8 days`);
    assert.match(stats.null_reason, /more days of NAV history/);
    assert.ok(stats.missing_days > 300, "the shortfall is stated, not just the failure");
  }
});

test("an empty history says so rather than dividing by zero", () => {
  const stats = rollingStats([], ROLLING_WINDOWS[0]);
  assert.equal(stats.available, false);
  assert.equal(stats.observed_days, 0);
  assert.match(stats.null_reason, /no NAV history/);
});

// --------------------------------------------------------------- the maths

test("CAGR over a full window recovers the compounded rate", () => {
  // 10% a year for two years, daily-compounded.
  const dailyReturn = Math.pow(1.1, 1 / 365.25) - 1;
  const daily = syntheticDaily(760, 1_000_000, dailyReturn);
  const stats = rollingStats(daily, { label: "2 years", years: 2 });
  assert.equal(stats.available, true);
  assert.ok(Math.abs(stats.nav_cagr - 0.10) < 0.005, `expected ~10%, got ${stats.nav_cagr}`);
});

test("a monotonic series has no drawdown and therefore no Calmar", () => {
  const daily = syntheticDaily(400, 1_000_000, 0.0002);
  const stats = rollingStats(daily, { label: "1 year", years: 1 });
  assert.equal(stats.max_drawdown, 0);
  assert.equal(stats.calmar, null, "Infinity is not a ratio worth printing");
});

test("max drawdown is peak-to-trough inside the window", () => {
  const daily = [];
  for (let index = 0; index < 400; index += 1) {
    const stamp = new Date(Date.parse("2016-01-01T00:00:00Z") + index * 86_400_000).toISOString().slice(0, 10);
    // Rise to 200 by day 200, fall to 150, recover to 210.
    const value = index <= 200 ? 100 + index / 2 : index <= 300 ? 200 - (index - 200) / 2 : 150 + (index - 300) * 0.6;
    daily.push({ date: stamp, value });
  }
  const stats = rollingStats(daily, { label: "1 year", years: 1 });
  assert.ok(stats.max_drawdown < -0.2 && stats.max_drawdown > -0.3, `got ${stats.max_drawdown}`);
  assert.ok(stats.calmar != null);
});

test("volatility is annualised from daily returns, not from raw observations", () => {
  const daily = [];
  for (let index = 0; index < 400; index += 1) {
    const stamp = new Date(Date.parse("2016-01-01T00:00:00Z") + index * 86_400_000).toISOString().slice(0, 10);
    daily.push({ date: stamp, value: 100 * (1 + (index % 2 ? 0.01 : -0.01)) });
  }
  const stats = rollingStats(daily, { label: "1 year", years: 1 });
  // A +/-1% daily alternation is ~2% daily sigma -> ~32% annualised.
  assert.ok(stats.volatility > 0.2 && stats.volatility < 0.5, `got ${stats.volatility}`);
});

test("a flat series reports zero volatility rather than null", () => {
  const daily = syntheticDaily(400, 1_000_000, 0);
  const stats = rollingStats(daily, { label: "1 year", years: 1 });
  assert.equal(stats.volatility, 0);
  assert.equal(stats.nav_cagr, 0);
});

test("only the requested window is measured, not all of history", () => {
  const daily = syntheticDaily(2000, 1_000_000, 0.0001);
  const oneYear = rollingStats(daily, { label: "1 year", years: 1 });
  assert.equal(oneYear.available, true);
  const spanDays = (Date.parse(oneYear.to) - Date.parse(oneYear.from)) / 86_400_000;
  assert.ok(Math.abs(spanDays - 365) < 3, `window spans ${spanDays} days`);
});

test("the window set is 1, 2, 3, 5 and 10 years", () => {
  assert.deepEqual(ROLLING_WINDOWS.map((window) => window.years), [1, 2, 3, 5, 10]);
});
