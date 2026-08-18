#!/usr/bin/env python3
"""Land remaining open cursor PRs onto local main with ticker-prefer-PR conflicts."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DAILY = ROOT / "_system" / "memory" / "daily"
JSONL = "_system/portfolio/research_events.jsonl"
MILLY = "_system/research/milly_log.md"

PRS = [
    (823, "COP"),
    (824, "DD"),
    (825, "DOC"),
    (826, "DVA"),
    (846, "AXON"),
    (848, "ALB"),
    (854, "ASML"),
    (855, "AVGO"),
    (856, "AMZN"),
    (859, "RIG"),
]


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if check and proc.returncode != 0:
        sys.stderr.write(proc.stderr or proc.stdout or "")
        raise subprocess.CalledProcessError(proc.returncode, cmd, proc.stdout, proc.stderr)
    return proc


def gh_json(args: list[str]) -> dict:
    return json.loads(run(["gh", *args]).stdout)


def latest_daily_log() -> Path | None:
    if not DAILY.is_dir():
        return None
    logs = sorted(DAILY.glob("*.md"), reverse=True)
    return logs[0] if logs else None


def git_show(ref: str, path: str) -> str | None:
    proc = run(["git", "show", f"{ref}:{path}"], check=False)
    if proc.returncode != 0:
        return None
    return proc.stdout


def extract_section(content: str, ticker: str) -> str | None:
    pattern = rf"(## {re.escape(ticker)} [^\n]+\n(?:.*?\n)*?)(?=## |\Z)"
    m = re.search(pattern, content, re.DOTALL)
    if not m:
        return None
    return m.group(1).rstrip() + "\n\n"


def lines_for_ticker(text: str, ticker: str, *, kind: str) -> list[str]:
    if not text:
        return []
    if kind == "jsonl":
        return [
            ln.strip()
            for ln in text.splitlines()
            if f'"ticker": "{ticker}"' in ln or f'"ticker":"{ticker}"' in ln
        ]
    return [ln.strip() for ln in text.splitlines() if f"| {ticker} |" in ln]


def restore_ticker_logs(
    ticker: str,
    *,
    daily_section: str | None,
    jsonl_lines: list[str],
    milly_lines: list[str],
) -> None:
    daily_path = latest_daily_log()
    if daily_path and daily_section:
        body = daily_path.read_text(encoding="utf-8")
        if f"## {ticker} " not in body:
            lines = body.splitlines(keepends=True)
            if lines:
                daily_path.write_text(
                    lines[0].rstrip() + "\n\n" + daily_section + "".join(lines[1:]),
                    encoding="utf-8",
                )
            else:
                daily_path.write_text(daily_section, encoding="utf-8")

    jsonl_path = ROOT / JSONL
    if jsonl_path.is_file() and jsonl_lines:
        body = jsonl_path.read_text(encoding="utf-8")
        missing = [ln for ln in jsonl_lines if ln not in body]
        if missing:
            jsonl_path.write_text(body.rstrip() + "\n" + "\n".join(missing) + "\n", encoding="utf-8")

    milly_path = ROOT / MILLY
    if milly_path.is_file() and milly_lines:
        body = milly_path.read_text(encoding="utf-8")
        missing = [ln for ln in milly_lines if ln not in body]
        if missing:
            milly_path.write_text(body.rstrip() + "\n" + "\n".join(missing) + "\n", encoding="utf-8")


def conflicted_files() -> list[str]:
    proc = run(["git", "diff", "--name-only", "--diff-filter=U"], check=False)
    return [ln.strip().replace("\\", "/") for ln in proc.stdout.splitlines() if ln.strip()]


def take_side(side: str, path: str) -> None:
    chk = run(["git", "checkout", f"--{side}", "--", path], check=False)
    if chk.returncode != 0:
        run(["git", "rm", "-f", "--", path], check=False)
        return
    run(["git", "add", "--", path], check=False)


def resolve_conflicts(ticker: str) -> None:
    prefix = f"{ticker}/"
    for path in conflicted_files():
        if path == prefix or path.startswith(prefix):
            take_side("theirs", path)
        else:
            take_side("ours", path)
    leftover = conflicted_files()
    if leftover:
        raise SystemExit(f"Unresolved after policy: {leftover}")


def merge_pr(number: int, ticker: str) -> None:
    data = gh_json(["pr", "view", str(number), "--json", "state,headRefName,title"])
    if data.get("state") != "OPEN":
        print(f"PR #{number} is {data.get('state')}; skip.")
        return
    head = data["headRefName"]
    print(f"\n=== Merging PR #{number} ({ticker}) from {head} ===")
    run(["git", "fetch", "origin", f"+{head}:refs/remotes/origin/{head}"])
    branch_ref = f"origin/{head}"
    daily_path = latest_daily_log()
    daily_rel = str(daily_path.relative_to(ROOT)).replace("\\", "/") if daily_path else None
    daily_section = None
    if daily_rel:
        daily_orig = git_show(branch_ref, daily_rel)
        if daily_orig:
            daily_section = extract_section(daily_orig, ticker)
    jsonl_lines = lines_for_ticker(git_show(branch_ref, JSONL) or "", ticker, kind="jsonl")
    milly_lines = lines_for_ticker(git_show(branch_ref, MILLY) or "", ticker, kind="milly")

    merge = run(
        [
            "git",
            "merge",
            "--no-edit",
            "-m",
            f"Merge pull request #{number} from magis-capital-partners/{head}",
            branch_ref,
        ],
        check=False,
    )
    if merge.returncode != 0:
        if not (ROOT / ".git" / "MERGE_HEAD").exists():
            sys.stderr.write(merge.stderr or merge.stdout or "")
            raise SystemExit(merge.returncode)
        print(f"Conflicts in #{number}; preferring {ticker}/ from PR, main elsewhere.")
        resolve_conflicts(ticker)
        restore_ticker_logs(
            ticker,
            daily_section=daily_section,
            jsonl_lines=jsonl_lines,
            milly_lines=milly_lines,
        )
        run(["git", "add", "-A"])
        run(
            [
                "git",
                "commit",
                "--no-edit",
                "-m",
                f"Merge pull request #{number} from magis-capital-partners/{head}",
            ]
        )
    else:
        restore_ticker_logs(
            ticker,
            daily_section=daily_section,
            jsonl_lines=jsonl_lines,
            milly_lines=milly_lines,
        )
        status = run(["git", "status", "--porcelain"], check=False)
        if status.stdout.strip():
            run(["git", "add", "-A"])
            run(["git", "commit", "-m", f"fix: restore {ticker} log rows after merging #{number}"])
    print(f"Landed PR #{number} ({ticker})")


def main() -> None:
    branch = run(["git", "branch", "--show-current"]).stdout.strip()
    if branch != "main":
        raise SystemExit(f"Must run on main (on {branch})")
    run(["git", "fetch", "origin", "main"])
    pull = run(["git", "merge", "--ff-only", "origin/main"], check=False)
    if pull.returncode != 0:
        raise SystemExit("local main is not a fast-forward of origin/main")
    for number, ticker in PRS:
        merge_pr(number, ticker)
    print("\nAll listed PRs processed.")


if __name__ == "__main__":
    main()
