# AMKR pricing analysis

**As of:** 2026-07-28

**Price:** $62.56

**Decision:** watch_pending_owner_review

## Price versus component value

| Component | Method | Low | Base | High |
|---|---|---:|---:|---:|
| OSAT owner-cash engine | owner_cash_or_dividend_discount | $10.28 | $20.52 | $36.04 |
| Advanced packaging / AI attach runway | owner_earnings_reinvestment_dcf | $1.00 | $5.00 | $15.00 |
| Net cash and long-term debt claims | net_asset_value | $0.12 | $0.38 | $0.64 |
| Semi and customer-cycle reserve | midcycle_capacity_value | $-15.00 | $-5.00 | $-1.00 |
| **Total** |  | **$0.00** | **$20.90** | **$50.68** |

Base value versus price: **-66.6%**. Current or contracted operating and financial assets support approximately **$20.90** per share; the market asks investors to pay another **$41.66** for growth, inventory, projects, or scarcity.


## Economic value versus accounting value

**GAAP role:** cross_check

**Accounting reference:** AMKR/investor-documents/sec-edgar/10-K_20260220_rpt20251231_acc0001047127_26_000014.htm; AMKR/research/evidence/filing_facts_2026-07-25.json

A complete comparable NAV is not asserted; comparable marks are used only where the economic asset and ownership claim are sufficiently defined.

| Economic component | Comparable basis | Comparable base / share | Risked base / share | Overlap control |
|---|---|---:|---:|---|
| OSAT owner-cash engine | owner_cash_or_dividend_discount proof outputs. | n/a | $20.52 | Unique overlap key core_engine. |
| Advanced packaging / AI attach runway | owner_earnings_reinvestment_dcf proof outputs. | n/a | $5.00 | Unique overlap key reinvestment_runway. |
| Net cash and long-term debt claims | net_asset_value proof outputs. | n/a | $0.38 | Unique overlap key net_financial_claims. |
| Semi and customer-cycle reserve | midcycle_capacity_value proof outputs. | n/a | $-5.00 | Unique overlap key cycle_reserve. |

### Deterministic valuation proof

| Economic claim | Method | Comparable | Low / base / high | Risk / timing | Overlap control | Falsifier |
|---|---|---|---:|---|---|---|
| OSAT owner-cash engine | owner_cash_or_dividend_discount | not_applicable | $10.28 / $20.52 / $36.04 | n/a | Unique overlap key core_engine. | Primary evidence shows owner cash or capital structure materially worse than low case. |
| Advanced packaging / AI attach runway | owner_earnings_reinvestment_dcf | not_applicable | $1.00 / $5.00 / $15.00 | n/a | Unique overlap key reinvestment_runway. | Primary evidence shows owner cash or capital structure materially worse than low case. |
| Net cash and long-term debt claims | net_asset_value | not_applicable | $0.12 / $0.38 / $0.64 | n/a | Unique overlap key net_financial_claims. | Primary evidence shows owner cash or capital structure materially worse than low case. |
| Semi and customer-cycle reserve | midcycle_capacity_value | not_applicable | $-15.00 / $-5.00 / $-1.00 | n/a | Unique overlap key cycle_reserve. | Primary evidence shows owner cash or capital structure materially worse than low case. |

### Investor-wisdom rules applied

- None documented.

### Limitations

- Judgment bands remain widest for runway and cycle reserve.



## What the price implies

At the stated terminal multiple, the price requires approximately **15.9%** constant annual owner-cash growth for seven years. Constant 7-year owner-cash growth with a 14x terminal owner-cash multiple; diagnostic, not forecast.

## Entry prices by required return

These prices are the present value of the explicit seven-year cash-flow and terminal-value scenarios at each hurdle. They are not arbitrary discounts to the current quote.

| Scenario | 10% | 12% | 15% | 20% |
|---|---:|---:|---:|---:|
| Bear | $11.90 | $10.81 | $9.42 | $7.61 |
| Base | $21.51 | $19.35 | $16.61 | $13.07 |
| Bull | $35.49 | $31.75 | $27.01 | $20.92 |

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
