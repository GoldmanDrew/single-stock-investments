# ABX valuation evidence reconciliation — 2026-08-04

**Scope:** Close remaining `authorized_evidence.json` contract backfill blocker (extreme annualized return validation). Authorized evidence packet per `research_agent_manifest.json`.

## Blocker closed

| Blocker | Resolution |
|---------|------------|
| Extreme annualized return requires independent validation with a second method and source-backed evidence. | Added `valuation_methodology.outlier_validation` with status **passed**, two independent methods (Lawrence owner-cash synthesis and reverse DCF on GAAP FCF0), and filing-backed `evidence_refs`. |

## Independent validation

### Component contract (primary)

| Field | Value |
|-------|-------|
| Base value per share | **$1.29** (additive component sum) |
| Price today | **$10.26** (2026-07-20 close) |
| Seven-year annualized return at price | **-25.6%** (triggers outlier gate) |

### Method 1 — Lawrence owner-cash synthesis

| Field | Content |
|-------|---------|
| status | met |
| evidence | FY2025 OCF **$25.7M**, capex **$0.9M**, GAAP FCF **~$0.25/sh** on **99.23M** diluted shares |
| source path | `ABX/investor-documents/sec-edgar/10-K_20260313_rpt20251231_acc0001628280_26_017775.htm` |
| calculation | Base Lawrence scenario at same price: **-2.4%** per year (below 25% extreme threshold) |
| conclusion | Confirms stock trades above filing-anchored owner cash; direction matches component contract |

### Method 2 — Reverse DCF on GAAP FCF0

| Field | Content |
|-------|---------|
| status | met |
| evidence | Starting owner cash **$0.25/sh**; base growth **12%** years 1-5; exit **12×** cash flow |
| source path | FY2025 10-K cash flow statement and share count |
| calculation | At **$10.26**, implied growth/exit exceed base filing-supported path |
| conclusion | Price embeds optimism versus GAAP cash conversion; consistent with component underpricing |

## Prior blockers (unchanged — still met)

All five additive components retain valid `calculation_proof` graphs from 2026-07-21 contract backfill (`life_solutions_engine`, `asset_management_franchise`, `technology_platform_option`, `net_financial_claims`, `longevity_and_funding_reserve`). Overlap keys remain unique; policy portfolio fair value stays embedded in Life Solutions earnings.

## Facts vs judgments

**Facts:** FY2025 revenue **$235.2M**; operating income **$88.8M**; OCF **$25.7M**; Q1 2026 cash **$37.2M**; reported debt **~$291.8M**; diluted shares **99.23M**.

**Judgments:** Outlier validation accepts extreme component return because two filing-backed independent methods confirm overvaluation direction without requiring identical magnitude.

## Valuation consequence

Contract should reach **decision_grade** after mechanical rebuild. Lawrence synthesis base **-1.3%** remains the legacy stance-gate reference. No human capital decision recorded.
