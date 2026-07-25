# AEE — Cross-Check: Third-Party Sources

**Date:** 2026-07-25
**Agent:** Marvin (contract backfill refresh)
**Marvin dive:** `AEE/research/deep_dive_2026-07-25.md`
**Source inventory:** `AEE/third-party-analyses/source_inventory_2026-07-25.md`
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

Marvin Lawrence synthesis **7.1%** per year (infrastructure; stance **watch**) from primary filings and `valuation.json`. Universal contract at **decision_grade** values additive components at **$43.38/sh** base (**-12.7%** annualized at **$111.77**). No third-party sources indexed; filings-only stance. **[HUMAN REVIEW]** for approved-source numeric blend.

**Synthesis (best estimate):** Marvin **7.1%** Lawrence base · contract **$43.38/sh** · stance **watch**; external sources adjust conviction on catalyst timing, not primary IRR without human OK.

## Sources in scope

| Source ID | Title | Path | Status | Cross-check status |
|-----------|-------|------|--------|-------------------|
| (none) | Primary filings only | — | — | n/a |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| Base return anchor | **7.1%** per year (Lawrence synthesis) | Qualitative support only | `AEE/research/deep_dive_2026-07-25.md` |
| Contract value | **$43.38/sh** base additive sum | No external value estimate | `valuation.json` → `universal_valuation_contract` |
| Archetype / stance | **infrastructure** · **watch** | See indexed sources | `valuation.json` |
| Normalization | Regulated utility: Lawrence uses filing earnings power per share, not OCF minus capex | Cross-check vs posts | Marvin |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| Primary IRR | **7.1%** (Lawrence synthesis) | No single approved IRR unless promoted | Marvin **70%** numeric; external **30%** catalyst timing |
| Contract vs Lawrence | **$43.38/sh** vs earnings-power DCF **$109.23/sh** engine alone | N/A | Contract prices debt and regulatory reserve explicitly; Lawrence path is consolidated owner-cash IRR |
| Third party | Filing-first | Context tier only | No numeric upgrade without human OK |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor (Lawrence) | $5.10/sh normalized earnings power | **7.1%** | **watch** |
| Contract (decision_grade) | **$43.38/sh** additive | **-12.7%** at spot | **watch** (valuation discipline) |
| External (combined) | Narrative / catalyst | No change to base % | **watch** (conviction) |
| **Blended best estimate** | **Filing anchor** | **7.1%** Lawrence · **$43.38/sh** contract | **watch** |

**Weights:** Marvin **70%** on numbers; indexed third party **30%** on catalyst timing and narrative (approved Substacks/HK context only in qualitative layer until human promotes).

**Returns statement (blended):** We expect **7.1%** per year at today's price on the Marvin Lawrence base case; the contract additive sum of **$43.38/sh** flags that explicit debt and regulatory reserve claims compress economic value below spot. Third-party sources may raise or lower conviction on timing but do not replace filing math without **[HUMAN REVIEW]**.

## [HUMAN REVIEW]

- [ ] Every **approved** source reviewed against filings
- [ ] Every **pending** source cited with **[PENDING APPROVAL]** only
- [ ] Blended estimate in `valuation.json` → `estimates.external[]` if material
- [ ] Reconcile Lawrence 7.1% stance gate with contract -12.7% at price for capital decisions

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] AEE: contract backfill 2026-07-25 — four additive components at decision_grade; Lawrence synthesis **7.1%** unchanged; contract base **$43.38/sh** at **$111.77**.

## Primary sources cited

1. `AEE/research/deep_dive_2026-07-25.md`
2. `AEE/research/valuation.json`
3. `AEE/third-party-analyses/source_inventory_2026-07-25.md`
4. `AEE/investor-documents/sec-edgar/10-K_20260218_rpt20251231_acc0001002910_26_000009.htm`
