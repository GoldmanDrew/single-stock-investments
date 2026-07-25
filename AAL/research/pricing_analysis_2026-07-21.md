# AAL pricing analysis

**As of:** 2026-07-21

**Price:** $15.14

**Decision:** watch_pending_owner_review

## Price versus component value

| Component | Method | Low | Base | High |
|---|---|---:|---:|---:|
| Mid-cycle U.S. network passenger and cargo operations | owner_cash_or_dividend_discount | $21.17 | $33.88 | $49.41 |
| AAdvantage co-brand and partner loyalty economics | risk_adjusted_milestone_value | $0.00 | $8.00 | $20.00 |
| Net cash and debt claims on common equity | net_asset_value | $-44.87 | $-42.67 | $-40.26 |
| Fuel, recession, and leverage stress reserve | net_asset_value | $-18.00 | $-9.00 | $-3.00 |
| **Total** |  | **$0.00** | **$0.00** | **$26.15** |

Base value versus price: **-100.0%**. Current or contracted operating and financial assets support approximately **$-17.79** per share; the market asks investors to pay another **$32.93** for growth, inventory, projects, or scarcity.


## Economic value versus accounting value

**GAAP role:** cross_check

**Accounting reference:** FY2025 10-K and Q1 2026 10-Q filing extracts; GAAP net income is cross-check only for levered airline.

A complete comparable NAV is not asserted; comparable marks are used only where the economic asset and ownership claim are sufficiently defined.

| Economic component | Comparable basis | Comparable base / share | Risked base / share | Overlap control |
|---|---|---:|---:|---|
| Mid-cycle U.S. network passenger and cargo operations | Proof outputs {'low': 21.1701, 'base': 33.88, 'high': 49.4099}; see calculation_proof graph. | n/a | $33.88 | Unique overlap key midcycle_passenger_network. |
| AAdvantage co-brand and partner loyalty economics | Proof outputs {'low': 0.0, 'base': 8.0, 'high': 20.0}; see calculation_proof graph. | n/a | $8.00 | Unique overlap key aadvantage_co_brand_option. |
| Net cash and debt claims on common equity | Proof outputs {'low': -44.8747, 'base': -42.6725, 'high': -40.2649}; see calculation_proof graph. | n/a | $-42.67 | Unique overlap key net_financial_claims. |
| Fuel, recession, and leverage stress reserve | Proof outputs {'low': -18.0, 'base': -9.0, 'high': -3.0001}; see calculation_proof graph. | n/a | $-9.00 | Unique overlap key cycle_leverage_reserve. |

### Deterministic valuation proof

| Economic claim | Method | Comparable | Low / base / high | Risk / timing | Overlap control | Falsifier |
|---|---|---|---:|---|---|---|
| Mid-cycle U.S. network passenger and cargo operations | owner_cash_or_dividend_discount | not_applicable | $21.17 / $33.88 / $49.41 | n/a | Unique overlap key midcycle_passenger_network. | Primary evidence shows claim, cash conversion, or capital structure is materially worse than low case. |
| AAdvantage co-brand and partner loyalty economics | risk_adjusted_milestone_value | not_applicable | $0.00 / $8.00 / $20.00 | risked range; Co-brand and partner mile contracts renew over 3 to 7 years; base case assumes continued monetization through FY2030. | Unique overlap key aadvantage_co_brand_option. | Primary evidence shows claim, cash conversion, or capital structure is materially worse than low case. |
| Net cash and debt claims on common equity | net_asset_value | not_applicable | $-44.87 / $-42.67 / $-40.26 | n/a | Unique overlap key net_financial_claims. | Primary evidence shows claim, cash conversion, or capital structure is materially worse than low case. |
| Fuel, recession, and leverage stress reserve | net_asset_value | not_applicable | $-18.00 / $-9.00 / $-3.00 | n/a | Unique overlap key cycle_leverage_reserve. | Primary evidence shows claim, cash conversion, or capital structure is materially worse than low case. |

### Investor-wisdom rules applied

- None documented.

### Limitations

- AAdvantage standalone value is judgment-based pending issuer disclosure.
- Levered equity stub; component sum can be negative while market prices recovery.



## What the price implies

At the stated terminal multiple, the price requires approximately **-19.0%** constant annual owner-cash growth for seven years. Constant 7-year owner-cash growth with a 7x terminal owner-cash multiple; diagnostic, not forecast.

## Entry prices by required return

These prices are the present value of the explicit seven-year cash-flow and terminal-value scenarios at each hurdle. They are not arbitrary discounts to the current quote.

| Scenario | 10% | 12% | 15% | 20% |
|---|---:|---:|---:|---:|
| Bear | $18.62 | $17.16 | $15.27 | $12.76 |
| Base | $30.20 | $27.53 | $24.10 | $19.61 |
| Bull | $42.63 | $38.60 | $33.46 | $26.76 |

## Decision explanation

Entry prices were computed mechanically from the routed power-zone profile (Predictable cash-flow security). They are decision inputs, not a decision; the owner must review the scenarios before acting.

**Strongest counter-explanation:** dividend treated as earning power

**Committee routing:** ready_to_assemble — buffett_weschler, hohn, marks_credit_cycle

**Falsifiers:**

- dividend treated as earning power
- growth capital and dilution omitted
- contract renewal or regulatory reset ignored

## Economic claim

Per-share claims use fully diluted shares from valuation.inputs.
