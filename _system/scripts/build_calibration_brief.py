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


def challenge_for(bucket: dict) -> str:
    skill = bucket.get("brier_skill_vs_climatology")
    base_rate = bucket.get("base_rate")
    if isinstance(skill, (int, float)) and skill < 0:
        return ("Challenge the route probability with the observed base rate and show why "
                "company-specific evidence deserves to depart from it.")
    if isinstance(base_rate, (int, float)) and base_rate >= .6:
        return ("Stress the low-case bridge against the route's elevated falsifier base rate "
                "before accepting quality or reinvestment persistence.")
    return ("Rebuild the metric bridge from primary evidence and explicitly test the frozen "
            "threshold before carrying the component into valuation.")


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
        scored = int(bucket.get("eligible_scored_outcomes") or 0)
        status = str(bucket.get("learning_status") or "plumbing_only")
        routes.setdefault(zone, {"falsifier_methods": {}, "committee_personas": {}})
        routes[zone]["falsifier_methods"][str(bucket.get("method_id") or key)] = {
            "scored_outcomes": int(bucket.get("scored_outcomes") or 0),
            "diagnostic_scored_outcomes": int(bucket.get("diagnostic_scored_outcomes") or 0),
            "eligible_scored_outcomes": scored,
            "effective_outcomes": int(bucket.get("effective_outcomes") or 0),
            "hit": int(bucket.get("hit") or 0),
            "miss": int(bucket.get("miss") or 0),
            "unresolvable": int(bucket.get("unresolvable") or 0),
            "hit_rate": bucket.get("hit_rate"),
            "hit_rate_wilson_95": bucket.get("hit_rate_wilson_95"),
            "probabilistic_outcomes": int(bucket.get("probabilistic_outcomes") or 0),
            "brier_score": bucket.get("brier_score"),
            "brier_skill_vs_climatology": bucket.get("brier_skill_vs_climatology"),
            "log_loss": bucket.get("log_loss"),
            "base_rate": bucket.get("base_rate"),
            "distinct_tickers": int(bucket.get("distinct_tickers") or 0),
            "distinct_industries": int(bucket.get("distinct_industries") or 0),
            "measurement_periods": int(bucket.get("measurement_periods") or 0),
            "resolution_yield": bucket.get("resolution_yield"),
            "maximum_cluster_share": bucket.get("maximum_cluster_share"),
            "learning_status": status,
            "named_challenge": (challenge_for(bucket)
                                if status == "eligible_for_prompt_challenge" else None),
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
        "schema_version": "2.0",
        "authority": "verified_outcome_calibration_only",
        "source_hashes": {
            "falsifier_calibration": digest(fals_path),
            "committee_calibration": digest(committee_path),
        },
        "minimum_same-route_outcomes": minimum,
        "routes": routes,
        "global_status": (
            "eligible_for_prompt_challenge" if any(
                item.get("learning_status") == "eligible_for_prompt_challenge"
                for route in routes.values()
                for item in route.get("falsifier_methods", {}).values())
            else "insufficient_outcomes"),
        "agent_rule": (
            "Read only the active route. If learning_status is insufficient_outcomes, "
            "state that calibration cannot yet change the analysis. If eligible, use the "
            "observed error pattern as a named challenge, never as an automatic weight, "
            "formula change, decision, or sizing rule."),
        "consumption_contract": {
            "required_fields": ["calibration_release_hash", "route", "challenges_addressed", "calibration_response"],
            "responses": ["addressed", "not_applicable", "disputed"],
            "automatic_weight_changes": False,
        },
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    candidate_digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    payload["candidate_digest"] = candidate_digest
    payload["release_hash"] = (candidate_digest if payload["global_status"] ==
                               "eligible_for_prompt_challenge" else None)
    target = out or root / OUT_REL
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if payload["global_status"] == "eligible_for_prompt_challenge":
        release = root / "_system/research/calibration_releases" / f"{payload['release_hash']}.json"
        release.parent.mkdir(parents=True, exist_ok=True)
        if not release.exists():
            release.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
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
