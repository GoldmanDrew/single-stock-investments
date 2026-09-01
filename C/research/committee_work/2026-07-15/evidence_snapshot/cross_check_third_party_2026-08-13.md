# C — Cross-Check: Third-Party Sources

**Date:** 2026-08-13  
**Agent:** Marvin  
**Marvin dive:** `C/research/deep_dive_2026-08-13.md`  
**Source inventory:** `C/third-party-analyses/source_inventory_2026-08-13.md` (mechanical scan)  
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

No Citigroup-specific approved third-party research is indexed for base IRR. Context-tier HK and approved registry entries for other tickers (ICE croupier lens, CMSG holdco) inform **bank capital and simplification** themes only. **[PENDING APPROVAL]** for any sell-side or Substack work not in `third_party_sources.md`.

**Synthesis (best estimate):** Marvin filing-backed component base **$107/sh** vs price **~$135**; no approved external floor above tangible book to override proof schedule.

## Sources in scope

| Source ID | Title | Path | Status | Cross-check status |
|-----------|-------|------|--------|-------------------|
| hk_context_ice | HK context (ICE) | `ICE/third-party-analyses/references.md` | approved (context) | reviewed — exchange/croupier lens only |
| hk_context_cmsg | HK + SSI + LCI (CMSG) | `CMSG/third-party-analyses/references.md` | approved (context) | reviewed — holdco/book discount lens only |
| verdad_biotech_2026 | Verdad biotech paper | `_system/reference/biotech-quant/papers/verdad_biotech_investing_2026.pdf` | approved (context) | not applicable to C |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| Large-bank capital return is regulatory-gated | CET1 13.2% vs 11.6% req; $17.6B returned FY2025 | HK/ICE context: croupier and infrastructure names differ from G-SIB capital rules | 10-K; ICE references (context) |
| Tangible book is the anchor, not headline price | TBVPS $97.06; proof base TCE component $97/sh | Klarman-style asset value discipline in method route | 10-K; valuation contract |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| Franchise premium at ~1.4× TBVPS | Base economic value $107/sh implies modest franchise + capital option minus stress | No approved C-specific external target | Marvin proof schedule stands; external context does not enter base IRR |
| Transformation upside | $10/sh excess-capital component with 55% realization probability | No dated external catalyst cited | Watch until quarterly CET1 walk confirms headroom |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor (proof sum) | $107/sh base | -3.25% per year (7-year synthesis) | watch |
| External (combined) | No approved C-specific value | n/a | context only |
| **Blended best estimate** | **$107/sh** | **-3.25% per year** | **watch** |

**Weights:** 100% Marvin filing-backed component schedule; zero weight on non-C approved sources.

**Returns statement (blended):** At **~$135** per share, the blended best estimate is **-3.25%** per year over seven years on the proof-backed component base of **$107** per share.

## [HUMAN REVIEW]

- [ ] Promote any Citigroup-specific third-party source to `third_party_sources.md` before use in base IRR
- [ ] HK commentaries remain context tier per `hk_cross_reference.md`

## Primary sources cited

1. `C/investor-documents/sec-edgar/10-K_20260220_rpt20251231_acc0000831001_26_000011.htm`
2. `C/research/evidence_reconciliation_2026-08-13.md`
3. `C/research/valuation.json`
