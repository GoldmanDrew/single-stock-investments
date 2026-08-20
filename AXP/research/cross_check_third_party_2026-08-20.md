# AXP — Cross-Check: Third-Party Sources

**Date:** 2026-08-20  
**Agent:** Marvin  
**Marvin dive:** `AXP/research/deep_dive_2026-08-20.md`  
**Source inventory:** `AXP/third-party-analyses/source_inventory_2026-08-02.md`  
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

No **approved** third-party sources are indexed for American Express as of this scan. Four **context-tier** activist SEC filings exist (SC-13D/SC-13G series); none are in base IRR. Marvin stance rests on **primary filings** (FY2025 10-K, Q2 2026 10-Q, 2026 proxy). Re-run `scan_third_party_sources.py AXP --with-hk` when Substacks, fund letters, or HK material is added.

**Synthesis:** Marvin floor only; no external blend.

## Sources in scope

| ID | Title | Path | Status | Use |
|----|-------|------|--------|-----|
| activist_long | American Express Company — SC 13D/A (Jan 2024) | `AXP/third-party-analyses/activist_reports/long/SC-13D/A_20240116_acc0000004962_24_000005.htm` | context | Long activist position disclosure |
| activist_long | American Express Company — SC 13D/A (Jul 2023) | `AXP/third-party-analyses/activist_reports/long/SC-13D/A_20230711_acc0001104659_23_079999.htm` | context | Long activist position disclosure |
| activist_long | American Express Company — SC 13D (Jun 2022) | `AXP/third-party-analyses/activist_reports/long/SC-13D_20220606_acc0001104659_22_068218.htm` | context | Initial activist filing |
| activist_short | Spruce Point (Mar 2021, unrelated ticker in index) | `_system/reference/activist-reports/spruce_point/...` | context | Inventory artifact; not AXP-specific |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| Revenue growth | FY2025 revenues net of interest expense **$72.2B** (+10%) | No approved external view | FY2025 10-K |
| Card fee momentum | Record **$10B** net card fees (+18%) | No approved external view | 2026 proxy |
| H1 2026 trend | Revenues net of interest **$38.5B** (+10.7% YoY) | No approved external view | Q2 2026 10-Q |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| Base annual return at **$351.93** | **2.3%** per year (contract base) | — | No external input |
| Stance | **watch** (below ~15% hurdle) | — | Filing-only |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | **$412.52** per share base intrinsic | **2.3%** per year / 7 years | watch |
| External (combined) | — | — | — |
| **Blended best estimate** | **$412.52** per share | **2.3%** per year | **watch** |

**Weights:** 100% Marvin primary filings; no approved external sources to blend.

**Returns statement (blended):** At **$351.93** per share, blended best estimate is **2.3%** per year over seven years on filing-based owner earnings reinvestment (no third-party adjustment).

## [HUMAN REVIEW]

- [ ] Every **approved** source reviewed against filings (none indexed)
- [ ] Every **pending** source cited with **[PENDING APPROVAL]** only
- [ ] Blended estimate in `valuation.json` → `estimates.external[]` if material third party added

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] AXP: third-party cross-check 2026-08-20; primary filings only; context activist SC-13D filings not in base IRR.

## Primary sources cited

1. `AXP/research/deep_dive_2026-08-20.md`
2. `AXP/research/evidence/filing_digest_2026-08-06.md`
3. `AXP/third-party-analyses/source_inventory_2026-08-02.md`
4. `investor-documents/sec-edgar/10-K_20260206_rpt20251231_acc0000004962_26_000080.htm`
5. `investor-documents/sec-edgar/10-Q_20260724_rpt20260630_acc0000004962_26_000322.htm`
