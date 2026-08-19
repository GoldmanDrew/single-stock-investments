# AMR — Cross-Check: Third-Party Sources

**Date:** 2026-08-19  
**Agent:** Marvin  
**Marvin dive:** `AMR/research/deep_dive_2026-08-19.md`  
**Source inventory:** `AMR/third-party-analyses/source_inventory_2026-08-06.md`  
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

No approved third-party sources are indexed for AMR as of this refresh. Marvin stance rests on **primary filings only** (FY2025 10-K, Q2 2026 10-Q, DOWNLOAD_MANIFEST). Re-run `scan_third_party_sources.py AMR --with-hk --date 2026-08-19` when Substacks, fund letters, or HK material is added.

**Synthesis:** Marvin floor only; no external blend.

## Sources in scope

| Source | Type | Status | Role |
|--------|------|--------|------|
| Primary SEC filings | 10-K, 10-Q, 8-K, proxy | Approved (primary) | Base economics and capital allocation |
| Third-party analyses | — | None indexed | n/a |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| Cycle collapse post-2022 | Revenue fell from $4.10B (2022) to $2.13B (2025); OCF from $1.48B to $145M | n/a | 10-K series |
| Aggressive buybacks | $1.14B repurchases FY2025 while net loss $62M | n/a | FY2025 10-K cash flow |
| Reserve base | 294.5M tons reserves; 13.7M tons met shipped FY2025 | n/a | FY2025 10-K Item 1 |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| — | — | — | No external view to blend |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor (filings) | ~$63/sh component base | Sub-15% at ~$153 price | watch |
| External (combined) | — | — | — |
| **Blended best estimate** | **~$63/sh** | **Negative low-teens % at price (contract path)** | **watch** |

**Weights:** 100% Marvin primary; no approved external sources.

**Returns statement (blended):** At **$152.94** per share, filing-normalized component economics imply deeply sub-15% annual returns; pending third-party sources are not in base IRR.

## [HUMAN REVIEW]

- [ ] Every **approved** source reviewed against filings when added
- [ ] Every **pending** source cited with **[PENDING APPROVAL]** only
- [ ] Blended estimate in `valuation.json` → `estimates.external[]` if material external view arrives

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] AMR: CAPP met coal trough with $1.14B FY2025 buybacks against $145M OCF; component base ~$63/sh vs price ~$153 at 2026-08-06 — `AMR/investor-documents/sec-edgar/10-K_20260227_rpt20251231_acc0001704715_26_000010.htm`

## Primary sources cited

1. `AMR/investor-documents/sec-edgar/10-K_20260227_rpt20251231_acc0001704715_26_000010.htm`
2. `AMR/investor-documents/sec-edgar/10-Q_20260807_rpt20260630_acc0001704715_26_000031.htm`
3. `AMR/investor-documents/DOWNLOAD_MANIFEST.json`
4. `AMR/third-party-analyses/source_inventory_2026-08-06.md`
