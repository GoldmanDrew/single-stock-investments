#!/usr/bin/env python3
"""Promote independently approved forecast drafts into immutable sidecars."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from falsifier_evidence_adapters import preflight_spec
from falsifier_specs import calibration_eligibility, read_json, spec_errors, spec_payload_hash

ROOT = Path(__file__).resolve().parents[2]


def _component_fingerprint(component: dict) -> str:
    raw = json.dumps(component, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def promote(root: Path = ROOT, write: bool = True) -> dict:
    promoted, blocked = [], []
    for path in sorted(root.glob("*/research/falsifier_drafts/*.json")):
        try:
            draft = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            blocked.append({
                "draft": str(path.relative_to(root)).replace("\\", "/"),
                "reasons": [f"invalid draft JSON: {exc}"],
            })
            continue
        if draft.get("status") != "approved":
            continue
        ticker = path.parents[2].name.upper()
        spec = draft.get("spec") or {}
        contract = read_json(root / ticker / "research/valuation_contract.json")
        components = {str(row.get("component_id")): row
                      for row in contract.get("economic_ownership_map") or [] if isinstance(row, dict)}
        component = components.get(str(spec.get("component_id") or ""))
        reasons = list(spec_errors(spec))
        if not component or _component_fingerprint(component) != draft.get("component_fingerprint"):
            reasons.append("component fingerprint changed after authoring")
        eligible, eligibility_reason = calibration_eligibility(spec)
        if not eligible:
            reasons.append(f"not calibration eligible: {eligibility_reason}")
        preflight = preflight_spec(ticker, spec, root)
        if not preflight.get("ok"):
            reasons.append(f"source preflight failed: {preflight.get('reason')}")
        review = spec.get("review") or {}
        if review.get("reviewer") == spec.get("author"):
            reasons.append("reviewer must differ from author")
        if reasons:
            blocked.append({"draft": str(path.relative_to(root)).replace("\\", "/"),
                            "reasons": reasons})
            continue
        sidecar_path = root / ticker / "research/falsifier_specs.json"
        sidecar = read_json(sidecar_path) or {"schema_version": "3.0", "ticker": ticker, "specs": []}
        identities = {(str(row.get("spec_id")), int(row.get("spec_revision") or 1))
                      for row in sidecar.get("specs") or []}
        identity = (str(spec.get("spec_id")), int(spec.get("spec_revision") or 1))
        if identity not in identities:
            sidecar.setdefault("specs", []).append(spec)
        draft["status"] = "published"
        draft["published_at"] = datetime.now(timezone.utc).isoformat()
        draft["published_spec_hash"] = spec_payload_hash(spec)
        if write:
            sidecar_path.write_text(json.dumps(sidecar, indent=2) + "\n", encoding="utf-8")
            path.write_text(json.dumps(draft, indent=2) + "\n", encoding="utf-8")
        promoted.append({"ticker": ticker, "spec_id": spec.get("spec_id"),
                         "spec_hash": draft["published_spec_hash"]})
    return {"promoted": promoted, "blocked": blocked}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = promote(args.root, not args.dry_run)
    print(json.dumps({"promoted": len(result["promoted"]),
                      "blocked": len(result["blocked"]),
                      "blocked_details": result["blocked"]}, indent=2))
    return 1 if result["blocked"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
