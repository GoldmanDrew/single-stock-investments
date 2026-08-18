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
Decided items are excluded from the next build; no history is deleted.
Disposition changes are appended to `_system/memory/triage_events.jsonl`; the JSON ledger is
a current-state projection. Pass `--show-decided` to inspect handled proposals.

It does **not** promote anything into MEMORY.md. Promotion is the human owner's;
an agent may run a promotion pass only when the human asks for one in that
session, and every agent-promoted belief is stamped as such in MEMORY.md.

Cadence: rebuild daily (and after any promotion pass), then record decisions
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

  # reverse a decision without deleting history
  python _system/scripts/build_memory_triage.py --mark rejected --ids c79e14f64cfc \
      --reason "contradicts a promoted belief" --reverse

  # check every `promoted` id still corresponds to a belief in MEMORY.md
  python _system/scripts/build_memory_triage.py --audit-promoted
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[2]
DAILY = ROOT / "_system" / "memory" / "daily"
MEMORY = ROOT / "_system" / "memory" / "MEMORY.md"
LEDGER = ROOT / "_system" / "memory" / "triage_ledger.json"
DEFAULT_OUT = ROOT / "_system" / "reviews" / "pending" / "memory_triage.md"
SUMMARY_OUT = ROOT / "_system" / "reviews" / "pending" / "memory_triage_summary.json"

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
DECISIONS = ("promoted", "routed", "rejected", "dropped")
KINDS = ("durable_belief", "company_observation", "process_learning",
         "ephemeral_output", "parse_artifact")
TICKER_PREFIX = re.compile(r"^(?:\*\*)?([A-Z0-9][A-Z0-9.\-]{0,11})(?:\*\*)?\s*[:\-]")
TICKER_CITATION = re.compile(r"`([A-Z0-9][A-Z0-9.\-]{0,11})/")

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
    inline: dict | None = None

    def finish(value: dict | None) -> None:
        if value and value["body"]:
            items.append(value)
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.rstrip()
        match = HEADING.match(line.strip())
        if match:
            finish(inline)
            inline = None
            finish(current)
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
            finish(inline)
            inline = {
                "lens": (bullet.group(1) or "").strip() or "GENERIC",
                "title": "",
                "day": day.group(1) if day else path.stem,
                "file": path.name,
                "body": [bullet.group(2).strip()],
            }
            current = None
            continue
        if inline is not None:
            if line.startswith((" ", "\t")) and line.strip():
                inline["body"].append(line.strip())
                continue
            finish(inline)
            inline = None
        if current is None:
            continue
        # A non-PROPOSED heading closes the block.
        if ANY_HEADING.match(line):
            finish(current)
            current = None
            continue
        if line.strip():
            current["body"].append(line.strip())
    finish(current)
    finish(inline)
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


def proposal_kind(item: dict) -> str:
    """Classify retention needs without making a promotion judgement."""
    body = " ".join(item.get("body") or []).strip()
    normalized = re.sub(r"\s+", " ", body.lower()).strip()
    title = str(item.get("title") or "").lower()
    if (normalized in {"---", "--", "status: promoted", "status promoted"}
            or normalized.startswith("status: promoted ")
            or normalized.startswith("--- | prior dive")
            or "run summary" in title
            or re.match(r"^(?:run|contract run)\s+(?:complete|summary|receipt)\b", normalized)):
        return "parse_artifact"
    if is_mechanical(item) or any(token in normalized for token in (
            "dashboard build complete", "batch run complete", "receipt written")):
        return "ephemeral_output"
    lens = str(item.get("lens") or "").upper()
    if lens == "COMPANY" or TICKER_PREFIX.match(body):
        return "company_observation"
    if lens in {"MEMORY", "SYSTEM", "PROCESS", "OPS", "WORKFLOW"}:
        return "process_learning"
    return "durable_belief"


def route_destination(item: dict, kind: str) -> str | None:
    if kind == "company_observation":
        body = " ".join(item.get("body") or []).strip()
        match = TICKER_PREFIX.match(body) or TICKER_CITATION.search(body)
        ticker = match.group(1).upper() if match else body.split(" ", 1)[0].upper()
        if ticker and (ROOT / ticker / "research").is_dir():
            return f"{ticker}/research"
        # The routed row stores full content in this ledger. This honest
        # fallback is preferable to inventing a ticker or pointing at a
        # directory that does not exist.
        return "_system/memory/triage_ledger.json"
    if kind == "process_learning":
        return "_system/memory/corrections.md"
    return None


# --------------------------------------------------------------------------- #
# decision ledger
# --------------------------------------------------------------------------- #

def load_ledger() -> dict:
    events_path = LEDGER.with_name("triage_events.jsonl")
    if events_path.is_file():
        decisions = {}
        for line in events_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("proposal_id") and isinstance(event.get("decision"), dict):
                decisions[str(event["proposal_id"])] = event["decision"]
        return {"version": 2, "updated": None, "cadence": "weekly",
                "authority": "projection_of_triage_events_jsonl", "decisions": decisions}
    if not LEDGER.is_file():
        return {"version": 2, "updated": None, "cadence": "weekly", "decisions": {}}
    data = json.loads(LEDGER.read_text(encoding="utf-8"))
    data.setdefault("decisions", {})
    return data


def save_ledger(ledger: dict) -> None:
    events_path = LEDGER.with_name("triage_events.jsonl")
    known = set()
    if events_path.exists():
        for line in events_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    known.add(json.loads(line).get("event_id"))
                except json.JSONDecodeError:
                    continue
    events_path.parent.mkdir(parents=True, exist_ok=True)
    with events_path.open("a", encoding="utf-8") as handle:
        for proposal_id, decision in sorted((ledger.get("decisions") or {}).items()):
            raw = json.dumps({"proposal_id": proposal_id, "decision": decision},
                             sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            event_id = hashlib.sha256(raw.encode()).hexdigest()[:24]
            if event_id in known:
                continue
            handle.write(json.dumps({
                "event_id": event_id, "proposal_id": proposal_id,
                "event_type": "disposition_recorded",
                "recorded_on": decision.get("date"), "decision": decision,
            }, sort_keys=True, ensure_ascii=False) + "\n")
            known.add(event_id)
    ledger["version"] = 2
    ledger["authority"] = "projection_of_triage_events_jsonl"
    ledger["updated"] = date.today().isoformat()
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")


def record(ledger: dict, item: dict, decision: str, reason: str, by: str,
           when: str, anchor: str | None = None, quiet: bool = False,
           previous: dict | None = None, reason_code: str | None = None,
           destination: str | None = None) -> bool:
    """Write one current decision; the event log preserves explicit reversals."""
    ident = fingerprint(item)
    prior = ledger["decisions"].get(ident)
    if prior is not None and previous is None:
        if not quiet and prior.get("decision") != decision:
            print(f"  [warn] {ident} is already recorded as "
                  f"'{prior.get('decision')}' ({prior.get('date')}, by "
                  f"{prior.get('by')}); the ledger is append-only, so "
                  f"'{decision}' was NOT applied. Re-run with --reverse to "
                  "append a reversal event.")
        return False
    if decision == "routed" and not (destination or route_destination(item, proposal_kind(item))):
        raise ValueError("routed decisions require a deterministic destination")
    entry = {
        "decision": decision,
        "date": when,
        "by": by,
        "lens": item["lens"],
        "reason": reason,
        "first_seen": item["day"],
        "excerpt": " ".join(item["body"])[:160],
        "kind": proposal_kind(item),
        "reason_code": reason_code or "manual_disposition",
        "source_ref": f"_system/memory/daily/{item['file']}",
    }
    if decision == "routed":
        entry["destination"] = destination or route_destination(item, entry["kind"])
        entry["content"] = "\n".join(item["body"])
        entry["delivery_status"] = "pending"
        entry["delivery_acknowledged_at"] = None
        entry["applied_ref"] = None
    if anchor:
        # Where the belief landed, so `promoted` is checkable against MEMORY.md.
        entry["memory_anchor"] = anchor
    if previous:
        # The decision this row replaced, structurally, not as prose.
        entry["previous_decision"] = previous
        entry["supersedes_decision"] = prior
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
            f"**{counts.get('routed', 0)} routed**, "
            f"**{counts.get('rejected', 0)} rejected**, "
            f"**{counts.get('dropped', 0)} dropped** (decided, but no belief "
            "claimed) — already decided, so they do not re-surface. Delete an id "
            "with `--reverse`, or rebuild with `--show-decided` to inspect it. "
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
        "Cadence: rebuild daily, and after every promotion pass.",
        "",
    ]
    for lens in sorted(by_lens, key=lambda k: (-len(by_lens[k]), k)):
        rows = sorted(by_lens[lens], key=lambda r: r["day"], reverse=True)
        out.append(f"## {lens} ({len(rows)})")
        out.append("")
        for row in rows:
            mark = {"promoted": "x", "routed": ">", "rejected": "-",
                    "dropped": "d"}.get(row.get("_decision"), " ")
            head = f"- [{mark}] **{row['day']}**"
            if row["title"]:
                head += f" — {row['title']}"
            head += f" · `{proposal_kind(row)}`"
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
            pending = {"x": "promoted", ">": "routed", "-": "rejected",
                       "r": "rejected", "d": "dropped"}.get(mark)
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


def build_learning_loop_summary(items: list[dict], ledger: dict,
                                duplicate_sightings: int) -> dict:
    from falsifier_specs import calibration_eligibility, spec_payload_hash
    today = date.today()
    decisions = ledger.get("decisions") or {}
    undecided = [item for item in items if fingerprint(item) not in decisions]
    ages = [(today - date.fromisoformat(item["day"])).days for item in undecided]
    kinds: dict[str, int] = defaultdict(int)
    for item in undecided:
        kinds[proposal_kind(item)] += 1
    disposition_counts: dict[str, int] = defaultdict(int)
    closed_7d = 0
    for entry in decisions.values():
        disposition_counts[str(entry.get("decision") or "unknown")] += 1
        try:
            closed_7d += date.fromisoformat(str(entry.get("date"))[:10]) >= today - timedelta(days=7)
        except ValueError:
            pass
    intake_7d = sum(1 for item in items
                    if date.fromisoformat(item["day"]) >= today - timedelta(days=7))

    outcome_path = ROOT / "_system/research/falsifier_outcomes.jsonl"
    outcomes = []
    if outcome_path.exists():
        for line in outcome_path.read_text(encoding="utf-8").splitlines():
            try:
                outcomes.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    resolved_hashes = {row.get("spec_hash") for row in outcomes if row.get("spec_hash")}
    forecast = {"specs": 0, "v2_specs": 0, "testable": 0, "matured": 0,
                "calibration_eligible": 0, "diagnostic_only": 0,
                "resolved": len(outcomes), "pending_evidence": 0, "overdue": 0}
    for path in ROOT.glob("*/research/falsifier_specs.json"):
        try:
            specs = json.loads(path.read_text(encoding="utf-8")).get("specs") or []
        except (OSError, json.JSONDecodeError):
            continue
        for spec in specs:
            forecast["specs"] += 1
            forecast["v2_specs"] += bool(spec.get("spec_id"))
            if spec.get("untestable"):
                continue
            forecast["testable"] += 1
            if calibration_eligibility(spec)[0]:
                forecast["calibration_eligible"] += 1
            else:
                forecast["diagnostic_only"] += 1
            observable = str(spec.get("observable_after") or spec.get("due") or "")[:10]
            deadline = str(spec.get("resolution_deadline") or spec.get("due") or "")[:10]
            if observable and observable <= today.isoformat():
                forecast["matured"] += 1
                if spec_payload_hash(spec) not in resolved_hashes:
                    if deadline and deadline < today.isoformat():
                        forecast["overdue"] += 1
                    else:
                        forecast["pending_evidence"] += 1

    pending_owner = 0
    for committee_path in ROOT.glob("*/research/committee_????-??-??.json"):
        try:
            committee = json.loads(committee_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if committee.get("final_state") != "committee_complete_decision_pending":
            continue
        owner = committee_path.parent / "human_decision.json"
        decision = json.loads(owner.read_text(encoding="utf-8")) if owner.exists() else {}
        if decision.get("status") != "decided":
            pending_owner += 1
    committee_outcomes_path = ROOT / "_system/research/committee_outcomes.jsonl"
    committee_outcome_count = 0
    if committee_outcomes_path.exists():
        committee_outcome_count = sum(
            1 for line in committee_outcomes_path.read_text(encoding="utf-8").splitlines()
            if line.strip())
    try:
        git_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                  text=True, capture_output=True,
                                  check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        git_head = ""
    ssi_queue_path = ROOT / "_eval/ssi_adjudication_queue.json"
    ssi_queue = json.loads(ssi_queue_path.read_text(encoding="utf-8")) \
        if ssi_queue_path.exists() else {}
    return {
        "schema_version": "1.0",
        "as_of": today.isoformat(),
        "git_head": git_head,
        "forecast_loop": forecast,
        "decision_loop": {"pending_owner_decisions": pending_owner,
                          "resolved_committee_outcomes": committee_outcome_count},
        "proposal_loop": {
            "total_unique": len(items), "undecided": len(undecided),
            "undecided_by_kind": dict(sorted(kinds.items())),
            "duplicate_sightings": duplicate_sightings,
            "dispositions": dict(sorted(disposition_counts.items())),
            "intake_last_7d": intake_7d, "closures_last_7d": closed_7d,
            "oldest_undecided_days": max(ages, default=0),
            "over_30_days": sum(age > 30 for age in ages),
            "p90_age_days": sorted(ages)[min(len(ages) - 1, int(len(ages) * .9))]
            if ages else 0,
            "sla": {"deterministic_disposition_days": 7,
                    "durable_human_decision_days": 30,
                    "target_p90_days": 14},
            "routed_delivery_pending": sum(
                entry.get("decision") == "routed"
                and entry.get("delivery_status") != "acknowledged"
                for entry in decisions.values()),
            "routed_delivery_acknowledged": sum(
                entry.get("decision") == "routed"
                and entry.get("delivery_status") == "acknowledged"
                for entry in decisions.values()),
            "ledger_authority": ledger.get("authority") or "legacy_projection",
        },
        "calibration": {
            "falsifier": json.loads((ROOT / "_system/research/falsifier_calibration.json").read_text(encoding="utf-8"))
            if (ROOT / "_system/research/falsifier_calibration.json").exists() else {},
            "committee": json.loads((ROOT / "_system/research/committee_calibration.json").read_text(encoding="utf-8"))
            if (ROOT / "_system/research/committee_calibration.json").exists() else {},
        },
        "fast_feedback_loop": {
            "gold_pending": ssi_queue.get("gold_pending_total", 0),
            "alerts_pending": ssi_queue.get("alerts_pending_total", 0),
            "weekly_sample_size": (len(ssi_queue.get("gold_sample") or [])
                                   + len(ssi_queue.get("alert_sample") or [])),
            "human_ground_truth_required": True,
            "service_level_days": ssi_queue.get("service_level_days", 7),
        },
    }


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
    ap.add_argument("--reason-code", default="manual_disposition",
                    help="stable machine-readable disposition reason")
    ap.add_argument("--destination",
                    help="existing ownership destination for a routed item")
    ap.add_argument("--by", default="human", help="who decided (human / agent)")
    ap.add_argument("--anchor",
                    help="with --mark promoted: where the belief landed in "
                         "MEMORY.md, so the decision is checkable")
    ap.add_argument("--reverse", action="store_true",
                    help="with --mark, append a reversal of an existing decision")
    ap.add_argument("--previous-decision", metavar="JSON", help=argparse.SUPPRESS)
    ap.add_argument("--migrate-ledger", action="store_true",
                    help="append legacy ledger rows to the event log and refresh the projection")
    ap.add_argument("--ingest", nargs="?", const=str(DEFAULT_OUT), metavar="PATH",
                    help="read [x]/[-] ticks from a rendered queue into the ledger")
    ap.add_argument("--auto-reject-mechanical", action="store_true",
                    help="reject one-line per-ticker stance readouts as a class")
    ap.add_argument("--auto-dispose-nondurable", action="store_true",
                    help="drop parse/ephemeral artifacts and route company observations")
    ap.add_argument("--repair-routes", action="store_true",
                    help="repair routed destination metadata without changing decisions")
    ap.add_argument("--ack-delivery", action="store_true",
                    help="acknowledge delivery for routed --ids")
    ap.add_argument("--applied-ref", help="artifact or receipt proving a routed item was consumed")
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

    if args.migrate_ledger:
        save_ledger(ledger)
        print(f"[ok] migrated {len(ledger['decisions'])} disposition(s) to append-only events")
        return 0

    legacy_previous = None
    if args.previous_decision:
        try:
            legacy_previous = json.loads(args.previous_decision)
        except json.JSONDecodeError as exc:
            print(f"--previous-decision is not valid JSON: {exc}")
            return 1
        if not isinstance(legacy_previous, dict):
            print("--previous-decision must be a JSON object")
            return 1
        legacy_previous.setdefault("reversed_on", today)
        legacy_previous.setdefault("reversed_by", args.by)

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
            if prior is not None and prior.get("decision") != args.mark and not args.reverse:
                refused += 1
            previous_decision = legacy_previous
            if prior is not None and prior.get("decision") != args.mark and args.reverse:
                previous_decision = dict(prior)
                previous_decision["reversed_on"] = today
                previous_decision["reversed_by"] = args.by
            if record(ledger, item, args.mark, args.reason, args.by, today,
                      anchor=args.anchor, previous=previous_decision,
                      reason_code=args.reason_code,
                      destination=args.destination):
                written += 1
            else:
                skipped += 1
        save_ledger(ledger)
        print(f"[ok] {written} marked {args.mark}, {skipped} already decided, "
              f"{missing} unknown")
        if refused:
            print(f"  [warn] {refused} id(s) already carry a DIFFERENT decision "
                  "and were NOT changed. Re-run with --reverse to append "
                  "the reversal without deleting history.")
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
                      args.by, today, anchor=args.anchor,
                      reason_code=args.reason_code,
                      destination=args.destination):
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
                  "decision and were NOT applied (see the warnings above). "
                  "Use --mark with --reverse to append a reversal.")
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

    if args.auto_dispose_nondurable:
        counts: dict[str, int] = defaultdict(int)
        for item in items:
            kind = proposal_kind(item)
            if kind in {"parse_artifact", "ephemeral_output"}:
                decision, code = "dropped", f"non_durable_{kind}"
                reason = "deterministic non-durable output; retained in source log, excluded from belief review"
                destination = None
            elif kind == "company_observation":
                decision, code = "routed", "company_observation_routed"
                reason = "company-specific observation routed to ticker research ownership"
                destination = route_destination(item, kind)
            else:
                continue
            if record(ledger, item, decision, reason, args.by, today,
                      quiet=True, reason_code=code, destination=destination):
                counts[decision] += 1
        save_ledger(ledger)
        print(f"[ok] nondurable backfill: {counts['routed']} routed, "
              f"{counts['dropped']} dropped; durable/process proposals untouched")
        return 0

    if args.repair_routes:
        repaired = 0
        for ident, entry in ledger["decisions"].items():
            if entry.get("decision") != "routed" or ident not in by_id:
                continue
            destination = route_destination(by_id[ident], entry.get("kind") or
                                            proposal_kind(by_id[ident]))
            if destination and destination != entry.get("destination"):
                entry.setdefault("routing_history", []).append({
                    "destination": entry.get("destination"),
                    "superseded_on": today,
                })
                entry["destination"] = destination
                entry["routing_repaired_on"] = today
                repaired += 1
        save_ledger(ledger)
        print(f"[ok] repaired {repaired} routed destination(s); decisions unchanged")
        return 0

    if args.ack_delivery:
        wanted = [i.strip() for i in re.split(r"[,\s]+", args.ids or "") if i.strip()]
        if not wanted or not args.applied_ref:
            print("--ack-delivery requires --ids and --applied-ref")
            return 1
        acknowledged = 0
        for ident in wanted:
            entry = ledger["decisions"].get(ident)
            if not entry or entry.get("decision") != "routed":
                print(f"  [warn] {ident} is not a routed decision")
                continue
            entry["delivery_status"] = "acknowledged"
            entry["delivery_acknowledged_at"] = today
            entry["applied_ref"] = args.applied_ref
            acknowledged += 1
        save_ledger(ledger)
        print(f"[ok] acknowledged delivery for {acknowledged} routed item(s)")
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
            print("  belief that is not in MEMORY.md. Give it a --anchor, or append")
            print("  a dropped/rejected reversal with --mark and --reverse.")
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
    summary = build_learning_loop_summary(items, ledger, dropped)
    SUMMARY_OUT.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_OUT.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")

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
