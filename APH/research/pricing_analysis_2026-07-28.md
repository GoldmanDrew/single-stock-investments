# APH pricing analysis

**As of:** 2026-07-28

**Price:** $150.51

**Decision:** watch_pending_owner_review

## Price versus component value

| Component | Method | Low | Base | High |
|---|---|---:|---:|---:|
| Interconnect owner-cash engine | owner_cash_or_dividend_discount | $60.75 | $107.75 | $185.80 |
| AI datacom and auto runway | owner_earnings_reinvestment_dcf | $5.00 | $20.00 | $45.00 |
| Net cash and long-term debt claims | net_asset_value | $-3.42 | $-2.82 | $-2.22 |
| Industrial and IT-cycle reserve | midcycle_capacity_value | $-30.00 | $-10.00 | $-2.00 |
| **Total** |  | **$32.33** | **$114.93** | **$226.58** |

Base value versus price: **-23.6%**. Current or contracted operating and financial assets support approximately **$114.93** per share; the market asks investors to pay another **$35.58** for growth, inventory, projects, or scarcity.


## Economic value versus accounting value

**GAAP role:** cross_check

**Accounting reference:** APH/investor-documents/sec-edgar/10-K_20260211_rpt20251231_acc0001104659_26_013549.htm; APH/research/evidence/filing_facts_2026-07-25.json

A complete comparable NAV is not asserted; comparable marks are used only where the economic asset and ownership claim are sufficiently defined.

| Economic component | Comparable basis | Comparable base / share | Risked base / share | Overlap control |
|---|---|---:|---:|---|
| Interconnect owner-cash engine | owner_cash_or_dividend_discount proof outputs. | n/a | $107.75 | Unique overlap key core_engine. |
| AI datacom and auto runway | owner_earnings_reinvestment_dcf proof outputs. | n/a | $20.00 | Unique overlap key reinvestment_runway. |
| Net cash and long-term debt claims | net_asset_value proof outputs. | n/a | $-2.82 | Unique overlap key net_financial_claims. |
| Industrial and IT-cycle reserve | midcycle_capacity_value proof outputs. | n/a | $-10.00 | Unique overlap key cycle_reserve. |

### Deterministic valuation proof

| Economic claim | Method | Comparable | Low / base / high | Risk / timing | Overlap control | Falsifier |
|---|---|---|---:|---|---|---|
| Interconnect owner-cash engine | owner_cash_or_dividend_discount | not_applicable | $60.75 / $107.75 / $185.80 | n/a | Unique overlap key core_engine. | Primary evidence shows owner cash or capital structure materially worse than low case. |
| AI datacom and auto runway | owner_earnings_reinvestment_dcf | not_applicable | $5.00 / $20.00 / $45.00 | n/a | Unique overlap key reinvestment_runway. | Primary evidence shows owner cash or capital structure materially worse than low case. |
| Net cash and long-term debt claims | net_asset_value | not_applicable | $-3.42 / $-2.82 / $-2.22 | n/a | Unique overlap key net_financial_claims. | Primary evidence shows owner cash or capital structure materially worse than low case. |
| Industrial and IT-cycle reserve | midcycle_capacity_value | not_applicable | $-30.00 / $-10.00 / $-2.00 | n/a | Unique overlap key cycle_reserve. | Primary evidence shows owner cash or capital structure materially worse than low case. |

### Investor-wisdom rules applied

- None documented.

### Limitations

- Debt from filing digest: LongTermDebtAndCapitalLeaseObligations 14,564.8 (filing digest)



## What the price implies

At the stated terminal multiple, the price requires approximately **4.1%** constant annual owner-cash growth for seven years. Constant 7-year owner-cash growth with a 24x terminal owner-cash multiple; diagnostic, not forecast.

## Entry prices by required return

These prices are the present value of the explicit seven-year cash-flow and terminal-value scenarios at each hurdle. They are not arbitrary discounts to the current quote.

| Scenario | 10% | 12% | 15% | 20% |
|---|---:|---:|---:|---:|
| Bear | $63.12 | $56.74 | $48.64 | $38.19 |
| Base | $99.21 | $88.70 | $75.39 | $58.30 |
| Bull | $159.70 | $142.20 | $120.10 | $91.84 |

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
