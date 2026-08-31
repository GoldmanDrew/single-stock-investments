# Valuation Contract v3 and universe tiers

## End goal

This repository should become an auditable single-stock valuation compiler and
research operating system. It should never make a rough automated screen look
like completed underwriting, never manufacture a forward return from an
intrinsic value, and never treat the full research registry as if every name
were an owned position.

The target chain is:

```text
source-locked facts
  → routed, versioned method
  → deterministic component proof
  → explicit output basis
  → intrinsic value + margin of safety + optional genuine forward return
  → honest model maturity
  → Tier 1/2/3 research workflow
  → independent committee review
  → human capital decision
```

The first focus is semantic trustworthiness. Better company-specific forecasts
matter only after the system can state clearly what a number means, how mature
the model is, and whether it is allowed to influence a decision.

## Phase 1: Contract v3 valuation semantics

### 1. Separate value today from future return

Every approved method card and completed proof declares one output basis:

| Output basis | What the proof produced | Value shown today | Forward return | Hurdle price |
|--------------|-------------------------|-------------------|----------------|--------------|
| `present_value_today` | An intrinsic value already discounted to today | Proof low/base/high | Unavailable | Unavailable |
| `future_payoff` | A payoff at an explicit date or horizon | Payoff discounted at the required return | Annualized payoff/price return | Payoff discounted at the hurdle |
| `forward_cashflow_schedule` | Dated per-share cash flows | Schedule NPV at the required return | Unique cash-flow IRR using the stated timing | Schedule NPV at the hurdle |

Contract v3 publishes separate canonical fields for:

- `present_value_today_per_share`;
- `margin_of_safety_pct`, defined as `(value - price) / value`;
- `forward_return_at_price_pct`, only when dated forward economics make it computable;
- `required_return_pct`;
- the payoff date/horizon or the full forward cash-flow schedule;
- model, fact, and price dates.

The former calculation that annualized a present value relative to market price
is retained only in `legacy_audit`. It cannot be used for ranking, hurdle entry
prices, committee triggers, dashboard returns, or capital decisions.

### 2. Separate proof completeness from model maturity

`decision_grade` answers a narrow technical question: is the calculation
reproducible, source-traceable, complete, and free of open blockers? It does not
by itself mean that the assumptions constitute company-specific underwriting.

The model-level ladder is:

1. `unmodeled`: no complete economic ownership model;
2. `evidence_blocked`: required evidence, calculations, or component coverage is open;
3. `screening_grade`: useful for triage, but based on generic or first-pass assumptions;
4. `stock_specific`: proof-complete components and assumptions tailored to the security;
5. `committee_reviewed`: an eligible stock-specific model has completed independent review;
6. `owner_approved`: the owner has made the explicit decision.

A generic source-locked owner-earnings template can be proof-complete while its
model level remains `screening_grade`. That is intentional. It may guide the
research queue but cannot enter committee review or authorize capital.

### 3. Dashboard publishing rule

For every security the dashboard should show:

- universe tier and model level first;
- contract proof status and any blocking reason;
- market price, base intrinsic value today, and margin of safety;
- a forward return only when the contract has dated economics and the maturity
  policy permits publication;
- required return, output basis, and as-of dates;
- a clear “not modeled” or “withheld” state instead of a legacy fallback.

No consumer may substitute the Lawrence/Marvin implied return, an old
classification IRR, or the legacy present-value gap when Contract v3 withholds a
forward return.

## Phase 2: Tier 1/2/3 valuation universe

Model quality and research priority are different axes. A security can be Tier
1 and still be evidence-blocked; it can also have a stock-specific model while
remaining Tier 2. Tier assignment controls attention and automation, not truth.

### Tier 1: active capital and imminent decisions

Default qualifying signals include a positive live portfolio position, active
committee work, or an explicit current human decision/override. Tier 1 receives:

- current primary evidence and price dates;
- a complete stock-specific component model;
- explicit falsifiers and refresh triggers;
- committee admission only after proof status and model maturity both pass.

### Tier 2: curated research candidates

Default qualifying signals include the intentional watchlist, a named valuation
follow-up cohort, or a proposed but not approved portfolio target. Tier 2 receives:

- route and classification confirmation;
- a typed evidence plan and focused missing-fact collection;
- screening or stock-specific work proportional to the live research question;
- no automatic committee start.

### Tier 3: broad screening universe

All remaining registry names default to Tier 3. Tier 3 receives deterministic
screening, source/freshness checks, and promotion signals. It does not receive
automatic committee work, and an automated model can never authorize capital.

### Promotion and demotion controls

Every assignment should include its machine-readable reasons, promotion gates,
demotion conditions, workflow policy, and any time-bounded owner override.
Examples:

- Tier 3 → Tier 2: explicit follow-up, intentional watchlist admission, or a
  documented research catalyst;
- Tier 2 → Tier 1: positive position, approved near-term decision workflow, or
  explicit owner promotion;
- Tier 1 → Tier 2/3: position closed, committee work resolved, decision expired,
  or an override reaches its review date.

A high modeled upside, a legacy IRR, or `decision_grade` status alone is never a
promotion signal.

## Implementation status: 2026-08-30

Phases 1 and 2, including the repository-wide migration, are implemented:

- all 834 securities have Contract v3 and Workbench v3 artifacts;
- all 224 existing pricing artifacts use v3 semantics and withhold hurdle
  prices when proof is blocked or the model output is already a present value;
- the governed universe contains 40 Tier 1, 12 Tier 2, and 782 Tier 3 names;
- the dashboard boot payload contains all 834 tier/model assignments and stays
  below its 6 MB release budget;
- every current production valuation outputs `present_value_today`, so the
  dashboard honestly publishes zero forward returns. The old implied returns
  remain audit-only and cannot leak into ranking or decisions.

Tier 1 currently contains 11 stock-specific models, 8 screening-grade models,
and 21 evidence-blocked models. That distribution defines the operating queue;
a Tier 1 label does not conceal unfinished underwriting.

The Tier 1 readiness compiler now turns those 40 assignments into one governed
work order. It prioritizes critical and open evidence gaps, proof completion,
company-specific model depth, input freshness, falsifier coverage, independent
committee work, and finally the owner decision. The generated queue is stored
at `_system/data/tier1_decision_readiness.json`, is rebuilt by the security
decision pipeline, and is displayed in the dashboard Decision Queue. It orders
work only: it cannot clear a blocker, upgrade a model, start a committee, or
authorize capital.

## Overall repository plan

Phases 1 and 2 establish the contract and workflow boundary and their migration
is complete. The next plan is model depth and operating hardening:

1. **Deepen Tier 1 models.** Work the governed Tier 1 queue from top to bottom,
   replacing generic screens with company-specific segment economics,
   reinvestment logic, capital structure, dilution, event timing, and explicit
   falsifiers.
2. **Add genuine forward economics where the thesis requires them.** Use dated
   per-share payoffs or cash-flow schedules so CAGR/IRR and hurdle prices are
   calculated from actual future economics, never reverse-engineered from PV.
3. **Build the Tier 2 promotion funnel.** Measure evidence gaps, expected decision
   relevance, and research cost so work advances deliberately.
4. **Calibrate without self-modifying formulas.** Compare forecast assumptions
   with realized outcomes by method and archetype; use the evidence to revise
   governed method versions through review.
5. **Retire legacy consumers.** Remove old return fields only after every reader,
   export, and dashboard surface uses Contract v3 and retained history is safe.

## Release gates

The implementation is complete only when all of the following are verified:

- every approved method card declares a valid output basis;
- a present-value contract publishes no forward return or hurdle entry price;
- dated payoff and schedule fixtures reproduce correct PV, CAGR/IRR, and hurdle NPV;
- true extreme forward returns require independent, source-backed validation;
- generic first-pass models are labeled `screening_grade` and are not committee-eligible;
- every registry security has exactly one auditable tier assignment;
- Tier 2 and Tier 3 cannot auto-start committee work;
- dashboard and D1 consumers publish only canonical Contract v3 fields;
- generated artifacts pass schema, integrity, and migration checks;
- only `human_decision.json` can authorize capital.

Changing source code is not the same as completing the migration. The bulk
rebuild, database migration, dashboard verification, and artifact checks remain
mandatory release steps whenever the contract changes.
