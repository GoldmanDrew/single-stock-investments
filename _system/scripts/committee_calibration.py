#!/usr/bin/env python3
"""Score committee methods only from explicitly recorded, dividend-aware outcomes."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def current_revisions(rows: list[dict]) -> list[dict]:
    current = {}
    for row in rows:
        identity = (row.get("outcome_class") or "owner_decision",
                    row.get("forecast_id") or row.get("ticker"),
                    row.get("decision_date"), row.get("horizon_months") or row.get("measurement_date"))
        if identity not in current or int(row.get("revision") or 1) >= int(current[identity].get("revision") or 1):
            current[identity] = row
    return list(current.values())


def summarize(rows: list[dict]) -> dict:
    rows = current_revisions(rows)
    valid = [r for r in rows if r.get("return_status") == "complete" and r.get("total_return_pct") is not None]
    by_persona: dict[str, list[dict]] = defaultdict(list)
    by_persona_power_zone: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in valid:
        for vote in row.get("votes", []):
            enriched = {**vote, "total_return_pct": float(row["total_return_pct"]), "power_zone": row.get("power_zone") or "unclassified"}
            by_persona[vote["persona"]].append(enriched)
            by_persona_power_zone[(vote["persona"], enriched["power_zone"])].append(enriched)
    methods = {}
    for persona, votes in sorted(by_persona.items()):
        actionable = [v for v in votes if v.get("vote") in ("approve", "reject")]
        correct = [v for v in actionable if (v["vote"] == "approve") == (v["total_return_pct"] > 0)]
        ranged = [v for v in votes if isinstance(v.get("expected_return_range_pct"), list) and len(v["expected_return_range_pct"]) == 2]
        range_hits = [v for v in ranged if float(v["expected_return_range_pct"][0]) <= v["total_return_pct"] <= float(v["expected_return_range_pct"][1])]
        midpoint_errors = [abs(sum(map(float, v["expected_return_range_pct"])) / 2 - v["total_return_pct"]) for v in ranged]
        methods[persona] = {
            "completed_outcomes": len(votes),
            "actionable_votes": len(actionable),
            "abstention_or_watch_rate_pct": round(100 * (len(votes) - len(actionable)) / len(votes), 1),
            "directional_accuracy_pct": round(100 * len(correct) / len(actionable), 1) if actionable else None,
            "expected_range_observations": len(ranged),
            "expected_range_hit_rate_pct": round(100 * len(range_hits) / len(ranged), 1) if ranged else None,
            "mean_absolute_midpoint_error_pct": round(sum(midpoint_errors) / len(midpoint_errors), 2) if midpoint_errors else None,
            "mean_total_return_pct": round(sum(v["total_return_pct"] for v in votes) / len(votes), 2),
            "calibration_use": "descriptive" if len(votes) < 20 else "eligible_for_review",
        }
    power_zone_methods = {}
    for (persona, power_zone), votes in sorted(by_persona_power_zone.items()):
        ranged = [v for v in votes if isinstance(v.get("expected_return_range_pct"), list) and len(v["expected_return_range_pct"]) == 2]
        hits = [v for v in ranged if float(v["expected_return_range_pct"][0]) <= v["total_return_pct"] <= float(v["expected_return_range_pct"][1])]
        power_zone_methods[f"{persona}:{power_zone}"] = {
            "persona": persona,
            "power_zone": power_zone,
            "completed_outcomes": len(votes),
            "expected_range_observations": len(ranged),
            "expected_range_hit_rate_pct": round(100 * len(hits) / len(ranged), 1) if ranged else None,
            "calibration_use": "descriptive" if len(votes) < 20 else "eligible_for_review",
        }
    return {
        "status": "ready" if valid else "insufficient_outcomes",
        "completed_outcomes": len(valid),
        "excluded_rows": len(rows) - len(valid),
        "committee_forecast_outcomes": sum(r.get("outcome_class") == "committee_forecast" for r in valid),
        "owner_decision_outcomes": sum(r.get("outcome_class") != "committee_forecast" for r in valid),
        "methods": methods,
        "persona_power_zones": power_zone_methods,
        "warning": "Calibration is descriptive until each persona has at least 20 completed, dividend-aware outcomes in the same power zone; weights never change automatically.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, default=ROOT / "_system" / "research" / "committee_outcomes.jsonl")
    parser.add_argument("--out", type=Path, default=ROOT / "_system" / "research" / "committee_calibration.json")
    parser.add_argument("--forecast-ledger", type=Path,
                        default=ROOT / "_system" / "research" / "committee_forecast_outcomes.jsonl")
    args = parser.parse_args()
    result = summarize(load_jsonl(args.ledger) + load_jsonl(args.forecast_ledger))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
