# CRML — Evidence reconciliation (contract backfill)

**Date:** 2026-07-23  
**Agent:** Marvin (Cloud valuation contract backfill)  
**Ticker:** CRML  
**Primary filing:** `CRML/investor-documents/sec-edgar/20-F_20251006_rpt20250630_acc0001213900_25_096254.htm` (FY2025, report date 2025-06-30)

## Status

| Item | Result |
|------|--------|
| Contract status before | `evidence_blocked` — four additive components at `legacy_sensitivity` |
| Contract status after proofs | `bounded_estimate` on all four components; refresh pipeline re-syncs contract |
| Ownership map | Unchanged — cash, Tanbreez 42%, Wolfsberg option, dilution reserve |
| Double-counting | No overlap-key conflicts |

## Component proof summary

| Component | Method | Proof base ($/sh) | Legacy base | Filing anchor |
|-----------|--------|-------------------|-------------|---------------|
| `corporate_cash` | `net_asset_value@1.0` | $0.07 | $0.07 | $7.3M cash / 104,912,853 shares |
| `tanbreez_risked_nav` | `probability_weighted_catalyst_nav@1.0` | $3.00 | $3.00 | PEA ~$3B pre-tax NPV × 42% × composite risk |
| `wolfsberg_option` | `risk_adjusted_milestone_value@1.0` | $0.50 | $0.50 | BMW $15M restricted advance; M+I resource path |
| `dilution_reserve` | `net_asset_value@1.0` | -$0.50 | -$0.50 | Stage 2 14.5M shares; GEM overhang bracket |

**Sum (base):** $0.07 + $3.00 + $0.50 − $0.50 = **$3.07/sh** (matches `component_valuation_results.total_equity_value_per_share.base`).

## Arithmetic (show your work)

### Corporate cash

1. Cash per share = $7.3M ÷ 104.912853M = **$0.0696/sh**
2. Going-concern factor (base judgment) = 1.006 → **$0.07/sh**

### Tanbreez risked NAV

1. Gross 42% claim on PEA = $3,000M × 0.42 = **$1,260M**
2. Composite risk factor (base) = 0.2496 → risked equity = **$314.5M**
3. Per share = $314.5M ÷ 104.912853M = **$3.00/sh**

**Fact:** PEA cites ~$3B pre-tax project NPV (20-F Item 4, March 31, 2025 press release). **Judgment:** composite risk embeds inferred resource, Greenland jurisdiction, financing, and timing; not filing-stated probability.

### Wolfsberg option

1. Risked milestone value (base judgment) = **$52.4M**
2. Per share = $52.4M ÷ 104.912853M = **$0.50/sh**

**Fact:** BMW $15M advance restricted until production (20-F). **Judgment:** milestone value beyond restricted advance.

### Dilution reserve

1. Reserve per share (base judgment) = **$0.50/sh** (negative additive)
2. **Fact context:** Stage 2 issuance of 14,500,000 shares to reach 92.5% Tanbreez stake; GEM arbitration/warrant overhang (20-F risk factors)

## Remaining uncertainty

| Topic | Tier | Affects |
|-------|------|---------|
| Fully diluted share count (PIPE, warrants, Stage 2) | **[HUMAN REVIEW]** | Cash floor, dilution reserve |
| GEM arbitration outcome | Filing risk | Dilution reserve high/low |
| Tanbreez DFS and Greenland Stage 2 approval | Catalyst | Tanbreez composite risk |
| BMW advance restriction release | Milestone | Wolfsberg option |

## Falsifiers

- Cash impairment or going-concern qualification below $7.3M without offsetting asset mark
- PEA withdrawn or DFS fails economic viability test → cut Tanbreez composite risk to low case
- Stage 2 blocked or GEM settlement exceeds low-case reserve
- Wolfsberg production milestone missed with no alternate offtake

## Valuation consequence

Proof-complete component schedule supports **watch** stance at **$6.40** with base component sum **$3.07/sh** (**-52%** downside to base value vs price). Lawrence seven-year scenario payoff **$4.00/sh** remains separate stance gate (**-6.5%** per year).

**No human capital decision recorded.** `human_decision.json` unchanged.
