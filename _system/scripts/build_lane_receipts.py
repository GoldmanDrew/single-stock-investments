#!/usr/bin/env python3
"""Refresh lane-health receipts from successful GitHub workflow runs."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def build(root: Path = ROOT, repository: str | None = None) -> dict:
    config = json.loads((root / "_system/graph/graph_sources.json").read_text(encoding="utf-8"))
    repository = repository or os.environ.get("GITHUB_REPOSITORY")
    written, missing = [], []
    for lane in config.get("lanes") or []:
        workflow = lane.get("workflow_file")
        if not workflow:
            continue
        command = ["gh", "run", "list", "--workflow", workflow, "--status", "success",
                   "--limit", "1", "--json", "databaseId,createdAt,updatedAt,headSha,url,conclusion"]
        if repository:
            command.extend(["--repo", repository])
        result = subprocess.run(command, cwd=root, text=True, capture_output=True, check=False)
        try:
            rows = json.loads(result.stdout) if result.returncode == 0 else []
        except json.JSONDecodeError:
            rows = []
        if not rows:
            missing.append({"lane": lane["name"], "workflow": workflow,
                            "error": result.stderr.strip()[:300]})
            continue
        row = rows[0]
        payload = {
            "schema_version": "1.0", "lane": lane["name"], "workflow_file": workflow,
            "last_success_at": row.get("updatedAt") or row.get("createdAt"),
            "run_id": row.get("databaseId"), "head_sha": row.get("headSha"),
            "url": row.get("url"), "conclusion": row.get("conclusion"),
        }
        target = root / "_system/data/lane_receipts" / f"{lane['name']}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        written.append(payload)
    return {"written": written, "missing": missing}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--repository")
    args = parser.parse_args()
    result = build(args.root, args.repository)
    print(json.dumps({"written": len(result["written"]), "missing": result["missing"]}, indent=2))
    return 1 if result["missing"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
