#!/usr/bin/env python3
"""Collapse the [PROPOSED] backlog in daily logs into one reviewable queue.

Marvin proposes memory updates as `[PROPOSED …]` blocks in
`_system/memory/daily/{date}.md`; a promotion pass moves approved items into
`_system/memory/MEMORY.md`. The proposing side has run for months and the
promoting side has not, so the belief set freezes while proposals accumulate.
Reading them in place means opening every daily file, which is why it has not
happened.

This writes a single file grouped by lens (MUNGER / PABRAI / STAHL / MOI /
COMPANY / …), newest first, with an `- [ ]` marker and a stable `id` per item,
so promotion is one pass with checkboxes rather than dozens of file reads.

**Decision ledger.** Until 2026-08-09 the queue had no memory of its own: items
promoted in May 2026 were still sitting unticked in the August queue, so every
build re-surfaced work already done and the reviewer had to re-reject the same
noise. `_system/memory/triage_ledger.json` now records a decision per item id;
decided items are excluded from the next build. Nothing is deleted — remove an
id from the ledger (or pass `--show-decided`) to bring a proposal back.

It does **not** promote anything into MEMORY.md. Promotion is the human owner's;
an agent may run a promotion pass only when the human asks for one in that
session, and every agent-promoted belief is stamped as such in MEMORY.md.

Cadence: rebuild monthly (and after any promotion pass), then record decisions
so the next build starts from the undecided remainder. See the header of
`_system/memory/MEMORY.md`.

Usage:
  python _system/scripts/build_memory_triage.py
  python _system/scripts/build_memory_triage.py --since 2026-07-01
  python _system/scripts/build_memory_triage.py --show-decided

  # record decisions so they never re-surface
  python _system/scripts/build_memory_triage.py --ingest            # read [x]/[-] ticks
  python _system/scripts/build_memory_triage.py --mark promoted --ids a1b2,c3d4 \
      --reason "2026-08-09 promotion pass"
  python _system/scripts/build_memory_triage.py --auto-reject-mechanical
  python _system/scripts/build_memory_triage.py --sync-promoted-from-memory

  # reverse a decision: delete the id from the ledger, then re-mark it carrying
  # the row you deleted, so the reversal survives as data (the ledger is not
  # tracked by git, so nothing else remembers what was there)
  python _system/scripts/build_memory_triage.py --mark rejected --ids c79e14f64cfc \
      --reason "contradicts a promoted belief" \
      --previous-decision '{"decision": "promoted", "date": "2026-08-09", "by": "agent"}'

  # check every `promoted` id still corresponds to a belief in MEMORY.md
  python _system/scripts/build_memory_triage.py --audit-promoted
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[2]
DAILY = ROOT / "_system" / "memory" / "daily"
MEMORY = ROOT / "_system" / "memory" / "MEMORY.md"
LEDGER = ROOT / "_system" / "memory" / "triage_ledger.json"
DEFAULT_OUT = ROOT / "_system" / "reviews" / "pending" / "memory_triage.md"

HEADING = re.compile(r"^#{2,4}\s*\[PROPOSED([^\]]*)\]\s*(.*)$")
# Daily logs tag proposals two ways: a heading, or an inline bullet. A bullet
# carries its own lens and is frequently nested under a differently-tagged
# heading, so attributing it to the enclosing heading files company facts under
# MEMORY and makes the queue impossible to review lens by lens.
BULLET = re.compile(r"^[-*]\s*\[PROPOSED([^\]]*)\]\s*(.*)$")
ANY_HEADING = re.compile(r"^#{1,6}\s")
DATED = re.compile(r"(\d{4}-\d{2}-\d{2})")

# `AMZN: watch (3.2%, rel=0.5)`, `BN dissent: hold — archetype=platform`,
# `8697.T: lens consensus watch @ 1.78% blend (agreement 80%)`. These are the
# per-ticker stance readouts a scoring run emits for every name on one day.
# They are dated observations of a model's output, not beliefs, and they are
# what makes the LAWRENCE / HOHN / CONSENSUS / BUFFETT / GREENBLATT lenses look
# full while holding nothing promotable.
MECHANICAL_READOUT = re.compile(
    r"^[A-Z0-9][A-Za-z0-9.\-]{0,12}(?:\s+dissent)?:\s+"
    r"(?:lens consensus\s+)?(?:pass|watch|hold|accumulate|trim|exit)\b"
)
# The rendered queue tags each row `` `file.md` · `id` ``.
ROW_START = re.compile(r"^-\s*\[(.)\]")
ROW_ID = re.compile(r"`([0-9a-f]{12})`\s*$")

# `promoted` used to be the only way to retire a proposal that was not rejected,
# so a proposal merged into a neighbouring belief — or dropped mid-pass — was
# stamped promoted and then suppressed from every future build with nothing in
# MEMORY.md to check it against. `dropped` is that third state: decided, kept out
# of the queue, and explicitly *not* claiming a belief exists.
DECISIONS = ("promoted", "rejected", "dropped")

# The back-sync path (`--sync-promoted-from-memory`) does not make a judgement —
# it observes that a belief is already in MEMORY.md and back-marks the proposal
# that matches it. Stamping those with `--by` attributed the human owner's
# May-2026 promotions to whoever ran the sync, so "reverse the agent's decisions
# wholesale" would have unwound the human's work. They get their own marker.
BACKFILL_BY = "backfill"


def parse_file(path: Path) -> list[dict]:
    """Every [PROPOSED …] block with the bullet lines that follow it."""
    day = DATED.search(path.name)
    items: list[dict] = []
    current: dict | None = None
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.rstrip()
        match = HEADING.match(line.strip())
        if match:
            if current and current["body"]:
                items.append(current)
            current = {
                "lens": (match.group(1) or "").strip() or "GENERIC",
                "title": match.group(2).strip(),
                "day": day.group(1) if day else path.stem,
                "file": path.name,
                "body": [],
            }
            continue
        # An inline bullet is its own proposal, with its own lens, whether or not
        # it sits inside a heading block.
        bullet = BULLET.match(line.strip())
        if bullet and bullet.group(2).strip():
            items.append({
                "lens": (bullet.group(1) or "").strip() or "GENERIC",
                "title": "",
                "day": day.group(1) if day else path.stem,
                "file": path.name,
                "body": [bullet.group(2).strip()],
            })
            continue
        if current is None:
            continue
        # A non-PROPOSED heading closes the block.
        if ANY_HEADING.match(line):
            if current["body"]:
                items.append(current)
            current = None
            continue
        if line.strip():
            current["body"].append(line.strip())
    if current and current["body"]:
        items.append(current)
    return items


def _key(item: dict) -> tuple[str, str]:
    return (item["lens"], " ".join(item["body"]).lower()[:400])


def fingerprint(item: dict) -> str:
    """Stable id for a proposal, independent of the day it was re-proposed.

    Same normalization as `dedupe`, so an item re-proposed next month keeps the
    id it was decided under and stays out of the queue.
    """
    lens, body = _key(item)
    return hashlib.sha1(f"{lens}\n{body}".encode("utf-8")).hexdigest()[:12]


def dedupe(items: list[dict]) -> tuple[list[dict], int]:
    """Collapse items whose body text repeats, keeping the earliest sighting.

    The same belief is often re-proposed on successive days; promoting a
    duplicate wastes the reviewer's attention and inflates the backlog.
    """
    seen: dict[tuple, dict] = {}
    dropped = 0
    for item in items:
        key = _key(item)
        if key in seen:
            seen[key]["also_seen"].append(item["day"])
            dropped += 1
            continue
        seen[key] = {**item, "also_seen": []}
    return list(seen.values()), dropped


def is_mechanical(item: dict) -> bool:
    """A one-line per-ticker stance readout rather than a belief."""
    body = [line for line in item["body"] if line.strip()]
    return len(body) == 1 and bool(MECHANICAL_READOUT.match(body[0].strip()))


# --------------------------------------------------------------------------- #
# decision ledger
# --------------------------------------------------------------------------- #

def load_ledger() -> dict:
    if not LEDGER.is_file():
        return {"version": 1, "updated": None, "cadence": "monthly", "decisions": {}}
    data = json.loads(LEDGER.read_text(encoding="utf-8"))
    data.setdefault("decisions", {})
    return data


def save_ledger(ledger: dict) -> None:
    ledger["updated"] = date.today().isoformat()
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")


def record(ledger: dict, item: dict, decision: str, reason: str, by: str,
           when: str, anchor: str | None = None, quiet: bool = False,
           previous: dict | None = None) -> bool:
    """Write one decision. Returns False when the id was already decided.

    The ledger is append-only: a decided id is never overwritten in place, so
    re-ticking a row to *reverse* a decision does nothing. That used to be
    silent — the run reported "0 new" and the reviewer had no way to tell a
    duplicate tick from a rejected reversal. Say so out loud instead. Bulk paths
    pass `quiet=True`, because they walk every proposal and most are decided.

    Re-deciding therefore means *deleting* the id and writing it again, which
    destroys the row that was there. `previous` carries that destroyed row
    forward as a structured `previous_decision` field, so a reversal is a fact
    on the row rather than a sentence someone happened to write in `reason`.
    The ledger is untracked by git, so nothing else remembers it.
    """
    ident = fingerprint(item)
    prior = ledger["decisions"].get(ident)
    if prior is not None:
        if not quiet and prior.get("decision") != decision:
            print(f"  [warn] {ident} is already recorded as "
                  f"'{prior.get('decision')}' ({prior.get('date')}, by "
                  f"{prior.get('by')}); the ledger is append-only, so "
                  f"'{decision}' was NOT applied. To reverse a decision, delete "
                  f"the id from {LEDGER.name} and re-run.")
        return False
    entry = {
        "decision": decision,
        "date": when,
        "by": by,
        "lens": item["lens"],
        "reason": reason,
        "first_seen": item["day"],
        "excerpt": " ".join(item["body"])[:160],
    }
    if anchor:
        # Where the belief landed, so `promoted` is checkable against MEMORY.md.
        entry["memory_anchor"] = anchor
    if previous:
        # The decision this row replaced, structurally, not as prose.
        entry["previous_decision"] = previous
    ledger["decisions"][ident] = entry
    return True


def _normalize(text: str) -> str:
    """Strip markdown emphasis and a trailing source citation for matching."""
    text = re.sub(r"`[^`]*`", " ", text)
    text = text.replace("**", "").replace("*", "")
    text = re.sub(r"[^a-z0-9 ]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def already_in_memory(item: dict, memory_text: str) -> bool:
    """True when this proposal's text is already a promoted belief.

    Items promoted in May 2026 were still unticked in the August queue. Matching
    on a 60-character normalized prefix is deliberately strict: a near-miss stays
    in the queue rather than being silently suppressed.
    """
    body = _normalize(" ".join(item["body"]))
    if len(body) < 60:
        return False
    return body[:60] in memory_text


ANCHOR_QUOTE = re.compile(r'"([^"]{8,})"')


def audit_promoted(ledger: dict, by_id: dict[str, dict],
                   raw_memory: str) -> list[tuple[str, dict, str]]:
    """Promoted ids with nothing corresponding in MEMORY.md.

    `promoted` suppresses a proposal from every future build, so it has to be
    checkable or it is just a silent delete. A promoted row passes when either
    its text is findable in MEMORY.md, or it carries a `memory_anchor` naming
    the belief that absorbed it — proposals are merged before promotion, so a
    merged one will not match on text. Anything else was never written down
    anywhere and belongs in `dropped` or `rejected`, with a reason.

    An anchor is only worth having if it can go stale loudly, so any phrase the
    anchor puts in double quotes must still appear in MEMORY.md verbatim. Edit
    the belief out and the anchor breaks here rather than rotting unnoticed.

    **A bare path is not an anchor.** `--sync-promoted-from-memory` stamped 21
    backfill rows with `memory_anchor: "_system/memory/MEMORY.md"`, which every
    belief in the file satisfies trivially: the audit short-circuited on the
    field being *set*, so deleting a belief outright left the orphan count
    unchanged and those rows were checked *less* than before the field existed.
    An anchor with no double-quoted phrase names nothing, so it is skipped and
    the row falls through to the text check it would otherwise have had.
    """
    normalized = _normalize(raw_memory)
    orphans: list[tuple[str, dict, str]] = []
    for ident, entry in sorted(ledger.get("decisions", {}).items()):
        if entry.get("decision") != "promoted":
            continue
        anchor = entry.get("memory_anchor")
        quotes = ANCHOR_QUOTE.findall(anchor or "")
        if quotes:
            missing = [q for q in quotes if q not in raw_memory]
            if missing:
                orphans.append((ident, entry,
                                f"anchor quotes not in MEMORY.md: {missing[0]!r}"))
            continue
        item = by_id.get(ident)
        if item is not None and already_in_memory(item, normalized):
            continue
        orphans.append((ident, entry,
                        "anchor names no belief (no quoted phrase) and the text "
                        "is not in MEMORY.md" if anchor else
                        "no matching belief and no memory_anchor"))
    return orphans


# --------------------------------------------------------------------------- #
# render
# --------------------------------------------------------------------------- #

def render(items: list[dict], dropped: int, since: str | None,
           ledger: dict | None = None) -> str:
    by_lens: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        by_lens[item["lens"]].append(item)

    decisions = (ledger or {}).get("decisions", {})
    counts: dict[str, int] = defaultdict(int)
    for entry in decisions.values():
        counts[entry.get("decision", "?")] += 1

    out: list[str] = [
        "# Memory promotion queue",
        "",
        f"Generated by `build_memory_triage.py` on {date.today().isoformat()}"
        + (f", covering daily logs from {since}." if since else "."),
        "",
        f"**{len(items)} undecided proposals** across {len(by_lens)} lens(es); "
        f"{dropped} duplicate sighting(s) collapsed.",
        "",
    ]
    if decisions:
        out += [
            f"Suppressed by `_system/memory/triage_ledger.json`: "
            f"**{counts.get('promoted', 0)} promoted**, "
            f"**{counts.get('rejected', 0)} rejected**, "
            f"**{counts.get('dropped', 0)} dropped** (decided, but no belief "
            "claimed) — already decided, so they do not re-surface. Delete an id "
            "from the ledger, or rebuild with `--show-decided`, to bring one back. "
            "Check that `promoted` means what it says with `--audit-promoted`.",
            "",
        ]
    out += [
        "Tick an item `- [x]` to promote it, or `- [-]` to reject it, then run",
        "`python _system/scripts/build_memory_triage.py --ingest` to record both in",
        "the ledger. Promoted items still have to be written into",
        "`_system/memory/MEMORY.md` by hand, under the matching lens.",
        "",
        "Nothing in this file has been promoted. Only a human promotes — an agent may",
        "run a promotion pass when the human asks for one in that session, and marks",
        "each belief as agent-promoted. See the header of `MEMORY.md`.",
        "",
        "Cadence: rebuild monthly, and after every promotion pass.",
        "",
    ]
    for lens in sorted(by_lens, key=lambda k: (-len(by_lens[k]), k)):
        rows = sorted(by_lens[lens], key=lambda r: r["day"], reverse=True)
        out.append(f"## {lens} ({len(rows)})")
        out.append("")
        for row in rows:
            mark = "x" if row.get("_decision") == "promoted" else (
                "-" if row.get("_decision") == "rejected" else " ")
            head = f"- [{mark}] **{row['day']}**"
            if row["title"]:
                head += f" — {row['title']}"
            out.append(head)
            for line in row["body"][:6]:
                out.append(f"      {line}")
            if row["also_seen"]:
                extra = ", ".join(sorted(set(row["also_seen"]))[:5])
                out.append(f"      *(also proposed {len(row['also_seen'])}× — {extra})*")
            out.append(f"      `{row['file']}` · `{fingerprint(row)}`")
            out.append("")
    return "\n".join(out) + "\n"


def ingest(path: Path) -> dict[str, str]:
    """Read `- [x]` / `- [-]` ticks out of a rendered queue, keyed by item id."""
    marks: dict[str, str] = {}
    pending: str | None = None
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        start = ROW_START.match(raw.strip())
        if start:
            mark = start.group(1).strip().lower()
            pending = {"x": "promoted", "-": "rejected", "r": "rejected"}.get(mark)
            continue
        found = ROW_ID.search(raw.strip())
        if found and pending:
            marks[found.group(1)] = pending
            pending = None
    return marks


# --------------------------------------------------------------------------- #

def collect(since: str | None) -> tuple[list[dict], int]:
    items: list[dict] = []
    for path in sorted(DAILY.glob("*.md")):
        day = DATED.search(path.name)
        if since and day and day.group(1) < since:
            continue
        items.extend(parse_file(path))
    return dedupe(items)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--since", help="only daily logs on/after this YYYY-MM-DD")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--show-decided", action="store_true",
                    help="include items already recorded in the ledger")
    ap.add_argument("--mark", choices=DECISIONS,
                    help="record a decision for --ids and exit")
    ap.add_argument("--ids", help="comma-separated item ids, or @path to a file of ids")
    ap.add_argument("--reason", default="", help="why, recorded in the ledger")
    ap.add_argument("--by", default="human", help="who decided (human / agent)")
    ap.add_argument("--anchor",
                    help="with --mark promoted: where the belief landed in "
                         "MEMORY.md, so the decision is checkable")
    ap.add_argument("--previous-decision", metavar="JSON",
                    help="with --mark, after deleting an id to re-decide it: the "
                         "row that was deleted, as JSON (e.g. '{\"decision\": "
                         "\"promoted\", \"date\": \"2026-08-09\", \"by\": "
                         "\"agent\"}'). Recorded as `previous_decision` so the "
                         "reversal is structured, not prose in --reason")
    ap.add_argument("--ingest", nargs="?", const=str(DEFAULT_OUT), metavar="PATH",
                    help="read [x]/[-] ticks from a rendered queue into the ledger")
    ap.add_argument("--auto-reject-mechanical", action="store_true",
                    help="reject one-line per-ticker stance readouts as a class")
    ap.add_argument("--sync-promoted-from-memory", action="store_true",
                    help="back-mark proposals whose text is already a belief in "
                         f"MEMORY.md (stamped by={BACKFILL_BY!r}, not --by)")
    ap.add_argument("--audit-promoted", action="store_true",
                    help="list promoted ids with no matching belief in MEMORY.md")
    args = ap.parse_args(argv)

    if not DAILY.is_dir():
        print(f"no daily log directory at {DAILY}")
        return 1

    items, dropped = collect(args.since)
    if not items:
        print("no [PROPOSED] blocks found")
        return 0
    by_id = {fingerprint(item): item for item in items}
    ledger = load_ledger()
    today = date.today().isoformat()

    previous_decision: dict | None = None
    if args.previous_decision:
        try:
            previous_decision = json.loads(args.previous_decision)
        except json.JSONDecodeError as exc:
            print(f"--previous-decision is not valid JSON: {exc}")
            return 1
        if not isinstance(previous_decision, dict):
            print("--previous-decision must be a JSON object")
            return 1
        previous_decision.setdefault("reversed_on", today)
        previous_decision.setdefault("reversed_by", args.by)

    if args.mark:
        raw = args.ids or ""
        if raw.startswith("@"):
            raw = Path(raw[1:]).read_text(encoding="utf-8")
        wanted = [i.strip() for i in re.split(r"[,\s]+", raw) if i.strip()]
        if not wanted:
            print("--mark needs --ids")
            return 1
        written = missing = skipped = refused = 0
        for ident in wanted:
            item = by_id.get(ident)
            if item is None:
                print(f"  [warn] unknown id {ident}")
                missing += 1
                continue
            prior = ledger["decisions"].get(ident)
            # A prior decision that *disagrees* is a refused reversal, not a
            # duplicate tick. It used to be counted as "already decided" and the
            # run still exited 0, so a caller could not tell the ledger had
            # ignored it.
            if prior is not None and prior.get("decision") != args.mark:
                refused += 1
            if record(ledger, item, args.mark, args.reason, args.by, today,
                      anchor=args.anchor, previous=previous_decision):
                written += 1
            else:
                skipped += 1
        save_ledger(ledger)
        print(f"[ok] {written} marked {args.mark}, {skipped} already decided, "
              f"{missing} unknown")
        if refused:
            print(f"  [warn] {refused} id(s) already carry a DIFFERENT decision "
                  f"and were NOT changed - the ledger is append-only. Delete "
                  f"those ids from {LEDGER.name} and re-run with "
                  f"--previous-decision to record the reversal.")
        return 1 if (missing or refused) else 0

    if args.ingest:
        marks = ingest(Path(args.ingest))
        written = missing = skipped = conflicts = 0
        for ident, decision in marks.items():
            item = by_id.get(ident)
            if item is None:
                missing += 1
                continue
            prior = ledger["decisions"].get(ident)
            if prior is not None and prior.get("decision") != decision:
                conflicts += 1
            if record(ledger, item, decision, args.reason or "ingested from queue ticks",
                      args.by, today, anchor=args.anchor):
                written += 1
            else:
                skipped += 1
        save_ledger(ledger)
        print(f"[ok] ingested {len(marks)} tick(s): {written} new, "
              f"{skipped} already decided, {missing} unknown")
        if conflicts:
            # The reversal case: a tick that disagrees with the recorded
            # decision. Append-only, so nothing changed - do not let that pass
            # as "0 new".
            print(f"  [warn] {conflicts} tick(s) disagreed with an existing "
                  f"decision and were NOT applied (see the warnings above). "
                  f"Delete those ids from {LEDGER.name} to re-decide them.")
        return 0

    if args.auto_reject_mechanical:
        reason = args.reason or (
            "per-ticker stance readout from a scoring run - a dated observation of "
            "model output, not a belief")
        written = 0
        for item in items:
            if is_mechanical(item) and record(ledger, item, "rejected", reason,
                                              args.by, today, quiet=True):
                written += 1
        save_ledger(ledger)
        print(f"[ok] {written} mechanical readout(s) recorded as rejected")
        return 0

    if args.sync_promoted_from_memory:
        if not MEMORY.is_file():
            print(f"no MEMORY.md at {MEMORY}")
            return 1
        memory_text = _normalize(MEMORY.read_text(encoding="utf-8", errors="replace"))
        reason = args.reason or "text already present in MEMORY.md"
        written = 0
        for item in items:
            # `BACKFILL_BY`, not `args.by`: this path observes a belief that is
            # already promoted, it does not promote one. See BACKFILL_BY.
            if already_in_memory(item, memory_text) and record(
                    ledger, item, "promoted", reason, BACKFILL_BY, today,
                    anchor=str(MEMORY.relative_to(ROOT)).replace("\\", "/"),
                    quiet=True):
                written += 1
        save_ledger(ledger)
        print(f"[ok] {written} proposal(s) matched to existing beliefs in MEMORY.md")
        print(f"  recorded as promoted by '{BACKFILL_BY}' - these are pre-existing")
        print("  beliefs being back-marked, not decisions made by this run")
        return 0

    if args.audit_promoted:
        if not MEMORY.is_file():
            print(f"no MEMORY.md at {MEMORY}")
            return 1
        raw_memory = MEMORY.read_text(encoding="utf-8", errors="replace")
        orphans = audit_promoted(ledger, by_id, raw_memory)
        promoted = sum(1 for e in ledger["decisions"].values()
                       if e.get("decision") == "promoted")
        print(f"[audit] {promoted} promoted, {len(orphans)} not checkable "
              f"against MEMORY.md")
        for ident, entry, why in orphans:
            print(f"  {ident}  {entry.get('lens', '?'):8} "
                  f"{entry.get('first_seen', '?')}  {why}")
            print(f"      {entry.get('excerpt', '')[:100]}")
        if orphans:
            print("\n  Each of these suppresses a proposal forever while claiming a")
            print("  belief that is not in MEMORY.md. Give it a --anchor, or delete")
            print(f"  the id from {LEDGER.name} and re-decide it as dropped/rejected.")
        return 1 if orphans else 0

    decisions = ledger["decisions"]
    if args.show_decided:
        for ident, item in by_id.items():
            if ident in decisions:
                item["_decision"] = decisions[ident]["decision"]
        queue = items
    else:
        queue = [item for item in items if fingerprint(item) not in decisions]

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render(queue, dropped, args.since, ledger), encoding="utf-8")

    suppressed = len(items) - len(queue)
    try:
        shown = out_path.resolve().relative_to(ROOT)
    except ValueError:  # --out pointed outside the repo
        shown = out_path
    print(f"[ok] {shown}")
    print(f"  {len(queue)} undecided proposals, {dropped} duplicate sighting(s) collapsed")
    if suppressed:
        print(f"  {suppressed} suppressed by the ledger (already decided)")
    lenses: dict[str, int] = defaultdict(int)
    for item in queue:
        lenses[item["lens"]] += 1
    for lens, count in sorted(lenses.items(), key=lambda kv: -kv[1]):
        print(f"    {lens:14} {count}")
    print("\n  Nothing promoted - MEMORY.md promotion is a separate, recorded pass.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
