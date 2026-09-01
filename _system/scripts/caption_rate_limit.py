#!/usr/bin/env python3
"""Proactive pacing for YouTube caption fetches, persisted across processes.

Built because reactive backoff is not enough. On 2026-09-01 a run at one fetch
per second reached about 25 items and then received `IpBlocked` for every
subsequent request regardless of which video it named. The block was still in
force more than twenty minutes later, and a second run spent its whole budget
discovering that. Backing off *after* the block has already cost the run.

So the limiter is a budget, not a retry policy. Three independent ceilings, all
of which must pass before a fetch is allowed:

  * **Spacing** -- a minimum interval between fetches, with jitter. The observed
    trigger was burst rate, so this is the ceiling that matters most. Jitter
    exists because a perfectly periodic request train is itself a fingerprint.
  * **Hourly** and **daily** caps -- so a long-running daemon cannot drift into
    a burst by accumulating "catch-up" credit after an idle period. A token
    bucket that refills without a cap would do exactly that.
  * **Backoff** -- when a block does happen, `blocked_until` is persisted and
    doubles from 30 minutes to a 4-hour ceiling. It survives process restart,
    which is the point: without persistence, restarting the daemon is
    indistinguishable from having waited, and a supervisor loop turns a
    single block into a hammering loop.

State lives in the vault next to the backlog so a host rebuild does not lose it,
and so `--status` can answer "why is nothing happening" without reading code.

    python _system/scripts/caption_rate_limit.py --status
    python _system/scripts/caption_rate_limit.py --reset-backoff
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from vault_paths import videos_root  # noqa: E402

STATE_NAME = "caption_rate_state.json"

# Measured trigger: ~25 fetches at 1s spacing. 150s is two orders of magnitude
# slower than that and still drains a 25-item backlog in about an hour.
MIN_INTERVAL_SECONDS = int(os.environ.get("CAPTION_MIN_INTERVAL", "150"))
JITTER_SECONDS = int(os.environ.get("CAPTION_JITTER", "45"))
MAX_PER_HOUR = int(os.environ.get("CAPTION_MAX_PER_HOUR", "20"))
# Deliberately set to 24 x the hourly cap, so the hourly ceiling and the spacing
# floor are the only things that ever bind. A lower daily number would throttle
# an overnight run that is already inside the safe per-hour rate, buying no extra
# protection -- the block is triggered by burst rate, not by daily volume.
#
# This is the free ceiling and there is no paid tier above it by design. The
# youtube-transcript-api answer to IP blocks is a paid proxy pool (Webshare and
# similar); this lane uses pacing instead, which costs nothing and has held at
# zero blocks. Do not add a proxy.
MAX_PER_DAY = int(os.environ.get("CAPTION_MAX_PER_DAY", str(24 * MAX_PER_HOUR)))

BACKOFF_START_SECONDS = 1800      # 30 minutes
BACKOFF_CEILING_SECONDS = 14400   # 4 hours


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(stamp: str | None) -> datetime | None:
    if not stamp:
        return None
    try:
        return datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _fmt(when: datetime) -> str:
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def state_path() -> Path:
    return videos_root(create=True) / STATE_NAME


def load_state() -> dict:
    path = state_path()
    if not path.exists():
        return {"fetches": [], "backoff_seconds": 0, "blocked_until": None}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"fetches": [], "backoff_seconds": 0, "blocked_until": None}
    doc.setdefault("fetches", [])
    doc.setdefault("backoff_seconds", 0)
    doc.setdefault("blocked_until", None)
    return doc


def save_state(doc: dict) -> None:
    # Keep only what the ceilings need to see; this file is written often.
    cutoff = _now() - timedelta(days=1)
    doc["fetches"] = [f for f in doc.get("fetches", []) if (_parse(f) or cutoff) > cutoff]
    doc["updated_at"] = _fmt(_now())
    path = state_path()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _counts(doc: dict) -> tuple[int, int, datetime | None]:
    now = _now()
    stamps = [s for s in (_parse(f) for f in doc.get("fetches", [])) if s]
    hour = sum(1 for s in stamps if s > now - timedelta(hours=1))
    day = sum(1 for s in stamps if s > now - timedelta(days=1))
    return hour, day, (max(stamps) if stamps else None)


def check(doc: dict | None = None) -> dict:
    """May a fetch happen right now? Returns {allowed, wait_seconds, reason}."""
    doc = doc if doc is not None else load_state()
    now = _now()

    blocked_until = _parse(doc.get("blocked_until"))
    if blocked_until and blocked_until > now:
        return {"allowed": False, "wait_seconds": int((blocked_until - now).total_seconds()),
                "reason": "backoff_until_" + _fmt(blocked_until)}

    hour, day, last = _counts(doc)
    if day >= MAX_PER_DAY:
        return {"allowed": False, "wait_seconds": 3600, "reason": "daily_cap_" + str(day)}
    if hour >= MAX_PER_HOUR:
        return {"allowed": False, "wait_seconds": 600, "reason": "hourly_cap_" + str(hour)}
    if last:
        # Jitter is added to the requirement, not subtracted, so the spacing
        # floor is never undercut.
        need = MIN_INTERVAL_SECONDS + random.randint(0, JITTER_SECONDS)
        waited = (now - last).total_seconds()
        if waited < need:
            return {"allowed": False, "wait_seconds": int(need - waited), "reason": "spacing"}
    return {"allowed": True, "wait_seconds": 0, "reason": "ok"}


def record_fetch(doc: dict | None = None) -> dict:
    doc = doc if doc is not None else load_state()
    doc.setdefault("fetches", []).append(_fmt(_now()))
    save_state(doc)
    return doc


def record_success(doc: dict | None = None) -> dict:
    """A completed fetch clears the backoff ladder."""
    doc = doc if doc is not None else load_state()
    doc["backoff_seconds"] = 0
    doc["blocked_until"] = None
    save_state(doc)
    return doc


def record_block(doc: dict | None = None) -> dict:
    """Double the backoff and persist it, so a restart does not reset the wait."""
    doc = doc if doc is not None else load_state()
    current = int(doc.get("backoff_seconds") or 0)
    nxt = BACKOFF_START_SECONDS if current <= 0 else min(current * 2, BACKOFF_CEILING_SECONDS)
    doc["backoff_seconds"] = nxt
    doc["blocked_until"] = _fmt(_now() + timedelta(seconds=nxt))
    doc["last_block_at"] = _fmt(_now())
    doc["block_count"] = int(doc.get("block_count") or 0) + 1
    save_state(doc)
    return doc


def status() -> dict:
    doc = load_state()
    hour, day, last = _counts(doc)
    decision = check(doc)
    return {
        "fetches_last_hour": hour,
        "fetches_last_day": day,
        "last_fetch_at": _fmt(last) if last else None,
        "blocked_until": doc.get("blocked_until"),
        "backoff_seconds": doc.get("backoff_seconds"),
        "block_count": doc.get("block_count", 0),
        "limits": {
            "min_interval_seconds": MIN_INTERVAL_SECONDS,
            "jitter_seconds": JITTER_SECONDS,
            "max_per_hour": MAX_PER_HOUR,
            "max_per_day": MAX_PER_DAY,
        },
        "decision": decision,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--status", action="store_true", help="Show pacing state and the next decision")
    p.add_argument("--reset-backoff", action="store_true",
                   help="Clear a persisted block (only if you know it has lifted)")
    args = p.parse_args()

    if args.reset_backoff:
        doc = load_state()
        doc["backoff_seconds"] = 0
        doc["blocked_until"] = None
        save_state(doc)
        print("backoff cleared")
        return 0
    print(json.dumps(status(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
