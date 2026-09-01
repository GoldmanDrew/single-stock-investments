#!/usr/bin/env python3
"""Compare Drive letter folders vs vault text extracts (coverage gate).

Vault commits ``.txt`` extracts only (PDFs are gitignored). This gate fails when
a recent Drive quarter folder has materially more PDFs than vault extracts, so
letter-backfill cannot silently drift again.

Usage:
  python _system/scripts/check_letter_drive_coverage.py --since-year 2026
  python _system/scripts/check_letter_drive_coverage.py --quarter 2026Q2 --fail-under 0.85
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))

from vault_paths import letters_root  # noqa: E402

LETTERS_ROOT = letters_root()
FILENAME_INDEX_PATH = ROOT / "_system" / "reference" / "document-store" / "drive_filename_index.json"
FOLDER_INDEX_PATH = ROOT / "_system" / "reference" / "document-store" / "drive_folder_index.json"

QUARTER_FOLDER_RE = re.compile(r"^Letters/(20\d{2})\s+Q([1-4])$", re.I)


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def quarter_id(year: str, q: str) -> str:
    return f"{year}Q{q}"


def drive_counts_by_quarter() -> dict[str, int]:
    folders = (load_json(FOLDER_INDEX_PATH).get("folders") or {})
    id_to_quarter: dict[str, str] = {}
    for path, meta in folders.items():
        m = QUARTER_FOLDER_RE.match(str(path).replace("\\", "/"))
        if not m:
            continue
        folder_id = (meta or {}).get("id")
        if folder_id:
            id_to_quarter[str(folder_id)] = quarter_id(m.group(1), m.group(2))

    counts: dict[str, int] = {}
    by_filename = load_json(FILENAME_INDEX_PATH).get("by_filename") or {}
    seen: set[str] = set()
    for _key, row in by_filename.items():
        if not isinstance(row, dict):
            continue
        # The filename index also contains folder sentinels and README files.
        # The denominator is explicitly Drive PDFs; counting those bookkeeping
        # files made a healthy 6/7 2026Q3 corpus appear to be 6/12 and kept the
        # entire letter lane permanently red.
        name = str(row.get("name") or _key)
        if Path(name).suffix.lower() != ".pdf":
            continue
        file_id = row.get("id")
        if not file_id or file_id in seen:
            continue
        seen.add(file_id)
        for parent in row.get("parents") or []:
            q = id_to_quarter.get(str(parent))
            if q:
                counts[q] = counts.get(q, 0) + 1
                break
    return counts


def vault_counts_by_quarter() -> dict[str, int]:
    counts: dict[str, int] = {}
    if not LETTERS_ROOT.exists():
        return counts
    for qdir in LETTERS_ROOT.iterdir():
        if not qdir.is_dir():
            continue
        name = qdir.name.upper()
        if not re.fullmatch(r"20\d{2}Q[1-4]", name):
            continue
        n = 0
        for txt in qdir.glob("*.txt"):
            try:
                if len(txt.read_text(encoding="utf-8", errors="ignore").strip()) >= 50:
                    n += 1
            except OSError:
                continue
        counts[name] = n
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Gate Drive letter coverage vs vault extracts")
    parser.add_argument("--since-year", type=int, help="Only check quarters from this year onward")
    parser.add_argument("--quarter", help="Single quarter id e.g. 2026Q2")
    parser.add_argument(
        "--fail-under",
        type=float,
        default=0.85,
        help="Fail when vault_extracts/drive_pdfs is below this ratio (default 0.85)",
    )
    parser.add_argument(
        "--max-missing",
        type=int,
        default=25,
        help="Also fail when absolute missing count exceeds this (default 25)",
    )
    args = parser.parse_args()

    drive = drive_counts_by_quarter()
    vault = vault_counts_by_quarter()
    quarters = sorted(set(drive) | set(vault))
    if args.quarter:
        quarters = [args.quarter.upper()]
    elif args.since_year:
        quarters = [q for q in quarters if int(q[:4]) >= args.since_year]

    if not quarters:
        print("No quarters to check (empty Drive/vault indexes for filter).")
        return 0

    print("quarter  drive  vault  ratio  missing")
    failures: list[str] = []
    for q in quarters:
        d = int(drive.get(q, 0))
        v = int(vault.get(q, 0))
        ratio = (v / d) if d else 1.0
        missing = max(0, d - v)
        flag = ""
        if d > 0 and (ratio < args.fail_under or missing > args.max_missing):
            flag = " FAIL"
            failures.append(
                f"{q}: vault={v} drive={d} ratio={ratio:.2%} missing={missing}"
            )
        print(f"{q:8} {d:5}  {v:5}  {ratio:5.1%}  {missing:5}{flag}")

    index_meta = load_json(FILENAME_INDEX_PATH)
    print(
        f"\nDrive filename index generated_at={index_meta.get('generated_at') or 'unknown'} "
        f"pdf_count={index_meta.get('pdf_count')}"
    )
    print(f"Letters root: {LETTERS_ROOT}")

    if failures:
        print("\nCoverage gate failed:", file=sys.stderr)
        for line in failures:
            print(f"  {line}", file=sys.stderr)
        print(
            "Re-run letter-backfill with --since-year / --quarter, then rebuild insights.",
            file=sys.stderr,
        )
        return 1

    print("\nOK: letter Drive coverage within threshold")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
