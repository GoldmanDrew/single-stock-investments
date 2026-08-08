# AEHR pricing analysis

**As of:** 2026-07-24

**Price:** $109.89

**Decision:** watch_pending_owner_review

## Price versus component value

| Component | Method | Low | Base | High |
|---|---|---:|---:|---:|
| Mid-cycle burn-in / test systems owner-cash engine | owner_cash_or_dividend_discount | $0.59 | $2.55 | $14.42 |
| Deferred revenue and customer deposit conversion option | risk_adjusted_milestone_value | $0.00 | $11.80 | $35.10 |
| Net cash and financial claims per share | net_asset_value | $0.80 | $1.05 | $1.30 |
| Cycle, customer concentration, and dilution reserve | net_asset_value | $-12.00 | $-6.00 | $-2.00 |
| **Total** |  | **$0.00** | **$9.40** | **$48.82** |

Base value versus price: **-91.4%**. Current or contracted operating and financial assets support approximately **$-2.40** per share; the market asks investors to pay another **$112.29** for growth, inventory, projects, or scarcity.


## Economic value versus accounting value

**GAAP role:** cross_check

**Accounting reference:** FY2025 10-K and Q3 FY2026 10-Q; mid-cycle owner cash normalized on FY2023–FY2024 average free cash flow per share with FY2025 trough excluded from base.

A complete comparable NAV is not asserted; comparable marks are used only where the economic asset and ownership claim are sufficiently defined.

| Economic component | Comparable basis | Comparable base / share | Risked base / share | Overlap control |
|---|---|---:|---:|---|
| Mid-cycle burn-in / test systems owner-cash engine | Owner-cash discount on normalized $0.1632 per share mid-cycle free cash flow per AEHR/investor-documents/sec-edgar/10-K_20250728_rpt20250530_acc0001654954_25_008553.htm. | n/a | $2.55 | Unique overlap key midcycle_burn_in_operations. |
| Deferred revenue and customer deposit conversion option | Risk-adjusted milestone on $1.91M deferred revenue per Q3 FY2026 10-Q. | n/a | $11.80 | Unique overlap key deferred_revenue_milestone_option. |
| Net cash and financial claims per share | Cash $36.9M less no term debt divided by 31.453M diluted shares per Q3 FY2026 10-Q. | n/a | $1.05 | Unique overlap key net_financial_claims. |
| Cycle, customer concentration, and dilution reserve | Reserve for customer pause, $60M ATM dilution overhang, and order lumpiness. | n/a | $-6.00 | Unique overlap key cycle_customer_concentration_reserve. |

### Deterministic valuation proof

| Economic claim | Method | Comparable | Low / base / high | Risk / timing | Overlap control | Falsifier |
|---|---|---|---:|---|---|---|
| Mid-cycle burn-in / test systems owner-cash engine | owner_cash_or_dividend_discount | not_applicable | $0.59 / $2.55 / $14.42 | n/a | Unique overlap key midcycle_burn_in_operations. | Primary evidence shows claim, cash conversion, or cycle path is materially worse than low case. |
| Deferred revenue and customer deposit conversion option | risk_adjusted_milestone_value | not_applicable | $0.00 / $11.80 / $35.10 | p=55.0%; Typical 12-24 month implant system delivery from backlog disclosure (10-K); base realization ~2 years | Unique overlap key deferred_revenue_milestone_option. | Primary evidence shows claim, cash conversion, or cycle path is materially worse than low case. |
| Net cash and financial claims per share | net_asset_value | not_applicable | $0.80 / $1.05 / $1.30 | n/a | Unique overlap key net_financial_claims. | Primary evidence shows claim, cash conversion, or cycle path is materially worse than low case. |
| Cycle, customer concentration, and dilution reserve | net_asset_value | not_applicable | $-12.00 / $-6.00 / $-2.00 | n/a | Unique overlap key cycle_customer_concentration_reserve. | Primary evidence shows claim, cash conversion, or cycle path is materially worse than low case. |

### Investor-wisdom rules applied

- None documented.

### Limitations

- Component schedule is filing-grounded but not committee-approved.
- Mid-cycle owner cash normalization remains [HUMAN REVIEW] vs spot trough cash burn.



## What the price implies

At the stated terminal multiple, the price requires approximately **70.1%** constant annual owner-cash growth for seven years. Constant 7-year owner-cash growth with a 14x terminal owner-cash multiple; diagnostic, not forecast.

## Entry prices by required return

These prices are the present value of the explicit seven-year cash-flow and terminal-value scenarios at each hurdle. They are not arbitrary discounts to the current quote.

| Scenario | 10% | 12% | 15% | 20% |
|---|---:|---:|---:|---:|
| Bear | $1.14 | $1.04 | $0.91 | $0.75 |
| Base | $2.61 | $2.35 | $2.02 | $1.60 |
| Bull | $4.95 | $4.43 | $3.77 | $2.91 |

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
