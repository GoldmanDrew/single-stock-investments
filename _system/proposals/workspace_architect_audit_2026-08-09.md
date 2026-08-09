# Workspace architect audit and system blueprint — 2026-08-09

**Status:** executed-in-part 2026-08-09 (low-effort verified fixes shipped this
session; medium fixes implemented and under verification; items needing human
sign-off listed at the end). Produced by a ten-agent parallel audit
(9 subsystem readers + completeness critic) plus deterministic verification.

## 1. Audit summary

The factory's machinery is largely sound — 21 CI workflows, 833 ticker trees
each with a schema-2.0 valuation contract, a deterministic committee pipeline
with frozen evidence packets, and a disciplined LLM cost ladder that matches
its implementation exactly. The failures are all of one species: **silent
no-ops that read as green**.

Hard numbers (verified 2026-08-09):

- **Contracts:** 833 total; 189 decision_grade (22.7%), 644 evidence_blocked.
  Dominant blocker: ownership map missing (587), then missing market price
  (129 — mechanical, no analyst work needed), stale source facts (32).
- **Backfill lane frozen since 2026-08-05:** 3 of 5 agent jobs failed (COHR,
  COP, CSX); the 2-hourly refill rebuilds the identical wave, sees "unchanged;
  no push", and never re-dispatches. 644 tickers wait behind 3 failures.
- **Committee dead since 2026-08-04** (agent execution disabled in
  13d0534f2e): 19 zero-vote committees; AAOI packet superseded 21 times by
  daily compiler churn (livelock by design — the freeze hashes live files);
  0 human_decision.json ever recorded, so calibration has no outcomes;
  2 records await human decisions (TPL 2026-07-14, 8697.T 2026-07-21).
- **Human review loop dead since 2026-07-16:** 1,882 files in pending/ of
  which 775 were machine run-receipts; 25 approvals ever; memory promotion
  queue at 1,014 items with 0 ticked; MEMORY.md frozen at 2026-05-22 while
  daily logs proposed 1,168 bullets.
- **Data integrity:** NVO's 5 locked facts are DKK recorded as "USD millions"
  (~6.9x overstatement risk; caught before compile because NVO is still
  evidence_blocked on shares/price). 202 of 244 null-CIK config tickers are
  resolvable in the SEC map the downloader never consults — each one silently
  skips all SEC downloads.
- **Deploy honesty:** dashboard deploy concludes green with the build job
  skipped when upstream fails (run 31319060163); the site serves only
  committed artifacts; a monolith-only patch (0598b731b8) never shipped.
- **CI rename fallout:** "Research quality (PR)" → "Research quality"
  (2026-08-07) left dead references in marvin-pr-automerge.yml and
  ci-autofix.yml — automerge re-trigger and repair coverage were dead paths.

Full per-subsystem findings: ten structured audit reports in the session
workflow transcript; the top-5 ranked improvements below all came from its
adversarial critique pass.

## 2. Executed this session

1. **Queue split** — power_zone run receipts (775 files) moved out of
   `_system/reviews/pending/` to `_system/data/runs/`;
   `run_security_decision_pipeline.py`, its test, and
   `power-zone-universe.yml` updated. Pending is now 1,107 files, all
   human-facing. (Tests pass.)
2. **CI rename fix** — 3 dead "Research quality (PR)" references updated.
3. **Fail-loud deploys** — new `upstream-failed` job in `dashboard-pages.yml`
   turns the silent green-on-skip window red (failure conclusions only;
   cancelled upstreams stay quiet to avoid dedupe noise).
4. **Hygiene** — `tmp/` and root `.wrangler/` gitignored (the wrangler cache
   holds account metadata and was one `git add -A` from being committed);
   finished `_tmp_*` batch scripts moved to `_system/scripts/attic/`;
   stray download logs moved out of `_system/memory/daily/`.
5. **Prompt repairs** — dead `werdn` workspace paths in MARVIN/VICKI/MILLY
   replaced with resolve-at-runtime language; VICKI now points at her live
   runbook; MILLY's "four workstreams" heading fixed (there are 8);
   the founding Cursor plan doc marked historical/superseded.
6. **Architect runbook** — `_system/prompts/architect_runbook.md`: the
   optimized self-prompt for this architect role (startup health sweep for
   the six known silent-stall modes, guards-over-prose principle, cycle
   deliverables).

## 3. Implemented, under adversarial verification (this session's workflow)

- **Fact-ledger unit guard + NVO correction** — lock-time assert that ledger
  currency matches the companyfacts unit key (explicit FX row required on
  mismatch), NVO's 5 DKK rows fixed, plus a repo-wide mismatch scan of all
  locked ledgers (any other foreign filer in the 276-ticker sleeve is exposed).
- **SEC CIK fallback + name-checked backfill** — downloader falls back to the
  SEC ticker-CIK map and logs "SEC SKIPPED: no CIK" instead of silently
  skipping; new `backfill_registry_ciks.py` applies CIKs to registry.json only
  on confident company-name matches (recycled symbols are the known identity
  trap), everything else to a held-for-review file; config regenerated via
  sync. Attacks the largest evidence bottleneck (SEC coverage 550 → ~750 of
  795 US tickers).
- **Backfill stall-breaker** — when the rebuilt wave equals the already-
  dispatched wave with no progress, stalled tickers rotate to the back so the
  refill actually re-dispatches.

## 4. Blueprint — remaining architecture (proposed, next cycles)

**Committee unfreeze (needs human sign-off — agent execution was deliberately
disabled 2026-08-04):** copy-on-freeze evidence packets (snapshot into
`committee_work/` and hash the snapshot, not live files — would have prevented
all 34 supersedes); `evidence_hash` required inside each vote and checked in
`validate_vote()`; supersede circuit breaker (park after N refreshes, surface
for triage); gate the 4-hourly refresh on the same disable flag (today it
burns cycles re-freezing packets nobody votes on); fix the ADBE-class
deadlock in `select_committee_work.py` (assembled-file existence check blinds
it to live work dirs with newer packets).

**Memory compounding:** weekly capped promotion pass over the triage queue
(newest N per lens, rejections annotated so they never re-surface); add the
six missing lens sections to MEMORY.md (Lawrence, Hohn, Buffett, Greenblatt,
Consensus, MOI) so ~316 queued bullets have a destination; a
status column on promoted beliefs (active/superseded/disproven + evidence) so
stale facts (e.g. SJT 2025 figures) can retire; per-ticker lessons files so
the 233 COMPANY bullets become queryable by ticker; auto-stub the daily log on
working days (36 of 81 days missing, including the two most eventful).

**Queue drainability:** typed rollup view over pending/ (group by the ~5
item types that need verdicts, sort by age) instead of a flat directory;
auto-expiry for dated ephemera (regime briefs, press digests); status-header
convention on every proposal with a close-out rule (the sp500 bulk-onboard
plan still says "ready to execute" though 503/503 completed).

**Validator honesty:** content-hash core.json/shards against
dashboard_data.json (row counts pass today while content diverges); a
freshness beacon (commit SHA + generated_at) in the deployed artifact;
generate ci-autofix's watched-workflow list from the workflows directory
instead of a hand-curated stale list; staleness alert when nightly lanes go
> 48h without landing a commit.

**Mechanical unblocks:** split the 129 missing-price tickers into a price-feed
queue (no analyst work; cuts blocked count ~20%); machine-readable blocker
codes `{code, component_id}` beside the prose (14 blockers already defy
regex tallying); regenerate the backfill queue at end of each wave instead of
shipping a snapshot that drifts in days; pre-screen queue waves for CIK
presence (the missing-CIK dead end is invisible in logs).

## 5. Needs a human decision

1. **TPL and 8697.T committee records** rest at decision_pending (evidence now
   stale — decide, or approve re-freeze under the new packet design).
2. **Memory promotion cadence** — approve the weekly capped pass; 1,014 items
   wait, zero ever promoted.
3. **Committee re-enable** — the unfreeze design above, given agent execution
   was deliberately disabled.
4. **Extreme-IRR review** — outlier_validation cleared ABX, AEHR, AXON, AXTI,
   CEG with human review advised.
5. **NVO shares_outstanding** — the IFRS taxonomy lacks the dei concept; the
   diluted share count needs extracting from the 2026-02-04 20-F on disk and
   locking with an evidence ref.
6. **811 onboard checklists** in pending/ — approve an expiry/sampling policy,
   or they remain permanent queue sediment.
