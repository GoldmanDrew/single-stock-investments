# AAOI — Cross-Check: Third-Party Sources

**Date:** 2026-07-17  
**Agent:** Marvin  
**Marvin dive:** `AAOI/research/deep_dive_2026-07-17.md`  
**Source inventory:** `AAOI/third-party-analyses/source_inventory_2026-07-17.md`  
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

No third-party sources are indexed for AAOI as of 2026-07-17 (`scan_third_party_sources.py` returned zero rows). Marvin stance rests on **primary SEC filings only** (FY2025 10-K, Q1 2026 10-Q, 2026 proxy). There is no approved Substack, Horizon Kinetics, or sell-side note in the approved registry to blend into base IRR.

**Synthesis:** Marvin floor only; no external blend. Stance **watch** pending normalized FCF math and live price.

## Sources in scope

| ID | Title | Path | Status | Reviewed |
|----|-------|------|--------|----------|
| — | (none) | — | n/a | Primary filings only |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| — | — | — | No external sources |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| — | — | — | n/a |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | Normalized ~$0.74/sh starting owner cash (FY2025 OCF minus normalized capex) | Lawrence base IRR from `marvin_valuation.py` | watch |
| External (combined) | — | — | — |
| **Blended best estimate** | **Marvin floor only** | **Pending mechanical IRR** | **watch** |

**Weights:** 100% primary filings; 0% external (none indexed).

**Returns statement (blended):** Same as Marvin Lawrence base until approved third-party sources exist.

## [HUMAN REVIEW]

- [ ] Re-run `scan_third_party_sources.py AAOI --with-hk` when vault or research notes added
- [ ] Promote any useful external work via `third_party_sources.md` before blending into base IRR
- [ ] No pending sources cited in narrative

## Primary sources cited

1. `AAOI/investor-documents/sec-edgar/10-K_20260226_rpt20251231_acc0001437749_26_005875.htm`
2. `AAOI/investor-documents/sec-edgar/10-Q_20260507_rpt20260331_acc0001437749_26_015620.htm`
3. `AAOI/research/deep_dive_2026-07-17.md`
4. `AAOI/third-party-analyses/source_inventory_2026-07-17.md`
