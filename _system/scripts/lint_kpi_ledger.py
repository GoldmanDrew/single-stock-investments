#!/usr/bin/env python3
"""Lint per-ticker World Model KPI ledgers.

  python _system/scripts/lint_kpi_ledger.py
  python _system/scripts/lint_kpi_ledger.py TPL APLD
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import world_model_common as wm  # noqa: E402


def lint_ledger(ticker: str, ledger: dict) -> list[str]:
    errors: list[str] = []
    if ledger.get("ticker") and ledger.get("ticker") != ticker:
        errors.append(f"{ticker}: ticker field mismatch ({ledger.get('ticker')})")
    kpis = ledger.get("kpis")
    if not isinstance(kpis, list):
        errors.append(f"{ticker}: kpis must be a list")
        return errors
    # A newly scaffolded industry may legitimately have no thesis-narrow KPI
    # until the first filing review. Keep it visible but do not fail the whole
    # weekly World Model pipeline for that acknowledged state.
    if not kpis and not (ledger.get("scaffold_meta") or {}).get("note"):
        errors.append(f"{ticker}: empty kpis require scaffold_meta.note")
        return errors
    if len(kpis) > 15:
        errors.append(f"{ticker}: more than 15 KPIs ({len(kpis)}); keep thesis-narrow")

    val_path = wm.ROOT / ticker / "research" / "valuation.json"
    val = wm.load_json(val_path) if val_path.exists() else {}

    seen: set[str] = set()
    today = date.today()
    for kpi in kpis:
        kid = kpi.get("kpi_id")
        if not kid:
            errors.append(f"{ticker}: KPI missing kpi_id")
            continue
        if kid in seen:
            errors.append(f"{ticker}: duplicate kpi_id {kid}")
        seen.add(kid)

        if kpi.get("status") not in wm.STATUS_VALUES:
            errors.append(f"{ticker}/{kid}: invalid status {kpi.get('status')!r}")

        expected = kpi.get("expected") or {}
        if expected.get("op") and expected.get("op") not in wm.EXPECTED_OPS:
            errors.append(f"{ticker}/{kid}: invalid expected.op {expected.get('op')!r}")

        if kpi.get("in_base_irr") is True:
            errors.append(
                f"{ticker}/{kid}: in_base_irr=true requires human promotion "
                "(lint forbids silent base-IRR flags on World Model rows)"
            )

        binds = kpi.get("binds_to") or {}
        vpath = binds.get("valuation_path")
        note = binds.get("note")
        if not vpath and not note:
            errors.append(f"{ticker}/{kid}: binds_to needs valuation_path or note")
        if vpath:
            # Binding *to* segment_build / growth paths is allowed; rewriting them is not.
            if not val:
                errors.append(f"{ticker}/{kid}: valuation.json missing for bind check")
            elif not wm.path_exists(val, vpath):
                errors.append(f"{ticker}/{kid}: valuation_path not found: {vpath}")

        last = wm.parse_as_of(kpi.get("last_checked"))
        if last and (today - last).days > wm.STALE_DAYS:
            if kpi.get("status") != "stale":
                errors.append(
                    f"{ticker}/{kid}: last_checked {kpi.get('last_checked')} "
                    f">{wm.STALE_DAYS}d — mark status stale or re-check"
                )

        on_fail = binds.get("on_fail")
        if on_fail and on_fail not in ("human_review", "stance_only", "open_diligence"):
            errors.append(f"{ticker}/{kid}: binds_to.on_fail must be human_review, stance_only, or open_diligence")

    summary = ledger.get("summary") or {}
    computed = wm.summarize_statuses(kpis)
    for key in ("pass", "fail", "stale", "unchecked"):
        if key in summary and int(summary[key]) != computed[key]:
            errors.append(
                f"{ticker}: summary.{key}={summary[key]} but computed {computed[key]}"
            )
    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("tickers", nargs="*", help="Limit to these tickers (default: all ledgers)")
    args = ap.parse_args()
    wanted = set(args.tickers) if args.tickers else None

    all_errors: list[str] = []
    count = 0
    for ticker, _path, ledger in wm.iter_kpi_ledgers():
        if wanted and ticker not in wanted:
            continue
        count += 1
        all_errors.extend(lint_ledger(ticker, ledger))

    if wanted:
        for t in args.tickers:
            p = wm.ROOT / t / "research" / "kpi_ledger.json"
            if not p.exists():
                all_errors.append(f"{t}: missing research/kpi_ledger.json")

    if all_errors:
        for e in all_errors:
            print(f"ERROR: {e}")
        print(f"lint_kpi_ledger: {len(all_errors)} error(s)")
        return 1
    print(f"lint_kpi_ledger: ok ({count} ledger(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
