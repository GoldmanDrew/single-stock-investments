---
filing: pass
consistency: pass
disclosure: pass
short: litigation
third_party: pass
block_final: false
blocking_issues: []
re_pass: true
---

# QDEL — Adversarial review

**Date:** 2026-05-28  
**Agent:** Milly  
**Dive reviewed:** `QDEL/research/deep_dive_2026-05-28.md`  
**Valuation reviewed:** `QDEL/research/valuation.json`  
**Filings used:** `10-K_20260219_rpt20251228_acc0001906324_26_000008.htm`, `10-Q_20260506_rpt20260329_acc0001906324_26_000024.htm`

**Goal:** Truth-seeking QA.

---

## Summary verdict

| Area | Status | One line |
|------|--------|----------|
| Filing reconciliation | **pass** | FY25 and Q1 FY26 headline numbers match extracts |
| Internal consistency | **fail** | Returns statement **~11%** vs base IRR **18%** (blocks “final”) |
| Short activist scan | **no Tier-1 forensic** | 2024 class actions / channel-stuffing theme; dive covers turnaround |

**Overall:** Filings match. **Fix returns statement** before dive is final. McIntyre blend appropriately labeled as judgment.

---

## Filing reconciliation

| # | Claim in dive | Filing value | Match? | Severity |
|---|---------------|--------------|--------|----------|
| 1 | FY2025 revenue **$2,730.2M** | `Revenues: 2,730.2` | **Yes** | — |
| 2 | Stockholders' equity **$1,920.5M** | `StockholdersEquity: 1,920.5` | **Yes** | — |
| 3 | Q1 FY26 revenue **$619.8M** | `Revenues: 619.8` (current Q) | **Yes** | — |
| 4 | Prior-year Q revenue **$692.8M** | `Revenues: 692.8` (prior Q in pair) | **Yes** | — |
| 5 | YoY Q1 **-10.5%** | (619.8−692.8)/692.8 = **-10.5%** | **Yes** | — |
| 6 | LT debt **$2,471.9M** | Per 10-K extract (dive cites) | **Yes** | — |
| 7 | Adj. EBITDA **21.9%** margin | IR presentation (not XBRL line) | **Inference** | cite deck path |

---

## Internal consistency

| Check | Expected | Found | OK? |
|-------|----------|-------|-----|
| Executive summary base IRR | **18%** | **18%** | Yes |
| Classification IRR | **18.0%** | **18.0%** | Yes |
| `valuation.json` blended return | **18.0** | **18.0** | Yes |
| **Returns statement** | **18%** (must match base) | **~11%** | **NO — factual error** |
| Mental models “~17%” | ~18% | **17%** | Minor typo |
| Stance | **hold** | **hold** | Yes |

**Blocking issue:** End **Returns statement** still uses old Marvin-floor language (~11%) while executive summary and valuation use **blended 18%**.

---

## Short activist scan

| Firm | Report? | Date | Reconciliation |
|------|-----------|------|----------------|
| Muddy Waters / Hindenburg / Kerrisdale / Spruce Point | **No** dedicated forensic report found | — | — |
| **Securities class actions** | Allegations (not short firms) | **2024** | Channel-stuffing / COVID inventory; **partially addressed** in “Why market wrong” and pillars |
| McIntyre letter | External long (approved) | **2026** | Properly triangulated, not filing fact |

**Verdict:** No current Tier-1 short to reconcile. **2024 litigation risk** remains in background; dive should keep **[HUMAN REVIEW]** on covenant headroom (already present).

---

## Recommended actions

1. ~~**Marvin (required):** Returns statement IRR~~ — **done** (2026-05-28).
2. ~~Mental models ~17% → ~18%~~ — **done**.
3. **Human:** McIntyre **$4/sh 2028** remains unproven — keep 45% weight discipline.

---

## Resolved in dive

- **Returns statement** and **Classification** aligned to **18.0%** blended IRR (`deep_dive_2026-05-28.md`).
- **Mental models** triangulation line updated to **~18%**.

---

## [HUMAN REVIEW]

- Debt covenant detail still open (already in dive)
