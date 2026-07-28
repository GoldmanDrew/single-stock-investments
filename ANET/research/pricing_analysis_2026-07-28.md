# ANET pricing analysis

**As of:** 2026-07-28

**Price:** $169.35

**Decision:** watch_pending_owner_review

## Price versus component value

| Component | Method | Low | Base | High |
|---|---|---:|---:|---:|
| Cloud networking owner-cash engine | owner_cash_or_dividend_discount | $64.21 | $134.31 | $252.13 |
| AI ethernet / campus runway | owner_earnings_reinvestment_dcf | $5.00 | $20.00 | $50.00 |
| Net cash claims | net_asset_value | $1.56 | $1.56 | $1.56 |
| Competition and customer-concentration reserve | midcycle_capacity_value | $-40.00 | $-12.00 | $-3.00 |
| **Total** |  | **$30.77** | **$143.87** | **$300.69** |

Base value versus price: **-15.0%**. Current or contracted operating and financial assets support approximately **$143.87** per share; the market asks investors to pay another **$25.48** for growth, inventory, projects, or scarcity.


## Economic value versus accounting value

**GAAP role:** cross_check

**Accounting reference:** ANET/investor-documents/sec-edgar/10-K_20260217_rpt20251231_acc0001596532_26_000013.htm; ANET/research/evidence/filing_facts_2026-07-25.json

A complete comparable NAV is not asserted; comparable marks are used only where the economic asset and ownership claim are sufficiently defined.

| Economic component | Comparable basis | Comparable base / share | Risked base / share | Overlap control |
|---|---|---:|---:|---|
| Cloud networking owner-cash engine | owner_cash_or_dividend_discount proof outputs. | n/a | $134.31 | Unique overlap key core_engine. |
| AI ethernet / campus runway | owner_earnings_reinvestment_dcf proof outputs. | n/a | $20.00 | Unique overlap key reinvestment_runway. |
| Net cash claims | net_asset_value proof outputs. | n/a | $1.56 | Unique overlap key net_financial_claims. |
| Competition and customer-concentration reserve | midcycle_capacity_value proof outputs. | n/a | $-12.00 | Unique overlap key cycle_reserve. |

### Deterministic valuation proof

| Economic claim | Method | Comparable | Low / base / high | Risk / timing | Overlap control | Falsifier |
|---|---|---|---:|---|---|---|
| Cloud networking owner-cash engine | owner_cash_or_dividend_discount | not_applicable | $64.21 / $134.31 / $252.13 | n/a | Unique overlap key core_engine. | Primary evidence shows owner cash or capital structure materially worse than low case. |
| AI ethernet / campus runway | owner_earnings_reinvestment_dcf | not_applicable | $5.00 / $20.00 / $50.00 | n/a | Unique overlap key reinvestment_runway. | Primary evidence shows owner cash or capital structure materially worse than low case. |
| Net cash claims | net_asset_value | not_applicable | $1.56 / $1.56 / $1.56 | n/a | Unique overlap key net_financial_claims. | Primary evidence shows owner cash or capital structure materially worse than low case. |
| Competition and customer-concentration reserve | midcycle_capacity_value | not_applicable | $-40.00 / $-12.00 / $-3.00 | n/a | Unique overlap key cycle_reserve. | Primary evidence shows owner cash or capital structure materially worse than low case. |

### Investor-wisdom rules applied

- None documented.

### Limitations

- Judgment bands remain widest for runway and cycle reserve.



## What the price implies

At the stated terminal multiple, the price requires approximately **5.7%** constant annual owner-cash growth for seven years. Constant 7-year owner-cash growth with a 28x terminal owner-cash multiple; diagnostic, not forecast.

## Entry prices by required return

These prices are the present value of the explicit seven-year cash-flow and terminal-value scenarios at each hurdle. They are not arbitrary discounts to the current quote.

| Scenario | 10% | 12% | 15% | 20% |
|---|---:|---:|---:|---:|
| Bear | $66.56 | $59.71 | $51.02 | $39.83 |
| Base | $122.93 | $109.59 | $92.73 | $71.14 |
| Bull | $215.33 | $191.30 | $160.97 | $122.24 |

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
