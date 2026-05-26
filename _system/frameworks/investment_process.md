# Investment Process

Single-stock research workflow for this workspace.

## 1. Discover
- List all ticker folders at workspace root
- Read README, INDEX.csv, or document-index.csv per holding
- Check `_download_log.txt` for freshness

## 2. Download
- Run or author market-appropriate download scripts
- Log every run; never delete existing PDFs without explicit instruction

## 3. Read primary sources
- Latest annual report
- Latest quarterly / interim report
- Latest strategy or investor presentation
- Proxy / governance docs for US holdings

## 4. Analyze
- Apply `_system/frameworks/decision_stack.md` (single pipeline: what → durable → payoff → return → stance)
- Write prose per `_system/frameworks/report_prose.md` (Hohn/HK voice; spell out mental models; no em dashes)
- Tier 2 prompts from `archetype_models.json`; appendix detail in `mental_models.md` / `lawrence_irr.md` only if needed
- Apply `ai_disruption_lens.md` where relevant
- Write to `{TICKER}/research/` — not chat-only
- Valuation: `{TICKER}/research/valuation.json` + `marvin_valuation.py --write`

## 5. Review loop
- Copy summary to `_system/reviews/pending/`
- Human discusses and corrects
- Promote approved items to `_system/memory/MEMORY.md`
- Move review to `_system/reviews/approved/`

## Output standards
Every report ends with:
- **Classification** table (archetype, moat, dhando, stance, cycle, implied_irr, irr_method, lawrence_bucket) — see `_system/frameworks/classification.md`
- [HUMAN REVIEW] items
- [PROPOSED MEMORY] bullets (daily log only)

Sync: `python _system/scripts/sync_classification.py` · Lint: `python _system/scripts/lint_deep_dive.py {TICKER}` (`--legacy` until dive refreshed to new template)

Separate **facts**, **inferences**, and **opinions**. Cite file paths and page refs where possible.

## 6. Daily automation (GitHub Actions)

| Step | Workflow | Behavior |
|------|----------|----------|
| Download | `daily-sync.yml` job `download-and-sync` | 12:00 UTC — pull SEC/IR for all holdings, rebuild INDEX + dashboard JSON, push |
| News | `daily-sync.yml` job `portfolio-news` or `portfolio-news.yml` | Polygon bulk + Google News RSS → `dashboard/data/portfolio_news.json`; review `_system/reviews/pending/news_{date}.md` |
| Refresh analysis | `daily-sync.yml` job `marvin-refresh` | After news — pick ticker with **new primary documents or refresh-eligible valuation news** since last deep dive; skip if caught up; Cursor cloud agent opens PR |
| Manual refresh | `marvin-daily-deep-dive.yml` | Optional ticker; **force_rotate** if you want oldest dive refreshed without new activity |

Picker: `_system/scripts/marvin_pick_ticker.py --json` · News ingest: `_system/scripts/ingest_portfolio_news.py`
