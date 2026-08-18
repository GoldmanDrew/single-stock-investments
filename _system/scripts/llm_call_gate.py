#!/usr/bin/env python3
"""Enforce evidence-hash, cooldown, and call budgets for Cursor consumers.

The ledger may live in a restored GitHub Actions cache. It is deliberately
append-only so every approval and suppression remains auditable within a run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = ROOT / "_system" / "config" / "llm_usage_policy.json"
TERMINAL_CALL_STATUSES = {"reserved", "completed"}
BUDGET_STATUSES = {"reserved"}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {} if default is None else default


def read_ledger(path: Path) -> list[dict]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows = []
    for line in lines:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def append_ledger(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")


def stable_evidence_hash(paths: list[Path], explicit: str | None = None) -> str:
    if explicit:
        return explicit.lower()
    rows = []
    for path in sorted({p.resolve() for p in paths}, key=lambda p: p.as_posix()):
        if not path.is_file():
            continue
        try:
            label = path.relative_to(ROOT).as_posix()
        except ValueError:
            label = path.as_posix()
        rows.append({"path": label, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def consumer_policy(policy_doc: dict, consumer: str) -> dict:
    return {**(policy_doc.get("default") or {}), **((policy_doc.get("consumers") or {}).get(consumer) or {})}


def resolve_model(policy_doc: dict, consumer: str, *, reason: str = "", task_id: str = "") -> str:
    """Pick the model per the ladder: cheap default, frontier on escalation keys.

    Frontier lanes are judgment-heavy: brand-new deep dives (reason keys) and
    IC chair synthesis (task_id keys). Everything mechanical stays cheap.
    """
    ladder = policy_doc.get("model_ladder") or {}
    default = ladder.get("default_model") or "composer-2.5"
    frontier = ladder.get("frontier_model") or default
    config = (ladder.get("consumers") or {}).get(consumer) or {}
    if config.get("model"):
        return config["model"]
    if reason and reason in (config.get("frontier_reasons") or []):
        return frontier
    if task_id and task_id in (config.get("frontier_task_ids") or []):
        return frontier
    return default


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def evaluate(
    *,
    consumer: str,
    subject: str,
    reason: str,
    evidence_hash: str,
    policy_doc: dict,
    ledger: list[dict],
    state: dict | None = None,
    at: datetime | None = None,
    force: bool = False,
) -> dict:
    at = at or now_utc()
    config = consumer_policy(policy_doc, consumer)
    subject = subject.upper() if consumer != "ci_autofix" else subject.lower()
    base = {
        "schema_version": "1.0",
        "consumer": consumer,
        "subject": subject,
        "reason": reason,
        "evidence_hash": evidence_hash,
        "evaluated_at": at.isoformat(),
        "approved": False,
        "policy": config,
    }
    allowed = config.get("allowed_reasons")
    allowed_prefixes = config.get("allowed_reason_prefixes") or []
    reason_allowed = (
        (not allowed and not allowed_prefixes)
        or reason in (allowed or [])
        or any(reason.startswith(str(prefix)) for prefix in allowed_prefixes)
    )
    if not reason_allowed and not force:
        return {**base, "decision": "suppressed", "gate_reason": "reason_not_allowed"}
    if not evidence_hash or set(evidence_hash) == {"0"}:
        return {**base, "decision": "suppressed", "gate_reason": "missing_evidence_hash"}
    if (state or {}).get("evidence_hash") == evidence_hash and not force:
        return {**base, "decision": "suppressed", "gate_reason": "evidence_already_processed"}

    # A reservation is a concurrency/budget lock, not a permanent charge when
    # the same run later records a failed startup. Catch-up workflows may retry
    # those calls; completed and still-running reservations remain protected.
    failed = {
        (row.get("run_id"), row.get("subject"), row.get("evidence_hash"))
        for row in ledger
        if row.get("status") == "failed"
    }
    effective_ledger = [
        row for row in ledger
        if not (
            row.get("status") == "reserved"
            and (row.get("run_id"), row.get("subject"), row.get("evidence_hash")) in failed
        )
    ]
    relevant = [row for row in effective_ledger if row.get("consumer") == consumer]
    same = [row for row in relevant if row.get("subject") == subject]
    if config.get("duplicate_evidence_block", True) and not force:
        if any(row.get("evidence_hash") == evidence_hash and row.get("status") in TERMINAL_CALL_STATUSES for row in same):
            return {**base, "decision": "suppressed", "gate_reason": "duplicate_evidence_hash"}

    day_start = at.replace(hour=0, minute=0, second=0, microsecond=0)
    today = [row for row in relevant if (parse_time(row.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc)) >= day_start and row.get("status") in BUDGET_STATUSES]
    if len(today) >= int(config.get("daily_repo_limit") or 999999) and not force:
        return {**base, "decision": "suppressed", "gate_reason": "daily_repo_limit"}
    today_subject = [row for row in today if row.get("subject") == subject]
    if len(today_subject) >= int(config.get("per_subject_daily_limit") or 999999) and not force:
        return {**base, "decision": "suppressed", "gate_reason": "per_subject_daily_limit"}

    cooldown = timedelta(hours=float(config.get("cooldown_hours") or 0))
    # A new primary-evidence fingerprint is a new decision event. Cooldown
    # only guards retries of that same evidence; it must never strand a ticker
    # when a new filing or explicitly authorized packet arrives.
    completed_times = [
        parse_time(row.get("timestamp"))
        for row in same
        if row.get("status") in BUDGET_STATUSES and row.get("evidence_hash") == evidence_hash
    ]
    completed_times = [value for value in completed_times if value]
    if cooldown and completed_times and at - max(completed_times) < cooldown and not force:
        return {**base, "decision": "suppressed", "gate_reason": "subject_cooldown"}
    return {**base, "approved": True, "decision": "approved", "gate_reason": "judgment_call_admitted"}


def write_github_output(result: dict) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with Path(path).open("a", encoding="utf-8") as handle:
        for key in ("approved", "decision", "gate_reason", "evidence_hash"):
            value = result.get(key)
            if isinstance(value, bool):
                value = str(value).lower()
            handle.write(f"{key}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("evaluate", "record", "model"))
    parser.add_argument("--consumer", required=True)
    parser.add_argument("--subject", required=False, default="")
    parser.add_argument("--reason", required=False, default="")
    parser.add_argument("--task-id", default="")
    parser.add_argument("--evidence-hash")
    parser.add_argument("--evidence-path", action="append", default=[])
    parser.add_argument("--state-file", type=Path)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--status", choices=("reserved", "completed", "failed", "suppressed"), default="completed")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--reserve", action="store_true")
    parser.add_argument("--github-output", action="store_true")
    args = parser.parse_args()
    if args.command == "model":
        model = resolve_model(read_json(args.policy), args.consumer, reason=args.reason, task_id=args.task_id)
        output = os.environ.get("GITHUB_OUTPUT")
        if output:
            with Path(output).open("a", encoding="utf-8") as handle:
                handle.write(f"model={model}\n")
        print(model)
        return 0
    if not args.subject or not args.reason or not args.ledger:
        raise SystemExit(f"--subject, --reason, and --ledger are required for '{args.command}'")
    evidence_hash = stable_evidence_hash([Path(p) for p in args.evidence_path], args.evidence_hash)
    if args.command == "record":
        event = {
            "timestamp": now_utc().isoformat(),
            "consumer": args.consumer,
            "subject": args.subject.upper() if args.consumer != "ci_autofix" else args.subject.lower(),
            "reason": args.reason,
            "evidence_hash": evidence_hash,
            "status": args.status,
            "run_id": os.environ.get("GITHUB_RUN_ID"),
            "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        }
        append_ledger(args.ledger, event)
        print(json.dumps(event, sort_keys=True))
        return 0

    policy = read_json(args.policy)
    state = read_json(args.state_file) if args.state_file else {}
    result = evaluate(
        consumer=args.consumer,
        subject=args.subject,
        reason=args.reason,
        evidence_hash=evidence_hash,
        policy_doc=policy,
        ledger=read_ledger(args.ledger),
        state=state,
        force=args.force,
    )
    if args.reserve:
        append_ledger(args.ledger, {
            "timestamp": now_utc().isoformat(),
            "consumer": result["consumer"],
            "subject": result["subject"],
            "reason": result.get("reason") or args.reason,
            "evidence_hash": evidence_hash,
            "status": "reserved" if result["approved"] else "suppressed",
            "gate_reason": result["gate_reason"],
            "run_id": os.environ.get("GITHUB_RUN_ID"),
            "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        })
    if args.github_output:
        write_github_output(result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
