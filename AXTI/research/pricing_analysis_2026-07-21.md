# AXTI pricing analysis

**As of:** 2026-07-21

**Price:** $47.23

**Decision:** watch_pending_owner_review

## Price versus component value

| Component | Method | Low | Base | High |
|---|---|---:|---:|---:|
| Specialty substrate manufacturing (InP, GaAs, Ge) at mid-cycle utilization | dcf | $0.80 | $1.40 | $2.20 |
| Cash, cash equivalents and restricted cash | market_value | $0.75 | $0.89 | $0.89 |
| Tongmei Hong Kong listing option (STAR Market withdrawn July 2026) | milestone_nav | $0.00 | $0.50 | $1.50 |
| Tongmei private-equity redemption rights (~$49M gross) | manual | $-1.00 | $-0.75 | $-0.00 |
| Equity dilution reserve (2025–2026 offerings) | manual | $-0.50 | $-0.30 | $-0.00 |
| **Total** |  | **$0.05** | **$1.74** | **$4.59** |

Base value versus price: **-96.3%**. Current or contracted operating and financial assets support approximately **$1.24** per share; the market asks investors to pay another **$45.99** for growth, inventory, projects, or scarcity.


## Economic value versus accounting value

**GAAP role:** cross_check

**Accounting reference:** FY2025 10-K and Q1 2026 10-Q via sec_companyfacts.json; mid-cycle owner cash is normalized [Assumption].

A complete comparable NAV is not asserted; comparable marks are used only where the economic asset and ownership claim are sufficiently defined.

| Economic component | Comparable basis | Comparable base / share | Risked base / share | Overlap control |
|---|---|---:|---:|---|
| Specialty substrate manufacturing (InP, GaAs, Ge) at mid-cycle utilization | Mid-cycle owner cash $7.8M at base × capital-cycle multiple / 65.4M shares; proof in calculation_proof. | n/a | $1.40 | Unique overlap key substrate_operating_cash. |
| Cash, cash equivalents and restricted cash | market_value | n/a | $0.89 | Unique overlap key balance_sheet_cash. |
| Tongmei Hong Kong listing option (STAR Market withdrawn July 2026) | milestone_nav | n/a | $0.50 | Unique overlap key tongmei_listing_catalyst. |
| Tongmei private-equity redemption rights (~$49M gross) | manual | n/a | $-0.75 | Unique overlap key tongmei_pe_redemption. |
| Equity dilution reserve (2025–2026 offerings) | manual | n/a | $-0.30 | Unique overlap key share_count_dilution. |

### Deterministic valuation proof

| Economic claim | Method | Comparable | Low / base / high | Risk / timing | Overlap control | Falsifier |
|---|---|---|---:|---|---|---|
| Specialty substrate manufacturing (InP, GaAs, Ge) at mid-cycle utilization | dcf | not_applicable | $0.80 / $1.40 / $2.20 | n/a | Unique overlap key substrate_operating_cash. | Owner cash, reinvestment economics, or competitive position remains below the low-case path for two reporting periods. |
| Cash, cash equivalents and restricted cash | market_value | not_applicable | $0.75 / $0.89 / $0.89 | n/a | Unique overlap key balance_sheet_cash. | Owner cash, reinvestment economics, or competitive position remains below the low-case path for two reporting periods. |
| Tongmei Hong Kong listing option (STAR Market withdrawn July 2026) | milestone_nav | not_applicable | $0.00 / $0.50 / $1.50 | p=35.0%; HK listing application per 8-K 2026-07-08; base realization 3 years | Unique overlap key tongmei_listing_catalyst. | HK listing fails or PE redemptions drain parent cash before listing |
| Tongmei private-equity redemption rights (~$49M gross) | manual | not_applicable | $-1.00 / $-0.75 / $0.00 | n/a | Unique overlap key tongmei_pe_redemption. | The obligation, financing claim, tax, or realization friction is materially larger than the low-case reserve. |
| Equity dilution reserve (2025–2026 offerings) | manual | not_applicable | $-0.50 / $-0.30 / $0.00 | n/a | Unique overlap key share_count_dilution. | The obligation, financing claim, tax, or realization friction is materially larger than the low-case reserve. |
| Specialty substrate manufacturing (InP, GaAs, Ge) at mid-cycle utilization | manual | not_applicable | $0.00 / $0.00 / $0.00 | n/a | Unique overlap key substrate_operating_cash. | Owner cash, reinvestment economics, or competitive position remains below the low-case path for two reporting periods. |

### Investor-wisdom rules applied

- None documented.

### Limitations

- None documented.



## What the price implies

At the stated terminal multiple, the price requires approximately **60.2%** constant annual owner-cash growth for seven years. Constant 7-year owner-cash growth with a 12x terminal owner-cash multiple; diagnostic, not forecast.

## Entry prices by required return

These prices are the present value of the explicit seven-year cash-flow and terminal-value scenarios at each hurdle. They are not arbitrary discounts to the current quote.

| Scenario | 10% | 12% | 15% | 20% |
|---|---:|---:|---:|---:|
| Bear | $0.88 | $0.80 | $0.71 | $0.58 |
| Base | $1.97 | $1.78 | $1.53 | $1.21 |
| Bull | $3.15 | $2.82 | $2.41 | $1.87 |

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
