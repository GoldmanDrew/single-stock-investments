#!/usr/bin/env python3
"""Pick the next ticker for Marvin's daily deep dive.

Priority:
  1. Explicit ticker (CLI arg) — always runs
  2. Holdings with no deep dive yet
  3. Holdings with primary documents newer than the latest deep dive
  4. Holdings with refresh-eligible valuation news newer than the latest deep dive
  5. Optional --force-rotate: oldest deep dive when nothing new (--require-new skips instead)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from portfolio_news_common import latest_refresh_news_activity  # noqa: E402

SKIP = {"_system", "dashboard", ".git", ".github", ".cursor"}
DATE_RE = re.compile(r"deep_dive_(\d{4}-\d{2}-\d{2})\.md$")
ISO_RE = re.compile(r"(\d{4}-\d{2}-\d{2}T[\d:.+-]+)")
DOC_SUFFIXES = {".pdf", ".htm", ".html", ".json", ".csv"}
DOC_DIR_NAMES = {
    "investor-documents",
    "01_Official",
    "02_Quarterly",
    "03_Investor",
    "04_Strategy",
    "05_Other",
    "06_References",
}


def list_tickers() -> list[str]:
    tickers = []
    for p in ROOT.iterdir():
        if p.is_dir() and p.name not in SKIP and not p.name.startswith("."):
            tickers.append(p.name)
    return sorted(tickers)


def _parse_iso(line: str) -> datetime | None:
    m = ISO_RE.match(line.strip())
    if not m:
        return None
    raw = m.group(1)
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def latest_deep_dive(ticker: str) -> tuple[datetime | None, Path | None]:
    research = ROOT / ticker / "research"
    if not research.is_dir():
        return None, None
    best: datetime | None = None
    best_path: Path | None = None
    for path in research.glob("deep_dive_*.md"):
        m = DATE_RE.search(path.name)
        if m:
            dt = datetime.strptime(m.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
        else:
            dt = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        file_dt = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        candidate = max(dt, file_dt)
        if best is None or candidate > best:
            best = candidate
            best_path = path
    return best, best_path


def _max_dt(current: datetime | None, candidate: datetime | None) -> datetime | None:
    if candidate is None:
        return current
    if current is None:
        return candidate
    return max(current, candidate)


def latest_document_activity(ticker: str) -> datetime | None:
    """Latest timestamp from downloads, SEC manifest, or primary document files."""
    ticker_dir = ROOT / ticker
    latest: datetime | None = None

    manifest = ticker_dir / "investor-documents" / "DOWNLOAD_MANIFEST.json"
    if manifest.exists():
        try:
            rows = json.loads(manifest.read_text(encoding="utf-8"))
            for row in rows:
                fd = row.get("filingDate")
                if fd:
                    latest = _max_dt(
                        latest,
                        datetime.strptime(fd, "%Y-%m-%d").replace(tzinfo=timezone.utc),
                    )
                local = row.get("local")
                if local:
                    fname = Path(str(local)).name
                    lp = ticker_dir / "investor-documents" / "sec-edgar" / fname
                    if lp.exists():
                        latest = _max_dt(
                            latest,
                            datetime.fromtimestamp(lp.stat().st_mtime, tz=timezone.utc),
                        )
        except (json.JSONDecodeError, ValueError, OSError):
            pass

    log = ticker_dir / "_download_log.txt"
    if log.exists():
        for line in log.read_text(encoding="utf-8", errors="ignore").splitlines():
            ts = _parse_iso(line)
            if ts:
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                latest = _max_dt(latest, ts)

    for sub in DOC_DIR_NAMES:
        base = ticker_dir / sub
        if not base.exists():
            continue
        for f in base.rglob("*"):
            if not f.is_file() or f.suffix.lower() not in DOC_SUFFIXES:
                continue
            if "DOWNLOAD_MANIFEST.json" in f.name:
                continue
            try:
                latest = _max_dt(
                    latest,
                    datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc),
                )
            except OSError:
                continue

    index = ticker_dir / "INDEX.csv"
    if index.exists():
        try:
            latest = _max_dt(
                latest,
                datetime.fromtimestamp(index.stat().st_mtime, tz=timezone.utc),
            )
        except OSError:
            pass

    return latest


def _activity_snapshot(ticker: str) -> dict:
    dive_dt, dive_path = latest_deep_dive(ticker)
    doc_dt = latest_document_activity(ticker)
    news_dt = None
    if dive_dt:
        news_dt = latest_refresh_news_activity(ticker, since=dive_dt)
    elif latest_refresh_news_activity(ticker):
        news_dt = latest_refresh_news_activity(ticker)

    trigger_dt: datetime | None = None
    reason: str | None = None
    if doc_dt and (dive_dt is None or doc_dt > dive_dt):
        trigger_dt = doc_dt
        reason = "new_documents"
    if news_dt and (dive_dt is None or news_dt > dive_dt):
        if trigger_dt is None or news_dt > trigger_dt:
            trigger_dt = news_dt
            reason = "new_valuation_news"

    return {
        "deep_dive_at": dive_dt.isoformat() if dive_dt else None,
        "deep_dive_path": str(dive_path.relative_to(ROOT)) if dive_path else None,
        "document_at": doc_dt.isoformat() if doc_dt else None,
        "news_at": news_dt.isoformat() if news_dt else None,
        "trigger_at": trigger_dt.isoformat() if trigger_dt else None,
        "reason": reason,
    }


def pick_ticker(
    explicit: str | None = None,
    *,
    require_new_documents: bool = True,
    force_rotate: bool = False,
) -> dict:
    if explicit:
        explicit = explicit.strip()
        if explicit not in list_tickers():
            raise SystemExit(f"Unknown ticker: {explicit}")
        snap = _activity_snapshot(explicit)
        return {
            "ticker": explicit,
            "skip": False,
            "reason": "manual_override",
            **{k: v for k, v in snap.items() if k != "reason"},
        }

    no_dive: list[str] = []
    stale: list[tuple[datetime, str, str]] = []

    for ticker in list_tickers():
        snap = _activity_snapshot(ticker)
        dive_dt = snap["deep_dive_at"]
        if dive_dt is None:
            no_dive.append(ticker)
            continue
        if not snap.get("trigger_at") or not snap.get("reason"):
            continue
        trigger_dt = datetime.fromisoformat(snap["trigger_at"])
        stale.append((trigger_dt, snap["reason"], ticker))

    if no_dive:
        t = sorted(no_dive)[0]
        snap = _activity_snapshot(t)
        return {
            "ticker": t,
            "skip": False,
            "reason": "no_deep_dive",
            "deep_dive_at": snap["deep_dive_at"],
            "document_at": snap["document_at"],
            "news_at": snap["news_at"],
        }

    if stale:
        stale.sort(key=lambda x: (-x[0].timestamp(), x[2]))
        trigger_dt, reason, t = stale[0]
        snap = _activity_snapshot(t)
        return {
            "ticker": t,
            "skip": False,
            "reason": reason,
            "deep_dive_at": snap["deep_dive_at"],
            "document_at": snap["document_at"],
            "news_at": snap["news_at"],
            "trigger_at": trigger_dt.isoformat(),
        }

    if force_rotate and not require_new_documents:
        ranked: list[tuple[datetime, str]] = []
        for ticker in list_tickers():
            dive_dt, _ = latest_deep_dive(ticker)
            if dive_dt:
                ranked.append((dive_dt, ticker))
        if ranked:
            ranked.sort(key=lambda x: (x[0], x[1]))
            t = ranked[0][1]
            snap = _activity_snapshot(t)
            return {
                "ticker": t,
                "skip": False,
                "reason": "rotate_oldest_dive",
                "deep_dive_at": snap["deep_dive_at"],
                "document_at": snap["document_at"],
                "news_at": snap["news_at"],
            }

    return {
        "ticker": None,
        "skip": True,
        "reason": "caught_up",
        "deep_dive_at": None,
        "document_at": None,
        "news_at": None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Pick ticker for Marvin daily deep dive")
    parser.add_argument("ticker", nargs="?", help="Explicit ticker override")
    parser.add_argument("--json", action="store_true", help="Emit JSON result")
    parser.add_argument(
        "--force-rotate",
        action="store_true",
        help="If no new documents or news, pick oldest deep dive anyway",
    )
    parser.add_argument(
        "--require-new",
        action="store_true",
        default=True,
        help="Default: skip when no holdings have new activity (default: true)",
    )
    parser.add_argument(
        "--no-require-new",
        action="store_false",
        dest="require_new",
        help="Allow rotation fallback without new activity",
    )
    args = parser.parse_args()

    result = pick_ticker(
        args.ticker,
        require_new_documents=args.require_new and not args.force_rotate,
        force_rotate=args.force_rotate or not args.require_new,
    )

    if args.json:
        print(json.dumps(result, indent=2))
    elif result.get("skip"):
        print("", end="")
        sys.exit(0)
    else:
        print(result["ticker"])

    if result.get("skip"):
        sys.exit(0)


if __name__ == "__main__":
    main()
