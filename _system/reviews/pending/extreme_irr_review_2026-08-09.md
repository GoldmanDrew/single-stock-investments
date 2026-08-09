# Extreme-IRR review — 5 tickers cleared by outlier_validation

**Date:** 2026-08-09 · **Revision 2** (supersedes rev 1 of the same date)
**Trigger:** `validate_dashboard_data.py` warning — "Extreme IRRs cleared by outlier_validation (human review advised): ABX=-26.24%, AEHR=-25.98%, AXON=-52.60%, AXTI=-40.40%, CEG=-27.36%"
**Machine-readable adjudication:** `_system/research/extreme_irr_adjudication_2026-08-09.json`
**Authority:** advisory only. No stance, no `valuation.json`, no `human_decision.json`, no script was changed by this pass.

> **Amendments to revision 2 (documentation only).** A follow-up verification pass confirmed all five verdicts and found nine defects in how they were *stated*. All are fixed in place below and marked in situ; no verdict, stance, `valuation.json` or contract field was touched. In brief: the rule gained an **admissibility clause** it formally needed for AXTI; the **strongest AXTI variant was missing** and is now the headline row (a facts-only cash restatement inside AXTI's own component method — **$11.6656/sh, -21.81%**, no anchor replacement required); **variant breadth** was applied unevenly across tickers and is now stated explicitly; **ABX's verdict was unreasoned** under the stated rule and is re-reasoned under a new fourth defect class (*fabricated judgment*); the AXON $1.276B swing was **mis-attributed** to date alone; the AXTI share reconciliation named the **wrong mechanism** and is now exact against the 424B5; the AXTI pro-forma cash row now **names its tag**; a stale `git status` row count is **dropped**; line-number citations now carry **symbol names**; and XC-8 has been appended to `_system/memory/corrections.md`.

> **Why there is a revision 2.** An adversarial re-verification reproduced rev 1's arithmetic exactly and then overturned two of its five verdicts. **AXTI is not real — it is a share-count artifact**, because AXT closed a $600.2M net follow-on between the balance-sheet date the contract uses and the share count it divides by. **AXON is not an artifact — it is real**, because rev 1 corrected the cash side on the wrong balance-sheet date and then cleared the band using the single most favourable normalization year out of three. Several supporting claims also failed checking and are corrected below. Every number in rev 2 was recomputed from the on-disk proofs and companyfacts in this pass.

---

## The rule, stated once and applied to all five

Rev 1 used two different rules. It called AXTI *real* because the extremity survived a ladder of anchors, then called AXON an *artifact* on the strength of one normalization year — the only one of three that cleared the band. That is the same evidence standard producing opposite verdicts.

**Rule (rev 1's own stated method, applied consistently):**

1. Correct **every** defect found in the contract's inputs — period mismatches, omitted balance-sheet items, subsequent capital events, sign errors, and unsourced or reverse-engineered judgments — **without touching** the model's method or its genuinely sourced judgments.
2. **Admissibility.** A variant counts only if it is stated **as of the same date as the market price it is compared against**. A variant describing the enterprise at an earlier date, however internally consistent, is not a candidate answer to "what is this share worth at today's price".
3. Recompute the annualized return **across the reasonable range** of *admissible* corrected inputs, not one hand-picked variant.
4. The flag is an **artifact** only if the corrected result lands **inside** the ±25% band across that range. If |return| ≥ 25% survives correction, the flag is **real** — whatever else is wrong with the proof.

> **Why step 2 was added (amendment).** Without it the rule is incomplete, and AXTI's own variant table contradicts it: the row *"pre-raise book $274.874M ÷ 55,579,000 pre-raise shares"* is arithmetically correct, internally consistent, and lands at **-30.83%, outside the band** — so a literal reading of steps 1 and 3 would have to keep AXTI "real". Rev 2 excluded it by a prose aside ("describes a company that no longer exists"). Step 2 makes that exclusion part of the rule: the price is a 2026-08-09 price, so the enterprise must be stated post-2026-04-22. The pre-raise row is kept below as **diagnostic** arithmetic — it isolates the size of the share-count artifact — and is marked inadmissible. *(AXTI does not actually depend on this: its headline row is inside the band on the contract's own component method with one fact corrected, and needs no admissibility argument at all.)*

### Defect classes

The rule needs to know what kind of defect it is correcting, because "hold the judgments fixed" is protective for some defects and self-defeating for others.

| Class | Defect | How it is corrected | Instances |
|---|---|---|---|
| **D1** | Wrong or incomplete **fact** | Re-select the tag | AXTI/AXON omitted `ShortTermInvestments`/`MarketableSecurities`; AEHR dropped sign; AEHR stale `net_financial_claims` |
| **D2** | **Date mismatch** between two facts that must describe the same enterprise | Re-date, then apply admissibility | CEG (post-Calpine sheet ÷ pre-Calpine cash flow); AXON |
| **D3** | Numerator/denominator mismatch **inside one per-share division** | Re-date *both sides*; survives any balance-sheet-only fix | AXTI (XC-8) |
| **D4** | **Fabricated judgment** — *new in this amendment* | Replace the point value with a **range** and test whether the verdict survives | ABX's 4.0x; AXTI's 11.75x |

**D4 in full.** A number presented in the proof as a derived or sourced judgment is in fact a hardcoded constant, typed to reproduce a pre-existing answer and then reverse-engineered into the proof under a technical-sounding label. It is not a wrong *fact*, so step 1's "correct the inputs" does not reach it; and it is not a sourced *judgment*, so "hold the judgments fixed" must not protect it. Holding judgments fixed is what stops an adjudicator manufacturing whatever answer it wants by re-picking multiples — that protection is owed to a judgment someone actually exercised and can be argued with. Extending it to a typed constant would make any sufficiently fabricated proof un-adjudicable.

### Variant breadth is applied unevenly — stated, not hidden

**AXTI and ABX are adjudicated with anchor replacement** (book equity, revenue and earnings multiples substituted for the published component set). **AXON and CEG are adjudicated facts-only** (published model, judgments and multiples held exactly fixed; only locked facts re-selected or re-dated). AEHR gets both.

That asymmetry follows the *defect class*, not a considered choice about evidence standard: where the defect is D1/D2/D3 the published method survives correction, so facts-only is the natural test; where it is D4 the published method **cannot** be held fixed, because holding it fixed *is* holding the fabricated number fixed. AXTI was framed with anchor replacement in rev 1 and rev 2 carried that forward even though its decisive defects are D1 and D3 — that is corrected below, and AXTI's headline is now the facts-only row.

**No verdict turns on it, and this was checked rather than assumed.** Applying an ABX-style audited-book anchor to **AXON** — the ticker where anchor replacement was *not* used — gives `StockholdersEquity` $3,242.658M at 2025-12-31 ÷ 80.602077M = **$40.2305/sh, -32.14%**, and $3,534.113M at 2026-03-31 ÷ 80.602077M = **$43.8464/sh, -31.30%**. Both are outside the band and both are *worse* than the -31.04% three-year facts-only variant, so AXON stays real on either breadth. CEG already clears facts-only at -18.72%, so anchors cannot make it real. It is recorded because an adjudication that silently varies its evidence breadth by ticker is the exact failure rev 2 charged rev 1 with.

To be inside the band over 7 years, value per share must exceed 0.75⁷ × price:

| | ABX | AEHR | AXON | AXTI | CEG |
|---|---|---|---|---|---|
| price | $10.86 | $109.89 | $607.20 | $65.27 | $267.25 |
| **band threshold** | **$1.4496** | **$14.6685** | **$81.0514** | **$8.7125** | **$35.6736** |

---

## Verdicts

| Ticker | Published IRR | Verdict | Δ from rev 1 | The one-line reason |
|---|---|---|---|---|
| **AXTI** | -40.40% | **artifact** | **real → artifact** | Pre-raise balance sheet ÷ post-raise share count. AXT took in **$600.2M net on 2026-04-22** — $9.17/sh against an $8.71/sh threshold. Correcting **one fact** inside AXTI's own component method gives **$11.6656/sh, -21.81%**; pro-forma cash alone -22.7%, pro-forma book -20.3%. |
| **CEG** | -27.36% | artifact | — | Charges $16.99B of *post*-Calpine debt against $1.288B of *pre*-Calpine FY2025 cash flow. Matched 2025-12-31 sheet: **-18.7%**. |
| **ABX** | -26.24% | artifact | — | **D4, fabricated judgment**: the extremity is a `4.0` typed into a build script and re-presented as a derived `4.0027x`. At 6x -16.5%, at 8x -10.8%, at audited book -12.6% — it exists nowhere but at the fabricated value. |
| **AXON** | -52.60% | **real** | **artifact → real** | The bridge *is* broken, but on the **date-matched** 2025-12-31 sheet the corrected range is **-31% to -39%**. Only FY2024 alone clears, at -24.7%. |
| **AEHR** | -25.98% | real | — | $3.57B market cap on a shrinking, loss-making ~$45M-revenue business. Every correction makes it worse: -26.8%, then -61.7%. |

---

## AXTI — the verdict that flips, and why rev 1 missed it

AXT closed an underwritten follow-on on **2026-04-22**:

- 8,560,311 shares at **$64.25**, plus a 1,284,046-share over-allotment **exercised in full** on 2026-04-22
- **$632.5M gross / $600.2M net**

This is not obscure. It is in **Note 20 Subsequent Events** *and* the "Recent Financing" and liquidity sections of the MD&A of **the very 10-Q the contract cites**, and in the 424B5 sitting on disk at `AXTI/investor-documents/sec-edgar/424B5_20260421_rpt_acc0001213900_26_046176.htm`.

The share reconciliation closes **exactly, to the share** — and the residual rev 2 waved at is explained. *(Amended: rev 2 wrote "173 shares apart — ordinary option/RSU noise", which named the wrong mechanism.)* The 424B5 states both sides itself:

> "The number of shares of common stock that will be outstanding after this offering as shown above is based on **55,578,827** shares of common stock issued and outstanding as of April 20, 2026"
>
> "Shares of Common Stock to be Outstanding Immediately After this Offering: 64,139,138 shares of common stock (or **65,423,184** shares if the underwriter exercises its option to purchase additional shares in full)"

The option **was** exercised in full on 2026-04-22. So:

| | shares | source |
|---|---|---|
| prospectus base, outstanding at 2026-04-20 | 55,578,827 | 424B5 footnote (1) |
| + April offering (8,560,311 + 1,284,046) | 9,844,357 | 424B5 / 10-Q Note 20 |
| = | **65,423,184** | — |
| contract `fully_diluted_shares` (cover page, as of 2026-05-04) | **65,423,184** | `dei:EntityCommonStockSharesOutstanding` |
| **difference** | **0** | |

The prospectus itself *projects* 65,423,184 as the post-offering count on full exercise, and that is precisely the number the contract divides by. There is no share gap and no option/RSU settlement anywhere in the reconciliation. The 173-share discrepancy rev 2 reported is on the **XBRL side**, not the offering side: `us-gaap:CommonStockSharesOutstanding` at 2026-03-31 is tagged **55,579,000** — the thousands-rounded value of the 55,578,827 actual count (55,579,000 − 55,578,827 = **173**). It is scale rounding in the balance-sheet tag, nothing more.

**The contract divides a pre-raise numerator by a post-raise denominator.** Every per-share number in it, and every anchor rev 1 used to declare the flag "real", inherits that.

#### The variant that settles it needs no anchor at all *(amendment — this row was missing from rev 2)*

The strongest correction is not an anchor replacement. It is **one fact**, restated inside AXTI's own published five-component method, with every judgment, multiple and other component left untouched: `cash_and_liquidity` currently locks `cash_m = 57.9` (`us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents`, as of 2026-03-31) and applies `usable_cash_pct` 1.005, giving $58.19M and **$0.8894/sh**. On a pro-forma basis that component is **$707.344M** — $41.769M cash + $65.375M short-term investments at 2026-03-31, plus the $600.2M of April net proceeds:

| component | published | facts-only corrected |
|---|---|---|
| `midcycle_substrate_operations` | 1.4009 | 1.4009 *(untouched)* |
| **`cash_and_liquidity`** | **0.8894** | **10.8118** |
| `tongmei_hk_listing_option` | 0.5000 | 0.5000 *(untouched)* |
| `pe_redemption_liability` | -0.7490 | -0.7490 *(untouched)* |
| `dilution_reserve` | -0.2981 | -0.2981 *(untouched)* |
| **sum** | **$1.7432** | **$11.6656** |
| **annualized return at $65.27** | **-40.40%** | **-21.81%** — *inside the band* |

`(11.6656 / 65.27)^(1/7) − 1 = -21.81%`. No anchor replaced, no admissibility argument, no judgment touched — just the two defects this pass identifies (XC-6a omitted short-term investments, XC-8 pre-raise numerator ÷ post-raise denominator) corrected on the one locked fact that carries them. **This is the headline result for AXTI.** *(The published `usable_cash_pct` base of 1.005 is set to 1.000 here because 1.005 is an uplift* above *the filing balance and cannot apply to a figure already stated in full. Carrying 1.005 anyway gives $10.8659/sh for the component, $11.7197 total, **-21.75%** — also inside the band. Either way AXTI clears on facts alone.)*

The anchor-replacement variants all agree:

| Anchor | value/sh | IRR | inside band? | admissible? |
|---|---|---|---|---|
| **facts-only cash restatement (headline)** | **$11.6656** | **-21.81%** | **yes** | yes |
| as published | $1.7432 | -40.40% | no | yes |
| rev 1: $274.874M book ÷ **post**-raise shares | $4.2015 | -32.42% | no — **void, this is the artifact** | **no** |
| internally consistent pre-raise: $274.874M ÷ 55,579,000 | $4.9456 | -30.83% | no — **diagnostic only** | **no** (rule step 2) |
| **pro-forma cash + securities only** ($41.769 + $65.375 + $600.2 = $707.344M) | **$10.8118** | **-22.65%** | **yes** | yes |
| **pro-forma book equity** ($274.874 + $600.2 = $875.074M) | **$13.3756** | **-20.26%** | **yes** | yes |
| pro-forma book incl. redeemable NCI ($898.650M) | $13.7360 | -19.96% | yes | yes |

The pre-raise row is retained because it is *useful*, not because it counts: $4.9456 pre-raise against $4.2015 on the same numerator over the post-raise count isolates the share-count error alone at 1.18x. Under rule step 2 it is inadmissible — it prices a 2026-03-31 enterprise against a 2026-08-09 market price.

**Which cash tag the pro-forma row uses** *(amendment — rev 2 printed the figure without naming the tag, which read as an inconsistency against its own prose)*. The row uses the **narrow** `us-gaap:CashAndCashEquivalentsAtCarryingValue` = **$41.769M** at 2026-03-31, while the surrounding text and the fact ledger anchor on the **broader** `us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents` = **$57.869M** (which is what `cash_m` actually locks). On the broader tag the row is ($57.869 + $65.375 + $600.2) = **$723.444M ÷ 65,423,184 = $11.0579/sh, -22.40%**. Both are inside the band; the narrow tag is the conservative one and is used for that reason.

The net proceeds alone are **$9.1741 per post-raise share** against an **$8.7125** threshold. *The capital raise by itself pushes AXTI inside the band before any operating asset is valued above zero.* The pro-forma cash row assigns exactly $0 to the InP franchise, the Tongmei stake and the substrate business.

**And the same one-sided net-cash bug rev 1 made the centerpiece of the AXON verdict is sitting in AXTI, unflagged.** `us-gaap:ShortTermInvestments` at 2026-03-31 is **$65,375,000** — *larger than the $57.869M of cash the ledger locked* — and is not in the bridge. It also explains a fact rev 1 relied on: cash fell $128.366M → $57.869M, which reads as a 55% burn, but STI went **$0 → $65.375M** over the same quarter. Cash + STI: $128.366M → $123.244M. The December 2025 offering proceeds were moved into short-term investments and the cash tag cannot see it.

Everything rev 1 said about the *magnitude* still stands and is unaffected: the hardcoded `LEGACY` table, the 11.75x multiple that exists because $1.40/sh was typed, the FY2021-FY2022 owner-cash anchor against a business inflecting at +39.1% YoY, and a `dilution_reserve` priced at $45.86 (Yahoo, 2026-07-17) and sourced to a *filing-facts* file. Note what that last one now means: **a dilution reserve computed before the largest dilution event in the company's recent history, at a price 30% below the market.**

What this review does **not** claim: that AXT is cheap. At $65.27 the market cap is $4.270B against FY2025 revenue of $88.326M, a $21.976M operating loss and five consecutive quarters of negative operating cash flow. But price/pro-forma-book is **4.9x**, not the 15.6x rev 1 computed — and the market itself set $64.25 three weeks after the balance-sheet date in question. That is a valuation argument, not a ≥25% seven-year artifact-free finding.

---

## AXON — the other flip

Rev 1 was right that the inputs are broken. It got the correction wrong twice.

**1. It never applied its own CEG test.** `normalized_owner_earnings_m` is an **FY2025** figure ending **2025-12-31**. Cash and debt are locked at **2026-03-31**. That is the exact defect rev 1 correctly diagnosed for CEG — and then did not apply here, even while fixing the *other* defect on the same balance sheet.

| Cash + short-term investments + marketable securities | 2025-12-31 | 2026-03-31 (used) |
|---|---|---|
| `CashCashEquivalentsRestrictedCash…` | $1,213.393M | $471.156M |
| `ShortTermInvestments` | $505.417M | $260.000M |
| `MarketableSecurities` | $27.213M | $18.052M |
| **total** | **$1,746.023M** | **$749.208M** (**-57.1%**) |

The two defects **together** move the net financial position from **+$15.853M** to **-$1,259.831M** — a $1.276B swing on a business whose entire modelled equity value is $263M. *(Amended: rev 2 attributed the whole swing to "the date choice alone", which folded the cash-tag defect into the date defect.)* Attributing it correctly: the **date alone**, holding the cash side complete, moves it from +$15.853M at 2025-12-31 to **-$981.779M** at 2026-03-31 — a $997.6M swing; the remaining **$278.052M** is the one-sided cash tag (`ShortTermInvestments` $260.000M + `MarketableSecurities` $18.052M at 2026-03-31, XC-6a). On the matched sheet the **same FY2025 base** gives **$19.0924/sh and -39.00%**, not the $6.72 / -47.45% rev 1 published as "the cash correction".

**2. It cleared the band on one cherry-picked year.** Holding the published judgments fixed (growth 6.3%, discount 10%, terminal 18x, 80.602077M shares) and correcting only the *facts*:

| Variant (all on the date-matched 2025-12-31 sheet) | owner earnings | value/sh | IRR | inside band? |
|---|---|---|---|---|
| published (FY2025 base, 2026-03-31 sheet, cash tag only) | $75.081M | $3.2655 | -52.60% | no |
| rev 1's fix (complete cash, **wrong date**) | $75.081M | $6.7152 | -47.45% | no |
| **FY2025 base, date-matched** | $75.081M | **$19.0924** | **-39.00%** | no |
| …also subtracting `LongTermDebtCurrent` $80.552M | $75.081M | $18.0931 | -39.46% | no |
| FY2023 base ($189.263 − $59.635) | $129.628M | $32.8204 | -34.09% | no |
| **3-year FY2023–FY2025 average** | $178.079M | **$45.0140** | **-31.04%** | no |
| FY2024 base ($408.312 − $78.785) — *the only one that clears* | $329.527M | $83.1293 | **-24.73%** | **yes, by 2.6%** |

Six of seven variants are outside the band, five by more than 6 points. The one that clears does so by 2.6% of value per share, and only because FY2024 pairs the highest OCF of four years with capex ($78.785M) that is low *relative to that year's cash generation*.

**The trough argument also does not survive checking.** Rev 1 cited "$169.312M of net income in Q1 2026, more than the whole of FY2025 ($124.656M)". But `us-gaap:OperatingIncomeLoss` for Q1 2026 is only **$29.243M** — that net income is dominated by non-operating items. FY2025 shows the same pattern in reverse: a **-$62.076M operating loss** against $124.656M of net income. And most decisively, **Q1 2026 operating cash flow was -$31.517M** against $23.125M of capex — **-$54.6M on the very measure the model capitalizes**, in the quarter after the alleged trough.

**One rev 1 claim withdrawn.** The parenthetical that Axon "also carried $1,733.777M of AFS debt securities at 2025-12-31, so the real net financial position is nowhere near -$1.26B" should not be used as an additive asset. $1,733.777M is the AFS fair-value disclosure and **overlaps** the cash, STI and marketable-securities lines already counted (which total $1,746.023M). The corrected net financial position at 2025-12-31 is **+$15.853M**, not +$1.7B.

Two secondary defects stand, unchanged: `shares_m` is the **basic cover-page count** labelled "Diluted shares"; $1.731B of convertibles is charged at face with **no offsetting conversion shares**; and the locked fact's locator names `us-gaap:NetCashProvidedByUsedInOperatingActivities` ($211.339M) for a value of $75.081M.

**Verdict: real — but the number is not -52.60%, and it is not -47.45% either.** The honest corrected range is about **-31% to -39%**. And note what none of these variants test: the 6.3% growth and 18x terminal are unexamined judgments carried through every row. If AXON is genuinely a 30%-compounder, *those* are the numbers that decide it. The finding is that the **flag** is correct, not that the **value** is.

---

## The finding that matters most (largely intact, one claim corrected)

**A cleared `outlier_validation` on these five means almost nothing, because the contracts are corroborating themselves.**

The `extreme_return_validated` assignment in `build_contract` (`universal_valuation_contract.py`, currently :274-282 — **cite the symbol; line numbers drift**) sets the flag when three boxes are ticked: status is `"passed"`, `independent_methods` is non-empty, and `evidence_refs` is non-empty. It never checks that the "independent" method is independent, and never compares the two answers.

- Four of five list **`component_economic_value`** as an independent method. That *is* the contract's own primary method — ABX's `outlier_validation.primary_method` literally reads `"component_economic_value"`.
- All five list **the file being validated** (`{TICKER}/research/valuation.json`) as an evidence ref.
- AXON's note asserts the exact conclusion this pass overturns: *"net debt ~$1.26B, not a proof error."* The $1.26B **is** the proof error.

**The one genuinely independent number disagrees — in four of five it says the return is not extreme:**

| Ticker | Contract IRR | `lawrence_owner_cash_irr` | Extreme by the 25% rule? |
|---|---|---|---|
| ABX | -26.24% | **-2.40%** | no |
| AEHR | -25.98% | **-16.02%** | no |
| AXTI | -40.40% | **-9.92%** | no |
| CEG | -27.36% | **-12.50%** | no |
| AXON | -52.60% | -37.90% | yes |

Rev 1 treated the AXTI disagreement as a defect *of the cross-check*. On rev 2's arithmetic, the cross-check was closer to right than the contract.

### Corrected: the "byte-identical to legacy" claim

Rev 1 wrote that **every** component's `range_per_share` is *byte-identical* to its `legacy_range_per_share`. **That is false as written.** Verified component by component:

| Ticker | exactly identical | which |
|---|---|---|
| AXTI | **1 of 5** | `tongmei_hk_listing_option` |
| ABX | **2 of 5** | `life_solutions_engine`, `asset_management_franchise` |
| AEHR | **1 of 4** | `cycle_customer_concentration_reserve` |

The true statement is weaker in form and no weaker in force: for every other AXTI and ABX component, and for AEHR's `midcycle_burn_in_operations`, the derived value differs from legacy by **at most $0.002/sh** — it *rounds to* the legacy number at the two decimal places the legacy table was typed at. Largest relative gaps: AXTI `dilution_reserve` -0.2981 vs -0.30 (0.63%), AEHR midcycle low 0.5882 vs 0.59 (0.31%), ABX `technology_platform_option` 0.1995 vs 0.20 (0.25%). **Two AEHR components genuinely diverge and are not reverse-engineered:** `net_financial_claims` is `{3.2207, 4.6323, 5.8405}` against legacy `{0.8, 1.05, 1.3}`, and `deferred_revenue_milestone_option` is `{0, 12.19, 36.24}` against legacy `{0, 11.8, 35.1}`.

The mechanism is still on disk and still decides the answer: the `life_solutions_engine` builder in `build_abx_contract_proofs.py` computes `mult = LEGACY["life_solutions_engine"][case] / OP_PS` (currently :97), so ABX's "Duration-adjusted reinvestment capitalization multiple of 4.0027x" exists only because the `LEGACY` constant says `base = round(OP_PS * 4.0, 2)` (currently :42). The component is declared `method_id: owner_earnings_reinvestment_dcf` and contains no discounting whatsoever. It is EBIT × 4.

### Corrected: the stale-price class is **not** closed

The stale cross-checks are real — AEHR's at **$77.36** against $109.89 (the `PRICE` module constant in `build_aehr_contract_proofs.py`, currently :21), AXON's at $527.48 against $607.20 (reporting -51.63% where the contract says -52.60%), ABX's at ~$10.26 against $10.86.

But rev 1's exculpation does not hold. It claimed the contract prices are independently corroborated because each matches `end_price` in `{TICKER}/research/total_return_panel.json`. **Every one of those panels carries `price_source: "yahoo:{TICKER}"` — the same vendor feed as the contract price.** Agreement demonstrates internal consistency and nothing else.

**And it is not even true for AEHR:** panel `end_price` is **$105.465** against a contract price of **$109.89**, a 4.2% gap rev 1 asserted did not exist. AEHR's verdict is unaffected (-25.55% at the panel price, still extreme), but the class stays open and needs a genuinely independent price source.

---

## Ticker detail (unchanged verdicts)

### CEG — artifact (still the clearest of the five)

The proof pairs a balance sheet with a cash-flow period that describes a **different company**.

| Fact | 2025-12-31 | 2026-03-31 (used) |
|---|---|---|
| `LongTermDebtNoncurrent` | $7,250M | **$16,994M** |
| Cash and restricted cash | $3,748M | **$1,171M** |

Long-term debt **more than doubled** (+$9,744M) and cash fell $2,577M in one quarter as Calpine closed. Owner earnings are calendar-2025: FY2025 OCF $4,237M less capex $2,949M = $1,288M, containing **none** of the acquired earnings. Implied net debt of $15,823M is **$43.81/sh** against a base value of **$28.53/sh** — the entire negative result *is* the unearned debt. Rebuild the identical proof on the matched 2025-12-31 sheet:

> equity $22,625.403M, value/sh **$62.6413**, annualized return **-18.72%** — inside the band, before crediting Calpine with a dollar. (Reproduced in this pass from the on-disk trace, `enterprise_value 26127.40348497`.)

CEG also carries the XC-8 pattern — `shares_m` as of 2026-04-30 against a 2026-03-31 sheet — but no capital event falls in that window, so it does not affect the verdict. It is the same unguarded pattern that decided AXTI.

### ABX — artifact (defect class **D4**, fabricated judgment)

There is no model here. The `LEGACY` module constant in `build_abx_contract_proofs.py` says `base = round(OP_PS * 4.0, 2)` (currently line 42) and everything downstream is dressing.

> **Why ABX needed re-reasoning (amendment).** Rev 2's verdict was *unreasoned under its own rule*. Step 1 permits correcting **inputs** "without changing the model's method, judgments, discount rate or terminal multiple" — yet ABX was adjudicated by varying the capitalization multiple and substituting audited book, i.e. by changing exactly what step 1 said to hold fixed. The resolution is not that ABX is an exception. It is that **ABX's defect is not a wrong fact at all.** Its facts reproduce from the filings: FY2025 operating income $88.757M, revenue $235.2M, debt $291.844M, equity $418.54M, 99.2M shares. What is wrong is a **judgment that was never made**. The typed constant is re-presented in the proof as a derived quantity: the `life_solutions_engine` builder computes `mult = LEGACY["life_solutions_engine"][case] / OP_PS` (currently line 97) and reports the quotient, **4.0027x**, as a *"Duration-adjusted reinvestment capitalization multiple"*. The label describes a derivation that does not exist — the quotient is just the typed 4.0 divided back out. Nothing in the 10-K, the transcripts or the method registry supports 4x. Under **D4** the correction is not "replace the fact" but "replace the point value with a range and test whether the verdict survives":

| Multiple on FY2025 consolidated **pre-tax** operating income | value/sh | IRR |
|---|---|---|
| 4.0x (as published) | $1.2901 | **-26.24%** |
| 6.0x | $3.08 | -16.49% |
| 8.0x | $4.87 | -10.84% |
| audited book value ($418.54M ÷ 99.2M) | $4.2192 | -12.63% |

To stay outside the band ABX must be worth **less than $1.4496/sh — below 0.35x audited book**, and below 4.5x FY2025 pre-tax consolidated operating income. Only the typed 4.0x delivers that; every other point in the range is inside the band. **The extremity exists nowhere except at the fabricated value — that is the D4 test, and ABX fails it. Artifact.**

Note how much weaker — and how much more honest — this claim is than rev 2's: it is *not* that ABX is worth $3.08 or $4.22. It is that **nothing in the proof establishes that ABX is worth less than $1.4496/sh**, which is what the flag asserts. (ABX is adjudicated by anchor replacement rather than facts-only because under D4 that is *forced*, not chosen: a facts-only variant holds the fabricated multiple fixed and can only ever return -26.24%. See "Variant breadth" above.)

Two asymmetries push the same direction:

- The model subtracts **100% of the $291.844M of debt** but explicitly declines to carry the life-settlement policy portfolio as an asset (`build_abx_contract_proofs.py:130`). So the debt that funds the portfolio is counted and the fair-value-marked portfolio behind $902.2M of total assets and $418.5M of book equity is not. **That is the WHK failure mode in `corrections.md`, inverted.**
- `longevity_and_funding_reserve` charges another -$59.5M partly for *"credit spread widening on ABXL notes"* — a second bite at the same credit claim.

The anchor is shaky in both directions: 37.7% operating margin ($88.757M on $235.2M) against only $25.680M of operating cash flow means most of that "income" is non-cash fair-value marks, and cash is lumpy (Q1 2026 OCF $91.7M vs FY2025 $25.7M).

### AEHR — real

At $109.89 on 32.48M shares that is a **$3.569B market capitalization**, roughly 79x trailing revenue, against:

- FY2025 (to 2025-05-30): revenue $58.968M, operating **loss** $5.677M, operating cash **outflow** $7.4M
- FY2026 nine months (to 2026-02-27): revenue $31.166M, operating loss $12.943M, net loss $8.517M
- FY2026 full year: net loss $7.126M; $116.358M cash, no debt; 77% of revenue from the top five customers

Every correction makes it worse:

| Correction | value/sh | IRR |
|---|---|---|
| as published | $13.3733 | -25.98% |
| repriced at the vendor panel's $105.465 | $13.3733 | -25.55% |
| `net_financial_claims` restated to FY2026 cash $116.358M ÷ 32.48M = $3.5825/sh | $12.3235 | **-26.84%** |
| …and strip the unsourced $383.412M backlog option (+$12.19/sh) | $0.1335 | **-61.68%** |

*(Rev 1 reported -26.74% and -58.07% for the last two; those did not reproduce exactly. The reproduced figures are above; direction and verdict unchanged.)*

Also: `cycle_customer_concentration_reserve` records `operating_income_m = 5.677 USD_m` as a **locked fact** where `us-gaap:OperatingIncomeLoss` for FY2025 is **-5,677,000** — the sign was dropped, and the same component's OCF input handles its sign correctly. Three different share counts appear in one contract: 32.480M, 31.453M, 29.581M.

Right answer, wrong reasoning.

---

## Structural notes

**`no_double_counting` can never fail.** The `overlap_key` / `overlap_seen` / `double_counting_flags` loop in `build_contract` (`universal_valuation_contract.py`, currently :168-172) flags a double count only when two additive components share an `overlap_key`, and every builder assigns `overlap_key = component_id` — unique by construction. ABX shows the miss: `life_solutions_engine` capitalizes **consolidated** FY2025 operating income while `asset_management_franchise` separately capitalizes 25% of the Asset Management **segment**'s revenue ($33.8M of that same $235.2M) and `technology_platform_option` capitalizes Technology Services segment revenue. `double_counting_flags: []`. AXTI likely has the same problem between `midcycle_substrate_operations` and `tongmei_hk_listing_option`.

**The cash/debt bridge is one-sided *and* undated (XC-6).** In `automate_valuation_readiness.py`, `build_fact_ledger`'s `companyfact_specs["cash_m"]` entry selects from `CashAndCashEquivalentsAtCarryingValue` / `CashCashEquivalentsRestrictedCash…` only — `ShortTermInvestments`, `MarketableSecurities` and AFS portfolios are never added — while `companyfact_specs["debt_m"]` subtracts long-term debt in full. **Cite by symbol:** rev 2 recorded these at :378-385; the file was modified again on 2026-08-09 and they now begin at :369. AXON loses $278.052M at 2026-03-31; **AXTI loses $65.375M, more than the $57.869M of cash that was locked.** And nothing checks that the balance-sheet date and the cash-flow period describe the same enterprise (CEG, AXON). The derived `normalized_owner_earnings_m` block in the same function (currently :430-438) also stamps the fact with `ocf["source"]`, so a reader following the AXON proof to `us-gaap:NetCashProvidedByUsedInOperatingActivities` finds $211.339M where the proof says $75.081M.

**NEW — the share count and the balance sheet are on different dates by construction (XC-8).** `shares_outstanding` comes from `dei:EntityCommonStockSharesOutstanding` via `ENTITY_SHARE_SPECS` → `_select_share_companyfact` (`automate_valuation_readiness.py`, currently :172-175 and :191 — **symbols, not lines**), whose `as_of` is the **filing cover date** (AXTI 2026-05-04, AXON 2026-04-30, CEG 2026-04-30). Cash, debt and equity come from the **balance-sheet date** (2026-03-31). Any issuance, buyback or debt raise in between enters the denominator and never the numerator, and nothing reads Subsequent Events. **This is strictly more dangerous than the CEG date mismatch: it mismatches a numerator and a denominator inside the *same* per-share division, so it survives any fix that only re-dates the balance sheet.** AXTI is a fully reconciling worked example. This is the recommended first patch — smallest blast radius, clearest failure mode.

**The reinvestment haircut has flip-flopped.** `c72fe6094e6` removed the `(1 - reinvestment)` haircut on `owner_cash_yN` in `compile_owner_earnings` (the `distribution_rate` node and the `owner_cash_y{N}` multiply nodes, currently :813-825 — rev 2 cited :733-751, which no longer points at them); `b0cb064adcf` restored it. `normalized_owner_earnings_m` is OCF minus **total** capex, so growth capital is already deducted once; a second retention haircut deducts it twice. The AXON and CEG artifacts on disk **predate** the restore (`owner_cash_yN = owner_earnings_yN × 1`, no `distribution_rate` node), so the published numbers do not include it. Re-running the compiler today would cut AXON's base from $3.2655 to about $1.27/sh and move every automation-compiled owner-earnings ticker. Settle it deliberately rather than by the next batch run.

---

## What was deliberately not changed

Four script defects are real and precisely located — self-corroborating `extreme_return_validated` (XC-1); one-sided *and* undated cash/debt selection (XC-6); the reinvestment flip-flop (XC-7); and the new share-count/balance-sheet date mismatch (XC-8). None was patched here:

- Tightening `extreme_return_validated` flips all five from a **warning** to an **error** — and per `_system/memory/corrections.md`, a validator ERROR fails the build step and **silently skips the Cloudflare deploy**.
- Changing the cash/debt fact selection rewrites the net financial position of every automation-compiled ticker.
- Flipping the reinvestment haircut would be the **third** reversal of the same three lines.
- XC-8 has the smallest blast radius and is the recommended first patch.

Exact patch sites are in `cross_cutting_findings` in the JSON, cited **by symbol** as well as by line number. *(Amendment: the `memory_row_proposed` row **has now been appended** to `_system/memory/corrections.md`, dated 2026-08-09, ticker AXTI/AXON. Rev 2 deferred it because that file was concurrently modified by another agent — but by the repo's own rule, a finding recorded only in an advisory file that is not itself durable is lost. The file was re-read immediately before the append and the row added append-only, preserving every existing row.)*

**Scope.** This pass wrote exactly two files: `_system/research/extreme_irr_adjudication_2026-08-09.json` and this review. It changed no ticker data, no stance, no `human_decision.json` and no script. That is the whole scope claim, and it is checkable at any time. Rev 1 implied a clean tree; that is not supportable — this working tree carries uncommitted changes from other agents continuously. *(Amended: rev 2 tried to quantify that with a `git status --porcelain` row count. The count was offered as a checkable claim and no longer checks — the tree moved within the same day. It has been **dropped** rather than re-measured: a git-state assertion inside a research artifact goes stale by design and corroborates nothing about the analysis.)*

---

## Suggested order of action

1. **AXTI** — re-lock the fact ledger pro forma: cash **+ short-term investments** at 2026-03-31 **plus the $600.2M of April net proceeds** against 65,423,184 shares; or, if the compiler cannot read subsequent events, re-lock shares at the prospectus base of 55,578,827 that matches the balance sheet and say so. That single change to `cash_and_liquidity`, with nothing else touched, moves the published base from $1.7432/sh to **$11.6656/sh** and the return from -40.40% to **-21.81%**. Then clear the extreme flag as an artifact. The magnitude defects (FY2021-22 anchor, 11.75x, the $45.86 dilution reserve) still need fixing before any capital view.
2. **CEG** — re-lock cash and debt to 2025-12-31 to match the FY2025 cash flow (or re-lock owner earnings pro-forma post-Calpine). Expect about -18.7%; the warning disappears legitimately.
3. **AXON** — keep the flag, kill the number. Date-match the balance sheet to 2025-12-31, complete the cash side, and re-lock the earnings base on a multi-year measure: the honest range is about **-31% to -39%**. Decide how the $1.731B convertible is treated — debt at face **or** conversion shares, not both. Then examine the 6.3% growth and 18x terminal, which no variant here tests.
4. **ABX** — source the capitalization multiple or replace the component with an actual discounted owner-cash model; decide explicitly on the policy portfolio; remove the segment double-count.
5. **AEHR** — keep the flag; restate `net_financial_claims` to $116.358M, fix the `OperatingIncomeLoss` sign, reconcile the three share counts, and source or drop the $383.412M backlog option. Reconcile the $109.89 contract price against the $105.465 panel price.
6. **Universe-wide** — add the XC-8 date-consistency guard first; then decide the reinvestment-haircut question and make `outlier_validation` reject a primary method listed as its own corroboration.

None of the five should be treated as decision-grade on the strength of a cleared outlier flag.
