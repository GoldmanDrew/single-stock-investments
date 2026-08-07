#!/usr/bin/env python3
"""Map TBBK share repurchases and earnings growth over a five-year horizon.

The Bancorp runs against a $10 billion asset cap (FRB Reg II, Durbin), so it
cannot compound by retaining capital into the balance sheet.  Management's
stated policy is to return close to 100% of net income, and it has done so:
$885 million of repurchases since 2022, retiring 33% of the shares.

That makes the earnings-per-share path an identity with only four moving
parts, and it is worth writing the identity down because it explains most of
what looks like growth:

    shares repurchased  = payout * net income / repurchase price
                        = payout * average shares / forward P/E

The net income term cancels.  Annual share count reduction is therefore
governed by the payout ratio and the multiple the market charges, not by how
much the company earns.  A rerating upward mechanically slows the buyback
contribution to earnings per share.  This is the central and under-appreciated
mechanic in the name, so the model solves it explicitly rather than assuming a
share count path.

Outputs TBBK/research/buyback_eps_model.json and a markdown companion.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

TICKER = "TBBK"
AS_OF = "2026-08-06"
PRICE = 72.095  # Yahoo TBBK close 2026-08-06

K10 = "TBBK/investor-documents/sec-edgar/10-K_20260225_rpt20251231_acc0001295401_26_000002.htm"
Q10_2025 = "TBBK/investor-documents/ir-tbbk/TBBK-Q2-2025-10Q.pdf"
DECK = "TBBK/investor-documents/ir-tbbk/tbbk-investor-presentation-q2-2026.pdf"

# --- History, all primary sourced -------------------------------------------------
HISTORY = [
    {"year": 2022, "eps_diluted": 2.27, "net_income_m": None, "avg_diluted_m": None,
     "source": f"{DECK} EPS trend page"},
    {"year": 2023, "eps_diluted": 3.49, "net_income_m": 192.296, "avg_diluted_m": 55.10,
     "source": f"{K10} us-gaap:NetIncomeLoss; {DECK} EPS trend page"},
    {"year": 2024, "eps_diluted": 4.29, "net_income_m": 217.540, "avg_diluted_m": 50.71,
     "source": f"{K10} us-gaap:NetIncomeLoss; {DECK} EPS trend page"},
    {"year": 2025, "eps_diluted": 4.92, "net_income_m": 228.213, "avg_diluted_m": 46.39,
     "source": f"{K10} us-gaap:NetIncomeLoss; {DECK} EPS trend page"},
    {"year": "H1 2026", "eps_diluted": 2.86, "net_income_m": 120.725, "avg_diluted_m": 42.21,
     "source": f"{DECK} segment table six months ended 2026-06-30; TTM EPS page"},
]

# Repurchase authorisations, from the Q2 2025 10-Q Note and subsequent events.
AUTHORISATIONS = [
    {"period": "FY2024", "amount_m": 250.0, "note": "2024 Repurchase Program, executed in full",
     "source": f"{Q10_2025} Note: 'the Company repurchased $250.0 million in value ... in 2024'"},
    {"period": "FY2025", "amount_m": 150.0, "note": "Original 2025 program, $37.5m per quarter",
     "source": f"{Q10_2025} Note: 2025 Repurchase Program"},
    {"period": "H2 2025", "amount_m": 300.0, "note": "Board increase, 2025-07-07",
     "source": f"{Q10_2025} subsequent events: capacity increased to $300 million for Q3 and Q4 2025"},
    {"period": "FY2026", "amount_m": 200.0, "note": "Board authorisation for 2026",
     "source": f"{Q10_2025} subsequent events: '$200 million for 2026 ... up to $500 million through year-end 2026'"},
]

CUMULATIVE_SINCE_2022_M = 885.0        # Q2 2026 deck, capital return page
CUMULATIVE_SHARE_PCT = 0.33            # Q2 2026 deck, "% of Shares repurchased"
CAPITAL_RETURNED_PCT_OF_NI = 1.00      # Q2 2026 deck, "Capital returned as % of Net income"

SHARES_START_M = 41.634439             # 10-Q cover 2026-04-27
TOTAL_ASSETS_2025_M = 9352.425         # 10-K us-gaap:Assets
EQUITY_2025_M = 689.796                # 10-K us-gaap:StockholdersEquity
ASSET_CAP_M = 10000.0                  # FRB Reg II / Durbin threshold

GUIDANCE = {
    "fy2026_eps_range": [5.95, 6.05],
    "q4_2026_run_rate_range": [6.60, 7.00],
    "fy2027_eps_range": [8.10, 8.30],
    "apex_2030_eps_growth_range": [0.15, 0.30],
    "source": f"{DECK} earnings per share trends page and Apex 2030 page",
}

# --- Scenarios --------------------------------------------------------------------
# fy2026_net_income_m is anchored so that FY2026 EPS lands inside management's
# $5.95-$6.05 guidance in the base case, then grown at the stated rate.
SCENARIOS = {
    "bear": {
        "label": "Fee growth stalls, credit normalises",
        "fy2026_net_income_m": 243.0,
        "net_income_growth": 0.01,
        "payout_ratio": 0.85,
        "forward_pe_for_repurchase": 10.0,
        "sbc_shares_m_per_year": 0.70,
        "rationale": "Fintech fee growth decelerates to low single digits, real estate bridge lending runs off, and "
                     "the board retains more capital as credit normalises. Repurchases happen at a derated multiple, "
                     "which is the one respect in which a bear case helps the share count.",
    },
    "base": {
        "label": "Fee franchise compounds, balance sheet flat at the cap",
        "fy2026_net_income_m": 248.0,
        "net_income_growth": 0.065,
        "payout_ratio": 0.95,
        "forward_pe_for_repurchase": 13.0,
        "sbc_shares_m_per_year": 0.60,
        "rationale": "Fintech fee revenue continues to compound at high single digits with positive operating "
                     "leverage while Credit Solutions is held flat inside the asset cap. Near-full payout continues "
                     "because retained capital has nowhere productive to go.",
    },
    "bull": {
        "label": "Apex 2030 embedded finance delivers",
        "fy2026_net_income_m": 252.0,
        "net_income_growth": 0.14,
        "payout_ratio": 1.00,
        "forward_pe_for_repurchase": 17.0,
        "sbc_shares_m_per_year": 0.60,
        "rationale": "Embedded finance and credit sponsorship scale, carrying net income growth into the mid teens. "
                     "The market rerates the fee mix toward payments company multiples, which raises the value of "
                     "each share but reduces how many shares a dollar of buyback retires.",
    },
}

YEARS = [2026, 2027, 2028, 2029, 2030]


def project(scenario: dict) -> list[dict]:
    """Project net income, buybacks, share count and EPS.

    Share count is solved by fixed point because the repurchase price depends
    on earnings per share, which depends on the share count.
    """
    payout = scenario["payout_ratio"]
    pe = scenario["forward_pe_for_repurchase"]
    sbc = scenario["sbc_shares_m_per_year"]

    rows = []
    start_shares = SHARES_START_M
    net_income = scenario["fy2026_net_income_m"]

    for index, year in enumerate(YEARS):
        if index:
            net_income *= 1 + scenario["net_income_growth"]

        # FY2026 is half elapsed: only the remaining authorisation is available.
        if year == 2026:
            buyback_m = 100.0  # $200m 2026 authorisation less the $100m spent in H1
            avg_shares = 41.40  # H1 actual 42.21m blended with a lower H2 count
            for _ in range(50):
                eps = net_income / avg_shares
                price = pe * eps
                retired = buyback_m / price
                end_shares = start_shares - retired + sbc / 2
                new_avg = (42.21 + end_shares) / 2
                if abs(new_avg - avg_shares) < 1e-9:
                    break
                avg_shares = new_avg
        else:
            avg_shares = start_shares
            for _ in range(50):
                eps = net_income / avg_shares
                price = pe * eps
                # retired = payout * net_income / price, which reduces to
                # payout * avg_shares / pe once price is substituted.
                retired = payout * net_income / price
                end_shares = start_shares - retired + sbc
                new_avg = (start_shares + end_shares) / 2
                if abs(new_avg - avg_shares) < 1e-9:
                    break
                avg_shares = new_avg
            buyback_m = payout * net_income

        eps = net_income / avg_shares
        price = pe * eps
        rows.append({
            "year": year,
            "net_income_m": round(net_income, 1),
            "buyback_m": round(buyback_m, 1),
            "repurchase_price": round(price, 2),
            "shares_retired_m": round(retired, 2),
            "start_shares_m": round(start_shares, 2),
            "end_shares_m": round(end_shares, 2),
            "avg_diluted_shares_m": round(avg_shares, 2),
            "eps_diluted": round(eps, 2),
            "share_count_change_pct": round((end_shares / start_shares - 1) * 100, 2),
        })
        start_shares = end_shares

    for previous, current in zip(rows, rows[1:]):
        current["eps_growth_pct"] = round((current["eps_diluted"] / previous["eps_diluted"] - 1) * 100, 1)
        current["net_income_growth_pct"] = round((current["net_income_m"] / previous["net_income_m"] - 1) * 100, 1)
        current["buyback_contribution_pp"] = round(
            current["eps_growth_pct"] - current["net_income_growth_pct"], 1
        )
    rows[0]["eps_growth_pct"] = round((rows[0]["eps_diluted"] / 4.92 - 1) * 100, 1)
    rows[0]["net_income_growth_pct"] = round((rows[0]["net_income_m"] / 228.213 - 1) * 100, 1)
    rows[0]["buyback_contribution_pp"] = round(
        rows[0]["eps_growth_pct"] - rows[0]["net_income_growth_pct"], 1
    )
    return rows


def guidance_reconciliation(base_rows: list[dict]) -> dict:
    """What net income growth would management's 2027 guidance actually require?

    This is the sharpest question the model can ask. The Apex 2030 framing
    presents 15% to 30% annualised EPS growth as the sum of an "established"
    10% to 15% and an "incremental" 5% to 15%. But the step from FY2026 to
    FY2027 guidance is far larger than the buyback can carry.
    """
    fy2026_eps = sum(GUIDANCE["fy2026_eps_range"]) / 2
    fy2027_eps = sum(GUIDANCE["fy2027_eps_range"]) / 2
    implied_eps_growth = fy2027_eps / fy2026_eps - 1

    row_2026, row_2027 = base_rows[0], base_rows[1]
    share_reduction = 1 - row_2027["avg_diluted_shares_m"] / row_2026["avg_diluted_shares_m"]
    required_ni_growth = (1 + implied_eps_growth) * (1 - share_reduction) - 1

    fy2026_ni = fy2026_eps * row_2026["avg_diluted_shares_m"]
    fy2027_ni = fy2027_eps * row_2027["avg_diluted_shares_m"]

    return {
        "fy2026_guidance_eps_midpoint": round(fy2026_eps, 2),
        "fy2027_guidance_eps_midpoint": round(fy2027_eps, 2),
        "implied_eps_growth_pct": round(implied_eps_growth * 100, 1),
        "share_count_reduction_pct": round(share_reduction * 100, 1),
        "required_net_income_growth_pct": round(required_ni_growth * 100, 1),
        "implied_fy2026_net_income_m": round(fy2026_ni, 1),
        "implied_fy2027_net_income_m": round(fy2027_ni, 1),
        "implied_net_income_step_m": round(fy2027_ni - fy2026_ni, 1),
        "historical_net_income_growth_pct": {
            "2023_to_2024": round((217.540 / 192.296 - 1) * 100, 1),
            "2024_to_2025": round((228.213 / 217.540 - 1) * 100, 1),
            "2025_to_2026e": round((248.0 / 228.213 - 1) * 100, 1),
        },
        "read": (
            "Management's own guidance implies net income must grow by roughly "
            f"{round(required_ni_growth * 100)}% between 2026 and 2027, because the repurchase can only supply about "
            f"{round(share_reduction * 100, 1)} points of the {round(implied_eps_growth * 100, 1)}% earnings-per-share "
            "step. Net income has grown 13.1%, 4.9% and an estimated 8.7% in the three prior years. The 2027 target "
            "is therefore not an extrapolation of the established business plus buyback; it requires a step change in "
            "fintech revenue that has not yet appeared in reported results."
        ),
    }


def capital_capacity() -> dict:
    """Can the payout actually continue? Regulatory capital, not earnings, binds."""
    equity_to_assets = EQUITY_2025_M / TOTAL_ASSETS_2025_M
    headroom_m = ASSET_CAP_M - TOTAL_ASSETS_2025_M
    return {
        "total_assets_2025_m": TOTAL_ASSETS_2025_M,
        "asset_cap_m": ASSET_CAP_M,
        "headroom_to_cap_m": round(headroom_m, 1),
        "headroom_to_cap_pct": round(headroom_m / ASSET_CAP_M * 100, 1),
        "equity_2025_m": EQUITY_2025_M,
        "equity_2024_m": 789.783,
        "equity_change_m": round(EQUITY_2025_M - 789.783, 1),
        "equity_to_assets_pct": round(equity_to_assets * 100, 2),
        "read": (
            "Equity fell $100.0m in 2025 while the company earned $228.2m, so capital returned exceeded net income. "
            "That is not repeatable indefinitely. Equity to assets is 7.4% and assets grew 7.2% in 2025 to within "
            "$647.6m of the cap. If assets keep drifting toward $10bn the bank must hold more capital, not less, and "
            "the payout ratio has to fall below 100%. The buyback is bounded by regulatory capital, not by earnings, "
            "and the base case reflects that with a 95% payout rather than the 100%+ of 2025."
        ),
    }


def main() -> int:
    projections = {}
    for name, scenario in SCENARIOS.items():
        rows = project(scenario)
        projections[name] = {
            "label": scenario["label"],
            "rationale": scenario["rationale"],
            "assumptions": {
                "fy2026_net_income_m": scenario["fy2026_net_income_m"],
                "net_income_growth_pct": round(scenario["net_income_growth"] * 100, 1),
                "payout_ratio_pct": round(scenario["payout_ratio"] * 100, 1),
                "forward_pe_for_repurchase": scenario["forward_pe_for_repurchase"],
                "sbc_shares_m_per_year": scenario["sbc_shares_m_per_year"],
            },
            "gross_annual_share_retirement_pct": round(
                scenario["payout_ratio"] / scenario["forward_pe_for_repurchase"] * 100, 2
            ),
            "years": rows,
            "fy2030_eps": rows[-1]["eps_diluted"],
            "fy2030_shares_m": rows[-1]["end_shares_m"],
            "eps_cagr_2025_to_2030_pct": round(((rows[-1]["eps_diluted"] / 4.92) ** (1 / 5) - 1) * 100, 1),
            "net_income_cagr_2025_to_2030_pct": round(((rows[-1]["net_income_m"] / 228.213) ** (1 / 5) - 1) * 100, 1),
            "cumulative_buyback_m": round(sum(row["buyback_m"] for row in rows), 1),
            "cumulative_share_reduction_pct": round((rows[-1]["end_shares_m"] / SHARES_START_M - 1) * 100, 1),
        }

    payload = {
        "schema_version": "1.0",
        "ticker": TICKER,
        "as_of": AS_OF,
        "price": PRICE,
        "price_source": "Yahoo TBBK close 2026-08-06",
        "purpose": "Five-year map of share repurchases and earnings growth, and how much of the growth each supplies.",
        "identity": {
            "formula": "shares retired = payout * net income / repurchase price = payout * average shares / forward P/E",
            "read": (
                "Net income cancels out of the share retirement rate. How fast the share count falls is set by the "
                "payout ratio and the multiple, not by how much the company earns. At a 95% payout and 13 times "
                "forward earnings the company retires 7.3% of its shares a year; at 17 times it retires 5.9%. A "
                "rerating upward is good for the share price and bad for the buyback engine, and those two effects "
                "partly cancel."
            ),
        },
        "history": HISTORY,
        "authorisations": AUTHORISATIONS,
        "cumulative_since_2022": {
            "buyback_m": CUMULATIVE_SINCE_2022_M,
            "share_pct_repurchased": CUMULATIVE_SHARE_PCT,
            "capital_returned_pct_of_net_income": CAPITAL_RETURNED_PCT_OF_NI,
            "source": f"{DECK} capital return page, metrics through 2026-06-30",
        },
        "guidance": GUIDANCE,
        "capital_capacity": capital_capacity(),
        "scenarios": projections,
        "guidance_reconciliation": guidance_reconciliation(projections["base"]["years"]),
    }

    out = ROOT / TICKER / "research" / "buyback_eps_model.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    for name in ("bear", "base", "bull"):
        block = projections[name]
        print(f"\n=== {name.upper()}  {block['label']}")
        print(f"    gross retirement {block['gross_annual_share_retirement_pct']}%/yr  "
              f"EPS CAGR 25-30 {block['eps_cagr_2025_to_2030_pct']}%  "
              f"NI CAGR {block['net_income_cagr_2025_to_2030_pct']}%")
        print(f"    {'year':<6}{'NI $m':>9}{'buyback':>10}{'px':>9}{'avg sh':>9}{'EPS':>8}{'EPS gr':>8}{'bb pp':>8}")
        for row in block["years"]:
            print(f"    {row['year']:<6}{row['net_income_m']:>9.1f}{row['buyback_m']:>10.1f}"
                  f"{row['repurchase_price']:>9.2f}{row['avg_diluted_shares_m']:>9.2f}"
                  f"{row['eps_diluted']:>8.2f}{row.get('eps_growth_pct', 0):>8.1f}"
                  f"{row.get('buyback_contribution_pp', 0):>8.1f}")

    rec = payload["guidance_reconciliation"]
    print(f"\nGuidance check: FY2027 guide needs {rec['required_net_income_growth_pct']}% net income growth "
          f"(buyback supplies {rec['share_count_reduction_pct']}pp of the {rec['implied_eps_growth_pct']}% EPS step)")
    print(f"Wrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
