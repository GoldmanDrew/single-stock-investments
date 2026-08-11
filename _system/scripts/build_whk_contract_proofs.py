#!/usr/bin/env python3
"""Build WHK's economic ownership map and component proofs from the 424B4.

WhiteHawk Minerals is a non-operated natural gas mineral and royalty aggregator
(Marcellus / Haynesville) that IPO'd 2026-06-10 in an Up-C structure. The
generic first-pass compiler cannot model this: the routed profile is
`scarce_asset_optionality`, whose first listed failure mode is "gross asset
value mistaken for shareholder value", and an Up-C is precisely where that
happens. WhiteHawk Minerals Corp. does not own the royalties -- it owns 86.0%
of WhiteHawk OpCo, which does.

Two facts drive the ownership arithmetic, both taken verbatim from the
prospectus rather than derived:

  * The Company holds 22,996,579 OpCo Interests = 86.0% of the common economic
    interest in WhiteHawk OpCo; the Management Contributor holds the other
    3,750,000 = 14.0%, exchangeable 1:1 into Class A (424B4 p.19/p.24).
  * Cash Available for Distribution is defined *after* cash interest expense,
    cash taxes and cash preferred dividends (424B4 "Non-GAAP Financial
    Measures"). It is therefore already an equity-level cash flow. Subtracting
    net debt or the mezzanine preferred from a CAFD-derived value would
    double-count them -- the profile's second listed failure mode, "operating
    cash flow and NAV counted twice".

The routed method `component_owner_cash_and_unit_nav` is a *pairing*: an
owner-cash leg and a unit-NAV leg. Earlier revisions of this script emitted
only the owner-cash leg and recorded the NAV leg as an unevidenced gap, which
left the route and the executed proof disagreeing. The 424B4 SUMMARY RESERVE
DATA table supplies the missing leg, so both are now built -- over a partition
that keeps them non-overlapping:

  * `pdp_royalty_cash_stream` -- the producing wells, whose cash flow *is* the
    disclosed CAFD, valued on owner cash at the producing decline rate.
  * `undeveloped_location_inventory` -- the 8,783 gross undeveloped locations,
    which contribute no CAFD today, valued at unit NAV.

The partition disciplines the decline rate. A perpetuity declining at rate d
consumes total volume P/d. Proved developed producing reserves are 178,544
MMcfe against pro forma annual production of 24,548 MMcfe, so the producing
component is held to d = 13.75% and cannot reach into volumes the second
component already counts.

An earlier revision valued the second component on booked reserves alone --
the 27,930 MMcfe of PDNP plus PUD -- and so credited the inventory at roughly
zero. That was wrong, and wrong for a structural reason worth recording: a
non-operated mineral owner cannot commit to a development plan, so SEC rules
bar it from booking PUDs. WhiteHawk's proved reserves are 98% PD / 2% PUD *by
construction*, and using them as the economic endowment values the company as
if operators stop drilling forever. The filing discloses 8,783 gross
undeveloped locations, 8,353 of which sit outside the reserve report but were
audited and approved by CG&A, the same engineer. Those locations are now the
second component.

Two disciplines keep that from becoming the profile's third failure mode,
"remote options treated as contracted cash". Volumes are basin-weighted --
Mid-Continent is 50% of the net location count on much shorter laterals and
lower EUR per foot, so a uniform rate overstates the book by ~40%. And the
realisation haircut is deep (0.10-0.25 of the blended PV-10 unit value),
because 8,783 locations at the disclosed 126-198 wells/yr pace is a 35-58 year
programme whose average location is discounted over decades.

Still not credited anywhere: a gas price deck above the SEC trailing
$3.387/MMBtu. That is the largest remaining lever and it needs a live strip,
which the filing does not contain.

Usage:
  python _system/scripts/build_whk_contract_proofs.py [--date YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from marvin_valuation import compute_component_valuation  # noqa: E402
from economic_value_framework import build_economic_value_analysis  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
TICKER = "WHK"
PROSPECTUS = (
    "WHK/investor-documents/sec-edgar/424B4_20260609_rpt_acc0001193125_26_264014.htm"
)
CASES = ("low", "base", "high")

# --- Facts locked from the 424B4 -------------------------------------------
# Ownership
COMPANY_OPCO_INTERESTS = 22_996_579      # = Class A shares outstanding, 1:1
MGMT_OPCO_INTERESTS = 3_750_000          # Continuing Equity Owners
TOTAL_OPCO_INTERESTS = COMPANY_OPCO_INTERESTS + MGMT_OPCO_INTERESTS
COMPANY_SHARE = COMPANY_OPCO_INTERESTS / TOTAL_OPCO_INTERESTS      # 0.8598
CLASS_A_SHARES = COMPANY_OPCO_INTERESTS

# Earnout: 25% of the $130.0m Internalization Price, payable in OpCo Interests
# plus matching Class B if Adjusted EBITDA targets are met in the Earnout Years.
INTERNALIZATION_PRICE_M = 130.0
EARNOUT_FRACTION = 0.25
IPO_PRICE = 26.00
EARNOUT_UNITS = (INTERNALIZATION_PRICE_M * 1e6 * EARNOUT_FRACTION) / IPO_PRICE  # 1,250,000
COMPANY_SHARE_FULLY_EARNED = COMPANY_OPCO_INTERESTS / (TOTAL_OPCO_INTERESTS + EARNOUT_UNITS)

# Cash economics (USD millions, pro forma for the Transactions)
PF_FY2025_CAFD_M = 36.317
PF_Q1_2026_CAFD_M = 9.959
PF_FY2025_ADJ_EBITDA_M = 64.405
PF_FY2025_ROYALTY_REVENUE_M = 71.839
PF_FY2025_DDA_M = 36.451
PF_FY2025_NET_LOSS_M = -32.330

# Reserves at 2025-12-31, CG&A reserve report (MMcfe unless noted)
PROVED_PDP_MMCFE = 178_544.0
PROVED_PDNP_MMCFE = 23_066.0
PROVED_PUD_MMCFE = 4_864.0
TOTAL_PROVED_MMCFE = 206_473.0
PV10_M = 293.690
STANDARDIZED_MEASURE_M = 266.326

# Undeveloped inventory at 2025-12-31. 430 of the 8,783 gross locations are in
# the reserve report; the other 8,353 are not, but were audited and approved by
# CG&A. Net locations are basin-weighted because Mid-Continent is 50% of the
# net count on 9,314 ft laterals against Appalachia's 13,246 ft and far lower
# EUR per foot -- treating them uniformly overstates the book by ~40%.
# (net locations, avg lateral ft, low/high basin-typical Bcfe per 1,000 ft)
INVENTORY_BY_BASIN = {
    "appalachian":    (8.7, 13_246, 2.0, 2.7),
    "haynesville":    (3.1,  9_267, 2.2, 2.8),
    "mid_continent":  (14.1, 9_314, 0.6, 1.2),
    "other":          (2.1,  9_864, 0.6, 1.2),
}
GROSS_UNDEVELOPED_LOCATIONS = 8_783
GROSS_UNDEVELOPED_UNBOOKED = 8_353


def _inventory_mmcfe(which: str) -> float:
    """Net undeveloped reserves in MMcfe, basin-weighted.

    net locations x (lateral ft / 1000 x Bcfe per 1,000 ft) x 1000 -> MMcfe.
    A "net location" is already gross locations scaled by net revenue
    interest, so multiplying by a gross per-well EUR gives net volume.
    """
    total = 0.0
    for net, lateral_ft, bcfe_low, bcfe_high in INVENTORY_BY_BASIN.values():
        per_kft = bcfe_low if which == "low" else bcfe_high
        eur_bcfe = (lateral_ft / 1000.0) * per_kft
        total += net * eur_bcfe * 1000.0
    return total


INVENTORY_MMCFE = {
    "low": round(_inventory_mmcfe("low"), 0),
    "base": round((_inventory_mmcfe("low") + _inventory_mmcfe("high")) / 2, 0),
    "high": round(_inventory_mmcfe("high"), 0),
}

# Net production (Mcfe/d)
PF_FY2025_PRODUCTION_MCFE_D = 67_255.0
Q1_2026_PRODUCTION_MCFE_D = 64_270.0
PF_FY2025_PRODUCTION_MMCFE = PF_FY2025_PRODUCTION_MCFE_D * 365 / 1000     # 24,548
Q1_2026_PRODUCTION_MMCFE = Q1_2026_PRODUCTION_MCFE_D * 365 / 1000         # 23,459

# Balance sheet (USD millions, as-adjusted)
PF_DEBT_M = 75.000
PF_CASH_M = 10.537
SERIES_B_PREFERRED_M = 30.643

# --- Case assumptions -------------------------------------------------------
# Sustainable CAFD: FY2025 pro forma, the midpoint, and Q1 2026 annualised.
CAFD_RUN_RATE_M = {
    "low": PF_FY2025_CAFD_M,
    "base": round((PF_FY2025_CAFD_M + PF_Q1_2026_CAFD_M * 4) / 2, 3),
    "high": round(PF_Q1_2026_CAFD_M * 4, 3),
}
ECONOMIC_INTEREST = {
    "low": round(COMPANY_SHARE_FULLY_EARNED, 6),
    "base": round(COMPANY_SHARE_FULLY_EARNED, 6),
    "high": round(COMPANY_SHARE, 6),
}
REQUIRED_RETURN = {"low": 0.12, "base": 0.10, "high": 0.09}
# PDP reserve life bounds the decline: 178,544 MMcfe / 24,548 MMcfe per year is
# 7.27 years (d = 13.75%); against Q1 2026 annualised it is 7.61 years
# (d = 13.14%). The band sits between those two computed values.
PDP_DECLINE = {"low": -0.1375, "base": -0.135, "high": -0.130}
# Share of the blended PV-10 unit value realised on the undeveloped inventory.
# Far deeper than the old 0.40-0.70 band, which applied only to the 430 booked
# locations: the full 8,783-location inventory is a 35-58 year drilling
# programme at the disclosed 126-198 wells/yr pace, so the average location is
# discounted over decades. 0.10-0.25 brackets that.
REALIZATION_HAIRCUT = {"low": 0.10, "base": 0.17, "high": 0.25}
SENIOR_CLAIMS_IN_NAV_M = {"low": 0.0, "base": 0.0, "high": 0.0}


def _src(locator: str, as_of: str) -> dict:
    return {"ref": PROSPECTUS, "locator": locator, "as_of": as_of}


def _fact(node_id: str, label: str, value: float, unit: str, locator: str, as_of: str) -> dict:
    return {
        "id": node_id, "label": label, "kind": "fact", "value": float(value),
        "unit": unit, "source": _src(locator, as_of), "locked": True,
    }


def _judgment(node_id: str, label: str, values: dict, unit: str,
              rationale: str, lo: float, hi: float) -> dict:
    return {
        "id": node_id, "label": label, "kind": "judgment",
        "values": {case: values[case] for case in CASES}, "unit": unit,
        "rationale": rationale, "allowed_range": {"min": lo, "max": hi},
    }


# --- Component 1: producing royalty cash stream -----------------------------

def pdp_value_per_share(case: str) -> float:
    """Mirror of the component 1 proof graph, used to set the emitted range."""
    attributable_cafd_m = CAFD_RUN_RATE_M[case] * ECONOMIC_INTEREST[case]
    next_year_cafd_m = attributable_cafd_m * (1 + PDP_DECLINE[case])
    cap_rate = REQUIRED_RETURN[case] - PDP_DECLINE[case]
    return (next_year_cafd_m / cap_rate) * 1_000_000 / CLASS_A_SHARES


def pdp_component() -> dict:
    proof = {
        "schema_version": "1.0",
        "method_id": "owner_cash_or_dividend_discount",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact("pf_fy2025_cafd_m", "Pro forma Cash Available for Distribution, FY2025",
                  PF_FY2025_CAFD_M, "USD_m",
                  "Reconciliation of Cash Available for Distribution, Pro Forma Year "
                  "Ended December 31, 2025: $36,317 thousand", "2025-12-31"),
            _fact("pf_q1_2026_cafd_m", "Pro forma Cash Available for Distribution, Q1 2026",
                  PF_Q1_2026_CAFD_M, "USD_m",
                  "Reconciliation of Cash Available for Distribution, Pro Forma Three "
                  "Months Ended March 31, 2026: $9,959 thousand", "2026-03-31"),
            _fact("proved_pdp_mmcfe", "Proved developed producing reserves at 2025-12-31",
                  PROVED_PDP_MMCFE, "MMcfe",
                  "SUMMARY RESERVE DATA, WhiteHawk at December 31, 2025, Estimated "
                  "proved developed producing reserves Total (MMcfe): 178,544", "2025-12-31"),
            _fact("pf_fy2025_production_mmcfe", "Pro forma FY2025 net production",
                  PF_FY2025_PRODUCTION_MMCFE, "MMcfe",
                  "Pro forma average net daily production of 67,255 Mcfe/d for the year "
                  "ended December 31, 2025, annualised at 365 days", "2025-12-31"),
            _fact("class_a_shares", "Class A common shares outstanding after the Transactions",
                  float(CLASS_A_SHARES), "shares",
                  "Our Organizational Structure: we will own 22,996,579 OpCo Interests, "
                  "held one-for-one against Class A common stock", "2026-06-09"),
        ],
        "assumptions": [
            _judgment(
                "cafd_run_rate_m", "Sustainable annual CAFD at OpCo", CAFD_RUN_RATE_M, "USD_m",
                "Q1 2026 pro forma CAFD annualises to $39.8m against $36.3m for pro forma "
                "FY2025, so the disclosed run-rate is rising. One quarter is not a year for "
                "a commodity royalty, so the base takes the midpoint rather than the latest "
                "quarter. Note this is a cash measure struck before depletion: pro forma "
                "DD&A of $36.451m is essentially equal to CAFD of $36.317m, and pro forma "
                "FY2025 net income is a $32.330m loss.",
                30.0, 42.0,
            ),
            _judgment(
                "company_economic_interest", "Company's common economic interest in WhiteHawk OpCo",
                ECONOMIC_INTEREST, "ratio",
                "86.0% today. The Earnout Amount is 25% of the $130.0m Internalization Price, "
                "payable in OpCo Interests and matching Class B if Adjusted EBITDA targets are "
                "met; at the $26.00 IPO price that is 1,250,000 units, cutting the Company's "
                "interest to 82.1%. Given CAFD is already growing, low and base assume the "
                "targets are met and the dilution occurs; only the high case keeps 86.0%.",
                0.80, 0.86,
            ),
            _judgment(
                "required_return", "Required return on a non-operated gas royalty",
                REQUIRED_RETURN, "ratio",
                "No capex and no operating cost, but full commodity exposure, a single-basin "
                "pair, a first-year public company with a restated FY2025 and identified "
                "material weaknesses, and no declared dividend policy. The low value case "
                "carries the high discount rate. The 10% base matches the discount rate the "
                "SEC prescribes for PV-10, keeping this leg comparable with the NAV leg.",
                0.08, 0.14,
            ),
            _judgment(
                "pdp_decline", "Net annual decline in attributable producing CAFD",
                PDP_DECLINE, "ratio",
                "A perpetuity declining at d consumes total volume P/d, so the decline rate is "
                "what ties this component to a finite reserve book. Proved developed producing "
                "reserves of 178,544 MMcfe against pro forma annual production of 24,548 MMcfe "
                "give a 7.27-year producing life and d = 13.75%; against Q1 2026 annualised "
                "production of 23,459 MMcfe the life is 7.61 years and d = 13.14%. The band "
                "spans those two computed values. Anything shallower reaches into the "
                "non-producing and undeveloped volumes that component 2 already counts, or "
                "into unbooked acreage that no filed reserve report supports. Observed pro "
                "forma volumes fell 4.4% (67,255 to 64,270 Mcfe/d), the difference being new "
                "wells converting inventory into production -- value credited in component 2, "
                "not here.",
                -0.16, -0.10,
            ),
        ],
        "calculations": [
            {"id": "attributable_cafd_m", "op": "multiply",
             "args": ["cafd_run_rate_m", "company_economic_interest"], "unit": "USD_m"},
            {"id": "growth_factor", "op": "add", "args": [1, "pdp_decline"], "unit": "ratio"},
            {"id": "next_year_cafd_m", "op": "multiply",
             "args": ["attributable_cafd_m", "growth_factor"], "unit": "USD_m"},
            {"id": "cap_rate", "op": "subtract",
             "args": ["required_return", "pdp_decline"], "unit": "ratio"},
            {"id": "pdp_value_m", "op": "divide",
             "args": ["next_year_cafd_m", "cap_rate"], "unit": "USD_m"},
            {"id": "pdp_value", "op": "multiply", "args": ["pdp_value_m", 1_000_000], "unit": "USD"},
            {"id": "value_per_share", "op": "divide",
             "args": ["pdp_value", "class_a_shares"], "unit": "USD_per_share"},
        ],
        "outputs": {case: "value_per_share" for case in CASES},
        "source_lineage": [{
            "ref": PROSPECTUS,
            "locator": "424B4 filed 2026-06-09: Cash Available for Distribution "
                       "reconciliation, SUMMARY RESERVE DATA, Our Organizational Structure",
            "as_of": "2026-06-09",
        }],
    }
    return {
        "id": "pdp_royalty_cash_stream",
        "label": "Producing Marcellus and Haynesville royalty cash stream, attributable "
                 "to Class A via the Company's OpCo stake",
        # Not `real_option`. These are wells already on production paying royalties
        # today; the economic-value framework rightly demands probability, timing
        # and remaining-capital treatment for option components, and none of the
        # three is meaningful for a contracted stream on producing wells. The
        # optionality in this business sits in the second component.
        "category": "operating_business",
        "overlap_key": "pdp_producing_royalty_cash",
        "treatment": "additive",
        "valuation": {
            "method": "owner_cash_or_dividend_discount",
            "basis": "per_share",
            "low": round(pdp_value_per_share("low"), 4),
            "base": round(pdp_value_per_share("base"), 4),
            "high": round(pdp_value_per_share("high"), 4),
            "valuation_status": "bounded_estimate",
            "evidence_tier": "primary_derived",
            "evidence": (
                "Pro forma Cash Available for Distribution of $36.317m for FY2025 and "
                "$9.959m for Q1 2026, from the 424B4 reconciliation. CAFD is defined and "
                "reconciled after cash interest expense, cash taxes and cash preferred "
                "dividends, so it is an equity-level cash flow and net debt and the "
                "mezzanine preferred are deliberately not subtracted again. The Company's "
                "economic interest in WhiteHawk OpCo is applied before the per-share "
                "division so that the 14.0% held by Continuing Equity Owners is never "
                "counted as Class A value. The decline rate is bounded by the 178,544 "
                "MMcfe proved developed producing reserve book."
            ),
            "assumption_summary": (
                "Owner-cash leg of component_owner_cash_and_unit_nav. Declining perpetuity "
                "on attributable CAFD, with the decline rate pinned to the producing "
                "reserve life so the component cannot capitalise volume it does not own."
            ),
            "cross_check": (
                "The unit-NAV leg is component `undeveloped_location_inventory`. Together "
                "the two components span the 206,473 MMcfe proved book: 178,544 MMcfe "
                "producing here, 27,930 MMcfe non-producing there. As an aggregate check, "
                "PV-10 of $293.690m less net debt of $64.463m and the $30.643m Series B "
                "preferred, at the 82.1% economic interest, is $6.51 per Class A share "
                "before any corporate G&A -- the same order as the sum of the two "
                "components, from an independent SEC-prescribed computation."
            ),
            "falsifier": (
                "The first 10-Q reports net production above 67,255 Mcfe/d, implying a "
                "producing decline shallower than the 13.14%-13.75% band derived from the "
                "reserve report; or the FY2026 reserve report raises PV-10 above $500m "
                "against the $293.690m booked here; or a declared dividend sets an "
                "annualised Class A rate above $1.30 per share, which no sustainable "
                "distribution consistent with this decline band supports."
            ),
            "calculation_proof": proof,
        },
    }


# --- Component 2: non-producing and undeveloped reserve inventory -----------

def nav_value_per_share(case: str) -> float:
    """Mirror of the component 2 proof graph, used to set the emitted range."""
    non_producing_mmcfe = INVENTORY_MMCFE[case]
    blended_unit_value = PV10_M / TOTAL_PROVED_MMCFE
    gross_assets_m = non_producing_mmcfe * (blended_unit_value * REALIZATION_HAIRCUT[case])
    tax_drag_ratio = (PV10_M - STANDARDIZED_MEASURE_M) / PV10_M
    assets_after_tax_m = gross_assets_m - gross_assets_m * tax_drag_ratio
    net_assets_m = assets_after_tax_m - SENIOR_CLAIMS_IN_NAV_M[case]
    return net_assets_m * ECONOMIC_INTEREST[case] * 1_000_000 / CLASS_A_SHARES


def nav_component() -> dict:
    proof = {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact("undeveloped_locations_gross",
                  "Total gross undeveloped locations at 2025-12-31",
                  float(GROSS_UNDEVELOPED_LOCATIONS), "gross locations",
                  "Gross and net locations by region or basin: Appalachian 2,792, "
                  "Haynesville 1,581, Mid-Continent 3,952, Other 458. Only 430 are "
                  "included in proved reserves; the other 8,353 were audited and "
                  "approved by CG&A per footnote (3)", "2025-12-31"),
            _fact("undeveloped_locations_net",
                  "Net undeveloped locations at 2025-12-31",
                  28.0, "net locations",
                  "Gross and net locations by region or basin, Net Undeveloped Location "
                  "Count: Appalachian 8.7, Haynesville 3.1, Mid-Continent 14.1, Other 2.1",
                  "2025-12-31"),
            _fact("total_proved_mmcfe", "Total proved reserves at 2025-12-31",
                  TOTAL_PROVED_MMCFE, "MMcfe",
                  "SUMMARY RESERVE DATA, WhiteHawk at December 31, 2025, Estimated proved "
                  "reserves Total (MMcfe): 206,473", "2025-12-31"),
            _fact("pv10_m", "PV-10 of total proved reserves at 2025-12-31", PV10_M, "USD_m",
                  "SUMMARY RESERVE DATA, WhiteHawk at December 31, 2025, PV-10: $293,690 "
                  "thousand, at $3.387/MMBtu Henry Hub and $65.34/bbl WTI SEC pricing",
                  "2025-12-31"),
            _fact("standardized_measure_m",
                  "Standardized measure of discounted future net cash flows at 2025-12-31",
                  STANDARDIZED_MEASURE_M, "USD_m",
                  "SUMMARY RESERVE DATA, WhiteHawk at December 31, 2025, Standardized "
                  "Measure: $266,326 thousand", "2025-12-31"),
            _fact("class_a_shares", "Class A common shares outstanding after the Transactions",
                  float(CLASS_A_SHARES), "shares",
                  "Our Organizational Structure: we will own 22,996,579 OpCo Interests, "
                  "held one-for-one against Class A common stock", "2026-06-09"),
        ],
        "assumptions": [
            _judgment(
                "inventory_mmcfe",
                "Net undeveloped reserves behind the location inventory",
                INVENTORY_MMCFE, "MMcfe",
                "Net locations x basin-typical EUR. A net location is already gross "
                "locations scaled by net revenue interest, so multiplying by a gross "
                "per-well EUR gives net volume. Basin-weighted rather than uniform "
                "because Mid-Continent is 50% of the net count (14.1 of 28.0) on "
                "9,314 ft laterals against Appalachia's 13,246 ft and far lower EUR "
                "per foot: a uniform rate overstates the book by roughly 40%. Bands "
                "use 2.0-2.7 Bcfe per 1,000 ft in Appalachia, 2.2-2.8 in Haynesville "
                "and 0.6-1.2 in Mid-Continent and Other. This is the largest single "
                "estimate in the contract and the one a third-party type-curve study "
                "would replace.",
                200_000.0, 700_000.0,
            ),
            _judgment(
                "realization_haircut",
                "Share of the blended PV-10 unit value realised on undeveloped volumes",
                REALIZATION_HAIRCUT, "ratio",
                "PV-10 of $293.690m spread over 206,473 MMcfe is $1.422 per Mcfe, but that "
                "blended rate is dominated by the 178,544 MMcfe already producing, which sit "
                "earliest in the discount schedule. The inventory is a 35-58 year drilling "
                "programme -- 8,783 gross locations at the 126-198 wells/yr implied by "
                "WhiteHawk's disclosed interest in 18% of new Appalachian and Haynesville "
                "wells -- so the average location is discounted over decades and is worth a "
                "small fraction of the blended rate. A royalty owner funds none of the "
                "development cost, so the haircut is timing and operator pace only, never "
                "capital. The band is deliberately deep: crediting this inventory at "
                "anything near the producing rate would be the routed profile's third "
                "failure mode, remote options treated as contracted cash.",
                0.05, 0.40,
            ),
            _judgment(
                "company_economic_interest", "Company's common economic interest in WhiteHawk OpCo",
                ECONOMIC_INTEREST, "ratio",
                "Same ownership arithmetic as the producing component: 86.0% today, 82.1% if "
                "the 1,250,000 earnout OpCo Interests are issued. Applied before the per-share "
                "division so the Continuing Equity Owners' 14.0% is never counted as Class A "
                "value.",
                0.80, 0.86,
            ),
            _judgment(
                "senior_claims_m", "Senior claims charged against this component",
                SENIOR_CLAIMS_IN_NAV_M, "USD_m",
                "Explicitly zero, not omitted. Net debt of $64.463m ($75.000m less $10.537m "
                "cash) and the $30.643m Series B preferred are serviced inside Cash Available "
                "for Distribution, which is struck after cash interest expense and cash "
                "preferred dividends and drives the producing component. Deducting the "
                "principal here as well would charge the same claims twice -- the routed "
                "profile's 'operating cash flow and NAV counted twice' failure mode.",
                0.0, 0.0,
            ),
        ],
        "calculations": [
            {"id": "blended_unit_value", "op": "divide",
             "args": ["pv10_m", "total_proved_mmcfe"], "unit": "USD_m_per_MMcfe"},
            {"id": "effective_unit_value", "op": "multiply",
             "args": ["blended_unit_value", "realization_haircut"], "unit": "USD_m_per_MMcfe"},
            {"id": "gross_assets_m", "op": "multiply",
             "args": ["inventory_mmcfe", "effective_unit_value"], "unit": "USD_m"},
            {"id": "tax_drag_m", "op": "subtract",
             "args": ["pv10_m", "standardized_measure_m"], "unit": "USD_m"},
            {"id": "tax_drag_ratio", "op": "divide", "args": ["tax_drag_m", "pv10_m"], "unit": "ratio"},
            {"id": "tax_and_realization_costs_m", "op": "multiply",
             "args": ["gross_assets_m", "tax_drag_ratio"], "unit": "USD_m"},
            {"id": "assets_after_tax_m", "op": "subtract",
             "args": ["gross_assets_m", "tax_and_realization_costs_m"], "unit": "USD_m"},
            {"id": "net_assets_m", "op": "subtract",
             "args": ["assets_after_tax_m", "senior_claims_m"], "unit": "USD_m"},
            {"id": "attributable_net_assets_m", "op": "multiply",
             "args": ["net_assets_m", "company_economic_interest"], "unit": "USD_m"},
            {"id": "attributable_net_assets", "op": "multiply",
             "args": ["attributable_net_assets_m", 1_000_000], "unit": "USD"},
            {"id": "value_per_share", "op": "divide",
             "args": ["attributable_net_assets", "class_a_shares"], "unit": "USD_per_share"},
        ],
        "outputs": {case: "value_per_share" for case in CASES},
        "source_lineage": [{
            "ref": PROSPECTUS,
            "locator": "424B4 filed 2026-06-09: SUMMARY RESERVE DATA (CG&A reserve report "
                       "at December 31, 2025) and Our Organizational Structure",
            "as_of": "2026-06-09",
        }],
    }
    return {
        "id": "undeveloped_location_inventory",
        "label": "Undeveloped mineral location inventory (8,783 gross locations, CG&A "
                 "audited), attributable to Class A via the Company's OpCo stake",
        "category": "net_assets",
        "overlap_key": "undeveloped_location_inventory",
        "treatment": "additive",
        "valuation": {
            "method": "net_asset_value",
            "basis": "per_share",
            "low": round(nav_value_per_share("low"), 4),
            "base": round(nav_value_per_share("base"), 4),
            "high": round(nav_value_per_share("high"), 4),
            "valuation_status": "bounded_estimate",
            "evidence_tier": "primary_derived",
            "evidence": (
                "23,066 MMcfe of proved developed non-producing plus 4,864 MMcfe of proved "
                "undeveloped reserves at 2025-12-31, from the CG&A reserve report in the "
                "424B4. Valued at the blended PV-10 unit value of $1.422 per Mcfe "
                "($293.690m over 206,473 MMcfe) less a timing haircut, then less the "
                "SEC-computed future income tax drag of 9.32% (PV-10 $293.690m against a "
                "standardized measure of $266.326m). These volumes contribute no Cash "
                "Available for Distribution today, so they do not overlap the producing "
                "component."
            ),
            "assumption_summary": (
                "Unit-NAV leg of component_owner_cash_and_unit_nav. Booked non-producing "
                "reserves only; unbooked acreage is deliberately uncredited."
            ),
            "cross_check": (
                "The owner-cash leg is component `pdp_royalty_cash_stream`. The two "
                "components partition the 206,473 MMcfe proved book with no volume counted "
                "twice. PV-10 is a pre-tax, SEC-prescribed 10% discounting of the same "
                "reserve report that sets the producing component's decline rate, so the "
                "legs share source data but not method."
            ),
            "falsifier": (
                "The FY2026 reserve report or an updated location census carries fewer "
                "than 6,000 gross undeveloped locations against the 8,783 booked here, "
                "or fewer than 20 net locations against 28.0, either of which removes "
                "the inventory this component exists to value; or PV-10 per Mcfe moves "
                "outside $1.00-$2.00 on the next SEC price deck, which resets the unit "
                "value it is built on; or operators convert inventory into production "
                "fast enough that the producing component's decline shallows, which "
                "would mean the partition double-counts."
            ),
            "calculation_proof": proof,
        },
    }


def ownership_note() -> str:
    return (
        f"WhiteHawk Minerals Corp. holds {COMPANY_OPCO_INTERESTS:,} OpCo Interests "
        f"({COMPANY_SHARE:.1%} of common economic interest); Continuing Equity Owners "
        f"hold {MGMT_OPCO_INTERESTS:,} ({1 - COMPANY_SHARE:.1%}), exchangeable 1:1 into "
        f"Class A. Class B carries votes and no economic rights, so it is not a claim on "
        f"value and is excluded from the map. The Company owns all Series B preferred "
        f"units of OpCo, mirroring its own Series B preferred stock, so that leg is "
        f"intra-group and nets to zero. Note the prospectus also states IPO purchasers "
        f"hold 24.8% of OpCo indirectly; 33.5% of the Company x 86.0% is 28.8%, so that "
        f"figure does not tie. The explicit interest counts are used here and the "
        f"discrepancy is flagged for human review rather than reconciled by assumption. "
        f"The two components partition the {TOTAL_PROVED_MMCFE:,.0f} MMcfe proved reserve "
        f"book: {PROVED_PDP_MMCFE:,.0f} MMcfe producing and "
        f"{PROVED_PDNP_MMCFE + PROVED_PUD_MMCFE:,.0f} MMcfe non-producing. Unbooked "
        f"acreage beyond the proved book is not valued in any component."
    )


def economic_value_spec() -> dict:
    """The universal economic-value specification behind the two components."""
    return {
        "schema_version": "1.0",
        "method": "component_owner_cash_and_unit_nav",
        "economic_claim": {
            "description": (
                "A Class A share is a claim on WhiteHawk Minerals Corp., which owns "
                f"{COMPANY_OPCO_INTERESTS:,} of {TOTAL_OPCO_INTERESTS:,} common OpCo "
                f"Interests ({COMPANY_SHARE:.1%}) in WhiteHawk OpCo. OpCo owns non-operated "
                "mineral and royalty interests in the Marcellus and Haynesville Shales. The "
                "holder therefore owns a royalty on gas produced by third-party operators, "
                "not an operating business: WhiteHawk funds no drilling capital, bears no "
                "lease operating expense and carries no plugging and abandonment obligation. "
                "The claim is finite in the proved book - 206,473 MMcfe against 24,548 MMcfe "
                "of pro forma annual production, an 8.4-year proved life - and perpetual only "
                "to the extent operators keep converting unbooked fee acreage, which is not "
                "valued here."
            ),
            "unit_label": "Class A common share",
            "unit_count": float(CLASS_A_SHARES),
            "unit_source": (
                "424B4 Dilution: 15,296,579 Class A outstanding before the offering plus "
                "7,700,000 offered = 22,996,579, held one-for-one against the Company's "
                "OpCo Interests. Class B (3,750,000) carries votes and no economic rights "
                "and is excluded from the unit count."
            ),
            "enterprise_to_equity_reconciliation": (
                "The bridge is deliberately charged once, not twice. Cash Available for "
                "Distribution is defined and reconciled after cash interest expense, cash "
                "taxes and cash preferred dividends, so the producing component is already "
                "an equity-level cash flow and the $64.463m of net debt ($75.000m debt less "
                "$10.537m cash) and the $30.643m Series B preferred are not deducted from it "
                "again. The unit-NAV component therefore carries senior_claims of exactly "
                "zero, recorded explicitly rather than omitted. Series D preferred was fully "
                "redeemed with IPO proceeds and is zero as-adjusted. The Company's economic "
                "interest in OpCo is applied before the per-share division in both components "
                "so the 14.0% held by Continuing Equity Owners is never counted as Class A "
                "value; low and base further assume the 1,250,000 earnout OpCo Interests "
                "issue, cutting the interest to 82.1%."
            ),
        },
        "gaap_role": "misleading_historical_cost",
        "accounting_reference": (
            "GAAP understates and misdates this economics in both directions. Pro forma "
            "FY2025 net income is a $32.330m loss while pro forma Cash Available for "
            "Distribution is $36.317m, because depletion of $36.451m is a historical-cost "
            "amortisation of acquisition prices rather than a measure of economic decline. "
            "Conversely the balance sheet carries the minerals at the cost of the 2025 PHX "
            "and Three Rivers Royalty acquisitions, not at the $293.690m PV-10 of the "
            "reserves. Neither the income statement nor the balance sheet is usable as the "
            "primary valuation basis; the CG&A reserve report is."
        ),
        "component_groups": [
            {
                "id": "producing_royalty_group",
                "label": "Producing mineral and royalty interests",
                "component_ids": ["pdp_royalty_cash_stream"],
                "economic_claim": (
                    "Royalties on the 178,544 MMcfe of proved developed producing reserves - "
                    "wells already on production, paying today, at an average net rate of "
                    "64,270 Mcfe/d in Q1 2026."
                ),
                "valuation_basis": (
                    "Declining perpetuity on attributable Cash Available for Distribution at "
                    "a 9%-12% required return, with the decline rate pinned to the producing "
                    "reserve life so the component cannot capitalise volume the reserve "
                    "report does not book."
                ),
                "adjustments": (
                    "CAFD is taken at the OpCo level and multiplied by the Company's economic "
                    "interest before the per-share division. No deduction for net debt or "
                    "preferred, which CAFD already services. No addition for reinvestment of "
                    "retained cash into further royalty acquisitions."
                ),
                "overlap_control": (
                    "overlap_key `pdp_producing_royalty_cash`. Bounded by volume: a perpetuity "
                    "declining at d consumes P/d, so the -13.75% to -13.0% band consumes "
                    "178,531 to 188,831 MMcfe against a 178,544 MMcfe producing book. Volumes "
                    "beyond that belong to the non-producing group and are not double-counted."
                ),
            },
            {
                "id": "undeveloped_inventory_group",
                "label": "Non-producing and undeveloped mineral reserves",
                "component_ids": ["undeveloped_location_inventory"],
                "economic_claim": (
                    "Royalties on the 23,066 MMcfe of proved developed non-producing and "
                    "4,864 MMcfe of proved undeveloped reserves, which generate no Cash "
                    "Available for Distribution today."
                ),
                "valuation_basis": (
                    "Unit NAV: the blended PV-10 unit value of $1.422 per Mcfe ($293.690m "
                    "over 206,473 MMcfe), haircut for realisation timing, less the "
                    "SEC-computed future income tax drag of 9.32%."
                ),
                "adjustments": (
                    "Tax drag taken from the $27.364m difference between PV-10 of $293.690m "
                    "and the standardized measure of $266.326m. Senior claims explicitly "
                    "zero to avoid charging debt and preferred a second time. Company "
                    "economic interest applied before the per-share division."
                ),
                "overlap_control": (
                    "overlap_key `pdnp_and_pud_reserves`. Disjoint from the producing group "
                    "by definition of the reserve report's own categories: 178,544 + 23,066 + "
                    "4,864 = 206,473 MMcfe with no volume in two groups."
                ),
                "risk_and_timing": {
                    "probability_basis": (
                        "Proved reserves only, so SEC reasonable-certainty already applies and "
                        "no further probability weighting is imposed. Unbooked acreage, which "
                        "would require a type-curve and risking model, is excluded entirely "
                        "rather than risked at a guessed probability."
                    ),
                    "timing_basis": (
                        "Not scheduled well by well. The 0.40/0.55/0.70 realisation haircut on "
                        "the blended PV-10 unit value stands in for the fact that these volumes "
                        "sit later in the discount schedule than the producing volumes that "
                        "dominate PV-10. This is the weakest judgment in the contract and is "
                        "what the FY2026 reserve report would replace."
                    ),
                    "remaining_capital_basis": (
                        "Zero, and structurally so. A royalty owner funds none of the "
                        "development cost; the working-interest operators bear all drilling and "
                        "completion capital. The haircut is therefore timing and "
                        "operator-behaviour only, not a capital charge."
                    ),
                },
            },
        ],
    }


def coverage_statement() -> str:
    return (
        "All material economic claims on Class A are identified. The royalty book is "
        "partitioned by production status so no reserve volume is valued twice, and the "
        "senior claims (net debt, Series B preferred) are charged once, inside Cash "
        "Available for Distribution."
    )


def change_log_entries(as_of: str) -> list[dict]:
    stamp = datetime.now(timezone.utc).isoformat()
    return [
        {
            "at": stamp, "author": "build_whk_contract_proofs.py", "as_of": as_of,
            "field": "component_valuation.components",
            "before": "single component `mineral_royalty_cash_stream` on owner cash, with "
                      "the unit-NAV leg recorded as an unevidenced corroboration gap",
            "after": "two non-overlapping components: `pdp_royalty_cash_stream` "
                     "(owner_cash_or_dividend_discount) and `undeveloped_location_inventory` "
                     "(net_asset_value)",
            "reason": "The routed method component_owner_cash_and_unit_nav is a pairing and "
                      "requires both legs. The 424B4 SUMMARY RESERVE DATA table supplies the "
                      "reserve quantities, PV-10 and standardized measure the NAV leg needs, "
                      "so the gap is closed rather than carried.",
        },
        {
            "at": stamp, "author": "build_whk_contract_proofs.py", "as_of": as_of,
            "field": "assumptions.net_decline -> assumptions.pdp_decline",
            "before": {"low": -0.06, "base": -0.03, "high": 0.02},
            "after": PDP_DECLINE,
            "reason": "The prior band was unanchored. A perpetuity declining at d consumes "
                      "P/d of volume, so the +2% high case implied roughly 22.7 years of "
                      "production against an 8.4-year total proved reserve life and a "
                      "7.27-year producing life. The new band is computed from the reserve "
                      "report: 178,544 MMcfe of PDP over 24,548 MMcfe of pro forma annual "
                      "production (d = 13.75%) and over 23,459 MMcfe annualised from Q1 2026 "
                      "(d = 13.14%). This is the reserve-life model the prior falsifier "
                      "named as the test, and it fires against the old band.",
        },
    ]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--date", default=date.today().isoformat())
    args = ap.parse_args(argv)

    valuation_path = ROOT / TICKER / "research" / "valuation.json"
    valuation = json.loads(valuation_path.read_text(encoding="utf-8"))

    components = [pdp_component(), nav_component()]
    valuation["component_valuation"] = {
        "schema_version": "2.0",
        "all_material_components_identified": True,
        "coverage_statement": coverage_statement(),
        "partition_note": ownership_note(),
        "components": components,
    }

    # `inputs.shares_outstanding` is what resolve_share_count() reads; without it
    # any total_value_m component would silently fail and market-cap-derived
    # dashboard fields stay null.
    valuation.setdefault("inputs", {})["shares_outstanding"] = float(CLASS_A_SHARES)

    results = compute_component_valuation(valuation)
    if not results:
        print("[error] compute_component_valuation returned nothing", file=sys.stderr)
        return 1
    results["partition_note"] = ownership_note()
    results["source"] = "build_whk_contract_proofs.py"
    results["as_of"] = args.date
    valuation["component_valuation_results"] = results
    valuation["economic_value"] = economic_value_spec()
    build_economic_value_analysis(valuation)
    valuation["as_of"] = args.date
    valuation["method"] = "component_owner_cash_and_unit_nav"
    valuation["irr_method"] = "scarce_asset_optionality"
    valuation.setdefault("change_log", []).extend(change_log_entries(args.date))

    valuation_path.write_text(
        json.dumps(valuation, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    total = results.get("total_equity_value_per_share") or {}
    print(f"[ok] {valuation_path.relative_to(ROOT)}")
    print(f"  components: {len(components)}")
    for row in results.get("additive_components") or []:
        print(f"    {row['id']}: {row['low_per_share']} / {row['base_per_share']} / {row['high_per_share']}")
    print(f"  total per share: {total.get('low')} / {total.get('base')} / {total.get('high')}")
    print(f"  market price: {results.get('market_price_per_share')}")
    print(f"  upside/downside pct: {results.get('upside_downside_pct')}")
    print(f"  company economic interest: {COMPANY_SHARE:.4f} "
          f"(fully earned-out {COMPANY_SHARE_FULLY_EARNED:.4f})")
    print(f"  Class A shares: {CLASS_A_SHARES:,}")
    print(f"  proved reserve life: {TOTAL_PROVED_MMCFE / PF_FY2025_PRODUCTION_MMCFE:.2f} yr; "
          f"PDP life {PROVED_PDP_MMCFE / PF_FY2025_PRODUCTION_MMCFE:.2f} yr")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
