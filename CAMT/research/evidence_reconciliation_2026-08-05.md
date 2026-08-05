# CAMT valuation evidence reconciliation — 2026-08-05

**Scope:** Contract backfill. Close universal contract blocker on stale debt fact. Evidence packet per `research_agent_manifest.json`. // pragma: allowlist secret

## What changed since 2026-07-29

| Artifact | Prior | Current |
|----------|-------|---------|
| `DOWNLOAD_MANIFEST.json` | 5 SEC docs indexed | Stable; all entries `ok: true` |
| `valuation.json` debt input | `LongTermDebt` **$3.792M** (FY2012 accession 0001178913-13-001068) | **`ConvertibleDebtNoncurrent` $519.833M** (FY2025 20-F accession 0001178913-26-001561) |
| `valuation_fact_ledger.json` `debt_m` | Stale 2012 tag | Locked to FY2025 convertible notes carrying amount |
| Contract status | `evidence_blocked` (stale debt) | **Target:** decision-grade after refresh |

## Blocker closure: stale debt fact

### Acceptance test — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 Form 20-F balance sheet reports convertible debt non-current carrying amount **$519,833 thousands** ($519.833M) at December 31, 2025 |
| source path | `CAMT/investor-documents/sec-edgar/20-F_20260319_rpt20251231_acc0001178913_26_001561.htm` |
| calculation | Prior proof subtracted **$3.792M** debt sourced from a 2012 `LongTermDebt` XBRL tag (4958 days stale vs contract as-of). Updated proof subtracts **$519.833M** `ConvertibleDebtNoncurrent` from equity bridge: equity value = PV(distributable owner cash + terminal) + cash − convertible debt. Base value per share falls from **$54.27** to **$43.01** at unchanged reinvestment judgments. |
| remaining uncertainty | Lease liabilities ($5.3M finance + $5.6M operating at Dec 2025) are not added to debt_m; convertible notes dominate capital structure. Dilution from conversion is not modeled separately in the single-component proof. |
| falsifier | FY2026 filing shows convertible debt repaid or reclassified below $100M without offsetting cash build; would reopen debt fact and equity bridge. |

## Facts vs judgments

**Facts (locked):** FY2025 revenue **$496.1M**; operating income **$128.2M**; operating cash flow **$141.9M**; capital spending **$14.4M**; cash **$177.8M**; convertible debt non-current **$519.8M**; shares **45.83M** (Dec 31, 2025 20-F). Price **$147.09** (Yahoo close 2026-07-20).

**Judgments (bounded):** Reinvestment rate 20–50%; incremental after-tax return on invested capital 12–25%; discount rate 9–12%; terminal owner-earnings multiple 12–24×. **[Assumption]** Pending primary-source reinvestment ledger refresh from management capital-allocation discussion.

## Valuation consequence

Proof-complete operating component base **$43.01 per share** vs **$147.09** price implies **−16.1%** per year over seven years (contract method). Stale debt materially overstated equity value; economics still show price far above filing-grounded owner-cash path. No human capital decision recorded.
