# AXON valuation evidence reconciliation — 2026-08-05

**Scope:** Close `authorized_evidence.json` contract backfill blockers. Evidence packet per `research_agent_manifest.json`. // pragma: allowlist secret

## Blockers closed

| Blocker | Status | Resolution |
|---------|--------|------------|
| Extreme annualized return requires independent validation | **Closed** | Second-method cross-check: Lawrence owner-cash IRR **-37.9%** and component economic value **-51.6%** both confirm extreme negative return at **$527.48**; reverse DCF requires **>40%** perpetual owner-cash growth at 18x exit |

## Acceptance tests

### Component ownership map — met

| Field | Content |
|---|---|
| status | met |
| evidence | Single additive component `operating_business_and_net_assets` with overlap_key `entire_security`; no double-counting flags |
| source path | `AXON/research/valuation.json` → `component_valuation_results.additive_components[]` |
| calculation | Proof validates at `owner_earnings_reinvestment_dcf@1.0`; base **$3.27/sh** |
| remaining uncertainty | Reinvestment rate and incremental return on capital remain bounded judgments pending segment bridge |
| affected components | `operating_business_and_net_assets` |
| valuation consequence | Ownership map complete; proof hash valid |
| falsifier | New filing shows separate material economic claim without unique overlap_key |

### Primary cash / owner-cash bridge — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 10-K: OCF **$211.3M**, capex **$136.3M**, normalized owner earnings **$75.1M** (**$0.93/sh** at 80.6M shares) |
| source path | `AXON/investor-documents/sec-edgar/10-K_20260225_rpt20251231_acc0001628280_26_011360.htm`; `AXON/research/evidence/sec_companyfacts.json` |
| calculation | $211.339M − $136.258M = **$75.081M** owner earnings; ÷ 80.602M = **$0.9315/sh** |
| remaining uncertainty | Q1 2026 OCF negative (**-$31.5M**); FY2025 is normalization anchor |
| affected components | `operating_business_and_net_assets` |
| valuation consequence | Locked fact ledger reconciles to calculation_proof inputs |
| falsifier | FY2026 full-year owner cash exceeds **$150M** without matching debt paydown |

### Downside and capital claims — met

| Field | Content |
|---|---|
| status | met |
| evidence | Q1 2026 10-Q: cash **$471.2M**, long-term debt **$1,731.0M** (convertible notes); net debt **~$1.26B** |
| source path | `AXON/investor-documents/sec-edgar/10-Q_20260507_rpt20260331_acc0001628280_26_031542.htm` |
| calculation | Enterprise value from proof + net debt bridge: equity base **$263M** ÷ 80.6M = **$3.27/sh** |
| remaining uncertainty | Convertible note conversion/dilution not modeled separately in single-component proof |
| affected components | `operating_business_and_net_assets` |
| valuation consequence | Net debt explains gap between per-share owner-cash DCF (**~$19/sh** pre-debt) and equity value |
| falsifier | Debt repaid below **$1.0B** without equity issuance while owner cash flat |

### Extreme return independent validation — met

| Field | Content |
|---|---|
| status | met |
| evidence | Component method base annualized return **-51.63%**; Lawrence per-share path **-37.9%**; reverse DCF growth requirement **~42%** |
| source path | `AXON/research/valuation.json` → `valuation_methodology.outlier_validation` |
| calculation | At **$527.48**, base value **$3.27/sh** over 7 years → **-51.6%**; normalized **$0.93/sh** cash with 6.3% growth and 18x exit → **-37.9%** |
| remaining uncertainty | High case (**-37.5%**) still extreme; stock prices optionality not in base owner-cash path |
| affected components | All |
| valuation consequence | `extreme_return_validated` set true; contract advances to **decision_grade** |
| falsifier | Either method shows base return above **-25%** without price change |

## Facts vs judgments

**Facts (locked):** FY2025 revenue **$2.78B**; annual recurring revenue **$1.3B** (10-K); net income **$124.7M**; OCF **$211.3M**; capex **$136.3M**; cash **$471.2M** (Mar 2026); debt **$1,731.0M**; shares **~80.6M**; price **$527.48** (2026-07-20).

**Judgments (bounded):** Reinvestment rate 20–50%; incremental after-tax return on capital 12–25%; discount rate 9–12%; terminal owner-earnings multiple 12–24x.

## Valuation consequence

Proof-complete single-component schedule base case **$3.27 per share** vs market **$527.48** implies roughly **-51.6%** annualized return over seven years on filing-normalized owner cash net of **~$1.26B** net debt. Security remains **watch** pending human capital decision; no stance promotion in this agent run.
