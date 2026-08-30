#!/usr/bin/env python3
"""Audit the approved valuation method registry against the local research library."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "_system" / "reference" / "valuation_method_registry.json"
OUTPUT = ROOT / "dashboard" / "data" / "valuation_method_registry.json"
REQUIRED = {
    "method_id", "version", "status", "label", "power_zones", "economic_claim",
    "required_inputs", "equation", "allowed_judgments", "scenario_rule",
    "double_counting_exclusions", "failure_modes", "corroborating_methods", "sources",
    "output_basis",
}

OUTPUT_BASES = {"present_value_today", "future_payoff", "forward_cashflow_schedule"}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> dict:
    doc = json.loads(REGISTRY.read_text(encoding="utf-8"))
    errors, sources, ids = [], [], set()
    for card in doc.get("method_cards") or []:
        missing = sorted(REQUIRED - set(card))
        if missing: errors.append(f"{card.get('method_id')}: missing {', '.join(missing)}")
        key = f"{card.get('method_id')}@{card.get('version')}"
        if key in ids: errors.append(f"duplicate method card {key}")
        ids.add(key)
        if card.get("status") not in {"candidate", "approved", "deprecated"}:
            errors.append(f"{key}: invalid status")
        if card.get("output_basis") not in OUTPUT_BASES:
            errors.append(f"{key}: invalid output_basis {card.get('output_basis')!r}")
        for source in card.get("sources") or []:
            path = ROOT / str(source.get("ref") or "")
            present = path.is_file()
            sources.append({"method": key, **source, "present": present, "sha256": sha(path) if present else None})
            if card.get("status") == "approved" and not present:
                errors.append(f"{key}: approved source missing: {source.get('ref')}")
    result = {
        **doc,
        "audit": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "method_count": len(doc.get("method_cards") or []),
            "approved_count": sum(1 for x in doc.get("method_cards") or [] if x.get("status") == "approved"),
            "source_count": len(sources),
            "source_records": sources,
            "errors": sorted(set(errors)),
            "status": "pass" if not errors else "blocked",
        },
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = build()
    if not args.check:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(OUTPUT.relative_to(ROOT).as_posix())
    for error in result["audit"]["errors"]: print(error)
    return 1 if result["audit"]["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
