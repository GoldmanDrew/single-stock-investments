(function () {
  'use strict';

  const locale = (navigator.languages && navigator.languages[0]) || navigator.language || 'en-US';
  const finite = (value) => {
    if (value == null || value === '') return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  };
  const numberCache = new Map();
  const formatter = (options) => {
    const key = JSON.stringify(options);
    if (!numberCache.has(key)) numberCache.set(key, new Intl.NumberFormat(locale, options));
    return numberCache.get(key);
  };

  // Quotes that are denominated in a minor unit. Intl.NumberFormat matches
  // currency codes case-insensitively, so passing 'GBp' to it renders "£2,591.00"
  // -- the right symbol on a pence figure, which reads 100x larger than the real
  // price. These never go through Intl's currency style; they get the number plus
  // an explicit unit label so the scale cannot be misread.
  const MINOR_UNIT_LABEL = { GBP: 'GBp', ILS: 'ILA', ZAR: 'ZAc' };

  const isMinorUnit = (units) => Boolean(units) && Number(units.minor_unit_factor || 1) !== 1;

  window.DashboardFormat = Object.freeze({
    finite,
    isMinorUnit,

    number(value, options = {}) {
      const number = finite(value);
      return number == null ? '—' : formatter({ maximumFractionDigits: 4, ...options }).format(number);
    },

    currency(value, currency = 'USD', options = {}) {
      const number = finite(value);
      return number == null ? '—' : formatter({
        style: 'currency', currency: currency || 'USD', maximumFractionDigits: 2, ...options,
      }).format(number);
    },

    percent(value, options = {}) {
      const number = finite(value);
      return number == null ? '—' : formatter({ style: 'percent', maximumFractionDigits: 1, ...options }).format(number);
    },

    date(value, options = {}) {
      if (!value) return 'Unavailable';
      // "2026-08-19" is a calendar date, but Date parses a bare date-only string as
      // UTC midnight and Intl then renders it in the viewer's zone -- which shows
      // the previous day for everyone west of UTC. Read those parts literally.
      const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value).trim());
      const date = dateOnly
        ? new Date(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3]))
        : new Date(value);
      return Number.isNaN(date.getTime()) ? String(value) : new Intl.DateTimeFormat(locale, {
        year: 'numeric', month: 'short', day: '2-digit', ...options,
      }).format(date);
    },

    /**
     * Render a figure in the units it was quoted in.
     *
     * `units` is the block build_dashboard_data.py attaches to every ticker
     * payload: { currency, minor_unit_factor, source }. A null currency means the
     * listing's units could not be resolved, and the number renders bare rather
     * than borrowing a symbol it has not earned.
     */
    quote(value, units, options = {}) {
      const number = finite(value);
      if (number == null) return '—';
      const currency = units && units.currency;
      if (!currency) return formatter({ maximumFractionDigits: 2, ...options }).format(number);
      if (isMinorUnit(units)) {
        const label = MINOR_UNIT_LABEL[currency] || currency;
        return `${formatter({ maximumFractionDigits: 2, ...options }).format(number)} ${label}`;
      }
      return formatter({
        style: 'currency', currency, maximumFractionDigits: 2, ...options,
      }).format(number);
    },

    /** quote() with an explicit sign, for P&L and deltas. */
    signedQuote(value, units, options = {}) {
      const number = finite(value);
      if (number == null) return '—';
      const rendered = this.quote(Math.abs(number), units, options);
      return `${number < 0 ? '−' : number > 0 ? '+' : ''}${rendered}`;
    },

    /** Short form for axis ticks and dense tables: $2.6K / ¥2.6K / 2.6K GBp. */
    compactQuote(value, units, options = {}) {
      return this.quote(value, units, { notation: 'compact', maximumFractionDigits: 1, ...options });
    },

    /** The code to show a human, distinguishing GBp from GBP. */
    unitLabel(units) {
      if (!units || !units.currency) return null;
      return isMinorUnit(units) ? (MINOR_UNIT_LABEL[units.currency] || units.currency) : units.currency;
    },
  });
})();
