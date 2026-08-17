#!/usr/bin/env python3
"""Plan bounded healer dispatches and persist repeated repository failures."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE_REL = Path("_system/data/repository_health_supervisor.json")


def plan(root: Path = ROOT) -> dict:
    report = json.loads((root / "_system/graph/invariants.json").read_text(encoding="utf-8"))
    prior_path = root / STATE_REL
    prior = json.loads(prior_path.read_text(encoding="utf-8")) if prior_path.exists() else {}
    previous = prior.get("failures") or {}
    hard = []
    for invariant in report.get("invariants") or []:
        if invariant.get("severity") == "hard" and invariant.get("count"):
            hard.extend(f"{invariant['id']}|{item}" for item in invariant.get("violations") or [])
    failures = {key: {"consecutive_runs": int((previous.get(key) or {}).get("consecutive_runs") or 0) + 1,
                      "last_seen_at": datetime.now(timezone.utc).isoformat()}
                for key in hard}
    p6 = "\n".join(key for key in hard if key.startswith("P6|"))
    dispatches = []
    if any(name in p6 for name in ("criticality_summary", "technical_summary", "vol_metrics", "spx_surface")):
        dispatches.append({"workflow": "data-pipeline.yml", "fields": {"mode": "technicals"}})
    if "warrant_monitor" in p6:
        dispatches.append({"workflow": "data-pipeline.yml", "fields": {"mode": "warrant_refresh"}})
    if "market_risk_components_committed" in p6:
        dispatches.append({"workflow": "market-risk-components.yml", "fields": {}})
    if "podcast_catalog" in p6:
        dispatches.append({"workflow": "podcast-refresh.yml", "fields": {"backfill": "false", "whisper_batch": "0"}})
    payload = {
        "schema_version": "1.0", "checked_at": datetime.now(timezone.utc).isoformat(),
        "git_head": report.get("git_head"), "hard_violation_count": len(hard),
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
