# CMI — Cross-Check: Third-Party Sources

**Date:** 2026-08-05
**Agent:** Marvin
**Marvin dive:** `CMI/research/deep_dive_2026-08-05.md`
**Source inventory:** `CMI/third-party-analyses/source_inventory_2026-08-05.md` (if present) / prior `source_inventory_2026-07-10.md`
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

No approved third-party sources are indexed for CMI as of this scan. Marvin stance rests on **primary SEC filings** and mechanical companyfacts. Pending sell-side or Substack material is **context only** and does not enter base proof value.

**Synthesis:** Marvin floor only; no external blend.

## Sources in scope

| Source | Type | Status | In base IRR? |
|--------|------|--------|--------------|
| SEC 10-K / 10-Q | Primary | Verified via DOWNLOAD_MANIFEST | Yes (proof inputs) |
| sec_companyfacts.json | Mechanical | Locked facts | Yes |
| Third-party research | External | None indexed | No |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| Revenue scale | FY2025 **$33.67B** | n/a | 10-K / companyfacts |
| Owner cash anchor | Normalized **$2.386B** (OCF − capex) | n/a | FY2025 10-K |
| Leverage | Debt **$7.686B** Q1 2026 | n/a | 10-Q debt note / companyfacts |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| — | — | — | No external views to reconcile |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor (proof) | Base **~$277/sh** | Negative at **$639.43** | watch |
| External (combined) | — | — | — |
| **Blended best estimate** | **~$277/sh** base proof | **Negative** base annual return at spot | **watch** |

**Weights:** 100% Marvin proof (no approved external inputs).

## Missing data / follow-ups

- Re-run `scan_third_party_sources.py CMI --with-hk --date 2026-08-05` when new Substacks or fund letters are added.
- Segment-level sell-side engine-cycle views would help stress-test reinvestment judgments only; they do not replace filing-based owner cash.

## Classification impact

No change to archetype (**compounder**) or payoff lens (**operating**) from cross-check alone. Stance remains **watch** pending human review of price vs proof value.
