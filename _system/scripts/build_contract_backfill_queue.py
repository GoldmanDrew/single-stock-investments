#!/usr/bin/env python3
"""Build the contract_backfill dispatch queue and authorize evidence packets.

Priority inside the queue:
  1. Almost-there names (component map present, still evidence_blocked)
  2. Remaining evidence_blocked holdings, holdings/core/hold first then alpha

Writes:
  - _system/data/contract_backfill_queue.json
  - {TICKER}/research/authorized_evidence.json for each queued ticker so the
    evidence hash differs from a prior deep-dive hash (daily lane stays gated).

Stall breaker: statuses alone would rebuild the identical wave forever when its
tickers fail without progress (they stay evidence_blocked), and the continue
workflow skips the push/dispatch on "unchanged". When the rebuilt wave matches
the previously dispatched wave (authorized_packets > 0 in the prior queue file),
the stalled tickers rotate to the back of the priority order so the next wave
differs and the drain resumes. dispatch_attempts in the queue JSON records how
often each pending ticker has been waved.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QUEUE = ROOT / "_system" / "data" / "contract_backfill_queue.json"
REGISTRY = ROOT / "_system" / "portfolio" / "registry.json"


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, ValueError):
        return {} if default is None else default


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def is_almost_there(contract: dict) -> bool:
    if contract.get("status") != "evidence_blocked":
        return False
    cc = contract.get("component_coverage") or {}
    return bool(cc.get("all_material_components_identified")) and int(cc.get("additive_component_count") or 0) > 0


def stance_rank(entry: dict) -> int:
    stance = str(entry.get("stance") or entry.get("approved_stance") or "").lower()
    order = {"core": 0, "accumulate": 1, "hold": 2, "watch": 3, "pass": 4, "trim": 5, "exit": 6}
    return order.get(stance, 7)


def authorize(ticker: str, contract: dict, *, cohort: str) -> dict:
    blockers = ((contract.get("evidence") or {}).get("blockers") or [])[:12]
    packet = {
        "schema_version": "1.0",
        "purpose": "contract_backfill",
        "ticker": ticker,
        "authorized_at": now(),
        "cohort": cohort,
        "contract_status": contract.get("status"),
        "component_coverage": contract.get("component_coverage") or {},
        "blockers": blockers,
        "instruction": (
            "Upgrade this ticker's universal valuation contract toward decision_grade. "
            "Read research/thesis_card.json and the latest research/evidence/filing_digest_*.md first. "
            "Attach valid calculation_proof graphs (approved method_id@version) to every additive "
            "component, keep overlap_keys non-overlapping, and reconcile owner-cash/NAV plus downside "
            "capital claims to primary filings. Do not invent a human capital decision."
        ),
    }
    write_json(ROOT / ticker / "research" / "authorized_evidence.json", packet)
    return packet


MAX_DISPATCH_ATTEMPTS = 3


def rotate_if_stalled(ordered: list[str], wave_size: int, previous: dict) -> tuple[list[str], bool]:
    """Rotate stalled tickers to the back when rebuilding the already-dispatched wave.

    A wave is "stalled" when the fresh priority order reproduces exactly the
    tickers of the previous queue file AND that file was a real dispatch
    (authorized_packets > 0; dry runs write 0). Returns (ordered, stalled).
    """
    prev_wave = [str(t) for t in (previous.get("tickers") or [])]
    if not prev_wave or int(previous.get("authorized_packets") or 0) <= 0:
        return ordered, False
    if ordered[:wave_size] != prev_wave:
        return ordered, False
    rotated = ordered[len(prev_wave):] + prev_wave
    if rotated[:wave_size] == prev_wave and len(rotated) > 1:
        # Everything pending was in the stalled wave; rotate by one inside it
        # so the serialized ticker list still changes and the push fires.
        rotated = rotated[1:] + rotated[:1]
    if rotated[:wave_size] == prev_wave:
        # Rotation is a no-op (a single pending ticker). Claiming a rotation
        # here would record rotated=true while the workflow's BEFORE==AFTER
        # check suppresses the push — report the state honestly instead.
        return ordered, False
    return rotated, True


def build_queue(
    *,
    wave_size: int,
    authorize_packets: bool,
    exclude_tickers: set[str] | None = None,
    persist: bool = True,
) -> dict:
    registry = read_json(REGISTRY)
    holdings = registry.get("holdings") or {}
    excluded = {t.upper() for t in (exclude_tickers or set())}
    almost: list[str] = []
    unmapped: list[tuple[int, str]] = []
    for ticker in sorted(holdings):
        if ticker.upper() in excluded:
            continue
        contract = read_json(ROOT / ticker / "research" / "valuation_contract.json")
        if not contract or contract.get("status") == "decision_grade":
            continue
        if contract.get("status") != "evidence_blocked":
            continue
        if is_almost_there(contract):
            almost.append(ticker)
        else:
            unmapped.append((stance_rank(holdings.get(ticker) or {}), ticker))
    unmapped.sort()
    ordered = almost + [t for _, t in unmapped]
    previous = read_json(QUEUE)
    prev_attempts = {
        t: int(n)
        for t, n in ((previous.get("dispatch_attempts") or {}).items())
    }
    # Park tickers that already burned MAX_DISPATCH_ATTEMPTS dispatches at the
    # back of the order so fresh work drains first; they only re-enter a wave
    # once everything else is exhausted. Parking is visible in stall_breaker.
    parked = [t for t in ordered if prev_attempts.get(t, 0) >= MAX_DISPATCH_ATTEMPTS]
    if parked and len(parked) < len(ordered):
        parked_set = set(parked)
        ordered = [t for t in ordered if t not in parked_set] + parked
    ordered, stalled = rotate_if_stalled(ordered, wave_size, previous)
    wave = ordered[:wave_size]
    attempts = {t: n for t, n in prev_attempts.items() if t in set(ordered)}
    prev_wave = [str(t) for t in (previous.get("tickers") or [])]
    if wave != prev_wave:
        # The workflow only pushes and dispatches when the wave changed, so an
        # unchanged rebuild must not count as an attempt.
        for ticker in wave:
            attempts[ticker] = attempts.get(ticker, 0) + 1
    authorized = 0
    if authorize_packets:
        for ticker in wave:
            contract = read_json(ROOT / ticker / "research" / "valuation_contract.json")
            cohort = "almost_there" if ticker in almost else "unmapped"
            authorize(ticker, contract, cohort=cohort)
            authorized += 1
    payload = {
        "updated": now(),
        "source": "build_contract_backfill_queue.py",
        "reason": "contract_backfill",
        "max_parallel": 1,
        "total_pending": len(ordered),
        "almost_there_count": len(almost),
        "unmapped_count": len(unmapped),
        "wave_size": len(wave),
        "authorized_packets": authorized,
        "tickers": wave,
        "almost_there": almost,
        "dispatch_attempts": attempts,
        "stall_breaker": {
            "rotated": stalled,
            "stalled_wave": [str(t) for t in (previous.get("tickers") or [])] if stalled else [],
            "parked": parked,
            "max_dispatch_attempts": MAX_DISPATCH_ATTEMPTS,
        },
    }
    if persist:
        write_json(QUEUE, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--wave-size",
        type=int,
        default=5,
        help="Tickers to authorize and queue now (keep small so CI/automerge can drain)",
    )
    parser.add_argument("--no-authorize", action="store_true", help="Write queue without authorized_evidence packets")
    parser.add_argument(
        "--exclude-ticker",
        action="append",
        default=[],
        help="Ticker to skip (repeatable); used to avoid open Cursor PRs",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    exclude = {t.strip().upper() for t in args.exclude_ticker if t.strip()}
    if args.dry_run:
        # persist=False: a dry-run must not overwrite the dispatched-wave
        # record (authorized_packets/dispatch_attempts) that arms the stall
        # breaker for the next scheduled run.
        payload = build_queue(wave_size=args.wave_size, authorize_packets=False, exclude_tickers=exclude, persist=False)
        print(json.dumps({k: payload[k] for k in ("total_pending", "almost_there_count", "unmapped_count", "wave_size", "tickers")}, indent=2))
        return 0
    payload = build_queue(
        wave_size=args.wave_size,
        authorize_packets=not args.no_authorize,
        exclude_tickers=exclude,
    )
    print(json.dumps({k: payload[k] for k in ("total_pending", "almost_there_count", "wave_size", "authorized_packets", "tickers")}, indent=2))
    print(f"Wrote {QUEUE.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
