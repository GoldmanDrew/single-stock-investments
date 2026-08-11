# Lens-plane invariants: human-gated follow-ups

**Status:** proposed (2026-08-11, architect cycle)
**Context:** The L-series invariants (L1–L6, `_system/graph/README.md`) now count the
classification/lens-plane defects that made the persona/consensus layer single-lens
in practice. The mechanical heals landed the same day (canonical `persona_groups.py`,
layered classification read + contract-return fallback in `persona_lens_common.py`,
lens regeneration wired into the power-zone-universe lane, WHK reclassified
optionality/asset, all 721 lenses regenerated, ratchet baseline armed). The items
below change judgment, not plumbing, and belong to the human.

## 1. Re-seat the 23 collided committees — **DONE 2026-08-11** (L6 23 → 0)

31 of 76 manifests seated `[buffett_weschler, hohn, munger]` — two
`quality_reinvestment` seats under the canonical map; 23 were active, including
**8697.T at `committee_complete_decision_pending`** (a decision about to be made on
a non-independent committee) and 21 `round_one_open` (ADBE, AMZN, GOOGL, SPGI, CSU,
ICE, FRMO, …). Future seatings were already fixed by the shared GROUPS import.

Resolved by owner direction (skip the 8697.T human decision; re-seat rather than
park) via `_system/scripts/reseat_collided_committees.py --apply`. All 23 re-seated
to `marathon_capital_cycle` in the third seat — route-driven, not hand-picked: every
one routes to `quality_reinvestment`, whose cross-checks are
`[munger, marathon_capital_cycle]`, and munger now shares buffett's group. Zero
unfixable.

Preservation, verified after the run: **145/145 vote files byte-identical, none
deleted** (the 7 munger votes across 7176.T, 8697.T, ADBE, AMZN survive as orphans —
real opinions that no longer count toward a quorum they never legitimately formed);
the 3 assembled records built on the old seating renamed to
`committee_<date>-superseded-<hash8>.json`, which breaks the reader glob while
staying on disk; the frozen packet and its hash untouched, so the surviving raters'
votes stay valid. 8697.T reverted `committee_complete_decision_pending` →
`round_one_open` with **no `human_decision.json` written** — the pending decision is
skipped, not recorded.

**Open follow-up (lane work, not a gate):** all 23 now need round-one votes from the
newly seated rater; the committee lane dispatches them. `marathon_capital_cycle` is
outside its power zone on several of these compounders and may legitimately vote
`outside_power_zone` — that is an honest committee output, not a failure.

## 2. Independence-group split for hk vs stahl (scarce-asset names)

`GROUPS` puts hk and stahl both in `scarce_assets`, so a scarce-asset name seats at
most one specialist and the committee is structurally 1 specialist + 2 conservatives.
Options: (a) split into `scarce_assets_royalty` (hk) vs `scarce_assets_duration`
(stahl); (b) relax seatability to "3 groups OR 2 specialists + 1 independent when the
power zone is their specialty". (a) is mechanical once approved; (b) changes
`validate_work`. Either way L6 keeps counting quorum under whatever map is canonical.

## 3. Widen buffett_weschler and marathon lenses to match their zones (L4 = 2)

The narrower-than-zone check (stahl's bug class) also caught:
- `buffett_weschler` lens archetypes miss `holding_co`, `infrastructure` (zone routes them)
- `marathon_capital_cycle` lens misses `turnaround`

The stahl fix (add `optionality`) was applied because last cycle's review endorsed it;
these two are the same defect but change scoring for many tickers — approve/decline
per persona.

## 4. Vocabulary reconciliation (L4 = 29 criteria/data values)

Non-canonical criteria values (`bank`, `insurer`, `special_situation`,
`commodity_cyclical`, `cyclical`, `biotech`, `regulated_utility`, `utility`,
`mature_cash_generator`, `pre_profit`, `exploration`, `leveraged_equity`) can match
nothing the taxonomy emits. Decide per value: promote into
`classification.md` + `classification_vocab` (bank/insurer/utility arguably deserve
canon status) or rewrite the criteria to canonical values. Data-side drift
(`narrow`, `durable`, `partial` moats; `cyclical`/`capital_cycle`/`resource`/`biotech`
archetypes; `earnings` payoff_lens — 44 tickers) needs a mapping decision
(e.g. `narrow` → `stable`? `capital_cycle` → `turnaround`?) before a backfill pass.

## 5. Classification backfill for the 540 unresolved tickers (L1 = 540)

Mechanical seed exists: `valuation_method_route.profile_id` strongly implies
payoff_lens (`scarce_asset_optionality` → asset, `catalyst_asset_value` → event,
`credit_and_normalized_returns` → levered, else operating). Proposal: batch-write
`classification_inputs.payoff_lens` from the route with `method_source:
route_seeded`, queue exceptions for review. This moves the L1 ratchet in bulk;
wants sign-off because it stamps a classification field 500+ times.

## 6. Per-persona independent valuation functions (the real fix)

Every `persona_return` today transforms the compiler's base/bear/bull. The blend can
therefore never disagree with the compiler by more than a nudge — the WHK
depleting-vs-perpetual spread ($8.76 contract vs ~$24 cap-rate view) is
unexpressible. Design: each primary persona gets a valuation model over the same
frozen contract inputs (stahl: cap-rate on the royalty stream with a duration
schedule; klarman: NAV − realization discount; marks: stressed equity; hohn/buffett:
the operating DCF = today's compiler), `valuation_blend` blends genuinely
independent estimates, and the spread surfaces as dissent. The contract-return
fallback added today is the first step (personas can now *read* contract-first
valuations); this item makes them *produce* values. Biggest change in this list —
wants a design review before code.

## 7. Registry vs classification_inputs precedence + remaining L2 conflicts (L2 = 7)

ICE, MSB, PCH, SJT, SPGI, TEQ.ST, VTRS carry conflicting archetype/payoff_lens/dhando
across surfaces. Each needs a one-line adjudication (which surface is right), then
the mirrors sync. Also decide whether the persona layer's precedence (top-level →
classification_inputs → registry) should flip to contract-first once item 6 lands.

## 8. Arm the ratchet for P/E-series report invariants

The baseline ratchet currently arms only L1–L6. Arming P1/P5 (guards and validator
orphans) would make "counts must not grow" real for the procedural plane too, at the
cost of merge friction when someone adds a validator without CI wiring. E1/E6 grow
organically and should stay unarmed.

## 9. SPA consensus honesty (found by recon, not yet coded)

`dashboard/index.html` (the active-lens chip mount, `t.lenses.active` /
`t.lenses.silent_count`) reads fields the builder never writes (all lens rows render
silent personas as active chips, the "+N silent" chip never renders);
`insights-viz.js` `renderConsensusDetail` renders the stance badge regardless of
contributor count; `build_decision_summary` drops `contributor_count` and
`low_coverage`; WHK's `decision_summary.stance` is an object, not a string.
Small fixes, user-facing — separate reviewed change.
