# Portfolio short activist scan

**Date:** 2026-05-28  
**Agent:** Milly (`short_scan_batch.py`)  
**Registry:** `_system/frameworks/short_activist_registry.md`

**Method:** Local `short_reports/` scan + known hits. Tier-1 web search: run per ticker in Milly pass.

## Summary

| Ticker | Status | Local cache | Notes |
|--------|--------|-------------|-------|
| 3905.T | no_local_hit | — | Run Milly Tier-1 web scan per registry |
| 8697.T | no_local_hit | — | Run Milly Tier-1 web scan per registry |
| AMZN | no_local_hit | — | Run Milly Tier-1 web scan per registry |
| APLD | stale_hit | 1 file(s) in short_reports/ | Wolfpack / Bear Cave / Friendly Bear Jul 2023 — see short_reports/ |
| BN | no_local_hit | — | Run Milly Tier-1 web scan per registry |
| CMSG | no_local_hit | — | Run Milly Tier-1 web scan per registry |
| CPRT | no_local_hit | — | Run Milly Tier-1 web scan per registry |
| CSGP | no_local_hit | — | Run Milly Tier-1 web scan per registry |
| CSU | no_local_hit | — | Run Milly Tier-1 web scan per registry |
| DHR | no_local_hit | — | Run Milly Tier-1 web scan per registry |
| FRMO | no_hit | — | No Muddy/Hindenburg; Jan 2026 non-reliance (disclosure, not short) |
| GOOGL | no_local_hit | — | Run Milly Tier-1 web scan per registry |
| ICE | no_local_hit | — | Run Milly Tier-1 web scan per registry |
| KEWL | no_local_hit | — | Run Milly Tier-1 web scan per registry |
| MSB | no_local_hit | — | Run Milly Tier-1 web scan per registry |
| OTCM | no_local_hit | — | Run Milly Tier-1 web scan per registry |
| QDEL | litigation | — | 2024 securities class actions; no Tier-1 forensic short |
| SJT | no_local_hit | — | Run Milly Tier-1 web scan per registry |
| SPGI | no_local_hit | — | Run Milly Tier-1 web scan per registry |
| TEQ.ST | no_local_hit | — | Run Milly Tier-1 web scan per registry |
| WBI | no_local_hit | — | Run Milly Tier-1 web scan per registry |

## Maintenance

- Re-run: `python _system/scripts/short_scan_batch.py`
- Save hits: `{TICKER}/third-party-analyses/short_reports/{firm}_{date}.md`
- Reconcile in `{TICKER}/research/adversarial_{date}.md`

