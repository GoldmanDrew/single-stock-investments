(function (global) {
  'use strict';

  const base = global.TechnicalViz || {};

  function finite(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  function whole(value) {
    const number = finite(value);
    return number == null ? '—' : Math.round(number);
  }

  function pct(value, digits) {
    const number = finite(value);
    if (number == null) return '—';
    return `${number > 0 ? '+' : ''}${number.toFixed(digits == null ? 1 : digits)}%`;
  }

  function compact(value) {
    const number = finite(value);
    if (number == null) return '—';
    if (Math.abs(number) >= 1e9) return `${(number / 1e9).toFixed(2)}B`;
    if (Math.abs(number) >= 1e6) return `${(number / 1e6).toFixed(1)}M`;
    if (Math.abs(number) >= 1e3) return `${(number / 1e3).toFixed(1)}K`;
    return Math.round(number).toLocaleString();
  }

  function tone(value) {
    return {
      falling_knife: 'picture-negative',
      lagging_downtrend: 'picture-negative',
      distribution: 'picture-negative',
      deeply_oversold: 'picture-warning',
      oversold: 'picture-warning',
      stabilizing: 'picture-positive',
      trend_intact: 'picture-positive',
      leading_uptrend: 'picture-positive',
      accumulation: 'picture-positive',
    }[String(value || '')] || 'picture-neutral';
  }

  function priceChart(history, escapeHtml) {
    const points = (history || [])
      .map((row) => [String(row[0] || ''), finite(row[1])])
      .filter((row) => row[0] && row[1] != null);
    if (points.length < 2) {
      return '<div class="technical-chart-empty">Price history will appear after the nightly refresh.</div>';
    }
    const width = 620;
    const height = 102;
    const values = points.map((row) => row[1]);
    const low = Math.min(...values);
    const high = Math.max(...values);
    const span = high - low || 1;
    const path = points.map((row, index) => {
      const x = index / (points.length - 1) * width;
      const y = height - (row[1] - low) / span * (height - 14) - 7;
      return `${index ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
    const change = values[0] > 0 ? (values[values.length - 1] / values[0] - 1) * 100 : null;
    return `<figure class="technical-chart">
      <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="One-year adjusted price history">
        <title>Adjusted close from ${escapeHtml(points[0][0])} to ${escapeHtml(points[points.length - 1][0])}</title>
        <path class="technical-chart-baseline" d="M0,${height - 8} L${width},${height - 8}"></path>
        <path class="technical-chart-line" d="${path}"></path>
      </svg>
      <figcaption><span>${escapeHtml(points[0][0])}</span><strong>${pct(change)}</strong><span>${escapeHtml(points[points.length - 1][0])}</span></figcaption>
    </figure>`;
  }

  function shortChart(structure, escapeHtml) {
    const points = (structure.history || [])
      .map((row) => {
        const value = finite(row.short_percent_float);
        return [String(row.date || ''), value == null ? null : value * 100];
      })
      .filter((row) => row[0] && row[1] != null);
    if (points.length < 2) {
      return '<p class="market-structure-empty">History starts with each reported short-interest refresh.</p>';
    }
    const width = 330;
    const height = 48;
    const values = points.map((row) => row[1]);
    const low = Math.min(...values);
    const high = Math.max(...values);
    const span = high - low || 1;
    const path = points.map((row, index) => {
      const x = index / (points.length - 1) * width;
      const y = height - (row[1] - low) / span * (height - 12) - 6;
      return `${index ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
    return `<figure class="short-history-chart">
      <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Reported short interest as a percentage of float over time">
        <title>Reported short interest from ${escapeHtml(points[0][0])} to ${escapeHtml(points[points.length - 1][0])}</title>
        <path d="${path}"></path>
      </svg>
      <figcaption><span>${escapeHtml(points[0][0])}</span><strong>${values[values.length - 1].toFixed(1)}% of float</strong><span>${escapeHtml(points[points.length - 1][0])}</span></figcaption>
    </figure>`;
  }

  function valuationRead(ticker) {
    const decision = ticker.valuation_decision || {};
    const values = decision.value_per_share || ticker.component_valuation?.total_equity_value_per_share || {};
    const price = finite(decision.price_per_share ?? ticker.component_valuation?.market_price_per_share);
    const low = finite(values.low);
    const valueBase = finite(values.base);
    const high = finite(values.high);
    if (price == null || (valueBase == null && high == null)) {
      return { label: 'Valuation incomplete', detail: decision.status || 'No usable value range', tone: 'picture-neutral' };
    }
    if (high != null && high > 0 && price > high) {
      return { label: 'Above modeled range', detail: `${pct((high / price - 1) * 100)} to high case`, tone: 'picture-negative' };
    }
    if (valueBase != null && valueBase > 0 && price < valueBase) {
      return { label: 'Below base value', detail: `${pct((valueBase / price - 1) * 100)} to base`, tone: 'picture-positive' };
    }
    if (low != null && low > 0 && price < low) {
      return { label: 'Below modeled range', detail: 'Price is below the low case', tone: 'picture-positive' };
    }
    return { label: 'Inside modeled range', detail: decision.status || 'Valuation available', tone: 'picture-neutral' };
  }

  function businessRead(ticker) {
    const momentum = ticker.kpi_trends?.business_momentum || {};
    const leadership = ticker.kpi_trends?.leadership_risk || {};
    const latest = ticker.essential_insights?.latest || {};
    const direction = String(momentum.direction || '');
    return {
      label: momentum.label || 'Business trend not scored',
      detail: leadership.label || latest.title || 'No fresh material insight',
      tone: direction === 'accelerating'
        ? 'picture-positive'
        : direction === 'decelerating'
          ? 'picture-warning'
          : 'picture-neutral',
    };
  }

  function macroRead(marketContext) {
    const internal = marketContext?.internal || {};
    const panic = finite(internal.scores?.panic);
    const state = String(internal.state || 'unavailable').replace(/_/g, ' ');
    return {
      label: internal.state ? `Market ${state}` : 'Macro context unavailable',
      detail: panic == null ? 'SPY fear tape unavailable' : `SPY panic ${Math.round(panic)}/100`,
      tone: panic != null && panic >= 70 ? 'picture-warning' : 'picture-neutral',
    };
  }

  function synthesis(setup, valuation, business, macro) {
    if (valuation.tone === 'picture-negative' && setup.phase === 'falling_knife') {
      return 'Fear is not margin of safety here: price remains above modeled value while the tape is still deteriorating. Reconcile valuation inputs and wait for stabilization.';
    }
    if (valuation.tone === 'picture-positive' && setup.phase === 'stabilizing') {
      return 'Fundamental discount and improving tape agree. Define an entry range, then keep evidence and business-trend gates intact.';
    }
    if (valuation.tone === 'picture-positive' && setup.phase === 'falling_knife') {
      return 'The valuation gap is attractive, but the stock is still a falling knife. Investigate whether the decline changes the business case before sequencing an entry.';
    }
    if (business.tone === 'picture-warning' && setup.participation === 'distribution') {
      return 'Fading business momentum and distribution reinforce one another. Elevate thesis review before treating oversold conditions as opportunity.';
    }
    if (macro.tone === 'picture-warning' && setup.direction === 'lagging_downtrend') {
      return 'Broad fear and stock-specific underperformance are both active. Separate macro beta from company-specific deterioration before acting.';
    }
    return 'Valuation, business evidence, tape, and macro are not strongly aligned. Keep the stance evidence-led and use the technical setup only for timing and risk.';
  }

  function investmentPicture(ticker, setup, marketContext, escapeHtml) {
    const valuation = valuationRead(ticker);
    const business = businessRead(ticker);
    const macro = macroRead(marketContext);
    const tape = {
      label: setup.phase_label || 'Technical setup unavailable',
      detail: `${setup.direction_label || 'Direction unavailable'} · ${setup.participation_label || 'volume unavailable'}`,
      tone: tone(setup.phase),
    };
    const lanes = [
      ['Valuation', valuation],
      ['Business', business],
      ['Tape', tape],
      ['Macro', macro],
    ];
    return `<section class="investment-picture" aria-label="Integrated investment picture">
      <div class="investment-picture-head">
        <div><span>Decision picture</span><strong>What agrees, what conflicts</strong></div>
        <p>${escapeHtml(synthesis(setup, valuation, business, macro))}</p>
      </div>
      <div class="investment-picture-grid">
        ${lanes.map(([name, row]) => `<div class="picture-lane ${row.tone}">
          <span>${name}</span><strong>${escapeHtml(row.label)}</strong><small>${escapeHtml(row.detail)}</small>
        </div>`).join('')}
      </div>
    </section>`;
  }

  function setupPillar(name, label, detail, read, value) {
    return `<div class="setup-pillar ${tone(value)}">
      <span>${name}</span>
      <strong>${label}</strong>
      <small>${detail}</small>
      <p>${read}</p>
    </div>`;
  }

  function marketStructure(structure, escapeHtml) {
    if (!structure || (!structure.float_shares && !structure.short_interest_shares)) {
      return `<section class="market-structure">
        <div class="section-kicker">Crowding & liquidity</div>
        <p class="market-structure-empty">Float and reported short interest are awaiting the free market-structure refresh.</p>
      </section>`;
    }
    const shortFloat = finite(structure.short_percent_float);
    const crowdLabel = shortFloat == null
      ? 'Crowding unavailable'
      : shortFloat >= 20
        ? 'Heavily shorted'
        : shortFloat >= 10
          ? 'Elevated short interest'
          : 'Light short interest';
    const crowdTone = shortFloat != null && shortFloat >= 20
      ? 'picture-warning'
      : 'picture-neutral';
    return `<section class="market-structure ${crowdTone}">
      <div class="market-structure-head">
        <div><span>Crowding & liquidity</span><strong>${crowdLabel}</strong></div>
        <span class="market-structure-date">Reported ${escapeHtml(structure.as_of || 'date unavailable')}</span>
      </div>
      <div class="market-structure-grid">
        <div><span>Float</span><strong>${compact(structure.float_shares)}</strong><small>${pct(structure.float_percent_outstanding)} of shares outstanding</small></div>
        <div><span>Shares short</span><strong>${compact(structure.short_interest_shares)}</strong><small>${shortFloat == null ? '—' : shortFloat.toFixed(1) + '%'} of float</small></div>
        <div><span>Change</span><strong>${pct(structure.short_change_pct)}</strong><small>versus prior report</small></div>
        <div><span>Days to cover</span><strong>${finite(structure.days_to_cover) == null ? '—' : finite(structure.days_to_cover).toFixed(1)}</strong><small>reported short ratio</small></div>
        <div class="market-structure-history">${shortChart(structure, escapeHtml)}</div>
      </div>
      <p class="market-structure-note">Reported short interest is a twice-monthly position snapshot. It is not FINRA daily short-sale volume.</p>
    </section>`;
  }

  function fearRail(label, value) {
    const number = finite(value);
    const width = number == null ? 0 : Math.max(0, Math.min(100, number));
    return `<div class="fear-rail">
      <div class="fear-rail-head"><span>${label}</span><strong>${whole(number)}</strong></div>
      <div class="fear-rail-track" aria-label="${label}: ${whole(number)} out of 100"><span style="width:${width}%"></span></div>
    </div>`;
  }

  function confirmations(values) {
    const rows = [
      ['Positive session', values.positive_session],
      ['Closed in upper half', values.closed_upper_half],
      ['Reclaimed prior high', values.reclaimed_prior_high],
      ['Volume cooled after climax', values.volume_cooled],
    ];
    return rows.map(([label, passed]) =>
      `<li class="${passed ? 'confirmation-pass' : 'confirmation-wait'}"><span aria-hidden="true">${passed ? '✓' : '○'}</span>${label}</li>`
    ).join('');
  }

  function renderPanel(ticker, helpers) {
    const escapeHtml = helpers.escapeHtml;
    const marketContext = helpers.marketContext || {};
    const technicals = ticker.technicals;
    if (!technicals) {
      return `<details class="detail-section technical-panel">
        <summary>Stock setup · awaiting first refresh</summary>
        <p class="tier-sub" style="margin-top:9px">The free-price job has not produced a snapshot for this security yet.</p>
      </details>`;
    }
    const setup = technicals.setup || {};
    const indicators = setup.indicators || {};
    const capitulation = technicals.capitulation || {};
    const scores = capitulation.scores || {};
    const families = capitulation.families || {};
    const measures = technicals.measures || {};
    const fear = base.fearMeta ? base.fearMeta(capitulation.state) : { label: capitulation.state || 'unavailable', cls: 'fear-normal', marker: '·' };
    const directionRead = `${pct(indicators.price_vs_50d_pct)} vs 50d · ${pct(indicators.price_vs_200d_pct)} vs 200d · ${pct(measures.relative_return_60d_pct)} vs SPY`;
    const pressureRead = `RSI ${finite(indicators.rsi_14) == null ? '—' : finite(indicators.rsi_14).toFixed(0)} · panic ${whole(scores.panic)}/100 · exhaustion ${whole(scores.exhaustion)}/100`;
    const participationRead = `CMF ${finite(indicators.chaikin_money_flow_20d) == null ? '—' : finite(indicators.chaikin_money_flow_20d).toFixed(2)} · volume ${finite(indicators.relative_volume_20d) == null ? '—' : finite(indicators.relative_volume_20d).toFixed(1) + '×'} normal · ATR ${pct(indicators.atr_20d_pct)}`;
    return `<details class="detail-section technical-panel" open>
      <summary>Stock setup · <span class="${fear.cls}">${escapeHtml(setup.phase_label || fear.label)}</span></summary>
      <div class="technical-panel-body">
        ${investmentPicture(ticker, setup, marketContext, escapeHtml)}
        <section class="stock-setup">
          <div class="stock-setup-head ${fear.cls}">
            <div><span aria-hidden="true">${fear.marker}</span><strong>${escapeHtml(setup.phase_label || fear.label)}</strong></div>
            <p>${escapeHtml(capitulation.interpretation || technicals.regime?.interpretation || 'No unusual technical condition')}</p>
            <span class="setup-confidence">${escapeHtml(technicals.data_grade || '—')} grade · ${whole(scores.confidence)}% coverage</span>
          </div>
          <div class="stock-setup-grid">
            ${setupPillar('Direction', escapeHtml(setup.direction_label || 'Unavailable'), escapeHtml(setup.explainers?.direction || ''), directionRead, setup.direction)}
            ${setupPillar('Pressure', escapeHtml(setup.pressure_label || 'Unavailable'), escapeHtml(setup.explainers?.pressure || ''), pressureRead, setup.pressure)}
            ${setupPillar('Participation', escapeHtml(setup.participation_label || 'Unavailable'), escapeHtml(setup.explainers?.participation || ''), participationRead, setup.participation)}
          </div>
        </section>
        ${marketStructure(technicals.market_structure, escapeHtml)}
        ${priceChart(technicals.history, escapeHtml)}
        <details class="technical-diagnostics">
          <summary>Why the model says ${escapeHtml(fear.label)} · detailed diagnostics</summary>
          <div class="fear-monitor-grid">
            <div class="fear-family-rails">
              ${fearRail('Price dislocation', families.price_dislocation)}
              ${fearRail('Selling climax', families.selling_climax)}
              ${fearRail('Volatility stress', families.volatility_stress)}
              ${fearRail('Relative / path stress', families.relative_path_stress)}
            </div>
            <div class="fear-confirmation">
              <span class="fear-section-label">What would confirm exhaustion</span>
              <ul>${confirmations(capitulation.confirmation || {})}</ul>
              <p>Extreme fear is not a bottom. Confirmation requires stabilization after climactic selling.</p>
            </div>
          </div>
          <div class="technical-metric-grid">
            <div class="technical-metric"><span>20-day return</span><strong>${pct(measures.return_20d_pct)}</strong></div>
            <div class="technical-metric"><span>60-day vs SPY</span><strong>${pct(measures.relative_return_60d_pct)}</strong></div>
            <div class="technical-metric"><span>1-year drawdown</span><strong>${pct(measures.drawdown_1y_pct)}</strong></div>
            <div class="technical-metric"><span>Realized volatility</span><strong>${pct(measures.realized_volatility_20d_pct)}</strong></div>
            <div class="technical-metric"><span>Pressure</span><strong>${whole(scores.pressure)}/100</strong></div>
            <div class="technical-metric"><span>Exhaustion</span><strong>${whole(scores.exhaustion)}/100</strong></div>
          </div>
        </details>
        <div class="technical-foot">
          <span>${escapeHtml(technicals.data_grade_reason || 'Technical data quality unavailable')}</span>
          <span class="mono">${escapeHtml(technicals.as_of || '—')} · ${escapeHtml(technicals.source || 'source pending')} · benchmark ${escapeHtml(technicals.benchmark || '—')}</span>
        </div>
        <div class="technical-references">
          <span>Method references:</span>
          <a href="https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators" target="_blank" rel="noopener">StockCharts indicators</a>
          <a href="https://www.finra.org/investors/insights/short-interest" target="_blank" rel="noopener">FINRA short interest</a>
        </div>
        <p class="technical-policy">Timing and risk overlay only. It cannot upgrade valuation readiness, clear evidence blockers, or change stance automatically.</p>
      </div>
    </details>`;
  }

  global.TechnicalViz = Object.assign({}, base, {
    renderPanel,
  });
})(typeof window !== 'undefined' ? window : globalThis);
