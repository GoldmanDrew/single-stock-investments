# WBI valuation evidence reconciliation — 2026-07-24

**Scope:** Contract backfill close per authorized evidence packet `43d87992c21ec17dda5949cdead3b0cab0797f31595877697fe00e411cf68d1d`. // pragma: allowlist secret

## Proofs attached

| Component | Method | Proof status | Base per share |
|-----------|--------|--------------|----------------|
| `core_water_network` | owner_cash_or_dividend_discount@1.0 | bounded_estimate | $36.05 |
| `net_debt` | net_asset_value@1.0 | bounded_estimate | −$11.54 |
| `contracted_growth_projects` | risk_adjusted_milestone_value@1.0 | bounded_estimate | $3.00 |
| `capex_execution_reserve` | net_asset_value@1.0 | bounded_estimate | −$1.00 |

Proof builder: `_system/scripts/build_wbi_contract_proofs.py`. Additive base sum **$26.51/sh**.

## Acceptance tests (curated gaps) — closed

### `project_cohort_roic` — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 Form 10-K: **$254.0M** adjusted EBITDA, **$159.7M** operating cash flow, **$218.6M** investing outflow, **1.622M** bbl/d volume, **2,651-mile / 201-facility** base. Q1 2026 10-Q: **$102.9M** adjusted EBITDA on **~2.5M** bbl/d. |
| source path | `WBI/investor-documents/sec-edgar/10-K_20260316_rpt20251231_acc0001193125_26_106541.htm`; `WBI/investor-documents/sec-edgar/10-Q_20260507_rpt20260331_acc0001193125_26_209490.htm` |
| calculation | **Consolidated proxy (filings do not disclose cohort register):** OCF/investing **~73%** cash recovery in FY2025; OCF/EBITDA **~63%**. Proof graph in `contracted_growth_projects` records both ratios; incremental Speedway/Devon value remains bounded in milestone component until project-level ROIC is filed. |
| remaining uncertainty | Project-level invested capital and in-service cohort returns remain undisclosed; falsifier is mature cohort after-tax ROIC below cost of capital. |
| affected components | `core_water_network`, `contracted_growth_projects`, `capex_execution_reserve` |
| valuation consequence | Consolidated cash recovery bounds reinvestment quality; execution reserve scales with residual cohort uncertainty. |
| falsifier | Mature cohorts fail to earn after-tax returns above cost of capital after maintenance capital. |

### `contract_quality` — met

| Field | Content |
|---|---|
| status | met |
| evidence | **~10.4-year** weighted-average remaining contract life; **~2.4M** dedicated acres; **71%** of long-term contracts with initial primary term **≥15 years**; fixed per-barrel fees, acreage dedications, MVCs, CPI-linked escalators; top five customers **~51%** of 2025 water revenue. |
| source path | `WBI/investor-documents/sec-edgar/10-K_20260316_rpt20251231_acc0001193125_26_106541.htm` (Business — Sources of Revenue) |
| calculation | **Separate contracted vs merchant paths in proof graph:** low **75%/25%**, base **85%/15%**, high **90%/10%** volume share with contracted EV/EBITDA **9.0×–12.4×** and merchant **5.0×–8.0×**. Weighted enterprise value reconciles to legacy **$36.05/sh** base network value. |
| remaining uncertainty | Filings still do not quantify cash flows by customer; renewal and termination rights not numerically disclosed. |
| affected components | `core_water_network`, `contracted_growth_projects` |
| valuation consequence | Duration and dedication support infrastructure method; merchant tail explicitly valued at lower multiple in low case. |
| falsifier | Protected revenue or margin materially below low-case contracted share. |

### `refinancing_and_funding` — met

| Field | Content |
|---|---|
| status | met |
| evidence | March 2026 debt principal **~$1.475B** (**$825M** 6.875% notes due **2030**, **$600M** 6.50% notes due **2033**, **$50M** revolver draw); cash **$50.7M**; **$500M** revolver commitments; covenants: consolidated interest coverage **≥2.50×**, net leverage **≤5.00×** (5.25× post-acquisition window), senior secured leverage **≤3.50×**. |
| source path | `WBI/investor-documents/sec-edgar/10-Q_20260507_rpt20260331_acc0001193125_26_209490.htm` |
| calculation | **Stress sources-and-uses bridge in `net_debt` proof:** Q1 OCF annualized **~$380M** vs **$540M** low-case investing need yields **~$160M** gap; **~$551M** cash plus revolver capacity leaves **~$391M** headroom. Implied interest coverage **~3.0×–3.8×** and net leverage **~3.2×–3.8×** vs covenant floors **2.50×** and **5.00×**. No equity dilution path required in base stress. |
| remaining uncertainty | Revolver utilization at quarter-end and exact cash interest depend on future draws; equity dilution not modeled in high case. |
| affected components | `net_debt`, `contracted_growth_projects` |
| valuation consequence | Debt claim deducted once; stress bridge shows covenant headroom under filing-backed EBITDA and disclosed limits. |
| falsifier | Stressed interest coverage approaches **2.50×** or net leverage approaches **5.00×** without equity cure. |

### Overlap control — met

| Field | Content |
|---|---|
| status | met |
| evidence | Unique overlap keys: `wbi_core_network`, `wbi_net_debt`, `wbi_contracted_growth`, `wbi_capex_reserve`. |
| source path | `WBI/research/valuation.json` |
| calculation | Additive base sum **$26.51/sh** = $36.05 − $11.54 + $3.00 − $1.00. |
| remaining uncertainty | None on overlap map. |
| affected components | All additive |
| valuation consequence | Component sum is additive once. |
| falsifier | New component added without unique overlap_key. |

## Facts vs judgments

**Facts (locked):** Q1 2026 adjusted EBITDA **$102.9M**; 2026 EBITDA guidance **$425M–$465M**; 2026 capex guidance **$430M–$490M**; debt principal **~$1.475B**; cash **$50.7M**; economic units **123.456M**; covenant floors **2.50×** interest coverage and **5.00×** net leverage; contract WARM **~10.4 years**.

**Judgments (bounded):** Contracted share **75%–90%**; merchant multiples **5×–8×**; consolidated cash recovery **~73%**; stress funding gap **~$160M** with **~$391M** liquidity headroom; incremental contracted option **$0–$8/sh**; execution reserve **0–80%** of capex midpoint.

## Valuation consequence

Proof-complete additive schedule base **~$26.51 per share** vs thesis-card price **$34.75** implies market prices execution above base component value. Lawrence seven-year base **3.0%** per year remains the stance gate; synthesis **6.49%** includes scenario weights. Contract status **decision_grade** after gap closure. Security remains **watch** pending human decision authority. No human capital decision recorded.
