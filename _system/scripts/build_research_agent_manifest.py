#!/usr/bin/env python3
"""Build a stable primary-evidence manifest for one research-agent decision."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


VOLATILE_KEYS = {
    "generated_at",
    "updated_at",
    "created_at",
    "downloaded_at",
    "fetched_at",
    "refreshed_at",
    "timestamp",
    "run_id",
    "run_attempt",
}


def candidates(ticker: str) -> list[Path]:
    """Return only documents that can authorize a new research judgment call.

    Derived valuation, narrative, queue, chart, and scan artifacts are excluded
    deliberately: refreshes rewrite them even when no new primary evidence exists.
    """
    base = ROOT / ticker.upper()
    primary = [
        base / "investor-documents" / "DOWNLOAD_MANIFEST.json",
        base / "investor-documents" / "TRANSCRIPT_MANIFEST.json",
        base / "research" / "authorized_evidence.json",
    ]
    return [path for path in primary if path.is_file()]


def normalized_value(value):
    """Remove refresh metadata and canonicalize primary-evidence records."""
    if isinstance(value, dict):
        return {
            str(key): normalized_value(child)
            for key, child in sorted(value.items())
            if str(key).lower() not in VOLATILE_KEYS
        }
    if isinstance(value, list):
        normalized = [normalized_value(child) for child in value]
        return sorted(normalized, key=lambda child: json.dumps(child, sort_keys=True, separators=(",", ":")))
    return value


def evidence_reference(path: Path) -> dict:
    raw = path.read_bytes()
    try:
        normalized = normalized_value(json.loads(raw))
        digest_source = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
    except json.JSONDecodeError:
        digest_source = raw
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": hashlib.sha256(digest_source).hexdigest(),
        "bytes": len(raw),
    }


def routed_observations(ticker: str) -> list[dict]:
    """Return proposed observations as leads, never as primary evidence."""
    path = ROOT / "_system/memory/routed_observations.jsonl"
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if str(row.get("ticker") or "").upper() == ticker.upper():
            rows.append(row)
    return rows


def build_manifest(ticker: str, reason: str) -> dict:
    refs = []
    for path in candidates(ticker):
        refs.append(evidence_reference(path))
    canonical_evidence = {"ticker": ticker.upper(), "evidence": refs}
    evidence_hash = hashlib.sha256(json.dumps(canonical_evidence, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    work_item = None
    if reason.startswith(("epistemic_author_forecast:", "epistemic_review_forecast:")):
        work_id = reason.split(":", 2)[1]
        queue_path = ROOT / "_system/data/epistemic_work_queue.json"
        if queue_path.exists():
            queue = json.loads(queue_path.read_text(encoding="utf-8"))
            work_item = next((item for item in queue.get("items") or []
                              if item.get("work_id") == work_id), None)
    status_path = ROOT / "_system/research/epistemic_loop_status.json"
    status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
    memory_leads = routed_observations(ticker)
    return {
        "schema_version": "2.0",
        **canonical_evidence,
        "reason": reason,
        "evidence_hash": evidence_hash,
        "artifact_count": len(refs),
        "ready": bool(refs),
        "primary_evidence_ready": bool(refs),
        "epistemic_work_item": work_item,
        "epistemic_input_sha": (work_item or {}).get("input_sha"),
        "calibration_release_hash": status.get("calibration_release_hash"),
        "routed_memory_observations": memory_leads,
        "routed_memory_warning": (
            "Proposed leads only: verify against primary evidence before changing research."
            if memory_leads else None
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ticker", type=str.upper)
    parser.add_argument("--reason", default="manual_material_change")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    value = build_manifest(args.ticker, args.reason)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(value, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
