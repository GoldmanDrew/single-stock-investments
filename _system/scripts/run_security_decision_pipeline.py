#!/usr/bin/env python3
"""Portfolio-wide Power Zone valuation and committee-gate orchestrator.

Unlike the deprecated ls-algo sleeve runner, this pipeline uses the canonical
registry universe.  It routes every selected security, writes an explicit
universal contract for every existing valuation, builds the workbench only
after route/contract finalization, derives pricing only from decision-grade
contracts, and initializes a committee only when both readiness and a material
decision trigger are present.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "_system" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from build_power_zone_pricing import build_contract_pricing  # noqa: E402
from build_valuation_workbench import write as write_workbench  # noqa: E402
from falsifier_specs import coverage_summary as falsifier_coverage_summary  # noqa: E402
from investment_committee_pipeline import initialize as initialize_committee  # noqa: E402
from power_zone_router import build_route, registry_entries, write_json  # noqa: E402
from universal_valuation_contract import build_universal_valuation_contract  # noqa: E402

# Stages that mean a committee is still in flight or still owed a human, so no
# new committee may be opened over it. `parked` is the circuit breaker holding
# landed votes for a human decision: re-initializing over it drops the park
# block, resets the stage and refresh counter, and mints a new packet hash,
# which turns every held vote into an answer to a packet that no longer exists -
# exactly the loss the breaker exists to stop. `conditional_escalation` and
# `chair_pending` are set by committee_task_queue once round one has landed.
BUSY_COMMITTEE_STATES = {
    "round_one_open", "independent_review_open", "conditional_escalation", "chair_pending",
    "ready_to_assemble", "parked",
    "committee_complete_decision_pending", "owner_decision_pending", "outcome_tracking",
}
FOLLOWUPS = ROOT / "_system" / "reference" / "valuation_followups.json"
CLOSED_EVIDENCE_STATUSES = {"resolved", "accepted", "not_applicable", "met"}
REVIEW_METADATA_FIELDS = {"cohort_purpose", "cohort_expected_profile", "profile_match"}


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {} if default is None else default


def selected_tickers(scope: str, explicit: list[str] | None = None) -> list[str]:
    if explicit:
        return sorted(set(t.upper() for t in explicit))
    entries = registry_entries()
    if scope == "valued":
        return sorted(t for t in entries if (ROOT / t / "research" / "valuation.json").exists())
    if scope == "priority":
        followups = read_json(ROOT / "_system" / "reference" / "valuation_followups.json")
        followup_names = set((followups.get("tickers") or {})) & set(entries)
        portfolio_names = {
            ticker
            for ticker, holding in entries.items()
            if str(((holding or {}).get("classification") or {}).get("stance") or "").lower()
            in {"core", "hold", "accumulate"}
        }
        return sorted(followup_names | portfolio_names)
    return sorted(entries)


def curated_evidence_blockers(ticker: str) -> list[str]:
    """Return only still-open curated gaps for the security.

    The follow-up ledger is the readiness authority.  Rebuilding a contract
    must not resurrect an accepted gap or silently drop a still-open one.
    """
    followups = read_json(FOLLOWUPS)
    ticker_cfg = ((followups.get("tickers") or {}).get(ticker) or {})
    blockers = []
    for row in ticker_cfg.get("evidence_gaps") or []:
        status = str(row.get("status") or "open").lower()
        if status in CLOSED_EVIDENCE_STATUSES:
            continue
        gap_id = row.get("id") or "curated_evidence_gap"
        question = row.get("question") or row.get("evidence_required") or "Primary evidence remains incomplete."
        blockers.append(f"{gap_id}: {question}")
    return sorted(set(blockers))


def current_contract(ticker: str, valuation: dict, route: dict, reviewed: dict) -> dict:
    """Recompute financial fields while retaining explicit review metadata."""
    contract = build_universal_valuation_contract(valuation, route.get("profile_id"))
    blockers = sorted(set((contract.get("evidence") or {}).get("blockers") or []) | set(curated_evidence_blockers(ticker)))
    contract.setdefault("evidence", {})["blockers"] = blockers
    contract["evidence"]["unresolved_count"] = len(blockers)
    if blockers:
        contract["status"] = "evidence_blocked"
    for field in REVIEW_METADATA_FIELDS:
        if field in reviewed:
            contract[field] = reviewed[field]
    contract["method_route"] = route
    contract["authority"] = "universal_valuation_contract"
    contract["legacy_reference_present"] = bool(
        valuation.get("implied_return") or valuation.get("results_lawrence_legacy")
    )
    # Falsifier coverage mirrors curated_evidence_blockers: the sidecar
    # ({ticker}/research/falsifier_specs.json) is the durable source because
    # this contract is regenerated on every build; only a derived summary is
    # carried forward.  Coverage is NEVER a blocker while graph_sources.json
    # falsifier_enforcement.enforcement_enabled is false (flipping the
    # decision-grade book to evidence_blocked would freeze the factory).
    contract["falsifier_coverage"] = falsifier_coverage_summary(ticker, contract, root=ROOT)
    return contract


def stage_routes(tickers: list[str], as_of: str, dry_run: bool) -> dict:
    statuses: dict[str, int] = {}
    unchanged = 0
    errors = []
    for ticker in tickers:
        try:
            route = build_route(ticker, as_of)
            statuses[route["status"]] = statuses.get(route["status"], 0) + 1
            if not dry_run:
                path = ROOT / ticker / "research" / "valuation_route.json"
                previous = read_json(path)
                if (
                    previous.get("input_hash") == route.get("input_hash")
                    and previous.get("status") == route.get("status")
                    and previous.get("profile_id") == route.get("profile_id")
                    and previous.get("specialist_power_zones") == route.get("specialist_power_zones")
                    and previous.get("committee") == route.get("committee")
                ):
                    unchanged += 1
                else:
                    write_json(path, route)
        except Exception as exc:
            errors.append({"ticker": ticker, "error": f"{type(exc).__name__}: {exc}"})
    return {
        "processed": len(tickers) - len(errors),
        "unchanged": unchanged,
        "statuses": statuses,
        "errors": errors,
    }


def _model_scaffold(ticker: str, route: dict, as_of: str) -> dict:
    return {
        "schema_version": "2.0",
        "ticker": ticker,
        "as_of": as_of,
        "status": "evidence_blocked_model_required",
        "method_route": route,
        "required_component_map": route.get("required_evidence") or [],
        "required_outputs": [
            "complete non-overlapping economic ownership map",
            "primary-source input ledger",
            "approved versioned method card",
            "deterministic low/base/high calculation proof",
            "enterprise-to-equity and per-share reconciliation",
            "reverse expectations, falsifiers, and refresh triggers",
        ],
        "unvalued_component_count": 1,
        "next_action": "Gather the listed primary evidence and compile the first proof-complete component model; never substitute an analyst plug.",
    }


def stage_contracts(tickers: list[str], dry_run: bool, as_of: str | None = None) -> dict:
    written, missing, scaffolded, errors = [], [], [], []
    as_of = (as_of or date.today().isoformat())[:10]
    for ticker in tickers:
        research = ROOT / ticker / "research"
        valuation_path = research / "valuation.json"
        if not valuation_path.exists():
            try:
                route = read_json(research / "valuation_route.json") or build_route(ticker, as_of)
                scaffold = read_json(research / "valuation_model_scaffold.json")
                if ((scaffold.get("method_route") or {}).get("profile_id") != route.get("profile_id")):
                    scaffold = _model_scaffold(ticker, route, as_of)
                contract = build_universal_valuation_contract({"ticker": ticker, "as_of": as_of}, route.get("profile_id"))
                contract["method_route"] = route
                contract["authority"] = "universal_valuation_contract"
                contract["model_scaffold_ref"] = f"{ticker}/research/valuation_model_scaffold.json"
                contract["next_action"] = scaffold["next_action"]
                # Same durability rule as current_contract: summary only,
                # sourced from the sidecar, never a blocker.
                contract["falsifier_coverage"] = falsifier_coverage_summary(ticker, contract, root=ROOT)
                if not dry_run:
                    write_json(research / "valuation_model_scaffold.json", scaffold)
                    write_json(research / "valuation_contract.json", contract)
                scaffolded.append(ticker)
                written.append({"ticker": ticker, "status": contract.get("status")})
            except Exception as exc:
                missing.append(ticker)
                errors.append({"ticker": ticker, "error": f"{type(exc).__name__}: {exc}"})
            continue
        try:
            valuation = read_json(valuation_path)
            route = read_json(research / "valuation_route.json") or build_route(ticker)
            reviewed = read_json(research / "valuation_contract.json")
            contract = current_contract(ticker, valuation, route, reviewed)
            if not dry_run:
                write_json(research / "valuation_contract.json", contract)
            written.append({"ticker": ticker, "status": contract.get("status")})
        except Exception as exc:
            errors.append({"ticker": ticker, "error": f"{type(exc).__name__}: {exc}"})
    return {"written": written, "missing_valuation": missing, "scaffolded": scaffolded, "errors": errors}


def stage_workbenches(tickers: list[str], as_of: str, dry_run: bool) -> dict:
    written, skipped, errors = [], [], []
    for ticker in tickers:
        research = ROOT / ticker / "research"
        if not (research / "valuation.json").exists() and not (research / "valuation_model_scaffold.json").exists():
            if dry_run:
                written.append(ticker)
                continue
            skipped.append(ticker)
            continue
        try:
            if not dry_run:
                write_workbench(ticker, as_of)
            written.append(ticker)
        except Exception as exc:
            errors.append({"ticker": ticker, "error": f"{type(exc).__name__}: {exc}"})
    return {"written": written, "skipped": skipped, "errors": errors}


def workbench_status(ticker: str) -> tuple[str, str]:
    workbench = read_json(ROOT / ticker / "research" / "valuation_workbench.json")
    return (
        str(((workbench.get("decision") or {}).get("status")) or "missing"),
        str(((workbench.get("committee") or {}).get("status")) or "not_started"),
    )


def stage_pricing(tickers: list[str], as_of: str, dry_run: bool) -> dict:
    priced, skipped, errors = [], [], []
    for ticker in tickers:
        decision, _ = workbench_status(ticker)
        if decision != "decision_grade":
            skipped.append(ticker)
            continue
        try:
            if not dry_run:
                build_contract_pricing(ticker, as_of)
            priced.append(ticker)
        except Exception as exc:
            errors.append({"ticker": ticker, "error": f"{type(exc).__name__}: {exc}"})
    return {"priced": priced, "skipped": skipped, "errors": errors}


def decision_triggers(ticker: str, holding: dict) -> list[str]:
    research = ROOT / ticker / "research"
    triggers = []
    stance = str(((holding or {}).get("classification") or {}).get("stance") or "").lower()
    if stance in {"core", "hold", "accumulate"}:
        triggers.append(f"material portfolio stance: {stance}")
    flag = read_json(research / "committee_trigger.json")
    if str(flag.get("status") or "").lower() == "open":
        triggers.append(f"explicit trigger: {flag.get('reason') or 'material thesis/evidence change'}")
    pricing = read_json(research / "pricing_analysis.json")
    price, entry = pricing.get("price"), pricing.get("primary_entry_price_15pct_base")
    try:
        if price is not None and entry is not None and float(price) <= float(entry):
            triggers.append(f"price {price} at or below 15% hurdle entry {entry}")
    except (TypeError, ValueError):
        pass
    human = read_json(research / "human_decision.json")
    if human and str(human.get("status") or "").lower() == "expired":
        triggers.append("human decision expired")
    return triggers


def stage_committees(tickers: list[str], as_of: str, dry_run: bool) -> dict:
    entries = registry_entries()
    initiated, active, blocked, evidence_tasks, resting = [], [], [], [], []
    for ticker in tickers:
        existing_manifest = read_json(ROOT / ticker / "research" / "committee_work" / as_of / "manifest.json")
        # Any manifest at this exact date, whatever stage it reached, means the
        # work dir is taken. initialize() refuses to open a second door into it;
        # reporting it as active keeps that refusal off the blocked list.
        if existing_manifest.get("stage") or existing_manifest.get("packet_hash"):
            active.append({
                "ticker": ticker,
                "stage": existing_manifest.get("stage") or "unknown",
                "work": f"{ticker}/research/committee_work/{as_of}",
            })
            continue
        decision, committee = workbench_status(ticker)
        triggers = decision_triggers(ticker, entries.get(ticker) or {})
        if decision != "decision_grade":
            if triggers:
                evidence_tasks.append({"ticker": ticker, "decision": decision, "triggers": triggers})
            continue
        if not triggers:
            resting.append(ticker)
            continue
        if committee in BUSY_COMMITTEE_STATES:
            blocked.append({"ticker": ticker, "reason": f"committee already {committee}", "triggers": triggers})
            continue
        if dry_run:
            initiated.append({"ticker": ticker, "triggers": triggers, "note": "dry run"})
            continue
        try:
            path = initialize_committee(ticker, as_of)
            initiated.append({"ticker": ticker, "triggers": triggers, "work": path.relative_to(ROOT).as_posix()})
        except Exception as exc:
            blocked.append({"ticker": ticker, "reason": f"{type(exc).__name__}: {exc}", "triggers": triggers})
    return {
        "initiated": initiated,
        "active": active,
        "blocked": blocked,
        "triggered_evidence_tasks": evidence_tasks,
        "decision_grade_resting": resting,
    }


def run_script(*argv: str) -> dict:
    result = subprocess.run(
        [sys.executable, *argv],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip(), file=sys.stderr)
    return {
        "status": "refreshed" if result.returncode == 0 else "failed",
        "returncode": result.returncode,
        "command": " ".join(argv),
        "error_tail": result.stderr[-2000:].strip() or None,
    }


def write_summary(as_of: str, scope: str, tickers: list[str], stages: dict, dry_run: bool, explicit: bool = False) -> Path | None:
    summary = {
        "schema_version": "1.0",
        "as_of": as_of,
        "scope": scope,
        "dry_run": dry_run,
        "ticker_count": len(tickers),
        "stages": stages,
    }
    if dry_run:
        return None
    # Run receipts are pipeline telemetry, not human reviews — they live under
    # _system/data/runs/ so _system/reviews/pending/ holds only items that need
    # a human verdict.
    runs = ROOT / "_system" / "data" / "runs"
    if explicit:
        slug = "-".join(tickers).lower()[:80] or "none"
        path = runs / f"power_zone_security_run_{as_of}_{slug}.json"
    else:
        path = runs / f"power_zone_universe_run_{as_of}.json"
    write_json(path, summary)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=("all", "valued", "priority"), default="all")
    parser.add_argument("--tickers", nargs="*", type=str.upper)
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-dashboard", action="store_true")
    args = parser.parse_args()
    as_of = args.date[:10]
    tickers = selected_tickers(args.scope, args.tickers)
    print(f"universe: scope={args.scope} tickers={len(tickers)}")

    routes = stage_routes(tickers, as_of, args.dry_run)
    print(f"[1/6] routes: {routes['processed']} processed, {len(routes['errors'])} errors")
    power_zones = {"status": "skipped", "returncode": 0, "command": None, "error_tail": None}
    if not args.dry_run and not args.tickers:
        power_zones = run_script("_system/scripts/build_power_zones.py")
    elif args.tickers:
        power_zones["status"] = "targeted_route_only"

    contracts = stage_contracts(tickers, args.dry_run, as_of)
    print(f"[2/6] contracts: {len(contracts['written'])} ready, {len(contracts['scaffolded'])} model scaffolds, {len(contracts['missing_valuation'])} missing, {len(contracts['errors'])} errors")

    contract_tickers = [row["ticker"] for row in contracts["written"]]
    workbenches = stage_workbenches(contract_tickers, as_of, args.dry_run)
    print(f"[3/6] workbenches: {len(workbenches['written'])} built, {len(workbenches['skipped'])} skipped, {len(workbenches['errors'])} errors")

    pricing = stage_pricing(workbenches["written"], as_of, args.dry_run)
    print(f"[4/6] pricing: {len(pricing['priced'])} priced, {len(pricing['errors'])} errors")
    for row in pricing.get("errors") or []:
        print(f"  pricing error {row.get('ticker')}: {row.get('error')}")

    committees = stage_committees(workbenches["written"], as_of, args.dry_run)
    print(f"[5/6] committees: {len(committees['initiated'])} initialized, {len(committees['blocked'])} blocked, {len(committees['triggered_evidence_tasks'])} evidence tasks")

    dashboard = {"status": "skipped", "returncode": 0, "command": None, "error_tail": None}
    if not args.skip_dashboard and not args.dry_run:
        if args.tickers:
            dashboard = run_script("_system/scripts/refresh_valuation_dashboard_rows.py", "--tickers", *tickers)
        else:
            dashboard = run_script("_system/scripts/build_dashboard_data.py")
    print(f"[6/6] dashboard: {dashboard['status']}")

    stages = {
        "routes": routes,
        "power_zones": power_zones,
        "contracts": contracts,
        "workbenches": workbenches,
        "pricing": pricing,
        "committees": committees,
        "dashboard": dashboard,
    }
    summary = write_summary(as_of, args.scope, tickers, stages, args.dry_run, explicit=bool(args.tickers))
    if summary:
        print(f"summary: {summary.relative_to(ROOT).as_posix()}")
    errors = sum(len(stage.get("errors") or []) for stage in (routes, contracts, workbenches, pricing))
    errors += int(power_zones["returncode"] != 0) + int(dashboard["returncode"] != 0)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
