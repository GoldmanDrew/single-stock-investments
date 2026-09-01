# C valuation evidence reconciliation — 2026-08-13

**Scope:** Close remaining `authorized_evidence.json` contract backfill blockers (`segment_rotce_normalization`, `distributable_capital`). Evidence packet authorized 2026-08-13 per `research_agent_manifest.json` (hash on file; see manifest). // pragma: allowlist secret

**Primary source:** `C/investor-documents/sec-edgar/10-K_20260220_rpt20251231_acc0000831001_26_000011.htm` (FY2025, filed 2026-02-20).

## Blockers closed

| Gap | Prior status | Method | Proof status | Base per share |
|-----|--------------|--------|--------------|----------------|
| `segment_rotce_normalization` | partially_met | capital_structure_and_excess_return@1.0 | met | $15.00 franchise |
| `distributable_capital` | partially_met | probability_weighted_catalyst_nav@1.0 | met | $10.00 excess capital |
| `stress_claims` | met | net_asset_value@1.0 | met (unchanged) | -$15.00 reserve |
| `tangible_common_equity` | met | net_asset_value@1.0 | met (unchanged) | $97.00 |

**Base proof sum:** $97.00 + $15.00 + $10.00 − $15.00 = **$107.00/sh** (mechanical sum **$106.95/sh** before rounding).

## Acceptance tests

### `segment_rotce_normalization` — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 segment revenues (XBRL): Services **$21,256M**, Markets **$21,970M**, Banking **$8,215M**, Wealth **$8,559M**, US Personal Banking **$20,971M**. Segment income from continuing operations (10-K table): **$7,139M**, **$5,928M**, **$2,324M**, **$1,490M**, **$3,097M**. Firmwide income from continuing operations **$14,455M** on TCE **$169,618M**. |
| source path | `C/investor-documents/sec-edgar/10-K_20260220_rpt20251231_acc0000831001_26_000011.htm` segment results table + XBRL Revenues |
| calculation | Revenue-weighted five-segment TCE = **$169,618M × ($81,971M / $85,577M) = $162,466M**. Core segment return = **$19,978M / $162,466M = 12.3%**. Base normalized RoTCE **12.2%** in excess-return proof → franchise PV **$14.95/sh** (rounded **$15/sh**). Low/high: **9.94% / 14.8%** with cost of equity **12.0% / 9.0%** and duration **5 / 8** years → **-$10/sh** to **+$45/sh**. |
| remaining uncertainty | All Other managed basis lost **$4,441M** and divestiture reconciling items **$1,082M** remain outside the five-segment core; transformation drag could keep firmwide RoTCE below segment-weighted core. |
| affected components | `normalized_franchise_returns` |
| valuation consequence | `segment_calibration` fudge removed; proof uses explicit segment revenue/income facts and revenue-weighted TCE allocation. |
| falsifier | Firmwide RoTCE remains below **9%** for four consecutive quarters after transformation expense normalizes while core segments still earn **12%+** on allocated capital. |
| monitoring source | Quarterly 10-Q segment income table and key-metrics RoTCE |

### `distributable_capital` — met

| Field | Content |
|---|---|
| status | met |
| evidence | Standardized CET1 **13.2%** vs required **11.6%** (decomposed: **4.5%** minimum + **3.6%** SCB + **3.5%** GSIB surcharge). RWA **$1,192,174M**. FY2025 common capital return **$17.6B** (**$10.07/sh**). Transformation expense **~$3.3B**. |
| source path | 10-K Capital Resources (SCB, GSIB, CET1) and MD&A capital return |
| calculation | Headroom **160 bps**; net **40 bps** after **120 bps** discretionary buffer → gross excess **$4,769M**; × **55%** realization → **$2,623M**; ÷ **1,747.5M** shares = **$1.50/sh** one-year capacity; × **3.79** five-year NPV factor at **10%** × **1.76** transformation-completion uplift = **$10/sh** base. Low: zero probability (negative net headroom after **180 bps** buffer). High: **80 bps** net headroom, **80%** probability, **9%** discount → **$25/sh**. |
| remaining uncertainty | Fed SCB resets, RWA inflation, and consumer credit could absorb headroom; **$17.6B** FY2025 return is historical proof of capacity, not a forward guarantee. |
| affected components | `transformation_and_excess_capital` |
| valuation consequence | `execution_haircut` replaced by explicit **release_npv_factor** and **transformation_completion_uplift**; SCB/GSIB embedded in **cet1_required_pct** fact. |
| falsifier | CET1 ratio falls toward **11.6%** floor while management continues **$13B+** repurchases without RWA relief. |
| monitoring source | 10-Q CET1 table; 8-K capital actions |

### Component proof completeness — met

| Field | Content |
|---|---|
| status | met |
| evidence | All four additive components carry valid `calculation_proof` graphs; overlap keys non-overlapping. |
| source path | `C/research/valuation.json` via `build_c_contract_proofs.py` |
| calculation | Base sum **~$107/sh** vs price **$131.89** → contract synthesis **-2.94%** per year (seven-year horizon). |
| remaining uncertainty | Judgment bands on normalized RoTCE and capital-release timing. |
| affected components | All |
| valuation consequence | `authorized_evidence.json` and followups move to **decision_grade** / **met**. |
| falsifier | 10-K revises TCE, ACL, CET1, or segment income by **>10%** without proof refresh. |

## Facts vs judgments

**Facts (locked):** TCE **$169.618B**; TBVPS **$97.06**; RoTCE **7.7%** ( **8.8%** adjusted); revenues **$85.2B**; ACL **$21.373B**; CET1 **13.2%** vs req **11.6%** (SCB **3.6%**, GSIB **3.5%**); RWA **$1,192B**; capital return **$17.6B**; transformation **~$3.3B**; five-segment income **$19.978B** on **$81.971B** revenue.

**Judgments (bounded):** Normalized RoTCE **9.94–14.8%**; excess-capital realization probability **0–80%**; discretionary CET1 buffer **80–180 bps**; transformation-completion uplift **1.0–1.76×** on timed headroom release.

## Valuation consequence

Proof-complete schedule at **~$107/sh** base vs **~$132** price implies **-2.94%** annual return on the universal contract. No stance or sizing authority in `human_decision.json`. **[HUMAN REVIEW]** remains for capital decision and third-party promotion.
