#!/usr/bin/env python3
"""Decide whether a completed upstream workflow produced dashboard-relevant work."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


IGNORED_DATA_PIPELINE_JOBS = {"decide", "pipeline-summary"}


def should_deploy(workflow_name: str, jobs: list[dict]) -> bool:
    if workflow_name != "Data Pipeline":
        return True

    active = [
        job
        for job in jobs
        if job.get("name") not in IGNORED_DATA_PIPELINE_JOBS
        and job.get("conclusion") == "success"
    ]
    if not active:
        # A workflow shape we do not recognize should not suppress a valid deploy.
        return True
    if {job.get("name") for job in active} != {"drive"}:
        return True

    drive_steps = active[0].get("steps") or []
    return any(
        step.get("name") == "Commit imported documents" and step.get("conclusion") == "success"
        for step in drive_steps
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow-name", required=True)
    parser.add_argument("--jobs-json", type=Path, required=True)
    parser.add_argument("--github-output", type=Path, default=None)
    args = parser.parse_args(argv)

    payload = json.loads(args.jobs_json.read_text(encoding="utf-8"))
    deploy = should_deploy(args.workflow_name, payload.get("jobs") or [])
    value = "true" if deploy else "false"
    print(f"should_deploy={value}")

    output_path = args.github_output or (
        Path(os.environ["GITHUB_OUTPUT"]) if os.environ.get("GITHUB_OUTPUT") else None
    )
    if output_path:
        with output_path.open("a", encoding="utf-8") as handle:
            handle.write(f"should_deploy={value}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
