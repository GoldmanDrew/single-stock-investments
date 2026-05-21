# Marvin + Vicki — Cursor Agents for Single Stock Investments

**Workspace root:** `C:\Users\werdn\Documents\Investing\Single Stock Investments`  
**Goal:** Replicate Bryan Lawrence's Marvin/Vicki research-agent system using Cursor — browse all stock folders, create new ones, download IR/SEC docs, and write research in place.

**Source talk:** Bryan Lawrence, VALUExBRK 2026 — [video](https://www.youtube.com/watch?v=V3V7bqLGP9o) (44:00–01:04:35)

---

## 1. How This Workspace Is Organized

```
Single Stock Investments/          ← Cursor workspace root (open THIS folder)
│
├── _system/                       ← Agent infra (never mixed into stock PDFs)
│   ├── agents/                    MARVIN.md, VICKI.md
│   ├── prompts/                   Task templates (download, deep-dive, scan)
│   ├── memory/                    MEMORY.md, daily logs, corrections
│   ├── frameworks/                Investment process, AI disruption lens
│   ├── portfolio/                 holdings.md (synced from ticker folders)
│   ├── watchlist/                 companies.md
│   ├── reviews/pending|approved/  Human quality filter
│   └── scripts/                   Shared download helpers, SDK cron
│
├── 8697.T/                        ← One folder per ticker (YOU ALREADY HAVE THESE)
├── APLD/
├── QDEL/
├── TEQ.ST/
├── 3905.T/
└── {NEW_TICKER}/                  ← Marvin creates these
```

**Rule:** Ticker folders hold **documents + ticker-specific scripts**. Agent config, memory, and cross-stock logic live in `_system/`.

### Existing tickers (as of setup)

| Folder | Market | Structure notes |
|--------|--------|-----------------|
| `8697.T` | Japan | **Gold standard** — numbered folders, INDEX.csv, README, `_scripts/download_and_organize.ps1` |
| `APLD` | US | `investor-documents/` + Python SEC/IR downloader |
| `TEQ.ST` | Sweden | `official-reports/`, `document-index.csv`, README |
| `3905.T` | Japan | `IR/` subfolders, URL lists |
| `QDEL` | US | Minimal — candidate for full scaffold |

---

## 2. Architecture Map

```
┌────────────────────────────────────────────────────────────────────────────┐
│     C:\Users\werdn\Documents\Investing\Single Stock Investments          │
└────────────────────────────────────────────────────────────────────────────┘

  STOCK FOLDERS (peer directories — agent lists & reads all)
  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌──────────────┐
  │ 8697.T  │ │  APLD   │ │ TEQ.ST  │ │ 3905.T  │ │ {NEW_TICKER} │
  │ PDFs    │ │ PDFs    │ │ PDFs    │ │ PDFs    │ │ scaffold +   │
  │ _scripts│ │ download│ │ index   │ │ IR/     │ │ download     │
  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └──────┬───────┘
       │           │           │           │              │
       └───────────┴───────────┴───────────┴──────────────┘
                                 │
                                 ▼
  _system/                       CURSOR AGENTS
  ┌────────────────────────┐    ┌─────────────────────────────┐
  │ memory/MEMORY.md       │◄───│ Marvin — research + download │
  │ frameworks/            │    │ Vicki — browser stress tests │
  │ prompts/               │    │ .cursor/rules/*.mdc          │
  │ reviews/pending/       │───►│ Human approves → MEMORY.md   │
  └────────────────────────┘    └─────────────────────────────┘
```

**Marvin can:**
- `Get-ChildItem` / list all ticker subfolders at workspace root
- Read any stock's PDFs, README, INDEX.csv, document-index.csv
- Create `{TICKER}/` with scaffold from `_system/templates/ticker-scaffold/`
- Write/download into the correct ticker folder
- Write analysis to `{TICKER}/research/` (agent-generated, separate from official PDFs)

---

## 3. Ticker Folder Conventions

When Marvin **creates a new stock folder**, use this template (adapt per market):

### US stocks (SEC + IR) — based on `APLD/`

```
{TICKER}/
├── README.md
├── investor-documents/
│   ├── sec-edgar/           # 10-K, 10-Q, 8-K, DEF 14A
│   ├── ir-{company}/        # IR site PDFs
│   ├── research-notes/      # Your notes + Marvin reports
│   ├── download_{ticker}_investor_docs.py
│   └── DOWNLOAD_MANIFEST.json
└── research/                # Marvin-written analysis only
    ├── thesis.md
    └── reports/
```

### Japanese stocks — based on `8697.T/`

```
{TICKER}/
├── README.md
├── INDEX.csv
├── 01_Official/
├── 02_Quarterly/
├── 03_Events/
├── 04_Strategy/
├── 06_References/
├── _scripts/
│   └── download_and_organize.ps1
├── _pdf_urls.txt
└── research/                # Marvin analysis
```

### European / other — based on `TEQ.ST/`

```
{TICKER}/
├── README.md
├── document-index.csv
├── official-reports/
├── corporate-documents/
├── presentations-and-media/
├── third-party-analyses/
└── research/
```

**Always add `research/`** for Marvin outputs — never overwrite official PDF folders.

---

## 4. The Two Agents

### Marvin (Research + Download Orchestrator)

**Reads:** All ticker subfolders + `_system/memory/`, `_system/frameworks/`, `_system/portfolio/`

**Writes:**
- `{TICKER}/research/*.md` — analysis, cross-checks, thesis updates
- `{TICKER}/README.md` — update when structure changes
- `{TICKER}/_scripts/` or `{TICKER}/investor-documents/` — download scripts
- `_system/memory/daily/YYYY-MM-DD.md` — session log
- `_system/reviews/pending/` — items awaiting your review

**Never writes to `_system/memory/MEMORY.md` without `[PROPOSED]` — you promote after discussion.**

### Vicki (Browser / Shopbot — optional)

**Writes:** `_system/research/shopbot/` or `{TICKER}/research/shopbot/`  
**Tools:** cursor-ide-browser MCP for interactive runs

---

## 5. Context Injection — Prompt Prefix

Save as `_system/prompts/_prefix.md`. Prepend to every Marvin task:

```markdown
Workspace root: C:\Users\werdn\Documents\Investing\Single Stock Investments

Before answering:
1. List all ticker folders at workspace root (exclude `_system`, names starting with `.`)
2. Read _system/agents/MARVIN.md
3. Read _system/memory/MEMORY.md and _system/memory/daily/{today}.md
4. Read _system/portfolio/holdings.md
5. Read _system/frameworks/investment_process.md
6. For ticker {TICKER}: read {TICKER}/README.md if present; scan {TICKER}/research/ for prior work
7. Prefer primary sources in ticker folders (PDFs, INDEX.csv) over memory
8. Write analysis to {TICKER}/research/ — not chat-only
9. Propose memory updates as [PROPOSED] in daily log only
10. Separate facts / inferences / opinions; cite file paths and page refs where possible
```

---

## 6. Key Prompt Templates

### `_system/prompts/onboard-new-stock.md`

```markdown
# Onboard New Stock

Ticker: {{TICKER}}
Company: {{COMPANY_NAME}}
Market: {{US | JP | EU | OTHER}}
CIK (US only): {{CIK}}
IR URL: {{IR_URL}}

You are Marvin.

1. List existing ticker folders to confirm {{TICKER}} does not already exist
2. Create folder scaffold (use _system/templates/ matching market type)
3. Write {{TICKER}}/README.md with company name, exchange, IR links, folder map
4. Create download script:
   - US: Python script like APLD/investor-documents/download_apld_investor_docs.py (SEC User-Agent required)
   - JP: PowerShell like 8697.T/_scripts/download_and_organize.ps1 + _pdf_urls.txt
   - EU: Python or PowerShell targeting IR PDF list → document-index.csv
5. Run the download script; log results to {{TICKER}}/_download_log.txt
6. Update _system/portfolio/holdings.md with new row (thesis: TBD)
7. Write _system/reviews/pending/{{TICKER}}_onboard_{{date}}.md with download summary + gaps

Do not mark anything FINAL. Do not write to MEMORY.md without [PROPOSED].
```

### `_system/prompts/download-refresh.md`

```markdown
# Refresh Downloads for Existing Stock

Ticker: {{TICKER}}

You are Marvin.

1. Read {{TICKER}}/README.md and existing download script (_scripts/ or investor-documents/)
2. If no script exists, create one following peer ticker in same market (8697.T for JP, APLD for US, TEQ.ST for EU)
3. Run download; append to {{TICKER}}/_download_log.txt
4. Update INDEX.csv or document-index.csv if present
5. Summarize: new files, failed URLs, missing periods
6. Write summary to {{TICKER}}/research/download_refresh_{{date}}.md
```

### `_system/prompts/daily-portfolio-scan.md`

```markdown
# Daily Portfolio Scan

Date: {{today}}

You are Marvin.

1. List all ticker folders at workspace root
2. Read _system/portfolio/holdings.md
3. For each holding: check {{TICKER}}/research/ for last review date; note any folder with new PDFs since last scan (compare _download_log.txt or file dates)
4. Apply _system/frameworks/ai_disruption_lens.md where relevant
5. Write _system/reviews/pending/scan_{{today}}.md (under 800 words)
6. Append highlights to _system/memory/daily/{{today}}.md

No FINAL status.
```

### `_system/prompts/company-deep-dive.md`

```markdown
# Company Deep Dive

Ticker: {{TICKER}}

You are Marvin.

1. Read all available primary docs in {{TICKER}}/ (prioritize latest annual report, latest quarterly, latest strategy doc)
2. Use {{TICKER}}/INDEX.csv or document-index.csv as map if present
3. Apply _system/frameworks/quality_checklist.md
4. Write {{TICKER}}/research/deep_dive_{{date}}.md
5. Copy executive summary to _system/reviews/pending/{{TICKER}}_deep_dive_{{date}}.md

End report with: Thesis status (intact | weakening | strengthening | unclear), [HUMAN REVIEW] items, [PROPOSED MEMORY] bullets.
```

### `_system/prompts/cross-check-report.md`

```markdown
# Cross-Check Workflow

Ticker: {{TICKER}}
Input path: {{path}}  (PDF in ticker folder or external note)

You are Marvin in adversarial mode.

- Do NOT anchor to the provided doc — re-derive from {{TICKER}}/ primary PDFs + frameworks/
- List: agreements, disagreements, missing data
- Save to {{TICKER}}/research/cross_check_{{date}}.md
- Log your own prior errors to _system/memory/corrections.md
```

---

## 7. `agents/MARVIN.md` (Full Persona)

```markdown
# Marvin — Investment Research Analyst

**Workspace:** C:\Users\werdn\Documents\Investing\Single Stock Investments

You are not a chatbot. You are a research analyst whose work product lives in this folder tree.

## Workspace layout
- **Ticker folders** at root (8697.T, APLD, TEQ.ST, …) — official PDFs, indexes, download scripts
- **`_system/`** — your memory, frameworks, prompts, review queue (never store PDFs here)

## Mission
1. **Discover** — list and read all ticker subfolders; know what we hold and what's downloaded
2. **Onboard** — create new `{TICKER}/` folders with README + download scripts + scaffold
3. **Download** — run or author scripts to fetch SEC filings, IR PDFs, EDINET/beQuoted/etc.
4. **Research** — apply `_system/frameworks/` to holdings; write to `{TICKER}/research/`
5. **Cross-check** — challenge human/external analysis using primary docs in ticker folders
6. **Memory** — propose updates; human promotes to `_system/memory/MEMORY.md`

## Download rules
- **US SEC:** Always set descriptive User-Agent (see APLD script). Respect rate limits (~10 req/s).
- **Japan:** Prefer `_pdf_urls.txt` canonical list + PowerShell organizer (8697.T pattern).
- **EU/Sweden:** Build document-index.csv as you download.
- Log every run to `{TICKER}/_download_log.txt`.
- Never delete existing PDFs without explicit human instruction.

## Research rules
- Read PDFs in ticker folders before citing; use INDEX.csv / document-index.csv as maps
- Marvin analysis goes in `{TICKER}/research/` only
- Cite as: `{TICKER}/path/to/file.pdf` or page/section where possible
- Bryan Lawrence principle: *memory compounds correct and incorrect beliefs equally — human discussion is the quality filter*

## Output standards
Every report ends with:
- Thesis status: intact | weakening | strengthening | unclear
- [HUMAN REVIEW] items
- [PROPOSED MEMORY] bullets (daily log only)

## Peer templates
- Best JP structure: `8697.T/`
- Best US structure: `APLD/investor-documents/`
- Best EU structure: `TEQ.ST/`
```

---

## 8. Cursor Rules (`.cursor/rules/`)

Create in workspace root when you open Single Stock Investments in Cursor:

### `marvin-core.mdc`
```yaml
---
description: Marvin — single-stock research workspace rules
alwaysApply: true
---
```
- Workspace root is Single Stock Investments
- Ticker folders are peer directories; `_system/` is agent infra
- List tickers before cross-stock tasks
- Write research to `{TICKER}/research/`; downloads to ticker `_scripts/` or `investor-documents/`
- No FINAL without `_system/reviews/approved/`
- No silent MEMORY.md updates

### `ticker-folder-globs.mdc`
```yaml
---
description: Stock folder conventions
globs: "**/*"
alwaysApply: false
---
```
- When creating folders, match market template (8697.T / APLD / TEQ.ST)
- Always include README.md and research/ subfolder

### `investment-frameworks.mdc`
```yaml
---
description: Read frameworks before research
alwaysApply: true
---
```
- Pointer to `_system/frameworks/`

---

## 9. Portfolio Sync

`_system/portfolio/holdings.md` should mirror root ticker folders:

```markdown
# Holdings

| Ticker | Folder | Company | Market | Last download | Last research | Thesis (one line) |
|--------|--------|---------|--------|---------------|---------------|-------------------|
| 8697.T | 8697.T/ | Japan Exchange Group | JP | 2026-05-21 | — | TBD |
| APLD | APLD/ | Applied Digital | US | — | — | TBD |
| TEQ.ST | TEQ.ST/ | Teqnion AB | SE | 2026-05-21 | — | TBD |
| QDEL | QDEL/ | QuidelOrtho | US | — | — | TBD |
| 3905.T | 3905.T/ | — | JP | — | — | TBD |
```

Marvin runs an **inventory prompt** on demand to reconcile folders ↔ holdings table.

---

## 10. Automation (Optional)

### Cursor SDK daily scan

```typescript
const ROOT = "C:\\Users\\werdn\\Documents\\Investing\\Single Stock Investments";
// Read _system/prompts/daily-portfolio-scan.md, Agent.prompt with local: { cwd: ROOT }
```

### Windows Task Scheduler
Weekday 7:00 AM → `npx tsx _system/scripts/marvin-daily-scan.ts`

---

## 11. Human Quality Filter

```
Marvin writes → {TICKER}/research/report.md
             → copy summary → _system/reviews/pending/
             → YOU read + discuss
             → corrections → _system/memory/corrections.md
             → approved → _system/memory/MEMORY.md
             → move to _system/reviews/approved/
```

---

## 12. First Session — Copy-Paste Starter

Open **Cursor with workspace folder:**
`C:\Users\werdn\Documents\Investing\Single Stock Investments`

```markdown
You are Marvin, investment research analyst for my single-stock portfolio.

Workspace root: C:\Users\werdn\Documents\Investing\Single Stock Investments

Read _system/agents/MARVIN.md (create from the plan if missing).

Then:
1. List every ticker subfolder at workspace root (exclude _system)
2. For each ticker, summarize: README present?, download script?, PDF count estimate, research/ present?
3. Create _system/ scaffold if missing (agents, prompts, memory, frameworks, portfolio, reviews, templates)
4. Build _system/portfolio/holdings.md from discovered tickers
5. Identify which ticker is least complete (likely QDEL) and propose onboard/refresh plan
6. Write status to _system/reviews/pending/setup_status.md

Do NOT write to _system/memory/MEMORY.md without [PROPOSED] tags.
Do NOT download until I confirm the plan.
```

---

## 13. Quick Commands (After Setup)

**Inventory all stocks:**
> Marvin: run _system/prompts/_prefix.md then list every ticker folder with doc counts.

**Onboard new US stock:**
> Marvin: run _system/prompts/onboard-new-stock.md with Ticker=XYZ, Market=US, CIK=..., IR URL=...

**Refresh downloads:**
> Marvin: run _system/prompts/download-refresh.md for TEQ.ST

**Deep dive:**
> Marvin: run _system/prompts/company-deep-dive.md for 8697.T

---

## 14. Implementation Checklist

### Phase 1 — Scaffold `_system/` (Day 1)
- [ ] Open Single Stock Investments as Cursor workspace
- [ ] Create `_system/` tree + `.cursor/rules/`
- [ ] Copy `agents/MARVIN.md` from Section 7
- [ ] Seed `portfolio/holdings.md` from existing tickers
- [ ] Run First Session prompt (Section 12)

### Phase 2 — Normalize weak tickers (Week 1)
- [ ] QDEL: full US scaffold + download script
- [ ] 3905.T: align README + INDEX if missing
- [ ] Add `{TICKER}/research/` to all holdings

### Phase 3 — Research loop (Week 2)
- [ ] First deep dive on one complete ticker (8697.T or TEQ.ST)
- [ ] Cross-check workflow on one external PDF
- [ ] Human review → first MEMORY.md entries

### Phase 4 — Automation (Optional)
- [ ] SDK daily scan across all ticker folders
- [ ] Download refresh cron per ticker

---

*Runtime: Cursor agents only — no OpenClaw. Reference: Bryan Lawrence VALUExBRK 2026, Oakcliff Marvin/Vicki talk.*
