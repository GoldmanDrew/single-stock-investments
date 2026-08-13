(function (global) {
  'use strict';

  const CLUSTERS = ['idiosyncratic', 'ai_infra', 'biotech', 'croupier', 'real_assets', 'rates', 'oil'];

  function esc(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }
  function money(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return '—';
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(n);
  }
  function pct(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return '—';
    return `${(n * 100).toFixed(1)}%`;
  }
  function num(value, digits) {
    const n = Number(value);
    return Number.isFinite(n) ? n.toFixed(digits ?? 2) : '—';
  }

  function render(owner, book, opts) {
    const header = book.header || {};
    const metrics = book.metrics || {};
    const independence = metrics.independence || {};
    const positions = book.positions || [];
    const ideas = book.ideas || [];
    const prefill = (opts && opts.prefillTicker) || '';
    const rows = positions.map((p) => {
      const irr = (metrics.name_irrs || {})[p.ticker];
      return `<tr>
        <td class="mono">${esc(p.ticker)}</td>
        <td>${esc(p.side || 'BUY')}</td>
        <td>${esc(p.status || '—')}</td>
        <td class="mono">${num(p.entry_price)}</td>
        <td class="mono">${money(p.cost_usd)}</td>
        <td class="mono">${num(p.mark)}</td>
        <td class="mono">${money(p.market_value)}</td>
        <td class="mono">${irr == null ? '—' : pct(irr)}</td>
        <td>${p.conviction ?? '—'}</td>
        <td>${p.plc_score ?? '—'}</td>
        <td>${esc(p.cluster || '—')}</td>
        <td>${p.holding_period_years ?? '—'}</td>
        <td>${p.needs_thesis ? '<span class="badge badge-warn">needs thesis</span>' : '<span class="badge badge-ok">noted</span>'}</td>
        <td><button type="button" class="linkish" data-sleeve-note="${esc(p.ticker)}">Notes</button></td>
      </tr>`;
    }).join('');
    const ideaRows = ideas.filter((i) => !positions.some((p) => p.ticker === i.ticker)).map((i) => `
      <tr>
        <td class="mono">${esc(i.ticker)}</td>
        <td colspan="12">${esc(i.status || 'idea')} · ${esc(i.cluster || '')}</td>
        <td><button type="button" class="linkish" data-sleeve-note="${esc(i.ticker)}">Notes</button></td>
      </tr>`).join('');
    const cal = (metrics.conviction_calibration || []).map((row) => `
      <tr><td>${row.conviction}</td><td>${row.count}</td><td>${row.avg_irr == null ? '—' : pct(row.avg_irr)}</td>
      <td>${row.plc_rate == null ? '—' : pct(row.plc_rate)}</td><td>${row.median_years_held ?? '—'}</td></tr>`).join('');
    const warnHold = owner === 'michael' && metrics.median_holding_years != null && metrics.median_holding_years < 1
      ? '<p class="subhead">Warning: median holding period of tracked names is under one year.</p>' : '';
    return `
      <p class="subhead">${esc(header.blurb || '')} · source ${esc(book.source || 'local')}</p>
      <div class="metric-grid metric-grid-3">
        <div class="metric"><div class="k">NAV</div><div class="v mono">${money(header.nav_usd)}</div></div>
        <div class="metric"><div class="k">Gross</div><div class="v mono">${money(header.gross_usd)}</div></div>
        <div class="metric"><div class="k">Buying power</div><div class="v mono">${money(header.buying_power_usd)}</div></div>
        <div class="metric"><div class="k">Open names</div><div class="v mono">${header.open_names ?? 0}</div></div>
        <div class="metric"><div class="k">Independence (1y / cluster)</div><div class="v mono">${num(independence.score, 2)}</div></div>
        <div class="metric"><div class="k">Sleeve XIRR</div><div class="v mono">${metrics.sleeve_xirr == null ? '—' : pct(metrics.sleeve_xirr)}</div></div>
        <div class="metric"><div class="k">Max drawdown (MTM)</div><div class="v mono">${metrics.max_drawdown == null ? '—' : pct(metrics.max_drawdown)}</div></div>
        <div class="metric"><div class="k">Median years held</div><div class="v mono">${metrics.median_holding_years ?? '—'}</div></div>
        <div class="metric"><div class="k">Notes complete</div><div class="v mono">${pct(metrics.completeness)}</div></div>
      </div>
      ${warnHold}
      <h3 style="margin-top:18px">Positions and ideas</h3>
      <table class="darwin-table">
        <thead><tr>
          <th>Ticker</th><th>Side</th><th>Status</th><th>Entry</th><th>Cost</th><th>Mark</th><th>Value</th>
          <th>IRR</th><th>Conv</th><th>PLC</th><th>Cluster</th><th>Years</th><th>Thesis</th><th></th>
        </tr></thead>
        <tbody>${rows || ''}${ideaRows || ''}${(!rows && !ideaRows) ? '<tr><td colspan="14">No positions yet. Sync IB (Michael) or dry-run a fill (Drew). Use Notes to journal a ticker before trading.</td></tr>' : ''}</tbody>
      </table>
      <details class="short-alpha-add" ${prefill ? 'open' : ''} style="margin-top:16px">
        <summary>${prefill ? `Note for ${esc(prefill)}` : '+ Write a note / idea'}</summary>
        <form class="short-alpha-add-form" data-sleeve-note-form>
          <input type="hidden" name="owner" value="${esc(owner)}" />
          <label>Date<input name="note_date" type="date" required value="${new Date().toISOString().slice(0, 10)}"></label>
          <label>Ticker<input name="ticker" required maxlength="14" value="${esc(prefill)}" placeholder="MSFT"></label>
          <label>Side<select name="side"><option>BUY</option><option>SELL</option></select></label>
          <label>Shares<input name="shares" type="number" step="any"></label>
          <label>Entry price<input name="entry_price" type="number" step="any"></label>
          <label>Cost<input name="cost_usd" type="number" step="any"></label>
          <label>Conviction 1–5<input name="conviction" type="number" min="1" max="5" required value="3"></label>
          <label>PLC 1–5<input name="plc_score" type="number" min="1" max="5" value="3"></label>
          <label>Holding period (years)<input name="holding_period_years" type="number" min="0.25" step="0.25" required value="3"></label>
          <label>Cluster<select name="cluster">${CLUSTERS.map((c) => `<option value="${c}">${c}</option>`).join('')}</select></label>
          <label class="full">Thought process<textarea name="body" required rows="3" placeholder="Why this is a long-term investment, what the market misses, and how we get paid."></textarea></label>
          <label class="full">What would make this a permanent loss?<textarea name="plc_thesis" required rows="2"></textarea></label>
          <div class="full"><button type="submit">Save to dashboard</button> <span class="form-hint" data-sleeve-save-status>Requires Sign in with GitHub. Saved to D1.</span></div>
        </form>
      </details>
      <h3 style="margin-top:22px">Quality over time</h3>
      <p class="subhead">Independence, IRR, permanent-loss risk, and conviction are the levers. Drawdown is shown separately and is not PLC.</p>
      <table class="darwin-table">
        <thead><tr><th>Conviction</th><th>Count</th><th>Avg IRR</th><th>PLC rate</th><th>Median years</th></tr></thead>
        <tbody>${cal}</tbody>
      </table>
    `;
  }

  function attach(container, owner, reload) {
    container.querySelectorAll('[data-sleeve-note]').forEach((btn) => {
      btn.addEventListener('click', (event) => {
        event.preventDefault();
        const ticker = btn.getAttribute('data-sleeve-note');
        const input = container.querySelector('[name="ticker"]');
        if (input) input.value = ticker;
        container.querySelector('details')?.setAttribute('open', 'open');
        input?.focus();
      });
    });
    const form = container.querySelector('[data-sleeve-note-form]');
    if (!form) return;
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const status = container.querySelector('[data-sleeve-save-status]');
      const token = global.MarvinOAuth && MarvinOAuth.getToken();
      if (!token) {
        if (status) status.textContent = 'Sign in with GitHub (top bar) before saving.';
        return;
      }
      const data = Object.fromEntries(new FormData(form).entries());
      data.owner = owner;
      data.conviction = Number(data.conviction);
      data.plc_score = Number(data.plc_score);
      data.holding_period_years = Number(data.holding_period_years);
      ['shares', 'entry_price', 'cost_usd'].forEach((key) => {
        if (data[key] === '') delete data[key];
        else data[key] = Number(data[key]);
      });
      try {
        const res = await fetch('/api/v1/sleeves/notes', {
          method: 'POST',
          headers: {
            'content-type': 'application/json',
            authorization: `Bearer ${token}`,
          },
          body: JSON.stringify(data),
        });
        const payload = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(payload.error || res.statusText);
        if (status) status.textContent = `Saved as @${payload.author || 'you'}.`;
        if (typeof reload === 'function') reload(payload.book);
      } catch (err) {
        if (status) status.textContent = String(err.message || err);
      }
    });
  }

  async function load(owner) {
    try {
      const res = await fetch(`/api/v1/sleeves/book?owner=${encodeURIComponent(owner)}`);
      if (res.ok) return res.json();
    } catch (_) { /* static fallback */ }
    const res = await fetch(`data/sleeves_${owner}.json`);
    if (!res.ok) throw new Error('Could not load sleeve book');
    return res.json();
  }

  global.SleeveViz = { render, attach, load };
})(window);
