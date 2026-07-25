# ADM — Cross-Check: Third-Party Sources

**Date:** 2026-07-25  
**Agent:** Marvin  
**Marvin dive:** `ADM/research/deep_dive_2026-07-25.md`  
**Source inventory:** `ADM/third-party-analyses/source_inventory_2026-07-25.md`  
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

No approved or pending third-party analyses are indexed for ADM as of 2026-07-25. Marvin stance rests on **primary SEC filings only** (FY2025 10-K, Q1 2026 10-Q, recent 8-Ks). The universal valuation contract is at **decision_grade** with four additive components and filing-grounded calculation proofs.

**Synthesis:** Marvin floor only; no external blend. Base contract value **$84.83 per share** vs price **$85.67** implies roughly flat seven-year annualized return at the component schedule; Lawrence normalized owner-cash path yields **12.4%** per year (reference stance gate).

## Sources in scope

| ID | Title | Path | Status | Use |
|----|-------|------|--------|-----|
| (none) | Primary filings only | `ADM/investor-documents/sec-edgar/` | n/a | Base case |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| FY2025 revenue decline | $80.3B vs $85.5B prior year | — | `10-K_20260217_rpt20251231_acc0000007084_26_000011.htm` |
| FY2025 net income | $1.078B; EPS $2.23 | — | Same 10-K |
| Operating cash flow recovery | $5.45B FY2025 vs $2.79B FY2024 | — | Same 10-K |
| Net debt position | Cash $1.0B; long-term debt $6.6B | — | Same 10-K |
| SEC investigation resolved | Settlement announced Jan 27, 2026 | — | `8-K_20260128_rpt20260127_acc0001193125_26_025560.htm` |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| Normalized owner cash | $6.50/sh (OCF minus capex haircut) | — | No external view to blend |
| Nutrition runway value | $6/sh base additive component | — | Judgment only; no sell-side in base |
| Cycle reserve | -$7/sh base (crush/trade stress) | — | Marvin-only downside buffer |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor (Lawrence) | $6.50/sh normalized | **12.4%** / 7yr | Reference gate |
| Component contract | $84.83/sh base value | **-0.14%** / 7yr at $85.67 | Decision-grade schedule |
| External (combined) | — | — | — |
| **Blended best estimate** | **$6.50/sh owner cash; $84.83/sh component value** | **12.4% Lawrence; ~flat contract** | **watch** |

**Weights:** 100% primary filings. No approved third-party sources in base IRR.

**Returns statement (blended):** At **$85.67**, Lawrence normalized owner-cash math implies **12.4%** per year; the filing-grounded component contract implies roughly **flat** annualized return (**-0.14%**) because cycle reserve and net debt offset the operating engine. Stance remains **watch** pending moat proof and capex tagging from filings.

## [HUMAN REVIEW]

- [ ] Every **approved** source reviewed against filings (none indexed)
- [ ] Every **pending** source cited with **[PENDING APPROVAL]** only (none)
- [ ] Blended estimate in `valuation.json` → `estimates.external[]` if material (not applicable)

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] ADM: universal contract refresh 2026-07-25; decision_grade component schedule ($84.83/sh base); Lawrence **12.4%** at $85.67 on $6.50/sh normalized owner cash; stance **watch**; SEC intersegment investigation settled Jan 2026.

## Primary sources cited

1. `ADM/investor-documents/sec-edgar/10-K_20260217_rpt20251231_acc0000007084_26_000011.htm`
2. `ADM/investor-documents/sec-edgar/10-Q_20260505_rpt20260331_acc0000007084_26_000023.htm`
3. `ADM/investor-documents/sec-edgar/8-K_20260128_rpt20260127_acc0001193125_26_025560.htm`
4. `ADM/research/valuation.json`
5. `ADM/third-party-analyses/source_inventory_2026-07-25.md`
