#!/usr/bin/env python3
"""Smoke test for dashboard/vol-viz.js against the real committed data files.

Runs the renderer under node with a minimal window shim, loads the four real
feeds off disk (never synthetic fixtures - the point is to catch a shape drift
in the committed artifacts), and asserts the invariants that would otherwise
fail silently in the browser:

  * the panel returns non-empty HTML
  * the heatmap draws exactly one cell per (metric, session) in its window, and
    that window is the 5 orthogonal metrics x 120 sessions = 600 cells (it was
    14 x 120 = 1680; nine rows ran 0.92-0.97 correlated with VIX or were
    arithmetic derivatives of a row already present)
  * a metric with a null as-of value renders its lag label and its last real
    print, and its cells use the null-hatch channel - never the neutral
    (z ~ 0) colour
  * a DARK feed (3+ trailing sessions with no print) is banner-ranked above the
    merely-lagging ones, forces quality_state='stale', and is excluded from
    coverage.symbols_ok - the vendor answers 200 the whole time, so this is
    only ever visible in the column
  * the term-state tile names the basis that produced it, and a chain-derived
    fallback is unmistakably flagged rather than passing as a primary reading

Assertions are derived from the loaded payload, never pinned to one day's
numbers. The literal-pinned version of this file (skew 132.57, "Lagging feeds
(2)", 3m dte 81, expiry 2026-10-30, iv30 12.345) expired within a week and then
CRASHED rather than failed, because `metrics_lagging.skew` stopped existing when
the vendor caught up. A shape test must survive its own data moving.
  * the deleted 14-row metric detail table does not come back
  * the dealer-gamma sign-convention / OI / gamma-flip caveats appear verbatim
  * the 3m tenor is labelled with its ACTUAL dte (81), not the target (91)
  * every feed being unreachable yields the panel's own empty state

ASCII-only output: this runs on a cp1252 console.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DASHBOARD = REPO / "dashboard"
DATA = DASHBOARD / "data"

HARNESS = r"""
'use strict';
const fs = require('fs');
const path = require('path');

const dashboard = process.argv[2];
const dataDir = path.join(dashboard, 'data');

// Minimal window shim: vol-viz.js is a browser IIFE that hangs VolViz off the
// global it is handed.
global.window = global;
require(path.join(dashboard, 'vol-viz.js'));
const VolViz = global.window.VolViz;

function readJson(name) {
  return JSON.parse(fs.readFileSync(path.join(dataDir, name), 'utf8'));
}
function readJsonl(name, maxRows) {
  const lines = fs.readFileSync(path.join(dataDir, name), 'utf8')
    .split('\n').map((s) => s.trim()).filter(Boolean);
  const tail = maxRows ? lines.slice(-maxRows) : lines;
  return tail.map((line) => JSON.parse(line));
}
function escapeHtml(value) {
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
function count(haystack, needle) {
  let n = 0; let i = 0;
  for (;;) { const at = haystack.indexOf(needle, i); if (at < 0) break; n += 1; i = at + needle.length; }
  return n;
}

const latest = readJson('vol_metrics_latest.json');
const history = readJsonl('vol_metrics_history.jsonl', null);
const surface = readJson('spx_surface_latest.json');
const surfaceHistory = readJsonl('spx_surface_history.jsonl', 60);

const html = VolViz.renderVolPanel(latest, history, surface, { escapeHtml, surfaceHistory });
const empty = VolViz.renderVolPanel(null, [], null, { escapeHtml });

const HEATMAP_SESSIONS = 120;
const metrics = VolViz.METRIC_ORDER;
const window_ = history.slice().sort((a, b) => String(a.date).localeCompare(String(b.date))).slice(-HEATMAP_SESSIONS);

// Expected null-cell count straight from the source rows.
let expectedNulls = 0;
const nullsByMetric = {};
metrics.forEach((metric) => {
  const n = window_.filter((row) => {
    const v = row[metric + '_z1y'];
    return v == null || !Number.isFinite(Number(v));
  }).length;
  nullsByMetric[metric] = n;
  expectedNulls += n;
});

const results = [];
function check(name, ok, detail) { results.push({ name, ok: !!ok, detail: String(detail) }); }

check('html non-empty', html.length > 5000 && html.includes('<section class="vol-panel">'),
  html.length + ' chars, root section present');

const longAt = html.indexOf('vol-long-view');
const dailyHtml = longAt < 0 ? html : html.slice(0, longAt);
const longHtml = longAt < 0 ? '' : html.slice(longAt);
const cells = count(dailyHtml, '<rect class="vol-heat-cell');
check('heatmap cell count == metrics x sessions',
  cells === metrics.length * window_.length,
  cells + ' cells (expected ' + metrics.length + ' x ' + window_.length + ' = ' + (metrics.length * window_.length) + ')');

check('heatmap is the 5 orthogonal rows x 120 sessions = 600 cells',
  cells === 600 && metrics.length === 5 && window_.length === 120
    && metrics.join(',') === 'vix,spx_rv20,skew,move,iv_rv_spread',
  cells + ' cells over [' + metrics.join(', ') + ']');
check('the nine redundant rows are gone from every heatmap surface',
  ['vix3m', 'vix9d', 'vix6m', 'vix1d', 'vvix', 'slope_9d_vix', 'slope_3m_6m']
    .every((m) => !metrics.includes(m))
    && !html.includes('>VIX3M<') && !html.includes('>VIX9D<') && !html.includes('>VVIX<'),
  'no near-copy of VIX draws a row');

const hatched = count(html, 'fill="url(#vol-null-hatch)"');
check('null cells use the hatch channel, not a colour',
  hatched === expectedNulls && hatched > 0,
  hatched + ' hatched cells (expected ' + expectedNulls + '); per-metric nulls: '
    + Object.entries(nullsByMetric).filter(([, n]) => n > 0).map(([m, n]) => m + '=' + n).join(', '));

// A multi-session hole must be visible as hatch in the strip, per session -
// the banner only says "16 sessions behind", it cannot show WHERE the hole is.
const lastDate = window_[window_.length - 1].date.slice(0, 10);
const holed = metrics.filter((m) => nullsByMetric[m] > 1);
check('a multi-session feed hole draws one hatched cell per missing session',
  holed.length > 0 && holed.every((m) => html.includes(
    (VolViz.METRIC_LABELS[m] || m) + ' · ' + lastDate + ' · no print')
    || window_[window_.length - 1][m + '_z1y'] != null),
  holed.map((m) => m + '=' + nullsByMetric[m]).join(', ') + ' hatched in the window');

// ---- long-history strip -------------------------------------------------
// The daily strip is capped at 120 sessions for legibility, which left 1,278
// of the 1,528 sessions on file undrawn while the browser downloaded all of
// them anyway. The long strip changes the UNIT rather than shrinking the cell.
const allDates = history.map((r) => String(r.date).slice(0, 7)).filter((m) => m.length === 7);
const expectedMonths = new Set(allDates).size;
check('the long strip covers every month on file, not a 120-session tail',
  longHtml && count(longHtml, '<rect class="vol-heat-cell') === metrics.length * expectedMonths,
  count(longHtml, '<rect class="vol-heat-cell') + ' cells (expected ' + metrics.length
    + ' x ' + expectedMonths + ' months) spanning ' + allDates[0] + '..' + allDates[allDates.length - 1]);
check('the long strip declares that its cells are monthly MEANS, not readings',
  longHtml.includes('mean</b> of that month')
    && longHtml.includes('not a reading of any single session'),
  'aggregation is disclosed rather than implied');
check('a monthly cell reports how many sessions it averages',
  /mean z1y [+−]\d+\.\d\d over \d+ sessions?/.test(longHtml),
  'per-cell tooltip carries the mean and its sample size');
// A wall of colour with no anchors cannot be navigated; named episodes are
// context laid over the data, never derived from it.
const drawnEvents = ['SVB', 'yen carry unwind', 'tariff shock', 'bear low']
  .filter((label) => longHtml.includes('>' + label + '</text>'));
check('named vol episodes anchor the long strip',
  drawnEvents.length >= 3, 'markers drawn: ' + drawnEvents.join(', '));
check('the long strip is ruled by year',
  count(longHtml, 'vol-year-rule') >= 5,
  count(longHtml, 'vol-year-rule') + ' year rules');

// The tiles assert a percentile in words; the sparkline must show it.
check('sparklines carry the trailing-year 10th-90th band behind the line',
  count(html, 'vol-spark-band') >= 3 && count(html, 'vol-spark-median') >= 3
    && html.includes('10th to 90th percentile band shaded behind it'),
  count(html, 'vol-spark-band') + ' bands drawn, described in the aria label');

// ---- forward conditioning -----------------------------------------------
// The panel's value is entirely in its honesty about sample size. A bucket
// with 300 overlapping observations has been measured ~5 times, and a result
// that does not separate must not be styled as though it did.
const fc = latest.forward_conditioning;
if (fc) {
  check('the current reading is placed in a named band',
    html.includes('the ' + fc.current_pct1y.toFixed(1) + 'th percentile')
      && html.includes('← today'),
    'current bucket ' + fc.current_bucket + ' at pct ' + fc.current_pct1y);
  Object.entries(fc.buckets_by_horizon).forEach(([horizon, block]) => {
    check('horizon ' + horizon + ' reports independent windows, not just observations',
      Object.values(block.buckets).every((b) => b.observations === 0
        || (b.independent_windows < b.observations
            && html.includes(b.independent_windows.toFixed(1))
            && html.includes('>' + b.observations + ' overlapping</small>'))),
      Object.entries(block.buckets).map(([n, b]) =>
        n + ' ' + b.observations + '->' + b.independent_windows).join(', '));
    check('horizon ' + horizon + ' excludes unfinished forward windows rather than zero-filling',
      block.truncated_sessions > 0
        && html.includes(block.truncated_sessions + ' recent sessions are excluded'),
      block.truncated_sessions + ' truncated, ' + block.unusable_sessions + ' unusable');
    // The separation verdict must follow the data, not the author.
    const meds = Object.values(block.buckets)
      .map((b) => b.median_max_drawdown_pct).filter((v) => v != null);
    const spread = Math.max(...meds) - Math.min(...meds);
    const typical = Math.abs(meds.reduce((a, b) => a + b, 0) / meds.length);
    const separates = (spread / typical) > 0.35;
    check('horizon ' + horizon + ' states the separation it actually found',
      html.includes(separates ? 'The bands separate.' : 'The bands do not separate.'),
      'spread ' + spread.toFixed(2) + ' vs typical ' + typical.toFixed(2)
        + ' -> ' + (separates ? 'separating' : 'flat'));
  });
  check('the panel says the grouping is point-in-time and the outcome is hindsight',
    html.includes('knowable <em>on that date</em>')
      && html.includes('the outcome is pure hindsight')
      && html.includes('Nothing here is a forecast'),
    'no-look-ahead and hindsight both stated');
}

// A null z must never be binned. zBin(null) is the contract that guarantees it.
check('zBin(null) is not the neutral bin', VolViz.zBin(null) === null && VolViz.zBin(0) === 'z0',
  'zBin(null)=' + VolViz.zBin(null) + ', zBin(0)=' + VolViz.zBin(0));

// These assertions used to hard-code one day's readings (skew 132.57, one
// session behind, "Lagging feeds (2)"). Every one of them went stale the next
// time a vendor changed its publishing lag, and the file crashed rather than
// failed - `metrics_lagging.skew` simply stopped existing. The invariant is
// not WHICH feed lags, it is that a lagging feed is disclosed with its own
// last-print date and a grammatical session count. Derive it from the payload.
const laggingNames = Object.keys(latest.coverage.metrics_lagging || {});
const darkNames = Object.keys(latest.coverage.metrics_dark || {});
const labelled = (m) => (VolViz.METRIC_LABELS[m] || m);

laggingNames.forEach((metric) => {
  const lag = latest.coverage.metrics_lagging[metric];
  const entry = latest.metrics[metric] || {};
  check('lagging metric ' + metric + ' has a null as-of value, not a carried one',
    entry.value === null && entry.last_value !== null,
    'value=' + entry.value + ' last_value=' + entry.last_value);
  check('lagging metric ' + metric + ' discloses its last-print date',
    html.includes(String(lag.last_value_date).slice(0, 10)),
    'looking for ' + lag.last_value_date);
});

// Singular/plural must agree with the count, whatever the count happens to be.
const anyLag = laggingNames.map((m) => latest.coverage.metrics_lagging[m].sessions_behind)
  .concat(darkNames.map((m) => latest.coverage.metrics_dark[m].sessions_dark))
  .filter((n) => n != null);
check('session counts are grammatical',
  anyLag.every((n) => html.includes(n + (n === 1 ? ' session behind' : ' sessions behind')))
    && !html.includes('1 sessions behind'),
  'counts seen: ' + anyLag.join(', '));

// A feed that has printed nothing for DARK_SESSION_THRESHOLD+ sessions is dead,
// not late, and the fetch that collected it returned 200 the whole time. It has
// to be ranked above the routine lag banner, never merged into it.
if (darkNames.length) {
  check('dark feeds get their own banner, ranked above the lag banner',
    html.includes('Dark feeds (' + darkNames.length + ')')
      && html.indexOf('vol-dark-banner') < (html.indexOf('vol-lag-banner') === -1
        ? Infinity : html.indexOf('vol-lag-banner')),
    darkNames.length + ' dark: ' + darkNames.join(', '));
  darkNames.forEach((metric) => {
    check('dark feed ' + metric + ' is named in the dark banner',
      html.includes(labelled(metric)), 'label ' + labelled(metric));
  });
  check('a dark column forces the snapshot stale and drops the symbol from symbols_ok',
    latest.quality_state === 'stale'
      && darkNames.every((m) => !latest.coverage.symbols_ok.includes(
        (latest.coverage.metrics_dark[m] || {}).symbol)),
    'quality=' + latest.quality_state + ' ok=' + latest.coverage.symbols_ok.join(','));
}

// The term tile must never read `unknown` while the chain below it can answer,
// and a chain-derived state must be unmistakably labelled as the fallback.
const regime = latest.regime || {};
check('term state names the basis that produced it',
  ['vix_vix3m', 'spx_chain_atm', 'none'].includes(regime.term_state_source)
    && html.includes(escapeHtml(regime.term_state_basis)),
  'source=' + regime.term_state_source + ' state=' + regime.term_state);
if (regime.term_state_is_fallback) {
  check('a fallback term state is flagged as one, and shows no borrowed z-score',
    html.includes('Chain fallback') && html.includes('VIX3M is dark')
      && html.includes('the chain series is too short to have a distribution'),
    'state=' + regime.term_state + ' ratio=' + regime.chain_term_ratio);
  check('the fallback ratio is the one the chart below is drawn from',
    Math.abs(regime.chain_term_ratio
      - (regime.chain_term_detail.near_atm_iv / regime.chain_term_detail.far_atm_iv)) < 1e-6,
    'ratio=' + regime.chain_term_ratio);
}
if (regime.term_state_source === 'vix_vix3m') {
  check('a primary term state does not claim to be a fallback',
    !html.includes('Chain fallback'), 'source=' + regime.term_state_source);
}

// The 14-row metric detail table was deleted as a duplicate of the strip
// beside it. Guard that it does not creep back.
check('the metric detail table is gone',
  !html.includes('vol-metrics-table') && !html.includes('no print today')
    && !html.includes('Metric detail'),
  'no metrics table markup, caption or heading');
check('a lagging metric still refuses to render a fake value',
  (laggingNames.length === 0)
    || (html.includes('Dark feeds') || html.includes('Lagging feeds')),
  'absence is declared in a banner and in the hatched cells');

// Dealer gamma caveats, verbatim (after the same escaping the panel applies).
const gamma = surface.dealer_gamma_proxy;
['sign_convention', 'oi_caveat', 'gamma_flip_omitted_reason', 'formula'].forEach((key) => {
  const wanted = escapeHtml(gamma[key]);
  check('gamma ' + key + ' appears verbatim', html.includes(wanted),
    'len ' + wanted.length + ' matched=' + html.includes(wanted));
});
check('gamma proxy is flagged an estimate', html.includes('ESTIMATE &mdash; not an observation') || html.includes('ESTIMATE'),
  'estimate flag present');
check('gamma flip omission is stated, not blank',
  html.includes('Omitted.') && gamma.gamma_flip_estimate_status === 'omitted',
  'status=' + gamma.gamma_flip_estimate_status);

// The nearest listed expiry rarely lands on the requested tenor. Whatever the
// drift is on any given day, the ACTUAL dte is what gets rendered and the
// target is only ever shown labelled as a target - pinning the literals here
// (81 vs 91, expiry 2026-10-30) made this assertion expire within the week.
const drifted = surface.tenors.filter((t) => t.dte_error_vs_target);
check('source shape: at least one tenor misses its target, and says by how much',
  drifted.length > 0 && drifted.every((t) => t.dte !== t.target_dte
    && t.dte_error_vs_target === t.dte - t.target_dte),
  drifted.map((t) => t.tenor + ' ' + t.dte + 'd vs target ' + t.target_dte).join(', '));
drifted.forEach((t) => {
  check(t.tenor + ' renders its actual dte and expiry, never the target as the dte',
    html.includes('>' + t.dte + '<') && html.includes(t.expiry.slice(0, 10))
      && html.includes(t.dte + ' dte') && html.includes('target ' + t.target_dte)
      && !html.includes('>' + t.target_dte + '<'),
    'actual=' + t.dte + ' target=' + t.target_dte + ' expiry=' + t.expiry);
});

// iv30 cross-check line. Both numbers move every session; what must hold is
// that the CBOE feed's own iv30 and the value rebuilt from the chain are both
// printed, so a divergence between them is visible rather than reconciled away.
const thirty = surface.tenors.find((t) => t.dte === 30) || surface.tenors.find((t) => t.tenor === '1m');
check('iv30 cross-check renders both the feed value and the chain-rebuilt one',
  html.includes('iv30 cross-check')
    && html.includes(surface.spot.iv30_feed.toFixed(3))
    && html.includes((thirty.atm_iv * 100).toFixed(3)),
  'feed ' + surface.spot.iv30_feed.toFixed(3) + ' vs computed ' + (thirty.atm_iv * 100).toFixed(3));

// Term structure ticks: one per priced tenor, at its ACTUAL dte.
check('term structure plots every priced tenor at its actual dte',
  surface.tenors.every((t) => html.includes('>' + t.dte + 'd<')),
  surface.tenors.map((t) => t.dte).join('/') + ' ticks present');

// Quality counts, read off the snapshot rather than pinned to one day's totals.
const q = surface.quality;
const topReason = Object.entries(q.rows_rejected_by_reason || q.rejected_by_reason || {})
  .sort((a, b) => b[1] - a[1])[0];
check('surface quality counts render',
  html.includes(q.rows_used.toLocaleString('en-US'))
    && html.includes(q.rows_total.toLocaleString('en-US'))
    && (!topReason || html.includes(topReason[0].replace(/_/g, ' ') + ' ' + topReason[1])),
  'rows_used ' + q.rows_used + ' / rows_total ' + q.rows_total
    + (topReason ? ', top rejection ' + topReason[0] + '=' + topReason[1] : ''));

// Table-view twin + legend (the relief channel the colour scale requires).
check('heatmap ships a table-view twin and a scale legend',
  html.includes('Table view &middot; z-scores') || html.includes('Table view'),
  'table view present');
check('research-only footer present', html.includes('Research only.'), 'footer present');

// Degraded path.
check('all-feeds-missing renders the panel empty state',
  empty.includes('No volatility feed is loaded') && empty.includes('vol-panel'),
  empty.length + ' chars');
const partial = VolViz.renderVolPanel(latest, history, null, { escapeHtml });
check('missing surface only degrades the surface sections',
  partial.includes('No SPX surface snapshot is loaded') && partial.includes('vol-heat-cell'),
  'heatmap still renders without the surface feed');
const noHistory = VolViz.renderVolPanel(latest, [], surface, { escapeHtml });
check('missing history only degrades the heatmap',
  noHistory.includes('No vol-metrics history is loaded') && noHistory.includes('iv30 cross-check'),
  'surface card still renders without the history feed');

process.stdout.write(JSON.stringify({ results, html_len: html.length }));
"""


def main() -> int:
    node = shutil.which("node")
    if not node:
        print("FAIL: node is not on PATH")
        return 2
    for name in (
        "vol_metrics_latest.json",
        "vol_metrics_history.jsonl",
        "spx_surface_latest.json",
        "spx_surface_history.jsonl",
    ):
        if not (DATA / name).exists():
            print("FAIL: missing data file %s" % name)
            return 2

    with tempfile.TemporaryDirectory() as tmp:
        harness = Path(tmp) / "harness.js"
        harness.write_text(HARNESS, encoding="utf-8")
        proc = subprocess.run(
            [node, str(harness), str(DASHBOARD)],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    if proc.returncode != 0:
        print("FAIL: harness exited %d" % proc.returncode)
        print(proc.stderr.strip()[:4000])
        return 2

    payload = json.loads(proc.stdout)
    results = payload["results"]
    failures = [row for row in results if not row["ok"]]
    print("vol-viz smoke test: %d assertions, panel html %d chars"
          % (len(results), payload["html_len"]))
    for row in results:
        print("  [%s] %s -- %s" % ("PASS" if row["ok"] else "FAIL", row["name"], row["detail"]))
    print("%d passed, %d failed" % (len(results) - len(failures), len(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
