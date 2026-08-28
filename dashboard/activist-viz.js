/** Activist long/short feed panel for portfolio dashboard. */
(function (global) {
  function sideBadge(side) {
    if (side === 'long') return 'badge-ok';
    if (side === 'short') return 'badge-bad';
    return 'badge-us';
  }

  function tierBadge(tier) {
    if (tier === 'signal') return 'badge-ok';
    if (tier === 'noise') return 'badge-warn';
    return 'badge-us';
  }

  function formatReportDate(row) {
    const date = row?.report_date;
    if (!date) return '—';
    const precision = row?.date_precision || 'day';
    if (precision === 'month' && /^\d{4}-\d{2}$/.test(String(date).slice(0, 7))) {
      const [year, month] = String(date).slice(0, 7).split('-');
      const monthName = new Date(Number(year), Number(month) - 1, 1).toLocaleString(undefined, { month: 'short' });
      return `${monthName} ${year}`;
    }
    if (precision === 'year' && /^\d{4}/.test(String(date))) {
      return String(date).slice(0, 4);
    }
    return String(date).slice(0, 10);
  }

  function dateTitle(row) {
    const bits = [];
    if (row?.report_date) bits.push(`Date: ${row.report_date}`);
    if (row?.date_source) bits.push(`Source: ${row.date_source}`);
    if (row?.date_precision && row.date_precision !== 'day') bits.push(`Precision: ${row.date_precision}`);
    return bits.join(' · ');
  }

  function firmDisplay(row) {
    const name = row?.firm_name || row?.firm_id || '—';
    const persons = row?.reporting_persons || [];
    if (persons.length <= 1) return name;
    const extra = persons.length - 1;
    return `${name} <span class="tier-sub">(+${extra})</span>`;
  }

  function sourceBadgeLabel(source) {
    if (source === 'sec_edgar') return 'SEC';
    if (source === 'publisher_site') return 'Site';
    if (source === 'press_wire') return 'Wire';
    if (source === 'local') return 'Local';
    if (source === 'short_reports_md') return 'Short MD';
    return source || '—';
  }

  function sourceLinkLabel(row) {
    if (row.source === 'sec_edgar') return 'SEC filing';
    if (row.source === 'press_wire') {
      if ((row.filing_class || '').includes('letter') || (row.title || '').toLowerCase().includes('letter')) {
        return 'Open letter';
      }
      return 'Press wire';
    }
    if (row.source === 'publisher_site') return 'Firm site';
    return 'Original';
  }

  function fileStatusBadge(row) {
    if (row?.body_verified === false) {
      return ' <span class="badge badge-warn" title="Ticker not found in document body — likely false positive">unverified</span>';
    }
    if (row?.file_exists === false && row?.needs_file) {
      return ' <span class="badge badge-warn" title="Publisher link only; local copy missing">no file</span>';
    }
    if (row?.weak_match) {
      return ' <span class="badge badge-warn" title="Same report attached to many tickers or weak alias match">weak match</span>';
    }
    return '';
  }

  function materialityCell(row, escapeHtml) {
    const score = row?.materiality;
    if (score == null) return '<td class="mono">—</td>';
    const tier = row?.tier || 'context';
    const pct = Math.max(2, Math.min(100, Number(score) || 0));
    const scoreExplain = Object.entries(row?.materiality_components || {})
      .map(([key, value]) => `${key} ${Number(value).toFixed(2)}`)
      .join(' · ');
    const stake = row?.stake_percent != null ? ` · stake ${row.stake_percent}%` : '';
    return `
      <td title="${escapeHtml(`Materiality ${score}/100 · tier: ${tier}${stake}`)}">
        <span class="mono">${score}</span>
        <span class="badge ${tierBadge(tier)}" style="margin-left:4px">${escapeHtml(tier)}</span>
        ${scoreExplain ? `<span class="tier-sub" title="${escapeHtml(scoreExplain)}"> why</span>` : ''}
        <div style="height:3px;margin-top:3px;border-radius:2px;background:rgba(148,163,184,.18);max-width:72px">
          <div style="height:100%;width:${pct}%;border-radius:2px;background:${tier === 'signal' ? '#34d399' : tier === 'noise' ? '#64748b' : '#818cf8'}"></div>
        </div>
      </td>`;
  }

  function renderSummary(summary) {
    const s = summary || {};
    return `
      <div class="darwin-grid">
        <div class="metric"><div class="k">Signal</div><div class="v mono">${s.signal_count || 0}</div></div>
        <div class="metric"><div class="k">Context</div><div class="v mono">${s.context_count || 0}</div></div>
        <div class="metric"><div class="k">Noise</div><div class="v mono">${s.noise_count || 0}</div></div>
        <div class="metric"><div class="k">Human review</div><div class="v mono">${s.triage_human_review || 0}</div></div>
        <div class="metric"><div class="k">Auto-passive</div><div class="v mono">${s.triage_auto_passive || 0}</div></div>
        <div class="metric"><div class="k">Long</div><div class="v mono">${s.long_count || 0}</div></div>
        <div class="metric"><div class="k">Short</div><div class="v mono">${s.short_count || 0}</div></div>
        <div class="metric"><div class="k">Tickers with hits</div><div class="v mono">${s.tickers_with_hits || 0}</div></div>
        <div class="metric"><div class="k">Broken links dropped</div><div class="v mono">${s.broken_link_count || 0}</div></div>
        <div class="metric"><div class="k">Body unverified</div><div class="v mono">${s.body_unverified_count || 0}</div></div>
        <div class="metric"><div class="k">Targets rejected</div><div class="v mono">${s.target_unverified_excluded_count || 0}</div></div>
        <div class="metric"><div class="k">Non-reports rejected</div><div class="v mono">${s.non_report_excluded_count || 0}</div></div>
        <div class="metric"><div class="k">Duplicates removed</div><div class="v mono">${s.canonical_duplicate_count || 0}</div></div>
        <div class="metric"><div class="k">Cross-ticker conflicts</div><div class="v mono">${s.cross_ticker_conflict_count || 0}</div></div>
      </div>`;
  }

  // Schedule 13D covers any >5% holder with control intent, so a raw feed mixes
  // founders, strategic buyers and PE sponsors in with activists. Default to
  // activists; the rest stay one click away rather than being discarded.
  const FILER_CLASS_TABS = [
    { id: 'activist', label: 'Activists', title: 'Filers matched to the activist registry' },
    { id: 'strategic', label: 'Strategic', title: 'Operating companies taking a stake' },
    { id: 'sponsor', label: 'Sponsors', title: 'PE / holdco vehicles' },
    { id: 'insider', label: 'Insiders', title: 'Founders and other natural persons' },
    { id: 'all', label: 'All filers', title: 'No filer-type filter' },
  ];

  function renderFilters(state) {
    const review = state.reviewFilter || '';
    const tier = state.tier || 'signal';
    const view = state.view || 'active';
    const sortMode = state.sortMode || 'materiality';
    const filerClass = state.filerClass || 'activist';
    return `
      <div class="toolbar" style="margin:12px 0 0">
        <button type="button" class="filter-btn${view === 'active' ? ' active' : ''}" data-activist-view="active">Active campaigns</button>
        <button type="button" class="filter-btn${view === 'short' ? ' active' : ''}" data-activist-view="short">Short reports</button>
        <button type="button" class="filter-btn${view === 'ownership' ? ' active' : ''}" data-activist-view="ownership">Ownership filings</button>
        <button type="button" class="filter-btn${view === 'review' ? ' active' : ''}" data-activist-view="review">Review queue</button>
        <button type="button" class="filter-btn${view === 'discovery' ? ' active' : ''}" data-activist-view="discovery" title="Campaigns by firms we track, at companies we do not hold">Off-book campaigns</button>
        <label class="tier-sub" for="activist-sort">Sort</label>
        <select id="activist-sort" class="search" style="max-width:150px;padding:6px 9px">
          <option value="materiality"${sortMode === 'materiality' ? ' selected' : ''}>Materiality</option>
          <option value="newest"${sortMode === 'newest' ? ' selected' : ''}>Newest</option>
        </select>
      </div>
      <div class="toolbar" style="margin:12px 0">
        <input class="search" id="activist-search" placeholder="Filter ticker, firm, title…" value="${state.escapeHtml(state.search || '')}" />
        <button type="button" class="filter-btn${tier === 'signal' && !review ? ' active' : ''}" data-activist-tier="signal">Signal</button>
        <button type="button" class="filter-btn${tier === 'all' && !review ? ' active' : ''}" data-activist-tier="all">All</button>
        <button type="button" class="filter-btn${tier === 'noise' && !review ? ' active' : ''}" data-activist-tier="noise">Noise</button>
        <span class="tier-sub" style="margin:0 4px">·</span>
        <button type="button" class="filter-btn${state.side === 'long' ? ' active' : ''}" data-activist-side="long">Long</button>
        <button type="button" class="filter-btn${state.side === 'short' ? ' active' : ''}" data-activist-side="short">Short</button>
        <button type="button" class="filter-btn${review === 'needs_filer_review' ? ' active' : ''}" data-activist-review="needs_filer_review">Needs filer review</button>
        <button type="button" class="filter-btn${review === 'missing_file' ? ' active' : ''}" data-activist-review="missing_file">Missing file</button>
        <button type="button" class="filter-btn${review === 'weak_match' ? ' active' : ''}" data-activist-review="weak_match">Weak match</button>
      </div>
      <div class="toolbar" style="margin:0 0 12px">
        <span class="tier-sub">Filer</span>
        ${FILER_CLASS_TABS.map(t => `<button type="button" class="filter-btn${filerClass === t.id ? ' active' : ''}" data-activist-filer="${t.id}" title="${state.escapeHtml(t.title)}">${t.label}</button>`).join('')}
      </div>`;
  }

  function isPdfReport(row) {
    if (row?.local_is_pdf) return true;
    const path = row?.local_pdf || '';
    return /\.pdf(\?|#|$)/i.test(String(path));
  }

  function renderReportLinks(row, linkHtml) {
    const parts = [];
    if (row.source_url && row.source_url_ok !== false) {
      parts.push(linkHtml(row.source_url, sourceLinkLabel(row), 'source-open-link'));
    }
    if (row.file_exists !== false && row.github_url) {
      const label = isPdfReport(row) ? 'Archived PDF' : 'Archived copy';
      parts.push(linkHtml(row.github_url, label, 'source-open-link'));
    }
    if (!parts.length) {
      return '<span class="tier-sub" title="No working document link">no document</span>';
    }
    return parts.join(' ');
  }

  function sortFeedRows(rows, sortMode) {
    return rows.slice().sort((a, b) => {
      const da = a.report_date || '';
      const db = b.report_date || '';
      if (sortMode === 'newest' && da !== db) return db.localeCompare(da);
      const ma = a.materiality == null ? -1 : Number(a.materiality);
      const mb = b.materiality == null ? -1 : Number(b.materiality);
      if (ma !== mb) return mb - ma;
      if (da !== db) return db.localeCompare(da);
      const ta = (a.ticker || '').localeCompare(b.ticker || '');
      if (ta) return ta;
      const fa = (a.firm_name || a.firm_id || '').localeCompare(b.firm_name || b.firm_id || '');
      if (fa) return fa;
      return (a.title || '').localeCompare(b.title || '');
    });
  }

  function groupCampaigns(rows) {
    const groups = new Map();
    const order = [];
    rows.forEach(r => {
      const key = r.campaign_id || `${r.ticker || ''}|${r.firm_id || ''}|${r.side || ''}`;
      if (!groups.has(key)) {
        groups.set(key, []);
        order.push(key);
      }
      groups.get(key).push(r);
    });
    return order.map(key => ({ key, rows: groups.get(key) }));
  }

  function renderFeedRow(r, state, extra) {
    const groupBadge = r.campaign_group_size > 1
      ? ` <span class="badge badge-purple" title="Latest in ${r.campaign_group_size}-filing campaign window">×${r.campaign_group_size}</span>`
      : '';
    const reviewBadge = r.needs_filer_review
      ? ' <span class="badge badge-warn" title="Filer unresolved or low confidence">review</span>'
      : '';
    return `
      <tr class="clickable-row${extra?.muted ? ' campaign-child' : ''}" data-select-ticker="${state.escapeHtml(r.ticker || '')}" tabindex="0" role="link" aria-label="Open ${state.escapeHtml(r.ticker || 'activist')} research"${extra?.muted ? ' style="opacity:.65"' : ''}>
        <td class="mono" title="${state.escapeHtml(dateTitle(r))}">${state.escapeHtml(formatReportDate(r))}${r.date_precision && r.date_precision !== 'day' ? ' <span class="tier-sub">~</span>' : ''}</td>
        <td class="mono">${state.escapeHtml(r.ticker || '—')}</td>
        ${materialityCell(r, state.escapeHtml)}
        <td><span class="badge ${sideBadge(r.side)}">${state.escapeHtml(r.side || '—')}</span></td>
        <td><div>${firmDisplay(r)}${reviewBadge}${fileStatusBadge(r)}</div><div class="tier-sub">Target: ${state.escapeHtml(r.target_company || r.ticker || '')} · ${state.escapeHtml(r.target_match_evidence || 'unverified')} · ${state.escapeHtml((r.report_kind || 'activist_report').replaceAll('_', ' '))}</div></td>
        <td>${state.escapeHtml(r.title || '—')}${groupBadge}${extra?.expander || ''}</td>
        <td><span class="badge badge-us" title="${state.escapeHtml(r.source || '')}">${state.escapeHtml(sourceBadgeLabel(r.source))}</span>${r.status === 'new' ? ' <span class="badge badge-warn">new</span>' : ''}${r.filing_class === 'open_letter' ? ' <span class="badge badge-purple">letter</span>' : ''}</td>
        <td>${renderReportLinks(r, state.linkHtml)}</td>
      </tr>`;
  }

  function renderFeed(feed, state) {
    const q = (state.search || '').trim().toLowerCase();
    const tier = state.tier || 'signal';
    const view = state.view || 'active';
    let rows = Array.isArray(feed) ? feed.slice() : [];
    if (view === 'short') {
      rows = rows.filter(r => r.report_kind === 'short_report' && !r.needs_filer_review);
    } else if (view === 'ownership') {
      rows = rows.filter(r => r.report_kind === 'ownership_filing' && !r.needs_filer_review);
    } else if (view === 'review') {
      rows = rows.filter(r => r.needs_filer_review || !r.target_verified || r.weak_match || r.body_verified === false);
    } else {
      rows = rows.filter(r => !r.needs_filer_review && (r.tier === 'signal' || Number(r.campaign_group_size || 1) > 1));
    }
    if (state.reviewFilter === 'needs_filer_review') {
      rows = rows.filter(r => r.needs_filer_review);
    } else if (state.reviewFilter === 'missing_file') {
      rows = rows.filter(r => r.needs_file || r.file_exists === false);
    } else if (state.reviewFilter === 'weak_match') {
      rows = rows.filter(r => r.weak_match || r.body_verified === false);
    } else if (view !== 'review') {
      if (tier === 'signal') {
        rows = rows.filter(r => (r.tier || 'context') === 'signal');
      } else if (tier === 'noise') {
        rows = rows.filter(r => (r.tier || 'context') === 'noise');
      }
      if (state.side && state.side !== 'all') {
        rows = rows.filter(r => r.side === state.side);
      }
    }
    const filerClass = state.filerClass || 'activist';
    if (filerClass !== 'all' && view !== 'review') {
      rows = rows.filter(r => (r.filer_class || 'unknown') === filerClass);
    }
    if (q) {
      rows = rows.filter(r =>
        [r.ticker, r.target_company, r.firm_name, r.firm_id, r.title, r.source, r.report_kind, r.target_match_evidence, ...(r.reporting_persons || [])]
          .join(' ')
          .toLowerCase()
          .includes(q)
      );
    }
    rows = sortFeedRows(rows, state.sortMode || 'materiality');
    if (!rows.length) {
      if (filerClass !== 'all' && !q) {
        return `<div class="empty">No ${state.escapeHtml(filerClass)} filings match. Try <strong>All filers</strong> — 13D covers founders, strategic buyers and sponsors too.</div>`;
      }
      return tier === 'signal' && !q && !state.reviewFilter
        ? '<div class="empty">No signal-tier activist reports right now. Switch to All to browse context and noise tiers.</div>'
        : '<div class="empty">No activist reports match your filters.</div>';
    }
    const expanded = state.expandedGroups || new Set();
    const groups = groupCampaigns(rows);
    let rendered = 0;
    const bodyHtml = [];
    for (const group of groups) {
      if (rendered >= 300) break;
      const primary = group.rows[0];
      const rest = group.rows.slice(1);
      const isOpen = expanded.has(group.key);
      let expander = '';
      if (rest.length) {
        expander = ` <button type="button" class="filter-btn" style="padding:1px 8px;font-size:11px" data-activist-group="${state.escapeHtml(group.key)}" title="${rest.length} more filing(s) from this campaign">${isOpen ? '− collapse' : `+${rest.length} more`}</button>`;
      }
      bodyHtml.push(renderFeedRow(primary, state, { expander }));
      rendered += 1;
      if (isOpen) {
        for (const child of rest) {
          if (rendered >= 300) break;
          bodyHtml.push(renderFeedRow(child, state, { muted: true }));
          rendered += 1;
        }
      }
    }
    const hiddenCount = rows.length - rendered;
    return `
      <table class="darwin-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Ticker</th>
            <th>Materiality</th>
            <th>Side</th>
            <th>Firm</th>
            <th>Title</th>
            <th>Source</th>
            <th>Links</th>
          </tr>
        </thead>
        <tbody>
          ${bodyHtml.join('')}
        </tbody>
      </table>
      ${hiddenCount > 0 ? `<p class="tier-sub">${hiddenCount} more reports collapsed into campaigns or outside the table window.</p>` : ''}`;
  }

  function renderTickerActivistSection(activist, helpers) {
    if (!activist || (!activist.long_count && !activist.short_count)) return '';
    const latest = activist.latest || {};
    return `
      <div class="detail-section">
        <h3>Activist reports</h3>
        <div class="metric-grid metric-grid-3">
          <div class="metric"><div class="k">Signal</div><div class="v mono">${activist.signal_count || 0}</div></div>
          <div class="metric"><div class="k">Long / Short</div><div class="v mono">${activist.long_count || 0} / ${activist.short_count || 0}</div></div>
          <div class="metric"><div class="k">Latest</div><div class="v">${helpers.escapeHtml(latest.firm_name || '—')} · ${helpers.escapeHtml(latest.date || '—')}</div></div>
        </div>
        ${activist.has_unreconciled ? '<div class="tier-sub"><span class="badge badge-warn">Unreconciled hits</span> — run Milly adversarial pass.</div>' : ''}
      </div>`;
  }

  function renderActivistBadge(activist) {
    if (!activist) return '<span class="tier-sub">—</span>';
    const longN = activist.long_count || 0;
    const shortN = activist.short_count || 0;
    if (!longN && !shortN) return '<span class="tier-sub">—</span>';
    const signal = activist.signal_count
      ? ` <span class="badge badge-ok" title="Signal-tier reports">${activist.signal_count}!</span>`
      : '';
    const dot = activist.has_unreconciled ? ' <span class="badge badge-warn" title="Unreconciled">!</span>' : '';
    return `<span class="mono">L${longN}/S${shortN}</span>${signal}${dot}`;
  }

  function renderDiscovery(discovery, state) {
    const esc = state.escapeHtml;
    if (!discovery) {
      return '<div class="empty">Filer discovery has not run yet. Run: <code>python _system/scripts/sec_filer_discovery.py</code></div>';
    }
    const rows = Array.isArray(discovery.rows) ? discovery.rows.slice() : [];
    const q = (state.search || '').trim().toLowerCase();
    let shown = rows.filter(r => r.issuer_name);
    if (q) {
      shown = shown.filter(r =>
        [r.firm_name, r.firm_id, r.issuer_name, r.form, r.filing_date].join(' ').toLowerCase().includes(q)
      );
    }
    shown.sort((a, b) => String(b.filing_date || '').localeCompare(String(a.filing_date || '')));
    if (!shown.length) {
      return '<div class="empty">No off-book campaigns match your filter.</div>';
    }
    const unresolved = (discovery.unresolved_firms || []).length;
    return `
      <p class="tier-sub" style="margin-bottom:10px">
        What the firms we track filed anywhere &mdash; not just on names we hold.
        ${discovery.row_count || 0} filings from ${discovery.resolved_firm_count || 0}/${discovery.firm_count || 0} firms
        &middot; ${discovery.off_book_count || 0} at issuers outside the book
        ${unresolved ? `&middot; <span style="color:var(--accent-amber)">${unresolved} firm(s) unresolved</span>` : ''}
      </p>
      <table class="darwin-table">
        <thead><tr><th>Date</th><th>Firm</th><th>Form</th><th>Issuer</th><th>Stake</th><th></th></tr></thead>
        <tbody>
          ${shown.slice(0, 200).map(r => `
            <tr>
              <td class="mono">${esc(r.filing_date || '—')}</td>
              <td>${esc(r.firm_name || r.firm_id || '—')}</td>
              <td class="mono" style="font-size:11px">${esc(r.form || '—')}</td>
              <td>${esc(r.issuer_name || '—')}</td>
              <td class="mono">${r.stake_percent != null ? `${Number(r.stake_percent).toFixed(1)}%` : '—'}</td>
              <td>${r.index_url ? state.linkHtml(r.index_url, 'EDGAR', 'source-open-link') : ''}</td>
            </tr>`).join('')}
        </tbody>
      </table>
      ${shown.length > 200 ? `<p class="tier-sub">${shown.length - 200} more &mdash; refine the filter</p>` : ''}`;
  }

  function renderActivistPanel(feedDoc, state) {
    if (!feedDoc) {
      return '<div class="empty">Activist feed not built. Run: python _system/scripts/build_activist_feed.py</div>';
    }
    return `
      <h2 style="margin-bottom:8px">Activist reports</h2>
      <div class="subhead">Materiality-ranked activist filings and short reports · signal tier shown by default</div>
      ${renderSummary(feedDoc.summary)}
      ${renderFilters(state)}
      ${(state.view || 'active') === 'discovery'
        ? renderDiscovery(state.discovery, state)
        : renderFeed([...(feedDoc.feed || []), ...(feedDoc.review_queue || [])], state)}
      <div class="tier-sub" style="margin-top:12px">Last scan: ${state.escapeHtml(feedDoc.last_scan || feedDoc.generated_at || '—')}</div>`;
  }

  global.ActivistViz = {
    renderActivistPanel,
    renderTickerActivistSection,
    renderActivistBadge,
  };
})(window);
