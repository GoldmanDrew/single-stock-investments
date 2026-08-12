#!/usr/bin/env python3
"""Build the contract-first warrant dashboard feed."""
from __future__ import annotations

from datetime import date

from warrant_common import (
    CALIBRATION_PATH,
    COHORTS_PATH,
    DASHBOARD_PATH,
    DISCOVERY_STATE_PATH,
    EVENTS_PATH,
    MARKET_PATH,
    OUTCOMES_PATH,
    finite_number,
    gate_state,
    latest_registry,
    load_jsonl,
    market_pair,
    parse_date,
    quote_age_days,
    read_json,
    utc_now,
    validate_registry,
    write_json,
)


def _round(value: float | None, digits: int = 4) -> float | None:
    return round(value, digits) if value is not None else None


def _priority(record: dict, gates: dict, days_to_expiry: int | None) -> tuple[str, list[str]]:
    reasons: list[str] = []
    lifecycle = record.get("lifecycle")
    if lifecycle not in {"active", "candidate"}:
        return "closed", [f"Lifecycle is {lifecycle}; retained for survivorship-free history."]
    if days_to_expiry is not None and days_to_expiry <= 45:
        reasons.append(f"Only {days_to_expiry} days remain on the contract clock.")
    if record.get("lane") == "chapter_11":
        reasons.append("Post-reorganization security: complete claim stack and Chapter 22 review.")
    if not gates["identity"]["pass"]:
        reasons.append("Terms or identity can be resolved from primary documents.")
    elif not gates["survival"]["pass"]:
        reasons.append("Contract verified; issuer survival packet is the next decision gate.")
    elif not gates["market"]["pass"]:
        reasons.append("Obtain an executable bid/ask before comparing model value with cost.")
    if days_to_expiry is not None and days_to_expiry <= 45:
        return "urgent", reasons
    if record.get("lane") == "chapter_11" or gates["status"] == "review_ready":
        return "active", reasons
    return "monitor", reasons


def _build_row(record: dict, market_doc: dict) -> dict:
    warrant_quote, common_quote = market_pair(record, market_doc)
    gates = gate_state(record, warrant_quote, common_quote)
    terms = record.get("terms") or {}
    expiry = parse_date(terms.get("expiry"))
    issue = parse_date(terms.get("issue_date") or record.get("effective_date"))
    days_to_expiry = (expiry - date.today()).days if expiry else None
    total_days = (expiry - issue).days if expiry and issue else None
    elapsed_days = (date.today() - issue).days if issue else None
    clock_pct = None
    if total_days and elapsed_days is not None:
        clock_pct = max(0.0, min(100.0, elapsed_days / total_days * 100))
    spot = finite_number(common_quote.get("close"))
    warrant_price = finite_number(warrant_quote.get("close"))
    strike = finite_number(terms.get("strike"))
    ratio = finite_number(terms.get("share_ratio"))
    intrinsic = None
    parity_premium = None
    breakeven = None
    moneyness_pct = None
    cagr_to_breakeven_pct = None
    exercise_cost = None
    if strike is not None and ratio and ratio > 0:
        exercise_cost = strike * ratio if terms.get("strike_basis") == "per_share" else strike
    if spot is not None and exercise_cost is not None and ratio and ratio > 0:
        intrinsic = max(spot * ratio - exercise_cost, 0.0)
        moneyness_pct = (spot * ratio / exercise_cost - 1) * 100 if exercise_cost > 0 else None
        if warrant_price is not None:
            parity_premium = warrant_price - intrinsic
            breakeven = (exercise_cost + warrant_price) / ratio
            # Annualizing a move over a near-expiry stub produces a spectacular
            # but useless number. Show the raw move for <90d clocks instead.
            if days_to_expiry and days_to_expiry >= 90 and spot > 0 and breakeven > 0:
                cagr_to_breakeven_pct = ((breakeven / spot) ** (365.0 / days_to_expiry) - 1) * 100
    move_to_breakeven_pct = (
        (breakeven / spot - 1) * 100
        if breakeven is not None and spot is not None and spot > 0
        else None
    )
    outstanding = finite_number(terms.get("warrants_outstanding"))
    basic_shares = finite_number((record.get("survival") or {}).get("basic_shares"))
    overhang_pct = outstanding * ratio / basic_shares * 100 if outstanding and ratio and basic_shares else None
    priority, priority_reasons = _priority(record, gates, days_to_expiry)
    return {
        "warrant_id": record.get("warrant_id"),
        "issuer": record.get("issuer"),
        "cik": record.get("cik"),
        "common_ticker": record.get("common_ticker"),
        "warrant_ticker": record.get("warrant_ticker"),
        "exchange": record.get("exchange"),
        "lane": record.get("lane"),
        "classification": record.get("classification"),
        "lifecycle": record.get("lifecycle"),
        "status": gates.get("status"),
        "priority": priority,
        "priority_reasons": priority_reasons,
        "gates": gates,
        "terms": terms,
        "contract_clock": {
            "issue_date": terms.get("issue_date") or record.get("effective_date"),
            "expiry": terms.get("expiry"),
            "days_to_expiry": days_to_expiry,
            "elapsed_pct": _round(clock_pct, 2),
            "callable": bool(terms.get("callable")),
            "call": terms.get("call"),
            "threshold": terms.get("threshold"),
        },
        "market": {
            "common": common_quote,
            "warrant": warrant_quote,
            "quote_age_days": quote_age_days(warrant_quote),
            "executable": gates["market"]["pass"],
        },
        "diagnostics": {
            "intrinsic_value": _round(intrinsic),
            "exercise_cost_per_warrant": _round(exercise_cost),
            "parity_premium": _round(parity_premium),
            "breakeven_common": _round(breakeven),
            "moneyness_pct": _round(moneyness_pct, 2),
            "cagr_to_breakeven_pct": _round(cagr_to_breakeven_pct, 2),
            "move_to_breakeven_pct": _round(move_to_breakeven_pct, 2),
            "diluted_overhang_pct": _round(overhang_pct, 2),
            "model_route": "clause_aware_pending" if terms.get("callable") or terms.get("threshold") else "dilution_aware_pending",
            "fair_value": None,
            "opportunity_score": None,
            "warning": "Delayed closes are diagnostics, not executable prices or fair values.",
        },
        "survival": record.get("survival") or {},
        "source": record.get("source") or {},
        "corporate_action": record.get("corporate_action"),
        "next_action": record.get("next_action"),
    }


def _serve_events(events: list[dict]) -> list[dict]:
    """One visible row per accession, retaining the strongest exhibit."""
    by_accession: dict[str, dict] = {}
    for event in events:
        accession = str(event.get("accession") or event.get("event_id") or "")
        recorded_score = event.get("research_priority_score")
        score = int(recorded_score or 0)
        file_type = str(event.get("file_type") or "").upper()
        description = str(event.get("description") or "").lower()
        items = {str(item) for item in event.get("items") or []}
        if recorded_score is None:
            if file_type.startswith("EX-4"):
                score += 4
            if "warrant" in description:
                score += 5
            if "1.03" in items:
                score += 5
            if "3.02" in items:
                score += 2
        candidate = {**event, "research_priority_score": score}
        prior = by_accession.get(accession)
        if prior is None or score > int(prior.get("research_priority_score") or 0):
            by_accession[accession] = candidate
    return sorted(
        by_accession.values(),
        key=lambda row: (int(row.get("research_priority_score") or 0), str(row.get("filed_at") or "")),
        reverse=True,
    )


def build() -> dict:
    registry_errors = validate_registry()
    market_doc = read_json(MARKET_PATH, {}) or {}
    rows = [_build_row(record, market_doc) for record in latest_registry()]
    rows.sort(
        key=lambda row: (
            {"urgent": 0, "active": 1, "monitor": 2, "closed": 3}.get(str(row.get("priority")), 4),
            row.get("contract_clock", {}).get("days_to_expiry") if row.get("contract_clock", {}).get("days_to_expiry") is not None else 10**9,
            str(row.get("warrant_ticker")),
        )
    )
    events = sorted(load_jsonl(EVENTS_PATH), key=lambda row: str(row.get("filed_at") or ""), reverse=True)
    unresolved_events = _serve_events(
        [row for row in events if row.get("resolution_state") == "pending"]
    )
    alerts: list[dict] = []
    for row in rows:
        clock = row.get("contract_clock") or {}
        dte = clock.get("days_to_expiry")
        if row.get("lifecycle") == "active" and dte is not None and dte <= 60:
            alerts.append({
                "severity": "high" if dte <= 30 else "medium",
                "kind": "contract_clock",
                "warrant_id": row.get("warrant_id"),
                "ticker": row.get("warrant_ticker"),
                "message": f"{dte} days to contractual expiry; verify exchange cutoff and settlement mechanics.",
            })
        age = (row.get("market") or {}).get("quote_age_days")
        if row.get("lifecycle") == "active" and (age is None or age > 5):
            alerts.append({
                "severity": "medium",
                "kind": "stale_market",
                "warrant_id": row.get("warrant_id"),
                "ticker": row.get("warrant_ticker"),
                "message": "Delayed warrant mark is missing or stale; last-known-good terms remain intact.",
            })
    if unresolved_events:
        alerts.insert(0, {
            "severity": "medium",
            "kind": "unresolved_sec_events",
            "message": f"{len(unresolved_events)} SEC warrant filing(s) await identity and terms review.",
        })
    discovery_state = read_json(DISCOVERY_STATE_PATH, {}) or {}
    calibration = read_json(CALIBRATION_PATH, {}) or {}
    cohorts = load_jsonl(COHORTS_PATH)
    outcomes = load_jsonl(OUTCOMES_PATH)
    active = [row for row in rows if row.get("lifecycle") == "active"]
    market_success = parse_date(market_doc.get("last_successful_refresh"))
    market_age_days = (date.today() - market_success).days if market_success else None
    market_freshness_state = (
        "ready" if market_age_days is not None and market_age_days <= 5
        else "stale" if market_success else "unavailable"
    )
    stale_active_quotes = [
        str(row.get("warrant_ticker"))
        for row in active
        if (row.get("market") or {}).get("quote_age_days") is None
        or int((row.get("market") or {}).get("quote_age_days")) > 5
    ]
    health_unhealthy = bool(
        registry_errors or discovery_state.get("unhealthy")
        or market_freshness_state != "ready" or stale_active_quotes
    )
    return {
        "schema_version": "1.0",
        "generated_at": utc_now(),
        "title": "Rare warrant opportunity monitor",
        "policy": {
            "research_only": True,
            "trade_authority": False,
            "score_rule": "No executable score until identity, survival, and two-sided market gates pass.",
            "collateral_rule": "A long warrant is not treated as covered-call collateral without account-specific broker confirmation.",
        },
        "summary": {
            "registry_series": len(rows),
            "active_series": len(active),
            "review_ready": sum(row.get("status") == "review_ready" for row in active),
            "terms_blocked": sum(row.get("status") == "terms_blocked" for row in active),
            "survival_blocked": sum(row.get("status") == "survival_blocked" for row in active),
            "market_blocked": sum(row.get("status") == "market_blocked" for row in active),
            "near_expiry": sum((row.get("contract_clock") or {}).get("days_to_expiry") is not None and (row.get("contract_clock") or {}).get("days_to_expiry") <= 60 for row in active),
            "unresolved_events": len(unresolved_events),
            "alerts": len(alerts),
        },
        "health": {
            "status": "unhealthy" if health_unhealthy else "healthy",
            "structural_errors": registry_errors,
            "discovery": discovery_state,
            "market_generated_at": market_doc.get("generated_at"),
            "market_last_successful_refresh": market_doc.get("last_successful_refresh"),
            "market_age_days": market_age_days,
            "market_freshness_state": market_freshness_state,
            "stale_active_quotes": stale_active_quotes,
            "last_known_good_preserved": (market_doc.get("summary") or {}).get("preserved_last_known_good", False),
            "healers": [
                "python _system/scripts/refresh_warrant_universe.py --refresh-market --capture-cohort",
                "python _system/scripts/refresh_warrant_universe.py --discover --discover-days 14",
                "python _system/scripts/check_warrant_universe.py --strict",
            ],
        },
        "learning_loop": {
            "cohort_count": len(cohorts),
            "resolved_outcome_count": len(outcomes),
            "calibration": calibration,
            "next_resolution": "90- and 365-day outcomes resolve from append-only market history.",
            "automatic_weight_changes": False,
        },
        "alerts": alerts,
        "rows": rows,
        "events": unresolved_events[:50],
    }


def main() -> int:
    payload = build()
    write_json(DASHBOARD_PATH, payload)
    print(
        f"warrant dashboard: {payload['summary']['active_series']} active; "
        f"{payload['summary']['unresolved_events']} unresolved event(s); "
        f"health={payload['health']['status']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
