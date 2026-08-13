# Filing Sentinel gold-set baseline - 2026-08-04

## Result

The Filing Sentinel now has an executable gold-set foundation rather than a prompt-only specification.

| Measure | Current seed |
|---|---:|
| Filing-level gold cases | 4 |
| 10-K / 10-Q | 3 / 1 |
| Gold events | 6 |
| Financial-oxygen / operations events | 3 / 3 |
| Strengthens / weakens risk case | 3 / 3 |
| Explicit parser traps | 2 |
| Evidence excerpts with verified hashes | 7 / 7 |
| Original filings with verified hashes | 4 / 4 |

The perfect-prediction control scores 100% on event precision, recall, evidence citation, direction, and every configured quality gate. This proves the harness; it is not an estimate of a production agent's quality.

The operational batch is now built at `_system/reviews/pending/filing_sentinel_candidates_2026-08-04.jsonl`: 100 schema-validated portfolio/watchlist candidates with original filing hashes, section evidence, deterministic issuer splits, and separate blinded extractor/skeptic packets. Candidate creation does not mutate the locked gold set.

The batch has 22 usable 10-Q cases and 78 10-K cases. The local evidence corpus therefore misses the 35-case 10-Q quota by 13 cases; it also misses two clean controls and has no model-failure regressions yet. These are recorded quota shortfalls, not silently relaxed release criteria. The next ingestion job should prioritize historical 10-Q evidence and quiet filings before another batch is promoted.

That historical 10-Q lane is now operating: the first 25 source-hashed prior-year 10-Q pairs and their blinded packets are in `_system/reviews/pending/filing_sentinel_raw_10q_candidates_2026-08-04.jsonl`. See `_system/research/filing_sentinel_discovery_review_2026-08-04.md` for the review findings and guardrails.

## What is covered

- Material operating-income contraction and expansion.
- Material cash contraction and expansion as offsetting financial-oxygen evidence.
- Consolidated revenue growth hidden behind a segment-zero pairing trap.
- Debt-footnote values that must not be interpreted as a balance-sheet debt change.
- Issuer-group split isolation, immutable evidence hashes, controlled tags, forbidden-tag checks, and unknown-case checks.

## What is not yet covered

This seed is a regression harness, not a release-grade benchmark. Do not use its aggregate score as a production claim yet.

- No critical-severity cases.
- No fully reviewed zero-event filing.
- No accounting, controls, legal, governance, identity/instrument, or transaction gold events.
- No section-diff examples from Risk Factors, MD&A, Controls and Procedures, Legal Proceedings, or footnotes.
- The bootstrap labels have not yet received two independent analyst passes.
- Only four issuers are represented, so category and form scores are not statistically meaningful.

## Autonomous expansion decision

The next milestone is **100 double-reviewed cases**, with the sampling quotas in `_system/frameworks/filing_sentinel_gold_set.md`. The system can autonomously perform discovery, evidence packing, hashing, stratification, blind first/second labels, disagreement routing, schema checks, leakage checks, evaluation, and failure mining.

Human involvement should be concentrated at two gates:

1. adjudication of disagreements and the always-review tag list;
2. a random audit of agreed low/medium-risk labels before promotion.

This preserves autonomy without allowing the model under evaluation to manufacture its own answer key.

## Release criterion for the first useful Sentinel

Do not connect alerts to the main portfolio feed until all of the following hold on the frozen test split:

- at least 100 total gold cases and 25 clean/no-event cases;
- at least 15 critical/high financial-oxygen or accounting cases;
- 100% critical recall;
- at least 85% event precision and 80% event recall;
- at least 95% evidence citation precision;
- no more than 0.25 false alerts per filing;
- no unsupported always-review conclusion.

Until then, the agent should write only to a review queue.
