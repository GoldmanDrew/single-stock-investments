# The workspace graph — procedural + epistemic memory, executed

**Status:** live spec (v1, 2026-08-10). Implemented by `_system/scripts/graph_build.py`
(projection), `_system/scripts/graph_invariants.py` (health), and
`_system/scripts/resolve_falsifiers.py` (epistemic resolver). The latest health
report is committed at [`INVARIANTS.md`](INVARIANTS.md); the database itself is
derived and gitignored.

## Why a graph, and why this one

This repo runs two memory loops. The **procedural loop** (mistake → correction →
guard → CI enforcement) works but leaks: corrections stay prose, guards go
unwired — 17 of 27 validator scripts had zero CI references when audited on
2026-08-09. The **epistemic loop** (valuation → falsifier → outcome →
calibration → belief revision) has *never executed*: 157,320 claims emitted,
0 adjudicated; 833 contracts with monitoring blocks nothing reads; 568
falsifiers of which 545 are untestable prose; calibration stores that report
`insufficient_outcomes` since creation.

Every failure found in the 2026-08-09 audit shared one shape: **a link in one of
these chains was missing, and nothing could see that it was missing.** A
validator existed but nothing invoked it. A correction existed but no guard
enforced it. A falsifier existed but nothing could score it. The graph's job is
to make every such chain a *queryable path*, so a broken chain is a visible,
typed, countable defect instead of a silent gap.

Design sources: the commit-DAG/knowledge-graph split, the five-plane
separation, and the four provenance invariants follow the graph-engineering
synthesis (Karpathy autoresearch/AgentHub + Anthropic workflow/KG-cookbook
material, `investing-docs/Graph-Engineering-Athropic-Karpathy-Loop.pdf`).
The store design follows the filesystem-memory study
(`investing-docs/Filesystem-Based Memory for LLM Agents.pdf`): the filesystem
**is** the memory; the graph is a typed index over it, never a second source of
truth. Two of that paper's failure findings are already in our corrections log
as lived experience: reorganizing passes silently condense unless a
preservation rule is imposed (= the readiness-compiler clobber), and
management agents leave stale facts standing as live traits (= the SJT belief
frozen from May to August).

## First principles

1. **The graph is a projection, never a store.** `graph_build.py` rebuilds the
   whole graph deterministically from files already in the repo (contracts,
   ledgers, corrections, MEMORY.md, triage ledger, committee manifests, run
   receipts, CI workflow files, git lane history). It can be deleted and
   rebuilt at any time; it can therefore never drift from reality, and no
   agent ever "updates the graph" — agents update the repo, the graph follows.
2. **Preservation rule.** Nothing is deleted from memory surfaces; retirement
   is a `SUPERSEDES` edge and a status change, and every superseded object
   remains addressable. In-place rewrites of promoted beliefs are an invariant
   violation (E4), detected by diffing against git history.
3. **Provenance invariants** (adapted from the graph-engineering note): every
   claim node has a source edge or is marked inference; every artifact has an
   authoring run; every evaluation names its rubric; every superseded object
   stays addressable.
4. **Two planes, connected, never collapsed.** The *work* plane (lanes, runs,
   commits, waves) answers "what ran, what landed, what stalled." The
   *knowledge* plane (facts, beliefs, corrections, guards, falsifiers,
   outcomes) answers "what do we hold true, on what evidence, and has it been
   tested." Edges connect them (`PRODUCED_BY`, `LANDED_IN`) so any number on
   the dashboard traces to a run, a commit, a source, and an evaluation.
5. **Verbatim + distilled, linked.** Daily logs are the episode log; MEMORY.md
   is the curated store; `DISTILLED_FROM` edges tie each promoted belief to
   its proposals. The filesystem study shows strong consumers do better on
   verbatim logs and weak consumers on distilled guidance — we keep both and
   audit the link (that audit is what caught the LSEG misquote).
6. **Reports are the committed artifact.** The DB is derived; what lands in
   git is `INVARIANTS.md` — small, diffable, so the *trend* of every violation
   count is visible in git history. A ratchet needs a visible metric.

## Node types

| Plane | Node | Projected from |
|---|---|---|
| work | `Lane` | git log subjects per lane (`chore(ls-algo)`, `chore(valuation)`, backfill, committee, deploy, memory-digest, daily-sync) |
| work | `Run` | `_system/data/runs/*.json` receipts; workflow files |
| work | `Commit` | git log (lane-matched, bounded window) |
| work | `Wave` | `contract_backfill_queue.json` (tickers, dispatch_attempts, stall_breaker) |
| knowledge | `Ticker` | registry.json holdings |
| knowledge | `Contract` | `*/research/valuation_contract.json` (status, as_of) |
| knowledge | `Component` | `economic_ownership_map[]` entries |
| knowledge | `Fact` | `*/research/valuation_fact_ledger.json` locked rows (unit, fx_conversion, source) |
| knowledge | `Blocker` | contract `evidence.blockers[]` entries (BLOCKS edge to the Contract) |
| knowledge | `Falsifier` | component/monitoring falsifiers; typed when a `falsifier_spec` exists, prose otherwise |
| knowledge | `Outcome` | `_system/research/falsifier_outcomes.jsonl`; committee outcome records |
| knowledge | `Belief` | MEMORY.md bullets/table rows (lens, status, date, agent-marker) |
| knowledge | `Proposal` | daily-log `[PROPOSED*]` bullets + `triage_ledger.json` decisions |
| knowledge | `Correction` | corrections.md rows |
| knowledge | `Guard` | executable asserts registered in `graph_sources.json` **only** (deliberate: a correction's Source column cites evidence — scripts, filings, run ids — not asserts, so parsing it would fabricate guards that enforce nothing; a correction without a registry entry surfaces as a P1 violation instead) |
| knowledge | `Validator` | `_system/scripts/{scan,check,validate,audit,calibrate}_*.py` |
| knowledge | `CIJob` | `.github/workflows/*.yml` jobs that invoke a validator |
| knowledge | `Evaluation` | adjudications, calibration stores, Milly passes (rubric + verdict) |
| knowledge | `Source` | evidence files cited by facts/beliefs (existence-checked, not parsed) |

## Edge types

`GUARDED_BY` (Correction→Guard) · `ENFORCED_BY` (Guard→Validator) ·
`INVOKED_BY` (Validator→CIJob) — the procedural chain.
`ASSERTS` (Component→Falsifier) · `RESOLVED_BY` (Falsifier→Outcome) ·
`SCORES` (Outcome→calibration bucket: method_id × power_zone) — the epistemic
chain.
`SUPPORTED_BY` (Belief/Fact→Source) · `CONTRADICTS` (spec-reserved; no
projector yet — no repo surface records pairwise contradiction, see the
edge-type comment in `graph_build.py`) ·
`SUPERSEDES` (Belief→Belief, packet→packet, adjudication rev→rev) ·
`DISTILLED_FROM` (Belief→Proposal) · `DECIDED_AS` (Proposal→ledger decision) ·
`PRODUCED_BY` (artifact→Run) · `LANDED_IN` (Run→Commit) ·
`BLOCKS` (blocker→Contract) · `ABOUT` (anything→Ticker).

## Invariants — the executable health contract

Each invariant is a graph query with an ID, a severity, and an owner-action.
`graph_invariants.py` runs them all, writes `INVARIANTS.md` + JSON, and exits
non-zero on any **hard** violation. Report-only invariants are the ratchet
surface: their counts must be monotonically non-increasing across cycles.

**Procedural (self-healing):**
- **P1** (report): every `Correction` has a `GUARDED_BY` path. A correction row
  without a guard is a TODO wearing a correction's clothes.
- **P2** (hard): every `Guard` reaches a `CIJob` via `ENFORCED_BY→INVOKED_BY`.
  A guard invoked by nothing is the validator-orphan trap.
- **P3** (hard): every active `Lane` has a `Commit` younger than its freshness
  window (default 48h; per-lane overrides in `graph_sources.json`). Lane
  freshness, not run conclusions, is the health signal.
- **P4** (hard): no run receipts outside `_system/data/runs/`.
- **P5** (report): validator scripts with zero CI references (the 17-orphan
  finding, kept measured so it can only shrink).
- **P6** (hard): every data feed registered in `graph_sources.json`
  `data_feeds` carries a parseable freshness stamp younger than its window.
  Born from the risk page's committed components fallback silently freezing
  at 2026-08-02 while its workflow ran green hourly (D1-only publishes).
  Each violation names its healer; a stamp that cannot be parsed can never
  be judged fresh and is always a violation.
- **P7** (report): every *live* feed registered in `graph_sources.json`
  `live_feeds` — feeds published through the HMAC ingest rather than
  committed as files — has published inside its window. Born from the
  Databento flow monitor dying on 2026-08-03 on an uncaught `urlopen`
  timeout in its publish path: the flow rails, sector pressure/exhaustion
  columns and alert journal were empty for seven days and nothing said so.
  The evidence is the publisher's own log on the publishing host, so the
  skip rule differs from P6's and is deliberate: an evidence file that is
  **absent** is SKIPPED with a reason in the note (a CI checkout has no
  local monitor logs, and an invariant that reddens on every CI run is one
  everybody learns to ignore), while an evidence file that **exists** and is
  stale — or whose stamp cannot be parsed — is a violation. Report severity:
  a local feed being down must be loud without blocking a merge by someone
  who cannot see that host.

**Epistemic (self-compounding):**
- **E1** (report): decision-grade components carrying a *typed* falsifier
  (`metric, comparator, threshold, unit, due`). Coverage %, per method.
- **E2** (hard once >0 typed): every matured typed falsifier (due date past)
  has a `RESOLVED_BY` outcome within 14 days.
- **E3** (hard): every `Outcome` carries a `SCORES` edge and appears in the
  calibration store.
- **E4** (hard): no promoted `Belief` text rewritten in place (diff vs git
  HEAD~n; supersede edges only).
- **E5** (hard): every `Belief`'s `SUPPORTED_BY` source exists on disk.
- **E6** (report): `Proposal`s with no `DECIDED_AS` decision (silent-drop
  detector; the 1,014-item backlog class).

## The two ratchet loops

**Procedural ratchet** (runs in the architect cycle): build graph → run
invariants → pick the highest-severity violation class → close one link
(write the guard, wire the validator, fix the lane) → re-run → keep iff the
violation count fell. The INVARIANTS.md diff in the commit is the experiment
record.

**Epistemic ratchet** (runs on schedule): `resolve_falsifiers.py` finds typed
falsifiers whose `due` has passed, resolves the metric from companyfacts/the
fact ledger, writes an `Outcome` (hit/miss/unresolvable + evidence ref) to
`_system/research/falsifier_outcomes.jsonl`, and updates
`_system/research/falsifier_calibration.json` — descriptive buckets by
method_id × power_zone. **Weights never change automatically** (same rule as
committee calibration); calibration informs humans and prompts, not sizing.
Untestable prose falsifiers are visible as E1 coverage debt; new compiles
stamp `falsifier_spec_status` so the debt cannot silently grow.
Enforcement (typed-falsifier-required for decision_grade) stays OFF until
coverage crosses the threshold recorded in `graph_sources.json` — flipping 189
contracts to evidence_blocked overnight would freeze the factory, which is a
worse failure than the debt.

## Commands

```bash
python _system/scripts/graph_build.py            # rebuild _system/graph/graph.db (derived, gitignored)
python _system/scripts/graph_invariants.py       # health report -> INVARIANTS.md (+ exit 1 on hard violations)
python _system/scripts/graph_query.py <query>    # canned traversals: chain <correction-id> | lane-freshness | falsifier-coverage | belief <slug>
python _system/scripts/resolve_falsifiers.py     # score matured falsifiers -> outcomes + calibration
python _system/scripts/check_evidence_integrity.py   # V1-V7 evidence-chain sweep (ratchet, not the graph)
```

**Sibling sweep — `check_evidence_integrity.py`.** Not part of the graph (it
reads files directly, no projection), but the same idea one plane over: it
finds tickers whose *evidence* chain is broken while every individual artifact
reads healthy. The motivating case was WHK, whose contract said
`decision_grade` with zero blockers while its compiler stage said
`evidence_blocked` and its eight evidence tasks sat at `attempts: 0`. The
finding that generalised: `build_contract_backfill_queue.py`,
`build_evidence_recovery_queue.py` (default `all-blocked` scope) and the
committee trigger all skip `status == "decision_grade"`, so a contract that
reaches that status prematurely is treated as finished by every path that
could have finished it — 124 tickers, none of them in either queue. V6
overlaps E1 deliberately and at a different grain: E1 is the per-component
coverage ratchet, V6 the per-ticker triage list. Baseline lives in
`_system/data/evidence_integrity_baseline.json`; the sweep is report-severity
and fails CI only when a count rises.

CI: the invariant suite runs in the Research quality workflow (fail-loud on
hard invariants); the resolver runs weekly in the dedicated
`.github/workflows/falsifier-resolution.yml` workflow (Saturday 13:00 UTC).

## What this is not

Not a second memory (the filesystem is the memory). Not an embedding store
(deterministic projection only; the corpus is structured). Not an autonomous
weight-updater (calibration is descriptive; `human_decision.json` remains the
only capital authority). And not a place to write: agents change the repo; the
graph follows.
