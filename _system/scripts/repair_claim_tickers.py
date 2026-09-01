#!/usr/bin/env python3
"""Re-attribute stored podcast claims after a ticker-validation fix.

The claims, quotes, figures and theses in the corpus are sound -- they were
read off the transcript and verified against it. Only the *symbol* attached to
each claim was wrong, because `validate_tickers` matched company names by raw
characters and by "does this symbol exist" rather than "is this symbol this
company". Four Costco claims were rewritten onto CMRE (a Greek containership
lessor) and a Vanguard claim was left sitting on IVZ (Invesco).

So this is a repair, not a re-run. Re-analysing the affected episodes would
cost roughly nine minutes of GPU each to regenerate text that is already
correct; re-validating costs milliseconds and touches nothing but the ticker
fields. The model's original symbol is recoverable because the old code
recorded what it overwrote (`ticker_corrected_from`) and what it discarded
(`ticker_rejected`), so each claim can be returned to what the model actually
said and put back through the fixed validator.

`transcript_sha1` is deliberately left alone: the transcript did not change, so
the batch runner should not re-analyse these episodes afterwards.

    python _system/scripts/repair_claim_tickers.py --dry-run
    python _system/scripts/repair_claim_tickers.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

# Episode titles come from RSS feeds and carry whatever the publisher typed --
# en dashes, smart quotes, and on 2026-08-29 a U+2060 WORD JOINER that killed a
# run outright. Python picks cp1252 for a redirected stdout on Windows, so the
# progress line that *reports* a finished episode was the thing that crashed:
# 730 episodes still to do, the process gone, and the last log line a normal
# success. Same idiom as build_memory_digest.py.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from analyze_podcast_episode import (  # noqa: E402
    _clean_ticker, build_aliases, resolve_tickers, validate_tickers,
)
from vault_paths import podcasts_root  # noqa: E402


def restore_model_tickers(claims: list[dict]) -> None:
    """Put each claim back to the symbol the model actually emitted."""
    for claim in claims:
        original = claim.pop("ticker_corrected_from", None)
        rejected = claim.pop("ticker_rejected", None)
        if original is not None:
            claim["ticker"] = original
        elif rejected is not None:
            claim["ticker"] = rejected
        claim["ticker"] = _clean_ticker(claim.get("ticker"))


def revalidate(analysis: dict, aliases: dict[str, str]) -> dict:
    """Re-run attribution over stored claims. Returns what changed."""
    claims = [c for c in (analysis.get("claims") or []) if isinstance(c, dict)]
    before = {id(c): c.get("ticker") for c in claims}
    restore_model_tickers(claims)
    analysis["tickers_rejected"] = validate_tickers(claims, aliases)
    analysis["tickers_resolved_post_hoc"] = resolve_tickers(claims, aliases)

    # Same rule as analyze(): the episode's ticker list is the symbols that
    # survived validation on a claim, in first-seen order.
    survivors = [t for t in (c.get("ticker") for c in claims) if t]
    analysis["tickers"] = list(dict.fromkeys(survivors))

    changed = [
        {"company": c.get("company"), "from": before[id(c)], "to": c.get("ticker")}
        for c in claims
        if before[id(c)] != c.get("ticker")
    ]
    return {"claims": len(claims), "changed": changed, "tickers": analysis["tickers"]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="Report and write nothing.")
    args = ap.parse_args()

    aliases = build_aliases()
    root = podcasts_root(create=False)
    if root is None or not (root / "episodes").is_dir():
        print("no vault corpus found", file=sys.stderr)
        return 1

    episodes = touched = total_changed = 0
    for meta_path in sorted((root / "episodes").rglob("*.meta.json")):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        analysis = meta.get("llm_analysis")
        if not isinstance(analysis, dict) or not analysis.get("claims"):
            continue
        episodes += 1
        before = json.dumps(meta, indent=2, ensure_ascii=False, sort_keys=True)
        report = revalidate(analysis, aliases)
        after = json.dumps(meta, indent=2, ensure_ascii=False, sort_keys=True)
        if report["changed"]:
            touched += 1
            total_changed += len(report["changed"])
            print(f"{meta.get('title', meta_path.stem)[:52]:<54} "
                  f"{len(report['changed'])}/{report['claims']} claims re-attributed")
            for row in report["changed"]:
                print(f"    {str(row['from']):>6} -> {str(row['to']):<6}  {row['company']}")
        # Write on any difference, not only a re-attribution. `ticker_basis`
        # records which rule placed each claim, and it is worth nothing if it
        # exists only on the episodes that happened to need correcting -- the
        # point of it is to make the next variant of this bug visible across the
        # whole corpus without a hand audit.
        if after != before and not args.dry_run:
            meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
                                 encoding="utf-8")

    verb = "would re-attribute" if args.dry_run else "re-attributed"
    print(f"\n{verb} {total_changed} claims across {touched} of {episodes} analysed episodes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
