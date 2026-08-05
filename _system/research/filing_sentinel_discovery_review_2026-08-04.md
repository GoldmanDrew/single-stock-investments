# Filing Sentinel discovery review - 2026-08-04

## What the additional review found

The structured-fact lane is materially biased toward annual filings: it currently exposes 293 unique 10-K source filings but only 22 unique 10-Q source filings in the portfolio/watchlist universe. The repository also contains a much larger raw historical filing corpus, so absence from `filing_facts` is a pipeline-coverage issue, not evidence that quarterly filings are unavailable.

The new raw-discovery lane reviewed a first cohort of 25 historical 10-Q pairs. Every candidate compares a filing with the nearest same-form period 300-430 days earlier. This replaced an unsafe sequential-quarter comparison that was detected during the review.

| Raw 10-Q cohort | Count |
|---|---:|
| Candidate pairs | 25 |
| Clean/no-new-high-risk controls | 17 |
| High-risk semantic review proposals | 10 |
| Candidates with high/critical review priority | 8 |
| Train / dev / test | 17 / 4 / 4 |

## Review proposals, not conclusions

The keyword-delta lane found ten disclosures that warrant comparison by an independent reviewer:

| Tag | Count |
|---|---:|
| Investigation | 3 |
| Related party | 2 |
| Refinancing | 1 |
| Wind down | 1 |
| Auditor change | 1 |
| Serial equity issuance | 1 |
| Restatement | 1 |

These are deliberately low-confidence, `review_required` proposals. A keyword appearing in a filing is not evidence that the issuer has committed misconduct, faces a material legal issue, or has a deteriorating thesis. The paired source sections must establish novelty, materiality, and context before a gold event can exist.

## Knowledge compounded into the agent

1. **Prior-year comparability is mandatory.** The raw lane rejects quarter-over-quarter pairing for disclosure novelty. Every comparable filing period is now validated to be roughly one year earlier.
2. **Raw filings can bridge structured-data coverage.** The agent can now form source-hashed, filing-level evidence packs directly from historical 10-Q/K HTML even if no `filing_facts` artifact exists.
3. **Semantic hits are leads.** Going concern, controls, legal, transaction, and accounting vocabulary enters a human-review path, never an automatic conclusion.
4. **The corpus rotates safely.** `--issuer-offset` advances through deterministic issuer cohorts, so the next 25-issuer 10-Q batch expands coverage rather than repeatedly sampling the same issuers.
5. **Clean controls are first-class data.** Seventeen of the first 25 cases contain no new high-risk disclosure term; these are necessary to teach the Sentinel restraint.

## Next review batch

Run the next non-overlapping 10-Q cohort:

```bash
python _system/scripts/filing_sentinel_raw_discovery.py \
  --forms 10-Q --since 2023-01-01 --per-ticker 1 \
  --max-issuers 25 --issuer-offset 25 --limit 25 \
  --output _system/reviews/pending/filing_sentinel_raw_10q_candidates_next.jsonl
```

Do not merge these raw candidates into the locked gold file until blind extractor and skeptic labels, plus required adjudication, are complete.
