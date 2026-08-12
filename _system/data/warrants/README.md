# Warrant opportunity data

This directory separates immutable contract evidence from mutable observations.

- `warrant_registry.jsonl` — append-only, versioned warrant-series terms.
- `warrant_registry_amendments.jsonl` — append-only superseding versions when a seed term is corrected.
- `warrant_events.jsonl` — accession-locked SEC discoveries awaiting identity/terms work.
- `warrant_market.json` — last-known-good delayed market observations.
- `warrant_market_history.jsonl` — point-in-time quote history, never rewritten.
- `warrant_cohorts.jsonl` — monthly entry cohorts captured without hindsight.
- `warrant_outcomes.jsonl` and `warrant_calibration.json` — matured 90/365-day outcomes and descriptive calibration.
- `discovery_state.json` — collector health and consecutive-failure state.

Contract records never receive an executable opportunity score until identity,
survival, and two-sided-market gates all pass. Calibration never changes weights
or authorizes a trade.
