#!/usr/bin/env python3
"""Canned traversals over the workspace graph (_system/graph/graph.db).

Queries (see _system/graph/README.md):

  chain <correction-slug>   procedural chain: Correction -> Guard -> Validator -> CIJob
  lane-freshness            every Lane's last landed commit vs its freshness window
  falsifier-coverage        per method: components with typed vs prose falsifiers
  belief <slug>             a Belief, its sources (exists-on-disk) and proposals
  ticker <T>                everything the graph holds about one ticker

Run ``graph_build.py`` first; this tool only reads. Output is ASCII-only
(Windows cp1252 console) -- non-ASCII characters in labels are replaced.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "_system" / "graph" / "graph.db"


def ascii_safe(text) -> str:
    return str(text if text is not None else "").encode("ascii", "replace").decode("ascii")


def table(headers: list[str], rows: list[list], indent: str = "") -> str:
    rows = [[ascii_safe(c) for c in row] for row in rows]
    headers = [ascii_safe(h) for h in headers]
    widths = [max(len(h), *(len(r[i]) for r in rows)) if rows else len(h)
              for i, h in enumerate(headers)]
    def line(cells):
        return indent + "| " + " | ".join(c.ljust(w) for c, w in zip(cells, widths)) + " |"
    sep = indent + "+-" + "-+-".join("-" * w for w in widths) + "-+"
    out = [sep, line(headers), sep]
    out.extend(line(r) for r in rows)
    out.append(sep)
    return "\n".join(out)


def connect(db_path: Path) -> sqlite3.Connection:
    if not db_path.is_file():
        print(f"graph db not found at {db_path}; run graph_build.py first")
        raise SystemExit(2)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def edges_from(conn, src: str, etype: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT e.dst, e.data_json, n.type, n.label, n.status, n.path"
        " FROM edges e JOIN nodes n ON n.id = e.dst"
        " WHERE e.src = ? AND e.type = ? ORDER BY e.dst", (src, etype)).fetchall()


def edges_to(conn, dst: str, etype: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT e.src, e.data_json, n.type, n.label, n.status, n.path"
        " FROM edges e JOIN nodes n ON n.id = e.src"
        " WHERE e.dst = ? AND e.type = ? ORDER BY e.src", (dst, etype)).fetchall()


# --------------------------------------------------------------------------- #
# queries
# --------------------------------------------------------------------------- #

def cmd_chain(conn, slug: str) -> int:
    node = conn.execute("SELECT * FROM nodes WHERE id = ?",
                        (f"correction:{slug}",)).fetchone()
    if node is None:
        matches = conn.execute(
            "SELECT id FROM nodes WHERE type='Correction' AND id LIKE ?"
            " ORDER BY id", (f"correction:%{slug}%",)).fetchall()
        if len(matches) == 1:
            node = conn.execute("SELECT * FROM nodes WHERE id = ?",
                                (matches[0]["id"],)).fetchone()
        else:
            print(f"no unique correction matching '{ascii_safe(slug)}'"
                  f" ({len(matches)} candidates)")
            for m in matches:
                print("  " + ascii_safe(m["id"]))
            return 1
    print("correction: " + ascii_safe(node["id"][len("correction:"):]))
    print("status:     " + ascii_safe(node["status"]))
    print("error:      " + ascii_safe(json.loads(node["data_json"]).get("error", ""))[:150])
    rows = []
    guards = edges_from(conn, node["id"], "GUARDED_BY")
    if not guards:
        print("chain:      NO GUARD registered (P1: a TODO wearing a correction's clothes)")
        return 0
    for guard in guards:
        validators = edges_from(conn, guard["dst"], "ENFORCED_BY")
        if not validators:
            rows.append([guard["dst"][len("guard:"):], "-", "-", "NO ENFORCER"])
        for validator in validators:
            jobs = edges_from(conn, validator["dst"], "INVOKED_BY")
            if not jobs:
                rows.append([guard["dst"][len("guard:"):],
                             validator["dst"][len("validator:"):], "-",
                             "NOT IN CI (P2 orphan)"])
            for job in jobs:
                rows.append([guard["dst"][len("guard:"):],
                             validator["dst"][len("validator:"):],
                             job["label"], "wired"])
    print(table(["guard", "validator", "ci job", "state"], rows))
    return 0


def cmd_lane_freshness(conn) -> int:
    now = datetime.now(timezone.utc)
    rows = []
    stale = 0
    for node in conn.execute("SELECT * FROM nodes WHERE type='Lane' ORDER BY id"):
        data = json.loads(node["data_json"])
        window = data.get("freshness_hours", 48)
        last = data.get("last_commit_iso")
        if last:
            age_h = (now - datetime.fromisoformat(last)).total_seconds() / 3600.0
            state = "FRESH" if age_h <= window else "STALE"
            age_text = f"{age_h:.1f}"
        else:
            age_text, state = "-", "NO-COMMIT"
        if state != "FRESH":
            stale += 1
        rows.append([node["label"], last or "-", age_text, window, state,
                     data.get("commit_count_in_window", 0)])
    print(table(["lane", "last commit", "age h", "window h", "state",
                 "commits in window"], rows))
    return 1 if stale else 0


def cmd_falsifier_coverage(conn) -> int:
    # Best falsifier per component: typed > prose/untestable > none. E1 asks
    # which components carry a *typed* falsifier, so a component with both a
    # prose string and a typed spec counts once, as typed.
    best: dict[str, tuple[str, int]] = {}  # component id -> (method, rank)
    ranks = {"typed": 2, "prose": 1, "untestable": 1, None: 0}
    for row in conn.execute(
            "SELECT n.id AS comp_id, n.data_json AS comp_data, f.status AS fstatus"
            " FROM nodes n"
            " LEFT JOIN edges e ON e.src = n.id AND e.type = 'ASSERTS'"
            " LEFT JOIN nodes f ON f.id = e.dst"
            " WHERE n.type = 'Component'"):
        method = json.loads(row["comp_data"]).get("method") or "(none)"
        rank = ranks.get(row["fstatus"], 0)
        prior = best.get(row["comp_id"])
        if prior is None or rank > prior[1]:
            best[row["comp_id"]] = (method, rank)
    per_method: dict[str, list[int]] = {}
    for method, rank in best.values():
        bucket = per_method.setdefault(method, [0, 0, 0])  # typed, prose, none
        bucket[2 - rank] += 1
    rows = []
    total_typed = total = 0
    for method in sorted(per_method):
        typed, prose, none = per_method[method]
        n = typed + prose + none
        pct = 100.0 * typed / n if n else 0.0
        rows.append([method, n, typed, prose, none, f"{pct:.1f}%"])
        total_typed += typed
        total += n
    pct = 100.0 * total_typed / total if total else 0.0
    rows.append(["TOTAL", total, total_typed, "-", "-", f"{pct:.1f}%"])
    print(table(["method", "components", "typed", "prose/untestable",
                 "no falsifier", "typed %"], rows))
    return 0


def cmd_belief(conn, slug: str) -> int:
    node = conn.execute("SELECT * FROM nodes WHERE id = ?",
                        (f"belief:{slug}",)).fetchone()
    if node is None:
        matches = conn.execute(
            "SELECT id FROM nodes WHERE type='Belief' AND id LIKE ?"
            " ORDER BY id", (f"belief:%{slug}%",)).fetchall()
        if len(matches) == 1:
            node = conn.execute("SELECT * FROM nodes WHERE id = ?",
                                (matches[0]["id"],)).fetchone()
        else:
            print(f"no unique belief matching '{ascii_safe(slug)}'"
                  f" ({len(matches)} candidates)")
            for m in matches[:20]:
                print("  " + ascii_safe(m["id"]))
            return 1
    data = json.loads(node["data_json"])
    print("belief:  " + ascii_safe(node["id"][len("belief:"):]))
    print("lens:    " + ascii_safe(data.get("lens")))
    print("status:  " + ascii_safe(f"{node['status']} {node['as_of']}"
                                   + (" (agent)" if data.get("agent_approved") else "")))
    print("text:    " + ascii_safe(data.get("text", ""))[:300])
    sources = edges_from(conn, node["id"], "SUPPORTED_BY")
    rows = [[s["dst"][len("source:"):], s["status"]] for s in sources]
    print(table(["supported by", "on disk"], rows) if rows
          else "supported by: (no source edges)")
    superseded = edges_from(conn, node["id"], "SUPERSEDES")
    for s in superseded:
        print("supersedes: " + ascii_safe(s["dst"]))
    proposals = edges_from(conn, node["id"], "DISTILLED_FROM")
    for p in proposals:
        print("distilled from: " + ascii_safe(p["dst"]) + " ["
              + ascii_safe(p["status"]) + "]")
    return 0


def cmd_ticker(conn, ticker: str) -> int:
    node = conn.execute("SELECT * FROM nodes WHERE id = ?",
                        (f"ticker:{ticker}",)).fetchone()
    if node is None:
        print(f"no ticker node for '{ascii_safe(ticker)}'")
        return 1
    print("ticker: " + ascii_safe(ticker) + "  " + ascii_safe(node["label"]))
    contract = conn.execute("SELECT * FROM nodes WHERE id = ?",
                            (f"contract:{ticker}",)).fetchone()
    if contract:
        print(f"contract: {ascii_safe(contract['status'])}"
              f" as_of {ascii_safe(contract['as_of'])}")
        for blocker in edges_to(conn, contract["id"], "BLOCKS"):
            print("  blocked by: " + ascii_safe(blocker["label"])[:150])
    counts = {}
    for row in conn.execute(
            "SELECT type, COUNT(*) AS n FROM nodes WHERE ticker = ? GROUP BY type"
            " ORDER BY type", (ticker,)):
        counts[row["type"]] = row["n"]
    print(table(["node type", "count"], [[k, v] for k, v in sorted(counts.items())]))
    comps = conn.execute(
        "SELECT id, label, status, data_json FROM nodes"
        " WHERE type='Component' AND ticker = ? ORDER BY id", (ticker,)).fetchall()
    rows = []
    for comp in comps:
        method = json.loads(comp["data_json"]).get("method")
        falsifiers = edges_from(conn, comp["id"], "ASSERTS")
        fstate = ",".join(sorted({f["status"] for f in falsifiers})) or "none"
        rows.append([comp["id"].split(":", 2)[2], method, comp["status"], fstate])
    if rows:
        print(table(["component", "method", "status", "falsifiers"], rows))
    runs = edges_to(conn, f"ticker:{ticker}", "ABOUT")
    run_rows = [[r["src"], r["type"]] for r in runs if r["type"] in ("Run", "Wave")]
    if run_rows:
        print(table(["work-plane link", "type"], run_rows))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    sub = parser.add_subparsers(dest="command", required=True)
    p_chain = sub.add_parser("chain", help="Correction -> Guard -> Validator -> CIJob")
    p_chain.add_argument("slug")
    sub.add_parser("lane-freshness", help="lane last-commit age vs freshness window")
    sub.add_parser("falsifier-coverage", help="typed falsifier coverage per method")
    p_belief = sub.add_parser("belief", help="belief, sources, distilled proposals")
    p_belief.add_argument("slug")
    p_ticker = sub.add_parser("ticker", help="everything about one ticker")
    p_ticker.add_argument("ticker")
    args = parser.parse_args()
    conn = connect(args.db)
    try:
        if args.command == "chain":
            return cmd_chain(conn, args.slug)
        if args.command == "lane-freshness":
            return cmd_lane_freshness(conn)
        if args.command == "falsifier-coverage":
            return cmd_falsifier_coverage(conn)
        if args.command == "belief":
            return cmd_belief(conn, args.slug)
        if args.command == "ticker":
            return cmd_ticker(conn, args.ticker)
    finally:
        conn.close()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
