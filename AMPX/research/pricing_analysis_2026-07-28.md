# AMPX pricing analysis

**As of:** 2026-07-28

**Price:** $10.14

**Decision:** watch_pending_owner_review

## Price versus component value

| Component | Method | Low | Base | High |
|---|---|---:|---:|---:|
| Silicon-anode battery owner-cash engine | owner_cash_or_dividend_discount | $2.21 | $6.42 | $17.72 |
| Aviation and EV design-win runway | owner_earnings_reinvestment_dcf | $0.50 | $2.50 | $8.00 |
| Net cash claims | net_asset_value | $0.92 | $0.92 | $0.92 |
| Scale-up and competition reserve | midcycle_capacity_value | $-6.00 | $-2.00 | $-0.50 |
| **Total** |  | **$0.00** | **$7.84** | **$26.14** |

Base value versus price: **-22.7%**. Current or contracted operating and financial assets support approximately **$7.84** per share; the market asks investors to pay another **$2.30** for growth, inventory, projects, or scarcity.


## Economic value versus accounting value

**GAAP role:** cross_check

**Accounting reference:** AMPX/investor-documents/sec-edgar/10-K_20260306_rpt20251231_acc0001899287_26_000015.htm; AMPX/research/evidence/filing_facts_2026-07-25.json

A complete comparable NAV is not asserted; comparable marks are used only where the economic asset and ownership claim are sufficiently defined.

| Economic component | Comparable basis | Comparable base / share | Risked base / share | Overlap control |
|---|---|---:|---:|---|
| Silicon-anode battery owner-cash engine | owner_cash_or_dividend_discount proof outputs. | n/a | $6.42 | Unique overlap key core_engine. |
| Aviation and EV design-win runway | owner_earnings_reinvestment_dcf proof outputs. | n/a | $2.50 | Unique overlap key reinvestment_runway. |
| Net cash claims | net_asset_value proof outputs. | n/a | $0.92 | Unique overlap key net_financial_claims. |
| Scale-up and competition reserve | midcycle_capacity_value proof outputs. | n/a | $-2.00 | Unique overlap key cycle_reserve. |

### Deterministic valuation proof

| Economic claim | Method | Comparable | Low / base / high | Risk / timing | Overlap control | Falsifier |
|---|---|---|---:|---|---|---|
| Silicon-anode battery owner-cash engine | owner_cash_or_dividend_discount | not_applicable | $2.21 / $6.42 / $17.72 | n/a | Unique overlap key core_engine. | Primary evidence shows owner cash or capital structure materially worse than low case. |
| Aviation and EV design-win runway | owner_earnings_reinvestment_dcf | not_applicable | $0.50 / $2.50 / $8.00 | n/a | Unique overlap key reinvestment_runway. | Primary evidence shows owner cash or capital structure materially worse than low case. |
| Net cash claims | net_asset_value | not_applicable | $0.92 / $0.92 / $0.92 | n/a | Unique overlap key net_financial_claims. | Primary evidence shows owner cash or capital structure materially worse than low case. |
| Scale-up and competition reserve | midcycle_capacity_value | not_applicable | $-6.00 / $-2.00 / $-0.50 | n/a | Unique overlap key cycle_reserve. | Primary evidence shows owner cash or capital structure materially worse than low case. |

### Investor-wisdom rules applied

- None documented.

### Limitations

- Judgment bands remain widest for runway and cycle reserve.



## What the price implies

At the stated terminal multiple, the price requires approximately **11.9%** constant annual owner-cash growth for seven years. Constant 7-year owner-cash growth with a 18x terminal owner-cash multiple; diagnostic, not forecast.

## Entry prices by required return

These prices are the present value of the explicit seven-year cash-flow and terminal-value scenarios at each hurdle. They are not arbitrary discounts to the current quote.

| Scenario | 10% | 12% | 15% | 20% |
|---|---:|---:|---:|---:|
| Bear | $2.83 | $2.55 | $2.20 | $1.75 |
| Base | $7.49 | $6.69 | $5.68 | $4.38 |
| Bull | $18.33 | $16.28 | $13.70 | $10.40 |

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
