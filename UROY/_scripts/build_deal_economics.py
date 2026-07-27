#!/usr/bin/env python3
"""Build New URC deal economics scratchpad from circular facts."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research"

# FX: circular presents New URC pro forma in C$; Sweetwater MD&A often in US$.
# Deal consideration stated in US$. Use circular-implied debt bridge:
# Sweetwater debt US$625m (Apr 1 2026 PR) ≈ pro forma LTD C$859.0m → FX ≈ 0.728
CADUSD = 625.0 / 859.020  # ≈ 0.7276

# Pro forma share count (circular selected pro forma, basic)
SHARES = 361_037_249
DEEMED_USD = 3.64

# Sellers consideration
SELLER_SHARES = 223_252_749
SELLER_CASH_USD_M = 330.0
SELLER_EQUITY_USD_M = SELLER_SHARES * DEEMED_USD / 1e6  # ~813
SW_PCT = 0.92

# Pro forma income statement FY ended Apr 30 2025 (C$ thousands)
pf_fy2025_cad_k = {
    "revenue_total": 137_569,
    "uranium_inventory_sales": 15_507,
    "royalty_revenue": 112_214,
    "lease_bonus": 7_137,
    "surface_revenue": 2_711,
    "gross_profit": 83_554,
    "operating_income": 39_354,
    "interest_expense": 47_979,
    "net_income": 14_148,
}

# Pro forma 9mo ended Jan 31 2026 (C$ thousands)
pf_9mo_cad_k = {
    "uranium_inventory_sales": 49_533,
    "royalty_revenue": 55_972,
    "lease_bonus": 6_769,
    "surface_revenue": 2_742,
    "operating_income": 37_821,
    "interest_expense": 35_175,
    "net_income": 8_835,
}

# Balance sheet pro forma Jan 31 2026 (C$ thousands)
pf_bs_cad_k = {
    "cash": 16_452,
    "long_term_debt": 859_020,
}

# Sweetwater standalone (USD millions) from circular MD&A excerpts
sw_usd_m = {
    "adj_ebitda_recent": 66.244,  # circular money line; treat as recent FY/TTM proxy
    "avg_adj_ebitda_last_2fy": 74.0,  # company PR 100% basis
    "interest_expense_fy": 34.0,
    "royalty_rev_fy_recent": 59.276,
    "royalty_rev_fy_prior": 82.514,
    "debt_apr1_2026": 625.0,
}

# Convert key PF items to USD m
def cad_k_to_usd_m(v: float) -> float:
    return v * CADUSD / 1000.0


econ = {
    "as_of": "2026-07-27",
    "sources": [
        "UROY/research/evidence/circular_sedar_text.md (SEDAR MIC)",
        "UROY/investor-documents/sec-edgar/6K_20260416_ex99-1.htm (deal PR)",
        "UROY/investor-documents/sec-edgar/6K_20260626_ex99-1.htm (seller share count)",
        "Lemon Cakes 2026-07-27 (approved Substack context; not base IRR authority alone)",
    ],
    "fx": {"cadusd_implied": round(CADUSD, 6), "method": "US$625m Sweetwater debt / C$859.020m pro forma LTD"},
    "ownership_pf": {
        "old_urc_shareholders_pct": 0.41,
        "orion_pct": 0.43,
        "otpp_pct": 0.16,
        "sweetwater_interest_acquired_pct": SW_PCT,
        "seller_new_urc_shares": SELLER_SHARES,
        "pro_forma_shares": SHARES,
        "lockup_days": 180,
        "lockup_release_price_cad": 7.50,
    },
    "consideration_usd_m": {
        "cash_to_sellers": SELLER_CASH_USD_M,
        "equity_to_sellers_at_deemed": round(SELLER_EQUITY_USD_M, 1),
        "equity_value_92pct": round(SELLER_CASH_USD_M + SELLER_EQUITY_USD_M, 1),
        "sweetwater_ev_100pct_pr": 1900.0,
        "sweetwater_debt": 625.0,
        "uec_subscription": 40.0,
        "deemed_price_per_share": DEEMED_USD,
    },
    "pro_forma_fy2025_usd_m": {k: round(cad_k_to_usd_m(v), 2) for k, v in pf_fy2025_cad_k.items()},
    "pro_forma_9mo_jan2026_usd_m": {k: round(cad_k_to_usd_m(v), 2) for k, v in pf_9mo_cad_k.items()},
    "pro_forma_9mo_annualized_usd_m": {
        "royalty_revenue": round(cad_k_to_usd_m(pf_9mo_cad_k["royalty_revenue"]) * 12 / 9, 2),
        "operating_income": round(cad_k_to_usd_m(pf_9mo_cad_k["operating_income"]) * 12 / 9, 2),
        "interest_expense": round(cad_k_to_usd_m(pf_9mo_cad_k["interest_expense"]) * 12 / 9, 2),
    },
    "pro_forma_bs_usd_m": {k: round(cad_k_to_usd_m(v), 2) for k, v in pf_bs_cad_k.items()},
    "sweetwater_standalone_usd_m": sw_usd_m,
}

# Capitalization at deemed value
equity_mkt_usd = SHARES * DEEMED_USD / 1e6
net_debt = econ["pro_forma_bs_usd_m"]["long_term_debt"] - econ["pro_forma_bs_usd_m"]["cash"]
ev = equity_mkt_usd + net_debt

# EBITDA proxies
ebitda_avg2 = sw_usd_m["avg_adj_ebitda_last_2fy"] * SW_PCT  # attributable
ebitda_recent = sw_usd_m["adj_ebitda_recent"] * SW_PCT
# rough PF operating income + D&A not fully available; use Lemon/PR EBITDA anchors
ebitda_fy_pr = 74.0  # 100% 
ebitda_fy_attr = 74.0 * SW_PCT

multiples = {
    "price_deemed_usd": DEEMED_USD,
    "equity_mkt_cap_usd_m": round(equity_mkt_usd, 1),
    "net_debt_usd_m": round(net_debt, 1),
    "enterprise_value_usd_m": round(ev, 1),
    "ev_ebitda_on_avg2yr_100pct": round(ev / 74.0, 1),
    "ev_ebitda_on_avg2yr_92pct": round(ev / ebitda_fy_attr, 1),
    "ev_ebitda_on_recent_adj_92pct": round(ev / ebitda_recent, 1),
    "debt_ebitda_avg2yr_100pct": round(625.0 / 74.0, 1),
    "debt_ebitda_recent_adj_100pct": round(625.0 / 66.244, 1),
    "interest_coverage_fy2025_opinc_over_interest": round(
        econ["pro_forma_fy2025_usd_m"]["operating_income"] / econ["pro_forma_fy2025_usd_m"]["interest_expense"], 2
    ),
    "interest_coverage_9mo_ann_opinc_over_interest": round(
        econ["pro_forma_9mo_annualized_usd_m"]["operating_income"]
        / econ["pro_forma_9mo_annualized_usd_m"]["interest_expense"],
        2,
    ),
}

# Scenario values at various EV/EBITDA on attributable trough/mid/peak EBITDA
def price_from_multiple(mult: float, ebitda: float) -> float:
    # Equity = EV - net debt; price = equity / shares
    ev_ = mult * ebitda
    equity = ev_ - net_debt
    return equity / (SHARES / 1e6)


scenarios = {
    "trough_ebitda_attr_usd_m": round(50.0 * SW_PCT, 1),  # [Assumption] deep trough
    "midcycle_ebitda_attr_usd_m": round(74.0 * SW_PCT, 1),
    "expansion_ebitda_attr_usd_m": round(74.0 * 1.60 * SW_PCT, 1),  # mgmt +60% capacity case, static margins [Assumption]
}
for label, ebitda in [
    ("trough_15x", scenarios["trough_ebitda_attr_usd_m"]),
    ("mid_15x", scenarios["midcycle_ebitda_attr_usd_m"]),
    ("mid_18x", scenarios["midcycle_ebitda_attr_usd_m"]),
    ("mid_20x", scenarios["midcycle_ebitda_attr_usd_m"]),
    ("mid_26x_dealish", scenarios["midcycle_ebitda_attr_usd_m"]),
    ("expansion_18x", scenarios["expansion_ebitda_attr_usd_m"]),
]:
    mult = float(label.split("_")[1].replace("x", "").replace("dealish", ""))
    if "dealish" in label:
        mult = 26.0
    elif "15" in label:
        mult = 15.0
    elif "18" in label:
        mult = 18.0
    elif "20" in label:
        mult = 20.0
    scenarios[f"price_{label}"] = round(price_from_multiple(mult, ebitda), 2)

econ["capitalization_at_deemed"] = multiples
econ["price_scenarios_usd"] = scenarios
econ["notes"] = [
    "Pro forma income statement figures are in C$ thousands in the circular; converted with debt-implied CADUSD.",
    "Adjusted EBITDA anchors are Sweetwater-centric; uranium royalty cash flow remains small vs trona.",
    "9mo royalty revenue run-rate is materially below FY2025 — cycle trough, not seasonality (circular CFS commentary).",
    "PFIC warning applies to pre-domestication UROY/URC holders per Lemon Cakes / tax counsel needed.",
    "New ticker at listing TBD; folder uses current NASDAQ UROY.",
]

(OUT / "new_urc_deal_economics.json").write_text(json.dumps(econ, indent=2) + "\n", encoding="utf-8")
print(json.dumps({k: econ[k] for k in ["consideration_usd_m", "capitalization_at_deemed", "price_scenarios_usd"]}, indent=2))
