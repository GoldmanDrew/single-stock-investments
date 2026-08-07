#!/usr/bin/env python3
"""Build WHK's economic ownership map and component proofs from the 424B4.

WhiteHawk Minerals is a non-operated natural gas mineral and royalty aggregator
(Marcellus / Haynesville) that IPO'd 2026-06-10 in an Up-C structure. The
generic first-pass compiler cannot model this: the routed profile is
`scarce_asset_optionality`, whose first listed failure mode is "gross asset
value mistaken for shareholder value", and an Up-C is precisely where that
happens. WhiteHawk Minerals Corp. does not own the royalties -- it owns 86.0%
of WhiteHawk OpCo, which does.

Two facts drive everything here, both taken verbatim from the prospectus rather
than derived:

  * The Company holds 22,996,579 OpCo Interests = 86.0% of the common economic
    interest in WhiteHawk OpCo; the Management Contributor holds the other
    3,750,000 = 14.0%, exchangeable 1:1 into Class A (424B4 p.19/p.24).
  * Cash Available for Distribution is defined *after* cash interest expense,
    cash taxes and cash preferred dividends (424B4 "Non-GAAP Financial
    Measures", and the reconciliation subtracts all three). It is therefore
    already an equity-level cash flow. Subtracting net debt or the mezzanine
    preferred from a CAFD-derived value would double-count them -- the profile's
    second listed failure mode, "operating cash flow and NAV counted twice".

What this script does NOT do is claim a reserve-based NAV. No 10-K or 10-Q has
been filed yet, and the reserve-life / decline-curve model is still an open task
in WHK/research/thesis.md. The royalty component is therefore emitted as a
`bounded_estimate` on disclosed CAFD with the discount rate and decline stated
as explicit judgments, not as a calculated NAV.

Usage:
  python _system/scripts/build_whk_contract_proofs.py [--date YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[2]
TICKER = "WHK"
PROSPECTUS = (
    "WHK/investor-documents/sec-edgar/424B4_20260609_rpt_acc0001193125_26_264014.htm"
)

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


def _src(locator: str, as_of: str) -> dict:
    return {"ref": PROSPECTUS, "locator": locator, "as_of": as_of}


def royalty_component() -> dict:
    """Producing mineral and royalty interests, valued on attributable CAFD."""
    return {
        "id": "mineral_royalty_cash_stream",
        "label": "Marcellus and Haynesville mineral and royalty interests, "
                 "attributable to Class A via the Company's OpCo stake",
        "category": "real_option",
        "treatment": "additive",
        "overlap_key": "opco_royalty_interests",
        # The routed profile's primary method, component_owner_cash_and_unit_nav,
        # is a pairing: an owner-cash leg and a unit-NAV leg. Only the owner-cash
        # leg is evidenced today, and it maps exactly onto the approved registry
        # card owner_cash_or_dividend_discount@1.0, whose equation
        #   value = distribution*(1+growth)/(required_return-growth)
        # is the calculation below. The unit-NAV leg needs reserve data that has
        # not been filed yet, so it is recorded as missing corroboration rather
        # than asserted. royalty_distribution_curve@1.0 is the card to use once
        # the Summary Reserve Data is modelled.
        "method": "owner_cash_or_dividend_discount",
        "corroboration_gap": (
            "Unit-NAV leg of component_owner_cash_and_unit_nav is unevidenced: no "
            "reserve-life or decline-curve model exists, and no 10-K/10-Q has been "
            "filed since the 2026-06-10 IPO. Corroborate with "
            "royalty_distribution_curve@1.0 once Summary Reserve Data is modelled."
        ),
        "evidence_tier": "primary_derived",
        "evidence": (
            "Pro forma Cash Available for Distribution of $36.317m for FY2025 and "
            "$9.959m for Q1 2026, from the 424B4 summary financial data. CAFD is "
            "defined and reconciled after cash interest expense, cash taxes and cash "
            "preferred dividends, so it is an equity-level cash flow and net debt and "
            "the mezzanine preferred are deliberately not subtracted again. The "
            "Company's 86.0% economic interest in WhiteHawk OpCo is applied before "
            "the per-share division so that the 14.0% held by Continuing Equity "
            "Owners is never counted as Class A value."
        ),
        "falsifier": (
            "A reserve-life / decline-curve model built from the 424B4 Summary "
            "Reserve Data, or the first 10-Q, shows net decline outside the -6% to "
            "0% band assumed here; or a declared dividend policy sets a payout that "
            "implies a different sustainable distribution than pro forma CAFD."
        ),
        "valuation_status": "bounded_estimate",
        "calculation_proof": {
            "schema_version": "1.0",
            "method_id": "owner_cash_or_dividend_discount",
            "method_version": "1.0",
            "output_unit": "USD_per_share",
            "inputs": [
                {
                    "id": "pf_fy2025_cafd_m",
                    "label": "Pro forma Cash Available for Distribution, FY2025",
                    "kind": "fact",
                    "value": PF_FY2025_CAFD_M,
                    "unit": "USD_m",
                    "source": _src(
                        "Summary historical and pro forma financial data, "
                        "Cash Available for Distribution, Pro Forma Year Ended "
                        "December 31, 2025: $36,317 thousand",
                        "2025-12-31",
                    ),
                    "locked": True,
                },
                {
                    "id": "pf_q1_2026_cafd_m",
                    "label": "Pro forma Cash Available for Distribution, Q1 2026",
                    "kind": "fact",
                    "value": PF_Q1_2026_CAFD_M,
                    "unit": "USD_m",
                    "source": _src(
                        "Summary historical and pro forma financial data, "
                        "Cash Available for Distribution, Pro Forma Three Months "
                        "Ended March 31, 2026: $9,959 thousand",
                        "2026-03-31",
                    ),
                    "locked": True,
                },
                {
                    "id": "class_a_shares",
                    "label": "Class A common shares outstanding after the Transactions",
                    "kind": "fact",
                    "value": float(CLASS_A_SHARES),
                    "unit": "shares",
                    "source": _src(
                        "Our Organizational Structure: we will own 22,996,579 OpCo "
                        "Interests, held one-for-one against Class A common stock",
                        "2026-06-09",
                    ),
                    "locked": True,
                },
            ],
            "assumptions": [
                {
                    "id": "cafd_run_rate_m",
                    "label": "Sustainable annual CAFD at OpCo",
                    "kind": "judgment",
                    "values": {
                        # low: pro forma FY2025 as reported
                        "low": PF_FY2025_CAFD_M,
                        # base: midpoint of FY2025 and the annualised Q1 2026 rate
                        "base": round((PF_FY2025_CAFD_M + PF_Q1_2026_CAFD_M * 4) / 2, 3),
                        # high: Q1 2026 annualised
                        "high": round(PF_Q1_2026_CAFD_M * 4, 3),
                    },
                    "unit": "USD_m",
                    "rationale": (
                        "Q1 2026 pro forma CAFD annualises to $39.8m against $36.3m for "
                        "pro forma FY2025, so the disclosed run-rate is rising. One "
                        "quarter is not a year for a commodity royalty, so the base "
                        "takes the midpoint rather than the latest quarter."
                    ),
                    "allowed_range": {"min": 30.0, "max": 42.0},
                },
                {
                    "id": "company_economic_interest",
                    "label": "Company's common economic interest in WhiteHawk OpCo",
                    "kind": "judgment",
                    "values": {
                        # low/base assume the earnout units are fully issued
                        "low": round(COMPANY_SHARE_FULLY_EARNED, 6),
                        "base": round(COMPANY_SHARE_FULLY_EARNED, 6),
                        "high": round(COMPANY_SHARE, 6),
                    },
                    "unit": "ratio",
                    "rationale": (
                        "86.0% today. The Earnout Amount is 25% of the $130.0m "
                        "Internalization Price, payable in OpCo Interests and matching "
                        "Class B if Adjusted EBITDA targets are met; at the $26.00 IPO "
                        "price that is 1,250,000 units, cutting the Company's interest "
                        "to 82.1%. Given CAFD is already growing, low and base assume "
                        "the targets are met and the dilution occurs; only the high "
                        "case keeps 86.0%."
                    ),
                    "allowed_range": {"min": 0.80, "max": 0.86},
                },
                {
                    "id": "required_return",
                    "label": "Required return on a non-operated gas royalty",
                    "kind": "judgment",
                    "values": {"low": 0.12, "base": 0.10, "high": 0.09},
                    "unit": "ratio",
                    "rationale": (
                        "No capex and no operating cost, but full commodity exposure, a "
                        "single-basin pair, a first-year public company with a restated "
                        "FY2025 and identified material weaknesses, and no declared "
                        "dividend policy. The low value case carries the high discount "
                        "rate."
                    ),
                    "allowed_range": {"min": 0.08, "max": 0.14},
                },
                {
                    "id": "net_decline",
                    "label": "Net annual change in attributable CAFD",
                    "kind": "judgment",
                    "values": {"low": -0.06, "base": -0.03, "high": 0.02},
                    "unit": "ratio",
                    "rationale": (
                        "Mineral and royalty interests deplete as wells decline, which "
                        "sets the low case. But CAFD is struck before acquisition "
                        "spend, and the stated strategy is to reinvest cash beyond the "
                        "dividend into more royalties -- royalty revenue ran $12.702m "
                        "in FY2024, $50.075m in FY2025 and annualises to $102.5m off "
                        "Q1 2026. Capitalising that as a pure decline would charge "
                        "depletion while crediting nothing for reinvestment, the mirror "
                        "of the 'growth without its capital cost' error, so the high "
                        "case carries modest positive growth. This band is the single "
                        "largest unverified judgment here and is what the reserve model "
                        "in the falsifier would replace. For reference, the $26.16 "
                        "market price implies a ~5.0% cap rate, i.e. roughly +5% "
                        "perpetual growth at a 10% required return -- above even this "
                        "high case, so the gap to market is a growth disagreement, not "
                        "an arithmetic one."
                    ),
                    "allowed_range": {"min": -0.10, "max": 0.05},
                },
            ],
            "calculations": [
                {
                    "id": "attributable_cafd_m",
                    "op": "multiply",
                    "args": ["cafd_run_rate_m", "company_economic_interest"],
                    "unit": "USD_m",
                },
                {
                    "id": "growth_factor",
                    "op": "add",
                    "args": [1, "net_decline"],
                    "unit": "ratio",
                },
                {
                    "id": "next_year_cafd_m",
                    "op": "multiply",
                    "args": ["attributable_cafd_m", "growth_factor"],
                    "unit": "USD_m",
                },
                {
                    "id": "cap_rate",
                    "op": "subtract",
                    "args": ["required_return", "net_decline"],
                    "unit": "ratio",
                },
                {
                    "id": "attributable_value_m",
                    "op": "divide",
                    "args": ["next_year_cafd_m", "cap_rate"],
                    "unit": "USD_m",
                },
                {
                    "id": "attributable_value",
                    "op": "multiply",
                    "args": ["attributable_value_m", 1_000_000],
                    "unit": "USD",
                },
                {
                    "id": "value_per_share",
                    "op": "divide",
                    "args": ["attributable_value", "class_a_shares"],
                    "unit": "USD_per_share",
                },
            ],
            "outputs": {
                "low": "value_per_share",
                "base": "value_per_share",
                "high": "value_per_share",
            },
            "source_lineage": [
                {
                    "ref": PROSPECTUS,
                    "locator": "424B4 filed 2026-06-09, summary financial data and "
                               "Our Organizational Structure",
                    "as_of": "2026-06-09",
                }
            ],
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
        f"discrepancy is flagged for human review rather than reconciled by assumption."
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--date", default=date.today().isoformat())
    args = ap.parse_args(argv)

    valuation_path = ROOT / TICKER / "research" / "valuation.json"
    valuation = json.loads(valuation_path.read_text(encoding="utf-8"))

    components = [royalty_component()]
    valuation["component_valuation_results"] = {
        "all_material_components_identified": True,
        "additive_components": components,
        "embedded_components": [],
        "partition_note": ownership_note(),
        "source": "build_whk_contract_proofs.py",
        "as_of": args.date,
    }
    valuation["as_of"] = args.date
    valuation["method"] = "component_owner_cash_and_unit_nav"

    valuation_path.write_text(
        json.dumps(valuation, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"[ok] {valuation_path.relative_to(ROOT)}")
    print(f"  components: {len(components)}")
    print(f"  company economic interest: {COMPANY_SHARE:.4f} "
          f"(fully earned-out {COMPANY_SHARE_FULLY_EARNED:.4f})")
    print(f"  Class A shares: {CLASS_A_SHARES:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
