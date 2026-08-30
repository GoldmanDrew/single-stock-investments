# Valuation universe tiers

The valuation universe has three research-priority tiers. The tier decides how
much underwriting work the system should do and whether it may open a committee
workflow. It never grants permission to trade. Capital authority still comes
only from a valid `{TICKER}/research/human_decision.json`.

## The three tiers

| Tier | Purpose | Required treatment | Automated committee start |
|---|---|---|---|
| **Tier 1** | Active holdings and imminent decisions | Current, stock-specific model; fresh evidence; reverse expectations; committee/human review | Allowed only when `decision.model_level` is `stock_specific`, `committee_reviewed`, or `owner_approved` |
| **Tier 2** | Priority watchlist | Correct route, economic ownership map, screening valuation, explicit promotion gates | Blocked |
| **Tier 3** | Broad research universe | Honest screening only | Blocked |

Every tier has an actionability cap of `human_decision_only`. A contract grade,
price signal, implied return, or other automated output cannot promote a ticker
and cannot authorize capital.

## Canonical artifacts

- Policy and owner overrides:
  `_system/portfolio/valuation_universe_policy.json`
- Deterministic generator:
  `_system/scripts/build_valuation_universe_tiers.py`
- Generated manifest:
  `_system/data/valuation_universe_tiers.json`
- Pipeline integration:
  `_system/scripts/run_security_decision_pipeline.py`

The generated manifest assigns every registry ticker exactly once. Each row
contains the tier, human-readable label, source-linked assignment reasons,
promotion gates, demotion conditions, research depth, and workflow/actionability
limits. The summary reports counts by tier and by assignment reason.

## Assignment precedence

1. A valid owner override in `valuation_universe_policy.json` sets the research
   tier. It does not change capital authority or bypass the model-level gate.
2. Tier 1 is assigned from explicit high-priority evidence:
   - positive positions in `_system/portfolio/paper/taxable.json` or
     `_system/portfolio/paper/roth.json`;
   - an active committee status in the valuation workbench;
   - an open `committee_trigger.json`;
   - a current or expired `human_decision.json`; or
   - a positive weight in a human-approved capital plan.
3. Tier 2 is assigned from explicit watchlist evidence:
   - registry `watchlist` membership;
   - membership in `valuation_followups.json`;
   - a `core`, `hold`, or `accumulate` classification stance; or
   - a positive weight in a proposed target-weight plan.
4. All other registry names default to Tier 3.

The registry's `holdings` object contains the full research universe. It is not
evidence of an active position and is deliberately ignored for Tier 1.

## Promotion and demotion

Tier 3 moves to Tier 2 only after an explicit curated-priority signal. It moves
directly to Tier 1 only after a positive canonical position, an imminent decision
workflow, a human capital decision, or an approved capital plan.

Tier 2 moves to Tier 1 through the same Tier 1 gates. Removing its watchlist,
follow-up, stance, and proposed-plan signals demotes it to Tier 3 if no Tier 1
gate exists.

Tier 1 demotes only after all positive positions, active decision workflows,
human-decision review obligations, and approved-plan signals are gone. The
generator then re-evaluates Tier 2 signals before using the Tier 3 default.

Owner overrides provide an explicit, reviewable exception mechanism without a
code change. Each override requires a ticker, tier, and rationale; `review_by`
is optional.

## Fail-closed behavior

- Missing or invalid canonical position inputs are reported as source errors;
  they never cause a name to be inferred as held.
- Unmatched source tickers are listed rather than silently mapped to a different
  security.
- A missing tier assignment is treated as Tier 3 by the committee gate.
- Tier 2 and Tier 3 cannot auto-start a committee, even if a raw contract says
  `decision_grade` or a price crosses a hurdle.
- Tier 1 still cannot enter committee with `screening_grade`, `evidence_blocked`,
  or missing model-level evidence.
- The existing decision-authority resolver remains the final guard: only a
  human decision is actionable.

## Commands

Generate the canonical artifact:

```text
python _system/scripts/build_valuation_universe_tiers.py
```

Validate that the committed artifact exactly matches current inputs:

```text
python _system/scripts/build_valuation_universe_tiers.py --check --strict-sources
```

The Power Zone Universe workflow runs the generator through the security
decision pipeline, validates it, and commits the manifest with the other
valuation authority artifacts.
