#!/usr/bin/env python3
"""Plan bounded healer dispatches and persist repeated repository failures."""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import graph_invariants

ROOT = Path(__file__).resolve().parents[2]
STATE_REL = Path("_system/data/repository_health_supervisor.json")


def operational_failures(root: Path, now: datetime | None = None) -> list[str]:
    """Evaluate the receipt and feed invariants this supervisor can heal."""
    now = now or datetime.now(timezone.utc)
    config = json.loads((root / "_system/graph/graph_sources.json").read_text(encoding="utf-8"))
    hard = []
    for lane in config.get("lanes") or []:
        name = str(lane.get("name"))
        receipt_path = root / "_system/data/lane_receipts" / f"{name}.json"
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            stamp = datetime.fromisoformat(str(receipt["last_success_at"]).replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            age_h = (now - stamp).total_seconds() / 3600
            if age_h > float(lane.get("freshness_hours") or 96):
                hard.append(f"P3|{name}: successful workflow receipt is stale")
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            hard.append(f"P3|{name}: successful workflow receipt is missing or invalid")
    p6 = graph_invariants.inv_p6(None, root, now.date())
    hard.extend(f"P6|{item}" for item in p6.violations)
    return hard


def _head(root: Path) -> str | None:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                            text=True, capture_output=True, check=False)
    return result.stdout.strip() or None


def plan(root: Path = ROOT) -> dict:
    prior_path = root / STATE_REL
    prior = json.loads(prior_path.read_text(encoding="utf-8")) if prior_path.exists() else {}
    previous = prior.get("failures") or {}
    hard = operational_failures(root)
    failures = {key: {"consecutive_runs": int((previous.get(key) or {}).get("consecutive_runs") or 0) + 1,
                      "last_seen_at": datetime.now(timezone.utc).isoformat()}
                for key in hard}
    p6 = "\n".join(key for key in hard if key.startswith("P6|"))
    dispatches = []
    if any(name in p6 for name in ("criticality_summary", "technical_summary", "vol_metrics", "spx_surface")):
        dispatches.append({"event_type": "heal-technicals"})
    if "warrant_monitor" in p6:
        dispatches.append({"event_type": "heal-warrants"})
    if "market_risk_components_committed" in p6:
        dispatches.append({"event_type": "heal-market-risk"})
    if "podcast_catalog" in p6:
        dispatches.append({"workflow": "podcast-refresh.yml", "fields": {"backfill": "false", "whisper_batch": "0"}})
    payload = {
        "schema_version": "1.0", "checked_at": datetime.now(timezone.utc).isoformat(),
        "git_head": _head(root), "hard_violation_count": len(hard),
        "failures": failures, "dispatches": dispatches,
        "escalate": [key for key, row in failures.items() if row["consecutive_runs"] >= 3],
    }
    prior_path.parent.mkdir(parents=True, exist_ok=True)
    prior_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    print(json.dumps(plan(args.root), separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
