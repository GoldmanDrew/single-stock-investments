# 7176.T valuation evidence reconciliation — 2026-07-24

**Scope:** Contract backfill close per authorized evidence packet `598120c16dfc7ad73a793ed55cd64acc3eb455040540bf09ed83729e3b055d01`. // pragma: allowlist secret

## Proofs attached

| Component | Method | Proof status | Base per share |
|-----------|--------|--------------|----------------|
| `core_fee_engine` | owner_cash_or_dividend_discount@1.0 | bounded_estimate | ¥2,239.37 |
| `etf_product_pipeline` | owner_earnings_reinvestment_dcf@1.0 | bounded_estimate | ¥100.00 |
| `net_financial_claims` | net_asset_value@1.0 | bounded_estimate | ¥65.03 |
| `performance_fee_cycle_reserve` | midcycle_capacity_value@1.0 | bounded_estimate | −¥140.02 |

Proof builder: `_system/scripts/build_7176_contract_proofs.py`. Additive base sum **¥2,264.38/sh**.

## Acceptance test — economic ownership map — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2026 finfo2026 and Pnotice2026-1 (English `_text_en/`): consolidated revenue **¥22.512B**, parent net income **¥10.631B**, split-adjusted EPS **¥317.33** (FY2026) vs **¥137.14** (FY2025 mid-cycle anchor), AUM **¥1,335.7B**, base fees **¥7.869B**, success fees **¥14.316B**, BVPS **¥757.01**, issued shares **27.12M** post 1-for-20 split. |
| source path | `7176.T/02_Quarterly/Earnings_Releases/20260528_2026年3_月期_決算短信_日本基準_連結__finfo2026.pdf`; `7176.T/02_Quarterly/Earnings_Variance_Notices/20260528_前年同期実績_連結_との差異に関するお知らせ__Pnotice2026-1.pdf`; `7176.T/03_Events/Timely_Disclosures/20250924_株式分割及び定款の一部変更に関するお知らせ__irnews20250924.pdf` |
| calculation | Four non-overlapping additive components with valid calculation_proof graphs: fee-engine DCF on **¥137.14/sh** mid-cycle owner cash; bounded ETF pipeline; partial book claim (**8.6%** of BVPS at base); performance-fee cycle reserve (**~1.02×** mid-cycle owner cash at base). Sum **¥2,264.38/sh**. |
| remaining uncertainty | Yuho (EDINET E31267) not mirrored locally; last exchange print **¥464** (100 shares, Jan 2026) is illiquid, not VWAP. |
| affected components | All additive |
| valuation consequence | Universal contract ownership map supplied; status upgrades to **decision_grade** after mechanical refresh. |
| falsifier | Filings show material segment, capital structure, or fee mix change not reflected in overlap keys. |

## Overlap control — met

| Field | Content |
|---|---|
| status | met |
| evidence | Unique overlap keys: `core_fee_engine`, `etf_product_pipeline`, `net_financial_claims`, `performance_fee_cycle_reserve`. |
| source path | `7176.T/research/valuation.json` |
| calculation | Additive base sum **¥2,264.38/sh** = ¥2,239.37 + ¥100.00 + ¥65.03 − ¥140.02. |
| remaining uncertainty | None on overlap map. |
| affected components | All additive |
| valuation consequence | Component sum is additive once. |
| falsifier | New component added without unique overlap_key. |

## Facts vs judgments

**Facts (locked):** FY2026 revenue **¥22.512B**; parent net income **¥10.631B**; FY2025 mid-cycle EPS **¥137.14**; FY2026 EPS **¥317.33**; AUM **¥1,335.7B**; base fees **¥7.869B**; success fees **¥14.316B** (~65% of combined fees); BVPS **¥757.01**; issued shares **27.12M** post split; price **¥464** (last thin print).

**Judgments (bounded):** Mid-cycle owner cash anchor excludes FY2026 peak success fees; ETF pipeline **¥40–¥220/sh**; book claim **0–17%** of BVPS; performance-fee reserve **−¥320 to −¥25/sh**.

## Valuation consequence

Proof-complete additive schedule base **~¥2,264 per share** vs last print **¥464** implies deep discount on filing-grounded component value if the print is investable. Lawrence seven-year base **50.3%** per year remains the stance gate on mid-cycle owner cash; synthesis **53.33%** includes qualitative adjustments. Contract status **decision_grade** after gap closure. Security remains **watch** pending human decision authority and live quote confirmation. No human capital decision recorded.
