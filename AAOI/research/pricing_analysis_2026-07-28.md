# AAOI pricing analysis

**As of:** 2026-07-28

**Price:** $99.77

**Decision:** watch_pending_owner_review

## Price versus component value

| Component | Method | Low | Base | High |
|---|---|---:|---:|---:|
| Data-center and CATV optics owner-cash engine | owner_cash_or_dividend_discount | $8.06 | $15.01 | $28.85 |
| Hyperscaler 800G share and warrant volume runway | owner_earnings_reinvestment_dcf | $1.00 | $8.00 | $25.00 |
| Net cash and debt claims | net_asset_value | $3.51 | $5.34 | $5.72 |
| Customer concentration and capex overrun reserve | midcycle_capacity_value | $-35.00 | $-12.00 | $-3.00 |
| **Total** |  | **$0.00** | **$16.35** | **$56.57** |

Base value versus price: **-83.6%**. Current or contracted operating and financial assets support approximately **$16.35** per share; the market asks investors to pay another **$83.42** for growth, inventory, projects, or scarcity.


## Economic value versus accounting value

**GAAP role:** cross_check

**Accounting reference:** AAOI/investor-documents/sec-edgar/10-K_20260226_rpt20251231_acc0001437749_26_005875.htm; Q1 2026 cash and diluted shares from valuation.json inputs.

A complete comparable NAV is not asserted; comparable marks are used only where the economic asset and ownership claim are sufficiently defined.

| Economic component | Comparable basis | Comparable base / share | Risked base / share | Overlap control |
|---|---|---:|---:|---|
| Data-center and CATV optics owner-cash engine | Owner-cash discount on normalized FCF $0.74/sh. | n/a | $15.01 | Unique overlap key datacenter_optics_engine. |
| Hyperscaler 800G share and warrant volume runway | Owner-earnings reinvestment judgment band per share. | n/a | $8.00 | Unique overlap key hyperscaler_share_runway. |
| Net cash and debt claims | NAV on cash $439.7M less modest debt. | n/a | $5.34 | Unique overlap key net_financial_claims. |
| Customer concentration and capex overrun reserve | Bounded negative mid-cycle capacity reserve. | n/a | $-12.00 | Unique overlap key customer_capex_reserve. |

### Deterministic valuation proof

| Economic claim | Method | Comparable | Low / base / high | Risk / timing | Overlap control | Falsifier |
|---|---|---|---:|---|---|---|
| Normalized free cash flow after Taiwan capacity build-out | owner_cash_or_dividend_discount | not_applicable | $8.06 / $15.01 / $28.85 | n/a | Unique overlap key datacenter_optics_engine. | Primary evidence shows hyperscaler share loss or cash burn materially worse than low case. |
| Bounded multi-customer share gains above normalized FCF0 | owner_earnings_reinvestment_dcf | not_applicable | $1.00 / $8.00 / $25.00 | n/a | Unique overlap key hyperscaler_share_runway. | Primary evidence shows hyperscaler share loss or cash burn materially worse than low case. |
| Q1 2026 cash less modest debt after liquidity haircuts | net_asset_value | not_applicable | $3.51 / $5.34 / $5.72 | n/a | Unique overlap key net_financial_claims. | Primary evidence shows hyperscaler share loss or cash burn materially worse than low case. |
| Hyperscaler concentration, dilution, Taiwan capex stress | midcycle_capacity_value | not_applicable | $-35.00 / $-12.00 / $-3.00 | n/a | Unique overlap key customer_capex_reserve. | Primary evidence shows hyperscaler share loss or cash burn materially worse than low case. |

### Investor-wisdom rules applied

- None documented.

### Limitations

- FY2025 reported owner cash was negative; FCF0 uses normalized capex assumption.
- Long-term debt tag in filing_facts appears unit-skewed; debt treated as modest vs cash.



## What the price implies

At the stated terminal multiple, the price requires approximately **31.8%** constant annual owner-cash growth for seven years. Constant 7-year owner-cash growth with a 16x terminal owner-cash multiple; diagnostic, not forecast.

## Entry prices by required return

These prices are the present value of the explicit seven-year cash-flow and terminal-value scenarios at each hurdle. They are not arbitrary discounts to the current quote.

| Scenario | 10% | 12% | 15% | 20% |
|---|---:|---:|---:|---:|
| Bear | $10.32 | $9.33 | $8.06 | $6.41 |
| Base | $17.47 | $15.67 | $13.38 | $10.44 |
| Bull | $29.99 | $26.76 | $22.68 | $17.44 |

## Decision explanation

Entry prices were computed mechanically from the routed power-zone profile (Capital cycle and normalized industry economics). They are decision inputs, not a decision; the owner must review the scenarios before acting.

**Strongest counter-explanation:** peak margins capitalized

**Committee routing:** round_one_open — marathon_capital_cycle, marks_credit_cycle, pabrai

**Falsifiers:**

- peak margins capitalized
- supply response ignored
- replacement cost used for assets that cannot earn their cost of capital

## Economic claim

Per-share claims use fully diluted shares from valuation.inputs.
