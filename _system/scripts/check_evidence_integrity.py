#!/usr/bin/env python3
"""Find evidence that is blocked without anything saying so.

`check_evidence_completeness.py` answers "is this one ticker's contract
internally valid." It cannot answer the question that actually bit us on WHK:
*which tickers are stuck in a way no status field admits to?* WHK's contract
read `decision_grade` with zero blockers while its compiler stage read
`evidence_blocked`, its eight evidence tasks sat at `attempts: 0`, and
`build_contract_backfill_queue.py` skipped it precisely *because* it was
decision_grade -- so the automation that would have collected the missing
facts could never see it. Every individual artifact looked fine. The defect
was only visible in the disagreement *between* artifacts.

This sweep encodes those disagreements as checks over the whole universe.
Each check is a pairwise contradiction between two files that are supposed to
agree, or a queue that claims to be working and is not:

  V1  contract says decision_grade, compiler stage says evidence_blocked
  V2  decision_grade with no sourced fact node anywhere in its proofs
  V3  evidence tasks pending_collection with attempts: 0 on a stale queue
  V4  routed primary method not satisfied by the executed component proofs
  V5  component results present but no totals -> dashboard renders null
  V6  decision_grade with no typed falsifier -> monitoring cannot fire
  V7  decision_grade whose routed method inputs are absent from the ledger

V3 additionally reports the *trap*, which is the finding that motivated this
sweep. Three separate remediation paths all gate on the same field:

  build_contract_backfill_queue.py  skips status == "decision_grade"
  build_evidence_recovery_queue.py  skips status == "decision_grade" under
                                    its default `all-blocked` scope
  run_security_decision_pipeline    only opens committees on decision_grade

so a contract that reaches `decision_grade` prematurely is simultaneously
treated as finished by every path that could have finished it. 124 tickers
were in that state when this was written, and none of them appeared in either
queue. `decision_grade` is load-bearing as a completion signal and nothing
was checking that it had been earned.

Two checks deliberately measure something narrower than they first appear:

  * V2 counts proof nodes of `kind: fact` carrying a source, NOT the
    contract's `input_classification.facts`. That array is empty for 187 of
    192 decision-grade contracts because `_input_kind` classifies a whole
    component as "judgment" when *any* of its inputs is a judgment -- which
    every real model has. Counting it would report 187 defects that are not
    defects. The honest count is 1.
  * V4 mirrors `compile_existing_approved_proofs`'s own `route_supported`
    rule exactly rather than approximating it, because that function's return
    value is the consequence being detected: when the route is unsatisfied it
    returns None, the issuer's authored proofs are discarded, and the ticker
    is silently recompiled from the normalized ledger on every run.

V6 overlaps graph invariant E1 by design and at a different grain: E1 counts
decision-grade *components* lacking a typed falsifier, V6 counts *tickers*
with none at all. E1 is the coverage ratchet; V6 is the triage list.

Severity is deliberately `report` with a ratchet, not `hard`. 124 tickers were
trapped when this was written; failing CI on that would freeze the factory,
which the graph README already identifies as the worse failure. Instead the
baseline in `_system/data/evidence_integrity_baseline.json` records today's
counts and the check fails only when a count *rises* above its baseline. The
numbers can then only go down.

Usage:
  python _system/scripts/check_evidence_integrity.py                # report
  python _system/scripts/check_evidence_integrity.py --json         # machine
  python _system/scripts/check_evidence_integrity.py --ticker WHK   # triage one
  python _system/scripts/check_evidence_integrity.py --worklist 25  # what to fix
  python _system/scripts/check_evidence_integrity.py --update-baseline
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):          # Windows cp1252 console
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "_system" / "data" / "evidence_integrity_baseline.json"
REPORT = ROOT / "_system" / "data" / "evidence_integrity.json"
BACKFILL = ROOT / "_system" / "data" / "contract_backfill_queue.json"
REGISTRY = ROOT / "_system" / "portfolio" / "registry.json"

STALE_QUEUE_DAYS = 3        # a queue untouched this long is not "in progress"

CHECKS = {
    "V1": "contract decision_grade while the compiler stage is evidence_blocked",
    "V2": "decision_grade with no sourced fact node anywhere in its proofs",
    "V3": "evidence tasks never attempted on a stale queue",
    "V4": "routed method not satisfied by the proofs (authored proofs discarded)",
    "V5": "component results present but no totals (dashboard renders null)",
    "V6": "decision_grade with no typed falsifier (monitoring cannot fire)",
    "V7": "decision_grade whose routed method inputs are absent from the ledger",
}

# Mirrors METHOD_INPUT_SCHEMAS in automate_valuation_readiness.py. Kept as a
# literal rather than imported so this sweep stays runnable if that module is
# mid-edit; drift between the two is itself worth noticing.
REQUIRED_INPUTS = {
    "component_owner_cash_and_unit_nav": [
        "economic_ownership_map", "normalized_owner_cash", "asset_quantity",
        "unit_value", "senior_claims", "tax_and_realization_costs",
        "shares_outstanding"],
    "net_asset_value": [
        "asset_quantity", "unit_value", "ownership_claim", "senior_claims",
        "tax_and_realization_costs", "shares_outstanding"],
    "owner_earnings_reinvestment_dcf": [
        "normalized_owner_earnings_m", "shares_outstanding", "cash_m", "debt_m"],
    "owner_cash_or_dividend_discount": [
        "sustainable_distribution", "sustainable_growth", "required_return",
        "maintenance_funding", "dilution_per_share", "shares_outstanding"],
    "midcycle_capacity_value": [
        "capacity", "utilization", "revenue_per_unit", "normalized_margin",
        "maintenance_capital_m", "tax_rate", "debt_m", "shares_outstanding"],
    "capital_structure_and_excess_return": [
        "tangible_equity_m", "normalized_roe", "cost_of_equity",
        "excess_return_duration", "stress_losses_m", "senior_claims_m",
        "shares_outstanding"],
}

def route_satisfied(routed: str, proof_methods: set[str]) -> bool:
    """Exact mirror of ``compile_existing_approved_proofs``'s route_supported.

    Kept identical on purpose: when this returns False that function returns
    None, the issuer's authored proofs are dropped, and valuation.json is
    recompiled from the normalized ledger. Approximating the rule here would
    report tickers that are fine and miss tickers that are being silently
    overwritten every run.
    """
    if routed == "component_owner_cash_and_unit_nav":
        return bool(
            proof_methods & {"owner_cash_or_dividend_discount",
                             "owner_earnings_reinvestment_dcf"}
            and "net_asset_value" in proof_methods)
    return routed in proof_methods


def sourced_fact_nodes(contract: dict) -> int:
    """Proof inputs of kind 'fact' that carry a source, across all components.

    This is the real "is there evidence underneath" signal -- see the module
    docstring on why input_classification.facts is not.
    """
    total = 0
    for comp in contract.get("economic_ownership_map") or []:
        proof = comp.get("calculation_proof") or {}
        trace = (proof.get("traces") or {}).get("base") or []
        total += sum(1 for n in trace
                     if n.get("kind") == "fact" and n.get("source"))
    return total


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {} if default is None else default


def age_days(stamp, today: date) -> int | None:
    """Tolerant age in days. None when the stamp cannot be read at all --
    an unparseable stamp must never be treated as fresh."""
    if not stamp:
        return None
    text = str(stamp).strip().replace("Z", "+00:00")
    for parse in (lambda s: datetime.fromisoformat(s).date(),
                  lambda s: date.fromisoformat(s[:10])):
        try:
            return (today - parse(text)).days
        except (TypeError, ValueError):
            continue
    return None


def holdings() -> set[str]:
    reg = read_json(REGISTRY)
    out: set[str] = set()
    for key in ("holdings", "watchlist"):
        block = reg.get(key)
        if isinstance(block, dict):
            out |= set(block)
    return out


def backfill_members() -> set[str]:
    wave = read_json(BACKFILL)
    members = set(wave.get("tickers") or [])
    for row in wave.get("almost_there") or []:
        if isinstance(row, dict) and row.get("ticker"):
            members.add(row["ticker"])
        elif isinstance(row, str):
            members.add(row)
    return members


def scan_ticker(ticker: str, research: Path, wave: set[str], today: date) -> dict:
    """Every finding for one ticker. Returns {check_id: detail-string}."""
    contract = read_json(research / "valuation_contract.json")
    if not contract:
        return {}
    found: dict[str, str] = {}
    status = contract.get("status")
    grade = status == "decision_grade"

    state = read_json(research / "valuation_automation_state.json")
    stages = state.get("stages") or {}
    compile_stage = stages.get("model_compile") or {}
    queue = read_json(research / "evidence_task_queue.json")
    route = read_json(research / "valuation_route.json")
    ledger = read_json(research / "valuation_fact_ledger.json")
    valuation = read_json(research / "valuation.json")

    if grade and compile_stage.get("status") == "evidence_blocked":
        errs = compile_stage.get("input_errors") or []
        detail = f"{len(errs)} missing method inputs" if errs else "no input_errors recorded"
        found["V1"] = f"compiler stage evidence_blocked ({detail})"

    if grade and sourced_fact_nodes(contract) == 0:
        found["V2"] = (f"{len(contract.get('economic_ownership_map') or [])} components,"
                       " 0 proof inputs of kind 'fact' carrying a source")

    tasks = queue.get("tasks") or []
    untouched = [t for t in tasks if t.get("status") == "pending_collection"
                 and not t.get("attempts")]
    queue_age = age_days(queue.get("updated_at"), today)
    if untouched and (queue_age is None or queue_age >= STALE_QUEUE_DAYS):
        age_text = "unparseable stamp" if queue_age is None else f"{queue_age}d old"
        trap = grade and ticker not in wave
        found["V3"] = (f"{len(untouched)}/{len(tasks)} tasks never attempted,"
                       f" queue {age_text}, contract={status}"
                       + (" [TRAPPED: decision_grade and not in backfill wave]" if trap else ""))

    identity = read_json(research / "security_identity.json")
    routed = str(identity.get("primary_method")
                 or (route.get("primary_methods") or [None])[0] or "")
    proof_methods = {c.get("method") for c in (contract.get("economic_ownership_map") or [])}
    proof_methods.discard(None)
    if routed and proof_methods and not route_satisfied(routed, proof_methods):
        found["V4"] = (f"route={routed} proofs={sorted(proof_methods)}"
                       " -- authored proofs are discarded and recompiled each run")

    results = valuation.get("component_valuation_results") or {}
    if results.get("additive_components") and results.get("total_equity_value_per_share") is None:
        found["V5"] = (f"{len(results['additive_components'])} components,"
                       f" no total_equity_value_per_share (status={results.get('status')})")

    if grade:
        specs = read_json(research / "falsifier_specs.json").get("specs") or []
        typed = [s for s in specs
                 if not s.get("untestable") and s.get("threshold") is not None]
        if not typed:
            found["V6"] = f"{len(specs)} specs, 0 typed"

    # Restricted to decision_grade on purpose. An evidence_blocked ticker with
    # missing method inputs is the backlog working as designed -- 641 of them.
    # A decision_grade one is a contract asserting completeness over a ledger
    # that cannot support its own routed method.
    if grade:
        locked = {r.get("field_id") for r in (ledger.get("facts") or [])
                  if r.get("locked")}
        needed = REQUIRED_INPUTS.get(routed)
        if needed:
            missing = [f for f in needed if f not in locked]
            if missing:
                shown = ",".join(missing[:3]) + ("..." if len(missing) > 3 else "")
                found["V7"] = (f"{routed} missing {len(missing)}/{len(needed)}"
                               f" locked inputs ({shown})")

    return found


def sweep(root: Path, today: date, only: str | None = None) -> dict:
    wave = backfill_members()
    held = holdings()
    findings: dict[str, list[dict]] = {cid: [] for cid in CHECKS}
    per_ticker: dict[str, dict] = {}
    totals = {"tickers_scanned": 0, "contracts": 0,
              "decision_grade": 0, "evidence_blocked": 0, "trapped": 0}

    for folder in sorted(root.iterdir()):
        if only and folder.name != only:
            continue
        research = folder / "research"
        if not folder.is_dir() or not research.is_dir():
            continue
        ticker = folder.name
        totals["tickers_scanned"] += 1
        contract = read_json(research / "valuation_contract.json")
        if not contract:
            continue
        totals["contracts"] += 1
        status = contract.get("status")
        if status == "decision_grade":
            totals["decision_grade"] += 1
        elif status == "evidence_blocked":
            totals["evidence_blocked"] += 1

        found = scan_ticker(ticker, research, wave, today)
        if not found:
            continue
        per_ticker[ticker] = found
        for check_id, detail in found.items():
            findings[check_id].append({
                "ticker": ticker, "detail": detail, "held": ticker in held})
        if "TRAPPED" in found.get("V3", ""):
            totals["trapped"] += 1

    return {"generated_at": datetime.now(timezone.utc).isoformat(),
            "as_of": today.isoformat(), "totals": totals,
            "counts": {cid: len(rows) for cid, rows in findings.items()},
            "findings": findings, "per_ticker": per_ticker}


def worklist(report: dict, limit: int) -> list[dict]:
    """Most-broken first, holdings ahead of the rest.

    A ticker carrying several contradictions at once is not several small
    problems; it is one ticker whose evidence chain is broken end to end, and
    it is the cheapest place to recover real coverage.
    """
    held = {row["ticker"] for rows in report["findings"].values()
            for row in rows if row["held"]}
    scored = []
    for ticker, found in report["per_ticker"].items():
        trapped = "TRAPPED" in found.get("V3", "")
        scored.append({
            "ticker": ticker,
            "checks": sorted(found),
            "count": len(found),
            "trapped": trapped,
            "held": ticker in held,
            "score": len(found) + (3 if trapped else 0) + (5 if ticker in held else 0),
        })
    scored.sort(key=lambda r: (-r["score"], r["ticker"]))
    return scored[:limit]


def render(report: dict, work: list[dict]) -> str:
    t = report["totals"]
    lines = [
        "# Evidence integrity sweep",
        "",
        f"as_of {report['as_of']} -- {t['contracts']} contracts"
        f" ({t['decision_grade']} decision_grade, {t['evidence_blocked']} evidence_blocked)",
        "",
        "| check | count | what it means |",
        "|---|---:|---|",
    ]
    for cid, title in CHECKS.items():
        lines.append(f"| {cid} | {report['counts'][cid]} | {title} |")
    lines += ["", f"**Trapped: {t['trapped']}** -- decision_grade, evidence queue never"
                  " attempted, and absent from the backfill wave. These cannot heal"
                  " themselves and nothing else reports them.", ""]
    if work:
        lines += ["## Worklist (most-broken first, holdings weighted)", "",
                  "| ticker | checks | held | trapped |", "|---|---|---|---|"]
        for row in work:
            lines.append(f"| {row['ticker']} | {' '.join(row['checks'])} |"
                         f" {'yes' if row['held'] else ''} |"
                         f" {'yes' if row['trapped'] else ''} |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ticker", help="Triage a single ticker")
    ap.add_argument("--json", action="store_true", help="Machine-readable output")
    ap.add_argument("--worklist", type=int, default=20, help="Rows in the worklist")
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--update-baseline", action="store_true",
                    help="Record current counts as the ratchet baseline")
    ap.add_argument("--no-write", action="store_true", help="Do not write the report file")
    args = ap.parse_args(argv)

    today = date.fromisoformat(args.date)
    report = sweep(ROOT, today, only=args.ticker)
    work = worklist(report, args.worklist)

    if args.ticker:
        found = report["per_ticker"].get(args.ticker)
        if args.json:
            print(json.dumps({"ticker": args.ticker, "findings": found or {}}, indent=2))
        elif not found:
            print(f"OK {args.ticker}: no evidence-integrity findings")
        else:
            print(f"FINDINGS {args.ticker}:")
            for cid, detail in sorted(found.items()):
                print(f"  {cid} {CHECKS[cid]}\n      {detail}")
        return 0

    if not args.no_write:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if args.update_baseline:
        payload = {"as_of": report["as_of"], "counts": report["counts"],
                   "trapped": report["totals"]["trapped"],
                   "note": "Ratchet baseline. Counts may only fall; a rise fails CI."}
        BASELINE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"baseline written: {BASELINE.relative_to(ROOT)}")

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render(report, work))

    baseline = read_json(BASELINE)
    if not baseline:
        print("\nNOTE: no baseline recorded yet; run --update-baseline to arm the ratchet.")
        return 0
    regressions = [
        f"{cid}: {report['counts'][cid]} > baseline {baseline['counts'].get(cid, 0)}"
        for cid in CHECKS
        if report["counts"][cid] > baseline.get("counts", {}).get(cid, 0)
    ]
    if regressions:
        print("\nREGRESSION against baseline "
              f"{baseline.get('as_of')}:\n  - " + "\n  - ".join(regressions))
        return 1
    print(f"\nratchet OK against baseline {baseline.get('as_of')}"
          " (no check rose above its recorded count)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
