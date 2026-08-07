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

## Files

- **`ssi_skeptic_gold.jsonl`** — append-only; every Phase 3 verification
  failure lands here automatically (`verify_ssi_claims.py`) with
  `adjudication: "pending"`. A human (or adjudicator agent) edits the line to
  `adjudication: "generator_error" | "skeptic_error" | "ambiguous"`.
  - `generator_error` → Phase 2 emitted a bad claim (hurts locator accuracy)
  - `skeptic_error` → Phase 3 killed a good claim (false kill)
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
