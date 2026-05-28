#!/usr/bin/env python3
"""Compute GOOGL segment PV sum and reverse business return."""
from __future__ import annotations


def cashflows_from_fcf0(fcf0: float, g1: float, g2: float, exit_mult: float, years: int = 10) -> list[float]:
    stream: list[float] = []
    fcf = fcf0
    for year in range(1, years + 1):
        g = g1 if year <= 5 else g2
        fcf *= 1 + g
        stream.append(fcf)
    terminal = fcf * exit_mult
    return stream, terminal


def pv_stream(fcf0: float, g1: float, g2: float, exit_mult: float, r: float, years: int = 10) -> float:
    cfs, terminal = cashflows_from_fcf0(fcf0, g1, g2, exit_mult, years)
    pv = sum(cf / (1 + r) ** y for y, cf in enumerate(cfs, start=1))
    pv += terminal / (1 + r) ** years
    return pv


def irr_on_price(price: float, equity_pv: float, years: int = 10) -> float:
    """Solve r such that PV of equity cash = price (simplified: single terminal)."""
    rate = 0.10
    for _ in range(300):
        npv = -price + equity_pv / (1 + rate) ** years
        # Newton on equity_pv/(1+r)^10 - price = 0
        d = -years * equity_pv / (1 + rate) ** (years + 1)
        if abs(d) < 1e-12:
            break
        rate -= npv / d
    return rate


def cashflows_full(price: float, fcf0: float, g1: float, g2: float, exit_mult: float, years: int = 10) -> list[float]:
    stream = [-price]
    fcf = fcf0
    for year in range(1, years + 1):
        g = g1 if year <= 5 else g2
        fcf *= 1 + g
        if year < years:
            stream.append(fcf)
        else:
            stream.append(fcf + fcf * exit_mult)
    return stream


def irr(cfs: list[float], guess: float = 0.12) -> float:
    rate = guess
    for _ in range(200):
        npv = sum(cf / (1 + rate) ** i for i, cf in enumerate(cfs))
        dnpv = sum(-i * cf / (1 + rate) ** (i + 1) for i, cf in enumerate(cfs))
        if abs(dnpv) < 1e-12:
            break
        rate -= npv / dnpv
    return rate


def main() -> None:
    price = 386.0
    shares_bn = 12.447
    consolidated_fcf_bn = 72.8  # FY2025 OCF - capex

    # FY2025 segment OI ($B) — 10-K segment note (SEC R42.htm / 10-K)
    oi = {
        "services": 139.404,
        "cloud": 13.910,
        "other_bets": -7.515,
        "alphabet_level": -16.760,
    }
    positive_oi = oi["services"] + oi["cloud"]

    # Allocate reported FCF to profitable segments by OI share [Assumption]
    fcf_alloc = {
        "services": consolidated_fcf_bn * (oi["services"] / positive_oi),
        "cloud": consolidated_fcf_bn * (oi["cloud"] / positive_oi),
    }
    fcf0_sh = {
        "services": fcf_alloc["services"] / shares_bn,
        "cloud": fcf_alloc["cloud"] / shares_bn,
    }

    # Other Bets: annual drag only, zero terminal (Speedwell / TCI) — OI loss $/sh pre-tax
    drag_sh = abs(oi["other_bets"]) / shares_bn

    segments = {
        "services": {"fcf0_sh": fcf0_sh["services"], "g1": 0.09, "g2": 0.07, "exit": 22},
        "cloud": {"fcf0_sh": fcf0_sh["cloud"], "g1": 0.25, "g2": 0.12, "exit": 18},
    }
    r_discount = 0.10  # explicit discount for segment sum [Assumption]

    pv_total = 0.0
    print("=== Segment PV @ 10% discount (base) ===")
    for name, s in segments.items():
        pv = pv_stream(s["fcf0_sh"], s["g1"], s["g2"], s["exit"], r_discount)
        pv_total += pv
        print(f"{name}: fcf0=${s['fcf0_sh']:.2f}/sh PV=${pv:.1f}/sh")

    # Other Bets: 10yr PV of constant drag
    drag_pv = sum(-drag_sh / (1 + r_discount) ** y for y in range(1, 11))
    pv_total += drag_pv
    print(f"other_bets drag PV=${drag_pv:.1f}/sh")

    # Alphabet-level corp drag (OI loss, no terminal)
    corp_drag_sh = abs(oi["alphabet_level"]) / shares_bn
    corp_pv = sum(-corp_drag_sh / (1 + r_discount) ** y for y in range(1, 11))
    pv_total += corp_pv
    print(f"alphabet_level drag PV=${corp_pv:.1f}/sh")

    print(f"\nSum PV/sh = ${pv_total:.1f} vs price ${price:.1f}")

    # Lawrence consolidated
    lawrence = irr(cashflows_full(price, 5.85, 0.11, 0.08, 25))
    print(f"Lawrence consolidated IRR = {lawrence*100:.1f}%")

    # Reverse: what discount rate equates segment sum PV to price?
    rate = 0.10
    for _ in range(200):
        pv = 0.0
        for name, s in segments.items():
            pv += pv_stream(s["fcf0_sh"], s["g1"], s["g2"], s["exit"], rate)
        pv += sum(-drag_sh / (1 + rate) ** y for y in range(1, 11))
        pv += sum(-corp_drag_sh / (1 + rate) ** y for y in range(1, 11))
        npv = pv - price
        # numerical derivative
        eps = 1e-5
        pv2 = 0.0
        for name, s in segments.items():
            pv2 += pv_stream(s["fcf0_sh"], s["g1"], s["g2"], s["exit"], rate + eps)
        pv2 += sum(-drag_sh / (1 + rate + eps) ** y for y in range(1, 11))
        pv2 += sum(-corp_drag_sh / (1 + rate + eps) ** y for y in range(1, 11))
        d = (pv2 - pv) / eps
        if abs(d) < 1e-12:
            break
        rate -= npv / d
    print(f"Implied business return (segment sum = price) = {rate*100:.1f}%")

    # Terminal value check consolidated
    fcf10 = 5.85 * (1.11**5) * (1.08**5)
    term = fcf10 * 25
    print(f"Lawrence Y10 terminal ~${term:.0f}/sh")


if __name__ == "__main__":
    main()
