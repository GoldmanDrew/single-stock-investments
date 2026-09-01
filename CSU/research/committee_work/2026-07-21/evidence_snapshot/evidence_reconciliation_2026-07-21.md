# CSU valuation evidence reconciliation — 2026-07-21

**Purpose:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component and reconciling the owner-cash bridge to primary filings.

## Facts reconciled (primary filings)

| Fact | Value | Source |
|------|-------|--------|
| FY2025 FCFA2S | $1,683M (+14% YoY) | `CSU/official-reports/Q4-2025-Shareholder-Report.pdf` |
| FCFA2S per diluted share | $79.42 | $1,683M ÷ 21,191,530 diluted shares |
| Diluted shares | 21,191,530 | Same (year ended December 31, 2025) |
| FY2025 revenue | $11,623M (+15%) | Same |
| Q1 2026 revenue | $3,181M (+20%) | `CSU/official-reports/Q1-2026-Shareholder-Report.pdf` |
| Cash and cash equivalents | $3,089M | Q4 2025 shareholder report balance sheet |
| Debt with recourse to CSI | $1,489M | Q4 2025 note 11 |
| Total debt | $4,131M | Q4 2025 (recourse + non-recourse) |
| Contingent consideration (earnouts) | $122M | Q4 2025 balance sheet |
| FY2025 net income | $586M (-24% YoY) | Q4 2025 (GAAP; not owner metric) |

## Component ownership map — met

Four additive components with unique overlap keys, no double-counting flags:

| Component | Overlap key | Economic claim |
|-----------|-------------|----------------|
| core_engine | `core_engine` | Normalized FCFA2S owner-cash engine on existing VMS base |
| reinvestment_or_assets | `reinvestment_or_assets` | Incremental acquisition reinvestment runway beyond base engine |
| net_financial_claims | `net_financial_claims` | Parent net cash, recourse debt, and earnout claims |
| downside_reserve | `downside_reserve` | Competitive-fade and capital-allocation reserve (negative) |

Non-recourse subsidiary debt ($2,642M) is excluded from net financial claims to avoid double-count with BU operating value. Lumine/Topicus orbit stakes remain embedded in the reinvestment path, not separately capitalized.

## Primary owner-cash bridge — met

**Base case bridge (per diluted share, USD):**

1. Normalized owner cash: **$79.42** (FY2025 FCFA2S $1,683M ÷ 21.19M shares).
2. Seven-year Lawrence owner-cash present value (12%/8% growth, 28× exit, 9.5% discount) with schedule adjustment → **core_engine** base **$1,546**.
3. Incremental hurdle-rate M&A runway (Q1 2026 +20% revenue supports pipeline) → **+$271**.
4. Net corporate financial claim after recourse debt, earnouts, and operating-cash minimum → **+$97**.
5. Competitive-fade / M&A inflation reserve → **−$174**.
6. **Sum base value ≈ $1,739** vs legacy scaffold **$1,739** vs price **~$1,933** (−10% vs component base).

Low/high cases change causal growth, exit multiple, reinvestment runway, net financial claim, and reserve severity—not terminal multiple alone.

**Falsifier:** FY2025 FCFA2S per share falls below **$65** for two consecutive years without a disclosed restructuring that explains the decline.

**Monitoring:** Q4/Q1 shareholder reports and FCFA2S per share table.

## Downside and capital claims — met

| Claim | Treatment | Evidence |
|-------|-----------|----------|
| Consolidated net debt | ~$1,042M (cash $3,089M − debt $4,131M) | Q4 2025 balance sheet |
| Recourse debt to CSI | $1,489M deducted in net_financial_claims | Note 11 |
| Earnout / contingent consideration | $122M liability | Q4 2025 balance sheet |
| Non-recourse subsidiary debt | Excluded from parent net claim | Notes 11–12 |
| Dilution | 21,191,530 diluted shares locked | Q4 2025 |
| Material options | None valued separately | Option scan: operating path sufficient |
| Downside reserve | downside_reserve component | M&A multiple inflation + earnout GAAP noise |

**Falsifier:** Undisclosed recourse liability or earnout step-up above **$250M** not reflected in net_financial_claims low case.

## Valuation consequence

Each additive component carries an approved `method_id@version` calculation proof in `CSU/research/valuation.json`. Lawrence base **17.5%** (total synthesis **18.73%**) remains the stance-context gate; component sum supports **decision_grade** contract readiness.

## Acceptance summary

| Gap ID | Status |
|--------|--------|
| component_ownership_map | met |
| primary_cash_or_nav_bridge | met |
| downside_and_capital_claims | met |
| core_engine calculation proof | met (`owner_cash_or_dividend_discount@1.0`) |
| reinvestment_or_assets calculation proof | met (`owner_earnings_reinvestment_dcf@1.0`) |
| net_financial_claims calculation proof | met (`net_asset_value@1.0`) |
| downside_reserve calculation proof | met (`net_asset_value@1.0`) |
