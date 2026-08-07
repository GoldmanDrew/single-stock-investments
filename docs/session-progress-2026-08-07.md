# Session progress and open items — as of 2026-08-07

Reconstructed from the five Claude Code sessions of 2026-08-05 → 08-06, then updated
after the 2026-08-07 session closed out the queued work. Written so work can resume
without re-reading the transcripts.

---

## 1. What is done and on `main`

### SSI pipeline — all four blueprint phases now committed
Phases 1–3 were merged earlier. **Phase 4 (the renderer), the batch driver, the
calibration and coverage scripts, the v2 test module and the CI job had never actually
been committed** — they existed only in the working tree until 2026-08-07.

| Phase | What it does | Where |
|---|---|---|
| 1 — Evidence pack | Immutable point-in-time store: accession, date, content hash, locator | `build_ssi_evidence_pack.py` |
| 2 — Atomic claims | Filing deltas → severity-scored atomic claims, ledger, spawner | `build_ssi_claims.py` |
| 3 — Blind Skeptic | Pack-integrity recheck, re-parses every cited locator, re-derives direction from raw values, deletes (not softens) failures; gatekeeper routing via `decision_authority`; time-zero snapshot; failures appended to `_eval/ssi_skeptic_gold.jsonl` | `verify_ssi_claims.py` |
| 4 — Report + gate | §4 output contract, valuation strictly via `decision_authority`, missing feeds rendered as explicit **Gap** sections, mechanical §5 shipping gate | `build_ssi_report.py` |

Batch driver: `run_ssi_pipeline.py`. 157 tests passing.

### QDEL respiratory demand model
Merged as a full KPI panel (`5b8ce6b00db`). Lives on **Insights → Inflections**;
documented in [respiratory-kpi.md](docs/respiratory-kpi.md).

The important finding is negative and should not be quietly re-litigated: **flu-trend
terms had no out-of-sample forecasting value** under LOOCV on n=9, and permutation
testing showed the apparent fit was spec-search overfitting. The shipped model is a
log-linear baseline (seasonal dummies + trend, no flu terms); respiratory testing
volumes are carried as labeled demand *context* only. The panel includes the candidate
ladder showing why every testing-augmented spec scores worse, plus the falsification note.

### The three queued items (#9, #10, #11) — all applied 2026-08-07

**#9 — the valuation gate check is split.** One check had been answering two questions:
whether the renderer obeyed the one-valuation-language rule, and whether a
`decision_grade` contract existed to quote at all. An absent upstream contract therefore
surfaced as a defect in the run. Now `valuation_contract_only` reports renderer
discipline (and still FAILs on a genuine breach — value figures rendered without
`decision_grade`, or authority resolution erroring), while
`valuation_contract_decision_grade` BLOCKs when the contract simply isn't ready.

To keep the discipline check honest rather than tautological, the report body is now
assembled *before* the gate runs, so the check reads what was actually rendered.

**Effect across the batch: 160 `NOT SHIPPABLE` → 3.**

| | before | after |
|---|---|---|
| SHIPPABLE | 0 | 0 |
| DRAFT (blocked) | 107 | 266 |
| NOT SHIPPABLE | 160 | **3** |

**#11 — debt-maturity schedule buckets are footnote detail.** The real cause was
ordering: these tags match `LongTermDebt\w*` in `PRIMARY_CONCEPTS`, and `tag_tier` tests
primary *first*, so a single roll-forward bucket ranked as primary economics. Debt moving
from "year two" into "next twelve months" produces a −100%/+100% pair every year with no
change in the total obligation. `MATURITY_SCHEDULE` is now tested ahead of
`PRIMARY_CONCEPTS`; aggregate debt tags (`LongTermDebt`, `LongTermDebtNoncurrent`,
`DebtInstrumentCarryingAmount`, …) are unaffected. **905 claims across the batch had been
ranking as primary on this basis** and are now capped at severity 2.

**#10 — the batch was re-run.** 269 tickers, Phases 2–4: **269 ok, 0 failed**,
53,152 Skeptic-verified claims, 367 severity-5 signals, 268 with a gated YoY comparison.
BA and BB (the two mid-run failures from the previous session) are included and pass.

### Artifact compaction
`ssi_verified_claims` was verified to be a strict superset of `ssi_claims`' bodies (same
claim_ids, same fields, plus a `verification` block). The `claims` array is now dropped
once the Skeptic pass consumes it, while the Phase-2-only content Phase 4 reads
(`management_ledger`, `spawner`, the tier/severity histograms) is kept.

**`ssi_claims`: 78.5 MB → 1.3 MB, with no loss of information.**

Compaction runs *before* the time-zero snapshot and the Phase 4 audit trail hash the
file, so both record what is actually on disk — all 269 time-zero hashes and all 269
report audit-trail hashes verify. Phase 2 is deterministic, so re-running it restores the
array; re-verifying a compacted file raises rather than silently verifying nothing;
`--check` never compacts; `--no-compact` opts out.

### TBBK, AMR, RIG, HCC
Committed 2026-08-07. TBBK: **`decision_grade`, 4 components, zero blockers**, base
$87.00 vs $72.095, range $48.50–$141.93; committee correctly did not initialise (`watch`,
price far above the $32.71 hurdle). Root cause of the long-standing block was a missing
`cik` (see §4.1). AMR/RIG/HCC re-routed from the compounder default to
`cyclical`/`capital_cycle`; all three remain `evidence_blocked` pending their own
evidence work — that commit fixed routing, not valuations.

---

## 2. Outstanding

### 2a. Three genuine report failures
These are the gate working correctly, and each is a real defect worth its own look:

| Ticker | Failing checks | Detail |
|---|---|---|
| **NVDA** | `locator_resolution`, `comparability_gate`, `falsification_quantified` | **129 claims, all failed verification, 0 verified.** The most serious of the three. |
| **NVO** | `locator_resolution`, `falsification_quantified` | **0 claims produced at all** — Phase 2 yields nothing. |
| **ABX** | `locator_resolution` | 1 of 300 claims failed Skeptic verification. |

### 2b. Known lower-precision signals
- **`default` is the highest-volume, lowest-precision severity-5 trigger** (62 hits at
  last survey). One confirmed false positive (ALB) had evidence stating the company *was
  in compliance*; that pattern is fixed, but tickers processed before the fix may still
  carry it. The other sev-5 keywords look more trustworthy by nature: material weakness,
  subpoena, restatement, delisting, going concern, covenant breach.
- **Cash-flow reconciliation lines dominate severity 4** —
  `CashCashEquivalents…PeriodIncreaseDecreaseIncludingExchangeRateEffect` and the
  financing/investing activity lines. These are volatile by construction and probably
  over-weighted, the same class of problem #11 addressed. **Not yet acted on** — it was
  never a decided item, only an observation.

### 2c. Coverage
- **`no_transcripts` is the largest blocker (807 tickers).** `earnings_calendar.json`
  reports `access_status: no_key`, which is why the Management Ledger scores zero guidance
  promises. The PitchBook connector exposes `pitchbook_get_call_transcripts_analysis`,
  which could cover it without a new Polygon subscription — deliberately not wired, since
  that is an external data path to choose consciously.
- **269 of 512 tickers have been run.** The remainder were skipped because they lack both
  a gated comparison and XBRL, so their reports would be incomplete.

### 2d. Repo weight
`.git` is ~30 GB. The 2026-08-07 commits added ~444 MB (down from 521 MB after
compaction). The `dashboard/` refresh (~166 MB) and the ticker evidence directories are
the bulk. `dashboard_data.json` (74 MB) is still tracked: `investment-committee.yml` and
`power-zone-universe.yml` both `git add` it and `refresh_valuation_dashboard_rows.py`
patches it in place, so untracking it is a real refactor that breaks two workflows.

---

## 3. CI state

- **`dashboard-integrity` is red repo-wide** and has been bypassed on explicit approval.
  It flags any `decision_grade` valuation whose annualized return exceeds a 25%
  "uncorroborated IRR" threshold. AEHR, AXON, AXTI, CEG were already past that line;
  ABX's promotion added a fifth (−26.24%). Each is cross-validated via the repo's own
  `outlier_validation` methodology, so it reads as an expected human-review flag rather
  than a bug — but it is a real gate currently being bypassed.
- **`test_technical_signals.py` fails on `main`, unrelated to any of this work.** The
  module was renamed to `build_technical_signals.py` and bumped to `technical-fear-v2`
  while the test still asserts `technical-z-v1`. Both files are unmodified in the working
  tree, so this predates the 2026-08-07 session. Left alone deliberately — it is a
  one-line fix but belongs to whoever did the rename.
- **`research-lint` and `oauth-secrets` show transient GitHub runner-provisioning
  failures** ("job was not acquired by Runner of type hosted"), stalling ~28 min then
  cancelling. Run `31118200740` failed this way and the next run succeeded in 2m32s. Not
  a content problem.

---

## 4. Known traps — read before touching the valuation pipeline

Each of these cost a session to discover.

1. **A missing `cik` silently kills the whole chain.** No CIK → no SEC download → no fact
   ledger → permanently `evidence_blocked`, with nothing in the logs naming the cause.
   As of 2026-08-06 this affected 241 US registry holdings; 203 resolved from the local
   SEC map, the other 38 are CVR/ETF/OTC pseudo-tickers with no CIK by nature (correctly
   unresolvable, not a backlog).
2. **`_system/scripts/us_ticker_config.json` shadows `registry.json`.** The registry is
   only consulted when the ticker is *absent* from that config, so an entry with
   `"cik": null` beats a correct registry entry. **Fix both files**, and verify by a
   non-zero `SEC=` count, not by re-reading the registry.
3. **`automate_valuation_readiness.py` can clobber a rich `valuation.json`** — observed on
   STHO: 34 keys → 9, dropping `scenarios`, `approved_stance`, `human_review`,
   `property_register` and more, while still reporting `decision_grade ready 8/8`. It
   happens with *and* without `--full-rerun`. Snapshot before running; diff the top-level
   key set after. Losses limited to `context_overlay` / `human_review` / `insider_signal`
   / `notes` are fine — the daily refresh regenerates those.
4. **`--tickers` is `nargs="+"`** (space-separated). A comma list scaffolds a junk
   directory literally named `"KO,LMNR,TOI"`.
5. **Identity overrides the registry.** New tickers default to `archetype: compounder` /
   `valuation_profile: quality_reinvestment` in `research/security_identity.json`, and
   that beats the registry classification in `power_zone_router.merged_classification`.
   Fix identity, then re-run with `--full-rerun` — a reroute alone leaves the old compiled
   component in place and still reports `decision_grade`. Note that `valuation_profile`,
   not `archetype`, drives the method route and the seated reviewers; `archetype` feeds
   `specialist_fit` but is frequently a no-op once an explicit profile is set.
6. **Windows console is cp1252.** Any script here that `print()`s an em-dash, arrow or
   ellipsis dies with `UnicodeEncodeError` even though written files are fine. Add after
   imports:
   ```python
   if hasattr(sys.stdout, "reconfigure"):
       sys.stdout.reconfigure(encoding="utf-8", errors="replace")
   ```
7. **Stale `.git/index.lock` from killed sessions.** Sessions have shared this working
   tree and stepped on each other. Before removing a lock, confirm no `git` process is
   running and check the timestamp. If two agents run concurrently, give one a worktree.
