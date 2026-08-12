(function (global) {
  'use strict';
  const state = { query: '', lane: 'all', lifecycle: 'active', status: 'all' };
  const esc = value => String(value == null ? '' : value)
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#39;');
  const number = (value, digits = 2) => value == null || Number.isNaN(Number(value)) ? '—' : Number(value).toFixed(digits);
  const money = value => value == null || Number.isNaN(Number(value)) ? '—' : `$${Number(value).toFixed(Number(value) < 1 ? 3 : 2)}`;
  const pct = value => value == null || Number.isNaN(Number(value)) ? '—' : `${Number(value).toFixed(1)}%`;
  const words = value => String(value || '—').replaceAll('_', ' ');
  function option(value, label, selected) { return `<option value="${esc(value)}"${selected === value ? ' selected' : ''}>${esc(label)}</option>`; }
  function clockMarkup(clock, compact) {
    const elapsed = Math.max(0, Math.min(100, Number(clock?.elapsed_pct || 0)));
    const days = clock?.days_to_expiry;
    const label = days == null ? '—' : days < 0 ? 'ended' : `${days}d`;
    return `<div class="${compact ? 'warrant-clock-cell' : ''}"><div class="warrant-clock-ring" style="--clock:${elapsed}"><strong>${esc(label)}</strong><small>remaining</small></div>${compact ? `<div class="warrant-cell">${esc(label)}<small>${esc(clock?.expiry || 'unknown expiry')}</small></div>` : ''}</div>`;
  }
  function gateMarkup(label, gate, passText) {
    const missing = gate?.missing || [];
    return `<article class="warrant-gate${gate?.pass ? ' pass' : ''}"><header><h4>${esc(label)}</h4><b>${gate?.pass ? 'pass' : 'blocked'}</b></header><p>${gate?.pass ? esc(passText) : esc(missing.join(' · ') || 'Evidence is incomplete.')}</p></article>`;
  }
  function rowMarkup(row) {
    const terms = row.terms || {}; const market = row.market || {}; const diag = row.diagnostics || {};
    const common = market.common || {}; const warrant = market.warrant || {}; const gates = row.gates || {};
    const source = row.source || {}; const call = terms.call || {}; const survival = row.survival || {};
    return `<details class="warrant-row">
      <summary>
        <div class="warrant-name"><strong>${esc(row.warrant_ticker)}</strong><span>${esc(row.issuer)} · ${esc(row.common_ticker)}</span></div>
        <div><span class="warrant-badge ${esc(row.priority)}">${esc(row.priority)}</span><small style="display:block;margin-top:4px;color:var(--text-muted)">${esc(words(row.lane))}</small></div>
        ${clockMarkup(row.contract_clock, true)}
        <div class="warrant-cell">${money(common.close)}<small>common · ${esc(common.quote_date || 'no mark')}</small></div>
        <div class="warrant-cell">${money(warrant.close)}<small>warrant · ADV ${warrant.adv20 == null ? '—' : Math.round(warrant.adv20).toLocaleString()}</small></div>
        <div><span class="warrant-badge ${esc(row.status)}">${esc(words(row.status))}</span><small style="display:block;margin-top:4px;color:var(--text-muted)">${esc(words(diag.model_route))}</small></div>
      </summary>
      <div class="warrant-detail">
        <div class="warrant-gates">
          ${gateMarkup('1 · identity + terms', gates.identity, 'Series, agreement, strike, ratio, and expiry are source-locked.')}
          ${gateMarkup('2 · issuer survival', gates.survival, 'Liquidity, debt, dilution, and survival packet pass.')}
          ${gateMarkup('3 · executable market', gates.market, 'Fresh two-sided quote supports executable comparison.')}
        </div>
        <div class="warrant-detail-grid">
          <article class="warrant-card"><h4>Contract</h4><dl>
            <div><dt>Strike</dt><dd>${money(terms.strike)} ${esc(terms.strike_basis === 'per_share' ? '/ share' : '/ warrant')}</dd></div>
            <div><dt>Exercise cash</dt><dd>${money(diag.exercise_cost_per_warrant)} / warrant</dd></div>
            <div><dt>Ratio</dt><dd>${number(terms.share_ratio, 4)} share</dd></div>
            <div><dt>Expiry</dt><dd>${esc(terms.expiry || '—')}</dd></div>
            <div><dt>Settlement</dt><dd>${esc(words(terms.settlement))}</dd></div>
            <div><dt>Callable</dt><dd>${terms.callable ? `yes${(call.trigger ?? call.stock_trigger) != null ? ` · trigger ${money(call.trigger ?? call.stock_trigger)}` : ''}` : 'no'}</dd></div>
            <div><dt>Outstanding</dt><dd>${terms.warrants_outstanding == null ? '—' : Number(terms.warrants_outstanding).toLocaleString()}</dd></div>
          </dl></article>
          <article class="warrant-card"><h4>Delayed market</h4><dl>
            <div><dt>Common close</dt><dd>${money(common.close)}</dd></div>
            <div><dt>Warrant close</dt><dd>${money(warrant.close)}</dd></div>
            <div><dt>Warrant ADV20</dt><dd>${warrant.adv20 == null ? '—' : Math.round(warrant.adv20).toLocaleString()}</dd></div>
            <div><dt>Bid / ask</dt><dd>${money(warrant.bid)} / ${money(warrant.ask)}</dd></div>
            <div><dt>Age</dt><dd>${market.quote_age_days == null ? '—' : `${market.quote_age_days}d`}</dd></div>
            <div><dt>Executable</dt><dd>${market.executable ? 'yes' : 'no'}</dd></div>
          </dl></article>
          <article class="warrant-card"><h4>Contract diagnostics</h4><dl>
            <div><dt>Intrinsic</dt><dd>${money(diag.intrinsic_value)}</dd></div>
            <div><dt>Parity premium</dt><dd>${money(diag.parity_premium)}</dd></div>
            <div><dt>Breakeven common</dt><dd>${money(diag.breakeven_common)}</dd></div>
            <div><dt>Moneyness</dt><dd>${pct(diag.moneyness_pct)}</dd></div>
            <div><dt>Move to breakeven</dt><dd>${pct(diag.move_to_breakeven_pct)}</dd></div>
            <div><dt>CAGR to breakeven</dt><dd>${diag.cagr_to_breakeven_pct == null ? 'n/m <90d' : pct(diag.cagr_to_breakeven_pct)}</dd></div>
            <div><dt>Fair value / score</dt><dd>withheld</dd></div>
          </dl></article>
          <article class="warrant-card"><h4>Evidence + viability</h4><dl>
            <div><dt>Survival state</dt><dd>${esc(words(survival.status))}</dd></div>
            <div><dt>Missing</dt><dd>${esc((survival.missing_inputs || []).join(' · ') || 'none')}</dd></div>
            <div><dt>Source date</dt><dd>${esc(source.latest_terms_as_of || source.as_of || '—')}</dd></div>
            <div><dt>Primary filing</dt><dd>${source.url ? `<a class="warrant-source" href="${esc(source.url)}" target="_blank" rel="noopener">open SEC evidence ↗</a>` : '—'}</dd></div>
          </dl></article>
        </div>
        <div class="warrant-next"><b>Next gate:</b> ${esc(row.next_action || 'Resolve the first incomplete gate from primary evidence.')}</div>
      </div>
    </details>`;
  }
  function eventMarkup(event) {
    return `<tr><td class="mono">${esc(event.filed_at || '—')}</td><td>${esc(event.issuer || 'Unknown issuer')}</td><td>${esc(event.form || '—')} · ${esc(event.file_type || '—')}</td><td><span class="warrant-badge monitor">${esc(words(event.lane_hint))}</span></td><td><a class="warrant-source" href="${esc(event.source_url)}" target="_blank" rel="noopener">review filing ↗</a></td></tr>`;
  }
  function filteredRows(payload) {
    return (payload.rows || []).filter(row => {
      const hay = `${row.warrant_ticker} ${row.common_ticker} ${row.issuer} ${row.lane} ${row.status}`.toLowerCase();
      return (!state.query || hay.includes(state.query.toLowerCase()))
        && (state.lane === 'all' || row.lane === state.lane)
        && (state.lifecycle === 'all' || row.lifecycle === state.lifecycle)
        && (state.status === 'all' || row.status === state.status);
    });
  }
  function render(payload) {
    const summary = payload.summary || {}; const health = payload.health || {}; const loop = payload.learning_loop || {};
    const rows = filteredRows(payload); const active = (payload.rows || []).filter(row => row.lifecycle === 'active');
    const earliest = active.filter(row => row.contract_clock?.days_to_expiry != null).sort((a,b) => a.contract_clock.days_to_expiry - b.contract_clock.days_to_expiry)[0];
    const laneValues = [...new Set((payload.rows || []).map(row => row.lane))].sort();
    const statusValues = [...new Set((payload.rows || []).map(row => row.status))].sort();
    return `<div class="warrant-head">
      <div><div class="warrant-kicker">Warrants · contract-first special situations</div><h2>The agreement is the asset. The ticker is only its shadow.</h2><p>Track post-reorganization and de-SPAC warrants through three hard gates. Delayed prices can focus research; only primary terms, issuer survival, and an executable two-sided market can support a decision.</p></div>
      <div class="warrant-master-clock">${clockMarkup(earliest?.contract_clock || {}, false)}<div><h3>${esc(earliest ? `${earliest.warrant_ticker} is the nearest live clock` : 'No active contract clock')}</h3><p>${earliest ? `${earliest.contract_clock.days_to_expiry} days remain. ${earliest.next_action}` : 'New verified contracts will appear here.'}</p></div></div>
    </div>
    <div class="warrant-summary">
      <div class="warrant-stat"><span>Active contracts</span><strong>${summary.active_series || 0}</strong><small>${summary.registry_series || 0} series including history</small></div>
      <div class="warrant-stat"><span>Review ready</span><strong>${summary.review_ready || 0}</strong><small>all three gates must pass</small></div>
      <div class="warrant-stat"><span>Near expiry</span><strong>${summary.near_expiry || 0}</strong><small>inside 60 days</small></div>
      <div class="warrant-stat"><span>SEC inbox</span><strong>${summary.unresolved_events || 0}</strong><small>identity and terms unresolved</small></div>
      <div class="warrant-stat"><span>Learning cohorts</span><strong>${loop.cohort_count || 0}</strong><small>${loop.resolved_outcome_count || 0} matured outcomes</small></div>
    </div>
    <div class="warrant-loop-line"><span><b class="${health.status === 'healthy' ? 'is-healthy' : 'is-unhealthy'}">${esc(health.status || 'unknown')}</b> feed</span><span><b>Self-healing:</b> last-known-good terms and marks survive vendor failures</span><span><b>Self-compounding:</b> monthly cohorts resolve at 90/365 days</span><span><b>Auto-weighting:</b> off</span><span><b>Execution boundary:</b> a long warrant is not covered-call collateral without broker confirmation</span></div>
    ${(payload.alerts || []).slice(0,5).length ? `<div class="warrant-alerts">${(payload.alerts || []).slice(0,5).map(alert => `<div class="warrant-alert"><b>${esc(alert.severity || 'note')}</b><span>${esc(alert.message)}</span></div>`).join('')}</div>` : ''}
    <div class="warrant-toolbar">
      <input class="search" data-warrant-search aria-label="Search warrants" placeholder="Search warrant, issuer, lane, or state…" value="${esc(state.query)}">
      <select data-warrant-lane aria-label="Filter warrant lane">${option('all','All lanes',state.lane)}${laneValues.map(value => option(value, words(value), state.lane)).join('')}</select>
      <select data-warrant-lifecycle aria-label="Filter lifecycle">${option('active','Active only',state.lifecycle)}${option('all','All lifecycles',state.lifecycle)}${option('redeemed','Redeemed history',state.lifecycle)}</select>
      <select data-warrant-status aria-label="Filter gate state">${option('all','All gate states',state.status)}${statusValues.map(value => option(value, words(value), state.status)).join('')}</select>
      <span class="warrant-count">${rows.length} visible</span>
    </div>
    <div class="warrant-book">${rows.length ? rows.map(rowMarkup).join('') : '<div class="warrant-empty">No warrant series match these filters. Open the SEC inbox below to promote a new candidate.</div>'}</div>
    <section class="warrant-events"><div class="warrant-section-head"><div><h3>SEC warrant-event inbox</h3><p>Accession-locked discoveries. No ticker is promoted until identity and transferability are verified.</p></div><span class="warrant-badge monitor">${summary.unresolved_events || 0} pending</span></div>
      ${(payload.events || []).length ? `<div style="overflow:auto"><table class="warrant-event-table"><thead><tr><th>Filed</th><th>Issuer</th><th>Form</th><th>Lane hint</th><th>Evidence</th></tr></thead><tbody>${payload.events.map(eventMarkup).join('')}</tbody></table></div>` : '<div class="warrant-empty">The inbox is empty. The weekly SEC collector will add new warrant-language filings here.</div>'}
    </section>
    <section class="warrant-learning"><div class="warrant-section-head"><div><h3>Outcome calibration</h3><p>Point-in-time cohorts retain winners, zeros, redemptions, and delistings. Results are descriptive and never alter sizing automatically.</p></div><span class="warrant-badge ${loop.resolved_outcome_count ? 'active' : 'closed'}">${loop.resolved_outcome_count || 0} resolved</span></div>
      <div class="warrant-loop-line"><span><b>${loop.cohort_count || 0}</b> cohorts captured</span><span><b>${loop.resolved_outcome_count || 0}</b> outcomes matured</span><span>${esc(loop.next_resolution || '')}</span></div>
    </section>`;
  }
  function attach(container, payload, rerender) {
    const bind = (selector, key, event) => container.querySelector(selector)?.addEventListener(event, e => { state[key] = e.target.value.trim(); rerender(); requestAnimationFrame(() => container.querySelector(selector)?.focus()); });
    bind('[data-warrant-search]', 'query', 'input');
    bind('[data-warrant-lane]', 'lane', 'change');
    bind('[data-warrant-lifecycle]', 'lifecycle', 'change');
    bind('[data-warrant-status]', 'status', 'change');
  }
  global.WarrantViz = { render, attach };
})(window);
