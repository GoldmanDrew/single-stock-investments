# NVR — Cross-Check: Third-Party Sources

**Date:** 2026-07-21  
**Agent:** Marvin (contract backfill)  
**Marvin dive:** `NVR/research/deep_dive_2026-07-21.md`  
**Source inventory:** `NVR/third-party-analyses/source_inventory_2026-07-10.md` (latest scan)  
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

No approved third-party sources are indexed for NVR as of this scan. Marvin stance rests on **primary filings only** (2025 Form 10-K reconciled in `evidence_reconciliation_2026-07-15.json` and proof graphs in `evidence_reconciliation_2026-07-21.md`). HK vault: not indexed for NVR.

**Synthesis:** Marvin component floor only; no external blend. Pending sources remain **[PENDING APPROVAL]** and are excluded from base return.

## Sources in scope

| Source | Tier | Path | Role |
|--------|------|------|------|
| NVR 2025 Form 10-K | primary | SEC filing (see evidence reconciliation primary_sources) | Segment economics, lot control, cash, backlog |
| Third-party scan | pending | `NVR/third-party-analyses/source_inventory_2026-07-10.md` | No approved external analyses |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| Lot-control model | Controls ~207k lots via LPAs; net deposits $851M | n/a | evidence_reconciliation_2026-07-15 |
| FY2025 profitability | Net income $1.340B; homebuilding pretax $1.610B | n/a | evidence_reconciliation_2026-07-15 |
| Cash and debt | Cash $1.916B; senior notes $909M | n/a | evidence_reconciliation_2026-07-15 |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| Normalized owner earnings | $5,600/sh base capitalized from FY2025 anchor | n/a | No external normalization to blend |
| Lot option value | $600/sh incremental base | n/a | Sell-side land NAV not in approved registry |
| Fair value vs price | ~$6,550/sh base vs ~$6,498 price | n/a | Fairly priced on component base |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor (component base) | ~$6,550/sh | ~0.1% per year over 7 years | watch |
| External (combined) | n/a | n/a | n/a |
| **Blended best estimate** | **~$6,550/sh** | **~0.1% per year (7yr)** | **watch** |

**Weights:** 100% Marvin primary-derived component schedule; 0% external (no approved sources).

**Returns statement (blended):** At about **$6,498** per share, the proof-first component base case implies roughly **0.1%** per year over seven years to **~$6,550** per share economic value, a **watch** stance below our mid-teens hurdle.

## [HUMAN REVIEW]

- [ ] Every **approved** source reviewed against filings (none indexed)
- [ ] Every **pending** source cited with **[PENDING APPROVAL]** only
- [ ] Blended estimate in `valuation.json` → `estimates.external[]` if material (not applicable)

## Primary sources cited

1. `NVR/research/evidence_reconciliation_2026-07-15.json`
2. `NVR/research/evidence_reconciliation_2026-07-21.md`
3. `NVR/research/deep_dive_2026-07-21.md`
4. `NVR/third-party-analyses/source_inventory_2026-07-10.md`
