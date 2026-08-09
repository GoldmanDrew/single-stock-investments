# Pending review queues

Human review artifacts land here when auto-triage cannot resolve a row.

**Start at `_system/reviews/QUEUE.md`**, not at this directory listing. It is rebuilt by
`_system/scripts/build_review_queue_rollup.py` (machine-readable twin:
`_system/data/review_queue_rollup.json`) and shows only what actually needs a verdict,
oldest first.

```
python _system/scripts/build_review_queue_rollup.py                    # report only
python _system/scripts/build_review_queue_rollup.py --expire --close-onboard
python _system/scripts/build_review_queue_rollup.py --reverify-closed  # re-test old closures
```

## Where things go

| Directory | Meaning |
|-----------|---------|
| `pending/` | Awaiting a human verdict. |
| `approved/` | The human read it and accepted it. Move files here by hand. |
| `expired/<type>/` | Dated ephemera whose review value has passed. **Moved, never deleted** — the history is intact, and `build_index_membership.py` still harvests `expired/portfolio_news/`. Ledger: `expired/_expiry_ledger.json`. |
| `auto_closed/` | Onboard checklists that cleared every registry check — presence and cross-source agreement, **not** correctness (see below). Ledger: `auto_closed/_autoclose_ledger.json` records which checks passed for each. The ledger is **append-only**: `--reverify-closed` re-runs the current gate over this directory, moves failures back to `pending/` and appends an `"action": "reopened"` row rather than editing the original close. |

## Expiry policy

Only types marked `superseded_snapshot` or `machine_receipt` expire. A file expires when
**all three** hold, so nothing unique is ever retired:

1. a **strictly newer file of the same type exists** (the newer one restates its content),
2. it is older than the type's cutoff, and
3. it is not one of the `keep_latest` most recent files of that type.

Anything a person must decide (`human_verdict`) never expires, no matter how old.

## Every filename pattern present

### Needs a human verdict — never auto-expires

| Pattern | Source | What it requires |
|---------|--------|------------------|
| `{TICKER}_deep_dive_{date}.md` | deep dive Cloud Agent | Read the dive, set stance/archetype, move to `approved/`. |
| `{TICKER}_cross_check_{CC}_{date}.md` | cross-check pass | Adjudicate source disagreements before the valuation is trusted. |
| `world_model_review_{TICKER}_{date}.md` | `apply_world_model_context.py`, `check_kpi_ledger.py --queue-reviews` | Confirm or reject the proposed world-model / KPI context change. |
| `memory_digest_{date}.md` | `build_memory_digest.py` | Promote bullets into `MEMORY.md`, log rejections in `corrections.md`. Windows are weekly and **non-overlapping**, so an unreviewed week is never restated — this is why it does not expire. |
| `cvr_discovery_{date}.md` | `refresh_cvr_universe.py` | Confirm newly discovered CVRs before they enter the universe. |
| `deep_dive_depth_scorecard_{date}.csv` | deep dive quality pass | Decide which thin dives get re-run. |
| `{otc_sleeve,fund_nav_discounts}_onboard_{date}.md` | one-off sleeve build-out | Approve or reject the proposed sleeve additions. |
| `{slug}_{plan,roadmap,upgrade,suggestions}[_{date}].md` | one-off agent proposals | Accept, amend or reject a change of process. |
| `{slug}_{date}.{md,csv,json}` | ad hoc | One-off analysis or audit: read once and file. |
| `{slug}.{md,csv,json}` (undated) | ad hoc | Standing working document; no cadence, the human moves it out. |

### Onboard checklists

| Pattern | Source | What it requires |
|---------|--------|------------------|
| `{TICKER}_onboard_{date}.md` | onboarding pipeline | Only the items the auto-close pass could **not** verify. |

Its `[HUMAN REVIEW]` block has three lines, all three checked by `--close-onboard`:

- *Verify CIK and IR URLs in registry* — US: the registry CIK must be present and, when
  the ticker also appears in `_system/scripts/us_ticker_config.json`, the two must agree
  after zero-padding (that file is read **first** by the downloader and shadows the
  registry, so a null there blocks the close). Non-US: a download route must be set.
  At least one `ir_roots` entry must exist and all must be well-formed http(s) URLs —
  an empty list asserts nothing, so it is a blocker (`ir_roots_missing`), not a pass.
- *Confirm classification defaults* — every non-sleeve key of `DEFAULT_CLASSIFICATION`
  (`archetype`, `moat`, `dhando`, `stance`, `cycle`, `moi_bucket`, `payoff_lens`) must be
  **off** the value `onboard_ticker.py` wrote (`unknown` / `unproven` / `pending` /
  `watch` / `-` / `pending` / `pending`), plus a real sleeve (`-` is the no-sleeve
  sentinel, not an assignment; the fallback to a top-level `investment_sleeve` is taken
  when the classification value is that sentinel). The field list is **derived** from
  `DEFAULT_CLASSIFICATION` rather than hand-written — a hand-written list covered only
  five of the seven, so `moi_bucket` and `payoff_lens` went untested and a checklist
  could close with both still at their default. Every default is a truthy string, so
  testing truthiness here confirms nothing; the line asks a human to *confirm* them.
- *Review deep dive PR when Cloud Agent completes* — waived **only when a dive actually
  exists** for the ticker (`{TICKER}/research/deep_dive_{date}.md`, or a
  `{TICKER}_deep_dive_{date}.md` under any `reviews/` subdirectory). It used to be waived
  unconditionally on the argument that the dive arrives as its own review item; ~797 of
  the 802 onboarded tickers with an open checklist had no dive anywhere, so the item was
  discharged by argument rather than by an artifact. With no dive on disk it is now the
  `deep_dive_absent` blocker.

### What the close does and does not establish

The gate checks that values are **present, well formed and consistent across sources**.
It does not check that they are **right**. A CIK carried identically in `registry.json`
and `us_ticker_config.json` passes even when it belongs to a different issuer, and an
`ir_roots` entry passes on URL shape alone — nothing fetches it or ties it back to the
company. Read an auto-close as *"internally consistent and off its defaults"*, never as
*"verified"*. Wrong-but-present data is exactly what this gate cannot see.

A checklist auto-closes only on **positive evidence**: every applicable check passes, and
missing or default data never counts as a pass. Everything else stays in `pending/` with
its blocker named in `QUEUE.md`. Because the blockers are shared, `QUEUE.md` groups the
open checklists by blocker class with the single registry edit that clears the class —
work the classes top-down instead of opening 800 files.

### Superseded snapshots — auto-expiring

Each is a **full restatement** of current state; the newest file dominates the older ones.

| Pattern | Source | Cutoff | Keep latest |
|---------|--------|--------|-------------|
| `news_{date}.md` | `ingest_portfolio_news.py` | 30d | 3 |
| `event_triage_{date}.md` | `event_triage.py` | 30d | 2 |
| `filing_insights_{date}.md` | `auto_resolve_filing_events.py` | 30d | 2 |
| `activist_triage_{date}.md` | `activist_triage.py` | 30d | 2 |
| `activist_press_digest_{date}.md` | activist press seed harvester | 30d | 2 |
| `fund_family_proposals_{date}.md` | `fund_families.py` | 21d | 2 |
| `darwin_regime_brief_{date}.md` | `_system/scripts/darwin/observatory.py` | 14d | 2 |
| `transcript_coverage_{date}.md` | `transcript_gap_report.py` | 14d | 2 |
| `ls_algo_ic_queue_{date}.md` | ls-algo committee pass | 14d | 2 |

Cutoffs, and why:

- **14d** for snapshots of *current* state (regime label, live price triggers, coverage
  counts). A stale copy is not merely redundant, it is wrong.
- **21d** for `fund_family_proposals`: re-detected from scratch each run, so an
  unpromoted proposal reappears in the newer file; three weeks is a generous grace period.
- **30d** for tables and digests over a rolling or cumulative window. `news_{date}.md`
  covers a rolling 30-day feed, so at 30 days a newer digest covers the same ground;
  `event_triage` / `filing_insights` restate every unresolved row daily; `activist_triage`
  only grows, so the newest table strictly contains the older ones.

### Machine receipts — auto-expiring

| Pattern | Source | Cutoff | Keep latest |
|---------|--------|--------|-------------|
| `batch_onboard_{date}.md` | `bulk_sp500_onboard.py` | 30d | 2 |
| `{slug}_dispatch_{date}.md` | batch dispatch scripts | 30d | 2 |

They record that a batch ran. The reviewable content is in the per-ticker artifacts.

### Obsolete

| Pattern | Status |
|---------|--------|
| `activist_scan_{date}.md` | **Obsolete** — delete if found; replaced by the triage queue. `validate_dashboard_data.py` warns on these. |

Machine run-receipts belong in `_system/data/runs/`, not here. Portfolio scan summaries
(not review queues) live in `_system/research/activist_scan_{date}.md`.

## Adding a new pattern

Add a `QueueType` to `QUEUE_TYPES` in `_system/scripts/build_review_queue_rollup.py` and a
case to `test_build_review_queue_rollup.py`. Anything unmatched is reported as
`unclassified` and treated as needing a human verdict, so the queue fails safe.
