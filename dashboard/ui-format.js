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

  window.DashboardFormat = Object.freeze({
    finite,
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
      const date = new Date(value);
      return Number.isNaN(date.getTime()) ? String(value) : new Intl.DateTimeFormat(locale, {
        year: 'numeric', month: 'short', day: '2-digit', ...options,
      }).format(date);
    },
  });
})();
