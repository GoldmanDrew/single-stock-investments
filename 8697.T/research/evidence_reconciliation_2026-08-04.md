# 8697.T valuation evidence reconciliation — 2026-08-04

**Purpose:** Close universal contract backfill blockers (`net_financial_claims`, `reinvestment_or_assets`) by filing-verifying share count and parent equity in calculation proofs.

## Blockers closed

| Blocker | Resolution |
|---------|------------|
| `reinvestment_or_assets`: source locator requires human review | Shares outstanding sourced from FY2025 earnings release Note (3): **1,030,321,466** issued shares at Mar 31, 2026 |
| `net_financial_claims`: source locator requires human review | Same share count plus parent equity **¥345,015M** from consolidated balance sheet in `E_ER_JPX_Q4FY2025.pdf` |

## Facts reconciled (primary filings)

| Fact | Value | Source |
|------|-------|--------|
| Issued shares (FY2026 period-end) | 1,030,321,466 | `8697.T/02_Quarterly/Earnings_Releases/E_ER_JPX_Q4FY2025.pdf` Note (3) |
| Weighted average ordinary shares | 1,030,321 thousand | Same |
| Parent equity attributable to owners | ¥345,015M | Same, consolidated balance sheet |
| FY2025 parent EPS (spot) | ¥76.81 | Same |
| Normalized owner cash (base) | ¥70/sh | Below spot EPS; clearing pass-through and peak-volume adjustment |

## Component ownership map — **met**

Four additive components with unique overlap keys; no double-counting flags. All carry valid `method_id@version` calculation proofs after share-count fix.

## Downside and capital claims — **met**

Clearing and member deposits remain pass-through (excluded from net financial claim via haircut). Share count no longer carries `[HUMAN REVIEW]` on proof source locators.

## Acceptance summary

| Gap ID | Status |
|--------|--------|
| component_ownership_map | met |
| primary_cash_or_nav_bridge | met |
| downside_and_capital_claims | met |
| reinvestment_or_assets calculation proof | met (filing-verified shares) |
| net_financial_claims calculation proof | met (filing-verified shares + FY2026 parent equity) |
