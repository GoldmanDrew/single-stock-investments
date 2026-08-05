# BWEL — Water acre-foot reverification (contract backfill)

**Date:** 2026-08-05  
**Agent:** Marvin (contract backfill)  
**Purpose:** Refresh `documented_af_transfers` source freshness for `asset_option_inventory` calculation proof.

---

## Question

Does the **102,000+ acre-feet** lower bound on documented Kings County surface-water transfers since 2009 still hold after FY2025 filings?

---

## FY2025 primary filing check

| Item | FY2025 annual (June 30, 2025) | Implication |
|------|-------------------------------|-------------|
| Land and related water investments | **$106,048 thousand** at cost | Unchanged combined line; no fair-value mark |
| Acre-foot quantity disclosed | **None** | Cannot replace journalism lower bound from filings alone |
| Subsurface minerals | CA/OR on owned and third-party land | Option; no quantity change noted |
| Flood / NRV context | $38.7M flood COS; $42.8M NRV charge | Tulare basin stress; no contradiction of transfer history |

**Source:** `BWEL/investor-documents/ir-bwel/2025-06-30_Annual_Report.pdf` (balance sheet line 160; notes 1–2 in `research/evidence/_text/report_501277.txt`).

**Fact:** The FY2025 annual does **not** disclose total portfolio acre-feet and does **not** contradict prior documented transfer activity.

---

## Documented transfer lower bound (reconfirmed)

| Source | Quantity | As-of for journalism | Marvin use |
|--------|----------|----------------------|------------|
| GV Wire / SJV Water (DWR transfer records) | **102,000+ AF** sold/transferred out of Kings County since **2009** | Article **2021-11-22** | **Lower bound** on monetizable surface water |
| Prior Marvin fact-check | Same figure | `fact_check_water_nav_2026-06-02.md` | Unchanged |

**Inference:** Transfers through at least 2021 prove liquidity and a transferable portfolio **at least** 102k AF. No newer public DWR aggregate was located in this refresh; FY2025 filings add no conflicting quantity.

**Upper bound (still unverified):** ~400,000 AF press claims (Groundbreaker, Undervalued Shares) remain **bull-scenario only**, not filing-proven.

---

## Contract backfill verdict

| Field | Value |
|-------|-------|
| `documented_af_transfers` | **102,000** acre-feet |
| Evidence tier | **estimate** (journalism + DWR records cited in prior fact-check) |
| Re-verification date | **2026-08-05** |
| Filing anchor | FY2025 annual confirms land/water line; no AF disclosure |
| Blocker cleared | Stale `as_of` replaced; quantity unchanged |

---

## Citations

1. `BWEL/investor-documents/ir-bwel/2025-06-30_Annual_Report.pdf`
2. `BWEL/research/evidence/_text/report_501277.txt`
3. `BWEL/research/fact_check_water_nav_2026-06-02.md` (original 102k AF research)
4. https://gvwire.com/2021/11/22/special-report-small-farmers-struggle-as-ag-titans-boswell-vidovich-wheel-water-for-profit/
5. https://sjvwater.org/where-is-the-water-going/
