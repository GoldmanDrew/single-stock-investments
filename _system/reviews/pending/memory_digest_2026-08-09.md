# Memory digest — week ending 2026-08-09

Window: 2026-08-03 to 2026-08-09 (10 unpromoted proposals, 8 corrections)

Human filter workflow: discuss, promote approved bullets into
`_system/memory/MEMORY.md` genius sections, log rejections in
`_system/memory/corrections.md`, then move this file to
`_system/reviews/approved/`.

## Company-specific (9)

- (2026-08-04) WHK: IPO'd 2026-06-10 on NYSE at $26.00/share (7,700,000 Class A shares; ~$200.2M gross proceeds); internally managed at listing via a $130.0M Internalization (75% paid at closing in 3,750,000 OpCo units/Class B shares, 25% earnout up to 1,250,000 more units/shares on Adjusted EBITDA targets over three Earnout Years); Series D preferred redeemed for ~$39.9M; revolving credit facility amended with Capital One as administrative agent (8-K, 2026-06-10).
- (2026-08-04) WHK: no operating financial statements filed as of 2026-08-04; treat as evidence_blocked until the first 10-Q or Internalization pro forma financials appear, or until the 424B4 prospectus is added to the evidence folder.
- (2026-08-04) APLD: universal valuation contract **decision_grade** 2026-08-04; base proof sum **−$1.27/sh** floored at **$0/sh** under **liquidation_shortfall**; Lawrence synthesis **13.12%** per year remains stance gate; **watch** at **$31.27** pending human decision authority.
- (2026-08-04) ABX: component economic value base **~$1.29/sh** vs price **~$10.26** implies **~−26%** seven-year return at the component contract; Lawrence GAAP FCF0 path at same price is **~−2.4%** — both filing-backed methods confirm rich valuation versus owner cash without a single-model artifact.
- (2026-08-04) 0388.HK: issued share count **1,267,836,895** as at 31 December 2025 per FY2025 annual report (`260316ar_e.pdf`); unchanged vs 31 December 2024. Prior ~1,264M scaffold was rounded/wrong source.
- (2026-08-04) 0388.HK: universal valuation contract reached **decision_grade** 2026-08-04; additive component base **HK$258.45/sh** vs price **HK$383**; Lawrence base **0.0%** per year remains stance gate; **watch** pending human decision authority.
- (2026-08-04) AEHR: FY2026 effective backlog **$100.6M** and deferred revenue **$1.91M** per AEHR filings; five largest customers **77%** of FY2025 revenue; universal contract **decision_grade** 2026-08-04; **watch** at **$109.89** until guidance converts to owner cash.
- (2026-08-04) ARE: universal valuation contract **decision_grade** 2026-08-04; base component sum **−$11.35/sh** pre-floor; **zero_value_policy: liquidation_shortfall**; Lawrence synthesis **23.3%** per year vs component base **$0/sh**; price **$48.87**; **watch**.
- (2026-08-06) AEHR: backlog/guide improve visibility but mid-cycle owner cash still far below spot; watch.

## Untagged proposals (1)

- (2026-08-04) BTC demand power-law on dashboard is context-only; do not promote into Lawrence base IRR without human review. CoinGecko max-history backfill is best-effort (Yahoo BTC-USD from 2014-09 when CG blocked).

## Corrections in window

| Date | Ticker | Error | Correction | Source |
|---|---|---|---|---|
| 2026-08-07 | — | Edited `{TICKER}/research/security_identity.json` directly to fix an archetype or valuation profile. It reverts on the next readiness run. | `automate_valuation_readiness.py` **regenerates** that file from `_system/reference/security_identity_overrides.json` (`resolve_identity`). Write the durable entry there, then re-run and confirm the identity survives. `_system/reference/valuation_followups.json` `tickers.<T>.method_profile` is a *second*, separate file that `power_zone_router` reads for the explicit profile — set both. | `_system/scripts/automate_valuation_readiness.py:65,1114` |
| 2026-08-07 | — | Fixed a missing `cik` in `_system/portfolio/registry.json` and the SEC download still reported `SEC=0`. | `_system/scripts/us_ticker_config.json` is read **first**; the registry is only consulted when the ticker is absent from it, so an entry with `"cik": null` beats a correct registry value. Update both, and verify with a non-zero `SEC=` count rather than by re-reading the registry. | `_system/scripts/download_us_investor_docs.py` |
| 2026-08-07 | — | Ran `automate_valuation_readiness.py` over a ticker with accumulated analysis and silently lost it. | It can collapse a rich `research/valuation.json` to a compiler skeleton (observed 34 keys → 9, dropping `scenarios`, `synthesis`, `stance_proposal`, `human_review`) while still reporting `decision_grade`. Snapshot `valuation.json` first and diff the top-level key set after. Losses limited to `context_overlay` / `human_review` / `insider_signal` / `notes` are fine — the daily refresh regenerates those. | observed on STHO 2026-08-06; TBBK 2026-08-07 |
| 2026-08-07 | WHK | Treated Cash Available for Distribution as a pre-interest cash flow and subtracted net debt from a CAFD-derived value. | CAFD is defined and reconciled **after** cash interest expense, cash taxes and cash preferred dividends, so it is already an equity-level cash flow. Subtracting net debt or preferred again double-counts them — the `scarce_asset_optionality` profile's second listed failure mode, "operating cash flow and NAV counted twice". Always read the issuer's own non-GAAP definition before using the measure. | WHK 424B4, "Non-GAAP Financial Measures" |
| 2026-08-07 | WHK | Valued an Up-C issuer on consolidated cash flow without applying the public company's economic interest. | In an Up-C the listed company owns a *fraction* of the operating LLC (WHK: 86.0% of WhiteHawk OpCo; Continuing Equity Owners hold 14.0% exchangeable 1:1 into Class A). Apply the economic interest **before** dividing per share, or the minority's share is counted as shareholder value — the profile's first failure mode, "gross asset value mistaken for shareholder value". Class B carries votes and no economic rights and is not a claim on value. | WHK 424B4, "Our Organizational Structure" |
| 2026-08-07 | — | Added a validator check that read `{ticker}/research/*.json` and it silently failed for every ticker in CI. | `validate_dashboard_data.py` runs in the sparse `pages` checkout, which has **no ticker trees**. Anything the validator needs must be carried in the payload it validates (see `valuation_decision.extreme_return_validated`, stamped by `build_dashboard_data`). | `_system/scripts/ci_dashboard_deploy_mode.sh` |
| 2026-08-07 | — | Assumed committing research changes updates the live Cloudflare dashboard. | Every deploy path resolves to `deploy-only`: Pages publishes the committed `dashboard/` verbatim and never rebuilds. The SPA boots from `core.json` plus per-ticker shards, not `dashboard_data.json`. A validator ERROR fails the build step and the deploy step is **skipped silently**. Rebuild and commit the artifacts, and check the deploy actually ran. | `_system/scripts/ci_dashboard_deploy_mode.sh`, run 31198948792 |
| 2026-08-07 | — | Read a green calibration bar as evidence the capability worked. | `locator_accuracy` returned exactly `1.000 MEETS BAR` on **zero** adjudicated cases, and `severity5_recall` returned 100% on a single event. Both now report INSUFFICIENT DATA. A bar with no adjudications behind it is not a measurement — check the detail line, not the verdict. | `_system/scripts/calibrate_ssi.py` |
