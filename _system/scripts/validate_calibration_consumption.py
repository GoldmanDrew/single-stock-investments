#!/usr/bin/env python3
"""Validate that analyses consume only immutable, released calibration."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def validate(root: Path = ROOT) -> list[str]:
    brief_path = root / "_system/research/calibration_brief.json"
    brief = json.loads(brief_path.read_text(encoding="utf-8")) if brief_path.exists() else {}
    active = brief.get("release_hash")
    errors = []
    for path in sorted((root / "_system/data/runs").glob("**/*calibration_receipt*.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        if row.get("challenge_applied") and not row.get("calibration_release_hash"):
            errors.append(f"{path.relative_to(root)}: challenge lacks release hash")
        if row.get("calibration_release_hash") and row.get("calibration_release_hash") != active:
            release = root / "_system/research/calibration_releases" / f"{row['calibration_release_hash']}.json"
            if not release.exists():
                errors.append(f"{path.relative_to(root)}: unknown calibration release")
        if row.get("analysis_changed") and not row.get("challenge_applied"):
            errors.append(f"{path.relative_to(root)}: analysis changed without named challenge")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    errors = validate(args.root)
    for error in errors:
        print(f"ERROR: {error}")
    print(f"calibration consumption: {len(errors)} violation(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
