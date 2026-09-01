#!/usr/bin/env python3
"""Production Investment Committee packet and assembly pipeline.

The script does not call models and never invents votes. It freezes evidence,
selects method-diverse raters, writes isolated work packets, validates completed
work, and assembles a schema-compatible record only after every required stage
exists.

Parking and un-parking
----------------------
`park_committee` is the circuit breaker: it stops a committee that would
otherwise loop or lose votes, sets `stage=parked`, and files the packet in
`_system/data/committee_triage.json`. `parked` is terminal, so no automatic job
touches a parked packet again - a human does, through
`select_committee_work.py`:

    # list what is parked and why
    python _system/scripts/select_committee_work.py --parked

    # keep the landed votes and put the packet back to work
    python _system/scripts/select_committee_work.py \\
        --unpark AAA --unpark-date 2026-07-18 --unpark-mode resume

    # throw the packet away and freeze a new one from live evidence
    python _system/scripts/select_committee_work.py \\
        --unpark AAA --unpark-date 2026-07-18 --unpark-mode discard

`resume` keeps the votes only when the frozen copies still hash to the recorded
packet. If they do not, it re-freezes from live evidence, moves every landed
vote into `invalidated_votes/<old-packet-prefix>/`, and re-issues the rater
prompts against the new packet hash: an answer to a packet that no longer
exists is never silently accepted. `discard` archives the whole work directory
and initializes a fresh one.

`initialize` refuses to open a second door into a work directory that already
holds votes or a park block. Re-initializing such a directory would reset the
stage, drop the park block, and mint a new packet hash, which would reject every
landed vote as answering a different packet.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import median

from build_valuation_workbench import write as write_valuation_workbench
from persona_groups import INDEPENDENCE_GROUPS as GROUPS

ROOT = Path(__file__).resolve().parents[2]
DIMS = ("explanatory_strength", "evidence_sufficiency", "downside_control", "return_vs_alternatives")
DEFAULT_RATERS = ("hohn", "pabrai", "marks_credit_cycle")
BASELINE_LLM_CALLS = 5
MAXIMUM_LLM_CALLS = 9
PIPELINE_VERSION = "3.1-copy-on-freeze"
SNAPSHOT_DIR = "evidence_snapshot"
# A committee that has been re-frozen this many times without a single vote
# landing is not waiting on evidence; it is looping. Park it instead.
MAX_REFRESHES_WITHOUT_VOTES = 3
TERMINAL_STAGES = {
    "assembled",
    "complete",
    "superseded",
    "parked",
    "evidence_blocked",
    "committee_complete_decision_pending",
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def triage_path() -> Path:
    """Resolved at call time so tests can relocate ROOT."""
    return ROOT / "_system" / "data" / "committee_triage.json"


def file_reference(path: Path, source: Path | None = None) -> dict:
    """Hash `path`; record `source` as the packet path when the bytes are a copy."""
    raw = path.read_bytes()
    return {
        "path": (source or path).relative_to(ROOT).as_posix(),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "role": "frozen local evidence",
        "status": "available",
    }


def packet_hash(refs: list[dict]) -> str:
    canonical = [{k: row[k] for k in ("path", "sha256", "bytes")} for row in sorted(refs, key=lambda x: x["path"])]
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def vote_set_hash(votes: list[dict], frozen_packet_hash: str) -> str:
    """Bind the chair to the exact final votes as well as the evidence packet."""
    canonical = {
        "evidence_packet_hash": frozen_packet_hash,
        "votes": sorted(votes, key=lambda row: (
            str(row.get("independence_group") or ""),
            str(row.get("persona") or ""),
        )),
    }
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def validate_chair_binding(chair: dict, frozen_packet_hash: str,
                           final_vote_hash: str) -> list[str]:
    """Reject a synthesis written before the final isolated vote set existed."""
    errors = []
    if chair.get("evidence_packet_hash") != frozen_packet_hash:
        errors.append("chair_synthesis evidence_packet_hash must match the frozen packet")
    if chair.get("vote_set_hash") != final_vote_hash:
        errors.append("chair_synthesis vote_set_hash must match the final isolated vote set")
    return errors


def validate_pre_mortem_binding(pre_mortem: dict, frozen_packet_hash: str) -> list[str]:
    """A pre-mortem is independent work and must identify the packet it tested."""
    if pre_mortem.get("evidence_packet_hash") != frozen_packet_hash:
        return ["pre_mortem evidence_packet_hash must match the frozen packet"]
    return []


def snapshot_name(ticker: str, path: Path) -> str:
    """Flatten a research-relative evidence path into one snapshot filename."""
    try:
        relative = path.relative_to(ROOT / ticker / "research")
    except ValueError:
        relative = Path(path.name)
    return relative.as_posix().replace("/", "__")


def freeze_evidence(ticker: str, work: Path, paths: list[Path]) -> list[dict]:
    """Copy every evidence file into the work dir and reference the copy.

    The packet hash is taken over the frozen copies, so the daily compilers may
    rewrite the live research tree without ageing a packet that raters are still
    voting on. Only a deliberate refresh replaces the copies.
    """
    snapshot = work / SNAPSHOT_DIR
    snapshot.mkdir(parents=True, exist_ok=True)
    for stale in snapshot.iterdir():
        if stale.is_file():
            stale.unlink()
    refs = []
    for path in paths:
        target = snapshot / snapshot_name(ticker, path)
        target.write_bytes(path.read_bytes())
        row = file_reference(target, source=path)
        row["snapshot_path"] = target.relative_to(ROOT).as_posix()
        refs.append(row)
    return refs


def has_snapshot(manifest: dict) -> bool:
    return bool(manifest.get("evidence_snapshot")) or any(
        row.get("snapshot_path") for row in manifest.get("evidence") or []
    )


def packet_refs(manifest: dict) -> list[dict]:
    """Rehash the packet: the frozen copies when present, the live files otherwise."""
    rows = manifest.get("evidence") or []
    if has_snapshot(manifest):
        return [file_reference(ROOT / row["snapshot_path"], source=ROOT / row["path"]) for row in rows]
    return [file_reference(ROOT / row["path"]) for row in rows]


def verify_packet(manifest: dict) -> bool:
    """True when the packet still hashes to its frozen value.

    Packets frozen before copy-on-freeze carry no snapshot and keep the old
    live-file behaviour, so existing records need no migration.
    """
    try:
        refs = packet_refs(manifest)
    except (FileNotFoundError, OSError):
        return False
    return packet_hash(refs) == manifest.get("packet_hash")


def live_evidence_drifted(manifest: dict) -> bool:
    """Live research files no longer match the frozen copies (informational only)."""
    if not has_snapshot(manifest):
        return False
    try:
        refs = [file_reference(ROOT / row["path"]) for row in manifest.get("evidence") or []]
    except (FileNotFoundError, OSError):
        return True
    return packet_hash(refs) != manifest.get("packet_hash")


def vote_files(work: Path) -> list[Path]:
    """Every landed vote file in this work dir, in a stable order."""
    return sorted(work.glob("round_*/*.json"))


def votes_landed(work: Path) -> int:
    return len(vote_files(work))


def record_triage(entry: dict) -> Path:
    """Upsert one parked committee into the operator triage file."""
    path = triage_path()
    document = read_json(path) if path.exists() else {"schema_version": "1.0", "parked": []}
    rows = [
        row
        for row in document.get("parked") or []
        if (row.get("ticker"), row.get("committee_date")) != (entry["ticker"], entry["committee_date"])
    ]
    rows.append(entry)
    document["parked"] = sorted(rows, key=lambda row: (row.get("ticker", ""), row.get("committee_date", "")))
    document["updated_at"] = datetime.now(timezone.utc).isoformat()
    write_json(path, document)
    return path


def clear_triage(ticker: str, committee_date: str) -> Path | None:
    """Drop one committee from the operator triage file after it is un-parked."""
    path = triage_path()
    if not path.exists():
        return None
    document = read_json(path)
    rows = [
        row
        for row in document.get("parked") or []
        if (row.get("ticker"), row.get("committee_date")) != (ticker, committee_date)
    ]
    document["parked"] = rows
    document["updated_at"] = datetime.now(timezone.utc).isoformat()
    write_json(path, document)
    return path


def park_committee(work: Path, reason: str, detail: str) -> dict:
    """Stop the loop and surface the committee instead of re-freezing it again."""
    manifest_path = work / "manifest.json"
    manifest = read_json(manifest_path)
    previous_stage = str(manifest.get("stage") or "") or "round_one_open"
    manifest["stage"] = "parked"
    manifest["parked"] = {
        "reason": reason,
        "detail": detail,
        "parked_at": datetime.now(timezone.utc).isoformat(),
        # The stage to restore on `--unpark-mode resume`; parking must not lose
        # how far the committee had already got.
        "previous_stage": previous_stage if previous_stage != "parked" else "round_one_open",
        "refresh_count": int(manifest.get("refresh_count") or 0),
        "votes_landed": votes_landed(work),
    }
    write_json(manifest_path, manifest)
    record_triage({
        "ticker": manifest.get("ticker"),
        "committee_date": manifest.get("as_of"),
        "packet_hash": manifest.get("packet_hash"),
        "work_dir": work.relative_to(ROOT).as_posix(),
        **manifest["parked"],
    })
    return manifest


def latest(ticker_dir: Path, pattern: str, exclude: str | None = None) -> Path | None:
    rows = sorted(path for path in ticker_dir.glob(pattern) if not exclude or exclude not in path.name)
    return rows[-1] if rows else None


def discover_evidence(ticker: str) -> list[Path]:
    research = ROOT / ticker / "research"
    candidates = [
        latest(research, "deep_dive_*.md", exclude="deep_dive_committee_"),
        latest(research, "adversarial_*.md"),
        research / "valuation_route.json",
        research / "valuation_contract.json",
        research / "valuation.json",
        research / "thesis.md",
        latest(research, "cross_check_third_party_*.md"),
        research / "cross_check_third_party.md",
        latest(research, "*evidence_reconciliation*.json"),
        latest(research, "*evidence_reconciliation*.md"),
        research / "committee_gap_carryforward.json",
        latest(research / "evidence", "filing_facts_*.json"),
        latest(research / "evidence", "management_facts_*.json"),
        ROOT / "_system" / "research" / "calibration_brief.json",
    ]
    seen: set[Path] = set()
    out = []
    for path in candidates:
        if path and path.exists() and path not in seen and "deep_dive_committee_" not in path.name:
            out.append(path)
            seen.add(path)
    return out


def select_raters(valuation: dict) -> list[dict]:
    """Pick three raters with distinct error profiles.

    Preference order: the power-zone method route's primary personas, then its
    cross-check personas, then component-coverage recommendations, then the
    static defaults. Personas the route explicitly silenced are never seated;
    the same routing that chose the valuation method chooses who reviews it.
    """
    route = valuation.get("valuation_method_route") or {}
    silent = set(route.get("silent_personas") or [])
    route_ranked = [
        persona
        for persona in [*(route.get("primary_personas") or []), *(route.get("cross_check_personas") or [])]
        if persona not in silent
    ]
    queue = valuation.get("component_review_queue") or {}
    counts = Counter(
        persona
        for item in queue.get("items", [])
        for persona in item.get("recommended_raters", [])
    )
    ranked: list[str] = list(dict.fromkeys([
        *route_ranked,
        *(persona for persona, _ in counts.most_common() if persona not in silent),
        *(persona for persona in DEFAULT_RATERS if persona not in silent),
    ]))
    selected = []
    groups: set[str] = set()
    for persona in ranked:
        if persona not in GROUPS:
            # An id outside the canonical registry cannot prove independence;
            # minting it a private group is how 31 committees seated two
            # quality_reinvestment raters (corrections.md 2026-08-11).
            continue
        group = GROUPS[persona]
        if group in groups:
            continue
        if persona in route_ranked:
            reason = "Selected before scoring from the power-zone method route (persona chose or cross-checks the valuation method)."
        else:
            reason = "Selected before scoring from component coverage and a distinct error profile."
        selected.append({
            "persona": persona,
            "independence_group": group,
            "selection_reason": reason,
            "required_inputs_status": "partial",
        })
        groups.add(group)
        if len(selected) == 3:
            break
    if len(selected) != 3:
        raise ValueError("could not select three independent rater groups")
    return selected


def rater_prompt(ticker: str, persona: str, group: str, packet: str, evidence: list[dict], round_number: int) -> str:
    paths = "\n".join(f"- `{row.get('snapshot_path') or row['path']}`" for row in evidence)
    return f"""# {ticker} - isolated committee round {round_number}

You are the **{persona}** method, independence group **{group}**.

Evidence packet: `{packet}`

{paths}

Rules:

1. Do not inspect another rater's output or any synthesis. In round two, you may read only your own round-one vote and the targeted research response.
2. Ignore time already spent on the idea and prior portfolio ownership.
3. Score explanatory strength, evidence sufficiency, downside control, and return versus alternatives from 1-5 with a rationale.
4. Use `insufficient_evidence` or `outside_power_zone` when appropriate; abstention is valid.
5. State the strongest counter-explanation and the single most important missing fact.
6. Audit the economic claim, every valuation-proof row, comparable adjustments, capital requirements, option probabilities, and overlap controls before voting.
7. Read only the frozen copies listed above. They are the packet; the live research tree may have moved on.
8. Return only one JSON object matching the committee schema vote definition, including `"evidence_hash": "{packet}"`. A vote whose evidence_hash does not match the packet it answers is rejected.
9. If the calibration brief is in the packet, read only this route's bucket. "insufficient_outcomes" cannot change your analysis; eligible history is a named challenge, never an automatic weight or sizing rule.
"""


def deterministic_proposer(ticker: str, valuation: dict, contract: dict, refs: list[dict]) -> dict:
    """Create the neutral case packet without spending an LLM call."""
    thesis_path = ROOT / ticker / "research" / "thesis.md"
    thesis = ""
    if thesis_path.exists():
        paragraphs = [part.strip() for part in thesis_path.read_text(encoding="utf-8", errors="ignore").split("\n\n")]
        thesis = next((part.replace("\n", " ") for part in paragraphs if part and not part.startswith("#")), "")
    if not thesis:
        thesis = str(
            ((valuation.get("economic_value_analysis") or {}).get("economic_claim"))
            or valuation.get("one_line_thesis")
            or "The frozen evidence packet contains the complete decision claim."
        )
    required_contract_keys = {
        "id", "mechanism", "evidence_paths", "distinguishing_test",
        "counter_explanation", "falsifier", "valuation_link",
    }
    explanation_contracts = [
        {key: row[key] for key in required_contract_keys}
        for row in (valuation.get("explanation_contracts") or [])
        if isinstance(row, dict) and required_contract_keys <= set(row)
    ]
    gaps = contract.get("gaps") or contract.get("open_gaps") or []
    open_questions = []
    for gap in gaps:
        if isinstance(gap, dict):
            open_questions.append(str(gap.get("question") or gap.get("description") or gap.get("id") or gap))
        else:
            open_questions.append(str(gap))
    return {
        "recommendation_hidden_in_round_one": True,
        "thesis": thesis,
        "explanation_contracts": explanation_contracts,
        "open_questions": open_questions,
    }


def escalation_decision(votes: list[dict]) -> dict:
    """Admit extra calls only when disagreement or evidence insufficiency is material."""
    reasons = []
    split = Counter(vote.get("vote") for vote in votes)
    if not split or max(split.values()) < 2:
        reasons.append("no_two_vote_majority")
    if any(vote.get("evidence_status") != "sufficient" for vote in votes):
        reasons.append("insufficient_or_outside_power_zone")
    for dim in DIMS:
        values = [((vote.get("scores") or {}).get(dim) or {}).get("value") for vote in votes]
        values = [value for value in values if isinstance(value, int)]
        if values and max(values) - min(values) > 2:
            reasons.append(f"score_dispersion:{dim}")
    ranges = [vote.get("expected_return_range_pct") for vote in votes if vote.get("expected_return_range_pct")]
    if len(ranges) >= 2:
        bases = [(float(row[0]) + float(row[1])) / 2 for row in ranges]
        if max(bases) - min(bases) >= 10:
            reasons.append("return_range_dispersion_10pct")
    return {
        "required": bool(reasons),
        "research_required": any(vote.get("evidence_status") == "insufficient_evidence" for vote in votes),
        "reasons": reasons,
        "baseline_llm_calls": BASELINE_LLM_CALLS,
        "maximum_llm_calls": MAXIMUM_LLM_CALLS,
    }


def carry_round_one_forward(work: Path, raters: list[dict]) -> None:
    for row in raters:
        source = work / "round_1" / f"{row['persona']}.json"
        target = work / "round_2" / f"{row['persona']}.json"
        # No-escalation round two is defined as the validated round-one vote.
        # Always refresh it so an unbound legacy file cannot shadow a current,
        # hash-bound round-one answer merely because the path already exists.
        if source.exists():
            write_json(target, read_json(source))


def deterministic_committee_support(work: Path, votes: list[dict], escalation: dict) -> None:
    """Assemble factual/reconciliation/adversarial support without agent calls."""
    manifest = read_json(work / "manifest.json")
    packet = manifest["packet_hash"]
    final_vote_hash = vote_set_hash(votes, packet)
    evidence_paths = [row["path"] for row in manifest.get("evidence") or []]
    missing = sorted({
        str(vote.get("most_important_missing_fact") or "").strip()
        for vote in votes
        if vote.get("evidence_status") == "insufficient_evidence" and vote.get("most_important_missing_fact")
    })
    claims = [claim for vote in votes for claim in (vote.get("claims") or [])]
    write_json(work / "evidence_tribunal.json", {
        "status": "blocked" if missing else "complete",
        "resolved_facts": claims if not missing else [],
        "disputed_facts": escalation.get("reasons") or [],
        "unresolved_material_facts": missing,
        "evidence_paths": evidence_paths,
        "method": "deterministic_vote_and_packet_reconciliation",
    })
    response_path = work / "research_response.json"
    if not response_path.exists():
        write_json(response_path, {
            "loop_count": 0,
            "questions": [],
            "responses": [],
            "evidence_hash_after": packet,
        })
    disagreements = []
    split = Counter(vote.get("vote") for vote in votes)
    if len(split) > 1:
        disagreements.append({"type": "recommendation", "vote_split": dict(split)})
    for dim in DIMS:
        values = [vote["scores"][dim]["value"] for vote in votes]
        if max(values) != min(values):
            disagreements.append({"type": "score", "dimension": dim, "range": [min(values), max(values)]})
    route = read_json(ROOT / manifest["ticker"] / "research" / "valuation_route.json")
    write_json(work / "valuation_reconciliation.json", {
        "status": "complete",
        "disagreements": disagreements,
        "selected_primary_method": route.get("profile_id"),
        "rejected_averages": ["No incompatible valuation methods were averaged to manufacture consensus."],
        "method": "deterministic_classification",
    })
    pre_mortem = read_json(work / "pre_mortem.json")
    write_json(work / "adversarial_review.json", {
        "status": "complete_with_residual_risks" if pre_mortem.get("unresolved_items") else "complete",
        "tests": pre_mortem.get("forensic_checks") or [],
        "residual_risks": pre_mortem.get("unresolved_items") or [],
        "strongest_failure_path": pre_mortem.get("failure_story") or "No completed pre-mortem failure path.",
        "source": "independent_pre_mortem",
    })
    write_json(work / "committee_support.json", {
        "schema_version": "1.0",
        "evidence_packet_hash": packet,
        "vote_set_hash": final_vote_hash,
        "final_vote_count": len(votes),
        "independence_groups": sorted({
            str(vote.get("independence_group") or "") for vote in votes
        }),
        "rule": "The chair must copy both hashes; synthesis created before this vote set is invalid.",
    })


def write_prompts(ticker: str, work: Path, frozen_hash: str, refs: list[dict], raters: list[dict]) -> None:
    """(Re)issue every prompt bound to `frozen_hash`.

    Called on initialize and again whenever a resumed packet is re-frozen, so a
    rater is never handed a prompt quoting a packet hash that no longer exists.
    """
    for round_number in (1, 2):
        round_dir = work / f"round_{round_number}"
        round_dir.mkdir(parents=True, exist_ok=True)
        for row in raters:
            prompt = rater_prompt(ticker, row["persona"], row["independence_group"], frozen_hash, refs, round_number)
            (round_dir / f"{row['persona']}.prompt.md").write_text(prompt, encoding="utf-8")
    (work / "pre_mortem.prompt.md").write_text(
        f"# {ticker} mandatory pre-mortem\n\nPacket `{frozen_hash}`. Assume the investment failed severely. Explain the causal failure, earliest warnings, forensic checks, short-source coverage, and unresolved items. Do not read rater outputs. Include `\"evidence_packet_hash\": \"{frozen_hash}\"`. Return the committee schema pre_mortem object only.\n",
        encoding="utf-8",
    )
    (work / "evidence_tribunal.prompt.md").write_text(
        f"# {ticker} evidence tribunal\n\nPacket `{frozen_hash}`. Resolve disputed quantities, ownership, distributions, comparable validity, option beneficiary, and overlap before valuation debate. Separate resolved facts from material unresolved facts and cite packet paths. Return evidence_tribunal.json only.\n",
        encoding="utf-8",
    )
    (work / "research_response.prompt.md").write_text(
        f"# {ticker} targeted committee research response\n\nPacket `{frozen_hash}`. Read the deterministic proposer, round-one reviews, and pre-mortem. Answer only decision-material questions raised by insufficient-evidence votes using the frozen packet. If the packet cannot answer a question, mark it unresolved. Do not change the packet or read/write round-two votes. Return one research_loop object with loop_count=1, questions, schema-valid responses, and evidence_hash_after=`{frozen_hash}`.\n",
        encoding="utf-8",
    )
    (work / "valuation_reconciliation.prompt.md").write_text(
        f"# {ticker} valuation reconciliation\n\nClassify every material difference among isolated outputs as factual, methodological, assumption-based, horizon-based, risk-tolerance-based, or power-zone mismatch. Do not average incompatible estimates. Return valuation_reconciliation.json only.\n",
        encoding="utf-8",
    )
    (work / "adversarial_review.prompt.md").write_text(
        f"# {ticker} adversarial review\n\nTest double counting, peak-cycle extrapolation, reinvestment, multiple dependence, hidden capital, dilution, governance, tax, macro sensitivity, beneficiary mismatch, and comparable-cycle bias. Return adversarial_review.json only.\n",
        encoding="utf-8",
    )
    (work / "chair_synthesis.prompt.md").write_text(
        f"# {ticker} chair synthesis\n\nPacket `{frozen_hash}`. Read only `committee_support.json`, the frozen packet, the final isolated votes in `round_2/`, and the deterministic support files. Select the primary method, explain why it dominates corroborating methods, preserve dissent, state agreed and disputed facts, value and entry ranges, recommendation, and monitoring plan. Never average methods solely to create consensus. Copy `evidence_packet_hash` and `vote_set_hash` exactly from `committee_support.json`. Return chair_synthesis.json only.\n",
        encoding="utf-8",
    )


def occupied_reason(work: Path) -> str | None:
    """Why `work` must not be re-initialized, or None when it is free to use.

    Re-initializing over live work is a second door into the same failure the
    refresh circuit breaker closes: it drops the park block, resets the stage
    and refresh counter, and mints a new packet hash, which turns every landed
    vote into an answer to a packet that no longer exists.
    """
    if not work.exists():
        return None
    manifest_path = work / "manifest.json"
    manifest = read_json(manifest_path) if manifest_path.exists() else {}
    if manifest.get("parked") or str(manifest.get("stage") or "") == "parked":
        detail = (manifest.get("parked") or {}).get("reason") or "unknown"
        return (
            f"the committee is parked ({detail}); re-initializing would drop the park block. "
            "Use select_committee_work.py --unpark ... --unpark-mode resume|discard."
        )
    landed = vote_files(work)
    if landed:
        names = ", ".join(path.relative_to(work).as_posix() for path in landed[:5])
        return (
            f"{len(landed)} vote file(s) already answer this packet ({names}); re-initializing "
            "would mint a new packet hash and reject every one of them. Refresh or un-park "
            "through select_committee_work.py, which preserves or explicitly invalidates votes."
        )
    return None


def initialize(ticker: str, as_of: str) -> Path:
    ticker = ticker.upper()
    research = ROOT / ticker / "research"
    occupied = occupied_reason(research / "committee_work" / as_of)
    if occupied:
        raise FileExistsError(f"{ticker} {as_of}: refusing to re-initialize committee work: {occupied}")
    valuation_path = research / "valuation.json"
    if not valuation_path.exists():
        raise FileNotFoundError(f"{ticker}: valuation.json missing")
    valuation = read_json(valuation_path)
    canonical_route = research / "valuation_route.json"
    if canonical_route.exists():
        valuation["valuation_method_route"] = read_json(canonical_route)
    contract_path = research / "valuation_contract.json"
    contract = read_json(contract_path) if contract_path.exists() else (valuation.get("universal_valuation_contract") or {})
    if contract.get("status") != "decision_grade":
        raise ValueError(f"{ticker}: committee requires a decision-grade valuation contract")
    proof_summary = contract.get("calculation_proof_summary") or {}
    model_checks = contract.get("model_checks") or {}
    if not proof_summary.get("all_material_components_priced") or not all(model_checks.values()):
        raise ValueError(f"{ticker}: committee requires complete, valid calculation proofs and passing model checks")
    if (valuation.get("valuation_method_route") or {}).get("status") in {"default_needs_review", "reviewer_coverage_blocked"}:
        raise ValueError(f"{ticker}: canonical Power Zone route is not committee-ready")
    evidence_paths = discover_evidence(ticker)
    substantive = [
        path
        for path in evidence_paths
        if path.name == "thesis.md" or path.name.startswith(("deep_dive_", "adversarial_"))
    ]
    if len(evidence_paths) < 3 or not substantive:
        raise ValueError(
            f"{ticker}: at least three evidence artifacts, including a thesis, deep dive, or adversarial review, are required"
        )
    raters = select_raters(valuation)
    work = research / "committee_work" / as_of
    refs = freeze_evidence(ticker, work, evidence_paths)
    frozen_hash = packet_hash(refs)
    manifest = {
        "pipeline_version": PIPELINE_VERSION,
        "ticker": ticker,
        "as_of": as_of,
        "stage": "round_one_open",
        "packet_hash": frozen_hash,
        "evidence_snapshot": (work / SNAPSHOT_DIR).relative_to(ROOT).as_posix(),
        "refresh_count": 0,
        "route_hash": (valuation.get("valuation_method_route") or {}).get("input_hash"),
        "contract_source": "valuation_contract.json" if contract_path.exists() else "valuation.json#universal_valuation_contract",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "evidence": refs,
        "selected_raters": raters,
        "llm_policy": {
            "baseline_calls": BASELINE_LLM_CALLS,
            "maximum_calls": MAXIMUM_LLM_CALLS,
            "baseline_tasks": ["pre_mortem", "round1:<three-independent-raters>", "chair_synthesis"],
            "conditional_tasks": ["targeted_research", "round2:<three-independent-raters>"],
            "deterministic_tasks": ["proposer", "evidence_tribunal", "valuation_reconciliation", "adversarial_review", "assembly"],
        },
        "required_files": {
            "proposer": "proposer.json",
            "pre_mortem": "pre_mortem.json",
            "evidence_tribunal": "evidence_tribunal.json",
            "research_response": "research_response.json",
            "valuation_reconciliation": "valuation_reconciliation.json",
            "adversarial_review": "adversarial_review.json",
            "chair_synthesis": "chair_synthesis.json",
            "human_decision": "human_decision.json",
        },
    }
    write_json(work / "manifest.json", manifest)
    write_json(work / "proposer.json", deterministic_proposer(ticker, valuation, contract, refs))
    write_prompts(ticker, work, frozen_hash, refs, raters)
    return work


def validate_vote(vote: dict, expected: dict) -> list[str]:
    errors = []
    if vote.get("persona") != expected["persona"]:
        errors.append(f"persona must be {expected['persona']}")
    if vote.get("independence_group") != expected["independence_group"]:
        errors.append(f"independence_group must be {expected['independence_group']}")
    if set((vote.get("scores") or {})) != set(DIMS):
        errors.append("all four calibrated scores are required")
    for dim in DIMS:
        score = (vote.get("scores") or {}).get(dim) or {}
        if not isinstance(score.get("value"), int) or not 1 <= score["value"] <= 5 or not score.get("rationale"):
            errors.append(f"{dim} requires value 1-5 and rationale")
    if vote.get("vote") not in {"approve", "watch", "defer", "reject"}:
        errors.append("invalid vote")
    if vote.get("evidence_status") not in {"sufficient", "insufficient_evidence", "outside_power_zone"}:
        errors.append("invalid evidence_status")
    for key in ("claims", "strongest_counter_explanation", "most_important_missing_fact", "falsifiers", "specialist_findings", "confidence"):
        if vote.get(key) in (None, "", []):
            errors.append(f"{key} is required")
    expected_hash = expected.get("packet_hash")
    binding = expected.get("hash_binding", "required")
    claimed = vote.get("evidence_hash")
    if not expected_hash:
        # Fail closed: with no packet hash to bind to there is nothing proving
        # this vote answers the packet it was filed under.
        if binding == "required":
            errors.append("no frozen packet hash is available to bind this vote to")
    elif not claimed:
        if binding == "required":
            errors.append("evidence_hash is required and must equal the frozen packet hash")
    elif claimed != expected_hash:
        errors.append(
            f"evidence_hash {claimed[:12]} answers a different packet than {expected_hash[:12]}"
        )
    return errors


def vote_binding(work: Path) -> dict:
    """Hash binding for votes in this work dir.

    Copy-on-freeze packets bind every vote to the packet hash. Packets frozen
    before copy-on-freeze only reject a hash that is present and wrong, so past
    records stay valid without migration. A missing manifest fails closed: no
    manifest means no packet to answer, so no vote can validate.
    """
    manifest_path = work / "manifest.json"
    if not manifest_path.exists():
        return {"packet_hash": None, "hash_binding": "required"}
    manifest = read_json(manifest_path)
    return {
        "packet_hash": manifest.get("packet_hash"),
        "hash_binding": "required" if has_snapshot(manifest) else "legacy_optional",
    }


def load_round(work: Path, round_number: int, raters: list[dict]) -> tuple[list[dict], list[str]]:
    votes, errors = [], []
    binding = vote_binding(work)
    for expected in raters:
        path = work / f"round_{round_number}" / f"{expected['persona']}.json"
        if not path.exists():
            errors.append(f"missing {path.relative_to(work)}")
            continue
        vote = read_json(path)
        errors.extend(f"{path.name}: {message}" for message in validate_vote(vote, {**expected, **binding}))
        votes.append(vote)
    return votes, errors


def validate_work(work: Path) -> list[str]:
    manifest = read_json(work / "manifest.json")
    raters = manifest["selected_raters"]
    errors = []
    if len({row["independence_group"] for row in raters}) != 3:
        errors.append("raters must use three distinct independence groups")
    for round_number in (1, 2):
        _, round_errors = load_round(work, round_number, raters)
        errors.extend(round_errors)
    for name in (
        "proposer.json", "pre_mortem.json", "evidence_tribunal.json", "research_response.json",
        "valuation_reconciliation.json", "adversarial_review.json", "committee_support.json",
        "chair_synthesis.json",
    ):
        if not (work / name).exists():
            errors.append(f"missing {name}")
    if (work / "pre_mortem.json").exists():
        errors.extend(validate_pre_mortem_binding(
            read_json(work / "pre_mortem.json"),
            str(manifest.get("packet_hash") or ""),
        ))
    final_votes, final_vote_errors = load_round(work, 2, raters)
    if not final_vote_errors and (work / "chair_synthesis.json").exists():
        chair = read_json(work / "chair_synthesis.json")
        errors.extend(validate_chair_binding(
            chair,
            str(manifest.get("packet_hash") or ""),
            vote_set_hash(final_votes, str(manifest.get("packet_hash") or "")),
        ))
    if not verify_packet(manifest):
        errors.append(
            "frozen evidence copies changed after freezing"
            if has_snapshot(manifest)
            else "evidence packet changed after freezing"
        )
    return errors


def assembled_packet_hash(ticker: str, as_of: str) -> str | None:
    path = ROOT / ticker / "research" / f"committee_{as_of}.json"
    if not path.exists():
        return None
    return ((read_json(path).get("evidence_packet") or {}).get("packet_hash")) or None


def stale_archive_name(path: Path, as_of: str, suffix: str) -> Path:
    """A free archive name; never overwrite an audit artifact already on disk.

    Two different stale records can share the first eight hex characters of
    their packet hash, so the first name is uniquified rather than unlinked.
    """
    archive = path.with_name(f"committee_{as_of}-superseded-{suffix}.json")
    if not archive.exists():
        return archive
    for index in range(2, 100):
        candidate = path.with_name(f"committee_{as_of}-superseded-{suffix}-{index}.json")
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"cannot archive stale assembled record: {archive}")


def archive_stale_assembled(ticker: str, as_of: str, current_hash: str) -> Path | None:
    """Move an assembled record built from a superseded packet out of the way.

    The archive name deliberately breaks the `committee_????-??-??.json` glob
    every reader uses, so the stale record stops being the authority while
    staying on disk for audit.
    """
    recorded = assembled_packet_hash(ticker, as_of)
    if not recorded or recorded == current_hash:
        return None
    path = ROOT / ticker / "research" / f"committee_{as_of}.json"
    archive = stale_archive_name(path, as_of, recorded[:8])
    path.rename(archive)
    return archive


def assemble(work: Path) -> Path:
    errors = validate_work(work)
    if errors:
        raise ValueError("committee work is incomplete:\n- " + "\n- ".join(errors))
    manifest = read_json(work / "manifest.json")
    ticker = manifest["ticker"]
    raters = manifest["selected_raters"]
    round_one, _ = load_round(work, 1, raters)
    round_two, _ = load_round(work, 2, raters)
    proposer = read_json(work / "proposer.json")
    pre_mortem = read_json(work / "pre_mortem.json")
    evidence_tribunal = read_json(work / "evidence_tribunal.json")
    research_loop = read_json(work / "research_response.json")
    valuation_reconciliation = read_json(work / "valuation_reconciliation.json")
    adversarial_review = read_json(work / "adversarial_review.json")
    chair_synthesis = read_json(work / "chair_synthesis.json")
    medians = {dim: median(v["scores"][dim]["value"] for v in round_two) for dim in DIMS}
    ranges = {dim: [min(v["scores"][dim]["value"] for v in round_two), max(v["scores"][dim]["value"] for v in round_two)] for dim in DIMS}
    dissent = min(round_two, key=lambda v: (v["scores"]["return_vs_alternatives"]["value"], v["scores"]["downside_control"]["value"]))
    unresolved = sorted({v["most_important_missing_fact"] for v in round_two if v["most_important_missing_fact"]})
    valuation = read_json(ROOT / ticker / "research" / "valuation.json")
    contract = read_json(ROOT / ticker / "research" / "valuation_contract.json")
    economic = valuation.get("economic_value_analysis") or {}
    component = valuation.get("component_valuation_results") or {}
    proof = economic.get("valuation_proof") or []
    options = [row for row in proof if row.get("treatment") == "additive" and "option" in str(row.get("method", "")).lower()]
    economic_complete = economic.get("status") == "complete"
    component_complete = component.get("status") == "complete" and component.get("all_material_components_identified")
    comparable_complete = economic_complete and all(
        row.get("comparable_role") == "not_applicable" or row.get("comparable_ids")
        for row in proof
    )
    option_complete = all(row.get("falsifier") and row.get("range_per_share") for row in options)
    proof_summary = contract.get("calculation_proof_summary") or {}
    model_checks = contract.get("model_checks") or {}
    proof_complete = bool(proof_summary.get("all_material_components_priced")) and bool(model_checks) and all(model_checks.values())
    tribunal_blocked = bool(evidence_tribunal.get("unresolved_material_facts")) or evidence_tribunal.get("status") != "complete"
    adversarial_blocked = adversarial_review.get("status") not in {"complete", "complete_with_residual_risks"}
    chair_blocked = chair_synthesis.get("status") != "complete"
    blocked = any(v["evidence_status"] != "sufficient" for v in round_two) or not economic_complete or not component_complete or not proof_complete or tribunal_blocked or adversarial_blocked or chair_blocked
    record = {
        "schema_version": "1.0",
        "protocol_version": "production-2.0",
        "ticker": ticker,
        "review": {"level": "full_ic", "trigger": "production committee pipeline", "as_of": manifest["as_of"], "owner": None},
        "evidence_packet": {"frozen_at": manifest["frozen_at"], "hash_method": "sha256(canonical-json(sorted(path,sha256,bytes)))", "packet_hash": manifest["packet_hash"], "freshness_status": "mixed", "references": manifest["evidence"]},
        "proposer": proposer,
        "selected_raters": raters,
        "round_one": {"evidence_hash": manifest["packet_hash"], "peer_outputs_visible": False, "votes": round_one},
        "pre_mortem": pre_mortem,
        "evidence_tribunal": evidence_tribunal,
        "research_loop": research_loop,
        "round_two": {"evidence_hash": manifest["packet_hash"], "peer_outputs_visible": False, "votes": round_two},
        "valuation_reconciliation": valuation_reconciliation,
        "adversarial_review": adversarial_review,
        "chair_synthesis": chair_synthesis,
        "synthesis": {
            "strongest_dissent": dissent["strongest_counter_explanation"],
            "unresolved_items": unresolved,
            "vote_split": dict(Counter(v["vote"] for v in round_two)),
            "score_medians": medians,
            "score_ranges": ranges,
            "dissent_ledger": [{"issue": item, "impact": "high", "status": "unresolved", "owner_response": None} for item in unresolved],
        },
        "component_review": valuation.get("component_review_queue"),
        "gates": {
            "price": "pass" if (valuation.get("inputs") or {}).get("price") else "blocked",
            "shares": "pass" if (valuation.get("inputs") or {}).get("shares_outstanding") else "blocked",
            "reporting_period": "pass",
            "filing_reconciliation": "pass",
            "economic_claim": "pass" if economic_complete else "blocked",
            "component_completeness": "pass" if component_complete else "blocked",
            "calculation_proof": "pass" if proof_complete else "blocked",
            "comparable_evidence": "pass" if comparable_complete else "partial",
            "option_risking": "pass" if option_complete else "blocked",
            "disclosure_scan": "partial",
            "short_scan": "partial",
            "pre_mortem": "pass",
            "evidence_tribunal": "blocked" if tribunal_blocked else "pass",
            "valuation_reconciliation": "pass" if valuation_reconciliation.get("status") == "complete" else "blocked",
            "adversarial_review": "blocked" if adversarial_blocked else "pass",
            "chair_synthesis": "blocked" if chair_blocked else "pass",
            "explanation_contracts": "pass",
            "independent_groups": "pass",
            "owner": "not_run",
        },
        "human_decision": {"status": "pending", "decision": None, "sizing": None, "top_dissent_response": None, "decided_at": None},
        "monitoring_plan": chair_synthesis.get("monitoring_plan") or {
            "operational_milestones": [],
            "evidence_refresh_dates": [],
            "valuation_refresh_triggers": ["material filing", "capital-structure change", "thesis falsifier"],
            "price_review_thresholds": [],
            "thesis_break_conditions": [],
            "expected_catalyst_dates": [],
            "outcome_horizons_months": [6, 12, 24],
        },
        "final_state": "evidence_blocked" if blocked else "committee_complete_decision_pending",
        "provenance": {"prompt_version": "token-efficient-isolated-rater-3", "model": "five-call baseline with conditional escalation and deterministic support assembly", "schema_path": "_system/templates/committee_schema.json", "persona_registry_version": "1.1"},
    }
    if record["component_review"] is None:
        record.pop("component_review")
    archive_stale_assembled(ticker, manifest["as_of"], manifest["packet_hash"])
    output = ROOT / ticker / "research" / f"committee_{manifest['as_of']}.json"
    write_json(output, record)
    manifest["stage"] = record["final_state"]
    write_json(work / "manifest.json", manifest)
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("ticker")
    init.add_argument("--date", default=date.today().isoformat())
    check = sub.add_parser("validate")
    check.add_argument("ticker")
    check.add_argument("--date", required=True)
    build = sub.add_parser("assemble")
    build.add_argument("ticker")
    build.add_argument("--date", required=True)
    args = parser.parse_args()
    if args.command == "init":
        print(initialize(args.ticker, args.date).relative_to(ROOT))
        write_valuation_workbench(args.ticker, args.date)
        return 0
    work = ROOT / args.ticker.upper() / "research" / "committee_work" / args.date
    if args.command == "validate":
        errors = validate_work(work)
        write_valuation_workbench(args.ticker, args.date)
        print("valid" if not errors else "\n".join(errors))
        return 0 if not errors else 1
    print(assemble(work).relative_to(ROOT))
    write_valuation_workbench(args.ticker, args.date)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
