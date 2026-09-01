# BMNR valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component. Authorized evidence packet per `research_agent_manifest.json` (2026-07-21).

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `eth_look_through_today` | legacy_sensitivity | net_asset_value@1.0 | calculated | $18.73 |
| `eth_trajectory_net_dilution` | legacy_sensitivity | risk_adjusted_milestone_value@1.0 | bounded_estimate | $4.50 |
| `staking_and_legacy_cash` | legacy_sensitivity | owner_cash_or_dividend_discount@1.0 | bounded_estimate | $0.75 |
| `warrants_tax_preferred_reserve` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | $0.00 |

## Acceptance tests

### Component proof completeness — met

| Field | Content |
|---|---|
| status | met |
| evidence | Each additive component in `valuation.json` now carries `calculation_proof` with approved `method_id@1.0`; `calculation_proof.py` validates all four graphs. |
| source path | `BMNR/research/valuation.json` → `component_valuation.components[]` |
| calculation | Sum of proof outputs (base): $18.73 + $4.50 + $0.75 + $0.00 = **$23.98/sh** vs legacy component schedule **$24.00/sh**. |
| remaining uncertainty | ETH trajectory and preferred waterfall remain judgment-heavy; May marks may lag live spot. |
| affected components | All four additive blockers |
| valuation consequence | Universal contract may advance from `evidence_blocked` toward `decision_grade` after mechanical refresh. |
| falsifier | ETH fair value per share falls below low case after sustained spot decline and further dilution for two quarters. |

### Owner-cash / NAV reconciliation — met

| Field | Content |
|---|---|
| status | met |
| evidence | 10-Q Q3 FY2026: ETH fair value $10,855,537 thousand; 579,652,432 shares; staking revenue $56,924 thousand nine months; warrant liability $2.1M; deferred tax $92.3M. |
| source path | `BMNR/investor-documents/sec-edgar/10-Q_20260714_rpt20260531_acc0001628280_26_048157.htm` |
| calculation | ETH look-through proof: $10,855.537M × 1.0 / 579.652M = **$18.73/sh**. Staking: $56.924M × 1.3333 × 0.57 × 10 / 579.652M = **$0.75/sh**. |
| remaining uncertainty | GAAP net income dominated by $9.04B unrealized crypto loss; Lawrence path excludes marks. Preferred claims not fully modeled. |
| affected components | `eth_look_through_today`, `staking_and_legacy_cash`, `warrants_tax_preferred_reserve` |
| valuation consequence | Filing-locked facts drive calculated/bounded proofs; legacy sensitivities excluded from decision-grade sum. |
| falsifier | Next 10-Q revises ETH units or share count downward >10% without matching price disclosure. |

### Overlap control — met

| Field | Content |
|---|---|
| status | met |
| evidence | Unique overlap keys unchanged; ETH trajectory is incremental to static look-through; staking does not double-count ETH fair value. |
| source path | `BMNR/research/valuation.json` |
| calculation | No additive overlap key duplicates; `double_counting_flags` empty in authorized evidence. |
| remaining uncertainty | None on overlap map. |
| affected components | All |
| valuation consequence | Component sum is additive once. |
| falsifier | New component added without unique overlap_key. |

## Facts vs judgments

**Facts (locked):** ETH fair value $10.856B; 579.7M shares; staking revenue $56.9M nine months; warrant $2.1M; deferred tax $92.3M; cash $340.3M.

**Judgments (bounded):** ETH mark multiplier 0.56–1.17×; seven-year incremental ETH value -$869M to +$10.4B; staking margin 42–68% at 9.5–16.5× capitalization; senior-claim reserve application 0–100%.

## Valuation consequence

Proof-complete additive schedule base case **~$24.0 per share** vs price **$15.69** implies positive upside on component economic value but Lawrence seven-year yield-curve base **6.3%** remains below mid-teens accumulate hurdle. Security remains **watch**; no human capital decision recorded.
