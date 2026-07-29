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

  function whole(value) {
    const number = Number(value);
    return Number.isFinite(number) ? Math.round(number) : '—';
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

  function fearMeta(state) {
    const key = String(state || 'unavailable');
    return {
      normal: { label: 'normal', cls: 'fear-normal', marker: '○' },
      stress_building: { label: 'stress building', cls: 'fear-stress', marker: '◐' },
      panic: { label: 'panic · unconfirmed', cls: 'fear-panic', marker: '▼' },
      capitulation_candidate: { label: 'capitulation?', cls: 'fear-candidate', marker: '◆' },
      exhaustion_emerging: { label: 'exhaustion emerging', cls: 'fear-emerging', marker: '↗' },
      confirmed_exhaustion: { label: 'exhaustion confirmed', cls: 'fear-confirmed', marker: '✓' },
      unavailable: { label: 'unavailable', cls: 'fear-normal', marker: '—' },
    }[key] || { label: key.replace(/_/g, ' '), cls: 'fear-normal', marker: '·' };
  }

  function renderSetupCell(ticker, escapeHtml) {
    const technicals = technicalsOf(ticker);
    if (!technicals || technicals.data_quality === 'unavailable') {
      return '<span class="technical-empty">—</span>';
    }
    const capitulation = technicals.capitulation || {};
    if (!capitulation.state) {
      const legacyScores = technicals.scores || {};
      const legacyMeta = setupMeta((technicals.regime || {}).setup);
      return `<div class="technical-cell" title="${escapeHtml((technicals.regime || {}).interpretation || '')}">
        <div class="technical-cell-score ${legacyMeta.cls}">${score(legacyScores.trend_z)}</div>
        <div class="technical-cell-state">${escapeHtml(legacyMeta.label)} · upgrading</div>
      </div>`;
    }
    const scores = capitulation.scores || {};
    const meta = fearMeta(capitulation.state);
    const stale = technicals.fetch_status === 'preserved_after_fetch_failure';
    const title = `${capitulation.interpretation || ''} Panic ${whole(scores.panic)}. Exhaustion ${whole(scores.exhaustion)}.`;
    return `<div class="technical-cell fear-cell ${meta.cls}" title="${escapeHtml(title)}">
      <div class="fear-cell-head"><span aria-hidden="true">${meta.marker}</span><strong>${whole(scores.panic)}</strong><small>panic</small></div>
      <div class="technical-cell-state">${escapeHtml(meta.label)}${stale ? ' · stale' : ''}</div>
      <div class="fear-cell-sub">exhaustion ${whole(scores.exhaustion)} · ${escapeHtml(technicals.data_grade || '—')} grade</div>
    </div>`;
  }

  function renderScoreCell(ticker, key) {
    const technicals = technicalsOf(ticker) || {};
    const fearScores = (technicals.capitulation || {}).scores || {};
    const value = key in fearScores ? fearScores[key] : (technicals.scores || {})[key];
    const number = Number(value);
    const cls = !Number.isFinite(number)
      ? 'technical-neutral'
      : number >= 80
        ? 'fear-panic'
        : number >= 60
          ? 'fear-stress'
          : 'technical-neutral';
    return `<span class="technical-score ${cls}">${key in fearScores ? whole(value) : score(value)}</span>`;
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
    const state = (technicals.capitulation || {}).state;
    const gap = ticker.valuation_decision?.upside_downside_pct?.base
      ?? ticker.component_valuation?.upside_downside_pct?.base;
    if (!Number.isFinite(Number(gap)) || !state || state === 'unavailable') {
      return 'Technical context is independent; no complete fundamental value gap is available for a combined read.';
    }
    if (Number(gap) > 10 && ['panic', 'capitulation_candidate'].includes(state)) {
      return 'Fundamental discount with severe fear, but no stabilization. Pace entry work and investigate whether the break is company-specific.';
    }
    if (Number(gap) > 10 && ['exhaustion_emerging', 'confirmed_exhaustion'].includes(state)) {
      return 'Fundamental discount plus improving exhaustion evidence. Prioritize entry sequencing while preserving evidence gates.';
    }
    if (Number(gap) < -10 && ['panic', 'stress_building'].includes(state)) {
      return 'Price remains above base value while technical pressure rises. Elevate downside and thesis review.';
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

  function fearRail(label, value, detail) {
    const number = Number(value);
    const width = Number.isFinite(number) ? Math.max(0, Math.min(100, number)) : 0;
    return `<div class="fear-rail">
      <div class="fear-rail-head"><span>${label}</span><strong>${Number.isFinite(number) ? Math.round(number) : '—'}</strong></div>
      <div class="fear-rail-track" aria-label="${label}: ${Number.isFinite(number) ? Math.round(number) : 'unavailable'} out of 100">
        <span style="width:${width}%"></span>
      </div>
      <small>${detail}</small>
    </div>`;
  }

  function confirmationList(confirmation) {
    const rows = [
      ['Positive session', confirmation.positive_session],
      ['Closed in upper half', confirmation.closed_upper_half],
      ['Reclaimed prior high', confirmation.reclaimed_prior_high],
      ['Volume cooled after climax', confirmation.volume_cooled],
    ];
    return rows.map(([label, passed]) =>
      `<li class="${passed ? 'confirmation-pass' : 'confirmation-wait'}"><span>${passed ? '✓' : '○'}</span>${label}</li>`
    ).join('');
  }

  function renderPanel(ticker, helpers) {
    const { escapeHtml } = helpers;
    const technicals = technicalsOf(ticker);
    if (!technicals) {
      return `<details class="detail-section technical-panel">
        <summary>Capitulation monitor · awaiting first refresh</summary>
        <p class="tier-sub" style="margin-top:9px">The nightly free-price job has not produced a snapshot for this security yet.</p>
      </details>`;
    }
    const scores = technicals.scores || {};
    const measures = technicals.measures || {};
    const regime = technicals.regime || {};
    const setup = setupMeta(regime.setup);
    const capitulation = technicals.capitulation || {};
    const fearScores = capitulation.scores || {};
    const families = capitulation.families || {};
    const intraday = capitulation.intraday || {};
    const pathShape = capitulation.path_shape || {};
    const fear = fearMeta(capitulation.state);
    return `<details class="detail-section technical-panel" open>
      <summary>Capitulation monitor · <span class="${fear.cls}">${escapeHtml(fear.label)}</span></summary>
      <div class="technical-panel-body">
        <div class="fear-headline ${fear.cls}">
          <div class="fear-headline-state"><span>${fear.marker}</span><strong>${escapeHtml(fear.label)}</strong></div>
          <p>${escapeHtml(capitulation.interpretation || regime.interpretation || 'No unusual technical condition')}</p>
          <div class="fear-headline-scores">
            <span><b>${whole(fearScores.pressure)}</b> pressure</span>
            <span><b>${whole(fearScores.panic)}</b> panic</span>
            <span><b>${whole(fearScores.exhaustion)}</b> exhaustion</span>
            <span><b>${whole(fearScores.confidence)}</b> confidence</span>
          </div>
        </div>
        <div class="fear-monitor-grid">
          <div class="fear-family-rails">
            ${fearRail('Price dislocation', families.price_dislocation, 'Short returns, drawdown and distance from trend')}
            ${fearRail('Selling climax', families.selling_climax, 'Volume, range, gap and session close')}
            ${fearRail('Volatility stress', families.volatility_stress, 'Level, acceleration and downside concentration')}
            ${fearRail('Relative/path stress', families.relative_path_stress, 'Benchmark weakness and persistent down sessions')}
          </div>
          <div class="fear-confirmation">
            <span class="fear-section-label">What would confirm exhaustion</span>
            <ul>${confirmationList(capitulation.confirmation || {})}</ul>
            <p>Extreme fear is not a bottom. Confirmation requires stabilization after the selling climax.</p>
          </div>
        </div>
        <div class="technical-scoreboard technical-scoreboard-secondary">
          <div class="technical-primary-score">
            <span>Trend</span>
            <strong class="${setup.cls}">${score(scores.trend_z)}</strong>
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
          ${metric('Session gap', intraday.gap_pct, '%')}
          ${metric('Range / ATR', intraday.true_range_vs_atr, '×')}
          ${metric('Close location', intraday.close_location, '')}
          ${metric('Vol concentration', pathShape.volatility_concentration_ratio_20d != null ? pathShape.volatility_concentration_ratio_20d * 100 : null, '%')}
          ${metric('Trend ratio', pathShape.trend_ratio_20d, '×')}
          ${metric('Downside variance', pathShape.downside_variance_share_20d != null ? pathShape.downside_variance_share_20d * 100 : null, '%')}
          ${metric('20-day return', measures.return_20d_pct, '%')}
          ${metric('60-day relative', measures.relative_return_60d_pct, '%')}
          ${metric('1-year drawdown', measures.drawdown_1y_pct, '%')}
        </div>
        <div class="technical-foot">
          <span>${escapeHtml(technicals.data_grade_reason || regime.interpretation || 'No unusual technical condition')}</span>
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
    fearMeta,
    renderSetupCell,
    renderScoreCell,
    renderPanel,
    fundamentalTechnicalRead,
  };
})(typeof window !== 'undefined' ? window : globalThis);
