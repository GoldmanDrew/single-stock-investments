#!/usr/bin/env python3
"""Smoke test for dashboard/criticality-viz.js against the real data files.

Runs the risk-view renderer under node with a minimal window shim, loads the
committed feeds off disk (never synthetic fixtures - the point is to catch a
shape drift in the artifacts the page actually serves), and asserts the
properties that would otherwise fail silently in the browser:

  * the exhaustion score is rendered de-emphasised, struck through and flagged,
    with the model's own reason, whenever exhaustion_meaningful is false - the
    single most important property of the risk page
  * the five-state capitulation ladder lights exactly the published state, and
    shows the raw pre-hysteresis state as a pending ghost when they differ
  * all five stabilization confirmations render with their human labels
  * the sector map collapses to the honest summary form when no sector has
    passed `normal`
  * no component whose quality_state is 'unavailable' is drawn as a tile
  * the regime verdict carries the ACTUAL VIX percentile and term state from
    vol_metrics_latest.json, not a literal
  * the provenance line says daily-model when no live intraday feed is attached
  * a missing capitulation feed degrades to an honest empty state

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

global.window = global;
require(path.join(dashboard, 'criticality-viz.js'));
const CriticalityViz = global.window.CriticalityViz;

function readJson(name) {
  return JSON.parse(fs.readFileSync(path.join(dataDir, name), 'utf8'));
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

const capitulation = readJson('capitulation_daily.json');
const criticality = readJson('criticality_summary.json');
const components = readJson('market_risk_components.json');
const volLatest = readJson('vol_metrics_latest.json');
const technical = readJson('technical_signals.json');

const payload = Object.assign({}, criticality, { components: components.components || [] });
const details = { history: { criticality: [], flow: [] }, alerts: { items: [] }, health: { status: 'static_fallback' } };
const options = {
  escapeHtml,
  marketContext: technical.market_context || {},
  capitulation,
  volLatest,
  payload,
  details,
};

const html = CriticalityViz.renderRiskView(payload, details, options);
const verdictHtml = CriticalityViz.renderRegimeVerdict(options);
const resolved = CriticalityViz.resolveCapitulation(capitulation, payload, details);

const results = [];
function check(name, ok, detail) { results.push({ name, ok: !!ok, detail: String(detail) }); }

const market = capitulation.market;

check('risk view html non-empty',
  html.length > 5000 && html.includes('<section class="cap-panel">'),
  html.length + ' chars, capitulation panel present');

// ---- (1) exhaustion gating: the single most important property ----------
check('source shape: exhaustion_meaningful is false today with a reason',
  market.exhaustion_meaningful === false && String(market.exhaustion_meaningful_reason || '').length > 30,
  'meaningful=' + market.exhaustion_meaningful + ' exhaustion=' + market.exhaustion);

const voidBlock = html.slice(html.indexOf('cap-exhaustion is-void'), html.indexOf('cap-exhaustion is-void') + 900);
check('exhaustion is de-emphasised: struck through inside the void container',
  html.includes('cap-exhaustion is-void')
    && voidBlock.includes('<s>' + market.exhaustion.toFixed(1) + '</s>'),
  'struck value ' + market.exhaustion.toFixed(1) + ' inside cap-exhaustion is-void');
check('exhaustion carries an explicit not-a-signal flag',
  voidBlock.includes('Not a capitulation signal'),
  'flag present next to the struck score');
check('exhaustion shows the model\'s own reason verbatim',
  html.includes(escapeHtml(market.exhaustion_meaningful_reason)),
  'reason len ' + market.exhaustion_meaningful_reason.length);
check('the live-signal styling is NOT applied today',
  !html.includes('cap-exhaustion is-live') && !html.includes('cap-live-flag'),
  'no live exhaustion flag anywhere in the output');

// ---- (2) ladder ---------------------------------------------------------
const ladder = CriticalityViz.CAP_STATES.map((s) => s.key);
check('source shape: ladder is the 5 flow_stress states in rank order',
  ladder.join(',') === 'normal,observe,stress,exhaustion_candidate,confirmed_exhaustion',
  ladder.join(' -> '));
check('all 5 rungs render',
  count(html, '<li class="cap-rung') === 5,
  count(html, '<li class="cap-rung') + ' rungs');
check('exactly one rung is lit, and it is the published state',
  count(html, 'is-lit') === 1
    && html.includes('cap-rung cap-rank-' + market.state_rank + ' is-lit')
    && html.includes('aria-current="step"'),
  'lit rank ' + market.state_rank + " (state '" + market.state + "')");
check('raw state matches published today, so no pending ghost is drawn',
  market.raw_state === market.state && !html.includes('is-pending'),
  'raw=' + market.raw_state + ' published=' + market.state);

// Ghost path: force a divergence and confirm the pending marker appears.
const diverged = JSON.parse(JSON.stringify(capitulation));
diverged.market.raw_state = 'stress';
diverged.market.raw_state_rank = 2;
const divergedHtml = CriticalityViz.capitulationSection(
  CriticalityViz.resolveCapitulation(diverged, {}, {}), escapeHtml);
check('a raw/published divergence renders a pending ghost labelled awaiting dwell',
  divergedHtml.includes('cap-rung cap-rank-2 is-pending')
    && divergedHtml.includes('awaiting dwell')
    && divergedHtml.includes('Dwell in progress'),
  'ghost on rank 2 while published stays rank ' + market.state_rank);

// ---- (3) confirmations --------------------------------------------------
const labels = CriticalityViz.CONFIRMATION_LABELS;
check('all 5 confirmations render with human labels',
  count(html, '<li class="cap-check') === 5
    && labels.every(([, label]) => html.includes(escapeHtml(label))),
  labels.map(([k, l]) => l).join(' | '));
const metCount = labels.filter(([key]) => market.confirmations[key]).length;
check('confirmation ticks match the data and the count is shown',
  count(html, 'cap-check is-met') === metCount
    && count(html, 'cap-check is-unmet') === 5 - metCount
    && html.includes(metCount + ' of 5 met'),
  metCount + ' met / ' + (5 - metCount) + ' unmet, count line present');

// ---- (4) drawdown context ----------------------------------------------
check('drawdown context frames a calm tape as an idle model',
  html.includes('cap-drawdown is-calm')
    && html.includes(Math.abs(market.drawdown_pct).toFixed(2) + '%')
    && html.includes('not in a selloff')
    && html.includes('idle by construction')
    && html.includes(String(market.drawdown_window_sessions) + '-session high'),
  'drawdown ' + market.drawdown_pct + '%, ' + market.days_since_high + ' sessions since high');

// ---- (5) sector map -----------------------------------------------------
const sectorRanks = capitulation.sectors.map((row) => row.state_rank);
check('source shape: no sector has passed normal today',
  Math.max.apply(null, sectorRanks) === 0 && capitulation.sectors.length === 11,
  capitulation.sectors.length + ' sectors, max state_rank ' + Math.max.apply(null, sectorRanks));
const worst3 = capitulation.sectors.slice()
  .sort((a, b) => (b.state_rank - a.state_rank) || (b.panic - a.panic)).slice(0, 3);
check('sector map collapses to the summary form, not 11 rows of nothing',
  html.includes('cap-sector-summary')
    && !html.includes('cap-sector-row')
    && html.includes('11 sectors, none past <code>normal</code>')
    && count(html, '<li>\n          <span class="cap-sector-symbol">') === 3
    && worst3.every((row) => html.includes('>' + row.symbol + '<')),
  'summary + worst 3 by panic: ' + worst3.map((r) => r.symbol + ' ' + r.panic).join(', '));

// Elevated path: a sector past normal must produce real rows and a highlight.
const hot = JSON.parse(JSON.stringify(capitulation));
hot.sectors[0].state = 'stress';
hot.sectors[0].state_rank = 2;
const hotHtml = CriticalityViz.capitulationSection(
  CriticalityViz.resolveCapitulation(hot, {}, {}), escapeHtml);
check('a sector past normal switches the map to rows and highlights rank >= 2',
  hotHtml.includes('cap-sector-row is-elevated')
    && hotHtml.includes('cap-chip cap-rank-2')
    && !hotHtml.includes('cap-sector-summary'),
  'XLE forced to stress renders a highlighted row');

// ---- (6) provenance -----------------------------------------------------
check('provenance says DAILY model, never presents it as live',
  html.includes('DAILY model (live intraday feed unavailable)')
    && html.includes(escapeHtml(market.source))
    && !html.includes('LIVE intraday feed'),
  'basis=' + resolved.basis + ' source=' + market.source);
const livePayload = JSON.parse(JSON.stringify(payload));
livePayload.by_symbol.SPY.flow = {
  symbol: 'SPY', state: 'stress', raw_state: 'stress',
  scores: { pressure: 60, panic: 72, exhaustion: 55 },
  confirmation: market.confirmations, as_of: '2026-08-10T19:00:00Z',
  source: 'databento:EQUS.MINI:ohlcv-1m', quality_state: 'ready',
};
const liveHtml = CriticalityViz.renderRiskView(livePayload, details,
  Object.assign({}, options, { payload: livePayload, resolvedCapitulation: null }));
check('a live intraday snapshot is preferred over the daily model and says so',
  liveHtml.includes('LIVE intraday feed')
    && liveHtml.includes('databento:EQUS.MINI:ohlcv-1m')
    && !liveHtml.includes('DAILY model'),
  'live flow attached to by_symbol.SPY.flow wins');

// ---- (7) dead component tiles ------------------------------------------
const dead = (components.components || []).filter((c) => c.quality_state === 'unavailable');
check('source shape: 3 components are unavailable today',
  dead.length === 3 && dead.some((c) => c.component === 'observed_vol_target_flows'),
  dead.map((c) => c.component).join(', '));
check('no unavailable component is rendered as a tile',
  dead.every((c) => !html.includes('<h4>' + escapeHtml(c.label) + '</h4>'))
    && !html.includes('observed_vol_target_flows')
    && !html.includes('Unavailable'),
  'none of [' + dead.map((c) => c.label).join(', ') + '] appears as a tile');
check('the unconnected sources are still disclosed as a count, not silently dropped',
  html.includes(dead.length + ' not connected')
    && html.includes('are not connected and therefore not drawn'),
  dead.length + ' disclosed in the header');
const liveComponents = (components.components || [])
  .filter((c) => c.scope === 'market' && c.quality_state !== 'unavailable');
check('only live market tiles are drawn',
  count(html, '<article class="risk-component-card">') === liveComponents.length,
  count(html, '<article class="risk-component-card">') + ' tiles (expected ' + liveComponents.length + ')');

// ---- (8) verdict + trust ------------------------------------------------
const regime = volLatest.regime;
const composed = CriticalityViz.composeVerdict({
  vixPct1y: regime.vix_pct1y,
  termState: regime.term_state,
  ivRvSpread: regime.iv_rv_spread,
  capState: market.state,
  capStateRank: market.state_rank,
  fearPanic: technical.market_context.internal.scores.panic,
});
const pctFromData = Math.round(regime.vix_pct1y);
check('verdict carries the ACTUAL VIX percentile from the data',
  verdictHtml.includes(pctFromData + 'th percentile') && composed.text.includes(pctFromData + 'th percentile'),
  'vix_pct1y=' + regime.vix_pct1y + ' rendered as ' + pctFromData + 'th');
check('verdict carries the ACTUAL term state from the data',
  verdictHtml.includes('curve in ' + regime.term_state),
  'term_state=' + regime.term_state);
check('verdict carries the capitulation state and the tape fear score',
  verdictHtml.includes('capitulation model idle at ' + market.state)
    && verdictHtml.includes('tape fear ' + Math.round(technical.market_context.internal.scores.panic) + ' of 100'),
  'state=' + market.state + ' fear=' + technical.market_context.internal.scores.panic);
check('verdict is composed, not a literal: perturbing the inputs changes it',
  CriticalityViz.composeVerdict({
    vixPct1y: 92, termState: 'backwardation', ivRvSpread: -3.1,
    capState: 'exhaustion_candidate', capStateRank: 3, fearPanic: 81,
  }).verdict === 'stressed regime, capital-preservation posture until the tape confirms a peak'
    && composed.verdict === 'calm regime, no sizing change indicated',
  'calm today (stress ' + composed.stress + '); a stressed input set yields the stressed verdict');

const worstLag = Object.entries(volLatest.coverage.metrics_lagging)
  .sort((a, b) => b[1].sessions_behind - a[1].sessions_behind)[0];
const interior = Object.entries(volLatest.coverage.metrics_with_gaps)
  .filter(([, gap]) => String(gap.last_missing) < String(volLatest.as_of).slice(0, 10));
check('trust line names the worst feed lag from coverage',
  verdictHtml.includes(worstLag[0].toUpperCase() + ' at ' + worstLag[1].sessions_behind + ' sessions behind')
    && verdictHtml.includes(worstLag[1].last_value_date),
  worstLag[0] + ' ' + worstLag[1].sessions_behind + ' behind, last ' + worstLag[1].last_value_date);
check('trust line names the interior gap that metrics_lagging cannot see',
  verdictHtml.includes(interior.length + ' metrics had an interior gap')
    && verdictHtml.includes('closed 2026-08-07'),
  interior.length + ' metrics with a closed interior gap');
check('trust line discloses that the capitulation reading is the daily model',
  verdictHtml.includes('the capitulation reading is the daily model, not the live intraday feed'),
  'daily disclosure present in the trust line');

// ---- (9) deletions ------------------------------------------------------
check('the criticality monitor is down to one rail, not three',
  count(html, '<div class="criticality-stage ') === 1
    && html.includes('criticality-rail criticality-rail-single')
    && !html.includes('2 · Mechanical pressure') && !html.includes('3 · Exhaustion confirmation'),
  count(html, '<div class="criticality-stage ') + ' rail (was criticality + pressure + exhaustion)');
check('the breadth substitution is gone: technical_signals scores never reach the page',
  !html.includes('breadth proxy')
    && !html.includes(String(technical.market_context.internal.scores.exhaustion))
    && !html.includes(String(technical.market_context.internal.scores.pressure)),
  'internal exhaustion ' + technical.market_context.internal.scores.exhaustion
    + ' / pressure ' + technical.market_context.internal.scores.pressure + ' never rendered as flow');
check('sector criticality table dropped its 2 permanently blank columns',
  count(html, '<div class="criticality-sector-row criticality-sector-header" role="row">') === 1
    && html.includes('<span>Sector</span><span>Direction</span><span>Criticality</span><span>Critical window</span><span>Data</span>'),
  '5 columns, was 7');
check('the private-ingest prose card is gone',
  !html.includes('How the private ingest works'),
  'card removed');
check('the SPY history card advertises one series, not three',
  !html.includes('risk-line-pressure') && !html.includes('risk-line-exhaustion')
    && html.includes('SPY criticality history'),
  'flow polylines removed');

// ---- (10) degraded path -------------------------------------------------
const noCapHtml = CriticalityViz.renderRiskView(payload, details,
  Object.assign({}, options, { capitulation: null }));
check('a missing capitulation feed renders an honest empty state, not a substitute',
  noCapHtml.includes('No capitulation reading is loaded')
    && noCapHtml.includes('does not have')
    && noCapHtml.includes('cap-panel')
    && noCapHtml.includes('risk-data-stack'),
  noCapHtml.length + ' chars; the rest of the page still renders');
check('everything missing still renders without throwing',
  CriticalityViz.renderRiskView(null, {}, { escapeHtml }).length > 500,
  'null payload survives');

process.stdout.write(JSON.stringify({
  results,
  html_len: html.length,
  verdict_text: CriticalityViz.composeVerdict({
    vixPct1y: regime.vix_pct1y,
    termState: regime.term_state,
    ivRvSpread: regime.iv_rv_spread,
    capState: market.state,
    capStateRank: market.state_rank,
    fearPanic: technical.market_context.internal.scores.panic,
  }).text,
  trust_text: CriticalityViz.composeTrustLine(volLatest, resolved),
}));
"""


def ascii_only(text: str) -> str:
    return str(text).encode("ascii", "replace").decode("ascii")


def main() -> int:
    node = shutil.which("node")
    if not node:
        print("FAIL: node is not on PATH")
        return 2
    for name in (
        "capitulation_daily.json",
        "criticality_summary.json",
        "market_risk_components.json",
        "vol_metrics_latest.json",
        "technical_signals.json",
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
        print(ascii_only(proc.stderr.strip()[:4000]))
        return 2

    payload = json.loads(proc.stdout)
    results = payload["results"]
    failures = [row for row in results if not row["ok"]]
    print("risk-view smoke test: %d assertions, risk view html %d chars"
          % (len(results), payload["html_len"]))
    print("  VERDICT: %s" % ascii_only(payload["verdict_text"]))
    print("  TRUST:   %s" % ascii_only(payload["trust_text"]))
    for row in results:
        print("  [%s] %s -- %s"
              % ("PASS" if row["ok"] else "FAIL", ascii_only(row["name"]), ascii_only(row["detail"])))
    print("%d passed, %d failed" % (len(results) - len(failures), len(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
