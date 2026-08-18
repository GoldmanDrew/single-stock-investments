#!/usr/bin/env python3
"""Fail closed when a deploy artifact contains portfolio data or broker identifiers."""
from __future__ import annotations

import argparse
import os
import re
from pathlib import Path


ACCOUNT_PATTERN = re.compile(rb"\bDU\d{6,10}\b", re.IGNORECASE)
FORBIDDEN_RELATIVE_PATHS = {
    "data/sleeves_drew.json",
    "data/sleeves_michael.json",
    "data/portfolio.json",
    "data/account_snapshot.json",
}
TEXT_SUFFIXES = {".html", ".js", ".css", ".json", ".jsonl", ".md", ".txt", ".xml", ".csv"}


def validate(root: Path, explicit_identifiers: tuple[str, ...] = ()) -> list[str]:
    root = root.resolve()
    failures: list[str] = []
    for relative in sorted(FORBIDDEN_RELATIVE_PATHS):
        if (root / relative).is_file():
            failures.append(f"forbidden private artifact: {relative}")
    for path in root.rglob("*.json"):
        relative = path.relative_to(root).as_posix()
        if relative.startswith("data/sleeves_") or relative.startswith("data/portfolio/") or relative.startswith("data/account/"):
            failures.append(f"forbidden private artifact pattern: {relative}")
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        content = path.read_bytes()
        if ACCOUNT_PATTERN.search(content):
            failures.append(f"broker account identifier: {path.relative_to(root).as_posix()}")
        text = content.decode("utf-8", errors="ignore")
        if any(identifier and identifier in text for identifier in explicit_identifiers):
            failures.append(f"configured private identifier: {path.relative_to(root).as_posix()}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, nargs="?", default=Path("_cf_project/site"))
    args = parser.parse_args()
    identifiers = tuple(value.strip() for value in os.environ.get("IBKR_ACCOUNT_IDS_FOR_SCAN", "").split(",") if value.strip())
    failures = validate(args.root, identifiers)
    if failures:
        for failure in failures:
            print(f"PRIVATE BOUNDARY FAILURE: {failure}")
        return 1
    print(f"Private boundary valid: {args.root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
