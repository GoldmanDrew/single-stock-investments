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
  function pct(value, digits) {
    const n = Number(value);
    if (!Number.isFinite(n)) return '—';
    const d = digits != null ? digits : (Math.abs(n) >= 1 ? 0 : 1);
    const signed = n > 0 ? '+' : '';
    return `${signed}${(n * 100).toFixed(d)}%`;
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
      residual: 'Long-term residual',
      blacklist_family: 'Hand-traded',
      michael_new: 'Michael fill',
      drew_new: 'Drew fill',
      sleeve_tag: 'Sleeve fill',
      cash: 'Cash',
    }[reason] || '';
  }
  function clusterLabel(cluster) {
    return String(cluster || 'idiosyncratic').split('_').join(' ');
  }
  function sourceLabel(source) {
    if (!source) return 'Not synced yet';
    if (source === 'ib_live') return 'Live TWS snapshot, account U805366';
    if (String(source).startsWith('flex:')) return 'IBKR Flex snapshot, account U805366';
    if (source === 'd1') return 'Saved dashboard book';
    if (source === 'desk_export' || source === 'static_fallback') return 'Last saved book on this site';
    return source;
  }
  function simpleReturn(p) {
    const cost = Math.abs(Number(p.cost_usd) || 0);
    const pnl = Number(p.pnl_usd);
    if (!cost || !Number.isFinite(pnl)) return null;
    return pnl / cost;
  }
  function notePreview(p) {
    const notes = p.notes || [];
    const latest = notes[notes.length - 1] || {};
    const text = String(latest.body || latest.plc_thesis || p.plc_thesis || '').replace(/\s+/g, ' ').trim();
    if (!text) return '';
    return text.length > 90 ? `${text.slice(0, 87)}…` : text;
  }

  function render(owner, book, opts) {
    const header = book.header || {};
    const metrics = book.metrics || {};
    const independence = metrics.independence || {};
    const allPositions = book.positions || [];
    const ideas = book.ideas || [];
    const prefill = (opts && opts.prefillTicker) || '';
    const excluded = header.excluded || {};
    const showDust = Boolean(opts && opts.showDust);
    const dust = allPositions.filter((p) => Math.abs(Number(p.market_value) || 0) < DUST_USD);
    const positions = allPositions.filter((p) => showDust || Math.abs(Number(p.market_value) || 0) >= DUST_USD);
    const isDrew = owner === 'drew';
    const title = isDrew ? "Drew's sleeve" : "Michael's long-term book";
    const kicker = isDrew ? '$100,000 equity · $100,000 extra margin' : 'Magis taxable account · U805366';
    const nav = Number(header.nav_usd) || allPositions.reduce((s, p) => s + Math.abs(Number(p.market_value) || 0), 0);
    const costSum = allPositions.reduce((s, p) => s + Math.abs(Number(p.cost_usd) || 0), 0);
    const pnlSum = allPositions.reduce((s, p) => s + (Number.isFinite(Number(p.pnl_usd)) ? Number(p.pnl_usd) : 0), 0);
    const bookReturn = costSum ? pnlSum / costSum : null;
    const noted = allPositions.filter((p) => !p.needs_thesis).length;
    const needNotes = allPositions.length - noted;
    const top = allPositions[0];
    const topWeight = top && nav ? Math.abs(Number(top.market_value) || 0) / nav : 0;
    const maxWeight = Math.max(...positions.map((p) => nav ? Math.abs(Number(p.market_value) || 0) / nav : 0), 0.01);
    const clusters = independence.cluster_weights || {};
    const clusterKeys = Object.keys(clusters);
    const allIdio = clusterKeys.length <= 1 && (clusterKeys[0] || 'idiosyncratic') === 'idiosyncratic';
    const xirr = metrics.sleeve_xirr;
    const returnHint = xirr == null
      ? (bookReturn == null ? 'Needs dated buys and sells from notes or fills.' : 'Simple return vs cost. Money-weighted IRR appears after dated cashflows.')
      : 'Money-weighted IRR on recorded cashflows.';
    const independenceHint = allIdio
      ? 'Every name is still in one cluster. Assign clusters in a note so this score means something.'
      : '1.00 means each name is in a different cluster.';

    const rows = positions.map((p) => {
      const irr = (metrics.name_irrs || {})[p.ticker];
      const simple = simpleReturn(p);
      const shownReturn = irr != null ? irr : simple;
      const returnKind = irr != null ? 'XIRR' : (simple != null ? 'vs cost' : '');
      const pnl = p.pnl_usd;
      const weight = nav ? Math.abs(Number(p.market_value) || 0) / nav : 0;
      const preview = notePreview(p);
      const reason = reasonLabel(p.classifier_reason);
      const fx = p.currency && p.currency !== 'USD' ? ` ${p.currency}` : '';
      return `<tr>
        <td>
          <div class="sleeve-ticker mono">${esc(p.ticker)}</div>
          <div class="sleeve-name">${esc(p.name || p.ticker)}</div>
          <div class="sleeve-tags">
            ${reason ? `<span class="sleeve-mini">${esc(reason)}</span>` : ''}
            ${p.cluster && p.cluster !== 'idiosyncratic' ? `<span class="sleeve-mini">${esc(clusterLabel(p.cluster))}</span>` : ''}
          </div>
        </td>
        <td class="sleeve-num">
          <div class="mono">${pct(weight, 1).replace('+', '')}</div>
          <span class="sleeve-weight-bar" title="${esc(pct(weight, 1).replace('+', ''))} of book"><i style="width:${Math.max(4, (weight / maxWeight) * 100)}%"></i></span>
        </td>
        <td class="mono sleeve-num">${shares(p.qty)}</td>
        <td class="mono sleeve-num">${num(p.mark)}${esc(fx)}</td>
        <td class="mono sleeve-num">${money(p.market_value)}</td>
        <td class="mono sleeve-num ${pnlClass(pnl)}">${pnl == null ? '—' : money(pnl)}</td>
        <td class="sleeve-num">
          <div class="mono ${pnlClass(shownReturn)}">${shownReturn == null ? '—' : pct(shownReturn)}</div>
          ${returnKind ? `<div class="sleeve-sub">${esc(returnKind)}</div>` : ''}
        </td>
        <td class="sleeve-note-col">
          ${p.needs_thesis
            ? `<button type="button" class="linkish" data-sleeve-note="${esc(p.ticker)}">Add thesis</button>`
            : `<div class="sleeve-preview">${esc(preview || 'Noted')}</div>
               <button type="button" class="linkish sleeve-note-edit" data-sleeve-note="${esc(p.ticker)}">Edit</button>`}
        </td>
      </tr>`;
    }).join('');

    const ideaRows = ideas.filter((i) => !allPositions.some((p) => p.ticker === i.ticker)).map((i) => `
      <tr class="sleeve-idea-row">
        <td>
          <div class="sleeve-ticker mono">${esc(i.ticker)}</div>
          <div class="sleeve-name">Watching · not in the IB book yet</div>
        </td>
        <td class="sleeve-num">—</td>
        <td class="sleeve-num">—</td>
        <td class="sleeve-num">—</td>
        <td class="sleeve-num">—</td>
        <td class="sleeve-num">—</td>
        <td class="sleeve-name">${esc(clusterLabel(i.cluster))}</td>
        <td class="sleeve-note-col"><button type="button" class="linkish" data-sleeve-note="${esc(i.ticker)}">Add thesis</button></td>
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
    const warnConc = !isDrew && top && topWeight >= 0.25
      ? `<p class="sleeve-callout">${esc(top.ticker)} is ${pct(topWeight, 1).replace('+', '')} of the book. Size is a process choice, not a score.</p>` : '';

    const process = isDrew
      ? `<ol class="sleeve-process">
          <li><strong>Separate book.</strong> Drew does not inherit Michael's names. New buys are tagged <span class="mono">DREW_SLEEVE</span> on the local desk.</li>
          <li><strong>Write the thesis first.</strong> Why we own it, and what would make it a permanent loss of capital.</li>
          <li><strong>Hold for years.</strong> Mark-to-market is not the score.</li>
          <li><strong>Keep names independent.</strong> Assign a cluster in the note so one theme cannot swallow the sleeve.</li>
          <li><strong>Orders stay local.</strong> This page cannot talk to Interactive Brokers.</li>
        </ol>`
      : `<ol class="sleeve-process">
          <li><strong>Own residual businesses.</strong> ls-algo names drop out unless they are blacklist names Michael trades by hand. SPX / XSP stay off this tab.</li>
          <li><strong>Write why we own it.</strong> Every line needs a thesis and a permanent-loss sentence. Notes save here after GitHub sign-in.</li>
          <li><strong>Hold for years.</strong> The gain column is a fact. It is not permission to trade.</li>
          <li><strong>Watch concentration.</strong> Independence is 0 while every name sits in one cluster. Assign clusters in the note.</li>
          <li><strong>Orders stay on the local desk.</strong> Draft, retype the ticker, then send a DAY limit through Gateway. This page does not place orders.</li>
        </ol>`;

    const dustNote = dust.length
      ? `${dust.length} names under ${money(DUST_USD)} are ${showDust ? 'shown' : 'hidden'}.`
      : 'Sorted by size.';

    return `
      <header class="sleeve-hero">
        <p class="sleeve-kicker">${esc(kicker)}</p>
        <h2>${esc(title)}</h2>
        <p class="sleeve-lede">${esc(header.blurb || '')}</p>
        <p class="sleeve-source">${esc(sourceLabel(book.source))} · as of ${esc(book.as_of || '—')}</p>
        ${isDrew ? '' : `<div class="sleeve-chips">
          <span class="sleeve-chip sleeve-chip-in">${header.open_names ?? 0} names in this book</span>
          <span class="sleeve-chip">${excluded.etf_ls || 0} omitted (ls-algo universe)</span>
          <span class="sleeve-chip">${excluded.spx_0dte || 0} SPX / XSP option lines omitted</span>
        </div>`}
      </header>

      <section class="sleeve-process-box">
        <h3>How this book is run</h3>
        ${process}
      </section>

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
          <div class="hint">${positions.length} shown${dust.length ? ` · ${dust.length} under ${money(DUST_USD)}` : ''}</div>
        </div>
        <div class="sleeve-stat">
          <div class="k">Independence</div>
          <div class="v mono">${num(independence.score, 2)}</div>
          <div class="hint">${esc(independenceHint)}</div>
        </div>
        <div class="sleeve-stat">
          <div class="k">${xirr == null ? 'Simple return vs cost' : 'Money-weighted return'}</div>
          <div class="v mono ${pnlClass(xirr == null ? bookReturn : xirr)}">${xirr == null ? (bookReturn == null ? '—' : pct(bookReturn)) : pct(xirr)}</div>
          <div class="hint">${esc(returnHint)}</div>
        </div>
        <div class="sleeve-stat">
          <div class="k">Theses written</div>
          <div class="v mono">${noted}/${allPositions.length || 0}</div>
          <div class="hint">${needNotes ? `${needNotes} still need a why-we-own-it note.` : 'Every name has a note.'}</div>
        </div>
      </div>
      ${warnConc}${warnHold}

      <section class="sleeve-section">
        <div class="sleeve-section-head">
          <h3>Holdings</h3>
          <p>
            ${esc(dustNote)}
            ${dust.length ? `<button type="button" class="linkish" data-sleeve-dust>${showDust ? 'Hide small names' : 'Show small names'}</button>` : ''}
          </p>
        </div>
        <div class="sleeve-table-wrap">
          <table class="sleeve-table sleeve-holdings">
            <colgroup>
              <col class="sleeve-col-name">
              <col class="sleeve-col-w">
              <col class="sleeve-col-qty">
              <col class="sleeve-col-last">
              <col class="sleeve-col-val">
              <col class="sleeve-col-pnl">
              <col class="sleeve-col-ret">
              <col class="sleeve-col-note">
            </colgroup>
            <thead><tr>
              <th>Name</th>
              <th class="sleeve-num">Weight</th>
              <th class="sleeve-num">Shares</th>
              <th class="sleeve-num">Last</th>
              <th class="sleeve-num">Value</th>
              <th class="sleeve-num">Gain / loss</th>
              <th class="sleeve-num">Return</th>
              <th class="sleeve-note-col">Thesis</th>
            </tr></thead>
            <tbody>${rows}${ideaRows}${empty}</tbody>
          </table>
        </div>
      </section>

      <details class="sleeve-note-box" ${prefill ? 'open' : ''}>
        <summary>${prefill ? `Note for ${esc(prefill)}` : 'Write a note on a name'}</summary>
        <p class="sleeve-quality-copy">A note is the investment process on one name: why we own it, what would make it a permanent loss, intended years, conviction, and cluster. It does not send an order.</p>
        <form class="sleeve-note-form" data-sleeve-note-form>
          <input type="hidden" name="owner" value="${esc(owner)}" />
          <label>Date<input name="note_date" type="date" required value="${new Date().toISOString().slice(0, 10)}"></label>
          <label>Ticker<input name="ticker" required maxlength="14" value="${esc(prefill)}" placeholder="GTX"></label>
          <label>Side<select name="side"><option>BUY</option><option>SELL</option></select></label>
          <label>Shares<input name="shares" type="number" step="any"></label>
          <label>Entry price<input name="entry_price" type="number" step="any"></label>
          <label>Cost in dollars<input name="cost_usd" type="number" step="any"></label>
          <label>Conviction 1–5<input name="conviction" type="number" min="1" max="5" required value="3"></label>
          <label>Permanent-loss risk 1–5<input name="plc_score" type="number" min="1" max="5" value="3"></label>
          <label>Intended years held<input name="holding_period_years" type="number" min="0.25" step="0.25" required value="3"></label>
          <label>Cluster<select name="cluster">${CLUSTERS.map((c) => `<option value="${c}">${clusterLabel(c)}</option>`).join('')}</select></label>
          <label class="full">Why we own this<textarea name="body" required rows="3" placeholder="What the market is missing, and how we get paid over years."></textarea></label>
          <label class="full">What would make this a permanent loss of capital?<textarea name="plc_thesis" required rows="2"></textarea></label>
          <div class="full"><button type="submit">Save note</button> <span class="form-hint" data-sleeve-save-status>Sign in with GitHub in the top bar. Notes save to the dashboard database, not to Interactive Brokers.</span></div>
        </form>
      </details>

      <details class="sleeve-quality">
        <summary>Quality over time</summary>
        <p class="sleeve-quality-copy">Four levers, after notes exist: how independent the names are, money-weighted return, risk of permanent loss of capital (not a mark-to-market drawdown), and whether high conviction actually earned more.</p>
        <table class="sleeve-table">
          <thead><tr><th>Conviction</th><th class="sleeve-num">Count</th><th class="sleeve-num">Average return</th><th class="sleeve-num">Permanent-loss rate</th><th class="sleeve-num">Median years held</th></tr></thead>
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
        const box = container.querySelector('.sleeve-note-box');
        box?.setAttribute('open', 'open');
        box?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        input?.focus();
      });
    });
    container.querySelectorAll('[data-sleeve-dust]').forEach((btn) => {
      btn.addEventListener('click', (event) => {
        event.preventDefault();
        const next = btn.textContent.indexOf('Show') !== -1;
        if (typeof reload === 'function') reload(null, { showDust: next });
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
