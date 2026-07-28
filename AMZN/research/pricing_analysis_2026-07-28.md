# AMZN pricing analysis

**As of:** 2026-07-28

**Price:** $249.99

**Decision:** watch_pending_owner_review

## Price versus component value

| Component | Method | Low | Base | High |
|---|---|---:|---:|---:|
| Retail, AWS, and ads owner-cash engine | owner_cash_or_dividend_discount | $83.16 | $165.03 | $268.61 |
| AWS/AI and advertising reinvestment runway | owner_earnings_reinvestment_dcf | $10.00 | $40.00 | $90.00 |
| Net cash and long-term debt claims | net_asset_value | $2.15 | $2.39 | $2.63 |
| Capex intensity and competition reserve | midcycle_capacity_value | $-60.00 | $-20.00 | $-5.00 |
| **Total** |  | **$35.31** | **$187.42** | **$356.24** |

Base value versus price: **-25.0%**. Current or contracted operating and financial assets support approximately **$187.42** per share; the market asks investors to pay another **$62.57** for growth, inventory, projects, or scarcity.


## Economic value versus accounting value

**GAAP role:** cross_check

**Accounting reference:** AMZN/investor-documents/sec-edgar/10-K_20260206_rpt20251231_acc0001018724_26_000004.htm; AMZN/research/evidence/filing_facts_2026-07-10.json

A complete comparable NAV is not asserted; comparable marks are used only where the economic asset and ownership claim are sufficiently defined.

| Economic component | Comparable basis | Comparable base / share | Risked base / share | Overlap control |
|---|---|---:|---:|---|
| Retail, AWS, and ads owner-cash engine | owner_cash_or_dividend_discount proof outputs. | n/a | $165.03 | Unique overlap key core_engine. |
| AWS/AI and advertising reinvestment runway | owner_earnings_reinvestment_dcf proof outputs. | n/a | $40.00 | Unique overlap key reinvestment_runway. |
| Net cash and long-term debt claims | net_asset_value proof outputs. | n/a | $2.39 | Unique overlap key net_financial_claims. |
| Capex intensity and competition reserve | midcycle_capacity_value proof outputs. | n/a | $-20.00 | Unique overlap key cycle_reserve. |

### Deterministic valuation proof

| Economic claim | Method | Comparable | Low / base / high | Risk / timing | Overlap control | Falsifier |
|---|---|---|---:|---|---|---|
| Retail, AWS, and ads owner-cash engine | owner_cash_or_dividend_discount | not_applicable | $83.16 / $165.03 / $268.61 | n/a | Unique overlap key core_engine. | Primary evidence shows owner cash or capital structure materially worse than low case. |
| AWS/AI and advertising reinvestment runway | owner_earnings_reinvestment_dcf | not_applicable | $10.00 / $40.00 / $90.00 | n/a | Unique overlap key reinvestment_runway. | Primary evidence shows owner cash or capital structure materially worse than low case. |
| Net cash and long-term debt claims | net_asset_value | not_applicable | $2.15 / $2.39 / $2.63 | n/a | Unique overlap key net_financial_claims. | Primary evidence shows owner cash or capital structure materially worse than low case. |
| Capex intensity and competition reserve | midcycle_capacity_value | not_applicable | $-60.00 / $-20.00 / $-5.00 | n/a | Unique overlap key cycle_reserve. | Primary evidence shows owner cash or capital structure materially worse than low case. |

### Investor-wisdom rules applied

- None documented.

### Limitations

- Judgment bands remain widest for runway and cycle reserve.



## What the price implies

At the stated terminal multiple, the price requires approximately **6.6%** constant annual owner-cash growth for seven years. Constant 7-year owner-cash growth with a 24x terminal owner-cash multiple; diagnostic, not forecast.

## Entry prices by required return

These prices are the present value of the explicit seven-year cash-flow and terminal-value scenarios at each hurdle. They are not arbitrary discounts to the current quote.

| Scenario | 10% | 12% | 15% | 20% |
|---|---:|---:|---:|---:|
| Bear | $99.33 | $89.20 | $76.35 | $59.78 |
| Base | $151.91 | $135.72 | $115.23 | $88.94 |
| Bull | $208.94 | $186.12 | $157.29 | $120.41 |

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
