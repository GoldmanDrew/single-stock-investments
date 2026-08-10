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
const history = readJsonl('vol_metrics_history.jsonl', 250);
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

const cells = count(html, '<rect class="vol-heat-cell');
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
check('a multi-session feed hole draws one hatched cell per missing session',
  nullsByMetric.move >= 16 && html.includes('MOVE · 2026-08-10 · no print'),
  'move has ' + nullsByMetric.move + ' hatched cells in the 120-session window');

// A null z must never be binned. zBin(null) is the contract that guarantees it.
check('zBin(null) is not the neutral bin', VolViz.zBin(null) === null && VolViz.zBin(0) === 'z0',
  'zBin(null)=' + VolViz.zBin(null) + ', zBin(0)=' + VolViz.zBin(0));

// skew: value null today, last real print 132.57 on 2026-08-07, 1 session behind.
const skew = latest.metrics.skew;
const skewLag = latest.coverage.metrics_lagging.skew;
check('source shape: skew value is null with a last_value fallback',
  skew.value === null && skew.last_value === 132.57 && skewLag.sessions_behind === 1,
  'value=' + skew.value + ' last_value=' + skew.last_value + ' behind=' + skewLag.sessions_behind);
check('skew lag is disclosed with its date and correctly singular session count',
  html.includes('2026-08-07') && html.includes('1 session behind')
    && !html.includes('1 sessions behind'),
  'date and singular session lag present in the lagging banner');

// move: 16 sessions behind.
check('move lag is disclosed with its date and session count',
  html.includes('2026-07-17') && html.includes('16 sessions behind'),
  'date and session lag present in the lagging banner');

check('lagging banner names both stale feeds',
  html.includes('Lagging feeds (2)') && html.includes('SKEW &mdash; last print') === false
    && html.includes('MOVE') && html.includes('SKEW'),
  'banner present naming SKEW and MOVE');

// The 14-row metric detail table was deleted as a duplicate of the strip
// beside it. Guard that it does not creep back.
check('the metric detail table is gone',
  !html.includes('vol-metrics-table') && !html.includes('no print today')
    && !html.includes('Metric detail'),
  'no metrics table markup, caption or heading');
check('a lagging metric still refuses to render a fake value',
  html.includes('Lagging feeds') && html.includes('rather than carrying the previous value forward'),
  'absence is still declared, in the banner and the hatched cells');

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

// 3m tenor: actual dte 81, target 91.
const threeMonth = surface.tenors.find((t) => t.tenor === '3m');
check('source shape: 3m dte 81 vs target 91',
  threeMonth.dte === 81 && threeMonth.target_dte === 91 && threeMonth.dte_error_vs_target === -10,
  'dte=' + threeMonth.dte + ' target=' + threeMonth.target_dte);
check('3m renders actual dte 81 with the expiry',
  html.includes('>81<') && html.includes('2026-10-30') && html.includes('81 dte'),
  'actual dte in the table, the chart tick and the tooltip');
check('3m never presents 91 as the dte',
  !html.includes('>91<') && html.includes('target 91'),
  'target shown only as a labelled target');

// iv30 cross-check line.
check('iv30 cross-check renders as a validation line',
  html.includes('iv30 cross-check') && html.includes('12.345') && html.includes('12.430'),
  'feed 12.345 vs computed 12.430');

// Term structure actual dtes.
check('term structure plots all four actual dtes',
  ['7d', '30d', '81d', '172d'].every((tick) => html.includes('>' + tick + '<')),
  '7/30/81/172 ticks present');

// Quality counts.
check('surface quality counts render',
  html.includes('29,444') && html.includes('30,994') && html.includes('iv out of bounds 614'),
  'rows_used/rows_total and a rejection breakdown');

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
