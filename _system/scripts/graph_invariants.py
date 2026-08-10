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
PREV_ROW = re.compile(r"^\|\s*([PE]\d)\s*\|[^|]*\|\s*(\d+)\s*\|")
TABLE_STATUS = re.compile(r"^`?(active|superseded|disproven)\s+\d{4}-\d{2}-\d{2}")

BASE_SEVERITY = {
    "P1": "report", "P2": "hard", "P3": "hard", "P4": "hard", "P5": "report",
    "P6": "hard",
    "E1": "report", "E2": "hard", "E3": "hard", "E4": "hard", "E5": "hard",
    "E6": "report",
}

TITLES = {
    "P1": "every Correction has a GUARDED_BY path",
    "P2": "every Guard reaches a CIJob via ENFORCED_BY -> INVOKED_BY",
    "P3": "every active Lane has a Commit inside its freshness window",
    "P4": "no run receipts outside _system/data/runs/",
    "P5": "validator scripts with zero CI references",
    "E1": "decision-grade components carrying a typed falsifier",
    "E2": "matured typed falsifiers resolved within 14 days",
    "E3": "every Outcome has a SCORES edge and a calibration bucket",
    "E4": "no promoted Belief text rewritten in place (vs git HEAD +"
          " history window)",
    "E5": "every Belief's SUPPORTED_BY source exists on disk",
    "E6": "Proposals with no DECIDED_AS decision (silent-drop detector)",
    "P6": "every registered data feed is fresher than its window",
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
    typed = conn.execute(
        "SELECT * FROM nodes WHERE type='Falsifier' AND status='typed'"
        " ORDER BY id").fetchall()
    if not typed:
        return Result("E2", 0, [], note="vacuously green (0 typed)")
    violations = []
    matured = 0
    for row in typed:
        due = json.loads(row["data_json"]).get("due") or ""
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
        deadline = (due_date + timedelta(days=E2_GRACE_DAYS)).isoformat()
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
                  note=f"{len(typed)} typed, {matured} matured")


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
                  [f"{r['as_of']} {r['label'][:80]}" for r in rows])


def inv_p6(conn, root, today) -> Result:
    """Data-feed freshness (self-healing detector for the risk dashboard).

    Filesystem check like P4: each feed registered in graph_sources.json
    data_feeds must carry a parseable stamp younger than its window. The
    violation text is deliberately STABLE across days (feed + window, ages
    live in the note) so waivers with dated notes can target it exactly.
    A missing file or unparseable stamp is always a violation - a feed that
    cannot be judged fresh must never read as fresh."""
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
        if age_h > window:
            violations.append(f"{name}: stale (window {window:.0f}h)")
        else:
            fresh += 1
    return Result("P6", len(violations), violations,
                  note=f"{fresh}/{fresh + len(violations)} feeds fresh"
                       f" ({', '.join(ages)})")


INVARIANTS = [inv_p1, inv_p2, inv_p3, inv_p4, inv_p5, inv_p6,
              inv_e1, inv_e2, inv_e3, inv_e4, inv_e5, inv_e6]


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
    exit_code = 1 if any(r.severity == "hard" and r.count for r in results) \
        else 0
    meta = {
        "run_date": today.isoformat(),
        "git_head": builder.git_head(),
        "nodes": len(builder.nodes),
        "edges": len(builder.edges),
        "exit_code": exit_code,
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
    args = parser.parse_args()
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
    if exit_code:
        print("HARD INVARIANT VIOLATIONS -- see the report above")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
