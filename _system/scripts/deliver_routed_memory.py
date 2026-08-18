#!/usr/bin/env python3
"""Deliver routed company observations to an append-only agent inbox.

Routing is not promotion: inbox rows retain their proposal status and source.
Only destinations backed by a real ``<ticker>/research`` directory are
acknowledged. Ambiguous fallback routes remain pending for human repair.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

import build_memory_triage as triage

ROOT = Path(__file__).resolve().parents[2]
INBOX_REL = Path("_system/memory/routed_observations.jsonl")


def deliver(root: Path = ROOT, limit: int = 0) -> dict:
    # The triage module uses repository-level path constants. Override them for
    # isolated tests and alternate roots, then restore them before returning.
    old_ledger, old_root = triage.LEDGER, triage.ROOT
    triage.ROOT = root
    triage.LEDGER = root / "_system/memory/triage_ledger.json"
    try:
        ledger = triage.load_ledger()
        inbox = root / INBOX_REL
        known: set[str] = set()
        if inbox.exists():
            for line in inbox.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    try:
                        known.add(str(json.loads(line).get("proposal_id")))
                    except json.JSONDecodeError:
                        continue

        eligible = []
        ambiguous = 0
        for proposal_id, entry in sorted((ledger.get("decisions") or {}).items()):
            if entry.get("decision") != "routed" or entry.get("delivery_status") == "acknowledged":
                continue
            destination = str(entry.get("destination") or "")
            target = root / destination
            if not destination.endswith("/research") or not target.is_dir():
                ambiguous += 1
                continue
            eligible.append((proposal_id, entry))
        if limit > 0:
            eligible = eligible[:limit]

        inbox.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        if eligible:
            with inbox.open("a", encoding="utf-8") as handle:
                for proposal_id, entry in eligible:
                    if proposal_id not in known:
                        payload = {
                            "schema_version": "1.0",
                            "observation_id": hashlib.sha256(
                                f"{proposal_id}|{entry.get('destination')}".encode()
                            ).hexdigest()[:24],
                            "proposal_id": proposal_id,
                            "ticker": str(entry["destination"]).split("/", 1)[0],
                            "destination": entry["destination"],
                            "content": entry.get("content"),
                            "source_ref": entry.get("source_ref"),
                            "routed_on": entry.get("date"),
                            "status": "proposed_observation",
                            "delivered_on": date.today().isoformat(),
                        }
                        handle.write(json.dumps(payload, sort_keys=True,
                                                ensure_ascii=False) + "\n")
                        known.add(proposal_id)
                        written += 1
                    # Presence in the canonical inbox is the delivery proof.
                    entry["delivery_status"] = "acknowledged"
                    entry["delivery_acknowledged_at"] = date.today().isoformat()
                    entry["applied_ref"] = str(INBOX_REL).replace("\\", "/")
            triage.save_ledger(ledger)
        return {"eligible": len(eligible), "written": written,
                "acknowledged": len(eligible), "ambiguous_pending": ambiguous}
    finally:
        triage.LEDGER, triage.ROOT = old_ledger, old_root


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--limit", type=int, default=0,
                        help="maximum deliveries; 0 delivers the full backlog")
    args = parser.parse_args()
    print(json.dumps(deliver(args.root, args.limit), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
