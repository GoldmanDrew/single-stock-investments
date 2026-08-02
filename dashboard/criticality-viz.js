(function (global) {
  'use strict';

  function finite(value) {
    if (value == null || value === '') return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  function whole(value) {
    const number = finite(value);
    return number == null ? '—' : String(Math.round(number));
  }

  function escapeFallback(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function directionMeta(direction) {
    return {
      positive_bubble: { label: 'positive criticality', cls: 'criticality-positive' },
      negative_bubble: { label: 'negative criticality', cls: 'criticality-negative' },
      none: { label: 'no qualified regime', cls: 'criticality-neutral' },
    }[String(direction || 'none')]
      || { label: String(direction || 'unavailable').replace(/_/g, ' '), cls: 'criticality-neutral' };
  }

  function rail(label, value, detail, cls) {
    const number = finite(value);
    const width = number == null ? 0 : Math.max(0, Math.min(100, number));
    return `<div class="criticality-stage ${cls || ''}">
      <div class="criticality-stage-head"><span>${label}</span><strong>${whole(number)}</strong></div>
      <div class="criticality-stage-track" role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${number == null ? 0 : Math.round(number)}">
        <span style="width:${width}%"></span>
      </div>
      <small>${detail}</small>
    </div>`;
  }

  function criticalWindow(reading) {
    const range = reading?.critical_time || {};
    const low = finite(range.p10);
    const median = finite(range.median);
    const high = finite(range.p90);
    if (low == null || median == null || high == null) return 'No concentrated critical-time range';
    return `${Math.round(low)}–${Math.round(high)} trading days · median ${Math.round(median)}`;
  }

  function quality(reading) {
    const mode = String(reading?.entitlement_mode || 'unknown').toUpperCase();
    const state = String(reading?.quality_state || reading?.status || 'unknown').replace(/_/g, ' ');
    return `${mode} · ${state}`;
  }

  function businessAge(asOf, now = new Date()) {
    if (!asOf) return null;
    const start = new Date(asOf);
    if (Number.isNaN(start.getTime())) return null;
    let days = 0;
    const cursor = new Date(start.getFullYear(), start.getMonth(), start.getDate());
    const end = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    while (cursor < end && days < 3660) {
      cursor.setDate(cursor.getDate() + 1);
      if (cursor.getDay() !== 0 && cursor.getDay() !== 6) days += 1;
    }
    return days;
  }

  function freshness(asOf) {
    const age = businessAge(asOf);
    if (age == null) return { label: 'awaiting data', cls: 'criticality-neutral', stale: true };
    if (age <= 1) return { label: 'current', cls: 'criticality-exhaustion', stale: false };
    if (age <= 3) return { label: `${age} business days old`, cls: 'criticality-positive', stale: false };
    return { label: `${age} business days old`, cls: 'criticality-pressure', stale: true };
  }

  function sectorRows(rows, escapeHtml) {
    if (!rows.length) return '<div class="criticality-empty">Sector ensembles will appear after the next criticality refresh.</div>';
    return `<div class="criticality-sector-grid" role="table" aria-label="Sector criticality heatmap">
      <div class="criticality-sector-row criticality-sector-header" role="row">
        <span>Sector</span><span>Direction</span><span>Criticality</span><span>Pressure</span><span>Exhaustion</span><span>Critical window</span><span>Data</span>
      </div>
      ${rows.map((row) => {
        const meta = directionMeta(row.direction);
        const confidence = row.confidence || {};
        const flowScores = row.flow?.scores || {};
        return `<div class="criticality-sector-row" role="row">
          <span><strong>${escapeHtml(row.symbol || '—')}</strong><small>${escapeHtml(row.name || '')}</small></span>
          <span class="${meta.cls}">${escapeHtml(meta.label)}</span>
          <span class="criticality-heat" style="--score:${Math.max(0, Math.min(100, finite(row.score) || 0))}%"><b>${whole(row.score)}</b></span>
          <span>${whole(flowScores.pressure)}</span><span>${whole(flowScores.exhaustion)}</span>
          <span>${escapeHtml(criticalWindow(row))}</span>
          <span class="criticality-quality">${escapeHtml(quality(row))}<small>${whole(confidence.qualified)}% qualified</small></span>
        </div>`;
      }).join('')}
    </div>`;
  }

  function resolveReading(payload, marketContext) {
    const bySymbol = payload?.by_symbol || {};
    const spy = bySymbol.SPY || (payload?.market || []).find((row) => row.symbol === 'SPY') || {};
    const internal = marketContext?.internal || {};
    return { spy, flow: spy.flow || internal, flowScores: (spy.flow || internal).scores || {} };
  }

  function render(payload, options = {}) {
    const escapeHtml = options.escapeHtml || escapeFallback;
    const { spy, flow, flowScores } = resolveReading(payload, options.marketContext || {});
    const direction = directionMeta(spy.direction);
    const confidence = spy.confidence || {};
    const asOf = spy.as_of || payload?.generated_at;
    const fresh = freshness(asOf);
    const sectors = (payload?.sectors || []).slice().sort((a, b) => (finite(b.score) || 0) - (finite(a.score) || 0));
    return `<details class="criticality-monitor" ${options.open === false ? '' : 'open'}>
      <summary><span>Criticality &amp; forced-flow monitor</span><strong class="${direction.cls}">${escapeHtml(direction.label)}</strong>
        <small>${asOf ? `as of ${escapeHtml(String(asOf).slice(0, 10))}` : 'awaiting first refresh'} · <b class="${fresh.cls}">${escapeHtml(fresh.label)}</b></small></summary>
      <div class="criticality-body">
        <div class="criticality-headline"><div><span class="criticality-kicker">SPY ensemble · research only</span>
          <h3 class="${direction.cls}">${escapeHtml(direction.label)}</h3><p>${escapeHtml(spy.interpretation || 'No LPPLS snapshot is available yet.')}</p></div>
          <div class="criticality-window"><span>Critical-time ensemble</span><strong>${escapeHtml(criticalWindow(spy))}</strong>
          <small>${whole(spy.qualified_count)} qualified of ${whole(spy.attempted_count)} attempted fits · ${escapeHtml(quality(spy))}</small></div></div>
        <div class="criticality-rail" aria-label="Criticality, mechanical pressure, and exhaustion stages">
          ${rail('1 · Criticality buildup', spy.score, `${whole(confidence.positive)} positive · ${whole(confidence.negative)} negative confidence`, direction.cls)}
          ${rail('2 · Mechanical pressure', flowScores.pressure, flow.state ? String(flow.state).replace(/_/g, ' ') : 'awaiting intraday flow feed', 'criticality-pressure')}
          ${rail('3 · Exhaustion confirmation', flowScores.exhaustion, finite(flowScores.exhaustion) == null ? 'awaiting pressure-decay confirmation' : 'independent stabilization evidence', 'criticality-exhaustion')}
        </div>
        <details class="criticality-sectors" ${options.expandSectors ? 'open' : ''}><summary>Sector heatmap · ${sectors.length} available</summary>${sectorRows(sectors, escapeHtml)}</details>
        <p class="criticality-policy">${escapeHtml(spy.policy || 'Critical time describes regime instability, not a promised crash or reversal date.')} No model output has trading authority.</p>
      </div></details>`;
  }

  function points(rows, accessor, width, height) {
    const ordered = rows.slice().reverse();
    const values = ordered.map(accessor).map(finite);
    const valid = values.filter((v) => v != null);
    if (valid.length < 2) return '';
    return values.map((value, index) => {
      const x = 8 + (index / Math.max(1, values.length - 1)) * (width - 16);
      const y = height - 8 - ((value == null ? 0 : Math.max(0, Math.min(100, value))) / 100) * (height - 16);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
  }

  function historyChart(details) {
    const criticality = details?.history?.criticality || [];
    const flow = details?.history?.flow || [];
    const width = 820; const height = 180;
    const criticalPoints = points(criticality, (row) => row.score ?? row.criticality_score, width, height);
    const pressurePoints = points(flow, (row) => row.scores?.pressure ?? row.pressure_score, width, height);
    const exhaustionPoints = points(flow, (row) => row.scores?.exhaustion ?? row.exhaustion_score, width, height);
    if (!criticalPoints && !pressurePoints && !exhaustionPoints) return '<div class="risk-empty">History will build automatically as signed live snapshots arrive.</div>';
    return `<svg class="risk-history-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Criticality and forced-flow history">
      <line x1="8" y1="90" x2="812" y2="90" class="risk-grid-line"></line>
      ${criticalPoints ? `<polyline points="${criticalPoints}" class="risk-line risk-line-criticality"></polyline>` : ''}
      ${pressurePoints ? `<polyline points="${pressurePoints}" class="risk-line risk-line-pressure"></polyline>` : ''}
      ${exhaustionPoints ? `<polyline points="${exhaustionPoints}" class="risk-line risk-line-exhaustion"></polyline>` : ''}</svg>`;
  }

  function renderRiskView(payload, details = {}, options = {}) {
    const escapeHtml = options.escapeHtml || escapeFallback;
    const health = details.health || {};
    const ingest = health.latest_ingest || {};
    const alerts = details.alerts?.items || [];
    const status = health.status || 'static_fallback';
    const receivedFresh = freshness(ingest.received_at);
    return `<div class="risk-view-head"><div><span class="criticality-kicker">Systemic risk lab · research only</span><h2>Criticality &amp; forced-flow exhaustion</h2>
      <p>Tracks unstable price regimes, mechanical deleveraging pressure, and evidence that forced selling is fading. Signals are descriptive—not automatic trade instructions.</p></div>
      <div class="risk-live-state"><span class="risk-status-dot ${status === 'operational' ? 'is-live' : ''}"></span><strong>${escapeHtml(status.replace(/_/g, ' '))}</strong><small>${escapeHtml(receivedFresh.label)}</small></div></div>
      ${render(payload, { ...options, open: true, expandSectors: true })}
      <div class="risk-grid">
        <section class="risk-card risk-history"><header><h3>SPY signal history</h3><div class="risk-legend"><span class="criticality-positive">Criticality</span><span class="criticality-pressure">Pressure</span><span class="criticality-exhaustion">Exhaustion</span></div></header>${historyChart(details)}</section>
        <section class="risk-card"><h3>Feed health</h3><dl class="risk-health">
          <div><dt>Last signed ingest</dt><dd>${escapeHtml(ingest.received_at ? String(ingest.received_at).replace('T', ' ').slice(0, 19) + ' UTC' : 'Awaiting first live snapshot')}</dd></div>
          <div><dt>Latest flow</dt><dd>${escapeHtml(health.snapshots?.latest_flow_at || '—')}</dd></div>
          <div><dt>Stored snapshots</dt><dd>${whole(health.snapshots?.criticality_count)} criticality · ${whole(health.snapshots?.flow_count)} flow</dd></div>
          <div><dt>Open alerts</dt><dd>${whole(health.alerts?.open_count)}</dd></div></dl></section>
        <section class="risk-card"><h3>Alert journal</h3>${alerts.length ? `<div class="risk-alerts">${alerts.slice(0, 12).map((alert) => `<article><strong>${escapeHtml(alert.symbol)} · ${escapeHtml(alert.state.replace(/_/g, ' '))}</strong><span class="risk-severity risk-severity-${escapeHtml(alert.severity)}">${escapeHtml(alert.severity)}</span><small>${escapeHtml((alert.reason_codes || []).join(' · '))}</small></article>`).join('')}</div>` : '<div class="risk-empty">No alert episodes have been recorded yet.</div>'}</section>
        <section class="risk-card"><h3>How the private ingest works</h3><p>The browser can read risk data, but cannot write it. The publisher signs each payload with the market-risk ingest token, a timestamp, and a one-time nonce. Cloudflare verifies the signature, rejects requests older than five minutes, and refuses reused nonces.</p><p>The token never appears in this page, D1, request headers, or the market data feed. It is a private signing secret, separate from the Databento API key.</p></section>
      </div>
      <section class="risk-method"><h3>Interpretation guardrails</h3><p><strong>Criticality</strong> asks whether price dynamics resemble an unstable LPPLS regime. <strong>Pressure</strong> estimates mechanical stress consistent with volatility-sensitive deleveraging. <strong>Exhaustion</strong> requires stabilization evidence and persistence. A critical time is a probability window, not a scheduled crash; all outputs remain research-only until shadow validation establishes calibration and false-positive behavior.</p></section>`;
  }

  global.CriticalityViz = { directionMeta, freshness, render, renderRiskView };
})(window);
