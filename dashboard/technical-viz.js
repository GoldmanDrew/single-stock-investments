(function (global) {
  'use strict';

  function technicalsOf(ticker) {
    return ticker && ticker.technicals ? ticker.technicals : null;
  }

  function score(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return '—';
    return `${number > 0 ? '+' : ''}${number.toFixed(1)}σ`;
  }

  function setupMeta(setup) {
    const key = String(setup || 'unavailable');
    return {
      improving: { label: 'improving', cls: 'technical-positive' },
      deteriorating: { label: 'deteriorating', cls: 'technical-negative' },
      extended: { label: 'extended', cls: 'technical-warning' },
      washed_out: { label: 'washed out', cls: 'technical-cyan' },
      neutral: { label: 'neutral', cls: 'technical-neutral' },
      unavailable: { label: 'unavailable', cls: 'technical-neutral' },
    }[key] || { label: key.replace(/_/g, ' '), cls: 'technical-neutral' };
  }

  function renderSetupCell(ticker, escapeHtml) {
    const technicals = technicalsOf(ticker);
    if (!technicals || technicals.data_quality === 'unavailable') {
      return '<span class="technical-empty">—</span>';
    }
    const scores = technicals.scores || {};
    const meta = setupMeta((technicals.regime || {}).setup);
    const stale = technicals.fetch_status === 'preserved_after_fetch_failure';
    return `<div class="technical-cell" title="${escapeHtml((technicals.regime || {}).interpretation || '')}">
      <div class="technical-cell-score ${meta.cls}">${score(scores.trend_z)}</div>
      <div class="technical-cell-state">${escapeHtml(meta.label)}${stale ? ' · stale' : ''}</div>
    </div>`;
  }

  function renderScoreCell(ticker, key) {
    const value = ((technicalsOf(ticker) || {}).scores || {})[key];
    const number = Number(value);
    const cls = !Number.isFinite(number)
      ? 'technical-neutral'
      : number >= 1.25
        ? 'technical-positive'
        : number <= -1.25
          ? 'technical-negative'
          : 'technical-neutral';
    return `<span class="technical-score ${cls}">${score(value)}</span>`;
  }

  function sparkline(history, escapeHtml) {
    const points = (history || [])
      .map((row) => [String(row[0] || ''), Number(row[1])])
      .filter((row) => row[0] && Number.isFinite(row[1]));
    if (points.length < 2) {
      return '<div class="technical-chart-empty">Price history will appear after the nightly technical refresh.</div>';
    }
    const width = 620;
    const height = 118;
    const values = points.map((row) => row[1]);
    const low = Math.min(...values);
    const high = Math.max(...values);
    const span = high - low || 1;
    const path = points.map((row, index) => {
      const x = (index / (points.length - 1)) * width;
      const y = height - ((row[1] - low) / span) * (height - 14) - 7;
      return `${index ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
    const change = values[0] > 0 ? (values[values.length - 1] / values[0] - 1) * 100 : null;
    return `<figure class="technical-chart">
      <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="One-year adjusted price history">
        <title>Adjusted close from ${escapeHtml(points[0][0])} to ${escapeHtml(points[points.length - 1][0])}</title>
        <path class="technical-chart-baseline" d="M0,${height - 8} L${width},${height - 8}"></path>
        <path class="technical-chart-line" d="${path}"></path>
      </svg>
      <figcaption><span>${escapeHtml(points[0][0])}</span><strong>${change == null ? '—' : `${change > 0 ? '+' : ''}${change.toFixed(1)}%`}</strong><span>${escapeHtml(points[points.length - 1][0])}</span></figcaption>
    </figure>`;
  }

  function fundamentalTechnicalRead(ticker) {
    const technicals = technicalsOf(ticker) || {};
    const setup = (technicals.regime || {}).setup;
    const gap = ticker.valuation_decision?.upside_downside_pct?.base
      ?? ticker.component_valuation?.upside_downside_pct?.base;
    if (!Number.isFinite(Number(gap)) || !setup || setup === 'unavailable') {
      return 'Technical context is available independently; no complete fundamental value gap is available for a combined read.';
    }
    if (Number(gap) > 10 && setup === 'improving') {
      return 'Fundamental discount plus improving trend: prioritize entry sequencing and confirm the evidence packet.';
    }
    if (Number(gap) > 10 && ['deteriorating', 'washed_out'].includes(setup)) {
      return 'Fundamental discount is present, but price has not stabilized. Use the signal for pacing, not thesis rejection.';
    }
    if (Number(gap) < -10 && setup === 'extended') {
      return 'Price is above base value and technically extended. Review sizing and downside sensitivity.';
    }
    if (Number(gap) < -10 && setup === 'deteriorating') {
      return 'Price is above base value while trend weakens. Elevate downside and thesis review.';
    }
    return 'The technical overlay is not in conflict with the fundamental decision. It does not change evidence readiness.';
  }

  function metric(label, value, suffix) {
    const number = Number(value);
    return `<div class="technical-metric">
      <div class="technical-metric-label">${label}</div>
      <div class="technical-metric-value">${Number.isFinite(number) ? `${number > 0 ? '+' : ''}${number.toFixed(1)}${suffix || ''}` : '—'}</div>
    </div>`;
  }

  function renderPanel(ticker, helpers) {
    const { escapeHtml } = helpers;
    const technicals = technicalsOf(ticker);
    if (!technicals) {
      return `<details class="detail-section technical-panel">
        <summary>Technical setup · awaiting first refresh</summary>
        <p class="tier-sub" style="margin-top:9px">The nightly free-price job has not produced a snapshot for this security yet.</p>
      </details>`;
    }
    const scores = technicals.scores || {};
    const measures = technicals.measures || {};
    const regime = technicals.regime || {};
    const meta = setupMeta(regime.setup);
    return `<details class="detail-section technical-panel" open>
      <summary>Technical setup · <span class="${meta.cls}">${escapeHtml(meta.label)}</span></summary>
      <div class="technical-panel-body">
        <div class="technical-scoreboard">
          <div class="technical-primary-score">
            <span>Trend</span>
            <strong class="${meta.cls}">${score(scores.trend_z)}</strong>
            <small>relative momentum</small>
          </div>
          <div class="technical-primary-score">
            <span>Stretch</span>
            <strong>${score(scores.stretch_z)}</strong>
            <small>distance from trend</small>
          </div>
          <div class="technical-combined-read">
            <span>Fundamental × tape</span>
            <p>${escapeHtml(fundamentalTechnicalRead(ticker))}</p>
          </div>
        </div>
        ${sparkline(technicals.history, escapeHtml)}
        <div class="technical-metric-grid">
          ${metric('20-day return', measures.return_20d_pct, '%')}
          ${metric('60-day relative', measures.relative_return_60d_pct, '%')}
          ${metric('vs 50-day', measures.distance_50d_pct, '%')}
          ${metric('vs 200-day', measures.distance_200d_pct, '%')}
          ${metric('1-year drawdown', measures.drawdown_1y_pct, '%')}
          ${metric('20-day volatility', measures.realized_volatility_20d_pct, '%')}
        </div>
        <div class="technical-foot">
          <span>${escapeHtml(regime.interpretation || 'No unusual technical condition')}</span>
          <span class="mono">${escapeHtml(technicals.as_of || '—')} · ${escapeHtml(technicals.source || 'source pending')} · benchmark ${escapeHtml(technicals.benchmark || '—')}</span>
        </div>
        <p class="technical-policy">Timing and risk overlay only. This signal cannot upgrade valuation readiness, clear an evidence blocker, or change stance automatically.</p>
      </div>
    </details>`;
  }

  global.TechnicalViz = {
    technicalsOf,
    score,
    setupMeta,
    renderSetupCell,
    renderScoreCell,
    renderPanel,
    fundamentalTechnicalRead,
  };
})(typeof window !== 'undefined' ? window : globalThis);
