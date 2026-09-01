#!/usr/bin/env python3
"""Select one pending committee and deterministically advance its state.

Modes:

    --github-output PATH    select the next actionable committee (default)
    --refresh-ticker/--refresh-date
                            re-freeze one packet, or park it when that would
                            discard landed votes
    --refresh-backlog       markdown table of packets waiting on a re-freeze,
                            followed by the parked queue
    --parked                markdown table of parked committees only
    --unpark TICKER --unpark-date DATE --unpark-mode resume|discard
                            the only way out of stage=parked; see the
                            investment_committee_pipeline module docstring
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from committee_task_queue import next_tasks, read_json, ROOT
from investment_committee_pipeline import (
    MAX_REFRESHES_WITHOUT_VOTES,
    SNAPSHOT_DIR,
    TERMINAL_STAGES,
    archive_stale_assembled,
    assembled_packet_hash,
    clear_triage,
    discover_evidence,
    freeze_evidence,
    has_snapshot,
    initialize,
    live_evidence_drifted,
    packet_hash,
    park_committee,
    triage_path,
    verify_packet,
    vote_files,
    votes_landed,
    write_json,
    write_prompts,
)


def packet_is_current(manifest: dict) -> bool:
    """True when the packet still hashes to its frozen value.

    Copy-on-freeze packets are hashed over the frozen copies in the work dir, so
    a daily compiler rewriting the live research tree no longer ages a packet
    that raters are still voting on.
    """
    return verify_packet(manifest)


def refresh_reason(manifest: dict) -> str | None:
    """Why this packet needs a genuine re-freeze, or None for byte churn only."""
    if manifest.get("refresh_requested"):
        return "explicit_refresh_request"
    if packet_is_current(manifest):
        return None
    return "frozen_copies_missing_or_modified" if has_snapshot(manifest) else "legacy_evidence_drift"


def select() -> dict:
    """First actionable committee; a needed refresh never blocks live work."""
    manifests = sorted(ROOT.glob("*/research/committee_work/*/manifest.json"))
    deferred_refresh: dict | None = None
    for manifest_path in manifests:
        manifest = read_json(manifest_path)
        stage = str(manifest.get("stage") or "")
        if stage in TERMINAL_STAGES:
            continue
        ticker = manifest_path.parts[-5].upper()
        committee_date = manifest_path.parent.name
        recorded = assembled_packet_hash(ticker, committee_date)
        stale_assembled = bool(recorded) and recorded != manifest.get("packet_hash")
        if recorded and not stale_assembled:
            continue
        reason = refresh_reason(manifest)
        if reason:
            if deferred_refresh is None:
                deferred_refresh = {
                    "ticker": ticker,
                    "committee_date": committee_date,
                    "action": "refresh",
                    "reason": reason,
                    "stale_assembled": stale_assembled,
                    "tasks": [],
                }
            continue
        tasks = next_tasks(ticker, committee_date)
        current = read_json(manifest_path)
        if tasks:
            return {
                "ticker": ticker,
                "committee_date": committee_date,
                "action": "advance",
                "reason": "stale_assembled_record" if stale_assembled else "tasks_pending",
                "stale_assembled": stale_assembled,
                "live_evidence_drifted": live_evidence_drifted(manifest),
                "tasks": tasks,
            }
        if current.get("stage") == "ready_to_assemble":
            return {
                "ticker": ticker,
                "committee_date": committee_date,
                "action": "assemble",
                "reason": "stale_assembled_record" if stale_assembled else "ready_to_assemble",
                "stale_assembled": stale_assembled,
                "live_evidence_drifted": live_evidence_drifted(manifest),
                "tasks": [],
            }
    if deferred_refresh:
        return deferred_refresh
    return {"ticker": "", "committee_date": "", "action": "none", "reason": "caught_up", "stale_assembled": False, "tasks": []}


def refresh_backlog() -> list[dict]:
    """Every non-terminal packet waiting on a re-freeze, with its vote count.

    The refresh job is gated on COMMITTEE_AGENTS_ENABLED, so with the flag off
    nothing acts on these packets. Printing the backlog keeps the queue visible
    instead of leaving a green run that silently did nothing.
    """
    rows = []
    for manifest_path in sorted(ROOT.glob("*/research/committee_work/*/manifest.json")):
        manifest = read_json(manifest_path)
        if str(manifest.get("stage") or "") in TERMINAL_STAGES:
            continue
        work = manifest_path.parent
        reason = refresh_reason(manifest)
        if not reason:
            continue
        rows.append({
            "ticker": manifest_path.parts[-5].upper(),
            "committee_date": work.name,
            "reason": reason,
            "votes_landed": votes_landed(work),
        })
    return rows


def parked_committees() -> list[dict]:
    """Every parked committee, from the triage file and from the manifests.

    `parked` is in TERMINAL_STAGES, so select() and refresh_backlog() both skip
    it: without this listing a parked packet - and the votes it is protecting -
    is invisible to the human the park is deferring to. The manifests are the
    authority; committee_triage.json is an index that can go stale, so an entry
    it still lists after an un-park is reported as `stale_triage_entry` rather
    than silently dropped.
    """
    rows: dict[tuple[str, str], dict] = {}
    for entry in (read_json(triage_path()).get("parked") or []) if triage_path().exists() else []:
        ticker = str(entry.get("ticker") or "").upper()
        committee_date = str(entry.get("committee_date") or "")
        if not ticker or not committee_date:
            continue
        rows[(ticker, committee_date)] = {
            "ticker": ticker,
            "committee_date": committee_date,
            "reason": entry.get("reason") or "unknown",
            "detail": entry.get("detail") or "",
            "parked_at": entry.get("parked_at") or "",
            "votes_landed": int(entry.get("votes_landed") or 0),
            "source": "committee_triage.json",
            "state": "stale_triage_entry",
        }
    for manifest_path in sorted(ROOT.glob("*/research/committee_work/*/manifest.json")):
        manifest = read_json(manifest_path)
        if str(manifest.get("stage") or "") != "parked":
            continue
        work = manifest_path.parent
        parked = manifest.get("parked") or {}
        key = (manifest_path.parts[-5].upper(), work.name)
        row = rows.get(key, {"ticker": key[0], "committee_date": key[1], "source": "manifest"})
        row.update({
            "reason": parked.get("reason") or "unknown",
            "detail": parked.get("detail") or "",
            "parked_at": parked.get("parked_at") or "",
            "votes_landed": votes_landed(work),
            "state": "parked",
            "work_dir": work.relative_to(ROOT).as_posix(),
        })
        rows[key] = row
    return [rows[key] for key in sorted(rows)]


def print_parked() -> None:
    """Markdown section listing the parked queue, for a step summary or a shell."""
    rows = parked_committees()
    print(f"### Parked committees awaiting a human decision: {len(rows)}")
    print("")
    if not rows:
        print("No committee is parked.")
        return
    print("| Ticker | Packet date | Reason | Votes held | State | Un-park |")
    print("| --- | --- | --- | --- | --- | --- |")
    for row in rows:
        unpark = (
            f"`--unpark {row['ticker']} --unpark-date {row['committee_date']} "
            "--unpark-mode resume|discard`"
        )
        print(
            f"| {row['ticker']} | {row['committee_date']} | {row['reason']} | "
            f"{row['votes_landed']} | {row['state']} | {unpark} |"
        )
    print("")
    print("Nothing automatic resumes a parked packet; `resume` keeps the held votes when the")
    print("frozen copies still verify, `discard` archives the packet and freezes a new one.")


def invalidate_votes(work: Path, old_packet: str) -> list[str]:
    """Move votes bound to a packet that no longer exists out of the round dirs.

    Leaving them in place is not neutral: committee_task_queue skips a task whose
    output file exists, so a stale vote would block its own round forever while
    load_round rejected it. Moving them keeps the audit trail and reopens the
    round.
    """
    archive = work / "invalidated_votes" / (str(old_packet or "unknown")[:8] or "unknown")
    moved = []
    for path in vote_files(work):
        target = archive / path.relative_to(work)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            target.unlink()
        path.rename(target)
        moved.append(target.relative_to(work).as_posix())
    return moved


def carry_forward_prior_gaps(ticker: str, committee_date: str, work: Path, manifest: dict) -> Path | None:
    """Preserve unresolved committee questions in the next frozen packet.

    Re-opening review is legitimate only when the prior evidence block remains
    visible to the new raters.  The old assembled record and work directory stay
    immutable audit artifacts; this small live file is the explicit bridge from
    the superseded packet to its successor.
    """
    research = ROOT / ticker / "research"
    record_path = research / f"committee_{committee_date}.json"
    record = read_json(record_path) if record_path.exists() else {}
    questions: list[tuple[str, str]] = []

    def add(value, source: str) -> None:
        text = str(value or "").strip()
        if not text or text.lower() in {"none", "none material", "n/a", "not applicable"}:
            return
        questions.append((text, source))

    for value in (record.get("synthesis") or {}).get("unresolved_items") or []:
        add(value, "assembled_synthesis")
    for value in (record.get("evidence_tribunal") or {}).get("unresolved_material_facts") or []:
        add(value, "assembled_evidence_tribunal")
    for vote in ((record.get("round_two") or {}).get("votes") or []):
        if vote.get("evidence_status") != "sufficient":
            add(vote.get("most_important_missing_fact"), f"round_two:{vote.get('persona') or 'unknown'}")
    tribunal = read_json(work / "evidence_tribunal.json") if (work / "evidence_tribunal.json").exists() else {}
    for value in tribunal.get("unresolved_material_facts") or []:
        add(value, "work_evidence_tribunal")
    if not questions:
        return None
    by_question: dict[str, dict] = {}
    for question, source in questions:
        key = " ".join(question.lower().split())
        row = by_question.setdefault(key, {
            "question": question,
            "prior_sources": [],
            "prior_evidence_status": "insufficient_evidence",
            "required_disposition": (
                "Resolve with primary evidence, reflect the uncertainty in the valuation range, "
                "or document why it is immaterial; the successor committee must adjudicate the treatment."
            ),
        })
        if source not in row["prior_sources"]:
            row["prior_sources"].append(source)
    path = research / "committee_gap_carryforward.json"
    write_json(path, {
        "schema_version": "1.0",
        "ticker": ticker,
        "as_of": committee_date,
        "status": "requires_fresh_committee_adjudication",
        "prior_packet_hash": manifest.get("packet_hash"),
        "prior_manifest_ref": (work / "manifest.json").relative_to(ROOT).as_posix(),
        "items": list(by_question.values()),
        "rule": "A packet refresh never converts an unanswered question into a resolved fact.",
    })
    return path


def resume_parked(work: Path, manifest: dict) -> Path:
    """Put a parked committee back to work, re-freezing only if it must.

    The frozen copies still verifying means the held votes still answer the
    recorded packet, so they are kept untouched. Damaged copies mean the packet
    the votes answer is gone: re-freeze from live evidence, move the votes into
    invalidated_votes/, and re-issue the prompts against the new hash.
    """
    ticker = manifest["ticker"]
    parked = manifest.get("parked") or {}
    unparked = {
        "unparked_at": datetime.now(timezone.utc).isoformat(),
        "mode": "resume",
        "was_parked_for": parked.get("reason") or "unknown",
        "refresh_count_before_unpark": int(manifest.get("refresh_count") or 0),
    }
    if verify_packet(manifest):
        unparked["packet"] = "unchanged"
        unparked["votes_kept"] = votes_landed(work)
    else:
        old_packet = str(manifest.get("packet_hash") or "")
        refs = freeze_evidence(ticker, work, discover_evidence(ticker))
        fresh = packet_hash(refs)
        moved = invalidate_votes(work, old_packet)
        manifest["evidence"] = refs
        manifest["packet_hash"] = fresh
        manifest["evidence_snapshot"] = (work / SNAPSHOT_DIR).relative_to(ROOT).as_posix()
        manifest["frozen_at"] = datetime.now(timezone.utc).isoformat()
        write_prompts(ticker, work, fresh, refs, manifest["selected_raters"])
        unparked.update({
            "packet": "re_frozen_from_live_evidence",
            "superseded_packet_hash": old_packet,
            "votes_kept": 0,
            "invalidated_votes": moved,
            "invalidated_reason": "the frozen copies these votes answered are missing or modified",
        })
    manifest["stage"] = parked.get("previous_stage") or "round_one_open"
    # The breaker counts loops the human has now explicitly signed off on.
    manifest["refresh_count"] = 0
    manifest.pop("refresh_requested", None)
    manifest.pop("parked", None)
    manifest["unparked"] = unparked
    write_json(work / "manifest.json", manifest)
    clear_triage(ticker, manifest["as_of"])
    return work


def finalize_discarded_archive(archive: Path, manifest: dict, committee_date: str) -> Path:
    """Freeze the successor packet after the old parked directory is archived.

    This second half is deliberately restartable.  A process can be interrupted
    after the atomic directory rename but before ``initialize``; a later
    operator discard then finishes the transition without losing held votes.
    """
    ticker = manifest["ticker"]
    fresh = initialize(ticker, committee_date)
    updated = read_json(fresh / "manifest.json")
    stale_record = archive_stale_assembled(ticker, committee_date, updated["packet_hash"])
    updated["refresh_count"] = 0
    updated["superseded_from"] = archive.relative_to(ROOT).as_posix()
    updated["unparked"] = {
        "unparked_at": datetime.now(timezone.utc).isoformat(),
        "mode": "discard",
        "was_parked_for": (manifest.get("parked") or {}).get("reason") or "unknown",
        "discarded_packet_hash": manifest.get("packet_hash"),
        "discarded_votes": int((manifest.get("parked") or {}).get("votes_landed") or 0),
    }
    if stale_record:
        updated["superseded_assembled_record"] = stale_record.relative_to(ROOT).as_posix()
    write_json(fresh / "manifest.json", updated)
    clear_triage(ticker, committee_date)
    return fresh


def discard_parked(work: Path, manifest: dict, committee_date: str) -> Path:
    """Archive a parked packet whole and freeze a new one from live evidence."""
    ticker = manifest["ticker"]
    carry_forward_prior_gaps(ticker, committee_date, work, manifest)
    suffix = str(manifest.get("packet_hash") or "unknown")[:8]
    archive = archive_name(work, committee_date, suffix, kind="parked-discarded")
    manifest["stage"] = "superseded"
    manifest["superseded_reason"] = "parked_packet_discarded_by_operator"
    manifest["discarded_at"] = datetime.now(timezone.utc).isoformat()
    write_json(work / "manifest.json", manifest)
    work.rename(archive)
    return finalize_discarded_archive(archive, manifest, committee_date)


def unpark(ticker: str, committee_date: str, mode: str = "resume") -> Path:
    """The only exit from stage=parked. `mode` is `resume` or `discard`."""
    ticker = ticker.upper()
    if mode not in {"resume", "discard"}:
        raise ValueError(f"unknown un-park mode {mode!r}; use resume or discard")
    work = ROOT / ticker / "research" / "committee_work" / committee_date
    manifest_path = work / "manifest.json"
    if not manifest_path.exists():
        if mode == "discard":
            candidates = []
            for archived_manifest in sorted(work.parent.glob(
                    f"{committee_date}-parked-discarded-*/manifest.json")):
                archived = read_json(archived_manifest)
                if (
                    archived.get("ticker") == ticker
                    and archived.get("stage") == "superseded"
                    and archived.get("superseded_reason") == "parked_packet_discarded_by_operator"
                    and archived.get("parked")
                ):
                    candidates.append((archived_manifest.parent, archived))
            if len(candidates) == 1:
                archive, archived = candidates[0]
                return finalize_discarded_archive(archive, archived, committee_date)
            if len(candidates) > 1:
                raise RuntimeError(
                    f"{ticker} {committee_date}: multiple interrupted discard archives; "
                    "manual archive selection is required"
                )
        raise FileNotFoundError(f"{ticker} {committee_date}: no committee work to un-park")
    manifest = read_json(manifest_path)
    if str(manifest.get("stage") or "") != "parked":
        raise ValueError(
            f"{ticker} {committee_date}: stage is {manifest.get('stage')!r}, not 'parked'; nothing to un-park"
        )
    if mode == "resume":
        return resume_parked(work, manifest)
    return discard_parked(work, manifest, committee_date)


def adopt_snapshot(work: Path, manifest: dict) -> Path:
    """Bind a still-current legacy packet to frozen copies without superseding it.

    The live bytes already hash to the recorded packet, so copying them in
    preserves packet_hash exactly: no archive, no discarded votes.
    """
    ticker = manifest["ticker"]
    sources = [ROOT / row["path"] for row in manifest.get("evidence") or []]
    refs = freeze_evidence(ticker, work, sources)
    if packet_hash(refs) != manifest.get("packet_hash"):
        raise ValueError(f"{ticker}: snapshot adoption changed the packet hash")
    manifest["evidence"] = refs
    manifest["evidence_snapshot"] = (work / SNAPSHOT_DIR).relative_to(ROOT).as_posix()
    manifest["snapshot_adopted_at"] = datetime.now(timezone.utc).isoformat()
    manifest.pop("refresh_requested", None)
    write_json(work / "manifest.json", manifest)
    return work


def archive_name(work: Path, committee_date: str, suffix: str, kind: str = "superseded") -> Path:
    archive = work.with_name(f"{committee_date}-{kind}-{suffix}")
    if not archive.exists():
        return archive
    for index in range(2, 10):
        candidate = work.with_name(f"{committee_date}-{kind}-{suffix}-{index}")
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"stale committee archive already exists: {archive}")


def prior_refresh_count(work: Path, committee_date: str, manifest: dict) -> int:
    """How many times this ticker/date has already been re-frozen.

    Packets frozen before the counter existed are read off the supersede
    archives they left behind, so a committee that has already looped does not
    get a fresh budget of three more loops.
    """
    recorded = manifest.get("refresh_count")
    if recorded is not None:
        return int(recorded)
    return len(list(work.parent.glob(f"{committee_date}-superseded-*")))


def refresh(ticker: str, committee_date: str) -> Path:
    work = ROOT / ticker / "research" / "committee_work" / committee_date
    manifest = read_json(work / "manifest.json")
    landed = votes_landed(work)
    if not has_snapshot(manifest) and packet_is_current(manifest) and not landed:
        return adopt_snapshot(work, manifest)
    if landed:
        # Every generation of packet, not just pre-copy-on-freeze ones. A frozen
        # packet whose copies were deleted or edited, or whose operator set
        # refresh_requested, is exactly the AAOI failure with a snapshot dir:
        # superseding renames the work dir and re-initializes an empty one, so
        # the hash-bound votes are discarded. A human decides, never the job.
        reason = refresh_reason(manifest) or "explicit_refresh_request"
        park_committee(
            work,
            "evidence_drift_with_votes",
            f"{landed} vote file(s) already answer this packet ({reason}); "
            "a human decides whether to discard them.",
        )
        return work
    count = prior_refresh_count(work, committee_date, manifest)
    if count >= MAX_REFRESHES_WITHOUT_VOTES:
        manifest["refresh_count"] = count
        write_json(work / "manifest.json", manifest)
        park_committee(
            work,
            "refresh_limit",
            f"re-frozen {count} times with no vote landing; refreshing again would only loop.",
        )
        return work
    suffix = str(manifest.get("packet_hash") or "unknown")[:8]
    carry_forward_prior_gaps(ticker, committee_date, work, manifest)
    archive = archive_name(work, committee_date, suffix)
    manifest["stage"] = "superseded"
    manifest["superseded_reason"] = manifest.get("refresh_reason") or "frozen_evidence_changed"
    write_json(work / "manifest.json", manifest)
    work.rename(archive)
    fresh = initialize(ticker, committee_date)
    updated = read_json(fresh / "manifest.json")
    stale_record = archive_stale_assembled(ticker, committee_date, updated["packet_hash"])
    updated["refresh_count"] = count + 1
    updated["superseded_from"] = archive.relative_to(ROOT).as_posix()
    if stale_record:
        updated["superseded_assembled_record"] = stale_record.relative_to(ROOT).as_posix()
    write_json(fresh / "manifest.json", updated)
    return fresh


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--refresh-ticker")
    parser.add_argument("--refresh-date")
    parser.add_argument(
        "--refresh-backlog",
        action="store_true",
        help="Print the packets waiting on a re-freeze, then the parked queue, as markdown",
    )
    parser.add_argument(
        "--parked",
        action="store_true",
        help="Print the parked committees awaiting a human as a markdown table",
    )
    parser.add_argument("--unpark", help="Ticker of the parked committee to un-park")
    parser.add_argument("--unpark-date", help="Committee date of the parked committee to un-park")
    parser.add_argument(
        "--unpark-mode",
        choices=("resume", "discard"),
        default="resume",
        help="resume keeps the held votes when the frozen copies verify; discard archives the packet",
    )
    args = parser.parse_args()
    if args.refresh_backlog:
        rows = refresh_backlog()
        print(f"Committee packets waiting on a re-freeze: {len(rows)}")
        print("")
        print("| Ticker | Packet date | Reason | Votes landed |")
        print("| --- | --- | --- | --- |")
        for row in rows:
            print(f"| {row['ticker']} | {row['committee_date']} | {row['reason']} | {row['votes_landed']} |")
        print("")
        # A parked packet is skipped by select() and by the backlog above, so it
        # would otherwise never reach the human it is waiting on.
        print_parked()
        return 0
    if args.parked:
        print_parked()
        return 0
    if bool(args.unpark) != bool(args.unpark_date):
        parser.error("--unpark and --unpark-date must be used together")
    if args.unpark:
        path = unpark(args.unpark, args.unpark_date, args.unpark_mode)
        print(path.relative_to(ROOT).as_posix())
        return 0
    if bool(args.refresh_ticker) != bool(args.refresh_date):
        parser.error("--refresh-ticker and --refresh-date must be used together")
    if args.refresh_ticker:
        path = refresh(args.refresh_ticker.upper(), args.refresh_date)
        print(path.relative_to(ROOT).as_posix())
        return 0
    result = select()
    print(json.dumps(result, separators=(",", ":")))
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as handle:
            for key in ("ticker", "committee_date", "action", "reason"):
                handle.write(f"{key}={result[key]}\n")
            handle.write("tasks=" + json.dumps(result["tasks"], separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
