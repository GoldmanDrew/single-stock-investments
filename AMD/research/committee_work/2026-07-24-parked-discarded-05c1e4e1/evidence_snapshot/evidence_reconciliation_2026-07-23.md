# AMD — Evidence reconciliation (2026-07-23)

**Ticker:** AMD · **As-of:** 2026-07-23 · **Run:** contract backfill refresh

## Summary

| Item | Status |
|------|--------|
| Economic ownership map | **met** — three segment owner-cash components + net financial claims + AI competition reserve |
| Component calculation proofs | **met** — valid graphs on all five additive components |
| Owner-cash / NAV bridge | **met** — FY2025 continuing FCF **$5.52B** anchors segment allocation |
| Downside capital claims | **met** — long-term debt **$2.35B** netted against cash **$5.54B** in net financial claims |
| Double-counting | **met** — non-overlapping overlap keys; Xilinx and MI300 embedded in segment paths |

**Prior blocker resolved:** `authorized_evidence.json` flagged *"A complete economic ownership map has not been supplied."* Five additive components with filing-backed calculation proofs now populate `valuation.json` → `component_valuation`.

---

## Proofs attached

| Component | Method | Proof status | Base ($/sh) |
|-----------|--------|--------------|-------------|
| `data_center_owner_cash` | owner_cash_or_dividend_discount@1.0 | bounded_estimate | 72.50 |
| `client_gaming_owner_cash` | owner_cash_or_dividend_discount@1.0 | bounded_estimate | 20.80 |
| `embedded_owner_cash` | owner_cash_or_dividend_discount@1.0 | bounded_estimate | 3.20 |
| `net_financial_claims` | net_asset_value@1.0 | bounded_estimate | 1.95 |
| `ai_competition_and_capex_reserve` | net_asset_value@1.0 | bounded_estimate | −2.00 |

Additive base sum **$96.45/sh** = $72.50 + $20.80 + $3.20 + $1.95 − $2.00.

---

## Acceptance test: complete economic ownership map

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | Five additive components: Data Center, Client/Gaming, and Embedded segment owner cash; net corporate liquidity; AI competition and capex stress reserve |
| **Source** | `AMD/investor-documents/sec-edgar/10-K_20260204_rpt20251227_acc0000002488_26_000018.htm` segment note and cash-flow statement |
| **Calculation** | Base component sum **$96.45/sh** reconciles to `segment_build.reconciliation.sum_pv_per_share_at_10pct` **$96.5** |
| **Remaining uncertainty** | Segment FCF allocated by revenue share; segment-level cash conversion not separately disclosed |
| **Affected components** | All five additive |
| **Valuation consequence** | Lawrence synthesis base **7.84%** per year unchanged; proof-backed fair value **~$96/sh** vs market **~$466** |
| **Falsifier** | Two consecutive quarters Data Center revenue growth below **20%** with flat Client/Gaming |

---

## Acceptance test: primary cash / owner-cash bridge

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | FY2025 continuing OCF **$6.49B**; capex **$0.97B**; FCF **$5.52B**; **1.636B** diluted shares |
| **Source** | FY2025 10-K cash-flow statement and income statement |
| **Calculation** | $5.52B ÷ 1.636B shares = **$3.37/sh** consolidated owner cash; allocated 48% / 42% / 10% by segment revenue |
| **Remaining uncertainty** | Foundry prepayment timing can depress near-term FCF below segment allocation |
| **Affected components** | data_center_owner_cash, client_gaming_owner_cash, embedded_owner_cash |
| **Valuation consequence** | Segment sum ties to Lawrence FCF₀; stance gate unchanged |
| **Falsifier** | Continuing OCF falls below **$5.0B** annualized for two quarters |

---

## Acceptance test: downside and capital claims

| Field | Value |
|-------|-------|
| **Status** | met |
| **Evidence** | Cash **$5.54B**; long-term debt **$2.35B**; net cash **~$3.19B** (**~$1.95/sh**) |
| **Source** | 10-K balance sheet |
| **Calculation** | Net cash per share additive; AI competition reserve captures custom ASIC and capex stress separately |
| **Remaining uncertainty** | Operating cash minimum not separately disclosed; reserve is judgment band |
| **Affected components** | net_financial_claims, ai_competition_and_capex_reserve |
| **Valuation consequence** | Net liquidity modest relative to equity value; reserve sizes NVIDIA/custom-silicon downside |
| **Falsifier** | Net debt turns positive (cash below debt) without commensurate Data Center margin expansion |

---

## Open gaps (partially_met)

| Gap | Status | Notes |
|-----|--------|-------|
| Segment-level FCF disclosure | partially_met | Revenue and OI by segment disclosed; FCF allocated by revenue share |
| Custom ASIC share shift | partially_met | In `ai_overlay.not_in_model_requires_refresh`; reserve component bounds risk |
| Live price confirmation | open | `human_review.live_price_confirmed` false; mechanical refresh updates market inputs |

---

## Facts vs judgments

**Facts (locked):** FY2025 revenue **$34.6B** (+34%); Data Center **$16.6B**; Client/Gaming **$14.6B**; Embedded **$3.5B**; continuing OCF **$6.49B**; capex **$0.97B**; cash **$5.54B**; debt **$2.35B**; **1.636B** diluted shares.

**Judgments (bounded):** Segment growth paths and exit multiples from `segment_build`; AI competition reserve **−$2.00/sh** base; net cash **$1.95/sh** base.

## Valuation consequence

Proof-complete additive schedule base **$96.45 per share** aligns with prior segment sum **$96.5/sh**. Lawrence total-synthesis base **7.84%** per year and stance **watch** unchanged. No human capital decision recorded.
