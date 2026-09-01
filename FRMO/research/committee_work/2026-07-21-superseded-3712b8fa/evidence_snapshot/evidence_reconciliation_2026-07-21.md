# FRMO valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component. Authorized evidence packet per `research_agent_manifest.json`.

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `core_engine` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | $5.36 |
| `reinvestment_or_assets` | legacy_sensitivity | probability_weighted_catalyst_nav@1.0 | bounded_estimate | $0.94 |
| `net_financial_claims` | legacy_sensitivity | net_asset_value@1.0 | calculated | $0.34 |
| `downside_reserve` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | -$0.60 |

## Acceptance tests

### component_ownership_map — met

| Field | Content |
|---|---|
| status | met |
| evidence | Q3 FY2026 quarterly report maps Investment A ($308,984k, 82% of FRMO equity), affiliate bundle (MIH, HKHC, royalty, Winland, CMSG), and consolidated liquidity. |
| source path | `FRMO/investor-documents/ir-frmo/2026-02-28_Quarterly_Report.pdf` |
| calculation | Four non-overlapping overlap keys: `core_engine`, `reinvestment_or_assets`, `net_financial_claims`, `downside_reserve`. |
| remaining uncertainty | Investment A look-through weights remain proxy until filed schedule; noncontrolling interests ($418.5M) excluded from FRMO-attributable map. |
| affected components | All four additive components |
| valuation consequence | Ownership waterfall documented in `economic_value_analysis.ownership_waterfall`. |
| falsifier | Filing shows >10% of Investment A economic value reclassified into affiliate lines without overlap update. |

### primary_cash_or_nav_bridge — met

| Field | Content |
|---|---|
| status | met |
| evidence | FRMO-attributable equity $376.704M / 44,022,781 shares = $8.56/sh filed book; Investment A $308.984M; affiliate bundle $57.831M; cash $45.590M + digital assets $10.911M. |
| source path | `FRMO/research/evidence/_text/2026-02-28_Quarterly_Report.pdf.txt` |
| calculation | Proof sum (base): $5.36 + $0.94 + $0.34 − $0.60 = **$6.04/sh** vs price ~$6.70. |
| remaining uncertainty | Attributable liquid pct (26.5% base) is judgment; deferred tax reserve uses consolidated $122.6M context in low case. |
| affected components | All four |
| valuation consequence | Component schedule reconciles to filing anchors; Lawrence 5-year SOTP ($18/sh, 21.9%) remains legacy stance gate. |
| falsifier | Next quarterly filing revises share count or Investment A concentration without proof refresh. |

### downside_and_capital_claims — partially met

| Field | Content |
|---|---|
| status | partially_met |
| evidence | Consolidated deferred tax liability $122,588k; negligible mortgage; securities sold not yet purchased $717k; MIAX six-month lockup disclosed. |
| source path | `FRMO/research/evidence/_text/2026-02-28_Quarterly_Report.pdf.txt` |
| calculation | Downside reserve base: -$26.414M / 44.022781M = **-$0.60/sh**. |
| remaining uncertainty | FRMO-attributable share of deferred tax not line-item split; reserve uses bounded judgment not full DTL allocation. |
| affected components | `downside_reserve`, `net_financial_claims` |
| valuation consequence | Reserve caps holdco discount; does not auto-zero affiliate catalysts. |
| falsifier | Material new debt or tax assessment >15% above base reserve inputs. |

### Component proof completeness — met

| Field | Content |
|---|---|
| status | met |
| evidence | All four additive components carry valid `calculation_proof` with approved `method_id@1.0`; `calculation_proof.py` validates every graph. |
| source path | `FRMO/research/valuation.json` → `component_valuation.components[]` |
| calculation | Proof outputs reproduce scaffold low/base/high within rounding. |
| remaining uncertainty | Catalyst probabilities and attributable-liquid pct remain judgment bands. |
| affected components | All four additive blockers |
| valuation consequence | Universal contract may advance toward `decision_grade` after mechanical refresh. |
| falsifier | Any component proof fails validation or overlap key duplicates. |

## Facts vs judgments

**Facts (locked):** Shares 44,022,781; FRMO-attributable equity $376.704M ($8.56/sh); Investment A $308.984M (82%); MIH fair value $13.917M; HKHC equity $27.187M; royalty participation $10.200M; Winland $5.542M; CMSG $742k; cash $45.590M; digital assets $10.911M; deferred tax liability $122.588M consolidated.

**Judgments (bounded):** Investment A economic realization pct; affiliate catalyst realization pct; attributable liquid pct on consolidated cash/digital; holdco and tax realization reserve.

## Valuation consequence

Proof-complete additive schedule base case **$6.04 per share** vs market price **~$6.70** implies modest negative annualized return on component economic value at a seven-year horizon, while Lawrence 5-year catalyst SOTP still implies **21.9%** per year to $18/sh payoff. No human capital decision recorded in this agent run.
