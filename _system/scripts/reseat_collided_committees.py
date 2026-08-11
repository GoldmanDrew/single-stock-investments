#!/usr/bin/env python3
"""Re-seat committees whose raters collapse below the independence quorum.

Remediation for the divergent GROUPS maps (corrections.md 2026-08-11): the
committee pipeline's copy was missing munger and lawrence, and its
``.get(persona, persona)`` fallback minted each a private independence group,
so 31 manifests seated ``[buffett_weschler, hohn, munger]`` -- two
``quality_reinvestment`` seats out of three -- and passed the
three-distinct-groups check anyway. Future seatings are fixed at the source
(``persona_groups.py``); the manifests already on disk are not, and invariant
L6 counts them until they are.

Preservation rules, all three learned the expensive way (the AAOI vote loss,
corrections.md 2026-08-09):

  * **No vote file is ever deleted.** A vote by a de-seated rater stays on
    disk as an orphan: it is a real opinion someone paid for, it just no
    longer counts toward a quorum it never legitimately formed.
  * **No assembled record is deleted.** A record built on the old seating is
    renamed to ``committee_<date>-superseded-<hash8>.json``, which
    deliberately breaks the ``committee_????-??-??.json`` glob every reader
    uses -- it stops being the authority while staying auditable.
  * **The packet is never re-frozen.** Re-seating changes who reviews, not
    what they review, so the frozen evidence and its hash are untouched and
    the surviving raters' votes stay valid against it.

A committee sitting at ``committee_complete_decision_pending`` reverts to
``round_one_open``: a capital decision must not be recorded on a seating that
is being replaced. Stages blocked for unrelated reasons (``evidence_blocked``,
``parked``) keep their stage -- this script fixes independence, not evidence.

Usage:
    python _system/scripts/reseat_collided_committees.py            # dry run
    python _system/scripts/reseat_collided_committees.py --apply
    python _system/scripts/reseat_collided_committees.py --ticker ADBE --apply

Output is ASCII-only (Windows cp1252 console; the recorded trap).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import investment_committee_pipeline as icp  # noqa: E402
from persona_groups import INDEPENDENCE_GROUPS, INDEPENDENCE_QUORUM  # noqa: E402

# Stages that mean "this committee is blocked for a reason re-seating does not
# address"; the seating is corrected but the stage is left alone.
KEEP_STAGE = {"evidence_blocked", "parked", "superseded"}
# A decision must never be recorded on a seating that is being replaced.
REVERT_TO_OPEN = {"committee_complete_decision_pending"}


def canonical_groups(raters: list[str]) -> set[str]:
    """Groups under the canonical map, with NO id-becomes-its-own-group
    fallback -- that fallback is the defect being repaired."""
    return {INDEPENDENCE_GROUPS[p] for p in raters if p in INDEPENDENCE_GROUPS}


def collided(raters: list[str]) -> bool:
    unknown = [p for p in raters if p not in INDEPENDENCE_GROUPS]
    return bool(unknown) or len(canonical_groups(raters)) < INDEPENDENCE_QUORUM


def load_valuation(ticker: str) -> dict:
    research = ROOT / ticker / "research"
    valuation = icp.read_json(research / "valuation.json")
    route = research / "valuation_route.json"
    if route.exists():
        valuation["valuation_method_route"] = icp.read_json(route)
    return valuation


def archive_assembled(ticker: str, as_of: str, apply: bool) -> str | None:
    """Rename an assembled record built on the old seating out of the reader
    glob. Unlike archive_stale_assembled() this does not key on the packet
    hash: the packet is unchanged here -- what went stale is who voted."""
    path = ROOT / ticker / "research" / f"committee_{as_of}.json"
    if not path.exists():
        return None
    recorded = icp.assembled_packet_hash(ticker, as_of) or "noreseat"
    archive = icp.stale_archive_name(path, as_of, recorded[:8])
    if apply:
        path.rename(archive)
    return archive.relative_to(ROOT).as_posix()


def reseat(manifest_path: Path, apply: bool) -> dict:
    work = manifest_path.parent
    manifest = icp.read_json(manifest_path)
    ticker = str(manifest.get("ticker") or manifest_path.parents[3].name)
    as_of = str(manifest.get("as_of") or work.name)
    previous = [row.get("persona") for row in manifest.get("selected_raters") or []
                if isinstance(row, dict)]
    row: dict = {
        "ticker": ticker, "as_of": as_of, "previous_raters": previous,
        "previous_stage": str(manifest.get("stage") or ""),
    }

    raters = icp.select_raters(load_valuation(ticker))
    new_personas = [r["persona"] for r in raters]
    groups = {r["independence_group"] for r in raters}
    row["new_raters"] = new_personas
    if len(groups) < INDEPENDENCE_QUORUM:
        row["status"] = "unfixable"
        row["detail"] = (f"route offers only {len(groups)} independence"
                         " group(s); needs a routing or persona decision")
        return row

    dropped = [p for p in previous if p not in new_personas]
    orphans = sorted(
        path.relative_to(work).as_posix()
        for persona in dropped
        for path in work.glob(f"round_*/{persona}.json")
    )
    row["dropped"] = dropped
    row["added"] = [p for p in new_personas if p not in previous]
    row["orphaned_votes"] = orphans
    row["preserved_votes"] = sorted(
        path.relative_to(work).as_posix() for path in icp.vote_files(work)
        if path.stem in new_personas)

    stage = str(manifest.get("stage") or "")
    new_stage = stage if stage in KEEP_STAGE else (
        "round_one_open" if stage in REVERT_TO_OPEN else stage)
    row["new_stage"] = new_stage
    row["archived_assembled"] = archive_assembled(ticker, as_of, apply)
    row["status"] = "reseated"

    if not apply:
        return row

    manifest["selected_raters"] = raters
    manifest["stage"] = new_stage
    manifest.setdefault("reseat_history", []).append({
        "at": datetime.now(timezone.utc).isoformat(),
        "reason": "independence_collision",
        "detail": ("raters collapsed below the independence quorum under the"
                   " canonical persona_groups map; re-seated from the power"
                   " zone route. Votes by de-seated raters are preserved on"
                   " disk and no longer count."),
        "previous_raters": previous,
        "new_raters": new_personas,
        "previous_stage": stage,
        "orphaned_votes": orphans,
        "archived_assembled": row["archived_assembled"],
    })
    icp.write_json(manifest_path, manifest)

    # Re-issue prompts against the UNCHANGED packet hash, then drop prompts
    # for de-seated raters so no dispatcher hands out a seat that no longer
    # exists. Vote files are never touched.
    icp.write_prompts(ticker, work, manifest["packet_hash"],
                      manifest.get("evidence") or [], raters)
    for persona in dropped:
        for stale in work.glob(f"round_*/{persona}.prompt.md"):
            stale.unlink()

    try:
        from build_valuation_workbench import write as write_workbench
        write_workbench(ticker, as_of)
    except Exception as error:                      # noqa: BLE001
        row["workbench_error"] = f"{type(error).__name__}: {error}"
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true",
                        help="write changes (default is a dry run)")
    parser.add_argument("--ticker", action="append", type=str.upper,
                        help="limit to these tickers (repeatable)")
    args = parser.parse_args()

    rows = []
    for manifest_path in sorted(ROOT.glob("*/research/committee_work/*/manifest.json")):
        manifest = icp.read_json(manifest_path)
        if str(manifest.get("stage") or "") == "superseded":
            continue
        raters = [row.get("persona") for row in manifest.get("selected_raters") or []
                  if isinstance(row, dict)]
        if not raters or not collided(raters):
            continue
        ticker = str(manifest.get("ticker") or manifest_path.parents[3].name)
        if args.ticker and ticker not in args.ticker:
            continue
        rows.append(reseat(manifest_path, args.apply))

    mode = "APPLIED" if args.apply else "DRY RUN (use --apply to write)"
    print(f"reseat collided committees -- {mode}")
    print(f"collided manifests: {len(rows)}")
    for row in rows:
        print(f"  {row['ticker']:<8} {row['as_of']} {row['status']}"
              f" {'+'.join(row.get('added') or []) or '-'}"
              f" over {'+'.join(row.get('dropped') or []) or '-'}"
              f" | stage {row['previous_stage']} -> {row.get('new_stage', '(kept)')}"
              f" | orphaned votes {len(row.get('orphaned_votes') or [])}"
              f" | assembled {row.get('archived_assembled') or '-'}")
    unfixable = [row for row in rows if row["status"] == "unfixable"]
    if unfixable:
        print(f"\n{len(unfixable)} manifest(s) could not be re-seated:")
        for row in unfixable:
            print(f"  {row['ticker']}: {row['detail']}")
    print(json.dumps({"collided": len(rows),
                      "reseated": len(rows) - len(unfixable),
                      "unfixable": len(unfixable),
                      "applied": args.apply}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
