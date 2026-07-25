# ACLS pricing analysis

**As of:** 2026-07-22

**Price:** $131.70

**Decision:** watch_pending_owner_review

## Price versus component value

| Component | Method | Low | Base | High |
|---|---|---:|---:|---:|
| Mid-cycle ion implant systems and services owner-cash engine | owner_cash_or_dividend_discount | $29.45 | $59.80 | $99.87 |
| Systems backlog and deferred revenue conversion option | risk_adjusted_milestone_value | $0.00 | $12.11 | $36.00 |
| Net cash and debt-free balance-sheet claims on common equity | net_asset_value | $3.20 | $4.60 | $5.80 |
| WFE downcycle, China exposure, and backlog-decline reserve | net_asset_value | $-42.00 | $-20.00 | $-8.00 |
| **Total** |  | **$0.00** | **$56.51** | **$133.67** |

Base value versus price: **-57.1%**. Current or contracted operating and financial assets support approximately **$44.40** per share; the market asks investors to pay another **$87.30** for growth, inventory, projects, or scarcity.


## Economic value versus accounting value

**GAAP role:** cross_check

**Accounting reference:** FY2025 10-K and Q1 2026 10-Q; mid-cycle owner cash normalized across FY2023-FY2025.

A complete comparable NAV is not asserted; comparable marks are used only where the economic asset and ownership claim are sufficiently defined.

| Economic component | Comparable basis | Comparable base / share | Risked base / share | Overlap control |
|---|---|---:|---:|---|
| Mid-cycle ion implant systems and services owner-cash engine | Proof outputs {'low': 29.45, 'base': 59.8, 'high': 99.87}; see calculation_proof graph. | n/a | $59.80 | Unique overlap key midcycle_implant_operations. |
| Systems backlog and deferred revenue conversion option | Proof outputs {'low': 0.0, 'base': 22.0001, 'high': 48.0011}; see calculation_proof graph. | n/a | $12.11 | Unique overlap key systems_backlog_conversion_option. |
| Net cash and debt-free balance-sheet claims on common equity | Proof outputs {'low': 3.1988, 'base': 4.6009, 'high': 5.8008}; see calculation_proof graph. | n/a | $4.60 | Unique overlap key net_financial_claims. |
| WFE downcycle, China exposure, and backlog-decline reserve | Proof outputs {'low': -42.0014, 'base': -20.0013, 'high': -7.9986}; see calculation_proof graph. | n/a | $-20.00 | Unique overlap key cycle_and_concentration_reserve. |

### Deterministic valuation proof

| Economic claim | Method | Comparable | Low / base / high | Risk / timing | Overlap control | Falsifier |
|---|---|---|---:|---|---|---|
| Mid-cycle ion implant systems and services owner-cash engine | owner_cash_or_dividend_discount | not_applicable | $29.45 / $59.80 / $99.87 | n/a | Unique overlap key midcycle_implant_operations. | Primary evidence shows claim, cash conversion, or cycle path is materially worse than low case. |
| Systems backlog and deferred revenue conversion option | risk_adjusted_milestone_value | not_applicable | $0.00 / $12.11 / $36.00 | p=55.0%; Typical 12-24 month implant system delivery from backlog disclosure (10-K); base realization ~2 years | Unique overlap key systems_backlog_conversion_option. | Primary evidence shows claim, cash conversion, or cycle path is materially worse than low case. |
| Net cash and debt-free balance-sheet claims on common equity | net_asset_value | not_applicable | $3.20 / $4.60 / $5.80 | n/a | Unique overlap key net_financial_claims. | Primary evidence shows claim, cash conversion, or cycle path is materially worse than low case. |
| WFE downcycle, China exposure, and backlog-decline reserve | net_asset_value | not_applicable | $-42.00 / $-20.00 / $-8.00 | n/a | Unique overlap key cycle_and_concentration_reserve. | Primary evidence shows claim, cash conversion, or cycle path is materially worse than low case. |

### Investor-wisdom rules applied

- None documented.

### Limitations

- None documented.



## What the price implies

At the stated terminal multiple, the price requires approximately **8.9%** constant annual owner-cash growth for seven years. Constant 7-year owner-cash growth with a 16x terminal owner-cash multiple; diagnostic, not forecast.

## Entry prices by required return

These prices are the present value of the explicit seven-year cash-flow and terminal-value scenarios at each hurdle. They are not arbitrary discounts to the current quote.

| Scenario | 10% | 12% | 15% | 20% |
|---|---:|---:|---:|---:|
| Bear | $34.20 | $31.03 | $26.97 | $21.69 |
| Base | $54.00 | $48.61 | $41.77 | $32.92 |
| Bull | $75.64 | $67.79 | $57.84 | $45.03 |

## Decision explanation

Entry prices were computed mechanically from the routed power-zone profile (Capital cycle and normalized industry economics). They are decision inputs, not a decision; the owner must review the scenarios before acting.

**Strongest counter-explanation:** peak margins capitalized

**Committee routing:** not_initialized — not initialized

**Falsifiers:**

- peak margins capitalized
- supply response ignored
- replacement cost used for assets that cannot earn their cost of capital

## Economic claim

Per-share claims use fully diluted shares from valuation.inputs.
