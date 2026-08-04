#!/usr/bin/env python3
"""Validate and compile the Short Alpha hypothesis ledger for the static dashboard."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "_system" / "research" / "short-alpha" / "ideas.json"
OUTPUT = ROOT / "dashboard" / "data" / "short_alpha.json"


class LedgerError(ValueError):
    """Raised when the source ledger would produce a misleading dashboard."""


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LedgerError(f"Missing Short Alpha source: {path.relative_to(ROOT)}") from exc
    except json.JSONDecodeError as exc:
        raise LedgerError(f"Invalid JSON in {path.relative_to(ROOT)}: {exc}") from exc
    if not isinstance(value, dict):
        raise LedgerError("Short Alpha root must be an object")
    return value


def _validate(raw: dict) -> None:
    framework_ids = [str(row.get("id") or "") for row in raw.get("frameworks") or []]
    source_ids = [str(row.get("id") or "") for row in raw.get("source_types") or []]
    if not framework_ids or len(framework_ids) != len(set(framework_ids)):
        raise LedgerError("Framework ids must be present and unique")
    if not source_ids or len(source_ids) != len(set(source_ids)):
        raise LedgerError("Source-type ids must be present and unique")

    seen: set[str] = set()
    for idea in raw.get("ideas") or []:
        ticker = str(idea.get("ticker") or "").upper()
        if not ticker or ticker in seen:
            raise LedgerError(f"Ticker must be present and unique: {ticker or '<blank>'}")
        seen.add(ticker)
        shares = float((idea.get("position") or {}).get("shares") or 0)
        exposure = float((idea.get("position") or {}).get("initial_exposure_usd") or 0)
        baseline = float((idea.get("position") or {}).get("baseline_price") or 0)
        if shares >= 0 or exposure <= 0 or baseline <= 0:
            raise LedgerError(f"{ticker}: shares must be negative and exposure/baseline positive")
        tags = idea.get("frameworks") or []
        unknown_tags = sorted(set(tags) - set(framework_ids))
        if unknown_tags:
            raise LedgerError(f"{ticker}: unknown frameworks {unknown_tags}")
        if idea.get("primary_framework") not in tags:
            raise LedgerError(f"{ticker}: primary framework must also be in frameworks")
        unknown_sources = sorted(
            {str(row.get("type") or "") for row in idea.get("sources") or []} - set(source_ids)
        )
        if unknown_sources:
            raise LedgerError(f"{ticker}: unknown source types {unknown_sources}")
        check_ins = idea.get("check_ins") or []
        if not check_ins:
            raise LedgerError(f"{ticker}: at least one dated check-in is required")
        for row in check_ins:
            if float(row.get("price") or 0) <= 0:
                raise LedgerError(f"{ticker}: check-in prices must be positive")


def _artifact_status(idea: dict) -> dict:
    ticker = str(idea["ticker"])
    research_dir = ROOT / ticker / "research"
    deep_dives = sorted(research_dir.glob("deep_dive_*.md")) if research_dir.is_dir() else []
    source_refs = [row.get("ref") for row in idea.get("sources") or [] if row.get("ref")]
    missing_refs = [str(ref) for ref in source_refs if not (ROOT / str(ref)).exists()]
    research = idea.get("research") or {}
    valuation = research_dir / "valuation.json"
    workbench = research_dir / "valuation_workbench.json"
    dossier = research_dir / "dossier.json"
    score = 0
    score += 25 if deep_dives else 0
    score += 20 if valuation.exists() else 0
    score += 15 if workbench.exists() else 0
    score += 15 if dossier.exists() else 0
    score += 15 if len(source_refs) >= 3 and not missing_refs else 0
    score += 10 if str(research.get("ic") or "").lower() in {"ready", "complete", "approved"} else 0
    return {
        "ticker_folder": (ROOT / ticker).is_dir(),
        "deep_dive_count": len(deep_dives),
        "latest_deep_dive": deep_dives[-1].relative_to(ROOT).as_posix() if deep_dives else None,
        "valuation_present": valuation.exists(),
        "workbench_present": workbench.exists(),
        "dossier_present": dossier.exists(),
        "missing_source_refs": missing_refs,
        "completion_pct": score,
    }


def build(source: Path = SOURCE) -> dict:
    raw = _read_json(source)
    _validate(raw)
    ideas: list[dict] = []
    framework_counts: Counter[str] = Counter()
    gross = 0.0
    pnl = 0.0
    complete = 0
    for source_idea in raw.get("ideas") or []:
        idea = json.loads(json.dumps(source_idea))
        idea["ticker"] = str(idea["ticker"]).upper()
        idea["artifact_status"] = _artifact_status(idea)
        check_ins = sorted(idea.get("check_ins") or [], key=lambda row: str(row.get("date") or ""))
        latest = check_ins[-1]
        position = idea["position"]
        baseline = float(position["baseline_price"])
        latest_price = float(latest["price"])
        absolute_shares = abs(float(position["shares"]))
        idea["outcome"] = {
            "latest_date": latest["date"],
            "latest_price": latest_price,
            "hypothesis_state": latest.get("hypothesis_state") or "open",
            "short_return_pct": round(((baseline - latest_price) / baseline) * 100, 2),
            "pnl_usd": round((baseline - latest_price) * absolute_shares, 2),
            "check_in_count": len(check_ins),
        }
        gross += float(position["initial_exposure_usd"])
        pnl += float(idea["outcome"]["pnl_usd"])
        for tag in idea.get("frameworks") or []:
            framework_counts[tag] += 1
        if idea["artifact_status"]["completion_pct"] >= 85:
            complete += 1
        ideas.append(idea)

    return {
        "schema_version": raw.get("schema_version", "1.0"),
        "generated_at": date.today().isoformat(),
        "as_of": raw.get("as_of"),
        "currency": raw.get("currency", "USD"),
        "summary": {
            "position_count": len(ideas),
            "gross_short_exposure_usd": round(gross, 2),
            "tracked_pnl_usd": round(pnl, 2),
            "research_complete_count": complete,
            "framework_counts": dict(sorted(framework_counts.items())),
        },
        "frameworks": raw.get("frameworks") or [],
        "source_types": raw.get("source_types") or [],
        "ideas": ideas,
        "methodology": {
            "short_return": "(baseline_price - latest_price) / baseline_price",
            "pnl": "(baseline_price - latest_price) * abs(shares)",
            "warning": "Borrow fees, dividends, financing costs, taxes, locate availability, slippage, and corporate actions are not included unless recorded in a check-in note.",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--check", action="store_true", help="Validate and print summary without writing")
    args = parser.parse_args()
    payload = build(args.source)
    if args.check:
        print(json.dumps(payload["summary"], indent=2))
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output.relative_to(ROOT)} ({len(payload['ideas'])} ideas)")


if __name__ == "__main__":
    main()
