#!/usr/bin/env python3
"""Lint deep dives for tickers touched in a PR diff.

Usage:
  python _system/scripts/lint_pr_research.py
  python _system/scripts/lint_pr_research.py --base origin/main
  python _system/scripts/lint_pr_research.py --base origin/main --name-only-file /tmp/pr-files.txt
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
PY = sys.executable
TICKER_RE = re.compile(r"^([^/]+)/research/")

MECHANICAL_EVIDENCE = re.compile(r"^[^/]+/research/evidence/thematic_context_\d{4}-\d{2}-\d{2}\.md$")
MECHANICAL_INSIDER = re.compile(r"^[^/]+/research/evidence/insider_signal_\d{4}-\d{2}-\d{2}\.md$")
MECHANICAL_MI = re.compile(r"^[^/]+/research/market_inputs\.json$")

sys.path.insert(0, str(SCRIPTS))
from marvin_pipeline_common import has_evidence_refresh_config  # noqa: E402


def _normalize_paths(lines: list[str]) -> list[str]:
    return [line.strip().replace("\\", "/") for line in lines if line.strip()]


def read_name_only_file(path: Path) -> list[str]:
    return _normalize_paths(path.read_text(encoding="utf-8").splitlines())


def git_diff_names(base: str) -> list[str]:
    """Return paths changed on this branch vs merge-base with ``base``.

    Never fall back to a two-dot compare against the tip of ``base``: on shallow
    CI clones that incorrectly includes main-only commits (e.g. authorize waves)
    and poisons unrelated PRs with foreign tickers.
    """
    r = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", f"{base}...HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if r.returncode == 0:
        return _normalize_paths((r.stdout or "").splitlines())

    mb = subprocess.run(
        ["git", "merge-base", base, "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if mb.returncode != 0 or not (mb.stdout or "").strip():
        print(
            "ERROR: cannot compute merge-base for PR lint; "
            "deepen git history or pass --name-only-file from the GitHub PR file list.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    merge_base = mb.stdout.strip()
    r2 = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", f"{merge_base}...HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if r2.returncode != 0:
        print(
            f"ERROR: git diff failed for {merge_base}...HEAD: {(r2.stderr or r2.stdout or '').strip()}",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return _normalize_paths((r2.stdout or "").splitlines())


def tickers_from_paths(paths: list[str]) -> list[str]:
    tickers: set[str] = set()
    for line in paths:
        if "/research/" not in line:
            continue
        m = TICKER_RE.match(line)
        if m and not m.group(1).startswith(("_", ".")):
            tickers.add(m.group(1))
    return sorted(tickers)


def tickers_from_diff(base: str) -> list[str]:
    return tickers_from_paths(git_diff_names(base))


def valuation_overlay_only_diff(ticker: str, base: str) -> bool:
    vp = f"{ticker}/research/valuation.json"
    r = subprocess.run(
        ["git", "show", f"{base}:{vp}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        return False
    try:
        old = json.loads(r.stdout)
    except json.JSONDecodeError:
        return False
    new_path = ROOT / ticker / "research" / "valuation.json"
    if not new_path.exists():
        return False
    try:
        new = json.loads(new_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    forbidden = ("inputs", "scenarios", "implied_return", "results", "segment_build", "nav_overlay")
    for key in forbidden:
        if old.get(key) != new.get(key):
            return False
    return old.get("context_overlay") != new.get("context_overlay")


def valuation_insider_only_diff(ticker: str, base: str) -> bool:
    vp = f"{ticker}/research/valuation.json"
    r2 = subprocess.run(
        ["git", "show", f"{base}:{vp}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if r2.returncode != 0:
        return False
    try:
        old = json.loads(r2.stdout)
        new = json.loads((ROOT / ticker / "research" / "valuation.json").read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    forbidden = ("inputs", "scenarios", "implied_return", "results", "segment_build", "nav_overlay")
    for key in forbidden:
        if old.get(key) != new.get(key):
            return False
    return old.get("insider_signal") != new.get("insider_signal")


def _is_committee_side_path(path: str) -> bool:
    return "/research/committee_work/" in path or path.endswith("/research/valuation_workbench.json")


def _is_derived_path(path: str) -> bool:
    return path.endswith("/research/lenses.json")


def _is_mechanical_path(path: str, ticker: str, base: str) -> bool:
    if path.endswith("/research/valuation.json"):
        return valuation_overlay_only_diff(ticker, base) or valuation_insider_only_diff(ticker, base)
    if path.endswith("/research/authorized_evidence.json"):
        # Queue authorize packets / contract_backfill stubs — not narrative research.
        return True
    if MECHANICAL_EVIDENCE.match(path) or MECHANICAL_INSIDER.match(path) or MECHANICAL_MI.match(path):
        return True
    if "/research/evidence/filing_facts_" in path and path.endswith(".json"):
        return True
    return False


def research_diff_kind(ticker: str, paths: list[str], base: str) -> str:
    """Per ticker: derived_only | mechanical_only | committee_only | narrative | mixed."""
    tk_paths = [p for p in paths if p.startswith(f"{ticker}/research/")]
    if not tk_paths:
        return "narrative"
    if all(_is_derived_path(p) for p in tk_paths):
        return "derived_only"
    if all(_is_committee_side_path(p) for p in tk_paths):
        return "committee_only"
    non_mechanical = [p for p in tk_paths if not _is_mechanical_path(p, ticker, base)]
    if not non_mechanical:
        return "mechanical_only"
    val_only = all(p.endswith("/research/valuation.json") for p in non_mechanical)
    if val_only and (valuation_overlay_only_diff(ticker, base) or valuation_insider_only_diff(ticker, base)):
        return "mechanical_only"
    if any(p.endswith(".md") for p in non_mechanical):
        return "mixed" if any(not p.endswith(".md") for p in non_mechanical) else "narrative"
    return "mixed"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="origin/main", help="Git base ref for diff")
    parser.add_argument(
        "--name-only-file",
        default="",
        help="Optional file of changed paths (one per line). Prefer the GitHub PR file list in CI.",
    )
    args = parser.parse_args()

    if args.name_only_file:
        paths = read_name_only_file(Path(args.name_only_file))
        print(f"Using --name-only-file ({len(paths)} path(s))")
    else:
        paths = git_diff_names(args.base)
    tickers = tickers_from_paths(paths)
    if not tickers:
        print("SKIP: no ticker research paths in diff")
        return 0

    failed = 0
    for ticker in tickers:
        dive = ROOT / ticker / "research"
        if not dive.is_dir():
            continue
        kind = research_diff_kind(ticker, paths, args.base)
        print(f"\n=== lint {ticker} ({kind}) ===")
        if kind == "derived_only":
            lenses_path = dive / "lenses.json"
            try:
                lenses = json.loads(lenses_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                print(f"FAIL {ticker}: invalid lenses.json: {exc}")
                failed += 1
                continue
            required = {
                "ticker": str,
                "lenses": list,
                "valuation_blend": dict,
                "consensus": dict,
            }
            errors = [
                key
                for key, expected in required.items()
                if not isinstance(lenses.get(key), expected)
            ]
            if errors:
                print(f"FAIL {ticker}: lenses.json missing/invalid: {', '.join(errors)}")
                failed += 1
            continue
        if not list(dive.glob("deep_dive_*.md")):
            print(f"SKIP {ticker}: no deep dive")
            continue
        if kind == "committee_only":
            print(f"SKIP {ticker}: committee_work-only diff")
            continue
        if kind == "mechanical_only":
            val_path = ROOT / ticker / "research" / "valuation.json"
            val: dict = {}
            if val_path.exists():
                try:
                    val = json.loads(val_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    val = {}
            if val.get("context_overlay"):
                r = subprocess.run(
                    [PY, str(SCRIPTS / "lint_context_overlay.py"), ticker],
                    cwd=ROOT,
                )
                if r.returncode != 0:
                    failed += 1
            if val.get("insider_signal"):
                r = subprocess.run(
                    [PY, str(SCRIPTS / "lint_insider_signal.py"), ticker],
                    cwd=ROOT,
                )
                if r.returncode != 0:
                    failed += 1
            continue
        for script, extra in (
            ("lint_deep_dive.py", ["--milly"]),
            ("lint_adversarial.py", ["--consistency-only"]),
        ):
            cmd = [PY, str(SCRIPTS / script), ticker, *extra]
            r = subprocess.run(cmd, cwd=ROOT)
            if r.returncode != 0:
                failed += 1
        val_path = ROOT / ticker / "research" / "valuation.json"
        if val_path.exists():
            try:
                val = json.loads(val_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                val = {}
            if has_evidence_refresh_config(val) or val.get("valuation_mode") == "optionality":
                r = subprocess.run(
                    [PY, str(SCRIPTS / "check_evidence_completeness.py"), ticker],
                    cwd=ROOT,
                )
                if r.returncode != 0:
                    failed += 1

    if failed:
        print(f"\nFAIL: {failed} lint invocation(s)")
        return 1
    print(f"\nOK: {len(tickers)} ticker(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
