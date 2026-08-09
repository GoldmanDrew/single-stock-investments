# CVS — Cross-Check: Third-Party Sources

**Date:** 2026-08-09
**Agent:** Marvin
**Marvin dive:** `CVS/research/deep_dive_2026-08-09.md`
**Source inventory:** `CVS/third-party-analyses/source_inventory_2026-07-10.md`
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

No **approved** third-party sources are indexed for CVS as of this scan. Activist filings in `third-party-analyses/activist_reports/` are **context tier** only and were not promoted to base IRR. Marvin stance rests on **primary SEC filings** (10-K, 10-Q, proxy). The contract backfill refreshed stale debt to Q1 2026; no external view changes that mechanical fix.

**Synthesis:** Marvin floor only; no external blend.

## Sources in scope

| Source | Type | Status | Reviewed |
|--------|------|--------|----------|
| Primary filings | SEC 10-K / 10-Q / DEF 14A | primary | yes |
| Activist DFAN14A / SC-13G | activist | **[PENDING APPROVAL]** context | skimmed; not in base IRR |
| Approved Substacks / HK | — | none indexed | n/a |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| Scale | FY2025 revenue **$402.1B** | n/a | 10-K FY2025 |
| Leverage | Total debt **$63.1B** Q1 2026 | n/a | 10-Q Q1 2026 |
| Owner cash | FY2025 OCF **$10.6B** less capex **$2.8B** | n/a | companyfacts |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| — | — | — | No approved external normalization to blend |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | **$7.8B** normalized owner earnings; proof base **~$69/sh** | **~-6%** per year at **$107.61** (7-year base) | watch |
| External (combined) | — | — | — |
| **Blended best estimate** | **Same as Marvin floor** | **~-6%** per year | **watch** |

**Weights:** 100% Marvin primary filings; no approved external sources.

**Returns statement (blended):** At **$107.61**, the blended best estimate is **roughly -6% per year** over seven years on filing-normalized owner earnings and refreshed Q1 2026 debt; pending activist material is context only.

## [HUMAN REVIEW]

- [ ] Every **approved** source reviewed against filings (none indexed)
- [ ] Every **pending** source cited with **[PENDING APPROVAL]** only
- [ ] Blended estimate in `valuation.json` → `estimates.external[]` if material (not material today)

## Primary sources cited

1. `CVS/research/deep_dive_2026-08-09.md`
2. `CVS/research/evidence/filing_digest_2026-08-06.md`
3. `CVS/research/evidence/sec_companyfacts.json`
4. `CVS/third-party-analyses/source_inventory_2026-07-10.md`
