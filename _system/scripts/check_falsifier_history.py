#!/usr/bin/env python3
"""Fail CI when an immutable falsifier revision is edited or deleted."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from falsifier_specs import spec_payload_hash

ROOT = Path(__file__).resolve().parents[2]


def _identity(ticker: str, spec: dict) -> tuple[str, str, int] | None:
    if not spec.get("spec_id"):
        return None
    return ticker.upper(), str(spec["spec_id"]), int(spec.get("spec_revision") or 1)


def history_errors(base_docs: dict[str, dict], current_docs: dict[str, dict]) -> list[str]:
    errors = []
    base_records: dict[tuple[str, str, int], dict] = {}
    current_records: dict[tuple[str, str, int], dict] = {}
    for ticker, doc in base_docs.items():
        for spec in doc.get("specs") or []:
            identity = _identity(ticker, spec)
            if identity:
                base_records[identity] = spec
    for ticker, doc in current_docs.items():
        for spec in doc.get("specs") or []:
            identity = _identity(ticker, spec)
            if identity:
                if identity in current_records:
                    errors.append(f"duplicate immutable identity: {identity}")
                current_records[identity] = spec
    for identity, prior in sorted(base_records.items()):
        current = current_records.get(identity)
        if current is None:
            errors.append(f"immutable forecast deleted: {identity}")
        elif spec_payload_hash(current) != spec_payload_hash(prior):
            errors.append(f"immutable forecast edited: {identity}")
    known_ids = {(ticker, spec_id) for ticker, spec_id, _revision in base_records}
    for identity, spec in sorted(current_records.items()):
        if identity in base_records:
            continue
        ticker, spec_id, revision = identity
        supersedes = spec.get("supersedes_spec_id")
        if supersedes:
            if (ticker, str(supersedes)) not in known_ids:
                errors.append(f"supersedes unknown forecast: {identity} -> {supersedes}")
            prior_revisions = [prior_revision for prior_ticker, prior_id, prior_revision in base_records
                               if prior_ticker == ticker and prior_id == str(supersedes)]
            if prior_revisions and revision <= max(prior_revisions):
                errors.append(f"superseding revision must increase: {identity}")
        elif (ticker, spec_id) in known_ids:
            errors.append(f"new revision lacks supersedes_spec_id: {identity}")
    return errors


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], text=True,
                            capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout


def _current_docs(root: Path) -> dict[str, dict]:
    docs = {}
    for path in root.glob("*/research/falsifier_specs.json"):
        docs[path.parents[1].name] = json.loads(path.read_text(encoding="utf-8"))
    return docs


def _base_docs(root: Path, base_ref: str) -> dict[str, dict]:
    paths = [line.strip() for line in _git(root, "ls-tree", "-r", "--name-only", base_ref).splitlines()
             if line.strip().endswith("/research/falsifier_specs.json")]
    docs = {}
    for relative in paths:
        raw = _git(root, "show", f"{base_ref}:{relative}")
        docs[Path(relative).parts[0]] = json.loads(raw)
    return docs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--base-ref", default="origin/main")
    args = parser.parse_args()
    errors = history_errors(_base_docs(args.root, args.base_ref), _current_docs(args.root))
    for error in errors:
        print(f"ERROR: {error}")
    print(f"falsifier history: {len(errors)} violation(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
