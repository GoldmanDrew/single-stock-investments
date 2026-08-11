# Evidence integrity: finding what is missing when nothing reports it

**Status:** live runbook (2026-08-11). Detector: `_system/scripts/check_evidence_integrity.py`.
Baseline: `_system/data/evidence_integrity_baseline.json`. Runs in the
`graph-invariants` job of `research-quality.yml`.

## The failure class

Every defect this catches has one shape: **an artifact reports success while
the evidence underneath it is absent, and no status field disagrees.** The
pipeline is built so each stage validates its own output, which means a stage
fed starved inputs still passes. The signal never exists inside one file — it
exists only in the *disagreement between two files that should agree*.

Three worked examples, all found this way:

| found | looked healthy as | actually |
|---|---|---|
| WHK contract | `decision_grade`, 0 blockers | compiler stage said `evidence_blocked`, 8 evidence tasks at `attempts: 0` |
| 124 tickers | `decision_grade` | invisible to *every* remediation queue, because all three skip `decision_grade` |
| 531 tickers | filings extracted, facts parsed, reports rendered | text cut at 300K chars; Liquidity and the F/S notes never extracted |

The third is the most instructive. WHK's 424B4 cleans to **1,283,894 characters**
and was being cut to 300,000 — 23% of the document. Downstream *everything
still worked*: the fact parser ran, the contract compiled, the committee
convened, the dashboard rendered. The covenants (Leverage Ratio <= 3.0x), the
hedge book, and the percentage-depletion detail simply were not there, and the
committee recorded them as "not disclosed" when the truth was "not extracted."

## The loop

This is the reusable part. Four steps, each cheap:

**1. Name the contradiction, not the symptom.** Do not check "is this valid."
Check "do these two files agree." Every check in the sweep is a pair:

```
contract.status == decision_grade   vs   automation_state.model_compile == evidence_blocked   (V1)
route.primary_method                vs   the methods the proofs actually execute             (V4)
component results exist             vs   summary totals absent -> dashboard null             (V5)
extracted_chars                     vs   source_chars                                        (V8)
```

**2. Measure prevalence before building anything.** Write a throwaway script,
run it over all 833 tickers, and only then decide what deserves to be a check.
Two of the seven original checks were measuring the wrong thing and would have
shipped false headline counts:

- V2 first read `contract.input_classification.facts`, empty for 187 of 192
  decision-grade contracts. That field is empty *by construction* -- `_input_kind`
  classifies a whole component as "judgment" if any single input is one, which
  every real model has. Counting sourced `kind: fact` proof nodes instead gave
  the honest answer: **1**.
- V7 first counted every ticker missing method inputs: 646. But 641 contracts
  are *correctly* `evidence_blocked` -- that is the backlog working. Restricted
  to `decision_grade`: **81**.

A check that reports 187 defects where 1 exists is worse than no check.

**3. Mirror the real rule, never approximate it.** V4 copies
`compile_existing_approved_proofs`'s `route_supported` logic verbatim, because
that function returning `None` *is* the consequence being detected: the
issuer's authored proofs get silently discarded and recompiled from the
normalized ledger on the next run. An approximation would report tickers that
are fine and miss tickers being overwritten.

**4. Ratchet, do not gate.** 531 tickers fail V8 today. Failing CI on that
freezes the factory, which the graph README already names as the worse
failure. The baseline records today's counts; CI fails only when a count
*rises*. Numbers can then only go down.

```bash
python _system/scripts/check_evidence_integrity.py                 # report + ratchet
python _system/scripts/check_evidence_integrity.py --ticker WHK    # triage one
python _system/scripts/check_evidence_integrity.py --worklist 25   # what to fix first
python _system/scripts/check_evidence_integrity.py --update-baseline
```

## Making truncation impossible to hide

The generalisable fix, in `build_filing_evidence.py`:

1. **Separate the read from the cap.** `clean_filing_text()` returns the whole
   document; `apply_char_cap()` caps it. Only then can the caller know the true
   size. Previously the cap was applied inside the read, so the original length
   was never observable.
2. **Leave a marker.** A capped extract ends with
   `[EXTRACT TRUNCATED: kept N of M chars (P%)]`. A truncated file can no
   longer pass as whole to a human or a regex.
3. **Record coverage.** `coverage_record()` writes `source_chars`,
   `extracted_chars`, `truncated`, `coverage_pct` and which key sections landed
   into `document_inventory.json`.
4. **Size the cap from the corpus, not intuition.** The largest full-tier
   documents clean to 1.28M chars (WHK 424B4) and 885K (AAL 10-K), so the cap
   is 1.5M. This is the second time it was raised -- 120K -> 300K -> 1.5M -- and
   the first two raises were silent, which is why it broke again unnoticed.
   With coverage recorded, a third overflow reports itself.

`_text/` is gitignored, so a larger cap costs local disk, not repository weight.

## Applying it to the rest of the corpus

531 tickers still carry pre-fix extracts. Re-extraction is idempotent:

```bash
python _system/scripts/build_filing_evidence.py WHK ICE FRMO       # named tickers
python _system/scripts/build_filing_evidence.py                    # whole corpus (slow)
python _system/scripts/check_evidence_integrity.py                 # confirm V8 fell
```

Re-extraction alone does not fix downstream artifacts. A ticker whose evidence
was starved needs its facts re-parsed and its contract recompiled afterwards:

```bash
python _system/scripts/automate_valuation_readiness.py --tickers WHK --date <today> --full-rerun
python _system/scripts/run_security_decision_pipeline.py --tickers WHK --date <today>
```

**Order matters and is not optional.** Re-extract, then recompile, then
re-review. A committee convened on a starved packet reaches a confident
conclusion on absent evidence -- which is exactly what happened to WHK's
2026-08-10 round, where two of three raters recorded "insufficient evidence"
for facts that were in the filing all along.

## Open items

- 909 `_text/` files remain tracked in git from before the ignore rule at
  `.gitignore:54`. They are a derived cache; leaving them tracked means a
  re-extraction at the larger cap would add real weight to the repository.
  `git rm --cached` on that set would make the existing ignore rule effective.
- V8 currently proves only that text *reached* the cache. It does not verify
  that the fact parser then read the newly available sections. The natural
  next check is a parser-coverage one: locked facts per filing against the
  sections now present.
