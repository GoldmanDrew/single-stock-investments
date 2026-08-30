# Proof-first valuation operating model

## Do not mix two valuation languages

| Language | What it is | Authority today |
|----------|------------|-----------------|
| **Canonical (use this)** | Power Zone route → proof-first economic-value components → universal contract → IC → `human_decision.json` | Sole production path. Resolver: `_system/scripts/decision_authority.py` |
| **Legacy reference (do not size from this)** | Marvin/Lawrence owner-cash IRR, present-value/price annualization, `implied_return`, `stance_proposal`, classification “Thesis IRR” fallbacks | Audit / migration / specialist cross-check only. Never actionable once a contract exists |

Lawrence owner-cash math may still run as a **specialist module** inside a fitting Power Zone (predictable cash-flow names). It is **not** the universal stance gate and must not be labeled “house IRR” or Magis `P4` authority.

Cutover detail: `_system/proposals/power_zone_committee_valuation_cutover_2026-07-18.md`.  
Operator summary: root `README.md` § Marvin pipeline; agent rules in `_system/agents/MARVIN.md`.

## Authority

The universal valuation contract is the only source of decision-grade security value. Marvin may collect evidence and write narrative research, but neither Marvin nor an Investment Committee persona may enter an unsupported component value.

Production readers must resolve authority in this order (see `decision_authority.py`):

```text
human_decision → investment_committee → valuation_contract → legacy_reference
```

Only `human_decision` is capital-actionable. Contract and IC are research readiness / recommendation layers. Legacy Lawrence fields are never actionable.

The production chain is:

1. The research library supplies reusable valuation logic and failure modes.
2. The Power Zone router selects one approved primary method and at most two corroborating methods.
3. Issuer filings and contracts supply source-locked facts.
4. A deterministic calculation graph produces low/base/high component outputs.
5. The universal contract checks completeness, arithmetic, scenario order, overlap and evidence lineage.
6. Independent committee reviewers challenge method fit, facts, assumptions, falsifiers and omissions.
7. The dashboard displays the complete calculation trace and model hash.
8. Measured outcomes inform later calibration; they never rewrite formulas automatically.

## Contract v3 semantic rules

Every method card and proof output declares exactly one `output_basis`:

| Output basis | Meaning | Intrinsic value today | Forward return | Hurdle entry price |
|--------------|---------|-----------------------|----------------|--------------------|
| `present_value_today` | The output has already been discounted to today. | The proof output itself | Withheld | Withheld; discounting again would double-discount the value |
| `future_payoff` | The output is a payoff at an explicit future date or horizon. | Payoff discounted at the explicit required return | Annualized payoff/price return over the stated horizon | Payoff discounted at each hurdle |
| `forward_cashflow_schedule` | The output is a dated per-share cash-flow schedule. | Schedule NPV at the explicit required return | Unique dated cash-flow IRR | Schedule NPV at each hurdle |

Intrinsic value, margin of safety, and forward return are distinct fields. Margin of safety is `(intrinsic value today - market price) / intrinsic value today`. The former calculation that annualized a present value relative to price is retained only in `legacy_audit`; it cannot rank securities, set entry prices, trigger committee work, or authorize capital.

## Proof status, model maturity, and universe priority

These are independent controls:

- **Proof status** answers whether the calculation is reproducible and evidence-clear: `decision_grade` or `evidence_blocked`.
- **Model level** answers how specific and reviewed the underwriting is: `unmodeled → evidence_blocked → screening_grade → stock_specific → committee_reviewed → owner_approved`.
- **Universe tier** answers how much research attention the security receives: Tier 1 active/imminent decisions, Tier 2 curated candidates, Tier 3 broad screening universe.

A source-locked generic template can be proof-complete and still remain `screening_grade`. Tier membership never upgrades its model level. Committee admission requires a stock-specific, proof-complete model and an eligible workflow trigger; only the owner can approve capital.

## Value statuses

| Status | Meaning | Included in security value |
|---|---|---:|
| `calculated` | Locked facts and deterministic arithmetic fully reproduce the output. | Yes |
| `bounded_estimate` | The output is reproducible and every judgment is justified and inside an approved range. | Yes |
| `unpriced` | A material fact or defensible bound is unavailable. | No |
| `legacy_sensitivity` | A deprecated unsupported range is retained for change attribution. | No |

If any material additive component is unpriced, the complete low/base/high security value is withheld. `priced_components_per_share` may still be shown, with an explicit warning that it is not a security valuation.

## Calculation-proof format

Every fact includes a source reference, exact locator, as-of date, unit and `locked: true`. Every judgment includes a rationale and allowed minimum/maximum. Calculation nodes use only the allow-listed arithmetic operations in `calculation_proof.py`; arbitrary expressions and executable code are prohibited.

The graph records:

- every input and its fact/estimate/judgment classification;
- every dependency and intermediate value;
- symbolic and substituted arithmetic;
- low/base/high output nodes;
- source lineage and proof hash;
- validation errors and component status.

The same inputs and method version must reproduce the same output and hash.

## Method-card governance

The approved registry is `_system/reference/valuation_method_registry.json`. A card is eligible for production only when it defines:

- method ID, version, status and Power Zones;
- the exact economic claim;
- required inputs and equations;
- permitted judgments;
- causal scenario rules;
- double-counting exclusions;
- known failure modes;
- corroborating methods;
- library sources with stable locators;
- `output_basis`, so downstream code never guesses whether an output is a present value or future economics.

Library material provides method provenance and base-rate candidates. Issuer facts must still come from primary company evidence. LLMs can find passages, propose mappings and explain calculations, but deterministic code performs the arithmetic.

## Committee responsibilities

- **Proposer:** submits a complete calculation proof.
- **Evidence tribunal:** verifies source lineage and locks facts.
- **Power Zone specialist:** tests method applicability.
- **Adversarial reviewer:** challenges judgments, overlap, scenario causality and hidden claims.
- **Calibration reviewer:** compares assumptions with measured historical outcomes.
- **Chair:** selects a defensible assumption set and preserves dissent.

The chair cannot waive a failed proof check. Disagreement must appear as different bounded assumptions or event cases, not an averaged price target.

## Migration and retirement

`run_security_decision_pipeline.py --scope all` is the canonical migration command. A release is not complete until the regenerated contracts, workbenches, pricing artifacts, tier manifest, dashboard data, and database mirror pass their validators. For each security the pipeline should:

1. refreshes its Power Zone route;
2. converts raw unsupported ranges to excluded legacy sensitivities;
3. evaluates calculation proofs;
4. withholds incomplete security values;
5. rebuilds workbenches and proof-completeness measures;
6. records the output basis and computes value, margin of safety, and any genuine dated forward return separately;
7. assigns model maturity and universe tier without conflating them;
8. prices only dated future economics and opens committee work only for eligible stock-specific models;
9. publishes the resulting state to the dashboard.

The legacy Marvin/Lawrence fields may remain temporarily for historical comparison. Contract v3 must never read them as production value or forward return. They can be deleted after every active security has a proof-complete baseline, all consumers use canonical v3 fields, and change history has been retained.

## MSB pilot

- The latest disclosed trust reserve is calculated as `$18.342m / 13.12001m units = $1.3980 per unit`.
- The producing royalty stream remains unpriced until contractual tiers, production cadence and finite reserves support a period-by-period distribution curve.
- Depletion and counterparty concentration are embedded in the producing-stream scenarios, not deducted through an arbitrary standalone reserve.
- The current arbitration remains unpriced until the claim, remedy, timing and collectibility are supported. The prior award is context, not a current comparable payoff.
- Former ranges remain visible only as excluded legacy sensitivities.

## Release gates

A decision-grade contract requires all of the following:

- every material economic claim is identified and priced exactly once;
- all component proofs are valid;
- low ≤ base ≤ high;
- event probabilities sum to one where applicable;
- component and enterprise-to-equity sums reconcile;
- no overlap key is duplicated among additive components;
- source facts are locked and traceable;
- judgments are bounded, justified and sensitivity-tested;
- stale material facts are refreshed;
- the proof output basis is declared and semantically valid;
- a present value does not produce a forward return or hurdle entry price;
- future-return outputs have explicit dates or horizons and a required return for present-value comparison;
- proof status, model level, and universe tier are present and independently derived;
- generic screening models are not committee-eligible;
- every change has a reason and before/after record;
- open primary-evidence blockers equal zero.
