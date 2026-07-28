# AMAT pricing analysis

**As of:** 2026-07-28

**Price:** $588.66

**Decision:** watch_pending_owner_review

## Price versus component value

| Component | Method | Low | Base | High |
|---|---|---:|---:|---:|
| WFE and AGS owner-cash engine | owner_cash_or_dividend_discount | $86.40 | $158.82 | $246.94 |
| AI and advanced-packaging reinvestment runway | owner_earnings_reinvestment_dcf | $10.00 | $40.00 | $90.00 |
| Net cash and long-term debt claims | net_asset_value | $0.57 | $0.97 | $1.37 |
| Semi capital-cycle reserve | midcycle_capacity_value | $-120.00 | $-40.00 | $-10.00 |
| **Total** |  | **$0.00** | **$159.79** | **$328.31** |

Base value versus price: **-72.9%**. Current or contracted operating and financial assets support approximately **$159.79** per share; the market asks investors to pay another **$428.87** for growth, inventory, projects, or scarcity.


## Economic value versus accounting value

**GAAP role:** cross_check

**Accounting reference:** AMAT/investor-documents/sec-edgar/10-K_20251212_rpt20251026_acc0001628280_25_056742.htm; AMAT/research/evidence/filing_facts_2026-07-10.json

A complete comparable NAV is not asserted; comparable marks are used only where the economic asset and ownership claim are sufficiently defined.

| Economic component | Comparable basis | Comparable base / share | Risked base / share | Overlap control |
|---|---|---:|---:|---|
| WFE and AGS owner-cash engine | owner_cash_or_dividend_discount proof outputs. | n/a | $158.82 | Unique overlap key core_engine. |
| AI and advanced-packaging reinvestment runway | owner_earnings_reinvestment_dcf proof outputs. | n/a | $40.00 | Unique overlap key reinvestment_runway. |
| Net cash and long-term debt claims | net_asset_value proof outputs. | n/a | $0.97 | Unique overlap key net_financial_claims. |
| Semi capital-cycle reserve | midcycle_capacity_value proof outputs. | n/a | $-40.00 | Unique overlap key cycle_reserve. |

### Deterministic valuation proof

| Economic claim | Method | Comparable | Low / base / high | Risk / timing | Overlap control | Falsifier |
|---|---|---|---:|---|---|---|
| WFE and AGS owner-cash engine | owner_cash_or_dividend_discount | not_applicable | $86.40 / $158.82 / $246.94 | n/a | Unique overlap key core_engine. | Primary evidence shows owner cash or capital structure materially worse than low case. |
| AI and advanced-packaging reinvestment runway | owner_earnings_reinvestment_dcf | not_applicable | $10.00 / $40.00 / $90.00 | n/a | Unique overlap key reinvestment_runway. | Primary evidence shows owner cash or capital structure materially worse than low case. |
| Net cash and long-term debt claims | net_asset_value | not_applicable | $0.57 / $0.97 / $1.37 | n/a | Unique overlap key net_financial_claims. | Primary evidence shows owner cash or capital structure materially worse than low case. |
| Semi capital-cycle reserve | midcycle_capacity_value | not_applicable | $-120.00 / $-40.00 / $-10.00 | n/a | Unique overlap key cycle_reserve. | Primary evidence shows owner cash or capital structure materially worse than low case. |

### Investor-wisdom rules applied

- None documented.

### Limitations

- Judgment bands remain widest for runway and cycle reserve.



## What the price implies

At the stated terminal multiple, the price requires approximately **19.2%** constant annual owner-cash growth for seven years. Constant 7-year owner-cash growth with a 20x terminal owner-cash multiple; diagnostic, not forecast.

## Entry prices by required return

These prices are the present value of the explicit seven-year cash-flow and terminal-value scenarios at each hurdle. They are not arbitrary discounts to the current quote.

| Scenario | 10% | 12% | 15% | 20% |
|---|---:|---:|---:|---:|
| Bear | $107.95 | $97.22 | $83.58 | $65.95 |
| Base | $155.81 | $139.62 | $119.09 | $92.69 |
| Bull | $217.89 | $194.57 | $165.06 | $127.22 |

## Decision explanation

Entry prices were computed mechanically from the routed power-zone profile (High-return compounder). They are decision inputs, not a decision; the owner must review the scenarios before acting.

**Strongest counter-explanation:** growth projected without its capital cost

**Committee routing:** not_initialized — not initialized

**Falsifiers:**

- growth projected without its capital cost
- stock compensation or acquisitions omitted
- terminal value unsupported by a durable mechanism

## Economic claim

Per-share claims use fully diluted shares from valuation.inputs.
