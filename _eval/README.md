# _eval — error-driven gold sets for the SSI pipeline

The blueprint bar (`_system/prompts/ssi_perplexity_grade_blueprint.md` §1):

| Metric | Bar | Measured from |
|---|---|---|
| Severity-5 (critical event) recall | 100% | `ssi_sev5_events.jsonl` |
| Citation / locator accuracy | 100% | `ssi_skeptic_gold.jsonl` (adjudicated) |
| Top-alert precision | ≥ 85% | `ssi_alert_adjudications.jsonl` |

A capability that cannot state its current numbers against these bars is a
prototype, not a capability. Run `python _system/scripts/calibrate_ssi.py`
to see the current numbers (and `--enforce` in CI to fail on a missed bar).

**A bar with nothing behind it reports INSUFFICIENT DATA, not a pass.**
`locator_accuracy` used to return exactly `1.000 MEETS BAR` on zero adjudicated
cases — "no confirmed errors" rendered as "no errors" — and `severity5_recall`
returned 100% off a single event. Both now decline to answer until the evidence
exists: accuracy needs at least one adjudicated non-infrastructure case, recall
needs `MIN_SEV5_EVENTS_FOR_RECALL` (5) known events. `--enforce` only fails a
*measurable* bar that is unmet, so an honest gap never breaks CI — it just stops
the number from being quoted as if it meant something.

## Files

- **`ssi_skeptic_gold.jsonl`** — append-only; every Phase 3 verification
  failure lands here automatically (`verify_ssi_claims.py`) with
  `adjudication: "pending"`. Adjudicate with
  `python _system/scripts/ssi_adjudicate.py gold` rather than editing by hand.
  - `generator_error` → Phase 2 emitted a bad claim (hurts locator accuracy)
  - `skeptic_error` → Phase 3 killed a good claim (false kill)
  - `ambiguous` → genuinely unclear on the evidence
  - `infrastructure` → **auto-labelled, never queued.** Source drift or a pack
    mismatch means the sources moved underneath the pack, so the claim was never
    re-checked: it is neither a generator nor a skeptic error. Left as `pending`
    these swamp the queue — one NVDA run contributed 258 of 261 cases — and
    labelling them either way corrupts locator accuracy. Excluded from the bar
    and reported separately. Re-run on a stable pack to get a real verdict.

  Re-runs do not duplicate: a case already logged for the same
  `(issuer, claim_id, as_of)` is skipped. Before this, four Phase 3 re-runs had
  written the same 129 NVDA failures 516 times.
- **`ssi_alert_adjudications.jsonl`** — human verdicts on emitted severity ≥ 4
  claims, one JSON object per line:
  `{"issuer": "TBBK", "claim_id": "…", "as_of": "…", "adjudication": "real" | "noise", "note": "…"}`
  Feeds top-alert precision.
- **`ssi_sev5_events.jsonl`** — known critical events (going concern, material
  weakness, covenant breach, restatement, delisting) per issuer with whether
  the pipeline caught them:
  `{"issuer": "TBBK", "event": "material_weakness", "period": "FY2024", "caught": true, "claim_id": "…"}`
  Feeds severity-5 recall.

## Split discipline

Splits are **by issuer, never by filing**, to prevent leakage:
`sha1(issuer) % 10` → 0-6 train · 7-8 dev · 9 test (implemented in
`calibrate_ssi.py --splits`). Regex/threshold tuning may look at train/dev
issuers only; test issuers are untouchable until a release evaluation.

## Rules

- Never delete a gold case; supersede with a new line if re-adjudicated.
- Every false positive, missed event, or broken locator from any run becomes
  a case here — that is how the pipeline compounds instead of drifting.
- No unverified narrative is ever promoted to memory or reports from here.
