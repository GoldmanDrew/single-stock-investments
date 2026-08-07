#!/usr/bin/env python3
"""Run the full SSI Perplexity-grade chain (Phases 1-4) over many tickers.

Phases are deterministic and additive; this is a batch driver with a coverage
report, not new analysis logic. Each ticker runs independently — one failure
never stops the sweep, and the summary states exactly what was skipped and why
(no silent truncation).

  Phase 1  build_ssi_evidence_pack.py   → hashed pack (+ XBRL series)
  Phase 2  build_ssi_claims.py          → atomic claims, ledger, spawner
  Phase 3  verify_ssi_claims.py         → Skeptic verification, time-zero
  Phase 4  build_ssi_report.py          → §4 report + §5 gate

Usage:
  python _system/scripts/run_ssi_pipeline.py                  # all with _text
  python _system/scripts/run_ssi_pipeline.py TBBK ABX
  python _system/scripts/run_ssi_pipeline.py --holdings       # portfolio only
  python _system/scripts/run_ssi_pipeline.py --gated-only     # skip tickers with no YoY pair
  python _system/scripts/run_ssi_pipeline.py --limit 25 --json out.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

ROOT = SCRIPT_DIR.parents[1]

PHASES = (
    ("pack", "build_ssi_evidence_pack.py"),
    ("claims", "build_ssi_claims.py"),
    ("verify", "verify_ssi_claims.py"),
    ("report", "build_ssi_report.py"),
)


def _run(script: str, ticker: str, as_of: str) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / script), ticker, "--date", as_of],
        cwd=ROOT, text=True, capture_output=True,
    )
    err = (proc.stderr or proc.stdout or "").strip().splitlines()
    return proc.returncode, (err[-1][:200] if err else "")


def _holdings() -> list[str]:
    path = ROOT / "_system" / "portfolio" / "holdings.md"
    out: list[str] = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("|") and not line.startswith("| Ticker") and not line.startswith("|--"):
            cells = [c.strip() for c in line.split("|") if c.strip()]
            if cells and cells[0] not in ("Ticker", "--------"):
                out.append(cells[0])
    return out


def _gated_comparisons(ticker: str, as_of: str, prefer_disk: bool = False) -> int:
    """Read-only pre-check: how many cross-filing comparisons would the gate make?

    Rebuilding the pack just to count is the single most expensive step in the
    sweep, so when Phase 1 is not being re-run the on-disk pack is authoritative
    and is read instead. Falls back to building if there is no pack yet.
    """
    if prefer_disk:
        path = ROOT / ticker / "research" / "evidence" / f"ssi_evidence_pack_{as_of}.json"
        if path.exists():
            try:
                pack = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return -1
            return sum(1 for c in pack.get("comparisons", []) if c.get("gate", {}).get("matched"))

    from build_ssi_evidence_pack import build_evidence_pack

    try:
        pack = build_evidence_pack(ROOT / ticker, as_of)
    except Exception:
        return -1
    return sum(1 for c in pack.get("comparisons", []) if c.get("gate", {}).get("matched"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tickers", nargs="*")
    parser.add_argument("--date", default=datetime.now().date().isoformat())
    parser.add_argument("--holdings", action="store_true", help="run the portfolio holdings list")
    parser.add_argument("--gated-only", action="store_true",
                        help="skip tickers whose comparability gate finds no prior-year pair")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--json", dest="json_out", help="write the summary to this path")
    parser.add_argument(
        "--phases", default="",
        help="comma-separated subset of pack,claims,verify,report (default: all). "
             "Use e.g. --phases claims,verify,report to re-run scoring and rendering "
             "over existing evidence packs.")
    args = parser.parse_args(argv)

    phases = PHASES
    if args.phases:
        wanted = [p.strip() for p in args.phases.split(",") if p.strip()]
        known = {name for name, _ in PHASES}
        unknown = [p for p in wanted if p not in known]
        if unknown:
            parser.error(f"unknown phase(s): {', '.join(unknown)}; valid: {', '.join(known)}")
        phases = tuple(p for p in PHASES if p[0] in wanted)
    skipping_pack = "pack" not in {name for name, _ in phases}

    if args.tickers:
        # Ticker lists are routinely piped in from files; on Windows those
        # carry \r, which silently turns every name into a "no_folder" skip.
        tickers = [t.strip() for t in args.tickers if t.strip()]
    elif args.holdings:
        tickers = _holdings()
    else:
        tickers = sorted(
            p.parents[2].name for p in ROOT.glob("*/research/evidence/_text") if p.is_dir()
        )
    if args.limit:
        tickers = tickers[: args.limit]

    rows: list[dict] = []
    for i, ticker in enumerate(tickers, start=1):
        if not (ROOT / ticker).is_dir():
            rows.append({"ticker": ticker, "status": "skipped", "reason": "no_folder"})
            continue
        gated = _gated_comparisons(ticker, args.date, prefer_disk=skipping_pack)
        if args.gated_only and gated <= 0:
            rows.append({"ticker": ticker, "status": "skipped",
                         "reason": "no_gated_comparison", "gated": gated})
            print(f"[{i}/{len(tickers)}] {ticker}: skip (no gated comparison)")
            continue
        row: dict = {"ticker": ticker, "gated_comparisons": gated, "phases": {}}
        failed_at = None
        for name, script in phases:
            code, tail = _run(script, ticker, args.date)
            row["phases"][name] = "ok" if code == 0 else f"fail:{tail}"
            if code != 0:
                failed_at = name
                break
        row["status"] = "ok" if failed_at is None else f"failed_at_{failed_at}"

        gate_path = ROOT / ticker / "research" / "evidence" / f"ssi_report_gate_{args.date}.json"
        if gate_path.exists():
            try:
                gate = json.loads(gate_path.read_text(encoding="utf-8"))
                row["gate_result"] = gate.get("result")
                row["gate_fails"] = [c["name"] for c in gate["checks"] if c["verdict"] == "FAIL"]
            except (OSError, json.JSONDecodeError):
                pass
        verified_path = ROOT / ticker / "research" / "evidence" / f"ssi_verified_claims_{args.date}.json"
        if verified_path.exists():
            try:
                v = json.loads(verified_path.read_text(encoding="utf-8"))
                row["verified"] = v.get("verified_count")
                row["failed"] = v.get("failed_count")
                row["severity5"] = sum(
                    1 for c in v.get("verified_claims", []) if c.get("severity") == 5
                )
            except (OSError, json.JSONDecodeError):
                pass
        rows.append(row)
        print(
            f"[{i}/{len(tickers)}] {ticker}: {row['status']} | gated={gated} | "
            f"verified={row.get('verified', '—')} sev5={row.get('severity5', '—')} | "
            f"gate={row.get('gate_result', '—')}"
        )

    ok = [r for r in rows if r["status"] == "ok"]
    skipped = [r for r in rows if r["status"] == "skipped"]
    failed = [r for r in rows if r["status"].startswith("failed")]
    summary = {
        "as_of": args.date,
        "attempted": len(rows),
        "ok": len(ok),
        "skipped": len(skipped),
        "failed": len(failed),
        "with_gated_comparison": sum(1 for r in rows if (r.get("gated_comparisons") or 0) > 0),
        "total_verified_claims": sum(r.get("verified") or 0 for r in ok),
        "total_severity5": sum(r.get("severity5") or 0 for r in ok),
        "shippable": sum(1 for r in ok if r.get("gate_result") == "SHIPPABLE"),
        "draft_blocked": sum(1 for r in ok if r.get("gate_result") == "DRAFT (blocked)"),
        "not_shippable": sum(1 for r in ok if r.get("gate_result") == "NOT SHIPPABLE"),
        "rows": rows,
    }
    print("\n=== SSI pipeline summary ===")
    for key in ("attempted", "ok", "skipped", "failed", "with_gated_comparison",
                "total_verified_claims", "total_severity5", "shippable",
                "draft_blocked", "not_shippable"):
        print(f"  {key:24s} {summary[key]}")
    if skipped:
        reasons: dict[str, int] = {}
        for r in skipped:
            reasons[r.get("reason", "?")] = reasons.get(r.get("reason", "?"), 0) + 1
        print(f"  skipped reasons          {reasons}")
    if failed:
        print(f"  failures                 {[r['ticker'] for r in failed][:15]}")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(f"\nWrote {args.json_out}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
