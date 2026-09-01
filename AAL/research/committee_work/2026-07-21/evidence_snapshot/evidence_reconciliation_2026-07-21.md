# AAL valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component. Authorized evidence packet per `research_agent_manifest.json` (2026-07-21).

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `midcycle_passenger_network` | unpriced | owner_cash_or_dividend_discount@1.0 | bounded_estimate | $33.88 |
| `aadvantage_co_brand_option` | unpriced | risk_adjusted_milestone_value@1.0 | bounded_estimate | $8.00 |
| `net_financial_claims` | unpriced | net_asset_value@1.0 | bounded_estimate | −$42.67 |
| `cycle_leverage_reserve` | unpriced | net_asset_value@1.0 | bounded_estimate | −$9.00 |

## Acceptance tests

### Component ownership map — met

| Field | Content |
|---|---|
| status | met |
| evidence | Four additive components with unique overlap keys: mid-cycle passenger network, AAdvantage co-brand option, net financial claims, cycle/leverage reserve. No embedded double-count. |
| source path | `AAL/research/valuation.json` → `component_valuation.components[]` |
| calculation | Material claims mapped once per `overlap_key`; sum base **−$9.79/sh** = $33.88 + $8.00 − $42.67 − $9.00. |
| remaining uncertainty | AAdvantage standalone economics remain judgment-heavy; loyalty miles redeemed in ticket revenue are embedded in network cash. |
| affected components | All four additive blockers |
| valuation consequence | Ownership map complete; proofs attached. |
| falsifier | New filing reveals an unmodeled material claim or duplicate overlap key. |

### Primary owner-cash / NAV bridge — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 operating cash flow **$3,099M**; operating income **$1,467M** (prior **$2,614M**); Q1 2026 diluted **~658.6M** shares ($382M net income / $0.58 EPS). |
| source path | `AAL/investor-documents/sec-edgar/10-K_20260218_rpt20251231_acc0000006201_26_000014.htm`, `10-Q_20260423_rpt20260331_acc0000006201_26_000032.htm` |
| calculation | Network proof: $4.70/sh OCF × 7.2× capitalization ≈ **$33.88/sh**. Net financial: ($902M cash − $29,007M debt) / 658.6M ≈ **−$42.67/sh**. |
| remaining uncertainty | Capitalization multiple and co-brand milestone band are bounded judgments, not filing marks. |
| affected components | `midcycle_passenger_network`, `net_financial_claims`, `aadvantage_co_brand_option` |
| valuation consequence | Filing-locked facts anchor proofs; price stub replaced by component schedule. |
| falsifier | Trailing four-quarter operating cash flow per share falls below **$3.50** for four quarters without offsetting debt reduction. |

### Downside and capital claims — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 cash **$902M**; long-term debt and leases **$25,254M** plus current **$3,753M**; capex **$3,779M** exceeded OCF; stockholders' equity **$3,727M**. |
| source path | `10-K_20260218` balance sheet and cash-flow extracts |
| calculation | Net debt **$28,105M** filing-locked; cycle reserve base **−$9.00/sh** separate from net financial claim. |
| remaining uncertainty | Fuel volatility and recession severity remain widest bands on reserve component. |
| affected components | `net_financial_claims`, `cycle_leverage_reserve` |
| valuation consequence | Downside claims reconciled to filings; reserve separate from network capitalization. |
| falsifier | Total debt rises above **$32B** without proportional operating income recovery for two consecutive quarters. |

### Overlap control — met

| Field | Content |
|---|---|
| status | met |
| evidence | Unique overlap keys; AAdvantage miles in ticket revenue embedded in network OCF, not double-counted in co-brand option. |
| source path | `AAL/research/valuation.json` |
| calculation | No additive overlap key duplicates; `double_counting_flags` empty in authorized evidence. |
| remaining uncertainty | None on overlap map. |
| affected components | All |
| valuation consequence | Component sum is additive once. |
| falsifier | New component added without unique overlap_key. |

## Facts vs judgments

**Facts (locked):** FY2025 revenue **$54,633M**, operating income **$1,467M**, net income **$111M**, operating cash flow **$3,099M**, capital spending **$3,779M**; cash **$902M**; total debt and lease obligations **$29,007M**; Q1 2026 net income **$382M**, diluted EPS **$0.58**.

**Judgments (bounded):** Owner-cash capitalization multiple 4.5–10.5×; co-brand milestone **$0–$20/sh**; cycle reserve **−$18 to −$3/sh**.

## Valuation consequence

Proof-complete additive schedule base case **−$9.79 per share** vs price **~$15.14** implies the market prices equity recovery and deleveraging optionality beyond filing-locked mid-cycle components. Lawrence seven-year base and synthesis IRR are computed mechanically in Phase 3. Security remains **watch**; no human capital decision recorded.
