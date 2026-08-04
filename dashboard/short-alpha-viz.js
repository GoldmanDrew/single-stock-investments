(function (global) {
  'use strict';

  const CUSTOM_KEY = 'ssi_short_alpha_custom_v1';
  const CHECKINS_KEY = 'ssi_short_alpha_checkins_v1';
  const FILTER_KEY = 'ssi_short_alpha_filter_v1';
  const REMOVED_KEY = 'ssi_short_alpha_removed_v1';
  const REPO_BASE = 'https://github.com/magis-capital-partners/single-stock-investments/blob/main/';

  function esc(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
  }
  function read(key, fallback) {
    try { return JSON.parse(localStorage.getItem(key) || 'null') ?? fallback; } catch (_) { return fallback; }
  }
  function write(key, value) { localStorage.setItem(key, JSON.stringify(value)); }
  function money(value) {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(Number(value) || 0);
  }
  function price(value) {
    const n = Number(value);
    return Number.isFinite(n) ? n.toLocaleString('en-US', { minimumFractionDigits: n < 2 ? 3 : 2, maximumFractionDigits: 4 }) : '—';
  }
  function frameworkMap(payload) { return Object.fromEntries((payload.frameworks || []).map(x => [x.id, x])); }
  function sourceTypeMap(payload) { return Object.fromEntries((payload.source_types || []).map(x => [x.id, x])); }
  function getIdeas(payload) {
    const overlays = read(CHECKINS_KEY, {});
    const removed = new Set(read(REMOVED_KEY, []));
    return [...(payload.ideas || []), ...read(CUSTOM_KEY, [])].filter(raw => !removed.has(raw.ticker)).map(raw => {
      const idea = JSON.parse(JSON.stringify(raw));
      const allChecks = [...(idea.check_ins || []), ...(overlays[idea.ticker] || [])]
        .sort((a, b) => String(a.date).localeCompare(String(b.date)));
      const latest = allChecks[allChecks.length - 1] || { date: idea.position.opened_date, price: idea.position.opened_price, hypothesis_state: 'open' };
      const last = Number(latest.price);
      idea.check_ins = allChecks;
      idea.outcome = {
        latest_date: latest.date,
        latest_price: last,
        hypothesis_state: latest.hypothesis_state || 'open',
        check_in_count: allChecks.length,
      };
      return idea;
    });
  }
  function linkFor(source) {
    if (source.url) {
      try {
        const parsed = new URL(source.url);
        return ['http:', 'https:'].includes(parsed.protocol) ? parsed.href : '';
      } catch (_) { return ''; }
    }
    if (!source.ref) return '';
    return REPO_BASE + String(source.ref).split('/').map(encodeURIComponent).join('/');
  }
  function formOptions(rows, selected) {
    return (rows || []).map(row => `<option value="${esc(row.id)}" ${row.id === selected ? 'selected' : ''}>${esc(row.label)}</option>`).join('');
  }
  function renderAddForm(payload) {
    return `<details class="short-alpha-add">
      <summary>+ Add short idea</summary>
      <form class="short-alpha-add-form" data-short-add-form>
        <label>Ticker<input name="ticker" required maxlength="14" placeholder="XYZ"></label>
        <label>Security name<input name="security_name" required placeholder="Company or instrument"></label>
        <label>Shares short<input name="shares" required type="number" min="1" step="any" placeholder="1000"></label>
        <label>Opened price<input name="opened_price" required type="number" min="0.0001" step="any" placeholder="25.00"></label>
        <label>Primary framework<select name="framework">${formOptions(payload.frameworks)}</select></label>
        <label>Instrument<select name="instrument_type"><option value="operating_company">Operating company</option><option value="holding_company">Holding company</option><option value="leveraged_etf">Leveraged ETF</option><option value="etf">ETF</option><option value="other">Other</option></select></label>
        <label>Source type<select name="source_type">${formOptions(payload.source_types, 'internal_analysis')}</select></label>
        <label>Source URL<input name="source_url" type="url" placeholder="https://…"></label>
        <label class="full">Hypothesis<textarea name="hypothesis" required rows="2" placeholder="What does the market believe, why is it wrong, and what changes the price?"></textarea></label>
        <div class="full"><button type="submit">Add browser draft</button> <span class="form-hint" data-short-add-status>Saved locally until exported and promoted to the repository ledger.</span></div>
      </form>
    </details>`;
  }
  function renderRow(idea, maps) {
    const outcome = idea.outcome || {};
    const completion = Number(idea.artifact_status?.completion_pct || 0);
    const sourceTypes = sourceTypeMap(maps.payload);
    const tags = (idea.frameworks || []).map(id => `<span class="short-tag">${esc(maps.frameworks[id]?.label || id)}</span>`).join('');
    const list = rows => (rows || []).map(x => `<li>${esc(x)}</li>`).join('') || '<li>Not recorded yet.</li>';
    const sources = (idea.sources || []).map(source => {
      const href = linkFor(source);
      const label = `${sourceTypes[source.type]?.label || source.type}: ${source.label}`;
      return href ? `<a class="short-source" href="${esc(href)}" target="_blank" rel="noopener">${esc(label)} ↗</a>` : `<span class="short-source">${esc(label)}</span>`;
    }).join('');
    const latest = (idea.check_ins || [])[idea.check_ins.length - 1] || {};
    return `<details class="short-alpha-row" data-short-ticker="${esc(idea.ticker)}">
      <summary>
        <div class="short-name"><span class="short-symbol">${esc(idea.ticker)}</span><span class="short-security"><strong>${esc(idea.security_name)}</strong><small>${esc(String(idea.instrument_type || '').replace(/_/g, ' '))}${idea.underlying ? ` · underlying ${esc(idea.underlying)}` : ''}</small></span></div>
        <div class="short-frameworks">${tags}</div>
        <div class="short-metric">$${price(idea.position.split_adjusted_open_price || idea.position.opened_price)}<small>split-adjusted entry</small></div>
        <div class="short-metric">${idea.borrow?.rate_pct == null ? '—' : `${Number(idea.borrow.rate_pct).toFixed(1)}%`}<small>IBKR borrow · ${esc(idea.borrow?.status || 'pending')}</small></div>
        <div class="short-metric">${completion}%<small>${esc(idea.research?.status || 'draft')}</small></div>
      </summary>
      <div class="short-alpha-detail">
        <div class="short-hypothesis-flow">
          <div class="short-flow-block"><h4>Hypothesis · ${esc(idea.position.baseline_date)}</h4><p>${esc(idea.hypothesis)}</p></div>
          <div class="short-flow-arrow" aria-hidden="true">→</div>
          <div class="short-flow-block"><h4>Observed · ${esc(outcome.latest_date)}</h4><p><strong>${esc(outcome.hypothesis_state || 'open')}</strong> at $${price(outcome.latest_price)}. ${esc(latest.note || 'Add a check-in to compare evidence with the original claim.')}</p></div>
        </div>
        <div class="short-detail-grid">
          <div class="short-detail-card"><h4>What should break</h4><ul>${list(idea.catalysts)}</ul></div>
          <div class="short-detail-card"><h4>What proves us wrong</h4><ul>${list(idea.falsifiers)}</ul></div>
          <div class="short-detail-card"><h4>Evidence and next gate</h4><div class="short-sources">${sources || '<span class="form-hint">No sources linked.</span>'}</div><p class="form-hint" style="margin-top:8px">${esc(idea.research?.next_step || 'Define the next research gate.')}</p></div>
        </div>
        <details class="short-checkin"><summary>+ Record actual outcome</summary>
          <form class="short-checkin-form" data-short-checkin-form data-ticker="${esc(idea.ticker)}">
            <label>Date<input name="date" required type="date" value="${new Date().toISOString().slice(0,10)}"></label>
            <label>Price<input name="price" required type="number" min="0.0001" step="any" value="${esc(outcome.latest_price)}"></label>
            <label>Hypothesis state<select name="state"><option value="open">Open</option><option value="strengthened">Strengthened</option><option value="weakened">Weakened</option><option value="falsified">Falsified</option><option value="realized">Realized</option><option value="closed_risk">Closed for risk</option></select></label>
            <label>What actually happened<textarea name="note" required rows="1" placeholder="Evidence, borrow, catalyst, or falsifier"></textarea></label>
            <button type="submit">Save check-in</button>
          </form>
        </details>
        <button type="button" class="short-remove" data-short-remove="${esc(idea.ticker)}">Remove from this dashboard</button>
      </div>
    </details>`;
  }
  function render(payload) {
    const maps = { frameworks: frameworkMap(payload), payload };
    const savedFilter = read(FILTER_KEY, { query: '', framework: 'all' });
    const ideas = getIdeas(payload);
    const filtered = ideas.filter(idea => {
      const hay = `${idea.ticker} ${idea.security_name} ${idea.hypothesis}`.toLowerCase();
      return (!savedFilter.query || hay.includes(savedFilter.query.toLowerCase()))
        && (savedFilter.framework === 'all' || (idea.frameworks || []).includes(savedFilter.framework));
    });
    const complete = ideas.filter(x => Number(x.artifact_status?.completion_pct || 0) >= 85).length;
    return `<div class="short-alpha-header">
      <div><div class="short-alpha-kicker">Short Alpha · hypothesis ledger</div><h2>Thesis first. Tape second. Memory always.</h2><p>Partition every short by its economic failure mode, bind it to source evidence, and preserve what we expected before the outcome was known.</p></div>
      <div class="short-alpha-rail"><span>Hypothesis</span><i></i><span>Evidence</span><i></i><span>Outcome</span></div>
    </div>
    <div class="short-alpha-summary">
      <div class="short-alpha-stat"><span>Positions</span><strong>${ideas.length}</strong><small>${ideas.filter(x => x.instrument_type === 'leveraged_etf').length} instrument-level</small></div>
      <div class="short-alpha-stat"><span>Research complete</span><strong>${complete}/${ideas.length}</strong><small>artifact gate, not an IC decision</small></div>
    </div>
    <div class="short-alpha-toolbar">
      <input class="search" data-short-search placeholder="Search thesis, ticker, or security…" value="${esc(savedFilter.query)}" aria-label="Search Short Alpha">
      <select class="short-alpha-filter" data-short-framework aria-label="Filter by short framework"><option value="all">All frameworks</option>${formOptions(payload.frameworks, savedFilter.framework)}</select>
      <div class="short-alpha-actions"><button type="button" data-short-export>Export ledger</button><button type="button" data-short-reset title="Remove browser-only drafts and check-ins">Reset browser drafts</button></div>
    </div>
    ${renderAddForm(payload)}
    <p class="short-alpha-note">Entry prices are kept on a split-adjusted basis. Borrow is an IBKR feed field; missing means pending, never zero.</p>
    <div class="short-alpha-book">${filtered.length ? filtered.map(x => renderRow(x, maps)).join('') : '<div class="short-alpha-empty">No short ideas match this partition.</div>'}</div>`;
  }
  function mergedExport(payload) {
    const out = JSON.parse(JSON.stringify(payload));
    out.ideas = getIdeas(payload);
    out.exported_at = new Date().toISOString();
    return out;
  }
  function attach(container, payload, rerender) {
    const search = container.querySelector('[data-short-search]');
    const framework = container.querySelector('[data-short-framework]');
    const updateFilter = restoreFocus => {
      write(FILTER_KEY, { query: search.value.trim(), framework: framework.value });
      rerender();
      if (restoreFocus) {
        const nextSearch = container.querySelector('[data-short-search]');
        if (nextSearch) { nextSearch.focus(); nextSearch.setSelectionRange(nextSearch.value.length, nextSearch.value.length); }
      }
    };
    search?.addEventListener('input', () => updateFilter(true));
    framework?.addEventListener('change', () => updateFilter(false));
    container.querySelector('[data-short-add-form]')?.addEventListener('submit', event => {
      event.preventDefault();
      const form = new FormData(event.currentTarget);
      const ticker = String(form.get('ticker') || '').trim().toUpperCase();
      const shares = Number(form.get('shares'));
      const openedPrice = Number(form.get('opened_price'));
      if (!ticker || !(shares > 0) || !(openedPrice > 0)) return;
      if ((payload.ideas || []).some(idea => idea.ticker === ticker)) {
        const status = event.currentTarget.querySelector('[data-short-add-status]');
        if (status) status.textContent = `${ticker} is already in the repository ledger. Add a check-in to its existing row.`;
        return;
      }
      const frameworkId = String(form.get('framework'));
      const sourceUrl = String(form.get('source_url') || '').trim();
      const custom = read(CUSTOM_KEY, []).filter(x => x.ticker !== ticker);
      custom.push({
        ticker, security_name: String(form.get('security_name') || ticker), instrument_type: String(form.get('instrument_type') || 'operating_company'),
        position: { shares: -Math.abs(shares), opened_price: openedPrice, opened_date: new Date().toISOString().slice(0,10), split_adjustment_factor: 1, split_adjusted_open_price: openedPrice },
        frameworks: [frameworkId], primary_framework: frameworkId, hypothesis: String(form.get('hypothesis') || ''), catalysts: [], falsifiers: [],
        research: { status: 'browser_draft', ic: 'not_ready', next_step: 'Promote the exported draft to the repository ledger and begin evidence collection.' },
        sources: sourceUrl ? [{ type: String(form.get('source_type') || 'internal_analysis'), label: 'Initial source', url: sourceUrl }] : [],
        borrow: { status: 'pending', source: 'IBKR borrow feed', message: 'Awaiting the next IBKR borrow refresh.' },
        check_ins: [{ date: new Date().toISOString().slice(0,10), price: openedPrice, hypothesis_state: 'open', note: 'Browser draft baseline.' }],
        artifact_status: { completion_pct: 0 },
      });
      write(CUSTOM_KEY, custom); rerender();
    });
    container.querySelectorAll('[data-short-checkin-form]').forEach(node => node.addEventListener('submit', event => {
      event.preventDefault();
      const form = new FormData(event.currentTarget); const ticker = event.currentTarget.dataset.ticker;
      const overlays = read(CHECKINS_KEY, {}); overlays[ticker] = overlays[ticker] || [];
      overlays[ticker].push({ date: String(form.get('date')), price: Number(form.get('price')), hypothesis_state: String(form.get('state')), note: String(form.get('note')) });
      write(CHECKINS_KEY, overlays); rerender();
    }));
    container.querySelector('[data-short-export]')?.addEventListener('click', () => {
      const blob = new Blob([JSON.stringify(mergedExport(payload), null, 2) + '\n'], { type: 'application/json' });
      const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = `short-alpha-ledger-${new Date().toISOString().slice(0,10)}.json`; link.click(); URL.revokeObjectURL(link.href);
    });
    container.querySelector('[data-short-reset]')?.addEventListener('click', () => {
      if (!window.confirm('Remove all browser-only Short Alpha drafts and check-ins? The repository ledger is unchanged.')) return;
      localStorage.removeItem(CUSTOM_KEY); localStorage.removeItem(CHECKINS_KEY); localStorage.removeItem(REMOVED_KEY); rerender();
    });
    container.querySelectorAll('[data-short-remove]').forEach(button => button.addEventListener('click', () => {
      const ticker = button.dataset.shortRemove;
      if (!window.confirm(`Remove ${ticker} from this browser's Short Alpha dashboard? You can restore it with Reset browser drafts.`)) return;
      write(REMOVED_KEY, [...new Set([...read(REMOVED_KEY, []), ticker])]); rerender();
    }));
  }
  global.ShortAlphaViz = { render, attach, getIdeas };
})(window);
