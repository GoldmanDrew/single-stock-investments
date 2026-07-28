# AI pricing analysis

**As of:** 2026-07-28

**Price:** $8.61

**Decision:** watch_pending_owner_review

## Price versus component value

| Component | Method | Low | Base | High |
|---|---|---:|---:|---:|
| Enterprise AI platform owner-cash engine | owner_cash_or_dividend_discount | $8.82 | $20.50 | $46.80 |
| Enterprise pipeline and Federal reinvestment runway | owner_earnings_reinvestment_dcf | $0.20 | $1.50 | $4.00 |
| Net cash claims | net_asset_value | $0.48 | $0.48 | $0.48 |
| Dilution, SBC, and competition reserve | midcycle_capacity_value | $-4.00 | $-1.50 | $-0.40 |
| **Total** |  | **$5.50** | **$20.98** | **$50.88** |

Base value versus price: **143.7%**. Current or contracted operating and financial assets support approximately **$20.98** per share; the market asks investors to pay another **$-12.37** for growth, inventory, projects, or scarcity.


## Economic value versus accounting value

**GAAP role:** cross_check

**Accounting reference:** AI/investor-documents/sec-edgar/10-K_20260624_rpt20260430_acc0001577526_26_000078.htm; AI/research/evidence/filing_facts_2026-07-25.json

A complete comparable NAV is not asserted; comparable marks are used only where the economic asset and ownership claim are sufficiently defined.

| Economic component | Comparable basis | Comparable base / share | Risked base / share | Overlap control |
|---|---|---:|---:|---|
| Enterprise AI platform owner-cash engine | owner_cash_or_dividend_discount proof outputs. | n/a | $20.50 | Unique overlap key core_engine. |
| Enterprise pipeline and Federal reinvestment runway | owner_earnings_reinvestment_dcf proof outputs. | n/a | $1.50 | Unique overlap key reinvestment_runway. |
| Net cash claims | net_asset_value proof outputs. | n/a | $0.48 | Unique overlap key net_financial_claims. |
| Dilution, SBC, and competition reserve | midcycle_capacity_value proof outputs. | n/a | $-1.50 | Unique overlap key cycle_reserve. |

### Deterministic valuation proof

| Economic claim | Method | Comparable | Low / base / high | Risk / timing | Overlap control | Falsifier |
|---|---|---|---:|---|---|---|
| Enterprise AI platform owner-cash engine | owner_cash_or_dividend_discount | not_applicable | $8.82 / $20.50 / $46.80 | n/a | Unique overlap key core_engine. | Primary evidence shows owner cash or capital structure materially worse than low case. |
| Enterprise pipeline and Federal reinvestment runway | owner_earnings_reinvestment_dcf | not_applicable | $0.20 / $1.50 / $4.00 | n/a | Unique overlap key reinvestment_runway. | Primary evidence shows owner cash or capital structure materially worse than low case. |
| Net cash claims | net_asset_value | not_applicable | $0.48 / $0.48 / $0.48 | n/a | Unique overlap key net_financial_claims. | Primary evidence shows owner cash or capital structure materially worse than low case. |
| Dilution, SBC, and competition reserve | midcycle_capacity_value | not_applicable | $-4.00 / $-1.50 / $-0.40 | n/a | Unique overlap key cycle_reserve. | Primary evidence shows owner cash or capital structure materially worse than low case. |

### Investor-wisdom rules applied

- None documented.

### Limitations

- XBRL values treated as thousands; share count and FCF reinvestment haircut are assumptions.
- GAAP NI tag appears inconsistent with software-loss history; model anchors on OCF.



## What the price implies

At the stated terminal multiple, the price requires approximately **-13.3%** constant annual owner-cash growth for seven years. Constant 7-year owner-cash growth with a 18x terminal owner-cash multiple; diagnostic, not forecast.

## Entry prices by required return

These prices are the present value of the explicit seven-year cash-flow and terminal-value scenarios at each hurdle. They are not arbitrary discounts to the current quote.

| Scenario | 10% | 12% | 15% | 20% |
|---|---:|---:|---:|---:|
| Bear | $11.31 | $10.21 | $8.82 | $7.01 |
| Base | $23.86 | $21.34 | $18.16 | $14.06 |
| Bull | $48.37 | $43.03 | $36.29 | $27.67 |

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
