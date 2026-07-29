#!/usr/bin/env python3
"""Run bounded deterministic collection for the evidence recovery queue."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from onboard_ticker import lookup_cik
from portfolio_registry import ROOT, load_registry, save_registry

QUEUE = ROOT / "_system" / "data" / "evidence_recovery_queue.json"
DONE_STATUSES = {"evidence_ready", "closed", "complete", "resolved"}
TERMINAL_STATUSES = {"unavailable", "manual_only"}


def read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def evidence_refs(ticker: str) -> list[str]:
    base = ROOT / ticker
    refs = []
    for pattern in ("investor-documents/DOWNLOAD_MANIFEST.json", "investor-documents/sec-edgar/*", "research/evidence/*.json"):
        refs.extend(path.relative_to(ROOT).as_posix() for path in base.glob(pattern) if path.is_file())
    return sorted(set(refs))


def retry_delay_hours(attempts: int) -> int:
    """Bounded exponential retry delay; attempts is the post-attempt count."""
    return min(24 * 7, 2 ** max(0, attempts - 1))


def terminal_error(task: dict, collection_error: str | None) -> str:
    """Return durable context when a task exhausts its automated retries."""
    return (
        str(collection_error or "").strip()
        or str(task.get("last_error") or "").strip()
        or "Automated collection exhausted retry budget without satisfying acceptance test."
    )


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()
    aggregate = read(QUEUE)
    now_dt = datetime.now(timezone.utc)
    eligible = []
    for row in aggregate.get("items") or []:
        if int(row.get("pending_count") or 0) <= 0:
            continue
        next_attempt = _parse_time(row.get("next_attempt_at"))
        if next_attempt and next_attempt > now_dt:
            continue
        eligible.append(row)
    eligible.sort(key=lambda row: (
        not bool(row.get("triggered")),
        -int(row.get("critical_count") or 0),
        int(row.get("min_attempts") or 0),
        str(row.get("ticker") or ""),
    ))
    selected = eligible[: max(args.limit, 0)]
    now = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    for item in selected:
        ticker = item["ticker"]
        path = ROOT / item["task_ref"]
        packet = read(path) or item.get("task_packet") or {}
        before = evidence_refs(ticker)
        registry = load_registry()
        holding = (registry.get("holdings") or {}).get(ticker) or {}
        if str(holding.get("market") or "US") == "US" and not ((holding.get("download") or {}).get("cik")):
            cik = lookup_cik(ticker)
            if cik:
                holding.setdefault("download", {})["cik"] = cik
                save_registry(registry)
                subprocess.run([sys.executable, "_system/scripts/sync_portfolio_from_registry.py"], cwd=ROOT, check=False, timeout=120)
        error_message = None
        try:
            result = subprocess.run(
                [sys.executable, "_system/scripts/automate_valuation_readiness.py", "--tickers", ticker,
                 "--date", now[:10], "--collect", "--full-rerun"],
                cwd=ROOT, check=False, timeout=900, text=True, capture_output=True,
            )
            if result.returncode:
                error_message = (result.stderr or result.stdout or f"exit {result.returncode}")[-1000:]
        except subprocess.TimeoutExpired as exc:
            error_message = f"collection timed out after {exc.timeout} seconds"
        after = evidence_refs(ticker)
        packet = read(path) or packet
        if error_message is None and after == before:
            error_message = "Automated collection completed, but no new primary evidence satisfied the acceptance test."
        for task in packet.get("tasks") or []:
            status = str(task.get("status") or "").lower()
            if status in DONE_STATUSES or status in TERMINAL_STATUSES:
                continue
            attempts = int(task.get("attempts") or 0) + 1
            max_attempts = int(task.get("max_attempts") or 5)
            task["attempts"] = attempts
            task["last_attempt_at"] = now
            task["last_error"] = error_message
            if attempts >= max_attempts:
                task["status"] = "unavailable"
                task["next_attempt_at"] = None
                task["last_error"] = terminal_error(task, error_message)
            else:
                task["status"] = "retry_scheduled"
                task["next_attempt_at"] = (
                    now_dt + timedelta(hours=retry_delay_hours(attempts))
                ).strftime("%Y-%m-%dT%H:%M:%SZ")
        packet["ready_count"] = sum(
            str(task.get("status") or "").lower() in DONE_STATUSES
            for task in packet.get("tasks") or []
        )
        packet["terminal_count"] = sum(
            str(task.get("status") or "").lower() in TERMINAL_STATUSES
            for task in packet.get("tasks") or []
        )
        packet["updated_at"] = now
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")
        item["task_packet"] = packet
        refresh = {
            "schema_version": "1.0", "ticker": ticker, "updated_at": now,
            "status": (
                "evidence_ready"
                if packet.get("ready_count") == packet.get("task_count")
                else "unavailable"
                if packet.get("terminal_count")
                else "retry_scheduled"
            ),
            "new_artifact_count": len(set(after) - set(before)), "evidence_refs": after,
            "last_error": error_message or next(
                (
                    str(task.get("last_error") or "").strip()
                    for task in packet.get("tasks") or []
                    if str(task.get("status") or "").lower() in TERMINAL_STATUSES
                    and str(task.get("last_error") or "").strip()
                ),
                None,
            ),
        }
        refresh_path = ROOT / ticker / "research" / "evidence_refresh.json"
        refresh_path.write_text(json.dumps(refresh, indent=2) + "\n", encoding="utf-8")
        item["ready_count"] = packet.get("ready_count")
        item["terminal_count"] = packet.get("terminal_count")
        item["pending_count"] = max(
            0,
            int(packet.get("task_count") or 0)
            - int(packet.get("ready_count") or 0)
            - int(packet.get("terminal_count") or 0),
        )
        next_attempts = sorted(
            str(task.get("next_attempt_at"))
            for task in packet.get("tasks") or []
            if task.get("next_attempt_at")
        )
        item["next_attempt_at"] = next_attempts[0] if next_attempts else None
    aggregate["generated_at"] = now
    QUEUE.write_text(json.dumps(aggregate, indent=2) + "\n", encoding="utf-8")
    print(f"evidence collection attempted for {len(selected)} tickers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
