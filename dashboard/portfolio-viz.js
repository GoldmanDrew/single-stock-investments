(function () {
  'use strict';

  const COLUMN_DEFS = [
    { key: 'instrument', label: 'Instrument', required: true },
    { key: 'allocation', label: 'Allocation' },
    { key: 'identity', label: 'ConId / model' },
    { key: 'sec_type', label: 'Type' },
    { key: 'quantity_decimal', label: 'Qty', sort: 'quantity_decimal' },
    { key: 'average_cost_decimal', label: 'Avg cost · native' },
    { key: 'mark_decimal', label: 'Mark · native' },
    { key: 'market_value_decimal', label: 'Market value · base', sort: 'market_value_decimal' },
    { key: 'daily_pnl_decimal', label: 'Daily P&L · base', sort: 'daily_pnl_decimal' },
    { key: 'unrealized_pnl_decimal', label: 'Unrealized · base', sort: 'unrealized_pnl_decimal' },
    { key: 'currency', label: 'Currency' },
    { key: 'quality', label: 'Quality' },
  ];
  const DEFAULT_COLUMNS = COLUMN_DEFS.map((column) => column.key);
  const VIEW_STORAGE = 'portfolio-saved-views';
  const COLUMN_STORAGE = 'portfolio-visible-columns';

  const state = {
    scope: 'all', section: 'positions', strategySection: 'overview', strategyBucket: 'all', book: null, allBook: null,
    orders: null, paperOrders: null, performance: null, accountPerformance: null, margin: null, risk: null,
    strategy: null, query: '', positionFilter: 'all', sortKey: 'market_value_decimal',
    sortDirection: 'desc', density: localStorage.getItem('portfolio-density') || 'comfortable', onRoute: null,
    selectedPositionKey: null, lineage: null, showColumns: false, savedViewName: '', orderNotice: null,
    // Guarded order desk. `orderRequests` is the owner's recent tickets from the
    // command channel; `activeRequest` is the one being worked right now.
    orderRequests: null, activeRequestId: null, orderPollTimer: null,
    // Contract resolution. `contractDraft` is what the picker has settled on so
    // far; a ticket cannot be submitted until it holds a conId the hub resolved,
    // because a hand-typed option id is something nobody can check.
    contractDraft: { sec_type: 'STK', symbol: '', conid: null, identity: null },
    contractSuggestions: [], contractChain: null, contractLookup: null, lookupPollTimer: null,
    visibleColumns: loadColumns(), savedViews: loadViews(),
  };
  const sections = ['positions', 'risk', 'margin', 'performance', 'orders', 'reconciliation'];
  const strategySections = ['overview', 'positions', 'pnl', 'margin', 'risk', 'orders', 'reconciliation'];
  const buckets = ['all', 'b1', 'b2', 'b3', 'b4', 'b5', 'unbucketed'];
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const format = window.DashboardFormat;
  const num = (value) => format?.finite(value) ?? (() => { if (value == null || value === '') return null; const n = Number(value); return Number.isFinite(n) ? n : null; })();
  const money = (value, compact = false, currency = 'USD') => format ? format.currency(value, currency, { maximumFractionDigits: compact ? 0 : 2, notation: compact ? 'compact' : 'standard' }) : '—';
  const signed = (value, currency = 'USD') => { const n = num(value); return n == null ? '—' : `${n > 0 ? '+' : ''}${money(n, false, currency)}`; };
  const quantity = (value) => format ? format.number(value, { maximumFractionDigits: 4 }) : '—';
  const pct = (value, digits = 1) => { const n = num(value); return n == null ? '—' : `${(n * 100).toFixed(digits)}%`; };
  const valueMap = (book) => Object.fromEntries((book?.account_values || []).map((row) => [row.tag, row.value_decimal]));
  const positionKey = (row) => `${row.account_alias || ''}:${row.conid}:${row.model_code || ''}`;
  const columnVisible = (key) => state.visibleColumns.includes(key);
  const BASE_FIELD = {
    market_value_decimal: 'market_value_base_decimal',
    daily_pnl_decimal: 'daily_pnl_base_decimal',
    unrealized_pnl_decimal: 'unrealized_pnl_base_decimal',
    realized_pnl_decimal: 'realized_pnl_base_decimal',
  };
  const NATIVE_FIELD = {
    market_value_decimal: 'market_value_native_decimal',
    average_cost_decimal: 'average_cost_native_decimal',
    mark_decimal: 'mark_native_decimal',
  };
  const baseCurrencyOf = (row) => row?.base_currency || state.book?.snapshot?.base_currency || 'USD';
  const nativeCurrencyOf = (row) => row?.native_currency || row?.currency || baseCurrencyOf(row);
  const isNativeBase = (row) => nativeCurrencyOf(row) === baseCurrencyOf(row);

  /**
   * True when this row's base-currency figures are trustworthy.
   *
   * A same-currency row needs no translation. A foreign row needs an explicit
   * base figure AND a real FX rate behind it. Without both, the only number the
   * payload carries is the native one -- and 3,000 shares at JPY 1,688 is
   * 5,064,000 yen, which is about USD 34k, not USD 5,064,000. Presenting that
   * native figure as base is what made a small Tokyo position sort as the
   * largest holding in the book.
   */
  // Sources whose rate is inferred rather than stated. IBKR's own ExchangeRate is
  // authoritative and needs no sanity test -- EUR and CHF have both traded within
  // a whisker of parity, and second-guessing a stated rate would reject them.
  const INFERRED_FX = new Set(['ibkr_portfolio_translation']);

  /**
   * An inferred rate of ~1 between two different currencies carries no
   * information: it means the collector divided a figure by itself, because
   * IBKR returned marketValue in the contract currency rather than in base. It
   * is never exactly 1 -- marketValue is rounded to 2dp against a full-precision
   * product -- so an equality test cannot catch it. Observed live: JPY at
   * 1.000000000645, CAD at 0.999999996454, both labelled as real translations.
   */
  const hasUsableRate = (row) => {
    if (!INFERRED_FX.has(row?.fx_source)) return true;
    const rate = num(row?.fx_rate_to_base_decimal);
    return rate != null && Math.abs(rate - 1) >= 0.0001;
  };

  const hasBaseValue = (row) => isNativeBase(row)
    || (row?.market_value_base_decimal != null && row?.fx_source
        && row.fx_source !== 'fx_unavailable' && hasUsableRate(row));

  const scopeToOwner = (row, value) => {
    if (value == null || state.scope === 'all') return value;
    const brokerQty = num(row.quantity_decimal);
    const allocatedQty = (row.allocations || []).reduce((sum, allocation) => sum + (num(allocation.quantity_decimal) || 0), 0);
    return brokerQty ? value * allocatedQty / brokerQty : null;
  };

  /** A figure in account base currency, or null when it cannot be stated in base. */
  const scopedValue = (row, field) => {
    const baseField = BASE_FIELD[field];
    // Never fall back across currencies: a missing base figure on a foreign row
    // means "unknown in base", not "same as native".
    const raw = isNativeBase(row) ? (row?.[baseField] ?? row?.[field]) : (hasBaseValue(row) ? row?.[baseField] : null);
    return scopeToOwner(row, num(raw));
  };

  /** The same figure in the currency it was quoted in, which always exists. */
  const scopedNative = (row, field) => scopeToOwner(row, num(row?.[NATIVE_FIELD[field]] ?? row?.[field]));

  /**
   * P&L as a percentage of cost. Numerator and denominator are taken from the
   * same currency, so the ratio is unit-free and correct even when the row has
   * no usable FX rate.
   */
  const pnlPercent = (row, field) => {
    const useBase = hasBaseValue(row) && num(row[BASE_FIELD[field]]) != null;
    const pnl = num(useBase ? row[BASE_FIELD[field]] : row[field]);
    const value = num(useBase ? (row.market_value_base_decimal ?? row.market_value_decimal) : (row.market_value_native_decimal ?? row.market_value_decimal));
    if (pnl == null || value == null) return null;
    const cost = value - pnl;
    return cost ? pnl / Math.abs(cost) : null;
  };

  /**
   * Market value in account base, with the native quote underneath.
   *
   * When the row cannot be stated in base the base slot says so rather than
   * showing the native number with a base currency symbol.
   */
  function marketValueCell(row) {
    const base = scopedValue(row, 'market_value_decimal');
    const nativeCurrency = nativeCurrencyOf(row);
    const nativeText = isNativeBase(row) ? '' : `<br><span class="ph-dim">${money(scopedNative(row, 'market_value_decimal'), false, nativeCurrency)}</span>`;
    if (base == null) {
      return `<span class="ph-unconverted" title="No usable ${nativeCurrency}/${baseCurrencyOf(row)} rate in this snapshot, so this position has no base-currency value.">not converted</span>${nativeText}`;
    }
    return `${money(base, false, baseCurrencyOf(row))}${nativeText}`;
  }

  /** Signed P&L in base, with the percentage of cost it represents. */
  function pnlCell(row, field, precomputed) {
    const value = precomputed === undefined ? scopedValue(row, field) : precomputed;
    const percent = pnlPercent(row, field);
    const percentText = percent == null ? '' : `<span class="ph-pnl-pct">${percent > 0 ? '+' : ''}${(percent * 100).toFixed(1)}%</span>`;
    if (value == null) {
      // The percentage is a ratio within one currency, so it survives a missing
      // FX rate even when the base amount does not.
      const native = scopedNative(row, field === 'daily_pnl_decimal' ? 'market_value_decimal' : field);
      const nativeAmount = num(row[field]);
      return `${nativeAmount == null ? '—' : signed(nativeAmount, nativeCurrencyOf(row))}${percentText}`;
    }
    return `${signed(value, baseCurrencyOf(row))}${percentText}`;
  }

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

  async function sendJson(url, options) {
    const response = await fetch(url, {
      credentials: 'same-origin', cache: 'no-store',
      ...options,
      headers: { accept: 'application/json', 'content-type': 'application/json', 'x-paper-order-mode': 'paper', ...(options?.headers || {}) },
    });
    let payload = {};
    try { payload = await response.json(); } catch (_) { /* use status fallback */ }
    if (!response.ok) throw new Error(payload.error || `Paper order API ${response.status}`);
    return payload;
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

  /**
   * A time axis rendered as HTML underneath the chart rather than inside it.
   *
   * Both charts are `preserveAspectRatio="none"` so the plot fills its box; any
   * <text> inside them is stretched by the same factor and becomes unreadable.
   * Laying the labels out in HTML keeps them upright at any width.
   *
   * The format follows the span: a series covering hours needs clock times, one
   * covering weeks needs dates, and printing the wrong one makes a chart look
   * like it covers a period it does not.
   */
  function timeAxis(stamps, ariaLabel = 'Time axis') {
    const times = (stamps || []).map((value) => Date.parse(value)).filter((value) => Number.isFinite(value));
    if (times.length < 2) return '';
    const first = times[0];
    const last = times[times.length - 1];
    const spanHours = (last - first) / 3_600_000;
    const fmt = (ms) => {
      const date = new Date(ms);
      if (spanHours <= 36) {
        return date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', hour12: false });
      }
      return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
    };
    const ticks = Math.min(5, times.length);
    const labels = Array.from({ length: ticks }, (_, index) => {
      const position = Math.round(index / (ticks - 1) * (times.length - 1));
      return `<span>${esc(fmt(times[position]))}</span>`;
    }).join('');
    // A short series labelled only with clock times hides which day it is, so the
    // date is stated once alongside.
    const dayNote = spanHours <= 36
      ? `<em>${esc(new Date(first).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }))}${
          new Date(first).toDateString() === new Date(last).toDateString()
            ? ''
            : ` – ${esc(new Date(last).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }))}`}</em>`
      : '';
    return `<div class="ph-chart-axis" aria-label="${esc(ariaLabel)}">${labels}</div>${dayNote ? `<div class="ph-chart-axis-note">${dayNote}</div>` : ''}`;
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
    return `<svg class="ph-sparkline ${positive ? 'positive' : 'negative'}" viewBox="0 0 100 40" preserveAspectRatio="none" role="img" aria-label="Net liquidation history"><defs><linearGradient id="ph-nav-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="currentColor" stop-opacity=".24"/><stop offset="100%" stop-color="currentColor" stop-opacity="0"/></linearGradient></defs><polygon points="0,40 ${points} 100,40" fill="url(#ph-nav-fill)"/><polyline points="${points}" fill="none" vector-effect="non-scaling-stroke"/>${benchPoints ? `<polyline class="ph-benchmark" points="${benchPoints}" fill="none" vector-effect="non-scaling-stroke"/>` : ''}</svg>${timeAxis(rows.map((row) => row.asOf), 'Account value time axis')}`;
  }

  function describeAge(seconds) {
    if (seconds == null) return 'an unknown time';
    if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
    if (seconds < 172_800) return `${Math.round(seconds / 3600)} h`;
    return `${Math.round(seconds / 86_400)} days`;
  }

  function accountCockpit(book) {
    const values = valueMap(book);
    const nav = num(values.NetLiquidation); const daily = num(values.DailyPnL || values.DailyPnl);
    const maintenance = num(values.MaintMarginReq); const excess = num(values.ExcessLiquidity);
    const cushion = num(values.Cushion); const marginLoad = nav > 0 && maintenance != null ? Math.max(0, Math.min(1, maintenance / nav)) : null;
    // A stopped feed must not read the same as a live one. The collector was
    // disabled on 2026-08-25, so "complete" now means "this snapshot was whole
    // when it was taken", which can be days ago.
    const stale = book?.snapshot?.stale === true;
    const ageSeconds = num(book?.snapshot?.age_seconds);
    const dataState = book?.status !== 'complete'
      ? 'Broker feed unavailable'
      : stale ? `Broker feed stopped · last snapshot ${describeAge(ageSeconds)} ago` : 'Broker feed complete';
    return `<section class="ph-cockpit" aria-label="Account overview"><div class="ph-cockpit-value"><button type="button" class="ph-lineage-target" data-ph-lineage="Net liquidation" data-ph-source="IBKR live" data-ph-detail="Account tag NetLiquidation"><div class="ph-kicker">Net liquidation value</div><div class="ph-hero-value">${money(nav)}</div></button><div class="ph-daily ${daily < 0 ? 'ph-negative' : 'ph-positive'}"><span>${signed(daily)}</span><small>today</small></div><div class="ph-feed-state ${stale ? 'stale' : ''}"><i class="${book?.status === 'complete' && !stale ? 'live' : ''}"></i>${esc(dataState)}</div></div><div class="ph-cockpit-chart"><div class="ph-chart-head"><span>Account value</span><b>${state.accountPerformance?.nav_series?.length || 0} observations</b></div>${portfolioSparkline(state.accountPerformance?.nav_series, state.accountPerformance?.benchmark)}</div><div class="ph-cockpit-safety"><div class="ph-kicker">Liquidity runway</div><div class="ph-safety-line"><span>Excess liquidity</span><b>${money(excess, true)}</b></div><div class="ph-safety-line"><span>Margin load</span><b>${pct(marginLoad)}</b></div><div class="ph-meter"><i style="width:${marginLoad == null ? 0 : (marginLoad * 100).toFixed(1)}%"></i></div><div class="ph-safety-line"><span>Broker cushion</span><b>${cushion == null ? '—' : pct(cushion)}</b></div><div class="ph-readonly"><span>BROKER READ ONLY</span> Paper tickets never route to IBKR.</div></div></section>`;
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
    // Sorting is a cross-currency comparison, so it must use base values only.
    // Falling back to the raw field would rank a foreign row by its native
    // magnitude -- JPY 5,064,000 outranking every USD position in the book.
    // Rows with no usable rate sort to the end in either direction instead of
    // being silently mixed in at a fabricated size.
    const sortable = (row) => {
      if (state.sortKey === 'symbol') return String(row.local_symbol || row.symbol || '');
      if (BASE_FIELD[state.sortKey]) return scopedValue(row, state.sortKey);
      return num(row[state.sortKey]);
    };
    const rows = (book.positions || []).filter(filterRow).sort((left, right) => {
      const a = sortable(left);
      const b = sortable(right);
      // Unconvertible rows park at the end in both directions; they have no
      // comparable size, so any position among the sorted values would be a lie.
      if (a == null || b == null) return a == null && b == null ? 0 : a == null ? 1 : -1;
      const result = typeof a === 'string' ? a.localeCompare(b) : a - b;
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
        average_cost_decimal: `<td>${money(row.average_cost_native_decimal ?? row.average_cost_decimal, false, row.native_currency || row.currency)}</td>`,
        mark_decimal: `<td>${money(row.mark_native_decimal ?? row.mark_decimal, false, row.native_currency || row.currency)}</td>`,
        market_value_decimal: `<td>${marketValueCell(row)}</td>`,
        daily_pnl_decimal: `<td class="${scopeDaily == null ? '' : scopeDaily < 0 ? 'ph-negative' : 'ph-positive'}">${pnlCell(row, 'daily_pnl_decimal', scopeDaily)}</td>`,
        unrealized_pnl_decimal: `<td class="${(scopedValue(row, 'unrealized_pnl_decimal') ?? 0) < 0 ? 'ph-negative' : 'ph-positive'}">${pnlCell(row, 'unrealized_pnl_decimal')}</td>`,
        currency: `<td>${esc(row.currency)}</td>`,
        quality: `<td><span class="ph-pill ${row.quality === 'live' ? 'live' : ''}">${esc(row.quality)}</span></td>`,
      };
      return `<tr class="${positionKey(row) === state.selectedPositionKey ? 'ph-row-open' : ''}">${COLUMN_DEFS.filter((column) => columnVisible(column.key)).map((column) => cells[column.key]).join('')}</tr>`;
    }).join('')}</tbody></table>${rows.length ? '' : (book.allocation_status === 'upstream_absent' && book.broker_position_count > 0
      ? emptyState('upstream_absent', 'Owner allocation has not published', `${book.broker_position_count} broker positions exist, but the owner projection is absent. This is an allocation-pipeline issue, not a flat book.`, 'allocation_projection.v1', 'Publish the policy allocation projection, then refresh this page.')
      : emptyState('true_zero', 'No positions in this scope', 'Broker truth remains visible in All; strategy exclusions and other ownership are itemized in Reconciliation.', 'IBKR positions + allocation ledger', 'Open Reconciliation to review every exclusion.'))}</div>${positionDrawer(selected)}${lineageDrawer()}`;
  }

  function positionDrawer(row) {
    if (!row) return '';
    const lots = row.allocations || [];
    const related = (state.book?.positions || []).filter((candidate) => candidate.symbol === row.symbol && positionKey(candidate) !== positionKey(row));
    const orders = (state.orders?.broker_open_orders || []).filter((order) => Number(order.conid) === Number(row.conid));
    const nativeCurrency = row.native_currency || row.currency;
    const baseCurrency = row.base_currency || state.book?.snapshot?.base_currency || 'USD';
    const fx = row.fx_rate_to_base_decimal == null ? 'Not required / unavailable' : `${quantity(row.fx_rate_to_base_decimal)} ${baseCurrency} per ${nativeCurrency}`;
    return `<aside class="ph-drawer" aria-label="Position detail"><div class="ph-drawer-head"><div><div class="ph-kicker">Position detail</div><h3>${esc(row.local_symbol || row.symbol)}</h3><div class="ph-dim">${esc(row.description || '')} · conId ${row.conid}</div></div><button type="button" data-ph-close-drawer>Close</button></div><div class="ph-drawer-grid">${[['Quantity', `${quantity(row.quantity_decimal)} ${row.quantity_unit || 'shares'}`], [`Average cost · ${nativeCurrency}`, money(row.average_cost_native_decimal ?? row.average_cost_decimal, false, nativeCurrency)], [`Mark · ${nativeCurrency}`, money(row.mark_native_decimal ?? row.mark_decimal, false, nativeCurrency)], [`Market value · ${nativeCurrency}`, money(row.market_value_native_decimal, false, nativeCurrency)], [`Market value · ${baseCurrency}`, money(row.market_value_base_decimal ?? row.market_value_decimal, false, baseCurrency)], ['FX translation', fx], [`Daily P&L · ${baseCurrency}`, signed(row.daily_pnl_base_decimal ?? row.daily_pnl_decimal, baseCurrency)], [`Unrealized · ${baseCurrency}`, signed(row.unrealized_pnl_base_decimal ?? row.unrealized_pnl_decimal, baseCurrency)], ['FX source / as of', `${row.fx_source || 'Not required'} · ${row.fx_as_of || row.as_of}`], ['Quality', row.quality], ['Source', row.source], ['As of', row.as_of]].map(([k, v]) => `<div><span>${esc(k)}</span><b>${esc(v)}</b></div>`).join('')}</div><h4>Allocation lots</h4><div class="ph-table-wrap"><table class="ph-table"><thead><tr><th>Owner</th><th>Strategy</th><th>Bucket</th><th>Qty</th><th>Confidence</th></tr></thead><tbody>${lots.map((lot) => `<tr><td>${esc(lot.owner)}</td><td>${esc(lot.strategy)}</td><td>${esc(lot.bucket || '—')}</td><td>${quantity(lot.quantity_decimal)}</td><td>${esc(lot.confidence)}</td></tr>`).join('')}</tbody></table>${lots.length ? '' : '<div class="ph-empty"><div><b>Quarantined / unallocated</b>This broker quantity has no approved owner or strategy lot.</div></div>'}</div><div class="ph-drawer-links"><button type="button" data-ph-linked-symbol="${esc(row.symbol)}">Open ${esc(row.symbol)} research</button>${related.map((candidate) => `<button type="button" data-ph-open-row="${esc(positionKey(candidate))}">Linked ${esc(candidate.local_symbol || candidate.symbol)} ${candidate.sec_type}</button>`).join('')}</div>${orders.length ? `<h4>Working orders</h4><ul>${orders.map((order) => `<li>${esc(order.action)} ${quantity(order.total_quantity_decimal)} @ ${money(order.limit_price_decimal)} · ${esc(order.ownership)}</li>`).join('')}</ul>` : ''}</aside>`;
  }

  function lineageDrawer() {
    if (!state.lineage) return '';
    return `<aside class="ph-drawer ph-lineage-drawer" aria-label="Metric lineage"><div class="ph-drawer-head"><div><div class="ph-kicker">Metric lineage</div><h3>${esc(state.lineage.metric)}</h3></div><button type="button" data-ph-close-lineage>Close</button></div><div class="ph-drawer-grid"><div><span>Source</span><b>${esc(state.lineage.source)}</b></div><div><span>As of</span><b>${esc(state.lineage.as_of || '—')}</b></div><div><span>Detail</span><b>${esc(state.lineage.detail)}</b></div></div></aside>`;
  }

  function panelLines(title, lines) { return `<section class="ph-panel"><h3>${esc(title)}</h3>${lines.map(([k, v]) => `<div class="ph-line"><span>${esc(k)}</span><b>${esc(v)}</b></div>`).join('')}</section>`; }
  function emptyState(kind, title, detail, source, action) {
    return `<div class="ph-empty ph-empty--${esc(kind)}"><div><span class="ph-empty-kind">${esc(kind.replace(/_/g, ' '))}</span><b>${esc(title)}</b><p>${esc(detail)}</p>${source ? `<small>Source · ${esc(source)}</small>` : ''}${action ? `<small>Next · ${esc(action)}</small>` : ''}</div></div>`;
  }
  function sectionView(book) {
    if (state.section === 'positions') return positionsView(book);
    if (state.section === 'margin') return marginView(book);
    const values = valueMap(book);
    if (state.section === 'margin') return `<div class="ph-grid">${panelLines('Broker-reported account margin', [['Initial requirement', money(values.InitMarginReq)], ['Maintenance requirement', money(values.MaintMarginReq)], ['Available funds', money(values.AvailableFunds)], ['Excess liquidity', money(values.ExcessLiquidity)], ['Cushion', values.Cushion || '—'], ['SMA', money(values.SMA)]])}${panelLines('Selected scope', [['Attribution', 'Model estimates only'], ['Broker margin allocation', 'Not additive'], ['Incremental margin', 'IBKR what-if when previewed']])}${panelLines('History & lineage', [['Observations', String(state.margin?.rows?.length || 0)], ['Value kind', state.margin?.value_kind || 'broker_reported'], ['Source', 'IBKR account summary']])}</div>${lineageDrawer()}`;
    if (state.section === 'risk') return riskView(book);
    if (state.section === 'performance') return performanceView();
    if (state.section === 'orders') return ordersView();
    return reconciliationView(book);
  }

  function marginView(book) {
    const values = valueMap(book);
    const byTime = new Map();
    for (const row of state.margin?.rows || []) {
      const record = byTime.get(row.as_of) || { as_of: row.as_of };
      record[row.tag] = num(row.value_decimal);
      byTime.set(row.as_of, record);
    }
    const history = [...byTime.values()].sort((a, b) => String(a.as_of).localeCompare(String(b.as_of)));
    const latest = history.at(-1) || {};
    const prior = history.at(-2) || {};
    const peak = history.reduce((best, row) => (num(row.MaintMarginReq) || 0) > (num(best.MaintMarginReq) || 0) ? row : best, {});
    const maxValue = Math.max(1, ...history.flatMap((row) => [num(row.MaintMarginReq) || 0, num(row.ExcessLiquidity) || 0]));
    const points = (key) => history.length < 2 ? '' : history.map((row, index) => `${(index / (history.length - 1) * 100).toFixed(2)},${(42 - ((num(row[key]) || 0) / maxValue * 36)).toFixed(2)}`).join(' ');
    const change = (key) => (num(latest[key]) != null && num(prior[key]) != null) ? num(latest[key]) - num(prior[key]) : null;
    const chart = history.length > 1 ? `<svg class="ph-margin-chart" viewBox="0 0 100 46" preserveAspectRatio="none" role="img" aria-label="Maintenance margin and excess liquidity history"><polyline class="margin" points="${points('MaintMarginReq')}"/><polyline class="liquidity" points="${points('ExcessLiquidity')}"/></svg>${timeAxis(history.map((row) => row.as_of), 'Margin history time axis')}<div class="ph-chart-legend"><span class="margin">Maintenance margin</span><span class="liquidity">Excess liquidity</span></div>` : emptyState('upstream_absent', 'Margin history needs another observation', 'Current broker facts are available; a time series begins after the next complete snapshot.', 'IBKR account summary', 'Keep the collector running through the session.');
    return `<div class="ph-grid">${panelLines('Broker-reported margin now', [['Initial requirement · USD', money(values.InitMarginReq)], ['Maintenance requirement · USD', money(values.MaintMarginReq)], ['Available funds · USD', money(values.AvailableFunds)], ['Excess liquidity · USD', money(values.ExcessLiquidity)], ['Cushion · %', values.Cushion == null ? 'Unavailable' : pct(values.Cushion)]])}${panelLines('Intraday consumption', [['Peak maintenance · USD', money(peak.MaintMarginReq)], ['Peak time', peak.as_of || 'Awaiting history'], ['Maintenance change', signed(change('MaintMarginReq'))], ['Liquidity change', signed(change('ExcessLiquidity'))]])}${panelLines('Risk boundary', [['Selected owner', state.scope], ['Owner margin', 'Not additive · suppressed'], ['Order shock', 'IBKR what-if required'], ['Value kind', state.margin?.value_kind || 'broker_reported']])}</div><section class="ph-panel ph-chart-panel"><div class="ph-chart-head"><span>Account margin and liquidity · USD</span><b>${history.length} observations</b></div>${chart}</section>${lineageDrawer()}`;
  }

  /**
   * Exposure is a sum in one currency, so a position that cannot be stated in
   * that currency is left out of it. Saying so on the panel is the difference
   * between a total that is honestly incomplete and one that just reads low.
   */
  function untranslatedNote() {
    const count = state.risk?.coverage?.untranslated_positions ?? 0;
    if (!count) return 'None';
    const currencies = (state.risk?.coverage?.untranslated_currencies || []).join(', ');
    return `${count} position${count === 1 ? '' : 's'}${currencies ? ` · ${currencies}` : ''}`;
  }

  function riskView(book) {
    const factors = state.risk?.factors || [];
    const concentration = state.risk?.concentration || [];
    const scenarios = state.risk?.scenarios || [];
    const scenarioSurface = scenarios.length ? `<div class="ph-table-wrap"><table class="ph-table ph-table--scenario"><thead><tr><th>Strategy</th><th>Scenario</th><th>Shock</th><th>Horizon</th><th>P&amp;L · USD</th><th>P&amp;L · % NAV</th><th>Margin Δ · USD</th><th>Post-shock liquidity · USD</th><th>Top contributor</th></tr></thead><tbody>${scenarios.map((row) => `<tr><td>${esc(row.strategy)}</td><td>${esc(row.scenario)}</td><td>${row.shock_value == null ? 'Unavailable' : `${(row.shock_value * 100).toFixed(1)}%`}</td><td>${esc(row.horizon)}</td><td>${signed(row.pnl_usd)}</td><td>${row.pnl_pct_nav == null ? 'Unavailable' : `${(row.pnl_pct_nav * 100).toFixed(2)}%`}</td><td>${row.margin_delta_usd == null ? 'Not modeled' : signed(row.margin_delta_usd)}</td><td>${row.post_shock_excess_liquidity_usd == null ? 'Not modeled' : money(row.post_shock_excess_liquidity_usd)}</td><td>${esc(row.top_contributor || 'Unavailable')}</td></tr>`).join('')}</tbody></table></div>` : emptyState(state.scope === 'all' ? 'upstream_absent' : 'suppressed_by_methodology', 'No valid scenario surface for this scope', state.risk?.nonlinear?.null_reason || 'A producer must publish shock vectors and coverage before scenario P&L can be shown.', 'strategy scenario producers', state.scope === 'all' ? 'Publish scenario_surface.v1 with model version and coverage.' : 'Use All or the strategy page; owner nonlinear risk is never pro-rated.');
    return `<div class="ph-grid">${panelLines('Concentration', [['Gross exposure · USD', money(state.risk?.gross_exposure, true)], ['Net exposure · USD', money(state.risk?.net_exposure, true)], ['Largest gross weight', concentration[0]?.gross_weight == null ? 'Unavailable' : `${(concentration[0].gross_weight * 100).toFixed(1)}%`], ['Excluded · no FX rate', untranslatedNote()]])}${panelLines('Linear sensitivities', [['Beta exposure · USD', money(state.risk?.linear_sensitivities?.beta_exposure, true)], ['Delta exposure · USD', money(state.risk?.linear_sensitivities?.delta_exposure, true)], ['Gamma / vega', `${state.risk?.linear_sensitivities?.gamma ?? 'Unavailable'} / ${state.risk?.linear_sensitivities?.vega ?? 'Unavailable'}`]])}${panelLines('Shock coverage', [['Market slide', state.risk?.shock_coverage?.market_slide || 'unavailable'], ['Margin shock', state.risk?.shock_coverage?.margin || 'unavailable'], ['Correlation lift', state.risk?.shock_coverage?.correlation || 'unavailable'], ['Linked producer rows', `${state.risk?.coverage?.linked_atomic_rows ?? 0} / ${state.risk?.coverage?.producer_atomic_rows ?? 0}`]])}</div><section class="ph-panel ph-section-block"><h3>Top position concentration</h3><p>Rows are positions. Quantity retains its native unit; weights are percent of gross exposure and market value is signed USD.</p><div class="ph-table-wrap"><table class="ph-table ph-table--compact"><thead><tr><th>Position</th><th>Quantity</th><th>Unit</th><th>Gross weight · %</th><th>Signed market value · USD</th></tr></thead><tbody>${concentration.map((row) => `<tr><td><button type="button" class="ph-symbol-link" data-ph-linked-symbol="${esc(row.symbol)}">${esc(row.symbol)}</button></td><td>${quantity(row.quantity)}</td><td>${esc(row.quantity_unit)}</td><td>${row.gross_weight == null ? 'Unavailable' : `${(row.gross_weight * 100).toFixed(1)}%`}</td><td>${signed(row.market_value)}</td></tr>`).join('')}</tbody></table>${concentration.length ? '' : emptyState('true_zero', 'No concentration rows', 'This scope has no positions with market value.', 'IBKR positions', 'Select another owner or wait for the next complete snapshot.')}</div></section><section class="ph-panel ph-section-block"><h3>Published scenario surface</h3><p>Only producer-owned account or strategy models appear here. Missing margin and correlation values stay explicit.</p>${scenarioSurface}</section><section class="ph-panel ph-section-block"><h3>Factor drill-down</h3><div class="ph-table-wrap"><table class="ph-table ph-table--wide"><thead><tr><th>Row</th><th>Symbol</th><th>Role</th><th>Basis</th><th>Beta · USD</th><th>Delta · USD</th></tr></thead><tbody>${factors.map((row) => `<tr><td>${esc(row.row_id)}</td><td><button type="button" class="ph-symbol-link" data-ph-linked-symbol="${esc(row.symbol || '')}">${esc(row.symbol || 'Unavailable')}</button></td><td>${esc(row.reconciliation_role)}</td><td>${esc(row.exposure_basis)}</td><td>${row.beta_exposure == null ? 'Unavailable' : money(row.beta_exposure)}</td><td>${row.delta_exposure == null ? 'Unavailable' : money(row.delta_exposure)}</td></tr>`).join('')}</tbody></table>${factors.length ? '' : emptyState('suppressed_by_methodology', 'No factor rows at this scope', 'Producer atomic rows remain unpublished instead of being pro-rated.', 'strategy_snapshot.v1', 'Open All or the source strategy.')}</div></section>${lineageDrawer()}`;
    return `<div class="ph-grid">${panelLines('Concentration', [['Gross exposure', money(state.risk?.gross_exposure, true)], ['Net exposure', money(state.risk?.net_exposure, true)], ['Largest weight', state.risk?.concentration?.[0]?.gross_weight == null ? '—' : `${(state.risk.concentration[0].gross_weight * 100).toFixed(1)}%`]])}${panelLines('Linear sensitivities', [['Beta exposure', money(state.risk?.linear_sensitivities?.beta_exposure, true)], ['Delta exposure', money(state.risk?.linear_sensitivities?.delta_exposure, true)], ['Gamma / vega', `${state.risk?.linear_sensitivities?.gamma ?? '—'} / ${state.risk?.linear_sensitivities?.vega ?? '—'}`]])}${panelLines('Coverage & nonlinear gates', [['Broker positions', String(state.risk?.coverage?.broker_positions ?? book.positions?.length ?? 0)], ['Linked producer rows', `${state.risk?.coverage?.linked_atomic_rows ?? 0} / ${state.risk?.coverage?.producer_atomic_rows ?? 0}`], ['Scenario risk', state.risk?.nonlinear?.value == null ? 'Suppressed — unsupported scope' : String(state.risk.nonlinear.value)], ['Open breaks', String(book.reconciliation_breaks?.length || 0)]])}</div><div class="ph-split"><section class="ph-panel"><h3>Factor drill-down</h3><div class="ph-table-wrap"><table class="ph-table"><thead><tr><th>Row</th><th>Symbol</th><th>Role</th><th>Basis</th><th>Beta</th><th>Delta</th></tr></thead><tbody>${factors.map((row) => `<tr><td>${esc(row.row_id)}</td><td><button type="button" class="ph-symbol-link" data-ph-linked-symbol="${esc(row.symbol || '')}">${esc(row.symbol || '—')}</button></td><td>${esc(row.reconciliation_role)}</td><td>${esc(row.exposure_basis)}</td><td>${esc(row.beta_exposure ?? '—')}</td><td>${esc(row.delta_exposure ?? '—')}</td></tr>`).join('')}</tbody></table>${factors.length ? '' : '<div class="ph-empty"><div><b>No factor rows at this scope</b>Producer atomic rows stay unpublished rather than being pro-rated.</div></div>'}</div></section><section class="ph-panel"><h3>Scenario drill-down</h3><p>${esc(state.risk?.nonlinear?.null_reason || 'Scenario vectors have not been published.')}</p><div class="ph-table-wrap"><table class="ph-table"><thead><tr><th>Symbol</th><th>Weight</th><th>Market value</th></tr></thead><tbody>${concentration.map((row) => `<tr><td><button type="button" class="ph-symbol-link" data-ph-linked-symbol="${esc(row.symbol)}">${esc(row.symbol)}</button></td><td>${row.gross_weight == null ? '—' : `${(row.gross_weight * 100).toFixed(1)}%`}</td><td>${money(row.market_value, true)}</td></tr>`).join('')}</tbody></table></div></section></div>${lineageDrawer()}`;
  }

  function performanceView() {
    const rolling = state.performance?.rolling || [];
    const navFrom = state.performance?.nav_first_at;
    const navTo = state.performance?.nav_last_at;
    const navDays = state.performance?.nav_daily_observations ?? 0;
    const rollingRows = rolling.map((row) => {
      if (!row.available) {
        // The reason occupies the row rather than leaving four blank cells, so a
        // window that cannot be computed says when it will be.
        return `<tr class="ph-window-pending"><td>${esc(row.label)}</td><td colspan="5">${esc(row.null_reason || 'Not available')}</td></tr>`;
      }
      return `<tr><td>${esc(row.label)}</td><td>${pct(row.nav_cagr)}</td><td>${row.volatility == null ? 'Unavailable' : pct(row.volatility)}</td><td>${row.max_drawdown == null ? 'Unavailable' : pct(row.max_drawdown)}</td><td>${row.calmar == null ? 'No drawdown' : row.calmar.toFixed(2)}</td><td class="ph-dim">${esc(row.from)} → ${esc(row.to)}</td></tr>`;
    }).join('');
    return `<div class="ph-grid">${panelLines('Live P&L', [['Daily', 'IBKR reset-series'], ['Unrealized', 'Broker-reported'], ['Realized', 'Execution/Flex reconcile']])}${panelLines('Completed sessions', [['Flex versions', String(state.performance?.completed_sessions?.length || 0)], ['Session P&L', 'Immutable Flex lineage'], ['Restatements', 'Separate series'], ['Legacy pnl_today', 'Never used as daily']])}${panelLines('NAV history', [['Daily observations', String(navDays)], ['First', navFrom || 'None'], ['Last', navTo || 'None'], ['Max drawdown · all history', state.performance?.max_drawdown == null ? 'Unavailable' : pct(state.performance.max_drawdown)]])}</div>
      <section class="ph-panel ph-section-block"><h3>Rolling performance</h3>
        <p>NAV growth, not investor return: NetLiquidation moves with deposits and withdrawals as well as with P&amp;L, and is not cash-flow adjusted. Volatility is annualised from daily closes; Calmar is CAGR over the worst drawdown in the window.</p>
        <div class="ph-table-wrap"><table class="ph-table ph-table--compact"><thead><tr><th>Window</th><th>NAV CAGR</th><th>Volatility · ann.</th><th>Max drawdown</th><th>Calmar</th><th>Period</th></tr></thead><tbody>${rollingRows}</tbody></table></div>
      </section>
      <section class="ph-panel ph-chart-panel"><div class="ph-chart-head"><span>Net liquidation value</span><button type="button" class="ph-density" data-ph-lineage="NAV history" data-ph-source="IBKR NetLiquidation" data-ph-detail="${esc(state.performance?.lineage?.rolling?.note || 'Broker-reported NAV')}">Lineage</button></div>${portfolioSparkline(state.performance?.nav_series)}</section>${lineageDrawer()}`;
  }

  // ---------------------------------------------------------------------------
  // Guarded order ticket
  //
  // Draft -> Preview -> Approve -> Submit, mirroring GuardedOrderService. The
  // browser only ever *requests* and *approves*: the private hub prices the
  // order against the live book, holds the approval secret, and is the only
  // thing that can transmit. Every state below is one the hub published, so the
  // desk never claims progress the hub has not actually made.
  const TICKET_STEPS = ['requested', 'previewed', 'approved', 'acknowledged'];
  const OPEN_TICKET_STATES = new Set(['requested', 'drafting', 'previewed', 'approved', 'submitting']);
  const TERMINAL_TICKET_STATES = new Set(['filled', 'cancelled', 'rejected', 'expired']);

  const activeRequest = () => (state.orderRequests?.requests || [])
    .find((row) => row.request_id === state.activeRequestId)
    || (state.orderRequests?.requests || []).find((row) => OPEN_TICKET_STATES.has(row.state));

  function ticketStepIndex(ticketState) {
    if (ticketState === 'drafting') return 0;
    if (ticketState === 'submitting') return 2;
    if (ticketState === 'filled') return 3;
    const index = TICKET_STEPS.indexOf(ticketState);
    return index < 0 ? 0 : index;
  }

  function ticketStepper(ticketState) {
    const current = ticketStepIndex(ticketState);
    const failed = TERMINAL_TICKET_STATES.has(ticketState) && ticketState !== 'filled';
    return `<ol class="ph-ticket-steps" aria-label="Order progress">${TICKET_STEPS.map((label, index) => {
      let cls = index < current ? 'done' : index === current ? 'current' : '';
      if (failed && index === current) cls = 'failed';
      return `<li class="${cls}"><span>${index + 1}</span>${esc(label === 'acknowledged' ? 'submitted' : label)}</li>`;
    }).join('')}</ol>`;
  }

  function approvalCountdown(row) {
    if (!row.approval_expires_at) return '';
    const remaining = Math.max(0, Math.round((new Date(row.approval_expires_at) - Date.now()) / 1000));
    const urgent = remaining <= 30;
    return `<span class="ph-ticket-clock ${urgent ? 'urgent' : ''}" data-ph-countdown="${esc(row.approval_expires_at)}">${
      remaining === 0 ? 'expired' : `${remaining}s to approve`}</span>`;
  }

  function previewFacts(row) {
    let preview = {};
    try { preview = row.preview_json ? JSON.parse(row.preview_json) : {}; } catch (_) { preview = {}; }
    const quote = preview.quote || {};
    const whatIf = preview.what_if || {};
    const currency = row.currency || 'USD';
    const rows = [
      ['Bid / ask', quote.bid == null ? '—' : `${money(quote.bid, false, currency)} / ${money(quote.ask, false, currency)}`],
      ['Your limit', money(row.limit_price_decimal, false, currency)],
      ['Notional', preview.notional == null ? '—' : money(preview.notional, false, currency)],
      ['Initial margin', whatIf.initial_margin_change ? money(whatIf.initial_margin_change) : '—'],
      ['Maintenance margin', whatIf.maintenance_margin_change ? money(whatIf.maintenance_margin_change) : '—'],
      ['Commission', whatIf.commission ? money(whatIf.commission) : '—'],
    ];
    return `<dl class="ph-ticket-facts">${rows.map(([k, v]) =>
      `<div><dt>${esc(k)}</dt><dd>${v}</dd></div>`).join('')}</dl>`;
  }

  // The hub names its own refusals; translate them rather than showing a code.
  const REJECT_REASONS = {
    stale_quote: 'The quote went stale before the hub could price it. Request again.',
    invalid_nbbo: 'The book had no two-sided market for this contract.',
    price_band: 'Your limit sits too far from the midpoint.',
    invalid_market_tick: 'That price is not a whole multiple of the contract tick.',
    reduce_only_violation: 'This would open or extend a position rather than reduce it.',
    notional_limit: 'The order exceeds the notional cap for a single ticket.',
    kill_switch_engaged: 'The hub kill switch is engaged. No new orders are being accepted.',
    live_interlock_disabled: 'Live transmission is disabled on the hub.',
  };
  const rejectText = (row) => REJECT_REASONS[row.reject_reason] || row.reject_reason || 'The hub refused this ticket.';

  function ticketBody(row) {
    switch (row.state) {
      case 'requested':
      case 'drafting':
        return `<p class="ph-ticket-wait">Waiting for the private hub to pick this up and price it against the live
          book. Nothing has been sent to a broker.</p>
          <p class="ph-dim">If this sits here, the hub is not running: it polls this queue, the queue cannot call it.</p>`;
      case 'previewed':
        return `${previewFacts(row)}
          <div class="ph-ticket-approve">
            <div class="ph-ticket-fingerprint"><span>Contract</span><code>${esc(row.contract_fingerprint || '—')}</code></div>
            <label class="ph-order-confirm"><input type="checkbox" data-ph-approve-confirm>
              <span>I have checked this contract and price.</span></label>
            <button type="button" class="ph-order-submit" data-ph-approve="${esc(row.request_id)}" disabled>
              Approve paper order</button>
          </div>`;
      case 'approved':
      case 'submitting':
        return `<p class="ph-ticket-wait">Approved. The hub is re-verifying its own token and submitting.</p>`;
      case 'acknowledged':
        return `<p class="ph-ticket-ok">The broker has the order.${row.order_ref
          ? ` <span class="ph-dim">${esc(row.order_ref)}</span>` : ''}</p>${previewFacts(row)}`;
      case 'filled':
        return `<p class="ph-ticket-ok">Filled.</p>${previewFacts(row)}`;
      case 'rejected':
        return `<p class="ph-ticket-bad">${esc(rejectText(row))}</p>`;
      case 'expired':
        return `<p class="ph-ticket-bad">The approval window closed. Request it again for a fresh quote.</p>`;
      case 'cancelled':
        return `<p class="ph-ticket-bad">Cancelled.</p>`;
      default:
        return `<p class="ph-dim">State: ${esc(row.state)}</p>`;
    }
  }

  function guardedTicket(row) {
    if (!row) return '';
    const currency = row.currency || 'USD';
    return `<section class="ph-ticket" aria-label="Order ticket">
      <header class="ph-ticket-head">
        <div>
          <span class="ph-paper-stamp">PAPER · NEVER TRANSMITTED</span>
          <h3>${esc(row.action)} ${quantity(row.quantity_decimal)} ${esc(row.symbol)}
            <span class="ph-dim">@ ${money(row.limit_price_decimal, false, currency)} ${esc(row.tif || 'DAY')}</span></h3>
        </div>
        ${row.state === 'previewed' ? approvalCountdown(row) : ''}
      </header>
      ${ticketStepper(row.state)}
      ${ticketBody(row)}
      <footer class="ph-ticket-foot">
        <button type="button" class="ph-order-cancel" data-ph-dismiss-ticket>${
          OPEN_TICKET_STATES.has(row.state) ? 'Work a different ticket' : 'Close'}</button>
        <span class="ph-dim">Requested ${esc(row.created_at || '')}</span>
      </footer>
    </section>`;
  }

  function requestHistory() {
    const rows = (state.orderRequests?.requests || []).slice(0, 12);
    if (!rows.length) return '';
    return `<details class="ph-order-audit"><summary>Ticket history · ${rows.length}</summary>
      <div class="ph-table-wrap"><table class="ph-table"><thead><tr><th>Created</th><th>Instrument</th>
      <th>Side</th><th>Qty</th><th>Limit</th><th>Mode</th><th>State</th></tr></thead><tbody>${rows.map((row) => `<tr>
        <td>${esc(row.created_at)}</td>
        <td><button type="button" class="ph-symbol-link" data-ph-open-ticket="${esc(row.request_id)}">${esc(row.symbol)}</button>
          <br><span class="ph-dim">${esc(row.sec_type)} · ${esc(row.conid)}</span></td>
        <td>${esc(row.action)}</td><td>${quantity(row.quantity_decimal)}</td>
        <td>${money(row.limit_price_decimal, false, row.currency || 'USD')}</td>
        <td>${esc(row.mode)}</td>
        <td><span class="ph-pill ${row.state === 'filled' ? 'live' : row.state === 'rejected' ? '' : 'paper'}">${esc(row.state)}</span></td>
      </tr>`).join('')}</tbody></table></div></details>`;
  }

  async function refreshOrderRequests() {
    try {
      state.orderRequests = await getJson('/api/v2/portfolio/order-intents');
    } catch (error) {
      state.orderRequests = { error: error.message, requests: [], viewer: {} };
    }
  }

  function stopTicketPolling() {
    if (state.orderPollTimer) { clearInterval(state.orderPollTimer); state.orderPollTimer = null; }
  }

  /**
   * Poll while a ticket is open.
   *
   * The hub enforces a 10s quote-freshness rule and a 120s approval window, so a
   * preview cannot be waited on lazily -- by the time a slow poll noticed it,
   * the window would be gone. One second while a ticket is live, nothing at all
   * when the desk is idle.
   */
  function startTicketPolling() {
    stopTicketPolling();
    state.orderPollTimer = setInterval(async () => {
      const before = activeRequest()?.state;
      await refreshOrderRequests();
      const row = activeRequest();
      if (!row || !OPEN_TICKET_STATES.has(row.state)) stopTicketPolling();
      if (state.section === 'orders' && (row?.state !== before || !row)) renderPortfolio();
      else if (row?.state === 'previewed') tickCountdown();
    }, 1000);
  }

  // Repaint only the clock between renders, so the countdown stays honest
  // without re-rendering the ticket underneath the user's cursor.
  function tickCountdown() {
    document.querySelectorAll('[data-ph-countdown]').forEach((node) => {
      const remaining = Math.max(0, Math.round((new Date(node.dataset.phCountdown) - Date.now()) / 1000));
      node.textContent = remaining === 0 ? 'expired' : `${remaining}s to approve`;
      node.classList.toggle('urgent', remaining <= 30);
    });
  }

  // ---------------------------------------------------------- contract picker
  //
  // A conId is a broker fact, so nothing in this file ever produces one. These
  // renderers only display conIds the hub resolved and wrote back, and the
  // submit path refuses to send a ticket whose conId did not come from there.

  function contractSuggestionList() {
    const rows = state.contractSuggestions || [];
    if (!rows.length) return '';
    return `<ul class="ph-typeahead" role="listbox">${rows.map((row) => `<li><button type="button" role="option" data-ph-pick-contract="${esc(row.conid)}">
      <b>${esc(row.local_symbol || row.symbol)}</b><span>${esc(row.sec_type)}${row.expiry ? ` · ${esc(row.expiry)}` : ''}${row.right_code ? ` ${esc(row.right_code)}${esc(row.strike_decimal || '')}` : ''} · ${esc(row.currency || '')} · conId ${esc(row.conid)}</span>
      <em>${esc(row.description || (row.source === 'position' ? 'held in this account' : 'previously resolved'))}</em>
    </button></li>`).join('')}</ul>`;
  }

  function optionChainPicker() {
    const draft = state.contractDraft;
    const chain = state.contractChain;
    const lookup = state.contractLookup;
    if (!chain) {
      const busy = lookup && ['requested', 'resolving'].includes(lookup.state);
      return `<div class="ph-order-field ph-order-chain"><span>Option chain</span>
        <button type="button" class="ph-chain-load" data-ph-load-chain ${busy || !draft.symbol ? 'disabled' : ''}>
          ${busy ? 'Asking the hub…' : draft.symbol ? `Load ${esc(draft.symbol)} chain` : 'Enter a symbol first'}</button>
        ${lookup?.state === 'failed' ? `<p class="ph-order-status error">${esc(lookup.error || 'The hub could not resolve that symbol.')}</p>` : ''}
        <p class="ph-dim">Expirations and strikes come from IBKR through the private hub. The browser never contacts the broker.</p>
      </div>`;
    }
    const expiries = [...new Set(chain.map((row) => row.expiry))].sort();
    const chosenExpiry = draft.expiry && expiries.includes(draft.expiry) ? draft.expiry : '';
    const strikes = chosenExpiry
      ? [...new Set(chain.filter((row) => row.expiry === chosenExpiry).flatMap((row) => row.strikes || []))].sort((a, b) => a - b)
      : [];
    return `<div class="ph-order-field ph-order-chain"><span>Expiry</span>
        <select data-ph-expiry><option value="">Choose an expiry</option>${expiries.map((value) => `<option value="${esc(value)}"${value === chosenExpiry ? ' selected' : ''}>${esc(formatExpiry(value))}</option>`).join('')}</select>
      </div>
      <div class="ph-order-field"><span>Right</span>
        <select data-ph-right><option value="P"${draft.right === 'P' ? ' selected' : ''}>Put</option><option value="C"${draft.right === 'C' ? ' selected' : ''}>Call</option></select>
      </div>
      <div class="ph-order-field"><span>Strike</span>
        <select data-ph-strike ${strikes.length ? '' : 'disabled'}><option value="">${strikes.length ? 'Choose a strike' : 'Choose an expiry first'}</option>${strikes.map((value) => `<option value="${value}"${String(value) === String(draft.strike) ? ' selected' : ''}>${value}</option>`).join('')}</select>
      </div>`;
  }

  function formatExpiry(value) {
    const raw = String(value || '');
    if (!/^\d{8}$/.test(raw)) return raw;
    return `${raw.slice(0, 4)}-${raw.slice(4, 6)}-${raw.slice(6)}`;
  }

  function resolvedContractCell() {
    const draft = state.contractDraft;
    const lookup = state.contractLookup;
    if (draft.conid && draft.identity) {
      const row = draft.identity;
      return `<div class="ph-resolved ok"><b>${esc(row.local_symbol || row.symbol)}</b>
        <span>${esc(row.sec_type)}${row.expiry ? ` · ${esc(formatExpiry(row.expiry))}` : ''}${row.right_code ? ` · ${esc(row.right_code)} ${esc(row.strike_decimal || '')}` : ''}${row.multiplier_decimal ? ` · ${esc(row.multiplier_decimal)}x` : ''}</span>
        <span class="ph-dim">conId ${esc(row.conid)} · ${esc(row.exchange || 'SMART')}/${esc(row.currency || '')}</span>
        <button type="button" class="ph-order-cancel" data-ph-clear-contract>Change contract</button></div>`;
    }
    if (lookup && ['requested', 'resolving'].includes(lookup.state)) {
      return '<div class="ph-resolved"><span>Waiting on the hub to resolve this contract…</span></div>';
    }
    if (lookup?.state === 'failed') {
      return `<div class="ph-resolved error"><span>${esc(lookup.error || 'The hub could not resolve that contract.')}</span></div>`;
    }
    // Never offer a free-text conId box as a fallback. The whole point of this
    // panel is that the identity on the ticket came from IBKR; a manual escape
    // hatch would be used exactly when resolution failed, which is exactly when
    // the number is least likely to be right.
    return '<div class="ph-resolved"><span class="ph-dim">Pick a contract above. Order entry stays closed until the hub resolves one.</span></div>';
  }

  function ordersView() {
    const draft = state.contractDraft;
    const events = state.orders?.events || [];
    const broker = state.orders?.broker_open_orders || [];
    const paper = state.paperOrders?.orders || [];
    const viewer = state.paperOrders?.viewer || {};
    const orderOwner = viewer.order_owner || null;
    const ownerLabel = orderOwner ? orderOwner[0].toUpperCase() + orderOwner.slice(1) : 'Unassigned';
    const canEnter = Boolean(orderOwner && state.scope === orderOwner && !state.paperOrders?.error);
    const positionOptions = (state.book?.positions || [])
      .filter((row, index, rows) => rows.findIndex((candidate) => Number(candidate.conid) === Number(row.conid)) === index)
      .map((row) => `<option value="${esc(row.conid)}" data-symbol="${esc(row.symbol)}" data-sec-type="${esc(row.sec_type)}">${esc(row.local_symbol || row.symbol)} · ${esc(row.sec_type)} · conId ${esc(row.conid)}</option>`)
      .join('');
    const lockMessage = state.paperOrders?.error
      ? state.paperOrders.error
      : !orderOwner
        // Name the verified email. Without it the operator has to guess which
        // address Access actually asserted, and a guess lands in one of two bad
        // places: an alias that never matches (stays silently read-only), or a
        // second variant added "to be safe" that collides with the other owner
        // map and hard-errors. The address is already in the payload.
        ? `This Access login (${esc(viewer.email || 'email not returned')}) has no paper-order role. Add exactly this address to exactly one owner map — PORTFOLIO_DREW_ACCESS_EMAILS or PORTFOLIO_MICHAEL_ACCESS_EMAILS, never both — then redeploy.`
        : state.scope === 'all'
          ? `Choose the ${ownerLabel} portfolio to open your owner-locked paper ticket.`
          : `Signed in for ${ownerLabel}. Order entry cannot be opened on the ${state.scope[0].toUpperCase() + state.scope.slice(1)} portfolio.`;
    const ticket = canEnter ? `
      <section class="ph-order-desk" aria-labelledby="ph-paper-order-title">
        <div class="ph-order-custody">
          <span class="ph-paper-stamp">PAPER · NEVER TRANSMITTED</span>
          <strong>${esc(ownerLabel)} portfolio</strong>
          <span>${esc(viewer.email || 'Access login verified')}</span>
        </div>
        <div class="ph-order-desk-body">
          <div class="ph-order-intro"><div><div class="ph-kicker">Owner-locked order entry</div><h3 id="ph-paper-order-title">Queue a paper limit</h3></div><p>The login fixes the owner. This ticket is stored only in the paper ledger and has no broker route.</p></div>
          <form class="ph-order-form" data-ph-paper-order>
            <label class="ph-order-field ph-order-shortcut"><span>Existing contract shortcut</span><select data-ph-contract-shortcut><option value="">Search for a contract instead</option>${positionOptions}</select></label>
            <label class="ph-order-field"><span>Security type</span><select name="sec_type" required data-ph-sec-type>${[['STK', 'Stock / ETF'], ['OPT', 'Option']].map(([value, label]) => `<option value="${value}"${draft.sec_type === value ? ' selected' : ''}>${label}</option>`).join('')}</select></label>
            <label class="ph-order-field ph-order-symbol"><span>Symbol</span><input name="symbol" maxlength="24" autocomplete="off" spellcheck="false" required placeholder="MSFT" value="${esc(draft.symbol || '')}" data-ph-symbol>${contractSuggestionList()}</label>
            ${draft.sec_type === 'OPT' ? optionChainPicker() : ''}
            <div class="ph-order-field ph-order-resolved"><span>Contract</span>${resolvedContractCell()}</div>
            <input type="hidden" name="conid" value="${esc(draft.conid == null ? '' : String(draft.conid))}">
            <label class="ph-order-field"><span>Side</span><select name="side" required><option value="BUY">Buy</option><option value="SELL">Sell</option></select></label>
            <label class="ph-order-field"><span>Quantity</span><input name="quantity" inputmode="decimal" type="number" min="0.000001" step="any" required placeholder="10"></label>
            <label class="ph-order-field"><span>DAY limit price · USD</span><input name="limit_price" inputmode="decimal" type="number" min="0.000001" step="any" required placeholder="415.25"></label>
            <label class="ph-order-field ph-order-rationale"><span>Decision note <small>optional</small></span><textarea name="rationale" maxlength="500" rows="3" placeholder="Why this paper order belongs in the portfolio"></textarea></label>
            <aside class="ph-order-review" aria-label="Paper order review">
              <div class="ph-kicker">Ticket preview</div>
              <dl><div><dt>Owner</dt><dd>${esc(ownerLabel)} · locked</dd></div><div><dt>Route</dt><dd>Paper ledger only</dd></div><div><dt>Estimated notional</dt><dd data-ph-paper-notional>—</dd></div><div><dt>Current → paper position</dt><dd data-ph-paper-position>—</dd></div><div><dt>Quote / margin</dt><dd>Not modeled · queue only</dd></div></dl>
              <label class="ph-order-confirm"><input type="checkbox" name="paper_confirmed" required><span>I understand this will not place a broker order.</span></label>
              <button type="submit" class="ph-order-submit"${draft.conid ? '' : ' disabled'}>${draft.conid ? 'Request preview' : 'Resolve a contract first'}</button>
              <div class="ph-order-status" data-ph-order-status aria-live="polite"></div>
            </aside>
          </form>
        </div>
      </section>` : `
      <section class="ph-order-lock" aria-label="Paper order owner lock">
        <div class="ph-paper-stamp">PAPER ENTRY LOCKED</div><div><h3>${esc(ownerLabel)} login boundary</h3><p>${esc(lockMessage)}</p></div>
        ${orderOwner && state.scope !== orderOwner ? `<button type="button" data-ph-open-order-owner="${esc(orderOwner)}">Open ${esc(ownerLabel)} order entry</button>` : ''}
      </section>`;
    const notice = state.orderNotice ? `<div class="ph-order-notice ${state.orderNotice.type === 'error' ? 'error' : ''}" role="status">${esc(state.orderNotice.message)}</div>` : '';
    // A ticket in flight replaces the form. Two open tickets at once is how a
    // person approves the one they were not looking at.
    const working = activeRequest();
    const entry = working ? guardedTicket(working) : ticket;
    // The queue is filtered to the *logged-in* owner, so it is always Drew's
    // tickets when Drew is signed in -- including on the Michael tab, where it
    // rendered under a "Drew paper queue" heading as if Michael's book contained
    // Drew's orders. Nobody may read another owner's queue, so on a foreign tab
    // the right answer is to show nothing and say why.
    const foreignScope = Boolean(orderOwner) && state.scope !== orderOwner && state.scope !== 'all';
    const queue = foreignScope ? '' : `
      <div class="ph-toolbar"><strong>${esc(ownerLabel)} paper queue · ${paper.filter((row) => row.status === 'paper_queued').length}</strong><span class="ph-dim">Owner-filtered · audit stored in D1 · never published to the broker bridge</span></div>
      <div class="ph-table-wrap"><table class="ph-table ph-paper-table"><thead><tr><th>Created</th><th>Symbol / contract</th><th>Side</th><th>Qty</th><th>DAY limit</th><th>Notional</th><th>Status</th><th>Action</th></tr></thead><tbody>${paper.map((row) => {
        const notional = (num(row.quantity_decimal) || 0) * (num(row.limit_price_decimal) || 0);
        return `<tr><td>${esc(row.created_at)}</td><td><b>${esc(row.symbol)}</b><br><span class="ph-dim">${esc(row.sec_type)} · ${esc(row.conid)}</span></td><td>${esc(row.side)}</td><td>${quantity(row.quantity_decimal)}</td><td>${money(row.limit_price_decimal)}</td><td>${money(notional)}</td><td><span class="ph-pill ${row.status === 'paper_queued' ? 'paper' : ''}">${esc(String(row.status || '').replace('paper_', ''))}</span></td><td>${row.status === 'paper_queued' ? `<button type="button" class="ph-order-cancel" data-ph-cancel-paper="${esc(row.paper_order_id)}">Cancel paper</button>` : '—'}</td></tr>`;
      }).join('')}</tbody></table>${paper.length ? '' : '<div class="ph-order-empty"><b>No paper orders yet</b><span>Your first owner-authorized ticket will appear here.</span></div>'}</div>`;
    const scopeLabel = state.scope ? state.scope[0].toUpperCase() + state.scope.slice(1) : 'this';
    return `${entry}${notice}${requestHistory()}${queue}${foreignScope ? `
      <div class="ph-order-empty"><b>No queue shown for the ${esc(scopeLabel)} portfolio</b><span>You are signed in as ${esc(ownerLabel)}. A paper queue is only ever readable by the owner it belongs to.</span></div>` : ''}
      <details class="ph-order-audit"><summary>Broker and central order audit</summary>
        <div class="ph-alert"><strong>Live command plane remains private.</strong> Browser paper orders cannot reach Python, IB Gateway, or IBKR. Qualified live orders still require the separate guarded workflow.</div>
        <div class="ph-toolbar"><strong>Broker open orders · ${broker.length}</strong><span class="ph-dim">Foreign/manual orders are visible and never cancellable by the hub.</span></div>
        <div class="ph-table-wrap"><table class="ph-table"><thead><tr><th>Symbol</th><th>ConId</th><th>Action</th><th>Qty</th><th>Limit</th><th>Status</th><th>Ownership</th><th>Client / order / perm</th><th>Order ref</th></tr></thead><tbody>${broker.map((row) => `<tr><td><button type="button" class="ph-symbol-link" data-ph-linked-symbol="${esc(row.symbol)}">${esc(row.symbol)}</button></td><td>${esc(row.conid)}</td><td>${esc(row.action)}</td><td>${quantity(row.total_quantity_decimal)}</td><td>${money(row.limit_price_decimal)}</td><td>${esc(row.status)}</td><td><span class="ph-pill ${row.ownership === 'hub' ? 'live' : ''}">${esc(row.ownership)}</span></td><td>${esc(row.client_id)} / ${esc(row.order_id)} / ${esc(row.perm_id)}</td><td>${esc(row.order_ref || '—')}</td></tr>`).join('')}</tbody></table>${broker.length ? '' : '<div class="ph-order-empty"><b>No broker open orders</b><span>The latest complete snapshot contains no working orders.</span></div>'}</div>
        <div class="ph-toolbar"><strong>Central intent history</strong></div><div class="ph-table-wrap"><table class="ph-table"><thead><tr><th>Intent</th><th>Order ref</th><th>ConId</th><th>State</th><th>Event</th><th>Time</th></tr></thead><tbody>${events.map((row) => `<tr><td>${esc(row.intent_uuid)}</td><td>${esc(row.order_ref)}</td><td>${row.conid}</td><td>${esc(row.state)}</td><td>${esc(row.event_type)}</td><td>${esc(row.created_at)}</td></tr>`).join('')}</tbody></table>${events.length ? '' : '<div class="ph-order-empty"><b>No central order events</b><span>The private bridge has not published an audit event.</span></div>'}</div>
      </details>`;
  }

  function updatePaperOrderPreview(form) {
    if (!form) return;
    const qty = num(new FormData(form).get('quantity'));
    const price = num(new FormData(form).get('limit_price'));
    const conid = Number(new FormData(form).get('conid'));
    const side = String(new FormData(form).get('side') || 'BUY');
    const row = (state.book?.positions || []).find((candidate) => Number(candidate.conid) === conid);
    const ownerLots = (row?.allocations || []).filter((lot) => lot.owner === state.scope);
    const allocated = ownerLots.reduce((sum, lot) => sum + (num(lot.quantity_decimal) || 0), 0);
    const current = row ? (ownerLots.length ? allocated : state.scope === 'all' ? (num(row.quantity_decimal) || 0) : 0) : 0;
    const post = qty == null ? null : current + (side === 'SELL' ? -qty : qty);
    const notional = form.querySelector('[data-ph-paper-notional]');
    const position = form.querySelector('[data-ph-paper-position]');
    if (notional) notional.textContent = qty != null && price != null ? money(qty * price) : '—';
    if (position) position.textContent = qty != null ? `${quantity(current)} → ${quantity(post)}` : `${quantity(current)} → —`;
  }

  // ------------------------------------------------------- resolver behaviour

  let symbolDebounce = null;
  // The order desk re-renders by replacing innerHTML, so a suggestion list that
  // arrives while someone is still typing would take the caret with it. Same
  // problem the positions search box already solves at the bottom of
  // renderPortfolio; this is the flag that lets the symbol box do it too.
  let restoreSymbolCaret = null;

  function selectContract(identity) {
    state.contractDraft = {
      ...state.contractDraft,
      conid: Number(identity.conid),
      symbol: identity.symbol || state.contractDraft.symbol,
      sec_type: identity.sec_type || state.contractDraft.sec_type,
      identity,
    };
    state.contractSuggestions = [];
    state.contractLookup = null;
    stopLookupPolling();
    renderPortfolio();
  }

  function clearContract(keepSymbol = true) {
    state.contractDraft = {
      sec_type: state.contractDraft.sec_type,
      symbol: keepSymbol ? state.contractDraft.symbol : '',
      conid: null, identity: null,
      expiry: state.contractDraft.expiry, right: state.contractDraft.right, strike: state.contractDraft.strike,
    };
  }

  async function searchContracts(query) {
    if (!query || query.length < 1) { state.contractSuggestions = []; renderPortfolio(); return; }
    try {
      const params = new URLSearchParams({ q: query, sec_type: state.contractDraft.sec_type });
      const payload = await getJson(`/api/v2/portfolio/contracts?${params}`);
      // The cache can go stale between keystrokes; only render the answer to the
      // question still on screen.
      if (String(state.contractDraft.symbol || '').toUpperCase() !== String(payload.query || '').toUpperCase()) return;
      state.contractSuggestions = payload.contracts || [];
      restoreSymbolCaret = query.length;
      renderPortfolio();
    } catch (_) {
      // A cache miss is not an error worth interrupting typing for; the explicit
      // lookup button is still there.
      state.contractSuggestions = [];
    }
  }

  async function requestLookup(body) {
    stopLookupPolling();
    state.contractLookup = { state: 'requested' };
    renderPortfolio();
    try {
      const created = await sendJson('/api/v2/portfolio/contract-lookups', { method: 'POST', body: JSON.stringify(body) });
      pollLookup(created.lookup_id);
    } catch (error) {
      state.contractLookup = { state: 'failed', error: error.message };
      renderPortfolio();
    }
  }

  function stopLookupPolling() {
    if (state.lookupPollTimer) { clearInterval(state.lookupPollTimer); state.lookupPollTimer = null; }
  }

  function pollLookup(lookupId) {
    if (!lookupId) return;
    let elapsed = 0;
    state.lookupPollTimer = setInterval(async () => {
      elapsed += 2;
      try {
        const payload = await getJson(`/api/v2/portfolio/contract-lookups?lookup_id=${encodeURIComponent(lookupId)}`);
        const row = (payload.lookups || [])[0];
        if (!row) return;
        state.contractLookup = row;
        if (row.state === 'resolved') {
          stopLookupPolling();
          applyResolution(row);
        } else if (row.state === 'failed') {
          stopLookupPolling();
        }
        renderPortfolio();
      } catch (error) {
        stopLookupPolling();
        state.contractLookup = { state: 'failed', error: error.message };
        renderPortfolio();
      }
      // Give up out loud rather than spinning. The bridge is not running on a
      // weekend -- `ibc.service` is a session service -- and a picker that spins
      // forever reads as a bug rather than as "the Gateway is down right now".
      if (elapsed >= 40) {
        stopLookupPolling();
        state.contractLookup = { state: 'failed', error: 'The hub did not answer in 40 seconds. It may be outside session hours; held contracts still work.' };
        renderPortfolio();
      }
    }, 2000);
  }

  function applyResolution(row) {
    const matches = row.matches || [];
    if (row.kind === 'option_chain') {
      state.contractChain = matches;
      return;
    }
    // One unambiguous match is selected outright; several means the user has to
    // say which, because guessing among real contracts is how the wrong one gets
    // bought.
    if (matches.length === 1) selectContract(matches[0]);
    else state.contractSuggestions = matches;
  }

  function maybeResolveOption() {
    const draft = state.contractDraft;
    // Only ask once all three are pinned. A partial option query matches many
    // contracts, and the hub would have to pick one -- which is precisely the
    // guess this design refuses to make on a person's behalf.
    if (!draft.symbol || !draft.expiry || !draft.strike || !draft.right) { renderPortfolio(); return; }
    requestLookup({
      kind: 'option_contract', sec_type: 'OPT', symbol: draft.symbol,
      expiry: draft.expiry, strike: String(draft.strike), right: draft.right,
    });
  }

  function bindOrderDesk(root) {
    root.querySelector('[data-ph-open-order-owner]')?.addEventListener('click', (event) => {
      state.scope = event.currentTarget.dataset.phOpenOrderOwner;
      state.onRoute?.();
      loadBook();
    });
    const form = root.querySelector('[data-ph-paper-order]');
    if (form) {
      const shortcut = form.querySelector('[data-ph-contract-shortcut]');
      shortcut?.addEventListener('change', () => {
        const option = shortcut.selectedOptions?.[0];
        if (!option?.value) return;
        // A held position is already a resolved contract: the collector got its
        // conId from IBKR, so selecting one is a pick, not a manual entry.
        const held = (state.book?.positions || []).find((row) => Number(row.conid) === Number(option.value));
        selectContract({
          conid: Number(option.value),
          symbol: held?.symbol || option.dataset.symbol || '',
          local_symbol: held?.local_symbol || null,
          sec_type: held?.sec_type || option.dataset.secType || 'STK',
          currency: held?.currency || null,
          exchange: held?.exchange_name || null,
          expiry: held?.expiry || null,
          strike_decimal: held?.strike_decimal || null,
          right_code: held?.right_code || null,
          multiplier_decimal: held?.multiplier_decimal || null,
        });
      });
      form.querySelectorAll('input,select').forEach((control) => control.addEventListener('input', () => updatePaperOrderPreview(form)));
      updatePaperOrderPreview(form);

      // Symbol typing searches the cache. Changing the symbol drops any resolved
      // contract: keeping it would leave the ticket showing one instrument while
      // holding the conId of another.
      const symbolInput = form.querySelector('[data-ph-symbol]');
      if (symbolInput && restoreSymbolCaret != null) {
        const caret = restoreSymbolCaret;
        restoreSymbolCaret = null;
        symbolInput.focus();
        symbolInput.setSelectionRange(caret, caret);
      }
      symbolInput?.addEventListener('input', () => {
        const value = String(symbolInput.value || '').toUpperCase();
        if (value !== state.contractDraft.symbol) {
          state.contractDraft.symbol = value;
          if (state.contractDraft.conid) clearContract();
          state.contractChain = null;
        }
        if (symbolDebounce) clearTimeout(symbolDebounce);
        symbolDebounce = setTimeout(() => searchContracts(value), 250);
      });

      form.querySelector('[data-ph-sec-type]')?.addEventListener('change', (event) => {
        state.contractDraft = { sec_type: event.currentTarget.value, symbol: state.contractDraft.symbol, conid: null, identity: null };
        state.contractChain = null;
        state.contractSuggestions = [];
        state.contractLookup = null;
        renderPortfolio();
      });

      root.querySelectorAll('[data-ph-pick-contract]').forEach((button) => button.addEventListener('click', () => {
        const match = (state.contractSuggestions || []).find((row) => Number(row.conid) === Number(button.dataset.phPickContract));
        if (match) selectContract(match);
      }));

      root.querySelector('[data-ph-clear-contract]')?.addEventListener('click', () => {
        clearContract();
        renderPortfolio();
      });

      root.querySelector('[data-ph-load-chain]')?.addEventListener('click', () => {
        requestLookup({ kind: 'option_chain', symbol: state.contractDraft.symbol, sec_type: 'OPT' });
      });

      root.querySelector('[data-ph-expiry]')?.addEventListener('change', (event) => {
        state.contractDraft = { ...state.contractDraft, expiry: event.currentTarget.value, strike: null, conid: null, identity: null };
        renderPortfolio();
      });
      root.querySelector('[data-ph-right]')?.addEventListener('change', (event) => {
        state.contractDraft = { ...state.contractDraft, right: event.currentTarget.value, conid: null, identity: null };
        maybeResolveOption();
      });
      root.querySelector('[data-ph-strike]')?.addEventListener('change', (event) => {
        state.contractDraft = { ...state.contractDraft, strike: event.currentTarget.value, conid: null, identity: null };
        maybeResolveOption();
      });
      form.addEventListener('submit', async (event) => {
        event.preventDefault();
        if (!form.reportValidity()) return;
        const button = form.querySelector('.ph-order-submit');
        const status = form.querySelector('[data-ph-order-status]');
        const values = new FormData(form);
        button.disabled = true;
        status.className = 'ph-order-status';
        status.textContent = 'Requesting a price from the hub…';
        try {
          // Opens a guarded ticket rather than queueing a finished order: the
          // hub still has to price it, and a human still has to approve the
          // exact contract. mode is pinned to paper here -- live is not
          // something this form can ask for.
          const payload = await sendJson('/api/v2/portfolio/order-intents', {
            method: 'POST',
            body: JSON.stringify({
              symbol: values.get('symbol'),
              sec_type: values.get('sec_type'),
              // Straight from the resolved identity, never from a typed field.
              // The hub re-qualifies this conId and rebuilds the fingerprint, so
              // anything the page got wrong here surfaces as a mismatch on the
              // approval rather than as a wrong order.
              conid: Number(state.contractDraft.conid),
              action: values.get('side'),
              quantity: values.get('quantity'),
              limit_price: values.get('limit_price'),
              ...(state.contractDraft.sec_type === 'OPT' ? {
                expiry: state.contractDraft.identity?.expiry || state.contractDraft.expiry,
                strike: String(state.contractDraft.identity?.strike_decimal ?? state.contractDraft.strike ?? ''),
                right: state.contractDraft.identity?.right_code || state.contractDraft.right,
                multiplier: state.contractDraft.identity?.multiplier_decimal || null,
                trading_class: state.contractDraft.identity?.trading_class || null,
                exchange: state.contractDraft.identity?.exchange || null,
                local_symbol: state.contractDraft.identity?.local_symbol || null,
              } : {}),
              tif: 'DAY', mode: 'paper',
              strategy: 'single_stock',
              rationale: values.get('rationale'),
            }),
          });
          state.activeRequestId = payload.request_id_created;
          state.orderNotice = null;
          await refreshOrderRequests();
          renderPortfolio();
          startTicketPolling();
        } catch (error) {
          status.className = 'ph-order-status error';
          status.textContent = error.message;
          button.disabled = false;
        }
      });
    }
    // Approve is deliberately two actions: tick the contract, then press. The
    // fingerprint shown is what the hub binds its HMAC to.
    const confirmBox = root.querySelector('[data-ph-approve-confirm]');
    const approveButton = root.querySelector('[data-ph-approve]');
    confirmBox?.addEventListener('change', () => { approveButton.disabled = !confirmBox.checked; });
    approveButton?.addEventListener('click', async () => {
      const row = activeRequest();
      if (!row) return;
      approveButton.disabled = true;
      approveButton.textContent = 'Approving…';
      try {
        await sendJson(`/api/v2/portfolio/order-intents/${encodeURIComponent(row.request_id)}/approve`, {
          method: 'POST',
          body: JSON.stringify({ contract_fingerprint: row.contract_fingerprint }),
        });
        await refreshOrderRequests();
        renderPortfolio();
        startTicketPolling();
      } catch (error) {
        state.orderNotice = { type: 'error', message: error.message };
        await refreshOrderRequests();
        renderPortfolio();
      }
    });
    root.querySelector('[data-ph-dismiss-ticket]')?.addEventListener('click', () => {
      state.activeRequestId = null;
      stopTicketPolling();
      renderPortfolio();
    });
    root.querySelectorAll('[data-ph-open-ticket]').forEach((button) => button.addEventListener('click', () => {
      state.activeRequestId = button.dataset.phOpenTicket;
      renderPortfolio();
      startTicketPolling();
    }));
    root.querySelectorAll('[data-ph-cancel-paper]').forEach((button) => button.addEventListener('click', async () => {
      button.disabled = true;
      try {
        await sendJson(`/api/v2/portfolio/paper-orders/${encodeURIComponent(button.dataset.phCancelPaper)}`, { method: 'DELETE', body: '{}' });
        state.orderNotice = { type: 'success', message: 'Paper order cancelled. No broker instruction was sent.' };
        state.paperOrders = await getJson('/api/v2/portfolio/paper-orders');
        renderPortfolio();
      } catch (error) {
        state.orderNotice = { type: 'error', message: error.message };
        renderPortfolio();
      }
    }));
  }

  function reconciliationView(book) {
    const rows = book.reconciliation_breaks || [];
    const quarantined = (book.positions || []).filter((row) => !(row.allocations || []).length);
    if (state.scope !== 'all') {
      const included = new Set((book.positions || []).map(positionKey));
      const excluded = (state.allBook?.positions || []).filter((row) => !included.has(positionKey(row))).map((row) => {
        const allocations = row.allocations || [];
        const strategies = allocations.map((lot) => String(lot.strategy || '').toLowerCase());
        let reason = `Assigned to ${allocations.map((lot) => lot.owner).filter(Boolean).join(', ') || 'another scope'}`;
        if (strategies.some((strategy) => strategy.includes('spx'))) reason = 'SPX option · assigned to SPX 0DTE';
        else if (strategies.some((strategy) => strategy.includes('ls') || strategy.includes('letf') || strategy.includes('bucket'))) reason = 'LS-algo ETF / underlying universe';
        return { ...row, exclusion_reason: reason };
      });
      return `<div class="ph-alert"><strong>Owner custody is rule-driven.</strong> ${state.scope === 'michael' ? 'Michael receives every residual position except SPX options and every instrument in the LS-algo ETF/underlying universe.' : 'The table below makes every position assigned outside this owner book explicit.'}</div><div class="ph-toolbar"><strong>Included positions · ${(book.positions || []).length}</strong><span class="ph-dim">Allocation-ledger result at the current watermark</span></div><div class="ph-toolbar"><strong>Excluded / assigned elsewhere · ${excluded.length}</strong><span class="ph-dim">No silent omission</span></div><div class="ph-table-wrap"><table class="ph-table ph-table--wide"><thead><tr><th>Position</th><th>Type</th><th>Quantity</th><th>Unit</th><th>Market value · base</th><th>Rule / reason</th></tr></thead><tbody>${excluded.map((row) => `<tr><td>${esc(row.local_symbol || row.symbol)}</td><td>${esc(row.sec_type)}</td><td>${quantity(row.quantity_decimal)}</td><td>${esc(row.quantity_unit || (['OPT', 'FOP'].includes(String(row.sec_type).toUpperCase()) ? 'contracts' : 'shares'))}</td><td>${signed(row.market_value_base_decimal ?? row.market_value_decimal, row.base_currency || book.snapshot?.base_currency || 'USD')}</td><td>${esc(row.exclusion_reason)}</td></tr>`).join('')}</tbody></table>${excluded.length ? '' : emptyState('true_zero', 'Nothing assigned elsewhere', 'Every broker position is included in this owner scope.', 'allocation ledger', 'No action required.')}</div>`;
    }
    return `<div class="ph-alert"><strong>Quarantine is visible by default.</strong> Unresolved contracts and cash remain unallocated until their identity is complete.</div><div class="ph-toolbar"><strong>Unresolved positions · ${quarantined.length}</strong></div><div class="ph-table-wrap"><table class="ph-table"><thead><tr><th>Instrument</th><th>ConId / model</th><th>Qty</th><th>Market value · base</th><th>Status</th></tr></thead><tbody>${quarantined.map((row) => `<tr><td><button type="button" class="ph-symbol-link" data-ph-open-row="${esc(positionKey(row))}">${esc(row.local_symbol || row.symbol)}</button></td><td>${row.conid} / ${esc(row.model_code || 'default')}</td><td>${quantity(row.quantity_decimal)}</td><td>${money(row.market_value_base_decimal ?? row.market_value_decimal, false, row.base_currency || book.snapshot?.base_currency || 'USD')}</td><td>quarantined</td></tr>`).join('')}</tbody></table>${quarantined.length ? '' : emptyState('true_zero', 'No quarantined broker rows', 'Every conId has an allocation rule at this watermark.', 'allocation ledger', 'No action required.')}</div><div class="ph-table-wrap" style="margin-top:16px"><table class="ph-table"><thead><tr><th>Severity</th><th>Type</th><th>Instrument</th><th>Expected</th><th>Actual</th><th>Status</th></tr></thead><tbody>${rows.map((row) => `<tr><td>${esc(row.severity)}</td><td>${esc(row.break_type)}</td><td>${esc(row.conid || 'account')} ${esc(row.model_code || '')}</td><td>${esc(row.expected_decimal)}</td><td>${esc(row.actual_decimal)}</td><td>${esc(row.status)}</td></tr>`).join('')}</tbody></table>${rows.length ? '' : emptyState('true_zero', 'No open reconciliation breaks', 'The latest complete broker snapshot and allocation ledger agree within tolerance.', 'reconciliation ledger', 'No action required.')}</div>${positionDrawer((book.positions || []).find((row) => positionKey(row) === state.selectedPositionKey))}`;
  }

  async function loadActiveSectionData() {
    try {
      if (state.section === 'orders') {
        const [central, paper, requests] = await Promise.allSettled([
          getJson('/api/v2/portfolio/orders'),
          getJson('/api/v2/portfolio/paper-orders'),
          getJson('/api/v2/portfolio/order-intents'),
        ]);
        state.orders = central.status === 'fulfilled' ? central.value : { error: central.reason.message, events: [], broker_open_orders: [] };
        state.paperOrders = paper.status === 'fulfilled' ? paper.value : { error: paper.reason.message, orders: [], viewer: {} };
        state.orderRequests = requests.status === 'fulfilled' ? requests.value : { error: requests.reason.message, requests: [], viewer: {} };
        if (activeRequest()) startTicketPolling();
      } else if (state.selectedPositionKey) state.orders = await getJson('/api/v2/portfolio/orders');
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
    const sectionAvailable = book?.status === 'complete' || state.section === 'orders';
    root.innerHTML = `<div class="ph-shell">${shellHeader(book)}${sectionAvailable ? sectionView(book) : emptyState('upstream_absent', 'Waiting for the first complete IBKR snapshot', book?.reason || 'The private collector has not published broker truth yet.', 'Private IBKR collector · last checked on page load', 'Portfolio operations should publish a complete account summary and position watermark; Orders remains available for owner-scoped paper tickets.')}</div>`;
    bindCommon(root);
    if (state.section === 'orders') bindOrderDesk(root);
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
      const allBookIndex = state.scope === 'all' ? null : requests.push(getJson('/api/v2/portfolio/book?owner=all')) - 1;
      const performanceIndex = state.accountPerformance ? null : requests.push(getJson('/api/v2/portfolio/performance?owner=all')) - 1;
      const responses = await Promise.all(requests); state.book = responses[0];
      state.allBook = allBookIndex == null ? state.book : responses[allBookIndex];
      if (performanceIndex != null) state.accountPerformance = responses[performanceIndex];
    }
    catch (error) { state.book = { status: 'unknown', reason: error.message, positions: [], account_values: [], reconciliation_breaks: [] }; }
    await loadActiveSectionData();
    renderPortfolio();
  }

  function strategyRows(payload) {
    const chosen = state.strategySection;
    return (payload?.rows || []).filter((row) => chosen === 'overview' || String(row.bucket || '').toLowerCase() === chosen);
  }

  function strategyWorkbench(producer, payload) {
    const isSpx = producer === 'spx_0dte';
    const summary = payload.summary || {};
    const title = isSpx ? 'SPX 0DTE' : 'LS Algo';
    const sectionNav = `<div class="ph-section-nav" role="navigation" aria-label="${title} sections">${strategySections.map((section) => `<button type="button" data-ph-strategy-section="${section}" class="${state.strategySection === section ? 'active' : ''}">${section === 'pnl' ? 'P&L' : section[0].toUpperCase() + section.slice(1)}</button>`).join('')}</div>`;
    const bucketNav = isSpx || state.strategySection !== 'positions' ? '' : `<div class="ph-bucket-nav" aria-label="LS Algo bucket filter">${buckets.map((bucket) => `<button type="button" data-ph-bucket="${bucket}" class="${state.strategyBucket === bucket ? 'active' : ''}">${bucket === 'all' ? 'All buckets' : bucket.toUpperCase()}</button>`).join('')}</div>`;
    let body = '';
    if (state.strategySection === 'overview') {
      if (isSpx) {
        const riskPositions = payload.rows || [];
        const definedMargin = riskPositions.reduce((sum, row) => sum + (num(row.metrics?.defined_risk_margin) || 0), 0);
        body = `<div class="ph-grid">${panelLines('Session now', [['Process', summary.process === true ? 'alive' : summary.process === false ? 'stopped' : 'unknown'], ['Entries', summary.halted ? 'halted' : 'enabled'], ['Total P&L · USD', signed(summary.total_pnl)], ['Closed / marked · USD', `${signed(summary.closed_pnl)} / ${signed(summary.marked_pnl)}`]])}${panelLines('Risk rails', [['Open structures', String(summary.open_count ?? riskPositions.length)], ['Defined-risk margin · USD', money(definedMargin)], ['Open contracts', quantity(summary.open_contracts)], ['Flatten flag', summary.flattened ? 'active' : 'clear']])}${panelLines('Data health', [['As of', payload.as_of || 'unavailable'], ['Heartbeat', summary.heartbeat_ts || 'unavailable'], ['Status', payload.status || 'unknown'], ['Cadence', 'live snapshot + retained history']])}</div>`;
      } else {
        const book = summary.book || {};
        body = `<div class="ph-grid">${panelLines('Book', [['NAV · USD', money(book.nav_usd)], ['Gross notional · USD', money(book.gross_notional_usd)], ['Net notional · USD', money(book.net_notional_usd)], ['Long / short · USD', `${money(book.long_notional_usd)} / ${money(book.short_notional_usd)}`]])}${panelLines('Performance', [['Daily P&L · USD', signed(book.pnl_daily_usd ?? book.pnl_today_usd)], ['Daily P&L · % NAV', pct(book.pnl_daily_pct_nav ?? book.pnl_today_pct_nav)], ['YTD P&L · USD', signed(book.pnl_ytd_usd)], ['YTD P&L · % NAV', pct(book.pnl_ytd_pct_nav)]])}${panelLines('Exposure', [['Gross · % NAV', pct(book.gross_exposure_pct_nav)], ['Net · % NAV', pct(book.net_exposure_pct_nav)], ['Breaches', String((book.breaches || []).length)], ['As of', payload.as_of || 'unavailable']])}</div>`;
      }
    } else if (state.strategySection === 'positions') {
      // Bucket, then kind. This used to filter on "has a notional", which silently
      // hid the whole B5 put ladder -- a hedge has a market value, not a notional
      // -- and then the empty state blamed the adapter for sending no rows. The
      // cells below already render 'Not published' for a missing value, so the
      // row belongs on screen; what does not belong is a pnl row, which carries
      // attribution and no holding, and is what the notional test was really
      // excluding by accident.
      const rows = (payload.rows || [])
        .filter((row) => isSpx || state.strategyBucket === 'all' || String(row.bucket || '').toLowerCase() === state.strategyBucket)
        .filter((row) => isSpx || row.row_kind !== 'pnl');
      body = `${bucketNav}<div class="ph-table-wrap"><table class="ph-table ph-table--wide"><thead><tr><th>Position</th><th>Bucket</th><th>Quantity / legs</th><th>Position units</th><th>Market value · USD</th><th>Net notional · USD</th><th>Gross notional · USD</th><th>Marked P&amp;L · USD</th><th>Defined-risk margin · USD</th><th>Quality</th></tr></thead><tbody>${rows.map((row) => `<tr><td>${esc(row.symbol || row.underlying || 'Unavailable')}</td><td>${esc(row.bucket || 'strategy')}</td><td>${quantity(row.metrics?.contracts ?? row.metrics?.quantity ?? row.metrics?.n_legs)}</td><td>${esc(row.position_units || (isSpx ? 'contracts' : row.metrics?.n_legs != null ? 'legs' : 'shares'))}</td><td>${row.metrics?.market_value == null ? 'Not published' : signed(row.metrics.market_value)}</td><td>${row.metrics?.net_notional_usd == null ? 'Not published' : signed(row.metrics.net_notional_usd)}</td><td>${row.metrics?.gross_notional_usd == null ? 'Not published' : money(row.metrics.gross_notional_usd)}</td><td>${row.metrics?.marked_pnl == null ? 'Not published' : signed(row.metrics.marked_pnl)}</td><td>${row.metrics?.defined_risk_margin == null ? 'Not published' : money(row.metrics.defined_risk_margin)}</td><td>${esc(row.lineage?.mark_quality || row.lineage?.quality || 'producer')}</td></tr>`).join('')}</tbody></table>${rows.length ? '' : emptyState('upstream_absent', 'No published strategy positions', 'The adapter received no position rows for this filter.', producer, 'Publish stable position IDs and native quantity units.')}</div>`;
    } else if (state.strategySection === 'pnl') {
      const pnlRows = isSpx ? (summary.risk_history || []) : (payload.rows || []).filter((row) => row.metrics?.total_pnl != null || row.metrics?.session_pnl != null);
      body = `<div class="ph-grid">${panelLines('Accounting contract', isSpx ? [['Session total', 'closed realized + open marked'], ['Cadence', 'heartbeat producer'], ['Settlement', 'daily reconciliation']] : [['Daily', 'pnl_history.csv'], ['YTD', 'producer cumulative'], ['Restatements', 'separate from daily']])}</div><div class="ph-table-wrap"><table class="ph-table ph-table--wide"><thead><tr><th>Period / position</th><th>Realized · USD</th><th>Unrealized / marked · USD</th><th>Total · USD</th><th>Borrow / fees · USD</th><th>Margin · USD</th></tr></thead><tbody>${pnlRows.map((row) => { const metrics = row.metrics || row; return `<tr><td>${esc(row.ts || row.date || row.symbol || row.underlying || row.row_id || 'snapshot')}</td><td>${signed(metrics.realized_pnl ?? metrics.closed_pnl)}</td><td>${signed(metrics.unrealized_pnl ?? metrics.marked_pnl)}</td><td>${signed(metrics.total_pnl ?? metrics.session_pnl)}</td><td>${signed((num(metrics.borrow_fees) || 0) + (num(metrics.short_credit_interest) || 0))}</td><td>${money(metrics.defined_risk_margin)}</td></tr>`; }).join('')}</tbody></table>${pnlRows.length ? '' : emptyState('upstream_absent', 'P&L series not published', 'The current snapshot has no typed P&L rows.', producer, 'Publish strategy_metric_series.v1 with period and value kind.')}</div>`;
    } else if (state.strategySection === 'margin') {
      const marginRows = isSpx ? (summary.risk_history || []) : (summary.sleeves?.rows || []);
      body = `<div class="ph-alert"><strong>Margin meanings stay separate.</strong> ${isSpx ? 'Defined-risk margin is the spread-width model, not IBKR portfolio margin.' : 'Sleeve margin is producer/Flex-derived and is not a broker allocation.'}</div><div class="ph-table-wrap"><table class="ph-table ph-table--wide"><thead><tr><th>Time / sleeve</th><th>Current margin · USD</th><th>Average margin · USD</th><th>Return on margin · %</th><th>Headroom / rail · USD</th></tr></thead><tbody>${marginRows.map((row) => `<tr><td>${esc(row.ts || row.date || row.bucket_label || row.bucket || 'snapshot')}</td><td>${money(row.defined_risk_margin ?? row.margin_req_usd)}</td><td>${money(row.avg_margin_req_usd)}</td><td>${row.return_on_margin_pct != null ? `${Number(row.return_on_margin_pct).toFixed(2)}%` : row.rom_on_margin_req != null ? pct(row.rom_on_margin_req) : 'Not published'}</td><td>${row.headroom_usd == null ? 'Not published' : money(row.headroom_usd)}</td></tr>`).join('')}</tbody></table>${marginRows.length ? '' : emptyState('upstream_absent', 'Intraday margin series not retained here', isSpx ? 'The producer emits current risk snapshots; the hosted transport must retain the full current-day cadence.' : 'The producer has not published sleeve margin rows.', producer, 'Publish margin_series.v1 without combining model and broker values.')}</div>`;
    } else if (state.strategySection === 'risk') {
      if (isSpx) {
        const rows = payload.rows || [];
        body = `<div class="ph-grid">${panelLines('Live risk', [['Open positions', String(rows.length)], ['Max loss · USD', money(rows.reduce((sum, row) => sum + (num(row.metrics?.max_loss_no_stop) || 0), 0))], ['Planned stop · USD', money(rows.reduce((sum, row) => sum + (num(row.metrics?.planned_stop_loss) || 0), 0))], ['Defined-risk margin · USD', money(rows.reduce((sum, row) => sum + (num(row.metrics?.defined_risk_margin) || 0), 0))]])}${panelLines('Intraday coverage', [['P&L', 'closed + marked'], ['Margin', 'defined-risk model'], ['Spot / Greeks', rows.some((row) => row.metrics?.delta != null) ? 'published' : 'awaiting sanitized transport'], ['Broker margin', 'separate · not inferred']])}</div>`;
      } else {
        const slideRows = (summary.slide_risk?.indices || []).flatMap((index) => (index.shock_rows || []).map((row) => ({ ...row, index: index.index })));
        const borrowRows = summary.borrow_shocks?.scenarios || [];
        body = `<div class="ph-grid">${panelLines('Scenario model', [['Market strip', summary.slide_risk?.available ? 'published' : 'unavailable'], ['Factor coverage', String(summary.factors?.rows?.length || 0)], ['Concentration breaches', String(summary.concentration?.breaches?.length || 0)], ['Correlation lift', summary.correlation_shock?.available ? 'published' : 'not in sanitized snapshot']])}${panelLines('Borrow stress', [['Current annual cost · USD', money(summary.borrow_shocks?.current_annual_cost_usd)], ['Current · % NAV', pct(summary.borrow_shocks?.current_pct_nav)], ['Scenarios', String(borrowRows.length)], ['Value kind', 'producer model estimate']])}</div><div class="ph-table-wrap"><table class="ph-table ph-table--scenario"><thead><tr><th>Scenario</th><th>Shock</th><th>P&amp;L · USD</th><th>P&amp;L · % NAV</th><th>Top loss</th><th>Concentration</th></tr></thead><tbody>${slideRows.map((row) => `<tr><td>${esc(row.label)}</td><td>${row.shock_pct == null ? 'Unavailable' : `${(row.shock_pct * 100).toFixed(1)}%`}</td><td>${signed(row.pnl_usd)}</td><td>${row.pnl_pct_nav == null ? 'Unavailable' : `${(row.pnl_pct_nav * 100).toFixed(2)}%`}</td><td>${esc(row.top_loss?.underlying || 'Unavailable')}</td><td>${row.concentration?.top_n_share_of_scenario == null ? 'Unavailable' : pct(row.concentration.top_n_share_of_scenario)}</td></tr>`).join('')}</tbody></table>${slideRows.length ? '' : emptyState('upstream_absent', 'Slide-risk surface unavailable', 'The sanitized LS snapshot contains no scenario rows.', 'LS Algo slide_risk_panel', 'Republish the latest producer snapshot.')}</div>`;
      }
    } else if (state.strategySection === 'orders') {
      body = emptyState('not_applicable', 'Strategy order entry stays in the owner portfolio', 'Paper tickets are owner-authorized, while live strategy execution remains in its guarded private command plane.', 'Access login + owner paper ledger', 'Open Portfolio → Drew or Michael → Orders.');
    } else {
      body = `<div class="ph-grid">${panelLines('Contract', [['Producer', producer], ['Status', payload.status || 'unknown'], ['Rows', String((payload.rows || []).length)], ['Run', payload.source_run_id || 'unavailable']])}${panelLines('Reconciliation', [['Broker positions', 'canonical account feed'], ['Strategy analytics', 'producer-owned'], ['Owner allocation', 'never inferred from strategy'], ['Unlinked rows', String((payload.rows || []).filter((row) => !row.conid).length)]])}</div>`;
    }
    return `<div class="ph-shell"><div class="ph-eyebrow">Strategies workbench · versioned producer data</div><div class="ph-title-row"><div><h2 class="ph-title">${title}</h2><div class="ph-asof">${esc(payload.as_of || 'No producer snapshot')} · ${esc(payload.status || 'unknown')}</div></div><span class="ph-strategy-badge">${isSpx ? 'LIVE MODEL' : 'LS ALGO'}</span></div>${sectionNav}${body}</div>`;
  }

  function renderStrategy(producer) {
    const isSpx = producer === 'spx_0dte'; const root = document.getElementById(isSpx ? 'spx-0dte-content' : 'letf-content'); if (!root) return;
    const payload = state.strategy || {}; const rows = strategyRows(payload);
    root.innerHTML = strategyWorkbench(producer, payload);
    root.querySelectorAll('[data-ph-strategy-section]').forEach((button) => button.addEventListener('click', () => { state.strategySection = button.dataset.phStrategySection; state.onRoute?.(); renderStrategy(producer); }));
    root.querySelectorAll('[data-ph-bucket]').forEach((button) => button.addEventListener('click', () => { state.strategyBucket = button.dataset.phBucket; state.onRoute?.(); renderStrategy(producer); }));
    root.querySelectorAll('[data-ph-linked-symbol]').forEach((button) => button.addEventListener('click', () => openLinkedSymbol(button.dataset.phLinkedSymbol)));
  }

  async function openStrategy(producer, onRoute) {
    state.onRoute = onRoute;
    const root = document.getElementById(producer === 'spx_0dte' ? 'spx-0dte-content' : 'letf-content');
    if (root) root.innerHTML = '<div class="ph-empty"><div><b>Loading producer snapshot…</b>Broker facts remain independent of model availability.</div></div>';
    try { state.strategy = await getJson(`/api/v2/portfolio/strategies?producer=${encodeURIComponent(producer)}`); }
    catch (error) { state.strategy = { status: 'unknown', rows: [], error: error.message }; }
    renderStrategy(producer);
  }

  window.PortfolioViz = {
    state,
    setRoute(scope, section) { if (['all', 'drew', 'michael'].includes(scope)) state.scope = scope; if (sections.includes(section)) state.section = section; },
    setStrategyRoute(section) { if (strategySections.includes(section)) state.strategySection = section; else if (buckets.includes(section)) { state.strategySection = 'positions'; state.strategyBucket = section; } },
    openPortfolio(onRoute) { state.onRoute = onRoute; loadBook(); },
    openStrategy,
  };
})();
