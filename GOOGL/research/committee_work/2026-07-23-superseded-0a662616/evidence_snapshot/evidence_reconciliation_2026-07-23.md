# GOOGL valuation evidence reconciliation — 2026-07-23

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component. Evidence packet authorized 2026-07-23 per `research_agent_manifest.json` (hash `d5cc278f…8020a2`).

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `primary_operating_segment` | bounded_estimate | owner_cash_or_dividend_discount@1.0 | bounded_estimate | $200.66 |
| `secondary_operating_segments` | bounded_estimate | owner_cash_or_dividend_discount@1.0 | bounded_estimate | $100.35 |
| `strategic_option` | bounded_estimate | risk_adjusted_milestone_value@1.0 | bounded_estimate | $16.15 |
| `net_claims_and_reserve` | bounded_estimate | net_asset_value@1.0 | bounded_estimate | $30.88 |

## Acceptance tests

### Component ownership map — met

| Field | Content |
|---|---|
| status | met |
| evidence | Four non-overlapping overlap keys map one diluted share claim: Services owner cash, Cloud owner cash, Other Bets option, net cash plus AI-capital reserve. |
| source path | `GOOGL/research/valuation.json` → `component_valuation.components[]`; `economic_value_analysis.ownership_waterfall` |
| calculation | Each component `overlap_key` unique; `double_counting_flags` empty; Alphabet-level R&D drag excluded from additive schedule. |
| remaining uncertainty | Segment proofs capitalize after-tax OI; Lawrence consolidated path still uses FY2025 FCF per share. |
| affected components | All four |
| valuation consequence | Ownership map complete for universal contract at decision_grade. |
| falsifier | New filing shows material claim (e.g., separate chip revenue line) without unique overlap_key. |

### Primary cash / owner-cash bridge — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 10-K: OCF **$125,299M**, capex **$52,500M**, owner FCF **~$72,799M**; segment OI Services **$139,400M**, Cloud **$13,900M**; Q1 2026 Cloud revenue **+63%** YoY (`10-Q_20260430`, `8-K_20260429`). |
| source path | `GOOGL/investor-documents/sec-edgar/10-K_20260205_rpt20251231_acc0001652044_26_000018.htm` |
| calculation | Consolidated bridge: ($125,299M − $52,500M) ÷ 12,447M = **$5.85/sh** Lawrence FCF₀. Services proof: $139,400M × 0.79 × 22.68× ÷ 12,447M = **$200.66/sh**. Cloud proof: $13,900M × 0.79 × 113.75× ÷ 12,447M = **$100.35/sh**. |
| remaining uncertainty | Segment OI × multiple proxies approximate owner cash; full segment DCF trees remain sensitivity only. |
| affected components | `primary_operating_segment`, `secondary_operating_segments` |
| valuation consequence | Filing-locked OCF/capex and segment OI reproduce low/base/high proofs with causal falsifiers. |
| falsifier | FY2026 segment OI mix shifts >10pp without matching Cloud revenue growth in filings. |

### Downside and capital claims — met

| Field | Content |
|---|---|
| status | met |
| evidence | Cash + STI **$95,657M**; long-term debt **$10,883M**; 2026 capex guide **$180–190B** in Q1 materials; Other Bets loss **$7,500M** FY2025. |
| source path | `GOOGL/investor-documents/sec-edgar/10-K_20260205_rpt20251231_acc0001652044_26_000018.htm`; `10-Q_20260430` |
| calculation | Net cash: ($95,657M − $10,883M) = **$84,774M** (**$6.81/sh**). Base reserve/release: +$299,588M capex normalization → **$30.88/sh**. Low reserve **−$805,452M** → **−$57.90/sh**. Other Bets base: ($3,000,000M × 0.082 − $7,500M × 6 yr) ÷ 12,447M = **$16.15/sh**. |
| remaining uncertainty | Capex normalization and Waymo success probability remain explicit judgments with monitoring triggers. |
| affected components | `net_claims_and_reserve`, `strategic_option` |
| valuation consequence | Debt, cash, dilution reserve, and option burden bounded with probability, timing, and failure value in proofs. |
| falsifier | 2026–2027 FCF per share flat or down vs FY2025 with no capex guide reduction; Other Bets losses accelerate >20% YoY for two years. |

### Component proof completeness — met

| Field | Content |
|---|---|
| status | met |
| evidence | All four additive components carry valid `calculation_proof` with approved `method_id@1.0`; validation passes with zero calculation errors. |
| source path | `GOOGL/research/valuation.json` → `component_valuation.components[]` |
| calculation | Proof sum (base): $200.66 + $100.35 + $16.15 + $30.88 = **$348.04/sh** vs price **~$386**. |
| remaining uncertainty | Cloud multiple and capex normalization bands remain wide. |
| affected components | All four |
| valuation consequence | Universal contract advances to **decision_grade** after mechanical refresh. |
| falsifier | Any component proof fails validation or overlap key duplicates. |

## Facts vs judgments

**Facts (locked):** FY2025 revenue **$402.8B**; Services OI **$139.4B**; Cloud OI **$13.9B**; Other Bets loss **$7.5B**; OCF **$125.3B**; capex **$52.5B**; cash + STI **$95.657B**; LT debt **$10.883B**; diluted shares **~12.45B**; Q1 2026 Cloud revenue **+63%** YoY.

**Judgments (bounded):** Services/Cloud owner-cash multiples; Other Bets success probability and gross value; AI capex normalization reserve/release; consolidated Lawrence growth **11%/8%**.

## Valuation consequence

Proof-complete additive schedule base case **~$348 per share** vs market price **~$386** implies roughly **−10%** gap on component economic value. Lawrence consolidated base **−0.97%** per year remains the legacy stance gate reference. Security remains **watch** pending human capital decision; no stance promotion in this agent run.
