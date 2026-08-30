#!/usr/bin/env python3
"""Build the governed Tier 1/2/3 valuation research universe.

The registry is a research universe, not a position ledger.  A registry name is
therefore Tier 3 unless another explicit source promotes it.  Tiers allocate
research effort and workflow priority; only a signed ``human_decision.json``
may authorize capital or sizing.
"""
from __future__ import annotations

import argparse
import copy
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
POLICY_REL = Path("_system/portfolio/valuation_universe_policy.json")
OUTPUT_REL = Path("_system/data/valuation_universe_tiers.json")

PRIORITY_STANCES = {"accumulate", "core", "hold"}
APPROVED_TARGET_STATUSES = {"active", "approved", "current", "executed", "executing"}
ACTIVE_WORKBENCH_COMMITTEE_STATUSES = {
    "evidence_blocked",
    "independent_review_open",
    "owner_decision_pending",
    "parked",
    "ready_to_assemble",
}
ACTIVE_COMMITTEE_STAGES = {
    "chair_pending",
    "committee_complete_decision_pending",
    "conditional_escalation",
    "evidence_blocked",
    "independent_review_open",
    "owner_decision_pending",
    "parked",
    "ready_to_assemble",
    "round_one_open",
}
CASH_TICKERS = {"$CASH", "CASH", "CASH_USD", "USD"}


def _ticker(value: Any) -> str:
    return str(value or "").strip().upper()


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _source_bucket(health: dict, group: str, required: bool = False) -> dict:
    return health.setdefault(group, {
        "required": required,
        "files_seen": 0,
        "valid_files": 0,
        "record_count": 0,
        "missing_files": [],
        "invalid_files": [],
    })


def _read_json(path: Path, root: Path, health: dict, group: str,
               *, required: bool = False) -> dict | list:
    bucket = _source_bucket(health, group, required)
    ref = _relative(path, root)
    if not path.exists():
        bucket["missing_files"].append(ref)
        return {}
    bucket["files_seen"] += 1
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        bucket["invalid_files"].append({"path": ref, "error": str(exc)})
        return {}
    if not isinstance(payload, (dict, list)):
        bucket["invalid_files"].append({"path": ref, "error": "top level must be an object or array"})
        return {}
    bucket["valid_files"] += 1
    return payload


def _record_count(health: dict, group: str, count: int) -> None:
    _source_bucket(health, group)["record_count"] += count


def _watchlist_tickers(value: Any) -> set[str]:
    if isinstance(value, dict):
        return {_ticker(key) for key in value if _ticker(key)}
    if isinstance(value, list):
        names = set()
        for row in value:
            names.add(_ticker(row.get("ticker")) if isinstance(row, dict) else _ticker(row))
        return names - {""}
    return set()


def _positive_position(row: dict) -> bool:
    values = [row.get(field) for field in (
        "shares", "quantity", "notional_usd", "market_value", "market_value_usd", "weight_pct"
    )]
    numbers = [_number(value) for value in values]
    return any(value is not None and value > 0 for value in numbers)


def _positive_target(row: dict) -> bool:
    value = _number(row.get("weight_pct", row.get("target_weight_pct", row.get("weight"))))
    return value is None or value > 0


def _override_tier(value: Any) -> int | None:
    if isinstance(value, str):
        value = value.lower().replace("tier_", "").replace("tier ", "")
    try:
        tier = int(value)
    except (TypeError, ValueError):
        return None
    return tier if tier in {1, 2, 3} else None


def validate_policy(policy: dict) -> None:
    errors = []
    if policy.get("schema_version") != "1.0":
        errors.append("schema_version must be 1.0")
    governance = policy.get("governance") or {}
    if governance.get("capital_authority") != "human_decision_only":
        errors.append("governance.capital_authority must be human_decision_only")
    if governance.get("automated_model_cap") != "screening_only":
        errors.append("automated_model_cap must be screening_only")
    if governance.get("generic_model_cap") != "screening_only":
        errors.append("generic_model_cap must be screening_only")
    definitions = policy.get("tier_definitions") or {}
    required_definition_fields = {
        "tier", "label", "research_depth", "actionability_cap",
        "promotion_gates", "demotion_conditions", "workflow_policy",
    }
    for tier in (1, 2, 3):
        tier_id = f"tier_{tier}"
        definition = definitions.get(tier_id) or {}
        missing = sorted(required_definition_fields - set(definition))
        if missing:
            errors.append(f"{tier_id} missing fields: {', '.join(missing)}")
            continue
        if definition.get("tier") != tier:
            errors.append(f"{tier_id}.tier must be {tier}")
        workflow = definition.get("workflow_policy") or {}
        if workflow.get("capital_authority") != "human_decision_only":
            errors.append(f"{tier_id} capital authority must be human_decision_only")
        if workflow.get("automated_screen_can_authorize_capital") is not False:
            errors.append(f"{tier_id} automated screens must not authorize capital")
        if workflow.get("generic_screen_can_authorize_capital") is not False:
            errors.append(f"{tier_id} generic screens must not authorize capital")
        if tier > 1 and workflow.get("committee_auto_start") is not False:
            errors.append(f"{tier_id} committee_auto_start must be false")
    overrides = policy.get("overrides") or {}
    if not isinstance(overrides, dict):
        errors.append("overrides must be a ticker-keyed object")
    else:
        for ticker, override in overrides.items():
            if not _ticker(ticker) or not isinstance(override, dict):
                errors.append(f"invalid override entry for {ticker!r}")
                continue
            if _override_tier(override.get("tier")) is None:
                errors.append(f"override {ticker} must declare tier 1, 2, or 3")
            if not str(override.get("reason") or "").strip():
                errors.append(f"override {ticker} must include a reason")
    if errors:
        raise ValueError("Invalid valuation universe policy: " + "; ".join(errors))


def _add_signal(signals: dict[str, list[dict]], universe: set[str], ticker: Any,
                tier: int, code: str, detail: str, source_ref: str) -> None:
    name = _ticker(ticker)
    if not name or name in CASH_TICKERS:
        return
    universe.add(name)
    signal = {
        "qualifying_tier": tier,
        "code": code,
        "detail": detail,
        "source_ref": source_ref,
    }
    if signal not in signals[name]:
        signals[name].append(signal)


def _collect_registry(root: Path, health: dict, signals: dict, universe: set[str]) -> dict:
    path = root / "_system/portfolio/registry.json"
    payload = _read_json(path, root, health, "registry", required=True)
    payload = payload if isinstance(payload, dict) else {}
    holdings = payload.get("holdings") or {}
    if not isinstance(holdings, dict):
        holdings = {}
    ref = _relative(path, root)
    for ticker in sorted(holdings):
        _add_signal(signals, universe, ticker, 3, "research_universe_member",
                    "Registry membership establishes research coverage only; it is not evidence of ownership.", ref)
    watchlist = _watchlist_tickers(payload.get("watchlist"))
    for ticker in sorted(watchlist):
        _add_signal(signals, universe, ticker, 2, "registry_watchlist",
                    "The security is on the curated registry watchlist.", ref)
    _record_count(health, "registry", len(holdings) + len(watchlist))
    return holdings


def _collect_positions(root: Path, health: dict, signals: dict, universe: set[str]) -> None:
    paths = sorted((root / "_system/portfolio/paper").glob("*.json"))
    _source_bucket(health, "paper_positions")
    for path in paths:
        payload = _read_json(path, root, health, "paper_positions")
        payload = payload if isinstance(payload, dict) else {}
        positions = payload.get("positions") or []
        if not isinstance(positions, list):
            positions = []
        account = str(payload.get("account_id") or path.stem)
        count = 0
        for row in positions:
            if not isinstance(row, dict) or not _positive_position(row):
                continue
            count += 1
            _add_signal(signals, universe, row.get("ticker"), 1, "positive_paper_position",
                        f"Positive position in the {account} paper portfolio.", _relative(path, root))
        _record_count(health, "paper_positions", count)


def _collect_followups(root: Path, health: dict, signals: dict, universe: set[str]) -> None:
    path = root / "_system/reference/valuation_followups.json"
    payload = _read_json(path, root, health, "valuation_followups")
    payload = payload if isinstance(payload, dict) else {}
    ref = _relative(path, root)
    tickers = payload.get("tickers") or {}
    if isinstance(tickers, dict):
        for ticker in sorted(tickers):
            _add_signal(signals, universe, ticker, 2, "valuation_followup",
                        "The curated valuation follow-up ledger includes this security.", ref)
    cohort = payload.get("validation_cohort") or payload.get("securities") or []
    if isinstance(cohort, list):
        for row in cohort:
            ticker = row.get("ticker") if isinstance(row, dict) else row
            _add_signal(signals, universe, ticker, 2, "validation_cohort",
                        "The security is in the cross-method valuation validation cohort.", ref)
    _record_count(health, "valuation_followups",
                  (len(tickers) if isinstance(tickers, dict) else 0) + (len(cohort) if isinstance(cohort, list) else 0))


def _collect_classifications(root: Path, health: dict, signals: dict, universe: set[str],
                             registry_holdings: dict) -> None:
    path = root / "_system/portfolio/classification.json"
    payload = _read_json(path, root, health, "classifications")
    payload = payload if isinstance(payload, dict) else {}
    ref = _relative(path, root)
    names = set(payload) | set(registry_holdings)
    count = 0
    for ticker in sorted(names):
        standalone = payload.get(ticker) if isinstance(payload.get(ticker), dict) else None
        registry_row = registry_holdings.get(ticker) if isinstance(registry_holdings.get(ticker), dict) else {}
        classification = standalone or (registry_row.get("classification") or {})
        stance = str(classification.get("stance") or "").strip().lower()
        if stance not in PRIORITY_STANCES:
            continue
        count += 1
        source = ref if standalone else "_system/portfolio/registry.json"
        _add_signal(signals, universe, ticker, 2, "priority_classification",
                    f"Portfolio classification stance is {stance}.", source)
    _record_count(health, "classifications", count)


def _collect_targets(root: Path, health: dict, signals: dict, universe: set[str]) -> None:
    paths = sorted((root / "_system/portfolio").glob("*_target_weights.json"))
    _source_bucket(health, "target_weights")
    for path in paths:
        payload = _read_json(path, root, health, "target_weights")
        payload = payload if isinstance(payload, dict) else {}
        status = str(payload.get("status") or "").strip().lower()
        rows = payload.get("weights") or payload.get("targets") or []
        if not isinstance(rows, list):
            rows = []
        qualifying_tier = 1 if status in APPROVED_TARGET_STATUSES else 2 if status == "proposed" else None
        count = 0
        if qualifying_tier:
            for row in rows:
                if not isinstance(row, dict) or not _positive_target(row):
                    continue
                count += 1
                code = "approved_target_allocation" if qualifying_tier == 1 else "proposed_target_allocation"
                detail = ("Positive allocation in an approved/current target-weight plan."
                          if qualifying_tier == 1 else
                          "Positive allocation in a proposed, not-yet-approved target-weight plan.")
                _add_signal(signals, universe, row.get("ticker"), qualifying_tier,
                            code, detail, _relative(path, root))
        _record_count(health, "target_weights", count)


def _collect_workbenches(root: Path, health: dict, signals: dict, universe: set[str]) -> None:
    paths = sorted(root.glob("*/research/valuation_workbench.json"))
    _source_bucket(health, "committee_workbenches")
    for path in paths:
        payload = _read_json(path, root, health, "committee_workbenches")
        payload = payload if isinstance(payload, dict) else {}
        committee = payload.get("committee") or {}
        status = str(committee.get("status") or "").strip().lower()
        has_committee = bool(
            committee.get("manifest_ref") or committee.get("record_ref") or committee.get("stage")
            or (committee.get("analysis_progress") or {}).get("completed")
        )
        if status not in ACTIVE_WORKBENCH_COMMITTEE_STATUSES or (status == "evidence_blocked" and not has_committee):
            continue
        ticker = payload.get("ticker") or path.parents[1].name
        _add_signal(signals, universe, ticker, 1, "active_committee",
                    f"Valuation committee workflow is active with status {status}.", _relative(path, root))
        _record_count(health, "committee_workbenches", 1)


def _collect_committee_manifests(root: Path, health: dict, signals: dict, universe: set[str]) -> None:
    paths = sorted(root.glob("*/research/committee_work/????-??-??/manifest.json"))
    _source_bucket(health, "committee_manifests")
    latest: dict[str, Path] = {}
    for path in paths:
        latest[path.parents[3].name.upper()] = path
    for ticker, path in sorted(latest.items()):
        payload = _read_json(path, root, health, "committee_manifests")
        payload = payload if isinstance(payload, dict) else {}
        stage = str(payload.get("stage") or "").strip().lower()
        if stage not in ACTIVE_COMMITTEE_STAGES:
            continue
        _add_signal(signals, universe, payload.get("ticker") or ticker, 1, "active_committee_manifest",
                    f"Latest committee manifest remains active at stage {stage}.", _relative(path, root))
        _record_count(health, "committee_manifests", 1)


def _collect_triggers(root: Path, health: dict, signals: dict, universe: set[str]) -> None:
    paths = sorted(root.glob("*/research/committee_trigger.json"))
    _source_bucket(health, "committee_triggers")
    for path in paths:
        payload = _read_json(path, root, health, "committee_triggers")
        payload = payload if isinstance(payload, dict) else {}
        if str(payload.get("status") or "").strip().lower() != "open":
            continue
        reason = str(payload.get("reason") or "material thesis, evidence, or price change")
        _add_signal(signals, universe, payload.get("ticker") or path.parents[1].name, 1,
                    "open_committee_trigger", f"Open committee trigger: {reason}", _relative(path, root))
        _record_count(health, "committee_triggers", 1)


def _collect_human_decisions(root: Path, as_of: str, health: dict,
                             signals: dict, universe: set[str]) -> None:
    paths = sorted(root.glob("*/research/human_decision.json"))
    _source_bucket(health, "human_decisions")
    for path in paths:
        payload = _read_json(path, root, health, "human_decisions")
        payload = payload if isinstance(payload, dict) else {}
        status = str(payload.get("status") or "").strip().lower()
        if status not in {"decided", "expired"} or not payload.get("decision"):
            continue
        expires_at = str(payload.get("expires_at") or "")[:10]
        expired = status == "expired" or bool(expires_at and expires_at < as_of[:10])
        code = "expired_human_decision" if expired else "current_human_decision"
        detail = ("The recorded owner decision is expired and requires review."
                  if expired else "A current recorded owner decision governs this security.")
        _add_signal(signals, universe, payload.get("ticker") or path.parents[1].name, 1,
                    code, detail, _relative(path, root))
        _record_count(health, "human_decisions", 1)


def _finalize_health(health: dict) -> dict:
    degraded = False
    for group in sorted(health):
        bucket = health[group]
        bucket["missing_files"] = sorted(set(bucket["missing_files"]))
        bucket["invalid_files"] = sorted(bucket["invalid_files"], key=lambda row: row["path"])
        if bucket["invalid_files"] or (bucket["required"] and bucket["missing_files"]):
            degraded = True
    return {"status": "degraded" if degraded else "healthy", "sources": {key: health[key] for key in sorted(health)}}


def _assignment_validation(assignments: dict[str, dict], source_health: dict) -> dict:
    errors = []
    required = {
        "tier", "tier_id", "label", "research_depth", "actionability_cap",
        "assignment_reasons", "promotion_gates", "demotion_conditions", "workflow_policy",
    }
    for ticker, row in assignments.items():
        missing = sorted(required - set(row))
        if missing:
            errors.append(f"{ticker} missing assignment fields: {', '.join(missing)}")
            continue
        workflow = row.get("workflow_policy") or {}
        if workflow.get("capital_authority") != "human_decision_only":
            errors.append(f"{ticker} does not preserve human-only capital authority")
        if workflow.get("automated_screen_can_authorize_capital") is not False:
            errors.append(f"{ticker} permits automated capital authority")
        if workflow.get("generic_screen_can_authorize_capital") is not False:
            errors.append(f"{ticker} permits generic-screen capital authority")
        if row["tier"] > 1 and workflow.get("committee_auto_start") is not False:
            errors.append(f"{ticker} Tier {row['tier']} improperly permits committee auto-start")
        codes = {reason.get("code") for reason in row.get("assignment_reasons") or []}
        if row.get("assignment_source") == "automatic" and codes == {"research_universe_member"} and row["tier"] != 3:
            errors.append(f"{ticker} registry membership alone promoted above Tier 3")
    if source_health.get("status") == "degraded":
        errors.append("one or more required or present source files could not be read")
    return {
        "status": "pass" if not errors else "fail",
        "errors": errors,
        "checks": {
            "all_assignments_complete": not any("missing assignment fields" in row for row in errors),
            "registry_membership_is_not_position_evidence": not any("registry membership alone" in row for row in errors),
            "human_only_capital_authority": not any("capital authority" in row for row in errors),
            "automated_and_generic_screens_cannot_authorize_capital": not any("permits" in row for row in errors),
            "tier_2_and_tier_3_disable_committee_auto_start": not any("committee auto-start" in row for row in errors),
            "source_health_acceptable": source_health.get("status") == "healthy",
        },
    }


def build(as_of: str, root: Path = ROOT) -> dict:
    root = Path(root)
    health: dict[str, dict] = {}
    policy_path = root / POLICY_REL
    policy_payload = _read_json(policy_path, root, health, "policy", required=True)
    policy = policy_payload if isinstance(policy_payload, dict) else {}
    validate_policy(policy)

    signals: dict[str, list[dict]] = defaultdict(list)
    universe: set[str] = set()
    registry_holdings = _collect_registry(root, health, signals, universe)
    _collect_positions(root, health, signals, universe)
    _collect_followups(root, health, signals, universe)
    _collect_classifications(root, health, signals, universe, registry_holdings)
    _collect_targets(root, health, signals, universe)
    _collect_workbenches(root, health, signals, universe)
    _collect_committee_manifests(root, health, signals, universe)
    _collect_triggers(root, health, signals, universe)
    _collect_human_decisions(root, as_of, health, signals, universe)

    overrides = policy.get("overrides") or {}
    universe.update(_ticker(ticker) for ticker in overrides if _ticker(ticker))
    definitions = policy["tier_definitions"]
    assignments = {}
    for ticker in sorted(universe):
        observed = sorted(signals[ticker], key=lambda row: (
            row["qualifying_tier"], row["code"], row["source_ref"], row["detail"]
        ))
        automatic_tier = min((row["qualifying_tier"] for row in observed), default=3)
        override = overrides.get(ticker) or overrides.get(ticker.lower())
        final_tier = _override_tier((override or {}).get("tier")) if override else automatic_tier
        assignment_source = "owner_override" if override else "automatic"
        if override:
            observed.append({
                "qualifying_tier": final_tier,
                "code": "owner_override",
                "detail": str(override["reason"]).strip(),
                "source_ref": POLICY_REL.as_posix(),
            })
            observed = sorted(observed, key=lambda row: (
                row["qualifying_tier"], row["code"], row["source_ref"], row["detail"]
            ))
        definition = definitions[f"tier_{final_tier}"]
        assignments[ticker] = {
            "ticker": ticker,
            "tier": final_tier,
            "tier_id": f"tier_{final_tier}",
            "label": definition["label"],
            "research_depth": definition["research_depth"],
            "actionability_cap": definition["actionability_cap"],
            "assignment_source": assignment_source,
            "automatic_tier": automatic_tier,
            "override_reason": str((override or {}).get("reason") or "").strip() or None,
            "review_by": (override or {}).get("review_by"),
            "review_overdue": bool((override or {}).get("review_by") and str(override["review_by"])[:10] < as_of[:10]),
            "assignment_reasons": observed,
            "promotion_gates": copy.deepcopy(definition["promotion_gates"]),
            "demotion_conditions": copy.deepcopy(definition["demotion_conditions"]),
            "workflow_policy": copy.deepcopy(definition["workflow_policy"]),
        }

    source_health = _finalize_health(health)
    tier_counts = {
        f"tier_{tier}": sum(row["tier"] == tier for row in assignments.values())
        for tier in (1, 2, 3)
    }
    manifest = {
        "schema_version": "1.0",
        "as_of": as_of[:10],
        "policy_id": policy.get("policy_id"),
        "policy_ref": POLICY_REL.as_posix(),
        "universe_semantics": {
            "registry_holdings": "research universe membership only; never treated as owned positions",
            "tier_purpose": "research depth and workflow priority, not capital authorization",
            "capital_authority": "human_decision_only",
            "automated_and_generic_models": "screening only; never authorize capital",
        },
        "summary": {
            "security_count": len(assignments),
            "tier_counts": tier_counts,
            "owner_override_count": sum(row["assignment_source"] == "owner_override" for row in assignments.values()),
            "automatic_assignment_count": sum(row["assignment_source"] == "automatic" for row in assignments.values()),
        },
        "source_health": source_health,
        "assignments": assignments,
    }
    manifest["validation"] = _assignment_validation(assignments, source_health)
    return manifest


def render(payload: dict) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=datetime.now(timezone.utc).date().isoformat())
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--check", action="store_true", help="Fail when the committed manifest differs from a fresh build.")
    args = parser.parse_args()
    payload = build(args.date, args.root)
    target = args.out or args.root / OUTPUT_REL
    expected = render(payload)
    if args.check:
        actual = target.read_text(encoding="utf-8") if target.exists() else ""
        if actual != expected:
            print(f"valuation universe tier manifest is stale: {target}")
            return 1
        print(f"valuation universe tier manifest is current: {target}")
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(expected, encoding="utf-8")
    print(json.dumps(payload["summary"], sort_keys=True))
    return 0 if payload["validation"]["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
