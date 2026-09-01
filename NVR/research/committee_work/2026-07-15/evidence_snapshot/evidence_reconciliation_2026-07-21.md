# NVR valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component. Authorized evidence packet per `research_agent_manifest.json`.

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `homebuilding_owner_earnings` | legacy_sensitivity | owner_earnings_reinvestment_dcf@1.0 | bounded_estimate | $5,600 |
| `mortgage_banking` | legacy_sensitivity | owner_cash_or_dividend_discount@1.0 | bounded_estimate | $400 |
| `net_surplus_cash` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | $350 |
| `lot_control_and_future_communities` | legacy_sensitivity | risk_adjusted_milestone_value@1.0 | bounded_estimate | $600 |
| `housing_cycle_and_execution_reserve` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | −$400 |

## Gap assessments

### owner_earnings_cycle — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 homebuilding pretax **$1.610B**, consolidated net **$1.340B**, operating cash flow **$1.121B**; backlog **8,448** units; cancellation rate **17%**. |
| source path | `NVR/research/evidence_reconciliation_2026-07-15.json`; NVR 2025 Form 10-K (SEC URL in primary_sources) |
| calculation | After-tax homebuilding **$1.225B** ÷ **2.794M** shares = **$439/sh**; 12.8× capitalization = **$5,600/sh** base (proof graph). |
| remaining uncertainty | Community-level margin and volume distribution through a full housing downturn is not disclosed lot-by-lot. |
| affected components | `homebuilding_owner_earnings`, `housing_cycle_and_execution_reserve` |
| valuation consequence | Peak-year GAAP is anchored; normalization multiple remains judgment bounded by filing earnings power. |
| falsifier | Sustained settlement decline with rising cancellations and deposit impairments above 2025 levels. |

### controlled_lot_inventory — met

| Field | Content |
|---|---|
| status | met |
| evidence | **169,250** finished lots under LPAs (**$920.1M** deposits); **38,200** additional lots under contract (**$42.3M** deposits); net deposit asset **$851.5M** after **$111.0M** allowance; FY2025 impairments **$75.9M**; additional deposit commitments **$733.9M** if milestones met. |
| source path | `NVR/research/evidence_reconciliation_2026-07-15.json` |
| calculation | Incremental lot option base **$600/sh** valued separately from normalized earnings; deposit carrying value not double-counted. |
| remaining uncertainty | No primary lot-by-lot purchase schedule or community opening cadence in the packet. |
| affected components | `lot_control_and_future_communities` |
| valuation consequence | Asymmetric lot-control option sized as incremental claim; overlap key unique. |
| falsifier | Deposit impairments remain elevated or controlled-lot growth fails to convert to profitable openings. |

### surplus_cash — met

| Field | Content |
|---|---|
| status | met |
| evidence | Aggregate cash **$1.916B**; senior notes **$909M**; revolver and mortgage repurchase facility undrawn; gross net cash **$1.007B** (**~$360/sh**). |
| source path | `NVR/research/evidence_reconciliation_2026-07-15.json` |
| calculation | Surplus credit ratio **97%** of gross net cash at base → **$350/sh**; low case **69%**, high **125%** (stress-release upside). |
| remaining uncertainty | Management does not disclose a formal minimum liquidity or stress cash budget. |
| affected components | `net_surplus_cash` |
| valuation consequence | Only a fraction of gross net cash credited; deposits and working capital excluded via ratio. |
| falsifier | Cash falls below modeled operating and deposit needs or revolver usage rises in an ordinary slowdown. |

## Overlap control — met

Unique overlap keys preserved; `double_counting_flags` empty. Lot deposits and normalized homebuilding earnings are separated; surplus cash excludes pledged deposit and mortgage funding needs via the surplus credit ratio.

## Facts vs judgments

**Facts (locked):** FY2025 net income **$1.340B**; homebuilding pretax **$1.610B**; mortgage pretax **$152M**; cash **$1.916B**; senior notes **$909M**; shares **~2.794M**; controlled lots and deposit balances as above; backlog **8,448**; cancellation **17%**; deposit impairments **$75.9M**.

**Judgments (bounded):** Homebuilding capitalization **7.5–18.2×** after-tax filing anchor; mortgage **4.8–15.7×**; surplus credit **69–125%** of gross net cash; incremental lot option **$200–1,200/sh**; cycle reserve **5.5–29.4×** FY2025 impairment proxy.

## Valuation consequence

Proof-complete additive schedule base **~$6,550/sh** vs price **~$6,498** implies roughly **fair value** (**~0.1%** annualized return over seven years at base). Security remains **watch** pending through-cycle normalization and lot-option reconciliation; no human capital decision recorded.
