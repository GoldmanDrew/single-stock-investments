# Human review queue

Generated 2026-08-09T23:16:09Z by `_system/scripts/build_review_queue_rollup.py`.
Pending files: **1008** · needing a human verdict: **886** · approved/: 26 · expired/: 109 · auto_closed/: 0

## Needs a human verdict

| Type | Count | Oldest | Max age (d) | What it asks of you |
|------|-------|--------|-------------|---------------------|
| Deep dive | 44 | 2026-05-21 | 80 | Read the dive, set stance/archetype, then move to approved/. Never auto-expires. |
| Plan / proposal | 12 | 2026-06-01 | 69 | Accept, amend or reject the proposed change of process. |
| One-off analysis / audit | 8 | 2026-06-01 | 69 | Read once and file; these were written for a specific question. |
| Cross-check report | 4 | 2026-06-01 | 69 | Adjudicate the disagreements between sources before the valuation is trusted. |
| World-model review | 4 | 2026-07-23 | 17 | Confirm or reject the proposed world-model / KPI context change. |
| Weekly memory digest | 3 | 2026-07-26 | 14 | Promote approved bullets into MEMORY.md, log rejections in corrections.md. |
| Sleeve onboard proposal | 2 | 2026-07-17 | 23 | Approve or reject the proposed sleeve additions, then move to approved/. |
| CVR discovery | 1 | 2026-07-23 | 17 | Confirm newly discovered CVRs before they enter the universe. |
| Deep dive depth scorecard | 1 | 2026-06-04 | 66 | Decide which thin dives get re-run. |
| Standing working document | 2 | - | - | No date, no cadence: the human moves it out when it stops being useful. |

## Onboard checklists

- In pending: **805**
- Closable by the registry gate now: **0**
- Blocked on something the gate cannot check: **805**
- Already auto-closed to `_system/reviews/auto_closed/`: 0

A checklist closes only on positive evidence. A registry field still at its
onboarding default (`unknown`, `unproven`, `pending`, `watch`, `-`), an unassigned
sleeve, an empty `ir_roots` or a deep dive that was never produced is a blocker,
not a pass.

**What the gate does and does not establish.** It checks that values are present,
well formed and agree across sources - not that they are correct. A CIK that is
present in both `registry.json` and `us_ticker_config.json` and identical in both
still passes when it belongs to a different issuer, and an `ir_roots` URL passes on
shape alone; nothing here fetches it or ties it to the company. Read an auto-close
as "internally consistent and off its defaults", not as "verified".

### Fix by class, not by file

Each row is one kind of missing registry data. Fixing the class clears every
checklist counted in it, so work top-down rather than file-by-file.

| Blocker | Checklists | One fix clears them all | Example tickers |
|---------|-----------|-------------------------|-----------------|
| `classification_unconfirmed` | 805 | The named fields are still at the onboarding defaults (archetype='unknown', moat='unproven', dhando='pending', stance='watch', cycle='-', moi_bucket='pending', payoff_lens='pending'). The checklist asks a human to confirm them, so a default cannot count as confirmed. | `0388.HK`, `7176.T`, `9984.T`, `A`, `AAL`, `AAOI`, `AAPL`, `ABMD.CVR` +797 more |
| `ir_roots_missing` | 670 | Add at least one investor-relations root URL to holdings.<T>.download.ir_roots. An empty list is not a verified IR URL. | `A`, `AAL`, `AAPL`, `ABMD.CVR`, `ABNB`, `ABT`, `ACGL`, `ACHR` +662 more |
| `deep_dive_absent` | 620 | The checklist's 'review deep dive PR when Cloud Agent completes' line is only waivable once the dive exists. Run the deep dive (or drop the ticker) so that a {TICKER}/research/deep_dive_{date}.md or a {TICKER}_deep_dive_{date}.md review artifact is on disk. | `ABMD.CVR`, `AMGN`, `AMKR`, `AMPX`, `AMR`, `AMT`, `ANET`, `AON` +612 more |
| `sleeve_unassigned` | 378 | Assign holdings.<T>.classification.investment_sleeve; '-' is the no-sleeve sentinel, not a sleeve. | `9984.T`, `AMR`, `ASPN`, `AXON`, `B`, `BEN`, `BRBR`, `C` +370 more |
| `company_name_placeholder` | 172 | holdings.<T>.company is still the bare symbol; set the real legal name. | `AAL`, `ACHR`, `ACLS`, `ACMR`, `AEHR`, `AFRM`, `AI`, `ALAB` +164 more |
| `cik_missing_in_registry` | 41 | Set holdings.<T>.download.cik from SEC EDGAR, and add the same CIK to _system/scripts/us_ticker_config.json (it is read first and shadows the registry). | `ABMD.CVR`, `ABX`, `ARKK`, `ASHR`, `AZLCZ`, `BWEL`, `CHNL`, `CMSG` +33 more |

`classification_unconfirmed` by field set:

- `archetype,moat,dhando,stance,cycle,moi_bucket,payoff_lens` - 770
- `moat,stance,moi_bucket` - 9
- `moat,dhando,stance,cycle,moi_bucket` - 8
- `stance` - 4
- `stance,moi_bucket` - 4
- `moat,dhando,stance,cycle,moi_bucket,payoff_lens` - 3
- `moat,stance,cycle,moi_bucket,payoff_lens` - 3
- `moat,stance,cycle,moi_bucket` - 2
- `moat,cycle,moi_bucket,payoff_lens` - 1
- `moat,stance,moi_bucket,payoff_lens` - 1

## Superseded snapshots and receipts (auto-expiring)

| Type | Count | Cutoff (d) | Keep latest | Expiring now | Why it expires |
|------|-------|-----------|-------------|--------------|----------------|
| Portfolio news scan | 23 | 30 | 3 | 0 | Digest of a rolling 30-day feed window; at 30 days a newer digest covers the same window. |
| Event triage table | 18 | 30 | 2 | 0 | Full daily restatement of every unresolved row; still-open rows carry forward. |
| Activist triage table | 17 | 30 | 2 | 0 | Cumulative: row count only grows, so the newest table strictly contains the older ones. |
| Filing insights table | 17 | 30 | 2 | 0 | Full daily restatement of unresolved parser rows. |
| Fund family proposals | 11 | 21 | 2 | 0 | Re-detected from scratch each run; unpromoted proposals reappear in the newer file. |
| Activist press digest | 10 | 30 | 2 | 0 | Restated from a fixed seed list each run; nothing is unique to an old copy. |
| Darwin regime brief | 10 | 14 | 2 | 0 | States the CURRENT regime. A stale regime label is not reviewable, it is wrong. |
| ls-algo IC queue | 10 | 14 | 2 | 0 | Snapshot of live triggers at that day's prices; a stale trigger list is misleading. |
| Agent dispatch receipt | 2 | 30 | 2 | 0 | Records that jobs were dispatched; carries no verdict. |
| Batch onboard receipt | 2 | 30 | 2 | 0 | Run receipt for a batch whose per-ticker artifacts are queued separately. |
| Transcript coverage report | 2 | 14 | 2 | 0 | Restates coverage for all holdings every run; the newest file dominates. |

## Oldest items awaiting a verdict

- `3905.T_deep_dive_2026-05-21.md` — 80d (deep_dive)
- `AMZN_deep_dive_2026-05-21.md` — 80d (deep_dive)
- `APLD_deep_dive_2026-05-21.md` — 80d (deep_dive)
- `BN_deep_dive_2026-05-21.md` — 80d (deep_dive)
- `CPRT_deep_dive_2026-05-21.md` — 80d (deep_dive)
- `CSGP_deep_dive_2026-05-21.md` — 80d (deep_dive)
- `CSU_deep_dive_2026-05-21.md` — 80d (deep_dive)
- `DHR_deep_dive_2026-05-21.md` — 80d (deep_dive)
- `FRMO_deep_dive_2026-05-21.md` — 80d (deep_dive)
- `GOOGL_deep_dive_2026-05-21.md` — 80d (deep_dive)
- `ICE_deep_dive_2026-05-21.md` — 80d (deep_dive)
- `KEWL_deep_dive_2026-05-21.md` — 80d (deep_dive)
- `OTCM_deep_dive_2026-05-21.md` — 80d (deep_dive)
- `QDEL_deep_dive_2026-05-21.md` — 80d (deep_dive)
- `SJT_deep_dive_2026-05-21.md` — 80d (deep_dive)
- `SPGI_deep_dive_2026-05-21.md` — 80d (deep_dive)
- `TEQ.ST_deep_dive_2026-05-21.md` — 80d (deep_dive)
- `WBI_deep_dive_2026-05-21.md` — 80d (deep_dive)
- `ICE_deep_dive_2026-05-22.md` — 79d (deep_dive)
- `3905.T_deep_dive_2026-05-23.md` — 78d (deep_dive)
- `MSB_deep_dive_2026-05-25.md` — 76d (deep_dive)
- `3905.T_deep_dive_2026-05-26.md` — 75d (deep_dive)
- `8697.T_deep_dive_2026-05-26.md` — 75d (deep_dive)
- `AMZN_deep_dive_2026-05-26.md` — 75d (deep_dive)
- `APLD_deep_dive_2026-05-26.md` — 75d (deep_dive)
