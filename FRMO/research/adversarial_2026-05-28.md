---
filing: pass
consistency: pass
disclosure: hit
short: no_hit
third_party: n/a
block_final: false
blocking_issues: []
re_pass: false
---

# FRMO — Adversarial review

**Date:** 2026-05-28  
**Agent:** Milly  
**Dive reviewed:** `FRMO/research/deep_dive_2026-05-28.md`  
**Valuation reviewed:** `FRMO/research/valuation.json`  
**Filings used:** `investor-documents/ir-frmo/2026-02-28_Quarterly_Report.pdf`

**Goal:** Truth-seeking QA.

---

## Summary verdict

| Area | Status | One line |
|------|--------|----------|
| Filing reconciliation | **pass** | Assets, equity, book/sh, MIH, HKHC match Feb 2026 quarterly |
| Internal consistency | **pass** | **21.9%** base IRR consistent across exec, JSON, IRR block |
| Short activist scan | **no hit** | No Muddy/Hindenburg report; **Jan 2026 tax restatement** under-discussed |

**Overall:** Core numbers are filing-grounded. SOTP uplift lines are **labeled assumptions** (appropriate). Add **tax restatement / non-reliance** to Risks before calling dive final.

---

## Filing reconciliation

| # | Claim in dive | Filing value | Match? | Severity |
|---|---------------|--------------|--------|----------|
| 1 | Total assets **$919.5M** | `Total assets $ 919,482` | **Yes** | — |
| 2 | FRMO equity **$376.7M** | `Stockholders' equity attributable to the Company 376,704` | **Yes** | — |
| 3 | Book **~$8.55/sh** | $376,704 ÷ 44,022,781 ≈ **$8.55** | **Yes** | — |
| 4 | Shares **44,022,781** | Filing share count | **Yes** | — |
| 5 | MIH fair value **$13.9M** | Note 4 / exchanges line | **Yes** | — |
| 6 | HKHC investment **$27.2M** | `Investment in HKHC 27,187` | **Yes** | — |
| 7 | Royalty **$10.2M** | `royalty participation 10,200` | **Yes** | — |
| 8 | Q3 NI to FRMO **$83.4M** | Press release / quarterly (dive cites) | **Yes** | — |
| 9 | Investment A **~82%** of equity | `308,984 / 376,704` ≈ **82.0%** | **Yes** | — |
| 10 | Payoff **$18** / **21.9%** IRR | Model (`valuation.json`) | **N/A** | assumption-led SOTP |

---

## Internal consistency

| Check | Expected | Found | OK? |
|-------|----------|-------|-----|
| Base IRR exec | **21.9%** | **21.9%** | Yes |
| Returns statement | **21.9%** | **21.9%** | Yes |
| `valuation.json` primary_return | **21.9** | **21.9** | Yes |
| SOTP sum | **$18.00** | 8.55 + uplifts = 18.00 in Step 3d | Yes |
| Stance | **accumulate** | **accumulate** | Yes |

**Inference risk (expected):** Investment A **+4.50/sh** and HKHC **+2.00/sh** are judgment; ledger documents tie-out **+$0.44** — honest.

---

## Short activist scan

| Firm | Report? | Date | Reconciliation |
|------|-----------|------|----------------|
| Muddy Waters / Hindenburg / Kerrisdale / Spruce Point / Iceberg | **No** | — | OTC holdco rarely targeted |
| **Company event** | **Non-reliance on prior financials** | **Jan 15, 2026** | Tax / deferred tax restatement; **under-addressed in dive** |

**Verdict:** No public forensic short. **Jan 2026** announcement that prior annual and interim statements should **no longer be relied upon** (deferred tax) is material for OTC disclosure quality. Dive mentions **late filing** (Nov 2025) but **not** the Jan 2026 **non-reliance** press release.

---

## Recommended actions

1. **Marvin:** Add **Primary risk** bullet: Jan 2026 **non-reliance** on prior statements (deferred tax); link Nasdaq/ACCESS release; note cash NI pre-tax unchanged per company.
2. **Human:** Investment A look-through table still **[HUMAN REVIEW]** (correct).
3. **Human:** Murray Stahl death (Apr 2026) — governance follow-through on calls (dive context elsewhere).

---

## [HUMAN REVIEW]

- Tax restatement / non-reliance Jan 2026
- Full SOTP line-by-line vs filed look-through (when available)
