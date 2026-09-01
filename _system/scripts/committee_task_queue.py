#!/usr/bin/env python3
"""Materialize deterministic committee stages and return only necessary LLM tasks."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from investment_committee_pipeline import (
    carry_round_one_forward,
    deterministic_committee_support,
    deterministic_proposer,
    escalation_decision,
    load_round,
    validate_chair_binding,
    validate_pre_mortem_binding,
    validate_vote,
    vote_binding,
    vote_set_hash,
    write_json,
)

ROOT = Path(__file__).resolve().parents[2]


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def task(ticker: str, as_of: str, task_id: str, prompt: Path, output: Path, packet_hash: str) -> dict:
    return {
        "ticker": ticker,
        "as_of": as_of,
        "task_id": task_id,
        "task_key": f"IC-{ticker}-{as_of}-{task_id}",
        "prompt_path": prompt.relative_to(ROOT).as_posix(),
        "output_path": output.relative_to(ROOT).as_posix(),
        "evidence_hash": packet_hash,
    }


def ensure_proposer(ticker: str, work: Path, manifest: dict) -> None:
    path = work / "proposer.json"
    if path.exists():
        return
    research = ROOT / ticker / "research"
    valuation = read_json(research / "valuation.json")
    contract_path = research / "valuation_contract.json"
    contract = read_json(contract_path) if contract_path.exists() else valuation.get("universal_valuation_contract") or {}
    write_json(path, deterministic_proposer(ticker, valuation, contract, manifest.get("evidence") or []))


def first_round_tasks(ticker: str, as_of: str, work: Path, manifest: dict) -> list[dict]:
    packet = manifest["packet_hash"]
    rows = []
    pre_mortem = work / "pre_mortem.json"
    pre_mortem_payload = read_json(pre_mortem) if pre_mortem.exists() else {}
    if (not pre_mortem.exists()
            or validate_pre_mortem_binding(pre_mortem_payload, packet)):
        rows.append(task(ticker, as_of, "pre_mortem", work / "pre_mortem.prompt.md", pre_mortem, packet))
    for rater in manifest.get("selected_raters") or []:
        persona = rater["persona"]
        output = work / "round_1" / f"{persona}.json"
        payload = read_json(output) if output.exists() else {}
        if not output.exists() or validate_vote(payload, {**rater, **vote_binding(work)}):
            rows.append(task(ticker, as_of, f"round1-{persona}", work / "round_1" / f"{persona}.prompt.md", output, packet))
    return rows


def next_tasks(ticker: str, as_of: str) -> list[dict]:
    ticker = ticker.upper()
    work = ROOT / ticker / "research" / "committee_work" / as_of
    manifest = read_json(work / "manifest.json")
    raters = manifest.get("selected_raters") or []
    packet = manifest["packet_hash"]
    ensure_proposer(ticker, work, manifest)

    first = first_round_tasks(ticker, as_of, work, manifest)
    if first:
        return first

    round_one, errors = load_round(work, 1, raters)
    if errors:
        raise ValueError("invalid round one:\n- " + "\n- ".join(errors))
    escalation = escalation_decision(round_one)
    manifest["conditional_escalation"] = escalation
    manifest["stage"] = "conditional_escalation" if escalation["required"] else "chair_pending"
    write_json(work / "manifest.json", manifest)

    if escalation["required"]:
        response = work / "research_response.json"
        if escalation["research_required"] and not response.exists():
            return [task(ticker, as_of, "targeted-research", work / "research_response.prompt.md", response, packet)]
        second = []
        for rater in raters:
            persona = rater["persona"]
            output = work / "round_2" / f"{persona}.json"
            payload = read_json(output) if output.exists() else {}
            if not output.exists() or validate_vote(payload, {**rater, **vote_binding(work)}):
                second.append(task(ticker, as_of, f"round2-{persona}", work / "round_2" / f"{persona}.prompt.md", output, packet))
        if second:
            return second
    else:
        carry_round_one_forward(work, raters)

    final_votes, errors = load_round(work, 2, raters)
    if errors:
        raise ValueError("invalid final vote round:\n- " + "\n- ".join(errors))
    deterministic_committee_support(work, final_votes, escalation)
    chair = work / "chair_synthesis.json"
    chair_payload = read_json(chair) if chair.exists() else {}
    chair_errors = validate_chair_binding(
        chair_payload,
        packet,
        vote_set_hash(final_votes, packet),
    ) if chair.exists() else ["missing chair_synthesis"]
    if chair_errors:
        return [task(ticker, as_of, "chair-synthesis", work / "chair_synthesis.prompt.md", chair, packet)]
    manifest = read_json(work / "manifest.json")
    manifest["stage"] = "ready_to_assemble"
    write_json(work / "manifest.json", manifest)
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ticker", type=str.upper)
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    print(json.dumps(next_tasks(args.ticker, args.date), separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
