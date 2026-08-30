#!/usr/bin/env python3
"""Build the canonical three-tier valuation research universe.

Tiering controls research depth and automated workflow progression.  It does
not grant capital authority: only a valid human_decision.json may do that.

The portfolio registry's ``holdings`` key is intentionally treated as the
research universe, not as evidence that a security is currently owned.  The
only automatic active-position inputs are positive positions in the canonical
paper account states.  Automated valuation outputs, prices, returns, and model
grades are deliberately absent from the promotion inputs.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "_system" / "data" / "valuation_universe_tiers.json"
POLICY_PATH = "_system/portfolio/valuation_universe_policy.json"

PAPER_POSITION_PATHS = (
    "_system/portfolio/paper/taxable.json",
    "_system/portfolio/paper/roth.json",
)
TARGET_WEIGHT_PATHS = (
    "_system/portfolio/taxable_target_weights.json",
    "_system/portfolio/ira_target_weights.json",
    "_system/portfolio/roth_target_weights.json",
)

ACTIVE_COMMITTEE_STATES = {
    "round_one_open",
    "independent_review_open",
    "conditional_escalation",
    "chair_pending",
    "ready_to_assemble",
    "parked",
    "evidence_blocked",
    "committee_complete_decision_pending",
    "owner_decision_pending",
    "outcome_tracking",
}
PRIORITY_STANCES = {"core", "hold", "accumulate"}
APPROVED_PLAN_STATUSES = {"approved", "active", "live"}
PROPOSED_PLAN_STATUSES = {"proposed", "draft", "pending_review"}

TIER_META = {
    1: {
        "id": "tier_1",
        "label": "Active holdings and imminent decisions",
        "research_depth": "stock_specific_current",
        "committee_auto_start_allowed": True,
        "screening_only": False,
    },
    2: {
        "id": "tier_2",
        "label": "Priority watchlist",
        "research_depth": "routed_screening_with_promotion_gates",
        "committee_auto_start_allowed": False,
        "screening_only": True,
    },
    3: {
        "id": "tier_3",
        "label": "Broad universe",
        "research_depth": "screening_only",
        "committee_auto_start_allowed": False,
        "screening_only": True,
    },
}

TIER_ONE_CODES = {
    "active_paper_position",
    "active_committee_workflow",
    "explicit_committee_trigger",
    "current_human_decision",
    "expired_human_decision_review_due",
    "approved_target_weight",
}
TIER_TWO_CODES = {
    "registry_watchlist",
    "curated_valuation_followup",
    "priority_stance",
    "proposed_target_weight",
}

TIER_ONE_PROMOTION_GATES = [
    {
        "code": "positive_canonical_position",
        "requirement": "Ticker has a positive position in a canonical paper account state.",
    },
    {
        "code": "imminent_decision_workflow",
        "requirement": "An explicit committee trigger or active committee workbench requires a near-term decision.",
    },
    {
        "code": "human_capital_authority",
        "requirement": "A current or expired human decision requires ownership, renewal, or exit review.",
    },
    {
        "code": "approved_capital_plan",
        "requirement": "A human-approved target-weight plan includes the ticker with a positive weight.",
    },
]
TIER_TWO_PROMOTION_GATES = [
    {
        "code": "curated_priority",
        "requirement": "Ticker is explicitly placed on the registry watchlist or curated valuation follow-up list.",
    },
    {
        "code": "priority_stance",
        "requirement": "Human-maintained classification stance is core, hold, or accumulate.",
    },
    {
        "code": "proposed_capital_plan",
        "requirement": "A proposed target-weight plan includes the ticker with a positive weight.",
    },
]


def _read_json(path: Path) -> tuple[dict[str, Any], str | None]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, "missing"
    except (OSError, json.JSONDecodeError) as exc:
        return {}, f"{type(exc).__name__}: {exc}"
    if not isinstance(value, dict):
        return {}, "top-level JSON value is not an object"
    return value, None


def _number(value: Any) -> float | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _positive_position(row: dict[str, Any]) -> bool:
    """Recognize an explicit long position without inferring from a label."""
    for field in ("shares", "quantity", "qty", "notional_usd", "weight_pct"):
        value = _number(row.get(field))
        if value is not None and value > 0:
            return True
    return False


def _positive_weight(row: dict[str, Any]) -> bool:
    for field in ("weight_pct", "weight", "target_weight_pct"):
        value = _number(row.get(field))
        if value is not None and value > 0:
            return True
    return False


def _reason(code: str, source: str, detail: str, strength: str) -> dict[str, str]:
    return {"code": code, "source": source, "detail": detail, "strength": strength}


def _add_reason(reasons: dict[str, list[dict[str, str]]], ticker: str,
                reason: dict[str, str], universe: set[str],
                unmatched: list[dict[str, str]]) -> None:
    ticker = str(ticker or "").strip().upper()
    if not ticker:
        return
    if ticker not in universe:
        unmatched.append({
            "ticker": ticker,
            "source": reason["source"],
            "reason_code": reason["code"],
        })
        return
    reasons[ticker].append(reason)


def _source_health(path: str, status: str, records: int = 0,
                   detail: str | None = None, required: bool = False) -> dict[str, Any]:
    row: dict[str, Any] = {
        "path": path,
        "status": status,
        "records": records,
        "required": required,
    }
    if detail:
        row["detail"] = detail
    return row


def _expiry_state(human: dict[str, Any], as_of: str) -> str:
    expiry = str(human.get("expires_at") or human.get("review_by") or "")[:10]
    if expiry and expiry < as_of:
        return "expired"
    return "current"


def _assignment(ticker: str, tier: int, assignment_reasons: list[dict[str, str]]) -> dict[str, Any]:
    meta = TIER_META[tier]
    if tier == 1:
        promotion_gates: list[dict[str, str]] = []
        demotion = [
            "No positive canonical position remains.",
            "No explicit or active committee workflow remains.",
            "No current/expired human decision or approved capital plan requires review.",
            "Then re-evaluate Tier 2 priority signals; otherwise demote to Tier 3.",
        ]
    elif tier == 2:
        promotion_gates = TIER_ONE_PROMOTION_GATES
        demotion = [
            "Remove the ticker from every explicit watchlist and curated follow-up list.",
            "Remove it from proposed target-weight plans and any priority stance.",
            "Confirm no Tier 1 gate is present; then demote to Tier 3.",
        ]
    else:
        promotion_gates = [*TIER_TWO_PROMOTION_GATES, *TIER_ONE_PROMOTION_GATES]
        demotion = ["Tier 3 is the fail-closed default; archival/removal requires a separate universe decision."]

    return {
        "ticker": ticker,
        "tier": tier,
        "tier_id": meta["id"],
        "label": meta["label"],
        "research_depth": meta["research_depth"],
        "actionability_cap": "human_decision_only",
        "assignment_reasons": assignment_reasons,
        "promotion_gates": promotion_gates,
        "demotion_conditions": demotion,
        "workflow_policy": {
            "screening_only": meta["screening_only"],
            "committee_auto_start_allowed": meta["committee_auto_start_allowed"],
            "automated_models_can_authorize_capital": False,
            "capital_authority_required": "human_decision",
        },
    }


def build_manifest(root: Path = ROOT, as_of: str | None = None) -> dict[str, Any]:
    """Return a deterministic tier manifest from explicit local authority inputs."""
    root = Path(root)
    as_of = (as_of or date.today().isoformat())[:10]
    registry_path = root / "_system" / "portfolio" / "registry.json"
    registry, registry_error = _read_json(registry_path)
    if registry_error:
        raise ValueError(f"cannot build tier universe: _system/portfolio/registry.json {registry_error}")
    holdings = registry.get("holdings") or {}
    watchlist = registry.get("watchlist") or {}
    if not isinstance(holdings, dict) or not isinstance(watchlist, dict):
        raise ValueError("cannot build tier universe: registry holdings/watchlist must be objects")
    entries = {**watchlist, **holdings}
    universe = set(str(ticker).upper() for ticker in entries)
    reasons: dict[str, list[dict[str, str]]] = {ticker: [] for ticker in universe}
    source_health = [
        _source_health("_system/portfolio/registry.json", "loaded", len(universe), required=True)
    ]
    source_errors: list[str] = []
    unmatched: list[dict[str, str]] = []

    policy, policy_error = _read_json(root / POLICY_PATH)
    if policy_error:
        raise ValueError(f"cannot build tier universe: {POLICY_PATH} {policy_error}")
    if policy.get("schema_version") != "1.0" or not isinstance(policy.get("overrides"), dict):
        raise ValueError(f"cannot build tier universe: {POLICY_PATH} has an invalid schema")
    source_health.append(_source_health(POLICY_PATH, "loaded", len(policy["overrides"]), required=True))

    # Registry bucket membership is a priority signal only for the explicit
    # watchlist.  The misleadingly named holdings bucket is the full research
    # universe and is never interpreted as a position.
    for ticker in sorted(watchlist):
        _add_reason(
            reasons,
            ticker,
            _reason("registry_watchlist", "_system/portfolio/registry.json#watchlist",
                    "Explicit registry watchlist membership.", "tier_2"),
            universe,
            unmatched,
        )

    # Canonical active-position evidence.
    for relative in PAPER_POSITION_PATHS:
        payload, error = _read_json(root / relative)
        if error:
            source_errors.append(f"{relative}: {error}")
            source_health.append(_source_health(relative, "invalid", detail=error, required=True))
            continue
        active = 0
        for row in payload.get("positions") or []:
            if not isinstance(row, dict) or not _positive_position(row):
                continue
            active += 1
            account = str(payload.get("account_id") or Path(relative).stem)
            _add_reason(
                reasons,
                row.get("ticker"),
                _reason("active_paper_position", relative,
                        f"Positive canonical paper position in account {account}.", "tier_1"),
                universe,
                unmatched,
            )
        source_health.append(_source_health(relative, "loaded", active, required=True))

    # Explicitly approved plans are Tier 1; machine-proposed plans remain only
    # a Tier 2 research-priority signal.
    for relative in TARGET_WEIGHT_PATHS:
        payload, error = _read_json(root / relative)
        if error:
            source_health.append(_source_health(relative, "unavailable", detail=error))
            continue
        status = str(payload.get("status") or "").lower()
        records = 0
        for row in payload.get("weights") or []:
            if not isinstance(row, dict) or not _positive_weight(row):
                continue
            records += 1
            if status in APPROVED_PLAN_STATUSES:
                code, strength = "approved_target_weight", "tier_1"
            elif status in PROPOSED_PLAN_STATUSES:
                code, strength = "proposed_target_weight", "tier_2"
            else:
                continue
            _add_reason(
                reasons,
                row.get("ticker"),
                _reason(code, relative, f"Positive target weight in a {status or 'status-missing'} plan.", strength),
                universe,
                unmatched,
            )
        source_health.append(_source_health(relative, "loaded", records))

    followup_path = "_system/reference/valuation_followups.json"
    followups, followup_error = _read_json(root / followup_path)
    if followup_error:
        source_health.append(_source_health(followup_path, "unavailable", detail=followup_error))
    else:
        ticker_cfg = followups.get("tickers") or {}
        for ticker in sorted(ticker_cfg):
            _add_reason(
                reasons,
                ticker,
                _reason("curated_valuation_followup", f"{followup_path}#tickers",
                        "Ticker is in the curated valuation follow-up cohort.", "tier_2"),
                universe,
                unmatched,
            )
        source_health.append(_source_health(followup_path, "loaded", len(ticker_cfg)))

    classification_path = "_system/portfolio/classification.json"
    classifications, classification_error = _read_json(root / classification_path)
    if classification_error:
        classifications = {}
        source_health.append(_source_health(classification_path, "unavailable", detail=classification_error))
    else:
        source_health.append(_source_health(classification_path, "loaded", len(classifications)))

    priority_stance_count = 0
    overrides = policy.get("overrides") or {}
    normalized_overrides = {str(ticker).upper(): value for ticker, value in overrides.items()}
    invalid_overrides: list[str] = []
    for raw_ticker, override in sorted(overrides.items()):
        ticker = str(raw_ticker).upper()
        if ticker not in universe:
            invalid_overrides.append(f"{ticker}: ticker is outside the registry universe")
            continue
        if not isinstance(override, dict) or override.get("tier") not in {1, 2, 3}:
            invalid_overrides.append(f"{ticker}: tier must be 1, 2, or 3")
            continue
        if not str(override.get("reason") or "").strip():
            invalid_overrides.append(f"{ticker}: reason is required")
            continue
        review_by = str(override.get("review_by") or "")[:10]
        detail = str(override["reason"]).strip()
        if review_by:
            detail += f" Review by {review_by}."
        reasons[ticker].append(_reason("owner_tier_override", POLICY_PATH, detail, "owner_override"))
    if invalid_overrides:
        source_errors.extend(f"{POLICY_PATH}: {error}" for error in invalid_overrides)

    for ticker in sorted(universe):
        entry = entries.get(ticker) or entries.get(ticker.lower()) or {}
        inline = (entry.get("classification") or {}) if isinstance(entry, dict) else {}
        direct = classifications.get(ticker) or {}
        stance = str(direct.get("stance") or inline.get("stance") or "").lower()
        if stance in PRIORITY_STANCES:
            priority_stance_count += 1
            reasons[ticker].append(
                _reason("priority_stance", classification_path,
                        f"Classification stance is {stance}.", "tier_2")
            )

    workbench_records = 0
    active_workbenches = 0
    explicit_triggers = 0
    human_decisions = 0
    malformed_research_inputs: list[str] = []
    for ticker in sorted(universe):
        research = root / ticker / "research"
        workbench_path = research / "valuation_workbench.json"
        if workbench_path.exists():
            workbench, error = _read_json(workbench_path)
            if error:
                malformed_research_inputs.append(f"{ticker}/research/valuation_workbench.json: {error}")
            else:
                workbench_records += 1
                committee_status = str(((workbench.get("committee") or {}).get("status")) or "").lower()
                if committee_status in ACTIVE_COMMITTEE_STATES:
                    active_workbenches += 1
                    reasons[ticker].append(
                        _reason("active_committee_workflow",
                                f"{ticker}/research/valuation_workbench.json#committee",
                                f"Committee workflow status is {committee_status}.", "tier_1")
                    )

        trigger_path = research / "committee_trigger.json"
        if trigger_path.exists():
            trigger, error = _read_json(trigger_path)
            if error:
                malformed_research_inputs.append(f"{ticker}/research/committee_trigger.json: {error}")
            elif str(trigger.get("status") or "").lower() == "open":
                explicit_triggers += 1
                detail = str(trigger.get("reason") or "Explicit material decision trigger is open.")
                reasons[ticker].append(
                    _reason("explicit_committee_trigger", f"{ticker}/research/committee_trigger.json",
                            detail, "tier_1")
                )

        human_path = research / "human_decision.json"
        if human_path.exists():
            human, error = _read_json(human_path)
            if error:
                malformed_research_inputs.append(f"{ticker}/research/human_decision.json: {error}")
            elif str(human.get("status") or "").lower() in {"decided", "approved", "complete", "expired"}:
                human_decisions += 1
                expiry = _expiry_state(human, as_of)
                code = "expired_human_decision_review_due" if expiry == "expired" else "current_human_decision"
                reasons[ticker].append(
                    _reason(code, f"{ticker}/research/human_decision.json",
                            "Human decision is expired and requires review." if expiry == "expired"
                            else "Current human capital decision exists.", "tier_1")
                )

    source_health.extend([
        _source_health("*/research/valuation_workbench.json", "loaded", workbench_records,
                       f"{active_workbenches} active committee workflows"),
        _source_health("*/research/committee_trigger.json", "loaded", explicit_triggers),
        _source_health("*/research/human_decision.json", "loaded", human_decisions),
    ])
    if malformed_research_inputs:
        source_errors.extend(malformed_research_inputs)
        source_health.append(_source_health(
            "per-ticker research authority inputs",
            "degraded",
            len(malformed_research_inputs),
            "; ".join(malformed_research_inputs[:20]),
        ))

    assignments: dict[str, dict[str, Any]] = {}
    reason_counts: Counter[str] = Counter()
    for ticker in sorted(universe):
        rows = sorted(
            reasons[ticker],
            key=lambda row: (row["code"], row["source"], row["detail"]),
        )
        codes = {row["code"] for row in rows}
        override_value = normalized_overrides.get(ticker)
        override = override_value if isinstance(override_value, dict) else None
        valid_override = (
            override is not None
            and override.get("tier") in {1, 2, 3}
            and bool(str(override.get("reason") or "").strip())
        )
        if valid_override:
            tier = int(override["tier"])
        elif codes & TIER_ONE_CODES:
            tier = 1
        elif codes & TIER_TWO_CODES:
            tier = 2
        else:
            tier = 3
            rows = [_reason(
                "broad_universe_default",
                "valuation_universe_tiers_policy",
                "No explicit Tier 1 or Tier 2 promotion gate is present.",
                "tier_3",
            )]
        reason_counts.update(row["code"] for row in rows)
        assignments[ticker] = _assignment(ticker, tier, rows)

    counts = Counter(row["tier_id"] for row in assignments.values())
    unmatched = sorted(unmatched, key=lambda row: (row["ticker"], row["source"], row["reason_code"]))
    validation_errors = validate_assignments(assignments, universe)
    validation_status = (
        "valid" if not validation_errors and not source_errors and not malformed_research_inputs
        else "degraded"
    )
    active_position_tickers = sum(
        1 for row in assignments.values()
        if any(reason["code"] == "active_paper_position" for reason in row["assignment_reasons"])
    )
    return {
        "schema_version": "1.0",
        "as_of": as_of,
        "policy": {
            "id": "valuation_universe_tiers_v1",
            "purpose": "Allocate scarce valuation effort without converting automated screening into capital authority.",
            "definitions": {str(tier): TIER_META[tier] for tier in (1, 2, 3)},
            "source_precedence": [
                "positive canonical paper positions and human/committee authority inputs",
                "explicit watchlists, curated follow-ups, stances, and proposed plans",
                "fail-closed broad-universe default",
            ],
            "promotion_gates": {
                "to_tier_1": TIER_ONE_PROMOTION_GATES,
                "to_tier_2": TIER_TWO_PROMOTION_GATES,
            },
            "owner_override_source": POLICY_PATH,
            "committee_eligible_model_levels": policy.get("committee_eligible_model_levels") or [],
            "invariants": [
                "registry.holdings is the research universe and is never active-position evidence",
                "valuation grade, price, implied return, and automated model output are never tier-promotion signals",
                "Tier 2 and Tier 3 cannot auto-start an investment committee",
                "no automated model can authorize capital in any tier; human_decision is always required",
            ],
        },
        "source_health": source_health,
        "source_errors": sorted(source_errors),
        "unmatched_source_records": unmatched,
        "validation": {
            "status": validation_status,
            "errors": validation_errors,
        },
        "summary": {
            "universe_count": len(universe),
            "assignment_count": len(assignments),
            "tier_counts": {tier_id: counts.get(tier_id, 0) for tier_id in ("tier_1", "tier_2", "tier_3")},
            "reason_counts": dict(sorted(reason_counts.items())),
            "active_position_tickers": active_position_tickers,
            "active_committee_workflows": active_workbenches,
            "priority_stances": priority_stance_count,
            "unmatched_source_record_count": len(unmatched),
        },
        "assignments": assignments,
    }


def validate_assignments(assignments: dict[str, dict[str, Any]], universe: set[str]) -> list[str]:
    errors: list[str] = []
    assigned = set(assignments)
    if assigned != universe:
        missing = sorted(universe - assigned)
        extra = sorted(assigned - universe)
        if missing:
            errors.append("missing assignments: " + ", ".join(missing[:20]))
        if extra:
            errors.append("assignments outside universe: " + ", ".join(extra[:20]))
    for ticker, row in sorted(assignments.items()):
        tier = row.get("tier")
        if tier not in {1, 2, 3}:
            errors.append(f"{ticker}: invalid tier {tier!r}")
        if not row.get("assignment_reasons"):
            errors.append(f"{ticker}: assignment reasons are empty")
        policy = row.get("workflow_policy") or {}
        if policy.get("automated_models_can_authorize_capital") is not False:
            errors.append(f"{ticker}: automated capital authority is not explicitly false")
        if tier in {2, 3} and policy.get("committee_auto_start_allowed") is not False:
            errors.append(f"{ticker}: non-Tier-1 committee auto-start is not blocked")
    return errors


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    assignments = manifest.get("assignments") or {}
    errors = []
    if manifest.get("schema_version") != "1.0":
        errors.append("schema_version must be 1.0")
    if not isinstance(assignments, dict):
        return [*errors, "assignments must be an object"]
    errors.extend(validate_assignments(assignments, set(assignments)))
    counts = Counter(row.get("tier_id") for row in assignments.values())
    expected = (manifest.get("summary") or {}).get("tier_counts") or {}
    for tier_id in ("tier_1", "tier_2", "tier_3"):
        if expected.get(tier_id) != counts.get(tier_id, 0):
            errors.append(f"summary count mismatch for {tier_id}")
    if (manifest.get("summary") or {}).get("assignment_count") != len(assignments):
        errors.append("summary assignment_count mismatch")
    return errors


def write_manifest(manifest: dict[str, Any], output: Path = OUTPUT) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--check", action="store_true", help="Verify the committed artifact exactly matches current inputs.")
    parser.add_argument("--strict-sources", action="store_true", help="Fail when a required source is missing or invalid.")
    args = parser.parse_args(argv)
    output = args.output or (ROOT / "_system" / "data" / "valuation_universe_tiers.json")
    try:
        manifest = build_manifest(ROOT, args.date)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    errors = validate_manifest(manifest)
    if errors:
        print("tier manifest validation failed: " + "; ".join(errors), file=sys.stderr)
        return 1
    if args.strict_sources and manifest.get("source_errors"):
        print("tier source validation failed: " + "; ".join(manifest["source_errors"]), file=sys.stderr)
        return 1
    expected = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    if args.check:
        try:
            current = output.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"tier manifest missing or unreadable: {exc}", file=sys.stderr)
            return 1
        if current != expected:
            print(f"tier manifest is stale: regenerate {output}", file=sys.stderr)
            return 1
    else:
        write_manifest(manifest, output)
    summary = manifest["summary"]
    print(json.dumps({"status": "valid", "as_of": manifest["as_of"], **summary["tier_counts"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
