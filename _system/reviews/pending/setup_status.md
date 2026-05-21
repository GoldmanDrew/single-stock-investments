# Setup Status — First Session

**Date:** 2026-05-21  
**Agent:** Marvin  
**Status:** Scaffold complete — awaiting human confirmation before downloads

---

## 1. Ticker inventory

Five ticker folders at workspace root (excluding `_system`):

| Ticker | README | Download script | PDF count (est.) | research/ | Notes |
|--------|--------|-----------------|------------------|-----------|-------|
| **8697.T** | Yes | Yes — `_scripts/download_and_organize.ps1` | 399 | No | Gold standard JP layout; INDEX.csv; last download 2026-05-21 |
| **3905.T** | No | No — only `IR/en_financial_report_urls.txt` | 505 | No | PDFs in `IR/` subfolders; no README, INDEX, or organizer script |
| **APLD** | No | Yes — `investor-documents/download_apld_investor_docs.py` | 3 PDF + ~55 SEC HTML | No | SEC filings downloaded; duplicate research PDF at root |
| **QDEL** | No | No | 1 | No | Single third-party letter only (`McIntyre_Partnerships_Q1_2026_Letter.pdf`) |
| **TEQ.ST** | Yes | No | 41 | No | document-index.csv; organized EU layout; PDFs present |

**None of the five holdings have a `research/` folder yet.**

---

## 2. `_system/` scaffold

Created on 2026-05-21:

| Path | Status |
|------|--------|
| `_system/agents/MARVIN.md` | Created |
| `_system/agents/VICKI.md` | Created |
| `_system/prompts/` | Created (prefix, onboard, download-refresh, daily scan, deep-dive, cross-check) |
| `_system/memory/MEMORY.md` | Created (empty — human promotion only) |
| `_system/memory/corrections.md` | Created |
| `_system/memory/daily/` | Created (empty) |
| `_system/frameworks/` | Created (investment_process, ai_disruption_lens, quality_checklist) |
| `_system/portfolio/holdings.md` | Created |
| `_system/watchlist/companies.md` | Created |
| `_system/reviews/pending/` | Created |
| `_system/reviews/approved/` | Created |
| `_system/templates/ticker-scaffold/` | Created |

**Not written:** `_system/memory/MEMORY.md` content beyond empty scaffold (per instructions).

---

## 3. Least complete holding: QDEL

**QuidelOrtho (QDEL)** ranks last on every infrastructure dimension:

- No README or folder map
- No download script
- No SEC or IR primary documents
- No INDEX or manifest
- No `research/` folder
- Only asset: third-party commentary PDF (not primary source)

**3905.T** is second-weakest on *structure* (no README, no script, no INDEX) despite having 505 PDFs. **APLD** has tooling but lacks README and `research/`. **TEQ.ST** lacks a download script. **8697.T** is the reference implementation.

---

## 4. Proposed plan — QDEL onboard (awaiting confirmation)

**Do not execute until you confirm.**

### Phase A — Scaffold (no network)
1. Create US template structure under `QDEL/`:
   - `README.md` — company name, exchange (NASDAQ), CIK, IR URL, folder map
   - `investor-documents/sec-edgar/`, `ir-quidelortho/`, `research-notes/`
   - Move existing `McIntyre_Partnerships_Q1_2026_Letter.pdf` → `investor-documents/research-notes/`
   - Create empty `research/thesis.md` and `research/reports/`
2. Author `investor-documents/download_qdel_investor_docs.py` modeled on `APLD/investor-documents/download_apld_investor_docs.py`
   - SEC EDGAR: 10-K, 10-Q, 8-K, DEF 14A (CIK TBD — likely post-Quidel/Ortho merger entity)
   - IR site: earnings releases, investor presentations, annual reports

### Phase B — Download (requires confirmation)
3. Run download script; log to `QDEL/_download_log.txt`
4. Write `DOWNLOAD_MANIFEST.json`
5. Update `_system/portfolio/holdings.md` (Last download date)
6. Write `_system/reviews/pending/QDEL_onboard_2026-05-21.md` with summary + gaps

### Phase C — Optional follow-ups (separate confirmation)
- Add `research/` to all five tickers
- **3905.T:** README + INDEX.csv + PowerShell organizer (8697.T pattern)
- **APLD:** README + move root PDF into `investor-documents/research-notes/`
- **TEQ.ST:** download refresh script for beQuoted

---

## 5. Recommended next command

After you approve the QDEL plan:

> Marvin: run _system/prompts/onboard-new-stock.md with Ticker=QDEL, Company=QuidelOrtho, Market=US, CIK=[confirm], IR URL=[confirm]

Or approve Phase B only if scaffold already exists.

---

## Thesis status

**unclear** — no primary research completed for any holding.

## [HUMAN REVIEW]
- Confirm QDEL CIK and IR URL before download
- Confirm whether to proceed with QDEL only or batch-normalize all tickers (add `research/` everywhere)
- Confirm company name for 3905.T (DataSection Co., Ltd. inferred from IR URLs)

## [PROPOSED MEMORY]
*(none — logged here per daily-log convention; not written to MEMORY.md)*

- [PROPOSED] Portfolio holds 5 tickers: 8697.T, 3905.T, APLD, QDEL, TEQ.ST
- [PROPOSED] 8697.T is the JP reference structure; TEQ.ST is the EU reference; APLD is the US download reference
- [PROPOSED] QDEL is least complete and priority for onboard

---

*No downloads executed. Awaiting human confirmation.*
