#!/usr/bin/env python3
"""Freeze non-actionable committee forecasts without inventing owner decisions."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEDGER_REL = Path("_system/research/committee_forecasts.jsonl")


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def freeze(root: Path = ROOT, write: bool = True) -> list[dict]:
    ledger = root / LEDGER_REL
    existing = _rows(ledger)
    seen = {row.get("forecast_id") for row in existing}
    fresh = []
    for path in sorted(root.glob("*/research/committee_????-??-??.json")):
        committee = json.loads(path.read_text(encoding="utf-8"))
        if committee.get("final_state") not in {
                "committee_complete_decision_pending", "owner_decision_pending", "outcome_tracking"}:
            continue
        votes = (committee.get("round_two") or {}).get("votes") or []
        if not votes:
            continue
        ticker = str(committee.get("ticker") or path.parents[1].name).upper()
        committee_ref = str(path.relative_to(root)).replace("\\", "/")
        packet_hash = str((committee.get("evidence_packet") or {}).get("packet_hash") or "")
        forecast_id = hashlib.sha256(f"{committee_ref}|{packet_hash}".encode()).hexdigest()[:24]
        if forecast_id in seen:
            continue
        valuation = json.loads((root / ticker / "research/valuation.json").read_text(encoding="utf-8")) \
            if (root / ticker / "research/valuation.json").exists() else {}
        contract = valuation.get("universal_valuation_contract") or {}
        fresh.append({
            "schema_version": "1.0", "forecast_id": forecast_id,
            "ticker": ticker, "forecast_date": str((committee.get("review") or {}).get("as_of") or path.stem[-10:])[:10],
            "committee_ref": committee_ref, "committee_packet_hash": packet_hash or None,
            "decision_price": (valuation.get("inputs") or {}).get("price"),
            "power_zone": (contract.get("method_route") or valuation.get("valuation_method_route") or {}).get("profile_id"),
            "votes": votes, "outcome_horizons_months": [1, 3, 6, 12, 24],
            "actionable": False,
            "authority": "method_evaluation_only_no_capital_authority",
        })
        seen.add(forecast_id)
    if write:
        ledger.parent.mkdir(parents=True, exist_ok=True)
        with ledger.open("a", encoding="utf-8") as handle:
            for row in fresh:
                handle.write(json.dumps(row, sort_keys=True) + "\n")
    return fresh


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    rows = freeze(args.root, not args.dry_run)
    print(json.dumps({"new_forecasts": len(rows)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
