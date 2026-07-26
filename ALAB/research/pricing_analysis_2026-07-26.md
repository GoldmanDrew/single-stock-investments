# ALAB pricing analysis

**As of:** 2026-07-26

**Price:** $309.09

**Decision:** watch_pending_owner_review

## Price versus component value

| Component | Method | Low | Base | High |
|---|---|---:|---:|---:|
| Connectivity semiconductor owner-cash engine | owner_cash_or_dividend_discount | $31.82 | $88.19 | $231.29 |
| AI rack and PCIe/Ethernet attach runway | owner_earnings_reinvestment_dcf | $5.00 | $25.00 | $60.00 |
| Net cash claims | net_asset_value | $1.01 | $1.01 | $1.01 |
| Competition and semi-cycle reserve | midcycle_capacity_value | $-80.00 | $-30.00 | $-8.00 |
| **Total** |  | **$0.00** | **$84.20** | **$284.30** |

Base value versus price: **-72.8%**. Current or contracted operating and financial assets support approximately **$84.20** per share; the market asks investors to pay another **$224.89** for growth, inventory, projects, or scarcity.


## Economic value versus accounting value

**GAAP role:** cross_check

**Accounting reference:** ALAB/investor-documents/sec-edgar/10-K_20260220_rpt20251231_acc0001736297_26_000010.htm; ALAB/research/evidence/filing_facts_2026-07-25.json

A complete comparable NAV is not asserted; comparable marks are used only where the economic asset and ownership claim are sufficiently defined.

| Economic component | Comparable basis | Comparable base / share | Risked base / share | Overlap control |
|---|---|---:|---:|---|
| Connectivity semiconductor owner-cash engine | owner_cash_or_dividend_discount proof outputs. | n/a | $88.19 | Unique overlap key core_engine. |
| AI rack and PCIe/Ethernet attach runway | owner_earnings_reinvestment_dcf proof outputs. | n/a | $25.00 | Unique overlap key reinvestment_runway. |
| Net cash claims | net_asset_value proof outputs. | n/a | $1.01 | Unique overlap key net_financial_claims. |
| Competition and semi-cycle reserve | midcycle_capacity_value proof outputs. | n/a | $-30.00 | Unique overlap key cycle_reserve. |

### Deterministic valuation proof

| Economic claim | Method | Comparable | Low / base / high | Risk / timing | Overlap control | Falsifier |
|---|---|---|---:|---|---|---|
| Connectivity semiconductor owner-cash engine | owner_cash_or_dividend_discount | not_applicable | $31.82 / $88.19 / $231.29 | n/a | Unique overlap key core_engine. | Primary evidence shows owner cash or capital structure materially worse than low case. |
| AI rack and PCIe/Ethernet attach runway | owner_earnings_reinvestment_dcf | not_applicable | $5.00 / $25.00 / $60.00 | n/a | Unique overlap key reinvestment_runway. | Primary evidence shows owner cash or capital structure materially worse than low case. |
| Net cash claims | net_asset_value | not_applicable | $1.01 / $1.01 / $1.01 | n/a | Unique overlap key net_financial_claims. | Primary evidence shows owner cash or capital structure materially worse than low case. |
| Competition and semi-cycle reserve | midcycle_capacity_value | not_applicable | $-80.00 / $-30.00 / $-8.00 | n/a | Unique overlap key cycle_reserve. | Primary evidence shows owner cash or capital structure materially worse than low case. |

### Investor-wisdom rules applied

- None documented.

### Limitations

- XBRL values treated as thousands; capex not tagged; share count from NI/EPS.
- Price embeds large growth expectations; cycle reserve is wide.



## What the price implies

At the stated terminal multiple, the price requires approximately **28.1%** constant annual owner-cash growth for seven years. Constant 7-year owner-cash growth with a 30x terminal owner-cash multiple; diagnostic, not forecast.

## Entry prices by required return

These prices are the present value of the explicit seven-year cash-flow and terminal-value scenarios at each hurdle. They are not arbitrary discounts to the current quote.

| Scenario | 10% | 12% | 15% | 20% |
|---|---:|---:|---:|---:|
| Bear | $36.81 | $32.98 | $28.13 | $21.89 |
| Base | $90.69 | $80.65 | $67.98 | $51.78 |
| Bull | $222.45 | $197.09 | $165.13 | $124.42 |

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
