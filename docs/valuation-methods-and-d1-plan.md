# Valuation compiler and database plan

## Correction and current state

Power Zone already owns valuation routing. `power_zone_router.py` calls the
valuation method router and writes a canonical route. The automation gap was
downstream: valuation readiness independently defaulted most operating
companies to the owner-earnings compiler, so the selected Power Zone route did
not reliably reach evidence planning or compilation.

The current 830-security route inventory is:

| Power Zone profile | Securities | Current primary method |
| --- | ---: | --- |
| Quality reinvestment | 721 | Owner-earnings reinvestment DCF |
| Scarce assets and optionality | 75 | Component owner cash plus unit NAV |
| Predictable cash flow | 17 | Owner cash/dividend discount |
| Capital cycle | 13 | Midcycle earnings power |
| Catalyst/asset value | 2 | Probability-weighted catalyst NAV |
| Binary/milestone | 1 | Milestone probability value |
| Credit/normalized returns | 1 | Capital structure/excess return |

Of those routes, 396 are still `default_needs_review`. They must not silently
be treated as confirmed quality-reinvestment companies.

## Implemented foundation

1. Valuation readiness now reads the canonical Power Zone route first.
2. Reviewed per-security overrides still take precedence and are auditable.
3. Default or zero-confidence routes create a critical classification task.
4. Every approved method now has typed evidence requirements and a
   method-specific compiler task.
5. Evidence recovery covers the full blocked universe, records errors, uses
   bounded exponential retry, and terminates unavailable tasks.
6. A decision-grade zero or negative base value now requires an explicit,
   source-backed wipeout/insolvency exception.
7. D1 stores the operational state needed to schedule work and inspect
   provenance, while repository artifacts remain the source of truth.

## Implemented method-specific compilers

The planned dispatcher is now implemented for all approved routes. Every
compiler has a versioned normalized input contract, deterministic low/base/high
equations, source-lineage proof output, and validation tests. Existing
issuer-specific approved proofs are revalidated and preserved when they satisfy
the shared proof invariants.

### Phase 1 — deterministic single-entity methods (implemented)

- `owner_cash_or_dividend_discount`
- `capital_structure_and_excess_return`
- `midcycle_capacity_value`

Each method now includes:

- a versioned input schema;
- evidence freshness rules by field;
- low/base/high scenario equations;
- a deterministic proof payload and input hash;
- golden fixtures for normal, missing, stale, and contradictory evidence;
- method-specific plausibility checks.

### Phase 2 — scarce-asset component compiler (implemented)

The placeholder composite method is now a component planner that:

1. map every material economic claim to a stable component ID;
2. assign each component exactly one approved method:
   `royalty_distribution_curve`, `net_asset_value`, or
   `owner_cash_or_dividend_discount`;
3. attach an overlap key to prevent double counting;
4. value liabilities and dilution separately;
5. reconcile component values to enterprise and equity value;
6. fail closed when an owned asset has no treatment.

This is the highest-value next compiler because it covers 75 routed
securities and is where double counting is most dangerous.

### Phase 3 — event and probability methods (implemented)

- `probability_weighted_catalyst_nav`
- `risk_adjusted_milestone_value`

These use explicit normalized event inputs, independently sourced probabilities,
time-to-event, dilution/funding requirements, and terminal failure outcomes.
Probabilities must sum to one and evidence age must be visible.

### Phase 4 — quality-reinvestment hardening (implemented foundation)

The owner-earnings compiler now supports:

- normalized reinvestment and incremental-return inputs;
- explicit fade behavior;
- share-count and dilution reconciliation;
- cyclicality tests;
- terminal-value concentration limits;
- a fail-closed classification task for the 396 default routes before scale-out.

## Automatic evidence flow

```text
Power Zone route
  -> typed method requirements
  -> evidence task queue
  -> source-specific collectors
  -> locked facts with source locators
  -> method compiler
  -> proof + invariants
  -> decision-grade valuation
  -> dashboard and D1 snapshot
```

Human input is reserved for policy exceptions, not routine missing data.
Collectors should exhaust primary filings, issuer materials, exchange
disclosures, registries, and approved market-data sources before a task is
marked unavailable.

## D1 role and cutover gates

D1 is initially a free operational mirror with these responsibilities:

- current security and valuation state;
- retryable evidence tasks and attempt history;
- source-document metadata and immutable fact provenance;
- versioned valuation runs and component proofs;
- fast dashboard/API filtering.

Repository JSON remains authoritative until all of these gates pass:

1. two weeks of hash-equivalent snapshots;
2. zero missing blocked-security tasks;
3. idempotent re-imports;
4. reproducible valuation outputs from stored facts;
5. backup/export restoration test;
6. API latency and free-tier usage remain within budget.

Do not store full filings in D1. Store document hashes, locators, and extracted
facts; keep large source files in the research vault or object storage.

## Cloudflare deployment

The dashboard deployment workflow now synchronizes Cloudflare whenever both
Cloudflare secrets exist. It:

1. builds a safe artifact from the sharded dashboard;
2. creates the Pages project and D1 database if absent;
3. applies versioned migrations;
4. synchronizes the current dashboard/task state into D1;
5. deploys the same artifact and Pages Functions.

Required GitHub Actions secrets:

- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_ACCOUNT_ID`

Optional repository variables:

- `CLOUDFLARE_PAGES_PROJECT` (defaults to `single-stock-investments`)
- `CLOUDFLARE_D1_DATABASE` (defaults to `single-stock-investments`)

The token needs Cloudflare Pages edit and D1 edit access for the selected
account. After adding the secrets, run **Deploy Dashboard (GitHub Pages)** once
from GitHub Actions. Future successful dashboard rebuilds synchronize and
deploy both hosts automatically.
