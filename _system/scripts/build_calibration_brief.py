#!/usr/bin/env python3
"""Build the only agent-facing calibration brief from verified outcome stores."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_REL = Path("_system/research/calibration_brief.json")


def read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def digest(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def build(root: Path = ROOT, out: Path | None = None) -> dict:
    fals_path = root / "_system/research/falsifier_calibration.json"
    committee_path = root / "_system/research/committee_calibration.json"
    falsifier = read(fals_path)
    committee = read(committee_path)
    minimum = max(int(falsifier.get("minimum_outcomes") or 20), 20)
    routes: dict[str, dict] = {}
    for key, bucket in sorted((falsifier.get("buckets") or {}).items()):
        if not isinstance(bucket, dict):
            continue
        zone = str(bucket.get("power_zone") or "unclassified")
        scored = int(bucket.get("hit") or 0) + int(bucket.get("miss") or 0)
        routes.setdefault(zone, {"falsifier_methods": {}, "committee_personas": {}})
        routes[zone]["falsifier_methods"][str(bucket.get("method_id") or key)] = {
            "scored_outcomes": scored,
            "hit": int(bucket.get("hit") or 0),
            "miss": int(bucket.get("miss") or 0),
            "unresolvable": int(bucket.get("unresolvable") or 0),
            "hit_rate": bucket.get("hit_rate"),
            "hit_rate_wilson_95": bucket.get("hit_rate_wilson_95"),
            "probabilistic_outcomes": int(bucket.get("probabilistic_outcomes") or 0),
            "brier_score": bucket.get("brier_score"),
            "learning_status": "eligible_for_review" if scored >= minimum else "insufficient_outcomes",
        }
    for key, bucket in sorted((committee.get("persona_power_zones") or {}).items()):
        if not isinstance(bucket, dict):
            continue
        zone = str(bucket.get("power_zone") or "unclassified")
        n = int(bucket.get("completed_outcomes") or 0)
        routes.setdefault(zone, {"falsifier_methods": {}, "committee_personas": {}})
        routes[zone]["committee_personas"][str(bucket.get("persona") or key)] = {
            "completed_outcomes": n,
            "expected_range_hit_rate_pct": bucket.get("expected_range_hit_rate_pct"),
            "learning_status": "eligible_for_review" if n >= minimum else "insufficient_outcomes",
        }
    payload = {
        "schema_version": "1.0",
        "authority": "verified_outcome_calibration_only",
        "source_hashes": {
            "falsifier_calibration": digest(fals_path),
            "committee_calibration": digest(committee_path),
        },
        "minimum_same-route_outcomes": minimum,
        "routes": routes,
        "global_status": (
            "eligible_for_review" if any(
                item.get("learning_status") == "eligible_for_review"
                for route in routes.values()
                for group in route.values() for item in group.values())
            else "insufficient_outcomes"),
        "agent_rule": (
            "Read only the active route. If learning_status is insufficient_outcomes, "
            "state that calibration cannot yet change the analysis. If eligible, use the "
            "observed error pattern as a named challenge, never as an automatic weight, "
            "formula change, decision, or sizing rule."),
    }
    target = out or root / OUT_REL
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    payload = build(args.root, args.out)
    print(json.dumps({"global_status": payload["global_status"],
                      "routes": len(payload["routes"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
