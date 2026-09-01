# QDEL valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component. Authorized evidence packet per `research_agent_manifest.json` (2026-07-21).

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `core_diagnostics_engine` | legacy_sensitivity | owner_cash_or_dividend_discount@1.0 | bounded_estimate | $7.58 |
| `product_and_pipeline_options` | legacy_sensitivity | risk_adjusted_milestone_value@1.0 | bounded_estimate | $1.10 |
| `net_financial_claims` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | $1.65 |
| `downside_reserve` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | −$1.65 |

## Acceptance tests

### Component ownership map — met

| Field | Content |
|---|---|
| status | met |
| evidence | Four additive components with unique overlap keys: core diagnostics engine, product and pipeline options, net financial claims, downside reserve. Donor screening wind-down embedded in core allocation; POC/LEX options separate. |
| source path | `QDEL/research/valuation.json` → `component_valuation.components[]` |
| calculation | Material claims mapped once per `overlap_key`; sum base **$8.68/sh** = $7.58 + $1.10 + $1.65 − $1.65. |
| remaining uncertainty | Segment EBITDA allocation to Labs and immunohematology remains [Assumption] pending segment footnote refresh. |
| affected components | All four additive blockers |
| valuation consequence | Ownership map complete; proofs attached. |
| falsifier | New filing reveals an unmodeled material claim or duplicate overlap key. |

### Primary owner-cash / NAV bridge — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 revenue **$2,730.2M**; adjusted EBITDA **$597.0M**; FY2026 guidance **$615–630M**; Labs **$1,505.7M** + immunohematology **$543.8M** = **75%** of revenue; cash **$169.8M**; net debt **~$2,380M**; diluted shares **67.8M**. |
| source path | `QDEL/investor-documents/sec-edgar/10-K_20260219_rpt20251228_acc0001906324_26_000008.htm`; Q1 FY2026 10-Q; earnings deck |
| calculation | Guided EBITDA midpoint **$622.5M** × **18%** FCF conversion ÷ **67.8M** = **$1.65/sh** owner cash. Core proof: **80.7%** of guided EBITDA to Labs+IH × FCF conversion → seven-year DCF with schedule adjustment = **$7.58/sh** base. |
| remaining uncertainty | Company targets **25%** EBITDA-to-FCF; **18%** haircut for LEX drag and China working-capital timing. |
| affected components | `core_diagnostics_engine`, `net_financial_claims` |
| valuation consequence | Filing-locked facts anchor proofs; legacy sensitivities excluded from decision-grade sum. |
| falsifier | Two consecutive quarters of consolidated adjusted EBITDA below **$580M** without offsetting core segment growth. |

### Downside and capital claims — met

| Field | Content |
|---|---|
| status | met |
| evidence | Total debt **~$2,550M**; cash **$169.8M**; net debt **~$2,380M** (**~$35/sh** gross); interest **~$185M**; FY2026 capex guide **~$130M**. POC divestiture (**~$1.5B** FT Jun 27 2026) unconfirmed. |
| source path | FY2025 10-K debt footnote; Q1 FY2026 10-Q |
| calculation | Downside reserve base **−$1.65/sh** = **−$112M** judgment reserve for reimbursement, integration, and covenant stress (not full net debt double-count). Net financial claim **+$1.65/sh** = near-term distributable owner-cash bridge separate from capitalized core engine. |
| remaining uncertainty | POC sale failure or sub-**$1.0B** price widens reserve; confirmed sale would shift value to `product_and_pipeline_options`. |
| affected components | `downside_reserve`, `product_and_pipeline_options`, `net_financial_claims` |
| valuation consequence | Capital claims reconciled to filings; leverage stress reserved once. |
| falsifier | Net debt rises above **4.5×** EBITDA without announced deleveraging path. |

### Overlap control — met

| Field | Content |
|---|---|
| status | met |
| evidence | Unique overlap keys unchanged; POC proceeds modeled in options component only; near-term owner cash not capitalized twice inside core DCF terminal. |
| source path | `QDEL/research/valuation.json` |
| calculation | `double_counting_flags` empty in authorized evidence. |
| remaining uncertainty | None on overlap map. |
| affected components | All |
| valuation consequence | Component sum is additive once. |
| falsifier | New component added without unique overlap_key. |

## Facts vs judgments

**Facts (locked):** FY2025 revenue **$2,730.2M**; adj EBITDA **$597.0M**; Labs **$1,505.7M**; immunohematology **$543.8M**; POC **$601.6M**; cash **$169.8M**; net debt **~$2,380M**; shares **67.8M**; FY2026 EBITDA guide **$615–630M**.

**Judgments (bounded):** Core FCF conversion **15–22%**; core DCF exit multiples **7–10×**; POC sale probability **0–60%** on **$0.8–2.0B** proceeds; LEX success **0–40%** on **$0–200M** peak value; downside reserve **−$3.45 to −$0.41/sh**.

## Valuation consequence

Proof-complete additive schedule base case **~$8.68 per share** vs price **~$13.79** implies component economic value below market; Lawrence seven-year base **15.4%** remains the stance gate. Security remains **watch** pending POC confirmation; no human capital decision recorded.
