(function (global) {
  'use strict';

  // Volatility surface + vol-metrics panel for the risk view.
  // Tier 1+2 of _system/proposals/vol_surface_visibility_plan_2026-08-10.md.
  //
  // Conventions mirror criticality-viz.js: an IIFE that returns HTML strings,
  // `finite` for null-tolerant numbers, and an injected escapeHtml so the
  // caller owns escaping. Nulls in the vol feeds are real ("no print that
  // day") and are never imputed to zero — every surface here renders a null
  // as a distinct absence, not as a neutral/average value.

  // Five orthogonal rows, not fourteen. Correlation of each metric's 1y z-score
  // against VIX's over the 120 displayed sessions: vix3m 0.97, vix9d 0.95,
  // vix6m 0.95, slope_vix_3m 0.94, vvix 0.92, vix1d 0.75 - those are the same
  // signal repainted, and slope_9d_vix / slope_3m_6m / vvix_vix_ratio are
  // arithmetic derivatives of rows already present, so they cannot add
  // information by construction. The rows kept here are -0.15 (spx_rv20),
  // 0.28 (skew), 0.62 (move) and 0.71 (iv_rv_spread) against VIX. The full
  // 14-metric series is untouched in data/vol_metrics_history.jsonl; this is a
  // rendering choice, not a data deletion. The term slope survives as the term
  // STATE tile, which is the part that carries information.
  const METRIC_ORDER = ['vix', 'spx_rv20', 'skew', 'move', 'iv_rv_spread'];

  const METRIC_LABELS = {
    vix: 'VIX', vix9d: 'VIX9D', vix3m: 'VIX3M', vix6m: 'VIX6M', vix1d: 'VIX1D',
    vvix: 'VVIX', skew: 'SKEW', move: 'MOVE', spx_rv20: 'SPX RV20',
    slope_9d_vix: 'Slope 9D/VIX', slope_vix_3m: 'Slope VIX/3M',
    slope_3m_6m: 'Slope 3M/6M', vvix_vix_ratio: 'VVIX/VIX',
    iv_rv_spread: 'IV − RV',
  };

  const HEATMAP_SESSIONS = 120;
  const TABLE_SESSIONS = 30;

  function finite(value) {
    if (value == null || value === '') return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  function escapeFallback(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function num(value, digits) {
    const number = finite(value);
    return number == null ? '—' : number.toFixed(digits == null ? 2 : digits);
  }

  function signed(value, digits) {
    const number = finite(value);
    if (number == null) return '—';
    const body = Math.abs(number).toFixed(digits == null ? 2 : digits);
    return `${number < 0 ? '−' : '+'}${body}`;
  }

  function zText(value) {
    const number = finite(value);
    return number == null ? '—' : `${signed(number, 2)}σ`;
  }

  function pctText(value) {
    const number = finite(value);
    return number == null ? '—' : `${number.toFixed(1)}%`;
  }

  function ivPct(value) {
    const number = finite(value);
    return number == null ? '—' : `${(number * 100).toFixed(2)}%`;
  }

  function shortDate(value) {
    return String(value == null ? '' : value).slice(0, 10);
  }

  // Index levels want two decimals; ratios and slopes need four to be readable.
  function level(value) {
    const number = finite(value);
    if (number == null) return '—';
    return number.toFixed(Math.abs(number) >= 10 ? 2 : 4);
  }

  function behindText(sessions) {
    const count = finite(sessions);
    if (count == null) return 'lag unknown';
    return `${count} session${count === 1 ? '' : 's'} behind`;
  }

  // Diverging bin index for a z-score. 0 = neutral (|z| < 0.5); the arms use
  // the conventional 1-sigma and 2-sigma landmarks. Returns null for a null z
  // so callers can render the absence channel instead of a colour.
  function zBin(value) {
    const number = finite(value);
    if (number == null) return null;
    const magnitude = Math.abs(number);
    const step = magnitude < 0.5 ? 0 : magnitude < 1 ? 1 : magnitude < 2 ? 2 : 3;
    if (step === 0) return 'z0';
    return `${number < 0 ? 'n' : 'p'}${step}`;
  }

  function tailRows(rows, count) {
    const list = Array.isArray(rows) ? rows.filter((row) => row && row.date) : [];
    const ordered = list.slice().sort((a, b) => String(a.date).localeCompare(String(b.date)));
    return count == null ? ordered : ordered.slice(-count);
  }

  // ---------------------------------------------------------------------
  // (a) z-score heatmap strip
  // ---------------------------------------------------------------------

  function heatmap(rows, lagging, escapeHtml) {
    const window_ = tailRows(rows, HEATMAP_SESSIONS);
    if (!window_.length) {
      return '<div class="risk-empty">No vol-metrics history is loaded, so the z-score strip has nothing to draw.</div>';
    }

    const labelWidth = 150;
    const plotLeft = 154;
    const plotRight = 986;
    const plotWidth = plotRight - plotLeft;
    const plotTop = 10;
    const rowPitch = 17;
    const cellHeight = 15;
    const height = plotTop + METRIC_ORDER.length * rowPitch + 26;
    const pitch = plotWidth / window_.length;
    const cellWidth = Math.max(1, pitch - 0.8);

    const cells = [];
    METRIC_ORDER.forEach((metric, rowIndex) => {
      const y = plotTop + rowIndex * rowPitch;
      const label = METRIC_LABELS[metric] || metric;
      cells.push(`<text class="vol-heat-row-label" x="${labelWidth}" y="${(y + cellHeight / 2 + 3.4).toFixed(1)}">${escapeHtml(label)}${lagging[metric] ? ' ○' : ''}</text>`);
      window_.forEach((row, colIndex) => {
        const x = plotLeft + colIndex * pitch;
        const z1 = finite(row[`${metric}_z1y`]);
        const z5 = finite(row[`${metric}_z5y`]);
        const bin = zBin(z1);
        const tip = `${label} · ${shortDate(row.date)} · ${bin == null ? 'no print' : `z1y ${signed(z1, 2)} · z5y ${z5 == null ? 'n/a' : signed(z5, 2)}`}`;
        const fill = bin == null
          ? 'class="vol-heat-cell vol-heat-null" fill="url(#vol-null-hatch)"'
          : `class="vol-heat-cell vol-heat-${bin}"`;
        cells.push(`<rect ${fill} x="${x.toFixed(2)}" y="${y}" width="${cellWidth.toFixed(2)}" height="${cellHeight}" rx="1"><title>${escapeHtml(tip)}</title></rect>`);
      });
    });

    const tickCount = Math.min(6, window_.length);
    const axisY = plotTop + METRIC_ORDER.length * rowPitch + 16;
    const ticks = [];
    for (let i = 0; i < tickCount; i += 1) {
      const index = tickCount === 1 ? 0 : Math.round((i / (tickCount - 1)) * (window_.length - 1));
      const x = plotLeft + index * pitch + cellWidth / 2;
      const anchor = i === 0 ? 'start' : i === tickCount - 1 ? 'end' : 'middle';
      ticks.push(`<text class="vol-heat-axis-label" x="${x.toFixed(1)}" y="${axisY}" text-anchor="${anchor}">${escapeHtml(shortDate(window_[index].date))}</text>`);
    }

    const first = shortDate(window_[0].date);
    const last = shortDate(window_[window_.length - 1].date);

    // The strip is wrapped in a scroller: below its legibility floor the cells
    // and row labels would shrink to noise, so it scrolls sideways instead.
    return `<div class="vol-chart-scroll"><svg class="vol-heat-chart" viewBox="0 0 1000 ${height}" preserveAspectRatio="xMidYMid meet" role="img"
        aria-label="Z-score heatmap: ${escapeHtml(String(METRIC_ORDER.length))} volatility metrics over ${escapeHtml(String(window_.length))} sessions from ${escapeHtml(first)} to ${escapeHtml(last)}, coloured by trailing one-year z-score">
      <defs><pattern id="vol-null-hatch" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
        <path class="vol-heat-null-line" d="M0,0 L0,4"></path>
      </pattern></defs>
      ${cells.join('')}
      ${ticks.join('')}
    </svg></div>`;
  }

  // ---------------------------------------------------------------------
  // (a2) long-history strip
  //
  // The daily strip above is capped at 120 sessions because below roughly 6px
  // a cell and its row label degrade into noise. The file holds 1,528 sessions
  // back to 2020-07-13 and the browser now receives all of them, so the answer
  // is not to shrink the cells -- 1,528 columns across 832px is half a pixel
  // each -- but to change the unit. One cell per MONTH is ~73 columns at 11px,
  // which is legible, and a monthly mean of a daily z-score is a fair summary
  // of a regime as long as it is labelled as one and the underlying daily
  // strip stays available directly above it. Months with no prints hatch.
  // ---------------------------------------------------------------------

  // Named episodes, so a wall of colour has anchors a reader can navigate by.
  // Dates are the month the episode peaked, which is the resolution of the
  // strip; nothing here is derived from the data, it is context laid over it.
  const VOL_EVENTS = [
    { month: '2018-02', label: 'Volmageddon' },
    { month: '2020-03', label: 'COVID' },
    { month: '2020-11', label: 'vaccine' },
    { month: '2021-02', label: 'meme squeeze' },
    { month: '2022-01', label: 'rate repricing' },
    { month: '2022-10', label: 'bear low' },
    { month: '2023-03', label: 'SVB' },
    { month: '2024-08', label: 'yen carry unwind' },
    { month: '2025-04', label: 'tariff shock' },
  ];

  function monthlyRows(rows) {
    const buckets = new Map();
    tailRows(rows, null).forEach((row) => {
      const month = shortDate(row.date).slice(0, 7);
      if (month.length !== 7) return;
      if (!buckets.has(month)) buckets.set(month, { month, sums: {}, counts: {} });
      const bucket = buckets.get(month);
      METRIC_ORDER.forEach((metric) => {
        const z = finite(row[`${metric}_z1y`]);
        if (z == null) return;
        bucket.sums[metric] = (bucket.sums[metric] || 0) + z;
        bucket.counts[metric] = (bucket.counts[metric] || 0) + 1;
      });
    });
    return Array.from(buckets.values())
      .sort((a, b) => a.month.localeCompare(b.month))
      .map((bucket) => {
        const out = { month: bucket.month, sessions: {} };
        METRIC_ORDER.forEach((metric) => {
          const n = bucket.counts[metric] || 0;
          out[metric] = n ? bucket.sums[metric] / n : null;
          out.sessions[metric] = n;
        });
        return out;
      });
  }

  function longHeatmap(rows, escapeHtml) {
    const months = monthlyRows(rows);
    if (months.length < 6) return '';

    const labelWidth = 150;
    const plotLeft = 154;
    const plotRight = 986;
    const plotWidth = plotRight - plotLeft;
    const rowPitch = 17;
    const cellHeight = 15;
    const pitch = plotWidth / months.length;
    const cellWidth = Math.max(1, pitch - 0.8);

    // Events are placed before the plot is laid out, because the number of
    // label rows decides where the plot can start. Clustered episodes used to
    // overprint each other -- 2020-11 through 2023-03 are five events inside
    // 28 cells, which rendered as one unreadable smear -- so each label takes
    // the lowest row that its neighbours leave clear.
    //
    // .vol-event-label is 10px JetBrains Mono. A monospace advance of 0.6em
    // measures a label exactly, so this is a real collision test rather than a
    // guess, and it stays correct as labels are added or renamed.
    const EVENT_CHAR = 6;
    const EVENT_GUTTER = 6;
    const EVENT_LINE = 11;
    const events = [];
    VOL_EVENTS.forEach((event) => {
      const index = months.findIndex((bucket) => bucket.month === event.month);
      if (index < 0) return;
      const x = plotLeft + index * pitch + cellWidth / 2;
      const half = (event.label.length * EVENT_CHAR) / 2;
      // The rule stays on the true column; only the text slides, so an episode
      // near either edge is legible instead of clipped by the viewBox.
      const textX = Math.min(Math.max(x, half + 2), 998 - half);
      let row = 0;
      while (events.some((placed) => placed.row === row
        && textX - half < placed.right + EVENT_GUTTER)) row += 1;
      events.push({ x, textX, row, label: event.label, right: textX + half });
    });
    const eventRows = events.length
      ? Math.max(...events.map((placed) => placed.row)) + 1
      : 1;
    // The topmost row keeps the single-row baseline of 13, so a strip with no
    // collisions is laid out exactly as before.
    const plotTop = 22 + (eventRows - 1) * EVENT_LINE;
    const height = plotTop + METRIC_ORDER.length * rowPitch + 40;

    const cells = [];
    METRIC_ORDER.forEach((metric, rowIndex) => {
      const y = plotTop + rowIndex * rowPitch;
      const label = METRIC_LABELS[metric] || metric;
      cells.push(`<text class="vol-heat-row-label" x="${labelWidth}" y="${(y + cellHeight / 2 + 3.4).toFixed(1)}">${escapeHtml(label)}</text>`);
      months.forEach((bucket, colIndex) => {
        const x = plotLeft + colIndex * pitch;
        const mean = finite(bucket[metric]);
        const bin = zBin(mean);
        const n = bucket.sessions[metric] || 0;
        const tip = `${label} · ${bucket.month} · ${bin == null ? 'no print in this month' : `mean z1y ${signed(mean, 2)} over ${n} session${n === 1 ? '' : 's'}`}`;
        const fill = bin == null
          ? 'class="vol-heat-cell vol-heat-null" fill="url(#vol-null-hatch-long)"'
          : `class="vol-heat-cell vol-heat-${bin}"`;
        cells.push(`<rect ${fill} x="${x.toFixed(2)}" y="${y}" width="${cellWidth.toFixed(2)}" height="${cellHeight}" rx="1"><title>${escapeHtml(tip)}</title></rect>`);
      });
    });

    // Year boundaries carry the axis; a monthly tick would collide at 73 cells.
    const axisY = plotTop + METRIC_ORDER.length * rowPitch + 15;
    const ticks = [];
    months.forEach((bucket, index) => {
      if (!bucket.month.endsWith('-01') && index !== 0) return;
      const x = plotLeft + index * pitch;
      ticks.push(`<line class="vol-year-rule" x1="${x.toFixed(1)}" y1="${plotTop - 4}" x2="${x.toFixed(1)}" y2="${(plotTop + METRIC_ORDER.length * rowPitch).toFixed(1)}"></line>`);
      ticks.push(`<text class="vol-heat-axis-label" x="${(x + 2).toFixed(1)}" y="${axisY}" text-anchor="start">${escapeHtml(bucket.month.slice(0, 4))}</text>`);
    });

    const marks = events.map((placed) => {
      const labelY = plotTop - 9 - placed.row * EVENT_LINE;
      // Each rule starts just under its own label, so a label lifted onto a
      // higher row still reads as belonging to its column.
      return `<line class="vol-event-rule" x1="${placed.x.toFixed(1)}" y1="${(labelY + 3).toFixed(1)}" x2="${placed.x.toFixed(1)}" y2="${(plotTop + METRIC_ORDER.length * rowPitch + 2).toFixed(1)}"></line>
        <text class="vol-event-label" x="${placed.textX.toFixed(1)}" y="${labelY.toFixed(1)}" text-anchor="middle">${escapeHtml(placed.label)}</text>`;
    }).join('');

    return `<details class="vol-long-view" open><summary>Full history · ${escapeHtml(String(months.length))} months, ${escapeHtml(shortDate(months[0].month))} to ${escapeHtml(months[months.length - 1].month)}</summary>
      <p class="vol-note">One cell per calendar month, coloured by the <b>mean</b> of that month's daily one-year z-scores — a summary of the regime, not a reading of any single session. The daily strip above is the unsmoothed version of the most recent 120 sessions. Hover any cell for the mean and how many sessions it averages.</p>
      <div class="vol-chart-scroll"><svg class="vol-heat-chart" viewBox="0 0 1000 ${height}" preserveAspectRatio="xMidYMid meet" role="img"
        aria-label="Monthly mean z-score heatmap: ${escapeHtml(String(METRIC_ORDER.length))} volatility metrics over ${escapeHtml(String(months.length))} months from ${escapeHtml(months[0].month)} to ${escapeHtml(months[months.length - 1].month)}">
        <defs><pattern id="vol-null-hatch-long" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <path class="vol-heat-null-line" d="M0,0 L0,4"></path>
        </pattern></defs>
        ${cells.join('')}
        ${ticks.join('')}
        ${marks}
      </svg></div></details>`;
  }

  function heatLegend(escapeHtml) {
    const swatches = [
      ['n3', '≤ −2'], ['n2', '−2 to −1'], ['n1', '−1 to −0.5'],
      ['z0', 'within ±0.5'],
      ['p1', '+0.5 to +1'], ['p2', '+1 to +2'], ['p3', '≥ +2'],
    ];
    return `<div class="vol-legend" role="img" aria-label="Colour scale: blue below the one-year mean, red above, grey within half a sigma, hatched where no print exists">
      <span class="vol-legend-end">calmer</span>
      ${swatches.map(([bin, label]) => `<span class="vol-legend-item"><i class="vol-heat-swatch vol-heat-${bin}"></i>${escapeHtml(label)}</span>`).join('')}
      <span class="vol-legend-end">more stressed</span>
      <span class="vol-legend-item"><i class="vol-heat-swatch vol-heat-swatch-null"></i>no print (not zero)</span>
    </div>`;
  }

  function heatTable(rows, escapeHtml) {
    const window_ = tailRows(rows, TABLE_SESSIONS);
    if (!window_.length) return '';
    return `<details class="vol-table-view"><summary>Table view · z-scores, last ${window_.length} sessions</summary>
      <div class="vol-table-scroll"><table class="vol-matrix"><caption>Trailing one-year z-score by metric and session. Blank means no print that day. The heatmap above spans a longer window; the full series lives in data/vol_metrics_history.jsonl.</caption>
        <thead><tr><th scope="col">Metric</th>${window_.map((row) => `<th scope="col">${escapeHtml(shortDate(row.date).slice(5))}</th>`).join('')}</tr></thead>
        <tbody>${METRIC_ORDER.map((metric) => `<tr><th scope="row">${escapeHtml(METRIC_LABELS[metric] || metric)}</th>${window_.map((row) => {
          const z = finite(row[`${metric}_z1y`]);
          return `<td>${z == null ? '<span class="vol-na">no print</span>' : escapeHtml(signed(z, 2))}</td>`;
        }).join('')}</tr>`).join('')}</tbody>
      </table></div></details>`;
  }

  // ---------------------------------------------------------------------
  // (b) term structure
  // ---------------------------------------------------------------------

  function termStructure(surface, priorSurface, volLatest, escapeHtml) {
    const tenors = (surface?.tenors || [])
      .map((tenor) => ({ ...tenor, dteValue: finite(tenor.dte), iv: finite(tenor.atm_iv) }))
      .filter((tenor) => tenor.dteValue != null && tenor.iv != null)
      .sort((a, b) => a.dteValue - b.dteValue);
    if (!tenors.length) {
      return '<div class="risk-empty">No SPX surface snapshot is loaded, so the term-structure curve has nothing to draw.</div>';
    }

    const prior = (priorSurface?.tenors || [])
      .map((tenor) => ({ dteValue: finite(tenor.dte), iv: finite(tenor.atm_iv) }))
      .filter((tenor) => tenor.dteValue != null && tenor.iv != null)
      .sort((a, b) => a.dteValue - b.dteValue);

    const vix = finite(volLatest?.regime?.vix ?? volLatest?.metrics?.vix?.last_value);
    const width = 1000;
    const height = 300;
    const padLeft = 54;
    const padRight = 132;
    const padTop = 22;
    const padBottom = 46;
    const plotWidth = width - padLeft - padRight;
    const plotHeight = height - padTop - padBottom;

    const maxDte = Math.max(...tenors.map((t) => t.dteValue), ...prior.map((t) => t.dteValue));
    // Vol scales with sqrt(time), so the x axis is sqrt-spaced. Ticks sit at
    // the ACTUAL listed dte of each snapshot, never the requested target.
    const xOf = (dte) => padLeft + (Math.sqrt(Math.max(0, dte)) / Math.sqrt(maxDte)) * plotWidth;

    const ivValues = tenors.map((t) => t.iv * 100)
      .concat(prior.map((t) => t.iv * 100))
      .concat(vix == null ? [] : [vix]);
    const rawMin = Math.min(...ivValues);
    const rawMax = Math.max(...ivValues);
    const yMin = Math.floor((rawMin - 0.8) / 2) * 2;
    const yMax = Math.ceil((rawMax + 0.8) / 2) * 2;
    const yOf = (value) => padTop + plotHeight - ((value - yMin) / (yMax - yMin)) * plotHeight;

    const gridlines = [];
    for (let v = yMin; v <= yMax + 1e-9; v += 2) {
      const y = yOf(v);
      gridlines.push(`<line class="vol-grid-line" x1="${padLeft}" y1="${y.toFixed(1)}" x2="${(padLeft + plotWidth).toFixed(1)}" y2="${y.toFixed(1)}"></line>`);
      gridlines.push(`<text class="vol-axis-label" x="${padLeft - 8}" y="${(y + 3.2).toFixed(1)}" text-anchor="end">${v.toFixed(0)}%</text>`);
    }

    const priorPath = prior.length >= 2
      ? `<polyline class="vol-term-line vol-term-prior" points="${prior.map((t) => `${xOf(t.dteValue).toFixed(1)},${yOf(t.iv * 100).toFixed(1)}`).join(' ')}"></polyline>`
      : '';
    const priorDots = prior.map((t) => `<circle class="vol-term-dot vol-term-prior-dot" cx="${xOf(t.dteValue).toFixed(1)}" cy="${yOf(t.iv * 100).toFixed(1)}" r="3.5"><title>${escapeHtml(`prior snapshot ${shortDate(priorSurface?.as_of)} · ${t.dteValue} dte · ATM IV ${(t.iv * 100).toFixed(2)}%`)}</title></circle>`).join('');

    const linePoints = tenors.map((t) => `${xOf(t.dteValue).toFixed(1)},${yOf(t.iv * 100).toFixed(1)}`).join(' ');

    const dots = tenors.map((t) => {
      const x = xOf(t.dteValue);
      const y = yOf(t.iv * 100);
      const drift = finite(t.dte_error_vs_target);
      const driftNote = drift ? ` (nearest listed expiry; target was ${finite(t.target_dte)} dte)` : '';
      const tip = `${t.tenor} · ${t.dteValue} dte · expiry ${shortDate(t.expiry)} · ATM IV ${(t.iv * 100).toFixed(2)}%${driftNote}`;
      return `<circle class="vol-term-dot" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="4.5"><title>${escapeHtml(tip)}</title></circle>
        <text class="vol-term-point-label" x="${x.toFixed(1)}" y="${(y - 13).toFixed(1)}" text-anchor="middle">${escapeHtml(`${(t.iv * 100).toFixed(2)}%`)}</text>
        <text class="vol-axis-label" x="${x.toFixed(1)}" y="${(padTop + plotHeight + 16).toFixed(1)}" text-anchor="middle">${escapeHtml(`${t.dteValue}d`)}</text>
        <text class="vol-axis-sub" x="${x.toFixed(1)}" y="${(padTop + plotHeight + 29).toFixed(1)}" text-anchor="middle">${escapeHtml(shortDate(t.expiry))}</text>`;
    }).join('');

    const vixMark = vix == null ? '' : (() => {
      const y = yOf(vix);
      const x = xOf(30);
      return `<line class="vol-ref-line" x1="${padLeft}" y1="${y.toFixed(1)}" x2="${(padLeft + plotWidth + 6).toFixed(1)}" y2="${y.toFixed(1)}"></line>
        <circle class="vol-ref-dot" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="4"><title>${escapeHtml(`VIX cash ${vix.toFixed(2)} — the 30-day constant-maturity reference, plotted at 30 dte`)}</title></circle>
        <text class="vol-ref-label" x="${(padLeft + plotWidth + 12).toFixed(1)}" y="${(y + 3.4).toFixed(1)}">VIX ${escapeHtml(vix.toFixed(2))}</text>`;
    })();

    const legend = prior.length >= 2
      ? `<div class="vol-legend"><span class="vol-legend-item"><i class="vol-key vol-key-current"></i>this snapshot ${escapeHtml(shortDate(surface?.as_of))}</span>
         <span class="vol-legend-item"><i class="vol-key vol-key-prior"></i>prior snapshot ${escapeHtml(shortDate(priorSurface?.as_of))}</span></div>`
      : '<p class="vol-note">Only one surface snapshot exists so far, so there is no prior curve to overlay. The overlay appears automatically once spx_surface_history.jsonl holds a second row.</p>';

    return `${legend}
      <div class="vol-chart-scroll"><svg class="vol-term-chart" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet" role="img"
        aria-label="SPX at-the-money implied volatility by actual days to expiry, with VIX cash as a reference level">
        ${gridlines.join('')}
        <line class="vol-axis-line" x1="${padLeft}" y1="${(padTop + plotHeight).toFixed(1)}" x2="${(padLeft + plotWidth).toFixed(1)}" y2="${(padTop + plotHeight).toFixed(1)}"></line>
        ${vixMark}
        ${priorPath}${priorDots}
        <polyline class="vol-term-line" points="${linePoints}"></polyline>
        ${dots}
      </svg></div>
      <p class="vol-note">X axis is sqrt-spaced in days (vol scales with the square root of time); ticks mark the ACTUAL listed dte of each snapshot, not the requested target tenor. VIX is drawn as a reference level because it is the same unit — an annualised 30-day implied vol — not as a second axis.</p>`;
  }

  // ---------------------------------------------------------------------
  // (c) regime tiles
  // ---------------------------------------------------------------------

  function quantile(sorted, q) {
    if (!sorted.length) return null;
    const pos = (sorted.length - 1) * q;
    const lo = Math.floor(pos);
    const hi = Math.ceil(pos);
    return lo === hi ? sorted[lo] : sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
  }

  function sparkline(rows, metric, escapeHtml) {
    const series = tailRows(rows, 90).map((row) => finite(row[metric]));
    const valid = series.filter((value) => value != null);
    if (valid.length < 3) return '';
    const min = Math.min(...valid);
    const max = Math.max(...valid);
    const span = (max - min) || 1;
    const width = 132;
    const height = 26;

    // The tile states a percentile ("17.1% of the last year") in words; the
    // sparkline drew 90 sessions with no reference at all, so the two never
    // met. Shade the trailing-year 10th-90th band behind the line and rule the
    // median, and the sentence becomes something you can see. Built from the
    // full trailing year on file, not from the 90 sessions drawn.
    const yearly = tailRows(rows, 252).map((row) => finite(row[metric]))
      .filter((value) => value != null).sort((a, b) => a - b);
    const band = (() => {
      if (yearly.length < 30) return '';
      const p10 = quantile(yearly, 0.1);
      const p50 = quantile(yearly, 0.5);
      const p90 = quantile(yearly, 0.9);
      const yOfValue = (v) => height - 3 - ((v - min) / span) * (height - 6);
      const top = Math.max(0, yOfValue(p90));
      const bottom = Math.min(height, yOfValue(p10));
      if (!(bottom > top)) return '';
      const mid = yOfValue(p50);
      return `<rect class="vol-spark-band" x="0" y="${top.toFixed(1)}" width="${width}" height="${(bottom - top).toFixed(1)}"></rect>
        ${mid >= 0 && mid <= height ? `<line class="vol-spark-median" x1="0" y1="${mid.toFixed(1)}" x2="${width}" y2="${mid.toFixed(1)}"></line>` : ''}`;
    })();
    let lastPoint = null;
    const segments = [];
    let current = [];
    series.forEach((value, index) => {
      if (value == null) {
        if (current.length > 1) segments.push(current.join(' '));
        current = [];
        return;
      }
      const x = (index / Math.max(1, series.length - 1)) * (width - 6) + 3;
      const y = height - 3 - ((value - min) / span) * (height - 6);
      current.push(`${x.toFixed(1)},${y.toFixed(1)}`);
      lastPoint = [x, y];
    });
    if (current.length > 1) segments.push(current.join(' '));
    if (!segments.length) return '';
    return `<svg class="vol-spark" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="${escapeHtml(`${METRIC_LABELS[metric] || metric} over the last ${series.length} sessions, ${min.toFixed(2)} to ${max.toFixed(2)}${band ? ', with the trailing-year 10th to 90th percentile band shaded behind it' : ''}`)}">
      ${band}
      ${segments.map((points) => `<polyline class="vol-spark-line" points="${points}"></polyline>`).join('')}
      ${lastPoint ? `<circle class="vol-spark-dot" cx="${lastPoint[0].toFixed(1)}" cy="${lastPoint[1].toFixed(1)}" r="2.6"></circle>` : ''}
    </svg>`;
  }

  // A metric whose as-of value is null must never render blank or borrow the
  // previous print's freshness. Return the honest fallback text instead.
  function lagNote(metric, entry, lagging, escapeHtml) {
    const lag = lagging[metric];
    if (finite(entry?.value) != null) return '';
    const lastValue = finite(entry?.last_value);
    if (lastValue == null) return '<small class="vol-lag">No print on record for this metric.</small>';
    const date = shortDate(lag?.last_value_date || entry?.last_value_date);
    return `<small class="vol-lag">No print as of today · last ${escapeHtml(level(lastValue))} on ${escapeHtml(date)} · ${escapeHtml(behindText(lag?.sessions_behind))}</small>`;
  }

  function tile(config) {
    const { label, value, sub, z, spark, note, escapeHtml } = config;
    return `<article class="vol-tile">
      <span class="vol-tile-label">${escapeHtml(label)}</span>
      <strong class="vol-tile-value">${escapeHtml(value)}</strong>
      ${sub ? `<span class="vol-tile-sub">${escapeHtml(sub)}</span>` : ''}
      ${z ? `<span class="vol-tile-z">${escapeHtml(z)}</span>` : ''}
      ${note || ''}
      ${spark || ''}
    </article>`;
  }

  // The term-state tile is the one place on this panel where a null in the
  // primary feed does not have to mean a null on the page. ^VIX3M went dark
  // after 2026-07-17 and this tile read "Unknown" for sixteen sessions while
  // the term-structure chart directly below it drew an unambiguous curve off a
  // chain snapshot that was current to the hour. The builder now resolves the
  // state off that same chain when the index feed is silent; this renders WHICH
  // basis answered, so a fallback reading can never be mistaken for a primary
  // one, and the tile still refuses to guess when the chain is inconclusive.
  function termTile(regime, slopeEntry, lagging, history, escapeHtml) {
    const isFallback = !!regime.term_state_is_fallback;
    const source = String(regime.term_state_source || 'none');
    const chain = regime.chain_term_detail || {};
    const state = String(regime.term_state || 'unknown').replace(/_/g, ' ');
    const chainRatio = finite(regime.chain_term_ratio ?? chain.ratio);

    const sub = isFallback
      ? `SPX chain ${finite(chain.near_dte) ?? '—'}d/${finite(chain.far_dte) ?? '—'}d ATM ${num(chainRatio, 3)}`
      : `VIX/VIX3M ${num(regime.slope_vix_3m ?? slopeEntry.value, 3)}`;

    // A fallback state carries no z-score: the chain series is two snapshots
    // deep, so there is no distribution to sit against. Say that instead of
    // showing the primary metric's stale z next to a chain-derived state.
    const z = isFallback
      ? 'no z-score — the chain series is too short to have a distribution'
      : `z1y ${zText(slopeEntry.z1y ?? slopeEntry.last_z1y)}`;

    const badge = isFallback
      ? '<b class="vol-fallback-flag">Chain fallback — VIX3M is dark</b>'
      : source === 'none'
        ? '<b class="vol-unknown-flag">No basis available</b>'
        : '';

    return `<article class="vol-tile ${isFallback ? 'is-fallback' : ''}">
      <span class="vol-tile-label">Term state</span>
      <strong class="vol-tile-value">${escapeHtml(state)}</strong>
      <span class="vol-tile-sub">${escapeHtml(sub)}</span>
      <span class="vol-tile-z">${escapeHtml(z)}</span>
      ${badge}
      <small class="vol-basis">${escapeHtml(String(regime.term_state_basis || 'no basis recorded'))}</small>
      ${lagNote('slope_vix_3m', slopeEntry, lagging, escapeHtml)}
      ${isFallback ? '' : sparkline(history, 'slope_vix_3m', escapeHtml)}
    </article>`;
  }

  function regimeTiles(volLatest, history, escapeHtml) {
    const metrics = volLatest?.metrics || {};
    const regime = volLatest?.regime || {};
    const lagging = volLatest?.coverage?.metrics_lagging || {};

    const vixEntry = metrics.vix || {};
    const vvixEntry = metrics.vvix_vix_ratio || {};
    const ivrvEntry = metrics.iv_rv_spread || {};
    const slopeEntry = metrics.slope_vix_3m || {};

    return `<div class="vol-tile-row">
      ${tile({
        escapeHtml,
        label: 'VIX cash',
        value: finite(vixEntry.value) == null ? num(vixEntry.last_value, 2) : num(vixEntry.value, 2),
        sub: `${pctText(regime.vix_pct1y ?? vixEntry.pct1y ?? vixEntry.last_pct1y)} of the last year`,
        z: `z1y ${zText(vixEntry.z1y ?? vixEntry.last_z1y)} · z5y ${zText(vixEntry.z5y ?? vixEntry.last_z5y)}`,
        note: lagNote('vix', vixEntry, lagging, escapeHtml),
        spark: sparkline(history, 'vix', escapeHtml),
      })}
      ${termTile(regime, slopeEntry, lagging, history, escapeHtml)}
      ${tile({
        escapeHtml,
        label: 'VVIX / VIX',
        value: finite(vvixEntry.value) == null ? num(vvixEntry.last_value, 3) : num(vvixEntry.value, 3),
        sub: `${pctText(vvixEntry.pct1y ?? vvixEntry.last_pct1y)} of the last year`,
        z: `z1y ${zText(vvixEntry.z1y ?? vvixEntry.last_z1y)} · z5y ${zText(vvixEntry.z5y ?? vvixEntry.last_z5y)}`,
        note: lagNote('vvix_vix_ratio', vvixEntry, lagging, escapeHtml),
        spark: sparkline(history, 'vvix_vix_ratio', escapeHtml),
      })}
      ${tile({
        escapeHtml,
        label: 'IV − RV spread',
        value: finite(ivrvEntry.value) == null ? num(ivrvEntry.last_value, 2) : num(ivrvEntry.value, 2),
        sub: `VIX less SPX 20-day realised (${num(regime.spx_rv20, 2)})`,
        z: `z1y ${zText(ivrvEntry.z1y ?? ivrvEntry.last_z1y)} · z5y ${zText(ivrvEntry.z5y ?? ivrvEntry.last_z5y)}`,
        note: lagNote('iv_rv_spread', ivrvEntry, lagging, escapeHtml),
        spark: sparkline(history, 'iv_rv_spread', escapeHtml),
      })}
    </div>`;
  }

  // The 14-row metric detail table was deleted: it restated, as numbers, the
  // strip that sat beside it. The heatmap's table view carries the same
  // z-scores in an accessible form, and a lagging feed still declares itself in
  // the banner, the tiles and the hatched cells.

  // ---------------------------------------------------------------------
  // (c2) forward conditioning
  //
  // The panel states that IV-RV sits at the 12.75th percentile of its year and
  // then stops, which leaves the only question a reader actually has -- so what
  // usually happens next? -- unanswered on a page holding ten years of the
  // answer. This shows the realised forward path of every historical session
  // that sat in the same bucket.
  //
  // The finding in the current sample is mostly NEGATIVE: at 21 sessions the
  // buckets are indistinguishable, and at 63 sessions the gradient is real but
  // small and rests on four to five independent windows per bucket. A panel
  // that dressed that up as a signal would be worse than no panel, so the
  // separation is computed here and reported as whatever it is.
  // ---------------------------------------------------------------------

  const BUCKET_LABELS = {
    cheapest: 'cheapest 20%', cheap: '20–40%', middle: '40–60%',
    rich: '60–80%', richest: 'richest 20%',
  };
  const BUCKET_ORDER = ['cheapest', 'cheap', 'middle', 'rich', 'richest'];

  function forwardPanel(conditioning, escapeHtml) {
    const byHorizon = conditioning?.buckets_by_horizon || {};
    const horizons = Object.keys(byHorizon).sort((a, b) => Number(a) - Number(b));
    if (!horizons.length) return '';
    const current = String(conditioning.current_bucket || '');
    const currentPct = finite(conditioning.current_pct1y);

    const tables = horizons.map((horizon) => {
      const block = byHorizon[horizon];
      const buckets = block.buckets || {};
      const drawdowns = BUCKET_ORDER
        .map((name) => finite(buckets[name]?.median_max_drawdown_pct))
        .filter((value) => value != null);
      // Does the bucketing separate anything? Spread of the bucket medians
      // against the typical bucket median. Stated, never assumed.
      const spread = drawdowns.length >= 2
        ? Math.max(...drawdowns) - Math.min(...drawdowns) : null;
      const typical = drawdowns.length
        ? Math.abs(drawdowns.reduce((a, b) => a + b, 0) / drawdowns.length) : null;
      const separates = spread != null && typical ? (spread / typical) > 0.35 : false;
      const minIndependent = Math.min(...BUCKET_ORDER
        .map((name) => finite(buckets[name]?.independent_windows) ?? 0));

      return `<div class="vol-forward-block">
        <h4>Next ${escapeHtml(String(block.horizon_sessions))} sessions</h4>
        <div class="vol-table-scroll"><table class="vol-matrix vol-forward-table">
          <caption>Realised outcome of every past session whose trailing IV−RV percentile fell in each band. ${escapeHtml(String(block.truncated_sessions))} recent sessions are excluded because their forward window has not finished.</caption>
          <thead><tr><th scope="col">IV−RV band</th><th scope="col">Median drawdown</th><th scope="col">Worst</th><th scope="col">Chance of &gt;5% drawdown</th><th scope="col">Median realised vol</th><th scope="col">Independent windows</th></tr></thead>
          <tbody>${BUCKET_ORDER.map((name) => {
            const row = buckets[name] || {};
            const isNow = name === current;
            const share = finite(row.share_drawdown_over_5pct);
            return `<tr class="${isNow ? 'is-current' : ''}">
              <th scope="row">${escapeHtml(BUCKET_LABELS[name] || name)}${isNow ? ' <b>← today</b>' : ''}</th>
              <td>${escapeHtml(num(row.median_max_drawdown_pct, 2))}%</td>
              <td>${escapeHtml(num(row.worst_max_drawdown_pct, 2))}%</td>
              <td>${share == null ? '—' : escapeHtml(`${(share * 100).toFixed(0)}%`)}</td>
              <td>${escapeHtml(num(row.median_realized_vol, 2))}</td>
              <td>${escapeHtml(num(row.independent_windows, 1))}<small class="vol-lag">${escapeHtml(String(row.observations || 0))} overlapping</small></td>
            </tr>`;
          }).join('')}</tbody>
        </table></div>
        <p class="vol-forward-read ${separates ? 'is-separating' : 'is-flat'}">${separates
          ? `<b>The bands separate.</b> Median drawdown ranges ${escapeHtml(spread.toFixed(2))} points across them, against a typical bucket median of ${escapeHtml(typical.toFixed(2))}%. With as few as ${escapeHtml(minIndependent.toFixed(1))} independent windows in the thinnest band this is a tendency in one sample, not an estimate with a confidence interval.`
          : `<b>The bands do not separate.</b> Median drawdown varies by only ${escapeHtml((spread ?? 0).toFixed(2))} points across the whole percentile range, which is noise at this sample size. At this horizon, knowing where IV−RV sits told you nothing useful about what followed.`}</p>
      </div>`;
    }).join('');

    return `<section class="risk-card vol-forward-card">
      <header class="vol-card-head"><div><h3>What followed readings like today's</h3>
        <p>Today IV−RV sits at <b>${currentPct == null ? 'an unknown percentile' : `the ${escapeHtml(currentPct.toFixed(1))}th percentile`}</b> of its trailing year${current ? ` — the <b>${escapeHtml(BUCKET_LABELS[current] || current)}</b> band` : ''}. Every past session in the same band is scored by what the S&amp;P actually did over the following weeks. Sessions are bucketed on the percentile that was knowable <em>on that date</em>, so the grouping carries no look-ahead; the outcome is pure hindsight, which is the point.</p></div></header>
      ${tables}
      <p class="vol-caveat"><b>Read the independent-windows column before anything else.</b> ${escapeHtml(String(conditioning.caveat || ''))} A band showing 300 observations and 4.8 independent windows has been measured four or five times, not three hundred. Nothing here is a forecast, and one market over one decade is a single sample.</p>
    </section>`;
  }

  // ---------------------------------------------------------------------
  // (d) SPX surface card
  // ---------------------------------------------------------------------

  function surfaceCard(surface, escapeHtml) {
    if (!surface || !(surface.tenors || []).length) {
      return `<section class="risk-card vol-surface-card"><h3>SPX surface snapshot</h3>
        <div class="risk-empty">No SPX surface snapshot is loaded. The panel renders without it; nothing here is inferred from the other feeds.</div></section>`;
    }

    const tenors = (surface.tenors || []).slice().sort((a, b) => (finite(a.dte) || 0) - (finite(b.dte) || 0));
    const gamma = surface.dealer_gamma_proxy || {};
    const quality = surface.quality || {};
    const rejected = quality.rows_rejected_by_reason || quality.rejected_by_reason || {};
    const spot = surface.spot || {};

    const rows = tenors.map((tenor) => {
      const drift = finite(tenor.dte_error_vs_target);
      return `<tr>
        <th scope="row">${escapeHtml(String(tenor.tenor || '—'))}</th>
        <td>${escapeHtml(String(finite(tenor.dte) == null ? '—' : finite(tenor.dte)))}${drift ? `<small class="vol-lag">target ${escapeHtml(String(finite(tenor.target_dte)))} · nearest listed</small>` : ''}</td>
        <td>${escapeHtml(shortDate(tenor.expiry))}</td>
        <td>${escapeHtml(ivPct(tenor.atm_iv))}</td>
        <td>${escapeHtml(signed(finite(tenor.rr_25d) == null ? null : finite(tenor.rr_25d) * 100, 2))}</td>
        <td>${escapeHtml(signed(finite(tenor.bf_25d) == null ? null : finite(tenor.bf_25d) * 100, 2))}</td>
        <td>${escapeHtml(num(tenor.put_skew_slope, 5))}<small class="vol-lag">R² ${escapeHtml(num(tenor.put_skew_r_squared, 3))}</small></td>
      </tr>`;
    }).join('');

    const thirtyDay = tenors.find((tenor) => finite(tenor.dte) === 30) || tenors.find((tenor) => tenor.tenor === '1m');
    const computed = finite(thirtyDay?.atm_iv);
    const feed = finite(spot.iv30_feed);
    const crossCheck = (computed == null || feed == null)
      ? '<p class="vol-note">No iv30 cross-check is available for this snapshot.</p>'
      : (() => {
        const computedPct = computed * 100;
        const gap = computedPct - feed;
        return `<p class="vol-validation"><b>iv30 cross-check</b> — the CBOE feed reports ${escapeHtml(feed.toFixed(3))} and the ${escapeHtml(String(finite(thirtyDay.dte)))}-dte ATM IV rebuilt here from the chain is ${escapeHtml(computedPct.toFixed(3))}. They agree to ${escapeHtml(Math.abs(gap).toFixed(3))} vol points (${escapeHtml(signed(gap, 3))}), which is an independent check that the strike interpolation is reading the chain correctly.</p>`;
      })();

    const rejectionText = Object.keys(rejected).length
      ? Object.entries(rejected).filter(([, count]) => finite(count)).map(([reason, count]) => `${String(reason).replace(/_/g, ' ')} ${count}`).join(' · ')
      : 'no rejection breakdown recorded';

    const flipStatus = String(gamma.gamma_flip_estimate_status || '').toLowerCase();

    return `<section class="risk-card vol-surface-card">
      <header class="vol-card-head"><div><span class="criticality-kicker">CBOE delayed quotes · ${escapeHtml(String(finite(surface.source?.delayed_minutes) == null ? '15' : finite(surface.source.delayed_minutes)))}-minute delay</span>
        <h3>SPX surface snapshot</h3></div>
        <span class="vol-tile-sub">spot ${escapeHtml(num(spot.value, 2))} · ${escapeHtml(shortDate(surface.as_of))}</span></header>

      <div class="vol-table-scroll"><table class="vol-surface-table">
        <caption>Per-tenor surface. The dte column is the ACTUAL listed days to expiry; where the nearest listed expiry misses the requested tenor the target is shown beneath it.</caption>
        <thead><tr><th scope="col">Tenor</th><th scope="col">Actual dte</th><th scope="col">Expiry</th><th scope="col">ATM IV</th><th scope="col">25Δ RR (pts)</th><th scope="col">25Δ BF (pts)</th><th scope="col">Put-skew slope</th></tr></thead>
        <tbody>${rows}</tbody></table></div>
      <p class="vol-note">Put-skew slope is ${escapeHtml(String(tenors[0]?.put_skew_slope_units || 'an IV fraction per unit of moneyness'))}. RR and BF are shown in vol points (the stored fractions × 100).</p>

      ${crossCheck}

      <div class="vol-gamma">
        <div class="vol-gamma-head"><span class="vol-tile-label">Dealer gamma proxy</span><b class="vol-estimate-flag">ESTIMATE — not an observation</b></div>
        <strong class="vol-gamma-value">${escapeHtml(finite(gamma.value) == null ? '—' : `${(finite(gamma.value) / 1e9).toFixed(2)}B`)}</strong>
        <span class="vol-tile-sub">${escapeHtml(String(gamma.units || ''))} · ${escapeHtml(String(finite(gamma.contracts_used) == null ? '—' : finite(gamma.contracts_used).toLocaleString()))} contracts · method ${escapeHtml(String(gamma.method || 'unknown'))}</span>
        <p class="vol-caveat"><b>Sign convention.</b> ${escapeHtml(String(gamma.sign_convention || 'No sign convention was recorded, so the sign of this number is uninterpretable.'))}</p>
        <p class="vol-caveat"><b>Open-interest caveat.</b> ${escapeHtml(String(gamma.oi_caveat || 'No open-interest caveat was recorded.'))}</p>
        <p class="vol-caveat"><b>Formula.</b> <code>${escapeHtml(String(gamma.formula || 'not recorded'))}</code> · call leg ${escapeHtml(finite(gamma.call_gamma_notional) == null ? '—' : `${(finite(gamma.call_gamma_notional) / 1e9).toFixed(1)}B`)} · put leg ${escapeHtml(finite(gamma.put_gamma_notional) == null ? '—' : `${(finite(gamma.put_gamma_notional) / 1e9).toFixed(1)}B`)}</p>
        <p class="vol-caveat"><b>Gamma flip level.</b> ${flipStatus === 'omitted'
          ? `Omitted. ${escapeHtml(String(gamma.gamma_flip_omitted_reason || 'No reason was recorded.'))}`
          : escapeHtml(String(gamma.gamma_flip_estimate_status || 'No gamma-flip status was recorded.'))}</p>
      </div>

      <dl class="risk-health vol-quality">
        <div><dt>Chain rows used</dt><dd>${escapeHtml(String(finite(quality.rows_used) == null ? '—' : finite(quality.rows_used).toLocaleString()))} of ${escapeHtml(String(finite(quality.rows_total) == null ? '—' : finite(quality.rows_total).toLocaleString()))}</dd></div>
        <div><dt>Rows rejected</dt><dd>${escapeHtml(String(finite(quality.rows_rejected) == null ? '—' : finite(quality.rows_rejected).toLocaleString()))} · ${escapeHtml(rejectionText)}</dd></div>
        <div><dt>Chains / tenors</dt><dd>${escapeHtml(String(finite(quality.n_chains) ?? '—'))} chains · ${escapeHtml(String(finite(quality.tenors_resolved) ?? tenors.length))} tenors resolved</dd></div>
        <div><dt>Snapshot state</dt><dd>${escapeHtml(String(surface.quality_state || 'unknown'))} · fetch ${escapeHtml(String(surface.fetch_status || 'unknown'))}</dd></div>
      </dl>
    </section>`;
  }

  // ---------------------------------------------------------------------
  // panel
  // ---------------------------------------------------------------------

  // Two different conditions used to share one banner, and the more serious one
  // was the quieter of the two. A feed that is a session late (^SKEW most
  // weeks) is routine. A feed that has printed nothing for three-plus sessions
  // is DEAD, and the request that fetched it still returned 200 — that is only
  // visible in the column, which is why the builder now flags it separately.
  // Ranking them together buried five dead feeds among eight "lagging" ones.
  function feedBanners(volLatest, escapeHtml) {
    const lagging = volLatest?.coverage?.metrics_lagging || {};
    const dark = volLatest?.coverage?.metrics_dark || {};
    const darkNames = Object.keys(dark).filter((metric) => METRIC_LABELS[metric]);
    const laggingOnly = Object.keys(lagging).filter((metric) => !dark[metric]);

    const darkBanner = darkNames.length
      ? `<p class="vol-dark-banner"><b>Dark feeds (${darkNames.length}) — not merely late.</b> ${escapeHtml(darkNames.sort().map((metric) => {
        const entry = dark[metric] || {};
        return `${METRIC_LABELS[metric] || metric} — last print ${shortDate(entry.last_value_date)}, ${behindText(entry.sessions_dark)}`;
      }).join(' · '))}. The vendor answered every one of these requests and returned a series that simply stops, so no fetch error was ever raised; the gap is only visible in the data. This snapshot is marked <b>stale</b> and these symbols are excluded from the healthy list.</p>`
      : '';

    const lagBanner = laggingOnly.length
      ? `<p class="vol-lag-banner"><b>Lagging feeds (${laggingOnly.length}).</b> ${escapeHtml(laggingOnly.sort().map((metric) => {
        const lag = lagging[metric] || {};
        return `${METRIC_LABELS[metric] || metric} — last print ${shortDate(lag.last_value_date)}, ${behindText(lag.sessions_behind)}`;
      }).join(' · '))}. These metrics have no print for the snapshot date; their tiles, rows and heatmap cells show the absence rather than carrying the previous value forward.</p>`
      : '';

    return `${darkBanner}${lagBanner}`;
  }

  function renderVolPanel(volLatest, volHistory, surfaceLatest, options = {}) {
    const escapeHtml = options.escapeHtml || escapeFallback;
    const history = Array.isArray(volHistory) ? volHistory : [];
    const surfaceHistory = Array.isArray(options.surfaceHistory) ? options.surfaceHistory : [];

    if (!volLatest && !history.length && !surfaceLatest) {
      return `<section class="vol-panel"><div class="vol-panel-head"><div>
          <span class="criticality-kicker">Volatility surface · research only</span>
          <h2>Volatility regime &amp; SPX surface</h2></div></div>
        <div class="risk-empty">No volatility feed is loaded. vol_metrics_latest.json, vol_metrics_history.jsonl and spx_surface_latest.json were all unreachable, so this panel is showing nothing rather than guessing. The rest of the risk page is unaffected.</div>
      </section>`;
    }

    const lagging = volLatest?.coverage?.metrics_lagging || {};
    const coverage = volLatest?.coverage || {};
    const priorSurface = surfaceHistory
      .filter((row) => row && row.as_of && row.as_of !== surfaceLatest?.as_of)
      .sort((a, b) => String(a.as_of).localeCompare(String(b.as_of)))
      .pop() || null;

    const heatWindow = tailRows(history, HEATMAP_SESSIONS);

    return `<section class="vol-panel">
      <div class="vol-panel-head">
        <div><span class="criticality-kicker">Volatility surface · research only</span>
          <h2>Volatility regime &amp; SPX surface</h2>
          <p>Trailing z-scores for the listed vol complex, the current SPX at-the-money term structure, and a delayed-chain surface snapshot. Nulls are real — a missing vendor print is drawn as an absence, never as an average.</p></div>
        <div class="vol-panel-state">
          <strong>${escapeHtml(shortDate(volLatest?.as_of) || 'no snapshot')}</strong>
          <small>${escapeHtml(String(volLatest?.quality_state || 'unknown'))} · ${escapeHtml(String(finite(coverage.rows) == null ? '—' : finite(coverage.rows).toLocaleString()))} sessions on file</small>
        </div>
      </div>

      ${feedBanners(volLatest, escapeHtml)}

      ${volLatest ? regimeTiles(volLatest, history, escapeHtml) : ''}

      <section class="risk-card vol-heat-card">
        <header class="vol-card-head"><div><h3>Z-score history · ${escapeHtml(String(METRIC_ORDER.length))} metrics × ${escapeHtml(String(heatWindow.length))} sessions</h3>
          <p>Each cell is one metric on one session, coloured by its trailing one-year z-score. Blue is below the one-year mean, red is above, grey is within half a sigma of it. A hatched cell means the vendor did not print that day — it is deliberately not the same as zero. Hover any cell for the exact 1y and 5y z. Only metrics that are not near-copies of VIX are drawn: the nine dropped rows ran 0.92–0.97 correlated with a row that stays, or were arithmetic derivatives of one.</p></div></header>
        ${heatLegend(escapeHtml)}
        ${heatmap(history, lagging, escapeHtml)}
        ${longHeatmap(history, escapeHtml)}
        ${heatTable(history, escapeHtml)}
      </section>

      <section class="risk-card vol-term-card"><header class="vol-card-head"><div><h3>SPX term structure</h3>
        <p>At-the-money implied vol by actual days to expiry from the latest chain snapshot. The curve's state — contango or backwardation — is the tile above; this is the shape behind it.</p></div></header>
        ${termStructure(surfaceLatest, priorSurface, volLatest, escapeHtml)}</section>

      ${volLatest?.forward_conditioning ? forwardPanel(volLatest.forward_conditioning, escapeHtml) : ''}

      ${surfaceCard(surfaceLatest, escapeHtml)}

      <p class="vol-footer">Research only. Z-scores describe where a metric sits against its own trailing distribution — they are not forecasts, and a two-sigma reading is a description of rarity, not a signal to act. The surface snapshot comes from a 15-minute-delayed public chain with start-of-day open interest, and the dealer-gamma figure is a proxy built on an assumed dealer sign convention, not observed positioning. Nothing on this panel has trading authority.</p>
    </section>`;
  }

  global.VolViz = { renderVolPanel, METRIC_ORDER, METRIC_LABELS, zBin };
})(typeof window !== 'undefined' ? window : globalThis);
