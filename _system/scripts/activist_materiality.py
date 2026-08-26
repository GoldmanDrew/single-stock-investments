"""Deterministic materiality scoring for activist feed rows.

Score components (all multiplicative, normalized to 0-100):
  filing base   -- what kind of event this is (13D > proxy > publisher short > 13G)
  stake factor  -- disclosed ownership percent scales conviction
  firm weight   -- registry tier 1 firms carry more signal than unknown filers
  freshness     -- exponential decay, one-year half-life
  book factor   -- holdings > watchlist > everything else
  campaign      -- sustained multi-filing campaigns get a small boost
  verification  -- weak matches / unverified document bodies get crushed
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

from activist_common import PUBLISHER_SOURCES, load_firm_registry
from sec_filer_parse import PROXY_FORMS, normalize_form

SIGNAL_THRESHOLD = 55
NOISE_THRESHOLD = 25

_FIRM_TIERS: dict[str, int] | None = None


def _firm_tiers() -> dict[str, int]:
    global _FIRM_TIERS
    if _FIRM_TIERS is None:
        tiers: dict[str, int] = {}
        for firm in load_firm_registry().get("firms") or []:
            fid = firm.get("id")
            if fid:
                tiers[fid] = int(firm.get("tier") or 3)
        _FIRM_TIERS = tiers
    return _FIRM_TIERS


def firm_weight(firm_id: str | None) -> float:
    if not firm_id or firm_id == "unknown_activist":
        return 0.55
    tier = _firm_tiers().get(firm_id)
    if tier == 1:
        return 1.0
    if tier == 2:
        return 0.85
    if firm_id.startswith("sec_filer:"):
        # Resolved from the SEC cover page but not in our registry.
        return 0.7
    return 0.6


def filing_base_weight(row: dict) -> float:
    filing_class = row.get("filing_class") or ""
    # Normalize so a post-2024 "SCHEDULE 13D/A" scores as the amendment it is.
    form = normalize_form((row.get("form") or "").upper())
    if filing_class == "activist_proxy" or form in PROXY_FORMS:
        return 0.88
    if filing_class == "activist_13d":
        return 0.8 if form.endswith("/A") else 0.92
    if filing_class in ("activist_13g", "registry_13g"):
        return 0.55
    if filing_class in {"open_letter", "campaign_presentation"}:
        return 0.86
    if filing_class == "press_campaign":
        return 0.78
    if filing_class == "publisher_report":
        return 0.72
    if filing_class == "short_markdown":
        return 0.55
    if row.get("source") == "press_wire":
        return 0.8
    if row.get("source") == "sec_edgar":
        return 0.6
    return 0.5


def stake_factor(stake_percent: float | None) -> float:
    if stake_percent is None:
        return 1.0
    pct = max(0.0, min(float(stake_percent), 100.0))
    # 0% -> 0.85, >=15% -> 1.15
    return 0.85 + 0.3 * min(pct / 15.0, 1.0)


def freshness_factor(report_date: str | None, *, now: datetime | None = None) -> float:
    if not report_date:
        return 0.55
    try:
        dt = datetime.strptime(str(report_date)[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return 0.55
    now = now or datetime.now(timezone.utc)
    days = max(0.0, (now - dt).total_seconds() / 86400.0)
    return max(0.3, math.pow(0.5, days / 365.0))


def book_factor(*, in_holdings: bool, in_watchlist: bool) -> float:
    if in_holdings:
        return 1.0
    if in_watchlist:
        return 0.72
    return 0.45


def campaign_factor(group_size: int | None) -> float:
    size = max(1, int(group_size or 1))
    return 1.0 + 0.05 * min(size - 1, 4)


def verification_factor(row: dict) -> float:
    factor = 1.0
    if row.get("source") in PUBLISHER_SOURCES and not row.get("target_verified"):
        factor *= 0.1
    if row.get("body_verified") is False:
        factor *= 0.45
    if row.get("weak_match"):
        factor *= 0.5
    if row.get("file_exists") is False:
        factor *= 0.9
    return factor


def materiality_score(
    row: dict,
    *,
    in_holdings: bool = True,
    in_watchlist: bool = False,
    now: datetime | None = None,
) -> tuple[int, dict]:
    components = {
        "base": filing_base_weight(row),
        "stake": stake_factor(row.get("stake_percent")),
        "firm": firm_weight(row.get("firm_id")),
        "freshness": freshness_factor(row.get("report_date"), now=now),
        "book": book_factor(in_holdings=in_holdings, in_watchlist=in_watchlist),
        "campaign": campaign_factor(row.get("campaign_group_size")),
        "verification": verification_factor(row),
    }
    campaign_floor = row.get("campaign_freshness_floor")
    if campaign_floor is not None:
        components["freshness"] = max(components["freshness"], float(campaign_floor))
    raw = 100.0
    for value in components.values():
        raw *= value
    score = max(1, min(100, round(raw)))
    floor = row.get("materiality_floor")
    floor_allowed = row.get("source") not in PUBLISHER_SOURCES or row.get("target_verified") is True
    if floor is not None and floor_allowed:
        score = max(score, int(floor))
    return score, components


def materiality_tier(score: int, row: dict) -> str:
    if row.get("source") in PUBLISHER_SOURCES and not row.get("target_verified"):
        return "noise"
    if row.get("body_verified") is False or row.get("weak_match"):
        return "noise"
    triage = row.get("triage_verdict")
    if triage == "auto_signal":
        return "signal"
    if triage == "auto_passive" or triage == "auto_noise":
        return "noise"
    if triage == "auto_context":
        return "context"
    if score >= SIGNAL_THRESHOLD:
        return "signal"
    if score < NOISE_THRESHOLD:
        return "noise"
    return "context"
