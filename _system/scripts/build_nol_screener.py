#!/usr/bin/env python3
"""Build NOL carryforward screener JSON for dashboard Watchlist tab.

Reads seed candidates + SEC XBRL company facts (deferred tax assets / valuation allowance).
Market cap = SEC shares outstanding × Yahoo chart price (v7 quote API is blocked).
Marks rows already in registry holdings or watchlist.

Usage:
  python _system/scripts/build_nol_screener.py
  python _system/scripts/build_nol_screener.py --write
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEED_PATH = ROOT / "_system" / "reference" / "market-data" / "screens" / "nol_seed.csv"
REGISTRY_PATH = ROOT / "_system" / "portfolio" / "registry.json"
OUTPUT = ROOT / "dashboard" / "data" / "nol_screener.json"

SEC_UA = "Marvin Research marvin@single-stock-investments.local"
YAHOO_UA = "MarvinResearch/1.0 (nol-screener)"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart"

# XBRL tags seen on 10-K balance sheets / tax footnotes
DTA_TAGS = (
    "DeferredTaxAssetsGross",
    "DeferredTaxAssetsNet",
    "DeferredIncomeTaxAssetsNet",
    "DeferredTaxAssets",
)
NOL_DTA_TAGS = ("DeferredTaxAssetsOperatingLossCarryforwards",)
OPERATING_LOSS_TAGS = ("OperatingLossCarryforwards",)
ALLOWANCE_TAGS = (
    "ValuationAllowanceDeferredTaxAssets",
    "DeferredTaxAssetsValuationAllowance",
)
SHARES_TAGS = (
    "CommonStockSharesOutstanding",
    "EntityCommonStockSharesOutstanding",
)
CASH_TAGS = (
    "CashAndCashEquivalentsAtCarryingValue",
    "Cash",
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
)
DEBT_TAGS = (
    "LongTermDebtNoncurrent",
    "LongTermDebt",
    "DebtInstrumentCarryingAmount",
    "ShortTermBorrowings",
)

CAP_BUCKETS = (
    ("micro", 300_000_000),
    ("small", 2_000_000_000),
    ("mid", 10_000_000_000),
    ("large", None),
)


def load_registry_sets() -> tuple[set[str], set[str]]:
    if not REGISTRY_PATH.exists():
        return set(), set()
    reg = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    holdings = set((reg.get("holdings") or {}).keys())
    watchlist = set((reg.get("watchlist") or {}).keys())
    return holdings, watchlist


def load_seed_rows() -> list[dict]:
    if not SEED_PATH.exists():
        return []
    rows = []
    with SEED_PATH.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            ticker = (row.get("ticker") or "").strip().upper()
            if not ticker:
                continue
            rows.append(
                {
                    "ticker": ticker,
                    "company": (row.get("company") or ticker).strip(),
                    "market": (row.get("market") or "US").strip().upper(),
                    "cap_tier_seed": (row.get("cap_tier") or "").strip().lower(),
                    "notes": (row.get("notes") or "").strip(),
                    "source": "seed",
                }
            )
    return rows


def fetch_json(url: str, ua: str = SEC_UA) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def load_cik_map() -> dict[str, str]:
    data = fetch_json(SEC_TICKERS_URL)
    if not data:
        return {}
    out: dict[str, str] = {}
    for row in data.values():
        t = str(row.get("ticker", "")).upper()
        cik = str(row.get("cik_str", "")).zfill(10)
        if t and cik:
            out[t] = cik
    return out


def _pick_best_entry(entries: list[dict]) -> tuple[float | None, str | None]:
    best_date = ""
    best_val: float | None = None
    for entry in entries or []:
        form = entry.get("form")
        if form not in ("10-K", "10-Q", None):
            if form and not str(form).startswith("10-"):
                continue
        end = str(entry.get("end") or "")
        val = entry.get("val")
        if val is None or not end:
            continue
        if end >= best_date:
            best_date = end
            best_val = float(val)
    return best_val, best_date or None


def latest_usd_fact(facts: dict, tags: tuple[str, ...]) -> tuple[float | None, str | None]:
    """Return most recent USD fact value and period end across tag variants."""
    best_date = ""
    best_val: float | None = None
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    for tag in tags:
        block = us_gaap.get(tag)
        if not block:
            continue
        for unit_key, entries in (block.get("units") or {}).items():
            if "USD" not in unit_key.upper():
                continue
            val, end = _pick_best_entry(entries)
            if val is not None and end and end >= best_date:
                best_date = end
                best_val = val
    return best_val, best_date or None


def latest_shares_fact(facts: dict) -> tuple[float | None, str | None]:
    """Return most recent shares-outstanding fact (unit contains 'share')."""
    best_date = ""
    best_val: float | None = None
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    for tag in SHARES_TAGS:
        block = us_gaap.get(tag)
        if not block:
            continue
        for unit_key, entries in (block.get("units") or {}).items():
            if "share" not in unit_key.lower():
                continue
            val, end = _pick_best_entry(entries)
            if val is not None and end and end >= best_date:
                best_date = end
                best_val = val
    return best_val, best_date or None


def fetch_yahoo_price(symbol: str) -> tuple[float | None, str | None]:
    """Latest regular market price from Yahoo chart API."""
    url = f"{YAHOO_CHART_URL}/{symbol}?interval=1d&range=5d"
    data = fetch_json(url, ua=YAHOO_UA)
    if not data:
        return None, None
    try:
        meta = data["chart"]["result"][0]["meta"]
        price = meta.get("regularMarketPrice")
        if price is not None:
            return float(price), str(meta.get("currency") or "USD")
    except (KeyError, IndexError, TypeError, ValueError):
        pass
    return None, None


def compute_realizable(dta: float | None, allowance: float | None) -> float | None:
    if dta is None:
        return None
    if allowance is not None:
        return max(0.0, dta - allowance)
    return dta


def screen_ticker(ticker: str, cik: str) -> dict:
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    data = fetch_json(url)
    if not data:
        return {"sec_error": "companyfacts unavailable"}

    dta, dta_date = latest_usd_fact(data, DTA_TAGS)
    allowance, _ = latest_usd_fact(data, ALLOWANCE_TAGS)
    nol_dta, _ = latest_usd_fact(data, NOL_DTA_TAGS)
    operating_loss, _ = latest_usd_fact(data, OPERATING_LOSS_TAGS)
    shares, shares_date = latest_shares_fact(data)
    cash, _ = latest_usd_fact(data, CASH_TAGS)
    debt_long, _ = latest_usd_fact(data, ("LongTermDebtNoncurrent", "LongTermDebt"))
    debt_short, _ = latest_usd_fact(data, ("ShortTermBorrowings", "DebtCurrent"))

    realizable = compute_realizable(dta, allowance)
    total_debt = None
    if debt_long is not None or debt_short is not None:
        total_debt = (debt_long or 0.0) + (debt_short or 0.0)

    allowance_pct = None
    if dta and dta > 0 and allowance is not None:
        allowance_pct = round(100.0 * allowance / dta, 1)

    return {
        "cik": cik,
        "dta_gross_usd": dta,
        "valuation_allowance_usd": allowance,
        "dta_realizable_usd": realizable,
        "nol_dta_usd": nol_dta,
        "operating_loss_carryforward_usd": operating_loss,
        "allowance_pct": allowance_pct,
        "shares_outstanding": shares,
        "shares_as_of": shares_date,
        "cash_usd": cash,
        "total_debt_usd": total_debt,
        "filing_as_of": dta_date,
        "sec_entity": data.get("entityName"),
    }


def cap_bucket_from_mcap(mcap: float | None) -> str | None:
    if mcap is None or mcap <= 0:
        return None
    for name, ceiling in CAP_BUCKETS:
        if ceiling is None or mcap < ceiling:
            return name
    return "large"


def fmt_usd_mm(val: float | None) -> str | None:
    if val is None:
        return None
    return f"${val / 1_000_000:.1f}M"


def fmt_mcap(val: float | None) -> str | None:
    if val is None:
        return None
    if val >= 1_000_000_000:
        return f"${val / 1_000_000_000:.2f}B"
    return f"${val / 1_000_000:.0f}M"


def fmt_pct(val: float | None) -> str | None:
    if val is None:
        return None
    return f"{val:.1f}%"


def fmt_per_share(val: float | None) -> str | None:
    if val is None:
        return None
    if val >= 1:
        return f"${val:.2f}"
    return f"${val:.3f}"


# ---------------------------------------------------------------------------
# Section 382 and what an acquirer can actually use
#
# The screen used to rank on realizable DTA / market cap and call anything with
# a positive realizable DTA "actionable". Both are misleading for the question
# the list is built to answer -- is this worth acquiring for its tax attributes:
#
#   1. WRONG TAXPAYER. A C-corp's NOLs offset that corporation's own taxable
#      income. They do nothing for capital gains held personally or in a fund,
#      and under the consolidated-return SRLY rules an acquired subsidiary's
#      pre-change losses generally shelter only income that subsidiary itself
#      generates. "Buy an NOL shell to shelter my gains" is not a structure the
#      code permits; the gains have to already sit inside a corporation that can
#      absorb the loss company.
#
#   2. SECTION 382 THROTTLE. An ownership change -- more than 50 percentage
#      points among 5% shareholders over a rolling three years, which any
#      takeover triggers -- caps annual use of pre-change NOLs at roughly
#      (equity value immediately before the change) x (long-term tax-exempt
#      rate). So the asset is not the carryforward; it is an annuity whose
#      size is set by the PRICE PAID, which is why a large DTA on a small
#      market cap is close to worthless rather than a bargain. Buying $77.8M
#      of DTA at a $47M market cap yields ~$2M of usable NOL per year.
#
#   3. DTA IS NOT NOL. DeferredTaxAssetsGross includes lease/ROU liabilities,
#      accruals, reserves and credits that reverse through normal operations
#      and are not a transferable loss asset. Ranking on total DTA put a
#      retailer with $1.4M of loss carryforward at the top of the screen.
#
# Everything below is an ESTIMATE for triage, not tax advice, and the payload
# says so. Real cases turn on NUBIG/NUBIL, 382(l)(5)/(l)(6), SRLY, 383 credits
# and state conformity, none of which XBRL exposes.
# ---------------------------------------------------------------------------

# IRS publishes the long-term tax-exempt rate monthly (Rev. Rul. tables); it is
# the ceiling used in the 382 limitation. Stored as an explicit, dated
# assumption rather than buried in a formula so it can be refreshed.
SECTION_382_RATE = 0.0450
SECTION_382_RATE_AS_OF = "2026-08"
SECTION_382_RATE_SOURCE = "IRS long-term tax-exempt rate (Section 382(f)); update monthly"
FEDERAL_CORPORATE_RATE = 0.21
# Post-TCJA, NOLs arising after 2017 offset at most 80% of taxable income.
POST_2017_INCOME_OFFSET_CAP = 0.80
# Discount rate for the PV of the throttled annual stream.
NOL_PV_DISCOUNT_RATE = 0.10
# Carryforwards arising after 2017 are indefinite; cap the PV horizon anyway.
NOL_PV_HORIZON_YEARS = 20
# Below this, the "DTA" is overwhelmingly timing differences, not losses.
NOL_SHARE_OF_DTA_FLOOR = 0.40
# At or above this valuation allowance, management and their auditor have said
# realization is not more likely than not. That is their judgment, not ours.
FULLY_RESERVED_ALLOWANCE_PCT = 90.0
# A row counts as material when it recovers at least this share of the
# theoretical ceiling. Judging against a flat percentage is a trap: the ceiling
# is ~6% of the price, so any threshold above that is unreachable by
# construction and the screen reports zero candidates forever.
SECTION_382_MATERIAL_FRACTION_OF_CEILING = 0.60
# Below this a reported market cap is a bad price feed, not a nano-cap.
IMPLAUSIBLE_MCAP_FLOOR_USD = 1_000_000.0


def section_382_ceiling_ratio() -> float:
    """Most of the purchase price any acquirer can ever recover as tax shield.

    The 382 limit is a fixed percentage OF THE PRICE PAID, so paying more buys
    a proportionally larger allowance and the ratio is scale-invariant. With an
    unlimited carryforward it converges to:

        rate x annuity_factor(horizon, discount) x corporate_rate x offset_cap

    which is roughly 6% under the assumptions above. This is why "big NOL, tiny
    market cap" is not a bargain: shrinking the price shrinks the annual
    allowance in exact proportion.
    """
    annuity = sum(
        1.0 / ((1 + NOL_PV_DISCOUNT_RATE) ** y)
        for y in range(1, NOL_PV_HORIZON_YEARS + 1)
    )
    return (
        SECTION_382_RATE * annuity * FEDERAL_CORPORATE_RATE * POST_2017_INCOME_OFFSET_CAP
    )


def section_382_profile(sec: dict, mcap: float | None) -> dict:
    """Estimate what an acquirer could actually use, and name what blocks it."""
    nol_dta = sec.get("nol_dta_usd")
    dta_gross = sec.get("dta_gross_usd")
    realizable = sec.get("dta_realizable_usd")
    allowance_pct = sec.get("allowance_pct")

    blockers: list[str] = []

    # Is the DTA actually a loss asset?
    nol_share = None
    if nol_dta is not None and dta_gross:
        nol_share = round(nol_dta / dta_gross, 3)
        if nol_share < NOL_SHARE_OF_DTA_FLOOR:
            blockers.append("dta_is_mostly_timing_differences")
    elif nol_dta is None:
        blockers.append("no_nol_component_reported")

    if allowance_pct is not None and allowance_pct >= FULLY_RESERVED_ALLOWANCE_PCT:
        blockers.append("management_fully_reserves_it")

    # The 382 limit throttles the GROSS carryforward, not the tax-effected
    # asset. nol_dta_usd is already net of the tax rate -- SIRI reports
    # $1,447.2M of NOL DTA against $7,844M of gross carryforward, a ratio of
    # 18%, i.e. roughly the corporate rate. Multiplying the DTA by 21% again to
    # get a "shield" double-counts the rate and understates every row by ~5x.
    # Prefer the reported gross carryforward; gross the DTA up only as a
    # fallback, and say which was used.
    gross_nol = sec.get("operating_loss_carryforward_usd")
    nol_basis = "reported_carryforward"
    if not gross_nol or gross_nol <= 0:
        if nol_dta and nol_dta > 0:
            gross_nol = nol_dta / FEDERAL_CORPORATE_RATE
            nol_basis = "grossed_up_from_dta"
        else:
            gross_nol = None
            nol_basis = "unavailable"

    annual_limit = None
    years_to_absorb = None
    usable_pv = None
    shield_pv = None
    if mcap and mcap > 0:
        # 382 limit is based on the equity value of the loss corporation
        # immediately BEFORE the ownership change; market cap is the closest
        # observable proxy and ignores any control premium actually paid.
        annual_limit = mcap * SECTION_382_RATE
        if gross_nol and gross_nol > 0 and annual_limit > 0:
            years_to_absorb = round(gross_nol / annual_limit, 1)
            # PV of an annuity of `annual_limit`, running until the carryforward
            # is exhausted or the horizon ends, whichever comes first.
            years = min(NOL_PV_HORIZON_YEARS, max(0.0, gross_nol / annual_limit))
            whole = int(years)
            pv = sum(annual_limit / ((1 + NOL_PV_DISCOUNT_RATE) ** y) for y in range(1, whole + 1))
            frac = years - whole
            if frac > 0:
                pv += (annual_limit * frac) / ((1 + NOL_PV_DISCOUNT_RATE) ** (whole + 1))
            usable_pv = pv
            shield_pv = pv * FEDERAL_CORPORATE_RATE * POST_2017_INCOME_OFFSET_CAP
    else:
        blockers.append("no_market_cap_so_382_limit_unknown")

    # A market cap below this is a data error, not a nano-cap: VTRS (Viatris, a
    # multi-billion company) priced out under $1M here and produced a
    # 47,000,000-year absorption estimate. Ratios stay scale-invariant and so
    # look fine, which is exactly why the absurdity has to be caught on the
    # input rather than spotted in the output.
    if mcap is not None and 0 < mcap < IMPLAUSIBLE_MCAP_FLOOR_USD:
        blockers.append("implausible_market_cap_check_price_feed")
    # A carryforward that needs more than a few horizons to absorb is not being
    # used by anyone: the limit is too small relative to the loss, so the
    # ratio saturates at the ceiling while the absolute recovery stays trivial.
    if years_to_absorb is not None and years_to_absorb > NOL_PV_HORIZON_YEARS * 3:
        blockers.append("carryforward_far_exceeds_what_the_382_limit_can_absorb")

    # Because the 382 limit is a fixed percentage OF THE PRICE PAID, the
    # recoverable shield saturates: once the carryforward is big enough to run
    # the whole horizon, shield/price converges on a constant that no amount of
    # additional NOL can raise. That ceiling is the single most useful number
    # on this screen -- it is the most any acquirer can get back, ever -- and
    # materiality has to be judged against it, not against an arbitrary
    # percentage that sits above it and can never be reached.
    ratio = None if shield_pv is None or not mcap else shield_pv / mcap
    ceiling = section_382_ceiling_ratio()
    if blockers:
        usability = "blocked"
    elif ratio is not None and ratio >= SECTION_382_MATERIAL_FRACTION_OF_CEILING * ceiling:
        usability = "material_after_382"
    else:
        usability = "immaterial_after_382"

    return {
        "nol_share_of_dta": nol_share,
        "gross_nol_usd": gross_nol,
        "gross_nol_basis": nol_basis,
        "section_382_annual_limit_usd": annual_limit,
        "section_382_years_to_absorb": years_to_absorb,
        "acquirer_usable_nol_pv_usd": usable_pv,
        "acquirer_tax_shield_pv_usd": shield_pv,
        "tax_shield_pv_to_mcap_pct": (None if ratio is None else round(100.0 * ratio, 2)),
        "pct_of_382_ceiling": (None if ratio is None else round(100.0 * ratio / ceiling, 0)),
        "usability": usability,
        "blockers": blockers,
    }


def enrich_metrics(
    sec: dict,
    price: float | None,
    mcap: float | None,
) -> dict:
    realizable = sec.get("dta_realizable_usd")
    shares = sec.get("shares_outstanding")
    cash = sec.get("cash_usd")
    debt = sec.get("total_debt_usd")

    dta_per_share = None
    if realizable is not None and shares and shares > 0:
        dta_per_share = realizable / shares

    dta_to_mcap_pct = None
    if realizable is not None and mcap and mcap > 0:
        dta_to_mcap_pct = round(100.0 * realizable / mcap, 1)

    enterprise_value = None
    dta_to_ev_pct = None
    if mcap is not None and mcap > 0:
        enterprise_value = mcap + (debt or 0.0) - (cash or 0.0)
        if enterprise_value > 0 and realizable is not None:
            dta_to_ev_pct = round(100.0 * realizable / enterprise_value, 1)

    fully_reserved = (
        sec.get("dta_gross_usd") is not None
        and sec.get("dta_gross_usd", 0) > 0
        and (realizable is None or realizable <= 0)
    )
    # `is_actionable` used to mean "realizable DTA is a positive number", which
    # 24 of 89 rows satisfied including a retailer whose loss carryforward was
    # $1.4M and eight biotechs their own auditors fully reserve. It now means
    # the 382-throttled shield is material against the price you would pay.
    profile = section_382_profile(sec, mcap)
    is_actionable = profile["usability"] == "material_after_382"

    return {
        **profile,
        "price_usd": price,
        "market_cap_usd": mcap,
        "market_cap_display": fmt_mcap(mcap),
        "enterprise_value_usd": enterprise_value if enterprise_value and enterprise_value > 0 else None,
        "dta_per_share_usd": dta_per_share,
        "dta_per_share_display": fmt_per_share(dta_per_share),
        "dta_to_mcap_pct": dta_to_mcap_pct,
        "dta_to_mcap_display": fmt_pct(dta_to_mcap_pct),
        "dta_to_ev_pct": dta_to_ev_pct,
        "dta_to_ev_display": fmt_pct(dta_to_ev_pct),
        "allowance_pct_display": fmt_pct(sec.get("allowance_pct")),
        "nol_dta_display": fmt_usd_mm(sec.get("nol_dta_usd")),
        "fully_reserved": fully_reserved,
        "is_actionable": is_actionable,
    }


def build_rows() -> list[dict]:
    holdings, watchlist = load_registry_sets()
    seeds = load_seed_rows()
    cik_map = load_cik_map()

    seen: set[str] = set()
    out: list[dict] = []

    for seed in seeds:
        ticker = seed["ticker"]
        if ticker in seen:
            continue
        seen.add(ticker)

        row = {**seed}
        base_ticker = ticker.split(".")[0]
        cik = cik_map.get(base_ticker) or cik_map.get(ticker)

        sec: dict = {}
        if cik:
            sec = screen_ticker(ticker, cik)
            if sec.get("sec_entity") and not row.get("company"):
                row["company"] = sec["sec_entity"]
            time.sleep(0.12)

        price, _ = fetch_yahoo_price(base_ticker)
        time.sleep(0.08)
        shares = sec.get("shares_outstanding")
        mcap = None
        if price is not None and shares and shares > 0:
            mcap = price * shares

        cap_bucket = cap_bucket_from_mcap(mcap) or seed.get("cap_tier_seed") or None
        metrics = enrich_metrics(sec, price, mcap)

        row.update(
            {
                "in_holdings": ticker in holdings,
                "in_watchlist": ticker in watchlist,
                "dta_gross_usd": sec.get("dta_gross_usd"),
                "valuation_allowance_usd": sec.get("valuation_allowance_usd"),
                "dta_realizable_usd": sec.get("dta_realizable_usd"),
                "nol_dta_usd": sec.get("nol_dta_usd"),
                "operating_loss_carryforward_usd": sec.get("operating_loss_carryforward_usd"),
                "allowance_pct": sec.get("allowance_pct"),
                "shares_outstanding": shares,
                "shares_as_of": sec.get("shares_as_of"),
                "dta_gross_display": fmt_usd_mm(sec.get("dta_gross_usd")),
                "dta_realizable_display": fmt_usd_mm(sec.get("dta_realizable_usd")),
                "filing_as_of": sec.get("filing_as_of"),
                "cik": sec.get("cik"),
                "sec_error": sec.get("sec_error"),
                "screen_status": "ok" if sec.get("dta_gross_usd") is not None else "pending_sec",
                "cap_bucket": cap_bucket,
                "is_small_cap": cap_bucket in ("micro", "small"),
            }
        )
        row.update(metrics)
        row.pop("cap_tier_seed", None)
        out.append(row)

    # Rank by the 382-throttled shield against the price paid, not by raw
    # DTA/mcap. The old key put micro-caps first by construction, which is
    # backwards: a small market cap SHRINKS the annual 382 limit, so a big DTA
    # on a tiny company is the least usable combination on the screen, not the
    # most. Blocked rows sort last regardless of how large their DTA looks.
    usability_rank = {"material_after_382": 0, "immaterial_after_382": 1, "blocked": 2}
    out.sort(
        key=lambda r: (
            usability_rank.get(r.get("usability") or "", 9),
            -(r.get("tax_shield_pv_to_mcap_pct") or 0),
            -(r.get("acquirer_tax_shield_pv_usd") or 0),
            r["ticker"],
        ),
    )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Build NOL carryforward screener JSON")
    parser.add_argument("--write", action="store_true", help="Write dashboard/data/nol_screener.json")
    args = parser.parse_args()

    rows = build_rows()
    small_count = sum(1 for r in rows if r.get("is_small_cap"))
    actionable_count = sum(1 for r in rows if r.get("is_actionable"))
    blocker_tally: dict[str, int] = {}
    for row in rows:
        for blocker in row.get("blockers") or []:
            blocker_tally[blocker] = blocker_tally.get(blocker, 0) + 1
    payload = {
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "criteria": (
            "US deferred tax assets (SEC companyfacts) + market cap (SEC shares × Yahoo chart price). "
            "Realizable DTA ≈ gross − valuation allowance; NOL DTA from DeferredTaxAssetsOperatingLossCarryforwards. "
            "Ranked by the Section 382-throttled tax shield against the price paid, NOT by DTA/market cap. "
            "Seed: _system/reference/market-data/screens/nol_seed.csv."
        ),
        # The two facts that decide whether any row on this screen is usable.
        # They belong in the payload, not only in a UI string, so any consumer
        # of this artifact carries them.
        "tax_reality": {
            "who_can_use_it": (
                "A C corporation's NOLs offset that corporation's own taxable income. They do not "
                "shelter capital gains held personally or in a fund, and under the consolidated-return "
                "SRLY rules an acquired subsidiary's pre-change losses generally offset only income "
                "that subsidiary itself generates. Acquiring an NOL company to shelter unrelated gains "
                "is not a structure the code permits."
            ),
            "section_382": (
                "Any takeover triggers an ownership change (>50 percentage points among 5% holders over "
                "three years), which caps annual use of pre-change NOLs at roughly the loss "
                "corporation's equity value immediately before the change times the long-term "
                "tax-exempt rate. The asset is an annuity whose size is set by the price paid, so a "
                "large DTA on a small market cap is the LEAST usable combination on this screen."
            ),
            "dta_is_not_nol": (
                "DeferredTaxAssetsGross includes lease/ROU liabilities, accruals and reserves that "
                "reverse through normal operations and transfer no loss asset. nol_share_of_dta below "
                f"{NOL_SHARE_OF_DTA_FLOOR:.0%} means the headline DTA is mostly timing differences."
            ),
            "valuation_allowance": (
                f"An allowance at or above {FULLY_RESERVED_ALLOWANCE_PCT:.0f}% is management and their "
                "auditor stating realization is not more likely than not. Treat it as their answer, "
                "not as a discount."
            ),
            "assumptions": {
                "section_382_rate": SECTION_382_RATE,
                "section_382_rate_as_of": SECTION_382_RATE_AS_OF,
                "section_382_rate_source": SECTION_382_RATE_SOURCE,
                "federal_corporate_rate": FEDERAL_CORPORATE_RATE,
                "post_2017_income_offset_cap": POST_2017_INCOME_OFFSET_CAP,
                "pv_discount_rate": NOL_PV_DISCOUNT_RATE,
                "pv_horizon_years": NOL_PV_HORIZON_YEARS,
            },
            "not_modelled": [
                "NUBIG / NUBIL adjustments to the 382 limit",
                "Section 382(l)(5) bankruptcy and 382(l)(6) exceptions",
                "Section 383 credit and capital loss carryforwards",
                "state NOL conformity and separate-company limits",
                "existing NOL rights plans / poison pills that block a change of control",
                "control premium actually paid, which raises the 382 limit above market cap",
            ],
            "research_only": True,
            "not_tax_advice": (
                "Triage estimates from XBRL tags. Every real case turns on facts XBRL does not expose. "
                "Not tax or investment advice."
            ),
        },
        "seed_path": str(SEED_PATH.relative_to(ROOT)).replace("\\", "/"),
        "row_count": len(rows),
        "small_cap_count": small_count,
        "actionable_count": actionable_count,
        "blocker_tally": blocker_tally,
        "rows": rows,
    }

    if args.write:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(
            f"Wrote {OUTPUT} ({len(rows)} rows, {small_count} small/micro, "
            f"{actionable_count} actionable)"
        )
    else:
        print(json.dumps(payload, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
