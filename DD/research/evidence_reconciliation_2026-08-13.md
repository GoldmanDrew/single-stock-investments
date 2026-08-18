# DD valuation evidence reconciliation — 2026-08-13

**Scope:** Contract backfill. Close remaining `valuation_contract.json` blocker: extreme annualized return validation. Evidence packet per `research_agent_manifest.json`.

## What changed since 2026-08-09

| Artifact | Prior | Current |
|----------|-------|---------|
| `authorized_evidence.json` | Stale-debt blocker closed; extreme-return blocker open | Extreme-return validation added |
| `valuation.json` | No `outlier_validation` | `outlier_validation.status: passed` with reverse DCF and earnings/book cross-check |
| Debt / owner earnings | Locked at $3.172B debt, $227M owner earnings | Unchanged (no new filings in packet) |

## Blocker closure: extreme annualized return validation

### Acceptance test — met

| Field | Content |
|---|---|
| status | met |
| evidence | Primary `owner_earnings_reinvestment_dcf@1.0` base value **$4.14/sh** implies **-39.67%** annual return at **$142.47** (Yahoo close 2026-08-07). Independent reverse DCF: **$0.55/sh** normalized owner earnings (FY2025 OCF **$560M** less capex **$333M** over **409.9M** shares) implies **~257×** owner-cash multiple at price. Book cross-check: FY2025 `StockholdersEquity` **$13.92B** → **$33.95/sh**; even 1× book implies **-17.4%** annual return at current price. |
| source path | `DD/investor-documents/sec-edgar/10-K_20260217_rpt20251231_acc0001666700_26_000013.htm`; `DD/investor-documents/sec-edgar/10-Q_20260505_rpt20260331_acc0001666700_26_000031.htm` |
| calculation | Reverse multiple: $142.47 ÷ ($227M ÷ 409.921306M) = **257.3×**. GAAP P/E: $142.47 ÷ ($779M ÷ 409.921306M) = **75.0×**. Book anchor IRR: ($33.95 ÷ $142.47)^(1/7) − 1 = **-17.4%**. All confirm price embeds expectations above bounded proof range ($4.14 base, $12.88 high). |
| remaining uncertainty | Extreme return is **real** (overvaluation vs filing owner economics), not a proof artifact. Segment-level reinvestment bridge still uses versioned bounds. **[HUMAN REVIEW]** for stance. |
| falsifier | FY2026 filings show normalized owner earnings above **$600M** without a matching capital event, or price falls below **$15/sh** making the extreme flag moot. |

## Prior blocker (2026-08-09) — remains closed

Stale debt fact ($7.17B from 2024 `LongTermDebt` tag) replaced with **$3.172B** (LT + current) from FY2025 10-K and Q1 2026 10-Q. See `evidence_reconciliation_2026-08-09.md`.

## Valuation consequence

With `outlier_validation` passed, contract should advance toward `decision_grade` pending mechanical pipeline recompile. Base proof **~$4.14/sh** vs **$142.47** price; annual return at price **-39.7%** on base case.
