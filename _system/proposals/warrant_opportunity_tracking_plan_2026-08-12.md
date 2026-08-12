# Rare warrant opportunity tracking plan

Date: 2026-08-12
Status: implemented as the initial operational release; research-only; no trading authority

## Implementation record

The initial release is live in the dashboard and scheduled data loop. It includes an immutable, versioned warrant registry; SEC event discovery; contract-term, issuer-survival, and executable-market gates; delayed last-known-good market observations; expiry and redemption alerts; point-in-time 90/365-day cohorts; survivorship-aware terminal outcomes; descriptive calibration; and strict feed-health assertions.

The first live universe contains eight verified historical and active series, with four active contracts. Fair values and opportunity scores are intentionally withheld until all three gates pass. Calibration is descriptive only: it cannot change score weights, sizing, or trade state without a separately reviewed policy change.

## Decision

Build a separate warrant-security registry and event funnel before adding a dashboard tab or an automated score. Reuse the existing SEC, ticker-identity, CVR, and optionality infrastructure, but do not force warrants into the common-stock registry until their issuer, terms, and exchange identity have been verified.

The first release should cover two primary opportunity lanes:

1. **Chapter 11 / distressed-recapitalization warrants** - rare, long-dated securities created by plans of reorganization, distressed exchanges, rights offerings, and recapitalizations.
2. **Public de-SPAC warrants** - standardized enough to screen at scale, but only after parsing callability, cashless redemption, make-whole tables, registration status, and public/private warrant differences.

Secondary lanes can follow after the data contract is stable: litigation/settlement warrants, shareholder-distribution warrants, and warrants attached to rescue financings or rights offerings.

## What the research changes

The research does not support ranking warrants with a vanilla Black-Scholes discount alone.

- Post-emergence securities can be underpriced, and informed creditors' willingness to accept equity contains signal, but leverage and profitability at emergence are critical predictors of refiling risk.
- De-SPAC warrants historically beat de-SPAC common shares on a percentage basis, but the strongest returns were concentrated in low-priced warrants; price-weighted returns were much lower, showing a capacity and scalability problem.
- Dilution must be solved jointly across all warrant/option series. Debt maturity changes the model. Threshold and call features require clause-aware valuation.

Therefore the opportunity pipeline has three hard gates, in order:

1. **Identity and terms complete** - security, agreement, ratio, strike, expiry, settlement, and call/redemption clauses are source-locked.
2. **Issuer survival and financing complete** - post-money share count, all dilutive claims, debt maturity wall, liquidity runway, and post-reorganization viability are measurable.
3. **Executable mispricing** - two-sided warrant market, capacity, spread, borrow/margin constraints, and a clause-aware valuation range are available.

No candidate receives an opportunity score until all three gates pass.

## Architecture

```text
SEC / court / exchange event
        |
        v
candidate event ledger
        |
        v
identity resolver ----> unresolved-security queue
        |
        v
terms parser ---------> terms-blocked queue
        |
        v
claim-stack + survival gate
        |
        v
clause-aware valuation + market quality
        |
        v
research watchlist / alerts / human decision
```

### Reuse from the current repository

- `_system/scripts/refresh_cvr_universe.py` and `_system/scripts/cvr_common.py` for event-ledger and rare-security workflow patterns.
- `_system/scripts/intake_ticker_resolve.py`, `_system/scripts/ticker_identity.py`, and `_system/scripts/build_security_master.py` for issuer and symbol resolution.
- `_system/scripts/optionality_evidence_common.py` and the Power Zone/valuation-contract gates for evidence state and owner-review boundaries.
- Existing SEC download/evidence builders for accession locking and exhibit storage.

Do not extend `portfolio/registry.json` directly. Create a warrant registry keyed independently and link to the common issuer by CIK/security ID.

## Data contract

Create `_system/data/warrants/warrant_registry.jsonl`, one immutable versioned record per warrant series and effective agreement.

### Identity

- `warrant_id`: `CIK:origin_accession:series_slug`
- issuer name, CIK, LEI if available
- common ticker and exchange
- warrant ticker as represented by each venue/vendor
- CUSIP/ISIN/FIGI when available
- public/private/sponsor/employee classification
- originating event: `chapter_11`, `despac`, `rights_offering`, `distressed_exchange`, `settlement`, `distribution`, `other`
- source accession, exhibit number, agreement URL, effective date

### Contract terms

- units-to-warrant and warrant-to-share ratios
- strike and currency
- issue date, exercise start, contractual expiry
- cash, cashless, net-share, or issuer-election settlement
- shares/warrants outstanding and maximum incremental shares
- anti-dilution formula and protected corporate actions
- registration/effectiveness condition
- issuer call rights and notice period
- stock-price trigger, observation window, and measurement definition
- make-whole/cashless redemption table
- takeover, reorganization, and delisting treatment
- amendment/tender history
- broker deliverability and collateral status, marked account-specific

### Issuer and market state

- basic and fully diluted shares
- cash, debt, debt maturities, and post-exercise cash inflow
- post-reorganization Z-score/distress proxy and liquidity runway
- common/warrant bid, ask, last, volume, ADV, and quote timestamp
- common realized volatility and option-implied volatility term structure where available
- borrow/margin status for any proposed overlay

### Valuation outputs

- intrinsic value and parity spread
- vanilla call diagnostic
- dilution-aware observable-variable value
- levered value when debt is material
- joint-series value when multiple claims exist
- clause-aware tree/simulation value for calls, thresholds, and cashless tables
- implied volatility from the warrant price
- implied common-stock CAGR to strike and to modeled fair value
- bear/base/bull value after spread and capacity haircuts
- model route, missing inputs, sensitivity ranges, and evidence references

## Discovery lanes

### 1. Chapter 11 and distressed recapitalizations

Daily SEC query:

- 8-K Item 1.03 (bankruptcy/receivership), Item 3.02 (unregistered sales), Item 5.03 (charter changes)
- 8-A12B / 8-A12G for a new listed class
- plan-emergence 8-K and related exhibits
- S-1/S-3 resale registrations and prospectus supplements for warrant shares
- 10-K/10-Q updates to outstanding warrants and exercise proceeds
- Schedule TO and 8-K amendments/tenders affecting the agreement

Stage court-docket adapters for Kroll, Epiq, and Stretto only after an SEC event identifies the case. Court documents are valuable for plan distributions but too heterogeneous for the first detector.

Required special fields:

- creditor class receiving warrants
- percentage of class electing stock/cash/warrants when disclosed
- plan enterprise value and fresh-start equity value
- exit financing, first-lien debt, maturity wall, projected free cash flow
- management/old-equity retention
- distribution date and likely forced-seller cohort

### 2. Public de-SPAC warrants

Detect from S-1/S-4/F-4/424B filings, the super 8-K, 8-A filing, and Exhibit 4 warrant agreement. Maintain the public and private warrant agreements as separate series.

Monitor continuously for:

- registration statement effectiveness, which can change exercisability
- redemption notices and cashless exchange announcements
- tender/exchange offers
- warrant amendments
- merger/acquisition consideration adjustments
- delisting and OTC migration

Required special fields:

- trust redemptions and cash actually delivered at close
- public warrants per surviving public share
- sponsor/private warrants and whether uncapped
- $11.50-style strike, $18-style call trigger, 20-of-30 observation window, and variations
- make-whole table and fractional-share treatment

### 3. Rescue, rights-offering, and settlement warrants

Scan Item 3.02 8-Ks, rights-offering prospectuses, purchase agreements, and settlement exhibits. These enter the queue only if they are transferable or expected to become transferable; non-tradable employee/options compensation belongs in the claim stack but not the opportunity universe.

## Valuation router

| Condition | Model route | Blocking rule |
|---|---|---|
| Single simple series, immaterial dilution and debt | vanilla diagnostic plus dilution sensitivity | never publish vanilla value alone |
| Single series, observable stock/volatility, material dilution | Ukhov-style simultaneous solve | shares and warrants outstanding required |
| Multiple warrant/option/earnout series | joint-series dilution model | every material series required |
| Material debt | levered observable-variable model | debt amount and maturity required |
| Call, threshold, cashless table, or acceleration | clause-aware tree/Monte Carlo | exact clause and table required |
| Illiquid/no reliable two-sided market | scenario value only | no executable score |

Use common-stock option IV as an input/sensitivity, not as proof of value. For high-IV overlays, treat the short call as a separate trade with its own collateral, assignment, and gap-risk analysis. Do not label a warrant-backed short call “covered” unless the broker confirms deliverability and margin treatment for that exact instrument.

## Ranking

Produce two outputs instead of one seductive score:

### Research priority

Ranks where analyst time is most valuable:

- new/rare event and forced-distribution evidence
- unusually long runway
- unusually high apparent discount across conservative model routes
- upcoming term clarification, registration effectiveness, or first post-emergence filing
- high uncertainty that can be resolved from primary documents

### Executable opportunity quality

Only for fully gated candidates:

- conservative model discount after dilution/callability
- post-reorganization survival quality
- contract protection and runway
- quote quality, spread, ADV, and realistic capacity
- catalyst clarity
- downside-to-zero probability and expected loss

Each component must show the raw inputs. Weights should remain unset until the historical backtest is complete.

## Dashboard and alerts

After the registry and tests are stable, add a Watchlist sub-view called **Warrants** with:

- lane, issuer, common/warrant symbol
- days to expiry, strike, spot, moneyness
- call/threshold badge
- diluted warrant overhang
- model range vs executable ask
- spread/ADV/capacity
- survival gate and next filing/catalyst
- `terms_blocked`, `survival_blocked`, `market_blocked`, or `review_ready`

Alerts should be event based, not price-spam:

- new warrant agreement or listed class
- emergence distribution date
- registration effectiveness
- amendment/tender/redemption notice
- stock entering a call-trigger observation window
- warrant ask crossing a pre-approved valuation band
- material change in debt/liquidity or Chapter 22 risk

## Phased implementation

### Phase 0 - historical seed and specification

- Hand-code 20-30 historical instruments across reorganization, de-SPAC, and rescue-financing lanes.
- Include winners, zeros, called warrants, delistings, and Chapter 22 failures.
- Freeze the JSON schema and a clause taxonomy from actual agreements.
- Acceptance: two researchers independently reconstruct the same terms and payoff for five cases.

### Phase 1 - discovery and evidence

- Build the SEC event collector and accession-locked candidate ledger.
- Add identity resolution and unresolved queue.
- Store agreements/exhibits; build deterministic term extraction with confidence and exact source spans.
- Acceptance: at least 95% recall on the historical seed for events already present in EDGAR and zero silent ticker substitutions.

### Phase 2 - pricing and viability gates

- Implement vanilla diagnostic, dilution-aware solve, joint-series route, levered route, and clause-aware simulation.
- Add post-emergence survival packet and Chapter 22 blockers.
- Acceptance: unit tests against paper examples and hand calculations; no value emitted when required claims/debt/clauses are missing.

### Phase 3 - market quality and opportunity research

- Connect existing market-data adapters for common and warrant quotes; add options IV only where available.
- Add spread, ADV, quote staleness, and capacity haircuts.
- Backtest from the first executable quote after the event, not from hindsight-selected lows.
- Acceptance: results shown equal-weighted, dollar/price-weighted, after spreads, and with zeros/delistings retained.

### Phase 4 - dashboard and operating loop

- Add the Warrants watchlist sub-view and event alerts.
- Route `review_ready` candidates to the existing optionality/Investment Committee process.
- Park every action at owner review; the system never sizes or trades.

## Backtest requirements

- Point-in-time security master and agreement terms
- Survivorship-free universe, including expired, called, amended, delisted, and worthless warrants
- Entry at observed ask; exit at bid or modeled corporate-action proceeds
- Corporate-action-adjusted ratios and strikes
- Separate Chapter 11, de-SPAC, and other lanes
- Equal-weighted, price-weighted, and capacity-weighted returns
- Dollar P&L and maximum deployable capital, not only percentage returns
- Common-stock and call-option benchmarks
- Sensitivity to quote staleness and inability to trade
- Out-of-sample threshold setting; no score weights chosen on the evaluation period

## First build slice

The smallest useful build is:

1. `warrant_registry.jsonl` schema and five hand-coded instruments.
2. SEC detector for 8-K Item 1.03/3.02 plus 8-A forms and warrant-agreement exhibits.
3. Deterministic terms card with `terms_blocked` state.
4. Dilution-aware diagnostic with a Chapter 22 survival gate.
5. A CLI/report that prints the ten newest candidates and why each is blocked or review-ready.

Do this before adding dashboard UI or a high-IV call-selling layer. The research edge begins with complete contracts and complete claim stacks; the volatility overlay is downstream execution, not the discovery engine.

## Source shelf

The supporting papers and reading synthesis are stored in the private research vault at `investment-wisdom/warrants/` and mirrored to Google Drive at:

https://drive.google.com/drive/folders/18in5XTvp6AEc-n_9ygkrFW0sKJXJl1y8
