# 0388.HK valuation evidence reconciliation — 2026-08-04

**Scope:** Contract backfill close per authorized evidence packet `170316c90888b999c021c9c53f601dc1daae451d57c9a69fd0daf1b30d095ac5`. // pragma: allowlist secret

## Blockers closed

| Blocker | Resolution |
|---------|------------|
| `reinvestment_or_assets: source locator explicitly requires human review` | Replaced `[HUMAN REVIEW]` share-count locator with FY2025 annual report citation: **1,267,836,895** shares in issue as at 31 December 2025 (`0388.HK/investor-documents/ir-0388.hk/260316ar_e.pdf`). |
| `net_financial_claims: source locator explicitly requires human review` | Same filing-backed share count attached to `shares_m` input in `net_asset_value@1.0` proof graph. |

Proof builder: `_system/scripts/build_0388_contract_proofs.py` (run 2026-08-04).

## Proofs attached

| Component | Method | Proof status | Base per share |
|-----------|--------|--------------|----------------|
| `core_engine` | owner_cash_or_dividend_discount@1.0 | bounded_estimate | HK$243.82 |
| `reinvestment_or_assets` | owner_earnings_reinvestment_dcf@1.0 | bounded_estimate | HK$36.57 |
| `net_financial_claims` | net_asset_value@1.0 | bounded_estimate | HK$14.63 |
| `downside_reserve` | midcycle_capacity_value@1.0 | bounded_estimate | −HK$36.63 |

Additive base sum **HK$258.45/sh** (unchanged; share count correction is immaterial to judgment-layer per-share component values).

## Acceptance test — economic ownership map — met

| Field | Content |
|---|---|
| status | met |
| evidence | Four non-overlapping additive components map croupier fee infrastructure, Connect/data reinvestment, net financial claims after clearing pass-through, and peak-cycle volume reserve. |
| source path | `0388.HK/official-reports/annual-reports/annual_report_fy2024.pdf`; `0388.HK/investor-documents/ir-0388.hk/260316ar_e.pdf`; `0388.HK/investor-documents/ir-0388.hk/260316sr_e.pdf` |
| calculation | Unique overlap keys: `core_engine`, `reinvestment_or_assets`, `net_financial_claims`, `downside_reserve`. Base sum HK$243.82 + HK$36.57 + HK$14.63 − HK$36.63 = **HK$258.45/sh**. |
| remaining uncertainty | Full-tier OCR text extract still pending for segment fee bridge; equity context uses FY2024 annual report notes. |
| affected components | `reinvestment_or_assets`, `net_financial_claims` (share input only) |
| valuation consequence | Contract blockers cleared; share count locked at **1,267,836,895** from FY2025 annual report. |
| falsifier | Issued share count changes materially without updated proof graph and overlap reconciliation. |

## Facts vs judgments

**Facts (locked):** FY2024 revenue **HK$22.4B** (+9% YoY); profit attributable **HK$13.1B**; basic EPS **HK$10.32**; FY2025 profit attributable **HK$17.754B**; FY2025 basic EPS **HK$14.05**; DPS **HK$12.52**; issued shares **1,267,836,895** as at 31 December 2025.

**Judgments (bounded):** Normalized owner cash **HK$11/sh**; component per-share ranges unchanged from 2026-07-24 backfill.

## Valuation consequence

Proof-complete additive schedule base **~HK$258.45 per share** vs thesis-card price **~HK$383** implies market prices sustained peak-cycle earnings above normalized component value. Lawrence seven-year base **0.0%** per year and total synthesis **−0.15%** remain stance gates. Security remains **watch** pending human decision authority.
