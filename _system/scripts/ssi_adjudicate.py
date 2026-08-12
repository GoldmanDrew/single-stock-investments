#!/usr/bin/env python3
"""Adjudicate SSI gold cases and severity>=4 alerts.

The blueprint bars in `_eval/README.md` are only measurable once a human has
labelled cases. Hand-editing JSONL is the reason none of them ever were, so this
turns adjudication into a listing and a one-line command.

Two queues:

  gold   — Phase 3 verification failures awaiting generator_error / skeptic_error
           / ambiguous. Infrastructure failures (source drift, pack mismatch) are
           auto-labelled by verify_ssi_claims and never appear here.
  alerts — emitted severity>=4 claims awaiting real / noise, feeding top-alert
           precision. Sampled across issuers so one noisy ticker cannot dominate
           the sample and flatter the metric.

Nothing here decides a verdict. It prints the claim, its locator and its source
so a human can check the filing, and appends exactly what is typed.

Usage:
  python _system/scripts/ssi_adjudicate.py gold                    # list pending
  python _system/scripts/ssi_adjudicate.py gold --limit 5
  python _system/scripts/ssi_adjudicate.py gold --set <claim_id> generator_error --note "..."
  python _system/scripts/ssi_adjudicate.py alerts --limit 10       # sample alerts
  python _system/scripts/ssi_adjudicate.py alerts --set <claim_id> real --issuer TBBK
  python _system/scripts/ssi_adjudicate.py status                  # queue sizes
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
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

EVAL = ROOT / "_eval"
GOLD = EVAL / "ssi_skeptic_gold.jsonl"
ALERTS = EVAL / "ssi_alert_adjudications.jsonl"
QUEUE = EVAL / "ssi_adjudication_queue.json"

GOLD_VERDICTS = ("generator_error", "skeptic_error", "ambiguous")
ALERT_VERDICTS = ("real", "noise")


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _latest_gold() -> list[dict]:
    from calibrate_ssi import latest_adjudications
    return latest_adjudications(_read(GOLD))


def _pending_gold() -> list[dict]:
    return [r for r in _latest_gold() if r.get("adjudication") in (None, "pending")]


def _adjudicated_alert_ids() -> set[str]:
    return {str(r.get("claim_id")) for r in _read(ALERTS) if r.get("claim_id")}


def _emitted_alerts() -> list[dict]:
    """Severity>=4 verified claims across the repo, round-robin by issuer.

    Sampling issuer-by-issuer matters: taking the first N from a flat list would
    hand back one ticker's alerts, and a precision number measured on a single
    issuer says nothing about the detector.
    """
    by_issuer: dict[str, list[dict]] = {}
    for path in sorted(ROOT.glob("*/research/evidence/ssi_verified_claims_*.json")):
        issuer = path.parents[2].name
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for claim in doc.get("verified_claims") or []:
            if (claim.get("severity") or 0) >= 4:
                by_issuer.setdefault(issuer, []).append({
                    "issuer": issuer,
                    "as_of": doc.get("as_of"),
                    "claim_id": claim.get("claim_id"),
                    "severity": claim.get("severity"),
                    "taxonomy": claim.get("taxonomy"),
                    "statement": claim.get("statement"),
                    "evidence_ref": claim.get("evidence_ref"),
                })
    out: list[dict] = []
    queues = [iter(v) for v in by_issuer.values()]
    while queues:
        still = []
        for q in queues:
            item = next(q, None)
            if item is not None:
                out.append(item)
                still.append(q)
        queues = still
    return out


def _show(row: dict, index: int) -> None:
    ref = row.get("evidence_ref") or {}
    if isinstance(ref, str):
        try:
            ref = json.loads(ref.replace("'", '"'))
        except (json.JSONDecodeError, ValueError):
            ref = {"raw": ref}
    print(f"\n[{index}] {row.get('issuer')}  {row.get('claim_id')}"
          f"  sev={row.get('severity', '-')}  {row.get('taxonomy') or ''}")
    print(f"    {str(row.get('statement') or '')[:200]}")
    if row.get("failure_reason"):
        print(f"    failure_reason: {row['failure_reason']}")
    src = ref.get("source_path") or ref.get("ref") or ""
    line = ref.get("line") or ref.get("locator") or ""
    if src:
        print(f"    source: {src}{(':' + str(line)) if line else ''}")


def cmd_gold(args) -> int:
    if args.set:
        claim_id, verdict = args.set
        if verdict not in GOLD_VERDICTS:
            print(f"verdict must be one of {', '.join(GOLD_VERDICTS)}")
            return 2
        match = next((r for r in _pending_gold() if str(r.get("claim_id")) == claim_id), None)
        if match is None:
            print(f"no pending gold case with claim_id {claim_id}")
            return 1
        row = dict(match)
        row["adjudication"] = verdict
        row["adjudicated_at"] = args.date
        if args.note:
            row["note"] = args.note
        row["supersedes"] = {"claim_id": claim_id, "as_of": match.get("as_of"),
                             "prior_adjudication": match.get("adjudication")}
        with GOLD.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=True) + "\n")
        print(f"recorded {claim_id} -> {verdict}")
        return 0

    pending = _pending_gold()
    if not pending:
        print("gold queue empty — no cases awaiting adjudication")
        return 0
    print(f"{len(pending)} gold case(s) pending. Verdicts: {', '.join(GOLD_VERDICTS)}")
    print("  generator_error = Phase 2 emitted a bad claim")
    print("  skeptic_error   = Phase 3 killed a good claim")
    for i, row in enumerate(pending[: args.limit], start=1):
        _show(row, i)
    print(f"\nSet one with:\n  python {Path(__file__).name} gold --set <claim_id> generator_error --note \"...\"")
    return 0


def cmd_alerts(args) -> int:
    if args.set:
        claim_id, verdict = args.set
        if verdict not in ALERT_VERDICTS:
            print(f"verdict must be one of {', '.join(ALERT_VERDICTS)}")
            return 2
        known = {str(a.get("claim_id")): a for a in _emitted_alerts()}
        found = known.get(claim_id)
        if found is None and not args.issuer:
            print(f"claim_id {claim_id} not found among emitted severity>=4 claims; "
                  "pass --issuer to record it anyway")
            return 1
        ALERTS.parent.mkdir(parents=True, exist_ok=True)
        with ALERTS.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "issuer": args.issuer or (found or {}).get("issuer"),
                "claim_id": claim_id,
                "as_of": (found or {}).get("as_of") or args.date,
                "adjudication": verdict,
                "note": args.note or "",
                "adjudicated_at": args.date,
            }, ensure_ascii=True) + "\n")
        print(f"recorded {claim_id} -> {verdict}")
        return 0

    done = _adjudicated_alert_ids()
    queue = [a for a in _emitted_alerts() if str(a.get("claim_id")) not in done]
    if not queue:
        print("alert queue empty — every emitted severity>=4 claim is adjudicated")
        return 0
    issuers = len({a["issuer"] for a in queue})
    print(f"{len(queue)} unadjudicated severity>=4 alert(s) across {issuers} issuer(s), "
          f"sampled round-robin. Verdicts: {', '.join(ALERT_VERDICTS)}")
    for i, row in enumerate(queue[: args.limit], start=1):
        _show(row, i)
    print(f"\nSet one with:\n  python {Path(__file__).name} alerts --set <claim_id> real --note \"...\"")
    return 0


def cmd_status(args) -> int:
    gold_pending = len(_pending_gold())
    gold_infra = sum(1 for r in _latest_gold() if r.get("adjudication") == "infrastructure")
    gold_done = sum(1 for r in _latest_gold()
                    if r.get("adjudication") in GOLD_VERDICTS)
    alerts_done = len(_adjudicated_alert_ids())
    alerts_open = len([a for a in _emitted_alerts()
                       if str(a.get("claim_id")) not in _adjudicated_alert_ids()])
    events = _read(EVAL / "ssi_sev5_events.jsonl")
    print("SSI adjudication queues")
    print(f"  gold pending        {gold_pending}")
    print(f"  gold adjudicated    {gold_done}")
    print(f"  gold infrastructure {gold_infra}  (auto-labelled, excluded from accuracy)")
    print(f"  alerts adjudicated  {alerts_done}")
    print(f"  alerts open         {alerts_open}")
    print(f"  sev5 events known   {len(events)}")
    print("\nRun calibrate_ssi.py to see what these currently support.")
    return 0


def queue_payload(gold_limit: int = 5, alert_limit: int = 20) -> dict:
    """Bounded, issuer-diverse weekly human-ground-truth work queue."""
    done = _adjudicated_alert_ids()
    alerts = [row for row in _emitted_alerts()
              if str(row.get("claim_id")) not in done][:alert_limit]
    gold = _pending_gold()[:gold_limit]
    return {
        "schema_version": "1.0",
        "generated_on": date.today().isoformat(),
        "service_level_days": 7,
        "gold_pending_total": len(_pending_gold()),
        "alerts_pending_total": len([row for row in _emitted_alerts()
                                     if str(row.get("claim_id")) not in done]),
        "gold_sample": gold,
        "alert_sample": alerts,
        "issuer_count": len({row.get("issuer") for row in alerts}),
        "human_ground_truth_required": True,
        "rule": "Never infer a verdict. A human checks the cited filing and records one with ssi_adjudicate.py.",
    }


def cmd_queue(args) -> int:
    payload = queue_payload(min(args.limit, 5), args.limit)
    if args.write:
        QUEUE.parent.mkdir(parents=True, exist_ok=True)
        QUEUE.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
                         encoding="utf-8")
        print(QUEUE)
    else:
        print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("gold", cmd_gold), ("alerts", cmd_alerts),
                     ("status", cmd_status), ("queue", cmd_queue)):
        p = sub.add_parser(name)
        p.add_argument("--limit", type=int, default=10)
        p.add_argument("--set", nargs=2, metavar=("CLAIM_ID", "VERDICT"))
        p.add_argument("--note", default="")
        p.add_argument("--issuer", default="")
        p.add_argument("--date", default=date.today().isoformat())
        p.add_argument("--write", action="store_true")
        p.set_defaults(fn=fn)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
