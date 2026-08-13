(function (global) {
  'use strict';

  const CLUSTERS = ['idiosyncratic', 'ai_infra', 'biotech', 'croupier', 'real_assets', 'rates', 'oil'];
  const DUST_USD = 500;

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
  function shares(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return '—';
    return new Intl.NumberFormat('en-US', { maximumFractionDigits: n % 1 ? 2 : 0 }).format(n);
  }
  function num(value, digits) {
    const n = Number(value);
    return Number.isFinite(n) ? n.toFixed(digits ?? 2) : '—';
  }
  function pnlClass(value) {
    const n = Number(value);
    if (!Number.isFinite(n) || n === 0) return '';
    return n > 0 ? 'sleeve-pnl-up' : 'sleeve-pnl-down';
  }
  function reasonLabel(reason) {
    return {
      residual: 'Long-term holding',
      blacklist_family: 'Hand-traded (blacklist family)',
      michael_new: 'Tagged Michael fill',
      drew_new: 'Tagged Drew fill',
      cash: 'Cash',
    }[reason] || reason || 'Holding';
  }
  function sourceLabel(source) {
    if (!source) return 'Not synced yet';
    if (source === 'ib_live') return 'Live TWS snapshot, account U805366';
    if (String(source).startsWith('flex:')) return 'IBKR Flex snapshot, account U805366';
    if (source === 'd1') return 'Saved dashboard book';
    if (source === 'desk_export' || source === 'static_fallback') return 'Last saved book on this site';
    return source;
  }

  function render(owner, book, opts) {
    const header = book.header || {};
    const metrics = book.metrics || {};
    const independence = metrics.independence || {};
    const allPositions = book.positions || [];
    const ideas = book.ideas || [];
    const prefill = (opts && opts.prefillTicker) || '';
    const excluded = header.excluded || {};
    const dust = allPositions.filter((p) => Math.abs(Number(p.market_value) || 0) < DUST_USD);
    const positions = allPositions.filter((p) => Math.abs(Number(p.market_value) || 0) >= DUST_USD);
    const isDrew = owner === 'drew';
    const title = isDrew ? "Drew's sleeve" : "Michael's long-term book";
    const kicker = isDrew ? '$100,000 equity · $100,000 extra margin' : 'Magis taxable account · U805366';

    const rows = positions.map((p) => {
      const irr = (metrics.name_irrs || {})[p.ticker];
      const pnl = p.pnl_usd;
      return `<tr>
        <td>
          <div class="sleeve-ticker mono">${esc(p.ticker)}</div>
          <div class="sleeve-name">${esc(p.name || reasonLabel(p.classifier_reason))}</div>
        </td>
        <td class="mono sleeve-num">${shares(p.qty)}</td>
        <td class="mono sleeve-num">${num(p.mark)}</td>
        <td class="mono sleeve-num">${money(p.market_value)}</td>
        <td class="mono sleeve-num ${pnlClass(pnl)}">${pnl == null ? '—' : money(pnl)}</td>
        <td class="mono sleeve-num">${irr == null ? '—' : pct(irr)}</td>
        <td>${p.needs_thesis ? '<span class="badge badge-warn">Needs a note</span>' : '<span class="badge badge-ok">Noted</span>'}</td>
        <td><button type="button" class="linkish" data-sleeve-note="${esc(p.ticker)}">Write note</button></td>
      </tr>`;
    }).join('');

    const ideaRows = ideas.filter((i) => !allPositions.some((p) => p.ticker === i.ticker)).map((i) => `
      <tr class="sleeve-idea-row">
        <td>
          <div class="sleeve-ticker mono">${esc(i.ticker)}</div>
          <div class="sleeve-name">Watching · not in the IB book yet</div>
        </td>
        <td colspan="5">${esc(i.cluster || 'idiosyncratic')}</td>
        <td colspan="2"><button type="button" class="linkish" data-sleeve-note="${esc(i.ticker)}">Write note</button></td>
      </tr>`).join('');

    const empty = (!rows && !ideaRows) ? (
      isDrew
        ? `<tr><td colspan="8" class="sleeve-empty">
            <strong>No positions yet.</strong>
            This sleeve stays empty until a fill is tagged <span class="mono">DREW_SLEEVE</span> on the local order desk.
            It does not pick up names from Michael's book.
          </td></tr>`
        : `<tr><td colspan="8" class="sleeve-empty">
            <strong>No long-term names in the last IB snapshot.</strong>
            Sync from TWS on the machine logged into Magis, or pass the Flex positions file to the desk.
          </td></tr>`
    ) : '';

    const cal = (metrics.conviction_calibration || []).map((row) => `
      <tr><td>${row.conviction}</td><td>${row.count}</td><td>${row.avg_irr == null ? '—' : pct(row.avg_irr)}</td>
      <td>${row.plc_rate == null ? '—' : pct(row.plc_rate)}</td><td>${row.median_years_held ?? '—'}</td></tr>`).join('');

    const warnHold = owner === 'michael' && metrics.median_holding_years != null && metrics.median_holding_years < 1
      ? '<p class="sleeve-callout">Median holding period of noted names is under one year. This book is meant to be long-term.</p>' : '';

    return `
      <header class="sleeve-hero">
        <p class="sleeve-kicker">${esc(kicker)}</p>
        <h2>${esc(title)}</h2>
        <p class="sleeve-lede">${esc(header.blurb || '')}</p>
        <p class="sleeve-source">${esc(sourceLabel(book.source))} · as of ${esc(book.as_of || '—')}</p>
        ${isDrew ? '' : `<div class="sleeve-chips">
          <span class="sleeve-chip sleeve-chip-in">${header.open_names ?? 0} names in this book</span>
          <span class="sleeve-chip">${excluded.etf_ls || 0} left on the LETF desk</span>
          <span class="sleeve-chip">${excluded.spx_0dte || 0} SPX / XSP option lines omitted</span>
        </div>`}
      </header>

      <div class="sleeve-stats">
        <div class="sleeve-stat">
          <div class="k">${isDrew ? 'Capital' : 'Book value'}</div>
          <div class="v mono">${money(isDrew ? header.equity_usd : header.nav_usd)}</div>
        </div>
        <div class="sleeve-stat">
          <div class="k">${isDrew ? 'Room to add' : 'Cash in this book'}</div>
          <div class="v mono">${money(isDrew ? header.buying_power_usd : header.cash_usd)}</div>
        </div>
        <div class="sleeve-stat">
          <div class="k">Names</div>
          <div class="v mono">${header.open_names ?? 0}</div>
        </div>
        <div class="sleeve-stat">
          <div class="k">Independence</div>
          <div class="v mono">${num(independence.score, 2)}</div>
          <div class="hint">1.00 means every name is in a different cluster</div>
        </div>
        <div class="sleeve-stat">
          <div class="k">Money-weighted return</div>
          <div class="v mono">${metrics.sleeve_xirr == null ? '—' : pct(metrics.sleeve_xirr)}</div>
        </div>
        <div class="sleeve-stat">
          <div class="k">Notes written</div>
          <div class="v mono">${pct(metrics.completeness)}</div>
        </div>
      </div>
      ${warnHold}

      <section class="sleeve-section">
        <div class="sleeve-section-head">
          <h3>Holdings</h3>
          <p>${dust.length ? `${dust.length} names under ${money(DUST_USD)} are hidden so the large lines are readable.` : 'Sorted by size.'}</p>
        </div>
        <div class="sleeve-table-wrap">
          <table class="sleeve-table">
            <thead><tr>
              <th>Name</th><th>Shares</th><th>Last</th><th>Value</th>
              <th>Gain / loss</th><th>Return</th><th>Thesis</th><th></th>
            </tr></thead>
            <tbody>${rows}${ideaRows}${empty}</tbody>
          </table>
        </div>
      </section>

      <details class="sleeve-note-box" ${prefill ? 'open' : ''}>
        <summary>${prefill ? `Note for ${esc(prefill)}` : 'Write a note on a name'}</summary>
        <form class="sleeve-note-form" data-sleeve-note-form>
          <input type="hidden" name="owner" value="${esc(owner)}" />
          <label>Date<input name="note_date" type="date" required value="${new Date().toISOString().slice(0, 10)}"></label>
          <label>Ticker<input name="ticker" required maxlength="14" value="${esc(prefill)}" placeholder="MSFT"></label>
          <label>Side<select name="side"><option>BUY</option><option>SELL</option></select></label>
          <label>Shares<input name="shares" type="number" step="any"></label>
          <label>Entry price<input name="entry_price" type="number" step="any"></label>
          <label>Cost in dollars<input name="cost_usd" type="number" step="any"></label>
          <label>Conviction 1–5<input name="conviction" type="number" min="1" max="5" required value="3"></label>
          <label>Permanent-loss risk 1–5<input name="plc_score" type="number" min="1" max="5" value="3"></label>
          <label>Intended years held<input name="holding_period_years" type="number" min="0.25" step="0.25" required value="3"></label>
          <label>Cluster<select name="cluster">${CLUSTERS.map((c) => `<option value="${c}">${c.split('_').join(' ')}</option>`).join('')}</select></label>
          <label class="full">Why we own this<textarea name="body" required rows="3" placeholder="What the market is missing, and how we get paid over years."></textarea></label>
          <label class="full">What would make this a permanent loss of capital?<textarea name="plc_thesis" required rows="2"></textarea></label>
          <div class="full"><button type="submit">Save note</button> <span class="form-hint" data-sleeve-save-status>Sign in with GitHub in the top bar. Notes save to the dashboard database, not to Interactive Brokers.</span></div>
        </form>
      </details>

      <details class="sleeve-quality">
        <summary>Quality over time</summary>
        <p class="sleeve-quality-copy">Four levers: how independent the names are, money-weighted return, risk of permanent loss of capital (not a mark-to-market drawdown), and whether high conviction actually earned more.</p>
        <table class="sleeve-table">
          <thead><tr><th>Conviction</th><th>Count</th><th>Average return</th><th>Permanent-loss rate</th><th>Median years held</th></tr></thead>
          <tbody>${cal || '<tr><td colspan="5" class="sleeve-empty">No notes yet, so there is nothing to calibrate.</td></tr>'}</tbody>
        </table>
      </details>
    `;
  }

  function attach(container, owner, reload) {
    container.querySelectorAll('[data-sleeve-note]').forEach((btn) => {
      btn.addEventListener('click', (event) => {
        event.preventDefault();
        const ticker = btn.getAttribute('data-sleeve-note');
        const input = container.querySelector('[name="ticker"]');
        if (input) input.value = ticker;
        container.querySelector('.sleeve-note-box')?.setAttribute('open', 'open');
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
        if (status) status.textContent = 'Sign in with GitHub in the top bar before saving.';
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

  function isPopulated(book) {
    if (!book) return false;
    return (book.positions || []).length > 0 || (book.ideas || []).length > 0;
  }

  async function load(owner) {
    let remote = null;
    try {
      const res = await fetch(`/api/v1/sleeves/book?owner=${encodeURIComponent(owner)}`);
      if (res.ok) remote = await res.json();
    } catch (_) { /* static fallback */ }
    let local = null;
    try {
      const res = await fetch(`data/sleeves_${owner}.json`);
      if (res.ok) local = await res.json();
    } catch (_) { /* ignore */ }
    if (isPopulated(remote)) return remote;
    if (isPopulated(local)) return local;
    return remote || local || Promise.reject(new Error('Could not load sleeve book'));
  }

  global.SleeveViz = { render, attach, load };
})(window);
