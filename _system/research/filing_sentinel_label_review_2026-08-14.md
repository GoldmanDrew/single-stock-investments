# Filing Sentinel raw 10-Q labeling review - 2026-08-14

## Current position

The first 25-case historical 10-Q cohort has completed two role-separated blind passes and the workflow has ingested the results. No case was promoted to gold.

| Cohort-one result | Count |
|---|---:|
| Valid label pairs | 25 |
| Exact structured consensus | 21 |
| Consensus clean controls | 19 |
| Consensus material-change cases | 2 |
| Adjudication queue | 4 |
| Valid-pair consensus rate | 84% |

The two low-risk consensus events are:

- ABNB: debt refinancing that retired the 2026 convertible notes and retained approximately $500 million of proceeds;
- AEE: a multi-year equity-financing plan and outstanding forward-sale agreements that create dilution risk.

These rows are `labeled`, not `gold`. Auto-consensus promotion remains opt-in and was not used.

## Adjudication queue

| Issuer | Why queued | Recommended adjudication question |
|---|---|---|
| ACHR | Extractor added patent litigation; skeptic accepted only the related-party disclosure | Confirm the CEO-linked related-party transaction. Treat the ITC matter as litigation, not an adverse regulatory investigation, and require full comparable legal-section review before retaining it. |
| AFL | Both reviewers agreed on a material related-party coinsurance transaction | Always-review policy applies. Confirm the Japan Post affiliation, economics, and whether restricted trust cash changes the risk interpretation. |
| ABX | Extractor labeled a small investee impairment; skeptic rejected an issuer wind-down interpretation | Establish impairment materiality relative to issuer earnings/assets. Reject `wind_down` unless the issuer or a material operating unit—not merely an investee—is winding down. |
| ACMR | Both saw a resolved customs investigation but disagreed on severity | Reject `auditor_change`. Confirm that the prosecutor dismissal is final and decide whether a resolved investigation merits a positive/neutral event at all. |

The two passes were blinded and role-separated inside one Codex work session. They are useful for exercising disagreement logic and forming an adjudication brief, but they are not a substitute for an isolated second model/operator when creating immutable gold labels.

## Proposed gold expansion

The adjudicator pass resolved all four queued cases and the consensus audit accepted its five sampled cases. Those nine reviewed rows were appended to a **separate** proposed-gold artifact rather than the locked benchmark:

| Dataset | Gold cases |
|---|---:|
| Locked seed benchmark | 4 |
| Proposed expansion | 13 |

The proposed set validates with 10 10-Qs and 3 10-Ks across train/dev/test splits. It contains five financial-oxygen, three operations, and two governance/legal events plus clean controls. The file remains a promotion candidate because the initial two label passes were role-separated within one session rather than independently executed by separate operators.

## Benchmark-provenance gate

The workflow now records opaque `review_context_id` values for each extractor, skeptic, and adjudicator run, and `promote` fails closed unless the contexts are present and distinct. The retrospective gate report found all nine promotion candidates in this first cohort unverified: each is missing extractor, skeptic, and adjudicator review-run provenance. This does not invalidate their source evidence or the proposed-gold schema; it prevents the evidence from being represented as independent benchmark truth.

The next isolated-review batch must return labels with a different context ID for each role. Adjudication must use a third context. Run `promotion-gate` before promotion; no provenance-bypass flag is permitted for the locked benchmark.

## Knowledge compounded into the miner

1. **Reviewer position leaked through order.** Extractor and skeptic packets previously used identical row order. They now receive deterministic reverse orders with unrelated blind IDs.
2. **Consensus must be exact on material fields.** Severity, evidence IDs, claim, falsifier, confidence, values, units, and rejected tags now participate in blind agreement. Evaluation matching remains intentionally less strict.
3. **Cohort offset alone is not a durable ledger.** The raw miner now accepts prior candidate files through `--exclude-candidates`; cohort two uses both offset 25 and an explicit 25-issuer exclusion list.
4. **XBRL taxonomy members are not restatements.** `srt:RestatementAdjustmentMember` no longer creates a restatement lead.
5. **Long normalized lines create regex cross-talk.** Auditor-change matching is now bounded so an unrelated phrase such as “investigation dismissed” cannot pair with a remote generic auditor reference.
6. **Locked text hashes must be platform-stable.** Extract hashes now use normalized UTF-8 text, while raw filing sources remain byte-exact.
7. **Agreement needs an audit artifact.** Label ingestion now writes paired-label counts, consensus rate, queue reasons, and queue-tag counts.

## Cohort two

The next non-overlapping raw 10-Q cohort is ready:

| Cohort-two composition | Count |
|---|---:|
| Candidate pairs | 25 |
| Prior-cohort issuer overlap | 0 |
| Semantic-review cases | 9 |
| Clean controls | 16 |

The packet order is independently blinded by role. The next operating step is to run isolated extractor and skeptic reviews over cohort two, then ingest them with the same audit report. Cohort one should remain unpromoted until the four queued cases receive independent adjudication and the 21 consensus rows receive a spot audit.

## Autonomous cohort ledger and expansion

Raw discovery now has a persistent, hash-locked cohort ledger. It registers candidate-file hashes and issuer sets, refuses issuer overlap, automatically excludes every registered issuer, and audits whether a registered candidate file later changed. Discovery also widens its issuer scan when an issuer lacks a usable prior-year comparison instead of silently returning an undersized batch.

The ledger currently validates across four cohorts and 99 distinct issuers:

| Cohort | Cases | Semantic-review leads | Clean controls |
|---|---:|---:|---:|
| 1 | 25 | 8 | 17 |
| 2 | 25 | 9 | 16 |
| 3 | 24 | 7 | 17 |
| 4 | 25 | 5 | 20 |

Cohorts three and four have blinded extractor/skeptic packets and provenance-aware response templates ready. Cohort four requested 25 issuers, automatically expanded the scan to 30, found 27 usable candidates, and selected 25. This proves the next-batch loop can advance without manual offsets while preserving issuer isolation.

## Review packets ready now

- The four disputed cohort-one cases are in `filing_sentinel_raw_10q_2026-08-14_adjudication_packets/`. The packet includes both blind labels, all candidate evidence, and a decision template, but explicitly forbids gold promotion.
- The deterministic five-case consensus audit contains both consensus events (ABNB refinancing and AEE equity issuance) plus three clean controls. Event cases are reserved before clean controls so a restraint-focused audit cannot accidentally omit the small number of positive alerts.
