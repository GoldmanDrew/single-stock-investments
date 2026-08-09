#!/usr/bin/env python3
"""Validate that a Cursor Investment Committee PR carries a valid task artifact."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from investment_committee_pipeline import has_snapshot, validate_vote

ROOT = Path(__file__).resolve().parents[2]
COMMITTEE_RE = re.compile(
    r"^(?P<ticker>[^/]+)/research/committee_work/"
    r"(?P<as_of>\d{4}-\d{2}-\d{2})/(?P<rel>.+)$"
)
ALLOWED_TOP_LEVEL = {
    "pre_mortem.json",
    "research_response.json",
    "chair_synthesis.json",
}
FORBIDDEN_BASENAMES = {
    "manifest.json",
    "proposer.json",
    "evidence_tribunal.json",
    "valuation_reconciliation.json",
    "adversarial_review.json",
    "human_decision.json",
}
ROUND_RE = re.compile(r"^round_([12])/([^/]+)\.json$")


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def validate_pre_mortem(payload: dict) -> list[str]:
    errors: list[str] = []
    for key in (
        "failure_story",
        "earliest_warning_signals",
        "forensic_checks",
        "short_source_coverage",
        "unresolved_items",
    ):
        if payload.get(key) in (None, ""):
            errors.append(f"pre_mortem missing {key}")
    if not isinstance(payload.get("earliest_warning_signals"), list):
        errors.append("pre_mortem earliest_warning_signals must be a list")
    if not isinstance(payload.get("forensic_checks"), list):
        errors.append("pre_mortem forensic_checks must be a list")
    if not isinstance(payload.get("unresolved_items"), list):
        errors.append("pre_mortem unresolved_items must be a list")
    return errors


def validate_chair(payload: dict) -> list[str]:
    errors: list[str] = []
    for key in (
        "primary_method",
        "weighting_rationale",
        "agreed_facts",
        "disputed_facts",
        "recommendation",
        "monitoring_plan",
    ):
        if payload.get(key) in (None, ""):
            errors.append(f"chair_synthesis missing {key}")
    if payload.get("recommendation") not in {"approve", "watch", "defer", "reject", None}:
        # Allow free-text recommendation strings used by some chairs, but reject empty.
        if not isinstance(payload.get("recommendation"), str):
            errors.append("chair_synthesis recommendation must be a string")
    plan = payload.get("monitoring_plan")
    if not isinstance(plan, dict):
        errors.append("chair_synthesis monitoring_plan must be an object")
    return errors


def validate_research_response(payload: dict) -> list[str]:
    if not payload:
        return ["research_response is empty"]
    if not any(payload.get(key) not in (None, "", []) for key in payload):
        return ["research_response has no substantive fields"]
    return []


def validate_artifact(path: Path, rel: str, manifest: dict) -> list[str]:
    payload = read_json(path)
    if rel == "pre_mortem.json":
        return validate_pre_mortem(payload)
    if rel == "chair_synthesis.json":
        return validate_chair(payload)
    if rel == "research_response.json":
        return validate_research_response(payload)
    match = ROUND_RE.match(rel)
    if match:
        persona = match.group(2)
        expected = next(
            (row for row in (manifest.get("selected_raters") or []) if row.get("persona") == persona),
            None,
        )
        if expected is None:
            return [f"{rel}: persona {persona} is not a selected rater"]
        # Bind the vote to the packet it claims to answer, so a vote written
        # against a superseded packet cannot merge.
        bound = {
            **expected,
            "packet_hash": manifest.get("packet_hash"),
            "hash_binding": "required" if has_snapshot(manifest) else "legacy_optional",
        }
        return [f"{rel}: {message}" for message in validate_vote(payload, bound)]
    return [f"unsupported committee artifact: {rel}"]


def classify_paths(paths: list[str]) -> tuple[list[str], list[str]]:
    """Return (committee_paths, other_paths)."""
    committee: list[str] = []
    other: list[str] = []
    for raw in paths:
        path = raw.replace("\\", "/").strip()
        if not path:
            continue
        if COMMITTEE_RE.match(path):
            committee.append(path)
        else:
            other.append(path)
    return committee, other


def validate_paths(paths: list[str], *, root: Path = ROOT) -> list[str]:
    committee, other = classify_paths(paths)
    errors: list[str] = []
    if other:
        errors.append(
            "committee PR may only change committee_work artifacts; unexpected: "
            + ", ".join(other[:8])
        )
    if not committee:
        errors.append("committee PR must include at least one committee_work JSON artifact")
        return errors

    by_packet: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for path in committee:
        match = COMMITTEE_RE.match(path)
        assert match is not None
        ticker = match.group("ticker")
        as_of = match.group("as_of")
        rel = match.group("rel")
        if rel.endswith(".prompt.md"):
            errors.append(f"committee PR must not edit prompt files: {path}")
            continue
        if Path(rel).name in FORBIDDEN_BASENAMES or rel in FORBIDDEN_BASENAMES:
            errors.append(f"committee PR must not edit frozen/deterministic file: {path}")
            continue
        if not (rel in ALLOWED_TOP_LEVEL or ROUND_RE.match(rel)):
            errors.append(f"unsupported committee artifact path: {path}")
            continue
        by_packet.setdefault((ticker, as_of), []).append((path, rel))

    for (ticker, as_of), rows in sorted(by_packet.items()):
        manifest_path = root / ticker / "research" / "committee_work" / as_of / "manifest.json"
        if not manifest_path.exists():
            errors.append(f"missing committee manifest for {ticker} {as_of}")
            continue
        try:
            manifest = read_json(manifest_path)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if str(manifest.get("ticker") or "").upper() != ticker.upper():
            errors.append(f"{manifest_path}: ticker mismatch")
        for path, rel in rows:
            full = root / path
            if not full.exists():
                errors.append(f"missing artifact on head: {path}")
                continue
            try:
                errors.extend(validate_artifact(full, rel, manifest))
            except ValueError as exc:
                errors.append(str(exc))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        help="Changed paths in the PR (also accepts newline-delimited stdin)",
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    paths = list(args.paths)
    if not sys.stdin.isatty():
        paths.extend(line.strip() for line in sys.stdin if line.strip())
    errors = validate_paths(paths, root=args.root)
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print(f"OK: {len(paths)} committee PR path(s) validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
