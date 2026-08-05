# 10-Q/K Filing Sentinel gold set

**Status:** executable foundation  
**Scope:** 10-Q and 10-K material-change detection for portfolio and watchlist issuers  
**North star:** catch decision-relevant changes with exact primary evidence while keeping false alerts low enough that the feed remains trusted.

## What the benchmark tests

The evaluation unit is a filing, not an isolated sentence. A case can contain multiple offsetting events and explicit tags that must **not** be emitted. Each gold event records:

- one stable category and one or more controlled tags;
- whether it strengthens or weakens the short/risk case;
- severity, claim, values, and a falsifier;
- exact evidence IDs resolving to hashed excerpts;
- whether the conclusion requires human review.

The locked seed set lives in `_system/scripts/_eval/filing_sentinel_gold.jsonl`. It deliberately includes real material changes plus segment and footnote pairing traps inherited from the repository's filing regression tests.

## Lifecycle

```text
raw filing -> candidate -> independently labeled -> adjudicated gold -> frozen evaluation split
                   |                   |
                   +-> reject/retire <-+
```

`mine` may create candidates autonomously. It never changes `label_status` to `gold`. Gold promotion is a separate reviewed action so model output cannot silently become its own answer key.

### Candidate

- Filing identity and accession are resolved.
- Source hash is stored when the local extract exists.
- Exact XBRL evidence windows are hashed.
- Material metric proposals, parser traps, and quiet controls are prioritized.
- Split remains `_unassigned`; `expected` is intentionally empty.

### Labeled

- Two independent passes label the case without seeing each other's answer.
- Each event has a source-resolving evidence ID and falsifier.
- Disagreements are retained, not averaged away.

### Gold

- An adjudicator resolves event existence, taxonomy, direction, severity, and evidence.
- Always-review tags (going concern, restatement, auditor change, material weakness, related party, investigation, and litigation) require analyst review.
- Content hashes, schema, controlled vocabulary, and leakage rules pass.
- The case is assigned by issuer group to one frozen split.

## Autonomous build loop

Run the following loop after new filing facts are generated:

1. **Discover:** scan portfolio and watchlist `filing_facts` artifacts; deduplicate by source filing.
2. **Stratify:** rank material positives/negatives, parser hard negatives, and quiet controls. Preserve offsetting evidence in the same filing.
3. **Pack evidence:** attach current/prior fact windows, accession, period, original source reference, and hashes. Later semantic miners should add section-level windows for risks, accounting policies, liquidity, legal matters, and controls.
4. **Blind labels:** run an extractor pass and a skeptic pass with independently randomized case order. Neither may read the agent prediction being evaluated.
5. **Adjudicate:** auto-accept exact agreement on low/medium-risk tags; send disagreements and always-review tags to a separate adjudicator or analyst.
6. **Quality check:** validate hashes and locators, reject unsupported claims, deduplicate near-identical cases, and check issuer/source leakage.
7. **Promote:** append immutable gold rows. Never rewrite an old label; retire it with a replacement case and reason.
8. **Evaluate:** score event precision/recall, severity-weighted recall, critical recall, direction, citation validity, clean-filing accuracy, and false alerts per filing.
9. **Mine failures:** route false positives, false negatives, and adjudicator disagreements back into the next candidate batch at higher priority.

## Sampling policy

Each 100-case expansion should target:

| Stratum | Target | Purpose |
|---|---:|---|
| High/critical adverse changes | 25% | Red-flag recall |
| Material offsetting or positive changes | 15% | Direction and balanced reasoning |
| Accounting/controls/legal/governance | 15% | Semantic and high-risk conclusions |
| Parser and comparison traps | 20% | False-positive resistance |
| Quiet filings / no material change | 15% | Alert precision |
| Rare tags and prior model failures | 10% | Long-tail and regression coverage |

Also require at least 35% 10-Q, 35% 10-K, and no more than 5% of the set from one issuer. Sampling quotas are checked on gold promotion, not by weakening evidence requirements.

## Leakage policy

- All filings for one issuer belong to one split.
- Amended filings, duplicate downloads, and identical source hashes remain in one split.
- Candidate creation date does not determine the split.
- Test labels are never included in retrieval context, prompts, traces, or training exports.
- Training examples may be derived only from the `train` split; threshold tuning uses `dev`; final claims use `test`.

## Evaluation gates

The initial gates are stored in `_system/data/filing_sentinel_taxonomy.json`:

- precision >= 85%;
- recall >= 80%;
- critical-event recall = 100%;
- citation precision >= 95%;
- false alerts <= 0.25 per filing.

These are release gates, not optimization targets. Report every metric by form, category, tag, severity, issuer size, and parser-confidence stratum once the set is large enough.

## Commands

```bash
# Validate the locked benchmark, including hashes and leakage.
python _system/scripts/filing_sentinel_gold.py validate --require-gold

# Autonomously mine a bounded portfolio/watchlist review queue.
python _system/scripts/filing_sentinel_gold.py mine --as-of YYYY-MM-DD --limit 100

# Inspect mining behavior without writing a queue.
python _system/scripts/filing_sentinel_gold.py mine --universe all --limit 25 --dry-run

# Evaluate an agent prediction file and fail when a release gate is missed.
python _system/scripts/filing_sentinel_gold.py evaluate \
  --predictions path/to/predictions.jsonl --split test --strict
```

## Operating the autonomous loop

The workflow runner implements the full pre-promotion loop:

```bash
# 1. Build a quota-balanced, issuer-split batch with current/prior section packs.
python _system/scripts/filing_sentinel_workflow.py build-batch \
  --as-of YYYY-MM-DD --limit 100 \
  --output _system/reviews/pending/filing_sentinel_candidates_YYYY-MM-DD.jsonl

# Mine historical raw filings when filing_facts coverage is incomplete.
# This discovers comparable 10-Q/K pairs directly and produces review-only
# section deltas (never final semantic conclusions).
python _system/scripts/filing_sentinel_raw_discovery.py \
  --since 2023-01-01 --per-ticker 4 --limit 100 \
  --output _system/reviews/pending/filing_sentinel_raw_candidates_YYYY-MM-DD.jsonl

# Advance to a non-overlapping issuer cohort on the next run.
# --issuer-offset 25 is appropriate after a 25-issuer cohort.

# 2. Generate independent packets. The packets hide issuer, source path,
# existing proposals, labels, and split from both reviewers.
python _system/scripts/filing_sentinel_workflow.py create-packets \
  --candidates _system/reviews/pending/filing_sentinel_candidates_YYYY-MM-DD.jsonl \
  --batch-id YYYY-MM-DD \
  --output-dir _system/reviews/pending/filing_sentinel_YYYY-MM-DD_packets

# 3. After each reviewer returns JSONL, auto-label exact low-risk agreements
# and write every disagreement or always-review tag to adjudication.
python _system/scripts/filing_sentinel_workflow.py ingest-labels \
  --candidates ...candidates_YYYY-MM-DD.jsonl \
  --manifest ...packets/control/blind_manifest.json \
  --extractor extractor_labels.jsonl --skeptic skeptic_labels.jsonl \
  --output labeled.jsonl --adjudication-output adjudication_queue.jsonl

# 4. Explicitly adjudicate and promote. Auto-consensus promotion is opt-in.
python _system/scripts/filing_sentinel_workflow.py promote \
  --labeled labeled.jsonl --decisions adjudications.jsonl \
  --gold _system/scripts/_eval/filing_sentinel_gold.jsonl \
  --output proposed_gold.jsonl

# 5. Route model errors to a regression queue. Test failures stay excluded
# from training exports by construction.
python _system/scripts/filing_sentinel_workflow.py queue-failures \
  --gold _system/scripts/_eval/filing_sentinel_gold.jsonl \
  --predictions predictions.jsonl --output failure_queue.jsonl
```

`build-batch` locks splits by issuer before labels exist, applies the filing-form and stratum quotas, caps issuer concentration, and emits a companion JSON summary. It packs structured facts plus source-hashed section snippets for liquidity, accounting, operating, governance/legal, transaction, and instrument language; section hits are review leads, not automatic conclusions. Give labelers only `packets/labelers/*.jsonl`; the `packets/control/blind_manifest.json` mapping is restricted control-plane data.

Prediction rows use this minimal contract:

```json
{"case_id":"fs-example","events":[{"category":"financial_oxygen","tags":["cash_runway"],"direction":"strengthens","evidence_ids":["ev-liquidity-note"]}]}
```

## Next autonomous expansions

The current miner is intentionally limited to structured-fact neighborhoods. The next gold-set expansion should add section diffs in this order:

1. liquidity, debt maturities, covenants, going concern, and equity issuance;
2. controls, accounting policies, restatements, and auditor language;
3. risk-factor additions/removals and legal proceedings;
4. customer concentration, backlog, impairments, restructuring, and related parties.

For each new extractor, first add hard-negative gold cases. A semantic detector should not ship merely because it finds examples; it ships when it distinguishes them from look-alike language.
