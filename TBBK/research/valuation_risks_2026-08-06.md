# TBBK — the biggest risks at today's valuation

**Date:** 2026-08-06
**Price:** $72.095 (Yahoo close 2026-08-06) · **Market capitalisation:** $3,002 million · **Shares outstanding:** 41,634,439 (Form 10-Q cover, 2026-04-27)
**Contract:** `TBBK/research/valuation_contract.json` — decision grade, four components, no unresolved evidence
**Companion model:** `TBBK/research/buyback_eps_model.json`

---

## What you are paying for

At $72.10 The Bancorp trades at 13.6 times trailing twelve month earnings of $5.32, 12.0 times the midpoint of management's 2026 guidance, and 8.8 times the midpoint of the 2027 preliminary guidance. Against tangible capital the picture is different: shareholders' equity was $689.8 million at the end of 2025, so the market pays roughly 4.4 times book for a bank earning a 35% return on equity in the first half of 2026.

Both of those framings are true, and the gap between them is the whole argument. On earnings the stock looks ordinary. On capital it is priced as an exceptional business. Which one is right depends entirely on whether a 30%-plus return on equity survives, and the risks below are the specific ways it might not.

The decision-grade contract puts intrinsic value at **$87.00 per share in the base case**, with a range of **$48.50 to $141.93**. That is 21% above the current price in the base case and 33% below it in the low case. The framework's convention of annualising the gap over seven years gives 2.7% a year in the base case, negative 5.5% in the low case, and 10.2% in the high case. The honest summary is that the current price already contains most of the base case, and the distribution is wide in both directions.

---

## Risk 1. The 2027 guidance requires a step change in net income, not an extrapolation

This is the largest single risk, and it is arithmetic rather than judgement.

Management guides to $5.95 to $6.05 for 2026 and $8.10 to $8.30 for 2027. That is a 36.7% jump in earnings per share. The repurchase programme cannot supply most of it. At a 95% payout and a 13 times multiple the company retires about 7.3% of its shares a year gross, and roughly 4.6 points of it net across that particular twelve-month span. **The remaining 30 points have to come from net income.**

In dollars: the 2026 guidance implies about $249 million of net income, the 2027 guidance implies about $324 million. That is a **$75 million step in a single year**, from a company whose net income grew 13.1% in 2024, 4.9% in 2025, and an estimated 8.7% in 2026.

Nothing in the reported results yet shows where that $75 million comes from. Fintech is the plausible source, and it is growing well: adjusted fintech fee revenue compounded 14.4% a year from $82.3 million in 2021 to $141.3 million in 2025, with operating leverage positive in every year. But 14% growth on a $141 million fee base is $20 million a year, not $75 million.

The company describes the 2027 range as "generally consistent with the previous target," and it has already softened the nearer-term marker: the April 2026 deck showed a clean $7.00 fourth-quarter 2026 run rate, and the July 2026 deck restated that as $6.60 to $7.00. The bottom of the range moved down 5.7% in one quarter while the 2027 number was left alone. That is the sequence you would expect to see if the 2027 target eventually moves too.

**Why this matters at this price.** If 2027 lands at $7.00 rather than $8.20 and the market keeps paying 12 times, the stock is worth $84. If it lands at $7.00 and the multiple compresses to 10 times on a broken guidance track record, it is worth $70, which is where it trades now, having wasted a year. The 8.8 times 2027 multiple that makes the stock look cheap is only cheap if the 2027 number is real.

**Falsifier:** two consecutive quarters where the annualised fintech fee revenue run rate grows less than 15%, or any restatement of the 2027 range.

---

## Risk 2. The fintech credit enhancement is an undisclosed counterparty exposure that has grown ten times in two years

This is the risk least visible in the reported numbers, because by construction it nets to zero.

The Bancorp originates consumer fintech loans through marketers and servicers. It books a provision for credit losses on those loans and simultaneously books an equal amount in non-interest income under "Fintech loan credit enhancement," a contractual recovery from the fintech partner. The Q2 2025 Form 10-Q states it plainly: the arrangement "resulted in the company recording a $89.1 million provision for credit losses and a correlated amount in non-interest income resulting in no impact to net income."

The scale of what is being netted has grown very fast:

| | 2024 | 2025 | 2026 year to date |
|---|---|---|---|
| Fintech net charge-offs | $17.7m | $151.1m | $55.0m |
| Credit enhancement income | $30.7m | $169.3m | $54.6m |
| Average fintech balances | $138m | $607m | $1,254m |
| Implied loss rate on average balances | 12.8% | 24.9% | 8.8% annualised |

Average covered balances went from $138 million to $1,254 million in two years, a nine-fold increase. In 2025 the credit enhancement income of $169.3 million was **more than half** of the fintech segment's entire $310.6 million of non-interest income, and 74% of that year's $228.2 million of net income.

The exposure is an unsecured contractual claim. The filings do not disclose who the counterparties are, what their credit standing is, or whether the receivable is collateralised. The company itself treats the item as noise, stripping it out of its non-GAAP measures "to remove the volatility of that credit enhancement recovery." That is a reasonable way to show underlying fee trends. It is not a reason for an owner to ignore the exposure, because stripping something out of a performance metric does not strip it off the balance sheet.

Note also the asymmetry of the structure. The Bancorp keeps the fee income on these programmes in good times and is protected from losses by a partner promise. Fintech lenders are precisely the sort of counterparty whose ability to honour a large loss-sharing agreement is weakest exactly when the losses arrive, because the same credit deterioration hits their own balance sheet. The protection is negatively correlated with the event it protects against.

The valuation contract carries this as a fourth component, `fintech_credit_enhancement_reserve`, priced at one year of unabsorbed losses ($110 million annualised) times the probability the enhancement fails. At a 25% base-case probability that is $27.5 million, or $0.66 a share. In the low case, at a 60% probability, it is $1.59 a share. Those numbers are small against an $87 base case, and deliberately so: this is a tail risk, not an expected cost. The real damage in a failure scenario is not the direct loss, it is what the market would then pay for the rest of the fee stream.

**Falsifier, in the good direction:** the company discloses the identity and credit standing of the enhancement counterparties, or collateralises the receivable.

---

## Risk 3. The $10 billion asset cap is now within 6.5% and it binds everything

Total assets were $9,352.4 million at the end of 2025, against the $10 billion Federal Reserve Regulation II threshold above which the Durbin Amendment caps debit interchange. Assets grew 7.2% in 2025, which is $624.9 million. That leaves **$647.6 million of headroom, 6.5% of the cap, or roughly one more year of growth at the recent rate**.

This single constraint explains most of the company's structure. It is why capital is returned rather than retained: retained equity would have to support assets the bank is not allowed to grow. It is why management describes managing "to an asset cap of $10B (per FRB Reg II, Durbin)" as an integral part of strategy. It is why the whole Apex 2030 plan is about fee income and off-balance-sheet activity rather than lending.

Three ways it bites.

**It caps the spread business.** Fintech deposits are $8.1 billion at a 1.63% cost of funds, which is a genuinely excellent liability franchise. But the bank cannot lever it further. Deposits above the cap have to be swept off balance sheet, and $1.1 billion already is. The value of each incremental deposit dollar falls once you cannot lend against it.

**A breach would be expensive and is not reversible quickly.** Crossing $10 billion caps debit interchange on the programmes that make The Bancorp the number one United States prepaid issuer. The company has not quantified the hit, which is itself worth noting for a risk this close and this material.

**It caps the buyback.** Equity fell $100 million in 2025, from $789.8 million to $689.8 million, while the company earned $228.2 million. Capital returned therefore exceeded net income. Equity to assets is now 7.4%. If assets drift toward $10 billion the bank needs more capital, not less, and the payout ratio must come down below 100%. The buyback is bounded by regulatory capital, not by earnings, and the 100%-plus payout of 2025 is not a repeatable base case. The model uses 95%.

---

## Risk 4. Concentration in both directions

Two concentrations sit on top of each other.

**Funding.** Fintech Solutions supplies $8.1 billion of deposits, **96% of total bank deposits**, up from 93% one quarter earlier. Forty-plus fintech partners is diversification of a sort, but they are a single correlated category exposed to the same regulatory weather and the same funding cycle. A sponsor-bank enforcement action anywhere in the industry, or a large partner failure, moves deposits and fee income and credit enhancement at the same time. This is the deposit equivalent of a single-industry loan book, and it has grown more concentrated, not less, over the past year.

**Earnings.** Fintech produced $71.3 million of the $120.7 million of first-half 2026 net income, 59% of the total. Real estate bridge lending, which is the second largest contributor at $29.3 million, is a value-add multifamily rehabilitation book. Those two businesses have almost nothing in common except that both are running at the same time. There is no third leg.

Related, and easy to miss: the Credit Solutions book is shrinking, from $6.2 billion at the end of 2024 and 2025 to $5.8 billion at the second quarter of 2026, and the corporate segment result more than halved from $22.9 million in 2025 to a $10.1 million run rate in 2026 as interest allocation shifted toward fintech. Consolidated growth is therefore coming from one segment while two others contract. That makes the fintech growth rate load-bearing for the entire thesis in a way the consolidated numbers disguise.

---

## Risk 5. Valuation asymmetry — what the low case actually costs

The contract's low case is $48.50, which is 32.7% below the current price. That case does not assume anything dramatic. It assumes fintech owner earnings grow 3% a year rather than 9%, the credit book shrinks 6% a year, exit multiples land at 10 times for fintech and 7 times for lending, and the credit enhancement fails once. Each of those is a plausible bad quarter compounded, not a catastrophe.

The high case of $141.93 requires 15% fintech growth for seven years and a 17 times exit multiple. That is roughly management's Apex 2030 plan delivered in full.

So the distribution around a $72 price is about 33% down against roughly 97% up, on a seven-year view. That is not a bad shape. What makes it uncomfortable is the base case of $87, which is only 21% above the price after seven years of waiting, or 2.7% a year. **You are being paid very little for the base case and relying on the bull case to make the position work.** For a bank with a nine-times-in-two-years off-balance-sheet credit exposure and 7% of headroom against a hard regulatory cap, that is a thin cushion.

One point in the other direction, in fairness. The buyback provides genuine downside support that a discounted cash flow does not capture. If the stock derates, the same dollar of repurchase retires more shares: holding the 95% payout constant, a 10 times multiple retires 9.5% of the shares a year against 7.3% at 13 times. A cheap stock and a large committed buyback is a self-correcting combination, and it is the main reason the bear case still compounds earnings per share at 9.9% a year in the model even with net income essentially flat.

---

## What would change the assessment

| Watch | Threshold | Direction |
|---|---|---|
| Fintech fee revenue run rate | Below 15% growth for two quarters | Kills Risk 1's bull resolution |
| 2027 guidance | Any restatement of the $8.10 to $8.30 range | Confirms Risk 1 |
| Total assets | Above $9.7 billion | Forces the payout below 95%, Risk 3 |
| Credit enhancement disclosure | Counterparty identity or collateral disclosed | Materially reduces Risk 2 |
| Average fintech balances | Above $1.75 billion | Escalates Risk 2 |
| Charge-offs excluding fintech | Above 0.35% of loans | Credit normalisation, Risk 4 |
| Fintech deposit share | Above 97% of total deposits | Escalates Risk 4 |

---

## Facts, inferences and opinions

**Facts** (primary sourced): all figures in the tables above, the guidance ranges, the segment net income partition, total assets, equity, share count, charge-offs, credit enhancement income, and average fintech balances. Sources are the FY2025 Form 10-K (`10-K_20260225_rpt20251231_acc0001295401_26_000002.htm`), the Q1 2026 Form 10-Q (`10-Q_20260506_rpt20260331_acc0001295401_26_000004.htm`), the Q2 2025 Form 10-Q, and the July 2026 investor presentation (`tbbk-investor-presentation-q2-2026.pdf`).

**Inferences** (arithmetic on facts): the 30.3% net income growth requirement embedded in 2027 guidance; the $75 million step; the 7.3% annual share retirement rate; the implied fintech loss rates; the 7% headroom to the asset cap; the observation that 2025 capital returned exceeded net income.

**Opinions** (judgement, argued but not proved): that the fourth-quarter 2026 run-rate softening presages a 2027 revision; that credit enhancement protection is negatively correlated with the event it insures; that the base case pays too little for the risks carried. Reasonable people can disagree with all three, and the falsifiers above are the way to settle them.

---

## [HUMAN REVIEW]

- Contract moved from `evidence_blocked` to `decision_grade` on 2026-08-06 after the missing CIK was added to the registry and SEC filings downloaded. Base case fell from the legacy 16.73% synthesis return to 2.72%. The legacy number was built on a single generic component with no filing-backed proof; it should not be used.
- Registry stance for TBBK is `watch`, while the dashboard shard shows `hold`. Worth reconciling.
- No committee was initialised: the pipeline correctly rested the name because the price is far above the 15% hurdle entry of $32.71 and stance is `watch`. If the stance is promoted, a committee will trigger on the next run.
- The Q2 2026 Form 10-Q was not yet on EDGAR at download time. Segment figures for the first half of 2026 come from the July 2026 investor presentation and should be reconciled to the 10-Q when it lands.
