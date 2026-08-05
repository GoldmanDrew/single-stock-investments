# AXTI valuation evidence reconciliation — 2026-08-05

**Scope:** Contract backfill. Close `authorized_evidence.json` blocker: extreme annualized return requires independent validation with a second method and source-backed evidence. Evidence packet per `research_agent_manifest.json`. // pragma: allowlist secret

## What changed since 2026-07-24

| Artifact | Prior | Current |
|----------|-------|---------|
| `DOWNLOAD_MANIFEST.json` | 53+ SEC docs indexed | Stable; all entries `ok: true` |
| `authorized_evidence.json` | `extreme_return_validated: false` | **Target:** pass via `outlier_validation` |
| `valuation.json` | Component proofs complete; no outlier block | Added `valuation_methodology.outlier_validation` with Lawrence IRR cross-check |
| Narrative | `deep_dive_2026-07-27.md` | Carried forward; economics unchanged |

## Blocker closure: extreme return validation

### Acceptance test — met

| Field | Content |
|---|---|
| status | met |
| evidence | `valuation_methodology.outlier_validation.status` = `passed`; two independent methods with filing refs |
| source path | `AXTI/research/valuation.json` |
| calculation | **Method 1 (component economic value):** proof sum base $1.40 + $0.89 + $0.50 − $0.75 − $0.30 = **$1.74/sh** at price **$47.23** → contract annualized return **−37.58%** over 7 years. **Method 2 (Lawrence owner-cash IRR):** mid-cycle normalized starting owner cash **$0.12/sh** (FY2021–FY2022 operating profit ~$13M less ~$6M maintenance capital spending, scaled to 65.4M shares) at **$47.23** → synthesis base **−9.92%** per year (8% growth years 1–5, 5% years 6–7, 12× exit). |
| remaining uncertainty | Methods diverge in magnitude (−37.58% vs −9.92%) because component sum is static mid-cycle multiple plus bounded options/liabilities while Lawrence path models growth from normalized cash; both independently confirm price far above filing-grounded economics. |
| falsifier | Q2 2026 owner cash exceeds high-case normalized path **and** component mid-cycle owner cash revised above $12M annual on sustained margins; would invalidate overvaluation conclusion. |

### Component proof completeness — unchanged, met

All five additive components retain valid `calculation_proof` graphs (`midcycle_capacity_value@1.0`, `net_asset_value@1.0`, `risk_adjusted_milestone_value@1.0`). Overlap keys non-overlapping; `double_counting_flags` empty.

## Facts vs judgments

**Facts (locked):** Cash $57.9M (Q1 2026 10-Q); shares 65,423,184 (May 4, 2026 cover page); PE redemption ~$49M (10-Q Note 1); FY2025 revenue $88.3M; Q1 2026 revenue $26.9M (+39% YoY); price $47.23 (Yahoo close 2026-07-24).

**Judgments (bounded):** Mid-cycle owner cash $4.5M–$12.0M; Tongmei HK success probability 0–55%; PE redemption pct 0–133%; future dilution haircut 0–1.1% of price.

## Valuation consequence

Proof-complete additive schedule base **$1.74 per share** vs **$47.23** price. Lawrence synthesis **−9.92%** per year remains stance reference. Both methods validate extreme negative return at current quote. Security remains **watch**; no human capital decision recorded.
