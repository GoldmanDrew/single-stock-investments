# DD — Cross-Check: Third-Party Sources

**Date:** 2026-08-09
**Agent:** Marvin
**Marvin dive:** `DD/research/deep_dive_2026-08-09.md`
**Source inventory:** `DD/third-party-analyses/source_inventory_2026-07-10.md` (no new scan artifacts in evidence packet)
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

No approved third-party sources are indexed for DuPont as of this refresh. Marvin stance rests on **primary filings only** (FY2025 10-K, Q1 2026 10-Q). Legacy 2018 DowDuPont activist 13D filings remain **context tier** only and do not enter base IRR.

**Synthesis:** Marvin floor only; no external blend.

## Sources in scope

| Source | Type | Date | Approval | Use |
|--------|------|------|----------|-----|
| Primary SEC filings | 10-K / 10-Q | 2026-02-17 / 2026-05-05 | primary | Base IRR inputs |
| SC-13D/A (Third Point et al.) | Activist | 2018 | **[PENDING APPROVAL]** / context | Historical DowDuPont governance only |
| HK / Substack | — | — | n/a | Not indexed |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| FY2025 net sales | **$6.85B** | No approved external | `10-K_20260217` |
| Total debt (FY2025) | **~$3.19B** | No approved external | `10-K_20260217` |
| Two-segment structure | Healthcare & Water; Diversified Industrials | No approved external | `10-K_20260217` |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| — | — | — | No approved external views to reconcile |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | **~$4.14/sh** base proof | **-39.7%** per year at **$142.47** | watch |
| External (combined) | — | — | — |
| **Blended best estimate** | **~$4.14/sh** | **-39.7%** per year | **watch** |

**Weights:** 100% Marvin floor (no approved external inputs).

**Returns statement (blended):** At **$142.47**, blended best estimate is **-39.7%** per year on filing-normalized owner earnings; pending sources not in base IRR.

## [HUMAN REVIEW]

- [ ] Re-run `scan_third_party_sources.py DD --with-hk --date 2026-08-09` when third-party inventory expands beyond 2018 activist stubs.
- [ ] Every **pending** source cited with **[PENDING APPROVAL]** only.

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] DD: contract backfill 2026-08-09 closed stale-debt blocker (LongTermDebt 2024 tag → LT+current **$3.17B**); base proof **$4.14/sh** vs price **$142.47**; watch.

## Primary sources cited

1. `DD/investor-documents/sec-edgar/10-K_20260217_rpt20251231_acc0001666700_26_000013.htm`
2. `DD/investor-documents/sec-edgar/10-Q_20260505_rpt20260331_acc0001666700_26_000031.htm`
3. `DD/research/evidence_reconciliation_2026-08-09.md`
