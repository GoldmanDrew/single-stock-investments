"""No workflow may ask a ticker-less checkout for a ticker rebuild.

This exact mismatch broke two scheduled lanes and neither was noticed for weeks:

  letter-backfill.yml  `pages`  profile -> build_dashboard_data.py  (4 runs, 2 weeks)
  darwin-refresh.yml   `darwin` profile -> build_dashboard_data.py  (12 days)

build_dashboard_data.py walks the per-ticker trees to compute pdf_count, readme,
research_dir, sec_filings and friends. A checkout without those trees makes all
of them compute to zero, and the script's clobber guard then refuses to write --
correctly, because the alternative is shipping 833 tickers with gutted infra
stats to the live dashboard.

That guard is the last line, not the first. It fires at the END of a long rebuild
chain (letter-backfill spent ~43 minutes reaching it, 40 of them inside
build_superinvestor_insights.py) to report a precondition knowable from the
workflow file alone. This test reads it from the workflow file alone.

**"Sparse" is not the test.** `marvin-pick` is sparse and ships 1,666 ticker
research paths; `news` ships 833. Those workflows rebuild fine, and a test that
flagged them would be a false positive that someone would rightly delete. The
question is only ever whether the profile actually yields ticker trees, so this
asks ci_sparse_checkout_paths.py -- the same source of truth CI uses -- rather
than hardcoding a list that would rot the moment a profile changed.
"""
from __future__ import annotations

import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = ROOT / ".github" / "workflows"
PATHS_SCRIPT = ROOT / "_system/scripts/ci_sparse_checkout_paths.py"

# ci_checkout_workspace.sh disables sparse checkout entirely for these, so the
# whole tree — every ticker — is present.
SPARSE_DISABLED = {"full", "history"}

# Builders that walk the per-ticker trees and therefore need them present.
TREE_WALKING_BUILDERS = ("build_dashboard_data.py",)

CHECKOUT = re.compile(r"ci_checkout_workspace\.sh\s+([a-z-]+)")
TICKER_RESEARCH = re.compile(r"^[A-Za-z0-9.\-]+/research")


@lru_cache(maxsize=None)
def provides_ticker_trees(profile: str) -> bool:
    if profile in SPARSE_DISABLED:
        return True
    result = subprocess.run(
        [sys.executable, str(PATHS_SCRIPT), profile],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )
    if result.returncode != 0:
        return False
    return any(TICKER_RESEARCH.match(line.strip()) for line in result.stdout.splitlines())


def _jobs():
    for path in sorted(WORKFLOWS.glob("*.yml")):
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:  # a malformed workflow is its own failure
            pytest.fail(f"{path.name}: {exc}")
        if not isinstance(doc, dict):
            continue
        # PyYAML parses the bare key `on:` as the boolean True.
        triggers = doc.get("on") or doc.get(True) or {}
        for name, job in (doc.get("jobs") or {}).items():
            if isinstance(job, dict):
                yield path, name, job, triggers


def _run_text(job) -> str:
    return "\n".join(
        str(step["run"]) for step in (job.get("steps") or [])
        if isinstance(step, dict) and step.get("run")
    )


def test_no_ticker_less_checkout_runs_a_ticker_tree_builder():
    offenders = []
    for path, job_name, job, triggers in _jobs():
        text = _run_text(job)
        profiles = set(CHECKOUT.findall(text))
        if not profiles or any(provides_ticker_trees(p) for p in profiles):
            continue

        # Manual-only workflows are effectively parked (darwin-refresh.yml is
        # disabled this way). Exempt — and re-adding a schedule or push trigger
        # brings them straight back under this test, which is the point: you
        # cannot quietly resume a lane that still carries the mismatch.
        if set(triggers) <= {"workflow_dispatch", "repository_dispatch"}:
            continue

        # A call guarded on ticker trees actually being present is the
        # sanctioned fix (see letter-backfill.yml).
        if re.search(r"TICKER_TREES", text):
            continue

        for builder in TREE_WALKING_BUILDERS:
            if any(builder in line and not line.strip().startswith("#")
                   for line in text.splitlines()):
                offenders.append(
                    f"{path.name}:{job_name} checks out {sorted(profiles)} "
                    f"(no ticker trees) then runs {builder}"
                )
                break

    assert not offenders, (
        "ticker-less checkout paired with a ticker-tree builder:\n  "
        + "\n  ".join(offenders)
        + "\n\nUse `full`, or a profile whose sparse paths include ticker trees, "
          "or guard the call on TICKER_TREES, or drop the builder and let "
          "data-pipeline.yml intake-full rebuild the payload nightly."
    )


def test_the_profiles_this_test_reasons_about_still_behave_as_assumed():
    """If a profile changes shape this test can go quietly blind, so pin both sides."""
    assert provides_ticker_trees("full"), "`full` must present the whole tree"
    assert provides_ticker_trees("marvin-pick"), (
        "`marvin-pick` used to ship 1,666 ticker research paths; if that stopped, "
        "ls-algo-universe.yml is now broken the same way darwin was"
    )
    assert not provides_ticker_trees("pages"), (
        "`pages` used to be ticker-less; if it now ships tickers this test has "
        "lost the case it was written for"
    )
