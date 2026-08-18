(function () {
  'use strict';

  const COLUMN_DEFS = [
    { key: 'instrument', label: 'Instrument', required: true },
    { key: 'allocation', label: 'Allocation' },
    { key: 'identity', label: 'ConId / model' },
    { key: 'sec_type', label: 'Type' },
    { key: 'quantity_decimal', label: 'Qty', sort: 'quantity_decimal' },
    { key: 'average_cost_decimal', label: 'Avg cost' },
    { key: 'mark_decimal', label: 'Mark' },
    { key: 'market_value_decimal', label: 'Market value', sort: 'market_value_decimal' },
    { key: 'daily_pnl_decimal', label: 'Daily P&L', sort: 'daily_pnl_decimal' },
    { key: 'unrealized_pnl_decimal', label: 'Unrealized', sort: 'unrealized_pnl_decimal' },
    { key: 'currency', label: 'Currency' },
    { key: 'quality', label: 'Quality' },
  ];
  const DEFAULT_COLUMNS = COLUMN_DEFS.map((column) => column.key);
  const VIEW_STORAGE = 'portfolio-saved-views';
  const COLUMN_STORAGE = 'portfolio-visible-columns';

  const state = {
    scope: 'all', section: 'positions', strategySection: 'overview', book: null,
    orders: null, performance: null, accountPerformance: null, margin: null, risk: null,
    strategy: null, query: '', positionFilter: 'all', sortKey: 'market_value_decimal',
    sortDirection: 'desc', density: localStorage.getItem('portfolio-density') || 'comfortable', onRoute: null,
    selectedPositionKey: null, lineage: null, showColumns: false, savedViewName: '',
    visibleColumns: loadColumns(), savedViews: loadViews(),
  };
  const sections = ['positions', 'risk', 'margin', 'performance', 'orders', 'reconciliation'];
  const buckets = ['overview', 'b1', 'b2', 'b3', 'b4', 'b5'];
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const num = (value) => { if (value == null || value === '') return null; const n = Number(value); return Number.isFinite(n) ? n : null; };
  const money = (value, compact = false) => { const n = num(value); return n == null ? '—' : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: compact ? 0 : 2, notation: compact ? 'compact' : 'standard' }).format(n); };
  const signed = (value) => { const n = num(value); return n == null ? '—' : `${n > 0 ? '+' : ''}${money(n)}`; };
  const quantity = (value) => { const n = num(value); return n == null ? '—' : new Intl.NumberFormat('en-US', { maximumFractionDigits: 4 }).format(n); };
  const pct = (value, digits = 1) => { const n = num(value); return n == null ? '—' : `${(n * 100).toFixed(digits)}%`; };
  const valueMap = (book) => Object.fromEntries((book?.account_values || []).map((row) => [row.tag, row.value_decimal]));
  const positionKey = (row) => `${row.account_alias || ''}:${row.conid}:${row.model_code || ''}`;
  const columnVisible = (key) => state.visibleColumns.includes(key);
  const scopedValue = (row, field) => {
    const value = num(row?.[field]);
    if (value == null || state.scope === 'all') return value;
    const brokerQty = num(row.quantity_decimal);
    const allocatedQty = (row.allocations || []).reduce((sum, allocation) => sum + (num(allocation.quantity_decimal) || 0), 0);
    return brokerQty ? value * allocatedQty / brokerQty : null;
  };

  function loadColumns() {
    try {
      const stored = JSON.parse(localStorage.getItem(COLUMN_STORAGE) || 'null');
      if (Array.isArray(stored) && stored.includes('instrument')) return stored.filter((key) => COLUMN_DEFS.some((column) => column.key === key));
    } catch (_) { /* ignore */ }
    return DEFAULT_COLUMNS.slice();
  }
  function loadViews() {
    try { return JSON.parse(localStorage.getItem(VIEW_STORAGE) || '[]'); } catch (_) { return []; }
  }
  function persistViews() { localStorage.setItem(VIEW_STORAGE, JSON.stringify(state.savedViews)); localStorage.setItem(COLUMN_STORAGE, JSON.stringify(state.visibleColumns)); }

  async function getJson(url) {
    const response = await fetch(url, { credentials: 'same-origin', cache: 'no-store', headers: { accept: 'application/json' } });
    if (!response.ok) throw new Error(response.status === 401 ? 'Sign in through Cloudflare Access to view the IBKR book.' : `Portfolio API ${response.status}`);
    return response.json();
  }

  function openLineage(metric, source, detail) {
    state.lineage = { metric, source, detail, as_of: state.book?.snapshot?.as_of || state.performance?.lineage?.nav?.as_of || null };
    renderPortfolio();
  }

  function openLinkedSymbol(symbol) {
    const ticker = String(symbol || '').split(' ')[0];
    if (typeof window.selectTicker === 'function' && typeof window.setView === 'function') {
      window.setView('holdings', { syncHash: false });
      window.selectTicker(ticker);
      return;
    }
    state.query = ticker;
    state.section = 'positions';
    renderPortfolio();
  }

  function portfolioSparkline(series, benchmark) {
    const rows = (series || []).map((row) => ({ value: num(row.nav_decimal), asOf: row.as_of })).filter((row) => row.value != null);
    if (rows.length < 2) return '<div class="ph-chart-empty">History begins after the next complete snapshots.</div>';
    const values = rows.map((row) => row.value);
    const low = Math.min(...values); const high = Math.max(...values); const spread = high - low || 1;
    const points = values.map((value, index) => `${(index / (values.length - 1) * 100).toFixed(2)},${(36 - ((value - low) / spread * 30)).toFixed(2)}`).join(' ');
    const positive = values[values.length - 1] >= values[0];
    const bench = (benchmark?.series || []).map((row) => num(row.value)).filter((value) => value != null);
    const benchPoints = bench.length === values.length ? bench.map((value, index) => {
      const scaled = 36 - ((value - Math.min(...bench)) / ((Math.max(...bench) - Math.min(...bench)) || 1) * 30);
      return `${(index / (bench.length - 1) * 100).toFixed(2)},${scaled.toFixed(2)}`;
    }).join(' ') : '';
    return `<svg class="ph-sparkline ${positive ? 'positive' : 'negative'}" viewBox="0 0 100 40" preserveAspectRatio="none" role="img" aria-label="Net liquidation history"><defs><linearGradient id="ph-nav-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="currentColor" stop-opacity=".24"/><stop offset="100%" stop-color="currentColor" stop-opacity="0"/></linearGradient></defs><polygon points="0,40 ${points} 100,40" fill="url(#ph-nav-fill)"/><polyline points="${points}" fill="none" vector-effect="non-scaling-stroke"/>${benchPoints ? `<polyline class="ph-benchmark" points="${benchPoints}" fill="none" vector-effect="non-scaling-stroke"/>` : ''}</svg>`;
  }

  function accountCockpit(book) {
    const values = valueMap(book);
    const nav = num(values.NetLiquidation); const daily = num(values.DailyPnL || values.DailyPnl);
    const maintenance = num(values.MaintMarginReq); const excess = num(values.ExcessLiquidity);
    const cushion = num(values.Cushion); const marginLoad = nav > 0 && maintenance != null ? Math.max(0, Math.min(1, maintenance / nav)) : null;
    const dataState = book?.status === 'complete' ? 'Broker feed complete' : 'Broker feed unavailable';
    return `<section class="ph-cockpit" aria-label="Account overview"><div class="ph-cockpit-value"><button type="button" class="ph-lineage-target" data-ph-lineage="Net liquidation" data-ph-source="IBKR live" data-ph-detail="Account tag NetLiquidation"><div class="ph-kicker">Net liquidation value</div><div class="ph-hero-value">${money(nav)}</div></button><div class="ph-daily ${daily < 0 ? 'ph-negative' : 'ph-positive'}"><span>${signed(daily)}</span><small>today</small></div><div class="ph-feed-state"><i class="${book?.status === 'complete' ? 'live' : ''}"></i>${esc(dataState)}</div></div><div class="ph-cockpit-chart"><div class="ph-chart-head"><span>Account value</span><b>${state.accountPerformance?.nav_series?.length || 0} observations</b></div>${portfolioSparkline(state.accountPerformance?.nav_series, state.accountPerformance?.benchmark)}</div><div class="ph-cockpit-safety"><div class="ph-kicker">Liquidity runway</div><div class="ph-safety-line"><span>Excess liquidity</span><b>${money(excess, true)}</b></div><div class="ph-safety-line"><span>Margin load</span><b>${pct(marginLoad)}</b></div><div class="ph-meter"><i style="width:${marginLoad == null ? 0 : (marginLoad * 100).toFixed(1)}%"></i></div><div class="ph-safety-line"><span>Broker cushion</span><b>${cushion == null ? '—' : pct(cushion)}</b></div><div class="ph-readonly"><span>READ ONLY</span> Orders stay in the approved Python workflow.</div></div></section>`;
  }

  function accountFacts(book) {
    const values = valueMap(book);
    const facts = [
      ['Net liquidation', values.NetLiquidation, 'IBKR live', 'Account tag NetLiquidation'],
      ['Daily P&L', values.DailyPnL || values.DailyPnl, 'IBKR P&L', 'IBKR reset-series, not Flex session P&L'],
      ['Buying power', values.BuyingPower, 'IBKR live', 'Account tag BuyingPower'],
      ['Initial margin', values.InitMarginReq, 'IBKR live', 'Broker-reported, not additive by owner'],
      ['Maintenance margin', values.MaintMarginReq, 'IBKR live', 'Broker-reported, not additive by owner'],
      ['Excess liquidity', values.ExcessLiquidity, 'IBKR live', 'Liquidity runway source'],
    ];
    return `<div class="ph-ledger"><div class="ph-facts">${facts.map(([label, value, source, detail]) => `<button type="button" class="ph-fact ph-lineage-target" data-ph-lineage="${esc(label)}" data-ph-source="${esc(source)}" data-ph-detail="${esc(detail)}"><div class="ph-fact-label">${label}</div><div class="ph-fact-value">${money(value, true)}</div><div class="ph-fact-source">${source}</div></button>`).join('')}</div>${scopeStrip(book)}</div>`;
  }

  function scopeStrip(book) {
    const positions = book?.positions || [];
    const gross = positions.reduce((sum, row) => sum + Math.abs(scopedValue(row, 'market_value_decimal') || 0), 0);
    const net = positions.reduce((sum, row) => sum + (scopedValue(row, 'market_value_decimal') || 0), 0);
    const pnl = positions.reduce((sum, row) => sum + (scopedValue(row, 'daily_pnl_decimal') || 0), 0);
    const cash = (book?.cash_events || []).reduce((sum, row) => sum + (num(row.amount_decimal) || 0), 0);
    const unresolved = (book?.reconciliation_breaks || []).length;
    const quarantined = (book?.positions || []).filter((row) => !(row.allocations || []).length).length;
    const label = state.scope === 'all' ? 'Whole account' : `${state.scope[0].toUpperCase()}${state.scope.slice(1)} allocation`;
    return `<div class="ph-scope-strip"><div class="ph-scope-name"><strong>${esc(label)}</strong><span>Selected scope · account facts above stay fixed</span></div><div class="ph-scope-metric"><span>Allocated cash</span><b>${money(cash, true)}</b></div><div class="ph-scope-metric"><span>Gross exposure</span><b>${money(gross, true)}</b></div><div class="ph-scope-metric"><span>Net exposure</span><b>${money(net, true)}</b></div><div class="ph-scope-metric"><span>Daily attributable P&L</span><b class="${pnl < 0 ? 'ph-negative' : 'ph-positive'}">${signed(pnl)}</b></div><div class="ph-scope-metric"><span>Orders / breaks / quarantine</span><b>${book?.broker_open_order_count || 0} / ${unresolved} / ${quarantined}</b></div></div>`;
  }

  function shellHeader(book) {
    const asOf = book?.snapshot?.as_of || 'No complete broker snapshot';
    return `<div class="ph-eyebrow">Private IBKR account · canonical ledger</div><div class="ph-title-row"><div><h2 class="ph-title">Portfolio book</h2><div class="ph-asof">${esc(asOf)} · ${esc(book?.status || 'unknown')}</div></div><div class="ph-scope-nav" aria-label="Portfolio scope">${['all', 'drew', 'michael'].map((scope) => `<button type="button" data-ph-scope="${scope}" class="${state.scope === scope ? 'active' : ''}">${scope === 'all' ? 'All positions' : scope[0].toUpperCase() + scope.slice(1)}</button>`).join('')}</div></div>${accountCockpit(book)}${accountFacts(book)}<div class="ph-section-nav" role="tablist">${sections.map((section) => `<button type="button" data-ph-section="${section}" class="${state.section === section ? 'active' : ''}">${section === 'margin' ? 'Margin & liquidity' : section[0].toUpperCase() + section.slice(1)}</button>`).join('')}</div>`;
  }

  function columnPicker() {
    if (!state.showColumns) return '';
    return `<div class="ph-column-picker" role="dialog" aria-label="Configurable columns"><div class="ph-column-grid">${COLUMN_DEFS.map((column) => `<label><input type="checkbox" data-ph-column="${column.key}" ${column.required ? 'checked disabled' : ''} ${columnVisible(column.key) ? 'checked' : ''}>${esc(column.label)}</label>`).join('')}</div><div class="ph-view-save"><input data-ph-view-name value="${esc(state.savedViewName)}" placeholder="Saved view name"><button type="button" data-ph-save-view>Save view</button></div></div>`;
  }

  function positionsView(book) {
    const query = state.query.trim().toLowerCase();
    const filterRow = (row) => {
      const quantityValue = state.scope === 'all' ? num(row.quantity_decimal) : (row.allocations || []).reduce((sum, allocation) => sum + (num(allocation.quantity_decimal) || 0), 0);
      if (state.positionFilter === 'equity' && !['STK', 'ETF'].includes(String(row.sec_type).toUpperCase())) return false;
      if (state.positionFilter === 'option' && String(row.sec_type).toUpperCase() !== 'OPT') return false;
      if (state.positionFilter === 'long' && !(quantityValue > 0)) return false;
      if (state.positionFilter === 'short' && !(quantityValue < 0)) return false;
      if (state.positionFilter === 'unallocated' && (row.allocations || []).length) return false;
      return !query || `${row.symbol} ${row.local_symbol} ${row.description} ${row.sec_type} ${row.currency} ${row.conid}`.toLowerCase().includes(query);
    };
    const sortable = (row) => state.sortKey === 'symbol' ? String(row.local_symbol || row.symbol || '') : (scopedValue(row, state.sortKey) ?? num(row[state.sortKey]) ?? 0);
    const rows = (book.positions || []).filter(filterRow).sort((left, right) => {
      const a = sortable(left); const b = sortable(right); const result = typeof a === 'string' ? a.localeCompare(b) : a - b;
      return state.sortDirection === 'asc' ? result : -result;
    });
    const filterLabels = { all: 'All', equity: 'Stocks & ETFs', option: 'Options', long: 'Long', short: 'Short', unallocated: 'Unallocated' };
    const sortHead = (label, key) => `<button type="button" data-ph-sort="${key}" class="ph-sort ${state.sortKey === key ? 'active' : ''}">${label}${state.sortKey === key ? `<span>${state.sortDirection === 'asc' ? '↑' : '↓'}</span>` : ''}</button>`;
    const selected = (book.positions || []).find((row) => positionKey(row) === state.selectedPositionKey);
    return `<div class="ph-toolbar ph-positions-toolbar"><div><strong>${rows.length}</strong> canonical instruments <span class="ph-dim">· no row truncation</span></div><div class="ph-view-actions"><label class="ph-search-wrap"><span>/</span><input class="ph-search" data-ph-search value="${esc(state.query)}" placeholder="Search the book" aria-label="Filter positions"></label><button type="button" class="ph-density" data-ph-columns>Columns & views</button><button type="button" class="ph-density" data-ph-density title="Toggle row density">${state.density === 'compact' ? 'Comfortable rows' : 'Compact rows'}</button></div></div>${columnPicker()}<div class="ph-filter-row">${Object.entries(filterLabels).map(([key, label]) => `<button type="button" data-ph-filter="${key}" class="${state.positionFilter === key ? 'active' : ''}">${label}</button>`).join('')}${state.savedViews.map((view) => `<button type="button" data-ph-load-view="${esc(view.name)}" class="ph-saved-view">${esc(view.name)}</button>`).join('')}</div><div class="ph-table-wrap"><table class="ph-table ${state.density === 'compact' ? 'compact' : ''}"><thead><tr>${COLUMN_DEFS.filter((column) => columnVisible(column.key)).map((column) => `<th>${column.sort ? sortHead(column.label, column.sort) : column.key === 'instrument' ? sortHead(column.label, 'symbol') : esc(column.label)}</th>`).join('')}</tr></thead><tbody>${rows.map((row) => {
      const allocation = (row.allocations || []).map((a) => `${a.owner}/${a.strategy}${a.bucket ? `/${a.bucket}` : ''}`).join(', ') || 'unallocated';
      const scopeDaily = scopedValue(row, 'daily_pnl_decimal');
      const cells = {
        instrument: `<td><button type="button" class="ph-symbol-link" data-ph-open-row="${esc(positionKey(row))}"><span class="ph-symbol">${esc(row.local_symbol || row.symbol)}</span></button><br><span class="ph-dim">${esc(row.description || row.symbol)}</span></td>`,
        allocation: `<td>${esc(allocation)}</td>`,
        identity: `<td>${row.conid}<br><span class="ph-dim">${esc(row.model_code || 'default')}</span></td>`,
        sec_type: `<td>${esc(row.sec_type)}</td>`,
        quantity_decimal: `<td>${quantity(state.scope === 'all' ? row.quantity_decimal : row.allocations?.reduce((s, a) => s + (num(a.quantity_decimal) || 0), 0))}</td>`,
        average_cost_decimal: `<td>${money(row.average_cost_decimal)}</td>`,
        mark_decimal: `<td>${money(row.mark_decimal)}</td>`,
        market_value_decimal: `<td>${money(scopedValue(row, 'market_value_decimal'))}</td>`,
        daily_pnl_decimal: `<td class="${scopeDaily < 0 ? 'ph-negative' : 'ph-positive'}">${signed(scopeDaily)}</td>`,
        unrealized_pnl_decimal: `<td>${signed(scopedValue(row, 'unrealized_pnl_decimal'))}</td>`,
        currency: `<td>${esc(row.currency)}</td>`,
        quality: `<td><span class="ph-pill ${row.quality === 'live' ? 'live' : ''}">${esc(row.quality)}</span></td>`,
      };
      return `<tr class="${positionKey(row) === state.selectedPositionKey ? 'ph-row-open' : ''}">${COLUMN_DEFS.filter((column) => columnVisible(column.key)).map((column) => cells[column.key]).join('')}</tr>`;
    }).join('')}</tbody></table>${rows.length ? '' : '<div class="ph-empty"><div><b>No positions in this scope</b>Broker truth remains visible in All; unresolved ownership belongs in Reconciliation.</div></div>'}</div>${positionDrawer(selected)}${lineageDrawer()}`;
  }

  function positionDrawer(row) {
    if (!row) return '';
    const lots = row.allocations || [];
    const related = (state.book?.positions || []).filter((candidate) => candidate.symbol === row.symbol && positionKey(candidate) !== positionKey(row));
    const orders = (state.orders?.broker_open_orders || []).filter((order) => Number(order.conid) === Number(row.conid));
    return `<aside class="ph-drawer" aria-label="Position detail"><div class="ph-drawer-head"><div><div class="ph-kicker">Position detail</div><h3>${esc(row.local_symbol || row.symbol)}</h3><div class="ph-dim">${esc(row.description || '')} · conId ${row.conid}</div></div><button type="button" data-ph-close-drawer>Close</button></div><div class="ph-drawer-grid">${[['Quantity', quantity(row.quantity_decimal)], ['Average cost', money(row.average_cost_decimal)], ['Mark', money(row.mark_decimal)], ['Market value', money(row.market_value_decimal)], ['Daily P&L', signed(row.daily_pnl_decimal)], ['Unrealized', signed(row.unrealized_pnl_decimal)], ['Currency', row.currency], ['Quality', row.quality], ['Source', row.source], ['As of', row.as_of]].map(([k, v]) => `<div><span>${esc(k)}</span><b>${esc(v)}</b></div>`).join('')}</div><h4>Allocation lots</h4><div class="ph-table-wrap"><table class="ph-table"><thead><tr><th>Owner</th><th>Strategy</th><th>Bucket</th><th>Qty</th><th>Confidence</th></tr></thead><tbody>${lots.map((lot) => `<tr><td>${esc(lot.owner)}</td><td>${esc(lot.strategy)}</td><td>${esc(lot.bucket || '—')}</td><td>${quantity(lot.quantity_decimal)}</td><td>${esc(lot.confidence)}</td></tr>`).join('')}</tbody></table>${lots.length ? '' : '<div class="ph-empty"><div><b>Quarantined / unallocated</b>This broker quantity has no approved owner or strategy lot.</div></div>'}</div><div class="ph-drawer-links"><button type="button" data-ph-linked-symbol="${esc(row.symbol)}">Open ${esc(row.symbol)} research</button>${related.map((candidate) => `<button type="button" data-ph-open-row="${esc(positionKey(candidate))}">Linked ${esc(candidate.local_symbol || candidate.symbol)} ${candidate.sec_type}</button>`).join('')}</div>${orders.length ? `<h4>Working orders</h4><ul>${orders.map((order) => `<li>${esc(order.action)} ${quantity(order.total_quantity_decimal)} @ ${money(order.limit_price_decimal)} · ${esc(order.ownership)}</li>`).join('')}</ul>` : ''}</aside>`;
  }

  function lineageDrawer() {
    if (!state.lineage) return '';
    return `<aside class="ph-drawer ph-lineage-drawer" aria-label="Metric lineage"><div class="ph-drawer-head"><div><div class="ph-kicker">Metric lineage</div><h3>${esc(state.lineage.metric)}</h3></div><button type="button" data-ph-close-lineage>Close</button></div><div class="ph-drawer-grid"><div><span>Source</span><b>${esc(state.lineage.source)}</b></div><div><span>As of</span><b>${esc(state.lineage.as_of || '—')}</b></div><div><span>Detail</span><b>${esc(state.lineage.detail)}</b></div></div></aside>`;
  }

  function panelLines(title, lines) { return `<section class="ph-panel"><h3>${esc(title)}</h3>${lines.map(([k, v]) => `<div class="ph-line"><span>${esc(k)}</span><b>${esc(v)}</b></div>`).join('')}</section>`; }
  function sectionView(book) {
    if (state.section === 'positions') return positionsView(book);
    const values = valueMap(book);
    if (state.section === 'margin') return `<div class="ph-grid">${panelLines('Broker-reported account margin', [['Initial requirement', money(values.InitMarginReq)], ['Maintenance requirement', money(values.MaintMarginReq)], ['Available funds', money(values.AvailableFunds)], ['Excess liquidity', money(values.ExcessLiquidity)], ['Cushion', values.Cushion || '—'], ['SMA', money(values.SMA)]])}${panelLines('Selected scope', [['Attribution', 'Model estimates only'], ['Broker margin allocation', 'Not additive'], ['Incremental margin', 'IBKR what-if when previewed']])}${panelLines('History & lineage', [['Observations', String(state.margin?.rows?.length || 0)], ['Value kind', state.margin?.value_kind || 'broker_reported'], ['Source', 'IBKR account summary']])}</div>${lineageDrawer()}`;
    if (state.section === 'risk') return riskView(book);
    if (state.section === 'performance') return performanceView();
    if (state.section === 'orders') return ordersView();
    return reconciliationView(book);
  }

  function riskView(book) {
    const factors = state.risk?.factors || [];
    const concentration = state.risk?.concentration || [];
    return `<div class="ph-grid">${panelLines('Concentration', [['Gross exposure', money(state.risk?.gross_exposure, true)], ['Net exposure', money(state.risk?.net_exposure, true)], ['Largest weight', state.risk?.concentration?.[0]?.gross_weight == null ? '—' : `${(state.risk.concentration[0].gross_weight * 100).toFixed(1)}%`]])}${panelLines('Linear sensitivities', [['Beta exposure', money(state.risk?.linear_sensitivities?.beta_exposure, true)], ['Delta exposure', money(state.risk?.linear_sensitivities?.delta_exposure, true)], ['Gamma / vega', `${state.risk?.linear_sensitivities?.gamma ?? '—'} / ${state.risk?.linear_sensitivities?.vega ?? '—'}`]])}${panelLines('Coverage & nonlinear gates', [['Broker positions', String(state.risk?.coverage?.broker_positions ?? book.positions?.length ?? 0)], ['Linked producer rows', `${state.risk?.coverage?.linked_atomic_rows ?? 0} / ${state.risk?.coverage?.producer_atomic_rows ?? 0}`], ['Scenario risk', state.risk?.nonlinear?.value == null ? 'Suppressed — unsupported scope' : String(state.risk.nonlinear.value)], ['Open breaks', String(book.reconciliation_breaks?.length || 0)]])}</div><div class="ph-split"><section class="ph-panel"><h3>Factor drill-down</h3><div class="ph-table-wrap"><table class="ph-table"><thead><tr><th>Row</th><th>Symbol</th><th>Role</th><th>Basis</th><th>Beta</th><th>Delta</th></tr></thead><tbody>${factors.map((row) => `<tr><td>${esc(row.row_id)}</td><td><button type="button" class="ph-symbol-link" data-ph-linked-symbol="${esc(row.symbol || '')}">${esc(row.symbol || '—')}</button></td><td>${esc(row.reconciliation_role)}</td><td>${esc(row.exposure_basis)}</td><td>${esc(row.beta_exposure ?? '—')}</td><td>${esc(row.delta_exposure ?? '—')}</td></tr>`).join('')}</tbody></table>${factors.length ? '' : '<div class="ph-empty"><div><b>No factor rows at this scope</b>Producer atomic rows stay unpublished rather than being pro-rated.</div></div>'}</div></section><section class="ph-panel"><h3>Scenario drill-down</h3><p>${esc(state.risk?.nonlinear?.null_reason || 'Scenario vectors have not been published.')}</p><div class="ph-table-wrap"><table class="ph-table"><thead><tr><th>Symbol</th><th>Weight</th><th>Market value</th></tr></thead><tbody>${concentration.map((row) => `<tr><td><button type="button" class="ph-symbol-link" data-ph-linked-symbol="${esc(row.symbol)}">${esc(row.symbol)}</button></td><td>${row.gross_weight == null ? '—' : `${(row.gross_weight * 100).toFixed(1)}%`}</td><td>${money(row.market_value, true)}</td></tr>`).join('')}</tbody></table></div></section></div>${lineageDrawer()}`;
  }

  function performanceView() {
    const reason = state.performance?.benchmark?.null_reason || state.performance?.null_reason || 'Benchmark withheld';
    return `<div class="ph-grid">${panelLines('Live P&L', [['Daily', 'IBKR reset-series'], ['Unrealized', 'Broker-reported'], ['Realized', 'Execution/Flex reconcile']])}${panelLines('Completed sessions', [['Flex versions', String(state.performance?.completed_sessions?.length || 0)], ['Session P&L', 'Immutable Flex lineage'], ['Restatements', 'Separate series'], ['Legacy pnl_today', 'Never used as daily']])}${panelLines('Returns', [['NAV observations', String(state.performance?.nav_series?.length || 0)], ['TWR', state.performance?.twr == null ? 'Suppressed' : String(state.performance.twr)], ['Max drawdown', state.performance?.max_drawdown == null ? '—' : `${(state.performance.max_drawdown * 100).toFixed(2)}%`], ['Reason', state.performance?.null_reason || '—']])}</div><section class="ph-panel ph-chart-panel"><div class="ph-chart-head"><span>NAV vs ${esc(state.performance?.benchmark?.symbol || 'SPY')}</span><button type="button" class="ph-density" data-ph-lineage="NAV vs benchmark" data-ph-source="IBKR NetLiquidation" data-ph-detail="${esc(reason)}">Lineage</button></div>${portfolioSparkline(state.performance?.nav_series, state.performance?.benchmark)}<p class="ph-dim">${esc(reason)}</p></section>${lineageDrawer()}`;
  }

  function ordersView() {
    const events = state.orders?.events || [];
    const broker = state.orders?.broker_open_orders || [];
    return `<div class="ph-alert"><strong>Python command plane only.</strong> The browser is read-only. Orders require a qualified conId, quote and what-if preview, ticket-bound approval, positive orderRef, and reconciliation.</div><div class="ph-toolbar"><strong>Broker open orders · ${broker.length}</strong><span class="ph-dim">Foreign/manual orders are visible and never cancellable by the hub.</span></div><div class="ph-table-wrap"><table class="ph-table"><thead><tr><th>Symbol</th><th>ConId</th><th>Action</th><th>Qty</th><th>Limit</th><th>Status</th><th>Ownership</th><th>Client / order / perm</th><th>Order ref</th></tr></thead><tbody>${broker.map((row) => `<tr><td><button type="button" class="ph-symbol-link" data-ph-linked-symbol="${esc(row.symbol)}">${esc(row.symbol)}</button></td><td>${esc(row.conid)}</td><td>${esc(row.action)}</td><td>${quantity(row.total_quantity_decimal)}</td><td>${money(row.limit_price_decimal)}</td><td>${esc(row.status)}</td><td><span class="ph-pill ${row.ownership === 'hub' ? 'live' : ''}">${esc(row.ownership)}</span></td><td>${esc(row.client_id)} / ${esc(row.order_id)} / ${esc(row.perm_id)}</td><td>${esc(row.order_ref || '—')}</td></tr>`).join('')}</tbody></table>${broker.length ? '' : '<div class="ph-empty"><div><b>No broker open orders</b>The latest complete snapshot contains no working orders.</div></div>'}</div><div class="ph-toolbar"><strong>Central intent history</strong></div><div class="ph-table-wrap"><table class="ph-table"><thead><tr><th>Intent</th><th>Order ref</th><th>ConId</th><th>State</th><th>Event</th><th>Time</th></tr></thead><tbody>${events.map((row) => `<tr><td>${esc(row.intent_uuid)}</td><td>${esc(row.order_ref)}</td><td>${row.conid}</td><td>${esc(row.state)}</td><td>${esc(row.event_type)}</td><td>${esc(row.created_at)}</td></tr>`).join('')}</tbody></table>${events.length ? '' : '<div class="ph-empty"><div><b>No central order events</b>Paper orders will appear after the private bridge publishes its audit outbox.</div></div>'}</div>`;
  }

  function reconciliationView(book) {
    const rows = book.reconciliation_breaks || [];
    const quarantined = (book.positions || []).filter((row) => !(row.allocations || []).length);
    return `<div class="ph-alert"><strong>Quarantine is visible by default.</strong> Unresolved conIds and cash remain unallocated until an approved bootstrap lot exists.</div><div class="ph-toolbar"><strong>Unresolved positions · ${quarantined.length}</strong></div><div class="ph-table-wrap"><table class="ph-table"><thead><tr><th>Instrument</th><th>ConId / model</th><th>Qty</th><th>Market value</th><th>Status</th></tr></thead><tbody>${quarantined.map((row) => `<tr><td><button type="button" class="ph-symbol-link" data-ph-open-row="${esc(positionKey(row))}">${esc(row.local_symbol || row.symbol)}</button></td><td>${row.conid} / ${esc(row.model_code || 'default')}</td><td>${quantity(row.quantity_decimal)}</td><td>${money(row.market_value_decimal)}</td><td>quarantined</td></tr>`).join('')}</tbody></table>${quarantined.length ? '' : '<div class="ph-empty"><div><b>No quarantined broker rows</b>Every conId has an allocation lot at this watermark.</div></div>'}</div><div class="ph-table-wrap" style="margin-top:16px"><table class="ph-table"><thead><tr><th>Severity</th><th>Type</th><th>Instrument</th><th>Expected</th><th>Actual</th><th>Status</th></tr></thead><tbody>${rows.map((row) => `<tr><td>${esc(row.severity)}</td><td>${esc(row.break_type)}</td><td>${esc(row.conid || 'account')} ${esc(row.model_code || '')}</td><td>${esc(row.expected_decimal)}</td><td>${esc(row.actual_decimal)}</td><td>${esc(row.status)}</td></tr>`).join('')}</tbody></table>${rows.length ? '' : '<div class="ph-empty"><div><b>No open reconciliation breaks</b>The latest complete broker snapshot and allocation ledger agree within tolerance.</div></div>'}</div>${positionDrawer((book.positions || []).find((row) => positionKey(row) === state.selectedPositionKey))}`;
  }

  async function loadActiveSectionData() {
    try {
      if (state.section === 'orders' || state.selectedPositionKey) state.orders = await getJson('/api/v2/portfolio/orders');
      if (state.section === 'performance') state.performance = await getJson(`/api/v2/portfolio/performance?owner=${state.scope}`);
      if (state.section === 'margin' && !state.margin) state.margin = await getJson('/api/v2/portfolio/margin');
      if (state.section === 'risk') state.risk = await getJson(`/api/v2/portfolio/risk?owner=${state.scope}`);
    } catch (error) {
      state[state.section] = { error: error.message };
    }
  }

  function bindCommon(root) {
    root.querySelectorAll('[data-ph-scope]').forEach((button) => button.addEventListener('click', () => { state.scope = button.dataset.phScope; state.risk = null; state.performance = null; state.onRoute?.(); loadBook(); }));
    root.querySelectorAll('[data-ph-section]').forEach((button) => button.addEventListener('click', async () => { state.section = button.dataset.phSection; state.onRoute?.(); await loadActiveSectionData(); renderPortfolio(); }));
    root.querySelectorAll('[data-ph-lineage]').forEach((button) => button.addEventListener('click', () => openLineage(button.dataset.phLineage, button.dataset.phSource, button.dataset.phDetail)));
    root.querySelectorAll('[data-ph-linked-symbol]').forEach((button) => button.addEventListener('click', () => openLinkedSymbol(button.dataset.phLinkedSymbol)));
    root.querySelectorAll('[data-ph-open-row]').forEach((button) => button.addEventListener('click', async () => { state.selectedPositionKey = button.dataset.phOpenRow; await loadActiveSectionData(); renderPortfolio(); }));
    root.querySelector('[data-ph-close-drawer]')?.addEventListener('click', () => { state.selectedPositionKey = null; renderPortfolio(); });
    root.querySelector('[data-ph-close-lineage]')?.addEventListener('click', () => { state.lineage = null; renderPortfolio(); });
  }

  function renderPortfolio() {
    const root = document.getElementById('portfolio-content'); if (!root) return;
    const book = state.book;
    root.innerHTML = `<div class="ph-shell">${shellHeader(book)}${book?.status === 'complete' ? sectionView(book) : `<div class="ph-empty"><div><b>Waiting for the first complete IBKR snapshot</b>${esc(book?.reason || 'The private collector has not published broker truth yet.')}</div></div>`}</div>`;
    bindCommon(root);
    root.querySelector('[data-ph-search]')?.addEventListener('input', (event) => { state.query = event.target.value; renderPortfolio(); const input = root.querySelector('[data-ph-search]'); input?.focus(); input?.setSelectionRange(state.query.length, state.query.length); });
    root.querySelectorAll('[data-ph-filter]').forEach((button) => button.addEventListener('click', () => { state.positionFilter = button.dataset.phFilter; renderPortfolio(); }));
    root.querySelectorAll('[data-ph-sort]').forEach((button) => button.addEventListener('click', () => { const key = button.dataset.phSort; state.sortDirection = state.sortKey === key && state.sortDirection === 'desc' ? 'asc' : 'desc'; state.sortKey = key; renderPortfolio(); }));
    root.querySelector('[data-ph-density]')?.addEventListener('click', () => { state.density = state.density === 'compact' ? 'comfortable' : 'compact'; localStorage.setItem('portfolio-density', state.density); renderPortfolio(); });
    root.querySelector('[data-ph-columns]')?.addEventListener('click', () => { state.showColumns = !state.showColumns; renderPortfolio(); });
    root.querySelectorAll('[data-ph-column]').forEach((input) => input.addEventListener('change', () => {
      const key = input.dataset.phColumn;
      if (input.checked && !state.visibleColumns.includes(key)) state.visibleColumns.push(key);
      if (!input.checked) state.visibleColumns = state.visibleColumns.filter((item) => item !== key);
      persistViews(); renderPortfolio();
    }));
    root.querySelector('[data-ph-view-name]')?.addEventListener('input', (event) => { state.savedViewName = event.target.value; });
    root.querySelector('[data-ph-save-view]')?.addEventListener('click', () => {
      const name = state.savedViewName.trim();
      if (!name) return;
      state.savedViews = [...state.savedViews.filter((view) => view.name !== name), { name, columns: state.visibleColumns.slice(), filter: state.positionFilter, sortKey: state.sortKey, sortDirection: state.sortDirection, density: state.density }];
      persistViews(); renderPortfolio();
    });
    root.querySelectorAll('[data-ph-load-view]').forEach((button) => button.addEventListener('click', () => {
      const view = state.savedViews.find((item) => item.name === button.dataset.phLoadView);
      if (!view) return;
      state.visibleColumns = view.columns.slice(); state.positionFilter = view.filter; state.sortKey = view.sortKey; state.sortDirection = view.sortDirection; state.density = view.density;
      persistViews(); renderPortfolio();
    }));
  }

  async function loadBook() {
    const root = document.getElementById('portfolio-content'); if (root) root.innerHTML = '<div class="ph-empty"><div><b>Reconciling broker book…</b>Loading the latest complete snapshot.</div></div>';
    try {
      const requests = [getJson(`/api/v2/portfolio/book?owner=${encodeURIComponent(state.scope)}`)];
      if (!state.accountPerformance) requests.push(getJson('/api/v2/portfolio/performance?owner=all'));
      const responses = await Promise.all(requests); state.book = responses[0];
      if (responses[1]) state.accountPerformance = responses[1];
    }
    catch (error) { state.book = { status: 'unknown', reason: error.message, positions: [], account_values: [], reconciliation_breaks: [] }; }
    await loadActiveSectionData();
    renderPortfolio();
  }

  function strategyRows(payload) {
    const chosen = state.strategySection;
    return (payload?.rows || []).filter((row) => chosen === 'overview' || String(row.bucket || '').toLowerCase() === chosen);
  }
  function renderStrategy(producer) {
    const isSpx = producer === 'spx_0dte'; const root = document.getElementById(isSpx ? 'spx-0dte-content' : 'letf-content'); if (!root) return;
    const payload = state.strategy || {}; const rows = strategyRows(payload);
    root.innerHTML = `<div class="ph-shell"><div class="ph-eyebrow">Versioned strategy producer · broker-reconciled separately</div><div class="ph-title-row"><div><h2 class="ph-title">${isSpx ? 'SPX 0DTE' : 'Leveraged ETF book'}</h2><div class="ph-asof">${esc(payload.as_of || 'No producer snapshot')} · ${esc(payload.status || 'unknown')}</div></div></div>${isSpx ? '' : `<div class="ph-bucket-nav">${buckets.map((bucket) => `<button type="button" data-ph-bucket="${bucket}" class="${state.strategySection === bucket ? 'active' : ''}">${bucket === 'overview' ? 'Overview' : bucket.toUpperCase()}</button>`).join('')}</div>`}<div class="ph-grid">${panelLines('Producer health', [['Status', payload.status || 'unknown'], ['Rows', String(rows.length)], ['Run', payload.source_run_id || '—']])}${panelLines('Reconciliation discipline', [['Broker positions', 'Canonical account feed'], ['Model analytics', 'Producer lineage'], ['Stale fallback', 'Broker facts only']])}${panelLines(isSpx ? 'Session controls' : 'Accounting bases', isSpx ? [['Health / halt', 'Producer snapshot'], ['Defined risk', 'Strategy model'], ['Orders', 'Positive orderRef required']] : [['Exposure', 'B1+B2+B4+unbucketed'], ['Factors', 'B3/B5 excluded'], ['P&L', 'B1–B5']])}</div><div class="ph-table-wrap" style="margin-top:12px"><table class="ph-table"><thead><tr><th>Row</th><th>Symbol</th><th>Strategy</th><th>Bucket</th><th>Product class</th><th>Role</th><th>Basis</th><th>Metrics</th></tr></thead><tbody>${rows.map((row) => `<tr><td>${esc(row.row_id)}</td><td><button type="button" class="ph-symbol-link" data-ph-linked-symbol="${esc(row.symbol || row.underlying || '')}">${esc(row.symbol || row.underlying || '—')}</button></td><td>${esc(row.strategy)}</td><td>${esc(row.bucket || '—')}</td><td>${esc(row.product_class || '—')}</td><td>${esc(row.reconciliation_role)}</td><td>${esc(row.exposure_basis)}</td><td>${esc(JSON.stringify(row.metrics || {}))}</td></tr>`).join('')}</tbody></table>${rows.length ? '' : `<div class="ph-empty"><div><b>No ${isSpx ? 'SPX' : 'bucket'} producer rows</b>The page is ready for the first signed strategy_snapshot.v1 artifact.</div></div>`}</div></div>`;
    root.querySelectorAll('[data-ph-bucket]').forEach((button) => button.addEventListener('click', () => { state.strategySection = button.dataset.phBucket; state.onRoute?.(); renderStrategy(producer); }));
    root.querySelectorAll('[data-ph-linked-symbol]').forEach((button) => button.addEventListener('click', () => openLinkedSymbol(button.dataset.phLinkedSymbol)));
  }

  async function openStrategy(producer, onRoute) {
    state.onRoute = onRoute; if (producer === 'spx_0dte') state.strategySection = 'overview';
    const root = document.getElementById(producer === 'spx_0dte' ? 'spx-0dte-content' : 'letf-content');
    if (root) root.innerHTML = '<div class="ph-empty"><div><b>Loading producer snapshot…</b>Broker facts remain independent of model availability.</div></div>';
    try { state.strategy = await getJson(`/api/v2/portfolio/strategies?producer=${encodeURIComponent(producer)}`); }
    catch (error) { state.strategy = { status: 'unknown', rows: [], error: error.message }; }
    renderStrategy(producer);
  }

  window.PortfolioViz = {
    state,
    setRoute(scope, section) { if (['all', 'drew', 'michael'].includes(scope)) state.scope = scope; if (sections.includes(section)) state.section = section; },
    setStrategyRoute(section) { if (buckets.includes(section)) state.strategySection = section; },
    openPortfolio(onRoute) { state.onRoute = onRoute; loadBook(); },
    openStrategy,
  };
})();
