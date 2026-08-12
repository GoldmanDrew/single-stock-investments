# WHK valuation reconciliation — supplemental working paper

**Purpose.** Audit the assumptions in the 2026-08-11 production contract and
add three independent checks. This is a working paper, not a capital decision
and does not alter `valuation_contract.json`.

## 1. What the existing contract values

The production contract adds two non-overlapping claims:

1. **PDP royalty cash stream** — a declining cash-flow value for the proved,
   developed and producing (PDP) reserve book.
2. **Undeveloped location inventory** — a unit-NAV estimate for locations that
   are not in the PDP stream.

| Per Class A share | Low | Base | High |
|---|---:|---:|---:|
| PDP royalty cash stream | $4.35 | $5.01 | $5.89 |
| Undeveloped inventory | $1.77 | $3.76 | $6.92 |
| Contract value | $6.12 | $8.76 | $12.81 |

This partition prevents double counting, but it does not make either component
an independent market valuation.

## 2. Existing-assumption audit

### PDP royalty cash stream

| Input | Low / Base / High | Status | Current rationale |
|---|---:|---|---|
| Pro-forma CAFD | $36.317m / $38.076m / $39.836m | Judgment built from disclosed non-GAAP figures | Base is the midpoint of pro-forma FY2025 CAFD and annualized pro-forma Q1 2026 CAFD. |
| Company economic interest | 82.14% / 82.14% / 85.98% | Judgment | Low/base assume the 1.25m-unit earnout is issued; high assumes no earnout dilution. |
| Required return | 12% / 10% / 9% | Judgment | Commodity, first-public-year, governance, and distribution-policy risk. |
| Annual cash-flow decline | 13.75% / 13.50% / 13.00% | Derived judgment | PDP reserves of 178,544 MMcfe divided by annual production of 24,548 MMcfe imply a 7.27-year life; Q1 annualized production gives 7.61 years. The model uses the reciprocal as a simplifying decline rate. |
| Class A shares | 22,996,579 | Filing fact | Class A shares and matching Company-owned OpCo interests at the IPO. |

The calculation is:

`attributable CAFD × (1 - decline) ÷ (required return + decline) ÷ Class A shares`.

For the base case, that is:

`$38.076m × 82.1407% × 86.5% ÷ 23.5% ÷ 22.996579m = $5.01/share`.

### Important CAFD caveat

CAFD is management's non-GAAP measure, not free cash flow. The prospectus
defines it from operating cash flow after adding back several items and then
deducting cash interest, cash taxes, and preferred dividends. Pro-forma FY2025
CAFD of $36.317m includes a $13.6m **Liquidity Incentive Fee** add-back. The
same one-time IPO item appears in the pro-forma Q1 management-fee adjustment;
therefore annualizing Q1 CAFD to $39.836m is not a clean recurring run rate.

The ongoing Internalization saving disclosed by management is much smaller:
$6.2m base management fees + $3.7m dividend incentive fees - $1.7m estimated
incremental compensation = about $8.2m. A first reconciliation should remove
the $13.6m IPO fee before treating CAFD as recurring. This can lower the PDP
leg even while the inventory analysis below raises the asset leg.

### Undeveloped-location inventory

| Input | Low / Base / High | Status | Current rationale |
|---|---:|---|---|
| Gross locations | 8,783 | Filing fact | 430 in proved reserves and 8,353 other locations, audited and approved by CG&A. |
| Net locations | 28.0 | Filing fact | App 8.7, Haynesville 3.1, Mid-Continent 14.1, Other 2.1. |
| EUR per 1,000 lateral feet | App 2.0/2.35/2.7; Haynesville 2.2/2.5/2.8; Mid-Con & Other 0.6/0.9/1.2 Bcfe | Judgment | Not supplied by CG&A in the evidence packet. |
| Inventory volume | 384.9 / 479.5 / 574.0 Bcfe | Derived judgment | Basin net locations × average lateral length × EUR per 1,000 feet. |
| PV-10 unit value | $1.422/MMcfe | Filing fact, used as proxy | $293.690m PV-10 ÷ 206,473 MMcfe proved reserves; the SEC price deck was $3.387/MMBtu Henry Hub. |
| After-tax factor | 90.683% | Derived | $266.326m standardized measure ÷ $293.690m PV-10. |
| Realization multiplier | 10% / 17% / 25% | Judgment | Proxy for when operators convert locations to producing wells. It is an additional present-value factor, not a conventional 10–25% haircut. |
| Senior-claims deduction | $0 | Judgment | The contract says CAFD already services interest and preferred dividends, so deducting debt and preferred again would double count. |

Base volume calculation:

| Basin | Net locations | Avg. lateral feet | Base EUR / 1,000 ft | Net inventory |
|---|---:|---:|---:|---:|
| Appalachia | 8.7 | 13,246 | 2.35 Bcfe | 270.9 Bcfe |
| Haynesville | 3.1 | 9,267 | 2.50 Bcfe | 71.8 Bcfe |
| Mid-Continent | 14.1 | 9,314 | 0.90 Bcfe | 118.2 Bcfe |
| Other | 2.1 | 9,864 | 0.90 Bcfe | 18.6 Bcfe |
| **Total** | **28.0** | — | — | **479.5 Bcfe** |

Base inventory calculation:

`479,471 MMcfe × ($293.690m ÷ 206,473 MMcfe) × 17% × 90.683% × 82.1407% ÷ 22.996579m shares = $3.76/share`.

## 3. Independent check #1 — development-timing NAV

The existing 17% multiplier assumes a very long conversion period but does not
show the schedule. WhiteHawk disclosed 411 gross wells turned to production in
2025. Holding the base 479.5-Bcfe inventory, unit value, tax treatment, and
ownership constant, the table below replaces the multiplier with an evenly
spaced annual development schedule discounted at 10%. It treats $1.422/MMcfe
as value at first production, then discounts only the additional wait to first
production.

| Gross wells per year | Years to develop 8,783 locations | Average timing factor | Inventory value/share | Value incl. current PDP base |
|---:|---:|---:|---:|---:|
| Contract base | n/a | 17.0% | $3.76 | $8.76 |
| 200 | 43.9 | 22.4% | $4.95 | $9.96 |
| 300 | 29.3 | 32.1% | $7.08 | $12.09 |
| 411 — 2025 observed gross pace | 21.4 | 40.7% | $8.99 | $13.99 |
| 500 | 17.6 | 46.3% | $10.22 | $15.22 |
| 600 | 14.6 | 51.4% | $11.35 | $16.36 |

This does **not** prove that 411 is the right forward pace: it includes all
WhiteHawk acreage, and neither the filing nor this model allocates that pace by
location quality or operator. It does show that the original 17% factor needs a
specific, dated explanation. The next evidence target is operator-by-operator
development of WhiteHawk acreage.

## 4. Independent check #2 — transaction evidence

| Transaction | Observed consideration | Proved PV-10 at the relevant reserve date | Raw implied multiple | Interpretation |
|---|---:|---:|---:|---|
| PHX acquisition, June 2025 | ~$187m enterprise value | $79.642m | 2.35x | A cash tender at $4.35/share. The reserve deck used $2.13/MMBtu Henry Hub, so this is not directly comparable to WHK's $3.387 deck. |
| TRR acquisition, March 2025 | $118m for the remaining 50% | $45.088m for the TRR Seller | ~5.23x if the reserve disclosure represents the full seller asset | Strong but non-clean point: WhiteHawk already owned the other 50%, had superior asset knowledge, and the purchase agreement should be checked for adjustments. |
| WHK market-implied enterprise claim at $26.16 | ~$795m | $293.690m | ~2.71x | Approximate whole-OpCo common value plus net debt and Series B preferred; it is directionally comparable only. |

These transactions reject the idea that PV-10 itself is intrinsic value. They
do not prove that WHK deserves the same multiple: price decks, quality,
undeveloped inventory, liabilities, and transaction structure differ. The
PHX and TRR records are, however, evidence that the current contract's
PV-10-based unit proxy cannot be treated as a complete valuation.

## 5. Independent check #3 — reverse valuation

At the $26.16 reference price, the existing base PDP component contributes
$5.01/share. With base inventory volume and unit economics unchanged, the
inventory realization multiplier required to explain the remaining value is:

`($26.16 - $5.01) ÷ $22.09/share at 100% realization = 95.8%`.

At the 411-wells/year timing factor, inventory is $8.99/share and total value
is $13.99/share. Reaching $26.16 then requires about **2.35×** more inventory
unit economics (roughly $3.34/MMcfe rather than $1.42/MMcfe), more inventory,
or an equivalent increase in the producing-cash component.

If the original 17% inventory treatment is retained, the $26.16 market price
requires the PDP cash stream to grow about 3.7% in perpetuity at a 10% required
return instead of declining 13.5%. With the 411-well timing schedule, it
requires about 1.9% perpetual PDP growth. Neither is an appropriate forecast;
these are simply the mathematical expectations embedded by the price under the
current model architecture.

## 6. Reconciliation agenda

1. Rebuild recurring CAFD from the first public-company 10-Q, removing the
   one-time liquidity fee and separately showing recurring corporate costs.
2. Obtain the actual swap schedule, then model a forward gas-price strip rather
   than applying one historical SEC price deck to every case.
3. Build an acreage-specific, operator-by-operator well schedule. Use permits,
   rig allocation, lateral plans, and public capital budgets rather than a
   portfolio-wide multiplier.
4. Verify transaction consideration and normalize PHX/TRR and a broader royalty
   peer set for price deck, net debt, NRI, PDP/PUD mix, and inventory quality.
5. Reconcile the total OpCo claim, Class A claim, earnout dilution, debt, and
   preferred stock in one bridge so the cash-flow and NAV legs carry senior
   claims exactly once.

## 7. Recurring CAFD bridge - do not call $38.1m recurring yet

This bridge starts with management's *pro-forma FY2025* CAFD reconciliation;
it is not a forecast and it does not assume that every adjustment is either
recurring or non-recurring. Its purpose is to make the decision visible.

| Step | CAFD effect ($m) | Result ($m) | Treatment and reason |
|---|---:|---:|---|
| Reported pro-forma FY2025 CAFD | - | 36.317 | Prospectus non-GAAP reconciliation. |
| Less: Liquidity Incentive Fee add-back | (13.600) | 22.717 | The disclosed liquidity incentive was a transaction/IPO item, not an operating cash-cost saving that repeats each year. |
| Recurring CAFD, first-pass estimate | - | **22.717** | Provisional. It still requires review of transaction costs, cash taxes, interest/refinancing, preferred dividends, and the first post-IPO 10-Q. |

The $13.6m is the issue. The internalization adjustment contains approximately
$6.2m of base management fees, $3.7m of dividend incentive fees and $1.7m of
estimated incremental compensation. That makes an estimated *ongoing* net
benefit of about $8.2m. It does not justify retaining the separate $13.6m
liquidity-incentive add-back in a recurring run rate.

| CAFD basis | Company-attributable CAFD at 82.1407% ($m) | Cash / Class A share | PDP value/share using the current 10% return and 13.5% decline |
|---|---:|---:|---:|
| Reported pro-forma FY2025 CAFD: $36.317m | 29.828 | $1.30 | $4.77 |
| Existing-contract base: $38.076m | 31.276 | $1.36 | $5.01 |
| First-pass Liquidity-Incentive-Fee-normalized CAFD: $22.717m | 18.660 | $0.81 | **$2.99** |

The last column is deliberately mechanical: `attributable CAFD x 86.5% /
23.5% / shares`. It says what the existing perpetuity formula produces, not
what WHK's PDP royalty should ultimately be worth. The field schedule in the
next section is the replacement for the 13.5% shortcut.

### Recurring-CAFD decisions still open

| Item | Current treatment | What would settle it |
|---|---|---|
| $11.596m transaction-cost add-back in FY2025 | Retained in the first-pass number because it is in reported CAFD; it should be removed for a steady-state royalty-company case unless a defined acquisition program makes it recurring. | First public-company results and a capital-allocation policy. |
| Cash interest | Deducted in CAFD. | Debt schedule, refinancing terms, and whether the valuation is to common equity or the whole OpCo. |
| Preferred dividends | Deducted in CAFD. | A separate common-versus-OpCo claim bridge; avoid deducting the preference again in NAV. |
| Cash taxes | Deducted in CAFD, but the PV-10 inventory is separately multiplied by a 90.683% standardized-measure/PV-10 tax proxy. | Tax-basis and NOL review to ensure the two components use consistent tax assumptions. |
| Q1 2026 annualization | **Not used** for recurring CAFD. It repeats the one-time liquidity-incentive effect. | A post-IPO quarterly run rate with the one-time items separately identified. |

## 8. Acreage-by-operator development model - evidence-aware first build

The prospectus discloses location counts by basin and **production captured by
operator**, but it does not disclose a location/acreage intersection by
operator. Therefore the following is an explicitly labelled *production-mix
proxy*, not a claim that these are WhiteHawk's operator-specific locations or
net royalty acres.

It allocates the 8,783 gross locations and the observed 411 gross 2025
turned-in-line pace in proportion to the disclosed 2025 production mix in each
basin. If the proportional pace held, every basin would take 21.4 years to
develop. The important product of this table is the data gap: a defensible
model must replace the proxy with permit/geospatial intersections.

| Basin | Gross locations | Proxy gross TILs/year at 411 total | Implied development years | Existing evidence |
|---|---:|---:|---:|---|
| Appalachia | 2,792 | 130.7 | 21.4 | 2025 production mix by operator; active EQT, Antero, Range, CNX and Expand footprint. |
| Haynesville | 1,581 | 74.0 | 21.4 | 2025 production mix by operator; active Expand, Aethon, Comstock, Trinity and TG Natural footprint. |
| Mid-Continent | 3,952 | 185.0 | 21.4 | 2025 production mix by operator; location quality and operator plans need separate work. |
| Other | 458 | 21.4 | 21.4 | No operator-level allocation used. |
| **Total** | **8,783** | **411.0** | **21.4** | Portfolio-wide observed 2025 TIL count, not guidance. |

### Appalachia and Haynesville operator schedule (production-mix proxy)

| Basin / operator | Disclosed 2025 production mix | Proxy locations | Proxy TILs/year | Evidence level |
|---|---:|---:|---:|---|
| Appalachia - EQT | 48.3% | 1,349 | 63.1 | Operator is known; allocation is a production proxy. |
| Appalachia - Antero | 14.6% | 408 | 19.1 | Operator is known; allocation is a production proxy. |
| Appalachia - Range | 14.5% | 405 | 19.0 | Operator is known; allocation is a production proxy. |
| Appalachia - CNX | 13.5% | 377 | 17.6 | Operator is known; allocation is a production proxy. |
| Appalachia - Expand | 3.9% | 109 | 5.1 | Operator is known; allocation is a production proxy. |
| Appalachia - Other | 5.2% | 145 | 6.8 | Aggregated production proxy. |
| Haynesville - Expand | 37.6% | 594 | 27.8 | Operator is known; allocation is a production proxy. |
| Haynesville - Aethon | 18.3% | 289 | 13.5 | Operator is known; allocation is a production proxy. |
| Haynesville - Comstock | 7.9% | 125 | 5.9 | Operator is known; allocation is a production proxy. |
| Haynesville - Trinity | 5.3% | 84 | 3.9 | Operator is known; allocation is a production proxy. |
| Haynesville - TG Natural | 5.2% | 82 | 3.8 | Operator is known; allocation is a production proxy. |
| Haynesville - Other | 25.7% | 406 | 19.0 | Aggregated production proxy. |

The next version must contain, for every operator-basin cohort: county/state,
net royalty acres or net locations, working-interest/NRI, permit or DUC date,
operator's well sequence, assumed spud-to-first-production lag, lateral feet,
EUR distribution, commodity differential, and an explicit royalty cash-flow
waterfall. That will value a dated stream of royalties directly and will remove
the arbitrary 17% multiplier and the portfolio-wide 13.5% decline shortcut.

Public operating disclosures show that activity is real but do **not** identify
WHK-specific wells: EQT disclosed 34-50 planned Q3 2026 net turn-in-lines;
CNX disclosed 34 2026 turn-in-lines; Expand reported 49 first-quarter 2026
turn-in-lines; and Antero outlined a multi-year development plan. These are
reason to acquire the location intersection, not evidence to credit WHK with
their full programs.

## 9. Transaction and peer bridge - what the evidence can and cannot say

| Lens | Value / PV-10 | Why it matters | Why it is not a plug-in multiple |
|---|---:|---|---|
| PHX cash acquisition | ~2.35x | A mineral/royalty transaction showed buyers can pay well above a low-price-deck PV-10. | PHX reserve deck used $2.13/MMBtu Henry Hub; consideration includes a different inventory, liability, and capital-structure mix. |
| TRR remaining-50% acquisition | ~5.23x, conditional | A strategic buyer paid a high headline multiple if the cited seller PV-10 covers the full seller asset. | WhiteHawk already owned the other half and had information/strategic value; the purchase agreement and reserve-claim scope must be verified. |
| WHK whole-claim value at $26.16 | ~2.71x | It frames the market's aggregate claim against the current $293.690m PV-10. | It mixes PDP, undeveloped inventory, acquisition capacity, debt and preferred claims. |
| Kimbell public reference | ~2.44x estimated EV / standardized PV-10 | A diversified public mineral/royalty business provides a capital-structure-aware reference point. | Primarily liquids and multi-basin; it is not a gas-basin comparable and uses a different reserve/property mix. |
| Viper Energy public reference | equity market cap / PV-10 is about 0.75x | A large public royalty business is a useful reminder that equity value alone is not enterprise value. | Oil-weighted Permian company; not Appalachian/Haynesville, and debt must be added before using EV/PV-10. |

For the Kimbell cross-check, the August 12 market capitalization reference is
about $1.807bn. Its December 31, 2025 balance sheet reported $441.5m of debt,
$44.0m of cash and $158.8m of Series A preferred units; the year-end
standardized measure before income taxes was $969.9m. This produces an
estimated $2.36bn enterprise/preferred claim or about 2.44x. Kimbell reported
2025 production equivalent to roughly 154.6 MMcfe/d, making the same claim
about $15,300 per flowing Mcfe/d. WHK's $795m whole-claim reference divided by
64.27 MMcfe/d is about $12,400 per flowing Mcfe/d. This proximity is a useful
sanity check only: it does not establish value because Kimbell is liquids-heavy
and its public valuation, leverage and reserve mix differ materially.

The present evidence does **not** support a credible $/net-royalty-acre
comparison. In particular, WhiteHawk's 8,783 are gross *locations*, not net
royalty acres. A small disclosed Black Stone Haynesville acquisition illustrates
why the distinction matters: $2.5m for 363 net royalty acres, but without its
flowing volume, NRI and undeveloped inventory it cannot be used as a WHK
multiple. We will keep acre metrics blank rather than convert one into the
other.

The correct comparison set must be normalized rather than averaged. For each
transaction or peer, record: announcement date; equity and enterprise value;
net debt, preferred and NCI; PV-10 and price deck; proved developed/proved
undeveloped split; undeveloped inventory; production volume; net royalty acres;
commodity and basin; and whether it was a control transaction. Only then can
we compare EV/PV-10, dollars per net royalty acre, and dollars per flowing
Mcfe without mixing unlike claims. The present evidence supports a **range of
possible market valuations**, not a target multiple.

## 10. Reverse valuation - four ways $26.16 can be made true

All cases retain the base 479.5-Bcfe inventory and 82.1407% ownership. The
timing cases use a 10% discount rate. They show the economic burden imposed by
the market price; they are not forecasts.

| Case | PDP cash basis | Inventory timing | Value produced by that case | Additional economics required to reach $26.16 |
|---|---:|---:|---:|---|
| Existing contract | $38.076m CAFD / 13.5% decline | 17.0% multiplier | $8.76/share | 95.8% inventory realization versus the model's full $22.09/share inventory value, or a different source of value. |
| Dated 411-TIL schedule | $38.076m CAFD / 13.5% decline | 40.7% factor | $14.00/share | 2.35x the inventory unit economics: about $3.34/MMcfe rather than $1.42/MMcfe, more net inventory, or capital-allocation value. |
| Recurring-CAFD plus dated schedule | $22.717m CAFD / 13.5% decline | 40.7% factor | **$11.98/share** | 2.58x the inventory unit economics: about **$3.67/MMcfe**, more net inventory, a materially better cash-flow schedule, or capital-allocation value. |
| Perpetual-cash-flow cross-check | $38.076m reported/pro-forma CAFD | 17.0% / 40.7% | n/a | The residual PDP cash stream needs approximately +3.7% / +1.9% perpetual growth at a 10% return, rather than the model's 13.5% decline. With the $22.717m first-pass recurring CAFD, those growth rates rise to about +6.2% / +5.0%. |

There is no sound one-variable answer such as "gas must be $X." A $26.16
price can be reconciled by a combination of: higher future gas realization;
shorter wait to first production; higher EUR or more net locations; lower
royalty-burden or operating deductions; and value created by management's
reinvestment of retained cash. The model currently assigns **zero** value to
future acquisitions/capital allocation. That may be conservative, but it must
remain zero until an acquisition-return record, reinvestment policy, financing
capacity, and per-share value-accretion test support a positive value.

The most decision-useful next calculation is therefore cohort-level, not a
multiple: each permit/location gets a date, operator, lateral, EUR range,
royalty NRI, price/differential, and cash-flow curve. Sum the dated after-tax
royalty cash flows, then add a separately valued, evidence-tested capital
allocation option. That will tell us whether the gap is timing, commodity,
inventory quality, reinvestment, or an actual market overvaluation.

## Primary sources

- WhiteHawk 424B4 prospectus, filed 2026-06-09:
  `WHK/investor-documents/sec-edgar/424B4_20260609_rpt_acc0001193125_26_264014.htm`.
- WHK production valuation contract, 2026-08-11:
  `WHK/research/valuation_contract.json`.
- PHX acquisition announcement, 2025-05-08.
- Expand Energy, CNX, Antero, and EQT 2026 operating disclosures, used only as
  general evidence of basin activity—not as proof of development on WHK
  acreage.
