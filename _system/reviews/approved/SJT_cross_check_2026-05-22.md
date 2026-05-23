# SJT — Cross-Check: Equity Yield Curve Lens

**Date:** 2026-05-22  
**Agent:** Marvin  
**Cross-checks:** `SJT/research/deep_dive_2026-05-21.md` vs Horizon Kinetics framework + primary filings  
**Framework:** `_system/frameworks/mental_models.md` (Tier 3 — equity yield curve)

---

## Executive summary

The 2026-05-21 deep dive correctly documented **facts** (zero royalties, excess production costs, going-concern doubt) but **under-applied** the Horizon Kinetics equity yield curve / time arbitrage lens. Under that framework, SJT is not merely “no dhando because no cash flow” — it is a **transitory NPI deficit** situation where the market may demand a steep discount for waiting, with **re-rating potential** when distributions resume (Mesabi Trust precedent).

**Critical update vs HK Q1 2025:** HK modeled dividend reinstatement by **May/June 2025** at ~$3 gas. As of **May 2026**, distributions remain suspended; deficit paydown was **slower** than HK assumed because 2025 capital charges to the NPI **far exceeded** Hilcorp’s budget ($23.8M actual vs $9.0M planned). The **framework still applies**; the **timeline and risk** are worse than HK’s base case.

**Revised view (human confirmed 2026-05-22):** Dhando **`partial`** under equity yield curve lens (time arbitrage on recoverable NPI deficit). **Stance `watch`** — going-concern disclosure and depleting reserves block `accumulate` despite attractive bull-case implied returns at **~$4.10/unit**.

---

## Mental models applied


| Model                                   | Finding                                                                                                                                                                              |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Equity yield curve / time arbitrage** | Bounded recovery event (NPI deficit erasure) with uncertain date → institutional yield investors exit → patient capital may earn steep implied return if/when distributions restart. |
| **Transitory problem**                  | Trustee states recovery is “likely, but not certain” before depletion; not a permanent impairment of reserves — but **duration** of “temporary” has extended.                        |
| **Market structure discount**           | Royalty trust, no yield screen, sub-index, K-1/WHFIT complexity → persistent holder base mismatch.                                                                                   |
| **Inversion (Munger)**                  | 2026 capex plan ($14M) + deferred horizontal **completion** costs (2027) could **add** to deficit; going-concern + line of credit + NYSE listing risk if distributions stay zero.    |
| **Incentive-caused bias**               | Hilcorp (private) controls capex charged against NPI; trust cannot block spending that delays distributions.                                                                         |
| **Dhando (Pabrai)**                     | Downside not fully protected today (zero cash, LOC drawn, depleting asset); upside asymmetric **if** deficit clears and gas/market re-rates trust — **partial**, not full.           |


**Predictive attribute:** `equity_yield_curve` + `market_structure_discount` + `transitory_problem`

---

## HK thesis vs primary-source reality

### What Horizon Kinetics argued

**Q1 2025 Commentary** (`horizon-kinetics/HK-Q1-2025-Commentary-extract.txt`, § IV — James Davolos):

- SJT grouped with Mesabi: **temporary dividend suspension** with predictable horizon; “nice time arbitrage example.”
- Zero distribution from Hilcorp **2024 capex ramp** ($36M vs $4.4M in 2023); production up ~50% but gas prices down ~56%.
- At **$3/mcf** (10% basis discount): estimated **May/June 2025** full paydown of capex deficit; run-rate NPI ~~**$3.6M/month** (~~**$43M/year**) → ~~**17% yield** on ~$3.83 unit price (~~$200M market cap).
- Prior distribution: **$0.41/month** (March 2023) → ~**$4.10/year** annualized.

**Q3 2025 Commentary** (`horizon-kinetics/HK-Q3-2025-Commentary-extract.txt`, p.34–35):

- Pure-play gas royalty; NPI net of Hilcorp opex/capex; deficit = interest-free capital contribution from trust perspective.
- “Just a matter of waiting” for royalties to erase deficit; reserves/production intact.

### What actually happened (10-K FY2025)

**Source:** `SJT/investor-documents/sec-edgar/10-K_20260327_rpt20251231_acc0001193125_26_128710.htm`


| Item                                                         | Fact                                                                                |
| ------------------------------------------------------------ | ----------------------------------------------------------------------------------- |
| FY2025 royalty income from Hilcorp                           | **$0**                                                                              |
| Unit-holder distributions                                    | **None** (since May 2024)                                                           |
| Excess production costs remaining (net to Trust, 12/31/2025) | **$6,328,902** (gross **$8,438,536**)                                               |
| 2025 Hilcorp capital in NPI calculation                      | **$23.8M actual** vs **$9.0M** 2025 Plan                                            |
| Cash reserves (12/31/2025)                                   | **$23,298**                                                                         |
| Line of credit (Texas Bank, May 2025)                        | **$2M** facility; **$387,808** drawn at 12/31/2025                                  |
| Going concern                                                | **Substantial doubt** within one year of filing                                     |
| Trust units outstanding                                      | **46,608,796**                                                                      |
| 2026 Hilcorp capital plan                                    | **~$14.0M** (incl. 6 horizontal drills; **completion costs deferred to 2027 plan**) |


**Deficit trajectory 2025 (net to Trust):**


| Date                     | Remaining net deficit                |
| ------------------------ | ------------------------------------ |
| 12/31/2024               | $15,936,006                          |
| 12/31/2025               | $6,328,902                           |
| **Net recovery in 2025** | **~$9.6M** (~60% of opening deficit) |


**Inference:** Deficit **is shrinking** — HK’s direction was right, but **timing was optimistic**. May/June 2025 full clearance did not occur because 2025 capital charged to the NPI (**$23.8M actual** vs **$9.0M** plan) partially offset gross-proceeds recovery. Reinstatement requires the remaining **~$6.3M** net (per 12/31/2025) to clear while 2026–2027 capex plans continue.

**Mar 31, 2026 (10-Q):** Cash reserves **$14,380**; May 18, 2026 8-K — **no** monthly distribution (`8-K_20260518_rpt20260518_acc0001193125_26_228303.htm`).

---

## Equity yield curve worksheet (qualitative)

**Method** (per `horizon-kinetics/Stahl-Equity-Yield-Curve-extract.txt` + Q1 2025 HK):

1. **Current price** = P₀ = **$4.10/unit** (human confirmed 2026-05-22; ~**$191M** market cap on 46,608,796 units). HK used **$3.83** at end 2024.
2. **Terminal value event** = first meaningful monthly distribution D restored.
3. **Implied terminal price** P_T = annualized distribution / target yield (yield investors re-enter post-reinstatement).
4. **Annualized return** ≈ (P_T / P₀)^(1/t) − 1 for t years to reinstatement.

### Scenario table (inferences — not facts)

Assumptions: **46.6M units**; net deficit **~$6.3M** must be recovered from gross proceeds before trust receives NPI.


| Scenario            | Gas / operations                               | Months to first distribution | Steady-state annual dist/unit | Implied P_T at 12% yield | Annualized return (P₀=$4.10) |
| ------------------- | ---------------------------------------------- | ---------------------------- | ----------------------------- | ------------------------ | ---------------------------- |
| **HK base (stale)** | $3 gas, 2025 ramp                              | 0 (already passed)           | ~$0.90–1.00                   | ~$7.50–8.30              | N/A — thesis delayed         |
| **Base**            | $3.50 gas, 2026 capex ~plan, no overrun        | 18                           | $0.50                         | $4.17                    | ~**1%** (18 mo)              |
| **Bull**            | $4+ gas, deficit clears 2026, production holds | 12                           | $0.80                         | $6.67                    | ~**63%** (12 mo)             |
| **Bull**            | Same                                           | 18                           | $0.80                         | $6.67                    | ~**38%** (18 mo)             |
| **Bear**            | Low gas + 2026/27 capex adds deficit           | 36+                          | $0.20                         | $1.67                    | **Negative**                 |

**HK run-rate check:** If post-recovery NPI were ~**$43M/year** (HK Q1 2025 estimate), that is ~**$0.92/unit** → **~22%** cash yield on **$4.10** — equity yield curve upside if reinstatement occurs, before any re-rating above yield-implied price.

**Opinion:** At **$4.10**, the **bull case** still fits HK’s steep equity yield curve profile, but **base case math is thin** (~1% annualized over 18 months). **Human stance: `watch`** — going-concern and depletion risk dominate; partial dhando does not justify sizing until deficit trajectory clears and administrative/LOC risk recedes.

### Mesabi precedent (HK comp)

HK Q1 2025: Mesabi suspension → reinstatement → **~two-year** journey to fully recovered share price. **Inference:** If SJT follows similar pattern, reinstatement could trigger **re-rating** toward prior yield-implied levels — but SJT lacks Mesabi’s arbitration lump-sum catalyst and faces **ongoing Hilcorp capex** charges.

---

## What the deep dive got right / wrong


| Deep dive claim                          | Assessment                                                                                              |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| Zero royalty FY2025                      | ✓ Correct                                                                                               |
| Not a croupier; no moat                  | ✓ Correct                                                                                               |
| Dhando `none` at zero cash flow          | **Partially wrong framing** — missed time arbitrage / partial dhando if price discounts recoverable NPI |
| Optionality on gas                       | ✓ Correct; HK adds SoCal pipeline / data-center gas demand angle                                        |
| Inversion risks (zero royalty prolonged) | ✓ Correct and **more salient** post going-concern disclosure                                            |


---

## Revised classification


| Field                    | Prior (2026-05-21) | Revised (2026-05-22)                                  |
| ------------------------ | ------------------ | ----------------------------------------------------- |
| **Archetype** (Stahl)    | optionality        | optionality                                           |
| **Moat** (Munger)        | n/a                | n/a                                                   |
| **Dhando** (Pabrai)      | none               | **partial** (time arbitrage; not downside-safe today) |
| **Stance**               | watch              | watch                                                 |
| **Cycle**                | —                  | —                                                     |
| **Predictive attribute** | *(missing)*        | equity_yield_curve + market_structure_discount        |


---

## Classification


| Field                 | Value       |
| --------------------- | ----------- |
| **Archetype** (Stahl) | optionality |
| **Moat** (Munger)     | n/a         |
| **Dhando** (Pabrai)   | partial     |
| **Stance**            | watch       |
| **Cycle**             | —           |


## [HUMAN REVIEW]

- [x] **Unit price:** ~**$4.10** (2026-05-22) — inserted in worksheet above.
- [x] **Stance:** **`watch`** confirmed — partial dhando insufficient vs going-concern and depletion; no `accumulate`.
- [ ] Track **monthly excess production cost balance** in 8-K exhibits.
- [ ] Model **2026 $14M capex plan** + 2027 horizontal completion costs vs deficit paydown.
- [ ] Compare **Mesabi Trust** post-reinstatement re-rating if distributions resume.

---

## [PROPOSED MEMORY]

*Promoted to `_system/memory/MEMORY.md` 2026-05-22 (human approved).*

---

## Primary sources cited

1. `SJT/investor-documents/sec-edgar/10-K_20260327_rpt20251231_acc0001193125_26_128710.htm`
2. `SJT/investor-documents/sec-edgar/10-Q_20260514_rpt20260331_acc0001193125_26_223189.htm`
3. `SJT/investor-documents/sec-edgar/8-K_20260518_rpt20260518_acc0001193125_26_228303.htm`
4. `_system/reference/investment-wisdom/horizon-kinetics/HK-Q1-2025-Commentary-extract.txt`
5. `_system/reference/investment-wisdom/horizon-kinetics/HK-Q3-2025-Commentary-extract.txt`
6. `_system/reference/investment-wisdom/horizon-kinetics/Stahl-Equity-Yield-Curve-extract.txt`
7. `SJT/research/deep_dive_2026-05-21.md`

