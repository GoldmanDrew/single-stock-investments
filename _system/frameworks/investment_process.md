# Investment Process

Single-stock research workflow for this workspace.

## 1. Discover
- List all ticker folders at workspace root
- Read README, INDEX.csv, or document-index.csv per holding
- Check `_download_log.txt` for freshness
- **New / watchlist names:** `idea_funnel.md` gate before full deep dive (see `analysis_arsenal.md`)
- Read the valuation-universe assignment. Tier 1 receives active underwriting, Tier 2 receives curated follow-up, and Tier 3 receives screening only until a promotion gate is met.

## 2. Download
- Run or author market-appropriate download scripts
- Log every run; never delete existing PDFs without explicit instruction

## 3. Read primary sources
- Latest annual report
- Latest quarterly / interim report
- Latest strategy or investor presentation
- Proxy / governance docs for US holdings

## 4. Analyze
- Apply `_system/frameworks/decision_stack.md` (six orthogonal questions)
- Triggered tools from `_system/frameworks/analysis_arsenal.md` only when payoff lens or archetype requires
- Write prose per `_system/frameworks/report_prose.md` (Hohn/HK voice; spell out mental models; no em dashes)
- Archetype second-pass prompts from `archetype_models.json`; appendix detail in `mental_models.md` / `lawrence_irr.md` only if needed
- Apply `ai_disruption_lens.md` where relevant
- Write to `{TICKER}/research/` — not chat-only
- Valuation authority: `valuation_route.json` → `valuation_contract.json` → `valuation_workbench.json` via `run_security_decision_pipeline.py`. `valuation.json` is an input/legacy envelope, not the final decision.
- Contract v3 records the proof's `output_basis`. `present_value_today` publishes value and margin of safety but no forward return; only a dated payoff or cash-flow schedule can publish a forward return or hurdle entry price.
- Keep proof status, model level, and universe tier separate. A proof-complete generic screen remains `screening_grade`, regardless of its tier.

## 5. Review loop
- Freeze a decision-grade evidence packet only after all critical acceptance tests close and the model is stock-specific.
- Run three isolated Power Zone committee reviewers plus an outside pre-mortem.
- Preserve dissent and route the recommendation to `human_decision.json`; agents never size capital.
- Copy summary to `_system/reviews/pending/`
- Human discusses and corrects
- Promote approved items to `_system/memory/MEMORY.md`
- Move review to `_system/reviews/approved/`

## Output standards
Every report ends with:
- **Classification** table (archetype, moat, dhando, stance, cycle, intrinsic value/margin of safety, forward return when available, model level, universe tier, method) — see `_system/frameworks/classification.md`
- [HUMAN REVIEW] items
- [PROPOSED MEMORY] bullets (daily log only)

Sync: `python _system/scripts/sync_classification.py` · Lint: `python _system/scripts/lint_deep_dive.py {TICKER}` (`--legacy` until dive refreshed to new template)

Separate **facts**, **inferences**, and **opinions**. Cite file paths and page refs where possible.

## 6. Daily automation (GitHub Actions)

| Step | Workflow | Behavior |
|------|----------|----------|
| Download | `daily-sync.yml` job `download-and-sync` | 12:00 UTC — pull SEC/IR for all holdings, rebuild INDEX + dashboard JSON, push |
| News | `daily-sync.yml` job `portfolio-news` or `portfolio-news.yml` | Polygon bulk + Google News RSS → `dashboard/data/portfolio_news.json`; review `_system/reviews/pending/news_{date}.md` |
| Refresh analysis | `research-agent-dispatch.yml` | Build a compact manifest and admit at most one changed ticker; unchanged/duplicate/cooldown/budget cases skip Cursor |
| Manual refresh | `marvin-deep-dive.yml` | Compatibility UI routed through the same gate; force is an audited incident override, not rotation |

Picker: `_system/scripts/marvin_pick_ticker.py --json` · Manifest: `_system/scripts/build_research_agent_manifest.py` · Policy: `_system/config/llm_usage_policy.json` · News ingest: `_system/scripts/ingest_portfolio_news.py`
