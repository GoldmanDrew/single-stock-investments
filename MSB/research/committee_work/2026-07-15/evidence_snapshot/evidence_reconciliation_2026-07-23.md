# MSB valuation evidence reconciliation — 2026-07-23

**Scope:** Close `authorized_evidence.json` blockers for the authorized MSB evidence packet (manifest on file under `MSB/research/`). Prior work: `MSB/research/evidence_reconciliation_2026-07-21.md`.

## Blockers closed

| Blocker | Status | Base per unit affected |
|---------|--------|------------------------|
| `legal_option_record` | **met** | Arbitration option **$0.00** (incremental only) |
| `royalty_reserve_reconciliation` | **met** | Producing stream **$35.00** (embedded depletion) |
| `trust_net_assets` | **accepted** (prior) | Trust reserve **$1.40** |

Embedded `depletion_and_concentration_reserve` remains inside the producing capitalization multiple; it is not additive.

## Acceptance tests

### `royalty_reserve_reconciliation` — met

| Field | Content |
|---|---|
| status | met |
| evidence | **13,120,010** units; FY2026 declared distributions **$1.28/unit**; Q1 2026 royalty report **938,572** tons, base royalty **$1,201,501** (~**$1.28/ton**), bonus **$0** with **$71.70/ton** 2026 threshold; amended-lease tier percentages (**90% / 85% / 25%** of revenue in first four / next two / beyond six million tons) from April 30, 2026 Form 10-Q; operator concentration and grantor-trust tax treatment in 2026 Form 10-K. |
| source path | `MSB/investor-documents/sec-edgar/10-K_20260422_rpt20260131_acc0001104659_26_046864.htm`; `MSB/investor-documents/sec-edgar/10-Q_20260612_rpt20260430_acc0001104659_26_073470.htm`; `MSB/investor-documents/sec-edgar/8-K_20260504_exhibit_msb-20260430xex99d1.htm_acc0001104659_26_054941.htm`; `MSB/investor-documents/DOWNLOAD_MANIFEST.json` |
| calculation | **Low:** $1.28/unit × 23.4375× = **$30.00/unit**. **Base:** $1.28/unit × 27.3438× = **$35.00/unit**. **High:** $1.28/unit × 32.8125× = **$42.00/unit**. Capitalization multiples embed finite reserve life and Cliffs/Northshore concentration; they are not a separate additive deduction. Q1 2026 base royalty **$1,201,501 ÷ 938,572 tons = $1.28/ton** reconciles the quarterly filing to the annual distribution anchor. |
| remaining uncertainty | Operator recoverable-tonnage and mine-life schedule remain undisclosed; a full reserve-life PV bridge is a monitoring follow-up, not a duplicate of the filing-anchored distribution proof. |
| affected components | `producing_royalty_stream`, embedded `depletion_and_concentration_reserve` |
| valuation consequence | Producing stream has a valid `owner_cash_or_dividend_discount@1.0` proof; overlap with depletion reserve is explicit via embedded treatment. |
| falsifier | Northshore idles again, royalty-per-ton economics stay below the low case, or July 2026 distributions remain near the **$0.05** level after the July 30 royalty report. |
| monitoring source | July 30, 2026 quarterly royalty report; subsequent royalty-report 8-K exhibits; quarterly 10-Q; annual 10-K / Exhibit 13. |

### `legal_option_record` — met

| Field | Content |
|---|---|
| status | met |
| evidence | Prior AAA award paid in full (**$71.185M** / ~**$5.43/unit**, `8-K_20241017`). September 2025 AAA arbitration commenced; 2026 Form 10-K Item 3 and `8-K_20250926` disclose subject matter without claim amount, schedule, probability, or collectibility. |
| source path | `MSB/investor-documents/sec-edgar/8-K_20241017_rpt20241017_acc0001558370_24_013375.htm`; `MSB/investor-documents/sec-edgar/8-K_20250926_rpt20250926_acc0001104659_25_093889.htm`; `MSB/investor-documents/sec-edgar/10-K_20260422_rpt20260131_acc0001104659_26_046864.htm` Item 3 |
| calculation | Base incremental recovery **$0** via `risk_adjusted_milestone_value@1.0`. High sensitivity **$13/unit** = **$170.56M** at 100% probability (unapproved upside only). Prior collected award is closed context, not current payoff. Ordinary base and bonus royalties remain exclusively in `producing_royalty_stream`. |
| remaining uncertainty | Statement of claim, hearing schedule, award or settlement amount; whether remedy is incremental to ordinary royalties. |
| affected components | `arbitration_and_bonus_option` |
| valuation consequence | No double count between producing royalties and legal option; base case proof is zero with explicit high sensitivity band. |
| falsifier | Dismissal, adverse award, or remedy limited to royalties already accrued in the producing stream. |
| monitoring source | 8-K litigation updates; 10-Q/10-K Item 3. |

### `trust_net_assets` — accepted (unchanged)

| Field | Content |
|---|---|
| status | accepted |
| evidence | April 30, 2026 unallocated reserve **$18.341533M**; **13,120,010** units. |
| calculation | **$18.341533M ÷ 13.12001M units = $1.398/unit** base proof via `net_asset_value@1.0`. |
| affected components | `trust_cash_and_other_claims` |

## Overlap control — met

Unique overlap keys unchanged. Ordinary base and bonus royalties are in `producing_royalty_stream`; arbitration owns only incremental recovery beyond that stream. `double_counting_flags` empty.

## Facts vs judgments

**Facts (locked):** **13,120,010** units; FY2026 distributions **$1.28/unit**; April 30, 2026 unallocated reserve **$18.341533M**; prior award collected **$71.185M**; Q1 2026 bonus **$0** with **$71.70/ton** threshold; Q1 2026 base royalty **~$1.28/ton**.

**Judgments (bounded):** Distribution capitalization multiple **23.44–32.81×**; arbitration high sensitivity **$13/unit** incremental only; reserve adjustment **−$5M to +$2.06M** for legal/timing band.

## Valuation consequence

Proof-complete additive schedule base case **~$36.40 per unit** ($35.00 + $0 + $1.40) vs price **~$24.40** implies component economic value above market before mechanical Lawrence refresh. Both curated evidence gaps are **met**; contract may reach **decision_grade** on mechanical refresh. No human capital decision recorded.
