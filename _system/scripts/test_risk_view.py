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

// The committed feeds carry no criticality history and no alerts - those come
// from the live /api/v1/market-risk endpoints, which a test must not depend
// on. Both are still rendering surfaces with real invariants (a 0-100 chart
// that must label its scale; a journal that must rank open above resolved), so
// they get a synthetic details payload rather than going untested. Shapes are
// copied from the live API, and the SPY reading is the real committed one.
const detailFixture = {
  health: { status: 'operational', snapshots: { criticality_count: 97 }, alerts: { open_count: 2 } },
  history: {
    criticality: [
      { as_of: '2026-08-10', score: 18.2 }, { as_of: '2026-08-07', score: 17.4 },
      { as_of: '2026-08-06', score: 16.9 }, { as_of: '2026-08-05', score: 15.1 },
      { as_of: '2026-08-04', score: 14.8 }, { as_of: '2026-08-03', score: 14.2 },
    ],
    flow: [],
  },
  alerts: {
    items: [
      { symbol: 'XLRE', state: 'stress', severity: 'high', opened_at: '2026-08-11T13:05:00Z',
        reason_codes: ['exhaustion_evidence'] },
      { symbol: 'SPY', state: 'stress', severity: 'critical', opened_at: '2026-03-02T14:10:00Z',
        resolved_at: '2026-03-02T19:40:00Z', reason_codes: ['confirmation:volume_cooling'] },
      { symbol: 'QQQ', state: 'observe', severity: 'medium', reason_codes: ['confirmation:volume_cooling'] },
    ],
  },
};
const detailHtml = CriticalityViz.renderRiskView(payload, detailFixture,
  Object.assign({}, options, { details: detailFixture }));

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
if (worstLag) {
  check('trust line names the worst feed lag from coverage',
    verdictHtml.includes(worstLag[0].toUpperCase() + ' at ' + worstLag[1].sessions_behind + ' sessions behind')
      && verdictHtml.includes(worstLag[1].last_value_date),
    worstLag[0] + ' ' + worstLag[1].sessions_behind + ' behind, last ' + worstLag[1].last_value_date);
} else {
  check('trust line confirms every feed printed on the snapshot date',
    verdictHtml.includes('every vol feed printed on the snapshot date'),
    'zero lagging feeds are stated explicitly rather than crashing the trust-line test');
}
// An interior gap is a hole that has since CLOSED. Whether any exists on a
// given day is a property of the feed, not of the renderer - pinning
// 'closed 2026-08-07' here made this assertion expire the day the holes became
// trailing rather than interior. Assert the branch the data actually selects.
if (interior.length) {
  const deepest = interior.slice().sort((a, b) => b[1].sessions_missing - a[1].sessions_missing)[0];
  const closed = interior.slice().sort((a, b) => String(b[1].last_missing).localeCompare(String(a[1].last_missing)))[0];
  check('trust line names the interior gap that metrics_lagging cannot see',
    verdictHtml.includes(interior.length + ' metric')
      && verdictHtml.includes('interior gap of up to ' + deepest[1].sessions_missing + ' sessions')
      && verdictHtml.includes('closed ' + String(closed[1].last_missing).slice(0, 10)),
    interior.length + ' metrics with a closed interior gap');
} else {
  check('trust line states plainly that there are no closed interior gaps',
    verdictHtml.includes('no interior gaps in the reported window'),
    'no closed interior gaps in this snapshot; the absence is stated, not omitted');
}

// A dark feed is the single most important thing the trust line can say: the
// vendor answers 200 the whole time, so this is the only surface that knows.
const darkFeeds = Object.keys(volLatest.coverage.metrics_dark || {});
if (darkFeeds.length) {
  check('trust line leads with the dark feeds, not the worst lag',
    verdictHtml.includes(darkFeeds.length + ' vol feeds are DARK, not late')
      && darkFeeds.every((m) => verdictHtml.includes(m.toUpperCase().replace(/_/g, ' ')))
      && verdictHtml.indexOf('DARK, not late') < verdictHtml.indexOf('worst feed lag'),
    darkFeeds.length + ' dark: ' + darkFeeds.join(', '));
}
if (volLatest.regime.term_state_is_fallback) {
  check('trust line discloses that term state came from the chain fallback',
    verdictHtml.includes('term state is the SPX-chain fallback, not VIX/VIX3M'),
    'fallback disclosed in the trust line');
}
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

// ---- (9b) the criticality chart is readable -----------------------------
// It was an 820x180 polyline with one unlabelled gridline hard-coded at y=90
// and no axis at all, so a score of 18.2 on a 0-100 scale pinned to the floor
// and read as flat, and the 50 mark read as a trend line.
const spyReading = payload.by_symbol.SPY;
const snapshots = detailFixture.history.criticality;
if (snapshots.length >= 2) {
  check('the criticality chart labels its 0-100 scale',
    [0, 25, 50, 75, 100].every((v) => detailHtml.includes('>' + v + '</text>'))
      && detailHtml.includes('risk-axis-caption'),
    'all five gridline labels drawn');
  check('the criticality chart is dated, not floating in time',
    detailHtml.includes('risk-axis-label') && /\d{4}-\d{2}-\d{2}<\/text>/.test(detailHtml),
    'date ticks present on the x axis');
  check('the current value is called out, not left to be read off a hairline',
    detailHtml.includes('risk-current-label') && detailHtml.includes('risk-current-rule'),
    'current-value rule and label drawn');
  const share = spyReading.qualified_count / spyReading.attempted_count;
  check('weak support is rendered as weak, not as a confident line',
    detailHtml.includes(Math.round(share * 100) + '% support')
      && detailHtml.includes(spyReading.qualified_count + ' of ' + spyReading.attempted_count + ' LPPLS fits qualified')
      && (share >= 0.5 || detailHtml.includes('is-weak')),
    Math.round(share * 100) + '% support (' + spyReading.qualified_count + '/' + spyReading.attempted_count + ')');
  check('the critical-time window is shown as a span, never as a date',
    detailHtml.includes(Math.round(spyReading.critical_time.p10) + '–'
      + Math.round(spyReading.critical_time.p90) + ' trading days')
      && detailHtml.includes('statement of uncertainty, not a date'),
    'p10-p90 span drawn with its dispersion stated');
}

// ---- (9c) alert journal ranks open above resolved -----------------------
const alertItems = detailFixture.alerts.items;
if (alertItems.length) {
  const openCount = alertItems.filter((a) => !(a.resolved_at || a.closed_at)
    && String(a.status || '').toLowerCase() !== 'resolved').length;
  check('the journal counts open vs resolved instead of showing an undated list',
    detailHtml.includes(openCount + ' open · ' + (alertItems.length - openCount) + ' resolved'),
    openCount + ' open of ' + alertItems.length);
  check('open and resolved episodes are visually distinct',
    (openCount === 0 || detailHtml.includes('article class="is-open"'))
      && (openCount === alertItems.length || detailHtml.includes('article class="is-resolved"')),
    'open/resolved styling applied per episode');
  check('every rendered episode is placed in time or says it cannot be',
    detailHtml.includes('risk-alert-when')
      && detailHtml.includes('no timestamp recorded'),
    'timestamps or an explicit no-timestamp note on each row');
}

// ---- (9d) LETF flow carries its liquidity denominator -------------------
const letfClose = payload.components.find((c) => c.component === 'letf_rebalance_close');
const letfIntra = payload.components.find((c) => c.component === 'letf_rebalance_intraday');
if (letfClose) {
  check('LETF flow is normalised by the auction volume it has to clear',
    html.includes("Flow as a share of that name's closing auction"),
    'liquidity denominator drawn, not just the dollar total');
  check('the two hard-coded model assumptions are disclosed on the tile',
    html.includes('is <b>' + Math.round(letfClose.auction_share_assumption * 100) + '%</b> of daily volume')
      && html.includes('<b>' + Math.round(letfClose.swap_hedge_share_assumption * 100) + '%</b> of leveraged exposure is swap-hedged'),
    'auction share and swap-hedge share stated');
  const ranked = (letfClose.top || []).filter((t) => t.net_moc_pct_auction_volume != null);
  const unfloated = ranked.filter((t) => !t.tradable_float_quality || t.tradable_float_quality === 'missing');
  if (unfloated.length) {
    check('a peak ratio built on a missing float is voided, not headlined',
      html.includes('not usable.') && html.includes('tradable_float_quality: missing')
        && html.includes('division artifact'),
      unfloated.length + ' of ' + ranked.length + ' ranked names have no tradable float');
  }
}
if (letfClose && letfIntra) {
  const forecast = letfIntra.net_dollars, realized = letfClose.net_dollars;
  const flip = (forecast < 0) !== (realized < 0);
  check('the two estimates of the same close are reconciled, not left side by side',
    html.includes('Same event, two methods')
      && html.includes(flip ? 'These two tiles disagree' : 'These two tiles agree'),
    'forecast ' + forecast + ' vs realized ' + realized);
  if (flip) {
    check('a sign disagreement is called out explicitly',
      html.includes('do not even agree on <b>direction</b>')
        && html.includes('At least one is wrong'),
      'opposite signs: one estimates net buying, the other net selling');
  }
}

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
