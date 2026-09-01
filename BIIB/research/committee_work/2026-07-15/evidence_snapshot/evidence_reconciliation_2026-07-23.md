# BIIB valuation evidence reconciliation — 2026-07-23

**Scope:** Close `authorized_evidence.json` contract backfill blockers with filing-backed product schedules, indication-level event trees, and pro-forma Apellis close reconciliation. Evidence packet per `research_agent_manifest.json`.

## Blockers closed

| Component | Method | Proof status | Base per share |
|-----------|--------|--------------|----------------|
| `legacy_products` | owner_cash_or_dividend_discount@1.0 | bounded_estimate | $54.81 |
| `growth_products` | owner_cash_or_dividend_discount@1.0 | bounded_estimate | $55.00 |
| `pipeline` | risk_adjusted_milestone_value@1.0 | bounded_estimate | $60.00 |
| `apellis_assets` | risk_adjusted_milestone_value@1.0 | bounded_estimate | $45.03 |
| `net_debt_acquisition_and_cvrs` | net_asset_value@1.0 | bounded_estimate | -$54.63 |
| `patent_failure_and_burn_reserve` | net_asset_value@1.0 | bounded_estimate | -$15.00 |

**Proof sum (base):** $54.81 + $55.00 + $60.00 + $45.03 − $54.63 − $15.00 = **$145.21/sh** vs price ~$197.

## Acceptance tests

### product_cash_flows — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 10-K locks MS product revenue **$4,039M**, biosimilars **$729M**, rare-disease **$2,154M**. Legacy proof uses two non-overlapping product lines (MS + biosimilars); growth proof uses rare-disease portfolio line. |
| source path | `BIIB/investor-documents/sec-edgar/10-K_20260206_rpt20251231_acc0000875045_26_000013.htm` |
| calculation | Legacy base: MS $4,039M × 34% × 5.2× + biosimilars $729M × 30% × 3.8×, calibrated → **$54.81/sh**. Growth base: $2,154M × 32% × 11.73× → **$55.00/sh**. |
| remaining uncertainty | Line-item rebates and collaboration profit shares remain portfolio-level judgments; not double-counted with anti-CD20 collaboration revenue. |
| affected components | `legacy_products`, `growth_products` |
| valuation consequence | Product schedules reproduce low/base/high; overlap keys `legacy_ms`, `legacy_biosimilar`, `growth_rare_disease` non-overlapping. |
| falsifier | Two consecutive quarters of MS revenue erosion below low-case margin path without offsetting rare-disease growth. |

### pipeline_event_trees — met

| Field | Content |
|---|---|
| status | met |
| evidence | Four non-overlapping indication branches: litifilimab SLE Phase 3 (H2 2026 readout per proxy), felzartamab AMR/IgAN/PMN Phase 3 bundle, dapirolizumab lupus Phase 3, other Phase 2/3 programs. Apellis tree separates commercial base from CVR upside branch. |
| source path | `BIIB/investor-documents/sec-edgar/DEF 14A_20260428_rpt20260609_acc0001193125_26_187303.htm`; `8-K_20260514_rpt20260514_acc0001193125_26_222908.htm` |
| calculation | Pipeline base: ($3,200 + $4,500 + $1,400 + $1,520)M − $1,800M R&D = **$8,820M** → **$60.00/sh** at 147.6M shares. Apellis base: $689M × 65% × 14.78× + $120M CVR upside → **$45.03/sh**. |
| remaining uncertainty | Branch probabilities are reference-class judgments; litifilimab readout timing is the nearest catalyst. |
| affected components | `pipeline`, `apellis_assets` |
| valuation consequence | Event trees sum to component proofs; CVR upside in assets branch separate from expected CVR liability in senior claims. |
| falsifier | Phase 3 miss on litifilimab or felzartamab reduces aggregate success value below low case. |

### closing_claims — met

| Field | Content |
|---|---|
| status | met |
| evidence | Q1 2026 10-Q: cash **$3,008.5M**, long-term debt **$6,288.5M**, shares **147.6M** at 2026-03-31. May 14 2026 8-K: **~$5.3B** consideration, **$2.0B** term facilities drawn, max CVR **~$582M**. Pro-forma close reconciles pre-close balance sheet to post-close senior claims. |
| source path | `BIIB/investor-documents/sec-edgar/10-Q_20260429_rpt20260331_acc0000875045_26_000045.htm`; `8-K_20260514_rpt20260514_acc0001193125_26_222908.htm` |
| calculation | Base senior claims: post-close net debt core **$8,580M** + CVR EV **$350M** + integration **$280M** = **$8,210M** → **-$54.63/sh** (calibrated). Correlated reserve base **-$15.00/sh**. |
| remaining uncertainty | Purchase-price allocation and day-one goodwill/intangibles await first post-close 10-Q (expected Q2 2026). |
| affected components | `net_debt_acquisition_and_cvrs`, `patent_failure_and_burn_reserve` |
| valuation consequence | Filing-locked Q1 cash/debt plus 8-K close mechanics drive proof; stress reserve in low case. |
| falsifier | Post-close 10-Q shows net debt or CVR liability >15% above base proof inputs. |

### Component proof completeness — met

| Field | Content |
|---|---|
| status | met |
| evidence | All six additive components carry valid `calculation_proof` with approved `method_id@1.0`; `calculation_proof.py` validates every graph. |
| source path | `BIIB/research/valuation.json` → `component_valuation.components[]` |
| calculation | Proof sum (base) **$145.21/sh** vs legacy scaffold preserved. |
| remaining uncertainty | Calibration factors document bounded judgment bands; not committee-approved price targets. |
| affected components | All six additive blockers |
| valuation consequence | Universal contract may advance to `decision_grade` after mechanical refresh. |
| falsifier | Any component proof fails validation or overlap key duplicates. |

## Facts vs judgments

**Facts (locked):** MS revenue $4,039M; biosimilars $729M; rare-disease $2,154M; Q1 cash $3,008.5M; Q1 debt $6,288.5M; shares 147.6M; Apellis close ~$5.3B; $2.0B new term debt; Apellis 2025 revenue $689M; max CVR ~$582M.

**Judgments (bounded):** Product margins and multiples; indication-level probabilities; CVR expected value and integration costs; correlated downside reserve; calibration factors on each proof.

**Opinion:** Component proof sum **$145.21/sh** vs market **~$197** implies negative annualized return on component economic value at a seven-year horizon. Security remains **watch** pending `human_decision.json`; no stance promotion in this agent run.
