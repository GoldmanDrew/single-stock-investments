#!/usr/bin/env python3
"""Build a Cloudflare Pages artifact from the sharded dashboard payload."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = ROOT / "dashboard"
DEFAULT_OUTPUT = ROOT / "_cf_project" / "site"
MAX_FILE_BYTES = 20 * 1024 * 1024
SKIP_DIRS = {"oauth-proxy", "functions", "cloudflare"}
SKIP_SUFFIXES = {".parquet", ".arrow"}
PRIVATE_STATIC_PATHS = {
    "data/sleeves_drew.json",
    "data/sleeves_michael.json",
}
PRIVATE_STATIC_PREFIXES = ("data/portfolio/", "data/account/")


def _private_static_path(relative: str) -> bool:
    return relative in PRIVATE_STATIC_PATHS or (
        relative.startswith("data/sleeves_") and relative.endswith(".json")
    ) or relative.startswith(PRIVATE_STATIC_PREFIXES)


ASSET_QUERY_RE = re.compile(
    r'(?P<attr>(?:src|href)=")(?P<file>[A-Za-z0-9._/-]+\.(?:js|css))\?v=(?P<ver>[^"]*)"'
)


def stamp_asset_versions(output: Path) -> int:
    """Rewrite ``?v=`` on local js/css to a hash of each file's own contents.

    The versions were hand-written, so they only changed when someone
    remembered. A fix to insights-viz.js shipped under a stamp last touched a
    week earlier, and because browsers cache on the full URL including the
    query, returning visitors kept the old file and the fix looked broken.
    Hashing the file means the stamp changes exactly when the asset does — and
    never when it doesn't, so caching still works.
    """
    index = output / "index.html"
    if not index.is_file():
        return 0
    html = index.read_text(encoding="utf-8")
    stamped = 0

    def replace(match: re.Match) -> str:
        nonlocal stamped
        asset = output / match.group("file")
        if not asset.is_file():
            # Leave unknown/remote assets exactly as they were.
            return match.group(0)
        digest = hashlib.sha256(asset.read_bytes()).hexdigest()[:12]
        stamped += 1
        return f'{match.group("attr")}{match.group("file")}?v={digest}"'

    updated = ASSET_QUERY_RE.sub(replace, html)
    if updated != html:
        index.write_text(updated, encoding="utf-8")
    return stamped


def _inside_workspace(path: Path) -> bool:
    try:
        path.resolve().relative_to(ROOT.resolve())
        return True
    except ValueError:
        return False


def _clean_output(output: Path) -> None:
    resolved = output.resolve()
    if not _inside_workspace(resolved) or resolved in {ROOT.resolve(), DEFAULT_SOURCE.resolve()}:
        raise ValueError(f"refusing to clean unsafe output path: {resolved}")
    if resolved.exists():
        shutil.rmtree(resolved)
    resolved.mkdir(parents=True, exist_ok=True)


def build(source: Path, output: Path, max_file_bytes: int = MAX_FILE_BYTES) -> dict:
    source = source.resolve()
    output = output.resolve()
    if not (source / "index.html").is_file():
        raise FileNotFoundError(f"missing dashboard index: {source / 'index.html'}")
    _clean_output(output)

    included: list[str] = []
    excluded: list[dict] = []
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(source)
        rel_posix = rel.as_posix()
        if any(part in SKIP_DIRS for part in rel.parts):
            excluded.append({"path": rel_posix, "reason": "deployment-control directory"})
            continue
        if _private_static_path(rel_posix):
            excluded.append({"path": rel_posix, "reason": "private account artifact"})
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            excluded.append({"path": rel.as_posix(), "reason": "unsupported large-data format"})
            continue
        size = path.stat().st_size
        if size >= max_file_bytes:
            excluded.append({"path": rel.as_posix(), "reason": f"{size} bytes exceeds artifact limit"})
            continue
        target = output / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        included.append(rel_posix)

    stamped = stamp_asset_versions(output)

    core_path = output / "data" / "core.json"
    manifest_path = output / "data" / "insights" / "manifest.json"
    if not core_path.is_file():
        raise RuntimeError("Cloudflare artifact is missing data/core.json")
    if not manifest_path.is_file():
        raise RuntimeError("Cloudflare artifact is missing data/insights/manifest.json")
    core = json.loads(core_path.read_text(encoding="utf-8"))
    ticker_count = len(core.get("tickers") or [])
    shard_count = len(list((output / "data" / "tickers").glob("*.json")))
    if shard_count < ticker_count:
        raise RuntimeError(f"Cloudflare artifact has {shard_count} ticker shards for {ticker_count} rows")
    leaked = [path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file() and _private_static_path(path.relative_to(output).as_posix())]
    if leaked:
        raise RuntimeError(f"Cloudflare artifact contains private account files: {sorted(leaked)}")

    headers = (
        "/*\n"
        "  X-Content-Type-Options: nosniff\n"
        "  Referrer-Policy: strict-origin-when-cross-origin\n"
        "  Permissions-Policy: camera=(), microphone=(), geolocation=()\n"
        "\n"
        "/data/*\n"
        "  Cache-Control: public, max-age=60, stale-while-revalidate=300\n"
    )
    (output / "_headers").write_text(headers, encoding="utf-8")

    report = {
        "source": source.as_posix(),
        "output": output.as_posix(),
        "ticker_count": ticker_count,
        "ticker_shard_count": shard_count,
        "included_file_count": len(included),
        "excluded_file_count": len(excluded),
        "asset_versions_stamped": stamped,
        "private_static_paths": sorted(PRIVATE_STATIC_PATHS),
        "excluded": excluded,
    }
    (output / "cloudflare-artifact-manifest.json").write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Cloudflare Pages artifact: {len(included)} files, "
        f"{ticker_count} tickers, {len(excluded)} oversized/control files omitted, "
        f"{stamped} asset versions content-stamped"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-file-mb", type=float, default=20.0)
    args = parser.parse_args()
    build(args.source, args.output, int(args.max_file_mb * 1024 * 1024))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
