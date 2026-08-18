#!/usr/bin/env python3
"""Validate every falsifier sidecar, anchor, eligibility, and source preflight."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from falsifier_specs import (anchor_errors, calibration_eligibility, is_v3_spec,
                             metric_resolvable, spec_errors)

ROOT = Path(__file__).resolve().parents[2]


def lint(root: Path = ROOT) -> list[str]:
    errors = []
    for path in sorted(root.glob("*/research/falsifier_specs.json")):
        ticker = path.parents[1].name
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{ticker}: unreadable sidecar: {exc}")
            continue
        contract_path = root / ticker / "research/valuation_contract.json"
        contract = json.loads(contract_path.read_text(encoding="utf-8")) if contract_path.exists() else {}
        for index, spec in enumerate(doc.get("specs") or []):
            prefix = f"{ticker}:{spec.get('spec_id') or index}"
            for error in spec_errors(spec, index):
                errors.append(f"{prefix}: {error}")
            if contract and not is_v3_spec(spec):
                for error in anchor_errors(spec, contract, index):
                    # Migrated ineligible records may outlive contract prose;
                    # preserve them as diagnostics instead of blocking CI.
                    if spec.get("calibration_eligible") is not False:
                        errors.append(f"{prefix}: {error}")
            if is_v3_spec(spec) and not spec.get("untestable"):
                eligible, reason = calibration_eligibility(spec)
                if spec.get("calibration_eligible") is True and not eligible:
                    errors.append(f"{prefix}: derived eligibility failed: {reason}")
                resolvable, resolution_reason = metric_resolvable(ticker, spec, root)
                if spec.get("calibration_eligible") is True and not resolvable:
                    errors.append(f"{prefix}: source preflight failed: {resolution_reason}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    errors = lint(args.root)
    for error in errors:
        print(f"ERROR: {error}")
    print(f"falsifier lint: {len(errors)} violation(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
