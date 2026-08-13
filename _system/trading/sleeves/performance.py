"""XIRR, independence, PLC vs drawdown, conviction calibration."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from math import isfinite, sqrt
from statistics import median
from typing import Any, Iterable, Mapping, Sequence


def _as_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    text = str(value)[:10]
    return date.fromisoformat(text)


def xirr(cashflows: Sequence[tuple[Any, float]], guess: float = 0.1) -> float | None:
    """Money-weighted IRR. Cashflows are (date, amount) with buys negative."""
    rows = [(_as_date(d), float(a)) for d, a in cashflows if a is not None]
    if len(rows) < 2:
        return None
    if all(a >= 0 for _, a in rows) or all(a <= 0 for _, a in rows):
        return None
    t0 = min(d for d, _ in rows)

    def npv(rate: float) -> float:
        total = 0.0
        for d, amount in rows:
            years = (d - t0).days / 365.25
            total += amount / ((1.0 + rate) ** years)
        return total

    def dnpv(rate: float) -> float:
        total = 0.0
        for d, amount in rows:
            years = (d - t0).days / 365.25
            if years == 0:
                continue
            total += -years * amount / ((1.0 + rate) ** (years + 1.0))
        return total

    rate = guess
    for _ in range(80):
        f = npv(rate)
        df = dnpv(rate)
        if abs(df) < 1e-12:
            break
        nxt = rate - f / df
        if nxt <= -0.999:
            nxt = -0.999
        if abs(nxt - rate) < 1e-8:
            return nxt if isfinite(nxt) else None
        rate = nxt
    return rate if isfinite(rate) else None


def _corr(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    n = min(len(xs), len(ys))
    if n < 20:
        return None
    xa, ya = xs[-n:], ys[-n:]
    mx = sum(xa) / n
    my = sum(ya) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(xa, ya))
    vx = sum((a - mx) ** 2 for a in xa)
    vy = sum((b - my) ** 2 for b in ya)
    den = sqrt(vx * vy)
    if den == 0:
        return None
    return cov / den


def independence_score(
    names: Sequence[Mapping[str, Any]],
    returns_by_ticker: Mapping[str, Sequence[float]] | None = None,
    cluster_cap: float = 0.40,
) -> dict[str, Any]:
    """1 - mean(|corr|). Missing returns: same cluster = 1, else 0."""
    tickers = [str(n.get("ticker") or "") for n in names if n.get("ticker")]
    clusters = {str(n.get("ticker")): str(n.get("cluster") or "idiosyncratic") for n in names}
    gross = {str(n.get("ticker")): abs(float(n.get("market_value") or n.get("marketValue") or 0)) for n in names}
    pairs: list[float] = []
    same_cluster_pairs = 0
    pair_count = 0
    for i, a in enumerate(tickers):
        for b in tickers[i + 1 :]:
            pair_count += 1
            if clusters.get(a) == clusters.get(b) and clusters.get(a):
                same_cluster_pairs += 1
            ra = (returns_by_ticker or {}).get(a)
            rb = (returns_by_ticker or {}).get(b)
            if ra and rb:
                c = _corr(list(ra), list(rb))
                pairs.append(abs(c) if c is not None else (1.0 if clusters.get(a) == clusters.get(b) else 0.0))
            else:
                pairs.append(1.0 if clusters.get(a) == clusters.get(b) else 0.0)
    mean_abs = sum(pairs) / len(pairs) if pairs else 0.0
    score = 1.0 - mean_abs
    total_gross = sum(gross.values()) or 1.0
    cluster_w: dict[str, float] = defaultdict(float)
    for t, g in gross.items():
        cluster_w[clusters.get(t, "idiosyncratic")] += g / total_gross
    max_cluster = max(cluster_w.values()) if cluster_w else 0.0
    penalty = max(0.0, max_cluster - cluster_cap)
    return {
        "score": round(max(0.0, score - penalty), 4),
        "mean_abs_corr": round(mean_abs, 4),
        "pair_count": pair_count,
        "same_cluster_pairs": same_cluster_pairs,
        "max_cluster_weight": round(max_cluster, 4),
        "penalty": round(penalty, 4),
        "cluster_weights": {k: round(v, 4) for k, v in cluster_w.items()},
    }


def max_drawdown(nav: Sequence[float]) -> float | None:
    if not nav:
        return None
    peak = nav[0]
    dd = 0.0
    for value in nav:
        peak = max(peak, value)
        if peak:
            dd = min(dd, value / peak - 1.0)
    return dd


def conviction_calibration(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        conv = row.get("conviction")
        if conv in (1, 2, 3, 4, 5):
            buckets[int(conv)].append(row)
    out = []
    for conv in range(1, 6):
        items = buckets.get(conv) or []
        irrs = [float(x["irr"]) for x in items if x.get("irr") is not None]
        plc = sum(1 for x in items if x.get("plc_event"))
        holds = [float(x["years_held"]) for x in items if x.get("years_held") is not None]
        out.append({
            "conviction": conv,
            "count": len(items),
            "avg_irr": round(sum(irrs) / len(irrs), 4) if irrs else None,
            "plc_rate": round(plc / len(items), 4) if items else None,
            "median_years_held": round(median(holds), 3) if holds else None,
        })
    return out


def scorecard(
    *,
    owner: str,
    positions: Sequence[Mapping[str, Any]],
    notes: Sequence[Mapping[str, Any]],
    cashflows: Sequence[Mapping[str, Any]],
    nav_series: Sequence[float] | None = None,
    returns_by_ticker: Mapping[str, Sequence[float]] | None = None,
    capital_base: float | None = None,
) -> dict[str, Any]:
    noted = {str(n.get("ticker")) for n in notes}
    open_pos = [p for p in positions if abs(float(p.get("qty") or 0)) > 1e-9]
    completeness = (sum(1 for p in open_pos if p.get("ticker") in noted) / len(open_pos)) if open_pos else 1.0
    by_ticker: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for cf in cashflows:
        by_ticker[str(cf.get("ticker"))].append((str(cf.get("date")), float(cf.get("amount") or 0)))
    name_irrs = {}
    for ticker, flows in by_ticker.items():
        name_irrs[ticker] = xirr(flows)
    sleeve_flows = [(c["date"], float(c["amount"])) for c in cashflows]
    if capital_base:
        dates = sorted(c["date"] for c in cashflows) if cashflows else []
        start = dates[0] if dates else date.today().isoformat()
        sleeve_flows = [(start, -abs(capital_base))] + sleeve_flows
    independence = independence_score(
        [
            {
                "ticker": p.get("ticker"),
                "cluster": p.get("cluster") or "idiosyncratic",
                "market_value": p.get("marketValue") or p.get("market_value") or 0,
            }
            for p in open_pos
        ],
        returns_by_ticker,
    )
    years = [float(p["years_held"]) for p in open_pos if p.get("years_held") is not None]
    return {
        "owner": owner,
        "completeness": round(completeness, 4),
        "independence": independence,
        "sleeve_xirr": xirr(sleeve_flows) if len(sleeve_flows) >= 2 else None,
        "name_irrs": name_irrs,
        "max_drawdown": max_drawdown(list(nav_series or [])),
        "median_holding_years": round(median(years), 3) if years else None,
        "open_names": len(open_pos),
        "plc_events": sum(1 for p in positions if p.get("plc_event")),
        "conviction_calibration": conviction_calibration(open_pos),
    }
