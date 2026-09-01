# AMD — Cross-Check: Third-Party Sources

**Date:** 2026-07-23  
**Agent:** Marvin (contract backfill refresh)  
**Marvin dive:** `AMD/research/deep_dive_2026-07-23.md`  
**Source inventory:** `AMD/third-party-analyses/source_inventory_2026-06-07.md`  
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

No third-party sources are indexed for AMD as of 2026-07-23. Marvin stance rests on **primary filings only** (FY2025 10-K, Q1 FY2026 10-Q, proxy). Lawrence total-synthesis base IRR is **−14.56%** per year at **~$550** on **$3.37** per share FY2025 free cash flow. Proof-first component base value is **$96.45/sh**. There is no external view to blend.

**Synthesis:** Marvin floor only; no external blend.

## Sources in scope

| ID | Title | Path | Status | Reviewed |
|----|-------|------|--------|----------|
| — | Primary filings only | `AMD/investor-documents/sec-edgar/` | n/a | Yes |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| FY2025 revenue | $34.6B (+34% YoY) | — | `10-K_20260204` |
| Data Center segment | $16.6B rev; $3.6B OI | — | 10-K segment note |
| Free cash flow per share | $3.37 (continuing ops) | — | OCF $6.49B − capex $0.97B ÷ shares |
| Component base value | $96.45/sh (five proofs) | — | `evidence_reconciliation_2026-07-23.md` |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| — | — | — | No external sources |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | $3.37/sh FCF; $96.45/sh components | **−14.56%** / 7yr synthesis | watch |
| External (combined) | — | — | — |
| **Blended best estimate** | **$96.45/sh** components; **$3.37/sh** FCF | **−14.56%** (Marvin only) | **watch** |

**Weights:** 100% Marvin filings; 0% external.

**Returns statement (blended):** With no approved third-party inputs, the blended return equals the Marvin total-synthesis base **−14.56%** per year.

## [HUMAN REVIEW]

- [x] No approved third-party sources in inventory (documented)
- [x] No pending sources in base IRR
- [ ] Re-run `scan_third_party_sources.py AMD --with-hk` when external material added
- [ ] Update `valuation.json` → `estimates.external[]` only after human approval

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] AMD: contract backfill 2026-07-23 — five component proofs; base value **$96.45/sh**; synthesis **−14.56%** watch at **~$550**

## Primary sources cited

1. `AMD/research/deep_dive_2026-07-23.md`
2. `AMD/research/valuation.json`
3. `AMD/research/evidence_reconciliation_2026-07-23.md`
4. `AMD/third-party-analyses/source_inventory_2026-06-07.md`
5. `AMD/investor-documents/sec-edgar/10-K_20260204_rpt20251227_acc0000002488_26_000018.htm`
