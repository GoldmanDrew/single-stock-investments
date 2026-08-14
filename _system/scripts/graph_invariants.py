#!/usr/bin/env python3
"""Executable health contract over the workspace graph (_system/graph/README.md).

Rebuilds ``_system/graph/graph.db`` via ``graph_build.build()`` (projection,
never a store), runs every invariant P1-P5 / E1-E6 as SQL and traversals over
the fresh database, writes ``_system/graph/INVARIANTS.md`` (small, diffable --
the committed artifact whose git history is the ratchet record) plus
``invariants.json`` next to it, and exits 1 iff any hard invariant has live
violations.

Honesty rules baked in (a validator must never look green on data it never saw):

  * E2 with zero typed falsifiers reports ``vacuously green (0 typed)``
    explicitly, and E3 with zero outcomes ``vacuously green (0 outcomes)`` --
    never a plain OK.
  * Severity demotions and per-violation waivers live in
    ``_system/graph/graph_sources.json`` under ``invariants``, each with a
    dated note, and are printed in the report -- never silent.
  * A waiver that matches no live violation is itself reported as stale
    (a waiver that cannot fire is a check that cannot fail, one level up).

Output is ASCII-only (Windows cp1252 console; the recorded trap).

Environment: ``GRAPH_LANE_REF`` -- git ref that ``graph_build`` projects lanes
and commits from (default HEAD). ``run()`` sets it to ``origin/main`` for the
duration of the build whenever that ref exists and the variable is not already
set, because P3 fires spuriously on PR checkouts whose branch point is older
than a lane's freshness window: the nightly lane commits land on main and are
absent from the PR head's own history. An explicitly set value is respected
untouched; the variable is unset again after the build so nothing leaks into
later builds against other roots.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(Path(__file__).resolve().parent))
import graph_build  # noqa: E402  (build(), norm_text, STATUS_TAG reuse)

VIOLATION_CAP = 20          # rows listed per invariant in both reports
E2_GRACE_DAYS = 14          # spec: outcome required within 14 days of due
E4_HISTORY_WINDOW = 15      # commits touching MEMORY.md the E4 baseline spans
LANE_REF_ENV = "GRAPH_LANE_REF"
RECEIPT_NAME = re.compile(r"(^|_)run_\d{4}-\d{2}-\d{2}")
PREV_ROW = re.compile(r"^\|\s*([PEL]\d)\s*\|[^|]*\|\s*(\d+)\s*\|")
TABLE_STATUS = re.compile(r"^`?(active|superseded|disproven)\s+\d{4}-\d{2}-\d{2}")

BASE_SEVERITY = {
    "P1": "report", "P2": "hard", "P3": "hard", "P4": "hard", "P5": "report",
    "P6": "hard", "P7": "report",
    "E1": "report", "E2": "hard", "E3": "hard", "E4": "hard", "E5": "hard",
    "E6": "report", "E7": "hard",
    # L-series: the classification/lens plane (spec in _system/graph/README.md).
    # All report severity with a committed baseline ratchet
    # (_system/graph/invariants_baseline.json): live counts at introduction
    # were far too large to gate hard without freezing the factory, so the
    # ratchet makes any RISE fail CI while the debt is worked down.
    "L1": "report", "L2": "report", "L3": "report", "L4": "report",
    "L5": "report", "L6": "report",
}

TITLES = {
    "P1": "every Correction has a GUARDED_BY path",
    "P2": "every Guard reaches a CIJob via ENFORCED_BY -> INVOKED_BY",
    "P3": "every active Lane has a Commit inside its freshness window",
    "P4": "no run receipts outside _system/data/runs/",
    "P5": "validator scripts with zero CI references",
    "E1": "decision-grade components carrying a typed falsifier",
    "E2": "matured typed falsifiers resolved by their terminal deadline",
    "E3": "every Outcome has a SCORES edge and a calibration bucket",
    "E4": "no promoted Belief text rewritten in place (vs git HEAD +"
          " history window)",
    "E5": "every Belief's SUPPORTED_BY source exists on disk",
    "E6": "Proposals with no DECIDED_AS decision (silent-drop detector)",
    "E7": "non-durable proposals never enter belief review; prospective decisions close within 30 days",
    "P6": "every registered data feed is fresher than its window",
    "P7": "every registered live feed has published inside its window",
    "L1": "every valued ticker resolves a payoff_lens through the"
          " classification chain",
    "L2": "classification surfaces agree (no shadowed classification)",
    "L3": "derived lens-plane artifacts are as fresh as their source"
          " valuation",
    "L4": "classification vocabulary is closed (criteria and data use"
          " canonical values; no lens narrower than its power zone)",
    "L5": "no lens consensus stance rests on fewer than 2 contributing"
          " personas",
    "L6": "persona registry, groups, and committee independence stay"
          " canonical",
}


def ascii_safe(text) -> str:
    return str(text if text is not None else "").encode(
        "ascii", "replace").decode("ascii")


class Result:
    def __init__(self, inv_id: str, count: int, violations: list[str],
                 note: str = ""):
        self.id = inv_id
        self.severity = BASE_SEVERITY[inv_id]      # effective; may be demoted
        self.base_severity = BASE_SEVERITY[inv_id]
        self.count = count                         # live violations
        self.violations = [ascii_safe(v) for v in violations]
        self.waived: list[str] = []
        self.note = ascii_safe(note)
        self.delta: str = "-"

    @property
    def status(self) -> str:
        return "VIOLATIONS" if self.count else "OK"


# --------------------------------------------------------------------------- #
# invariants
# --------------------------------------------------------------------------- #

def inv_p1(conn, root, today) -> Result:
    rows = conn.execute(
        "SELECT id FROM nodes WHERE type='Correction' AND id NOT IN"
        " (SELECT src FROM edges WHERE type='GUARDED_BY') ORDER BY id").fetchall()
    total = conn.execute(
        "SELECT COUNT(*) AS n FROM nodes WHERE type='Correction'").fetchone()["n"]
    return Result("P1", len(rows),
                  [r["id"][len("correction:"):] for r in rows],
                  note=f"{total - len(rows)}/{total} corrections guarded")


def inv_p2(conn, root, today) -> Result:
    violations = []
    for guard in conn.execute(
            "SELECT id FROM nodes WHERE type='Guard' ORDER BY id"):
        wired = conn.execute(
            "SELECT 1 FROM edges enf JOIN edges inv"
            " ON inv.src = enf.dst AND inv.type='INVOKED_BY'"
            " WHERE enf.src = ? AND enf.type='ENFORCED_BY' LIMIT 1",
            (guard["id"],)).fetchone()
        if not wired:
            enforcers = [r["dst"][len("validator:"):] for r in conn.execute(
                "SELECT dst FROM edges WHERE src=? AND type='ENFORCED_BY'"
                " ORDER BY dst", (guard["id"],))]
            violations.append(guard["id"][len("guard:"):] + " (enforcers: "
                              + (", ".join(enforcers) or "none") + ")")
    return Result("P2", len(violations), violations)


def inv_p3(conn, root, today) -> Result:
    now = datetime.now(timezone.utc)
    violations = []
    fresh = 0
    for lane in conn.execute("SELECT * FROM nodes WHERE type='Lane' ORDER BY id"):
        data = json.loads(lane["data_json"])
        window = data.get("freshness_hours", 48)
        last = data.get("last_commit_iso")
        if not last:
            violations.append(f"{lane['label']}: NO commit in the"
                              f" {graph_build.GIT_WINDOW}-commit window")
            continue
        age_h = (now - datetime.fromisoformat(last)).total_seconds() / 3600.0
        if age_h > window:
            violations.append(
                f"{lane['label']}: last commit {age_h:.1f}h old"
                f" (window {window}h)")
        else:
            fresh += 1
    return Result("P3", len(violations), violations,
                  note=f"{fresh} lanes fresh")


def inv_p4(conn, root, today) -> Result:
    """Filesystem scan, not a graph query: a receipt in the wrong place is
    exactly the file graph_build never projected as a Run."""
    violations = []
    for base in (root / "_system" / "reviews", root / "_system" / "data"):
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.json")):
            rel = path.relative_to(root).as_posix()
            if rel.startswith("_system/data/runs/"):
                continue
            receipt = RECEIPT_NAME.search(path.name) is not None
            if not receipt:
                payload = graph_build.load_json(path)
                receipt = (isinstance(payload, dict) and "stages" in payload
                           and ("scope" in payload or "dry_run" in payload))
            if receipt:
                violations.append(rel)
    return Result("P4", len(violations), violations,
                  note="scanned _system/reviews/ and _system/data/ (excl. runs/)")


def inv_p5(conn, root, today) -> Result:
    rows = conn.execute(
        "SELECT id FROM nodes WHERE type='Validator' AND id NOT IN"
        " (SELECT src FROM edges WHERE type='INVOKED_BY') ORDER BY id").fetchall()
    total = conn.execute(
        "SELECT COUNT(*) AS n FROM nodes WHERE type='Validator'").fetchone()["n"]
    return Result("P5", len(rows),
                  [r["id"][len("validator:"):] for r in rows],
                  note=f"{total - len(rows)}/{total} validators referenced by CI")


def inv_e1(conn, root, today) -> Result:
    """Count = decision-grade components WITHOUT a typed falsifier (the debt,
    so the ratchet can only shrink it). Note carries coverage % per method."""
    per_method: dict[str, list[int]] = {}   # method -> [typed, total]
    violations = []
    for comp in conn.execute(
            "SELECT c.id, c.data_json FROM nodes c"
            " JOIN nodes k ON k.id = 'contract:' || c.ticker"
            " WHERE c.type='Component' AND k.status='decision_grade'"
            " ORDER BY c.id"):
        method = json.loads(comp["data_json"]).get("method") or "(none)"
        typed = conn.execute(
            "SELECT 1 FROM edges e JOIN nodes f ON f.id=e.dst"
            " WHERE e.src=? AND e.type='ASSERTS' AND f.status='typed' LIMIT 1",
            (comp["id"],)).fetchone() is not None
        bucket = per_method.setdefault(method, [0, 0])
        bucket[1] += 1
        if typed:
            bucket[0] += 1
        else:
            violations.append(comp["id"][len("component:"):] + f" [{method}]")
    typed_total = sum(b[0] for b in per_method.values())
    total = sum(b[1] for b in per_method.values())
    pct = 100.0 * typed_total / total if total else 0.0
    # Per-method coverage, compressed so the report stays diffable: methods
    # with any typed coverage are named; the all-zero tail is one aggregate.
    covered = [(m, b) for m, b in sorted(per_method.items()) if b[0]]
    zeroed = [(m, b) for m, b in sorted(per_method.items()) if not b[0]]
    parts = [f"{m} {b[0]}/{b[1]}" for m, b in covered]
    if zeroed:
        parts.append(f"{len(zeroed)} methods 0/{sum(b[1] for _, b in zeroed)}")
    return Result("E1", len(violations), violations,
                  note=f"typed coverage {typed_total}/{total} ({pct:.1f}%)"
                       + (" -- " + "; ".join(parts) if parts else ""))


def _parse_due(due) -> date | None:
    """Tolerant ISO-date read of a spec's ``due``. Returns None on anything
    that is not a real calendar date -- '2026-06-31' (no June 31st),
    '2026-Q3', 'TBD'. The old strict parse crashed the whole suite (uncaught
    ValueError, no INVARIANTS.md written) on lexically-past garbage, and the
    lexical string comparison silently never matured lexically-future garbage."""
    try:
        return date.fromisoformat(str(due).strip()[:10])
    except (TypeError, ValueError):
        return None


def inv_e2(conn, root, today) -> Result:
    rows = conn.execute(
        "SELECT * FROM nodes WHERE type='Falsifier'"
        " AND status IN ('typed', 'invalid') ORDER BY id").fetchall()
    judged = []
    for row in rows:
        data = json.loads(row["data_json"] or "{}")
        errors = [str(err) for err in (data.get("validation_errors") or [])]
        due_broken = any("due" in err.lower() for err in errors)
        if row["status"] == "invalid" and not due_broken:
            continue
        judged.append((row, data))
    typed_n = sum(1 for row, _ in judged if row["status"] == "typed")
    if not judged:
        return Result("E2", 0, [], note="vacuously green (0 typed)")
    violations = []
    matured = 0
    for row, data in judged:
        due = data.get("observable_after") or data.get("due") or ""
        fid = row["id"][len("falsifier:"):]
        if not due:
            violations.append(fid + ": typed but no due date -- can never mature")
            continue
        due_date = _parse_due(due)
        if due_date is None:
            violations.append(
                f"{fid}: unparseable due '{ascii_safe(due)[:40]}'"
                " -- can never mature")
            continue
        if due_date > today:
            continue
        matured += 1
        explicit_deadline = _parse_due(data.get("resolution_deadline"))
        deadline = (explicit_deadline or
                    (due_date + timedelta(days=E2_GRACE_DAYS))).isoformat()
        outcome = conn.execute(
            "SELECT n.as_of FROM edges e JOIN nodes n ON n.id=e.dst"
            " WHERE e.src=? AND e.type='RESOLVED_BY' LIMIT 1",
            (row["id"],)).fetchone()
        if outcome is None:
            if today.isoformat() > deadline:
                violations.append(f"{fid}: due {due}, no outcome by {deadline}")
        elif outcome["as_of"] and str(outcome["as_of"])[:10] > deadline:
            violations.append(f"{fid}: due {due}, resolved late"
                              f" ({outcome['as_of']})")
    return Result("E2", len(violations), violations,
                  note=f"{typed_n} typed, {matured} matured")


def inv_e3(conn, root, today) -> Result:
    outcomes = conn.execute(
        "SELECT * FROM nodes WHERE type='Outcome' ORDER BY id").fetchall()
    if not outcomes:
        return Result("E3", 0, [], note="vacuously green (0 outcomes)")
    store = graph_build.load_json(
        root / "_system" / "research" / "falsifier_calibration.json")
    buckets = store.get("buckets", {}) if isinstance(store, dict) else {}
    violations = []
    for row in outcomes:
        oid = row["id"]
        bucket = conn.execute(
            "SELECT dst FROM edges WHERE src=? AND type='SCORES' LIMIT 1",
            (oid,)).fetchone()
        if bucket is None:
            violations.append(oid + ": no SCORES edge (missing"
                              " method_id/power_zone)")
            continue
        data = json.loads(row["data_json"])
        method, zone = data.get("method_id"), data.get("power_zone")
        if store is None:
            violations.append(oid + ": calibration store missing")
        elif not (f"{method}|{zone}" in buckets
                  or isinstance(buckets.get(method), dict)
                  and zone in buckets[method]):
            violations.append(f"{oid}: bucket {method} x {zone}"
                              " not in calibration store")
    return Result("E3", len(violations), violations,
                  note=f"{len(outcomes)} outcomes")


def _memory_beliefs(text: str) -> list[tuple[str, str]]:
    """(normalized belief text, status) for bullets and company-table rows."""
    beliefs = []
    for raw in text.splitlines():
        if raw.startswith("- "):
            tag = graph_build.STATUS_TAG.search(raw)
            if tag:
                beliefs.append((graph_build.norm_text(raw[2:tag.start()]),
                                tag.group(1)))
        elif raw.startswith("| "):
            cells = [c.strip() for c in raw.strip().strip("|").split("|")]
            if len(cells) >= 5 and cells[0] not in ("Ticker", ""):
                match = TABLE_STATUS.match(cells[4])
                if match:
                    beliefs.append((graph_build.norm_text(cells[1]),
                                    match.group(1)))
    return beliefs


def _git_show(root: Path, spec: str) -> str | None:
    try:
        return subprocess.run(
            ["git", "-C", str(root), "show", spec],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            check=True).stdout
    except (subprocess.CalledProcessError, OSError):
        return None


def inv_e4(conn, root, today) -> Result:
    """Diff MEMORY.md belief texts against git HEAD AND a bounded historical
    baseline. The working-tree-vs-HEAD diff catches an uncommitted rewrite,
    but a rewrite that was already committed makes HEAD equal the working
    tree, so that diff alone can never fire in CI. The baseline -- the oldest
    of the last E4_HISTORY_WINDOW commits touching MEMORY.md -- closes that
    hole: every belief present there must survive verbatim in the current
    file (the status tag may change; retirement is a status-tag change that
    keeps the text, and a supersede keeps the superseded text addressable).
    A belief whose normalized text vanished was rewritten in place or deleted
    -- the preservation rule forbids both."""
    rel = "_system/memory/MEMORY.md"
    work_path = root / rel
    if not work_path.is_file():
        return Result("E4", 0, [], note="no MEMORY.md; nothing to diff")
    head_text = _git_show(root, f"HEAD:{rel}")
    if head_text is None:
        return Result("E4", 0, [],
                      note="no committed MEMORY.md at HEAD; diff skipped")
    head_beliefs = _memory_beliefs(head_text)
    work_texts = {t for t, _ in
                  _memory_beliefs(work_path.read_text(encoding="utf-8"))}
    violations = []
    seen = set()
    for ntext, status in head_beliefs:
        if ntext in work_texts or ntext in seen:
            continue
        seen.add(ntext)
        violations.append(f"[{status}] {ntext[:100]}")
    note = f"{len(head_beliefs)} beliefs at HEAD"
    try:
        shas = subprocess.run(
            ["git", "-C", str(root), "log", "-n", str(E4_HISTORY_WINDOW),
             "--format=%H", "--", rel],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            check=True).stdout.split()
    except (subprocess.CalledProcessError, OSError):
        shas = []
    if shas:
        baseline = shas[-1]
        hist_text = _git_show(root, f"{baseline}:{rel}")
        if hist_text is None:
            note += f"; history baseline {baseline[:12]} unreadable"
        else:
            for ntext, status in _memory_beliefs(hist_text):
                if ntext in work_texts or ntext in seen:
                    continue
                seen.add(ntext)
                violations.append(
                    f"[{status}] {ntext[:100]} (present at {baseline[:12]},"
                    f" oldest of the last {E4_HISTORY_WINDOW} commits touching"
                    " MEMORY.md; rewritten or deleted without supersede)")
            note += (f"; history baseline {baseline[:12]}"
                     f" spans {len(shas)} commits")
    return Result("E4", len(violations), violations, note=note)


def inv_e5(conn, root, today) -> Result:
    rows = conn.execute(
        "SELECT e.src, e.dst FROM edges e"
        " JOIN nodes s ON s.id = e.dst"
        " WHERE e.type='SUPPORTED_BY' AND s.status='missing'"
        " AND e.src IN (SELECT id FROM nodes WHERE type='Belief')"
        " ORDER BY e.src, e.dst").fetchall()
    return Result("E5", len(rows),
                  [f"{r['src']} -> {r['dst']}" for r in rows])


def inv_e6(conn, root, today) -> Result:
    rows = conn.execute(
        "SELECT id, as_of, label FROM nodes"
        " WHERE type='Proposal' AND status='undecided'"
        " ORDER BY as_of, id").fetchall()
    return Result("E6", len(rows),
                  [f"{r['as_of']} {r['label'][:80].rstrip()}" for r in rows])


def inv_e7(conn, root, today) -> Result:
    triage = graph_build.build_memory_triage
    items = []
    for path in sorted((root / "_system/memory/daily").glob("*.md")):
        items.extend(triage.parse_file(path))
    items, _duplicates = triage.dedupe(items)
    ledger = graph_build.load_json(root / "_system/memory/triage_ledger.json") or {}
    decisions = ledger.get("decisions") or {}
    violations = []
    for item in items:
        if triage.fingerprint(item) in decisions:
            continue
        kind = triage.proposal_kind(item)
        if kind in {"company_observation", "ephemeral_output", "parse_artifact"}:
            violations.append(
                f"{item['day']} {triage.fingerprint(item)} {kind}: must be routed/dropped, not belief-reviewed")
            continue
        try:
            age = (today - date.fromisoformat(item["day"])).days
        except ValueError:
            age = 0
        if item["day"] >= "2026-08-12" and age > 30:
            violations.append(
                f"{item['day']} {triage.fingerprint(item)} {kind}: undecided {age} days (prospective SLA 30)")
    return Result("E7", len(violations), violations,
                  note="deterministic routing is immediate; 30-day gate applies prospectively from 2026-08-12")


def _dig(doc, dotted: str):
    """Walk a dotted path through nested dicts. Missing -> None."""
    node = doc
    for part in str(dotted).split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _content_violations(name: str, doc: dict, feed: dict, healer: str) -> tuple:
    """Assert declared fields INSIDE a feed, not just its stamp.

    A freshness window only proves the builder ran. It cannot see a builder
    that ran perfectly and wrote a file whose columns are dead: Yahoo answered
    200 for ^VIX3M for sixteen sessions while returning a series that stopped,
    so `vol_metrics_latest.json` was rewritten daily with a fresh
    `generated_at` and a term-structure complex that had gone dark. P6 passed
    every one of those days. The stamp was never the thing worth checking.

    Returns ``(violations, details)``. Violation text is built only from the
    feed name, the field and the CONFIGURED bound -- never from the observed
    value -- because waivers match by exact string equality (see
    ``_apply_overrides``). Folding the live count into the text would mean a
    waiver written at five dark symbols silently stops applying at six, which
    is the worst possible moment for a check to change its mind. Observed
    values ride in ``details`` and surface in the note, exactly as feed ages do.
    """
    checks = feed.get("assert_fields")
    if not isinstance(checks, dict):
        return [], []
    out, details = [], []
    for field, spec in sorted(checks.items()):
        if not isinstance(spec, dict):
            continue
        value = _dig(doc, field)
        why = ascii_safe(str(spec.get("why", "")))[:120]
        if "not_in" in spec and value in list(spec["not_in"]):
            out.append(f"{name}: {field} holds a disallowed value"
                       f" -- {why} -- heal: {healer}")
            details.append(f"{name}.{field}='{ascii_safe(str(value))[:40]}'")
        if "equals" in spec and value != spec["equals"]:
            out.append(f"{name}: {field} does not equal"
                       f" '{spec['equals']}' -- {why} -- heal: {healer}")
            details.append(f"{name}.{field}='{ascii_safe(str(value))[:40]}'")
        if "max_count" in spec:
            count = len(value) if isinstance(value, (list, dict)) else 0
            if count > int(spec["max_count"]):
                out.append(f"{name}: {field} exceeds its limit of"
                           f" {spec['max_count']} -- {why} -- heal: {healer}")
                members = sorted(value) if isinstance(value, (list, dict)) else []
                details.append(f"{name}.{field}={count}"
                               f" [{ascii_safe(', '.join(map(str, members)))[:60]}]")
    return out, details


def inv_p6(conn, root, today) -> Result:
    """Data-feed freshness (self-healing detector for the risk dashboard).

    Filesystem check like P4: each feed registered in graph_sources.json
    data_feeds must carry a parseable stamp younger than its window. The
    violation text is deliberately STABLE across days (feed + window, ages
    live in the note) so waivers with dated notes can target it exactly.
    A missing file or unparseable stamp is always a violation - a feed that
    cannot be judged fresh must never read as fresh.

    A feed may also declare ``assert_fields`` to have its CONTENTS checked;
    see ``_content_violations`` for why a fresh stamp is not evidence of a
    live feed."""
    config = graph_build.load_json(
        root / "_system" / "graph" / "graph_sources.json") or {}
    feeds = config.get("data_feeds", {}) if isinstance(config, dict) else {}
    now = datetime.now(timezone.utc)
    violations, ages, fresh = [], [], 0
    for name, feed in sorted(feeds.items()):
        if name.startswith("_") or not isinstance(feed, dict):
            continue
        window = float(feed.get("max_age_hours", 48))
        path = root / str(feed.get("path", ""))
        healer = ascii_safe(feed.get("healer", ""))[:100]
        if not path.is_file():
            violations.append(f"{name}: file missing ({feed.get('path')})"
                              f" -- heal: {healer}")
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            stamp = doc.get(str(feed.get("stamp_field", "generated_at")))
            when = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            violations.append(f"{name}: unparseable stamp -- can never be"
                              f" judged fresh -- heal: {healer}")
            continue
        age_h = (now - when).total_seconds() / 3600.0
        ages.append(f"{name} {age_h:.0f}h")
        content, detail = _content_violations(name, doc, feed, healer)
        ages.extend(detail)
        if age_h > window:
            violations.append(f"{name}: stale (window {window:.0f}h)")
            violations.extend(content)
        elif content:
            violations.extend(content)
        else:
            fresh += 1
    return Result("P6", len(violations), violations,
                  note=f"{fresh}/{fresh + len(violations)} feeds fresh"
                       f" ({', '.join(ages)})")


def _live_evidence_path(root: Path, raw) -> Path | None:
    """Resolve a live feed's evidence path. Absolute and ``~``-rooted paths
    are machine-local by design (monitor logs); a relative path resolves
    against the repo root like P6's ``path``."""
    text = str(raw or "").strip()
    if not text:
        return None
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = root / text
    return path


def _live_stamp(path: Path, field: str):
    """The most recent value of ``field`` in the evidence file.

    Accepts both a single JSON document and a JSONL/append-only log whose
    LAST line carries the stamp (the flow monitor's out log). Returns None
    when nothing in the file carries the field -- which the caller treats as
    unparseable, never as fresh."""
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        doc = json.loads(text)
        if isinstance(doc, dict) and doc.get(field) is not None:
            return doc[field]
    except (TypeError, ValueError):
        pass
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            doc = json.loads(line)
        except ValueError:
            continue
        if isinstance(doc, dict) and doc.get(field) is not None:
            return doc[field]
    return None


def inv_p7(conn, root, today) -> Result:
    """Live-feed staleness: feeds published through the HMAC ingest rather
    than committed as files (P6 covers the committed ones).

    Born from the Databento flow monitor dying on 2026-08-03 at 12:15 on an
    UNCAUGHT urlopen timeout in its publish path: the dashboard's flow rails,
    sector pressure/exhaustion columns and alert journal were empty for seven
    days and no surface anywhere said so. The disease was the silence, so the
    silence itself is now a countable defect.

    The evidence for a live feed is a machine-local artifact (a monitor log on
    the publishing host), so the CI rule differs from P6's and is deliberate:

      * evidence file ABSENT -> SKIPPED with a reason, named in the note,
        NEVER a violation. CI checkouts have no local monitor logs, and an
        invariant that reddens on every CI run is one everybody learns to
        ignore.
      * evidence file PRESENT but no parseable stamp -> violation. Same rule
        as P6: a stamp that cannot be parsed can never be judged fresh.
      * evidence file PRESENT and older than its window -> violation.

    Severity is report, not hard: a local feed being down must be loud, and
    must not block a merge by someone who cannot see that host.

    Violation text is stable across days (feed + window; ages live in the
    note) so a waiver carrying a dated note can target it exactly.
    """
    config = graph_build.load_json(
        root / "_system" / "graph" / "graph_sources.json") or {}
    feeds = config.get("live_feeds", {}) if isinstance(config, dict) else {}
    now = datetime.now(timezone.utc)
    violations, ages, skipped = [], [], []
    fresh = 0
    for name, feed in sorted(feeds.items()):
        if name.startswith("_") or not isinstance(feed, dict):
            continue
        window = float(feed.get("max_age_hours", 24))
        healer = ascii_safe(feed.get("healer", ""))[:120]
        raw_path = feed.get("evidence_path", "")
        path = _live_evidence_path(root, raw_path)
        if path is None:
            violations.append(f"{name}: no evidence_path registered -- can"
                              f" never be judged fresh -- heal: {healer}")
            continue
        if not path.is_file():
            skipped.append(f"{name} (evidence absent: {ascii_safe(raw_path)})")
            continue
        try:
            stamp = _live_stamp(path, str(feed.get("stamp_field",
                                                   "published_at")))
            when = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
        except (OSError, TypeError, ValueError):
            violations.append(f"{name}: unparseable stamp -- can never be"
                              f" judged fresh -- heal: {healer}")
            continue
        age_h = (now - when).total_seconds() / 3600.0
        ages.append(f"{name} {age_h:.0f}h")
        if age_h > window:
            violations.append(f"{name}: not published inside its window"
                              f" (window {window:.0f}h) -- heal: {healer}")
        else:
            fresh += 1
    judged = fresh + len(violations)
    note = f"{fresh}/{judged} live feeds fresh"
    if ages:
        note += f" ({', '.join(ages)})"
    if skipped:
        note += ("; " + str(len(skipped)) + " SKIPPED -- " + "; ".join(skipped)
                 + " -- an absent evidence file is reported, never a violation"
                 " (this evidence is machine-local and does not exist in CI)")
    return Result("P7", len(violations), violations, note=note)


# --------------------------------------------------------------------------- #
# L-series: the classification/lens plane
#
# Born 2026-08-11 from the WHK finding that generalised: the persona/consensus
# layer LOOKED like multi-lens validation but was single-lens -- 542/721
# valued tickers had no payoff_lens anywhere, 130 more stored it where the
# persona reader never looked, criteria referenced enum values no data emits,
# lenses.json went stale the moment anything but a full marvin refresh
# rewrote valuation.json, and two divergent GROUPS maps seated 31 committees
# whose raters collapse to two independence groups under the canonical map.
# Every one of these is a missing/broken link nothing could see; these
# invariants make each a countable defect. Filesystem/config scans in the
# P4/P6 style (graph_build projects none of these surfaces yet).
# --------------------------------------------------------------------------- #

_LENS_SCAN_CACHE: dict = {}

# Registry defaults cannot 'disagree' -- they mean unfilled, not asserted.
_CLASS_SENTINELS = {"", "pending", "unknown", "-"}
_REGISTRY_DEFAULTS = {"archetype": "unknown", "moat": "unproven",
                      "dhando": "pending", "payoff_lens": "pending"}


def _class_value(raw) -> str | None:
    text = str(raw if raw is not None else "").strip().lower()
    return text if text and text not in _CLASS_SENTINELS else None


def _lens_plane_scan(root: Path) -> list[dict]:
    """One pass over every ticker dir carrying research/valuation.json;
    shared by L1/L2/L3/L5 so each valuation.json parses once per run.
    run() clears the cache before executing the suite."""
    cached = _LENS_SCAN_CACHE.get(root)
    if cached is not None:
        return cached
    registry = graph_build.load_json(
        root / "_system" / "portfolio" / "registry.json") or {}
    entries = {**(registry.get("watchlist") or {}),
               **(registry.get("holdings") or {})}
    reg_class = {name: (entry or {}).get("classification") or {}
                 for name, entry in entries.items()}
    rows: list[dict] = []
    for tdir in sorted(root.iterdir()):
        if not tdir.is_dir() or tdir.name.startswith((".", "_")) \
                or tdir.name in ("dashboard", "investing-docs", "node_modules"):
            continue
        val_path = tdir / "research" / "valuation.json"
        if not val_path.is_file():
            continue
        val = graph_build.load_json(val_path)
        parse_failed = not isinstance(val, dict)
        val = val if isinstance(val, dict) else {}
        # Shape hardening: a string where a dict belongs must degrade to
        # "unclassified", never crash the suite (the E2 _parse_due lesson --
        # an uncaught exception here means no INVARIANTS.md at all).
        ci = val.get("classification_inputs")
        ci = ci if isinstance(ci, dict) else {}
        reg = reg_class.get(tdir.name, {})
        reg = reg if isinstance(reg, dict) else {}
        lenses = graph_build.load_json(tdir / "research" / "lenses.json")
        lenses = lenses if isinstance(lenses, dict) else None
        route = graph_build.load_json(
            tdir / "research" / "valuation_route.json")
        route = route if isinstance(route, dict) else None
        contract = graph_build.load_json(
            tdir / "research" / "valuation_contract.json")
        contract = contract if isinstance(contract, dict) else {}
        blend = (lenses or {}).get("valuation_blend")
        blend = blend if isinstance(blend, dict) else {}
        consensus = (lenses or {}).get("consensus")
        consensus = consensus if isinstance(consensus, dict) else {}
        contributors = blend.get("contributors")
        contributors = contributors if isinstance(contributors, list) else []
        rows.append({
            "ticker": tdir.name,
            "parse_failed": parse_failed,
            "val_as_of": str(val.get("as_of") or "")[:10],
            "surfaces": {
                "payoff_lens": {
                    "top-level": val.get("payoff_lens"),
                    "classification_inputs": ci.get("payoff_lens"),
                    "registry": reg.get("payoff_lens"),
                },
                "archetype": {
                    "classification_inputs": ci.get("archetype"),
                    "registry": reg.get("archetype"),
                },
                "moat": {
                    "classification_inputs": ci.get("moat"),
                    "registry": reg.get("moat"),
                },
                "dhando": {
                    "classification_inputs": ci.get("dhando"),
                    "registry": reg.get("dhando"),
                },
            },
            "contract_status": str(contract.get("status") or ""),
            "lenses_present": lenses is not None,
            "lenses_as_of": str((lenses or {}).get("as_of") or "")[:10],
            "consensus_stance": consensus.get("stance") if lenses else None,
            "blend_contributors": len(contributors) if lenses else None,
            "route_present": route is not None,
            "route_as_of": str((route or {}).get("as_of") or "")[:10],
        })
    _LENS_SCAN_CACHE.clear()
    _LENS_SCAN_CACHE[root] = rows
    return rows


def inv_l1(conn, root, today) -> Result:
    """A ticker whose payoff_lens resolves nowhere routes to no valuation
    toolkit and silences every asset/event persona before judgment starts.
    542/721 at introduction."""
    rows = _lens_plane_scan(root)
    if not rows:
        return Result("L1", 0, [], note="vacuously green (no valued tickers)")
    violations = []
    by_source = {"top-level": 0, "classification_inputs": 0, "registry": 0}
    for row in rows:
        if row["parse_failed"]:
            violations.append(f"{row['ticker']}: valuation.json unparseable --"
                              " can never be judged classified")
            continue
        surfaces = row["surfaces"]["payoff_lens"]
        resolved = None
        for source in ("top-level", "classification_inputs", "registry"):
            if _class_value(surfaces[source]):
                resolved = source
                break
        if resolved:
            by_source[resolved] += 1
        else:
            violations.append(f"{row['ticker']}: no payoff_lens on any surface"
                              " (top-level, classification_inputs, registry)")
    resolved_n = sum(by_source.values())
    return Result("L1", len(violations), violations,
                  note=f"{resolved_n}/{len(rows)} tickers resolve"
                       f" (top-level {by_source['top-level']},"
                       f" classification_inputs"
                       f" {by_source['classification_inputs']},"
                       f" registry {by_source['registry']})")


def inv_l2(conn, root, today) -> Result:
    """Shadowed classification: two surfaces asserting different values means
    every reader's answer depends on which file it happened to open (the
    us_ticker_config-shadows-registry failure class, one plane over).
    Registry defaults are 'unfilled', not assertions, and do not conflict."""
    rows = _lens_plane_scan(root)
    if not rows:
        return Result("L2", 0, [], note="vacuously green (no valued tickers)")
    violations = []
    tickers_hit = set()
    for row in rows:
        if row["parse_failed"]:
            continue
        for field, surfaces in row["surfaces"].items():
            asserted: dict[str, str] = {}
            for source, raw in surfaces.items():
                value = _class_value(raw)
                if value is None:
                    continue
                if source == "registry" and value == _REGISTRY_DEFAULTS.get(field):
                    continue
                asserted[source] = value
            if len(set(asserted.values())) > 1:
                tickers_hit.add(row["ticker"])
                detail = " vs ".join(f"{source}='{value}'"
                                     for source, value in sorted(asserted.items()))
                violations.append(f"{row['ticker']}: {field} {detail}")
    return Result("L2", len(violations), violations,
                  note=f"{len(tickers_hit)} tickers carry a conflict")


def inv_l3(conn, root, today) -> Result:
    """Derived lens-plane artifacts behind their source valuation: the WHK
    class (re-underwritten 2026-08-11, lenses.json still 2026-08-05, nightly
    dashboard bakes the stale file). Registry-driven like P6: entries in
    graph_sources.json derived_artifacts, each naming its healer."""
    config = graph_build.load_json(
        root / "_system" / "graph" / "graph_sources.json") or {}
    artifacts = config.get("derived_artifacts", {}) \
        if isinstance(config, dict) else {}
    artifacts = {name: spec for name, spec in sorted(artifacts.items())
                 if not name.startswith("_") and isinstance(spec, dict)}
    if not artifacts:
        return Result("L3", 0, [],
                      note="vacuously green (no derived_artifacts registered)")
    rows = _lens_plane_scan(root)
    if not rows:
        return Result("L3", 0, [], note="vacuously green (no valued tickers)")
    violations = []
    stale_n = missing_n = undated_n = 0
    # A source that cannot be dated can never have its derived artifacts
    # judged fresh -- that is a violation, not a silent skip (the P6 rule).
    for row in rows:
        if row["parse_failed"]:
            continue
        if not row["val_as_of"]:
            undated_n += 1
            violations.append(f"{row['ticker']}: research/valuation.json has"
                              " no as_of -- derived freshness can never be"
                              " judged")
    for name, spec in artifacts.items():
        healer = ascii_safe(spec.get("healer", ""))[:120]
        derived_rel = str(spec.get("derived") or "")
        missing_when = str(spec.get("missing_when") or "never")
        present_key, as_of_key = {
            "research/lenses.json": ("lenses_present", "lenses_as_of"),
            "research/valuation_route.json": ("route_present", "route_as_of"),
        }.get(derived_rel, (None, None))
        if present_key is None:
            violations.append(f"{name}: unrecognised derived path"
                              f" '{derived_rel}' -- can never be judged fresh")
            continue
        for row in rows:
            if row["parse_failed"] or not row["val_as_of"]:
                continue
            if not row[present_key]:
                if missing_when == "decision_grade" \
                        and row["contract_status"] == "decision_grade":
                    missing_n += 1
                    violations.append(
                        f"{row['ticker']}: {derived_rel} missing for a"
                        f" decision_grade contract -- heal: {healer}")
                continue
            if not row[as_of_key]:
                undated_n += 1
                violations.append(f"{row['ticker']}: {derived_rel} has no"
                                  " as_of -- can never be judged fresh --"
                                  f" heal: {healer}")
            elif row[as_of_key] < row["val_as_of"]:
                stale_n += 1
                violations.append(f"{row['ticker']}: {derived_rel} behind"
                                  f" {spec.get('source')} -- heal: {healer}")
    return Result("L3", len(violations), violations,
                  note=f"{stale_n} stale, {missing_n} missing where required,"
                       f" {undated_n} undatable, over {len(rows)} tickers x"
                       f" {len(artifacts)} artifacts")


def _criteria_value_sites(root: Path) -> list[tuple[str, str, str]]:
    """(field, value, site) triples for every enum value referenced by the
    persona lenses and the power zones."""
    sites: list[tuple[str, str, str]] = []
    check_fields = {"archetype_any": "archetype", "moat_any": "moat",
                    "dhando_any": "dhando", "dhando_not": "dhando",
                    "payoff_lens_any": "payoff_lens"}
    personas = graph_build.load_json(
        root / "_system" / "lenses" / "personas.json") or {}
    for pid, spec in (personas.get("personas") or {}).items():
        for criterion in (spec.get("criteria") or []):
            field = check_fields.get(str(criterion.get("check") or ""))
            if not field:
                continue
            for value in criterion.get("values") or []:
                sites.append((field, str(value).lower(),
                              f"personas.json:{pid}:{criterion.get('id')}"))
    zones_doc = graph_build.load_json(
        root / "_system" / "frameworks" / "power_zones.json") or {}
    for zid, zone in (zones_doc.get("zones") or {}).items():
        rules = zone.get("rules") or {}
        for field in ("archetype", "moat", "dhando", "payoff_lens"):
            for value in rules.get(field) or []:
                sites.append((field, str(value).lower(),
                              f"power_zones.json:zone:{zid}"))
    for prof_id, profile in (zones_doc.get("valuation_profiles") or {}).items():
        for value in profile.get("preferred_archetypes") or []:
            sites.append(("archetype", str(value).lower(),
                          f"power_zones.json:profile:{prof_id}"))
    return sites


def inv_l4(conn, root, today) -> Result:
    """Vocabulary closure. A criterion referencing a value no surface emits is
    dead -- its persona goes silent with nothing saying so (9 such values at
    introduction). A data value outside the canon routes nowhere. And a
    persona lens strictly narrower than its own power zone (stahl omitting
    optionality while 57 tickers carry it) silences the specialist on exactly
    the names routed to it."""
    config = graph_build.load_json(
        root / "_system" / "graph" / "graph_sources.json") or {}
    vocab = config.get("classification_vocab", {}) \
        if isinstance(config, dict) else {}
    fields = {name: {str(v).lower() for v in values}
              for name, values in (vocab.get("fields") or {}).items()}
    if not fields:
        return Result("L4", 0, [],
                      note="vacuously green (no classification_vocab"
                           " registered)")
    sentinels = {str(v).lower() for v in vocab.get("sentinels") or []}
    violations = []
    # (a) criteria values outside the canon
    criteria_bad = 0
    for field, value, site in _criteria_value_sites(root):
        canon = fields.get(field)
        if canon is not None and value not in canon and value not in sentinels:
            criteria_bad += 1
            violations.append(f"criteria: {site} {field} '{value}'"
                              " not canonical")
    # (b) data values outside the canon (distinct value per field, counts in
    # the note so the violation text stays waiver-stable)
    rows = _lens_plane_scan(root)
    data_bad: dict[tuple[str, str], int] = {}
    for row in rows:
        if row["parse_failed"]:
            continue
        for field, surfaces in row["surfaces"].items():
            canon = fields.get(field)
            if canon is None:
                continue
            for raw in surfaces.values():
                value = _class_value(raw)
                if value is not None and value not in canon:
                    data_bad[(field, value)] = data_bad.get(
                        (field, value), 0) + 1
                    break
    for (field, value) in sorted(data_bad):
        violations.append(f"data: {field} value '{value}' not canonical")
    # (c) persona lens narrower than its own power zone on a shared axis
    check_fields = {"archetype_any": "archetype", "moat_any": "moat",
                    "dhando_any": "dhando", "payoff_lens_any": "payoff_lens"}
    personas = graph_build.load_json(
        root / "_system" / "lenses" / "personas.json") or {}
    zones_doc = graph_build.load_json(
        root / "_system" / "frameworks" / "power_zones.json") or {}
    zones = zones_doc.get("zones") or {}
    narrower = 0
    for pid, spec in (personas.get("personas") or {}).items():
        zone_rules = (zones.get(pid) or {}).get("rules") or {}
        for criterion in (spec.get("criteria") or []):
            field = check_fields.get(str(criterion.get("check") or ""))
            if not field or field not in zone_rules:
                continue
            lens_values = {str(v).lower() for v in criterion.get("values") or []}
            zone_values = {str(v).lower() for v in zone_rules.get(field) or []}
            canon = fields.get(field) or set()
            missing = sorted((zone_values & canon) - lens_values)
            if missing:
                narrower += 1
                violations.append(
                    f"narrower-than-zone: persona {pid} {field} lens misses"
                    f" zone values {', '.join(missing)}")
    note = (f"{criteria_bad} non-canonical criteria values,"
            f" {len(data_bad)} non-canonical data values"
            f" ({sum(data_bad.values())} ticker-field hits),"
            f" {narrower} lenses narrower than their zone")
    return Result("L4", len(violations), violations, note=note)


def inv_l5(conn, root, today) -> Result:
    """Display honesty: a consensus stance carried by fewer than two
    contributing personas is the compiler's own number wearing a consensus
    badge. The zero-contributor case is structurally possible (build_consensus
    accepts verdict-only personas the blend excludes) and the SPA renders the
    stance badge unconditionally."""
    rows = _lens_plane_scan(root)
    judged = [row for row in rows if row["lenses_present"]]
    if not judged:
        return Result("L5", 0, [], note="vacuously green (no lenses.json)")
    violations = []
    for row in judged:
        stance = str(row["consensus_stance"] or "").lower()
        if stance in ("", "pending", "silent"):
            continue
        contributors = row["blend_contributors"] or 0
        if contributors < 2:
            violations.append(f"{row['ticker']}: consensus stance '{stance}'"
                              f" with {contributors} contributing persona(s)")
    return Result("L5", len(violations), violations,
                  note=f"{len(judged)} tickers with lenses.json")


def inv_l6(conn, root, today) -> Result:
    """The canonical persona map holds everywhere: registries equal, no
    re-defined GROUPS literal, and no active committee whose raters collapse
    below the independence quorum under the canonical map (31 manifests had
    already been seated with two quality_reinvestment raters when the
    divergent copies were found)."""
    personas = graph_build.load_json(
        root / "_system" / "lenses" / "personas.json") or {}
    persona_ids = set(personas.get("personas") or {})
    if not persona_ids:
        return Result("L6", 0, [],
                      note="vacuously green (no personas.json)")
    try:
        from persona_groups import INDEPENDENCE_GROUPS, INDEPENDENCE_QUORUM
    except ImportError:
        return Result("L6", 1, ["persona_groups.py missing -- canonical map"
                                " unavailable"])
    violations = []
    canonical_ids = set(INDEPENDENCE_GROUPS)
    for pid in sorted(persona_ids - canonical_ids):
        violations.append(f"registry: personas.json persona '{pid}' has no"
                          " entry in persona_groups.INDEPENDENCE_GROUPS")
    for pid in sorted(canonical_ids - persona_ids):
        violations.append(f"registry: persona_groups persona '{pid}' missing"
                          " from personas.json")
    zones_doc = graph_build.load_json(
        root / "_system" / "frameworks" / "power_zones.json") or {}
    zone_ids = set(zones_doc.get("zones") or {})
    if zone_ids:
        for pid in sorted(zone_ids ^ canonical_ids):
            violations.append(f"registry: power_zones.json zones and"
                              f" persona_groups disagree on '{pid}'")
    groups_literal = re.compile(r"^(GROUPS|INDEPENDENCE_GROUPS)\s*=\s*\{",
                                re.MULTILINE)
    scripts_dir = root / "_system" / "scripts"
    if scripts_dir.is_dir():
        for path in sorted(scripts_dir.glob("*.py")):
            if path.name == "persona_groups.py":
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if groups_literal.search(text):
                violations.append(f"literal: {path.name} re-defines a GROUPS"
                                  " map instead of importing persona_groups")
    manifest_n = collided = 0
    for manifest_path in sorted(root.glob(
            "*/research/committee_work/*/manifest.json")):
        manifest = graph_build.load_json(manifest_path)
        if not isinstance(manifest, dict):
            continue
        if str(manifest.get("stage") or "") == "superseded":
            continue
        raters = [str(row.get("persona") or "")
                  for row in manifest.get("selected_raters") or []
                  if isinstance(row, dict)]
        if not raters:
            continue
        manifest_n += 1
        ticker = str(manifest.get("ticker") or manifest_path.parents[3].name)
        # No .get(p, p) fallback here: minting an unknown id its own group is
        # the exact defect this check exists to catch -- a typo'd rater would
        # otherwise inflate the count past quorum.
        unknowns = sorted({p for p in raters if p not in INDEPENDENCE_GROUPS})
        canonical_groups = {INDEPENDENCE_GROUPS[p] for p in raters
                            if p in INDEPENDENCE_GROUPS}
        if unknowns:
            collided += 1
            violations.append(
                f"committee: {ticker}@{manifest_path.parent.name} rater id(s)"
                f" outside the canonical registry: {', '.join(unknowns)} --"
                " independence cannot be proven")
        elif len(canonical_groups) < INDEPENDENCE_QUORUM:
            collided += 1
            violations.append(
                f"committee: {ticker}@{manifest_path.parent.name} raters"
                f" {', '.join(raters)} collapse to {len(canonical_groups)}"
                " canonical group(s)")
    note = (f"{len(persona_ids)} personas, {manifest_n} active manifests,"
            f" {collided} below quorum under the canonical map")
    return Result("L6", len(violations), violations, note=note)


INVARIANTS = [inv_p1, inv_p2, inv_p3, inv_p4, inv_p5, inv_p6, inv_p7,
              inv_e1, inv_e2, inv_e3, inv_e4, inv_e5, inv_e6, inv_e7,
              inv_l1, inv_l2, inv_l3, inv_l4, inv_l5, inv_l6]


# --------------------------------------------------------------------------- #
# overrides, waivers, previous-report delta
# --------------------------------------------------------------------------- #

def apply_config(results: list[Result], config: dict,
                 warnings: list[str]) -> None:
    inv_cfg = config.get("invariants", {}) if isinstance(config, dict) else {}
    overrides = inv_cfg.get("overrides", {})
    waivers = inv_cfg.get("waivers", {})
    for result in results:
        override = overrides.get(result.id)
        if isinstance(override, dict) and override.get("severity"):
            if not override.get("todo"):
                warnings.append(f"{result.id}: override without a dated todo"
                                " note is not applied")
            else:
                result.severity = str(override["severity"])
                result.note = (result.note + "; " if result.note else "") + \
                    f"demoted from {result.base_severity} -- " + \
                    ascii_safe(override["todo"])[:200]
        for waiver in waivers.get(result.id, []):
            target = ascii_safe(str(waiver.get("violation", "")))
            note = ascii_safe(str(waiver.get("note", "")))
            if not note:
                warnings.append(f"{result.id}: waiver for '{target[:60]}' has"
                                " no dated note; not applied")
                continue
            if target in result.violations:
                result.violations.remove(target)
                result.count -= 1
                result.waived.append(f"{target} [waived: {note[:160]}]")
            else:
                warnings.append(f"{result.id}: STALE waiver -- no live"
                                f" violation matches '{target[:80]}'")


def _set_lane_ref(root: Path) -> bool:
    """Point graph_build's lane projection at origin/main when that ref
    exists (P3 spurious-fire fix: a PR checkout whose branch point is older
    than a lane's freshness window is missing the nightly lane commits that
    landed on main, so every such lane reads stale for a reason that has
    nothing to do with the lanes). The preference travels as GRAPH_LANE_REF
    in the environment, which graph_build's git-log subprocess inherits.
    A value already set by the caller is respected untouched. Returns True
    iff this call set the variable (the caller must unset it after the
    build so it cannot leak into a later build against another root)."""
    if os.environ.get(LANE_REF_ENV):
        return False
    try:
        probe = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", "--quiet",
             "origin/main^{commit}"], capture_output=True, text=True)
    except OSError:
        return False
    if probe.returncode != 0:
        return False
    os.environ[LANE_REF_ENV] = "origin/main"
    return True


BASELINE_REL = "_system/graph/invariants_baseline.json"


def baseline_ratchet(results: list[Result], root: Path) -> tuple[list[str], dict]:
    """CI-enforced ratchet for opt-in report-severity invariants, copying the
    check_evidence_integrity.py precedent: a committed baseline whose counts
    may only fall; any rise fails the run. Only ids PRESENT in the baseline
    file are armed (E6-style organically-growing counts stay unarmed), and an
    absent baseline file disarms the ratchet entirely. The Delta column
    compares against HEAD and is display-only; this compares against the
    pinned baseline and gates."""
    baseline = graph_build.load_json(root / BASELINE_REL) or {}
    counts = baseline.get("counts") if isinstance(baseline, dict) else None
    if not isinstance(counts, dict):
        return [], {}
    regressions = []
    for result in results:
        if result.id in counts and result.count > int(counts[result.id]):
            regressions.append(f"{result.id}: {result.count} > baseline"
                               f" {counts[result.id]}"
                               f" ({ascii_safe(TITLES[result.id])})")
    return regressions, baseline


def write_baseline(results: list[Result], root: Path,
                   today: date) -> Path:
    """Record current counts for the armed ids (or arm the L-series when no
    baseline exists yet). Deliberately an explicit flag, never automatic: the
    ratchet is only honest if lowering the bar is a reviewed act."""
    path = root / BASELINE_REL
    existing = graph_build.load_json(path) or {}
    armed = list((existing.get("counts") or {})) if isinstance(existing, dict) \
        else []
    if not armed:
        armed = [r.id for r in results if r.id.startswith("L")]
    by_id = {r.id: r.count for r in results}
    payload = {
        "as_of": today.isoformat(),
        "counts": {inv_id: by_id.get(inv_id, 0) for inv_id in sorted(armed)},
        "note": "Ratchet baseline for the armed invariant ids. Counts may"
                " only fall; a rise fails the suite. Re-record with"
                " graph_invariants.py --update-baseline.",
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def previous_counts(root: Path) -> dict[str, int]:
    try:
        text = subprocess.run(
            ["git", "-C", str(root), "show", "HEAD:_system/graph/INVARIANTS.md"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            check=True).stdout
    except (subprocess.CalledProcessError, OSError):
        return {}
    counts = {}
    for line in text.splitlines():
        match = PREV_ROW.match(line)
        if match:
            counts[match.group(1)] = int(match.group(2))
    return counts


# --------------------------------------------------------------------------- #
# reports
# --------------------------------------------------------------------------- #

def render_markdown(results: list[Result], meta: dict,
                    warnings: list[str]) -> str:
    lines = [
        "# Graph invariants",
        "",
        "Generated by `_system/scripts/graph_invariants.py` (rebuilds"
        " `graph.db` first; spec: `README.md` in this directory). Hard"
        " violations exit non-zero; report-severity counts are the ratchet"
        " surface and must not grow across cycles.",
        "",
        f"Run date {meta['run_date']} | git HEAD `{meta['git_head'][:12]}` |"
        f" {meta['nodes']} nodes, {meta['edges']} edges",
        "",
        "| ID | Severity | Count | Delta | Status | Note |",
        "|----|----------|------:|------:|--------|------|",
    ]
    for r in results:
        severity = r.severity if r.severity == r.base_severity \
            else f"{r.severity} (demoted)"
        note = "; ".join(p for p in (
            r.note, f"{len(r.waived)} waived" if r.waived else "") if p)
        lines.append(f"| {r.id} | {severity} | {r.count} | {r.delta} |"
                     f" {r.status} | {TITLES[r.id]} -- {note} |"
                     if note else
                     f"| {r.id} | {severity} | {r.count} | {r.delta} |"
                     f" {r.status} | {TITLES[r.id]} |")
    ratchet = meta.get("ratchet") or {}
    lines.append("")
    if ratchet.get("armed"):
        if ratchet.get("regressions"):
            lines.append("**RATCHET REGRESSION** (baseline"
                         f" {ratchet.get('baseline_as_of')}): "
                         + "; ".join(ratchet["regressions"])
                         + " -- the run fails; fix the regression or"
                         " re-record the baseline in a reviewed commit"
                         " (`--update-baseline`).")
        else:
            lines.append(f"Ratchet armed for {', '.join(ratchet['armed'])}"
                         f" against baseline {ratchet.get('baseline_as_of')};"
                         " no count rose.")
    else:
        lines.append("Ratchet disarmed (no"
                     " `_system/graph/invariants_baseline.json`).")
    detail = [r for r in results if r.violations or r.waived]
    if detail:
        lines += ["", "## Violations", ""]
    for r in detail:
        lines.append(f"### {r.id} ({r.severity}) -- {TITLES[r.id]}")
        lines.append("")
        for v in r.violations[:VIOLATION_CAP]:
            lines.append(f"- {v}")
        if len(r.violations) > VIOLATION_CAP:
            lines.append(f"- ... {len(r.violations) - VIOLATION_CAP} more"
                         " (capped; full count in the table above)")
        for w in r.waived:
            lines.append(f"- {w}")
        lines.append("")
    if warnings:
        lines += ["## Warnings", ""]
        lines += [f"- {ascii_safe(w)}" for w in warnings]
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def run(root: Path | None = None, db_path: Path | None = None,
        out_dir: Path | None = None,
        today: date | None = None) -> tuple[list[Result], int, dict]:
    root = root or ROOT
    out_dir = out_dir or root / "_system" / "graph"
    today = today or date.today()
    _LENS_SCAN_CACHE.clear()
    lane_ref_set_here = _set_lane_ref(root)
    try:
        builder = graph_build.build(root, db_path)
    finally:
        if lane_ref_set_here:
            os.environ.pop(LANE_REF_ENV, None)
    db = db_path or root / "_system" / "graph" / "graph.db"
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    warnings = list(builder.warnings)
    try:
        results = [fn(conn, root, today) for fn in INVARIANTS]
    finally:
        conn.close()
    apply_config(results, builder.config, warnings)
    prev = previous_counts(root)
    for result in results:
        if result.id in prev:
            diff = result.count - prev[result.id]
            result.delta = f"{diff:+d}" if diff else "0"
    regressions, baseline = baseline_ratchet(results, root)
    exit_code = 1 if (any(r.severity == "hard" and r.count for r in results)
                      or regressions) else 0
    meta = {
        "run_date": today.isoformat(),
        "git_head": builder.git_head(),
        "nodes": len(builder.nodes),
        "edges": len(builder.edges),
        "exit_code": exit_code,
        "ratchet": {
            "armed": sorted((baseline.get("counts") or {}))
            if isinstance(baseline, dict) else [],
            "baseline_as_of": (baseline or {}).get("as_of"),
            "regressions": regressions,
        },
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "INVARIANTS.md").write_text(
        render_markdown(results, meta, warnings), encoding="utf-8")
    payload = {**meta, "invariants": [{
        "id": r.id, "severity": r.severity, "base_severity": r.base_severity,
        "count": r.count, "delta": r.delta, "status": r.status, "note": r.note,
        "violations": r.violations[:VIOLATION_CAP],
        "violations_total": len(r.violations), "waived": r.waived,
    } for r in results], "warnings": [ascii_safe(w) for w in warnings]}
    (out_dir / "invariants.json").write_text(
        json.dumps(payload, indent=1, ensure_ascii=True) + "\n",
        encoding="utf-8")
    return results, exit_code, meta


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None,
                        help="report directory (default _system/graph)")
    parser.add_argument("--update-baseline", action="store_true",
                        help="re-record the ratchet baseline at the current"
                             " counts for the armed ids (arms the L-series"
                             " when no baseline exists)")
    args = parser.parse_args()
    results, exit_code, meta = run(args.root, args.db, args.out)
    if args.update_baseline:
        path = write_baseline(results, args.root, date.today())
        print("baseline re-recorded: %s" % path)
        results, exit_code, meta = run(args.root, args.db, args.out)
    print("graph invariants @ %s (git %s)" % (meta["run_date"],
                                              meta["git_head"][:12]))
    for r in results:
        severity = r.severity if r.severity == r.base_severity \
            else r.severity + "*"
        line = "  %s %-8s %5d %-10s %s" % (r.id, severity, r.count, r.status,
                                           ascii_safe(r.note)[:90])
        print(line)
    out = args.out or args.root / "_system" / "graph"
    print("report: %s" % (out / "INVARIANTS.md"))
    ratchet = meta.get("ratchet") or {}
    if ratchet.get("regressions"):
        print("RATCHET REGRESSIONS: " + "; ".join(ratchet["regressions"]))
    if exit_code:
        print("HARD INVARIANT OR RATCHET VIOLATIONS -- see the report above")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
