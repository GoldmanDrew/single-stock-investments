#!/usr/bin/env python3
"""Build the complete Tier 1 committee/research execution queue.

This is an operating projection only. It exposes prompt/output paths and
invalid legacy artifacts, but never reads peer vote content, generates a vote,
changes committee state, or grants capital authority.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from build_tier1_decision_readiness import build as build_readiness

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_REL = Path("_system/data/committee_execution_queue.json")


def _read(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _task_id(output: str) -> str:
    if output == "pre_mortem.json":
        return "pre_mortem"
    if output == "research_response.json":
        return "targeted-research"
    if output == "chair_synthesis.json":
        return "chair-synthesis"
    if output.startswith("round_1/"):
        return "round1-" + Path(output).stem
    if output.startswith("round_2/"):
        return "round2-" + Path(output).stem
    return "deterministic-" + Path(output).stem.replace("_", "-")


def _prompt_for(output: str) -> str | None:
    if output.startswith(("round_1/", "round_2/")):
        return output.removesuffix(".json") + ".prompt.md"
    if output in {"pre_mortem.json", "research_response.json", "chair_synthesis.json"}:
        return output.removesuffix(".json") + ".prompt.md"
    return None


def build(as_of: str | None = None, root: Path = ROOT) -> dict:
    readiness = build_readiness(as_of, root)
    rows = []
    for item in readiness.get("items") or []:
        ticker = str(item.get("ticker") or "").upper()
        workbench = _read(root / ticker / "research" / "valuation_workbench.json")
        committee = workbench.get("committee") or {}
        packet_date = str(committee.get("as_of") or "")[:10]
        manifest = _read(
            root / ticker / "research" / "committee_work" / packet_date / "manifest.json"
        ) if packet_date else {}
        state = str(item.get("readiness_state") or "")
        if state in {"research_blocked", "model_deepening_required", "freshness_refresh_required",
                     "falsifier_design_required"}:
            action = "research_closure"
            review_tasks = []
        elif state == "committee_ready":
            action = "committee_start"
            review_tasks = []
        elif state == "owner_decision_ready":
            action = "owner_decision"
            review_tasks = []
        elif state == "owner_approved":
            action = "monitor"
            review_tasks = []
        else:
            action = "independent_review"
            review_tasks = []
            for output in committee.get("next_outputs") or []:
                prompt = _prompt_for(output)
                if prompt is None:
                    continue
                task_id = _task_id(output)
                base = f"{ticker}/research/committee_work/{packet_date}"
                review_tasks.append({
                    "task_id": task_id,
                    "task_key": f"IC-{ticker}-{packet_date}-{task_id}",
                    "prompt_path": f"{base}/{prompt}",
                    "output_path": f"{base}/{output}",
                    "evidence_hash": manifest.get("packet_hash"),
                    "isolation_rule": "No peer vote content may be read before this output lands.",
                })
        rows.append({
            "ticker": ticker,
            "readiness_state": state,
            "action": action,
            "packet_date": packet_date or None,
            "packet_hash": manifest.get("packet_hash"),
            "current_phase": committee.get("current_phase"),
            "progress": committee.get("analysis_progress") or {"completed": 0, "required": 0},
            "invalid_outputs": committee.get("invalid_outputs") or [],
            "review_tasks": review_tasks,
            "next_action": item.get("next_action"),
            "capital_authority": "human_decision_only",
        })
    for index, row in enumerate(rows, start=1):
        row["queue_position"] = index
    actions = Counter(row["action"] for row in rows)
    return {
        "schema_version": "1.0",
        "as_of": readiness.get("as_of"),
        "capital_authority": "human_decision_only",
        "peer_vote_visibility": "isolated_until_landed",
        "summary": {
            "tier_1_count": len(rows),
            "review_task_count": sum(len(row["review_tasks"]) for row in rows),
            "invalid_output_count": sum(len(row["invalid_outputs"]) for row in rows),
            "action_counts": dict(sorted(actions.items())),
        },
        "items": rows,
    }


def render_markdown(payload: dict) -> str:
    lines = [
        f"### Tier 1 execution queue: {len(payload.get('items') or [])}",
        "",
        "| # | Ticker | Action | Phase | Valid outputs | Next isolated tasks |",
        "| ---: | --- | --- | --- | ---: | --- |",
    ]
    for row in (payload.get("items") or [])[:20]:
        progress = row.get("progress") or {}
        tasks = ", ".join(task["task_id"] for task in row.get("review_tasks") or []) or "blocked"
        lines.append(
            f"| {row['queue_position']} | {row['ticker']} | {row['action']} | "
            f"{row.get('current_phase') or '—'} | {progress.get('completed', 0)}/"
            f"{progress.get('required', 0)} | {tasks} |"
        )
    lines.extend([
        "",
        "Only hash-bound isolated tasks are listed. Votes and owner decisions are never generated by this compiler.",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args()
    payload = build(args.date, args.root)
    if args.markdown:
        print(render_markdown(payload), end="")
        return 0
    target = args.out or args.root / OUTPUT_REL
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
