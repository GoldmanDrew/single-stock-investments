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
- Apply `quality_checklist.md`
- Apply `ai_disruption_lens.md` where relevant
- Write to `{TICKER}/research/` — not chat-only

## 5. Review loop
- Copy summary to `_system/reviews/pending/`
- Human discusses and corrects
- Promote approved items to `_system/memory/MEMORY.md`
- Move review to `_system/reviews/approved/`

## Output standards
Every report ends with:
- Thesis status: intact | weakening | strengthening | unclear
- [HUMAN REVIEW] items
- [PROPOSED MEMORY] bullets (daily log only)

Separate **facts**, **inferences**, and **opinions**. Cite file paths and page refs where possible.
