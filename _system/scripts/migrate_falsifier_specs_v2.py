#!/usr/bin/env python3
"""One-time, deterministic migration of legacy falsifier sidecars to v2."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from falsifier_specs import is_v2_spec  # noqa: E402


MEASUREMENT_END = {
    "AEHR": "2026-05-31", "AXON": "2026-06-30",
    "8697.T": "2026-09-30", "CEG": "2026-06-30",
    "CPRT": "2026-07-31", "DG": "2026-08-01",
    "CVS": "2026-06-30", "ICE": "2026-06-30",
    "QDEL": "2026-06-30", "SPGI": "2026-06-30",
}


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def committed_at(path: Path) -> str:
    try:
        value = subprocess.run(
            ["git", "log", "-1", "--format=%cI", "--", str(path.relative_to(ROOT))],
            cwd=ROOT, text=True, capture_output=True, check=True).stdout.strip()
        return value or "2026-08-10T00:00:00Z"
    except (OSError, subprocess.CalledProcessError):
        return "2026-08-10T00:00:00Z"


def frozen_method(contract: dict, component_id: str) -> str:
    for component in contract.get("economic_ownership_map") or []:
        if isinstance(component, dict) and component.get("component_id") == component_id:
            return str(component.get("method") or "unknown")
    return "monitoring" if component_id == "monitoring" else "unknown"


def dates(ticker: str, spec: dict) -> tuple[str | None, str | None, str | None]:
    if spec.get("untestable"):
        return None, None, None
    deadline = date.fromisoformat(str(spec["due"])[:10])
    observable = deadline - timedelta(days=60)
    if ticker == "WHK":
        measurement = date(2026, 6, 30) if deadline.year == 2026 else date(2026, 12, 31)
    else:
        measurement = date.fromisoformat(MEASUREMENT_END[ticker])
    return measurement.isoformat(), observable.isoformat(), deadline.isoformat()


def migrate(path: Path) -> bool:
    doc = read(path)
    ticker = str(doc.get("ticker") or path.parents[1].name).upper()
    if all(is_v2_spec(spec) and all(spec.get(field) for field in
           ("author", "model_id", "prompt_version"))
           for spec in doc.get("specs") or []):
        return False
    contract_path = path.with_name("valuation_contract.json")
    contract = read(contract_path)
    route_path = path.with_name("valuation_route.json")
    route = read(route_path) if route_path.exists() else {}
    contract_hash = hashlib.sha256(contract_path.read_bytes()).hexdigest()
    authored_at = committed_at(path)
    migrated = []
    for old in doc.get("specs") or []:
        if is_v2_spec(old):
            migrated.append({
                **old,
                "author": old.get("author") or "legacy_unrecorded",
                "model_id": old.get("model_id") or "legacy_unrecorded",
                "prompt_version": old.get("prompt_version") or "legacy_unrecorded",
            })
            continue
        measurement, observable, deadline = dates(ticker, old)
        identity_payload = json.dumps({"ticker": ticker, **old}, sort_keys=True)
        spec_id = f"{ticker.lower().replace('.', '-')}-{hashlib.sha256(identity_payload.encode()).hexdigest()[:20]}"
        migrated.append({
            "spec_id": spec_id,
            "spec_revision": 1,
            "authored_at": authored_at,
            "analysis_run_id": "legacy-migration-2026-08-12",
            "author": "legacy_unrecorded",
            "model_id": "legacy_unrecorded",
            "prompt_version": "legacy_unrecorded",
            "contract_hash": contract_hash,
            "method_id": frozen_method(contract, str(old.get("component_id") or "")),
            "power_zone": str(route.get("profile_id") or "unclassified"),
            **{key: old.get(key) for key in (
                "component_id", "metric", "comparator", "threshold", "unit")},
            "measurement_period_end": measurement,
            "observable_after": observable,
            "resolution_deadline": deadline,
            "source_hint": old.get("source_hint"),
            "probability_fires": None,
            "calibration_eligible": False,
            "severity": 3,
            "derived_from": old.get("derived_from"),
            "untestable": bool(old.get("untestable")),
            "rationale": old.get("rationale"),
            "supersedes_spec_id": None,
            "migration_note": "Legacy forecast; ex-ante probability was not recorded and must not be backfilled.",
        })
    doc["schema_version"] = "2.0"
    doc["specs"] = migrated
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return True


def main() -> int:
    changed = []
    for path in sorted(ROOT.glob("*/research/falsifier_specs.json")):
        if migrate(path):
            changed.append(str(path.relative_to(ROOT)))
    print(json.dumps({"migrated": changed, "count": len(changed)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
