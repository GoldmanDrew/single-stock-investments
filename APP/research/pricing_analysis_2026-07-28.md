# APP pricing analysis

**As of:** 2026-07-28

**Price:** $520.43

**Decision:** watch_pending_owner_review

## Price versus component value

| Component | Method | Low | Base | High |
|---|---|---:|---:|---:|
| AXON advertising owner-cash engine | owner_cash_or_dividend_discount | $185.98 | $433.25 | $824.24 |
| Recommendation-engine and advertiser expansion runway | owner_earnings_reinvestment_dcf | $20.00 | $80.00 | $180.00 |
| Net cash and long-term debt claims | net_asset_value | $-3.56 | $-3.04 | $-2.52 |
| Competition, privacy, and concentration reserve | midcycle_capacity_value | $-150.00 | $-50.00 | $-15.00 |
| **Total** |  | **$52.42** | **$460.21** | **$986.72** |

Base value versus price: **-11.6%**. Current or contracted operating and financial assets support approximately **$460.21** per share; the market asks investors to pay another **$60.22** for growth, inventory, projects, or scarcity.


## Economic value versus accounting value

**GAAP role:** cross_check

**Accounting reference:** APP/investor-documents/sec-edgar/10-K_20260219_rpt20251231_acc0001751008_26_000010.htm; APP/research/evidence/filing_facts_2026-07-25.json

A complete comparable NAV is not asserted; comparable marks are used only where the economic asset and ownership claim are sufficiently defined.

| Economic component | Comparable basis | Comparable base / share | Risked base / share | Overlap control |
|---|---|---:|---:|---|
| AXON advertising owner-cash engine | owner_cash_or_dividend_discount proof outputs. | n/a | $433.25 | Unique overlap key core_engine. |
| Recommendation-engine and advertiser expansion runway | owner_earnings_reinvestment_dcf proof outputs. | n/a | $80.00 | Unique overlap key reinvestment_runway. |
| Net cash and long-term debt claims | net_asset_value proof outputs. | n/a | $-3.04 | Unique overlap key net_financial_claims. |
| Competition, privacy, and concentration reserve | midcycle_capacity_value proof outputs. | n/a | $-50.00 | Unique overlap key cycle_reserve. |

### Deterministic valuation proof

| Economic claim | Method | Comparable | Low / base / high | Risk / timing | Overlap control | Falsifier |
|---|---|---|---:|---|---|---|
| AXON advertising owner-cash engine | owner_cash_or_dividend_discount | not_applicable | $185.98 / $433.25 / $824.24 | n/a | Unique overlap key core_engine. | Primary evidence shows owner cash or capital structure materially worse than low case. |
| Recommendation-engine and advertiser expansion runway | owner_earnings_reinvestment_dcf | not_applicable | $20.00 / $80.00 / $180.00 | n/a | Unique overlap key reinvestment_runway. | Primary evidence shows owner cash or capital structure materially worse than low case. |
| Net cash and long-term debt claims | net_asset_value | not_applicable | $-3.56 / $-3.04 / $-2.52 | n/a | Unique overlap key net_financial_claims. | Primary evidence shows owner cash or capital structure materially worse than low case. |
| Competition, privacy, and concentration reserve | midcycle_capacity_value | not_applicable | $-150.00 / $-50.00 / $-15.00 | n/a | Unique overlap key cycle_reserve. | Primary evidence shows owner cash or capital structure materially worse than low case. |

### Investor-wisdom rules applied

- None documented.

### Limitations

- Judgment bands remain widest for runway and cycle reserve.



## What the price implies

At the stated terminal multiple, the price requires approximately **3.7%** constant annual owner-cash growth for seven years. Constant 7-year owner-cash growth with a 28x terminal owner-cash multiple; diagnostic, not forecast.

## Entry prices by required return

These prices are the present value of the explicit seven-year cash-flow and terminal-value scenarios at each hurdle. They are not arbitrary discounts to the current quote.

| Scenario | 10% | 12% | 15% | 20% |
|---|---:|---:|---:|---:|
| Bear | $241.55 | $216.63 | $185.01 | $144.31 |
| Base | $420.67 | $375.09 | $317.46 | $243.65 |
| Bull | $668.50 | $594.19 | $500.40 | $380.61 |

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
