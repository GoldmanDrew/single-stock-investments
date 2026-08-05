# ARE — Cross-Check: Third-Party Sources

**Date:** 2026-08-04  
**Agent:** Marvin (universal contract close)  
**Marvin dive:** `ARE/research/deep_dive_2026-08-04.md`  
**Source inventory:** `ARE/third-party-analyses/source_inventory_2026-08-02.md`  
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

Five third-party items are indexed for ARE as of 2026-08-02: one pending VIC note and four activist SC 13D/13D-A filings (Greenlight, Eminence). **None are approved** for base IRR per `_system/frameworks/third_party_sources.md`. Marvin stance rests on **primary filings** (FY2025 10-K, Q1 2026 10-Q). Activist filings support a **complexity / capital-allocation discount** narrative as context only.

**Synthesis:** Marvin floor only; no external blend into base case. Pending VIC and activist views do not change proof-first component sum (**−$11.35/sh** pre-floor, **$0/sh** after zero value policy).

## Sources in scope

| ID | Title | Path | Status | Use |
|----|-------|------|--------|-----|
| vic | ARE - 163601 | `third-party-analyses/vic/ARE - 163601.pdf` | **[PENDING APPROVAL]** | Not in base IRR |
| activist_long | Greenlight SC 13D/A (2023-07) | `activist_reports/long/SC-13D/A_20230726_*.htm` | context | Activist stake; no filing contradiction checked this pass |
| activist_long | Greenlight SC 13D (2023-06) | `activist_reports/long/SC-13D_20230608_*.htm` | context | Initial stake disclosure |
| activist_long | Eminence SC 13D (2023-10) | `activist_reports/long/SC-13D_20231023_*.htm` | context | Activist stake |
| activist_long | SC 13D/A (2024-04) | `activist_reports/long/SC-13D/A_20240401_*.htm` | context | Updated activist position |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| Scale | FY2025 revenue **$2.95B** | — | `10-K_20260126` |
| Leverage | Debt **~$19.1B**; cash **$549M** | Activists cite balance-sheet leverage (context) | 10-K; SC 13D filings |
| Lab exposure | Life-science cluster landlord | VIC thesis likely lab-cycle focused **[PENDING]** | 10-K business description |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| Equity value | Component base **$0/sh** (liquidation_shortfall policy) | Activists may argue asset/NAV upside | No blend; external not approved |
| Return path | Lawrence synthesis **23.3%** per year | Unknown until VIC approved | Pending only |
| Catalyst | Lab demand normalization **[Assumption]** | Activist capital-allocation push | Context; not in base proof |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor (filings + contract) | **$0/sh** base (pre-floor **−$11.35**) | **23.3%** synthesis / **22.6%** Lawrence | watch |
| External (combined) | Not blended | Not blended | n/a |
| **Blended best estimate** | **$0/sh** component base | **23.3%** synthesis (Lawrence gate) | **watch** |

**Weights:** 100% Marvin primary + contract proof; 0% external until human promotes sources.

**Returns statement (blended):** At **$50.05**, Marvin synthesis base implies **23.3%** per year over seven years, but proof-first components sum to **−$11.35** per share pre-floor; we do not blend pending VIC or activist views into base.

## [HUMAN REVIEW]

- [ ] Review and approve or reject `vic/ARE - 163601.pdf` for base IRR
- [ ] Read Greenlight / Eminence SC 13D filings against FY2025 10-K capital-allocation claims
- [ ] Confirm whether activist theses imply higher `reinvestment_runway` or lower `cycle_reserve` before adjusting components

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] ARE: third-party cross-check 2026-08-04 — no approved external sources; activist and VIC remain context/pending.

## Primary sources cited

1. `ARE/investor-documents/sec-edgar/10-K_20260126_rpt20251231_acc0001035443_26_000013.htm`
2. `ARE/research/evidence/filing_facts_2026-07-25.json`
3. `ARE/research/valuation_contract.json`
4. `ARE/third-party-analyses/source_inventory_2026-08-02.md`
