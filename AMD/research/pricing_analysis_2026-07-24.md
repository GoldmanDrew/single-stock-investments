# AMD pricing analysis

**As of:** 2026-07-24

**Price:** $549.86

**Decision:** watch_pending_owner_review

## Price versus component value

| Component | Method | Low | Base | High |
|---|---|---:|---:|---:|
| Data Center segment owner cash (EPYC CPUs, Instinct GPUs, AI accelerators) | owner_cash_or_dividend_discount | $58.00 | $72.50 | $88.00 |
| Client and Gaming segment owner cash (Ryzen, Radeon) | owner_cash_or_dividend_discount | $16.00 | $20.80 | $26.00 |
| Embedded segment owner cash (adaptive SoCs, Xilinx FPGAs) | owner_cash_or_dividend_discount | $2.50 | $3.20 | $4.50 |
| Net cash and debt claims on common equity | net_asset_value | $0.98 | $1.95 | $2.93 |
| AI competition, custom ASIC, and foundry capex stress reserve | net_asset_value | $-8.00 | $-2.00 | $0.00 |
| **Total** |  | **$69.48** | **$96.45** | **$121.43** |

Base value versus price: **-82.5%**. Current or contracted operating and financial assets support approximately **$96.45** per share; the market asks investors to pay another **$453.41** for growth, inventory, projects, or scarcity.


## Economic value versus accounting value

**GAAP role:** cross_check

**Accounting reference:** FY2025 10-K: stockholders' equity $63.0B; economic value in normalized owner cash ($3.3741/sh consolidated), not GAAP book alone.

A complete comparable NAV is not asserted; comparable marks are used only where the economic asset and ownership claim are sufficiently defined.

| Economic component | Comparable basis | Comparable base / share | Risked base / share | Overlap control |
|---|---|---:|---:|---|
| Data Center segment owner cash | Owner-cash discount on segment-allocated FY2025 FCF per share ($1.62/sh). | n/a | $72.50 | Unique overlap key data_center_owner_cash. |
| Client and Gaming segment owner cash | Owner-cash discount on segment-allocated FY2025 FCF per share ($1.42/sh). | n/a | $20.80 | Unique overlap key client_gaming_owner_cash. |
| Embedded segment owner cash | Owner-cash discount on segment-allocated FY2025 FCF per share ($0.34/sh). | n/a | $3.20 | Unique overlap key embedded_owner_cash. |
| Net cash and debt claims on common equity | Net asset value on FY2025 filing-locked cash less debt. | n/a | $1.95 | Unique overlap key net_financial_claims. |
| AI competition, custom ASIC, and foundry capex stress reserve | Bounded negative reserve; not full enterprise value haircut. | n/a | $-2.00 | Unique overlap key ai_competition_and_capex_reserve. |

### Deterministic valuation proof

| Economic claim | Method | Comparable | Low / base / high | Risk / timing | Overlap control | Falsifier |
|---|---|---|---:|---|---|---|
| EPYC server CPUs and Instinct GPU AI accelerator normalized owner cash | owner_cash_or_dividend_discount | not_applicable | $58.00 / $72.50 / $88.00 | n/a | Unique overlap key data_center_owner_cash. | Primary evidence shows claim, cash conversion, or capital structure is materially worse than low case. |
| Ryzen PC and Radeon gaming/console normalized owner cash | owner_cash_or_dividend_discount | not_applicable | $16.00 / $20.80 / $26.00 | n/a | Unique overlap key client_gaming_owner_cash. | Primary evidence shows claim, cash conversion, or capital structure is materially worse than low case. |
| Xilinx adaptive SoC and embedded FPGA normalized owner cash | owner_cash_or_dividend_discount | not_applicable | $2.50 / $3.20 / $4.50 | n/a | Unique overlap key embedded_owner_cash. | Primary evidence shows claim, cash conversion, or capital structure is materially worse than low case. |
| Net corporate liquidity after long-term debt | net_asset_value | not_applicable | $0.98 / $1.95 / $2.93 | n/a | Unique overlap key net_financial_claims. | Primary evidence shows claim, cash conversion, or capital structure is materially worse than low case. |
| NVIDIA CUDA moat, hyperscaler custom silicon, foundry prepayment timing | net_asset_value | not_applicable | $-8.00 / $-2.00 / $0.00 | n/a | Unique overlap key ai_competition_and_capex_reserve. | Primary evidence shows claim, cash conversion, or capital structure is materially worse than low case. |

### Investor-wisdom rules applied

- None documented.

### Limitations

- Segment FCF not separately disclosed; consolidated FCF allocated by revenue share.
- AI accelerator share gains versus NVIDIA remain judgment bands.



## What the price implies

At the stated terminal multiple, the price requires approximately **31.9%** constant annual owner-cash growth for seven years. Constant 7-year owner-cash growth with a 20x terminal owner-cash multiple; diagnostic, not forecast.

## Entry prices by required return

These prices are the present value of the explicit seven-year cash-flow and terminal-value scenarios at each hurdle. They are not arbitrary discounts to the current quote.

| Scenario | 10% | 12% | 15% | 20% |
|---|---:|---:|---:|---:|
| Bear | $60.30 | $54.21 | $46.48 | $36.51 |
| Base | $87.09 | $77.94 | $66.34 | $51.44 |
| Bull | $135.04 | $120.35 | $101.79 | $78.01 |

## Decision explanation

Entry prices were computed mechanically from the routed power-zone profile (High-return compounder). They are decision inputs, not a decision; the owner must review the scenarios before acting.

**Strongest counter-explanation:** growth projected without its capital cost

**Committee routing:** round_one_open — buffett_weschler, hohn, munger

**Falsifiers:**

- growth projected without its capital cost
- stock compensation or acquisitions omitted
- terminal value unsupported by a durable mechanism

## Economic claim

Per-share claims use fully diluted shares from valuation.inputs.
