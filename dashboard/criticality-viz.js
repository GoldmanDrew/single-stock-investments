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

  // Sector criticality only. The pressure/exhaustion columns that used to sit
  // here were 22 permanently blank cells - no sector-level flow feed has ever
  // existed. Sector capitulation now has its own panel, fed by real data.
  function sectorRows(rows, escapeHtml) {
    if (!rows.length) return '<div class="criticality-empty">Sector ensembles will appear after the next criticality refresh.</div>';
    return `<div class="criticality-sector-grid" role="table" aria-label="Sector criticality heatmap">
      <div class="criticality-sector-row criticality-sector-header" role="row">
        <span>Sector</span><span>Direction</span><span>Criticality</span><span>Critical window</span><span>Data</span>
      </div>
      ${rows.map((row) => {
        const meta = directionMeta(row.direction);
        const confidence = row.confidence || {};
        return `<div class="criticality-sector-row" role="row">
          <span><strong>${escapeHtml(row.symbol || '—')}</strong><small>${escapeHtml(row.name || '')}</small></span>
          <span class="${meta.cls}">${escapeHtml(meta.label)}</span>
          <span class="criticality-heat" style="--score:${Math.max(0, Math.min(100, finite(row.score) || 0))}%"><b>${whole(row.score)}</b></span>
          <span>${escapeHtml(criticalWindow(row))}</span>
          <span class="criticality-quality">${escapeHtml(quality(row))}<small>${whole(confidence.qualified)}% qualified</small></span>
        </div>`;
      }).join('')}
    </div>`;
  }

  function resolveReading(payload) {
    const bySymbol = payload?.by_symbol || {};
    const spy = bySymbol.SPY || (payload?.market || []).find((row) => row.symbol === 'SPY') || {};
    return { spy };
  }

  function render(payload, options = {}) {
    const escapeHtml = options.escapeHtml || escapeFallback;
    const { spy } = resolveReading(payload);
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
        <div class="criticality-rail criticality-rail-single" aria-label="Criticality buildup">
          ${rail('Criticality buildup', spy.score, `${whole(confidence.positive)} positive · ${whole(confidence.negative)} negative confidence`, direction.cls)}
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

  // One series: LPPLS criticality. The pressure/exhaustion polylines were
  // deleted - the intraday flow history they read has never been fed on this
  // deployment, so they drew nothing while the legend promised three series.
  function historyChart(details) {
    const criticality = details?.history?.criticality || [];
    const width = 820; const height = 180;
    const criticalPoints = points(criticality, (row) => row.score ?? row.criticality_score, width, height);
    if (!criticalPoints) return '<div class="risk-empty">History will build automatically as signed live snapshots arrive.</div>';
    return `<svg class="risk-history-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="SPY LPPLS criticality score history, 0 to 100">
      <line x1="8" y1="90" x2="812" y2="90" class="risk-grid-line"></line>
      <polyline points="${criticalPoints}" class="risk-line risk-line-criticality"></polyline></svg>`;
  }

  function compactNumber(value, unit) {
    const number = finite(value);
    if (number == null) return '—';
    if (unit === 'USD') {
      const abs = Math.abs(number);
      const scale = abs >= 1e9 ? [1e9, 'B'] : abs >= 1e6 ? [1e6, 'M'] : abs >= 1e3 ? [1e3, 'K'] : [1, ''];
      return `${number < 0 ? '−' : ''}$${(abs / scale[0]).toFixed(abs / scale[0] >= 100 ? 0 : 1)}${scale[1]}`;
    }
    if (unit === 'annualized_volatility') return `${(number * 100).toFixed(1)}%`;
    if (unit === 'z_score') return `${number.toFixed(2)}σ`;
    if (unit === 'index_points') return number.toFixed(2);
    if (unit === 'share_of_universe') return `${(number * 100).toFixed(1)}%`;
    return Math.abs(number) >= 100 ? Math.round(number).toLocaleString() : number.toFixed(2);
  }

  function qualityMeta(state) {
    return {
      ready: ['Current', 'is-ready'], delayed: ['Delayed', 'is-delayed'],
      stale: ['Stale', 'is-stale'], unavailable: ['Unavailable', 'is-unavailable'],
    }[String(state || '').toLowerCase()] || [String(state || 'Unknown').replace(/_/g, ' '), 'is-unavailable'];
  }

  function calendarAge(asOf, now = new Date()) {
    if (!asOf) return null;
    const start = new Date(asOf);
    if (Number.isNaN(start.getTime())) return null;
    const startDay = Date.UTC(start.getUTCFullYear(), start.getUTCMonth(), start.getUTCDate());
    const endDay = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
    return Math.round((endDay - startDay) / 86400000);
  }

  // quality_state is stamped at build time, so a frozen fallback snapshot
  // carries 'ready' forever. Recompute staleness from as_of at render time:
  // anything older than 2 calendar days renders as stale no matter what the
  // build claimed. 'unavailable' is exempt — a feed that was never connected
  // is missing, not old, and "stale" would imply data existed.
  function componentQuality(item, now = new Date()) {
    const state = String(item.quality_state || 'unknown').toLowerCase();
    const age = calendarAge(item.as_of, now);
    if (state !== 'unavailable' && age != null && age > 2) {
      return { state: 'stale', label: `Stale (as_of ${String(item.as_of).slice(0, 10)})`, cls: 'is-stale' };
    }
    const meta = qualityMeta(item.quality_state);
    return { state, label: meta[0], cls: meta[1] };
  }

  function componentDetail(item, escapeHtml) {
    if (item.component.startsWith('letf_rebalance')) {
      return `<dl><div><dt>Net close flow</dt><dd>${compactNumber(item.net_dollars ?? item.value, 'USD')}</dd></div>
        <div><dt>Gross flow</dt><dd>${compactNumber(item.gross_dollars, 'USD')}</dd></div>
        <div><dt>Coverage</dt><dd>${whole(item.underlyings)} underlyings</dd></div></dl>`;
    }
    if (item.component === 'volatility_borrow') {
      return `<dl><div><dt>Median 20d RV</dt><dd>${compactNumber(item.median_underlying_rv_20d_annual, 'annualized_volatility')}</dd></div>
        <div><dt>Borrow spikes</dt><dd>${whole(item.borrow_spiking_count)}</dd></div><div><dt>Products</dt><dd>${whole(item.products)}</dd></div></dl>`;
    }
    if (item.component === 'options_stress') {
      return `<dl><div><dt>Latest skew</dt><dd>${compactNumber(item.latest?.skew_z, 'z_score')}</dd></div>
        <div><dt>Term ratio</dt><dd>${compactNumber(item.latest?.term_ratio_z, 'z_score')}</dd></div>
        <div><dt>RV vs implied</dt><dd>${compactNumber(item.latest?.realized_vs_implied_z, 'z_score')}</dd></div>
        <div><dt>VIX</dt><dd>${compactNumber(item.latest_vix, 'index_points')}</dd></div><div><dt>Minute samples</dt><dd>${whole(item.observations)}</dd></div></dl>`;
    }
    if (item.component === 'etf_holdings_coverage') {
      return `<dl><div><dt>Funds mapped</dt><dd>${whole(item.funds)}</dd></div><div><dt>Positions</dt><dd>${whole(item.positions)}</dd></div>
        <div><dt>Derivatives</dt><dd>${whole(item.derivative_positions)}</dd></div></dl>`;
    }
    if (item.component === 'vix_regime') {
      return `<dl><div><dt>Close</dt><dd>${compactNumber(item.close, 'index_points')}</dd></div><div><dt>Daily change</dt><dd>${finite(item.change_pct) == null ? '—' : `${Number(item.change_pct).toFixed(1)}%`}</dd></div></dl>`;
    }
    if (item.component === 'market_breadth') {
      return `<dl><div><dt>Stressed</dt><dd>${finite(item.stress_share) == null ? '—' : `${(Number(item.stress_share) * 100).toFixed(1)}%`}</dd></div>
        <div><dt>Severe</dt><dd>${finite(item.severe_share) == null ? '—' : `${(Number(item.severe_share) * 100).toFixed(1)}%`}</dd></div><div><dt>Stocks</dt><dd>${whole(item.available)}</dd></div></dl>`;
    }
    return `<p>${escapeHtml(item.description || 'This source is not connected.')}</p>`;
  }

  // A component with no dataset behind it is not rendered at all. Dead tiles
  // (observed_vol_target_flows has no free source; options_stress and
  // dealer_gamma went dark) used to occupy a third of this grid saying nothing.
  // The count of unconnected sources is still disclosed in the header.
  function componentStack(payload, escapeHtml) {
    const all = payload?.components || [];
    const live = all.filter((item) => componentQuality(item).state !== 'unavailable');
    const dead = all.filter((item) => componentQuality(item).state === 'unavailable');
    const market = live.filter((item) => item.scope === 'market');
    const sectors = live.filter((item) => item.scope === 'sector' && item.component === 'letf_rebalance_intraday');
    const counts = live.reduce((memo, item) => { const state = componentQuality(item).state; memo[state] = (memo[state] || 0) + 1; return memo; }, {});
    if (!all.length) return `<section class="risk-data-stack"><header><div><h3>Mechanical-flow data stack</h3><p>Awaiting the first component ingest.</p></div></header></section>`;
    if (!live.length) return `<section class="risk-data-stack"><header><div><h3>Mechanical-flow data stack</h3>
      <p>None of the ${escapeHtml(String(all.length))} declared component sources is connected right now, so no tile is drawn. An empty grid is the honest reading; it does not mean risk is zero.</p></div></header></section>`;
    const deadNote = dead.length
      ? `<p class="risk-dead-note">${escapeHtml(String(dead.length))} declared source${dead.length === 1 ? ' is' : 's are'} not connected and therefore not drawn: ${escapeHtml(dead.map((item) => String(item.component).replace(/_/g, ' ')).sort().join(', '))}. A source with no data gets no tile rather than a blank one.</p>`
      : '';
    return `<section class="risk-data-stack"><header><div><span class="criticality-kicker">Independent inputs · never silently blended</span><h3>Mechanical-flow data stack</h3>
      <p>Each tile retains its source cadence and quality. Only connected sources are drawn.</p></div>
      <div class="risk-coverage"><strong>${counts.ready || 0} current</strong><span>${counts.delayed || 0} delayed · ${counts.stale || 0} stale · ${dead.length} not connected</span></div></header>
      ${deadNote}
      <div class="risk-component-grid">${market.map((item) => { const q = componentQuality(item); return `<article class="risk-component-card">
        <div class="risk-component-head"><div><span>${escapeHtml(String(item.component).replace(/_/g, ' '))}</span><h4>${escapeHtml(item.label || item.symbol)}</h4></div><b class="${q.cls}">${escapeHtml(q.label)}</b></div>
        <div class="risk-component-value">${compactNumber(item.value, item.unit)}${finite(item.score) == null ? '' : `<small>stress ${whole(item.score)} / 100</small>`}</div>
        ${componentDetail(item, escapeHtml)}<p>${escapeHtml(item.description || '')}</p><footer>${escapeHtml(item.source)} · ${escapeHtml(String(item.as_of || '').replace('T', ' ').slice(0, 19))}</footer>
      </article>`; }).join('')}</div>
      ${sectors.length ? `<details class="risk-sector-flows"><summary>Intraday sector close-flow map · ${sectors.length} sectors</summary><div>${sectors.sort((a, b) => Math.abs(finite(b.value) || 0) - Math.abs(finite(a.value) || 0)).map((item) => `<span><b>${escapeHtml(item.symbol)}</b><em>${compactNumber(item.value, 'USD')}</em><small>${finite(item.pct_auction_volume) == null ? '—' : `${Number(item.pct_auction_volume).toFixed(2)}% auction`}</small></span>`).join('')}</div></details>` : ''}
    </section>`;
  }

  // ---------------------------------------------------------------------
  // Capitulation ladder
  //
  // The ladder is the state machine in _system/scripts/criticality/flow_stress.py:
  // normal -> observe -> stress -> exhaustion_candidate -> confirmed_exhaustion.
  // It answers "how far into capitulation has this selloff progressed", which
  // a bare score cannot. The published `state` is post-hysteresis (2 repeat
  // observations to upgrade, 3 to downgrade); `raw_state` is the unsmoothed
  // reading, and the gap between them is the dwell discipline doing its job.
  //
  // Exhaustion is only a capitulation reading once panic has actually reached
  // the ladder's stress threshold. Rendering the raw score without that gate is
  // how "exhaustion 95" came to sit on the page at an all-time high.
  // ---------------------------------------------------------------------

  const CAP_STATES = [
    { key: 'normal', label: 'Normal', rule: 'pressure below 55' },
    { key: 'observe', label: 'Observe', rule: 'pressure 55 or more' },
    { key: 'stress', label: 'Stress', rule: 'panic 70 or more' },
    { key: 'exhaustion_candidate', label: 'Exhaustion candidate', rule: 'panic 70+ and exhaustion 45+' },
    { key: 'confirmed_exhaustion', label: 'Confirmed exhaustion', rule: 'panic 75+, exhaustion 65+, 3 confirmations' },
  ];

  const CAP_RANK = CAP_STATES.reduce((memo, state, index) => { memo[state.key] = index; return memo; }, {});

  const CONFIRMATION_LABELS = [
    ['positive_interval', 'Closed above its open'],
    ['closed_upper_half', 'Closed in the upper half of its range'],
    ['volatility_decelerating', 'Volatility decelerating'],
    ['selling_decelerating', 'Selling decelerating'],
    ['volume_cooling', 'Volume cooling'],
  ];

  function stateLabel(key) {
    const found = CAP_STATES.find((state) => state.key === key);
    return found ? found.label : String(key || 'unknown').replace(/_/g, ' ');
  }

  function one(value) {
    const number = finite(value);
    return number == null ? '—' : number.toFixed(1);
  }

  function normalizeFlowRow(row) {
    if (!row) return null;
    const scores = row.scores || {};
    const state = String(row.state || 'normal').toLowerCase();
    const rawState = String(row.raw_state || state).toLowerCase();
    const stateRank = finite(row.state_rank) ?? (CAP_RANK[state] ?? 0);
    const rawRank = finite(row.raw_state_rank) ?? (CAP_RANK[rawState] ?? stateRank);
    const confirmations = row.confirmations || row.confirmation || {};
    const confirmationCount = finite(row.confirmation_count)
      ?? CONFIRMATION_LABELS.reduce((total, [key]) => total + (confirmations[key] ? 1 : 0), 0);
    // A live intraday snapshot has no exhaustion_meaningful field; derive it
    // from the same rule the daily model states explicitly, and say why.
    const meaningful = typeof row.exhaustion_meaningful === 'boolean'
      ? row.exhaustion_meaningful
      : rawRank >= CAP_RANK.stress;
    const reason = row.exhaustion_meaningful_reason || (meaningful
      ? ''
      : `raw state '${rawState}' has not reached the ladder's stress threshold, so these confirmations describe routine stabilization, not capitulation`);
    return {
      symbol: row.symbol || '—',
      name: row.name || '',
      state,
      stateRank,
      rawState,
      rawRank,
      pressure: finite(row.pressure ?? scores.pressure),
      panic: finite(row.panic ?? scores.panic),
      exhaustion: finite(row.exhaustion ?? scores.exhaustion),
      exhaustionMeaningful: !!meaningful,
      exhaustionReason: String(reason || ''),
      confirmations,
      confirmationCount,
      drawdownPct: finite(row.drawdown_pct),
      daysSinceHigh: finite(row.days_since_high),
      inDrawdown: !!row.in_drawdown,
      drawdownWindow: finite(row.drawdown_window_sessions),
      barCount: finite(row.bar_count),
      qualityState: row.quality_state || null,
      source: row.source || null,
      asOf: row.as_of || null,
    };
  }

  // Prefer a live intraday flow snapshot if one is actually attached to the
  // criticality payload; otherwise fall back to the always-on daily model.
  // Daily is never presented as live.
  function resolveCapitulation(capitulation, payload, details) {
    const { spy } = resolveReading(payload);
    const liveRow = spy && spy.flow && (spy.flow.state || spy.flow.scores) ? spy.flow : null;
    if (liveRow) {
      const market = normalizeFlowRow(liveRow);
      return {
        basis: 'live',
        market,
        sectors: (payload?.sectors || []).map((row) => normalizeFlowRow(row.flow)).filter(Boolean),
        asOf: market.asOf || details?.health?.snapshots?.latest_flow_at || null,
        source: market.source || 'intraday forced-flow feed',
        cadence: 'intraday',
        qualityState: market.qualityState,
      };
    }
    if (capitulation && capitulation.market) {
      const market = normalizeFlowRow(capitulation.market);
      return {
        basis: 'daily',
        market,
        sectors: (capitulation.sectors || []).map((row) => normalizeFlowRow(row)).filter(Boolean),
        asOf: capitulation.as_of || market.asOf,
        source: market.source || 'daily bars',
        cadence: capitulation.cadence || 'daily',
        qualityState: capitulation.quality_state || market.qualityState,
        coverage: capitulation.coverage || null,
        basisNote: capitulation.basis || null,
      };
    }
    return null;
  }

  function capLadder(market, escapeHtml) {
    const ghostRank = market.rawRank !== market.stateRank ? market.rawRank : null;
    const rungs = CAP_STATES.map((state, index) => {
      const lit = index === market.stateRank;
      const ghost = ghostRank != null && index === ghostRank;
      const classes = ['cap-rung', `cap-rank-${index}`];
      if (lit) classes.push('is-lit');
      if (ghost) classes.push('is-pending');
      if (index < market.stateRank) classes.push('is-passed');
      const flag = lit
        ? '<span class="cap-rung-flag">current state</span>'
        : ghost
          ? '<span class="cap-rung-flag is-ghost">raw reading &mdash; awaiting dwell</span>'
          : '';
      return `<li class="${classes.join(' ')}"${lit ? ' aria-current="step"' : ''}>
        <span class="cap-rung-bar" aria-hidden="true"></span>
        <span class="cap-rung-step">${index}</span>
        <span class="cap-rung-name">${escapeHtml(state.label)}</span>
        <span class="cap-rung-rule">${escapeHtml(state.rule)}</span>
        ${flag}
      </li>`;
    }).join('');
    const dwell = ghostRank == null
      ? `<p class="cap-dwell">Published state and raw reading agree at <b>${escapeHtml(stateLabel(market.state))}</b>. Hysteresis needs 2 repeat observations to upgrade a state and 3 to downgrade it.</p>`
      : `<p class="cap-dwell"><b>Dwell in progress.</b> The raw reading is <b>${escapeHtml(stateLabel(market.rawState))}</b> but the published state is still <b>${escapeHtml(stateLabel(market.state))}</b>: a change needs 2 repeat observations to upgrade and 3 to downgrade, so a single bar cannot move the ladder. The ghost marker is the pending reading, not the state.</p>`;
    return `<ol class="cap-ladder" aria-label="Capitulation ladder: five ordered states, current state ${escapeHtml(stateLabel(market.state))}">${rungs}</ol>${dwell}`;
  }

  function capScoreTile(label, value, detail, escapeHtml) {
    const number = finite(value);
    const width = number == null ? 0 : Math.max(0, Math.min(100, number));
    return `<div class="cap-score">
      <span class="cap-score-label">${escapeHtml(label)}</span>
      <strong class="cap-score-value">${escapeHtml(one(number))}</strong>
      <span class="cap-score-track" role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${number == null ? 0 : Math.round(number)}" aria-label="${escapeHtml(`${label} ${one(number)} of 100`)}"><span style="width:${width}%"></span></span>
      <small>${escapeHtml(detail)}</small>
    </div>`;
  }

  // The single most important property on this page: an exhaustion score that
  // the model itself says is not a capitulation reading must be impossible to
  // read as one. It is struck through, greyed, flagged, and carries the
  // model's own reason.
  function capExhaustion(market, escapeHtml) {
    if (market.exhaustionMeaningful) {
      return `<div class="cap-score cap-exhaustion is-live">
        <span class="cap-score-label">Exhaustion confirmation</span>
        <strong class="cap-score-value">${escapeHtml(one(market.exhaustion))}</strong>
        <span class="cap-score-track" role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(finite(market.exhaustion) || 0)}" aria-label="${escapeHtml(`Exhaustion ${one(market.exhaustion)} of 100`)}"><span style="width:${Math.max(0, Math.min(100, finite(market.exhaustion) || 0))}%"></span></span>
        <b class="cap-live-flag">Live signal &mdash; panic reached the stress threshold</b>
      </div>`;
    }
    return `<div class="cap-score cap-exhaustion is-void">
      <span class="cap-score-label">Exhaustion confirmation</span>
      <strong class="cap-score-value"><s>${escapeHtml(one(market.exhaustion))}</s></strong>
      <b class="cap-void-flag">Not a capitulation signal</b>
      <p class="cap-void-reason">${escapeHtml(market.exhaustionReason || 'The ladder has not reached its stress threshold, so this score is not a capitulation reading.')}</p>
    </div>`;
  }

  function capConfirmations(market, escapeHtml) {
    const items = CONFIRMATION_LABELS.map(([key, label]) => {
      const met = !!market.confirmations[key];
      return `<li class="cap-check ${met ? 'is-met' : 'is-unmet'}">
        <span class="cap-check-mark" aria-hidden="true">${met ? '&#10003;' : '&#10007;'}</span>
        <span class="cap-check-label">${escapeHtml(label)}</span>
        <span class="cap-check-state">${met ? 'yes' : 'no'}</span>
      </li>`;
    }).join('');
    return `<div class="cap-checks">
      <div class="cap-checks-head"><span class="criticality-kicker">Stabilization confirmations</span>
        <strong>${escapeHtml(String(market.confirmationCount))} of ${escapeHtml(String(CONFIRMATION_LABELS.length))} met</strong></div>
      <ul class="cap-check-list">${items}</ul>
      <small>Confirmed exhaustion requires at least 3 of these <em>and</em> panic 75+ with exhaustion 65+. On their own they are ordinary bar mechanics that occur most sessions.</small>
    </div>`;
  }

  function capDrawdown(market, escapeHtml) {
    const window_ = market.drawdownWindow == null ? 252 : Math.round(market.drawdownWindow);
    const depth = finite(market.drawdownPct);
    const days = finite(market.daysSinceHigh);
    const depthText = depth == null ? 'an unknown distance' : `${Math.abs(depth).toFixed(2)}%`;
    const daysText = days == null ? 'an unknown number of sessions ago' : `${Math.round(days)} session${Math.round(days) === 1 ? '' : 's'} ago`;
    const body = market.inDrawdown
      ? `SPY is <b>${escapeHtml(depthText)} below</b> its ${escapeHtml(String(window_))}-session high, set ${escapeHtml(daysText)}. There is a selloff to measure, so the ladder above is reading a live drawdown.`
      : `SPY is <b>${escapeHtml(depthText)} below</b> its ${escapeHtml(String(window_))}-session high, set ${escapeHtml(daysText)} &mdash; <b>not in a selloff</b>. With no drawdown to measure, the capitulation model is idle by construction; nothing here is a signal.`;
    return `<div class="cap-drawdown ${market.inDrawdown ? 'is-drawdown' : 'is-calm'}">
      <span class="criticality-kicker">Drawdown context</span>
      <p>${body}</p>
    </div>`;
  }

  function capSectorMap(sectors, escapeHtml) {
    if (!sectors.length) {
      return '<div class="cap-empty">No sector rows in this snapshot.</div>';
    }
    const ordered = sectors.slice().sort((a, b) => (b.stateRank - a.stateRank) || ((b.panic || 0) - (a.panic || 0)));
    const elevated = ordered.filter((row) => row.stateRank >= CAP_RANK.stress);
    const past = ordered.filter((row) => row.stateRank > 0);
    const chip = (row) => `<b class="cap-chip cap-rank-${row.stateRank}">${escapeHtml(stateLabel(row.state))}</b>`;

    if (!past.length) {
      const worst = ordered.slice(0, 3);
      return `<div class="cap-sector-summary">
        <p><b>${escapeHtml(String(ordered.length))} sectors, none past <code>normal</code></b> &mdash; no sector-level capitulation. Eleven rows of the same word is not information, so only the three highest-panic sectors are listed.</p>
        <ul class="cap-sector-worst">${worst.map((row) => `<li>
          <span class="cap-sector-symbol">${escapeHtml(row.symbol)}</span>
          <span class="cap-sector-name">${escapeHtml(row.name)}</span>
          <span class="cap-sector-metric">panic <b>${escapeHtml(one(row.panic))}</b></span>
          <span class="cap-sector-metric">drawdown <b>${escapeHtml(row.drawdownPct == null ? '—' : `${row.drawdownPct.toFixed(2)}%`)}</b></span>
        </li>`).join('')}</ul>
      </div>`;
    }

    return `<div class="cap-sector-grid" role="table" aria-label="Sector capitulation map ranked by ladder state then panic">
      <div class="cap-sector-row cap-sector-header" role="row">
        <span>Sector</span><span>State</span><span>Panic</span><span>Drawdown</span><span>Exhaustion</span>
      </div>
      ${ordered.map((row) => `<div class="cap-sector-row${row.stateRank >= CAP_RANK.stress ? ' is-elevated' : ''}" role="row">
        <span><strong>${escapeHtml(row.symbol)}</strong><small>${escapeHtml(row.name)}</small></span>
        <span>${chip(row)}</span>
        <span>${escapeHtml(one(row.panic))}</span>
        <span>${escapeHtml(row.drawdownPct == null ? '—' : `${row.drawdownPct.toFixed(2)}%`)}</span>
        <span>${row.exhaustionMeaningful ? escapeHtml(one(row.exhaustion)) : '<small class="cap-na">not meaningful</small>'}</span>
      </div>`).join('')}
      ${elevated.length ? `<p class="cap-sector-note">${escapeHtml(String(elevated.length))} sector${elevated.length === 1 ? '' : 's'} at <code>stress</code> or beyond, highlighted above.</p>` : ''}
    </div>`;
  }

  function capProvenance(resolved, escapeHtml) {
    const asOf = String(resolved.asOf || '').replace('T', ' ').slice(0, 19) || 'unknown';
    if (resolved.basis === 'live') {
      return `<p class="cap-provenance is-live"><b>LIVE intraday feed.</b> Source ${escapeHtml(String(resolved.source))}, as of ${escapeHtml(asOf)}${resolved.qualityState ? ` (${escapeHtml(String(resolved.qualityState))})` : ''}.</p>`;
    }
    const coverage = resolved.coverage || {};
    const cover = finite(coverage.symbols_ok) == null
      ? ''
      : ` Coverage ${finite(coverage.symbols_ok)} of ${finite(coverage.symbols_requested)} symbols.`;
    return `<p class="cap-provenance is-daily"><b>DAILY model (live intraday feed unavailable).</b> The same forced-flow model run on daily bars: source ${escapeHtml(String(resolved.source))}, as of ${escapeHtml(asOf)}${resolved.qualityState ? ` (${escapeHtml(String(resolved.qualityState))})` : ''}.${escapeHtml(cover)} This is not an intraday reading and is never presented as one.</p>`;
  }

  function capitulationSection(resolved, escapeHtml) {
    if (!resolved || !resolved.market) {
      return `<section class="cap-panel"><div class="cap-panel-head"><div>
          <span class="criticality-kicker">Forced-flow capitulation · research only</span>
          <h2>Capitulation ladder</h2></div></div>
        <div class="risk-empty">No capitulation reading is loaded. Neither a live intraday flow snapshot nor data/capitulation_daily.json was reachable, so this panel shows nothing rather than substituting a different feed for one it does not have. The rest of the risk page is unaffected.</div>
      </section>`;
    }
    const market = resolved.market;
    return `<section class="cap-panel">
      <div class="cap-panel-head">
        <div><span class="criticality-kicker">Forced-flow capitulation · research only</span>
          <h2>Capitulation ladder &middot; ${escapeHtml(market.symbol)}</h2>
          <p>How far into capitulation a selloff has progressed, on the model's own five-state ladder. A score is only a capitulation reading when the ladder says the tape earned it.</p></div>
        <div class="cap-panel-state">
          <strong class="cap-rank-${market.stateRank}">${escapeHtml(stateLabel(market.state))}</strong>
          <small>state ${escapeHtml(String(market.stateRank))} of 4${market.barCount == null ? '' : ` · ${escapeHtml(String(Math.round(market.barCount)))} bars`}</small>
        </div>
      </div>
      ${capProvenance(resolved, escapeHtml)}
      ${capLadder(market, escapeHtml)}
      <div class="cap-score-row">
        ${capScoreTile('Mechanical pressure', market.pressure, 'Return stress, vol acceleration and downside share. 55 opens the ladder.', escapeHtml)}
        ${capScoreTile('Panic', market.panic, 'Pressure plus volume and range extremes. 70 is the stress threshold.', escapeHtml)}
        ${capExhaustion(market, escapeHtml)}
      </div>
      <div class="cap-evidence">
        ${capConfirmations(market, escapeHtml)}
        ${capDrawdown(market, escapeHtml)}
      </div>
      <div class="cap-sectors">
        <div class="cap-checks-head"><span class="criticality-kicker">Sector capitulation map</span>
          <strong>ranked by ladder state, then panic</strong></div>
        ${capSectorMap(resolved.sectors || [], escapeHtml)}
      </div>
    </section>`;
  }

  // ---------------------------------------------------------------------
  // Regime verdict + trust line
  //
  // Composed deterministically from whatever survived the page: never a
  // hardcoded sentence. Each clause carries its own explicit threshold so the
  // verdict can be audited against the data it claims to summarise.
  // ---------------------------------------------------------------------

  function ordinal(value) {
    const number = Math.round(value);
    const mod100 = number % 100;
    if (mod100 >= 11 && mod100 <= 13) return `${number}th`;
    return `${number}${['th', 'st', 'nd', 'rd'][number % 10] || 'th'}`;
  }

  function composeVerdict(context) {
    const clauses = [];
    let stress = 0;

    const vixPct = finite(context.vixPct1y);
    if (vixPct == null) clauses.push('VIX percentile unavailable');
    else {
      clauses.push(`Vol in the ${ordinal(vixPct)} percentile of the last year`);
      if (vixPct >= 80) stress += 2; else if (vixPct >= 60) stress += 1;
    }

    const term = String(context.termState || '').toLowerCase().replace(/_/g, ' ');
    if (!term || term === 'unknown') clauses.push('term state unavailable');
    else {
      clauses.push(`curve in ${term}`);
      if (term === 'backwardation') stress += 2; else if (term === 'flat') stress += 1;
    }

    const ivrv = finite(context.ivRvSpread);
    if (ivrv == null) clauses.push('IV-RV spread unavailable');
    else if (ivrv >= 0) clauses.push(`realized below implied (IV-RV +${ivrv.toFixed(2)})`);
    else { clauses.push(`realized above implied (IV-RV ${ivrv.toFixed(2)})`); stress += 1; }

    const capState = context.capState ? String(context.capState) : null;
    const capRank = finite(context.capStateRank);
    if (!capState) clauses.push('no capitulation reading loaded');
    else {
      const idle = (capRank || 0) === 0;
      clauses.push(`capitulation model ${idle ? 'idle' : 'active'} at ${capState.replace(/_/g, ' ')}`);
      if ((capRank || 0) >= 3) stress += 2; else if ((capRank || 0) >= 2) stress += 1;
    }

    const fear = finite(context.fearPanic);
    if (fear != null) {
      clauses.push(`tape fear ${Math.round(fear)} of 100`);
      if (fear >= 70) stress += 2; else if (fear >= 50) stress += 1;
    }

    const verdict = stress <= 0
      ? 'calm regime, no sizing change indicated'
      : stress <= 2
        ? 'mixed regime, nothing here forces a sizing change'
        : stress <= 4
          ? 'elevated stress, size new risk smaller until the curve and realized vol agree'
          : 'stressed regime, capital-preservation posture until the tape confirms a peak';

    return { text: `${clauses.join(', ')} - ${verdict}.`, stress, verdict };
  }

  function composeTrustLine(volLatest, resolved) {
    const coverage = volLatest?.coverage || {};
    const lagging = coverage.metrics_lagging || {};
    const gaps = coverage.metrics_with_gaps || {};
    const asOf = String(volLatest?.as_of || '').slice(0, 10);
    const parts = [];

    const worst = Object.entries(lagging)
      .map(([metric, lag]) => ({ metric, behind: finite(lag?.sessions_behind) || 0, date: String(lag?.last_value_date || '').slice(0, 10) }))
      .sort((a, b) => b.behind - a.behind)[0];
    if (!worst) parts.push('every vol feed printed on the snapshot date');
    else parts.push(`worst feed lag is ${worst.metric.toUpperCase().replace(/_/g, ' ')} at ${worst.behind} session${worst.behind === 1 ? '' : 's'} behind (last print ${worst.date})`);

    // An interior gap is a hole that has since closed - invisible in
    // metrics_lagging, which only reports feeds whose LAST print is old.
    const interior = Object.entries(gaps)
      .map(([metric, gap]) => ({ metric, missing: finite(gap?.sessions_missing) || 0, last: String(gap?.last_missing || '').slice(0, 10) }))
      .filter((row) => row.last && row.last < asOf);
    if (!interior.length) parts.push('no interior gaps in the reported window');
    else {
      const deepest = interior.slice().sort((a, b) => b.missing - a.missing)[0];
      const closed = interior.slice().sort((a, b) => b.last.localeCompare(a.last))[0];
      parts.push(`${interior.length} metric${interior.length === 1 ? '' : 's'} had an interior gap of up to ${deepest.missing} sessions that closed ${closed.last}`);
    }

    if (resolved && resolved.basis === 'daily') parts.push('the capitulation reading is the daily model, not the live intraday feed');
    return `${parts.join('; ')}.`;
  }

  function renderRegimeVerdict(options = {}) {
    const escapeHtml = options.escapeHtml || escapeFallback;
    const volLatest = options.volLatest || null;
    const regime = volLatest?.regime || {};
    const internal = options.marketContext?.internal || {};
    const resolved = options.resolvedCapitulation
      || resolveCapitulation(options.capitulation, options.payload, options.details);
    const verdict = composeVerdict({
      vixPct1y: regime.vix_pct1y ?? volLatest?.metrics?.vix?.pct1y,
      termState: regime.term_state,
      ivRvSpread: regime.iv_rv_spread ?? volLatest?.metrics?.iv_rv_spread?.value,
      capState: resolved?.market?.state || null,
      capStateRank: resolved?.market?.stateRank,
      fearPanic: internal?.scores?.panic,
    });
    const trust = composeTrustLine(volLatest, resolved);
    return `<section class="regime-verdict stress-${verdict.stress <= 0 ? 'calm' : verdict.stress <= 2 ? 'mixed' : verdict.stress <= 4 ? 'elevated' : 'stressed'}">
      <span class="criticality-kicker">Regime verdict · composed from the data below, never stored</span>
      <p class="regime-verdict-line">${escapeHtml(verdict.text)}</p>
      <p class="regime-trust-line"><b>Trust:</b> ${escapeHtml(trust)}</p>
    </section>`;
  }

  function renderRiskView(payload, details = {}, options = {}) {
    const escapeHtml = options.escapeHtml || escapeFallback;
    const health = details.health || {};
    const ingest = health.latest_ingest || {};
    const alerts = details.alerts?.items || [];
    const status = health.status || 'static_fallback';
    const receivedFresh = freshness(ingest.received_at);
    const resolved = options.resolvedCapitulation
      || resolveCapitulation(options.capitulation, payload, details);
    return `<div class="risk-view-head"><div><span class="criticality-kicker">Systemic risk lab · research only</span><h2>Criticality &amp; forced-flow capitulation</h2>
      <p>Tracks unstable price regimes and how far into capitulation a selloff has progressed. Signals are descriptive—not automatic trade instructions.</p></div>
      <div class="risk-live-state"><span class="risk-status-dot ${status === 'operational' ? 'is-live' : ''}"></span><strong>${escapeHtml(status.replace(/_/g, ' '))}</strong><small>${escapeHtml(receivedFresh.label)}</small></div></div>
      ${capitulationSection(resolved, escapeHtml)}
      ${render(payload, { ...options, open: true, expandSectors: true })}
      ${componentStack(payload, escapeHtml)}
      <div class="risk-grid">
        <section class="risk-card risk-history"><header><h3>SPY criticality history</h3><div class="risk-legend"><span class="criticality-positive">LPPLS criticality score</span></div></header>${historyChart(details)}</section>
        <section class="risk-card"><h3>Feed health</h3><dl class="risk-health">
          <div><dt>Last signed ingest</dt><dd>${escapeHtml(ingest.received_at ? String(ingest.received_at).replace('T', ' ').slice(0, 19) + ' UTC' : 'Awaiting first live snapshot')}</dd></div>
          <div><dt>Latest flow</dt><dd>${escapeHtml(health.snapshots?.latest_flow_at || '—')}</dd></div>
          <div><dt>Stored snapshots</dt><dd>${whole(health.snapshots?.criticality_count)} criticality · ${whole(health.snapshots?.flow_count)} flow · ${whole(health.snapshots?.component_count)} components</dd></div>
          <div><dt>Open alerts</dt><dd>${whole(health.alerts?.open_count)}</dd></div></dl></section>
        <section class="risk-card"><h3>Alert journal</h3>${alerts.length ? `<div class="risk-alerts">${alerts.slice(0, 12).map((alert) => `<article><strong>${escapeHtml(alert.symbol)} · ${escapeHtml(alert.state.replace(/_/g, ' '))}</strong><span class="risk-severity risk-severity-${escapeHtml(alert.severity)}">${escapeHtml(alert.severity)}</span><small>${escapeHtml((alert.reason_codes || []).join(' · '))}</small></article>`).join('')}</div>` : '<div class="risk-empty">No alert episodes recorded. Alerts come from the Databento flow monitor, a local scheduled task that runs outside CI—if that task is not running, this journal stays empty even during market stress.</div>'}</section>
      </div>
      <section class="risk-method"><h3>Interpretation guardrails</h3><p><strong>Criticality</strong> asks whether price dynamics resemble an unstable LPPLS regime. <strong>Pressure</strong> estimates mechanical stress consistent with volatility-sensitive deleveraging. <strong>Exhaustion</strong> requires stabilization evidence and persistence, and is only a capitulation reading once the ladder has reached its stress threshold — below that the score describes ordinary bar mechanics and is shown struck through. A critical time is a probability window, not a scheduled crash; all outputs remain research-only until shadow validation establishes calibration and false-positive behavior.</p></section>`;
  }

  global.CriticalityViz = {
    directionMeta, freshness, render, renderRiskView, renderRegimeVerdict,
    resolveCapitulation, composeVerdict, composeTrustLine, capitulationSection,
    CAP_STATES, CONFIRMATION_LABELS,
  };
})(window);
