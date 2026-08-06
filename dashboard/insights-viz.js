/** Insights tab + persona lens detail rendering for portfolio dashboard. */
(function (global) {
  const STANCE_BADGE = {
    accumulate: 'badge-ok',
    core: 'badge-ok',
    hold: 'badge-us',
    watch: 'badge-warn',
    pass: 'badge-bad',
    trim: 'badge-bad',
    exit: 'badge-bad',
    pending: 'badge-warn',
    silent: 'badge-warn',
    add: 'badge-ok',
    discussed: 'badge-us',
  };

  const SOURCE_LABEL = {
    superinvestor_letter: 'Letter',
    podcast_episode: 'Podcast',
    filing: 'Filing',
    earnings: 'Earnings',
    macro: 'Macro',
    insider: 'Insider',
    sumzero_research: 'SumZero',
    third_party: 'VIC / third party',
    company_document: 'Company',
    research: 'Research',
    pdf: 'Other PDFs',
    theme: 'Theme',
    news: 'News',
  };

  const CATALOG_SOURCE_LABEL = {
    superinvestor_letter: 'Letters',
    podcast_episode: 'Podcasts',
    company_document: 'Company',
    third_party: 'VIC / third party',
    sumzero_research: 'SumZero',
    research: 'Research',
    dropbox_ingestion: 'Dropbox ingestion',
    pdf: 'Other PDFs',
  };

  const CATALOG_SOURCE_SORT = {
    superinvestor_letter: 0,
    company_document: 1,
    third_party: 2,
    sumzero_research: 3,
    research: 4,
    dropbox_ingestion: 5,
    pdf: 6,
  };

  const AXIS_LABEL = {
    fundamentals: 'fundamentals',
    ownership: 'ownership',
    catalyst: 'catalyst',
    risk: 'risk',
    macro: 'macro',
    capital_allocation: 'capital allocation',
    variant_view: 'variant view',
    context: 'context',
  };

  function fmtPct(v, digits) {
    if (v == null || Number.isNaN(v)) return '—';
    const d = digits != null ? digits : (Math.abs(v % 1) > 0.01 ? 1 : 0);
    return `${Number(v).toFixed(d)}%`;
  }

  function isDriveGoogleHost(hostname) {
    const host = String(hostname || '').toLowerCase();
    return host === 'drive.google.com' || host.endsWith('.drive.google.com');
  }

  function evidenceLabel(ref, fallback) {
    const clean = (ref || '').split('#')[0].toLowerCase();
    const url = String(ref || '');
    if (url.startsWith('http')) {
      try {
        const parsed = new URL(url);
        if (isDriveGoogleHost(parsed.hostname) && parsed.pathname.includes('/drive/folders/')) return 'Drive folder';
        if (isDriveGoogleHost(parsed.hostname)) return 'PDF';
      } catch (_) {
        /* fall through */
      }
    }
    if (fallback && fallback !== 'Text') return fallback;
    if (clean.endsWith('.pdf')) return 'PDF';
    if (clean.endsWith('.htm') || clean.endsWith('.html')) return 'HTML';
    if (clean.startsWith('http')) return 'Open';
    if (clean.endsWith('.json')) return 'Index';
    if (fallback) return fallback;
    return 'Open';
  }

  function evidenceLink(ref, linkHtml, ghRepo, label) {
    if (!ref) return '—';
    const text = evidenceLabel(ref, label);
    if (String(ref).startsWith('http')) return linkHtml(ref, text, 'source-open-link');
    return linkHtml(`https://github.com/${ghRepo}/blob/main/${ref}`, text, 'source-open-link');
  }

  function recordEvidenceLink(row, linkHtml, ghRepo) {
    const url = row?.evidence_url;
    if (url) {
      return linkHtml(url, evidenceLabel(url, row?.evidence_label), 'source-open-link');
    }
    const ref = row?.source_document || row?.evidence_ref || row?.source_file;
    if (!ref) return '—';
    return evidenceLink(ref, linkHtml, ghRepo, row?.evidence_label);
  }

  function sourceBadgeClass(source) {
    if (source === 'news') return 'badge-ok';
    if (source === 'superinvestor_letter') return 'badge-purple';
    if (source === 'third_party' || source === 'sumzero_research') return 'badge-us';
    if (source === 'insider') return 'badge-warn';
    return 'badge-us';
  }

  function cleanText(value, limit = 220) {
    const text = String(value || '').replace(/\s+/g, ' ').trim();
    return text.length > limit ? text.slice(0, limit - 1).trim() + '...' : text;
  }

  function renderDecisionSummary(ds, humanReview, helpers) {
    if (!ds) return '';
    const { escapeHtml } = helpers;
    const stanceBadge = STANCE_BADGE[ds.stance] || 'badge-warn';
    let stanceHtml = `<span class="badge ${stanceBadge}">${escapeHtml(ds.stance || '—')}</span>`;
    if (ds.stance_source === 'approved' && ds.lens_stance && ds.lens_stance !== ds.stance) {
      stanceHtml += `<div class="tier-sub">lens: ${escapeHtml(ds.lens_stance)}</div>`;
    } else if (humanReview?.approved_stance) {
      stanceHtml += `<div class="tier-sub">approved</div>`;
    }
    const dissent = ds.top_dissent;
    const dissentStr = dissent
      ? `${escapeHtml(dissent.label || dissent.persona)} ${escapeHtml(dissent.verdict || '')}`
      : '—';
    return `
      <div class="detail-section tier-0">
        <div class="metric-grid metric-grid-3">
          <div class="metric"><div class="k">Stance</div><div class="v">${stanceHtml}</div></div>
          <div class="metric"><div class="k">Committee agreement</div><div class="v">${ds.agreement_pct != null ? ds.agreement_pct + '%' : '—'}</div></div>
          <div class="metric"><div class="k">Dissent</div><div class="v" style="font-size:12px">${dissentStr}</div></div>
          <div class="metric"><div class="k">As of</div><div class="v mono">${escapeHtml(ds.as_of || '—')}</div></div>
        </div>
      </div>`;
  }

  function renderIdentityLine(classification, escapeHtml) {
    if (!classification) return '';
    const sleeveLabel = classification.investment_sleeve_label && classification.investment_sleeve_label !== '—'
      ? classification.investment_sleeve_label
      : (classification.investment_sleeve && classification.investment_sleeve !== '-' && classification.investment_sleeve !== '—'
        ? String(classification.investment_sleeve).replace(/_/g, ' ')
        : null);
    const parts = [
      classification.archetype,
      classification.moat ? `moat ${classification.moat}` : null,
      classification.dhando ? `dhando ${classification.dhando}` : null,
      classification.lawrence_bucket && classification.lawrence_bucket !== '—'
        ? `${classification.lawrence_bucket} lens`
        : null,
      classification.cycle && classification.cycle !== '-' && classification.cycle !== '—'
        ? `cycle ${classification.cycle}`
        : null,
      sleeveLabel,
    ].filter(Boolean);
    if (!parts.length) return '';
    return `
      <div class="detail-section tier-1">
        <div class="identity-line">${parts.map(p => escapeHtml(p)).join(' · ')}</div>
      </div>`;
  }

  function renderActiveLensChips(activeLenses, silentCount, expandedPersona, lenses, escapeHtml, powerZones) {
    if (!activeLenses?.length && !silentCount) return '';
    const inZoneIds = new Set((powerZones && powerZones.in_zone) || []);
    const hasZones = inZoneIds.size > 0;
    const lensChip = (l, inZone) => {
      const short = (l.label || l.persona || '').split(' ')[0];
      const active = expandedPersona === l.persona ? ' lens-chip-active' : '';
      const zoneMark = inZone ? ' <span title="In power zone: this persona framework fits this company type">⚡</span>' : '';
      return `<button type="button" class="lens-chip${active}" data-lens-persona="${escapeHtml(l.persona)}">${escapeHtml(short)}${zoneMark} ${escapeHtml(l.verdict)} ${l.return_pct != null ? fmtPct(l.return_pct) : ''}</button>`;
    };
    const zoned = hasZones ? (activeLenses || []).filter(l => inZoneIds.has(l.persona)) : (activeLenses || []);
    const outside = hasZones ? (activeLenses || []).filter(l => !inZoneIds.has(l.persona)) : [];
    const chips = zoned.map(l => lensChip(l, hasZones)).join('');
    const outsideBlock = outside.length
      ? `<details style="display:inline-block"><summary class="lens-chip-silent" style="cursor:pointer;list-style:none">+${outside.length} outside framework</summary>
          <div class="lens-chips" style="margin-top:6px">${outside.map(l => lensChip(l, false)).join('')}</div>
        </details>`
      : '';
    const primary = hasZones && zoned.length ? zoned[0] : null;
    const viewedThrough = primary
      ? `<p class="tier-sub" style="margin:2px 0 6px">Viewed through: <strong>${escapeHtml(primary.label || primary.persona)}</strong> (in power zone)${primary.return_pct != null ? ` — IRR ${fmtPct(primary.return_pct)}` : ''}</p>`
      : '';
    const silent = silentCount > 0
      ? `<span class="lens-chip-silent">+${silentCount} silent</span>`
      : '';
    let expand = '';
    if (expandedPersona && lenses?.personas) {
      const p = lenses.personas.find(x => x.persona === expandedPersona)
        || (activeLenses || []).find(x => x.persona === expandedPersona);
      if (p) {
        expand = `
          <div class="lens-expand">
            <div class="metric-grid" style="margin-top:8px">
              <div class="metric"><div class="k">Verdict</div><div class="v"><span class="badge ${STANCE_BADGE[p.verdict] || 'badge-warn'}">${escapeHtml(p.verdict)}</span></div></div>
              <div class="metric"><div class="k">Return</div><div class="v">${p.return_pct != null ? fmtPct(p.return_pct) : '—'}</div></div>
              <div class="metric"><div class="k">Relevance</div><div class="v">${p.relevance != null ? p.relevance : '—'}</div></div>
              <div class="metric"><div class="k">Horizon</div><div class="v">${p.horizon_yrs || '—'} yr</div></div>
            </div>
            ${(p.key_metrics || []).length ? `<ul class="dev-list" style="margin-top:8px">${p.key_metrics.map(m => `<li><span class="mono">${escapeHtml(m.name)}</span>: ${escapeHtml(String(m.value ?? '—'))}</li>`).join('')}</ul>` : ''}
            ${p.falsifier ? `<p class="tier-sub" style="margin-top:6px">Falsifier: ${escapeHtml(p.falsifier)}</p>` : ''}
          </div>`;
      }
    }
    return `
      <div class="detail-section tier-2">
        <h3>Active lenses</h3>
        ${viewedThrough}
        <div class="lens-chips">${chips}${outsideBlock}${silent}</div>
        ${expand}
      </div>`;
  }

  function filterInsights(insights, filter) {
    if (!insights?.length) return [];
    if (!filter || filter === 'all') return insights;
    const map = {
      letters: 'superinvestor_letter',
      podcasts: 'podcast_episode',
      filings: 'filing',
      earnings: 'earnings',
      macro: 'macro',
      insider: 'insider',
      ownership: 'insider',
      news: 'news',
      sumzero: 'sumzero_research',
      company: 'company_document',
      research: ['third_party', 'sumzero_research', 'research'],
      third_party: 'third_party',
    };
    const src = map[filter] || filter;
    if (filter === 'vic') {
      return insights.filter(r =>
        r.source === 'third_party'
        && [r.publisher, r.source_name, r.source_path, r.evidence_ref, r.evidence_url]
          .join(' ')
          .toLowerCase()
          .includes('vic')
      );
    }
    if (Array.isArray(src)) return insights.filter(r => src.includes(r.source));
    return insights.filter(r => r.source === src);
  }

  function renderLetterDiscussants(discussants, escapeHtml, linkHtml, ghRepo) {
    if (!discussants?.length) return '';
    return `
      <div class="detail-section tier-3">
        <h3>Who discusses this</h3>
        <ul class="source-stack">
          ${discussants.slice(0, 8).map(d => {
            const action = d.action || 'discussed';
            const badge = STANCE_BADGE[action] || 'badge-us';
            const snippet = escapeHtml(cleanText(d.commentary, 220));
            const link = recordEvidenceLink(d, linkHtml, ghRepo);
            return `<li class="source-card">
              <div class="source-card-head">
                <div class="source-card-badges">
                  <span class="badge ${sourceBadgeClass('superinvestor_letter')}">Letter</span>
                  <span class="badge ${badge}">${escapeHtml(action)}</span>
                </div>
                <span class="source-date mono">${escapeHtml(d.letter_date || '')}</span>
              </div>
              <div class="source-card-title">${escapeHtml(d.fund || 'Investor letter')}</div>
              ${snippet ? `<div class="source-card-body">${snippet}</div>` : ''}
              <div class="source-card-footer">
                <span>${escapeHtml(d.quarter || '—')}</span>
                ${link}
              </div>
            </li>`;
          }).join('')}
        </ul>
      </div>`;
  }

  function renderExternalContext(insights, filter, escapeHtml, linkHtml, discussants, ghRepo) {
    const letterBlock = discussants?.length
      ? renderLetterDiscussants(discussants, escapeHtml, linkHtml, ghRepo)
      : '';
    const rows = filterInsights(insights, filter).slice(0, 6);
    const pills = [
      { id: 'letters', label: 'Letters' },
      { id: 'podcasts', label: 'Podcasts' },
      { id: 'filings', label: 'Filings' },
      { id: 'company', label: 'Company' },
      { id: 'vic', label: 'VIC' },
      { id: 'sumzero', label: 'SumZero' },
      { id: 'research', label: 'Research' },
      { id: 'news', label: 'News' },
      { id: 'all', label: 'All' },
    ];
    const otherBlock = `
      <div class="detail-section tier-3${letterBlock ? '' : ''}">
        <h3>External context</h3>
        <nav class="source-pills">
          ${pills.map(p => `<button type="button" class="filter-btn source-pill${filter === p.id ? ' active' : ''}" data-insight-filter="${p.id}">${p.label}</button>`).join('')}
        </nav>
        ${rows.length ? `<ul class="source-stack">
          ${rows.map(r => {
            const src = SOURCE_LABEL[r.source] || r.source;
            const sourceName = r.source_name || r.fund || r.publisher || '';
            const date = r.date || r.as_of || r.observed_at || '';
            const title = cleanText(r.title || sourceName || src, 110);
            const claim = escapeHtml(cleanText(r.summary || r.claim, 220));
            const link = recordEvidenceLink(r, linkHtml, ghRepo);
            const action = r.action ? `<span class="badge ${STANCE_BADGE[r.action] || 'badge-us'}">${escapeHtml(r.action)}</span> ` : '';
            const directionClass = r.direction === 'bullish' ? 'badge-ok' : (r.direction === 'bearish' ? 'badge-bad' : 'badge-us');
            return `<li class="source-card">
              <div class="source-card-head">
                <div class="source-card-badges">
                  <span class="badge ${sourceBadgeClass(r.source)}">${escapeHtml(src)}</span>
                  ${action || `<span class="badge ${directionClass}">${escapeHtml(r.direction || 'neutral')}</span>`}
                  ${r.confidence ? `<span class="badge badge-us">${escapeHtml(r.confidence)}</span>` : ''}
                </div>
                <span class="source-date mono">${escapeHtml(date || '')}</span>
              </div>
              <div class="source-card-title">${escapeHtml(title)}</div>
              ${sourceName ? `<div class="source-card-meta">${escapeHtml(sourceName)}</div>` : ''}
              ${claim ? `<div class="source-card-body">${claim}</div>` : ''}
              <div class="source-card-footer">
                <span>${escapeHtml(AXIS_LABEL[r.impact_axis] || r.event_type || r.ref || 'context')}</span>
                ${link}
              </div>
            </li>`;
          }).join('')}
        </ul>` : '<p class="tier-sub">No matching context for this filter.</p>'}
      </div>`;
    return letterBlock + (filter === 'letters' && letterBlock ? '' : otherBlock);
  }

  function insightToneClass(tone) {
    if (tone === 'bullish') return 'badge-ok';
    if (tone === 'risk') return 'badge-bad';
    if (tone === 'ownership') return 'badge-purple';
    if (tone === 'stale') return 'badge-warn';
    return 'badge-us';
  }

  function renderInsightItem(item, escapeHtml, linkHtml, opts) {
    const emptyLabel = (opts && opts.emptyLabel) || 'No signal';
    if (!item) return `<span class="tier-sub">${emptyLabel}</span>`;
    const directionClass = item.direction === 'bullish'
      ? 'badge-ok'
      : (item.direction === 'bearish' ? 'badge-bad' : 'badge-us');
    const link = item.evidence_url ? ` ${linkHtml(item.evidence_url, evidenceLabel(item.evidence_url, item.evidence_label), 'source-open-link')}` : '';
    return `
      <div class="essential-item">
        <div>
          <span class="badge ${directionClass}">${escapeHtml(item.direction || 'neutral')}</span>
          <span class="badge badge-us">${escapeHtml(item.source_label || item.source || 'source')}</span>
          <span class="badge badge-us">${escapeHtml(item.confidence || 'med')}</span>
          ${item.date ? `<span class="mono tier-sub">${escapeHtml(item.date)}</span>` : ''}
        </div>
        <div class="essential-title">${escapeHtml(item.title || 'Insight')}${link}</div>
        ${item.summary ? `<div class="tier-sub">${escapeHtml(item.summary)}</div>` : ''}
      </div>`;
  }

  function renderEssentialInsights(essential, escapeHtml, linkHtml) {
    if (!essential || !(essential.bullets || []).length) {
      return `
        <div class="detail-section tier-2">
          <h3>External context</h3>
          <div class="research-box">
            <div class="tier-sub">No ranked external context yet. Use Insights → Ticker insights for the portfolio scan.</div>
          </div>
        </div>`;
    }
    const status = essential.status || {};
    const sourceMix = (essential.source_mix || []).map(s => SOURCE_LABEL[s] || s).join(', ') || 'none';
    const primary = (essential.bullets || [])[0];
    return `
      <div class="detail-section tier-2">
        <h3>External context</h3>
        <div class="research-box essential-box">
          <div style="display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-bottom:10px">
            <span class="badge ${insightToneClass(status.tone)}">${escapeHtml(status.label || 'Covered')}</span>
            <span class="tier-sub">${essential.freshness_days != null ? `${essential.freshness_days}d old` : 'undated'} · ${escapeHtml(sourceMix)}</span>
          </div>
          ${renderInsightItem(primary, escapeHtml, linkHtml)}
          <p class="tier-sub" style="margin-top:8px">Full scan: Insights → Ticker insights. Filtered letter/macro rows below.</p>
        </div>
      </div>`;
  }

  function renderMemoryClaim(claim, escapeHtml, linkHtml, ghRepo) {
    if (!claim) return '';
    const directionClass = claim.direction === 'bullish'
      ? 'badge-ok'
      : (claim.direction === 'bearish' ? 'badge-bad' : 'badge-us');
    const link = claim.evidence_url
      ? ` ${evidenceLink(claim.evidence_url, linkHtml, ghRepo, claim.evidence_label)}`
      : '';
    return `<li class="source-card">
      <div class="source-card-head">
        <div class="source-card-badges">
          <span class="badge ${directionClass}">${escapeHtml(claim.direction || 'neutral')}</span>
          <span class="badge badge-us">${escapeHtml(claim.claim_type || 'claim')}</span>
        </div>
        <span class="source-date mono">${escapeHtml(claim.date || '')}</span>
      </div>
      <div class="source-card-title">${escapeHtml(claim.claim || 'Research claim')}${link}</div>
      <div class="source-card-footer">
        <span>${escapeHtml(claim.source_title || claim.source_type || 'source')}</span>
        <span class="mono">${Number(claim.confidence_score || 0)}</span>
      </div>
    </li>`;
  }

  function renderResearchMemory(memory, escapeHtml, linkHtml, ghRepo) {
    if (!memory || !memory.claim_count) {
      return `
        <div class="detail-section tier-2">
          <h3>Research memory</h3>
          <div class="research-box"><div class="tier-sub">No cross-referenced claims attached yet.</div></div>
        </div>`;
    }
    const biotech = memory.biotech || {};
    const sourceMix = (memory.source_mix || []).map(s => SOURCE_LABEL[s] || String(s).replace(/_/g, ' ')).join(', ') || 'none';
    const inflectionClaims = memory.inflection_claims || [];
    const riskClaims = memory.risk_claims || [];
    const topClaims = memory.top_claims || [];
    const sig = biotech.signals || {};
    const factorChips = biotech.in_biotech_quant_universe ? `
      <div class="memory-biotech" style="margin-top:8px">
        <span class="badge badge-purple">Biotech quant</span>
        ${sig.consensus_score != null ? `<span class="badge badge-us">consensus ${escapeHtml(String(sig.consensus_score))}</span>` : ''}
        ${sig.consensus_quintile != null ? `<span class="badge badge-us">Q${escapeHtml(String(sig.consensus_quintile))}</span>` : ''}
        ${sig.spend_value_quintile != null ? `<span class="badge badge-us">spend Q${escapeHtml(String(sig.spend_value_quintile))}</span>` : ''}
        ${sig.insider_score != null ? `<span class="badge badge-us">insider ${escapeHtml(String(sig.insider_score))}</span>` : ''}
        ${sig.composite_score != null ? `<span class="badge badge-ok">composite ${escapeHtml(String(sig.composite_score))}</span>` : ''}
        ${sig.convergence_flag ? '<span class="badge badge-ok">convergence</span>' : ''}
        <button type="button" class="linkish" data-memory-view="biotech" style="margin-left:6px">Open Biotech tab</button>
      </div>` : (biotech.is_biotech_related ? `
      <div class="memory-biotech">
        <span class="badge badge-purple">Biotech-related</span>
        <span class="tier-sub">Not in specialist 13F quant universe</span>
      </div>` : '');
    const ownershipClaims = memory.ownership_claims || [];
    const specialistMentions = biotech.specialist_mentions || [];
    return `
      <div class="detail-section tier-2">
        <h3>Research memory</h3>
        <div class="research-box essential-box">
          <div class="memory-score-row">
            <div class="metric"><div class="k">Claims</div><div class="v mono">${memory.claim_count}</div></div>
            <div class="metric"><div class="k">Sources</div><div class="v mono">${memory.source_count}</div></div>
            <div class="metric"><div class="k">Evidence</div><div class="v mono">+${memory.confirming_count || 0} / -${memory.disconfirming_count || 0}</div></div>
          </div>
          <div class="tier-sub" style="margin:8px 0">${escapeHtml(sourceMix)}</div>
          ${factorChips}
          ${ownershipClaims.length ? `<h3 style="margin-top:12px">Ownership claims</h3><ul class="source-stack">${ownershipClaims.map(c => renderMemoryClaim(c, escapeHtml, linkHtml, ghRepo)).join('')}</ul>` : ''}
          ${inflectionClaims.length ? `<h3 style="margin-top:12px">Inflection claims</h3><ul class="source-stack">${inflectionClaims.map(c => renderMemoryClaim(c, escapeHtml, linkHtml, ghRepo)).join('')}</ul>` : ''}
          ${riskClaims.length ? `<h3 style="margin-top:12px">Risks / disconfirming</h3><ul class="source-stack">${riskClaims.map(c => renderMemoryClaim(c, escapeHtml, linkHtml, ghRepo)).join('')}</ul>` : ''}
          ${specialistMentions.length ? `<h3 style="margin-top:12px">Specialist letter mentions</h3><ul class="source-stack">${specialistMentions.map(c => renderMemoryClaim(c, escapeHtml, linkHtml, ghRepo)).join('')}</ul>` : ''}
          ${!inflectionClaims.length && !riskClaims.length && !ownershipClaims.length ? `<ul class="source-stack">${topClaims.slice(0, 3).map(c => renderMemoryClaim(c, escapeHtml, linkHtml, ghRepo)).join('')}</ul>` : ''}
        </div>
      </div>`;
  }

  const MEMORY_VIEW_TABS = [
    { id: 'ledger', label: 'Claim ledger' },
    { id: 'biotech', label: 'Biotech' },
    { id: 'review', label: 'Review queue' },
  ];

  const MEMORY_TYPE_FILTERS = [
    { id: 'all', label: 'All types' },
    { id: 'thesis', label: 'Thesis' },
    { id: 'variant_view', label: 'Variant' },
    { id: 'risk', label: 'Risk' },
    { id: 'ownership', label: 'Ownership' },
    { id: 'fundamentals', label: 'Fundamentals' },
    { id: 'methodology', label: 'Methodology' },
    { id: 'deep_dive', label: 'Deep dive' },
  ];

  function memoryClaimMatchesType(row, typeFilter) {
    if (!typeFilter || typeFilter === 'all') return true;
    if (typeFilter === 'deep_dive') {
      return row.source_type === 'deep_dive' || row.source_type === 'adversarial_review';
    }
    return row.claim_type === typeFilter;
  }

  function renderMemorySubNav(activeView, escapeHtml) {
    const view = activeView || 'ledger';
    return `
      <nav class="view-tabs memory-sub-nav" id="memory-view-tabs" style="margin:12px 0 8px">
        ${MEMORY_VIEW_TABS.map(t => `<button type="button" class="view-tab${view === t.id ? ' active' : ''}" data-memory-view="${t.id}">${escapeHtml(t.label)}</button>`).join('')}
      </nav>`;
  }

  function renderMemoryFilters(opts, escapeHtml) {
    const typeFilter = opts?.memoryTypeFilter || 'all';
    const biotechOnly = Boolean(opts?.memoryBiotechOnly);
    const activeView = opts?.memoryViewMode || 'ledger';
    if (activeView !== 'ledger') return '';
    return `
      <div class="memory-filter-row" style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:10px">
        <nav class="source-pills" id="memory-type-tabs" style="margin:0">
          ${MEMORY_TYPE_FILTERS.map(t => `<button type="button" class="filter-btn source-pill${typeFilter === t.id ? ' active' : ''}" data-memory-type="${t.id}">${escapeHtml(t.label)}</button>`).join('')}
        </nav>
        <label class="tier-sub" style="display:flex;align-items:center;gap:6px;margin-left:4px">
          <input type="checkbox" id="memory-biotech-only" ${biotechOnly ? 'checked' : ''} />
          Biotech names only
        </label>
      </div>
      <p class="tier-sub" style="margin-bottom:10px">Claims span all research dates. Use search, type filters, and holdings overlap above.</p>`;
  }

  function renderMemorySummary(memory, escapeHtml) {
    const summary = memory?.summary || {};
    if (!summary.claim_count) return '';
    return `
      <div class="metric-grid" style="margin-bottom:12px">
        <div class="metric"><div class="k">Claims</div><div class="v mono">${summary.claim_count || 0}</div></div>
        <div class="metric"><div class="k">Sources</div><div class="v mono">${summary.source_count || 0}</div></div>
        <div class="metric"><div class="k">Review queue</div><div class="v mono">${summary.review_queue_count || 0}</div></div>
        <div class="metric"><div class="k">13F records</div><div class="v mono">${summary.ownership_record_count || 0}</div></div>
        <div class="metric"><div class="k">Biotech quant</div><div class="v mono">${summary.biotech_quant_universe_count || summary.biotech_related_ticker_count || 0}</div></div>
      </div>`;
  }

  function renderConsensusDetail(lenses, escapeHtml) {
    if (!lenses?.valuation_blend) return '';
    const blend = lenses.valuation_blend;
    const cons = lenses.consensus || {};
    const contributors = (blend.contributors || []).slice(0, 8);
    return `
      <details class="detail-section tier-4">
        <summary>Persona consensus detail</summary>
        <div class="metric-grid" style="margin-top:10px">
          <div class="metric"><div class="k">Blend</div><div class="v">${blend.blended_return_pct != null ? fmtPct(blend.blended_return_pct) : '—'}</div></div>
          <div class="metric"><div class="k">Band</div><div class="v">${blend.band_pct ? blend.band_pct.map(fmtPct).join('–') : '—'}</div></div>
          <div class="metric"><div class="k">Stance</div><div class="v"><span class="badge ${STANCE_BADGE[cons.stance] || 'badge-warn'}">${escapeHtml(cons.stance || '—')}</span></div></div>
        </div>
        ${contributors.length ? `
        <table class="darwin-table" style="margin-top:10px">
          <thead><tr><th>Persona</th><th>Return</th><th>Verdict</th><th>Rel</th></tr></thead>
          <tbody>
            ${contributors.map(c => `
              <tr>
                <td>${escapeHtml((c.label || c.persona || '').split('/')[0])}</td>
                <td class="mono">${c.return_pct != null ? fmtPct(c.return_pct) : '—'}</td>
                <td>${escapeHtml(c.verdict || '—')}</td>
                <td class="mono">${c.relevance != null ? c.relevance : '—'}</td>
              </tr>`).join('')}
          </tbody>
        </table>` : ''}
        ${(cons.dissents || []).length ? `<p class="tier-sub" style="margin-top:8px"><strong>Dissents:</strong> ${cons.dissents.map(d => escapeHtml(`${d.persona}: ${d.verdict}`)).join(' · ')}</p>` : ''}
      </details>`;
  }

  function renderPeriodEmptyState(activeSection, period, timeModel, escapeHtml) {
    const latestIndexed = timeModel?.latestIndexedQuarter;
    const latestLabel = latestIndexed ? quarterLabel(latestIndexed) : null;
    const emptyForPeriod = period && !period.all && latestIndexed && period.quarters?.[0] !== latestIndexed;
    if (activeSection === 'letters') {
      if (!emptyForPeriod) {
        return '<p class="subhead">No letters indexed yet — run make persona-fetch-letters</p>';
      }
      return `<p class="subhead">No letters indexed for ${escapeHtml(period.label)}. `
        + `${latestLabel ? `<button type="button" class="linkish" data-use-latest-quarter>Use ${escapeHtml(latestLabel)}</button> instead.` : ''}</p>`;
    }
    return `<p class="subhead">No data for ${escapeHtml(period?.label || 'this period')}.</p>`;
  }

  function uniqueTickers(list) {
    const out = [];
    const seen = new Set();
    for (const raw of list || []) {
      const t = String(raw || '').trim().toUpperCase();
      if (!t || seen.has(t)) continue;
      seen.add(t);
      out.push(t);
    }
    return out;
  }

  function letterDocumentLabel(row) {
    if (row?.document_label) return String(row.document_label);
    const ref = row?.source_file || row?.source_document || '';
    const stem = String(ref).replace(/\\/g, '/').split('/').pop() || '';
    return stem.replace(/\.(txt|pdf|md)$/i, '').slice(0, 48);
  }

  function podcastTranscriptRef(ref) {
    if (!ref) return '';
    const s = String(ref);
    if (s.endsWith('.meta.json')) return s.replace(/\.meta\.json$/, '.txt');
    return s;
  }

  function podcastEpisodeShardPath(episodeId) {
    const safe = String(episodeId || '').replace(/[^A-Za-z0-9._-]+/g, '_').slice(0, 180);
    return `data/insights/podcast_episodes/${safe}.json`;
  }

  function normalizePodcastGuests(guests) {
    if (!Array.isArray(guests)) return [];
    return guests.map(g => {
      if (typeof g === 'string') return g;
      return g?.display || g?.guest_id || '';
    }).filter(Boolean);
  }

  function renderPodcastEpisodeDetail(row, escapeHtml, linkHtml, ghRepo, opts = {}) {
    if (!row) return '';
    const detail = opts.detail || null;
    const loading = Boolean(opts.loading);
    const merged = detail ? { ...row, ...detail } : row;
    const flags = [
      merged.has_pz_guest ? 'PZ guest' : '',
      merged.has_officer_hit ? 'Officer' : '',
      merged.near_universe ? 'Near-universe' : '',
      merged.in_book ? 'In book' : '',
    ].filter(Boolean);
    const guests = normalizePodcastGuests(merged.guests);
    const personas = (merged.persona_ids || []).filter(Boolean);
    const themes = (merged.themes || []).map(t => {
      const label = typeof t === 'string' ? t : (t.theme || '');
      const stance = typeof t === 'object' ? (t.stance || '') : '';
      if (!label) return '';
      return `<span class="badge badge-us">${escapeHtml(label)}</span>${stance ? ` ${escapeHtml(stance)}` : ''}`;
    }).filter(Boolean).join(' · ');
    const tickers = (merged.tickers || []).filter(Boolean);
    const highlights = Array.isArray(merged.highlights)
      ? merged.highlights.map(h => (typeof h === 'string' ? h : (h.quote || h.text || ''))).filter(Boolean)
      : (merged.highlight_previews || []).filter(Boolean);
    const summary = (merged.summary || '').trim();
    const transcriptRef = podcastTranscriptRef(merged.source_document);
    const transcriptLink = transcriptRef
      ? evidenceLink(transcriptRef, linkHtml, ghRepo, 'Transcript')
      : '';
    const episodeLink = merged.link ? linkHtml(merged.link, 'Episode', 'source-open-link') : '';
    const positions = (merged.positions || []).filter(p => p && p.ticker).slice(0, 12);
    return `
      <div class="detail-section fund-detail" id="podcast-episode-detail">
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">
          <button type="button" class="filter-btn" data-podcast-back>← Back</button>
          <h3 style="margin:0;font-size:15px;line-height:1.35">${escapeHtml(merged.title || 'Episode')}</h3>
        </div>
        <p class="tier-sub">${escapeHtml(merged.show_title || merged.show_id || 'Podcast')} · ${escapeHtml(merged.published || '—')}</p>
        ${flags.length ? `<p style="margin:8px 0">${flags.map(f => `<span class="badge badge-us">${escapeHtml(f)}</span>`).join(' ')}</p>` : ''}
        ${guests.length ? `<p class="tier-sub">Guests: ${escapeHtml(guests.join(', '))}</p>` : ''}
        ${personas.length ? `<p class="tier-sub">Personas: ${escapeHtml(personas.join(', '))}</p>` : ''}
        ${themes ? `<div style="margin:8px 0"><strong>Themes:</strong> ${themes}</div>` : ''}
        ${loading ? '<p class="tier-sub">Loading summary and highlights…</p>' : ''}
        ${summary ? `<p style="font-size:13px;line-height:1.5;margin:10px 0">${escapeHtml(summary)}</p>` : ''}
        ${tickers.length ? `
        <div style="margin:10px 0">
          <strong>Tickers</strong>
          <div style="margin-top:6px;display:flex;flex-wrap:wrap;gap:6px">
            ${tickers.map(t => `<button type="button" class="filter-btn source-pill mono" data-select-ticker="${escapeHtml(t)}">${escapeHtml(t)}</button>`).join('')}
          </div>
        </div>` : ''}
        ${positions.length ? `
        <h4 style="margin-top:14px;font-size:12px;color:var(--text-muted)">TICKER COMMENTARY</h4>
        <ul class="dev-list">${positions.map(p => `<li style="font-size:12px"><span class="mono">${escapeHtml(p.ticker)}</span>${p.commentary ? ` — ${escapeHtml(String(p.commentary).slice(0, 200))}` : ''}</li>`).join('')}</ul>
        ` : ''}
        ${highlights.length ? `
        <h4 style="margin-top:14px;font-size:12px;color:var(--text-muted)">HIGHLIGHTS</h4>
        <ul class="dev-list">${highlights.map(p => `<li style="font-size:13px;line-height:1.45">${escapeHtml(p)}</li>`).join('')}</ul>
        ` : (!loading && merged.highlight_count ? `<p class="tier-sub">${merged.highlight_count} highlight(s) — open transcript for detail</p>` : '')}
        <p class="tier-sub" style="margin-top:12px">${[transcriptLink, episodeLink].filter(Boolean).join(' · ') || '—'}</p>
      </div>`;
  }

  function renderPodcastIndex(rows, byShow, escapeHtml, linkHtml, ghRepo, opts = {}) {
    const {
      bookOnly = false,
      search = '',
      period = null,
      showId = 'all',
      flagFilter = 'all',
      selectedEpisodeId = null,
      episodeDetail = null,
      episodeDetailLoading = false,
    } = opts;
    let list = Array.isArray(rows) ? rows.slice() : [];
    if (period) list = list.filter(r => periodMatchesRecord(r, period, ['published']));
    if (bookOnly) list = list.filter(r => r.in_book || (r.tickers || []).length);
    if (showId && showId !== 'all') list = list.filter(r => r.show_id === showId);
    if (flagFilter === 'pz') list = list.filter(r => r.has_pz_guest);
    else if (flagFilter === 'officer') list = list.filter(r => r.has_officer_hit);
    else if (flagFilter === 'in_book') list = list.filter(r => r.in_book);
    else if (flagFilter === 'highlights') list = list.filter(r => (r.highlight_count || 0) > 0);
    if (search) {
      const q = String(search).toLowerCase();
      list = list.filter(r => {
        const blob = [
          r.show_title, r.title, (r.guests || []).join(' '), (r.tickers || []).join(' '),
          (r.persona_ids || []).join(' '),
          (r.themes || []).map(t => (typeof t === 'string' ? t : t.theme) || '').join(' '),
        ].join(' ').toLowerCase();
        return blob.includes(q);
      });
    }

    if (selectedEpisodeId) {
      const selected = list.find(r => r.episode_id === selectedEpisodeId)
        || (rows || []).find(r => r.episode_id === selectedEpisodeId);
      if (selected) {
        return renderPodcastEpisodeDetail(selected, escapeHtml, linkHtml, ghRepo, {
          detail: episodeDetail && episodeDetail.episode_id === selectedEpisodeId ? episodeDetail : null,
          loading: episodeDetailLoading && !(episodeDetail && episodeDetail.episode_id === selectedEpisodeId),
        });
      }
    }

    const shows = Object.values(byShow || {}).sort((a, b) =>
      String(a.show_title || a.show_id).localeCompare(String(b.show_title || b.show_id))
    );
    const showPills = [
      { id: 'all', label: `All shows (${(rows || []).length})` },
      ...shows.map(s => ({
        id: s.show_id,
        label: `${s.show_title || s.show_id} (${s.episode_count || (s.episode_ids || []).length || 0})`,
      })),
    ];
    const flagPills = [
      { id: 'all', label: 'All' },
      { id: 'pz', label: 'PZ guest' },
      { id: 'officer', label: 'Officer' },
      { id: 'in_book', label: 'In book' },
      { id: 'highlights', label: 'Has highlights' },
    ];

    if (!list.length) {
      return `
        <nav class="source-pills" id="podcast-show-tabs" style="margin-bottom:8px">
          ${showPills.map(p => `<button type="button" class="filter-btn source-pill${showId === p.id ? ' active' : ''}" data-podcast-show="${escapeHtml(p.id)}">${escapeHtml(p.label)}</button>`).join('')}
        </nav>
        <nav class="source-pills" id="podcast-flag-tabs" style="margin-bottom:10px">
          ${flagPills.map(p => `<button type="button" class="filter-btn source-pill${flagFilter === p.id ? ' active' : ''}" data-podcast-flag="${escapeHtml(p.id)}">${escapeHtml(p.label)}</button>`).join('')}
        </nav>
        <p class="muted">${(rows || []).length ? 'No episodes match these filters.' : 'No podcast episodes indexed yet. Run <code>make podcasts-refresh</code>.'}</p>`;
    }

    return `
      <nav class="source-pills" id="podcast-show-tabs" style="margin-bottom:8px">
        ${showPills.map(p => `<button type="button" class="filter-btn source-pill${showId === p.id ? ' active' : ''}" data-podcast-show="${escapeHtml(p.id)}">${escapeHtml(p.label)}</button>`).join('')}
      </nav>
      <nav class="source-pills" id="podcast-flag-tabs" style="margin-bottom:10px">
        ${flagPills.map(p => `<button type="button" class="filter-btn source-pill${flagFilter === p.id ? ' active' : ''}" data-podcast-flag="${escapeHtml(p.id)}">${escapeHtml(p.label)}</button>`).join('')}
      </nav>
      <p class="tier-sub" style="margin-bottom:8px">${list.length} episode(s)${bookOnly ? ' · in-book / ticker overlap' : ''}${period && !period.all ? ` · ${escapeHtml(period.label || '')}` : ''}</p>
      <table class="darwin-table" id="insights-podcast-table">
        <thead><tr><th>Date</th><th>Show</th><th>Episode</th><th>Guests / PZ</th><th>Tickers</th><th>Flags</th><th>Highlights</th><th>Source</th></tr></thead>
        <tbody>
          ${list.slice(0, 100).map(r => {
            const flags = [
              r.has_pz_guest ? 'PZ guest' : '',
              r.has_officer_hit ? 'Officer' : '',
              r.near_universe ? 'Near-universe' : '',
              r.in_book ? 'In book' : '',
            ].filter(Boolean).join(' · ') || '—';
            const guests = (r.guests || []).filter(Boolean).slice(0, 4).join(', ') || '—';
            const personas = (r.persona_ids || []).slice(0, 3).join(', ');
            const guestCell = personas ? `${escapeHtml(guests)}<div class="tier-sub" style="font-size:10px">${escapeHtml(personas)}</div>` : escapeHtml(guests);
            const tickers = (r.tickers || []).slice(0, 6);
            const tickerCell = tickers.length
              ? tickers.map(t => `<button type="button" class="linkish mono" data-select-ticker="${escapeHtml(t)}">${escapeHtml(t)}</button>`).join(' ')
              : '—';
            const transcriptRef = podcastTranscriptRef(r.source_document);
            const src = transcriptRef
              ? evidenceLink(transcriptRef, linkHtml, ghRepo, 'Transcript')
              : (r.link ? linkHtml(r.link, 'Open', 'source-open-link') : '—');
            const eid = escapeHtml(r.episode_id || '');
            return `<tr class="podcast-row" data-podcast-episode="${eid}" style="cursor:pointer">
              <td class="mono">${escapeHtml(r.published || '—')}</td>
              <td>${escapeHtml(r.show_title || r.show_id || '—')}</td>
              <td style="font-size:11px;max-width:260px"><button type="button" class="linkish" data-podcast-episode="${eid}" style="text-align:left">${escapeHtml(r.title || '—')}</button></td>
              <td style="font-size:11px">${guestCell}</td>
              <td class="mono" style="font-size:11px">${tickerCell}</td>
              <td style="font-size:11px">${escapeHtml(flags)}</td>
              <td class="mono">${escapeHtml(String(r.highlight_count ?? 0))}</td>
              <td>${src}</td>
            </tr>`;
          }).join('')}
        </tbody>
      </table>
      ${list.length > 100 ? `<p class="tier-sub">${list.length - 100} more episodes — refine search</p>` : ''}`;
  }

  function renderLetterIndex(rows, escapeHtml, linkHtml, ghRepo, onFundClick, positionStats, period, timeModel, bookOnly) {
    if (!rows?.length) {
      return renderPeriodEmptyState('letters', period, timeModel, escapeHtml);
    }
    const statsLine = positionStats
      ? `<p class="tier-sub" style="margin-bottom:8px">${positionStats}</p>`
      : '';
    const fmtTickers = (list) => uniqueTickers(list).slice(0, 5).join(', ') || '—';
    const tickerHeader = bookOnly ? 'Other tickers' : 'Tickers';
    return `
      ${statsLine}
      <table class="darwin-table" id="insights-letter-table">
        <thead><tr><th>Date</th><th>Fund</th><th>Quarter</th><th>Themes</th><th>${tickerHeader}</th><th>New / Add</th><th>Trim / Exit</th><th>Our overlap</th><th>Summary</th><th>Source</th></tr></thead>
        <tbody>
          ${rows.slice(0, 80).map(r => {
            const overlapSet = new Set(uniqueTickers(r.our_overlap));
            const tickerList = bookOnly
              ? uniqueTickers(r.tickers).filter(t => !overlapSet.has(t))
              : uniqueTickers(r.tickers);
            const fundCell = onFundClick
              ? `<button type="button" class="linkish" data-fund-id="${escapeHtml(r.fund_id || '')}">${escapeHtml(r.fund)}</button>`
              : escapeHtml(r.fund);
            const docLabel = letterDocumentLabel(r);
            const fundBlock = docLabel
              ? `${fundCell}<div class="tier-sub" style="font-size:10px;margin-top:2px">${escapeHtml(docLabel)}</div>`
              : fundCell;
            return `
            <tr class="clickable-row" data-fund-id="${escapeHtml(r.fund_id || '')}">
              <td class="mono">${escapeHtml(r.letter_date || '—')}</td>
              <td>${fundBlock}</td>
              <td class="mono">${escapeHtml(r.quarter || '—')}</td>
              <td style="font-size:11px">${(r.themes || []).slice(0, 2).join(', ') || '—'}</td>
              <td class="mono" style="font-size:11px">${fmtTickers(tickerList)}</td>
              <td class="mono" style="font-size:11px;color:var(--accent-green)">${fmtTickers(r.adds)}</td>
              <td class="mono" style="font-size:11px;color:var(--accent-amber)">${fmtTickers([...(r.trims || []), ...(r.exits || [])])}</td>
              <td class="mono" style="font-size:11px;color:var(--accent-cyan)">${fmtTickers(r.our_overlap)}</td>
              <td style="font-size:11px;max-width:240px">${escapeHtml((r.lead_summary || '').slice(0, 120))}</td>
              <td>${recordEvidenceLink(r, linkHtml, ghRepo)}</td>
            </tr>`;
          }).join('')}
        </tbody>
      </table>
      ${rows.length > 80 ? `<p class="tier-sub">${rows.length - 80} more letters — use fund search</p>` : ''}`;
  }

  function renderFundRegistry(funds, escapeHtml, linkHtml, ghRepo, bookOnly) {
    if (!funds?.length) {
      return '<p class="subhead">No fund profiles yet.</p>';
    }
    let list = funds;
    if (bookOnly) {
      list = list.filter(f => (f.our_ticker_count || (f.our_tickers || []).length || 0) > 0);
    }
    return `
      <p class="muted" style="margin-bottom:8px">One row per fund profile (not every quarter letter). Sibling strategies stay separate; identical commentary collapses in Consensus.</p>
      <table class="darwin-table" id="insights-fund-table">
        <thead><tr><th>Fund</th><th>Letters</th><th>In our book</th><th>Dupes</th><th>Personas</th><th></th></tr></thead>
        <tbody>
          ${list.slice(0, 80).map(f => `
            <tr class="clickable-row" data-fund-id="${escapeHtml(f.fund_id || '')}">
              <td>
                <button type="button" class="linkish" data-fund-id="${escapeHtml(f.fund_id || '')}">${escapeHtml(f.fund)}</button>
                ${f.manager ? `<div class="tier-sub">${escapeHtml(f.manager)}</div>` : ''}
              </td>
              <td class="mono">${escapeHtml(String(f.letter_count != null ? f.letter_count : ((f.letters || []).length || f.quarter || '—')))}</td>
              <td class="mono">${(f.our_tickers || []).slice(0, 6).join(', ') || '—'}</td>
              <td class="mono">${f.duplicate_count != null ? f.duplicate_count : (f.near_dup_count != null ? f.near_dup_count : '—')}</td>
              <td style="font-size:11px">${(f.maps_to_persona || []).join(', ') || '—'}</td>
              <td>${recordEvidenceLink(f, linkHtml, ghRepo)}</td>
            </tr>`).join('')}
        </tbody>
      </table>
      ${list.length > 80 ? `<p class="tier-sub">${list.length - 80} more — refine search</p>` : ''}
      ${bookOnly && !list.length ? '<p class="subhead">No funds with overlap to your holdings.</p>' : ''}`;
  }

  function renderFundDetail(profile, escapeHtml, linkHtml, ghRepo) {
    if (!profile) return '';
    const latest = (profile.letters || [])[0] || {};
    const themes = (latest.themes || []).map(t =>
      `<span class="badge badge-us">${escapeHtml(t.theme)}</span> ${escapeHtml(t.stance || '')}`
    ).join(' · ');
    const positions = (latest.positions || []).slice(0, 15);
    const risks = latest.risks || [];
    const catalysts = latest.catalysts || [];
    return `
      <div class="detail-section fund-detail">
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">
          <button type="button" class="filter-btn" data-insights-back>← Back</button>
          <h3 style="margin:0">${escapeHtml(profile.fund)}</h3>
        </div>
        ${profile.manager ? `<p class="tier-sub">Manager: ${escapeHtml(profile.manager)}</p>` : ''}
        ${(profile.maps_to_persona || []).length ? `<p class="tier-sub">Persona map: ${profile.maps_to_persona.map(p => escapeHtml(p)).join(', ')}</p>` : ''}
        ${(profile.our_tickers || []).length ? `<p class="tier-sub">Discusses our book: <span class="mono">${profile.our_tickers.join(', ')}</span></p>` : ''}
        ${latest.lead_summary ? `<p style="font-size:13px;line-height:1.5;margin:10px 0">${escapeHtml(latest.lead_summary)}</p>` : ''}
        ${themes ? `<div style="margin:8px 0"><strong>Themes:</strong> ${themes}</div>` : ''}
        ${risks.length ? `<div style="margin:8px 0"><strong>Risks:</strong><ul class="dev-list">${risks.map(r => `<li>${escapeHtml(r)}</li>`).join('')}</ul></div>` : ''}
        ${catalysts.length ? `<div style="margin:8px 0"><strong>Catalysts:</strong><ul class="dev-list">${catalysts.map(c => `<li>${escapeHtml(c)}</li>`).join('')}</ul></div>` : ''}
        ${positions.length ? `
        <h4 style="margin-top:14px;font-size:12px;color:var(--text-muted)">TICKER COMMENTARY</h4>
        <table class="darwin-table">
          <thead><tr><th>Ticker</th><th>Action</th><th>Commentary</th></tr></thead>
          <tbody>
            ${positions.map(p => `
              <tr>
                <td class="mono">${escapeHtml(p.ticker)}</td>
                <td><span class="badge ${STANCE_BADGE[p.action] || 'badge-us'}">${escapeHtml(p.action || '—')}</span></td>
                <td style="font-size:12px">${escapeHtml((p.commentary || p.thesis || '').slice(0, 220))}</td>
              </tr>`).join('')}
          </tbody>
        </table>` : ''}
        <p class="tier-sub" style="margin-top:10px">
          ${(profile.letters || []).length} letter(s) · latest ${escapeHtml(latest.quarter || '—')} · ${recordEvidenceLink(latest, linkHtml, ghRepo)}
        </p>
      </div>`;
  }

  function parseQuarter(value) {
    const text = String(value || '').trim();
    if (!text) return null;
    let m = text.match(/(20\d{2})\s*Q([1-4])/i)
      || text.match(/(20\d{2})\s*([1-4])Q/i)
      || text.match(/(20\d{2})Q([1-4])/i);
    if (m) {
      const year = Number(m[1]);
      const quarter = Number(m[2]);
      return { id: `${year}Q${quarter}`, year, quarter, label: `Q${quarter} ${year}` };
    }
    m = text.match(/^(20\d{2})-(\d{2})-\d{2}/);
    if (m) {
      const year = Number(m[1]);
      const month = Number(m[2]);
      if (month >= 1 && month <= 12) {
        const quarter = Math.floor((month - 1) / 3) + 1;
        return { id: `${year}Q${quarter}`, year, quarter, label: `Q${quarter} ${year}` };
      }
    }
    return null;
  }

  function quarterLabel(id) {
    const q = parseQuarter(id);
    return q ? q.label : String(id || 'All history');
  }

  function addQuarter(map, value, meta) {
    const q = parseQuarter(value);
    if (!q) return null;
    const row = map.get(q.id) || {
      id: q.id,
      label: q.label,
      year: q.year,
      quarter: q.quarter,
      indexed_count: 0,
      document_count: 0,
      source_folder_count: 0,
      source_folder_url: null,
    };
    row.indexed_count += Number(meta?.indexed_count || 0);
    row.document_count += Number(meta?.document_count || 0);
    row.source_folder_count += Number(meta?.source_folder_count || 0);
    row.source_folder_url = row.source_folder_url || meta?.source_folder_url || null;
    map.set(q.id, row);
    return q.id;
  }

  function minIndexedYear(letterIndex) {
    let min = null;
    for (const row of letterIndex || []) {
      const q = parseQuarter(row.quarter || row.letter_date);
      if (q && (min === null || q.year < min)) min = q.year;
    }
    return min ?? 2011;
  }

  function quarterSortDesc(a, b) {
    return (b.year - a.year) || (b.quarter - a.quarter);
  }

  function collectIndexedQuarterIds(insights) {
    const ids = new Set();
    const fromPayload = insights?.time_periods?.indexed_quarters;
    if (Array.isArray(fromPayload) && fromPayload.length) {
      fromPayload.forEach(q => { if (q) ids.add(String(q)); });
      return ids;
    }
    (insights?.letter_index || []).forEach(row => {
      const q = parseQuarter(row.quarter || row.letter_date);
      if (q) ids.add(q.id);
    });
    Object.keys(insights?.theme_rankings_by_quarter || {}).forEach(q => {
      if (q && q !== 'all') ids.add(q);
    });
    Object.keys(insights?.consensus?.by_quarter || {}).forEach(q => {
      if (q && q !== 'all') ids.add(q);
    });
    return ids;
  }

  function resolveLatestIndexedQuarter(insights, indexedIds) {
    const explicit = insights?.time_periods?.latest_indexed_quarter;
    if (explicit && parseQuarter(explicit)) return explicit;
    return Array.from(indexedIds || [])
      .map(id => parseQuarter(id))
      .filter(Boolean)
      .sort(quarterSortDesc)[0]?.id || null;
  }

  function buildTimeModel(insights, documentCatalog) {
    const floorYear = minIndexedYear(insights?.letter_index);
    const map = new Map();
    const timePeriods = documentCatalog?.time_periods || {};
    (timePeriods.available_quarters || []).forEach(q => {
      if ((q.year || parseQuarter(q.id || q.label)?.year || 0) < floorYear) return;
      addQuarter(map, q.id || q.label, {
        document_count: q.document_count,
        source_folder_count: q.source_folder_count,
        source_folder_url: q.source_folder_url,
      });
    });
    Object.entries(insights?.theme_rankings_by_quarter || {})
      .filter(([q]) => q && q !== 'all')
      .forEach(([q]) => addQuarter(map, q, {}));
    (insights?.letter_index || []).forEach(r => addQuarter(map, r.quarter || r.letter_date, { indexed_count: 1 }));
    (insights?.fund_registry || []).forEach(r => addQuarter(map, r.quarter || r.letter_date, {}));
    (insights?.consensus?.quarters || []).forEach(q => addQuarter(map, q, {}));
    Object.entries((documentCatalog?.summary || {}).by_quarter || {})
      .forEach(([q, count]) => {
        if ((parseQuarter(q)?.year || 0) < floorYear) return;
        addQuarter(map, q, { document_count: count });
      });

    let quarters = Array.from(map.values())
      .filter(q => q.year >= floorYear)
      .sort((a, b) => (b.year - a.year) || (b.quarter - a.quarter));
    if (quarters.length && quarters.length < 12) {
      const latestYear = quarters[0].year;
      for (let year = latestYear - 1; year >= Math.max(latestYear - 12, floorYear); year -= 1) {
        for (let q = 4; q >= 1; q -= 1) addQuarter(map, `${year}Q${q}`, {});
      }
      quarters = Array.from(map.values())
        .filter(q => q.year >= floorYear)
        .sort((a, b) => (b.year - a.year) || (b.quarter - a.quarter));
    }
    const indexedQuarterSet = collectIndexedQuarterIds(insights);
    indexedQuarterSet.forEach(qid => {
      const row = map.get(qid);
      if (row && !row.indexed_count) row.indexed_count = 1;
    });
    quarters = Array.from(map.values())
      .filter(q => q.year >= floorYear)
      .sort((a, b) => (b.year - a.year) || (b.quarter - a.quarter));
    const latestIndexedQuarter = resolveLatestIndexedQuarter(insights, indexedQuarterSet);
    const latestCatalogQuarter = timePeriods.latest_catalog_quarter || timePeriods.latest_quarter || null;
    const indexedYears = Array.from(new Set(
      quarters.filter(q => indexedQuarterSet.has(q.id) || q.indexed_count > 0).map(q => q.year),
    )).sort((a, b) => b - a);
    const years = Array.from(new Set(quarters.map(q => q.year))).sort((a, b) => b - a);
    const byId = Object.fromEntries(quarters.map(q => [q.id, q]));
    return {
      quarters,
      years,
      indexedYears,
      indexedQuarterSet,
      byId,
      latestQuarter: latestIndexedQuarter || latestCatalogQuarter || quarters.find(q => q.indexed_count > 0)?.id || quarters[0]?.id || null,
      latestIndexedQuarter,
      latestCatalogQuarter,
      latestYear: (parseQuarter(latestIndexedQuarter) || quarters.find(q => indexedQuarterSet.has(q.id)) || quarters[0])?.year || null,
    };
  }

  function periodFromSelection(selection, timeModel) {
    const raw = selection || 'latest';
    const allQuarters = timeModel.quarters.map(q => q.id);
    let ids = [];
    let label = 'All history';
    let selectedYear = timeModel.latestYear;
    if (raw === 'latest') {
      ids = timeModel.latestQuarter ? [timeModel.latestQuarter] : allQuarters.slice(0, 1);
      label = ids[0] ? quarterLabel(ids[0]) : 'Latest quarter';
      selectedYear = parseQuarter(ids[0])?.year || selectedYear;
    } else if (raw === 'last4') {
      ids = allQuarters.slice(0, 4);
      label = 'Last 4 quarters';
    } else if (raw === 'last8') {
      ids = allQuarters.slice(0, 8);
      label = 'Last 8 quarters';
    } else if (raw === 'since2020') {
      ids = allQuarters.filter(id => (parseQuarter(id)?.year || 0) >= 2020);
      label = 'Since 2020';
    } else if (raw === 'all') {
      ids = allQuarters;
      label = 'All history';
    } else if (raw.startsWith('year:')) {
      selectedYear = Number(raw.split(':')[1]);
      ids = allQuarters.filter(id => parseQuarter(id)?.year === selectedYear);
      label = String(selectedYear);
    } else {
      const q = parseQuarter(raw);
      if (q) {
        ids = [q.id];
        label = q.label;
        selectedYear = q.year;
      }
    }
    return {
      id: raw,
      label,
      quarters: ids,
      quarterSet: new Set(ids),
      all: raw === 'all',
      selectedYear,
    };
  }

  function recordQuarterIds(record, fields) {
    const ids = new Set();
    for (const field of fields) {
      const q = parseQuarter(record?.[field]);
      if (q) ids.add(q.id);
    }
    return ids;
  }

  function periodMatchesRecord(record, period, fields) {
    if (!period || period.all) return true;
    const ids = recordQuarterIds(record, fields);
    if (!ids.size) return false;
    for (const qid of ids) {
      if (period.quarterSet.has(qid)) return true;
    }
    return false;
  }

  function periodCoverage(period, timeModel, letterIndex, funds) {
    const letters = (letterIndex || []).filter(r => periodMatchesRecord(r, period, ['quarter', 'letter_date']));
    const fundRows = (funds || []).filter(r => periodMatchesRecord(r, period, ['quarter', 'letter_date']));
    const quarterRows = period.all
      ? timeModel.quarters
      : period.quarters.map(id => timeModel.byId[id]).filter(Boolean);
    const folderCount = quarterRows.reduce((sum, q) => sum + (q.source_folder_count || 0), 0);
    const drivePdfCount = quarterRows.reduce((sum, q) => sum + (q.document_count || 0), 0);
    const indexedInPeriod = quarterRows.reduce((sum, q) => sum + (q.indexed_count || 0), 0);
    return {
      letters: letters.length,
      funds: fundRows.length,
      quarters: period.all ? timeModel.quarters.length : period.quarters.length,
      folderCount,
      drivePdfCount,
      indexedInPeriod,
    };
  }

  function dedupeEvents(events) {
    const best = new Map();
    for (const event of events || []) {
      const key = [
        event.source || '',
        event.ticker || '',
        event.event_type || '',
        event.observed_at || '',
        event.title || '',
      ].join('|');
      const prev = best.get(key);
      if (!prev || Number(event.score || 0) > Number(prev.score || 0)) {
        best.set(key, event);
      }
    }
    return Array.from(best.values());
  }

  function eventDate(event) {
    const raw = event?.effective_at || event?.observed_at || '';
    const parsed = raw ? new Date(`${String(raw).slice(0, 10)}T00:00:00Z`) : null;
    return parsed && !Number.isNaN(parsed.getTime()) ? parsed : null;
  }

  function eventMatchesRange(event, range, lastSeenAt, nowIso) {
    if (!range || range === 'all') return true;
    const date = eventDate(event);
    if (!date) return false;
    const now = nowIso ? new Date(nowIso) : new Date();
    if ((event?.event_kind || 'observed') === 'scheduled' && range !== 'all' && range !== 'since_last') {
      const horizon = range === 'last90' ? 90 : (range === 'last30' ? 30 : 30);
      return date >= now && date <= new Date(now.getTime() + horizon * 86400000);
    }
    if (range === 'since_last') {
      if (!lastSeenAt) return true;
      return date.getTime() > new Date(lastSeenAt).getTime();
    }
    if (range === 'ytd') return date.getUTCFullYear() === now.getUTCFullYear();
    const days = range === 'last30' ? 30 : (range === 'last90' ? 90 : 7);
    const cutoff = new Date(now.getTime() - days * 86400000);
    return date >= cutoff && date <= new Date(now.getTime() + 86400000);
  }

  function baseFilterEvents(events, opts) {
    const {
      search,
      knownTickers,
      eventRange = 'last7',
      lastSeenAt = null,
      generatedAt = null,
      eventScope = 'holdings',
      eventKind = 'observed',
      eventSource = 'all',
      eventAxis = 'all',
      eventDirection = 'all',
      eventConfidence = 'all',
      eventReview = 'unreviewed',
      reviewState = {},
    } = opts || {};
    let list = dedupeEvents(events);
    const reviewed = reviewState.reviewed || {};
    const saved = reviewState.saved || {};
    const muted = reviewState.mutedTemplates || {};
    list = list.filter(e => eventMatchesRange(e, eventRange, lastSeenAt, generatedAt));
    if (eventScope === 'holdings') list = list.filter(e => e.in_holdings || e.in_our_book);
    if (eventScope === 'watchlist') list = list.filter(e => e.in_watchlist);
    if (eventKind !== 'all') list = list.filter(e => (e.event_kind || 'observed') === eventKind);
    if (eventSource !== 'all') list = list.filter(e => e.source === eventSource);
    if (eventAxis !== 'all') list = list.filter(e => e.impact_axis === eventAxis);
    if (eventDirection !== 'all') list = list.filter(e => (e.direction || 'neutral') === eventDirection);
    if (eventConfidence !== 'all') {
      list = list.filter(e => String(e.confidence || 'med').toLowerCase().startsWith(eventConfidence));
    }
    if (eventReview === 'unreviewed') list = list.filter(e => !reviewed[e.id]);
    if (eventReview === 'reviewed') list = list.filter(e => reviewed[e.id]);
    if (eventReview === 'saved') list = list.filter(e => saved[e.id]);
    if (eventReview === 'needs_review') {
      list = list.filter(e => e.needs_review || e.triage_verdict === 'human_review');
    }
    if (eventReview !== 'muted') list = list.filter(e => !muted[e.template_id]);
    if (eventReview === 'muted') list = list.filter(e => muted[e.template_id]);
    if (search) {
      const tickers = knownTickers || [];
      list = list.filter(e => SearchMatch.matchEvent(e, search, tickers));
    }
    return list;
  }

  function filterEvents(events, opts) {
    const { eventTier = 'signal' } = opts || {};
    let list = baseFilterEvents(events, opts);
    const tier = eventTier || 'signal';
    if (tier === 'signal') {
      list = list.filter(e => e.tier === 'signal' && e.feed_eligible !== false);
    } else if (tier === 'context') {
      list = list.filter(e => e.tier === 'context' && e.feed_eligible !== false);
    } else if (tier === 'noise') {
      list = list.filter(e => e.tier === 'noise' || e.feed_eligible === false);
    }
    list.sort((a, b) => {
      const priority = Number(b.decision_priority || b.materiality || b.score || 0)
        - Number(a.decision_priority || a.materiality || a.score || 0);
      if (priority) return priority;
      return String(b.observed_at || '').localeCompare(String(a.observed_at || ''));
    });
    return list;
  }

  function eventTierSummary(events) {
    return {
      signal: events.filter(e => e.tier === 'signal' && e.feed_eligible !== false).length,
      context: events.filter(e => e.tier === 'context' && e.feed_eligible !== false).length,
      noise: events.filter(e => e.tier === 'noise' || e.feed_eligible === false).length,
      all: events.length,
    };
  }

  function diversifyEvents(events, headSize = 20) {
    const deferred = [];
    const head = [];
    const templateCounts = {};
    const tickerCounts = {};
    for (const event of events) {
      const template = event.template_id || event.title || 'event';
      const ticker = event.ticker || 'portfolio';
      if (head.length < headSize && (templateCounts[template] || 0) < 5 && (tickerCounts[ticker] || 0) < 2) {
        head.push(event);
        templateCounts[template] = (templateCounts[template] || 0) + 1;
        tickerCounts[ticker] = (tickerCounts[ticker] || 0) + 1;
      } else {
        deferred.push(event);
      }
    }
    return head.concat(deferred);
  }

  function renderEventTierTabs(activeTier, summary, escapeHtml) {
    const counts = summary || {};
    const tiers = [
      { id: 'signal', label: `Signal (${counts.signal || 0})` },
      { id: 'context', label: `Context (${counts.context || 0})` },
      { id: 'all', label: `All (${counts.all || 0})` },
      { id: 'noise', label: `Noise (${counts.noise || 0})` },
    ];
    return `<nav class="source-pills" id="insights-event-tier-tabs" style="margin-bottom:10px">
      ${tiers.map(t => `<button type="button" class="filter-btn source-pill${activeTier === t.id ? ' active' : ''}" data-event-tier="${t.id}">${escapeHtml(t.label)}</button>`).join('')}
    </nav>`;
  }

  function eventTierBadge(event) {
    const tier = event.tier || 'context';
    if (tier === 'signal') return 'badge-ok';
    if (tier === 'noise') return 'badge-warn';
    return 'badge-us';
  }

  function parserConfidenceBadge(confidence) {
    const level = String(confidence || 'low').toLowerCase();
    if (level === 'high') return 'badge-ok';
    if (level === 'medium' || level === 'med') return 'badge-us';
    return 'badge-warn';
  }

  function fmtFilingValue(value) {
    if (value == null || Number.isNaN(Number(value))) return '—';
    const num = Number(value);
    if (Math.abs(num) >= 1000) return num.toLocaleString(undefined, { maximumFractionDigits: 0 });
    if (Math.abs(num % 1) > 0.01) return num.toFixed(2);
    return String(num);
  }

  function renderFilingEvidenceLinks(event, linkHtml, ghRepo) {
    const links = [];
    const filingRef = event.source_filing_ref || (event.verification && event.verification.source_filing_ref);
    const extractRef = event.extract_ref || (event.verification && event.verification.extract_ref);
    const filingLabel = event.evidence_label || (event.verification && event.verification.source_label) || 'Filing';
    if (filingRef) {
      links.push(evidenceLink(filingRef, linkHtml, ghRepo, filingLabel));
    }
    if (extractRef) {
      links.push(evidenceLink(extractRef, linkHtml, ghRepo, event.extract_label || 'extract'));
    }
    if (!links.length) {
      return evidenceLink(event.evidence_url || event.evidence_ref, linkHtml, ghRepo, event.evidence_label);
    }
    return links.join(' ');
  }

  function renderEventVerificationStrip(event, escapeHtml) {
    const v = event.verification;
    if (!v || event.source !== 'filing') return '';
    const confClass = parserConfidenceBadge(v.parser_confidence || event.confidence);
    const confLabel = String(v.parser_confidence || event.confidence || 'low').toUpperCase();
    const parts = [
      v.filing_form ? `${v.filing_form}` : null,
      v.filing_date ? `filed ${v.filing_date}` : null,
      v.period_end ? `period ${v.period_end}` : null,
      v.xbrl_tag ? `tag ${v.xbrl_tag}` : null,
    ].filter(Boolean);
    const values = (v.prior_value != null && v.current_value != null)
      ? `Prior ${fmtFilingValue(v.prior_value)} → Current ${fmtFilingValue(v.current_value)} (${v.unit || 'USD thousands'})`
      : (v.current_value != null ? `Current ${fmtFilingValue(v.current_value)} (${v.unit || 'USD thousands'})` : '');
    const flags = (v.parser_flags || []).length
      ? `<span class="badge badge-warn" title="${escapeHtml((v.parser_flags || []).join(', '))}">review</span>`
      : '';
    const review = event.needs_review ? '<span class="badge badge-warn">needs review</span>' : '';
    return `
      <div class="tier-sub filing-verify-strip" style="margin-top:6px;line-height:1.45">
        ${parts.length ? `<span>${escapeHtml(parts.join(' · '))}</span>` : ''}
        ${values ? `<div>${escapeHtml(values)}</div>` : ''}
        <span class="badge ${confClass}" title="Parser confidence">${escapeHtml(confLabel)}</span>
        ${flags}
        ${review}
        ${v.extract_snippet ? `<button type="button" class="filter-btn source-pill filing-verify-btn" data-verify-event="${escapeHtml(event.id || '')}" style="margin-left:6px;padding:2px 8px;font-size:11px">Verify</button>` : ''}
      </div>`;
  }

  function renderFilingVerifyDrawer(events, escapeHtml, linkHtml, ghRepo) {
    const filingEvents = (events || []).filter(e => e.verification && e.source === 'filing');
    if (!filingEvents.length) return '';
    return `
      <div id="filing-verify-drawer" class="detail-section" style="display:none;margin-top:12px;border:1px solid var(--border);border-radius:8px;padding:12px;background:rgba(255,255,255,0.02)">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
          <strong>Filing verification</strong>
          <button type="button" class="filter-btn" id="filing-verify-close">Close</button>
        </div>
        <div id="filing-verify-body"></div>
      </div>`;
  }

  function renderFilingVerifyBody(event, escapeHtml, linkHtml, ghRepo) {
    const v = event.verification || {};
    const snippet = String(v.extract_snippet || '').split('\n').map(line => escapeHtml(line)).join('<br>');
    const allValues = (v.all_values || []).map(val => escapeHtml(fmtFilingValue(val))).join(', ');
    return `
      <p class="tier-sub"><strong>${escapeHtml(event.ticker || '')}</strong> · ${escapeHtml(event.title || '')}</p>
      <p class="tier-sub">${escapeHtml((v.filing_form || 'Filing') + (v.filing_date ? ` filed ${v.filing_date}` : '') + (v.period_end ? ` · period ${v.period_end}` : ''))}</p>
      <div style="display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));margin-top:10px">
        <div class="research-box" style="margin:0">
          <div class="label" style="font-size:11px;color:var(--text-muted);margin-bottom:6px">Extract lines used</div>
          <pre style="white-space:pre-wrap;margin:0;font-size:12px">${snippet || '—'}</pre>
        </div>
        <div class="research-box" style="margin:0">
          <div class="label" style="font-size:11px;color:var(--text-muted);margin-bottom:6px">Parser context</div>
          <div class="tier-sub">Tag: <span class="mono">${escapeHtml(v.xbrl_tag || '—')}</span></div>
          <div class="tier-sub">Confidence: <span class="badge ${parserConfidenceBadge(v.parser_confidence)}">${escapeHtml(String(v.parser_confidence || 'low').toUpperCase())}</span></div>
          <div class="tier-sub">Flags: ${escapeHtml((v.parser_flags || []).join(', ') || 'none')}</div>
          <div class="tier-sub">All parsed values: ${allValues || '—'}</div>
          <div style="margin-top:8px">${renderFilingEvidenceLinks(event, linkHtml, ghRepo)}</div>
        </div>
      </div>`;
  }

  function attachFilingVerifyHandlers(container, events, escapeHtml, linkHtml, ghRepo) {
    if (!container) return;
    const drawer = container.querySelector('#filing-verify-drawer');
    const body = container.querySelector('#filing-verify-body');
    const closeBtn = container.querySelector('#filing-verify-close');
    const byId = Object.fromEntries((events || []).map(e => [e.id, e]));
    container.querySelectorAll('[data-verify-event]').forEach(btn => {
      btn.addEventListener('click', () => {
        const event = byId[btn.dataset.verifyEvent];
        if (!event || !drawer || !body) return;
        body.innerHTML = renderFilingVerifyBody(event, escapeHtml, linkHtml, ghRepo);
        drawer.style.display = 'block';
        drawer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      });
    });
    if (closeBtn && drawer) {
      closeBtn.addEventListener('click', () => {
        drawer.style.display = 'none';
      });
    }
  }

  function renderEventQueue(events, escapeHtml, linkHtml, ghRepo, opts) {
    const eventTier = (opts && opts.eventTier) || 'signal';
    const triageSummary = (opts && opts.triageSummary) || {};
    const rows = filterEvents(events, opts).slice(0, 120);
    const tierTabs = renderEventTierTabs(eventTier, triageSummary, escapeHtml);
    if (!rows.length) {
      return `${tierTabs}<p class="subhead">No ranked events match this view.</p>`;
    }
    return `
      ${tierTabs}
      <table class="darwin-table" id="insights-event-table">
        <thead><tr><th>Relevance</th><th>Date</th><th>Ticker</th><th>Source</th><th>Axis</th><th>Event</th><th>Evidence</th></tr></thead>
        <tbody>
          ${rows.map(e => {
            const directionClass = e.direction === 'bullish' ? 'badge-ok' : (e.direction === 'bearish' ? 'badge-bad' : 'badge-us');
            const ticker = e.ticker ? `<span class="mono">${escapeHtml(e.ticker)}</span>` : '<span class="tier-sub">portfolio</span>';
            const confTip = e.verification
              ? ` title="Parser ${escapeHtml(String(e.verification.parser_confidence || e.confidence || 'med'))}${e.needs_review ? ' · needs review' : ''}"`
              : '';
            const tierLabel = String(e.tier || 'context');
            const reviewBadge = e.triage_verdict === 'human_review'
              ? ' <span class="badge badge-warn">review</span>'
              : '';
            return `
              <tr>
                <td class="mono"${confTip}><span class="badge ${eventTierBadge(e)}">${escapeHtml(tierLabel)}</span> ${Number(e.materiality || e.score || 0)}${reviewBadge}</td>
                <td class="mono">${escapeHtml(e.observed_at || 'n/a')}</td>
                <td>${ticker}</td>
                <td><span class="badge badge-us">${escapeHtml(e.source_label || SOURCE_LABEL[e.source] || e.source || 'source')}</span></td>
                <td>${escapeHtml(AXIS_LABEL[e.impact_axis] || e.impact_axis || 'context')}</td>
                <td style="min-width:280px">
                  <div><span class="badge ${directionClass}">${escapeHtml(e.direction || 'neutral')}</span> <strong>${escapeHtml(e.title || 'Insight')}</strong></div>
                  <div class="tier-sub" style="margin-top:4px">${escapeHtml((e.summary || '').slice(0, 220))}</div>
                  ${renderEventVerificationStrip(e, escapeHtml)}
                </td>
                <td>${renderFilingEvidenceLinks(e, linkHtml, ghRepo)}</td>
              </tr>`;
          }).join('')}
        </tbody>
      </table>
      ${renderFilingVerifyDrawer(events, escapeHtml, linkHtml, ghRepo)}
      ${(events || []).length > rows.length ? `<p class="tier-sub">${(events || []).length - rows.length} more events outside the current table window.</p>` : ''}`;
  }

  function eventSelect(id, label, value, choices, escapeHtml) {
    return `<label class="event-filter"><span>${escapeHtml(label)}</span><select id="${id}">
      ${choices.map(choice => `<option value="${escapeHtml(choice.value)}"${choice.value === value ? ' selected' : ''}>${escapeHtml(choice.label)}</option>`).join('')}
    </select></label>`;
  }

  function renderEventEvidence(event, escapeHtml, linkHtml, ghRepo) {
    const items = event.evidence_items || [];
    if (items.length) {
      return items.slice(0, 3).map(item => evidenceLink(
        item.url || item.ref, linkHtml, ghRepo, item.label || item.source || 'source',
      )).join(' ');
    }
    const fallback = renderFilingEvidenceLinks(event, linkHtml, ghRepo);
    if (fallback && fallback !== 'â€”') return fallback;
    return '<span class="event-evidence-missing">Evidence missing</span>';
  }

  function renderEventFilterBar(events, opts, escapeHtml) {
    const sources = Array.from(new Set((events || []).map(e => e.source).filter(Boolean))).sort();
    const axes = Array.from(new Set((events || []).map(e => e.impact_axis).filter(Boolean))).sort();
    return `<div class="event-filter-bar" data-testid="event-filter-bar">
      ${eventSelect('event-range-filter', 'Time', opts.eventRange || 'last7', [
        { value: 'last7', label: 'Last 7 days' }, { value: 'since_last', label: 'Since last review' },
        { value: 'last30', label: 'Last 30 days' }, { value: 'last90', label: 'Last 90 days' },
        { value: 'ytd', label: 'Year to date' }, { value: 'all', label: 'All retained history' },
      ], escapeHtml)}
      ${eventSelect('event-scope-filter', 'Scope', opts.eventScope || 'holdings', [
        { value: 'holdings', label: 'Holdings' }, { value: 'watchlist', label: 'Watchlist' },
        { value: 'all', label: 'Research universe' },
      ], escapeHtml)}
      ${eventSelect('event-kind-filter', 'Timing', opts.eventKind || 'observed', [
        { value: 'observed', label: 'Occurred' }, { value: 'scheduled', label: 'Upcoming' },
        { value: 'all', label: 'Occurred + upcoming' },
      ], escapeHtml)}
      ${eventSelect('event-source-filter', 'Source', opts.eventSource || 'all', [
        { value: 'all', label: 'All sources' }, ...sources.map(source => ({ value: source, label: SOURCE_LABEL[source] || source })),
      ], escapeHtml)}
      ${eventSelect('event-axis-filter', 'Impact', opts.eventAxis || 'all', [
        { value: 'all', label: 'All impacts' }, ...axes.map(axis => ({ value: axis, label: AXIS_LABEL[axis] || axis })),
      ], escapeHtml)}
      ${eventSelect('event-direction-filter', 'Direction', opts.eventDirection || 'all', [
        { value: 'all', label: 'Any direction' }, { value: 'bullish', label: 'Bullish' },
        { value: 'bearish', label: 'Bearish' }, { value: 'neutral', label: 'Neutral / mixed' },
      ], escapeHtml)}
      ${eventSelect('event-confidence-filter', 'Confidence', opts.eventConfidence || 'all', [
        { value: 'all', label: 'Any confidence' }, { value: 'high', label: 'High' },
        { value: 'med', label: 'Medium' }, { value: 'low', label: 'Low' },
      ], escapeHtml)}
      ${eventSelect('event-review-filter', 'Workflow', opts.eventReview || 'unreviewed', [
        { value: 'unreviewed', label: 'Unreviewed' }, { value: 'all', label: 'All items' },
        { value: 'reviewed', label: 'Reviewed' }, { value: 'saved', label: 'Saved' },
        { value: 'needs_review', label: 'Needs verification' }, { value: 'muted', label: 'Muted templates' },
      ], escapeHtml)}
      <button type="button" class="filter-btn event-reset-btn" id="event-reset-filters">Reset</button>
    </div>`;
  }

  function renderEventSummary(baseEvents, opts) {
    const reviewed = (opts.reviewState || {}).reviewed || {};
    const lastSeen = opts.lastSeenAt ? new Date(opts.lastSeenAt).getTime() : 0;
    const newCount = baseEvents.filter(e => eventDate(e)?.getTime() > lastSeen).length;
    const thesisCount = baseEvents.filter(e => ['fundamentals', 'risk', 'catalyst', 'capital_allocation'].includes(e.impact_axis)).length;
    const reviewCount = baseEvents.filter(e => e.needs_review || e.triage_verdict === 'human_review').length;
    const scheduledCount = baseEvents.filter(e => e.event_kind === 'scheduled').length;
    const unreviewed = baseEvents.filter(e => !reviewed[e.id]).length;
    return `<div class="event-summary" data-testid="event-summary">
      <div><strong>${baseEvents.length}</strong><span>matching changes</span></div>
      <div><strong>${newCount}</strong><span>new since review</span></div>
      <div><strong>${thesisCount}</strong><span>thesis-relevant</span></div>
      <div><strong>${reviewCount}</strong><span>need verification</span></div>
      <div><strong>${scheduledCount}</strong><span>upcoming</span></div>
      <div><strong>${unreviewed}</strong><span>unreviewed</span></div>
      <button type="button" class="filter-btn" id="event-mark-feed-seen">Mark feed reviewed</button>
    </div>`;
  }

  function renderEventClusters(events, escapeHtml) {
    const groups = {};
    for (const event of events) {
      const key = event.template_id || event.title || 'event';
      if (!groups[key]) groups[key] = { count: 0, title: event.title || 'Related activity' };
      groups[key].count += 1;
    }
    const clusters = Object.values(groups).filter(group => group.count >= 3).sort((a, b) => b.count - a.count).slice(0, 4);
    if (!clusters.length) return '';
    return `<div class="event-clusters"><strong>Clustered activity</strong>${clusters.map(group =>
      `<span title="Repeated events are diversified in the first 20 results">${escapeHtml(group.title)} <b>x${group.count}</b></span>`
    ).join('')}</div>`;
  }

  function renderDecisionEventCard(event, escapeHtml, linkHtml, ghRepo, opts) {
    const reviewState = opts.reviewState || {};
    const isReviewed = Boolean((reviewState.reviewed || {})[event.id]);
    const isSaved = Boolean((reviewState.saved || {})[event.id]);
    const directionClass = event.direction === 'bullish' ? 'badge-ok' : (event.direction === 'bearish' ? 'badge-bad' : 'badge-us');
    const priority = Number(event.decision_priority || event.materiality || event.score || 0);
    const dateLabel = event.event_kind === 'scheduled' ? (event.effective_at || event.observed_at) : event.observed_at;
    return `<article class="event-card${isReviewed ? ' is-reviewed' : ''}" data-event-id="${escapeHtml(event.id || '')}" data-testid="event-card">
      <div class="event-card-topline"><span class="event-priority" title="Decision priority">${priority}</span><span class="badge ${eventTierBadge(event)}">${escapeHtml(event.tier || 'context')}</span><span class="badge ${directionClass}">${escapeHtml(event.direction || 'neutral')}</span><button type="button" class="event-ticker" data-event-open-ticker="${escapeHtml(event.ticker || '')}">${escapeHtml(event.ticker || 'PORTFOLIO')}</button><span>${escapeHtml(event.source_label || SOURCE_LABEL[event.source] || event.source || 'source')}</span><span>${escapeHtml(AXIS_LABEL[event.impact_axis] || event.impact_axis || 'context')}</span><span class="event-date">${escapeHtml(dateLabel || 'n/a')}${event.event_kind === 'scheduled' ? ' - upcoming' : ''}</span></div>
      <div class="event-card-main"><div><h3>${escapeHtml(event.title || 'Insight')}</h3><p class="event-change">${escapeHtml((event.summary || '').slice(0, 360))}</p></div><div class="event-decision-context"><p><span>Why it matters</span>${escapeHtml(event.why_it_matters || 'Review against the current thesis.')}</p><p><span>Follow-up</span>${escapeHtml(event.recommended_follow_up || 'Review the evidence.')}</p></div></div>
      <div class="event-card-footer"><div class="event-evidence">${renderEventEvidence(event, escapeHtml, linkHtml, ghRepo)}</div><div class="event-card-actions">${event.triage_verdict === 'human_review' || event.needs_review ? '<span class="badge badge-warn">needs verification</span>' : ''}${event.evidence_status === 'missing' ? '<span class="badge badge-warn">no evidence link</span>' : ''}<button type="button" class="filter-btn" data-event-detail="${escapeHtml(event.id || '')}">Details</button><button type="button" class="filter-btn" data-event-save="${escapeHtml(event.id || '')}">${isSaved ? 'Saved' : 'Save'}</button><button type="button" class="filter-btn" data-event-reviewed="${escapeHtml(event.id || '')}">${isReviewed ? 'Reviewed' : 'Mark reviewed'}</button><button type="button" class="filter-btn" data-event-mute="${escapeHtml(event.template_id || '')}">Mute pattern</button></div></div>
    </article>`;
  }

  function renderEventDetailBody(event, escapeHtml, linkHtml, ghRepo, reviewState) {
    const v = event.verification || {};
    const note = ((reviewState || {}).notes || {})[event.id] || '';
    const comparison = event.prior_value != null || event.current_value != null
      ? `<div class="event-detail-comparison"><span>Prior <b>${escapeHtml(fmtFilingValue(event.prior_value))}</b></span><span>Current <b>${escapeHtml(fmtFilingValue(event.current_value))}</b></span><span>Change <b>${escapeHtml(event.change_pct != null ? `${event.change_pct}%` : 'n/a')}</b></span></div>`
      : '';
    const rules = (event.triage_rules || []).map(rule => `<span>${escapeHtml(rule)}</span>`).join('');
    const snippet = v.extract_snippet ? `<pre>${escapeHtml(v.extract_snippet)}</pre>` : '';
    return `<div class="event-detail-header"><div><span class="mono">${escapeHtml(event.ticker || 'portfolio')}</span><h3>${escapeHtml(event.title || 'Insight')}</h3></div><button type="button" class="filter-btn" id="event-detail-close">Close</button></div>
      <p>${escapeHtml(event.summary || '')}</p>${comparison}
      <div class="event-detail-grid"><section><h4>Why it matters</h4><p>${escapeHtml(event.why_it_matters || '')}</p></section><section><h4>Recommended follow-up</h4><p>${escapeHtml(event.recommended_follow_up || '')}</p></section><section><h4>Evidence</h4><div>${renderEventEvidence(event, escapeHtml, linkHtml, ghRepo)}</div>${snippet}</section><section><h4>Ranking explanation</h4><p>Priority ${Number(event.decision_priority || 0)} - materiality ${Number(event.materiality || 0)} - confidence ${escapeHtml(event.confidence || 'med')} - novelty ${escapeHtml(event.novelty_score ?? 'n/a')} - evidence ${Number(event.evidence_count || 0)}</p><div class="event-rule-list">${rules}</div></section></div>
      <label class="event-note-label">Research note<textarea id="event-note-input" rows="4" placeholder="Record the thesis implication, disagreement, or next question...">${escapeHtml(note)}</textarea></label>
      <div class="event-detail-actions"><button type="button" class="filter-btn" id="event-note-save" data-event-note-id="${escapeHtml(event.id || '')}">Save note</button><button type="button" class="filter-btn" data-event-open-ticker="${escapeHtml(event.ticker || '')}">Open ticker insights</button></div>`;
  }

  function renderDecisionEventQueue(events, escapeHtml, linkHtml, ghRepo, opts) {
    const options = opts || {};
    const eventTier = options.eventTier || 'signal';
    const baseEvents = baseFilterEvents(events, options);
    const summary = eventTierSummary(baseEvents);
    const ranked = diversifyEvents(filterEvents(events, options));
    const rows = ranked.slice(0, 80);
    const remaining = Math.max(0, ranked.length - rows.length);
    return `<div class="event-feed-intro"><div><strong>Decision feed</strong><span>New information that may change a thesis, valuation, risk, or catalyst.</span></div><span class="event-history-label">Retained ${escapeHtml(options.historyStart || 'n/a')} to ${escapeHtml(options.historyEnd || 'n/a')}</span></div>
      ${renderEventFilterBar(events, options, escapeHtml)}${renderEventSummary(baseEvents, options)}${renderEventTierTabs(eventTier, summary, escapeHtml)}${renderEventClusters(filterEvents(events, { ...options, eventTier: 'all' }), escapeHtml)}
      ${rows.length ? `<div class="event-feed" id="insights-event-feed">${rows.map(event => renderDecisionEventCard(event, escapeHtml, linkHtml, ghRepo, options)).join('')}</div>` : `<div class="event-empty"><strong>No changes match this view.</strong><span>Try widening the time, scope, timing, or workflow filters.</span><button type="button" class="filter-btn" id="event-empty-reset">Clear event filters</button></div>`}
      ${remaining ? `<p class="tier-sub event-more-count">${remaining} more matching ${escapeHtml(eventTier)} event(s) outside the current window.</p>` : ''}
      <aside id="event-detail-drawer" class="event-detail-drawer" style="display:none" aria-live="polite"><div id="event-detail-body"></div></aside>`;
  }

  function attachEventHandlers(container, events, escapeHtml, linkHtml, ghRepo, opts) {
    if (!container) return;
    const options = opts || {};
    const byId = Object.fromEntries((events || []).map(event => [event.id, event]));
    const drawer = container.querySelector('#event-detail-drawer');
    const drawerBody = container.querySelector('#event-detail-body');
    const filterMap = { 'event-range-filter': 'eventRange', 'event-scope-filter': 'eventScope', 'event-kind-filter': 'eventKind', 'event-source-filter': 'eventSource', 'event-axis-filter': 'eventAxis', 'event-direction-filter': 'eventDirection', 'event-confidence-filter': 'eventConfidence', 'event-review-filter': 'eventReview' };
    Object.entries(filterMap).forEach(([id, name]) => {
      const element = container.querySelector(`#${id}`);
      if (element) element.addEventListener('change', () => options.onFilter?.(name, element.value));
    });
    const reset = () => options.onReset?.();
    container.querySelector('#event-reset-filters')?.addEventListener('click', reset);
    container.querySelector('#event-empty-reset')?.addEventListener('click', reset);
    container.querySelector('#event-mark-feed-seen')?.addEventListener('click', () => options.onMarkFeedSeen?.());
    container.querySelectorAll('[data-event-detail]').forEach(button => {
      button.addEventListener('click', () => {
        const event = byId[button.dataset.eventDetail];
        if (!event || !drawer || !drawerBody) return;
        drawerBody.innerHTML = renderEventDetailBody(event, escapeHtml, linkHtml, ghRepo, options.reviewState || {});
        drawer.style.display = 'block';
        drawer.querySelector('#event-detail-close')?.addEventListener('click', () => { drawer.style.display = 'none'; });
        drawer.querySelector('#event-note-save')?.addEventListener('click', () => options.onAction?.('note', event.id, drawer.querySelector('#event-note-input')?.value || ''));
        drawer.querySelectorAll('[data-event-open-ticker]').forEach(tickerButton => tickerButton.addEventListener('click', () => options.onOpenTicker?.(tickerButton.dataset.eventOpenTicker || '')));
        drawer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      });
    });
    container.querySelectorAll('[data-event-reviewed]').forEach(button => button.addEventListener('click', () => options.onAction?.('reviewed', button.dataset.eventReviewed)));
    container.querySelectorAll('[data-event-save]').forEach(button => button.addEventListener('click', () => options.onAction?.('saved', button.dataset.eventSave)));
    container.querySelectorAll('[data-event-mute]').forEach(button => button.addEventListener('click', () => options.onAction?.('muted', button.dataset.eventMute)));
    container.querySelectorAll('[data-event-open-ticker]').forEach(button => button.addEventListener('click', () => options.onOpenTicker?.(button.dataset.eventOpenTicker || '')));
  }

  function filterTickerEssentials(tickers, opts) {
    const { search, bookOnly, sourceFilter, knownTickers } = opts || {};
    let rows = tickers || [];
    if (bookOnly) {
      rows = rows.filter(t => t.in_holdings);
    }
    if (sourceFilter && sourceFilter !== 'all') {
      rows = rows.filter(t => {
        const e = t.essential_insights || {};
        const sources = new Set(e.source_mix || []);
        if (sourceFilter === 'ownership') {
          return sources.has('superinvestor_letter') || sources.has('insider') || e.owner;
        }
        if (sourceFilter === 'letters') {
          return sources.has('superinvestor_letter') || e.owner?.source === 'superinvestor_letter';
        }
        if (sourceFilter === 'podcast_episode' || sourceFilter === 'podcasts') {
          return sources.has('podcast_episode');
        }
        if (sourceFilter === 'macro') {
          return e.macro_only || sources.has('macro');
        }
        return sources.has(sourceFilter);
      });
    }
    if (search) {
      const tickers = knownTickers || [];
      rows = rows.filter(t => SearchMatch.matchTickerEssential(t, search, tickers));
    }
    return rows;
  }

  function wmClassShort(cls) {
    if (!cls) return 'P?';
    const m = String(cls).match(/^P(\d)/);
    return m ? `P${m[1]}` : String(cls);
  }

  function wmTrimStance(text, maxLen) {
    let s = String(text || '').replace(/^\[[^\]]+\]\s*/, '').trim();
    const max = maxLen || 120;
    if (s.length <= max) return s;
    return `${s.slice(0, max - 1).trim()}…`;
  }

  function wmFormatNumber(v, unit) {
    if (v == null || v === '') return '—';
    const n = Number(v);
    if (!Number.isFinite(n)) return String(v);
    const u = String(unit || '').toLowerCase();
    if (u.includes('ratio') || Math.abs(n) < 1 && Math.abs(n) > 0) return n.toFixed(Math.abs(n) < 0.1 ? 4 : 3);
    if (u.includes('year') || Number.isInteger(n) || Math.abs(n - Math.round(n)) < 1e-9) {
      if (Math.abs(n) >= 1000) return String(Math.round(n));
      return String(Math.round(n * 100) / 100);
    }
    if (Math.abs(n) >= 100) return n.toFixed(1);
    if (Math.abs(n) >= 10) return n.toFixed(2);
    return n.toFixed(2);
  }

  function wmKpiLabel(row, strip) {
    const id = String((row && row.kpi_id) || '');
    let label = (row && row.label) || '';
    // Enrich P0 horizon quote rows with latest speaker from expert_horizons
    if (/_years_ahead$/.test(id) && strip) {
      const domain = id.replace(/_years_ahead$/, '');
      const h = (strip.expert_horizons || []).find(x => x.domain === domain);
      const latest = (h && h.latest) || {};
      const bits = ['P0'];
      if (latest.speaker) bits.push(String(latest.speaker));
      if (latest.years_ahead != null) bits.push(`${wmFormatNumber(latest.years_ahead)}y`);
      if (!label) label = id.replace(/_/g, ' ');
      if (!/P0/.test(label)) label = `${label} (${bits.join(' · ')})`;
    }
    if (label) {
      return label.length > 64 ? `${label.slice(0, 63)}…` : label;
    }
    return id.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) || '—';
  }

  function wmIsSharedThemeKpi(row) {
    if (!row) return false;
    const mode = row.magis_display && row.magis_display.mode;
    if (mode === 'shared_theme') return true;
    const src = String(row.source || '');
    return src.startsWith('theme:');
  }

  function wmSharedKey(row) {
    return String((row && row.source) || (row && row.kpi_id) || '');
  }

  function wmHideZScore(row) {
    const id = String((row && row.kpi_id) || '');
    if (id === 'price_usd') return true;
    if (/_years_ahead$/.test(id)) return true; // sparse quote series — z not meaningful
    return false;
  }

  function wmIndustryKey(row) {
    const ids = (row && row.industry_node_ids) || [];
    return ids[0] || 'other';
  }

  function wmIndustryTitle(key) {
    const titles = {
      robotaxi: 'robotaxi / AV ground',
      evtol_air_taxi: 'eVTOL / air taxi',
      pharma_royalty: 'pharma royalty',
      btc_mining_power: 'BTC mining / power',
      market_data_indices: 'index / market-data fees',
      ai_power: 'AI power / land',
      water_surface: 'water / surface',
      hyperscaler_cloud: 'hyperscaler cloud',
      nuclear_firm_power: 'nuclear / SMR',
      gold_royalty: 'gold royalty',
      timber_land: 'timber / housing',
      energy_royalty: 'energy royalty',
      exchange_markets: 'exchange markets',
      agi: 'AGI horizon',
    };
    return titles[key] || String(key || 'other').replace(/_/g, ' ');
  }

  function wmZValue(row) {
    if (wmHideZScore(row)) return null;
    const hist = (row && row.history) || {};
    const z = hist.z_score != null ? hist.z_score : (row && row.z_score);
    return z == null || Number.isNaN(Number(z)) ? null : Number(z);
  }

  function wmIsOutlier(row) {
    const z = wmZValue(row);
    return z != null && Math.abs(z) >= 2;
  }

  function wmGateText(row) {
    const exp = (row && row.expected) || {};
    if (!exp.op || exp.value == null) return '';
    return `${exp.op} ${wmFormatNumber(exp.value)}`;
  }

  function wmWhyText(row) {
    const kind = row._kind || row.status || '';
    if (kind === 'hard' || kind === 'fail') return 'Hard gate miss';
    if (kind === 'soft' || kind === 'soft-floor') return 'Soft floor (Goodhart)';
    if (kind === 'stale') return 'Stale actual';
    if (kind === 'unchecked') return 'Needs value';
    if (wmIsOutlier(row)) return `|z| elevated`;
    return kind || '—';
  }

  // Prefer theme_panel_config evidence; keep a UI fallback map in sync with ingest themes.
  const WM_THEME_SERIES = {
    ai_power_land: ['theme:hyperscaler_capex_ttm_usd_bn', 'theme:henry_hub_gas', 'theme:wti_crude'],
    exchange_volatility: ['theme:vix_level', 'theme:spy_20d_realized_vol', 'theme:vol_term_slope'],
    gold_royalties: ['theme:gold_spot_usd', 'theme:gdx_gld_ratio'],
    macro_regime: ['theme:hy_oas', 'theme:ust_10y', 'theme:vix_level'],
    water_surface: ['theme:tpl_water_revenue_m', 'theme:wti_crude', 'theme:permian_crude_production_mbbl_d'],
    timber_housing: ['theme:housing_starts', 'theme:building_permits'],
    btc_hash_power: ['theme:btc_usd', 'theme:henry_hub_gas'],
    energy_royalty: ['theme:wti_crude', 'theme:henry_hub_gas'],
    pharma_royalty: ['theme:xlv_etf', 'theme:xbi_etf', 'theme:ust_10y'],
    nuclear_power: ['theme:ura_etf', 'theme:hyperscaler_capex_ttm_usd_bn'],
    index_data_fees: ['theme:vix_level', 'theme:spy_20d_realized_vol'],
    space_network: [],
  };

  function wmSeriesLatest(historySeries, seriesKey) {
    const s = (historySeries || {})[seriesKey];
    if (!s) return null;
    const pts = s.points || [];
    const last = pts.length ? pts[pts.length - 1] : null;
    const stats = s.stats || {};
    const v = last && last.v != null ? last.v : stats.latest;
    return {
      key: seriesKey,
      label: s.label || seriesKey.replace(/^theme:/, '').replace(/_/g, ' '),
      value: v,
    };
  }

  function wmPillarLights(pillars) {
    const entries = Object.entries(pillars || {});
    if (!entries.length) return '—';
    return entries.map(([, st]) => {
      const s = String(st || '').toLowerCase();
      if (s === 'pass' || s === 'ok' || s === 'strong') return '●';
      if (s === 'partial' || s === 'watch' || s === 'weak') return '◐';
      if (s === 'fail' || s === 'gap' || s === 'missing') return '○';
      return '·';
    }).join('');
  }

  function wmZBadge(z, escapeHtml, opts) {
    if (opts && opts.hidden) {
      return `<span class="badge badge-us" title="Z not shown for this KPI type">—</span>`;
    }
    if (z == null || Number.isNaN(Number(z))) {
      return `<span class="badge badge-us" title="Insufficient history for z-score">n/a</span>`;
    }
    const n = Number(z);
    const abs = Math.abs(n);
    const cls = abs >= 2 ? 'badge-bad' : (abs >= 1 ? 'badge-warn' : 'badge-ok');
    const sign = n > 0 ? '+' : '';
    return `<span class="badge ${cls}" title="Vs trailing history only — descriptive; not a Magis gate">${escapeHtml(sign + n.toFixed(2))}</span>`;
  }

  function wmSparklineSvg(values, width, height) {
    const vals = (values || []).map(Number).filter(v => Number.isFinite(v));
    const w = width || 72;
    const h = height || 22;
    if (vals.length < 2) {
      return `<svg width="${w}" height="${h}" aria-hidden="true"></svg>`;
    }
    const min = Math.min(...vals);
    const max = Math.max(...vals);
    const span = max - min || 1;
    const pts = vals.map((v, i) => {
      const x = (i / (vals.length - 1)) * (w - 2) + 1;
      const y = h - 2 - ((v - min) / span) * (h - 4);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
    return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true" style="display:block">
      <polyline fill="none" stroke="currentColor" stroke-width="1.25" opacity="0.85" points="${pts}"/>
    </svg>`;
  }

  function wmHistoryChartSvg(points, stats, width, height) {
    const pts = (points || []).filter(p => p && p.d != null && Number.isFinite(Number(p.v)));
    const w = width || 420;
    const h = height || 120;
    if (pts.length < 2) {
      return `<p class="tier-sub">Not enough history points for a chart.</p>`;
    }
    const vals = pts.map(p => Number(p.v));
    const mean = stats && stats.mean != null ? Number(stats.mean) : null;
    const stdev = stats && stats.stdev != null ? Number(stats.stdev) : null;
    let min = Math.min(...vals);
    let max = Math.max(...vals);
    if (mean != null && stdev != null && Number.isFinite(stdev)) {
      min = Math.min(min, mean - stdev);
      max = Math.max(max, mean + stdev);
    }
    const span = max - min || 1;
    const padL = 36;
    const padR = 8;
    const padT = 8;
    const padB = 22;
    const iw = w - padL - padR;
    const ih = h - padT - padB;
    const xy = (i, v) => {
      const x = padL + (i / (pts.length - 1)) * iw;
      const y = padT + ih - ((v - min) / span) * ih;
      return [x, y];
    };
    const line = vals.map((v, i) => {
      const [x, y] = xy(i, v);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
    let band = '';
    if (mean != null && stdev != null && stdev > 0) {
      const [, yHi] = xy(0, mean + stdev);
      const [, yLo] = xy(0, mean - stdev);
      band = `<rect x="${padL}" y="${Math.min(yHi, yLo).toFixed(1)}" width="${iw}" height="${Math.abs(yLo - yHi).toFixed(1)}" fill="currentColor" opacity="0.08"/>`;
      const [, yM] = xy(0, mean);
      band += `<line x1="${padL}" y1="${yM.toFixed(1)}" x2="${w - padR}" y2="${yM.toFixed(1)}" stroke="currentColor" stroke-dasharray="3 3" opacity="0.45"/>`;
    }
    const [lx, ly] = xy(pts.length - 1, vals[vals.length - 1]);
    const d0 = pts[0].d;
    const d1 = pts[pts.length - 1].d;
    const y0 = min.toFixed(min >= 100 ? 0 : 2);
    const y1 = max.toFixed(max >= 100 ? 0 : 2);
    return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" role="img" aria-label="KPI history">
      ${band}
      <polyline fill="none" stroke="var(--accent, #6aa1ff)" stroke-width="1.6" points="${line}"/>
      <circle cx="${lx.toFixed(1)}" cy="${ly.toFixed(1)}" r="3.2" fill="var(--accent, #6aa1ff)"/>
      <text x="${padL}" y="${h - 6}" font-size="10" fill="currentColor" opacity="0.65">${d0}</text>
      <text x="${w - padR}" y="${h - 6}" font-size="10" fill="currentColor" opacity="0.65" text-anchor="end">${d1}</text>
      <text x="4" y="${padT + 8}" font-size="10" fill="currentColor" opacity="0.65">${y1}</text>
      <text x="4" y="${h - padB}" font-size="10" fill="currentColor" opacity="0.65">${y0}</text>
    </svg>`;
  }

  function wmHistoryDetailRow(r, historySeries, escapeHtml, colSpan) {
    const hist = r.history || {};
    const key = hist.series_key || r.series_key || '';
    const series = (historySeries && key && historySeries[key]) || null;
    const stats = (series && series.stats) || hist;
    const points = (series && series.points) || [];
    const rowId = `${r.ticker || ''}__${r.kpi_id || ''}`.replace(/[^\w.\-]+/g, '_');
    const zLine = hist.z_score != null
      ? `z=${Number(hist.z_score) >= 0 ? '+' : ''}${Number(hist.z_score).toFixed(2)}`
      : 'z=n/a';
    const meanLine = stats.mean != null ? `mean ${Number(stats.mean).toPrecision(4)}` : '';
    const sdLine = stats.stdev != null ? `σ ${Number(stats.stdev).toPrecision(4)}` : '';
    const nLine = stats.n != null ? `n=${stats.n}` : '';
    const pctLine = stats.percentile != null ? `pct ${stats.percentile}` : '';
    const win = stats.window || hist.window || '';
    const meta = [zLine, meanLine, sdLine, nLine, pctLine, win, hist.source_kind || '', hist.status || '']
      .filter(Boolean).join(' · ');
    return `<tr class="wm-hist-detail" data-wm-hist-detail="${escapeHtml(rowId)}" hidden>
      <td colspan="${colSpan || 7}" style="padding:10px 12px;background:rgba(127,127,127,0.06)">
        <div style="display:flex;flex-wrap:wrap;gap:14px;align-items:flex-start">
          <div style="min-width:280px;flex:1 1 320px">${wmHistoryChartSvg(points, stats)}</div>
          <div style="flex:1 1 220px;font-size:12px;max-width:420px">
            <div class="mono" style="margin-bottom:4px">${escapeHtml(key || 'no series')}</div>
            <div class="tier-sub" style="margin-bottom:6px">${escapeHtml(meta)}</div>
            <div class="tier-sub">Descriptive vs own history. Does not change the gate or capital stance.</div>
          </div>
        </div>
      </td>
    </tr>`;
  }

  function wmKpiHistCells(r, escapeHtml) {
    const hist = r.history || {};
    const spark = wmSparklineSvg(hist.sparkline || []);
    const rowId = `${r.ticker || ''}__${r.kpi_id || ''}__${String(r.source || '').replace(/:/g, '_')}`
      .replace(/[^\w.\-]+/g, '_');
    const title = 'Click to view time series and vs-history detail';
    const actualTxt = r.actual != null ? wmFormatNumber(r.actual, r.unit) : '—';
    const hideZ = wmHideZScore(r);
    const zVal = hideZ ? null : (hist.z_score != null ? hist.z_score : r.z_score);
    return {
      rowId,
      actualCell: `<td class="mono"><button type="button" class="wm-hist-toggle" data-wm-hist-toggle="${escapeHtml(rowId)}" title="${title}" style="all:unset;cursor:pointer;color:inherit">${escapeHtml(actualTxt)}</button></td>`,
      sparkCell: `<td class="wm-spark"><button type="button" class="wm-hist-toggle" data-wm-hist-toggle="${escapeHtml(rowId)}" title="${title}" style="all:unset;cursor:pointer;color:inherit">${spark}</button></td>`,
      zCell: `<td><button type="button" class="wm-hist-toggle" data-wm-hist-toggle="${escapeHtml(rowId)}" title="${title}" style="all:unset;cursor:pointer">${wmZBadge(zVal, escapeHtml, { hidden: hideZ })}</button></td>`,
    };
  }

  function hkFmtUsd(v, digits) {
    if (v == null || !Number.isFinite(Number(v))) return '—';
    const n = Number(v);
    if (Math.abs(n) >= 1000) return '$' + n.toLocaleString(undefined, { maximumFractionDigits: digits != null ? digits : 0 });
    return '$' + n.toLocaleString(undefined, { maximumFractionDigits: digits != null ? digits : 2 });
  }

  function hkFmtAxisUsd(v) {
    if (!Number.isFinite(v) || v <= 0) return '';
    if (v >= 1e6) return '$' + (v / 1e6).toFixed(v >= 1e7 ? 0 : 1) + 'M';
    if (v >= 1000) return '$' + Math.round(v / 1000) + 'k';
    if (v >= 1) return '$' + String(Math.round(v));
    return '$' + v.toFixed(2);
  }

  function hkDialLabel(raw) {
    const map = {
      on_schedule: 'On schedule',
      below_model: 'Below model',
      above_model: 'Above model',
      below_cost_floor: 'Below cost floor',
      insufficient_model: 'No model yet',
    };
    return map[raw] || String(raw || 'n/a').replace(/_/g, ' ');
  }

  function hkDownsample(pts, maxN) {
    if (!pts || pts.length <= maxN) return pts || [];
    const step = Math.ceil(pts.length / maxN);
    const out = pts.filter((_, i) => i % step === 0);
    const last = pts[pts.length - 1];
    if (out[out.length - 1] !== last) out.push(last);
    return out;
  }

  function hkSmoothSeries(pts, windowSize) {
    const win = Math.max(1, windowSize || 7);
    if (!pts || pts.length <= 2) return pts || [];
    const out = [];
    for (let i = 0; i < pts.length; i++) {
      const a = Math.max(0, i - Math.floor(win / 2));
      const b = Math.min(pts.length, a + win);
      let sum = 0;
      let n = 0;
      for (let j = a; j < b; j++) {
        if (Number.isFinite(pts[j].v)) {
          sum += pts[j].v;
          n += 1;
        }
      }
      out.push({ d: pts[i].d, v: n ? sum / n : pts[i].v });
    }
    return out;
  }

  function hkFilterByTime(pts, tMin, tMax, parse) {
    return (pts || []).filter((p) => {
      const t = parse(p.d);
      return Number.isFinite(t) && t >= tMin && t <= tMax && Number.isFinite(p.v);
    });
  }

  function hkBandPath(floorPts, premPts, xScale, yScale, parse) {
    if (!floorPts.length || !premPts.length) return '';
    const n = Math.min(floorPts.length, premPts.length);
    const top = [];
    const bot = [];
    for (let i = 0; i < n; i++) {
      top.push(`${i ? 'L' : 'M'}${xScale(parse(floorPts[i].d)).toFixed(1)},${yScale(floorPts[i].v).toFixed(1)}`);
      bot.push(`L${xScale(parse(premPts[n - 1 - i].d)).toFixed(1)},${yScale(premPts[n - 1 - i].v).toFixed(1)}`);
    }
    return `<path d="${top.join(' ')} ${bot.join(' ')} Z" fill="rgba(248,113,113,0.14)" stroke="none" />`;
  }

  function hkLogChart(doc, opts) {
    const options = opts || {};
    const zoom = options.zoom === 'full' ? 'full' : 'recent';
    const demand = (doc && doc.demand) || {};
    const supply = (doc && doc.supply) || {};
    const hkRef = (doc && doc.hk_reference) || {};
    const actual = demand.actual_path || [];
    const model = demand.model_path || [];
    const costPath = supply.cost_path || [];
    const supplyCurve = supply.curve || [];
    const spot = ((doc && doc.spot) || {}).btc_usd;
    const dial = (doc && doc.dial) || {};
    const w = options.width || 920;
    const h = options.height || 540;
    const pad = { t: 22, r: 18, b: 36, l: 58 };
    const Y_FLOOR = zoom === 'full' ? 1 : 100;
    const parse = (d) => Date.parse(String(d) + 'T00:00:00Z');

    let rawA = (actual || []).filter((p) => p && p.v >= Y_FLOOR && p.d);
    let rawM = (model || []).filter((p) => p && p.v >= Y_FLOOR && p.d);
    if (!rawA.length && !rawM.length) {
      return '<p class="tier-sub">No price path yet. Run fetch_crypto_panel.py.</p>';
    }

    const halvingIso = ((supply.assumptions || {}).next_halving) || '2028-04-15';
    const halvingT = parse(halvingIso);
    let tMin = Math.min(...rawA.concat(rawM).map((p) => parse(p.d)));
    let tMax = Math.max(...rawA.concat(rawM).map((p) => parse(p.d)));
    if (Number.isFinite(halvingT)) tMax = Math.max(tMax, halvingT);
    if (zoom === 'recent') {
      const recentStart = parse('2017-01-01');
      if (Number.isFinite(recentStart)) tMin = Math.max(tMin, recentStart);
    }
    if (!(tMax > tMin)) tMax = tMin + 1;

    rawA = hkFilterByTime(rawA, tMin, tMax, parse);
    rawM = hkFilterByTime(rawM, tMin, tMax, parse);
    const ptsA = hkDownsample(rawA, zoom === 'full' ? 360 : 280);
    const ptsM = hkDownsample(rawM, zoom === 'full' ? 240 : 200);

    const rawFloor = (costPath.length
      ? costPath.map((p) => ({ d: p.d || p.date, v: Number(p.v || p.all_in_cost_usd) }))
      : supplyCurve.map((p) => ({ d: p.date, v: Number(p.all_in_cost_usd) }))
    ).filter((p) => p.d && p.v >= 1000);
    const premMult = Number((supply.assumptions || {}).premium_multiple) || 1.75;
    const rawPrem = (costPath.length
      ? costPath.map((p) => ({
        d: p.d || p.date,
        v: Number(p.v || p.all_in_cost_usd) * premMult,
      }))
      : supplyCurve.map((p) => ({ d: p.date, v: Number(p.premium_band_usd || p.all_in_cost_usd) }))
    ).filter((p) => p.d && p.v >= 1000);

    const floorSeries = hkDownsample(
      hkSmoothSeries(hkFilterByTime(rawFloor, tMin, tMax, parse), 14),
      90,
    );
    const premSeries = hkDownsample(
      hkSmoothSeries(hkFilterByTime(rawPrem, tMin, tMax, parse), 14),
      90,
    );

    const allVals = ptsA.concat(ptsM).concat(floorSeries).concat(premSeries).map((p) => p.v);
    let vMin = allVals.length ? Math.min(...allVals) : Y_FLOOR;
    let vMax = allVals.length ? Math.max(...allVals) : Y_FLOOR * 10;
    if (hkRef.model_2028) vMax = Math.max(vMax, Number(hkRef.model_2028));
    if (hkRef.supply_high) vMax = Math.max(vMax, Number(hkRef.supply_high));
    if (spot && spot > 0) {
      vMin = Math.min(vMin, spot);
      vMax = Math.max(vMax, spot);
    }
    vMin = Math.max(vMin, Y_FLOOR);
    const logMin = Math.log10(vMin) - 0.04;
    const logMax = Math.log10(vMax) + 0.1;
    const xScale = (t) => pad.l + ((t - tMin) / (tMax - tMin)) * (w - pad.l - pad.r);
    const yScale = (v) => {
      const lv = Math.log10(Math.max(v, Y_FLOOR));
      return pad.t + (1 - (lv - logMin) / Math.max(logMax - logMin, 1e-9)) * (h - pad.t - pad.b);
    };
    const poly = (pts, stroke, widthPx, dash, opacity) => {
      if (!pts.length) return '';
      const d = pts.map((p, i) => `${i ? 'L' : 'M'}${xScale(parse(p.d)).toFixed(1)},${yScale(p.v).toFixed(1)}`).join(' ');
      return `<path d="${d}" fill="none" stroke="${stroke}" stroke-width="${widthPx}" stroke-linecap="round" stroke-linejoin="round" opacity="${opacity == null ? 1 : opacity}" ${dash ? `stroke-dasharray="${dash}"` : ''} />`;
    };

    const years = [];
    const y0 = new Date(tMin).getUTCFullYear();
    const y1 = new Date(tMax).getUTCFullYear();
    for (let y = y0; y <= y1; y += 1) years.push(y);
    const yTicks = [];
    for (let e = Math.ceil(logMin); e <= Math.floor(logMax); e++) {
      const v = Math.pow(10, e);
      if (v >= Y_FLOOR) yTicks.push(v);
    }
    const guideLevels = [150000, 250000, 270000].filter((v) => v > vMin && v <= vMax * 1.05);

    const asOfT = doc.as_of ? parse(doc.as_of) : Date.now();
    const spotX = xScale(Math.min(tMax, Number.isFinite(asOfT) ? asOfT : Date.now()));
    const spotMark = spot && spot > 0
      ? `<circle cx="${spotX.toFixed(1)}" cy="${yScale(spot).toFixed(1)}" r="5.5" fill="#60a5fa" stroke="#0b1220" stroke-width="2" />`
      : '';
    const halvingGuide = Number.isFinite(halvingT) && halvingT >= tMin && halvingT <= tMax
      ? `<line x1="${xScale(halvingT).toFixed(1)}" y1="${pad.t}" x2="${xScale(halvingT).toFixed(1)}" y2="${h - pad.b}" stroke="rgba(255,255,255,0.22)" stroke-width="1.25" stroke-dasharray="4 4" />
         <text x="${xScale(halvingT).toFixed(1)}" y="${(h - pad.b + 14).toFixed(1)}" text-anchor="middle" font-size="11" fill="currentColor" opacity="0.7">Apr 2028</text>`
      : '';
    const hkDot = hkRef.model_2028 && Number.isFinite(halvingT) && halvingT >= tMin
      ? `<circle cx="${xScale(halvingT).toFixed(1)}" cy="${yScale(Number(hkRef.model_2028)).toFixed(1)}" r="5" fill="#f472b6" stroke="#0b1220" stroke-width="1.5" />`
      : '';
    const bandLoDot = hkRef.supply_low && Number.isFinite(halvingT) && halvingT >= tMin
      ? `<circle cx="${xScale(halvingT).toFixed(1)}" cy="${yScale(Number(hkRef.supply_low)).toFixed(1)}" r="3.5" fill="#f87171" opacity="0.9" />`
      : '';
    const bandHiDot = hkRef.supply_high && Number.isFinite(halvingT) && halvingT >= tMin
      ? `<circle cx="${xScale(halvingT).toFixed(1)}" cy="${yScale(Number(hkRef.supply_high)).toFixed(1)}" r="3.5" fill="#34d399" opacity="0.9" />`
      : '';

    const residual = dial.spot_vs_model_pct;
    const residualTxt = residual != null && Number.isFinite(Number(residual))
      ? `${Number(residual) > 0 ? '+' : ''}${Number(residual).toFixed(0)}% vs model`
      : '';
    const floorNow = floorSeries.length ? floorSeries[floorSeries.length - 1].v : supply.halving_2028_cost_usd;
    const premNow = premSeries.length ? premSeries[premSeries.length - 1].v : supply.halving_2028_premium_band_usd;
    const modelNow = demand.model_price_as_of;

    const rail = `<aside class="hk-callout-rail" aria-label="Key levels">
      <div class="hk-callout"><span class="hk-callout-swatch" style="background:#60a5fa"></span><div><div class="hk-callout-label">Spot now</div><div class="hk-callout-value">${hkFmtUsd(spot)}</div><div class="hk-callout-sub">${residualTxt || '—'}</div></div></div>
      <div class="hk-callout"><span class="hk-callout-swatch" style="background:#fbbf24"></span><div><div class="hk-callout-label">Demand model</div><div class="hk-callout-value">${hkFmtUsd(modelNow)}</div><div class="hk-callout-sub">as of ${String(doc.as_of || '—')}</div></div></div>
      <div class="hk-callout"><span class="hk-callout-swatch" style="background:#f87171"></span><div><div class="hk-callout-label">Cost floor</div><div class="hk-callout-value">${hkFmtUsd(floorNow)}</div><div class="hk-callout-sub">smoothed live</div></div></div>
      <div class="hk-callout"><span class="hk-callout-swatch" style="background:#34d399"></span><div><div class="hk-callout-label">Cost +75%</div><div class="hk-callout-value">${hkFmtUsd(premNow)}</div><div class="hk-callout-sub">premium band</div></div></div>
      <div class="hk-callout"><span class="hk-callout-swatch" style="background:#f472b6"></span><div><div class="hk-callout-label">HK 2028</div><div class="hk-callout-value">${hkFmtUsd(hkRef.model_2028)}</div><div class="hk-callout-sub">quote target</div></div></div>
      <div class="hk-callout"><span class="hk-callout-swatch" style="background:linear-gradient(180deg,#34d399,#f87171)"></span><div><div class="hk-callout-label">2028 supply band</div><div class="hk-callout-value">${hkFmtUsd(hkRef.supply_low)}–${hkFmtUsd(hkRef.supply_high)}</div><div class="hk-callout-sub">HK reference</div></div></div>
    </aside>`;

    const svg = `<svg class="hk-chart" viewBox="0 0 ${w} ${h}" role="img" aria-label="BTC log price versus demand model and cost band">
      <rect x="${pad.l}" y="${pad.t}" width="${w - pad.l - pad.r}" height="${h - pad.t - pad.b}" fill="rgba(255,255,255,0.02)" />
      ${yTicks.map((v) => {
        const y = yScale(v);
        return `<line x1="${pad.l}" y1="${y.toFixed(1)}" x2="${w - pad.r}" y2="${y.toFixed(1)}" stroke="rgba(255,255,255,0.08)" />
          <text x="${pad.l - 8}" y="${(y + 4).toFixed(1)}" text-anchor="end" font-size="12" fill="currentColor" opacity="0.75">${hkFmtAxisUsd(v)}</text>`;
      }).join('')}
      ${guideLevels.map((v) => {
        const y = yScale(v);
        return `<line x1="${pad.l}" y1="${y.toFixed(1)}" x2="${w - pad.r}" y2="${y.toFixed(1)}" stroke="rgba(244,114,182,0.28)" stroke-dasharray="3 5" />
          <text x="${pad.l + 6}" y="${(y - 4).toFixed(1)}" font-size="10" fill="#f9a8d4" opacity="0.85">${hkFmtAxisUsd(v)}</text>`;
      }).join('')}
      ${years.map((y) => {
        const t = Date.parse(y + '-01-01T00:00:00Z');
        if (t < tMin || t > tMax) return '';
        const span = y1 - y0;
        if (span > 12 && y % 2 !== 0) return '';
        const x = xScale(t);
        return `<text x="${x.toFixed(1)}" y="${h - 12}" text-anchor="middle" font-size="12" fill="currentColor" opacity="0.72">${y}</text>`;
      }).join('')}
      ${halvingGuide}
      ${hkBandPath(floorSeries, premSeries, xScale, yScale, parse)}
      ${poly(floorSeries, '#f87171', 1.75, null, 0.7)}
      ${poly(premSeries, '#34d399', 1.75, '5 4', 0.75)}
      ${poly(ptsM, '#fbbf24', 3.25, '9 5', 0.98)}
      ${poly(ptsA, '#60a5fa', 3.4)}
      ${spotMark}
      ${hkDot}
      ${bandLoDot}
      ${bandHiDot}
    </svg>`;

    return `<div class="hk-chart-layout">
      <div class="hk-chart-main">${svg}</div>
      ${rail}
    </div>
    <div class="hk-legend">
      <span><i class="actual"></i>BTC spot</span>
      <span><i class="model"></i>Demand model</span>
      <span><i class="floor"></i>Cost band (floor → +75%)</span>
      <span><i class="hkref"></i>HK 2028 refs</span>
    </div>`;
  }

  function renderHkSnowballPanel(doc, escapeHtml) {
    if (!doc || !doc.demand) {
      return `<details class="wm-panel hk-snowball">
        <summary>BTC snowball (HK)</summary>
        <p class="tier-sub">No model yet. Run: <code>python _system/scripts/fetch_crypto_panel.py</code></p>
      </details>`;
    }
    const dial = doc.dial || {};
    const demand = doc.demand || {};
    const supply = doc.supply || {};
    const fit = demand.fit || {};
    const dialCls = dial.label === 'on_schedule' ? 'badge-ok'
      : (dial.label === 'below_cost_floor' ? 'badge-bad' : 'badge-warn');
    const residual = dial.spot_vs_model_pct;
    const residualTxt = residual != null && Number.isFinite(Number(residual))
      ? `${Number(residual) > 0 ? '+' : ''}${Number(residual).toFixed(0)}%`
      : '—';
    const nextHalving = ((supply.assumptions || {}).next_halving) || '2028-04-15';
    let daysToHalving = '—';
    try {
      const ms = Date.parse(nextHalving + 'T00:00:00Z') - Date.now();
      if (Number.isFinite(ms)) daysToHalving = `${Math.max(0, Math.round(ms / 86400000))} days`;
    } catch (_) { /* ignore */ }
    const kTxt = fit.k != null
      ? `${Number(fit.k).toFixed(2)}${fit.r2_log != null ? ` · R² ${Number(fit.r2_log).toFixed(2)}` : ''}`
      : '—';
    return `<details class="wm-panel hk-snowball" open>
      <summary>BTC snowball (HK) <span class="tier-sub">Demand path · cost floor</span></summary>
      <p class="hk-snowball-lede">${escapeHtml(dial.plain_english || '')}</p>
      <div class="hk-metric-grid">
        <div class="hk-metric hk-metric-status">
          <span class="hk-metric-label">Status</span>
          <span class="badge ${dialCls}">${escapeHtml(hkDialLabel(dial.label))}</span>
          <span class="hk-metric-sub">${escapeHtml(String(doc.as_of || ''))}</span>
        </div>
        <div class="hk-metric">
          <span class="hk-metric-label">Spot</span>
          <span class="hk-metric-value">${escapeHtml(hkFmtUsd((doc.spot || {}).btc_usd))}</span>
          <span class="hk-metric-sub">vs model ${escapeHtml(residualTxt)}</span>
        </div>
        <div class="hk-metric">
          <span class="hk-metric-label">Model now</span>
          <span class="hk-metric-value">${escapeHtml(hkFmtUsd(demand.model_price_as_of))}</span>
          <span class="hk-metric-sub">k = ${escapeHtml(kTxt)}</span>
        </div>
        <div class="hk-metric">
          <span class="hk-metric-label">2028 model</span>
          <span class="hk-metric-value">${escapeHtml(hkFmtUsd(demand.model_price_2028_04_15))}</span>
          <span class="hk-metric-sub">HK ref ${escapeHtml(hkFmtUsd((doc.hk_reference || {}).model_2028))}</span>
        </div>
        <div class="hk-metric">
          <span class="hk-metric-label">2028 cost floor</span>
          <span class="hk-metric-value">${escapeHtml(hkFmtUsd(supply.halving_2028_cost_usd))}</span>
          <span class="hk-metric-sub">+75% ${escapeHtml(hkFmtUsd(supply.halving_2028_premium_band_usd))}</span>
        </div>
        <div class="hk-metric">
          <span class="hk-metric-label">Next halving</span>
          <span class="hk-metric-value">${escapeHtml(daysToHalving)}</span>
          <span class="hk-metric-sub">${escapeHtml(nextHalving)}</span>
        </div>
      </div>
      <div class="hk-snowball-grid">
        <div class="hk-snowball-card" data-hk-chart-root>
          <div class="hk-chart-header">
            <h4>BTC log path</h4>
            <div class="hk-zoom-toggle" role="group" aria-label="Chart time range">
              <button type="button" class="filter-btn source-pill active" data-hk-zoom="recent">2017–2028</button>
              <button type="button" class="filter-btn source-pill" data-hk-zoom="full">Full history</button>
            </div>
          </div>
          <div class="hk-zoom-panel" data-hk-zoom-panel="recent">${hkLogChart(doc, { zoom: 'recent' })}</div>
          <div class="hk-zoom-panel" data-hk-zoom-panel="full" hidden>${hkLogChart(doc, { zoom: 'full' })}</div>
        </div>
      </div>
      <p class="tier-sub" style="margin-top:10px">${escapeHtml(doc.disclaimer || 'Context only. Not a trade signal. Not in base IRR.')}</p>
    </details>`;
  }
  function renderWorldModelStrip(worldModel, escapeHtml, hkSnowball) {
    const strip = worldModel && worldModel.strip;
    if (!strip) {
      return `<div class="detail-section world-model-strip">
        <h3>World Model</h3>
        <p class="tier-sub">No snapshot yet. Run: python _system/scripts/build_world_model_snapshot.py</p>
        ${renderHkSnowballPanel(hkSnowball, escapeHtml)}
      </div>`;
    }

    const label = strip.label || 'steady';
    const labelCls = label === 'broken' ? 'badge-bad' : (label === 'attention' ? 'badge-warn' : 'badge-ok');
    const bounds = strip.claim_boundaries || {};
    const claimCeiling = strip.claim_ceiling || bounds.claim_ceiling || 'P3_oriented';
    const ceilingShort = wmClassShort(claimCeiling);
    const counts = strip.counts || {};
    const historySeries = strip.history_series || {};
    const darwin = bounds.darwin || {};
    const demotions = bounds.demotions || [];
    const isHorizonDemotion = (d) => {
      const art = String(d.artifact || '');
      const reason = String(d.reason || '');
      return art.startsWith('expert_horizon:')
        || /Arrival-date quotes are observations/i.test(reason);
    };
    const horizonDemotions = demotions.filter(isHorizonDemotion);
    const nonHorizonDemotions = demotions.filter(d => !isHorizonDemotion(d));
    const goodhartAll = bounds.goodhart_watch || [];
    const goodhartFails = goodhartAll.filter(g => String(g.status || '').toLowerCase() === 'fail');
    const openCockpit = label === 'attention' || label === 'broken';
    const engines = bounds.engines || [];
    const enginesTooltip = engines.length
      ? engines.map(e => `${e.id || ''}: ${e.role || ''}`).join(' · ')
      : 'World Model / Darwin / house valuation / Lawrence / Santa Fe stay separate languages';
    const claimHygieneSummary = (() => {
      const bits = [`${goodhartFails.length} GH fails`];
      if (horizonDemotions.length) bits.push('horizons P0');
      if (nonHorizonDemotions.length) bits.push(`${nonHorizonDemotions.length} other demotions`);
      return bits.join(' · ');
    })();

    const exceptionBits = [
      counts.fail_hard ? `${counts.fail_hard} hard` : '',
      counts.fail_soft ? `${counts.fail_soft} soft` : '',
      counts.stale ? `${counts.stale} stale` : '',
      counts.unchecked ? `${counts.unchecked} unchecked` : '',
    ].filter(Boolean);
    const exceptionSummary = exceptionBits.length ? exceptionBits.join(' · ') : 'no exceptions';
    const stance = wmTrimStance(strip.ev_stance || '', 90);

    const attentionRows = [
      ...(strip.broken || []).map(r => ({ ...r, _kind: 'hard' })),
      ...(strip.soft_fails || []).map(r => ({ ...r, _kind: 'soft' })),
      ...(strip.stale || []).map(r => ({ ...r, _kind: 'stale' })),
      ...(strip.unchecked || []).map(r => ({ ...r, _kind: 'unchecked' })),
    ].slice(0, 12);

    const attentionTable = attentionRows.length ? `
      <div class="wm-attention">
        <h4 class="wm-section-title">Needs attention</h4>
        <table class="darwin-table wm-table">
          <thead><tr><th>Ticker</th><th>KPI</th><th>Actual</th><th>Hist</th><th>vs hist</th><th>Why</th></tr></thead>
          <tbody>${attentionRows.map(r => {
            const cells = wmKpiHistCells(r, escapeHtml);
            const kindCls = r._kind === 'hard' ? 'badge-bad' : 'badge-warn';
            const scaffoldBadge = r.scaffold ? ' <span class="badge badge-us" title="Industry scaffold — not curated filing KPIs">scaffold</span>' : '';
            return `<tr>
              <td class="mono">${escapeHtml(r.ticker || '')}</td>
              <td>${escapeHtml(wmKpiLabel(r, strip))}${scaffoldBadge}${r._kind === 'soft' ? ` <span class="badge badge-warn" title="Soft floor / Goodhart">soft</span>` : ''}</td>
              ${cells.actualCell}
              ${cells.sparkCell}
              ${cells.zCell}
              <td class="tier-sub">${escapeHtml(wmWhyText(r))} <span class="badge ${kindCls}">${escapeHtml(r._kind === 'soft' ? 'soft' : r._kind)}</span></td>
            </tr>${wmHistoryDetailRow(r, historySeries, escapeHtml, 6)}`;
          }).join('')}</tbody>
        </table>
      </div>` : '';

    const cards = strip.prediction_cards || [];
    const themeCards = cards.map(c => {
      const tid = c.theme_id || '';
      const seriesKeys = WM_THEME_SERIES[tid] || [];
      const seriesBits = seriesKeys.map(k => wmSeriesLatest(historySeries, k)).filter(Boolean).slice(0, 3)
        .map(s => `<span class="wm-theme-metric"><span class="wm-theme-metric-label">${escapeHtml(s.label)}</span> <span class="mono">${escapeHtml(wmFormatNumber(s.value))}</span></span>`)
        .join('');
      const phase = c.phase_transition || '—';
      const phaseCls = phase === 'likely' ? 'badge-warn' : (phase === 'gradual' ? 'badge-us' : 'badge-us');
      const rein = [
        c.recursive ? 'recursive' : null,
        c.tam_magnetism ? `TAM ${c.tam_magnetism}` : null,
        c.regulatory || null,
      ].filter(Boolean).join(' · ');
      let metricsBlock = seriesBits
        ? `<div class="wm-theme-metrics">${seriesBits}</div>`
        : '';
      if (!seriesBits && (tid === 'space_network' || seriesKeys.length === 0)) {
        metricsBlock = `<div class="tier-sub wm-theme-metrics">No market series yet — see Expert horizons · starship and Superorgs</div>`;
      }
      return `<div class="wm-theme-card">
        <div class="wm-theme-card-head">
          <span class="wm-theme-name">${escapeHtml(c.label || tid)}</span>
          <span class="badge ${phaseCls}">${escapeHtml(phase)}</span>
        </div>
        ${metricsBlock}
        <div class="tier-sub wm-theme-rein">${escapeHtml(rein)}</div>
      </div>`;
    }).join('');

    const superRows = (strip.superorgs || []).map(s => {
      const lights = wmPillarLights(s.pillars);
      const sum = s.summary || {};
      const score = sum.fail ? `${sum.fail} fail` : (sum.partial ? `${sum.partial} partial` : 'ok');
      return `<tr>
        <td>${escapeHtml(s.label || s.org_id || '')}</td>
        <td class="mono wm-pillar-lights" title="Pillar traffic: filled=pass, half=partial, empty=fail">${escapeHtml(lights)}</td>
        <td class="tier-sub">${escapeHtml(score)}</td>
      </tr>`;
    }).join('');

    const horizonRows = (strip.expert_horizons || []).map(h => {
      const latest = h.latest || {};
      const convCls = h.convergence === 'converging' ? 'badge-ok' : (h.convergence === 'receding' ? 'badge-bad' : 'badge-us');
      return `<tr>
        <td class="mono">${escapeHtml(h.domain || '')}</td>
        <td><span class="badge ${convCls}">${escapeHtml(h.convergence || '')}</span></td>
        <td class="mono">${latest.years_ahead != null ? escapeHtml(wmFormatNumber(latest.years_ahead, 'years')) : '—'}y</td>
        <td class="tier-sub">${escapeHtml(latest.speaker || '')}</td>
      </tr>`;
    }).join('');

    const industryNodes = strip.industry_nodes || [];
    const thesisInd = industryNodes.filter(n => (n.kind || 'thesis') !== 'horizon_industry');
    const horizonInd = industryNodes.filter(n => n.kind === 'horizon_industry');
    const industryRows = industryNodes.map(n => {
      const cl = n.checklist || {};
      const bits = ['capacity', 'pricing', 'regulatory'].map(k => {
        const st = (cl[k] && cl[k].status) || '—';
        return `${k}:${st}`;
      }).join(' · ');
      const kind = n.kind || 'thesis';
      return `<tr>
        <td>${escapeHtml(n.label || n.node_id || '')}</td>
        <td><span class="badge ${kind === 'horizon_industry' ? 'badge-warn' : 'badge-ok'}">${escapeHtml(kind === 'horizon_industry' ? 'horizon' : 'thesis')}</span></td>
        <td class="tier-sub">${escapeHtml(bits)}</td>
      </tr>`;
    }).join('');

    // KPI drill-down: group by industry; default outliers (+ attention already shown)
    const allPasses = strip.passes || [];
    const outlierPasses = allPasses.filter(wmIsOutlier);
    const defaultShow = outlierPasses.length ? outlierPasses : [];
    const groupsAll = new Map();
    allPasses.forEach(r => {
      const key = wmIndustryKey(r);
      if (!groupsAll.has(key)) groupsAll.set(key, []);
      groupsAll.get(key).push(r);
    });
    const groupsDefault = new Map();
    defaultShow.forEach(r => {
      const key = wmIndustryKey(r);
      if (!groupsDefault.has(key)) groupsDefault.set(key, []);
      groupsDefault.get(key).push(r);
    });

    function renderKpiGroups(groups, colSpan) {
      if (!groups.size) return '<p class="tier-sub">No elevated-z rows. Use “Show all passing” for the full ledger.</p>';
      return [...groups.entries()].map(([key, rows]) => {
        const sharedMap = new Map();
        const byTicker = new Map();
        rows.forEach(r => {
          if (wmIsSharedThemeKpi(r)) {
            const sk = wmSharedKey(r);
            if (!sharedMap.has(sk)) sharedMap.set(sk, { exemplar: r, tickers: [] });
            const entry = sharedMap.get(sk);
            const t = r.ticker || '—';
            if (!entry.tickers.includes(t)) entry.tickers.push(t);
            // Prefer denser history exemplar
            const nNew = ((r.history || {}).n) || 0;
            const nOld = ((entry.exemplar.history || {}).n) || 0;
            if (nNew > nOld) entry.exemplar = r;
          } else {
            const t = r.ticker || '—';
            if (!byTicker.has(t)) byTicker.set(t, []);
            byTicker.get(t).push(r);
          }
        });
        const sharedRows = [...sharedMap.values()].map(({ exemplar, tickers }) => {
          const cells = wmKpiHistCells(exemplar, escapeHtml);
          const gate = wmGateText(exemplar);
          const applies = tickers.slice().sort().join(', ');
          return `<tr>
              <td><span class="badge badge-us" title="Same theme series for every listed ticker">shared</span> ${escapeHtml(wmKpiLabel(exemplar, strip))}
                <div class="tier-sub">applies to ${escapeHtml(applies)}</div></td>
              ${cells.actualCell}
              ${cells.sparkCell}
              ${cells.zCell}
              <td class="mono tier-sub" title="Thesis floor pass/fail — not the same as vs-history z">${escapeHtml(gate)}</td>
            </tr>${wmHistoryDetailRow(exemplar, historySeries, escapeHtml, colSpan)}`;
        }).join('');
        const tickerBody = [...byTicker.entries()].map(([ticker, tRows]) => {
          const isScaffold = tRows.some(r => r.scaffold);
          const head = `<tr class="wm-ticker-band"><td colspan="5"><span class="mono">${escapeHtml(ticker)}</span>${isScaffold ? ' <span class="badge badge-us" title="Industry scaffold">scaffold</span>' : ' <span class="badge badge-ok" title="Curated / filing-backed ledger">curated</span>'}</td></tr>`;
          const kpiRows = tRows.map(r => {
            const cells = wmKpiHistCells(r, escapeHtml);
            const gate = wmGateText(r);
            return `<tr>
              <td>${escapeHtml(wmKpiLabel(r, strip))}</td>
              ${cells.actualCell}
              ${cells.sparkCell}
              ${cells.zCell}
              <td class="mono tier-sub" title="Thesis floor pass/fail — not the same as vs-history z">${escapeHtml(gate)}</td>
            </tr>${wmHistoryDetailRow(r, historySeries, escapeHtml, colSpan)}`;
          }).join('');
          return head + kpiRows;
        }).join('');
        const uniqueCount = sharedMap.size + [...byTicker.values()].reduce((n, a) => n + a.length, 0);
        const body = (sharedRows ? `<tr class="wm-ticker-band"><td colspan="5"><span class="tier-sub">Shared theme pulses (shown once)</span></td></tr>${sharedRows}` : '') + tickerBody;
        return `<details class="wm-group">
          <summary>${escapeHtml(wmIndustryTitle(key))} <span class="tier-sub">(${uniqueCount} signals · ${rows.length} raw)</span></summary>
          <table class="darwin-table wm-table">
            <thead><tr><th>KPI</th><th>Actual</th><th>Hist</th><th>vs hist</th><th>Thesis floor</th></tr></thead>
            <tbody>${body || '<tr><td colspan="5" class="tier-sub">No KPIs in this industry.</td></tr>'}</tbody>
          </table>
        </details>`;
      }).join('');
    }

    const demotionRows = nonHorizonDemotions.map(d => `<tr>
      <td>${escapeHtml(String(d.artifact || '').replace(/^expert_horizon:/, 'Horizon · '))}</td>
      <td><span class="badge badge-us">${escapeHtml(wmClassShort(d.predictability_class))}</span></td>
      <td class="tier-sub">${escapeHtml(d.reason || '')}</td>
    </tr>`).join('');
    const goodhartFailRows = goodhartFails.slice(0, 24).map(g => `<tr>
      <td class="mono">${escapeHtml(g.ticker || '')}</td>
      <td>${escapeHtml(wmKpiLabel({ kpi_id: g.kpi_id, label: g.label }))}</td>
      <td><span class="badge badge-bad">fail</span></td>
    </tr>`).join('');

    return `
      <div class="detail-section world-model-strip" data-wm-strip>
        <div class="wm-glance">
          <div class="wm-glance-row">
            <h3>World Model</h3>
            <span class="badge ${labelCls}">${escapeHtml(label)}</span>
            <span class="badge badge-us" title="${escapeHtml(bounds.reason || 'Magis claim ceiling')}">claim ${escapeHtml(ceilingShort)}</span>
            ${strip.as_of ? `<span class="mono tier-sub">${escapeHtml(String(strip.as_of))}</span>` : ''}
            <span class="tier-sub" title="Context only. Does not set capital stance.">ⓘ</span>
          </div>
          <div class="wm-glance-meta">
            <span>${escapeHtml(exceptionSummary)}</span>
            <span class="wm-sep">·</span>
            <span>${escapeHtml(String(counts.pass != null ? counts.pass : allPasses.length))} passing</span>
            ${goodhartAll.length ? `<span class="wm-sep">·</span><span title="Soft vol gates — Gameability high; fails only surface below">${escapeHtml(String(goodhartAll.length))} soft vol (Goodhart)${goodhartFails.length ? `, ${goodhartFails.length} fail` : ''}</span>` : ''}
            <span class="wm-sep">·</span>
            <span>${thesisInd.length} thesis · ${horizonInd.length} horizon industries</span>
          </div>
          ${stance ? `<p class="wm-stance">${escapeHtml(stance)}</p>` : ''}
        </div>

        ${renderHkSnowballPanel(hkSnowball, escapeHtml)}

        ${attentionTable}

        <details class="wm-panel" ${openCockpit ? 'open' : ''}>
          <summary>Themes <span class="tier-sub">(${cards.length})</span></summary>
          <div class="wm-theme-grid">${themeCards || '<p class="tier-sub">No theme cards.</p>'}</div>
        </details>

        <details class="wm-panel">
          <summary>Superorgs <span class="tier-sub">(${(strip.superorgs || []).length})</span></summary>
          ${(strip.superorgs || []).length ? `<table class="darwin-table wm-table">
            <thead><tr><th>Org</th><th>Pillars</th><th>Status</th></tr></thead>
            <tbody>${superRows}</tbody>
          </table>` : '<p class="tier-sub">None.</p>'}
        </details>

        <details class="wm-panel">
          <summary>Expert horizons <span class="tier-sub">(${(strip.expert_horizons || []).length}) · P0 quotes</span></summary>
          ${(strip.expert_horizons || []).length ? `<table class="darwin-table wm-table">
            <thead><tr><th>Domain</th><th>Trend</th><th>Years</th><th>Speaker</th></tr></thead>
            <tbody>${horizonRows}</tbody>
          </table>
          <p class="tier-sub wm-claim-line">P0 quotes only. Not forecasts.</p>` : '<p class="tier-sub">None.</p>'}
        </details>

        <details class="wm-panel">
          <summary>Claim hygiene <span class="tier-sub">(${escapeHtml(claimHygieneSummary)})</span></summary>
          <p class="tier-sub wm-claim-line">Darwin: <strong>${escapeHtml(String(darwin.regime_label || 'n/a'))}</strong>${darwin.stress ? ' (stress)' : ''} · Thesis ${escapeHtml(wmClassShort(bounds.thesis_hygiene_ceiling || 'P3_oriented'))} · Path ${escapeHtml(wmClassShort(bounds.market_path_ceiling || claimCeiling))}</p>
          ${horizonDemotions.length ? `<p class="tier-sub wm-claim-line">Horizons already P0 (see Expert horizons) — demotion rows suppressed</p>` : ''}
          ${demotionRows ? `<table class="darwin-table wm-table">
            <thead><tr><th>Demotion</th><th>Class</th><th>Why</th></tr></thead>
            <tbody>${demotionRows}</tbody>
          </table>` : ''}
          ${goodhartFailRows ? `<h4 class="wm-section-title">Goodhart fails</h4>
            <table class="darwin-table wm-table">
              <thead><tr><th>Ticker</th><th>KPI</th><th>Status</th></tr></thead>
              <tbody>${goodhartFailRows}</tbody>
            </table>` : '<p class="tier-sub">No Goodhart fails.</p>'}
        </details>

        <details class="wm-panel">
          <summary>Industries <span class="tier-sub">(${industryNodes.length})</span></summary>
          ${industryRows ? `<table class="darwin-table wm-table">
            <thead><tr><th>Industry</th><th>Kind</th><th>Checklist</th></tr></thead>
            <tbody>${industryRows}</tbody>
          </table>` : '<p class="tier-sub">None.</p>'}
        </details>

        <details class="wm-panel wm-kpi-drilldown">
          <summary>KPI drill-down <span class="tier-sub">(${outlierPasses.length} outliers · ${allPasses.length} pass)</span></summary>
          <div class="wm-kpi-toolbar">
            <button type="button" class="filter-btn wm-kpi-mode active" data-wm-kpi-mode="outliers">Outliers (|z|≥2)</button>
            <button type="button" class="filter-btn wm-kpi-mode" data-wm-kpi-mode="all">Show all passing</button>
            <span class="tier-sub">Click a KPI for history. Z-scores are descriptive only.</span>
          </div>
          <div class="wm-kpi-panels">
            <div class="wm-kpi-panel" data-wm-kpi-panel="outliers">${renderKpiGroups(groupsDefault, 5)}</div>
            <div class="wm-kpi-panel" data-wm-kpi-panel="all" hidden>${renderKpiGroups(groupsAll, 5)}</div>
          </div>
        </details>
      </div>`;
  }

  function attachWorldModelHistoryHandlers(container) {
    if (!container) return;
    container.querySelectorAll('[data-wm-hist-toggle]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        const id = btn.getAttribute('data-wm-hist-toggle');
        if (!id) return;
        let detail = null;
        container.querySelectorAll('[data-wm-hist-detail]').forEach(row => {
          if (row.getAttribute('data-wm-hist-detail') === id) detail = row;
        });
        if (!detail) return;
        const open = detail.hasAttribute('hidden');
        container.querySelectorAll('[data-wm-hist-detail]').forEach(row => row.setAttribute('hidden', ''));
        if (open) detail.removeAttribute('hidden');
      });
    });
    container.querySelectorAll('[data-wm-kpi-mode]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        const mode = btn.getAttribute('data-wm-kpi-mode');
        const root = btn.closest('[data-wm-strip]') || container;
        root.querySelectorAll('[data-wm-kpi-mode]').forEach(b => b.classList.toggle('active', b === btn));
        root.querySelectorAll('[data-wm-kpi-panel]').forEach(panel => {
          if (panel.getAttribute('data-wm-kpi-panel') === mode) panel.removeAttribute('hidden');
          else panel.setAttribute('hidden', '');
        });
      });
    });
    container.querySelectorAll('[data-hk-zoom]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        const mode = btn.getAttribute('data-hk-zoom');
        const root = btn.closest('[data-hk-chart-root]') || container;
        root.querySelectorAll('[data-hk-zoom]').forEach(b => b.classList.toggle('active', b === btn));
        root.querySelectorAll('[data-hk-zoom-panel]').forEach(panel => {
          if (panel.getAttribute('data-hk-zoom-panel') === mode) panel.removeAttribute('hidden');
          else panel.setAttribute('hidden', '');
        });
      });
    });
  }

  function renderPortfolioMacroStrip(portfolioMacroRegime, escapeHtml, linkHtml, portfolioMacro) {
    const regime = portfolioMacroRegime || null;
    if (regime && (regime.label || (regime.series || []).length)) {
      const label = regime.label || 'calm';
      const labelCls = label === 'stressed' ? 'badge-bad' : (label === 'adapting' ? 'badge-warn' : 'badge-ok');
      const series = (regime.series || []).slice(0, 4);
      const seriesRows = series.map(s => {
        const signed = s.signed_direction || 'neutral';
        const chipCls = signed === 'risk_off' ? 'badge-bad' : (signed === 'risk_on' ? 'badge-ok' : 'badge-us');
        const chip = signed === 'risk_off' ? 'risk-off' : (signed === 'risk_on' ? 'risk-on' : 'neutral');
        return `
          <tr>
            <td style="font-size:12px">${escapeHtml(s.label || s.id || 'Series')}</td>
            <td class="mono">${escapeHtml(s.value != null ? String(s.value) : '—')}</td>
            <td class="mono tier-sub">${escapeHtml(s.delta_label || '')}</td>
            <td><span class="badge ${chipCls}">${escapeHtml(chip)}</span></td>
            <td class="tier-sub">${escapeHtml(s.why || '')}</td>
          </tr>`;
      }).join('');
      return `
        <div class="detail-section portfolio-macro-regime" style="margin-bottom:14px">
          <div style="display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin-bottom:8px">
            <h3 style="font-size:14px;margin:0">Portfolio macro</h3>
            <span class="badge ${labelCls}" style="font-size:13px;padding:4px 10px">${escapeHtml(label)}</span>
            ${regime.as_of ? `<span class="mono tier-sub">${escapeHtml(String(regime.as_of))}</span>` : ''}
          </div>
          <p style="margin:0 0 10px;font-size:13px;max-width:720px">${escapeHtml(regime.summary || '')}</p>
          ${seriesRows ? `
          <table class="darwin-table" style="max-width:820px">
            <thead><tr><th>Series</th><th>Level</th><th>Change</th><th>Signal</th><th>Why</th></tr></thead>
            <tbody>${seriesRows}</tbody>
          </table>` : ''}
          <p class="tier-sub" style="margin-top:8px">Portfolio-wide context shown once — not repeated on every ticker.</p>
        </div>`;
    }
    // Fallback: legacy card list
    const rows = portfolioMacro || [];
    if (!rows.length) return '';
    return `
      <div class="detail-section" style="margin-bottom:14px">
        <h3 style="font-size:14px;margin-bottom:8px">Portfolio macro</h3>
        <div class="research-box essential-box">
          ${rows.slice(0, 4).map(item => renderInsightItem(item, escapeHtml, linkHtml)).join('')}
        </div>
      </div>`;
  }

  function insiderMaterialityCell(e, escapeHtml) {
    const score = e && e.insider_materiality;
    if (score == null) return '<td class="mono tier-sub">—</td>';
    const tier = e.insider_tier || 'context';
    const pct = Math.max(2, Math.min(100, Number(score) || 0));
    const tierCls = tier === 'signal' ? 'badge-ok' : (tier === 'noise' ? 'badge-warn' : 'badge-us');
    const ics = e.insider_ics != null ? ` · ICS ${e.insider_ics}` : '';
    return `
      <td title="${escapeHtml(`Insider materiality ${score}/100 · tier: ${tier}${ics}`)}">
        <span class="mono">${score}</span>
        <span class="badge ${tierCls}" style="margin-left:4px">${escapeHtml(tier)}</span>
        <div style="height:3px;margin-top:3px;border-radius:2px;background:rgba(148,163,184,.18);max-width:72px">
          <div style="height:100%;width:${pct}%;border-radius:2px;background:${tier === 'signal' ? '#34d399' : tier === 'noise' ? '#64748b' : '#818cf8'}"></div>
        </div>
      </td>`;
  }

  function renderTickerSourceFilters(activeFilter, escapeHtml) {
    const filters = [
      { id: 'ownership', label: 'Letters + insider' },
      { id: 'letters', label: 'Letters' },
      { id: 'podcast_episode', label: 'Podcasts' },
      { id: 'all', label: 'All sources' },
      { id: 'macro', label: 'Macro only' },
    ];
    return `
      <nav class="source-pills" id="insights-ticker-source-tabs" style="margin-bottom:10px">
        ${filters.map(f => `<button type="button" class="filter-btn source-pill${activeFilter === f.id ? ' active' : ''}" data-ticker-source-filter="${escapeHtml(f.id)}">${escapeHtml(f.label)}</button>`).join('')}
      </nav>`;
  }

  function renderSparkline(points, direction) {
    const values = (points || []).map(p => Number(p.value)).filter(v => Number.isFinite(v));
    if (values.length < 2) return '';
    const width = 90;
    const height = 22;
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min || 1;
    const step = width / (values.length - 1);
    const coords = values
      .map((v, i) => `${(i * step).toFixed(1)},${(height - 3 - ((v - min) / span) * (height - 6)).toFixed(1)}`)
      .join(' ');
    const color = direction === 'accelerating' ? '#34d399' : direction === 'decelerating' ? '#f87171' : '#818cf8';
    return `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" style="display:block">
      <polyline fill="none" stroke="${color}" stroke-width="1.5" points="${coords}" />
    </svg>`;
  }

  function trendBadge(direction, signalTier) {
    const tierHint = signalTier === 'confirmed' ? ' (confirmed)' : signalTier === 'emerging' ? ' (emerging)' : '';
    if (direction === 'accelerating' || direction === 'upshift') return `<span class="badge badge-ok" title="Growth accelerating${tierHint}">▲▲</span>`;
    if (direction === 'decelerating' || direction === 'downshift') return `<span class="badge badge-bad" title="Growth decelerating${tierHint}">▼▼</span>`;
    return '<span class="badge badge-us">steady</span>';
  }

  function leadershipRiskBadge(risk, escapeHtml) {
    if (!risk || !risk.level || risk.level === 'none') return '';
    const cls = risk.level === 'elevated' ? 'badge-bad' : 'badge-us';
    return `<span class="badge ${cls}" title="${escapeHtml(risk.label || risk.level)}">gov ${risk.level}</span>`;
  }

  function signalTierBadge(signalTier, escapeHtml) {
    if (signalTier === 'confirmed') {
      return '<span class="badge badge-ok" title="Two quarters in a row beyond this company\'s normal noise band">confirmed</span>';
    }
    if (signalTier === 'emerging') {
      return '<span class="badge badge-us" title="Latest quarter only — not yet confirmed by a second quarter">emerging</span>';
    }
    return '<span class="tier-sub">—</span>';
  }

  function strengthMultiplier(metric) {
    return metric.strength != null
      ? metric.strength
      : Math.abs(metric.accel || 0) / Math.max(metric.threshold || 1e-9, 1e-9);
  }

  function strengthLabel(metric) {
    const s = strengthMultiplier(metric);
    const raw = `${s.toFixed(1)}× vs noise threshold`;
    if (s >= 2) return `<span title="${raw}">strong</span>`;
    if (s >= 1) return `<span title="${raw}">moderate</span>`;
    return `<span title="${raw}">weak</span>`;
  }

  function inflectionWhatChanged(metric, escapeHtml) {
    const summary = (metric.human_summary || '').trim();
    if (summary) return escapeHtml(summary);
    const label = metric.label || metric.metric || 'Metric';
    const growth = formatGrowth(metric);
    return escapeHtml(`${label}: ${growth}`);
  }

  function dataTierBadge(trends, escapeHtml) {
    const tier = trends && trends.data_tier;
    if (!tier) return '';
    const meta = {
      sec_fundamentals: { label: 'SEC', title: 'Quarterly SEC XBRL fundamentals available', cls: 'badge-ok' },
      equity_model: { label: 'Model', title: 'Equity model / dossier KPI series', cls: 'badge-us' },
      sec_pending: { label: 'SEC pending', title: 'US CIK resolved but fundamentals not cached yet', cls: 'badge-warn' },
      news_governance: { label: 'News only', title: 'News/governance signals only — no financial trend series', cls: 'badge-warn' },
      none: { label: 'No trend data', title: 'No SEC, model, or dossier KPI series for this holding', cls: 'badge-warn' },
    }[tier] || { label: tier, title: tier, cls: 'badge-us' };
    return `<span class="badge ${meta.cls}" title="${escapeHtml(meta.title)}" style="margin-right:4px">${escapeHtml(meta.label)}</span>`;
  }

  function renderTickerTrendBadges(trends, escapeHtml) {
    const entry = trends || {};
    const parts = [];
    const tierBadge = dataTierBadge(entry, escapeHtml);
    if (tierBadge && !entry.has_trend_data) parts.push(tierBadge);
    const gov = leadershipRiskBadge(entry.leadership_risk, escapeHtml);
    if (gov) parts.push(gov);
    const bms = entry.business_momentum;
    if (bms && bms.direction && bms.direction !== 'steady') {
      parts.push(`<span title="${escapeHtml(bms.label || bms.direction)}" style="margin-right:4px">${trendBadge(bms.direction, 'confirmed')}</span>`);
    }
    const metrics = entry.metrics || [];
    const firing = metrics.filter(m => m.display && (m.direction === 'accelerating' || m.direction === 'decelerating' || m.direction === 'downshift' || m.direction === 'upshift'));
    if (!firing.length) {
      const fallback = metrics.filter(m => m.direction === 'accelerating' || m.direction === 'decelerating' || m.direction === 'downshift');
      if (!fallback.length) return parts.join('') || tierBadge;
      return parts.join('') + fallback.slice(0, 2).map(m =>
        `<span title="${escapeHtml(`${m.label || m.metric}: ${m.direction}`)}" style="margin-right:4px">${trendBadge(m.direction, m.signal_tier)}</span>`
      ).join('');
    }
    return parts.join('') + firing.slice(0, 2).map(m =>
      `<span title="${escapeHtml(`${m.label || m.metric}: ${m.direction}`)}" style="margin-right:4px">${trendBadge(m.direction, m.signal_tier)}</span>`
    ).join('');
  }

  function formatGrowth(metric) {
    const latest = metric.growth_latest;
    const prior = metric.growth_prior;
    if (latest == null || prior == null) return '—';
    if (metric.mode === 'diff') {
      return `${prior >= 0 ? '+' : ''}${prior} → ${latest >= 0 ? '+' : ''}${latest}`;
    }
    const pct = v => `${(v * 100).toFixed(1)}%`;
    const suffix = metric.basis === 'yoy' ? ' YoY' : '';
    return `${pct(prior)} → ${pct(latest)}${suffix}`;
  }

  const TREND_SOURCE_LABELS = {
    sec_fundamentals: { label: 'SEC XBRL', title: 'Quarterly fundamentals from SEC companyfacts (real fiscal periods, YoY basis)' },
    equity_model: { label: 'Equity model', title: 'Model observation series from equity_models.json' },
    news_flow: { label: 'News flow', title: 'Monthly news item counts (accumulated history)' },
    peer_relative: { label: 'Peer rel.', title: 'YoY growth vs investment-sleeve peers' },
    earnings_revision: { label: 'EPS rev.', title: 'Consensus EPS surprise / revision streak' },
    respiratory_panel: { label: 'Resp. demand', title: 'US respiratory testing volume (CDC FluView + NAAT panel) — exogenous demand context, not a revenue estimate' },
  };

  function trendSourceBadge(source, escapeHtml) {
    const meta = TREND_SOURCE_LABELS[source] || { label: source || '?', title: source || '' };
    return `<span class="badge badge-us" title="${escapeHtml(meta.title)}">${escapeHtml(meta.label)}</span>`;
  }

  function renderInflectionCoverage(kpiTrends) {
    const cov = (kpiTrends && kpiTrends.coverage) || null;
    if (!cov) return '';
    const parts = [
      cov.resolvable_ciks != null
        ? `${cov.fundamentals_tickers || 0}/${cov.resolvable_ciks} SEC CIK fundamentals`
        : `${cov.fundamentals_tickers || 0}/${cov.universe || '?'} tickers with SEC quarterly fundamentals`,
      `${cov.analyzed_tickers || cov.universe || 0} in universe`,
    ];
    if (cov.displayed_count != null) parts.push(`${cov.displayed_count} displayed signals`);
    if (cov.confirmed_count != null) parts.push(`${cov.confirmed_count} confirmed`);
    if (cov.regime_downshift_count != null) parts.push(`${cov.regime_downshift_count} regime downshifts`);
    if (cov.stale_suppressed_count) parts.push(`${cov.stale_suppressed_count} stale series suppressed`);
    if (cov.leadership_risk_watch) parts.push(`${cov.leadership_risk_watch} leadership/gov watch`);
    if (cov.missing_fundamentals && cov.missing_fundamentals.length) {
      parts.push(`${cov.missing_fundamentals.length} resolvable CIK(s) missing fundamentals cache`);
    }
    if (cov.no_trend_data && cov.no_trend_data.length) {
      parts.push(`${cov.no_trend_data.length} without financial trend data`);
    }
    if (cov.peer_relative_count != null && cov.peer_relative_count) parts.push(`${cov.peer_relative_count} peer-relative`);
    if (cov.earnings_revision_count != null && cov.earnings_revision_count) parts.push(`${cov.earnings_revision_count} EPS revision`);
    if (cov.suspect_points_excluded) parts.push(`${cov.suspect_points_excluded} suspect datapoints excluded`);
    return `<p class="tier-sub" style="margin-bottom:4px">Coverage: ${parts.join(' · ')}. Operating flow metrics prioritized; balance-sheet drift hidden by default.</p>`;
  }

  function renderInflectionRollup(kpiTrends, escapeHtml) {
    const byTicker = (kpiTrends && kpiTrends.by_ticker) || {};
    const rows = Object.entries(byTicker)
      .map(([ticker, entry]) => {
        const bms = entry.business_momentum;
        const displayed = (entry.metrics || []).filter(m => m.display);
        if (!bms && !displayed.length) return null;
        const direction = (bms && bms.direction) || (displayed[0] && displayed[0].direction) || 'steady';
        if (direction !== 'accelerating' && direction !== 'decelerating') return null;
        const labels = displayed.map(m => m.label || m.metric).slice(0, 3);
        const score = bms && bms.score != null ? bms.score : null;
        return { ticker, direction, label: bms && bms.label, labels, score, strength: displayed[0] && displayed[0].strength };
      })
      .filter(Boolean)
      .sort((a, b) => Math.abs(b.score || b.strength || 0) - Math.abs(a.score || a.strength || 0))
      .slice(0, 24);
    if (!rows.length) return '';
    return `
      <div style="margin-bottom:12px">
        <h3 style="margin:0 0 6px;font-size:13px">Ticker momentum rollup</h3>
        <div style="display:flex;flex-wrap:wrap;gap:6px">
          ${rows.map(r => `
            <button type="button" class="badge ${r.direction === 'accelerating' ? 'badge-ok' : 'badge-bad'} linkish" data-select-ticker="${escapeHtml(r.ticker)}" title="${escapeHtml(r.label || r.labels.join(', '))}">
              ${escapeHtml(r.ticker)} ${r.direction === 'accelerating' ? '▲' : '▼'}${r.score != null ? ` ${r.score.toFixed(2)}` : ''}
            </button>`).join('')}
        </div>
      </div>`;
  }

  function inflectionTierTabs(activeTier, escapeHtml) {
    const tiers = [
      { id: 'displayed', label: 'Displayed' },
      { id: 'regime', label: 'Growth regime' },
      { id: 'peer', label: 'Peer / EPS' },
      { id: 'confirmed', label: 'Confirmed' },
      { id: 'emerging', label: 'Emerging' },
      { id: 'all', label: 'All signals' },
      { id: 'balance_sheet', label: 'Balance sheet' },
    ];
    return `<div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px">
      ${tiers.map(t => `<button type="button" class="view-tab${activeTier === t.id ? ' active' : ''}" data-inflection-tier="${t.id}">${escapeHtml(t.label)}</button>`).join('')}
    </div>`;
  }

  function matchesInflectionTier(row, tier) {
    const active = row.direction === 'accelerating' || row.direction === 'decelerating'
      || row.direction === 'downshift' || row.direction === 'upshift';
    if (!active) return false;
    if (tier === 'all') return true;
    // Extreme / sign-flip prints stay under All signals only.
    if (row.artifact) return false;
    if (tier === 'balance_sheet') {
      return (row.tier === 'excluded' || ['cash', 'total_assets', 'stockholders_equity', 'long_term_debt'].includes(String(row.metric || '').split('.').pop()))
        && (row.direction === 'accelerating' || row.direction === 'decelerating');
    }
    if (tier === 'regime') {
      return row.signal_type === 'regime' && !!row.display
        && (row.direction === 'downshift' || row.direction === 'upshift');
    }
    if (tier === 'peer') return row.signal_type === 'peer_relative' || row.signal_type === 'estimate_revision';
    if (tier === 'confirmed') return row.signal_tier === 'confirmed';
    if (tier === 'emerging') return row.signal_tier === 'emerging';
    return !!row.display;
  }

  function inflectionHelpCopy(tier) {
    if (tier === 'regime') {
      return `
        <p class="tier-sub" style="margin-bottom:6px">
          Compares this quarter’s year-over-year growth to <strong>this company’s own history</strong>, not to peers.
          Strengthening means above its normal band; softening means below.
          Extreme percentages usually mean the business flipped between profit and loss — those stay under All signals.
        </p>`;
    }
    return `
      <p class="tier-sub" style="margin-bottom:6px">
        Highlights meaningful changes in growth — not the growth rate alone.
        <span title="YoY quarterly growth, 3-period smoothing, materiality floors, two-quarter persistence, and trailing-twelve-month cross-check">How this works</span>
      </p>`;
  }

  function renderInflections(kpiTrends, escapeHtml, opts) {
    const byTicker = (kpiTrends && kpiTrends.by_ticker) || {};
    const search = ((opts && opts.search) || '').trim().toLowerCase();
    const tier = (opts && opts.inflectionTier) || 'displayed';
    const rows = [];
    Object.entries(byTicker).forEach(([ticker, entry]) => {
      (entry.metrics || []).forEach(m => {
        if (!['accelerating', 'decelerating', 'downshift', 'upshift'].includes(m.direction)) return;
        rows.push({ ticker, ...m });
      });
    });
    let filtered = rows.filter(r => matchesInflectionTier(r, tier));
    if (search) {
      filtered = filtered.filter(r => `${r.ticker} ${r.metric} ${r.label} ${r.source} ${r.human_summary || ''}`.toLowerCase().includes(search));
    }
    filtered.sort((a, b) => {
      const sa = a.strength != null ? a.strength : Math.abs(a.accel || 0) / Math.max(a.threshold || 1e-9, 1e-9);
      const sb = b.strength != null ? b.strength : Math.abs(b.accel || 0) / Math.max(b.threshold || 1e-9, 1e-9);
      return sb - sa;
    });
    if (!filtered.length) {
      if (!kpiTrends) {
        return `<p class="subhead">KPI trend data not built yet — run: python _system/scripts/build_fundamental_series.py then build_kpi_trends.py.</p>`;
      }
      return `${renderInflectionCoverage(kpiTrends)}${inflectionTierTabs(tier, escapeHtml)}${inflectionHelpCopy(tier)}<p class="subhead">No inflections match this filter — try All signals or Emerging.</p>`;
    }
    const accel = filtered.filter(r => r.direction === 'accelerating' || r.direction === 'upshift').length;
    const decel = filtered.filter(r => r.direction === 'decelerating' || r.direction === 'downshift').length;
    const cov = (kpiTrends && kpiTrends.coverage) || {};
    const accelLabel = tier === 'regime' ? 'strengthening' : 'accelerating';
    const decelLabel = tier === 'regime' ? 'softening' : 'decelerating';
    return `
      ${renderInflectionCoverage(kpiTrends)}
      ${inflectionTierTabs(tier, escapeHtml)}
      ${tier === 'displayed' || tier === 'confirmed' ? renderInflectionRollup(kpiTrends, escapeHtml) : ''}
      ${inflectionHelpCopy(tier)}
      <p class="tier-sub" style="margin-bottom:8px">
        ${accel} ${accelLabel} · ${decel} ${decelLabel}${tier === 'displayed' || tier === 'confirmed' ? ` · ${cov.displayed_count || 0} displayed total` : ''}
      </p>
      <table class="darwin-table" id="insights-inflections-table">
        <thead><tr><th>Ticker</th><th>Metric</th><th>Trend</th><th>Tier</th><th>What changed</th><th>Growth</th><th>Strength</th><th>Last periods</th><th>Source</th></tr></thead>
        <tbody>
          ${filtered.slice(0, 120).map(r => {
            const accelTip = r.accel != null
              ? (r.mode === 'diff' ? `Second derivative: ${r.accel}` : `Second derivative: ${(r.accel * 100).toFixed(1)} pp`)
              : '';
            return `
            <tr>
              <td><button type="button" class="linkish mono" data-select-ticker="${escapeHtml(r.ticker)}">${escapeHtml(r.ticker)}</button></td>
              <td>${escapeHtml(r.label || r.metric)}${r.composite && r.composite_members ? `<div class="tier-sub">${escapeHtml(r.composite_members.join(', '))}</div>` : ''}${r.stale ? '<div class="tier-sub">stale series</div>' : ''}${r.revenue_proxy ? '<div class="tier-sub">revenue proxy</div>' : ''}${r.signal_type === 'regime' ? '<div class="tier-sub">growth regime</div>' : ''}${r.artifact ? '<div class="tier-sub">volatile base</div>' : ''}</td>
              <td title="${escapeHtml(accelTip)}">${trendBadge(r.direction, r.signal_tier)}</td>
              <td>${signalTierBadge(r.signal_tier, escapeHtml)}</td>
              <td style="max-width:340px">${inflectionWhatChanged(r, escapeHtml)}</td>
              <td class="mono" title="${escapeHtml(accelTip)}">${escapeHtml(formatGrowth(r))}${r.ttm_agrees === true ? ' ✓TTM' : r.ttm_agrees === false ? ' ✗TTM' : ''}</td>
              <td>${strengthLabel(r)}</td>
              <td>${renderSparkline(r.points, r.direction)}</td>
              <td>${trendSourceBadge(r.source, escapeHtml)}</td>
            </tr>`;
          }).join('')}
        </tbody>
      </table>`;
  }

  function formatFreshnessDisplay(days) {
    if (days == null || !Number.isFinite(Number(days))) {
      return { label: '—', cls: 'tier-sub', stale: false };
    }
    const d = Number(days);
    if (d <= 7) return { label: `${d}d`, cls: 'fresh-ok', stale: false };
    if (d <= 30) return { label: `${d}d`, cls: 'fresh-recent', stale: false };
    if (d <= 365) {
      const mo = Math.max(1, Math.round(d / 30));
      return { label: `${mo}mo`, cls: 'fresh-muted', stale: false };
    }
    const yr = (d / 365).toFixed(1).replace(/\.0$/, '');
    return { label: `${yr}y`, cls: 'fresh-stale', stale: true };
  }

  function tickerAttentionScore(t) {
    const e = t.essential_insights || {};
    const status = e.status || {};
    let score = 0;
    if (e.needs_work) score += 1000;
    if (status.tone === 'risk') score += 500;
    if (status.tone === 'bullish') score += 400;
    if (status.tone === 'ownership') score += 200;
    if (e.freshness_days != null && e.freshness_days <= 30) score += 100;
    if (status.tone === 'stale') score += 80;
    if (e.freshness_days != null && e.freshness_days > 365) score += 60;
    return score;
  }

  function sortTickerEssentialsRows(rows, sortMode) {
    const list = [...(rows || [])];
    if (sortMode === 'alpha') {
      return list.sort((a, b) => String(a.ticker).localeCompare(String(b.ticker)));
    }
    if (sortMode === 'fresh') {
      return list.sort((a, b) => {
        const ad = a.essential_insights?.freshness_days;
        const bd = b.essential_insights?.freshness_days;
        if (ad == null && bd == null) return String(a.ticker).localeCompare(String(b.ticker));
        if (ad == null) return 1;
        if (bd == null) return -1;
        return ad - bd;
      });
    }
    if (sortMode === 'stale') {
      return list.sort((a, b) => {
        const ad = a.essential_insights?.freshness_days ?? -1;
        const bd = b.essential_insights?.freshness_days ?? -1;
        return bd - ad;
      });
    }
    return list.sort((a, b) => {
      const scoreDelta = tickerAttentionScore(b) - tickerAttentionScore(a);
      if (scoreDelta) return scoreDelta;
      const ad = a.essential_insights?.freshness_days;
      const bd = b.essential_insights?.freshness_days;
      if (ad != null && bd != null && ad !== bd) return ad - bd;
      return String(a.ticker).localeCompare(String(b.ticker));
    });
  }

  function pickPrimaryInsight(e) {
    if (!e) return null;
    if (e.macro_only) return { macroOnly: true };
    const status = e.status || {};
    const fresh = e.freshness_days != null && e.freshness_days <= 30;
    if (fresh && status.tone === 'risk' && e.bear) return e.bear;
    if (fresh && status.tone === 'bullish' && e.bull) return e.bull;
    if (e.owner) return e.owner;
    if (e.latest) {
      const ownerId = e.owner && e.owner.id;
      if (!ownerId || e.latest.id !== ownerId) return e.latest;
    }
    return e.bull || e.bear || null;
  }

  function renderInsightCompact(item, escapeHtml, linkHtml, opts) {
    const emptyLabel = (opts && opts.emptyLabel) || '—';
    if (!item) return `<span class="tier-sub">${emptyLabel}</span>`;
    if (item.macroOnly) {
      return '<span class="tier-sub" title="Portfolio-wide macro — see strip above">Macro context ↑</span>';
    }
    const directionClass = item.direction === 'bullish'
      ? 'badge-ok'
      : (item.direction === 'bearish' ? 'badge-bad' : 'badge-us');
    const link = item.evidence_url
      ? ` ${linkHtml(item.evidence_url, evidenceLabel(item.evidence_url, item.evidence_label), 'source-open-link')}`
      : '';
    const conf = item.confidence && item.confidence !== 'med'
      ? `<span class="badge badge-us">${escapeHtml(item.confidence)}</span>`
      : '';
    const mat = item.materiality != null
      ? `<span class="badge ${item.tier === 'signal' ? 'badge-ok' : (item.tier === 'noise' ? 'badge-warn' : 'badge-us')}" title="Materiality">${escapeHtml(String(item.materiality))}${item.tier ? ' ' + escapeHtml(item.tier) : ''}</span>`
      : '';
    const title = escapeHtml(item.title || 'Insight');
    return `
      <div class="insight-compact">
        <div class="insight-compact-meta">
          <span class="badge ${directionClass}">${escapeHtml(item.direction || 'neutral')}</span>
          <span class="badge badge-us">${escapeHtml(item.source_label || item.source || 'source')}</span>
          ${mat}
          ${conf}
          ${item.date ? `<span class="mono tier-sub">${escapeHtml(item.date)}</span>` : ''}
        </div>
        <div class="insight-compact-title" title="${title}">${title}${link}</div>
      </div>`;
  }

  function renderTickerSourceMix(e, escapeHtml) {
    const mix = (e.source_mix || []).map(s => SOURCE_LABEL[s] || s);
    if (!mix.length) return '';
    return `<span class="ticker-source-mix">${mix.slice(0, 3).map(s => escapeHtml(s)).join(' · ')}</span>`;
  }

  function filterTickerEssentialsForView(rows, viewMode, gapsMode) {
    if (viewMode === 'trends') {
      return rows.filter(t => {
        const kt = t.kpi_trends || {};
        if (kt.has_trend_data) return true;
        return (kt.metrics || []).some(m => m.direction === 'accelerating' || m.direction === 'decelerating' || m.direction === 'downshift');
      });
    }
    if (viewMode === 'gaps') {
      return rows.filter(t => {
        const e = t.essential_insights || {};
        if (gapsMode === 'coverage') {
          return (e.coverage_gaps || []).length > 0;
        }
        return e.needs_work
          || (e.needs_work_reasons || []).length > 0
          || e.status?.tone === 'stale';
      });
    }
    if (viewMode === 'ownership') {
      return rows.filter(t => {
        const e = t.essential_insights || {};
        return e.owner || (t.letter_discussants || []).length;
      });
    }
    return rows;
  }

  function renderTickerInsightsDrawer(tickerRow, escapeHtml, linkHtml, ghRepo) {
    if (!tickerRow) return '';
    const t = tickerRow;
    const e = t.essential_insights || {};
    const events = (t.insight_events || []).slice(0, 12);
    const discussants = t.letter_discussants || [];
    const eventRows = events.map(r => `
      <tr>
        <td class="mono" style="font-size:11px">${escapeHtml(r.observed_at || r.date || '—')}</td>
        <td><span class="badge badge-us">${escapeHtml(r.source_label || SOURCE_LABEL[r.source] || r.source || '—')}</span></td>
        <td><span class="badge ${r.direction === 'bullish' ? 'badge-ok' : (r.direction === 'bearish' ? 'badge-bad' : 'badge-us')}">${escapeHtml(r.direction || 'neutral')}</span></td>
        <td style="font-size:11px">${escapeHtml((r.title || r.summary || '').slice(0, 120))}</td>
      </tr>`).join('');
    const trendHtml = t.kpi_trends?.has_trend_data
      ? `<div style="margin:8px 0">${renderTickerTrendBadges(t.kpi_trends, escapeHtml)}</div>`
      : '';
    const gapReasons = (e.needs_work_reasons || []).length
      ? `<p class="tier-sub">Gaps: ${e.needs_work_reasons.map(r => escapeHtml(r)).join(', ')}</p>`
      : '';
    const primary = pickPrimaryInsight(e);
    const primaryId = primary && primary.id;
    return `
      <div id="ticker-insights-drawer" class="detail-section ticker-insights-drawer">
        <div style="display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin-bottom:8px">
          <h4 style="margin:0"><span class="mono">${escapeHtml(t.ticker)}</span> · ${escapeHtml((t.company || '').slice(0, 48))}</h4>
          <button type="button" class="filter-btn" id="ticker-insights-drawer-close">Close</button>
          <button type="button" class="linkish" data-select-ticker="${escapeHtml(t.ticker)}">Open holding</button>
          <button type="button" class="linkish" data-insights-goto-consensus data-ticker="${escapeHtml(t.ticker)}">Open in Consensus</button>
        </div>
        <div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:8px">
          <span class="badge ${insightToneClass(e.status?.tone)}">${escapeHtml(e.status?.label || 'No insight')}</span>
          ${formatFreshnessDisplay(e.freshness_days).stale ? '<span class="badge badge-warn">Stale</span>' : ''}
        </div>
        ${gapReasons}
        ${trendHtml}
        ${renderInsightCompact(primary, escapeHtml, linkHtml, { emptyLabel: 'No signal' })}
        ${e.bull && e.bull.id !== primaryId ? `<div style="margin-top:8px"><span class="tier-sub">Bull case</span>${renderInsightCompact(e.bull, escapeHtml, linkHtml)}</div>` : ''}
        ${e.bear && e.bear.id !== primaryId ? `<div style="margin-top:8px"><span class="tier-sub">Bear / risk</span>${renderInsightCompact(e.bear, escapeHtml, linkHtml)}</div>` : ''}
        ${discussants.length ? renderLetterDiscussants(discussants, escapeHtml, linkHtml, ghRepo) : ''}
        ${eventRows ? `
        <h4 style="font-size:12px;color:var(--text-muted);margin:12px 0 6px">Recent events</h4>
        <table class="darwin-table">
          <thead><tr><th>Date</th><th>Source</th><th>Direction</th><th>Title</th></tr></thead>
          <tbody>${eventRows}</tbody>
        </table>` : ''}
      </div>`;
  }

  function renderTickerViewTabs(activeView, escapeHtml) {
    const views = [
      { id: 'scan', label: 'Scan' },
      { id: 'ownership', label: 'Ownership' },
      { id: 'trends', label: 'Trends' },
      { id: 'gaps', label: 'Gaps' },
    ];
    return `
      <nav class="source-pills" id="ticker-view-tabs" style="margin-bottom:8px">
        ${views.map(v => `<button type="button" class="filter-btn source-pill${activeView === v.id ? ' active' : ''}" data-ticker-view="${escapeHtml(v.id)}">${escapeHtml(v.label)}</button>`).join('')}
      </nav>`;
  }

  function renderTickerSortTabs(activeSort, escapeHtml) {
    const sorts = [
      { id: 'attention', label: 'Needs attention' },
      { id: 'fresh', label: 'Fresh' },
      { id: 'stale', label: 'Stale' },
      { id: 'alpha', label: 'A–Z' },
    ];
    return `
      <nav class="source-pills" id="ticker-sort-tabs" style="margin-bottom:10px">
        ${sorts.map(s => `<button type="button" class="filter-btn source-pill${activeSort === s.id ? ' active' : ''}" data-ticker-sort="${escapeHtml(s.id)}">${escapeHtml(s.label)}</button>`).join('')}
      </nav>`;
  }

  function renderTickerScanTable(rows, escapeHtml, linkHtml, opts) {
    const sourceFilter = (opts && opts.sourceFilter) || 'ownership';
    const insiderTier = (opts && opts.insiderTier) || 'signal';
    const showInsiderMat = sourceFilter === 'ownership' || sourceFilter === 'all';
    let list = rows;
    if (showInsiderMat && insiderTier === 'signal') {
      // Prefer signal-tier insider when filtering ownership; keep rows without insider score.
      list = rows.filter(t => {
        const e = t.essential_insights || {};
        if (e.insider_materiality == null) return true;
        return e.insider_tier === 'signal';
      });
    }
    const body = list.map(t => {
      const e = t.essential_insights || {};
      const status = e.status || {};
      const fresh = formatFreshnessDisplay(e.freshness_days);
      const primary = pickPrimaryInsight(e);
      return `
        <tr>
          <td>
            <button type="button" class="linkish mono" data-ticker-insight="${escapeHtml(t.ticker)}">${escapeHtml(t.ticker)}</button>
            <div class="tier-sub">${escapeHtml((t.company || '').slice(0, 36))}</div>
          </td>
          <td><span class="badge ${insightToneClass(status.tone)}">${escapeHtml(status.label || 'No insight')}</span>${e.needs_work ? ' <span class="badge badge-warn" title="Needs work">!</span>' : ''}</td>
          <td class="insight-cell">${renderInsightCompact(primary, escapeHtml, linkHtml, { emptyLabel: 'No signal' })}</td>
          ${showInsiderMat ? insiderMaterialityCell(e, escapeHtml) : ''}
          <td class="mono ${fresh.cls}">${escapeHtml(fresh.label)}${fresh.stale ? ' <span class="badge badge-warn">stale</span>' : ''}<div class="tier-sub">${renderTickerSourceMix(e, escapeHtml)}</div></td>
        </tr>`;
    }).join('');
    return `
      <table class="darwin-table" id="insights-ticker-table">
        <thead><tr><th>Ticker</th><th>Status</th><th>Signal</th>${showInsiderMat ? '<th>Insider</th>' : ''}<th>Fresh</th></tr></thead>
        <tbody>${body}</tbody>
      </table>`;
  }

  function renderTickerOwnershipTable(rows, escapeHtml, linkHtml) {
    const body = rows.map(t => {
      const e = t.essential_insights || {};
      const owner = e.owner;
      const d0 = (t.letter_discussants || [])[0];
      const fresh = formatFreshnessDisplay(e.freshness_days);
      const fund = owner?.source_name || d0?.fund || '—';
      const action = d0?.action || owner?.event_type || '—';
      const quarter = d0?.quarter || '—';
      const commentary = owner?.summary || d0?.commentary || '';
      return `
        <tr>
          <td>
            <button type="button" class="linkish mono" data-ticker-insight="${escapeHtml(t.ticker)}">${escapeHtml(t.ticker)}</button>
            <div class="tier-sub">${escapeHtml((t.company || '').slice(0, 32))}</div>
          </td>
          <td style="font-size:11px">${escapeHtml(fund)}</td>
          <td><span class="badge ${STANCE_BADGE[action] || 'badge-us'}">${escapeHtml(action)}</span></td>
          <td class="mono" style="font-size:11px">${escapeHtml(quarter)}</td>
          <td class="mono ${fresh.cls}">${escapeHtml(fresh.label)}</td>
          <td class="insight-cell">${renderInsightCompact(owner, escapeHtml, linkHtml)}${commentary && !owner ? `<div class="tier-sub">${escapeHtml(commentary.slice(0, 100))}</div>` : ''}</td>
        </tr>`;
    }).join('');
    return `
      <table class="darwin-table" id="insights-ticker-table">
        <thead><tr><th>Ticker</th><th>Fund</th><th>Action</th><th>Quarter</th><th>Fresh</th><th>Letter</th></tr></thead>
        <tbody>${body}</tbody>
      </table>`;
  }

  function renderTickerTrendsTable(rows, escapeHtml) {
    const body = rows.map(t => {
      const e = t.essential_insights || {};
      const fresh = formatFreshnessDisplay(e.freshness_days);
      const kt = t.kpi_trends || {};
      const metrics = (kt.metrics || []).filter(m => m.display !== false).slice(0, 2);
      const metricText = metrics.map(m => `${m.label || m.metric}: ${formatGrowth(m)}`).join(' · ') || '—';
      return `
        <tr>
          <td>
            <button type="button" class="linkish mono" data-ticker-insight="${escapeHtml(t.ticker)}">${escapeHtml(t.ticker)}</button>
          </td>
          <td>${renderTickerTrendBadges(kt, escapeHtml) || '<span class="tier-sub">—</span>'}</td>
          <td style="font-size:11px;max-width:280px">${escapeHtml(metricText)}</td>
          <td class="mono ${fresh.cls}">${escapeHtml(fresh.label)}</td>
          <td><span class="badge ${insightToneClass(e.status?.tone)}">${escapeHtml(e.status?.label || '—')}</span></td>
        </tr>`;
    }).join('');
    return `
      <table class="darwin-table" id="insights-ticker-table">
        <thead><tr><th>Ticker</th><th>Trend</th><th>Metrics</th><th>Fresh</th><th>Status</th></tr></thead>
        <tbody>${body}</tbody>
      </table>`;
  }

  function renderTickerGapsTable(rows, escapeHtml, linkHtml, gapsMode) {
    const mode = gapsMode || 'attention';
    const body = rows.map(t => {
      const e = t.essential_insights || {};
      const fresh = formatFreshnessDisplay(e.freshness_days);
      const reasons = mode === 'coverage'
        ? (e.coverage_gaps || []).slice(0, 4)
        : (e.needs_work_reasons || []).slice(0, 3);
      const primary = pickPrimaryInsight(e);
      return `
        <tr>
          <td>
            <button type="button" class="linkish mono" data-ticker-insight="${escapeHtml(t.ticker)}">${escapeHtml(t.ticker)}</button>
            <div class="tier-sub">${escapeHtml((t.company || '').slice(0, 32))}</div>
          </td>
          <td style="font-size:11px">${reasons.length ? reasons.map(r => `<span class="badge badge-warn">${escapeHtml(r)}</span>`).join(' ') : '<span class="tier-sub">—</span>'}</td>
          <td class="mono ${fresh.cls}">${escapeHtml(fresh.label)}</td>
          <td class="insight-cell">${renderInsightCompact(primary, escapeHtml, linkHtml)}</td>
        </tr>`;
    }).join('');
    return `
      <table class="darwin-table" id="insights-ticker-table">
        <thead><tr><th>Ticker</th><th>${mode === 'coverage' ? 'Coverage' : 'Attention gap'}</th><th>Fresh</th><th>Last signal</th></tr></thead>
        <tbody>${body}</tbody>
      </table>`;
  }

  function renderGapsModeTabs(activeMode, escapeHtml) {
    const modes = [
      { id: 'attention', label: 'Attention' },
      { id: 'coverage', label: 'Coverage audit' },
    ];
    return `
      <nav class="source-pills" id="gaps-mode-tabs" style="margin-bottom:8px">
        ${modes.map(m => `<button type="button" class="filter-btn source-pill${activeMode === m.id ? ' active' : ''}" data-gaps-mode="${escapeHtml(m.id)}">${escapeHtml(m.label)}</button>`).join('')}
      </nav>`;
  }

  function renderInsiderTierTabs(activeTier, escapeHtml) {
    const tiers = [
      { id: 'signal', label: 'Insider signal' },
      { id: 'all', label: 'All insider' },
    ];
    return `
      <nav class="source-pills" id="insider-tier-tabs" style="margin-bottom:8px">
        ${tiers.map(t => `<button type="button" class="filter-btn source-pill${activeTier === t.id ? ' active' : ''}" data-insider-tier="${escapeHtml(t.id)}">${escapeHtml(t.label)}</button>`).join('')}
      </nav>`;
  }

  function attachTickerInsightsHandlers(container, tickers, options) {
    const { onViewMode, onSortMode, onTickerSelect, onCloseDrawer, onGotoConsensus, onGapsMode, onInsiderTier } = options || {};
    if (!container) return;
    container.querySelectorAll('[data-ticker-view]').forEach(btn => {
      btn.addEventListener('click', () => {
        if (onViewMode) onViewMode(btn.dataset.tickerView || 'scan');
      });
    });
    container.querySelectorAll('[data-ticker-sort]').forEach(btn => {
      btn.addEventListener('click', () => {
        if (onSortMode) onSortMode(btn.dataset.tickerSort || 'attention');
      });
    });
    container.querySelectorAll('[data-gaps-mode]').forEach(btn => {
      btn.addEventListener('click', () => {
        if (onGapsMode) onGapsMode(btn.dataset.gapsMode || 'attention');
      });
    });
    container.querySelectorAll('[data-insider-tier]').forEach(btn => {
      btn.addEventListener('click', () => {
        if (onInsiderTier) onInsiderTier(btn.dataset.insiderTier || 'signal');
      });
    });
    container.querySelectorAll('[data-ticker-insight]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const ticker = btn.dataset.tickerInsight;
        if (ticker && onTickerSelect) onTickerSelect(ticker);
      });
    });
    const closeBtn = container.querySelector('#ticker-insights-drawer-close');
    if (closeBtn) closeBtn.addEventListener('click', () => { if (onCloseDrawer) onCloseDrawer(); });
    container.querySelectorAll('[data-insights-goto-consensus]').forEach(btn => {
      btn.addEventListener('click', () => {
        const ticker = btn.dataset.ticker;
        if (ticker && onGotoConsensus) onGotoConsensus(ticker);
      });
    });
  }

  function renderTickerEssentials(tickers, escapeHtml, linkHtml, opts) {
    const sourceFilter = (opts && opts.sourceFilter) || 'ownership';
    const viewMode = (opts && opts.viewMode) || 'scan';
    const sortMode = (opts && opts.sortMode) || 'attention';
    const gapsMode = (opts && opts.gapsMode) || 'attention';
    const insiderTier = (opts && opts.insiderTier) || 'signal';
    const selectedTicker = opts && opts.selectedTicker;
    const ghRepo = (opts && opts.ghRepo) || '';
    let rows = filterTickerEssentials(tickers, opts);
    rows = filterTickerEssentialsForView(rows, viewMode, gapsMode);
    if (viewMode === 'scan' && (sourceFilter === 'ownership' || sourceFilter === 'all')) {
      rows = [...rows].sort((a, b) => {
        const scoreDelta = tickerAttentionScore(b) - tickerAttentionScore(a);
        if (scoreDelta) return scoreDelta;
        const ma = a.essential_insights?.insider_materiality ?? -1;
        const mb = b.essential_insights?.insider_materiality ?? -1;
        if (mb !== ma) return mb - ma;
        return String(a.ticker).localeCompare(String(b.ticker));
      }).slice(0, 160);
    } else {
      rows = sortTickerEssentialsRows(rows, sortMode).slice(0, 160);
    }
    const sourceTabs = renderTickerSourceFilters(sourceFilter, escapeHtml);
    const viewTabs = renderTickerViewTabs(viewMode, escapeHtml);
    const sortTabs = renderTickerSortTabs(sortMode, escapeHtml);
    const gapsTabs = viewMode === 'gaps' ? renderGapsModeTabs(gapsMode, escapeHtml) : '';
    const insiderTabs = (viewMode === 'scan' && (sourceFilter === 'ownership' || sourceFilter === 'all'))
      ? renderInsiderTierTabs(insiderTier, escapeHtml)
      : '';
    const tickerBySymbol = Object.fromEntries((tickers || []).map(t => [t.ticker, t]));
    const drawer = selectedTicker && tickerBySymbol[selectedTicker]
      ? renderTickerInsightsDrawer(tickerBySymbol[selectedTicker], escapeHtml, linkHtml, ghRepo)
      : '';
    if (!rows.length) {
      return `${drawer}${sourceTabs}${viewTabs}${sortTabs}${gapsTabs}${insiderTabs}<p class="subhead">No ticker essentials match this view.</p>`;
    }
    let table = '';
    if (viewMode === 'ownership') table = renderTickerOwnershipTable(rows, escapeHtml, linkHtml);
    else if (viewMode === 'trends') table = renderTickerTrendsTable(rows, escapeHtml);
    else if (viewMode === 'gaps') table = renderTickerGapsTable(rows, escapeHtml, linkHtml, gapsMode);
    else table = renderTickerScanTable(rows, escapeHtml, linkHtml, { sourceFilter, insiderTier });
    const viewHint = {
      scan: 'One signal per holding — click a ticker for full timeline.',
      ownership: 'Letter positioning from superinvestor disclosures.',
      trends: 'KPI inflections and SEC fundamentals where available.',
      gaps: gapsMode === 'coverage'
        ? 'Completeness audit (dossier, third-party, stale source) — not Needs Attention.'
        : 'Holdings-critical attention gaps only.',
    }[viewMode] || '';
    return `
      ${drawer}
      <p class="tier-sub" style="margin-bottom:8px">
        Portfolio scan · for cross-fund positioning see <strong>Consensus</strong> · ${rows.length} row(s)
      </p>
      ${sourceTabs}
      ${viewTabs}
      ${sortTabs}
      ${gapsTabs}
      ${insiderTabs}
      <p class="tier-sub" style="margin-bottom:8px;color:var(--text-muted)">${escapeHtml(viewHint)}</p>
      ${table}`;
  }

  function renderSourceHealth(health, escapeHtml) {
    const rows = Object.entries(health || {});
    if (!rows.length) {
      return '<p class="subhead">No source health data yet.</p>';
    }
    return `
      <table class="darwin-table" id="insights-source-table">
        <thead><tr><th>Source</th><th>Status</th><th>Records</th><th>Items</th><th>As of</th><th>Notes</th></tr></thead>
        <tbody>
          ${rows.map(([key, h]) => {
            const status = h.status || 'unknown';
            const cls = status === 'ok' ? 'badge-ok' : (status === 'missing' || status === 'forbidden' ? 'badge-warn' : 'badge-us');
            const notes = h.notes || (h.warnings ? `${h.warnings} warning(s)` : (h.path || ''));
            return `
              <tr>
                <td>${escapeHtml(key.replace(/_/g, ' '))}</td>
                <td><span class="badge ${cls}">${escapeHtml(status)}</span></td>
                <td class="mono">${h.records ?? 'n/a'}</td>
                <td class="mono">${h.items ?? 'n/a'}</td>
                <td class="mono">${escapeHtml(h.as_of || 'n/a')}</td>
                <td class="tier-sub">${escapeHtml(notes)}</td>
              </tr>`;
          }).join('')}
        </tbody>
      </table>`;
  }

  function renderDataSourceCandidates(candidates, escapeHtml) {
    const tools = candidates?.selected_tools || [];
    if (!tools.length) return '<p class="subhead">No TerminalValue candidate source registry yet.</p>';
    return `
      <div class="detail-section">
        <h3>TerminalValue candidate feeds</h3>
        <p class="tier-sub" style="margin-bottom:8px">
          ${escapeHtml(candidates.source_label || 'TerminalValue.io')} · reviewed ${escapeHtml(candidates.reviewed_at || 'n/a')} · ${tools.length} selected feeds
        </p>
        <table class="darwin-table">
          <thead><tr><th>Provider</th><th>Role</th><th>Status</th><th>Priority</th><th>Credential</th><th>Target</th></tr></thead>
          <tbody>
            ${tools.map(t => `
              <tr>
                <td>${escapeHtml(t.name || 'Provider')}</td>
                <td>${escapeHtml(t.dashboard_role || '')}</td>
                <td><span class="badge ${t.integration_status === 'live' ? 'badge-ok' : 'badge-warn'}">${escapeHtml(t.integration_status || 'candidate')}</span></td>
                <td>${escapeHtml(t.priority || 'medium')}</td>
                <td>${t.credential_required ? 'required' : 'not required'}</td>
                <td class="mono" style="font-size:11px">${escapeHtml(t.target_pipeline || '')}</td>
              </tr>`).join('')}
          </tbody>
        </table>
      </div>`;
  }

  function catalogSourceLabel(row) {
    return row?.source_label || CATALOG_SOURCE_LABEL[row?.source_type] || 'Other PDFs';
  }

  function sortDocumentCatalogRows(rows, opts) {
    const { search = '', knownTickers = [] } = opts || {};
    const q = SearchMatch.normalizeQuery(search);
    return [...(rows || [])].sort((a, b) => {
      if (q) {
        const scoreDelta = SearchMatch.documentCatalogMatchScore(b, q, knownTickers)
          - SearchMatch.documentCatalogMatchScore(a, q, knownTickers);
        if (scoreDelta) return scoreDelta;
      }
      const ad = a.document_date || '';
      const bd = b.document_date || '';
      if (ad && bd && ad !== bd) return bd.localeCompare(ad);
      if (ad && !bd) return -1;
      if (!ad && bd) return 1;
      const sp = (CATALOG_SOURCE_SORT[a.source_type] ?? 99) - (CATALOG_SOURCE_SORT[b.source_type] ?? 99);
      if (sp) return sp;
      const ta = (a.ticker || '').localeCompare(b.ticker || '');
      if (ta) return ta;
      return (a.title || '').localeCompare(b.title || '');
    });
  }

  function filterDocumentCatalog(catalog, opts) {
    const {
      search = '',
      quarter = 'all',
      bookOnly = false,
      period = null,
      pdfSourceTab = 'all',
      pdfTimeMode = 'period',
    } = opts || {};
    const q = SearchMatch.normalizeQuery(search);
    const knownTickers = SearchMatch.catalogKnownTickers(catalog);
    let rows = catalog?.documents || [];
    if (period && !period.all) {
      const fields = pdfTimeMode === 'upload'
        ? ['modified_at']
        : ['document_quarter', 'quarter', 'document_date'];
      rows = rows.filter(r => periodMatchesRecord(r, period, fields));
    } else if (quarter && quarter !== 'all') {
      const label = quarter.replace(/^(\d{4})Q([1-4])$/, '$1 Q$2');
      rows = rows.filter(r => r.document_quarter === quarter || r.quarter === label || r.quarter === quarter);
    }
    if (pdfSourceTab === 'letters') {
      rows = rows.filter(r => r.source_type === 'superinvestor_letter');
    } else if (pdfSourceTab === 'company') {
      rows = rows.filter(r => r.source_type === 'company_document');
    } else if (pdfSourceTab === 'third_party') {
      rows = rows.filter(r => r.source_type === 'third_party' || r.source_type === 'sumzero_research' || r.source_type === 'research');
    } else if (pdfSourceTab === 'unclassified') {
      rows = rows.filter(r => r.period_source === 'unknown' || r.source_type === 'pdf');
    }
    if (bookOnly) {
      rows = rows.filter(r => r.ticker);
    }
    if (q) {
      rows = rows.filter(r => SearchMatch.matchDocumentCatalogRow(r, q, knownTickers));
    }
    return sortDocumentCatalogRows(rows, { search: q, knownTickers });
  }

  function renderDocumentCatalog(catalog, escapeHtml, linkHtml, opts) {
    const {
      pdfSourceTab = 'all',
      pdfTimeMode = 'period',
    } = opts || {};
    const filtered = filterDocumentCatalog(catalog, opts);
    const rows = filtered.slice(0, 300);
    const summary = catalog?.summary || {};
    const labelCounts = {};
    (catalog?.documents || []).forEach(r => {
      const label = catalogSourceLabel(r);
      labelCounts[label] = (labelCounts[label] || 0) + 1;
    });
    const cards = Object.entries(labelCounts)
      .sort((a, b) => b[1] - a[1])
      .map(([source, count]) => `<span class="badge badge-us">${escapeHtml(source)}: ${count}</span>`)
      .join('');
    const quarterCounts = {};
    (catalog?.documents || []).forEach(r => {
      const label = r.period_label && r.period_source !== 'unknown' ? r.period_label : null;
      if (label) quarterCounts[label] = (quarterCounts[label] || 0) + 1;
    });
    const quarterCards = Object.entries(quarterCounts)
      .sort((a, b) => String(b[0]).localeCompare(String(a[0])))
      .slice(0, 12)
      .map(([quarter, count]) => `<span class="badge badge-purple">${escapeHtml(quarter)}: ${count}</span>`)
      .join('');
    const sourceTabs = [
      { id: 'all', label: 'All PDFs' },
      { id: 'letters', label: 'Letters' },
      { id: 'company', label: 'Company docs' },
      { id: 'third_party', label: 'Third-party / VIC' },
      { id: 'unclassified', label: 'Unclassified' },
    ];
    const timeModes = [
      { id: 'period', label: 'Document period' },
      { id: 'upload', label: 'Recently uploaded' },
    ];
    if (!catalog) {
      return '<p class="subhead">PDF catalog not built. Run: python _system/scripts/build_dashboard_data.py</p>';
    }
    return `
      <div class="detail-section">
        <h3>PDF library</h3>
        <p class="tier-sub" style="margin-bottom:8px">
          ${summary.document_count || 0} documents · ${summary.uploaded_count || 0} uploaded · ${summary.pending_upload_count || 0} pending
          · showing ${rows.length} of ${filtered.length} matching
        </p>
        <nav class="source-pills" id="pdf-source-tabs" style="margin-bottom:8px">
          ${sourceTabs.map(t => `<button type="button" class="filter-btn source-pill${pdfSourceTab === t.id ? ' active' : ''}" data-pdf-source-tab="${escapeHtml(t.id)}">${escapeHtml(t.label)}</button>`).join('')}
        </nav>
        <nav class="source-pills" id="pdf-time-mode-tabs" style="margin-bottom:8px">
          ${timeModes.map(t => `<button type="button" class="filter-btn source-pill${pdfTimeMode === t.id ? ' active' : ''}" data-pdf-time-mode="${escapeHtml(t.id)}">${escapeHtml(t.label)}</button>`).join('')}
        </nav>
        <div class="source-card-badges" style="margin-bottom:6px">${cards}</div>
        ${quarterCards ? `<div class="source-card-badges" style="margin-bottom:10px">${quarterCards}</div>` : ''}
        <table class="darwin-table" id="insights-document-catalog">
          <thead><tr><th>Source</th><th>Ticker</th><th>Period</th><th>Title</th><th>Folder</th><th></th></tr></thead>
          <tbody>
            ${rows.map(r => `
              <tr>
                <td><span class="badge badge-us">${escapeHtml(catalogSourceLabel(r))}</span></td>
                <td class="mono">${escapeHtml(r.ticker || '—')}</td>
                <td class="mono">${escapeHtml(r.period_label || r.document_date || 'Unknown date')}</td>
                <td style="min-width:280px">${escapeHtml(r.title || 'Untitled')}</td>
                <td class="tier-sub">${escapeHtml(r.drive_folder_path || '')}</td>
                <td>${r.drive_web_view_link ? linkHtml(r.drive_web_view_link, 'PDF', 'source-open-link') : '—'}</td>
              </tr>`).join('')}
          </tbody>
        </table>
        ${filtered.length > rows.length ? `<p class="tier-sub">${filtered.length - rows.length} more documents outside the current table window.</p>` : ''}
      </div>`;
  }

  function renderMemoryLedger(memory, escapeHtml, linkHtml, opts) {
    const {
      search = '',
      bookOnly = false,
      period = null,
      knownTickers = [],
      biotechOnly = false,
      holdingsTickers = [],
      typeFilter = 'all',
      ghRepo = '',
    } = opts || {};
    const bookSet = new Set((holdingsTickers || []).map(t => String(t).toUpperCase()));
    let rows = memory?.claim_ledger || [];
    if (period && !period.all) {
      rows = rows.filter(r => periodMatchesRecord(r, period, ['quarter', 'date', 'as_of', 'source_date']));
    }
    if (bookOnly && bookSet.size) {
      rows = rows.filter(r => bookSet.has(String(r.ticker || '').toUpperCase()));
    }
    if (biotechOnly) {
      const quantTickers = new Set(
        Object.entries(memory?.by_ticker || {})
          .filter(([, v]) => v?.biotech?.in_biotech_quant_universe)
          .map(([t]) => t.toUpperCase())
      );
      rows = rows.filter(r => quantTickers.has(String(r.ticker || '').toUpperCase()));
    }
    if (typeFilter && typeFilter !== 'all') {
      rows = rows.filter(r => memoryClaimMatchesType(r, typeFilter));
    }
    if (search) {
      rows = rows.filter(r => SearchMatch.matchMemoryClaim(r, search, knownTickers));
    }
    const totalFiltered = rows.length;
    rows = rows.slice(0, 160);
    if (!rows.length) {
      return '<p class="subhead">No research-memory claims match this view. Try All history, clear filters, or switch type.</p>';
    }
    return `
      <table class="darwin-table" id="memory-claim-ledger">
        <thead><tr><th>Ticker</th><th>Type</th><th>Direction</th><th>Claim</th><th>Evidence</th></tr></thead>
        <tbody>${rows.map(r => {
          const cls = r.direction === 'bullish' ? 'badge-ok' : (r.direction === 'bearish' ? 'badge-bad' : 'badge-us');
          const evLabel = r.evidence_label || evidenceLabel(r.evidence_url, r.source_title);
          const evidenceCell = r.evidence_url
            ? evidenceLink(r.evidence_url, linkHtml, ghRepo, evLabel)
            : escapeHtml(r.source_title || r.source_type || 'source');
          return `<tr>
            <td><button type="button" class="linkish mono" data-select-ticker="${escapeHtml(r.ticker)}">${escapeHtml(r.ticker)}</button></td>
            <td><span class="badge badge-us">${escapeHtml(r.claim_type || 'claim')}</span></td>
            <td><span class="badge ${cls}">${escapeHtml(r.direction || 'neutral')}</span></td>
            <td style="min-width:320px">${escapeHtml(r.claim || '')}</td>
            <td style="min-width:140px">${evidenceCell}<div class="tier-sub">${escapeHtml(r.source_title || '')}</div></td>
          </tr>`;
        }).join('')}</tbody>
      </table>
      <p class="tier-sub" style="margin-top:8px">Showing ${rows.length} of ${totalFiltered} matching claim(s)${totalFiltered > rows.length ? ' (table capped at 160)' : ''}.</p>`;
  }

  function renderMemoryReviewQueue(memory, escapeHtml) {
    const rows = (memory?.review_queue || []).slice(0, 160);
    if (!rows.length) return '<p class="subhead">No memory review items.</p>';
    return `
      <div class="detail-section">
        <h3>Review queue</h3>
        <table class="darwin-table">
          <thead><tr><th>Priority</th><th>Ticker</th><th>Reason</th></tr></thead>
          <tbody>${rows.map(r => `<tr>
            <td><span class="badge ${r.priority === 'high' ? 'badge-bad' : 'badge-warn'}">${escapeHtml(r.priority || 'medium')}</span></td>
            <td><button type="button" class="linkish mono" data-select-ticker="${escapeHtml(r.ticker)}">${escapeHtml(r.ticker)}</button></td>
            <td>${escapeHtml(r.reason || '')}${(r.reasons || []).length > 1 ? `<div class="tier-sub">${escapeHtml((r.reasons || []).join(' · '))}</div>` : ''}</td>
          </tr>`).join('')}</tbody>
        </table>
      </div>`;
  }

  function renderBiotechMemory(memory, escapeHtml, linkHtml, ghRepo, opts) {
    const funds = memory?.biotech?.specialist_funds || [];
    const signals = memory?.biotech?.signals?.by_ticker || {};
    const tickers = Object.values(memory?.by_ticker || {}).filter(t => t.biotech?.in_biotech_quant_universe);
    const paperBook = memory?.biotech?.paper_book || null;
    const scope = opts?.biotechScope || 'book';
    const convergenceOnly = !!opts?.biotechConvergenceOnly;
    const spendQ4 = !!opts?.biotechSpendQ4;
    const sizeFilter = opts?.biotechSizeFilter || 'all';
    const issuerSizeFilter = opts?.biotechIssuerSizeFilter || 'all';
    const search = (opts?.biotechSearch || '').trim().toLowerCase();
    const showLimit = opts?.biotechShowLimit || 40;

    let signalRows = Object.values(signals)
      .filter(s => s.in_biotech_quant_universe !== false)
      .sort((a, b) => ((b.composite_score ?? b.consensus_score) || 0) - ((a.composite_score ?? a.consensus_score) || 0));
    if (scope === 'book') {
      signalRows = signalRows.filter(s => s.in_book);
    }
    if (convergenceOnly) {
      signalRows = signalRows.filter(s => s.convergence_flag);
    }
    if (spendQ4) {
      signalRows = signalRows.filter(s => (s.spend_value_quintile || 0) >= 4);
    }
    if (sizeFilter !== 'all') {
      signalRows = signalRows.filter(s => (s.position_size_bucket || s.size_bucket) === sizeFilter);
    }
    if (issuerSizeFilter !== 'all') {
      signalRows = signalRows.filter(s => (s.issuer_size_bucket || 'unknown') === issuerSizeFilter);
    }
    if (search) {
      signalRows = signalRows.filter(s => {
        const hay = `${s.ticker || ''} ${s.company || ''} ${s.issuer || ''}`.toLowerCase();
        return hay.includes(search);
      });
    }
    const shortRows = Object.values(signals)
      .filter(s => (s.short_candidate_score || 0) > 0 || (s.short_interest_quintile || 0) >= 4)
      .sort((a, b) => (b.short_candidate_score || 0) - (a.short_candidate_score || 0))
      .slice(0, 25);
    const catalog = memory?.biotech?.library_catalog || [];
    const scoreboard = memory?.biotech?.factor_scoreboard || [];
    const methodClaims = memory?.biotech?.methodology_claims || memory?.methodology_claims || [];
    const knowledgeDelta = memory?.biotech?.knowledge_delta || null;
    const initiations = signalRows.filter(s => s.initiation_signal).map(s => s.ticker);
    const visible = signalRows.slice(0, showLimit);
    const hasMore = signalRows.length > showLimit;

    const libraryHtml = catalog.length ? `
      <div class="detail-section">
        <h3>Methodology library</h3>
        <p class="tier-sub" style="margin-bottom:8px">Context-tier sources. Not used in base IRR until human approval.</p>
        <table class="darwin-table">
          <thead><tr><th>Title</th><th>Open</th></tr></thead>
          <tbody>${catalog.map(c => `<tr>
            <td>${escapeHtml(c.title || c.id || '')}</td>
            <td>${c.path ? evidenceLink(c.path, linkHtml, ghRepo, c.label || 'Open') : '—'}</td>
          </tr>`).join('')}</tbody>
        </table>
      </div>` : '';
    const scoreboardHtml = scoreboard.length ? `
      <div class="detail-section">
        <h3>Factor scoreboard</h3>
        <table class="darwin-table">
          <thead><tr><th>Factor</th><th>Status</th><th>Long w</th><th>Short w</th><th>In signals</th></tr></thead>
          <tbody>${scoreboard.map(f => `<tr>
            <td>${escapeHtml(f.label || f.id || '')}</td>
            <td><span class="badge ${f.status === 'live' ? 'badge-ok' : 'badge-warn'}">${escapeHtml(f.status || 'planned')}</span></td>
            <td class="mono">${f.weight_long != null ? f.weight_long : '—'}</td>
            <td class="mono">${f.weight_short != null ? f.weight_short : '—'}</td>
            <td>${f.present ? '<span class="badge badge-ok">yes</span>' : '<span class="badge badge-warn">no</span>'}</td>
          </tr>`).join('')}</tbody>
        </table>
      </div>` : '';
    const methodHtml = methodClaims.length ? `
      <div class="detail-section">
        <h3>Methodology claims</h3>
        <ul class="source-stack">${methodClaims.slice(0, 12).map(c => `<li class="source-card">
          <div class="source-card-title">${escapeHtml(c.claim || '')} ${c.evidence_url ? evidenceLink(c.evidence_url, linkHtml, ghRepo, c.evidence_label) : ''}</div>
        </li>`).join('')}</ul>
      </div>` : '';
    const deltaBits = [];
    if (knowledgeDelta) {
      if (knowledgeDelta.new_convergences?.length) deltaBits.push(`New convergence: ${knowledgeDelta.new_convergences.join(', ')}`);
      if (knowledgeDelta.spend_q_up?.length) deltaBits.push(`Spend Q↑: ${knowledgeDelta.spend_q_up.join(', ')}`);
      if (knowledgeDelta.paper_book_added?.length) deltaBits.push(`Paper +${knowledgeDelta.paper_book_added.join(', ')}`);
      if (knowledgeDelta.paper_book_removed?.length) deltaBits.push(`Paper −${knowledgeDelta.paper_book_removed.join(', ')}`);
    }
    const deltaHtml = `
      <div class="detail-section">
        <h3>Knowledge delta</h3>
        <p class="tier-sub">${methodClaims.length} methodology claim(s) · ${initiations.length ? `Initiations: ${escapeHtml(initiations.join(', '))}` : 'No core-fund initiations in filtered view'} · ${tickers.length} book quant name(s)${deltaBits.length ? ` · ${escapeHtml(deltaBits.join(' · '))}` : ''}.</p>
      </div>`;

    const paperLong = (paperBook?.long || []).slice(0, 20);
    const paperShort = (paperBook?.short || []).slice(0, 20);
    const paperHtml = (paperLong.length || paperShort.length) ? `
      <div class="detail-section">
        <h3>Paper book</h3>
        <p class="tier-sub" style="margin-bottom:8px">Not live trading. Composite-ranked long/short sleeve for research only.${paperBook?.as_of ? ` As of ${escapeHtml(paperBook.as_of)}.` : ''}</p>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
          <div>
            <h4 style="margin:0 0 6px">Long (${paperLong.length})</h4>
            <table class="darwin-table"><thead><tr><th>Ticker</th><th>Composite</th><th>Issuer size</th></tr></thead>
            <tbody>${paperLong.map(r => `<tr>
              <td><button type="button" class="linkish mono" data-select-ticker="${escapeHtml(r.ticker)}">${escapeHtml(r.ticker)}</button></td>
              <td class="mono">${r.composite_score ?? '—'}</td>
              <td>${escapeHtml(r.issuer_size_bucket || '—')}</td>
            </tr>`).join('') || '<tr><td colspan="3" class="tier-sub">Empty</td></tr>'}</tbody></table>
          </div>
          <div>
            <h4 style="margin:0 0 6px">Short (${paperShort.length})</h4>
            <table class="darwin-table"><thead><tr><th>Ticker</th><th>SI / score</th><th>Consensus Q</th></tr></thead>
            <tbody>${paperShort.map(r => `<tr>
              <td><button type="button" class="linkish mono" data-select-ticker="${escapeHtml(r.ticker)}">${escapeHtml(r.ticker)}</button></td>
              <td class="mono">${r.short_interest_pct != null ? r.short_interest_pct : (r.short_candidate_score ?? '—')}</td>
              <td class="mono">${r.consensus_quintile ?? '—'}</td>
            </tr>`).join('') || '<tr><td colspan="3" class="tier-sub">Empty</td></tr>'}</tbody></table>
          </div>
        </div>
      </div>` : '';

    const shortHtml = `
      <div class="detail-section">
        <h3>Short watchlist</h3>
        <p class="tier-sub" style="margin-bottom:8px">Diversified short candidates (high SI / weak consensus). Not conviction shorts.</p>
        <table class="darwin-table">
          <thead><tr><th>Ticker</th><th>SI %</th><th>Days to cover</th><th>Short score</th><th>Consensus Q</th></tr></thead>
          <tbody>${shortRows.map(s => `<tr>
            <td><button type="button" class="linkish mono" data-select-ticker="${escapeHtml(s.ticker)}">${escapeHtml(s.ticker)}</button>${s.in_book ? ' <span class="badge badge-warn">book</span>' : ''}</td>
            <td class="mono">${s.short_interest_pct != null ? s.short_interest_pct : '—'}</td>
            <td class="mono">${s.days_to_cover != null ? s.days_to_cover : '—'}</td>
            <td class="mono">${s.short_candidate_score ?? '—'}</td>
            <td class="mono">${s.consensus_quintile ?? '—'}</td>
          </tr>`).join('') || '<tr><td colspan="5" class="tier-sub">No short candidates in current signals.</td></tr>'}</tbody>
        </table>
      </div>`;

    const controlsHtml = `
      <div class="detail-section" style="margin-bottom:10px">
        <div style="display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:8px">
          <nav class="source-pills" id="biotech-scope-tabs">
            <button type="button" class="filter-btn source-pill${scope === 'book' ? ' active' : ''}" data-biotech-scope="book">Book</button>
            <button type="button" class="filter-btn source-pill${scope === 'universe' ? ' active' : ''}" data-biotech-scope="universe">Universe</button>
          </nav>
          <label class="tier-sub" style="display:flex;align-items:center;gap:4px"><input type="checkbox" id="biotech-convergence-only" ${convergenceOnly ? 'checked' : ''}/> Convergence</label>
          <label class="tier-sub" style="display:flex;align-items:center;gap:4px"><input type="checkbox" id="biotech-spend-q4" ${spendQ4 ? 'checked' : ''}/> Spend Q≥4</label>
          <label class="tier-sub">Pos size
            <select id="biotech-size-filter">
              ${['all', 'small', 'mid', 'large'].map(v => `<option value="${v}" ${sizeFilter === v ? 'selected' : ''}>${v}</option>`).join('')}
            </select>
          </label>
          <label class="tier-sub">Issuer size
            <select id="biotech-issuer-size-filter">
              ${['all', 'small', 'mid', 'large', 'unknown'].map(v => `<option value="${v}" ${issuerSizeFilter === v ? 'selected' : ''}>${v}</option>`).join('')}
            </select>
          </label>
          <input type="search" id="biotech-search" placeholder="Search ticker / company" value="${escapeHtml(opts?.biotechSearch || '')}" style="min-width:160px"/>
        </div>
        <p class="tier-sub">${signalRows.length} matching · showing ${visible.length}${scope === 'book' ? ' (book default)' : ' (full universe)'}</p>
      </div>`;

    return `
      <div class="detail-section">
        <p class="tier-sub" style="margin-bottom:4px"><span class="badge badge-purple">Ownership signals</span> Specialist 13F ownership — not a watchlist. Prospecting lists (NOL, advantaged banks) live under Watchlist.</p>
      </div>
      ${libraryHtml}
      ${scoreboardHtml}
      ${methodHtml}
      ${deltaHtml}
      ${paperHtml}
      <div class="detail-section">
        <h3>Biotech specialist registry</h3>
        <p class="tier-sub" style="margin-bottom:8px">${funds.length} specialist funds tracked · ${Object.keys(signals).length} universe signals · ${tickers.length} book quant names · ${memory?.biotech?.ownership_records?.length || 0} book 13F records.</p>
        <table class="darwin-table">
          <thead><tr><th>Fund</th><th>Specialty</th><th>Role</th><th>Notes</th></tr></thead>
          <tbody>${funds.slice(0, 28).map(f => `<tr>
            <td>${escapeHtml(f.fund || '')}</td>
            <td><span class="badge badge-purple">${escapeHtml(f.specialty || 'biotech')}</span></td>
            <td>${escapeHtml(f.signal_role || 'specialist_13f')}</td>
            <td class="tier-sub">${escapeHtml(f.notes || '')}</td>
          </tr>`).join('')}</tbody>
        </table>
      </div>
      <div class="detail-section">
        <h3>Biotech quant signals</h3>
        ${controlsHtml}
        <table class="darwin-table">
          <thead><tr><th>Ticker</th><th>Composite</th><th>Consensus</th><th>Q</th><th>Core</th><th>N</th><th>ΔN</th><th>Spend Q</th><th>Insider</th><th>Peer</th><th>Pos</th><th>Issuer</th><th>Flags</th></tr></thead>
          <tbody>${visible.map(s => `<tr>
            <td><button type="button" class="linkish mono" data-select-ticker="${escapeHtml(s.ticker)}">${escapeHtml(s.ticker)}</button>${s.in_book ? ' <span class="badge badge-ok">book</span>' : ''}</td>
            <td class="mono">${s.composite_score != null ? s.composite_score : '—'}</td>
            <td class="mono">${s.consensus_score ?? '—'}</td>
            <td class="mono">${s.consensus_quintile ?? '—'}</td>
            <td class="mono">${s.core_fund_holder_count ?? 0}</td>
            <td class="mono">${s.specialist_holder_count ?? 0}</td>
            <td class="mono">${s.holder_count_qoq != null ? (s.holder_count_qoq > 0 ? '+' : '') + s.holder_count_qoq : (s.initiation_signal ? 'new' : '—')}</td>
            <td class="mono">${s.spend_value_quintile ?? '—'}</td>
            <td class="mono">${s.insider_score != null ? s.insider_score : '—'}</td>
            <td class="mono">${s.peer_momentum_12m != null ? s.peer_momentum_12m : '—'}</td>
            <td>${escapeHtml(s.position_size_bucket || s.size_bucket || '—')}</td>
            <td>${escapeHtml(s.issuer_size_bucket || '—')}</td>
            <td>${[
              s.convergence_flag ? '<span class="badge badge-ok">convergence</span>' : '',
              s.initiation_signal ? '<span class="badge badge-ok">initiation</span>' : '',
              s.exit_signal ? '<span class="badge badge-bad">exit</span>' : '',
              s.concentration_flag ? '<span class="badge badge-warn">concentration</span>' : '',
              s.short_candidate_score != null && s.short_candidate_score > 0 ? '<span class="badge badge-warn">short-cand</span>' : '',
            ].filter(Boolean).join(' ') || '—'}</td>
          </tr>`).join('') || '<tr><td colspan="13" class="tier-sub">No rows match filters. Try Universe scope or clear filters.</td></tr>'}</tbody>
        </table>
        ${hasMore ? `<button type="button" class="filter-btn" id="biotech-show-more" style="margin-top:8px">Show more (${signalRows.length - showLimit} remaining)</button>` : ''}
      </div>
      ${shortHtml}
      <div class="detail-section">
        <h3>Biotech quant ticker queue</h3>
        <table class="darwin-table">
          <thead><tr><th>Ticker</th><th>Claims</th><th>Evidence</th><th>13F status</th><th>Top claim</th></tr></thead>
          <tbody>${tickers.map(t => {
            const top = (t.top_claims || [])[0] || {};
            const loaded = (t.biotech?.ownership_records || []).length;
            return `<tr>
              <td><button type="button" class="linkish mono" data-select-ticker="${escapeHtml(t.ticker)}">${escapeHtml(t.ticker)}</button><div class="tier-sub">${escapeHtml(t.company || '')}</div></td>
              <td class="mono">${t.claim_count || 0}</td>
              <td class="mono">+${t.confirming_count || 0} / -${t.disconfirming_count || 0}</td>
              <td><span class="badge ${loaded ? 'badge-ok' : 'badge-warn'}">${loaded ? 'loaded' : 'pending'}</span></td>
              <td>${escapeHtml((top.claim || '').slice(0, 180))} ${top.evidence_url ? evidenceLink(top.evidence_url, linkHtml, ghRepo, top.evidence_label) : ''}</td>
            </tr>`;
          }).join('') || '<tr><td colspan="5" class="tier-sub">No portfolio names currently in the biotech quant universe.</td></tr>'}</tbody>
        </table>
      </div>`;
  }

  function filterLetterIndex(rows, opts) {
    const { quarter, search, bookOnly, period, knownTickers = [] } = opts || {};
    let list = rows || [];
    if (period && !period.all) {
      list = list.filter(r => periodMatchesRecord(r, period, ['quarter', 'letter_date']));
    } else if (quarter && quarter !== 'all') {
      list = list.filter(r => r.quarter === quarter);
    }
    if (bookOnly) {
      list = list.filter(r => (r.our_overlap || []).length > 0);
    }
    if (search) {
      list = list.filter(r => SearchMatch.matchLetterIndexRow(r, search, knownTickers));
    }
    return list;
  }

  function consensusSentimentChip(sentiment, escapeHtml) {
    const map = { accumulating: 'badge-ok', reducing: 'badge-bad', mixed: 'badge-warn', discussed: 'badge-us' };
    return `<span class="badge ${map[sentiment] || 'badge-us'}">${escapeHtml(sentiment || 'discussed')}</span>`;
  }

  function consensusTickerCell(row, escapeHtml, opts) {
    const interactive = !(opts && opts.static);
    const book = row.in_book ? '<span class="badge badge-ok" title="In our book" style="margin-left:4px">book</span>' : '';
    if (!interactive) {
      return `<span class="mono">${escapeHtml(row.ticker)}</span>${book}`;
    }
    return `<button type="button" class="linkish mono" data-consensus-ticker="${escapeHtml(row.ticker)}">${escapeHtml(row.ticker)}</button>${book}`;
  }

  function consensusSentimentFromCounts(buys, sells, shorts) {
    if (buys > sells + shorts) return 'accumulating';
    if (sells + shorts > buys) return 'reducing';
    return (buys || sells || shorts) ? 'mixed' : 'discussed';
  }

  function consensusFundSets(row) {
    const buy = new Set(row.buy_fund_names || []);
    const sell = new Set(row.sell_fund_names || []);
    const short = new Set(row.short_fund_names || []);
    const all = new Set(row.funds || []);
    if (!all.size && (row.fund_count || row.buy_funds || row.sell_funds)) {
      (row.funds || []).forEach(f => all.add(f));
    }
    return { buy, sell, short, all };
  }

  function consensusRowsToMap(rows) {
    const map = new Map();
    (rows || []).forEach(r => {
      if (r && r.ticker) map.set(r.ticker, r);
    });
    return map;
  }

  function formatConsensusDelta(value) {
    const n = Number(value || 0);
    if (!n) return '<span class="mono" style="color:var(--text-muted)">0</span>';
    const color = n > 0 ? 'var(--accent-green,#4ade80)' : 'var(--accent-red,#f87171)';
    return `<span class="mono" style="color:${color}">${n > 0 ? '+' : ''}${n}</span>`;
  }

  function priorConsensusPeriod(period, timeModel) {
    if (!period || period.all || !timeModel?.quarters?.length) return null;
    const allIds = timeModel.quarters.map(q => q.id);
    const windowSize = period.quarters.length;
    if (!windowSize) return null;
    if (period.id === 'latest' || windowSize === 1) {
      const qid = period.quarters[0];
      const idx = allIds.indexOf(qid);
      if (idx < 0 || idx >= allIds.length - 1) return null;
      const priorId = allIds[idx + 1];
      return {
        id: `prior:${priorId}`,
        label: `Prior: ${quarterLabel(priorId)}`,
        quarters: [priorId],
        quarterSet: new Set([priorId]),
        all: false,
        selectedYear: parseQuarter(priorId)?.year || period.selectedYear,
      };
    }
    const oldest = period.quarters[period.quarters.length - 1];
    const idx = allIds.indexOf(oldest);
    if (idx < 0) return null;
    const priorIds = allIds.slice(idx + 1, idx + 1 + windowSize);
    if (!priorIds.length) return null;
    return {
      id: `prior:${period.id}`,
      label: `Prior ${windowSize} quarter(s)`,
      quarters: priorIds,
      quarterSet: new Set(priorIds),
      all: false,
      selectedYear: parseQuarter(priorIds[0])?.year || period.selectedYear,
    };
  }

  function computeConsensusQoqShifts(currRows, prevRows) {
    const currMap = consensusRowsToMap(currRows);
    const prevMap = consensusRowsToMap(prevRows);
    const tickers = new Set([...currMap.keys(), ...prevMap.keys()]);
    const shifts = [];
    tickers.forEach(ticker => {
      const c = currMap.get(ticker);
      const p = prevMap.get(ticker);
      const cSets = c ? consensusFundSets(c) : { all: new Set(), buy: new Set(), sell: new Set(), short: new Set() };
      const pSets = p ? consensusFundSets(p) : { all: new Set(), buy: new Set(), sell: new Set(), short: new Set() };
      const newFunds = [...cSets.all].filter(f => !pSets.all.has(f));
      const droppedFunds = [...pSets.all].filter(f => !cSets.all.has(f));
      const cFc = c ? (cSets.all.size || c.fund_count || 0) : 0;
      const pFc = p ? (pSets.all.size || p.fund_count || 0) : 0;
      const cNet = c ? (cSets.buy.size - cSets.sell.size - cSets.short.size) : 0;
      const pNet = p ? (pSets.buy.size - pSets.sell.size - pSets.short.size) : 0;
      const deltaFunds = cFc - pFc;
      const deltaNet = cNet - pNet;
      const cSent = c ? (c.sentiment || consensusSentimentFromCounts(cSets.buy.size, cSets.sell.size, cSets.short.size)) : null;
      const pSent = p ? (p.sentiment || consensusSentimentFromCounts(pSets.buy.size, pSets.sell.size, pSets.short.size)) : null;
      const leanFlip = Boolean(cSent && pSent && cSent !== pSent);
      if (!deltaFunds && !deltaNet && !newFunds.length && !droppedFunds.length && !leanFlip) return;
      const ref = c || p;
      shifts.push({
        ticker,
        name: ref.name,
        in_book: ref.in_book,
        fund_count: cFc,
        prior_fund_count: pFc,
        delta_funds: deltaFunds,
        net: cNet,
        prior_net: pNet,
        delta_net: deltaNet,
        sentiment: cSent || 'discussed',
        prior_sentiment: pSent,
        lean_flip: leanFlip,
        new_funds: newFunds.slice(0, 12),
        dropped_funds: droppedFunds.slice(0, 12),
      });
    });
    return shifts.sort((a, b) => Math.abs(b.delta_net) - Math.abs(a.delta_net)
      || Math.abs(b.delta_funds) - Math.abs(a.delta_funds)
      || String(a.ticker).localeCompare(String(b.ticker)));
  }

  function mergeConsensusRows(rows) {
    const byTicker = new Map();
    rows.forEach(r => {
      const ticker = r.ticker;
      if (!ticker) return;
      const sets = consensusFundSets(r);
      const row = byTicker.get(ticker) || {
        ticker,
        name: r.name || ticker,
        in_book: Boolean(r.in_book),
        buy: new Set(),
        sell: new Set(),
        short: new Set(),
        all: new Set(),
      };
      row.name = row.name || r.name || ticker;
      row.in_book = row.in_book || Boolean(r.in_book);
      sets.buy.forEach(f => row.buy.add(f));
      sets.sell.forEach(f => row.sell.add(f));
      sets.short.forEach(f => row.short.add(f));
      sets.all.forEach(f => row.all.add(f));
      byTicker.set(ticker, row);
    });
    return Array.from(byTicker.values()).map(row => {
      const buyNames = Array.from(row.buy);
      const sellNames = Array.from(row.sell);
      const shortNames = Array.from(row.short);
      const funds = Array.from(row.all);
      const fundCount = funds.length;
      const net = buyNames.length - sellNames.length - shortNames.length;
      return {
        ticker: row.ticker,
        name: row.name,
        in_book: row.in_book,
        fund_count: fundCount,
        buy_funds: buyNames.length,
        sell_funds: sellNames.length,
        short_funds: shortNames.length,
        net,
        sentiment: consensusSentimentFromCounts(buyNames.length, sellNames.length, shortNames.length),
        funds,
        buy_fund_names: buyNames,
        sell_fund_names: sellNames,
        short_fund_names: shortNames,
      };
    });
  }

  function consensusBlockForPeriod(consensus, period, fallbackQuarter) {
    const byQuarter = consensus?.by_quarter || {};
    const qids = period?.quarters || [];
    if (!period || period.all) {
      return { block: byQuarter.all || {}, scope: 'all history' };
    }
    if (qids.length === 1 && byQuarter[qids[0]]) {
      return { block: byQuarter[qids[0]], scope: quarterLabel(qids[0]) };
    }
    if (!qids.length && fallbackQuarter && byQuarter[fallbackQuarter]) {
      return { block: byQuarter[fallbackQuarter], scope: quarterLabel(fallbackQuarter) };
    }
    const blocks = qids.map(qid => byQuarter[qid]).filter(Boolean);
    if (!blocks.length) {
      return { block: { letter_count: 0, most_discussed: [], biggest_changes: [], activity: [] }, scope: period.label };
    }
    const activity = blocks.flatMap(b => b.activity || [])
      .sort((a, b) => String(b.letter_date || '').localeCompare(String(a.letter_date || '')));
    const most = mergeConsensusRows(blocks.flatMap(b => b.most_discussed || []))
      .sort((a, b) => (b.fund_count - a.fund_count) || (Math.abs(b.net) - Math.abs(a.net)) || String(a.ticker).localeCompare(String(b.ticker)));
    const changes = most.filter(r => r.net !== 0)
      .sort((a, b) => (Math.abs(b.net) - Math.abs(a.net)) || (b.fund_count - a.fund_count));
    return {
      block: {
        letter_count: blocks.reduce((sum, b) => sum + Number(b.letter_count || 0), 0),
        most_discussed: most,
        biggest_changes: changes,
        activity,
      },
      scope: period.label,
    };
  }

  function consensusHeatmapCell(row) {
    if (!row) return '<td class="consensus-heat-cell" style="text-align:center;color:var(--text-muted)">·</td>';
    const colors = {
      accumulating: 'rgba(74,222,128,0.35)',
      reducing: 'rgba(248,113,113,0.35)',
      mixed: 'rgba(245,158,11,0.28)',
      discussed: 'rgba(148,163,184,0.18)',
    };
    const bg = colors[row.sentiment] || colors.discussed;
    const net = row.net > 0 ? `+${row.net}` : String(row.net || 0);
    return `<td class="consensus-heat-cell" title="${row.fund_count || 0} funds · net ${net}" style="text-align:center;background:${bg};font-size:10px">${net}</td>`;
  }

  function consensusQuarterlyRows(consensus, ticker, quarterIds) {
    const byQuarter = consensus?.by_quarter || {};
    return (quarterIds || []).map(qid => {
      const block = byQuarter[qid];
      const row = (block?.most_discussed || []).find(r => r.ticker === ticker) || null;
      return { qid, label: quarterLabel(qid), row };
    });
  }

  function renderConsensusTickerDrawer(ticker, consensus, escapeHtml, linkHtml, ghRepo, timeModel) {
    if (!ticker || !consensus) return '';
    const history = consensus.by_ticker?.[ticker] || [];
    const quarterIds = (timeModel?.quarters || []).slice(0, 12).map(q => q.id);
    const quarterly = consensusQuarterlyRows(consensus, ticker, quarterIds);
    const name = history[0]?.name || quarterly.find(q => q.row)?.row?.name || ticker;
    const timelineRows = history.map(r => {
      const sibs = (r.sibling_funds || []).filter(Boolean);
      const fundTitle = sibs.length
        ? `${r.fund || ''} · strategies: ${[r.fund_id, ...sibs].filter(Boolean).join(', ')}`        : (r.fund || '');
      const fundCell = r.fund_id
        ? `<button type="button" class="linkish" data-consensus-fund-id="${escapeHtml(r.fund_id)}" title="${escapeHtml(fundTitle)}">${escapeHtml(r.fund)}</button>`
        : escapeHtml(r.fund);
      return `
      <tr>
        <td class="mono" style="font-size:11px">${escapeHtml(r.letter_date || '—')}</td>
        <td class="mono" style="font-size:11px">${escapeHtml(r.quarter || '—')}</td>
        <td>${fundCell}</td>
        <td><span class="badge ${STANCE_BADGE[r.action] || 'badge-us'}">${escapeHtml(r.action || '—')}</span></td>
        <td style="font-size:11px;max-width:300px">${escapeHtml((r.commentary || '').slice(0, 200))}</td>
        <td>${recordEvidenceLink(r, linkHtml, ghRepo)}</td>
      </tr>`;
    }).join('');
    const sparkCells = quarterly.slice().reverse().map(q => {
      if (!q.row) return `<span class="consensus-spark-dot" style="background:rgba(148,163,184,0.25)" title="${escapeHtml(q.label)}: no mention"></span>`;
      const color = q.row.sentiment === 'accumulating' ? '#4ade80'
        : q.row.sentiment === 'reducing' ? '#f87171'
          : q.row.sentiment === 'mixed' ? '#f59e0b'
            : q.row.sentiment === 'mentioned' ? '#64748b' : '#94a3b8';
      const leanLabel = q.row.fund_count
        ? `${q.row.fund_count} lean`
        : `${q.row.mentioned_count || 0} mentioned`;
      return `<span class="consensus-spark-dot" style="background:${color}" title="${escapeHtml(q.label)}: ${escapeHtml(q.row.sentiment)} (${leanLabel})"></span>`;
    }).join('');
    return `
      <div id="consensus-ticker-drawer" class="detail-section" style="margin-bottom:14px;border:1px solid var(--border);border-radius:8px;padding:12px;background:rgba(255,255,255,0.02)">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
          <h4 style="margin:0"><span class="mono">${escapeHtml(ticker)}</span> · ${escapeHtml((name || '').slice(0, 48))}</h4>
          <button type="button" class="filter-btn" id="consensus-drawer-close">Close</button>
          <button type="button" class="filter-btn" id="consensus-export-csv" data-export-ticker="${escapeHtml(ticker)}">Export CSV</button>
          <button type="button" class="linkish" data-select-ticker="${escapeHtml(ticker)}">Open holding</button>
        </div>
        <div style="display:flex;align-items:center;gap:4px;margin-bottom:10px" title="Fund lean by quarter (oldest → newest)">${sparkCells}</div>
        ${timelineRows ? `<table class="darwin-table">
          <thead><tr><th>Date</th><th>Quarter</th><th>Fund</th><th>Action</th><th>Commentary</th><th>Source</th></tr></thead>
          <tbody>${timelineRows}</tbody>
        </table>` : '<p class="subhead">No letter mentions for this ticker.</p>'}
      </div>`;
  }

  function renderConsensusShifted(shifts, priorLabel, escapeHtml) {
    if (!shifts.length) {
      return '<p class="subhead">No meaningful shifts vs the prior period for this filter.</p>';
    }
    const rows = shifts.slice(0, 48).map(r => {
      const direction = r.delta_net > 0 ? 'strengthening' : r.delta_net < 0 ? 'weakening' : 'coverage changed';
      const directionClass = r.delta_net > 0 ? 'positive' : r.delta_net < 0 ? 'negative' : 'neutral';
      const fundChanges = [
        r.new_funds?.length ? `Added: ${r.new_funds.map(f => escapeHtml(f)).join(', ')}` : '',
        r.dropped_funds?.length ? `Dropped: ${r.dropped_funds.map(f => escapeHtml(f)).join(', ')}` : '',
      ].filter(Boolean).join(' &middot; ');
      return `<article class="consensus-signal-row${r.in_book ? ' book-conflict' : ''}">
        <div class="consensus-signal-identity">
          <div>${consensusTickerCell(r, escapeHtml)} <strong>${escapeHtml((r.name || '').slice(0, 42))}</strong></div>
          <div class="consensus-signal-meta">${r.prior_fund_count ?? 0} &rarr; ${r.fund_count ?? 0} funds &middot; net ${r.prior_net > 0 ? '+' : ''}${r.prior_net ?? 0} &rarr; ${r.net > 0 ? '+' : ''}${r.net ?? 0}</div>
        </div>
        <div class="consensus-signal-change ${directionClass}">
          <strong>${r.delta_net > 0 ? '&uarr;' : r.delta_net < 0 ? '&darr;' : '&rarr;'} ${direction}</strong>
          <span>${formatConsensusDelta(r.delta_net)} net &middot; ${formatConsensusDelta(r.delta_funds)} funds</span>
        </div>
        <div class="consensus-signal-lean">${r.lean_flip ? `${consensusSentimentChip(r.prior_sentiment, escapeHtml)} &rarr; ${consensusSentimentChip(r.sentiment, escapeHtml)}` : consensusSentimentChip(r.sentiment, escapeHtml)}</div>
        ${fundChanges ? `<div class="consensus-signal-evidence">${fundChanges}</div>` : ''}
      </article>`;
    }).join('');
    return `
      <div class="consensus-section-heading"><div><strong>What changed</strong><span> versus ${escapeHtml(priorLabel || 'the prior period')}</span></div><span>${shifts.length} material shifts</span></div>
      <div class="consensus-signal-list">${rows}</div>`;
  }

  function renderConsensusHeatmap(consensus, escapeHtml, opts) {
    const { period, timeModel, bookOnly, search, knownTickers, quarterIds } = opts || {};
    const heatQuarters = (quarterIds || timeModel?.quarters?.slice(0, 8) || []).map(q => q.id || q);
    const byQuarter = consensus?.by_quarter || {};
    const tickerSet = new Map();
    heatQuarters.forEach(qid => {
      (byQuarter[qid]?.most_discussed || []).forEach(r => {
        if (bookOnly && !r.in_book) return;
        if (search && !SearchMatch.matchConsensusRow(r, search, knownTickers)) return;
        const prev = tickerSet.get(r.ticker) || { ticker: r.ticker, name: r.name, in_book: r.in_book, total: 0 };
        prev.total += r.fund_count || 0;
        tickerSet.set(r.ticker, prev);
      });
    });
    const tickers = Array.from(tickerSet.values())
      .sort((a, b) => b.total - a.total || String(a.ticker).localeCompare(String(b.ticker)))
      .slice(0, 50);
    if (!tickers.length) return '<p class="subhead">No securities match this filter.</p>';
    const head = heatQuarters.map(qid => `<th class="mono" style="font-size:10px">${escapeHtml(quarterLabel(qid))}</th>`).join('');
    const body = tickers.map(t => {
      const cells = heatQuarters.map(qid => {
        const row = (byQuarter[qid]?.most_discussed || []).find(r => r.ticker === t.ticker) || null;
        return consensusHeatmapCell(row);
      }).join('');
      return `<tr>
        <td>${consensusTickerCell(t, escapeHtml)}</td>
        <td style="font-size:11px">${escapeHtml((t.name || '').slice(0, 28))}</td>
        ${cells}
      </tr>`;
    }).join('');
    return `
      <p class="tier-sub" style="margin-bottom:8px">Net fund lean by quarter (cell = net buy−sell funds; color = lean)</p>
      <div style="overflow-x:auto">
        <table class="darwin-table consensus-heatmap">
          <thead><tr><th>Ticker</th><th>Name</th>${head}</tr></thead>
          <tbody>${body}</tbody>
        </table>
      </div>`;
  }

  function renderConsensusFundTrajectory(fundProfiles, letterIndex, escapeHtml, opts) {
    const { search, bookOnly, period, knownTickers, selectedFundId } = opts || {};
    let funds = Object.values(fundProfiles || {});
    if (search) {
      funds = funds.filter(f => SearchMatch.matchFundRegistryRow({
        fund: f.fund,
        fund_id: f.fund_id,
        manager: f.manager,
        quarter: (f.letters || [])[0]?.quarter,
        tickers: f.our_tickers,
      }, search, knownTickers));
    }
    if (bookOnly) {
      funds = funds.filter(f => (f.our_tickers || []).length > 0);
    }
    funds.sort((a, b) => String(a.fund || '').localeCompare(String(b.fund || '')));
    const profile = selectedFundId ? fundProfiles[selectedFundId] : null;
    const fundOptions = funds.map(f => {
      const label = `${f.fund || f.fund_id}${f.manager ? ` - ${f.manager}` : ''}`;
      return `<option value="${escapeHtml(label)}" data-fund-id="${escapeHtml(f.fund_id)}"></option>`;
    }).join('');
    let trajectory = '';
    if (profile) {
      const letters = (profile.letters || []).filter(l => {
        if (period && !period.all && period.quarterSet?.size) {
          return period.quarterSet.has(l.quarter);
        }
        return true;
      });
      const rows = letters.flatMap(letter => {
        const positions = (letter.positions || []).filter(p => p.ticker && (!bookOnly || (profile.our_tickers || []).includes(String(p.ticker).toUpperCase())));
        return positions.map(p => ({
          quarter: letter.quarter,
          letter_date: letter.letter_date,
          ticker: p.ticker,
          action: p.action,
          commentary: p.commentary || p.thesis,
        }));
      }).sort((a, b) => String(b.letter_date || b.quarter || '').localeCompare(String(a.letter_date || a.quarter || '')));
      trajectory = rows.length ? `<table class="darwin-table">
        <thead><tr><th>Quarter</th><th>Date</th><th>Ticker</th><th>Action</th><th>Commentary</th></tr></thead>
        <tbody>${rows.slice(0, 150).map(r => `
          <tr>
            <td class="mono" style="font-size:11px">${escapeHtml(r.quarter || '—')}</td>
            <td class="mono" style="font-size:11px">${escapeHtml(r.letter_date || '—')}</td>
            <td><button type="button" class="linkish mono" data-consensus-ticker="${escapeHtml(r.ticker)}">${escapeHtml(r.ticker)}</button></td>
            <td><span class="badge ${STANCE_BADGE[r.action] || 'badge-us'}">${escapeHtml(r.action || '—')}</span></td>
            <td style="font-size:11px">${escapeHtml((r.commentary || '').slice(0, 160))}</td>
          </tr>`).join('')}</tbody>
      </table>` : '<p class="subhead">No position commentary for this fund in the selected period.</p>';
    }
    return `
      <div class="consensus-section-heading"><div><strong>Fund trajectory</strong><span> one canonical fund across every letter and alias</span></div><span>${funds.length} funds</span></div>
      <label class="tier-sub consensus-fund-picker">
        <span>Find a fund</span>
        <input id="consensus-fund-search" class="search" list="consensus-fund-options" autocomplete="off" placeholder="Type a fund name..." value="${escapeHtml(profile?.fund || '')}" />
        <datalist id="consensus-fund-options">${fundOptions}</datalist>
      </label>
      ${profile ? `<p class="tier-sub" style="margin-bottom:10px"><strong>${escapeHtml(profile.fund || profile.fund_id)}</strong> &middot; ${profile.letters?.length || 0} letters &middot; ${profile.latest_quarter ? `latest ${escapeHtml(profile.latest_quarter)}` : 'no dated letters'}</p>` : '<p class="tier-sub" style="margin-bottom:10px">Quarter-stamped aliases are consolidated into one continuous history.</p>'}
      ${trajectory}`;
  }

  function buildConsensusCsv(ticker, consensus, timeModel) {
    const quarterIds = (timeModel?.quarters || []).map(q => q.id);
    const quarterly = consensusQuarterlyRows(consensus, ticker, quarterIds);
    const history = consensus?.by_ticker?.[ticker] || [];
    const lines = ['section,quarter,date,fund,action,fund_count,buy_funds,sell_funds,net,sentiment,commentary'];
    quarterly.forEach(q => {
      const r = q.row;
      if (!r) return;
      lines.push([
        'quarterly',
        q.qid,
        '',
        '',
        '',
        r.fund_count,
        r.buy_funds,
        (r.sell_funds || 0) + (r.short_funds || 0),
        r.net,
        r.sentiment,
        '',
      ].map(v => `"${String(v ?? '').replace(/"/g, '""')}"`).join(','));
    });
    history.forEach(r => {
      lines.push([
        'mention',
        r.quarter || '',
        r.letter_date || '',
        r.fund || '',
        r.action || '',
        '',
        '',
        '',
        '',
        '',
        (r.commentary || '').slice(0, 500),
      ].map(v => `"${String(v ?? '').replace(/"/g, '""')}"`).join(','));
    });
    return lines.join('\n');
  }

  function attachConsensusHandlers(container, insights, options) {
    const {
      escapeHtml,
      timeModel,
      onViewMode,
      onFundSelect,
      onTickerSelect,
      onCloseDrawer,
    } = options || {};
    if (!container) return;
    container.querySelectorAll('[data-consensus-view]').forEach(btn => {
      btn.addEventListener('click', () => {
        if (onViewMode) onViewMode(btn.dataset.consensusView || 'table');
      });
    });
    container.querySelectorAll('[data-consensus-ticker]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const ticker = btn.dataset.consensusTicker;
        if (ticker && onTickerSelect) onTickerSelect(ticker);
      });
    });
    container.querySelectorAll('[data-consensus-fund-id]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const id = btn.dataset.consensusFundId;
        if (id && onFundSelect) onFundSelect(id, 'fund');
      });
    });
    const closeBtn = container.querySelector('#consensus-drawer-close');
    if (closeBtn) closeBtn.addEventListener('click', () => { if (onCloseDrawer) onCloseDrawer(); });
    const exportBtn = container.querySelector('#consensus-export-csv');
    if (exportBtn) {
      exportBtn.addEventListener('click', () => {
        const ticker = exportBtn.dataset.exportTicker;
        if (!ticker || !insights?.consensus) return;
        const csv = buildConsensusCsv(ticker, insights.consensus, timeModel);
        const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `consensus_${ticker}.csv`;
        a.click();
        URL.revokeObjectURL(url);
      });
    }
    const fundSearch = container.querySelector('#consensus-fund-search');
    if (fundSearch) {
      const selectExactFund = () => {
        const options = Array.from(container.querySelectorAll('#consensus-fund-options option'));
        const value = fundSearch.value.trim().toLowerCase();
        const match = options.find(option => option.value.trim().toLowerCase() === value);
        if (match && onFundSelect) onFundSelect(match.dataset.fundId || null, 'fund');
      };
      fundSearch.addEventListener('input', selectExactFund);
      fundSearch.addEventListener('change', selectExactFund);
    }
  }

  function renderConsensus(consensus, escapeHtml, linkHtml, ghRepo, opts) {
    const {
      quarter = 'last4',
      bookOnly = false,
      search = '',
      period = null,
      knownTickers = [],
      timeModel = null,
      viewMode = 'table',
      selectedTicker = null,
      selectedFundId = null,
      fundProfiles = null,
      letterIndex = null,
    } = opts || {};
    if (!consensus || !consensus.by_quarter) {
      return '<p class="subhead">No consensus built yet. Run <span class="mono">python _system/scripts/build_insights.py</span>.</p>';
    }
    const { block, scope } = consensusBlockForPeriod(consensus, period, quarter);
    const matchRow = r => !search || SearchMatch.matchConsensusRow(r, search, knownTickers);
    const bookRow = r => !bookOnly || r.in_book;
    const most = (block.most_discussed || []).filter(r => bookRow(r) && matchRow(r));
    const changes = (block.biggest_changes || []).filter(r => bookRow(r) && matchRow(r));
    const activity = (block.activity || []).filter(r => bookRow(r) && matchRow(r));
    const summary = consensus.summary || {};

    const priorPeriod = priorConsensusPeriod(period, timeModel);
    let qoqShifts = [];
    let priorLabel = '';
    if (priorPeriod) {
      const priorBlock = consensusBlockForPeriod(consensus, priorPeriod, quarter).block;
      qoqShifts = computeConsensusQoqShifts(block.most_discussed, priorBlock.most_discussed)
        .filter(r => bookRow(r) && matchRow(r));
      priorLabel = priorPeriod.label;
    } else if (period?.quarters?.length === 1 && consensus.qoq_by_quarter?.[period.quarters[0]]?.shifts?.length) {
      qoqShifts = (consensus.qoq_by_quarter[period.quarters[0]].shifts || [])
        .filter(r => bookRow(r) && matchRow(r));
      priorLabel = quarterLabel(consensus.qoq_by_quarter[period.quarters[0]].prior_quarter);
    }

    const qoqByTicker = consensusRowsToMap(qoqShifts);
    const showDelta = viewMode === 'table' && qoqShifts.length > 0;

    const viewTabs = [
      { id: 'shifted', label: 'Changes' },
      { id: 'table', label: 'Current' },
      { id: 'heatmap', label: 'History' },
      { id: 'fund', label: 'By fund' },
    ];

    const mostRows = most.slice(0, 60).map((r, i) => {
      const qoq = qoqByTicker.get(r.ticker);
      const delta = qoq ? `${qoq.delta_net > 0 ? '&uarr;' : qoq.delta_net < 0 ? '&darr;' : '&rarr;'} ${formatConsensusDelta(qoq.delta_net)} net` : '&rarr; stable';
      return `<article class="consensus-signal-row${r.in_book && r.sentiment === 'reducing' ? ' book-conflict' : ''}">
        <div class="consensus-rank">${i + 1}</div>
        <div class="consensus-signal-identity">
          <div>${consensusTickerCell(r, escapeHtml)} <strong>${escapeHtml((r.name || '').slice(0, 44))}</strong></div>
          <div class="consensus-signal-meta">${r.fund_count} funds &middot; ${r.buy_funds || 0} adding &middot; ${(r.sell_funds || 0) + (r.short_funds || 0)} reducing &middot; net ${r.net > 0 ? '+' : ''}${r.net}</div>
        </div>
        <div class="consensus-signal-change ${qoq?.delta_net > 0 ? 'positive' : qoq?.delta_net < 0 ? 'negative' : 'neutral'}"><strong>${delta}</strong><span>${qoq ? `${formatConsensusDelta(qoq.delta_funds)} funds vs prior` : 'no prior comparison'}</span></div>
        <div class="consensus-signal-lean">${consensusSentimentChip(r.sentiment, escapeHtml)}</div>
      </article>`;
    }).join('');

    const activityRows = activity.slice(0, 120).map(r => `
      <tr>
        <td class="mono" style="font-size:11px">${escapeHtml(r.letter_date || '—')}</td>
        <td>${r.fund_id ? `<button type="button" class="linkish" data-consensus-fund-id="${escapeHtml(r.fund_id)}">${escapeHtml(r.fund)}</button>` : escapeHtml(r.fund)}</td>
        <td><span class="badge ${STANCE_BADGE[r.action] || 'badge-us'}">${escapeHtml(r.action)}</span></td>
        <td>${consensusTickerCell(r, escapeHtml)}</td>
        <td style="font-size:11px;max-width:340px">${escapeHtml((r.commentary || '').slice(0, 180))}</td>
        <td>${recordEvidenceLink(r, linkHtml, ghRepo)}</td>
      </tr>`).join('');

    const changesRows = changes.slice(0, 24).map(r => `
      <tr>
        <td>${consensusTickerCell(r, escapeHtml)}</td>
        <td style="font-size:11px">${escapeHtml((r.name || '').slice(0, 32))}</td>
        <td class="mono" style="text-align:center;color:${r.net >= 0 ? 'var(--accent-green,#4ade80)' : 'var(--accent-red,#f87171)'}">${r.net > 0 ? '+' : ''}${r.net}</td>
        <td>${consensusSentimentChip(r.sentiment, escapeHtml)}</td>
      </tr>`).join('');

    const drawer = selectedTicker
      ? renderConsensusTickerDrawer(selectedTicker, consensus, escapeHtml, linkHtml, ghRepo, timeModel)
      : '';

    let body = '';
    if (viewMode === 'shifted') {
      body = renderConsensusShifted(qoqShifts, priorLabel, escapeHtml);
    } else if (viewMode === 'heatmap') {
      body = renderConsensusHeatmap(consensus, escapeHtml, {
        period, timeModel, bookOnly, search, knownTickers,
        quarterIds: timeModel?.quarters?.slice(0, 8),
      });
    } else if (viewMode === 'fund') {
      body = renderConsensusFundTrajectory(fundProfiles, letterIndex, escapeHtml, {
        search, bookOnly, period, knownTickers, selectedFundId,
      });
    } else {
      body = `
      <div class="consensus-section-heading"><div><strong>Current consensus</strong><span> ranked by breadth and conviction</span></div><span>${most.length} securities</span></div>
      ${most.length ? `<div class="consensus-signal-list">${mostRows}</div>` : '<p class="subhead">No securities match this filter.</p>'}`;
    }

    const reducingBook = most.filter(r => r.in_book && r.sentiment === 'reducing').length;
    const reversals = qoqShifts.filter(r => r.lean_flip).length;
    const largestDrop = qoqShifts.slice().sort((a, b) => a.delta_net - b.delta_net)[0];
    const disagreement = most.filter(r => (r.buy_funds || 0) > 0 && ((r.sell_funds || 0) + (r.short_funds || 0)) > 0)
      .sort((a, b) => ((b.buy_funds || 0) + (b.sell_funds || 0) + (b.short_funds || 0)) - ((a.buy_funds || 0) + (a.sell_funds || 0) + (a.short_funds || 0)))[0];
    const brief = reducingBook
      ? `${reducingBook} portfolio holding${reducingBook === 1 ? ' is' : 's are'} being reduced by outside investors${largestDrop ? `; ${largestDrop.ticker} weakened most versus the prior period` : ''}.`
      : largestDrop
        ? `${largestDrop.ticker} showed the largest deterioration versus the prior period; no portfolio-wide reduction signal is present.`
        : 'No material portfolio conflict is visible in the selected period.';

    return `
      ${drawer}
      <section class="consensus-brief">
        <div><span class="consensus-eyebrow">Investor brief</span><strong>${escapeHtml(brief)}</strong></div>
        <span>${summary.fund_count || 0} canonical funds &middot; ${escapeHtml(scope)}${bookOnly ? ' &middot; our book only' : ''}</span>
      </section>
      <div class="consensus-kpis">
        <button type="button" data-consensus-view="table"><span>Holdings reducing</span><strong>${reducingBook}</strong><small>current conflicts</small></button>
        <button type="button" data-consensus-view="shifted"><span>Lean reversals</span><strong>${reversals}</strong><small>vs prior period</small></button>
        <button type="button" data-consensus-view="shifted"><span>Largest deterioration</span><strong>${escapeHtml(largestDrop?.ticker || 'None')}</strong><small>${largestDrop ? `net ${largestDrop.delta_net > 0 ? '+' : ''}${largestDrop.delta_net}` : 'no material shift'}</small></button>
        <button type="button" data-consensus-view="table"><span>Most disputed</span><strong>${escapeHtml(disagreement?.ticker || 'None')}</strong><small>${disagreement ? `${disagreement.buy_funds || 0} adding / ${(disagreement.sell_funds || 0) + (disagreement.short_funds || 0)} reducing` : 'no two-way action'}</small></button>
      </div>
      <nav class="source-pills consensus-view-tabs" id="consensus-view-tabs">
        ${viewTabs.map(t => `<button type="button" class="filter-btn source-pill${viewMode === t.id ? ' active' : ''}" data-consensus-view="${escapeHtml(t.id)}">${escapeHtml(t.label)}</button>`).join('')}
      </nav>
      ${body}`;
  }

  function renderInsightsPanel(insights, options) {
    const {
      escapeHtml,
      linkHtml,
      ghRepo = 'magis-capital-partners/single-stock-investments',
      quarter = 'all',
      fundSearch = '',
      bookOnly = false,
      needsReviewOnly = false,
      selectedFundId = null,
      activeSection = 'letters',
      tickers = [],
      memory = null,
      documentCatalog = null,
      pdfSourceTab = 'all',
      pdfTimeMode = 'period',
      portfolioMacro = [],
      portfolioMacroRegime = null,
      worldModel = null,
      hkSnowball = null,
      tickerSourceFilter = 'ownership',
      podcastShowId = 'all',
      podcastFlagFilter = 'all',
      selectedPodcastEpisodeId = null,
      podcastEpisodeDetail = null,
      podcastEpisodeDetailLoading = false,
      kpiTrends = null,
      inflectionTier = 'displayed',
      eventTier = 'signal',
      eventRange = 'last7',
      eventScope = 'holdings',
      eventKind = 'observed',
      eventSource = 'all',
      eventAxis = 'all',
      eventDirection = 'all',
      eventConfidence = 'all',
      eventReview = 'unreviewed',
      eventReviewState = {},
      eventLastSeenAt = null,
    } = options || {};

    const profiles = insights?.fund_profiles || {};
    if (selectedFundId && profiles[selectedFundId]) {
      return renderFundDetail(profiles[selectedFundId], escapeHtml, linkHtml, ghRepo);
    }

    const letterIndex = insights?.letter_index || [];
    const timeModel = buildTimeModel(insights, documentCatalog);
    const periodQuarter = activeSection === 'consensus' ? (options?.consensusQuarter || quarter || 'last4') : quarter;
    const period = periodFromSelection(periodQuarter, timeModel);
    const knownTickers = SearchMatch.catalogKnownTickers(documentCatalog);
    let funds = Object.values(insights?.fund_profiles || {});
    if (!funds.length) {
      funds = insights?.fund_registry || [];
    } else {
      funds = funds.map(p => ({
        ...p,
        letter_count: (p.letters || []).length,
        our_ticker_count: (p.our_tickers || []).length,
        duplicate_count: p.duplicate_count || p.near_dup_count || 0,
      })).sort((a, b) => String(a.fund || '').localeCompare(String(b.fund || '')));
    }
    let letters = filterLetterIndex(letterIndex, { period, search: fundSearch, bookOnly, knownTickers });
    const coverage = periodCoverage(period, timeModel, letterIndex, insights?.fund_registry || []);

    if (fundSearch) {
      funds = funds.filter(f => SearchMatch.matchFundRegistryRow(f, fundSearch, knownTickers));
    }
    if (bookOnly) {
      funds = funds.filter(f => (f.our_ticker_count || 0) > 0);
    }
    if (period && !period.all) {
      funds = funds.filter(f => periodMatchesRecord(f, period, ['quarter', 'letter_date']));
    }

    const rangeTabs = [
      { id: 'latest', label: activeSection === 'documents' ? 'Latest catalog' : 'Latest' },
      { id: 'last4', label: 'Last 4Q' },
      { id: 'last8', label: 'Last 8Q' },
      { id: 'since2020', label: 'Since 2020' },
      { id: 'all', label: 'All history' },
    ];
    const yearSource = activeSection === 'documents'
      ? timeModel.years
      : (timeModel.indexedYears?.length ? timeModel.indexedYears : timeModel.years);
    const selectedYear = period.selectedYear || timeModel.latestYear;
    const yearTabs = yearSource.map(y => ({ id: `year:${y}`, label: String(y), year: y }));
    const quarterTabs = selectedYear
      ? [
          { id: `year:${selectedYear}`, label: 'Full year' },
          { id: `${selectedYear}Q1`, label: 'Q1' },
          { id: `${selectedYear}Q2`, label: 'Q2' },
          { id: `${selectedYear}Q3`, label: 'Q3' },
          { id: `${selectedYear}Q4`, label: 'Q4' },
        ]
      : [];
    const sections = [
      { id: 'letters', label: 'Letters' },
      { id: 'podcasts', label: 'Podcasts' },
      { id: 'inflections', label: 'Inflections' },
      { id: 'events', label: 'What changed' },
      { id: 'index_watch', label: 'Index Watch' },
      { id: 'consensus', label: 'Consensus' },
      { id: 'funds', label: 'Funds' },
      { id: 'documents', label: 'PDF library' },
      { id: 'tickers', label: 'Ticker insights' },
      { id: 'memory', label: 'Research memory' },
      { id: 'sources', label: 'Pipeline status' },
    ];

    let body = '';
    if (activeSection === 'inflections') {
      body = renderInflections(kpiTrends, escapeHtml, { search: fundSearch, bookOnly, inflectionTier });
    } else if (activeSection === 'events') {
      body = renderDecisionEventQueue(insights?.events || [], escapeHtml, linkHtml, ghRepo, {
        search: fundSearch,
        knownTickers,
        eventTier,
        eventRange,
        eventScope,
        eventKind,
        eventSource,
        eventAxis,
        eventDirection,
        eventConfidence,
        eventReview,
        reviewState: eventReviewState,
        lastSeenAt: eventLastSeenAt,
        generatedAt: insights?.generated_at,
        historyStart: ((insights?.provenance || {}).event_triage_summary || {}).history_start,
        historyEnd: ((insights?.provenance || {}).event_triage_summary || {}).history_end,
      });
    } else if (activeSection === 'index_watch') {
      const indexPayload = options?.indexMembership || null;
      if (global.IndexViz && indexPayload) {
        body = global.IndexViz.renderIndexWatch(indexPayload, { escapeHtml, linkHtml });
      } else {
        body = '<p class="muted">Index membership not built. Run: python _system/scripts/build_index_membership.py</p>';
      }
    } else if (activeSection === 'consensus') {
      body = renderConsensus(insights?.consensus, escapeHtml, linkHtml, ghRepo, {
        quarter: periodQuarter,
        period,
        bookOnly,
        search: fundSearch,
        knownTickers,
        timeModel,
        viewMode: options?.consensusViewMode || 'table',
        selectedTicker: options?.consensusSelectedTicker || null,
        selectedFundId: options?.consensusFundId || null,
        fundProfiles: insights?.fund_profiles || {},
        letterIndex,
      });
    } else if (activeSection === 'letters') {
      const prov = insights?.provenance || {};
      const posPct = prov.letters_with_positions_pct != null
        ? `${Math.round(Number(prov.letters_with_positions_pct) * 1000) / 10}% with disclosed positions`
        : '';
      const positionStats = [posPct, `${letters.length} letter(s)`, escapeHtml(period.label), bookOnly ? 'overlap with our book only' : ''].filter(Boolean).join(' · ');
      body = `<p class="tier-sub" style="margin-bottom:8px">${escapeHtml(period.label)}${bookOnly ? ' · overlap with our book only' : ''}</p>`
        + renderLetterIndex(letters, escapeHtml, linkHtml, ghRepo, true, positionStats, period, timeModel, bookOnly);
        } else if (activeSection === 'podcasts') {
      body = renderPodcastIndex(
        insights?.podcast_index || [],
        insights?.podcast_by_show || {},
        escapeHtml,
        linkHtml,
        ghRepo,
        {
          bookOnly,
          search: fundSearch,
          period,
          showId: podcastShowId,
          flagFilter: podcastFlagFilter,
          selectedEpisodeId: selectedPodcastEpisodeId,
          episodeDetail: podcastEpisodeDetail,
          episodeDetailLoading: podcastEpisodeDetailLoading,
        },
      );
} else if (activeSection === 'funds') {
      body = renderFundRegistry(funds, escapeHtml, linkHtml, ghRepo, bookOnly);
    } else if (activeSection === 'documents') {
      body = renderDocumentCatalog(documentCatalog, escapeHtml, linkHtml, {
        search: fundSearch,
        period,
        bookOnly,
        pdfSourceTab,
        pdfTimeMode,
      });
    } else if (activeSection === 'tickers') {
      body = renderWorldModelStrip(worldModel, escapeHtml, hkSnowball)
        + renderPortfolioMacroStrip(portfolioMacroRegime, escapeHtml, linkHtml, portfolioMacro)
        + renderTickerEssentials(tickers, escapeHtml, linkHtml, {
          search: fundSearch,
          bookOnly,
          sourceFilter: tickerSourceFilter,
          knownTickers,
          viewMode: options?.tickerViewMode || 'scan',
          sortMode: options?.tickerSortMode || 'attention',
          gapsMode: options?.tickerGapsMode || 'attention',
          insiderTier: options?.tickerInsiderTier || 'signal',
          selectedTicker: options?.tickerSelectedTicker || null,
          ghRepo,
        });
    } else if (activeSection === 'memory') {
      const holdingsTickers = (tickers || []).filter(t => t.in_holdings).map(t => t.ticker);
      const memoryViewMode = options?.memoryViewMode || 'ledger';
      const memoryOpts = {
        search: fundSearch,
        bookOnly,
        period,
        knownTickers,
        holdingsTickers,
        biotechOnly: options?.memoryBiotechOnly || false,
        typeFilter: options?.memoryTypeFilter || 'all',
        memoryViewMode,
        memoryTypeFilter: options?.memoryTypeFilter || 'all',
        memoryBiotechOnly: options?.memoryBiotechOnly || false,
        ghRepo,
      };
      body = renderMemorySummary(memory, escapeHtml)
        + renderMemorySubNav(memoryViewMode, escapeHtml)
        + renderMemoryFilters(memoryOpts, escapeHtml);
      if (memoryViewMode === 'biotech') {
        body += renderBiotechMemory(memory, escapeHtml, linkHtml, ghRepo, {
          biotechScope: options?.biotechScope || 'book',
          biotechConvergenceOnly: options?.biotechConvergenceOnly || false,
          biotechSpendQ4: options?.biotechSpendQ4 || false,
          biotechSizeFilter: options?.biotechSizeFilter || 'all',
          biotechIssuerSizeFilter: options?.biotechIssuerSizeFilter || 'all',
          biotechSearch: options?.biotechSearch || '',
          biotechShowLimit: options?.biotechShowLimit || 40,
        });
      } else if (memoryViewMode === 'review') {
        body += renderMemoryReviewQueue(memory, escapeHtml);
      } else {
        body += renderMemoryLedger(memory, escapeHtml, linkHtml, memoryOpts);
      }
    } else {
      body = renderSourceHealth(insights?.source_health || {}, escapeHtml)
        + renderDataSourceCandidates(insights?.data_source_candidates || {}, escapeHtml);
    }

    const showPeriodControls = activeSection !== 'tickers' && activeSection !== 'inflections' && activeSection !== 'memory' && activeSection !== 'events';
    const bookLabel = activeSection === 'tickers' ? 'Holdings only' : 'Our book overlap';

    return `
      <h2 style="font-size:18px;margin-bottom:6px">Insights</h2>
      <p class="subhead" style="margin-bottom:14px">
        Portfolio context only · ${insights?.event_count || 0} events · ${insights?.letter_count || 0} letters · ${insights?.podcast_count || 0} podcasts · ${insights?.front_record_count || 0} front records · ${insights?.archived_record_count || 0} archived
      </p>
      <nav class="view-tabs" id="insights-section-tabs" style="margin-bottom:10px">
        ${sections.map(s => `<button type="button" class="view-tab${activeSection === s.id ? ' active' : ''}" data-insights-section="${s.id}">${s.label}</button>`).join('')}
      </nav>
      <div class="detail-section${activeSection === 'consensus' ? ' consensus-toolbar' : ''}" style="display:grid;gap:8px;margin-bottom:12px">
        ${activeSection === 'consensus' ? `<div class="consensus-toolbar-main">
          <label><span>Period</span><select id="consensus-period-select" class="search">
            ${[...rangeTabs, ...yearTabs, ...quarterTabs.filter(t => t.id !== `year:${selectedYear}`)].map(t => `<option value="${escapeHtml(t.id)}"${period.id === t.id ? ' selected' : ''}>${escapeHtml(t.label)}</option>`).join('')}
          </select></label>
          <label class="tier-sub consensus-book-toggle"><input type="checkbox" id="insights-book-only" ${bookOnly ? 'checked' : ''} /> Our book only</label>
          <input class="search consensus-search" id="fund-registry-search" placeholder="Search ticker or fund..." value="${escapeHtml(fundSearch)}" />
          <details class="consensus-coverage"><summary>Coverage</summary><div>Viewing ${escapeHtml(period.label)} &middot; ${coverage.quarters} quarter(s) &middot; ${coverage.letters} indexed letters &middot; ${coverage.funds} fund rows</div></details>
        </div>` : ''}
        ${showPeriodControls && activeSection !== 'consensus' ? `<nav class="source-pills" id="insights-range-tabs" style="margin-bottom:0">
          ${rangeTabs.map(t => `<button type="button" class="filter-btn source-pill${period.id === t.id ? ' active' : ''}" data-insights-quarter="${escapeHtml(t.id)}">${escapeHtml(t.label)}</button>`).join('')}
        </nav>
        <nav class="source-pills" id="insights-year-tabs" style="margin-bottom:0">
          ${yearTabs.map(t => `<button type="button" class="filter-btn source-pill${period.id === t.id ? ' active' : ''}" data-insights-quarter="${escapeHtml(t.id)}">${escapeHtml(t.label)}</button>`).join('')}
        </nav>
        ${quarterTabs.length ? `<nav class="source-pills" id="insights-quarter-tabs" style="margin-bottom:0">
          ${quarterTabs.map(t => `<button type="button" class="filter-btn source-pill${period.id === t.id ? ' active' : ''}" data-insights-quarter="${escapeHtml(t.id)}">${escapeHtml(t.label)}</button>`).join('')}
        </nav>` : ''}` : (activeSection === 'events' || activeSection === 'consensus' ? '' : `<p class="tier-sub">Ticker insights use ticker-specific signals by default. Macro indices appear once above the table.</p>`)}
        ${activeSection !== 'consensus' ? `<div style="display:flex;flex-wrap:wrap;gap:10px;align-items:center">
          ${activeSection !== 'events' ? `<label class="tier-sub" style="display:flex;align-items:center;gap:6px">
            <input type="checkbox" id="insights-book-only" ${bookOnly ? 'checked' : ''} />
            ${escapeHtml(bookLabel)}
          </label>` : ''}
          <input class="search" id="fund-registry-search" placeholder="${activeSection === 'podcasts' ? 'Search show, guest, ticker, theme...' : 'Search ticker, event, fund, theme, source...'}" value="${escapeHtml(fundSearch)}" style="max-width:320px" />
        </div>` : ''}
        ${showPeriodControls && activeSection !== 'consensus' ? `<div class="tier-sub">
          Viewing ${escapeHtml(period.label)} &middot; ${activeSection === 'podcasts'
            ? `${(insights?.podcast_index || []).length} indexed episode(s) · ${Object.keys(insights?.podcast_by_show || {}).length} show(s)`
            : `${coverage.quarters} quarter(s) &middot; ${coverage.letters} indexed letter(s)${coverage.drivePdfCount ? ` &middot; ${coverage.drivePdfCount} catalog PDF(s)` : ''} &middot; ${coverage.funds} fund row(s)${coverage.folderCount ? ` &middot; ${coverage.folderCount} Drive source folder(s)` : ''}${coverage.letters === 0 && coverage.drivePdfCount > 0 ? ' &middot; <span style="color:var(--accent-amber)">PDFs cataloged — run make letter-extract-text</span>' : ''}${period.id === 'latest' && timeModel.latestCatalogQuarter && timeModel.latestIndexedQuarter && timeModel.latestCatalogQuarter !== timeModel.latestIndexedQuarter ? ` &middot; <span style="color:var(--text-muted)">Latest indexed: ${escapeHtml(quarterLabel(timeModel.latestIndexedQuarter))}</span>` : ''}`}
        </div>` : ''}
      </div>
      ${body}`;
  }

  global.InsightsViz = {
    renderDecisionSummary,
    renderIdentityLine,
    renderActiveLensChips,
    renderExternalContext,
    renderConsensusDetail,
    renderEssentialInsights,
    renderResearchMemory,
    renderInsightsPanel,
    renderLetterDiscussants,
    renderTickerTrendBadges,
    renderInflections,
    filterInsights,
    attachFilingVerifyHandlers,
    attachEventHandlers,
    baseFilterEvents,
    filterEvents,
    diversifyEvents,
    attachConsensusHandlers,
    attachTickerInsightsHandlers,
    attachWorldModelHistoryHandlers,
    buildConsensusCsv,
    buildTimeModel,
    podcastEpisodeShardPath,
    STANCE_BADGE,
  };
})(window);
