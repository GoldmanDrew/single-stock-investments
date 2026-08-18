#!/usr/bin/env python3
"""Fail a lane only for the graph invariants that lane owns."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def validate(path: Path, wanted: set[str]) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = {str(row.get("id")): row for row in payload.get("invariants") or []}
    failures = []
    for ident in sorted(wanted):
        row = rows.get(ident)
        if row is None:
            failures.append(f"{ident}: absent from invariant report")
        elif row.get("severity") == "hard" and int(row.get("count") or 0):
            failures.append(f"{ident}: {row['count']} hard violation(s)")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ids", nargs="+")
    parser.add_argument("--report", type=Path,
                        default=ROOT / "_system/graph/invariants.json")
    args = parser.parse_args()
    failures = validate(args.report, set(args.ids))
    for failure in failures:
        print(failure)
    print(f"invariant subset: {len(failures)} failure(s); ids={','.join(args.ids)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
