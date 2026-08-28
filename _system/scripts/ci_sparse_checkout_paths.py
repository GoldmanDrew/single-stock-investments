#!/usr/bin/env python3
"""Emit git sparse-checkout paths for CI profiles (one path per line).

Profiles:
  news         — portfolio news ingest (holdings news JSON only)
  marvin-pick  — marvin_pick_ticker metadata (holdings research md/json)
  two-phase-watch — INV Accelsius cooling watch (eight ticker trees + INV shard)
  darwin       — Darwin refresh: no per-ticker trees (base paths only)
  dashboard    — deploy rebuild checkout (base paths only; alias of darwin)

Base paths (_system, .github, dashboard) are always set by
ci_checkout_workspace.sh; this script only emits extra ticker paths.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "_system" / "portfolio" / "registry.json"

# Soft cap for darwin/dashboard (must stay tiny — SPX-scale explosion caused 5h checkouts).
DARWIN_PATH_CAP = 200


def load_holdings() -> list[str]:
    if not REGISTRY_PATH.exists():
        return []
    reg = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return sorted((reg.get("holdings") or {}).keys())


def paths_for_profile(profile: str) -> list[str]:
    holdings = load_holdings()
    paths: list[str] = []

    if profile == "news":
        for ticker in holdings:
            paths.append(f"{ticker}/research/news")
        return paths

    if profile == "marvin-pick":
        for ticker in holdings:
            paths.extend(
                [
                    f"{ticker}/research/news",
                    f"{ticker}/research",
                    f"{ticker}/.onboard_status.json",
                    f"{ticker}/INDEX.csv",
                    f"{ticker}/_download_log.txt",
                    f"{ticker}/investor-documents/DOWNLOAD_MANIFEST.json",
                    f"{ticker}/investor-documents/TRANSCRIPT_MANIFEST.json",
                ]
            )
        return paths

    if profile == "two-phase-watch":
        tickers = ["NVDA", "AMD", "VRT", "JCI", "SMCI", "DELL", "HPE", "INV"]
        extra: list[str] = []
        for ticker in tickers:
            extra.extend(
                [
                    f"{ticker}/research",
                    f"{ticker}/investor-documents",
                ]
            )
        extra.append("dashboard/data/tickers/INV.json")
        return extra

    if profile == "marvin-forecast":
        ticker = os.environ.get("CI_FORECAST_TICKER", "").strip().upper()
        if not re.fullmatch(r"[A-Z0-9.^_-]+", ticker):
            raise SystemExit("CI_FORECAST_TICKER is required and must be a safe ticker")
        if ticker not in holdings:
            raise SystemExit(f"CI_FORECAST_TICKER is not in the portfolio registry: {ticker}")
        return [
            f"{ticker}/research",
            f"{ticker}/.onboard_status.json",
            f"{ticker}/investor-documents/DOWNLOAD_MANIFEST.json",
            f"{ticker}/investor-documents/TRANSCRIPT_MANIFEST.json",
        ]

    if profile in {"darwin", "dashboard"}:
        # Darwin + pages rebuild read market-data / portfolio / dashboard under
        # _system and dashboard/ (already in base sparse set). No ticker trees.
        return []

    raise SystemExit(f"Unknown sparse profile: {profile}")


def main() -> None:
    args = [a for a in sys.argv[1:] if a]
    count_only = False
    if args and args[0] == "--count":
        count_only = True
        args = args[1:]
    if len(args) != 1:
        raise SystemExit(f"Usage: {sys.argv[0]} [--count] <profile>")
    profile = args[0].strip()
    seen: set[str] = set()
    out: list[str] = []
    for path in paths_for_profile(profile):
        if path not in seen:
            seen.add(path)
            out.append(path)

    if profile in {"darwin", "dashboard"} and len(out) > DARWIN_PATH_CAP:
        raise SystemExit(
            f"ERROR: sparse profile {profile!r} has {len(out)} paths "
            f"(cap {DARWIN_PATH_CAP}). Refusing SPX-scale checkout explosion."
        )

    if count_only:
        print(len(out))
        return

    for path in out:
        print(path)


if __name__ == "__main__":
    main()
