// Rolling performance statistics over the NAV series.
//
// What these are, precisely: NAV growth rates. The series is IBKR's
// NetLiquidation tag, which moves with deposits and withdrawals as well as with
// P&L, so none of this is a time-weighted investor return. Calling it one would
// be wrong the first time money moved in or out. The lineage block says so and
// the field name (`nav_cagr`) keeps saying so at the point of use.

export const ROLLING_WINDOWS = [
  { label: "1 year", years: 1 },
  { label: "2 years", years: 2 },
  { label: "3 years", years: 3 },
  { label: "5 years", years: 5 },
  { label: "10 years", years: 10 },
];

const TRADING_DAYS = 252;

/**
 * One NAV per calendar day, taking the last observation of each day.
 *
 * The collector writes every 30 seconds, so the raw series is thousands of
 * intraday ticks. Computing volatility across those would measure the polling
 * interval rather than the book: 3,848 observations over six days annualised as
 * if they were daily would inflate vol by roughly an order of magnitude.
 */
export function dailyCloses(series) {
  const byDay = new Map();
  for (const row of series || []) {
    const stamp = String(row?.as_of || "");
    const day = stamp.slice(0, 10);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) continue;
    const value = Number(row?.nav_decimal);
    if (!Number.isFinite(value) || value <= 0) continue;
    // Later rows overwrite earlier ones, and the query is ordered by as_of, so
    // this keeps each day's close.
    byDay.set(day, { date: day, value });
  }
  return [...byDay.values()].sort((left, right) => left.date.localeCompare(right.date));
}

/**
 * CAGR, annualised volatility, max drawdown and Calmar over one window.
 *
 * Returns `available: false` with a reason rather than a number whenever the
 * history is too short. A window computed from a fraction of its period is not
 * a shorter-horizon estimate of the same quantity -- annualising six days of a
 * drawdown into a ten-year CAGR produces a number with no meaning at all, and
 * it would be indistinguishable on the page from a real one.
 */
export function rollingStats(daily, window) {
  const needed = Math.round(window.years * 365.25);
  const base = { label: window.label, years: window.years, required_days: needed };
  if (!daily.length) {
    return { ...base, available: false, observed_days: 0, missing_days: needed,
      null_reason: "no NAV history has been recorded yet" };
  }

  const last = daily[daily.length - 1];
  const cutoff = shiftDays(last.date, -needed);
  const span = daily.filter((row) => row.date >= cutoff);
  const observed = spanDays(daily[0].date, last.date) + 1;

  if (observed < needed) {
    return {
      ...base, available: false, observed_days: observed, missing_days: needed - observed,
      null_reason: `needs ${needed - observed} more days of NAV history`,
    };
  }
  if (span.length < 3) {
    return { ...base, available: false, observed_days: observed, missing_days: 0,
      null_reason: "too few daily observations inside the window" };
  }

  const first = span[0];
  const years = Math.max(spanDays(first.date, last.date) / 365.25, 1 / 365.25);
  const growth = last.value / first.value;
  const cagr = growth > 0 ? Math.pow(growth, 1 / years) - 1 : null;

  const returns = [];
  for (let index = 1; index < span.length; index += 1) {
    const previous = span[index - 1].value;
    if (previous > 0) returns.push(span[index].value / previous - 1);
  }
  const volatility = annualisedVolatility(returns);
  const drawdown = maxDrawdown(span);
  // Calmar is CAGR over the magnitude of the worst drawdown. A book that never
  // drew down has no denominator, and reporting Infinity as a ratio is worse
  // than reporting nothing.
  const calmar = cagr != null && drawdown < 0 ? cagr / Math.abs(drawdown) : null;

  return {
    ...base, available: true,
    observed_days: observed, missing_days: 0,
    from: first.date, to: last.date,
    nav_cagr: cagr, volatility, max_drawdown: drawdown, calmar,
    daily_observations: span.length,
  };
}

function annualisedVolatility(returns) {
  if (returns.length < 2) return null;
  const mean = returns.reduce((sum, value) => sum + value, 0) / returns.length;
  // Sample variance (n-1): these returns are a sample of the process, not the
  // whole population of it.
  const variance = returns.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (returns.length - 1);
  return Math.sqrt(variance) * Math.sqrt(TRADING_DAYS);
}

function maxDrawdown(span) {
  let peak = null;
  let worst = 0;
  for (const row of span) {
    peak = peak == null ? row.value : Math.max(peak, row.value);
    if (peak > 0) worst = Math.min(worst, row.value / peak - 1);
  }
  return worst;
}

function shiftDays(date, days) {
  const ms = Date.parse(`${date}T00:00:00Z`) + days * 86_400_000;
  return new Date(ms).toISOString().slice(0, 10);
}

function spanDays(from, to) {
  return Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / 86_400_000);
}
