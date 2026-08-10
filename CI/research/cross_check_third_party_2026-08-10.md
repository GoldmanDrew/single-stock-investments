# CI — Cross-Check: Third-Party Sources

**Date:** 2026-08-10
**Agent:** Marvin
**Marvin dive:** `CI/research/deep_dive_2026-08-10.md`
**Source inventory:** `CI/third-party-analyses/source_inventory_2026-07-10.md`
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

No third-party sources are indexed for this ticker as of this scan. Marvin stance rests on **primary filings only** (FY2025 10-K, Q1 2026 10-Q, debt prospectuses). Contract backfill refreshed long-term debt from **$39.5B (stale 2018 tag)** to **$30.9B (FY2025 10-K)** — a mechanical correction, not an external view.

**Synthesis:** Marvin floor only; no external blend.

## Sources in scope

| Source | Type | Status | Role |
|--------|------|--------|------|
| Primary SEC filings | 10-K / 10-Q / 424B5 | approved (primary) | Base owner cash, debt, segments |
| SC-13G activist filings | ownership | context | No active thesis indexed |
| (none other) | — | — | — |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| FY2025 revenue scale | $274.9B consolidated | n/a | FY2025 10-K |
| Long-term debt | $30.871B Dec-2025 | n/a | FY2025 10-K; sec_companyfacts |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| — | — | — | No external views to reconcile |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | Owner-earnings DCF post-debt fix | 7-year base case | watch |
| External (combined) | — | — | — |
| **Blended best estimate** | **Marvin floor only** | **7-year base** | **watch** |

**Weights:** 100% Marvin primary — no approved third-party inputs.

**Returns statement (blended):** Pending approved external sources; base return follows Marvin contract only.

## [HUMAN REVIEW]

- [ ] Every **approved** source reviewed against filings
- [ ] Every **pending** source cited with **[PENDING APPROVAL]** only
- [ ] Blended estimate in `valuation.json` → `estimates.external[]` if material

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] CI: third-party cross-check 2026-08-10 — Marvin floor only

## Primary sources cited

1. `CI/research/deep_dive_2026-08-10.md`
2. `CI/investor-documents/sec-edgar/10-K_20260226_rpt20251231_acc0001739940_26_000006.htm`
3. `CI/third-party-analyses/source_inventory_2026-07-10.md`
